from pathlib import Path


HTML = (Path(__file__).resolve().parent.parent / "static" / "index.html").read_text(encoding="utf-8")


def test_grouped_navigation_preserves_existing_modules_through_legacy_routes():
    assert "let currentPage='home'" in HTML
    for page in ("dashboard", "intel", "regulations", "projects", "workspace", "enterprises", "partners", "locked", "clients", "reports"):
        assert f"{page}:[" in HTML
    for marker in ("Information and Decisions", "Home", "Intelligence Center", "projectCenter", "Execution and Services", "Companies and Partners", "Service Center"):
        assert marker in HTML
    assert "loadInformationHub" in HTML
    assert "loadProjectHub" in HTML
    assert "loadEcosystemHub" in HTML


def test_secondary_tools_are_not_primary_navigation_items():
    assert "_hasPerm('intelligence.fetch')" in HTML
    assert "Administrator Settings" in HTML
    assert "Plans and Permissions" in HTML
    assert "navigate('newproject')" in HTML


def test_dashboard_uses_action_oriented_home_layout():
    for marker in (
        "Project Portfolio Overview", "Risk Priorities", "Priority Project Opportunities", "System and Data Status",
        "Compliance Readiness", "This Week's Recommendation", "Start by Role", "Three Issues, One Path to Action",
        "Why Not a Generic Tender Platform",
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
    for marker in ("Key Intelligence", "Risk Distribution This Week", "Recent Project Opportunities", "All Intelligence", "Today Recommendation"):
        assert marker in HTML
    assert "_esc(i.title)" in HTML
    assert "rel='noopener noreferrer'" in HTML


def test_figma_regulation_library_sections_are_present():
    for marker in ("European Automotive Regulation Library", "Required Materials", "Risk Level Definitions", "Effective Soon", "reg-detail-panel"):
        assert marker in HTML
    assert "encodeURIComponent(rid)" in HTML
    assert "_safeUrl(reg.official_source)" in HTML


def test_figma_project_opportunity_sections_are_present():
    for marker in ("European Project Opportunity Pool", "Deadline Within 30 Days", "Commercial Value Score", "Project Score Breakdown", "Key Gaps"):
        assert marker in HTML
    assert "function projectDoFilter()" in HTML
    assert "function _exportProjects()" in HTML


def test_figma_support_workspace_and_legacy_client_insights_are_present():
    for marker in ("Regulatory Advisory", "Project Tender Support", "Data and System Issues", "Support Tickets", "Service Performance"):
        assert marker in HTML
    assert "function supportSelectTicket(id)" in HTML
    assert "async function _loadClientInsights(el)" in HTML
    assert "Customer Profile and Sales Support" in HTML


def test_figma_project_workspace_and_legacy_detail_are_present():
    for marker in ("Project Progress Workspace", "Pending Tasks", "Task Progress List", "Project Progress", "Next-Step Tasks"):
        assert marker in HTML
    assert "function _workspaceFilter()" in HTML
    assert "async function _loadWorkspaceDetailLegacy(el)" in HTML
    assert "Back to Workspace Overview" in HTML


def test_figma_enterprise_profiles_are_present():
    for marker in ("Company Capability Profiles", "Partnership Information", "Partnership Capability Assessment", "Certification Credential Files", "Match Partners"):
        assert marker in HTML
    assert "function enterpriseSelect(idx)" in HTML
    assert "fetch('/api/matching/profiles')" in HTML


def test_enterprise_capability_editor_and_personalized_matching_are_present():
    for marker in ("Maintain Company Capabilities", "Generate Match", "Partially Satisfied", "Match Confidence", "Recommended Actions"):
        assert marker in HTML
    assert "async function loadEnterpriseProfiles(el)" in HTML
    assert "method:'PUT'" in HTML
    assert "profile_id=" in HTML


def test_admission_decision_and_gap_matrix_are_present():
    for marker in (
        "Company-Level Project Admission Decision", "Go Recommendation", "Hold and Reassess After Closing Gaps",
        "Requirement–Evidence–Status–Gap Matrix", "Requires Manual Review", "Generate Admission Assessment",
    ):
        assert marker in HTML
    assert "function _renderAdmissionMatch(m)" in HTML
    assert "m.requirement_gap_matrix" in HTML
    assert "m.hard_gates" in HTML


def test_gap_driven_partner_recommendations_are_connected():
    for marker in (
        "Gap-Driven Partner Recommendations", "Find Partners to Close Gaps", "verification_status_label",
        "No Public Candidate Coverage", "Recommendations Address Open Gaps Only",
    ):
        assert marker in HTML
    assert "async function loadGapPartners()" in HTML
    assert "/api/matching/partner-recommendations/" in HTML
    assert "p.solves_gaps" in HTML


def test_one_page_admission_demo_case_is_present():
    for marker in (
        "Demo Case", "Current Decision", "Method Decision", "Requirements, Materials, Status, and Gaps",
        "3 Gap-Driven Partner Candidates", "Partner Recommendation Rules", "Print One-Page Summary",
    ):
        assert marker in HTML
    assert "async function loadAdmissionDemoCase(el)" in HTML
    assert "fetch('/api/matching/demo-case')" in HTML
    assert "current_decision" in HTML
    assert "method_decision" in HTML


def test_admission_gaps_flow_into_workspace_tasks():
    for marker in ("Create Gap Tasks", "View Workspace", "Admission Assessment Created", "Resolve Gaps"):
        assert marker in HTML
    assert "async function createGapTasks()" in HTML
    assert "'/api/tasks/from-gaps/'" in HTML
    assert "async function updateGapProjectTask(taskId,status)" in HTML
    assert "fetch('/api/tasks')" in HTML


def test_figma_partner_matching_is_present():
    for marker in ("European Partner Directory", "High-Match Partners", "Partnership Potential", "Partner Match Analysis", "Match Advantages"):
        assert marker in HTML
    assert "function partnerFilter()" in HTML
    assert "function partnerFullAssessment()" in HTML
    assert "project.matching_detail" in HTML


def test_figma_locked_status_is_present_and_uses_permissions():
    for marker in ("Accessible Companies", "Locked Companies", "Access Requests Pending Approval", "Permission Approval Rate", "Restriction Reason", "Access Permissions"):
        assert marker in HTML
    assert "function lockedRequest(idx)" in HTML
    assert "function lockedExport()" in HTML
    assert "reports.export" in HTML


def test_demo_mode_switch_replaces_login_ui():
    for marker in ('value="visitor">Visitor', 'value="professional">Professional', 'value="enterprise">Enterprise', 'value="admin">Administrator'):
        assert marker in HTML
    assert "_switchDemoMode(this.value)" in HTML
    assert "/api/auth/demo-mode" in HTML
    assert "authEmail" not in HTML
    assert "Sign In / Register" not in HTML


def test_intelligence_displays_automatic_scheduler_status():
    assert "fetch('/api/intelligence/scheduler')" in HTML
    assert "Automated Fetching Enabled" in HTML
    assert "Next Automated Fetch" in HTML


def test_intelligence_saved_search_and_alert_settings_are_connected():
    for marker in (
        "My Intelligence Monitors", "Saved Searches and Alerts", "Alert Frequency", "Alerts enabled",
        "Currently records alert schedules only", "Apply Filters", "Search titles or summaries",
    ):
        assert marker in HTML
    assert "fetch('/api/intelligence/saved-searches')" in HTML
    assert "async function createSavedSearch()" in HTML
    assert "async function toggleSavedSearch(id,enabled)" in HTML
    assert "async function deleteSavedSearch(id)" in HTML
    assert "function applySavedSearch(index)" in HTML


def test_week7_locked_project_and_sprint_flow_are_connected():
    for marker in (
        "Scoring Rationale and Key Gaps Restricted", "Upgrade and Unlock", "Apply for a 14-Day Project Sprint",
        "Application Submitted Successfully", "Admin: Review and Start", "14-Day Delivery Roadmap", "Phase Tasks",
    ):
        assert marker in HTML
    assert "function _openProjectUnlock(projectId)" in HTML
    assert "async function openSprintApplication(projectId=0)" in HTML
    assert "fetch('/api/sprints'" in HTML
    assert "loadSprintWorkbench" in HTML


def test_pricing_separates_subscription_from_sprint_service():
    for marker in ("Free Plan", "Professional", "Enterprise", "Standard Advisory Service", "14-Day Sprint Service", "Single-Project Advisory Service"):
        assert marker in HTML
    assert "async function loadEnterpriseAccessStatus(el)" in HTML
    assert "async function loadLockedStatus(el)" in HTML


def test_commercial_pricing_boundaries_and_sla_are_present():
    for marker in (
        "Pricing Assumptions Require Validation", "Boundary Between Platform Automation and Analyst Work", "Fixed 14-Day Delivery Schedule",
        "Application Materials and Scope Confirmation", "Defined Deliverables and SLA", "Why the 14-Day Sprint Costs More",
        "Client Cooperation, Delays, and Changes", "Explicit Exclusions", "Frequently Asked Questions", "Upgrade Path",
    ):
        assert marker in HTML
    assert "fetch('/api/commercial/offers')" in HTML
    assert "function commercialSelect(offerId)" in HTML
    assert "openSprintApplication()" in HTML
    for marker in (
        "Prepare Materials and Resources", "sprintMaterial", "Client's Expected Bid Deadline", "Resources for a 24-Hour Response",
        "sprintScopeConfirmed", "sprintCooperationConfirmed",
    ):
        assert marker in HTML
