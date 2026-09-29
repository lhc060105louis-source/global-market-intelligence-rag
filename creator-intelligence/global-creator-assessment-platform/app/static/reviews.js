"use strict";

async function loadReviews() {
  const groups = await Promise.all(
    state.kols.map(async kol => ({
      kol,
      records: await api(`/kols/${kol.id}/reviews`),
    })),
  );
  const container = document.getElementById("reviews-list");
  if (!container) return;
  clear(container);
  const records = groups.flatMap(group =>
    group.records.map(record => ({kol: group.kol, record})),
  );
  if (!records.length) {
    container.append(el("div", "empty-state", "No performance reviews yet."));
    return;
  }
  records.forEach(({kol, record}) => {
    const row = el("div", "entity-row");
    row.append(
      el("strong", "", record.campaign),
      el("span", "", kol.name || kol.handle || "Unnamed creator"),
      el("small", "", `Impressions ${record.impressions ?? "—"} · Engagements ${record.engagements ?? "—"} · Conversions ${record.conversions ?? "—"}`),
    );
    container.append(row);
  });
}
