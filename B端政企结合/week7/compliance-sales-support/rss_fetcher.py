from __future__ import annotations

# Python标准库
import argparse
import calendar
import html
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# 第三方库
import feedparser
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from db import DATABASE_URL, create_tables, get_session
from models import IntelligenceItem, utc_now


# 1. 项目路径和数据库设置（复用平台统一数据层，兼容 SQLite/PostgreSQL）
BASE_DIR = Path(__file__).resolve().parent


def init_database() -> None:
    """
    如果intelligence_items表不存在，就自动创建。
    已存在时不会重复创建，也不会删除原有数据。
    """

    create_tables()


# 4. RSS来源设置

RSS_SOURCES = [
    {
        "name": "EUR-Lex",
        "url": (
            "https://eur-lex.europa.eu/"
            "EN/display-feed.rss?rssId=162"
        ),
        "enabled": True,
    },
    {
        "name": "UK Parliament",
        "url": (
            "https://bills.parliament.uk/"
            "rss/allbills.rss"
        ),
        "enabled": True,
    },
    {
        "name": "TED",
        "url": (
            "https://ted.europa.eu/en/simap/rss-feed/-/rss/generate"
            "?description=TED+%7C+Research+and+Development+%7C+%3A-++%7C+EN"
            "&fields=publication-date%2C+deadline-receipt-request%2C+notice-type"
            "&language=EN"
            "&limit="
            "&query=%28classification-cpv+IN+%28reco%29%29"
            "&scope="
            "&title=TED%3A"
        ),
        "enabled": True,
    },
]


# 5. 抓取日志设置
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "rss_fetcher.log"

def setup_logger() -> logging.Logger:
    """
    创建日志工具。

    运行记录会同时：
    1. 显示在VS Code终端；
    2. 保存到logs/rss_fetcher.log。
    """

    LOG_DIR.mkdir(exist_ok=True)

    logger = logging.getLogger("rss_fetcher")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # 避免重复创建日志处理器
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 终端显示
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # 日志文件
    file_handler = logging.FileHandler(
        LOG_FILE,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


logger = setup_logger()


# 6. 清理RSS中的HTML文本

def clean_text(value: Any) -> str:
    """
    清除摘要中的HTML标签、多余空格和特殊字符。

    例如：
    <p>New regulation</p>

    会变成：
    New regulation
    """

    if value is None:
        return ""

    text = html.unescape(str(value))

    # 删除<p>、<br>、strong等HTML标签
    text = re.sub(r"<[^>]+>", " ", text)

    # 合并换行和多余空格
    text = " ".join(text.split())

    return text.strip()


# 7. 读取RSS发布时间

def get_published_time(
    entry: Any,
) -> datetime | None:
    """
    不同RSS可能使用不同的时间字段，
    因此依次检查published、updated和created。
    """

    parsed_time = (
        entry.get("published_parsed")
        or entry.get("updated_parsed")
        or entry.get("created_parsed")
    )

    if parsed_time is None:
        return None

    # feedparser给出的是UTC时间元组
    timestamp = calendar.timegm(parsed_time)

    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    )


# 8. 下载和解析一个RSS

def load_rss(url: str, retries: int = 3):
    """
    下载RSS原始内容，再交给feedparser解析。
    """

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            request = Request(url, headers={
                "User-Agent": "Mozilla/5.0 OverseasIntelligenceRSS/1.0",
                "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*",
            })
            with urlopen(request, timeout=30) as response:
                status_code = response.status
                rss_content = response.read()
            return status_code, feedparser.parse(rss_content)
        except HTTPError:
            raise  # 明确 HTTP 错误不盲目重试
        except (URLError, TimeoutError) as error:
            last_error = error
            logger.warning("第%s/%s次请求失败，准备重试：%s", attempt, retries, error)
            if attempt < retries:
                time.sleep(2 ** (attempt - 1))
    raise last_error or RuntimeError("RSS请求失败")


# 9. 把不同RSS统一成相同字段

def normalize_entry(
    entry: Any,
    source_name: str,
) -> dict[str, Any]:
    """
    将不同来源的数据统一整理为：

    source
    title
    link
    summary
    published_at
    """

    title = clean_text(
        entry.get("title", "")
    )

    link = clean_text(
        entry.get("link", "")
    )

    summary = clean_text(
        entry.get("summary")
        or entry.get("description")
        or ""
    )

    published_at = get_published_time(entry)

    if not title:
        title = "无标题"

    return {
        "source": source_name,
        "title": title,
        "link": link,
        "summary": summary,
        "published_at": published_at,
    }


# 10. 把一条情报保存到数据库

def save_item(
    session: Session,
    item: dict[str, Any],
) -> str:
    """
    保存一条RSS数据。

    返回值：
    new       = 新增成功
    duplicate = 数据库中已经存在
    """

    # 根据原文链接检查是否已经存在
    existing_id = session.scalar(
        select(IntelligenceItem.id).where(
            IntelligenceItem.link == item["link"]
        )
    )

    if existing_id is not None:
        return "duplicate"

    database_item = IntelligenceItem(
        source=item["source"],
        title=item["title"],
        link=item["link"],
        summary=item["summary"],
        published_at=item["published_at"],
        fetched_at=utc_now(),
    )

    session.add(database_item)

    try:
        session.commit()

    except IntegrityError:
        # 处理极少数同时插入相同链接的情况
        session.rollback()
        return "duplicate"

    except SQLAlchemyError:
        session.rollback()
        raise

    return "new"


# 11. 抓取一个RSS来源

def fetch_one_rss(
    source: dict[str, Any],
) -> dict[str, int]:
    """
    抓取一个来源，并将结果存入数据库。
    """

    source_name = source["name"]
    rss_url = source["url"]

    result = {
        "read": 0,
        "new": 0,
        "duplicate": 0,
        "skipped": 0,
        "error": 0,
    }

    logger.info("=" * 70)
    logger.info("开始抓取来源：%s", source_name)
    logger.info("RSS地址：%s", rss_url)

    if not source.get("enabled", True):
        logger.info("该来源已经关闭，跳过。")
        return result

    try:
        status_code, feed = load_rss(rss_url)

    except HTTPError as error:
        result["error"] += 1

        logger.error(
            "HTTP请求失败：来源=%s，状态码=%s",
            source_name,
            error.code,
        )

        return result

    except URLError as error:
        result["error"] += 1

        logger.error(
            "网络连接失败：来源=%s，错误=%s",
            source_name,
            error.reason,
        )

        return result

    except TimeoutError:
        result["error"] += 1

        logger.error(
            "访问超时：来源=%s",
            source_name,
        )

        return result

    except Exception as error:
        result["error"] += 1

        logger.exception(
            "抓取发生未知错误：来源=%s，错误=%s",
            source_name,
            error,
        )

        return result

    result["read"] = len(feed.entries)

    logger.info("HTTP状态码：%s", status_code)
    logger.info("读取到原始条目：%s条", result["read"])

    if getattr(feed, "bozo", False):
        logger.warning(
            "RSS解析警告：来源=%s，内容=%s",
            source_name,
            getattr(
                feed,
                "bozo_exception",
                "未知解析警告",
            ),
        )

    if not feed.entries:
        result["error"] += 1

        logger.error(
            "没有读取到RSS内容：来源=%s",
            source_name,
        )

        return result

    preview_count = 0

    with get_session() as session:
        for entry in feed.entries:
            item = normalize_entry(
                entry=entry,
                source_name=source_name,
            )

            # 没有链接就无法查看原文，也无法稳定去重
            if not item["link"]:
                result["skipped"] += 1
                continue

            try:
                save_result = save_item(
                    session=session,
                    item=item,
                )

            except SQLAlchemyError as error:
                result["error"] += 1

                logger.exception(
                    "数据库保存失败：来源=%s，标题=%s，错误=%s",
                    source_name,
                    item["title"],
                    error,
                )

                continue

            if save_result == "new":
                result["new"] += 1

            else:
                result["duplicate"] += 1

            # 终端只预览前5条，数据库保存全部条目
            if preview_count < 5:
                preview_count += 1

                print("-" * 70)
                print(f"预览第 {preview_count} 条")
                print("来源：", item["source"])
                print("标题：", item["title"])
                print("链接：", item["link"])
                print("摘要：", item["summary"])
                print("发布时间：", item["published_at"])

    logger.info(
        "来源=%s | 读取=%s | 新增=%s | 重复=%s | "
        "跳过=%s | 错误=%s",
        source_name,
        result["read"],
        result["new"],
        result["duplicate"],
        result["skipped"],
        result["error"],
    )

    return result


# 12. 抓取所有来源

def run_all_sources() -> None:
    """
    初始化数据表，然后依次抓取所有RSS来源。
    """

    init_database()

    logger.info("RSS抓取任务开始")
    logger.info("数据库：%s", DATABASE_URL)

    totals = {
        "read": 0,
        "new": 0,
        "duplicate": 0,
        "skipped": 0,
        "error": 0,
    }

    for source in RSS_SOURCES:
        source_result = fetch_one_rss(source)

        for key in totals:
            totals[key] += source_result[key]

    logger.info("=" * 70)
    logger.info(
        "全部来源处理完成 | 总读取=%s | 总新增=%s | "
        "总重复=%s | 总跳过=%s | 总错误=%s",
        totals["read"],
        totals["new"],
        totals["duplicate"],
        totals["skipped"],
        totals["error"],
    )


# 13. 手动运行或定时运行

def main() -> None:
    """
    默认只运行一次。

    加上--loop后，按照指定分钟数循环运行。
    """

    parser = argparse.ArgumentParser(
        description="抓取RSS并存入intelligence_items表"
    )

    parser.add_argument(
        "--loop",
        action="store_true",
        help="开启定时循环抓取",
    )

    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=60,
        help="循环抓取间隔，默认60分钟",
    )

    args = parser.parse_args()

    if not args.loop:
        run_all_sources()
        return

    interval_minutes = max(
        1,
        args.interval_minutes,
    )

    logger.info(
        "定时模式已启动，每%s分钟抓取一次。",
        interval_minutes,
    )

    try:
        while True:
            run_all_sources()

            logger.info(
                "本轮完成，等待%s分钟。",
                interval_minutes,
            )

            time.sleep(
                interval_minutes * 60
            )

    except KeyboardInterrupt:
        logger.info("用户停止了定时抓取程序。")


if __name__ == "__main__":
    main()
