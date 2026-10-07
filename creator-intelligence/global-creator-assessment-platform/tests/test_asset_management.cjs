const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const elements = new Map();
const requests = [];
const empty = () => ({innerHTML: '', listeners: {}, decision: {options: [{value: 'Approved'}]}, addEventListener(type, callback) { this.listeners[type] = callback; }, querySelectorAll() { return []; }});
const element = id => {
  if (!elements.has(id)) elements.set(id, empty());
  return elements.get(id);
};
const overview = {metrics: {total: 0, preferred: 0, conditional: 0, watch: 0, blocked: 0, major_risk: 0}, assets: [], filters: {country: '', platform: '', status: ''}, updated_at: '2026-10-07', attention: []};
const context = vm.createContext({
  Intl, URLSearchParams, console,
  document: {getElementById: element, querySelectorAll() { return []; }},
  monitorMetric: (label, value) => `${label}: ${value}`,
  showStatus() {},
  FormData: class { entries() { return [['decision', 'Approved'], ['note', 'Recorded project approval']]; } },
  api: async (url, options) => {
    requests.push(url);
    if (url === '/campaigns') return {items: [{campaign_id: 'CMP-REAL', project_name: 'Actual project'}]};
    if (url.startsWith('/reinvestment/portfolio')) return {project: null, candidates: [], scenarios: [], checks: [], prediction_note: 'Unavailable'};
    if (url === '/reinvestment/overview') return overview;
    if (url.startsWith('/reinvestment/evaluations/')) {
      if (options?.method === 'POST') return {decision: 'Approved'};
      return {kol: {kol_id: 1, handle: '@recorded'}, project: null, suggestion_score: null, historical_score: null,
        suggestion_status: 'Insufficient Evidence', data_completeness: 0, major_risk: false, dimensions: [],
        conditions: {}, approval: {decision: 'Pending Approval', note: ''}, note: 'Unavailable'};
    }
    throw new Error(`Unexpected request: ${url}`);
  },
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/asset_management.js'), 'utf8'), context);

(async () => {
  assert.equal(context.assetNumber(null), 'Unavailable');
  assert.equal(context.assetNumber(0), '0');
  assert.equal(context.assetScore(null), 'Unavailable');
  await context.loadAssetArchive();
  await context.loadAssetEvaluation();
  assert.deepEqual(requests, []);
  assert.match(element('asset-archive').innerHTML, /Select a creator/);
  await context.loadAssetPortfolio();
  assert.match(element('asset-portfolio').innerHTML, /No portfolio proposals available/);
  assert.doesNotMatch(element('asset-portfolio').innerHTML, /null|undefined/);
  assert.match(element('asset-portfolio').innerHTML, /CMP-REAL/);
  assert.match(element('asset-portfolio').innerHTML, /Actual project/);
  vm.runInContext('assetState.campaignId = "CMP-REAL";', context);
  await context.loadAssetEvaluation('1');
  await element('asset-approval-form').listeners.submit({preventDefault() {}});
  assert.ok(requests.includes('/reinvestment/evaluations/1/approval?campaign_id=CMP-REAL'));
  console.log('Asset UI empty/unavailable and real campaign selection checks passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
