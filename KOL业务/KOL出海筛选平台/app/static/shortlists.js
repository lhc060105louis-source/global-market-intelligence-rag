"use strict";

async function loadShortlists() {
  const shortlists = await api("/shortlists");
  const container = document.getElementById("shortlists-list");
  clear(container);
  if (!shortlists.length) {
    container.append(el("div", "empty-state", "尚未创建候选名单"));
    return;
  }
  shortlists.forEach(shortlist => {
    const row = el("div", "entity-row");
    row.append(
      el("strong", "", shortlist.name),
      el("span", "", shortlist.target_country || "多市场"),
      el("small", "", `${shortlist.items.length} 位 KOL`),
    );
    container.append(row);
  });
}

async function createShortlist(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form));
  if (!data.target_country) data.target_country = null;
  await api("/shortlists", {
    method: "POST",
    body: JSON.stringify(data),
  });
  form.reset();
  await loadShortlists();
  showStatus("候选名单已创建");
}
