# CHANGED FILES — PROVIDER BOUNDARY GATE / OPEN-GAP CLOSURE (2026-09-17)

## RUNTIME — `Frantonaccio/esercitazioni`, branch `claude/provider-boundary-gate-closure-gd6b3g`

### Modificati (fix minimo, 4 file)

```
 RUNTIME_INTEGRATION_GATE_01/runtime/reconciliation.py   | 144 +++++++++++++++--
 RUNTIME_INTEGRATION_GATE_01/runtime/orphan_lease.py     | 179 ++++++++++++++++++++-
 RUNTIME_INTEGRATION_GATE_01/runtime/provider_gate.py    |  63 ++++++++
 RUNTIME_INTEGRATION_GATE_01/tests/worker.py             |  14 +-
 4 files changed, 385 insertions(+), 15 deletions(-)
```

| file | cosa cambia | perché |
|---|---|---|
| `runtime/reconciliation.py` | `FreshnessPolicy` (classe nuova); `freshness` diventa **argomento obbligatorio** di `reconcile_authenticated` (era `max_age_s: float \| None = None`); `_check_report_shape` non giudica più il valore di `issued_at`; l'attestazione di freshness entra nell'evidenza registrata | NG-04: la freshness non può restare opzionale nel percorso destinato al Provider Boundary Gate. Meccanismo qui, policy no. |
| `runtime/orphan_lease.py` | `LeasePolicy`, `LeaseRefused`, `fencing_token`, `reclaim_orphan_reserved` (tutto nuovo, additivo); `classify_attempt` e `inventory` invariate | Orphan lease: meccanismo parametrico che **pretende** la policy invece di sceglierla. |
| `runtime/provider_gate.py` | `PROVIDER_BOUNDARY_MODE_ENV`, `provider_boundary_mode()`, `refuse_if_provider_boundary_mode()`, `ProviderBoundaryModeEngaged`; `legacy_spend_path_state()` ora chiude anche quando la modalità è ingaggiata | Un solo interruttore per l'intera postura, invece di due da tenere allineati a mano. |
| `tests/worker.py` | `store_call` rifiuta con `PROVIDER_BOUNDARY_MODE_ENGAGED` prima di importare il Core e di aprire lo store | LEGACY #7: helper same-UID che dispaccia direttamente sullo store. |

**Compatibilità**: la modalità Provider Boundary è **disingaggiata per default**, quindi la suite
storica R0-R1 gira esattamente come a baseline (C07: 36/37 PASS, 0 FAIL, T29 `BLOCKED_ENVIRONMENT`
per policy, decisione `LAB_GATE_COMPLETE_WITH_ALLOWED_BLOCKED`).

**Rottura di API deliberata**: `reconcile_authenticated` senza `freshness` ora **rifiuta**. Nessun
chiamante del runtime la invoca (verificato con AST: gli unici chiamanti di `.reconcile` sono
`go_candidate._refuse_pre_submit` e `reconciliation.reconcile_authenticated`), e la suite R0-R1 non
la usa. È il comportamento fail-closed richiesto.

### Non toccati, deliberatamente

| file | perché |
|---|---|
| `runtime/go_candidate.py` | il percorso conservativo `reconcile` → `settle` resta in esercizio finché il delta Core non è approvato (NG-05). Verificato da C06. |
| `runtime/payload_snapshot.py`, `core_pin.py`, `authorization.py`, `genspec_bridge.py`, `hf_batch_*.py` | fuori dal fix minimo. |
| `tests/boundary_mock.py`, `tests/run_gate.py` | la suite storica e il mock same-UID non vanno alterati (T29 resta `BLOCKED` per policy). |
| `PROVIDER_BOUNDARY_HARDENING_01/**` (bundle v3) | il mandato vieta modifiche retroattive. |
| `p2_handoff/**` (P2 frozen) | SHA256 `637f3a80…` invariato, verificato before/after. |
| `RUNTIME_INTEGRATION_GATE_01/evidence/`, `state/` | ripristinati a HEAD dopo la regressione: l'esito di C07 è conservato in `PROVIDER_BOUNDARY_GATE_02/regression/`, l'evidenza storica non viene sovrascritta. |

### Aggiunti — bundle `PROVIDER_BOUNDARY_GATE_02/`

| percorso | contenuto |
|---|---|
| `pbg2/reproduce.py`, `pbg2/repro_workers.py` | PHASE A: riproduzioni pre-fix in processi reali |
| `pbg2/run_gate2.py` | runner del gate C00..C09 |
| `pbg2/gate_workers.py` | helper dei test C03/C04/C05/C06 in processi reali |
| `pbg2/readiness.py` | authority unica di classificazione (test suite ≠ phase readiness) |
| `pbg2/spender_daemon2.py` | daemon spender con l'autorità di firma **dentro** il dominio isolato |
| `pbg2/composition_probe.py` | probe dell'orchestrator per le controprove di composizione |
| `GAP_MATRIX.md` | PHASE A |
| `REALITY_LOCK.md` | before/after |
| `PB01_PB02_COMPOSITION.md` | composizione P-B01+P-B02 |
| `NG04_FRESHNESS.md` | meccanismo vs policy |
| `NG05_ATOMICITY.md` | decisione + Core delta |
| `ORPHAN_LEASE_MECHANISM_POLICY.md` | meccanismo vs policy |
| `LEGACY_SPEND_PATHS_V2.md` | inventario aggiornato |
| `REAL_PROVIDER_PREREQUISITES.md` | prerequisiti real-provider |
| `TEST_RESULTS.md`, `READINESS.json` | generati dall'authority unica |
| `OPEN_REQUIREMENTS.md`, `CHANGED_FILES.md`, `README.md` | consegna |
| `evidence/C00..C09_*.json` | evidenza per test |
| `evidence/pre_fix/reproduction_*.json` | evidenza PHASE A |
| `evidence/raw/*.log` | log grezzi (daemon spender, suite del branch Core) |
| `evidence/CORE_DELTA_NG05_mark_refused_pre_submit.patch` | diff completo del delta Core |
| `regression/r0_r1_RESULTS.json`, `regression/r0_r1_run_gate.log` | regressione R0-R1 |
| `MANIFEST.json`, `SHA256SUMS` | integrità del bundle |

## CORE — `Frantonaccio/creative-os`, branch `harden/provider-boundary-core-atomicity-2026-09-17`

`main` **non toccato**: resta `740ee979300fe20a9382992528604dee70cb2fcf`, working tree pulito
(verificato C00 before e C08 after). Il branch vive in un worktree separato.

```
 adapters/base.py                          |  39 +++++++++++++
 registry/reservations.py                  |  91 +++++++++++++++++++++++++++--
 tests/run_ng05_pre_submit_atomicity.py    | 306 +++++++++++++++++++++++++++++
 3 files changed, 436 insertions(+), 3 deletions(-)
```

| file | cosa cambia |
|---|---|
| `adapters/base.py` | `ReservationStore.mark_refused_pre_submit` dichiarata nel Protocol (additiva); controparte in `JobStore` (richiesta da CR-03) |
| `registry/reservations.py` | `SqliteReservationStore.mark_refused_pre_submit` (additiva); `_set_state` accetta `_crash_hook` (solo test, stessa convenzione già usata da `settle`); `ReconciliationEvidenceRequired` importata |
| `tests/run_ng05_pre_submit_atomicity.py` | nuovo, 8/8 PASS |

`mark_refused_before_send` **invariata** (firma, provenance, comportamento), verificato dal test G.

## Branch e SHA candidati

| repo | branch | SHA |
|---|---|---|
| `Frantonaccio/esercitazioni` | `claude/provider-boundary-gate-closure-gd6b3g` | vedi `MANIFEST.json` → `runtime_commit` |
| `Frantonaccio/creative-os` | `harden/provider-boundary-core-atomicity-2026-09-17` | `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` |

Nessun merge, nessun force-push, nessun tag, nessuna release, nessun deploy.
