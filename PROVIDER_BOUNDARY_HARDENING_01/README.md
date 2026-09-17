# PROVIDER / EXECUTION BOUNDARY HARDENING — EVIDENCE BUNDLE v3 (2026-09-17)

Bundle v3 = v2 + **delta correttivo di reporting** richiesto da Human Review 02
(`HUMAN_REVIEW_HOLD — PHASE_READINESS_REPORTING_INCONSISTENT`). Il v2 chiudeva NG-03
(`CORRECTIVE_DELTA_NG03.md`); il v3 separa l'esito dei test dalla readiness di fase
(`CORRECTIVE_DELTA_REPORTING.md`). Nessuna modifica al runtime, al Core o a P2 in v3.

Stato dichiarato: **`PROVIDER_EXECUTION_BOUNDARY_HARDENING_READY_FOR_HUMAN_REVIEW`** (LAB).
NON significa: provider ready · production ready · credenziali autorizzate · spend autorizzato · merge autorizzato · R2 autorizzato.
Provider reali: 0 · credenziali reali: 0 · rete generativa: 0 · crediti: 0 · Core modificato: no · P2: frozen · main: intoccato.

## Contenuto
| File | Cosa |
|---|---|
| `REALITY_LOCK.md` | Reality Lock iniziale (Core/Runtime/pin/P2/handoff): nessuna deriva |
| `CORRECTIVE_DELTA_NG03.md` | **v2**: blocker, riproduzione, fix minimo scelto, perche' nessuna modifica Core e' richiesta, limite noto, 5 controprove |
| `evidence/pre_fix/reproduction_ng03.json` | **v2**: il difetto di provenance riprodotto sul codice del candidate v1 |
| `PROVENANCE.json` + `SHA256SUMS.EXTERNAL` | **v2**: reference non ambigue (code sha, evidence head sha, branch, base canonica), generate DOPO il commit finale |
| `GAP_MATRIX.md` | matrice pre-fix (gap, file/funzioni reali, riproduzione, rischio, fix minimo, test) |
| `evidence/pre_fix/reproduction_baseline.json` | riproduzioni sul codice NON modificato (`pbgate/reproduce_pre_fix.py`) |
| `TEST_MATRIX.md` / `TEST_RESULTS.md` | matrice e risultati B00..B13 (tri-state) + readiness di fase |
| `pbgate/phase_readiness.py` | **v3**: authority unica di classificazione (test suite vs requisiti di fase) |
| `pbgate/make_manifest.py` | **v3**: MANIFEST.json derivato dallo stesso report |
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
| `runtime/orphan_lease.py` (nuovo) | classificazione read-only `RESERVED_NO_INTENT` / `RESERVED_WITH_INTENT`; `RECLAIM_POLICY = NOT_AUTHORIZED` (invariato in v2: nessuna reclaim) |
| `runtime/provider_gate.py` | interruttore `LEGACY_LAB_SPEND_PATH` / `LegacySpendPathDisabled` / env in sola chiusura |
| `runtime/go_candidate.py` | 1b) legacy switch prima di pin/import/store; 7c) seal + guard + binding; `ReservationObserver.mark_submitting`; `GoResult.payload_snapshot`; **v2**: `_refuse_pre_submit` con provenance veritiera (`reconcile` + `settle`), fail-closed se i fatti non concordano, una sola anomalia registrata dopo l'esito |
| `runtime/payload_snapshot.py` | **v2**: `PRE_SUBMIT_REFUSAL_SOURCE`, `observe_not_dispatched`, `not_dispatched`, `guard.armed`, `ledger.send_attested` |
| `runtime/reconciliation.py` | **v2**: perimetro corretto (binding/autenticazione verificati; custodia del segreto e composizione con P-B01 NON dimostrate dai test; freshness `max_age_s` dichiarata APERTA) |
| `tests/static_checks.py` | inventario import Core: + `adapters.base.PayloadBindingError` (il guard rifiuta con l'eccezione RV02 del Core) |
| `tests/run_gate.py` | `db_for`: pulizia dei ledger `.snapshots/.reconciliation` accanto allo store (igiene di riesecuzione) |
Non modificati: Core, P2, `tests/boundary_mock.py`, `tests/worker.py`, `tests/gate_report.py`, T01-T37 (assert invariati).

<!-- READINESS:BEGIN (generato da pbgate/phase_readiness.py — non modificare a mano) -->
## Stato (authority unica: `pbgate/phase_readiness.py`)

**A. Test suite** — 14/14 PASS, FAIL 0, BLOCKED 0, inventario 14/14 valido: `all_tests_passed = true`, `test_suite_decision = ALL_TESTS_PASS`.

**B. Phase readiness** — `all_requirements_verified = false`, `phase_gate_decision = LAB_GATE_COMPLETE_WITH_OPEN_GAPS`, stato massimo `PROVIDER_EXECUTION_BOUNDARY_HARDENING_READY_FOR_HUMAN_REVIEW`.

Requisiti aperti che impediscono `all_requirements_verified`: `ORPHAN_RESERVED_LEASE`, `LEGACY_SPEND_PATHS_PROVIDER_GATE`, `P_B02_P_B01_COMPOSITION`, `RECONCILIATION_FRESHNESS_NG04`, `NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY`, `REAL_AUTHORIZATION_AND_PRICING`, `REAL_PROVIDER_RECONCILIATION`.

Di questa fase: `ORPHAN_RESERVED_LEASE`, `P_B02_P_B01_COMPOSITION`, `NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY`. Rinviati al Provider Boundary Gate: `LEGACY_SPEND_PATHS_PROVIDER_GATE`, `RECONCILIATION_FRESHNESS_NG04`, `REAL_AUTHORIZATION_AND_PRICING`, `REAL_PROVIDER_RECONCILIATION`.

Un test PASS su un requisito aperto significa che il gate ha verificato che quel requisito resta aperto: non lo chiude. Dettaglio per requisito in `TEST_RESULTS.md` e `OPEN_GAPS.md`.
<!-- READINESS:END -->

## Risultati (sintesi)
Il blocco di stato qui sopra e' generato dall'authority unica (`pbgate/phase_readiness.py`) insieme a
`TEST_RESULTS.md`, `evidence/RESULTS.json` e `MANIFEST.json`: le due domande — "i test hanno prodotto l'esito
atteso?" e "i requisiti della fase sono chiusi?" — hanno risposte separate e non possono contraddirsi
(invariante fail-closed verificato da B13). Dettaglio per requisito in `TEST_RESULTS.md` sezione B e in
`OPEN_GAPS.md`.
