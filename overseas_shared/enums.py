# -*- coding: utf-8 -*-
"""三端统一枚举。C端/KOL端/B端均 import 此文件,保证同一个值在三端是同一个字符串。"""
from enum import Enum


class Country(str, Enum):
    """
    国家(ISO 3166-1 alpha-2)。三端统一,替代 C端"德国"、KOL端"DE"、B端"EU全域"。

    ## 枚举值确认清单
    | 成员名 | ISO2 码 | 中文名称 |
    |--------|---------|----------|
    | DE     | DE      | 德国     |
    | FR     | FR      | 法国     |
    | UK     | UK      | 英国     |
    | ES     | ES      | 西班牙   |
    | IT     | IT      | 意大利   |
    | EU     | EU      | EU 层面  |
    """
    DE = "DE"
    FR = "FR"
    UK = "UK"
    ES = "ES"
    IT = "IT"
    EU = "EU"


class RegType(str, Enum):
    """
    法规类型。对齐商分 Excel 主表的法规分类。

    ## 枚举值确认清单
    | 成员名        | 中文标签 |
    |---------------|----------|
    | ACCESS        | 准入认证 |
    | BATTERY       | 电池合规 |
    | CYBER         | 网络安全 |
    | DATA_AI       | 数据与AI |
    | CARBON        | 碳合规   |
    | EMISSION      | 排放合规 |
    | MATERIAL      | 材料合规 |
    | PROCUREMENT   | 公共采购 |
    | SAFETY        | 安全测评 |
    | INFRA         | 基础设施 |
    """
    ACCESS = "准入认证"
    BATTERY = "电池合规"
    CYBER = "网络安全"
    DATA_AI = "数据与AI"
    CARBON = "碳合规"
    EMISSION = "排放合规"
    MATERIAL = "材料合规"
    PROCUREMENT = "公共采购"
    SAFETY = "安全测评"
    INFRA = "基础设施"


class ImpactLevel(str, Enum):
    """
    影响程度。

    ## 枚举值确认清单
    | 成员名 | 中文标签 |
    |--------|----------|
    | HIGH   | 高       |
    | MEDIUM | 中       |
    | LOW    | 低       |
    """
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class Priority(str, Enum):
    """
    材料优先级(P0-P3)。对齐 PRD 8.3。

    ## 枚举值确认清单
    | 成员名 | 取值 | 说明                                         |
    |--------|------|----------------------------------------------|
    | P0     | P0   | 必备:缺失直接影响准入/投标资格               |
    | P1     | P1   | 重要:影响评分/信任/谈判                      |
    | P2     | P2   | 加分:增强竞争力                              |
    | P3     | P3   | 关注:持续跟踪,当前不一定适用                 |
    """
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class MaterialStatus(str, Enum):
    """
    材料准备状态(7 种)。对齐 PRD 8.4。

    ## 枚举值确认清单
    | 成员名         | 中文标签 | 说明                                     |
    |----------------|----------|------------------------------------------|
    | UNCONFIRMED    | 待确认   | 尚未核实                                 |
    | READY          | 已准备   | 文件存在、有效、已审核                   |
    | MISSING        | 缺失     | 确认需要但当前没有                       |
    | NEED_UPDATE    | 待更新   | 存在旧版本,需更新                        |
    | REVIEWING      | 审核中   | 已提交,等待确认                          |
    | EXPIRED        | 已过期   | 超有效期或被新版本取代                   |
    | NOT_APPLICABLE | 不适用   | 经授权确认不适用                         |
    """
    UNCONFIRMED = "待确认"
    READY = "已准备"
    MISSING = "缺失"
    NEED_UPDATE = "待更新"
    REVIEWING = "审核中"
    EXPIRED = "已过期"
    NOT_APPLICABLE = "不适用"


class ClientType(str, Enum):
    """
    B 端客户类型。对齐 Week2 销售支持模板。

    ## 枚举值确认清单
    | 成员名             | 中文标签         |
    |--------------------|------------------|
    | GOVERNMENT         | 政府 / 市政      |
    | BUS_OPERATOR       | 公交运营商       |
    | LOGISTICS          | 物流车队         |
    | ENTERPRISE_FLEET   | 企业内部车队     |
    | MOBILITY_PLATFORM  | 出行平台         |
    """
    GOVERNMENT = "政府 / 市政"
    BUS_OPERATOR = "公交运营商"
    LOGISTICS = "物流车队"
    ENTERPRISE_FLEET = "企业内部车队"
    MOBILITY_PLATFORM = "出行平台"


class SourceLevel(str, Enum):
    """
    来源可靠性等级(对齐 V2.0 PRD 9.3)。

    ## 枚举值确认清单
    | 成员名 | 取值 | 说明                                 |
    |--------|------|--------------------------------------|
    | T1     | T1   | 官方一手(EUR-Lex, TED, European Commission) |
    | T2     | T2   | 权威聚合(ACEA, EAFO, Euro NCAP)      |
    | T3     | T3   | 行业媒体/研究(JATO, Reuters, Autovista) |
    | T4     | T4   | 未核验(仅作线索,不得进入正式报告)    |
    """
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"


class RegulationStatus(str, Enum):
    """
    法规审核状态（Regulation 专用）。

    ## 枚举值确认清单
    | 成员名     | 中文标签 |
    |------------|----------|
    | DRAFT      | 草稿     |
    | PENDING    | 待审核   |
    | APPROVED   | 已审核   |
    | DEPRECATED | 已失效   |
    """
    DRAFT = "草稿"
    PENDING = "待审核"
    APPROVED = "已审核"
    DEPRECATED = "已失效"


class ProjectStage(str, Enum):
    """
    政企项目阶段。

    ## 枚举值确认清单
    | 成员名      | 中文标签   |
    |-------------|------------|
    | LEAD        | 新线索     |
    | EVALUATING  | 评估中     |
    | PREPARING   | 准备投标   |
    | SUBMITTED   | 已提交     |
    | WON         | 中标       |
    | LOST        | 未中标     |
    | TERMINATED  | 终止       |
    """
    LEAD = "新线索"
    EVALUATING = "评估中"
    PREPARING = "准备投标"
    SUBMITTED = "已提交"
    WON = "中标"
    LOST = "未中标"
    TERMINATED = "终止"


class ProjectLevel(str, Enum):
    """
    项目投入等级。

    ## 枚举值确认清单
    | 成员名     | 中文标签   |
    |------------|------------|
    | PRIORITY   | 优先跟进   |
    | OBSERVING  | 持续观察   |
    | HOLD       | 暂缓投入   |
    """
    PRIORITY = "优先跟进"
    OBSERVING = "持续观察"
    HOLD = "暂缓投入"


class SourceType(str, Enum):
    """
    数据来源类型。

    ## 枚举值确认清单
    | 成员名      | 中文标签   |
    |-------------|------------|
    | REGULATION  | 法规       |
    | POLICY      | 政策       |
    | PROCUREMENT | 采购       |
    | INDUSTRY    | 行业数据   |
    | NEWS        | 新闻资讯   |
    """
    REGULATION = "法规"
    POLICY = "政策"
    PROCUREMENT = "采购"
    INDUSTRY = "行业数据"
    NEWS = "新闻资讯"


class AccessMethod(str, Enum):
    """
    数据获取方式。

    ## 枚举值确认清单
    | 成员名 | 中文标签 |
    |--------|----------|
    | API    | API      |
    | WEB    | 网页     |
    | RSS    | RSS      |
    | MANUAL | 人工     |
    """
    API = "API"
    WEB = "网页"
    RSS = "RSS"
    MANUAL = "人工"
