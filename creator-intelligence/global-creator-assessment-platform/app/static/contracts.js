"use strict";

async function loadContracts() {
  const groups = await Promise.all(
    state.kols.map(async kol => ({
      kol,
      records: await api(`/kols/${kol.id}/contracts`),
    })),
  );
  const container = document.getElementById("contracts-list");
  clear(container);
  const records = groups.flatMap(group =>
    group.records.map(record => ({kol: group.kol, record})),
  );
  if (!records.length) {
    container.append(el("div", "empty-state", "No contract records yet."));
    return;
  }
  records.forEach(({kol, record}) => {
    const row = el("div", "entity-row");
    row.append(
      el("strong", "", record.title),
      el("span", "", kol.name || kol.handle || "Unnamed creator"),
      el("small", "", `${record.currency} ${record.amount ?? "TBD"} · ${record.status}`),
    );
    container.append(row);
  });
}
