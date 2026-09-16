# RUNTIME_DIFF — P2 `hf_batch.py` (originale) → `runtime/hf_batch_runtime.py` (candidate)

Diff completo: `evidence/RUNTIME_DIFF_hf_batch_P2_vs_candidate.patch` (25 righe rimosse, 55 aggiunte su 236).
Originale: `p2_handoff/VF_RUNTIME_T16_HANDOFF_2026-09-16/P2_RUNTIME/hf_batch.py`, SHA256 `637f3a80…3ea7d1`, **non modificato** (T16, T23).
Candidate: SHA256 in `SHA256SUMS`.

## Cosa cambia, e solo questo

| punto | originale | candidate |
|---|---|---|
| intestazione | docstring P2 | banner "RUNTIME CANDIDATE" + docstring originale conservata |
| import | `urllib.request` | rimosso; aggiunti `runtime.go_candidate`, `runtime.hf_batch_bridge.go_inputs_from_job`, `runtime.provider_gate.RealProviderDisabled`; `sys.path` con la root del gate |
| `_real_cli()` | — | nuova: solleva sempre `REAL_PROVIDER_DISABLED` |
| `Batch.__init__` | solo spec/lock/trace path | in più: `adapter`, `store_path`, `provider_mode="fake"`, `budget_units`, `envelope_units`, `max_polls`, `media_sha256` (default = `sha_file(resolve(ref))`, come nel `fingerprint` originale) |
| `lock` | preflight + `higgsfield --version` | prima istruzione `_real_cli()` → disabilitato in questo gate |
| `quote` | `higgsfield generate cost` + `account status` | prima istruzione `_real_cli()` → disabilitato |
| `run_job` | `subprocess higgsfield generate create … --wait` → `urlretrieve(result_url)` → `GENERATED` | `go_inputs_from_job` → `go_candidate.go(...)` → Core `run_job`; `rec` riporta `reservation_outcome`, `job_id`, `provider_job_id`, `spec_key`, `core_sha`, stato persistito |
| `run_job` guardie conservate | `fingerprint_at_submit` / `RUN_INVALIDATED`; `EXISTS_NOT_OVERWRITTEN` sul file di destinazione | identiche |
| `go` | `bal()` via `higgsfield account status` prima/dopo | `b0 = b1 = None`; nessuna CLI; ritorna la `trace` (per i test) |
| `qa` | invariato | invariato |
| `__main__` | `getattr(b, argv[2])()` | allowlist `lock|quote|go|qa`; senza adapter iniettato `go` si ferma in `REAL_PROVIDER_DISABLED` |

Invariati: `RUN/PILOT/WORK/TENANT/CORE`, `RULES`, `sha_file`, `sha_text`, `git`, `repo_state`, `resolve`,
`prompt`, `media`, `args`, `fingerprint`, `require`, il corpo di `lock`/`quote` dopo il gate, `qa`.

## Differenze semantiche da portare in review

1. **"1 tentativo, mai sovrascrivere"**: nell'originale era una guardia sul file (`EXISTS_NOT_OVERWRITTEN`) più
   `attempt=1`. Nel candidate l'identità della generazione è dello store Core: uno stesso `go` ripetuto mentre il job è
   vivo → `EXISTING_LIVE_JOB` senza submit (T22); dopo un terminale, un nuovo `go` è un **nuovo tentativo autorizzato**
   (C26-E, T18). La regola "non rigenerare un batch concluso" appartiene al layer di produzione, non al runtime.
2. **`CLIENT_FAILED_CHECK_SERVER`** dell'originale (rc≠0 o URL assente) diventa `SUBMIT_UNKNOWN` del Core: non
   terminale, occupa l'identità, richiede riconciliazione (T10). P-B02 resta aperto.
3. **Download e hash dell'output** (`urlretrieve`, `output.sha256`) non esistono nel candidate: il trasporto
   byte-perfect è `transport.pipeline.ingest` del Core, fuori dal perimetro di questo gate (P-B04).
4. **Saldo crediti** (`balance.before/after`) non è più letto dalla CLI: il budget passa per
   `budget_units`/`envelope_units` del Core (T12/T13); il ledger resta P-B03.
5. **Lock preventivo** (`fingerprint`/`require`): conservato tale e quale; in laboratorio è stubbato (T22) perché il
   tenant sul Mac non è in questo ambiente.

## Cosa la copia NON contiene (T19 statico)

Nessun `.submit(`, nessun `find_live_by_spec`, nessun `sqlite3`/SQL, nessun Enum di stati, nessun `urllib`;
`subprocess` verso la CLI provider raggiungibile solo da funzioni che iniziano con `_real_cli()`; `run_job` non
chiama `subprocess`/`urllib`/`os.system`.
