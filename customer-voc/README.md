# Customer VOC calculation engine

`six-dimensions-v3.0/core.py` and `dimensions.py` bundle the original calculation engine used by `sentiment-analysis/voc-sentiment-analysis/six_dimension_service.py`. They use only the Python standard library; `dimensions.py` imports the bundled `core.py` through the service's isolated loader. No separate engine checkout or historical dataset is required.

The engine retains its original emotion taxonomy, source/model deduplication, aggregation keys, sample gates, time windows and formulas. Its NPS prediction is the original **0–10 estimate**, derived from promoter and detractor emotion shares. Direct engine calls require five signals for the gated dimensions; the bucket adapter bypasses that gate to supply all six Hub records even for small buckets.

The adapter translates the analyzer's English emotion names and locally determined risk flags into the engine's Chinese vocabulary, then translates attitude, trend and legal-risk labels into the Hub contract. Brand, region and other business scope fields continue to come from the current records.

The restored files contain calculation code, ontology dictionaries and configurable thresholds. They contain no customer records, credentials, network calls, file loading or bundled demonstrations.

## Dependencies and deterministic checks

Use Python 3.12. From the repository root, install the Hub requirements into an isolated environment for envelope validation and pytest:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r rag/service/requirements.txt
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pytest customer-voc/sentiment-analysis/voc-sentiment-analysis/tests -q
```

These tests use synthetic records, temporary SQLite databases and deterministic retrieval/delivery substitutes. They require no API key, remote model download or live Hub. Run service suites in separate processes because the applications have overlapping Python module names.

The integration suite covers six-dimension aggregation and Hub envelope validation, independent scopes, historical snapshots, retry/recovery, all 28 emotion translations, positive attitude, complaint growth and simultaneous recall/legal intent. A local Hub API smoke test verifies that all six calculated records are stored, repeated delivery is idempotent and two open risks are created. The initial incomplete checkout produced nine missing-engine failures and one passing validation test; the repaired VOC test directory passes 25 tests.

For the full analyzer's PDF/OCR workflow, install `sentiment-analysis/voc-sentiment-analysis/requirements.txt`; semantic retrieval additionally uses `requirements-rag.txt`. Those optional packages are unnecessary for the deterministic calculation and integration checks above. `test_route.py` is a manual retrieval example outside the test directory and may require a configured case store and embedding provider.

If the Windows sandbox cannot access its default temporary directory, use a fresh directory under the ignored environment:

```powershell
$vocTemp = Join-Path (Get-Location) ('.venv/tmp-voc/' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $vocTemp -Force | Out-Null
$env:TEMP = $vocTemp
$env:TMP = $vocTemp
.\.venv\Scripts\python.exe -m pytest customer-voc/sentiment-analysis/voc-sentiment-analysis/tests -q -p no:cacheprovider --basetemp (Join-Path $vocTemp 'pytest')
```
