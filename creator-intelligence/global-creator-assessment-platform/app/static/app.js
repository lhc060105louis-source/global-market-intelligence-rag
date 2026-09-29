"use strict";

// The /collections and /comparisons workflows are implemented in separately loaded modules.

const state = {kols: [], selectedKolIds: new Set(), currentDetailId: null, stage: 0, currentQuery: ""};
const STAGE_NAMES = ["Creator Discovery", "Qualification", "Pitch & Negotiation", "Contracting", "Campaign Execution", "Performance Attribution", "Renewal / Archive"];
const COMMERCIAL_DIMENSIONS = ["audience_fit", "content_relevance", "interaction_quality", "voc_value", "commercial_efficiency", "brand_fit", "execution_capability"];
const RISK_DIMENSIONS = ["historical_controversy", "ad_disclosure", "competitor_conflict", "fake_traffic", "data_privacy", "sensitive_audience", "sustainability_claims", "execution_risk"];
const COMMERCIAL_INPUT_KEYS = ["geo", "lang", "autoInterest", "income", "age", "focus", "depth", "credibility", "err", "completion", "commentQuality", "shareSave", "vocDepth", "vocNeg", "vocHistory", "benchCpm", "cpm", "reuse", "exclusive", "brandTone", "histTone", "styleConsist", "fulfill", "briefCoop", "dataReady", "contractFlex"];
const RISK_INPUT_KEYS = ["incident", "falsead", "sentiment", "adlabel", "penalty", "compliance", "competitor", "compcontentpct", "complevel", "fakepct", "spikegrowth", "templatecomment", "gdpr", "datause", "minorpct", "agesuit", "exaggerate", "adas", "techaccuracy", "latedelete", "briefreject"];
const YOUTUBE_ENRICHMENT_BATCH_SIZE = 20;

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (window.__KOL_SESSION_TOKEN__) headers.set("X-KOL-Session", window.__KOL_SESSION_TOKEN__);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(path, {...options, headers});
  if (!response.ok) {
    let message = `Request failed ${response.status}`;
    try { message = (await response.json()).detail || message; } catch (_) { /* use fallback */ }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function formatNumber(value) { return value == null ? "Not provided" : new Intl.NumberFormat("en-US", {notation: "compact"}).format(value); }
function summary(kol) { return kol.score_summary || {}; }
function showStatus(message, error = false) {
  const bar = document.getElementById("status-bar");
  bar.textContent = message; bar.hidden = false; bar.classList.toggle("error", error);
  window.setTimeout(() => { bar.hidden = true; }, 4500);
}

function navigate(page) {
  document.querySelectorAll(".page").forEach(node => node.classList.toggle("active", node.id === `page-${page}`));
  document.querySelectorAll(".nav-item[data-page]").forEach(node => node.classList.toggle("active", node.dataset.page === page));
  const titles = {dashboard: "Dashboard", campaigns: "Campaign Setup & Goals", kol: "Creators", compare: "Creator Comparison", shortlists: "Shortlists", collab: "Partnerships", monitoring: "Campaign Monitoring", contracts: "Contracts", results: "Performance Review", assets: "Creator Assets & Reinvestment", closures: "Campaign Closeout & Archive", settings: "Settings"};
  document.getElementById("page-title").textContent = titles[page];
  if (page === "collab") renderCollabPage();
  if (page === "campaigns") loadCampaigns().catch(error => showStatus(error.message, true));
  if (page === "monitoring") loadMonitoringOverview().catch(error => showStatus(error.message, true));
  if (page === "shortlists") loadShortlists();
  if (page === "contracts") loadContracts();
  if (page === "results") { loadPostOverview().catch(error => showStatus(error.message, true));}
  if (page === "assets") { loadAssetOverview().catch(error => showStatus(error.message, true));}
  if (page === "closures") { loadClosureOverview().catch(error => showStatus(error.message, true));}
  if (page === "settings") { loadYoutubeSettings(); loadSupabaseSettings(); }
}

function scoreBox(label, value, risk = false) {
  const box = el("div", "ks-box");
  box.append(el("div", "ks-label", label));
  const num = el("div", "ks-num", value == null ? "—" : Math.round(value));
  num.style.color = KolAssessment.scoreColor(value, risk); box.append(num);
  const bar = el("div", "ks-bar"), fill = el("div", "ks-fill");
  fill.style.width = `${value || 0}%`; fill.style.background = KolAssessment.scoreColor(value, risk);
  bar.append(fill); box.append(bar); return box;
}

function makeKolCard(kol, index) {
  const card = el("article", "kol-card"); card.dataset.kolId = kol.id;
  const actions = el("div", "card-actions");
  const edit = el("button", "icon-btn", "Edit"); edit.type = "button";
  edit.addEventListener("click", event => { event.stopPropagation(); openEditKOL(kol.id); }); actions.append(edit); card.append(actions);
  const top = el("div", "kol-card-top"), avatar = el("div", "kol-avatar", (kol.name || kol.handle || "K").slice(0, 2).toUpperCase());
  avatar.style.background = ["#E0F2FE", "#E8EDFF", "#ECFDF5", "#FEF9C3"][index % 4];
  const identity = el("div"); identity.append(el("div", "kol-name", kol.name || kol.handle || "Unnamed creator"));
  identity.append(el("div", "kol-handle", `${kol.handle || "No handle"} · ${kol.country}`));
  const badges = el("div", "badges"); badges.append(el("span", "badge", kol.platform)); badges.append(el("span", "badge", `${formatNumber(kol.followers)} followers`));
  if (summary(kol).risk_level === "high") badges.append(el("span", "badge red", "⚠ High risk")); identity.append(badges); top.append(avatar, identity); card.append(top);
  const scores = el("div", "kol-scores"); scores.append(scoreBox("Commercial score", summary(kol).commercial_score), scoreBox("Risk score", summary(kol).risk_score, true));
  const select = el("label", "ks-box"); const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.checked = state.selectedKolIds.has(kol.id);
  checkbox.disabled = !checkbox.checked && state.selectedKolIds.size >= MAX_COMPARISON_KOLS;
  checkbox.addEventListener("click", event => event.stopPropagation()); checkbox.addEventListener("change", () => toggleComparison(kol.id, checkbox.checked)); select.append(checkbox, document.createTextNode(" Add to comparison")); scores.append(select); card.append(scores);
  card.addEventListener("click", () => showKOLDetail(kol.id)); return card;
}

function renderKOLPage() {
  const grid = document.getElementById("kol-results"); clear(grid);
  state.kols.forEach((kol, index) => grid.append(makeKolCard(kol, index)));
  document.getElementById("kol-count").textContent = state.kols.length;
  document.getElementById("kol-empty").hidden = state.kols.length > 0;
  updateSelectionUI();
}

function updateDashboard() {
  document.getElementById("dash-total").textContent = state.kols.length;
  document.getElementById("dash-agrade").textContent = state.kols.filter(k => (summary(k).commercial_score || 0) >= 80).length;
  document.getElementById("dash-active").textContent = state.kols.filter(k => k.workflow_stage === 4).length;
  document.getElementById("dash-risk").textContent = state.kols.filter(k => summary(k).risk_level === "high").length;
  const table = document.getElementById("dash-table"); clear(table);
  state.kols.slice(0, 5).forEach(kol => { const row = el("div", "collab-row"); row.append(el("strong", "", kol.name || kol.handle || "Unnamed"), el("span", "", `${kol.country} · ${formatNumber(kol.followers)} followers`), el("span", "", KolAssessment.commercialGrade(summary(kol).commercial_score))); table.append(row); });
}

async function loadKols(query = "", {skipEnrichment = false} = {}) {
  state.currentQuery = query;
  state.kols = await api("/kols" + query);
  renderKOLPage(); updateDashboard(); renderCollabPage();
  if (!skipEnrichment) await maybeEnrichVisibleYoutubeKols();
}

async function maybeEnrichVisibleYoutubeKols() {
  const ids = state.kols.filter(k => k.platform === "YouTube" && k.followers == null).slice(0, YOUTUBE_ENRICHMENT_BATCH_SIZE).map(k => k.id);
  if (!ids.length) return;
  showStatus("Filling in YouTube follower counts…");
  const result = await api("/kols/enrich-youtube", {method: "POST", body: JSON.stringify({kol_ids: ids})});
  if (result.updated) await loadKols(state.currentQuery, {skipEnrichment: true});
}

function updateSelectionUI() {
  document.getElementById("selected-kol-count").textContent = state.selectedKolIds.size;
  document.getElementById("comparison-count").textContent = state.selectedKolIds.size;
  const list = document.getElementById("comparison-selection"); clear(list);
  state.kols.filter(k => state.selectedKolIds.has(k.id)).forEach(k => list.append(el("span", "selection-pill", k.name || k.handle)));
  updateComparisonControls();
}

function renderCollabPage() {
  const bar = document.getElementById("stage-bar"), list = document.getElementById("collab-list"); clear(bar); clear(list);
  const stageCounts = STAGE_NAMES.map((_, index) => state.kols.filter(kol => (kol.workflow_stage || 0) === index).length);
  STAGE_NAMES.forEach((name, index) => { const stage = el("button", `stage${state.stage === index ? " active" : ""}`, `${index + 1}. ${name} (${stageCounts[index]})`); stage.addEventListener("click", () => { state.stage = index; renderCollabPage(); }); bar.append(stage); });
  const matches = state.kols.filter(k => (k.workflow_stage || 0) === state.stage);
  if (!matches.length) list.append(el("div", "empty-state", "No creators at this stage."));
  matches.forEach(kol => { const row = el("div", "collab-row"); const advance = el("button", "tb-btn teal", state.stage === 6 ? "Complete" : "Advance to next stage"); advance.disabled = state.stage === 6; advance.addEventListener("click", () => advanceWorkflow(kol.id)); row.append(el("strong", "", kol.name || kol.handle), el("span", "", STAGE_NAMES[state.stage]), advance); list.append(row); });
}

function openOverlay(id) { const overlay = document.getElementById(id); overlay.classList.add("open"); overlay.setAttribute("aria-hidden", "false"); }
function closeOverlay(overlay) { if (overlay.id === "auto-collection-overlay") stopCollectionPolling(); overlay.classList.remove("open"); overlay.setAttribute("aria-hidden", "true"); }
function switchModalTab(index) { document.querySelectorAll(".m-tab").forEach((tab, tabIndex) => tab.classList.toggle("active", tabIndex === index)); document.querySelectorAll(".m-tab-panel").forEach((panel, panelIndex) => { panel.hidden = panelIndex !== index; }); }
function openAddKOL() { const preview = document.getElementById("score-preview"), youtubePreview = document.getElementById("yt-preview-card"); document.getElementById("kol-form").reset(); document.getElementById("kol-id").value = ""; document.getElementById("kol-form-title").textContent = "Add Creator"; document.getElementById("yt-status").textContent = ""; youtubePreview.hidden = true; youtubePreview.textContent = ""; clear(preview); preview.append(el("strong", "", "Score Preview"), el("span", "", "Commercial and risk scores are calculated by the server.")); switchModalTab(0); scheduleAssessmentPreview(); openOverlay("add-kol-overlay"); }
async function openEditKOL(id) { const kol = await api(`/kols/${id}`); document.getElementById("kol-form").reset(); document.getElementById("kol-id").value = id; document.getElementById("kol-form-title").textContent = "Edit Creator"; const values = {name: kol.name, handle: kol.handle, platform_account_id: kol.platform_account_id, platform: kol.platform, country: kol.country, language: kol.language, followers: kol.followers, content_categories: kol.content_categories, profile_url: kol.profile_url, ...kol.commercial_inputs, ...kol.risk_inputs}; Object.entries(values).forEach(([name, value]) => { const input = document.querySelector(`#kol-form [name="${name}"]`); if (input) input.value = value ?? ""; }); switchModalTab(0); openOverlay("add-kol-overlay"); updateAssessmentPreview(); }

function typedFormValue(form, key) { const input = form.elements.namedItem(key); if (!input || input.value === "") return null; return input.type === "number" ? Number(input.value) : input.value; }
function collectAssessmentInputs(form) { const collect = keys => Object.fromEntries(keys.map(key => [key, typedFormValue(form, key)]).filter(([, value]) => value !== null)); return {commercial_inputs: collect(COMMERCIAL_INPUT_KEYS), risk_inputs: collect(RISK_INPUT_KEYS)}; }
function initializeAssessmentSelects() {
  const benchmark = document.querySelector('#kol-form input[name="benchCpm"]');
  benchmark.defaultValue = ""; benchmark.value = "";
  [...COMMERCIAL_INPUT_KEYS, ...RISK_INPUT_KEYS].forEach(name => {
    const select = document.querySelector(`#kol-form select[name="${name}"]`);
    if (!select || select.querySelector('option[value=""]')) return;
    select.prepend(new Option("Not assessed", "", true, true));
  });
}

async function saveKOL(event) {
  event.preventDefault(); const form = new FormData(event.currentTarget), kolId = document.getElementById("kol-id").value;
  const assessment = collectAssessmentInputs(event.currentTarget); const payload = Object.fromEntries([...form.entries()].filter(([key]) => !COMMERCIAL_INPUT_KEYS.includes(key) && !RISK_INPUT_KEYS.includes(key)));
  payload.followers = payload.followers === "" ? null : Number(payload.followers); payload.average_engagement_rate = assessment.commercial_inputs.err ?? null; payload.audience_country_ratio = assessment.commercial_inputs.geo ?? null; payload.handle = payload.handle.trim() || null; payload.platform_account_id = payload.platform_account_id.trim() || null; Object.assign(payload, assessment);
  await api(kolId ? `/kols/${kolId}` : "/kols", {method: kolId ? "PUT" : "POST", body: JSON.stringify(payload)});
  closeOverlay(document.getElementById("add-kol-overlay")); await loadKols(); navigate("kol"); showStatus(kolId ? "Creator updated." : "Creator added.");
}

async function fetchYouTubePreview() { const input = document.getElementById("yt-url-input"), status = document.getElementById("yt-status"); if (!input.value.trim()) { status.textContent = "Enter a channel URL or @handle."; return; } status.textContent = "Fetching channel data…"; try { const lookup = await api("/kols/lookup-youtube", {method: "POST", body: JSON.stringify({profile_url: input.value.trim()})}); const values = {name: lookup.name, platform_account_id: lookup.platform_account_id, profile_url: lookup.profile_url, followers: lookup.followers}; Object.entries(values).forEach(([name, value]) => { const field = document.querySelector(`#kol-form [name="${name}"]`); if (field) field.value = value ?? ""; }); document.getElementById("yt-preview-card").hidden = false; document.getElementById("yt-preview-card").textContent = `${lookup.name || "YouTube channel"} · ${formatNumber(lookup.followers)} subscribers`; status.textContent = "Channel details added. Complete the assessment fields."; } catch (error) { status.textContent = error.message; } }
let previewTimer;
function scheduleAssessmentPreview() { window.clearTimeout(previewTimer); previewTimer = window.setTimeout(updateAssessmentPreview, 180); }
async function updateAssessmentPreview() { const inputs = collectAssessmentInputs(document.getElementById("kol-form")); try { const result = await KolAssessment.calculatePreview(inputs.commercial_inputs, inputs.risk_inputs, api); const preview = document.getElementById("score-preview"); clear(preview); preview.append(el("strong", "", `Commercial score: ${result.commercial_score ?? "Not provided"} ${result.commercial_grade || ""}`), el("span", "", `Risk: ${result.risk_score ?? "Not provided"} ${result.risk_level || ""}${result.flags.length ? ` · ${result.flags.length} alert(s)` : ""}`)); } catch (_) { /* incomplete values are previewed when valid */ } }

function populateScoreDimensions() { const type = document.getElementById("score-type").value, select = document.getElementById("score-dimension"); clear(select); (type === "commercial" ? COMMERCIAL_DIMENSIONS : RISK_DIMENSIONS).forEach(dimension => { const option = el("option", "", dimension); option.value = dimension; select.append(option); }); }
function renderScoreRecords(records) { const container = document.getElementById("score-records"); clear(container); records.forEach(record => { const row = el("div", "collab-row"); row.append(el("strong", "", record.dimension), el("span", "", `Final score: ${record.final_score ?? "Not provided"}`), el("span", "", record.manual_evidence || record.evidence || "No evidence provided")); container.append(row); }); }
async function showKOLDetail(id) { const kol = await api(`/kols/${id}`); state.currentDetailId = id; document.getElementById("detail-title").textContent = kol.name || kol.handle || "Creator details"; const content = document.getElementById("detail-content"); clear(content); content.append(el("p", "", `${kol.platform} · ${kol.country} · ${formatNumber(kol.followers)} followers`)); populateScoreDimensions(); renderScoreRecords(kol.score_records || []); document.getElementById("detail-dialog").showModal(); }
async function saveScore(event) { event.preventDefault(); const payload = Object.fromEntries(new FormData(event.currentTarget).entries()); payload.manual_score = Number(payload.manual_score); await api(`/kols/${state.currentDetailId}/scores`, {method: "POST", body: JSON.stringify(payload)}); await loadKols(); document.getElementById("detail-dialog").close(); }

async function submitImport(event) { event.preventDefault(); const body = new FormData(); body.append("file", document.getElementById("import-file").files[0]); const result = await api("/imports", {method: "POST", body}); showStatus(`Import complete: ${result.created} created, ${result.updated} updated, ${result.failed} failed.`); closeOverlay(document.getElementById("import-overlay")); await loadKols(); }
function submitKolSearch(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const minFollowers = form.elements.namedItem("min_followers").value;
  const maxFollowers = form.elements.namedItem("max_followers").value;
  if (
    minFollowers !== "" &&
    maxFollowers !== "" &&
    Number(minFollowers) > Number(maxFollowers)
  ) {
    showStatus("The minimum follower count cannot exceed the maximum.", true);
    return;
  }

  const query = new URLSearchParams(new FormData(form));
  ["min_followers", "max_followers", "min_commercial_score"].forEach(field => {
    if (query.get(field) === "") query.delete(field);
  });
  loadKols(`?${query}`);
}

function bindEvents() {
  initializeAssessmentSelects();
  document.querySelectorAll("[data-page]").forEach(node => node.addEventListener("click", () => navigate(node.dataset.page)));
  document.querySelectorAll("[data-go]").forEach(node => node.addEventListener("click", () => navigate(node.dataset.go)));
  document.getElementById("open-add-kol").addEventListener("click", openAddKOL); document.getElementById("open-collection").addEventListener("click", openCollectionModal); document.getElementById("open-import").addEventListener("click", () => openOverlay("import-overlay"));
  document.querySelectorAll(".close-overlay").forEach(node => node.addEventListener("click", () => closeOverlay(node.closest(".overlay")))); document.querySelectorAll(".overlay").forEach(node => node.addEventListener("click", event => { if (event.target === node) closeOverlay(node); }));
  document.getElementById("kol-form").addEventListener("submit", saveKOL); document.getElementById("search-form").addEventListener("submit", submitKolSearch);
  document.querySelectorAll("[data-modal-tab]").forEach(tab => tab.addEventListener("click", () => switchModalTab(Number(tab.dataset.modalTab))));
  document.getElementById("fetch-youtube").addEventListener("click", fetchYouTubePreview); document.getElementById("kol-form").addEventListener("input", scheduleAssessmentPreview); document.getElementById("kol-form").addEventListener("change", scheduleAssessmentPreview);
  document.getElementById("run-comparison").addEventListener("click", renderComparison); document.getElementById("select-all-kols").addEventListener("change", event => { state.selectedKolIds.clear(); if (event.target.checked) state.kols.slice(0, MAX_COMPARISON_KOLS).forEach(k => state.selectedKolIds.add(k.id)); renderKOLPage(); });
  document.getElementById("collection-form").addEventListener("submit", submitCollection); document.getElementById("import-form").addEventListener("submit", submitImport); document.getElementById("settings-form").addEventListener("submit", saveYoutubeKey); document.getElementById("delete-settings").addEventListener("click", deleteYoutubeKey);
  document.getElementById("shortlist-form").addEventListener("submit", createShortlist);
  document.getElementById("supabase-settings-form").addEventListener("submit", saveSupabaseSettings);
  document.getElementById("sync-now").addEventListener("click", runSyncNow);
  document.getElementById("sync-status").addEventListener("click", () => navigate("settings"));
  document.getElementById("export-kols").addEventListener("click", downloadKolsExport);
  document.getElementById("close-detail").addEventListener("click", () => document.getElementById("detail-dialog").close()); document.getElementById("score-form").addEventListener("submit", saveScore);
  document.getElementById("score-type").addEventListener("change", populateScoreDimensions); populateScoreDimensions();
  bindCollectionEvents();
}

async function bootstrap() { bindEvents(); initMonitoringModule(); initPostCampaignModule(); initAssetModule(); initCampaignModule(); initClosureModule(); await loadKols(); await loadSyncStatus(); }
bootstrap().catch(error => showStatus(error.message, true));

async function protectedSameOriginDownload(path, filename) {
  const headers = new Headers();
  if (window.__KOL_SESSION_TOKEN__) headers.set("X-KOL-Session", window.__KOL_SESSION_TOKEN__);
  const response = await fetch(path, {credentials: "same-origin", headers});
  if (!response.ok) throw new Error(`Export failed (${response.status}).`);
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement("a"); link.href = objectUrl; link.download = filename; link.click();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}

function downloadKolsExport(event) {
  event.preventDefault();
  const query = state.currentQuery || "";
  protectedSameOriginDownload(`/exports/kols.xlsx${query}`, "kols.xlsx").catch(error => showStatus(error.message, true));
}
