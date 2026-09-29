# -*- coding: utf-8 -*-
"""跨端事件契约。先定义格式,Phase 1 不接线。
三端开发均 import 此文件,确保发的信号对方能读懂。

使用方式:
  from overseas_shared.events import VOCAlertToB
  alert = VOCAlertToB(brand="BYD", country="DE", sentiment="抱怨", severity="high")
  # 序列化为 JSON → 写入 events 表或消息队列
  # 对端 import 同一个类,反序列化后即可消费
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class VOCAlertToB:
    """C 端 → B 端:VOC 舆情告警。
    C 端情感引擎检测到某品牌某国负面情绪激增时发出。
    B 端收到后:匹配该国法规 → 标记 P0 缺口 → 生成客户保全话术。"""
    brand: str                           # 品牌,如 "BYD"
    country: str                         # ISO2 国家码,如 "DE"
    sentiment: str                       # 主导情感,如 "抱怨" / "愤怒" / "担忧"
    topic: str = ""                      # 激增话题,如 "刹车异响" / "续航虚标"
    severity: str = "medium"             # high / medium / low
    regulation_hints: list[str] = field(default_factory=list)  # 推测相关法规关键词
    signal_count: int = 0                # 信号数量
    detected_at: str = ""                # ISO datetime


@dataclass
class RegulationChange:
    """B 端 → C 端 + KOL 端:法规变更通知。
    B 端法规库新增/修订/废止某法规时发出。
    C 端收到后:标记受影响车型的营销文案待复核。
    KOL 端收到后:标记受影响 KOL 的旧话术待更新。"""
    regulation_id: str                   # REG-001
    regulation_name: str = ""            # 法规名称
    country: list[str] = field(default_factory=list)   # 影响国家(ISO2)
    change_type: str = "生效"            # 生效 / 修订 / 废止
    summary: str = ""                    # 变更摘要(一句话)
    affected_scenarios: list[str] = field(default_factory=list)  # 零售/车队/公交
    affected_brands: list[str] = field(default_factory=list)     # 影响的汽车品牌
    published_at: str = ""               # ISO datetime


@dataclass
class KOLRiskAlert:
    """KOL 端 → B 端:KOL 内容合规风险告警。
    KOL 平台检测到某达人内容引发负面或踩法规红线时发出。
    B 端收到后:匹配法规 → 评估客户影响 → 生成应对建议。"""
    brand: str                           # 品牌
    country: str                         # ISO2
    creator_name: str = ""               # KOL 名称
    platform: str = ""                   # YouTube / TikTok / Instagram
    severity: str = "medium"             # high / medium / low
    topic: str = ""                      # 争议话题
    regulation_hint: str = ""            # KOL 端推测踩了哪条法规红线
    detected_at: str = ""                # ISO datetime
