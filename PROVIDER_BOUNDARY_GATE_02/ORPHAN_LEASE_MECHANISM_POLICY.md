# ORPHAN RESERVED LEASE — MECCANISMO vs POLICY

Separazione obbligatoria, richiesta dal mandato. **Il requisito non è chiuso dal fatto che il
meccanismo esista.**

| | |
|---|---|
| **MECCANISMO** | ownership, lease timestamp, lease identity, authority, fencing token / CAS, recovery, zero blind retry, concorrenza, crash durante il reclaim. **Implementato e verificato parametricamente** (C05). |
| **POLICY** | durata del lease, chi può reclamare, quali evidenze servono, quali stati/classi consentono il reclaim, condizioni operative. **Non decisa**: `POLICY_DECISION_REQUIRED`. |

---

## 1. Il gap, riverificato

`evidence/pre_fix/reproduction_orphan_lease.json`.

Una riga `RESERVED` committata da `reserve_or_get_live` il cui processo muore **prima** di
`mark_submitting` non ha intento di submit persistito (`provider = ''`, `attempt_token = NULL`,
`payload_digest = NULL`). Da quel momento, sul Runtime canonico:

| tentativo di uscita | esito osservato |
|---|---|
| `resume` | `EXISTING_LIVE_JOB/reserved-no-dispatch`, `submits = 0` — per sempre |
| `new_attempt` (stessa operazione) | `LIVE_OR_UNCERTAIN_ATTEMPT` — per sempre |
| `recover_orphaned_submits` | `[]` (agisce solo su RESERVED **con** intento) |
| reconciliation autenticata | `OWNERSHIP_INCOMPLETE` (nulla è stato inviato: non c'è nulla da riconciliare) |
| `classify_attempt` | `class = RESERVED_NO_INTENT`, `exits_available = []` |

API pubblica di `runtime/orphan_lease.py` prima del fix: nessun simbolo `lease*` o `reclaim*`
oltre alla costante `RECLAIM_POLICY = "NOT_AUTHORIZED"`. `has_lease_mechanism = false`.

---

## 2. Il meccanismo

`RUNTIME_INTEGRATION_GATE_01/runtime/orphan_lease.py`.

### `LeasePolicy` — il contenitore della decisione, non la decisione

```python
LeasePolicy(*, min_age_s: float,
            reclaim_authority: str,
            allowed_classes: tuple[str, ...],
            required_evidence_keys: tuple[str, ...],
            label: str)
```

Nessun campo ha default. Il modulo non istanzia alcuna policy e non ne suggerisce una.

- **`min_age_s`** — età minima perché una prenotazione sia considerabile orfana. Zero è ammesso ed
  è il più permissivo: non è un default, va scritto.
- **`reclaim_authority`** — identità dell'attore autorizzato. Il meccanismo **confronta soltanto**:
  chi stabilisce che quell'identità sia legittima è fuori da qui.
- **`allowed_classes`** — classi su cui il reclaim è ammesso. Elencare `RESERVED_WITH_INTENT` è
  possibile ma è una decisione umana esplicita: quel caso ha già un'uscita
  (`recover_orphaned_submits` → `SUBMIT_UNKNOWN`).
- **`required_evidence_keys`** — chiavi che l'evidenza del reclaim deve portare.
- **`label`** — chi ha deciso questi valori. Finisce nell'evidenza registrata.

### `fencing_token(job) -> "<job_id>@<revision>"`

Il fence **è** la revisione persistita: qualunque scrittura concorrente la incrementa e il CAS del
Core rifiuta chi presenta quella vecchia. Il token la rende esplicita e trasportabile, perché
classificazione e reclaim possono avvenire in processi diversi.

### `reclaim_orphan_reserved(...)` — ordine fail-closed

Nessuna scrittura prima del passo 7.

| # | controllo | rifiuto |
|---|---|---|
| 1 | POLICY presente e del tipo giusto | `POLICY_DECISION_REQUIRED` / `LEASE_POLICY_INVALID` |
| 2 | AUTHORITY: `actor == policy.reclaim_authority` | `RECLAIM_NOT_AUTHORIZED` |
| 3 | EVIDENZA: chiavi richieste presenti e non vuote | `RECLAIM_EVIDENCE_INCOMPLETE` |
| 4 | OWNERSHIP: job riletto dallo store **autorevole**, classe ammessa dalla policy | `JOB_UNKNOWN` / `RECLAIM_CLASS_NOT_ALLOWED` |
| 5 | FENCE: `token == fencing_token(job)` riletto adesso | `FENCING_TOKEN_STALE` |
| 6 | LEASE: `age >= policy.min_age_s`, misurata su `submitted_at` | `LEASE_NOT_EXPIRED` |
| 7 | TERMINALE: `store.reconcile(job, FAILED, evidence)` — percorso esplicito del Core, transizione validata, **CAS sulla revisione letta al passo 4** | `StaleWrite` |
| 8 | SETTLEMENT: `store.settle(units=0, source=RUNTIME_ORPHAN_RESERVED_RECLAIMED_NOT_DISPATCHED)` | `SettlementConflict` |

### Provenance

`RUNTIME_ORPHAN_RESERVED_RECLAIMED_NOT_DISPATCHED`, `remote_ref = none:never_dispatched`.

Lo zero è attestato dal **fatto osservato**: nessun intento di submit persistito, quindi nulla è
stato inviato attraverso il percorso governato (il Core persiste l'intento **prima** di autorizzare
i byte e **prima** del marcatore di invio). Non è l'attestazione del trasporto, e non è una risposta
del provider: la classificazione osservata viene allegata all'evidenza.

### Zero blind retry

Il reclaim **non crea** un nuovo attempt: nessuna quote, nessun permit, nessun submit. La spesa
successiva resta `intent="new_attempt"` + reason + quote + permit + autorizzazione.
Verificato: `attempts_for_operation` resta di lunghezza 1 dopo il reclaim.

---

## 3. Cosa è stato verificato (C05, `evidence/C05_orphan_lease_mechanism_policy.json`)

Policy **di prova** iniettata dal test (non una decisione):
`min_age_s = 3600`, `reclaim_authority = "LAB_TEST_OPERATOR"`,
`allowed_classes = (RESERVED_NO_INTENT,)`,
`required_evidence_keys = ("incident_ref", "observed_by")`,
`label = "LAB_TEST_PARAMETER_NOT_A_POLICY_DECISION"`.

| caso | esito |
|---|---|
| policy omessa | `POLICY_DECISION_REQUIRED` |
| policy di tipo sbagliato | `LEASE_POLICY_INVALID` |
| attore diverso dall'authority | `RECLAIM_NOT_AUTHORIZED` |
| evidenza incompleta | `RECLAIM_EVIDENCE_INCOMPLETE` |
| evidenza non mapping | `RECLAIM_EVIDENCE_INCOMPLETE` |
| lease non scaduto | `LEASE_NOT_EXPIRED` |
| fencing token stantio | `FENCING_TOKEN_STALE` |
| classe non ammessa (attempt **con** intento) | `RECLAIM_CLASS_NOT_ALLOWED` |
| reclaim ripetuto su un terminale | `RECLAIM_CLASS_NOT_ALLOWED` |
| **reclaim legittimo** | `FAILED`, `settled_units = 0`, `settlement_source = RUNTIME_ORPHAN_RESERVED_RECLAIMED_NOT_DISPATCHED`, 1 sola riga ledger `SETTLE`, anomalie `RECONCILIATION` + `ORPHAN_RESERVED_RECLAIMED`, esposizione rilasciata, `terminal_unsettled_jobs = 0`, **nessun nuovo attempt** |

Su **ogni** rifiuto: `journal_unchanged = true`.

### Concorrenza

| corsa | esito |
|---|---|
| `mark_submitting` vince, il reclaim arriva con vista superata | reclaim rifiutato (`RECLAIM_CLASS_NOT_ALLOWED`: la classe è il controllo più esterno). Riga **intatta**: `RESERVED`, `attempt_token = att_race`, `settled_units = NULL` |
| scrittura concorrente **neutra** (`put`) che non cambia la classe | `FENCING_TOKEN_STALE` — il fence è un fence anche quando la classe non cambia; classificazione ancora `RESERVED_NO_INTENT` |
| **il reclaim vince**, poi `mark_submitting` con la vista precedente | `StaleWrite` — **nessun submit è più possibile dopo un reclaim**. È la proprietà che conta |

### Crash durante il reclaim

Processo reale che muore fra terminalizzazione e settlement (`os._exit(11)`):

- dopo il crash: `FAILED`, `settled_units = NULL`, `terminal_unsettled_jobs = 1` — **visibile**;
- riparazione: `settle(units=0, source=…)` → `applied = true`;
- ripetizione: `applied = false` (**idempotente**, nessun doppio conteggio);
- dopo la riparazione: `terminal_unsettled_jobs = 0`.

È la **stessa** finestra conservativa di NG-05, e la stessa cura: il reclaim non introduce un
rischio nuovo.

---

## 4. La policy: le decisioni che mancano

| decisione | perché non può essere presa qui |
|---|---|
| **`min_age_s`** — quanto attendere | Dipende dal tempo massimo realistico fra `reserve_or_get_live` e `mark_submitting` nel deployment reale. Un valore troppo basso reclama prenotazioni **vive**; troppo alto lascia l'operazione bloccata. Nessun dato operativo in questa fase. |
| **`reclaim_authority`** — chi può reclamare | Un operatore umano? Un job di manutenzione? Lo spender stesso? Ha implicazioni di sicurezza: chi può reclamare può liberare l'identità di una spec e abilitare una nuova spesa. |
| **`required_evidence_keys`** — quali evidenze | Un riferimento a un incidente? L'esito di una verifica che il processo originario è davvero morto? Serve sapere quali evidenze sono **ottenibili**. |
| **`allowed_classes`** — quali stati | `RESERVED_NO_INTENT` è il caso naturale. Ammettere `RESERVED_WITH_INTENT` significherebbe scavalcare `recover_orphaned_submits` e la reconciliation: è una decisione, non un default. |
| **condizioni operative** | Il reclaim è manuale o automatico? Se automatico, con quale frequenza e con quale limite di volume? |

Il meccanismo è **parametrico** proprio per non scegliere implicitamente: senza `LeasePolicy`
esplicita rifiuta, e `RECLAIM_POLICY` resta `NOT_AUTHORIZED`.

---

## 5. Stati

| requisito | stato |
|---|---|
| `ORPHAN_RESERVED_LEASE_MECHANISM` | **`VERIFIED_LAB`** |
| `ORPHAN_RESERVED_LEASE_POLICY` | **`POLICY_DECISION_REQUIRED`** |

`C05 PASS` significa: il gate ha verificato che il meccanismo esiste, è fail-closed e non sceglie
la policy — e che il requisito **resta aperto**. Non significa che l'orphan lease sia chiuso.

Nulla qui significa provider ready, production ready, credenziali autorizzate, spend autorizzato,
merge autorizzato o R2 autorizzato.
