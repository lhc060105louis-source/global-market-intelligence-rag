"use strict";

const closureState = {
  current: null,
  items: [],
  view: "overview",
};

const closureActionLabels = {
  created: "Create closeout workspace",
  checks_updated: "Update closeout check",
  issue_created: "Add Open Item",
  issue_updated: "Update open item",
  summary_updated: "Save closeout summary",
  submitted: "Submit for closeout approval",
  returned: "Return for More Information",
  closed: "Confirm Closure",
  revision_created: "Create a revised version",
};

function closureStatusClass(status) {
  if (["Passed", "Resolved"].includes(status)) return "pass";
  if (["closed", "Closed"].includes(status)) return "closed";
  if (["Blocked", "Critical"].includes(status)) return "block";
  if (["not_ready", "Not Ready to Close"].includes(status)) return "not-ready";
  if (["returned", "Returned"].includes(status)) return "returned";
  return "pending";
}

function closureStatus(text, raw = text) {
  return el("span", `closure-status ${closureStatusClass(raw)}`, text);
}

function closureDateTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("en-GB", {hour12: false});
}

async function closureRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (window.__KOL_SESSION_TOKEN__) headers.set("X-KOL-Session", window.__KOL_SESSION_TOKEN__);
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, {...options, headers});
  if (!response.ok) {
    let message = `Request failed ${response.status}`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (data.detail && data.detail.message) {
        message = data.detail.message;
        const issues = data.detail.issues || [];
        if (issues.length) message += ` ${issues.slice(0, 3).map(item => item.message).join("; ")}`;
      }
    } catch (_) { /* keep the status fallback */ }
    throw new Error(message);
  }
  return response.json();
}

function switchClosureView(view) {
  closureState.view = view;
  document.querySelectorAll("[data-closure-view]").forEach(node => {
    node.classList.toggle("active", node.dataset.closureView === view);
  });
  document.querySelectorAll(".closure-panel").forEach(node => {
    node.classList.toggle("active", node.id === `closure-${view}`);
  });
  if (view === "checks") renderClosureChecks();
  if (view === "archive") renderClosureArchive();
}

function updateClosureContext() {
  const box = document.getElementById("closure-context");
  const data = closureState.current;
  if (!data) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  clear(box);
  box.append(
    el("strong", "", data.Campaign_name),
    document.createElement("br"),
    document.createTextNode(`${data.brand} · ${data.primary_market} · V${data.version} · `),
    closureStatus(data.status_label, data.status),
  );
}

function closureMetric(label, value, note, warning = false) {
  const card = el("article", `closure-metric${warning ? " warning" : ""}`);
  card.append(el("span", "", label), el("strong", "", String(value)), el("small", "", note));
  return card;
}

function readinessNode(value) {
  const wrapper = el("div", "closure-progress");
  const track = el("div", "closure-progress-track");
  const fill = el("div", "closure-progress-fill");
  fill.style.width = `${Math.max(0, Math.min(100, value || 0))}%`;
  track.append(fill);
  wrapper.append(track, el("small", "", `${Math.round(value || 0)}% Complete`));
  return wrapper;
}

function renderClosureOverview(data) {
  const panel = document.getElementById("closure-overview");
  clear(panel);
  const metrics = el("div", "closure-metrics");
  metrics.append(
    closureMetric("Not Ready", data.metrics.not_ready, "Required checks remain incomplete"),
    closureMetric("Unconfirmed", data.metrics.pending_confirmation, "Awaiting brand owner approval"),
    closureMetric("Closed", data.metrics.closed, "Final version frozen"),
    closureMetric("Blocked", data.metrics.blocking, "Requires attention", data.metrics.blocking > 0),
  );

  const card = el("article", "closure-card");
  const heading = el("div", "closure-card-head");
  const text = el("div");
  text.append(el("h3", "", `Campaigns · ${data.total}`), el("p", "", "Select a campaign to review it. A draft closeout record is created automatically when needed."));
  heading.append(text);

  const toolbar = el("form", "closure-toolbar");
  toolbar.id = "closure-filter-form";
  const search = document.createElement("input");
  search.name = "q";
  search.placeholder = "Search by campaign name or ID";
  const brand = document.createElement("select");
  brand.name = "brand";
  brand.append(new Option("Allbrand", ""), new Option("BYD", "BYD"), new Option("XPENG", "XPENG"));
  const market = document.createElement("select");
  market.name = "market";
  market.append(new Option("All markets", ""), new Option("Germany DE", "DE"), new Option("United Kingdom GB", "GB"));
  const status = document.createElement("select");
  status.name = "status";
  status.append(
    new Option("All closeout statuses", ""), new Option("Not Ready to Close", "not_ready"),
    new Option("Draft closeout", "draft"), new Option("Unconfirmed", "pending_confirmation"),
    new Option("Returned", "returned"), new Option("Closed", "closed"),
  );
  const submit = el("button", "tb-btn teal", "Filter");
  submit.type = "submit";
  const reset = el("button", "tb-btn", "Reset");
  reset.type = "button";
  reset.addEventListener("click", () => loadClosureOverview());
  toolbar.append(search, brand, market, status, submit, reset);
  toolbar.addEventListener("submit", event => {
    event.preventDefault();
    const params = new URLSearchParams(new FormData(toolbar));
    [...params.keys()].forEach(key => { if (!params.get(key)) params.delete(key); });
    loadClosureOverview(params).catch(error => showStatus(error.message, true));
  });

  const tableWrap = el("div", "table-wrap");
  if (!data.items.length) {
    tableWrap.append(el("div", "closure-empty", "No campaigns match these filters. Create a campaign in Campaign Setup first."));
  } else {
    const table = el("table", "closure-table");
    const thead = document.createElement("thead");
    const header = document.createElement("tr");
    ["Campaign", "Brand / Market", "Owner", "Planned end date", "Closeout readiness", "Open / blocking items", "Status"].forEach(label => header.append(el("th", "", label)));
    thead.append(header);
    const tbody = document.createElement("tbody");
    data.items.forEach(item => {
      const row = document.createElement("tr");
      row.dataset.campaignId = item.campaign_id;
      const Campaign = document.createElement("td");
      Campaign.append(el("strong", "", item.Campaign_name), el("div", "closure-note", item.campaign_id));
      const brandMarket = document.createElement("td");
      brandMarket.append(el("strong", "", item.brand), el("div", "closure-note", (item.markets || []).join(" / ")));
      const progress = document.createElement("td");
      progress.append(readinessNode(item.readiness));
      const counts = document.createElement("td");
      counts.append(document.createTextNode(`${item.open_issue_count} open item(s)`), document.createElement("br"));
      counts.append(closureStatus(`${item.blocking_count} blocking item(s)`, item.blocking_count ? "Blocked" : "Passed"));
      const stateCell = document.createElement("td");
      stateCell.append(closureStatus(item.closure_status_label, item.closure_status));
      row.append(Campaign, brandMarket, el("td", "", item.owner), el("td", "", item.planned_end_date), progress, counts, stateCell);
      row.addEventListener("click", () => openClosureItem(item));
      tbody.append(row);
    });
    table.append(thead, tbody);
    tableWrap.append(table);
  }
  card.append(heading, toolbar, tableWrap);
  panel.append(metrics, card);
}

async function loadClosureOverview(params = new URLSearchParams()) {
  const suffix = params.toString() ? `?${params}` : "";
  const data = await closureRequest(`/closures${suffix}`);
  closureState.items = data.items;
  renderClosureOverview(data);
  return data;
}

async function openClosureItem(item) {
  const data = item.closure_id
    ? await closureRequest(`/closures/${encodeURIComponent(item.closure_id)}`)
    : await closureRequest(`/closures/campaigns/${encodeURIComponent(item.campaign_id)}`, {
        method: "POST",
        body: JSON.stringify({actor: "Campaign owner", actor_role: "project_owner"}),
      });
  closureState.current = data;
  updateClosureContext();
  switchClosureView(data.status === "closed" ? "archive" : "checks");
}

async function reloadCurrentClosure() {
  if (!closureState.current) return null;
  closureState.current = await closureRequest(`/closures/${encodeURIComponent(closureState.current.closure_id)}`);
  updateClosureContext();
  return closureState.current;
}

function closureSummaryStrip(data) {
  const strip = el("div", "closure-summary-strip");
  [
    ["Closeout status", data.status_label],
    ["Readiness", `${Math.round(data.readiness)}%`],
    ["Open items", `${data.open_issue_count} item(s)`],
    ["Current version", `V${data.version} · Revision ${data.revision}`],
  ].forEach(([label, value]) => {
    const item = document.createElement("div");
    item.append(el("span", "", label), el("strong", "", value));
    strip.append(item);
  });
  return strip;
}

async function saveClosureCheck(checkKey, status) {
  const data = closureState.current;
  const note = status === "Passed" ? "Manually confirmed" : "Additional review required";
  closureState.current = await closureRequest(`/closures/${encodeURIComponent(data.closure_id)}/checks`, {
    method: "PUT",
    body: JSON.stringify({
      expected_revision: data.revision,
      actor: "Campaign owner",
      actor_role: "project_owner",
      items: [{check_key: checkKey, status, note}],
    }),
  });
  updateClosureContext();
  renderClosureChecks();
  showStatus(status === "Passed" ? "Check confirmed manually." : "Check marked as unconfirmed.");
}

function renderCheckTable(data) {
  const table = el("table", "closure-table");
  const thead = document.createElement("thead");
  const header = document.createElement("tr");
  ["Check", "Current status", "Source & notes", "Updated / confirmed by", "Actions"].forEach(label => header.append(el("th", "", label)));
  thead.append(header);
  const tbody = document.createElement("tbody");
  data.checks.forEach(check => {
    const row = document.createElement("tr");
    row.className = `closure-check-row${check.system_blocking ? " system-blocking" : ""}`;
    const label = document.createElement("td");
    label.append(el("strong", "", check.label), el("div", "closure-note", check.required ? "Required" : "Recommended"));
    const status = document.createElement("td");
    status.append(closureStatus(check.status));
    const detail = el("td", "closure-check-detail", check.detail);
    detail.append(el("div", "closure-note", `Source: ${check.source}`));
    const confirmed = document.createElement("td");
    confirmed.append(document.createTextNode(closureDateTime(check.updated_at)), document.createElement("br"));
    confirmed.append(el("small", "", check.confirmed_by ? `Manually confirmed by: ${check.confirmed_by}` : `System status: ${check.automatic_status}`));
    const action = document.createElement("td");
    if (data.status !== "closed") {
      if (check.status !== "Passed") {
        const pass = el("button", "tb-btn teal", "Mark as passed");
        pass.type = "button";
        pass.disabled = check.system_blocking;
        pass.title = check.system_blocking ? "Resolve the major risk in the risk section before marking this check as passed." : "Record manual confirmation";
        pass.addEventListener("click", () => saveClosureCheck(check.key, "Passed").catch(error => showStatus(error.message, true)));
        action.append(pass);
      } else if (check.confirmed_by) {
        const reopen = el("button", "tb-btn", "Review again");
        reopen.type = "button";
        reopen.addEventListener("click", () => saveClosureCheck(check.key, "Unconfirmed").catch(error => showStatus(error.message, true)));
        action.append(reopen);
      } else {
        action.append(el("span", "closure-note", "Passed by system"));
      }
    } else {
      action.append(el("span", "closure-note", "Version is frozen"));
    }
    row.append(label, status, detail, confirmed, action);
    tbody.append(row);
  });
  table.append(thead, tbody);
  return table;
}

function issueForm(data) {
  const form = el("form", "closure-field-grid");
  const fields = [
    ["issue_type", "Item type", "select", ["Data", "Contract", "Payment", "Content", "risk", "Assets", "Other"]],
    ["severity", "Severity", "select", ["Standard", "Important", "Critical"]],
    ["title", "Item title", "input"],
    ["owner", "Owner", "input"],
    ["due_date", "Target completion date", "date"],
    ["source_reference", "Source reference", "input"],
  ];
  fields.forEach(([name, label, kind, options]) => {
    const wrap = el("label", "closure-field");
    wrap.append(el("span", "", label));
    let input;
    if (kind === "select") {
      input = document.createElement("select");
      options.forEach(value => input.append(new Option(value, value)));
    } else {
      input = document.createElement("input");
      input.type = kind === "date" ? "date" : "text";
    }
    input.name = name;
    input.required = name !== "source_reference";
    if (name === "due_date") {
      const due = new Date();
      due.setDate(due.getDate() + 7);
      input.value = due.toISOString().slice(0, 10);
    }
    wrap.append(input);
    form.append(wrap);
  });
  const desc = el("label", "closure-field wide");
  desc.append(el("span", "", "Item description"));
  const textarea = document.createElement("textarea");
  textarea.name = "description";
  textarea.required = true;
  textarea.placeholder = "Describe the unfinished content, current progress, and required outcome.";
  desc.append(textarea);
  form.append(desc);
  const actions = el("div", "closure-actions end wide");
  const submit = el("button", "tb-btn teal", "+ Add open item");
  submit.type = "submit";
  actions.append(submit);
  form.append(actions);
  form.addEventListener("submit", event => addClosureIssue(event, data));
  return form;
}

async function addClosureIssue(event, data) {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.currentTarget).entries());
  const response = await closureRequest(`/closures/${encodeURIComponent(data.closure_id)}/issues`, {
    method: "POST",
    body: JSON.stringify({
      ...values,
      expected_revision: data.revision,
      actor: "Campaign owner",
      actor_role: "project_owner",
    }),
  });
  closureState.current = response.closure;
  updateClosureContext();
  renderClosureChecks();
  showStatus("Open item added.");
}

async function changeClosureIssue(issue, status) {
  let note = null;
  if (["Resolved", "Accept Open Items"].includes(status)) {
    note = window.prompt(status === "Resolved" ? "Add a resolution note." : "Explain why the open item is being accepted.");
    if (!note) return;
  }
  const data = closureState.current;
  closureState.current = await closureRequest(
    `/closures/${encodeURIComponent(data.closure_id)}/issues/${encodeURIComponent(issue.issue_id)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        expected_revision: data.revision,
        actor: "Campaign owner",
        actor_role: "project_owner",
        status,
        resolution_note: note,
      }),
    },
  );
  updateClosureContext();
  renderClosureChecks();
  showStatus("Open item status updated.");
}

function renderIssues(data) {
  if (!data.issues.length) return el("div", "closure-empty", "No open items. Assign an owner and due date to every outstanding standard item." );
  const table = el("table", "closure-table");
  const head = document.createElement("tr");
  ["Item", "Type / Severity", "Owner / Due date", "Status", "Actions"].forEach(label => head.append(el("th", "", label)));
  const thead = document.createElement("thead"); thead.append(head);
  const tbody = document.createElement("tbody");
  data.issues.forEach(issue => {
    const row = document.createElement("tr");
    const title = document.createElement("td");
    title.append(el("strong", "", issue.title), el("div", "closure-note", issue.description));
    const type = document.createElement("td");
    type.append(document.createTextNode(issue.issue_type), document.createElement("br"), closureStatus(issue.severity, issue.severity));
    const owner = document.createElement("td");
    owner.append(document.createTextNode(issue.owner), document.createElement("br"), el("small", "", issue.due_date || "—"));
    const status = document.createElement("td");
    status.append(closureStatus(issue.status, issue.status));
    if (issue.resolution_note) status.append(el("div", "closure-note", issue.resolution_note));
    const action = el("td", "closure-actions");
    if (data.status !== "closed" && issue.status !== "Resolved") {
      const process = el("button", "tb-btn", "In Progress");
      process.type = "button";
      process.disabled = issue.status === "In Progress";
      process.addEventListener("click", () => changeClosureIssue(issue, "In Progress").catch(error => showStatus(error.message, true)));
      const resolve = el("button", "tb-btn teal", "Mark as resolved");
      resolve.type = "button";
      resolve.addEventListener("click", () => changeClosureIssue(issue, "Resolved").catch(error => showStatus(error.message, true)));
      action.append(process, resolve);
      if (issue.severity !== "Critical") {
        const accept = el("button", "tb-btn", "Accept Open Items");
        accept.type = "button";
        accept.addEventListener("click", () => changeClosureIssue(issue, "Accept Open Items").catch(error => showStatus(error.message, true)));
        action.append(accept);
      }
    }
    row.append(title, type, owner, status, action);
    tbody.append(row);
  });
  table.append(thead, tbody);
  return table;
}

function renderClosureChecks() {
  const panel = document.getElementById("closure-checks");
  const data = closureState.current;
  clear(panel);
  if (!data) {
    panel.append(el("div", "closure-empty", "Select a campaign from the M1 overview first."));
    return;
  }
  panel.append(closureSummaryStrip(data));

  const checks = el("article", "closure-card");
  const checkHead = el("div", "closure-card-head");
  const checkText = el("div");
  checkText.append(el("h3", "", "Closeout Checklist"), el("p", "", "System status and manual confirmation are shown separately. Unresolved major risks continue to block closeout."));
  checkHead.append(checkText, readinessNode(data.readiness));
  checks.append(checkHead, renderCheckTable(data));

  const grid = el("div", "closure-grid");
  const issues = el("article", "closure-card");
  const issueHead = el("div", "closure-card-head");
  const issueText = el("div");
  issueText.append(el("h3", "", `Open items · ${data.issues.length}`), el("p", "", "Track each issue, its owner, due date, and resolution."));
  issueHead.append(issueText);
  issues.append(issueHead, renderIssues(data));
  const add = el("article", "closure-card");
  const addHead = el("div", "closure-card-head");
  const addText = el("div");
  addText.append(el("h3", "", "Add Open Item"), el("p", "", "Blocking issues must be resolved; they cannot be accepted as open items."));
  addHead.append(addText);
  add.append(addHead);
  if (data.status === "closed") add.append(el("div", "closure-empty", "This version is frozen; no new items can be added."));
  else add.append(issueForm(data));
  grid.append(issues, add);

  const footer = el("div", "closure-actions end");
  const next = el("button", "tb-btn teal", "Next: Complete the Closeout Summary →");
  next.type = "button";
  next.addEventListener("click", () => switchClosureView("archive"));
  footer.append(next);
  panel.append(checks, grid, footer);
}

function summaryForm(data) {
  const summary = data.summary || {};
  const form = el("form", "closure-field-grid");
  const objective = el("label", "closure-field");
  objective.append(el("span", "", "Overall objective result"));
  const select = document.createElement("select");
  select.name = "objective_result";
  ["Unconfirmed", "Achieved", "Partially Achieved", "Not Achieved"].forEach(value => select.append(new Option(value, value)));
  select.value = summary.objective_result || "Unconfirmed";
  objective.append(select);
  const fields = [
    ["executive_summary", "Executive summary", "Summarize the objective, results, causes, and next steps in three to five sentences."],
    ["key_results", "Key business results", "Reference KPIs and measurement definitions from the performance review; do not recalculate them here."],
    ["top_kols", "Top-performing creators", "List creators, their contributions, and reusable lessons."],
    ["risk_kols", "Creators requiring caution or a paused partnership", "Record the risk facts and current list status, or enter “None.”"],
    ["lessons_learned", "Campaign lessons learned", "Describe what worked and what needs improvement."],
    ["next_action", "Recommendations for the next campaign", "Recommend whether to continue, adjust the approach, research further, or discontinue."],
  ];
  form.append(objective);
  fields.forEach(([name, label, placeholder], index) => {
    const wrap = el("label", `closure-field${index < 2 ? " wide" : ""}`);
    wrap.append(el("span", "", label));
    const input = document.createElement("textarea");
    input.name = name;
    input.required = true;
    input.placeholder = placeholder;
    input.value = summary[name] || "";
    wrap.append(input);
    form.append(wrap);
  });
  const actions = el("div", "closure-actions end wide");
  const save = el("button", "tb-btn teal", "Save closeout summary");
  save.type = "submit";
  save.disabled = data.status === "closed";
  actions.append(save);
  form.append(actions);
  form.addEventListener("submit", saveClosureSummary);
  return form;
}

async function saveClosureSummary(event) {
  event.preventDefault();
  const data = closureState.current;
  const values = Object.fromEntries(new FormData(event.currentTarget).entries());
  closureState.current = await closureRequest(`/closures/${encodeURIComponent(data.closure_id)}/summary`, {
    method: "PUT",
    body: JSON.stringify({
      ...values,
      expected_revision: data.revision,
      actor: "Business analyst",
      actor_role: "business_analyst",
    }),
  });
  updateClosureContext();
  renderClosureArchive();
  showStatus("Closeout summary saved.");
}

async function submitCurrentClosure() {
  const data = closureState.current;
  closureState.current = await closureRequest(`/closures/${encodeURIComponent(data.closure_id)}/submit`, {
    method: "POST",
    body: JSON.stringify({
      expected_revision: data.revision,
      actor: "Campaign owner",
      actor_role: "project_owner",
      reason: "Closeout checks and summary completed",
    }),
  });
  updateClosureContext();
  renderClosureArchive();
  showStatus("Closeout package submitted; awaiting brand owner approval.");
}

async function decideCurrentClosure(decision) {
  const data = closureState.current;
  let reason = null;
  if (decision === "Return for More Information") {
    reason = window.prompt("Provide a reason for returning the package.");
    if (!reason) return;
  } else if (!window.confirm("Confirming closure freezes this version as read-only. Continue?")) {
    return;
  }
  closureState.current = await closureRequest(`/closures/${encodeURIComponent(data.closure_id)}/decision`, {
    method: "POST",
    body: JSON.stringify({
      expected_revision: data.revision,
      actor: "Brand owner",
      actor_role: "brand_owner",
      decision,
      reason,
    }),
  });
  updateClosureContext();
  renderClosureArchive();
  showStatus(decision === "Confirm Closure" ? "Campaign closed; final version frozen." : "Closeout package returned for more information.");
}

async function reviseCurrentClosure() {
  const data = closureState.current;
  const reason = window.prompt("Explain why a revised version is needed.");
  if (!reason) return;
  closureState.current = await closureRequest(`/closures/${encodeURIComponent(data.closure_id)}/revise`, {
    method: "POST",
    body: JSON.stringify({
      expected_revision: data.revision,
      actor: "Campaign owner",
      actor_role: "project_owner",
      reason,
    }),
  });
  updateClosureContext();
  renderClosureArchive();
  showStatus(`Created revised version V${closureState.current.version}.`);
}

function renderClosureArchive() {
  const panel = document.getElementById("closure-archive");
  const data = closureState.current;
  clear(panel);
  if (!data) {
    panel.append(el("div", "closure-empty", "Select a campaign from the M1 overview first."));
    return;
  }
  panel.append(closureSummaryStrip(data));
  const grid = el("div", "closure-grid");
  const summary = el("article", "closure-card");
  const summaryHead = el("div", "closure-card-head");
  const summaryText = el("div");
  summaryText.append(el("h3", "", "Closeout Summary"), el("p", "", "The system references evidence; the owner confirms the final business judgment."));
  summaryHead.append(summaryText);
  summary.append(summaryHead, summaryForm(data));

  const side = document.createElement("div");
  const approval = el("article", "closure-card");
  const approvalHead = el("div", "closure-card-head");
  const approvalText = el("div");
  approvalText.append(el("h3", "", "Submission & Approval"), el("p", "", "Required checks, blocking issues, and summary completeness are validated again at submission."));
  approvalHead.append(approvalText);
  approval.append(approvalHead);
  const actions = el("div", "closure-actions");
  if (["not_ready", "draft", "returned", "revised"].includes(data.status)) {
    const submit = el("button", "tb-btn teal", "Submit for closeout approval");
    submit.type = "button";
    submit.addEventListener("click", () => submitCurrentClosure().catch(error => showStatus(error.message, true)));
    actions.append(submit);
  }
  if (data.status === "pending_confirmation") {
    const close = el("button", "tb-btn teal", "Confirm Closure");
    close.type = "button";
    close.addEventListener("click", () => decideCurrentClosure("Confirm Closure").catch(error => showStatus(error.message, true)));
    const reject = el("button", "tb-btn", "Return for More Information");
    reject.type = "button";
    reject.addEventListener("click", () => decideCurrentClosure("Return for More Information").catch(error => showStatus(error.message, true)));
    actions.append(close, reject);
  }
  if (data.status === "closed") {
    approval.append(closureStatus("Final version is read-only", "Closed"));
    const revise = el("button", "tb-btn", "Create a revised version");
    revise.type = "button";
    revise.addEventListener("click", () => reviseCurrentClosure().catch(error => showStatus(error.message, true)));
    actions.append(revise);
  }
  approval.append(actions, el("p", "closure-note", data.blocking_count
    ? `${data.blocking_count} blocking item(s) remain and must be resolved before submission.`
    : "There are no system blockers. Submit when readiness reaches 100% and the summary is complete."));

  const audit = el("article", "closure-card");
  const auditHead = el("div", "closure-card-head");
  const auditText = el("div");
  auditText.append(el("h3", "", "Version & Action History"), el("p", "", "Actions, roles, and reasons are logged without overwriting prior history."));
  auditHead.append(auditText);
  audit.append(auditHead);
  const list = el("ul", "closure-audit");
  [...data.audits].reverse().slice(0, 10).forEach(item => {
    const row = document.createElement("li");
    row.append(el("strong", "", closureActionLabels[item.action] || item.action));
    row.append(document.createTextNode(` · ${item.actor}`));
    if (item.reason) row.append(el("div", "closure-note", item.reason));
    row.append(el("small", "", `V${item.version} · ${closureDateTime(item.created_at)}`));
    list.append(row);
  });
  if (!data.audits.length) list.append(el("li", "", "No action history yet."));
  audit.append(list);
  side.append(approval, audit);
  grid.append(summary, side);
  panel.append(grid);
}

function initClosureModule() {
  document.querySelectorAll("[data-closure-view]").forEach(button => {
    button.addEventListener("click", () => switchClosureView(button.dataset.closureView));
  });
}
