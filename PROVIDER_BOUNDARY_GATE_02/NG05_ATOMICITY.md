# NG-05 — ATOMICITÀ DELLA TERMINALIZZAZIONE PRE-SUBMIT

## 1. La domanda del mandato, e la risposta letta dal codice

> «Prima verificare se il Core canonico offre già una primitive che possa ottenere in UNA
> transazione: terminalizzazione, settlement zero, provenance parametrica e veritiera, ledger,
> anomaly/evidence, CAS/revision safety.»

**Risposta: NO.** La premessa è falsa, e lo è per lettura del contratto reale (`inspect` sul Core
canonico `740ee979`), non della documentazione. Evidenza:
`evidence/pre_fix/reproduction_ng05_atomicity.json` → `core_surface`.

| primitive del Core | scrive lo stato | scrive `settled_units` | riga ledger `SETTLE` | provenance parametrica | nel Protocol |
|---|---|---|---|---|---|
| `mark_refused_before_send` | sì | sì | sì | **NO** — `TRANSPORT_ATTESTED_NOT_SENT` hardcodata | sì |
| `reconcile` | sì | **NO** | **NO** | no (`source` sta nell'evidenza, ma non produce settlement) | sì |
| `settle` | **NO** | sì | sì | sì (`source`) | **NO** |

`single_transaction_primitive_with_parametric_provenance = []`.

L'unico punto che compone stato + settlement nella stessa transazione è `_set_state(..., extra_sql=…)`,
che è **privato**. Usarlo dal Runtime significherebbe duplicare un'authority esistente e aggirare il
contratto pubblico: vietato dal mandato.

## 2. La finestra, riprodotta con una morte reale del processo

Un processo che chiama `store.reconcile(job, FAILED, evidence)` e poi muore con `os._exit(7)`
prima di `store.settle`:

| | prima | dopo |
|---|---|---|
| stato | `RESERVED` | `FAILED` |
| `settled_units` | `NULL` | **`NULL`** |
| `settlement_source` | `NULL` | **`NULL`** |
| `terminal_unsettled_jobs` | `0` | **`1`** |
| `unsettled_exposure_units` | `10` | **`10`** (mantenuta) |

exitcode osservato: `7`.

**Il comportamento è conservativo, non pericoloso**: l'esposizione resta impegnata (il Core non
tratta "FAILED" come "gratis"), il caso è **visibile** in `terminal_unsettled_jobs` ed è
**riparabile** perché `settle` è idempotente. Il costo è di audit e di rumore operativo, non di
sottostima economica.

## 3. Perché non si può usare `mark_refused_before_send`

Il rifiuto che stiamo terminalizzando avviene a `mark_submitting`, cioè **prima** del trasporto:
`adapter.authorize_payload` non è ancora stato chiamato e il Core non ha letto `sent_before`/
`sent_after` (quelle letture stanno attorno ad `adapter.submit`, che non verrà mai raggiunto).
Registrare `TRANSPORT_ATTESTED_NOT_SENT` significherebbe scrivere nel ledger una provenance **mai
prodotta**. È esattamente il difetto NG-03, chiuso nella fase precedente: non si riapre.

## 4. Decisione

**`CORE_CHANGE_REQUIRED`.**

Il Reality Lock dimostra che la modifica è realmente necessaria, quindi il mandato autorizza un
branch Core dedicato. È stato creato:

```
repo    Frantonaccio/creative-os
branch  harden/provider-boundary-core-atomicity-2026-09-17
base    740ee979300f2859 92528604dee70cb2fcf   (Core main canonico, invariato)
head    9cf9cee1a751f7a2ad6c768574ff5aa38d8db515
```

Il branch vive in un **worktree separato** (`/home/user/creative-os-atomicity`): il tree canonico
`/home/user/creative-os` resta su `main`, pulito, a `740ee979` — verificato da C00 (before) e C08
(after). **Core `main` non è stato toccato.**

## 5. API minima additiva proposta

```python
def mark_refused_pre_submit(self, job: Job, reason: str, *, source: str,
                            evidence: Mapping, now: float) -> Job
```

Identica a `mark_refused_before_send` nella meccanica, diversa in una cosa sola: la **provenance è
parametrica**.

### Invarianti

1. `source` obbligatoria, non vuota.
2. `source` **non può** essere `TRANSPORT_ATTESTED_NOT_SENT`: quella provenance appartiene
   esclusivamente al percorso del trasporto. Qui sarebbe falsa → `ReconciliationEvidenceRequired`.
3. `evidence` è un'evidenza di riconciliazione valida (`source` + `remote_ref` non vuoti) e il suo
   `source` deve **coincidere** con `source`: una sola verità, non due.
4. `reason` obbligatorio e non vuoto.

### Transizione ammessa

Solo `RESERVED → FAILED`, e solo per un tentativo **senza identità remota** (`provider_job_id`
assente). Un job che ha già un'identità presso il provider non è "pre-submit": `TransitionRefused`
più anomalia `PRE_SUBMIT_REFUSAL_NOT_APPLICABLE` con lo stato osservato.

### Modello economico

- `settled_units = 0` scritto **solo** `WHERE settled_units IS NULL`: nessun doppio conteggio.
- Una riga di ledger `SETTLE`, `units = 0`, `cost_known = 1`, `source = <source del chiamante>`.
- Lo zero non è «FAILED quindi gratis»: è «mai inviato, quindi 0, attestato da `<source>`».
- Esposizione sostituita: `unsettled_exposure_units 10 → 0`, `terminal_unsettled_jobs 0`,
  `remaining_units` ripristinato.

### Provenance

Registrata **due volte e coerentemente**: nella riga di ledger (`source`) e nell'anomalia
`RECONCILIATION` con l'evidenza completa del chiamante, inclusi i fatti osservati e
`transport_attestation: null`.

### CAS / concurrency

Compare-and-swap sulla revisione letta, via `_set_state`. Una scrittura concorrente vince e il
rifiuto diventa `StaleWrite`, con la scrittura obsoleta conservata come anomalia. Nulla viene
applicato.

### Atomicità

Stato, settlement, ledger e anomalia sono nella **stessa transazione**. `_set_state` accetta ora
`_crash_hook` (solo test), con la **stessa convenzione già usata da `settle`**: nessuna API nuova
inventata per i test.

## 6. Diff minimo

```
 adapters/base.py                          |  39 +++++++++++++
 registry/reservations.py                  |  91 +++++++++++++++++++++++++++--
 tests/run_ng05_pre_submit_atomicity.py    | 306 +++++++++++++++++++++++++++++
 3 files changed, 436 insertions(+), 3 deletions(-)
```

Patch completa: `evidence/CORE_DELTA_NG05_mark_refused_pre_submit.patch`.

- `adapters/base.py`: dichiarazione nel Protocol `ReservationStore` + controparte in `JobStore`
  (richiesta da CR-03, che pretende che entrambe le implementazioni abbiano tutti i metodi del
  Protocol con firme compatibili).
- `registry/reservations.py`: l'implementazione durevole + `_crash_hook` in `_set_state`.
- `mark_refused_before_send` **invariata**: firma, provenance e comportamento, verificato.

## 7. Test

`tests/run_ng05_pre_submit_atomicity.py` — **8/8 PASS**:

| | test | esito |
|---|---|---|
| A | transazione singola: `os._exit(9)` prima del COMMIT | stato `RESERVED` invariato, revisione invariata, 0 righe `SETTLE`, 0 anomalie `RECONCILIATION`, totali identici; ritentata senza crash → `FAILED` |
| B | provenance parametrica in ledger e anomalia | 1 riga `SETTLE` `units=0` con la `source` del chiamante; anomalia con `transport_attestation: null` |
| C | provenance falsa e evidenze incoerenti | 5 rifiuti fail-closed, journal invariato |
| D | solo `RESERVED` senza identità remota | `SUBMITTED` → `TransitionRefused` + anomalia; `RESERVED` pulita → `FAILED` |
| E | CAS sulla revisione | `StaleWrite`, 0 righe `SETTLE`, anomalia `STALE_WRITE` registrata |
| F | modello economico | esposizione 10 → settled 0, exposure 0, terminal_unsettled 0; ripetizione `TransitionRefused`; 1 sola riga `SETTLE`; `settle(0)` idempotente |
| G | non-regressione | `mark_refused_before_send` invariata |
| H | contratto CR-03 | Protocol + `SqliteReservationStore` + `JobStore` allineati |

Suite esistenti del Core sul branch: **8/8 invariate**
(`run_r0_r1_hardening`, `run_reservation`, `run_review_pr2_final`, `run_review_pr2`, `run_block2`,
`run_golden`, `run_boot_paths`, `run_case_collision`).

Totale verificato da C06: **9/9 suite PASS** sul branch.

## 8. Cosa NON è stato fatto, deliberatamente

- **Il Runtime non è stato commutato.** `runtime/go_candidate.py:ReservationObserver._refuse_pre_submit`
  continua a usare il percorso conservativo `reconcile` → `settle`. Commutarlo richiederebbe di
  spostare il pin del Core su un branch non approvato: il Runtime resta pinnato a `740ee979`
  (`REQUIRED_CORE_SHA`), verificato da C06 (`uses_reconcile_then_settle = true`,
  `uses_new_core_api = false`, `uses_mark_refused_before_send = false`).
- **Nessun merge, nessun tag, nessun deploy, nessuna release.**
- **Core `main` intoccato.**

## 9. Stato

**`NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY = CORE_CHANGE_REQUIRED`** — requisito **aperto**.

Il delta esiste ed è verificato, ma finché non è passato per Human Review e mergiato nel Core, e
finché il pin del Runtime non è spostato di conseguenza, la finestra a due transazioni resta quella
in esercizio. Un test PASS su questo requisito significa che il gate ha verificato che il requisito
**resta aperto**, non che è chiuso.

### Human Review 01: `APPROVED_PROPOSAL — NOT_MERGE_AUTHORIZED`

L'API è stata **accettata come proposta**. Il merge **non** è autorizzato, e il motivo è
strutturale, non procedurale: il Runtime candidate resta pinnato a `740ee979`, continua a usare
`reconcile → settle` e non consuma `mark_refused_pre_submit`. Portare Core `main` a `9cf9cee1`
renderebbe la baseline **incoerente per costruzione** — il Runtime canonico pretenderebbe ancora
il vecchio SHA.

Non esiste ancora una coppia Core+Runtime promuovibile. `merge_readiness` lo dice a macchina:

```
core_candidate_ready    = true
runtime_candidate_ready = true
core_runtime_pair_ready = false
merge_authorized        = false
blockers = [RUNTIME_DOES_NOT_CONSUME_CORE_CANDIDATE,
            REQUIRED_CORE_SHA_PINNED_TO_BASELINE_NOT_CANDIDATE,
            OPEN_REQUIREMENTS,
            HUMAN_MERGE_AUTHORIZATION_ABSENT]
```

La chiusura richiede un **delta coordinato separato**, elencato in
`merge_readiness.next_integration_required` e in `HUMAN_REVIEW_01_CORRECTIVE_DELTA.md`.
Non è stato iniziato.

Nulla qui significa provider ready, production ready, credenziali autorizzate, spend autorizzato,
merge autorizzato o R2 autorizzato.
