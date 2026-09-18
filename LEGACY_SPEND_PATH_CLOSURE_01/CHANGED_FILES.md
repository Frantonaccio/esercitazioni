# FILE TOCCATI

Diff completi: `evidence/CORE_DIFF_spender_boundary.patch`,
`evidence/RUNTIME_DIFF_legacy_spend_closure.patch`.

## CORE — `Frantonaccio/creative-os`, branch `harden/legacy-spend-core-2026-09-18`

Tre commit sullo stesso branch: `44f9ea29` (primo candidate), `605a8d74` (delta
correttivo HR01), `59304455` (delta correttivo HR02). Nessun amend, nessun force-push.

Delta **additivo**: nessuna firma cambiata, nessuna API rimossa, nessun comportamento
alterato per un adapter di laboratorio.

| file | cosa | perche' |
|---|---|---|
| `adapters/base.py` | `SpendCapableAdapter`, `DispatchAuthorization`, `authorize_dispatch`, `grant_dispatch`, `require_governed_dispatch_inputs`, `is_spend_capable`, due eccezioni. **Correttivo:** token di conio nel costruttore, registro dei coniati per identita' (`eq=False`), consumo singolo, guard automatico sugli hook in `__init_subclass__` | il confine dello spender. `submit` e `authorize_payload` sono template method non sovrascrivibili; l'autorizzazione non e' ricevuta ne' costruibile: nasce solo da una rilettura del journal |
| `transport/pipeline.py` | `run_job`: rifiuto pre-prenotazione per uno spender senza input governati; concessione fra `mark_submitting` e `authorize_payload` + `import contextlib`. **Correttivo:** `grant_dispatch` riceve lo STORE, non un'autorizzazione | e' l'arteria: e' li' che il dispatch avviene, quindi e' li' che va autorizzato. Per un adapter non spendibile il contesto e' `nullcontext`: comportamento identico a `9cf9cee1` |
| `registry/reservations.py` | `SqliteReservationStore(path, reconciliation_sources=None)` + controllo in `reconcile`. **HR02:** tabella `dispatch_claims` (`job_id` PRIMARY KEY), `claim_dispatch_authorization` (verifica + claim in UNA transazione) e `dispatch_claim` per l'audit | allowlist opzionale, default inerte. Il claim e' cio' che rende `ONE_ATTEMPT = AT_MOST_ONE_DISPATCH_AUTHORIZATION` vera anche fra processi: il vincolo lo impone il database |
| `tests/run_spender_boundary.py` | **nuovo**, 11 casi + 4 di HR01 (L/M/N/O) + **3 di HR02** (P/Q/R) = 18 | controprove unitarie del confine, sentinella al posto del provider. K e' la non-regressione; L/M/N/O l'autorizzazione fabbricata, gli hook diretti, la firma del grant e il replay; P/Q/R lo stesso attempt in sequenza, fra thread e fra processi |

## RUNTIME — `Frantonaccio/esercitazioni`, branch `claude/legacy-spend-path-closure-c50coy`

### Codice (commit `ad2f9c07`, poi `434e0ea5` e `b2dd6db8` per i due spostamenti del pin)

| file | cosa | perche' |
|---|---|---|
| `RUNTIME_INTEGRATION_GATE_01/runtime/provider_gate.py` | `LEGACY_LAB_PROVIDER_CAPABILITY`, `adapter_is_spend_capable`, `LegacyPathNotProviderCapable`, `require_legacy_lab_spend_path(adapter)` | rende `LAB_ONLY_NON_PROVIDER_CAPABLE` un fatto imposto dal codice. Il **valore** storico dell'interruttore (`ENABLED_LAB_ONLY`) non e' rinominato: i gate approvati lo asseriscono letteralmente |
| `RUNTIME_INTEGRATION_GATE_01/runtime/go_candidate.py` | il rifiuto entra al punto 1b, prima di pin/import/store | perche' "fallisce prima di ogni effetto esterno" sia vero e non approssimativo |
| `RUNTIME_INTEGRATION_GATE_01/runtime/core_pin.py` | `REQUIRED_CORE_SHA` → `59304455`; `9cf9cee1`, `44f9ea29` **e `605a8d74`** in `KNOWN_STALE_CORE_SHAS` | il Runtime pretende il confine del Core; nelle versioni in cui l'autorizzazione era falsificabile, o in cui lo stesso tentativo ne autorizzava due, quella promessa era falsa. Tutti e tre sono Core vecchi, non sconosciuti |
| `RUNTIME_INTEGRATION_GATE_01/tests/worker.py` | `STORE_CALL_ALLOWED` (READ_ONLY / AUTHORITY / CORE_PROBE) e rifiuto `STORE_CALL_METHOD_NOT_ALLOWED` | `store_call` dispacciava qualunque metodo. Ora la superficie e' dichiarata, e il rifiuto precede l'import del Core e l'apertura dello store |

### NON toccato, deliberatamente

- `RUNTIME_INTEGRATION_GATE_01/tests/run_gate.py` — base di non-regressione bit per bit;
- `RUNTIME_INTEGRATION_GATE_01/evidence/` — riscritta dall'esecuzione della suite e
  **ripristinata** dal gate; le due copie che contano stanno in `regression/`;
- `RUNTIME_INTEGRATION_GATE_01/p2_handoff/` — P2 congelato, `637f3a80…` before == after;
- `PROVIDER_BOUNDARY_HARDENING_01/`, `PROVIDER_BOUNDARY_GATE_02/`,
  `CORE_RUNTIME_INTEGRATION_01/` — bundle approvati, verificati intatti in `E11`.

### Nuovo bundle di questa fase

`LEGACY_SPEND_PATH_CLOSURE_01/`

| | |
|---|---|
| `lspc1/spenders.py` | la sentinella: si costruisce sul Core che trova (baseline senza confine / candidate con confine) |
| `lspc1/workers.py` | 17 sonde + esecutore governato + esecutore `hf_batch` governato, ognuna in un processo reale |
| `lspc1/probe_main.py` | esecutore delle sonde come processo a se': serve per far girare le sonde PRE-FIX contro il **Runtime canonico** |
| `lspc1/runner.py` | lancio isolato dei cinque gruppi di sonde |
| `lspc1/inventory.py` | inventario statico AST dei percorsi di spesa |
| `lspc1/migrated.py` | i 20 equivalenti dei test storici |
| `lspc1/run_gate_e.py` | il gate E00–E15 |
| `lspc1/readiness.py` | esito della suite e readiness del requisito, separati |
| `lspc1/threat_model.py` | threat model machine-readable (`E14`) |
| `THREAT_MODEL.md`, `HUMAN_REVIEW_01_CORRECTIVE_DELTA.md`, `HUMAN_REVIEW_02_CORRECTIVE_DELTA.md` | i documenti delle iterazioni 2 e 3 |
| `lspc1/make_bundle.py` | MANIFEST, SHA256SUMS, provenance esterna |
| `evidence/`, `regression/` | evidenza macchina, diff, log, R0-R1 pre e post fix |
| i `.md` di questo bundle | inventario, classificazione, migrazione, controprove, regressioni, requisiti aperti |

## Cosa NON e' stato fatto

Nessun merge, force-push, rebase, squash, amend, tag, release, deploy. Nessuna
scrittura su `main`. Nessuna modifica a Tenant, a P2, ai valori NG-04, ai valori
dell'orphan lease. Nessun `.pyc`, nessun `__pycache__` nel bundle (verificato in `E11`).
