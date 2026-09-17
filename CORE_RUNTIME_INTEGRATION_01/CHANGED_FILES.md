# CHANGED FILES — COORDINATED CORE + RUNTIME INTEGRATION (NG-05)

## RUNTIME — `Frantonaccio/esercitazioni`

Branch: **`integrate/provider-boundary-core-runtime-2026-09-17`**, creato dal reviewed head
`4a73cdad18034e7c1bd9842a37e34e0273f9325a`.

### Codice funzionale (2 file)

```
 RUNTIME_INTEGRATION_GATE_01/runtime/go_candidate.py | 63 +++++++++++-----------
 RUNTIME_INTEGRATION_GATE_01/runtime/core_pin.py     | 18 ++++--
 2 files changed, 46 insertions(+), 35 deletions(-)
```

| file | cosa cambia |
|---|---|
| `runtime/go_candidate.py` | `_refuse_pre_submit`: `store.reconcile(...)` + `store.settle(...)` → **una sola** `store.mark_refused_pre_submit(...)`. Report arricchito con `atomic` e `core_api`. Provenance, fatti osservati e fail-closed invariati. |
| `runtime/core_pin.py` | `REQUIRED_CORE_SHA` → `9cf9cee1…`; la baseline `740ee979…` entra in `KNOWN_STALE_CORE_SHAS`. |

Dettaglio riga per riga: `RUNTIME_DIFF.md`.

### Bundle nuovo — `CORE_RUNTIME_INTEGRATION_01/`

| percorso | contenuto |
|---|---|
| `cri1/run_gate_d.py` | runner del gate D00..D12 |
| `cri1/workers.py` | helper end-to-end in processi reali (NG-05, NG-03, SUBMIT_UNKNOWN, pin) |
| `cri1/readiness.py` | authority unica: test suite / phase readiness / **pair readiness** |
| `cri1/make_bundle.py` | confezionamento in due passi, riusa la provenance approvata |
| `README.md` | stato e come rieseguire |
| `REALITY_LOCK.md` | input approvati, before/after |
| `RUNTIME_DIFF.md` | il diff coordinato |
| `NG05_END_TO_END.md` | le sei dimostrazioni di atomicità + NG-03 + SUBMIT_UNKNOWN |
| `OPEN_REQUIREMENTS.md` | requisiti aperti e pair readiness |
| `CHANGED_FILES.md` | questo file |
| `TEST_RESULTS.md`, `READINESS.json` | generati dall'authority unica |
| `evidence/D00..D12_*.json` | evidenza per test |
| `evidence/mechanisms/` | evidenza delle regressioni dei meccanismi sul Core candidate |
| `regression/r0_r1_*_candidate.*` | regressione R0-R1 contro il candidate |
| `MANIFEST.json`, `SHA256SUMS` | integrità del bundle |

### Non toccati

| | |
|---|---|
| `runtime/payload_snapshot.py`, `reconciliation.py`, `orphan_lease.py`, `provider_gate.py`, `authorization.py`, `genspec_bridge.py`, `hf_batch_*.py` | invariati |
| `tests/` del gate storico, `boundary_mock.py`, `run_gate.py`, `worker.py` | invariati: nessun test storico indebolito |
| `PROVIDER_BOUNDARY_GATE_02/` (bundle approvato) | invariato, verificato da D11 |
| `PROVIDER_BOUNDARY_HARDENING_01/` (bundle v3) | invariato, verificato da D11 |
| `p2_handoff/` (P2 frozen) | invariato, `637f3a80…` before == after |
| `RUNTIME_INTEGRATION_GATE_01/evidence/`, `state/` | ripristinati a HEAD dopo la regressione; l'esito di D10 vive in `regression/` |

## CORE — `Frantonaccio/creative-os`

**Nessun commit.** Il candidate approvato resta esattamente
`9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` su
`harden/provider-boundary-core-atomicity-2026-09-17`, base `740ee979…`.

`main` invariato a `740ee979300fe20a9382992528604dee70cb2fcf`, working tree pulito.

Nessuno `STOP — APPROVED_CORE_CANDIDATE_INSUFFICIENT`: l'API approvata è bastata così com'era.

## SHA e branch

| repo | branch | SHA | significato |
|---|---|---|---|
| `Frantonaccio/esercitazioni` | `integrate/provider-boundary-core-runtime-2026-09-17` | `MANIFEST.json` → **`runtime_code_sha`** | commit con il diff funzionale coordinato |
| `Frantonaccio/esercitazioni` | idem | `PROVENANCE.json` → **`runtime_evidence_head_sha`** | commit che aggiunge manifest e checksum |
| `Frantonaccio/esercitazioni` | base canonica | `canonical_runtime_base_sha` = `0698279703ab…` | |
| `Frantonaccio/esercitazioni` | base revisionata | `reviewed_runtime_base_sha` = `4a73cdad1803…` | reviewed head approvato |
| `Frantonaccio/creative-os` | `harden/provider-boundary-core-atomicity-2026-09-17` | `9cf9cee1a751…` | `APPROVED_PROPOSAL — NOT_MERGE_AUTHORIZED` |

La chiave ambigua `runtime_commit` non esiste: il verificatore la rifiuta con
`AMBIGUOUS_MANIFEST_KEY`.

**Nessun merge, nessun rebase, nessun squash, nessun amend, nessun force-push, nessun tag,
nessun deploy.** `merge_authorized = false`.

### Nota sul branch di sessione

Il classifier di questa sessione impone `claude/provider-boundary-gate-closure-gd6b3g`, che
porta il lavoro già revisionato ed è rimasto intatto. Questa integrazione vive sul branch
dedicato richiesto dalla review, `integrate/provider-boundary-core-runtime-2026-09-17`, come da
autorizzazione esplicita.
