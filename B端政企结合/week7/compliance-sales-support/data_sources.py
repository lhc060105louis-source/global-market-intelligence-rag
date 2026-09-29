# -*- coding: utf-8 -*-
"""数据源目录。整合组内 Week1-2 调研的所有公开数据来源。
字段:name / url / type(数据类型) / frequency(更新频率) / access(获取方式) / free(是否免费) / module(所属模块) / notes
"""
SOURCES = [
  # ── 法规与政策 ──
  {"name": "EUR-Lex 欧盟法律数据库", "url": "https://eur-lex.europa.eu", "type": "法规原文",
   "frequency": "随法规颁布更新", "access": "API / 网页搜索", "free": True,
   "module": "法规与政策", "notes": "官方法律文本,支持按编号、日期、主题检索;有 RSS 订阅。"},
  {"name": "European Commission 政策页面", "url": "https://commission.europa.eu", "type": "政策公告",
   "frequency": "不定期", "access": "网页 / 新闻订阅", "free": True,
   "module": "法规与政策", "notes": "电池法规、AFIR、AI Act 等核心法规的官方政策背景。"},
  {"name": "UNECE WP.29 车辆法规", "url": "https://unece.org/transport/wp29", "type": "车辆技术法规",
   "frequency": "不定期", "access": "网页下载", "free": True,
   "module": "法规与政策", "notes": "R155(网络安全)、R156(软件更新)等 UN 法规原文。"},
  {"name": "UK Parliament 立法追踪", "url": "https://www.legislation.gov.uk", "type": "英国法规",
   "frequency": "随立法更新", "access": "API / 网页", "free": True,
   "module": "法规与政策", "notes": "英国脱欧后独立法规体系;支持 RSS 按主题订阅。"},
  # ── 行业数据 ──
  {"name": "ACEA 欧洲汽车制造商协会", "url": "https://www.acea.auto", "type": "注册量/市场份额",
   "frequency": "月度/季度", "access": "网页 / 报告下载", "free": True,
   "module": "行业数据", "notes": "EU 乘用车与商用车注册量、动力结构、保有量数据。"},
  {"name": "EAFO 欧洲替代燃料观测站", "url": "https://alternative-fuels-observatory.ec.europa.eu", "type": "充电基础设施",
   "frequency": "月度更新", "access": "网页 / 交互仪表盘", "free": True,
   "module": "行业数据", "notes": "EU27 公共充电点、HDV 充电网络、替代燃料车辆数据。"},
  {"name": "Euro NCAP 安全评级", "url": "https://www.euroncap.com", "type": "安全测评",
   "frequency": "年度/协议更新", "access": "网页", "free": True,
   "module": "行业数据", "notes": "2026 起四阶段评分体系;可用于竞品安全对标。"},
  {"name": "J.D. Power IQS/CSI", "url": "https://www.jdpower.com", "type": "质量/满意度",
   "frequency": "年度", "access": "报告购买 / 二手资料", "free": False,
   "module": "行业数据", "notes": "中国有 NEV-IQS 报告;欧洲数据需企业权限。"},
  {"name": "Autovista24 残值数据", "url": "https://autovista24.autovistagroup.com", "type": "二手车残值",
   "frequency": "月度/季度", "access": "网页", "free": True,
   "module": "行业数据", "notes": "欧洲分动力类型三年残值率;部分深度数据需订阅。"},
  # ── 政企商机 ──
  {"name": "TED 欧盟采购公告", "url": "https://ted.europa.eu", "type": "政府采购公告",
   "frequency": "每日更新", "access": "网页 / RSS / API", "free": True,
   "module": "政企商机", "notes": "欧盟公开采购入口,支持 CPV 编码、Expert Search;有 RSS 订阅。"},
  {"name": "GOV.UK Find a Tender", "url": "https://www.find-tender.service.gov.uk", "type": "英国政府采购",
   "frequency": "每日更新", "access": "网页 / API", "free": True,
   "module": "政企商机", "notes": "英国公共采购平台;LEVI 充电、电动公交项目。"},
  {"name": "Innovate UK 创新基金", "url": "https://iuk-business-connect.org.uk", "type": "创新项目/资金",
   "frequency": "项目制", "access": "网页", "free": True,
   "module": "政企商机", "notes": "充电、能源系统、超快充示范项目资金。"},
  {"name": "EU Publications Office 采购详情", "url": "https://op.europa.eu/en/web/public-procurement", "type": "公共采购详情",
   "frequency": "不定期", "access": "网页", "free": True,
   "module": "政企商机", "notes": "项目级采购详情;如北马其顿公交、罗马尼亚电动公交。"},
  # ── 竞品与市场 ──
  {"name": "Reuters / JATO 市场分析", "url": "https://www.reuters.com/business/autos-transportation/", "type": "市场份额/竞品",
   "frequency": "月度/季度", "access": "网页", "free": True,
   "module": "竞品与市场", "notes": "中国品牌欧洲份额、BYD 等品牌注册量数据。"},
  {"name": "ADAC 德国车辆故障统计", "url": "https://www.adac.de/rund-ums-fahrzeug/tests/pannenstatistik/", "type": "可靠性数据",
   "frequency": "年度", "access": "网页", "free": True,
   "module": "竞品与市场", "notes": "德国权威车辆可靠性;可作售后信任背书。"},
  {"name": "ECFR 欧洲外交关系委员会", "url": "https://ecfr.eu", "type": "政策/安全分析",
   "frequency": "不定期", "access": "网页", "free": True,
   "module": "竞品与市场", "notes": "中国 EV 数据安全、联网汽车安全风险等政策分析。"},
  # ── 企业采购 ──
  {"name": "Volkswagen Group Supplier Portal", "url": "https://supplier.volkswagen-group.com/", "type": "供应商门户",
   "frequency": "不定期", "access": "网页(需注册)", "free": True,
   "module": "企业采购", "notes": "大众动力电池、Unified Cell 等采购方向;非 RFP 公示,作为商机监测入口。"},
  {"name": "Mercedes-Benz Supplier Portal", "url": "https://supplier.mercedes-benz.com/", "type": "供应商门户",
   "frequency": "不定期", "access": "网页(需注册)", "free": True,
   "module": "企业采购", "notes": "高端纯电车型动力电池、联合研发采购方向。"},
  {"name": "Stellantis Supplier Portal", "url": "https://suppliers.stellantis.com/", "type": "供应商门户",
   "frequency": "不定期", "access": "网页(需注册)", "free": True,
   "module": "企业采购", "notes": "西班牙 LFP 电池工厂供应链;合资建厂机会。"},
  {"name": "Ford Supplier Portal", "url": "https://supplier.ford.com/", "type": "供应商门户",
   "frequency": "不定期", "access": "网页(需注册)", "free": True,
   "module": "企业采购", "notes": "欧洲电动商用车动力电池、供应链采购方向。"},
]

# 按模块分组
MODULES = ["法规与政策", "行业数据", "政企商机", "竞品与市场", "企业采购"]
# 获取方式枚举
ACCESS_METHODS = ["API / 网页搜索", "API / 网页", "网页", "网页 / RSS / API", "网页 / 报告下载",
                  "网页 / 交互仪表盘", "网页 / 新闻订阅", "网页(需注册)", "网页下载",
                  "报告购买 / 二手资料"]
