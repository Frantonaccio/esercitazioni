# NG-05 — ATOMICITÀ END-TO-END, RUNTIME → CORE

Il requisito era aperto come `CORE_CHANGE_REQUIRED`: il delta del Core esisteva ed era approvato
come proposta, ma il Runtime non lo consumava. Ora lo consuma, e l'atomicità è dimostrata
attraverso il percorso vero, non a livello di sola API del Core.

## Il percorso, prima e dopo

```
PRIMA (Core 740ee979 — due transazioni)
    ReservationObserver.mark_submitting
      └─ SnapshotBinding.bind  →  PayloadSnapshotError
           └─ _refuse_pre_submit
                ├─ store.reconcile(job, FAILED, evidence)     ← transazione 1
                └─ store.settle(job_id, units=0, source=…)    ← transazione 2
                   ▲ finestra: terminale non regolato

DOPO (Core candidate 9cf9cee1 — una transazione)
    ReservationObserver.mark_submitting
      └─ SnapshotBinding.bind  →  PayloadSnapshotError
           └─ _refuse_pre_submit
                └─ store.mark_refused_pre_submit(job, reason,
                       source=RUNTIME_PRE_SUBMIT_REFUSED_NOT_DISPATCHED,
                       evidence=<fatti osservati>, now=now)   ← UNA transazione
```

Unico call site dell'API, verificato con AST (D01, D06):
`mark_refused_pre_submit → [("go_candidate.py", "_refuse_pre_submit")]`.
`go_candidate` non chiama più né `reconcile` né `settle`.

## 1. SERIALIZATION_DRIFT (D02)

Adapter che serializza byte diversi fra sigillo e submit. Il guard P-B04 rifiuta a
`mark_submitting`, prima di `authorize_payload` e prima di qualunque invio.

| osservato | valore |
|---|---|
| stato | `FAILED` |
| `settled_units` | `0` |
| `settlement_source` | `RUNTIME_PRE_SUBMIT_REFUSED_NOT_DISPATCHED` |
| righe di ledger `SETTLE` | **1** (`units=0`, `cost_known=1`, stessa `source`) |
| anomalie `RECONCILIATION` | **1**, con `transport_attestation: null` |
| report del runtime | `atomic: true`, `core_api: mark_refused_pre_submit`, `terminalized: true`, `settled: true` |
| `transport_sent_count` | `0` |
| `terminal_unsettled_jobs` | `0` |

I fatti osservati allegati all'evidenza dicono *perché* nessun invio era possibile:
`refused_at: "store.mark_submitting (prima di adapter.authorize_payload e di ogni send)"`,
`core_digest_authorized_in_transport: false`, `sealed_digest_authorized_in_transport: false`,
`guard_armed_for_this_attempt: false`, `transport_sent_count_unchanged: true`.

## 2. IDENTITY_DRIFT (D03)

Adapter il cui `account_id` cambia dopo la lettura fatta per il sigillo: il Core persisterebbe
un'ownership diversa da quella sigillata. **Stesso comportamento identico** a D02, stessa
provenance, stessa singola transazione, `transport_sent_count = 0`.

## 3. Crash prima del COMMIT del Core (D04)

Processo reale che muore **dentro** la transazione del Core (`os._exit(13)` via `_crash_hook`,
la convenzione di test già usata da `settle`). Il percorso del runtime è quello vero,
integralmente, fino alla chiamata dell'API.

| dopo il crash (exit `13`) | valore |
|---|---|
| stato | `RESERVED` (invariato) |
| `settled_units` | `null` |
| `revision` | `0` (invariata) |
| righe `SETTLE` | `0` |
| anomalie | `[]` — nessuna `RECONCILIATION`, nessuna `SNAPSHOT_REFUSED_PRE_SUBMIT` |
| totali | `unsettled_exposure_units: 10`, `terminal_unsettled_jobs: 0` |

**Nessuna terminalizzazione parziale, nessun settlement, nessun ledger parziale, nessuna
anomalia parziale.** E la stessa chiusura, ritentata senza crash, riesce:
`FAILED`, `settled_units = 0`, 1 riga `SETTLE`, `terminal_unsettled_jobs = 0`,
`unsettled_exposure_units: 10 → 0`. La transazione abortita non lascia lock né stati intermedi.

Con il percorso a due transazioni, lo stesso crash lasciava `FAILED` + `settled_units = NULL` +
`terminal_unsettled_jobs = 1`. Quella finestra non esiste più.

## 4. Race / revisione obsoleta (D05)

Una seconda chiamata con la vista **precedente alla chiusura** (revisione obsoleta, stato
riportato a `RESERVED` nell'oggetto in memoria) viene rifiutata: `TransitionRefused`.

- `no_double_settlement`: le righe `SETTLE` restano **1**, prima e dopo;
- `journal_unchanged`: la riga persistita è identica.

Il CAS del Core è il fence reale: chi presenta una revisione superata non applica nulla.

## 5. Job non più RESERVED (D05)

`mark_refused_pre_submit` su un job già terminale → `TransitionRefused`. Un tentativo che ha
già un esito non è un rifiuto pre-submit.

## 6. `provider_job_id` già presente (D05)

Job `RESERVED` ma con identità remota persistita → `TransitionRefused`, più anomalia
`PRE_SUBMIT_REFUSAL_NOT_APPLICABLE` che registra stato e `provider_job_id` osservati. La riga
resta `SUBMITTED` con `settled_units = null`: **non diventa gratis**.

## 7. Provenance del trasporto vietata su questo percorso (D05)

`mark_refused_pre_submit(..., source="TRANSPORT_ATTESTED_NOT_SENT")` →
`ReconciliationEvidenceRequired`. Quella fonte appartiene al percorso che la produce davvero, e
ora è il **Core** a impedirne l'uso improprio, non solo la disciplina del Runtime.

---

## NG-03 preservato (D06, D07)

- `mark_refused_before_send` **invariata**: firma
  `(self, job: 'Job', reason: 'str', now: 'float') -> 'Job'`, provenance
  `TRANSPORT_ATTESTED_NOT_SENT`.
- Il runtime **non la chiama da nessuna parte** (AST).
- Controprova **positiva** (D07): quando l'attestazione del trasporto esiste davvero, quel
  percorso registra ancora `FAILED`, `settled_units = 0`,
  `settlement_source = TRANSPORT_ATTESTED_NOT_SENT`, 1 riga `SETTLE` con quella fonte e
  l'evidenza con `source = TRANSPORT_ATTESTED_NOT_SENT`. La fonte non è sparita: è confinata.

## SUBMIT_UNKNOWN invariato (D08)

Invio incerto: resta `SUBMIT_UNKNOWN`, `settled_units = null`, **0** righe `SETTLE`.
`RESUME` non crea un nuovo attempt né un nuovo submit (1 sola riga per l'operazione,
`submits = 0`). `mark_refused_pre_submit` su quel job è **rifiutata**: un invio che può essere
avvenuto non diventa gratis.

## Altri percorsi del Runtime, dichiarati e invariati

`reconcile` e `settle` restano usate da due percorsi **diversi**, fuori dallo scope di questo
delta:

| percorso | metodi | nota |
|---|---|---|
| `reconciliation.reconcile_authenticated` | `reconcile` | report autenticato P-B02 |
| `orphan_lease.reclaim_orphan_reserved` | `reconcile`, `settle` | reclaim dell'orphan lease: conserva la propria sequenza conservativa a due transazioni, **non toccata** da questo delta (requisito separato, `POLICY_DECISION_REQUIRED`) |

Verificato da D06 come inventario esatto dei call site: nessun residuo in `go_candidate`.

## Stato

**`NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY = VERIFIED_LAB`** (era `CORE_CHANGE_REQUIRED`).

Non significa merge autorizzato: `merge_authorized = false`.
