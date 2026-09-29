from pathlib import Path


HTML = (Path(__file__).resolve().parent.parent / "static" / "index.html").read_text(encoding="utf-8")


def test_grouped_navigation_preserves_existing_modules_through_legacy_routes():
    assert "let currentPage='home'" in HTML
    for page in ("dashboard", "intel", "regulations", "projects", "workspace", "enterprises", "partners", "locked", "clients", "reports"):
        assert f"{page}:[" in HTML
    for marker in ("信息与决策", "首页", "情报中心", "项目中心", "落地与服务", "企业与伙伴", "服务中心"):
        assert marker in HTML
    assert "loadInformationHub" in HTML
    assert "loadProjectHub" in HTML
    assert "loadEcosystemHub" in HTML


def test_secondary_tools_are_not_primary_navigation_items():
    assert "_hasPerm('intelligence.fetch')" in HTML
    assert "管理员设置" in HTML
    assert "套餐与权限" in HTML
    assert "navigate('newproject')" in HTML


def test_dashboard_uses_action_oriented_home_layout():
    for marker in (
        "项目组合进度", "风险优先级", "优先项目机会", "系统与数据状态",
        "合规准备度", "本周建议", "按你的角色开始", "三个问题，一条落地路径",
        "为什么不是通用招标平台",
    ):
        assert marker in HTML
    assert "async function _loadDashboardLegacy(el)" in HTML
    assert "async function loadDashboard(el)" in HTML
    assert "class='home-hero'" in HTML
    assert "fetch('/api/product/positioning')" in HTML
    assert "function openPersonaPath(index)" in HTML
    assert "function openScenarioPath(index)" in HTML
    assert "positioning.personas" in HTML
    assert "positioning.scenarios" in HTML


def test_figma_intelligence_sections_are_present():
    for marker in ("重点情报", "本周风险分布", "近期项目机会", "全部情报", "今日建议"):
        assert marker in HTML
    assert "_esc(i.title)" in HTML
    assert "rel='noopener noreferrer'" in HTML


def test_figma_regulation_library_sections_are_present():
    for marker in ("欧洲汽车法规数据库", "必须准备的材料", "风险等级定义", "即将生效", "reg-detail-panel"):
        assert marker in HTML
    assert "encodeURIComponent(rid)" in HTML
    assert "_safeUrl(reg.official_source)" in HTML


def test_figma_project_opportunity_sections_are_present():
    for marker in ("欧洲项目机会池", "30天内截止", "商业价值评分", "项目评分拆解", "关键缺口"):
        assert marker in HTML
    assert "function projectDoFilter()" in HTML
    assert "function _exportProjects()" in HTML


def test_figma_support_workspace_and_legacy_client_insights_are_present():
    for marker in ("法规专家咨询", "项目投标支持", "数据与系统问题", "支持工单", "服务表现"):
        assert marker in HTML
    assert "function supportSelectTicket(id)" in HTML
    assert "async function _loadClientInsights(el)" in HTML
    assert "客户画像与销售支持" in HTML


def test_figma_project_workspace_and_legacy_detail_are_present():
    for marker in ("项目推进工作台", "待处理任务", "任务推进列表", "项目推进进度", "下一步任务"):
        assert marker in HTML
    assert "function _workspaceFilter()" in HTML
    assert "async function _loadWorkspaceDetailLegacy(el)" in HTML
    assert "返回工作台总览" in HTML


def test_figma_enterprise_profiles_are_present():
    for marker in ("企业能力档案库", "合作资料", "合作能力评估", "认证资质文件", "匹配伙伴"):
        assert marker in HTML
    assert "function enterpriseSelect(idx)" in HTML
    assert "fetch('/api/matching/profiles')" in HTML


def test_enterprise_capability_editor_and_personalized_matching_are_present():
    for marker in ("维护本企业能力", "生成匹配", "部分满足", "匹配可信度", "建议行动"):
        assert marker in HTML
    assert "async function loadEnterpriseProfiles(el)" in HTML
    assert "method:'PUT'" in HTML
    assert "profile_id=" in HTML


def test_admission_decision_and_gap_matrix_are_present():
    for marker in (
        "企业级项目准入结论", "Go 建议推进", "Hold 补缺口后复核",
        "要求—证据—状态—缺口矩阵", "需人工复核", "生成准入诊断",
    ):
        assert marker in HTML
    assert "function _renderAdmissionMatch(m)" in HTML
    assert "m.requirement_gap_matrix" in HTML
    assert "m.hard_gates" in HTML


def test_gap_driven_partner_recommendations_are_connected():
    for marker in (
        "缺口驱动伙伴推荐", "生成补位伙伴", "verification_status_label",
        "暂无公开候选覆盖", "推荐仅对应未关闭缺口",
    ):
        assert marker in HTML
    assert "async function loadGapPartners()" in HTML
    assert "/api/matching/partner-recommendations/" in HTML
    assert "p.solves_gaps" in HTML


def test_one_page_admission_demo_case_is_present():
    for marker in (
        "示范案例", "现实结论", "方法结论", "要求—材料—状态—缺口表",
        "3家缺口驱动伙伴候选", "伙伴推荐规则", "打印一页结果",
    ):
        assert marker in HTML
    assert "async function loadAdmissionDemoCase(el)" in HTML
    assert "fetch('/api/matching/demo-case')" in HTML
    assert "current_decision" in HTML
    assert "method_decision" in HTML


def test_admission_gaps_flow_into_workspace_tasks():
    for marker in ("生成缺口任务", "查看工作台", "准入诊断生成", "缺口整改"):
        assert marker in HTML
    assert "async function createGapTasks()" in HTML
    assert "'/api/tasks/from-gaps/'" in HTML
    assert "async function updateGapProjectTask(taskId,status)" in HTML
    assert "fetch('/api/tasks')" in HTML


def test_figma_partner_matching_is_present():
    for marker in ("欧洲合作伙伴库", "高匹配伙伴", "合作潜力", "伙伴匹配分析", "匹配优势"):
        assert marker in HTML
    assert "function partnerFilter()" in HTML
    assert "function partnerFullAssessment()" in HTML
    assert "project.matching_detail" in HTML


def test_figma_locked_status_is_present_and_uses_permissions():
    for marker in ("可访问企业", "已锁定企业", "待审批申请", "权限通过率", "锁定原因", "访问权限"):
        assert marker in HTML
    assert "function lockedRequest(idx)" in HTML
    assert "function lockedExport()" in HTML
    assert "reports.export" in HTML


def test_demo_mode_switch_replaces_login_ui():
    for marker in ('value="visitor">游客', 'value="professional">专业版', 'value="enterprise">企业版', 'value="admin">管理员'):
        assert marker in HTML
    assert "_switchDemoMode(this.value)" in HTML
    assert "/api/auth/demo-mode" in HTML
    assert "authEmail" not in HTML
    assert "登录 / 注册" not in HTML


def test_intelligence_displays_automatic_scheduler_status():
    assert "fetch('/api/intelligence/scheduler')" in HTML
    assert "自动抓取已开启" in HTML
    assert "下次自动抓取" in HTML


def test_intelligence_saved_search_and_alert_settings_are_connected():
    for marker in (
        "我的情报监控", "保存搜索与提醒", "提醒频率", "提醒已开启",
        "当前仅记录提醒计划", "应用筛选", "搜索标题或摘要",
    ):
        assert marker in HTML
    assert "fetch('/api/intelligence/saved-searches')" in HTML
    assert "async function createSavedSearch()" in HTML
    assert "async function toggleSavedSearch(id,enabled)" in HTML
    assert "async function deleteSavedSearch(id)" in HTML
    assert "function applySavedSearch(index)" in HTML


def test_week7_locked_project_and_sprint_flow_are_connected():
    for marker in (
        "评分依据与关键缺口已锁定", "升级并解锁", "申请14天项目冲刺",
        "申请已成功提交", "管理员审核并启动", "14天交付路线", "阶段任务",
    ):
        assert marker in HTML
    assert "function _openProjectUnlock(projectId)" in HTML
    assert "async function openSprintApplication(projectId=0)" in HTML
    assert "fetch('/api/sprints'" in HTML
    assert "loadSprintWorkbench" in HTML


def test_pricing_separates_subscription_from_sprint_service():
    for marker in ("免费版", "专业版", "企业版", "标准专项服务", "14天冲刺专项", "单项目专项服务"):
        assert marker in HTML
    assert "async function loadEnterpriseAccessStatus(el)" in HTML
    assert "async function loadLockedStatus(el)" in HTML


def test_commercial_pricing_boundaries_and_sla_are_present():
    for marker in (
        "待验证报价假设", "平台自动与分析师人工的边界", "14天固定交付节奏",
        "申请材料与范围确认", "固定交付物与SLA", "为什么14天更贵",
        "客户配合、延期与变更", "明确不承诺", "常见问题", "升级路径",
    ):
        assert marker in HTML
    assert "fetch('/api/commercial/offers')" in HTML
    assert "function commercialSelect(offerId)" in HTML
    assert "openSprintApplication()" in HTML
    for marker in (
        "资料与资源准备", "sprintMaterial", "客户预期截标时间", "24小时响应资源",
        "sprintScopeConfirmed", "sprintCooperationConfirmed",
    ):
        assert marker in HTML
