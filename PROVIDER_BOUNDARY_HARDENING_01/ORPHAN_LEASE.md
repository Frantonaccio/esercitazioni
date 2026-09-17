# ORPHAN RESERVED LEASE — stato: STILL_OPEN (riprodotto, formalizzato, nessuna policy introdotta)

## Riproduzione (pre-fix e B08, deterministiche)
`reserve_or_get_live` committa una riga `RESERVED` (operation_id, quote/permit consumati nella stessa transazione);
il processo muore PRIMA di `mark_submitting`. Da quel momento, sul codice attuale:

| Azione | Esito | Evidenza |
|---|---|---|
| `resume` (governato) | `EXISTING_LIVE_JOB/reserved-no-dispatch`, 0 submit, per sempre | B08 `scenario.resume` |
| `new_attempt` stessa operazione | `LIVE_OR_UNCERTAIN_ATTEMPT` (rifiuto), per sempre | B08 `scenario.new_attempt_same_operation` |
| `recover_orphaned_submits` | `[]` (agisce solo su RESERVED **con** intento) | B08 |
| `due_for_reconcile` | la elenca; nessun consumatore la porta altrove | B08 |
| `reserved_units` | budget impegnato per sempre | B08 |
| reconciliation autenticata (P-B02) | `OWNERSHIP_INCOMPLETE`: nessun provider/token/digest → nulla e' stato inviato, nulla da riconciliare | B08 `scenario.reconcile_orphan` |

## Stati formalizzati (`runtime/orphan_lease.py`, classificazione read-only)
- `RESERVED_NO_INTENT` — RESERVED senza provider/attempt_token/payload_digest. Invariante del Core (RV02/RV05):
  `mark_submitting` persiste l'intento PRIMA di `authorize_payload` e del marcatore di invio ⇒ **nessun byte e' stato
  inviato attraverso il percorso governato**. E' l'orfana di questo gap. Uscite disponibili: **nessuna**.
- `RESERVED_WITH_INTENT` — RESERVED con intento (crash fra invio e journal): dominio di `recover_orphaned_submits`
  → `SUBMIT_UNKNOWN` → reconciliation autenticata. NON e' questo gap (B08: crash exit 4 → recover → SUBMIT_UNKNOWN).
- `NOT_RESERVED` — tutto il resto.

## Ownership e lease authority
Una `RESERVED_NO_INTENT` ha `operation_id` ma nessuna identita' di attempt: dai soli dati persistiti e'
**indistinguibile** da una prenotazione viva fatta un istante fa da un altro processo che sta per chiamare
`mark_submitting`. L'unico discriminante e' il tempo (`submitted_at` = istante della prenotazione). Nessuna
finestra di lease, nessun attore autorizzato e nessuna evidenza richiesta sono definiti in Core o Runtime.

## Policy candidata (NON implementata: richiede decisione umana)
1. Recovery ≠ nuovo attempt: la reclaim, se autorizzata, porta la riga a `FAILED` con settlement **0 attestato**
   (percorso esplicito del Core, evidenza `source="STORE_INVARIANT_NO_SUBMIT_INTENT"`, `remote_ref="none:not_sent"`),
   libera identita' di spec/operazione ed esposizione; **non** crea alcun attempt (zero blind retry: la spesa successiva
   resta `intent="new_attempt"` + reason + quote nuova + permit + autorizzazione).
2. Precondizioni: classe `RESERVED_NO_INTENT`, `age_s >= LEASE_WINDOW`, CAS sulla revisione. Race analizzata: se
   `mark_submitting` vince, la reclaim ottiene `StaleWrite` (journal intatto); se vince la reclaim, `mark_submitting`
   ottiene `StaleWrite` PRIMA di `authorize_payload`/send (nessun effetto esterno). Il CAS del Core rende la corsa
   sicura in entrambe le direzioni.
3. Da decidere (Human Review): valore di `LEASE_WINDOW`, chi puo' invocare la reclaim (operatore? scheduler?), se la
   reclaim vada registrata anche come anomalia dedicata, se serva un `settle` esplicito di 0 per quote gia' consumate
   (la quote resta consumata: nuova spesa = nuova quote, coerente con DELTA 02).

Fino alla decisione: `RECLAIM_POLICY = "NOT_AUTHORIZED"`, nessun auto-dispatch, gap `STILL_OPEN` con evidenza.
