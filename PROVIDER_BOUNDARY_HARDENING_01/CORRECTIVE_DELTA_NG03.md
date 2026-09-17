# CORRECTIVE DELTA — NG-03 / PRE_SEND_PROVENANCE_MISMATCH (HUMAN REVIEW 01)

Verdetto ricevuto: `HUMAN_REVIEW_HOLD — PRE_SEND_PROVENANCE_MISMATCH`. Questo delta corregge SOLO quel blocker,
piu' le correzioni di classificazione richieste su P-B02 e sulle reference del bundle. Nessuna riapertura R0-R1,
nessun provider reale, nessuna reclaim dell'orfana (resta `NOT_AUTHORIZED` / `STILL_OPEN` per decisione umana).

## 1. Difetto, riprodotto sul codice del candidate v1 (`9aafe9b1`)
`evidence/pre_fix/reproduction_ng03.json` (script: `pbgate/reproduce_pre_fix.py` per i gap originali; qui la
riproduzione dedicata e' stata eseguita sul codice non ancora corretto e conservata come evidenza):

| Caso | Percorso | `settlement_source` registrata | Attestazione realmente prodotta |
|---|---|---|---|
| A — `drift_nested` (rifiuto a `mark_submitting`) | `ReservationObserver.mark_submitting` → `store.mark_refused_before_send` | `TRANSPORT_ATTESTED_NOT_SENT` | **nessuna**: `adapter.authorize_payload` non e' ancora stato chiamato e il Core non ha letto `sent_before`/`sent_after` (quelle letture stanno attorno ad `adapter.submit`, mai raggiunto) |
| B — `reorder` (rifiuto dentro `adapter.submit`) | Core `run_job` → `attested_not_sent` → `mark_refused_before_send` | `TRANSPORT_ATTESTED_NOT_SENT` | **si'**: marcatore di invio del trasporto invariato, verificato dal Core |

Entrambi registravano la stessa provenance; solo B era veritiero. Il blocker e' fondato.

## 2. Fix minimo individuato (nessuna modifica del Core)
La domanda decisiva: esiste un percorso del Core che permetta di terminalizzare con settlement 0 **senza**
affermare un'attestazione del trasporto? Si', e sono due API gia' dichiarate nei Protocol del Core
(`ReservationStore.reconcile`, `EconomicLedger.settle`), quindi **nessuna API additiva e' richiesta**:
`CORE_CHANGE_REQUIRED_FOR_TRUTHFUL_PRE_SUBMIT_SETTLEMENT` **NON si applica**.

`runtime/go_candidate.py:ReservationObserver._refuse_pre_submit`, in questo ordine:

1. **osserva** i fatti (`SnapshotBinding.observe_not_dispatched`): marcatore di invio invariato dal sigillo,
   digest sigillato e digest del Core **non** presenti fra quelli autorizzati nel trasporto, guard **non** armato
   per questo tentativo, nessuna attestazione di invio nel ledger snapshot;
2. **verifica** che tutti concordino (`SnapshotBinding.not_dispatched`). Se non concordano: nessuna
   terminalizzazione, nessun settlement, anomalia `PRE_SUBMIT_REFUSAL_NOT_PROVABLE` (fail-closed: un settlement 0
   non provato sarebbe una sottostima economica; una RESERVED non liberata e' il gap gia' dichiarato);
3. `store.reconcile(job, FAILED, evidence)` con `source = RUNTIME_PRE_SUBMIT_REFUSED_NOT_DISPATCHED`,
   `remote_ref = none:never_dispatched`, `transport_attestation: null` e i fatti osservati allegati. Transizione
   ammessa da `RECONCILIATION_TRANSITIONS[RESERVED]`, CAS sulla revisione, evidenza registrata dal Core;
4. `store.settle(job_id, units=0, source = RUNTIME_PRE_SUBMIT_REFUSED_NOT_DISPATCHED)`: riga di ledger `SETTLE 0`
   con la stessa provenance;
5. **una** anomalia `SNAPSHOT_REFUSED_PRE_SUBMIT` con l'esito completo, registrata **dopo** che l'esito esiste
   (nella prima stesura era scritta prima, e dichiarava `terminalized/settled` non ancora avvenuti: corretto).

Il percorso B (rifiuto dentro `adapter.submit`) e' **invariato**: e' il Core a leggere il marcatore e a usare
`TRANSPORT_ATTESTED_NOT_SENT`, che li' e' veritiero.

## 3. Limite noto e accettato, dichiarato
`mark_refused_before_send` fa stato + settlement + ledger + anomalia in **una** transazione. La sostituzione ne usa
**due** (`reconcile`, poi `settle`). L'ordine e' deliberato: un'interruzione fra le due lascia un tentativo
terminale **non regolato**, quindi l'esposizione resta impegnata (comportamento conservativo del Core: "costo
ignoto resta ignoto"), e' visibile in `ledger_totals.terminal_unsettled_jobs` ed e' riparabile perche' `settle` e'
idempotente. L'ordine inverso avrebbe scaricato l'esposizione lasciando la riga viva. Una API additiva del Core
(es. `mark_refused_pre_submit(job, reason, *, source, evidence)`, identica a `mark_refused_before_send` ma con
provenance parametrica) renderebbe l'operazione di nuovo atomica: **proposta per Human Review, non necessaria**
alla correttezza semantica di questo delta (vedi OPEN_GAPS `NG-05`).

## 4. Controprove (B12, `evidence/B12_pre_submit_provenance.json`) — tutte richieste dal review
| # | Caso | Esito verificato |
|---|---|---|
| 1 | `SERIALIZATION_DRIFT` durante il binding | `transport_sent_count 0`; `FAILED`; `settled_units 0`; `settlement_source = RUNTIME_PRE_SUBMIT_REFUSED_NOT_DISPATCHED`; evidenza di riconciliazione con la stessa fonte; `SETTLE 0` con la stessa fonte; la stringa `TRANSPORT_ATTESTED_NOT_SENT` **non compare** in riga, anomalie o ledger di quel job; fatti osservati tutti a conferma |
| 2 | `IDENTITY_DRIFT` (l'`account_id` cambia dopo il sigillo) | identico al caso 1, `refusal_code = IDENTITY_DRIFT` |
| 3 | `PayloadBindingError` dentro `adapter.submit`, marcatore invariato | invariato: `TRANSPORT_ATTESTED_NOT_SENT` in riga, evidenza e ledger |
| 4 | invio avvenuto ed esito incerto (`submit_unknown`) | `transport_sent_count 1`; `SUBMIT_UNKNOWN`; `settled_units` NULL; **nessuna** riga `SETTLE`; nessuna provenance di rifiuto |
| 5 | race / stale write (seconda terminalizzazione con revisione obsoleta) | seconda respinta dal CAS del Core (`StaleWrite`, anomalia `PRE_SUBMIT_TERMINALIZE_REFUSED`), **nessun** settlement tentato; un solo `SETTLE` nel ledger; `settle` ripetuto con lo stesso importo → `duplicate`, non applicato; con importo diverso → `SettlementConflict` registrato e non applicato; totali envelope coerenti (`settled 0`, `exposure 0`, `terminal_unsettled 0`) |

Invariante aggiuntivo (B04): le uniche chiamate a `reconcile` nel runtime, individuate per **AST** (i docstring non
contano), sono `reconciliation.py:reconcile_authenticated` e `go_candidate.py:_refuse_pre_submit` — i due soli
percorsi con provenance esplicita e dichiarata. B06 verifica che i casi di drift non affermino mai l'attestazione
del trasporto.
