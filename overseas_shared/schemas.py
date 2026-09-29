# -*- coding: utf-8 -*-
"""三端共享实体字段定义。商分组可对照 Excel/PRD 审阅此文件。
字段名统一 snake_case,枚举使用 overseas_shared.enums。"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# enums 在本包内引用,不打乱 import 路径
# 如需类型提示: from overseas_shared.enums import Country, RegType, ...


@dataclass
class MaterialItem:
    """一条投标材料要求(对齐法规支持.xlsx 主表 + PRD 8.3-8.4)。"""
    name: str                              # 材料名称,如 "CSMS 证书"
    priority: str                          # P0 / P1 / P2 / P3
    status: str = "待确认"                 # 待确认/已准备/缺失/待更新/审核中/已过期/不适用
    owner: str = ""                        # 负责人
    due_date: str = ""                     # 截止日期


@dataclass
class Regulation:
    """法规主记录(对齐 PRD 9.3 Regulation 字段字典 + Excel 主表)。"""
    regulation_id: str                     # REG-001
    name: str                              # 法规名称
    official_number: str = ""              # 官方编号,如 (EU) 2023/1542
    issuer: str = ""                       # 发布机构
    type: str = ""                         # 法规类型(建议用 RegType 枚举值)
    country: list[str] = field(default_factory=list)  # 适用国家(ISO2),如 ["DE","EU"]
    applicable_product: list[str] = field(default_factory=list)
    effective_date: str = ""               # 生效日期
    impact_level: str = ""                 # 高 / 中 / 低
    core_requirement: str = ""             # 核心要求(人工核验摘要)
    official_source: str = ""              # 官方来源 URL
    last_verified_at: str = ""             # 最近核验日期
    status: str = "待审核"                 # 草稿/待审核/已审核/已失效
    version: str = "v1.0"
    materials: list[MaterialItem] = field(default_factory=list)  # 所需材料清单
    local_partner_duty: str = ""           # 本地合作方职责
    gap: str = ""                          # 合规缺口说明
    linked_intelligence_ids: list[str] = field(default_factory=list)


@dataclass
class Project:
    """政企采购项目(对齐 PRD 9.2 Project 字段字典 + 评分模型)。"""
    project_id: str                        # PRJ-001
    project_name: str                      # 公告正式名称
    country: str = ""                      # ISO2
    client_type: str = ""                  # 客户类型
    buyer_name: str = ""                   # 采购主体
    scenario: str = ""                     # 应用场景
    amount: float = 0.0                    # 合同金额
    currency: str = "EUR"
    deadline: str = ""
    source_url: str = ""
    description: str = ""
    stage: str = "评估中"                  # 新线索/评估中/准备投标/已提交/中标/未中标/终止
    scores: dict = field(default_factory=dict)   # 七维评分 {scale, buyer, technical, ...}
    total_score: int = 0
    project_level: str = "暂缓投入"        # 优先跟进/持续观察/暂缓投入
    linked_regulation_ids: list[str] = field(default_factory=list)


@dataclass
class ClientProfile:
    """B 端客户画像(对齐 Week2 销售支持模板)。"""
    client_type: str                       # 客户类型
    region: str = ""                       # 国家(ISO2)
    scenario: str = ""                     # 应用场景
    painpoints: list[str] = field(default_factory=list)
    focus_points: list[str] = field(default_factory=list)
    product_direction: list[str] = field(default_factory=list)
    tech_solution: list[str] = field(default_factory=list)
    service_plan: list[str] = field(default_factory=list)
    linked_regulations: list[str] = field(default_factory=list)


@dataclass
class DataSource:
    """公开数据来源(对齐 V2.0 PRD Source 实体)。"""
    source_id: str                         # SRC-001
    name: str                              # 来源名称
    type: str = ""                         # 数据类型(法规/政策/采购/行业数据...)
    level: str = "T4"                      # T1-T4 来源等级
    url: str = ""
    frequency: str = ""                    # 更新频率
    access_method: str = ""                # 获取方式(API/网页/RSS/人工)
    free: bool = True
    module: str = ""                       # 所属模块(法规与政策/行业数据/政企商机...)
    last_checked_at: str = ""
