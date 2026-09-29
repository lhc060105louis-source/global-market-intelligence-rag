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
    container.append(el("div", "empty-state", "暂无合同记录"));
    return;
  }
  records.forEach(({kol, record}) => {
    const row = el("div", "entity-row");
    row.append(
      el("strong", "", record.title),
      el("span", "", kol.name || kol.handle || "未命名 KOL"),
      el("small", "", `${record.currency} ${record.amount ?? "待定"} · ${record.status}`),
    );
    container.append(row);
  });
}
