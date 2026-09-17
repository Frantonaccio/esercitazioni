# PROVIDER / EXECUTION BOUNDARY HARDENING — EVIDENCE BUNDLE 01 (2026-09-17)

Stato dichiarato: **`PROVIDER_EXECUTION_BOUNDARY_HARDENING_READY_FOR_HUMAN_REVIEW`** (LAB).
NON significa: provider ready · production ready · credenziali autorizzate · spend autorizzato · merge autorizzato · R2 autorizzato.
Provider reali: 0 · credenziali reali: 0 · rete generativa: 0 · crediti: 0 · Core modificato: no · P2: frozen · main: intoccato.

## Contenuto
| File | Cosa |
|---|---|
| `REALITY_LOCK.md` | Reality Lock iniziale (Core/Runtime/pin/P2/handoff): nessuna deriva |
| `GAP_MATRIX.md` | matrice pre-fix (gap, file/funzioni reali, riproduzione, rischio, fix minimo, test) |
| `evidence/pre_fix/reproduction_baseline.json` | riproduzioni sul codice NON modificato (`pbgate/reproduce_pre_fix.py`) |
| `TEST_MATRIX.md` / `TEST_RESULTS.md` | matrice e risultati B00..B11 (tri-state) |
| `evidence/B*.json`, `evidence/RESULTS.json`, `evidence/raw/*.log` | evidenza strutturata e log grezzi |
| `evidence/RUNTIME_DIFF_hardening.patch` | diff completo del Runtime (file modificati + nuovi) |
| `regression/` | regressione R0-R1 (`run_gate.py` T01-T37) sul runtime modificato: log, RESULTS.json, TEST_RESULTS.md |
| `LEGACY_SPEND_PATHS.md` | inventario dei percorsi spendibili + stato |
| `ORPHAN_LEASE.md` | orphan RESERVED lease: riproduzione, stati, policy candidata, STILL_OPEN |
| `P_B01_ENVIRONMENT.md` | design eseguibile del confine, precondizioni ambiente, evidenza, limiti |
| `OPEN_GAPS.md` · `P2_FREEZE.md` · `BASELINE_PAIR.md` | gap aggiornati, freeze P2, coppia Core/Runtime |
| `MANIFEST.json` · `SHA256SUMS` | manifest del bundle e checksum di ogni file (`sha256sum -c SHA256SUMS`) |
| `pbgate/` | runner (`run_boundary_gate.py`), helper in processi reali (`pb_worker.py`), daemon spender P-B01 (`spender_daemon.py`), probe orchestrator (`orchestrator_probe.py`), riproduzione pre-fix |

## Esecuzione
```
cd PROVIDER_BOUNDARY_HARDENING_01
CREATIVE_OS_CORE_PATH=/home/user/creative-os PYTHONDONTWRITEBYTECODE=1 python3 pbgate/run_boundary_gate.py
```
Richiede il Core al pin `740ee979…` (clone pulito, con il commit stale `9afaddf` raggiungibile per T03/T20) e, per B01, un
ambiente con `CAP_SETUID` + `setpriv` (altrimenti B01/B09 → `BLOCKED_ENVIRONMENT`, mai PASS simulato). B10 riesegue il gate
storico e ripristina i file tracciati che esso riscrive (`git checkout` di evidence/, state/, TEST_RESULTS.md).

## File Runtime modificati / aggiunti (`RUNTIME_INTEGRATION_GATE_01/`)
| File | Modifica |
|---|---|
| `runtime/payload_snapshot.py` (nuovo) | P-B04: ledger write-once content-addressed, `SnapshotGuardedTransport`, `SnapshotBinding` |
| `runtime/reconciliation.py` (nuovo) | P-B02: report HMAC, binding, ownership, nonce monouso, audit snapshot, poi `store.reconcile` |
| `runtime/orphan_lease.py` (nuovo) | classificazione read-only `RESERVED_NO_INTENT` / `RESERVED_WITH_INTENT`; `RECLAIM_POLICY = NOT_AUTHORIZED` |
| `runtime/provider_gate.py` | interruttore `LEGACY_LAB_SPEND_PATH` / `LegacySpendPathDisabled` / env in sola chiusura |
| `runtime/go_candidate.py` | 1b) legacy switch prima di pin/import/store; 7c) seal + guard + binding; `ReservationObserver.mark_submitting`; `GoResult.payload_snapshot` |
| `tests/static_checks.py` | inventario import Core: + `adapters.base.PayloadBindingError` (il guard rifiuta con l'eccezione RV02 del Core) |
| `tests/run_gate.py` | `db_for`: pulizia dei ledger `.snapshots/.reconciliation` accanto allo store (igiene di riesecuzione) |
Non modificati: Core, P2, `tests/boundary_mock.py`, `tests/worker.py`, `tests/gate_report.py`, T01-T37 (assert invariati).

## Risultati (sintesi)
Vedi `TEST_RESULTS.md`: B00..B11 12/12 PASS, `LAB_GATE_COMPLETE_ALL_VERIFIED`; regressione R0-R1 36/37 PASS + T29
`BLOCKED_ENVIRONMENT` (per policy, mock same-UID invariato), 0 FAIL. Stati per gap in `OPEN_GAPS.md`.
