from __future__ import annotations

# Python standard library
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

# Third-party libraries
import feedparser
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from db import DATABASE_URL, create_tables, get_session
from models import IntelligenceItem, utc_now


# 1. Project paths and database settings (shared data layer for SQLite/PostgreSQL)
BASE_DIR = Path(__file__).resolve().parent


def init_database() -> None:
    """
    Create the intelligence_items table if it does not exist.
    Existing tables and data are preserved.
    """

    create_tables()


# 4. RSS source settings

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


# 5. Fetch logging
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "rss_fetcher.log"

def setup_logger() -> logging.Logger:
    """
    Create the logger.

    Run records are written to both:
    1. The VS Code terminal.
    2. logs/rss_fetcher.log.
    """

    LOG_DIR.mkdir(exist_ok=True)

    logger = logging.getLogger("rss_fetcher")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Avoid adding duplicate log handlers.
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Terminal output
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Log file
    file_handler = logging.FileHandler(
        LOG_FILE,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


logger = setup_logger()


# 6. Clean HTML text from RSS fields

def clean_text(value: Any) -> str:
    """
    Remove HTML tags, extra whitespace, and special entities from summaries.

    Example:
    <p>New regulation</p>

    Becomes:
    New regulation
    """

    if value is None:
        return ""

    text = html.unescape(str(value))

    # Remove tags such as <p>, <br>, and <strong>.
    text = re.sub(r"<[^>]+>", " ", text)

    # Normalize newlines and repeated whitespace.
    text = " ".join(text.split())

    return text.strip()


# 7. Read the RSS publication date

def get_published_time(
    entry: Any,
) -> datetime | None:
    """
    RSS feeds may use different time fields, so check published, updated, and created in order.
    """

    parsed_time = (
        entry.get("published_parsed")
        or entry.get("updated_parsed")
        or entry.get("created_parsed")
    )

    if parsed_time is None:
        return None

    # feedparser returns a UTC time tuple.
    timestamp = calendar.timegm(parsed_time)

    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    )


# 8. Download and parse an RSS feed

def load_rss(url: str, retries: int = 3):
    """
    Download the raw RSS content and pass it to feedparser for parsing.
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
            raise  # Do not retry explicit HTTP errors.
        except (URLError, TimeoutError) as error:
            last_error = error
            logger.warning("Request attempt %s/%s failed; retrying: %s", attempt, retries, error)
            if attempt < retries:
                time.sleep(2 ** (attempt - 1))
    raise last_error or RuntimeError("RSSRequest failed")


# 9. Normalize fields across RSS feeds

def normalize_entry(
    entry: Any,
    source_name: str,
) -> dict[str, Any]:
    """
    Normalize data from different sources into these fields:

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
        title = "Untitled"

    return {
        "source": source_name,
        "title": title,
        "link": link,
        "summary": summary,
        "published_at": published_at,
    }


# 10. Save one intelligence item to the database

def save_item(
    session: Session,
    item: dict[str, Any],
) -> str:
    """
    Save one RSS item.

    Return values:
    new       = successfully added
    duplicate = already exists in the database
    """

    # Check for an existing item by its source URL.
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
        # Handle the rare case where the same link is inserted concurrently.
        session.rollback()
        return "duplicate"

    except SQLAlchemyError:
        session.rollback()
        raise

    return "new"


# 11. Fetch one RSS source

def fetch_one_rss(
    source: dict[str, Any],
) -> dict[str, int]:
    """
    Fetch one source and save its results to the database.
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
    logger.info("Starting source fetch: %s", source_name)
    logger.info("RSS URL: %s", rss_url)

    if not source.get("enabled", True):
        logger.info("Source is disabled; skipping.")
        return result

    try:
        status_code, feed = load_rss(rss_url)

    except HTTPError as error:
        result["error"] += 1

        logger.error(
            "HTTP request failed: source=%s, status=%s",
            source_name,
            error.code,
        )

        return result

    except URLError as error:
        result["error"] += 1

        logger.error(
            "Network connection failed: source=%s, error=%s",
            source_name,
            error.reason,
        )

        return result

    except TimeoutError:
        result["error"] += 1

        logger.error(
            "Request timed out: source=%s",
            source_name,
        )

        return result

    except Exception as error:
        result["error"] += 1

        logger.exception(
            "Unexpected fetch error: source=%s, error=%s",
            source_name,
            error,
        )

        return result

    result["read"] = len(feed.entries)

    logger.info("HTTP status: %s", status_code)
    logger.info("Raw entries read: %s", result["read"])

    if getattr(feed, "bozo", False):
        logger.warning(
            "RSS parsing warning: source=%s, details=%s",
            source_name,
            getattr(
                feed,
                "bozo_exception",
                "Unknown parsing warning",
            ),
        )

    if not feed.entries:
        result["error"] += 1

        logger.error(
            "No RSS entries found: source=%s",
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

            # A missing link prevents users from viewing the source and reliable deduplication.
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
                    "Database save failed: source=%s, title=%s, error=%s",
                    source_name,
                    item["title"],
                    error,
                )

                continue

            if save_result == "new":
                result["new"] += 1

            else:
                result["duplicate"] += 1

            # Preview only the first five entries in the terminal; save every item.
            if preview_count < 5:
                preview_count += 1

                print("-" * 70)
                print(f"Preview item {preview_count}")
                print("Source: ", item["source"])
                print("Title: ", item["title"])
                print("Link: ", item["link"])
                print("Summary: ", item["summary"])
                print("Publication Date:", item["published_at"])

    logger.info(
        "Source=%s | Read=%s | Added=%s | Duplicates=%s | "
        "Skipped=%s | Errors=%s",
        source_name,
        result["read"],
        result["new"],
        result["duplicate"],
        result["skipped"],
        result["error"],
    )

    return result


# 12. Fetch all sources

def run_all_sources() -> None:
    """
    Initialize database tables, then fetch every configured RSS source.
    """

    init_database()

    logger.info("Starting RSS fetch task")
    logger.info("Database: %s", DATABASE_URL)

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
        "All sources complete | Total read=%s | Total added=%s | "
        "Total duplicates=%s | Total skipped=%s | Total errors=%s",
        totals["read"],
        totals["new"],
        totals["duplicate"],
        totals["skipped"],
        totals["error"],
    )


# 13. Run manually or on a schedule

def main() -> None:
    """
    By default, run once.

    With --loop, repeat at the specified interval in minutes.
    """

    parser = argparse.ArgumentParser(
        description="Fetch RSS items and save them to the intelligence_items table"
    )

    parser.add_argument(
        "--loop",
        action="store_true",
        help="Enable scheduled repeated fetching",
    )

    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=60,
        help="Interval between fetches in minutes (default: 60)",
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
        "Scheduled mode started; fetching every %s minutes.",
        interval_minutes,
    )

    try:
        while True:
            run_all_sources()

            logger.info(
                "Fetch cycle complete; waiting %s minutes.",
                interval_minutes,
            )

            time.sleep(
                interval_minutes * 60
            )

    except KeyboardInterrupt:
        logger.info("The user stopped the scheduled fetcher.")


if __name__ == "__main__":
    main()
