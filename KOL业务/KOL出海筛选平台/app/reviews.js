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
    container.append(el("div", "empty-state", "暂无效果复盘记录"));
    return;
  }
  records.forEach(({kol, record}) => {
    const row = el("div", "entity-row");
    row.append(
      el("strong", "", record.campaign),
      el("span", "", kol.name || kol.handle || "未命名 KOL"),
      el("small", "", `曝光 ${record.impressions ?? "—"} · 互动 ${record.engagements ?? "—"} · 转化 ${record.conversions ?? "—"}`),
    );
    container.append(row);
  });
}
