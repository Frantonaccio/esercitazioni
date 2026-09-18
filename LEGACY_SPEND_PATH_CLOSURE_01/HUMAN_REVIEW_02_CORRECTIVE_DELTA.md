# HUMAN REVIEW 02 — DELTA CORRETTIVO

**Verdetto ricevuto:** `HUMAN_REVIEW_HOLD — SAME_ATTEMPT_AUTHORIZATION_REISSUABLE`
**Stato dopo questo delta:** vedi `READINESS.json`

---

## Il blocker

Il delta della Human Review 01 aveva chiuso *la fotocopia della chiave*:
`DispatchAuthorization` non si costruisce, il registro dei coniati è per identità, la
stessa autorizzazione non si riusa.

Aveva lasciato aperta *la seconda chiave originale per la stessa camera*.

`authorize_dispatch` **leggeva** il journal e coniava un oggetto. La lettura era
corretta — stato `RESERVED`, ownership, digest, quote consumata, ledger `RESERVE` —
ma non **consumava** nulla. Finché la riga restava `RESERVED`, una seconda chiamata
trovava esattamente gli stessi fatti autorevoli e coniava una seconda autorizzazione,
distinta dalla prima: `minted`, non `spent`, valida.

Il registro `_SPENT` era per **identità dell'oggetto**, non per
`(job_id, attempt_token)`. E `mark_submitting` conserva proprio lo stato `RESERVED`:
persiste `submit_intent_at`, digest e attempt token, ma non chiude nulla.

### Riprodotto con soli fatti autorevoli

Nessun oggetto fabbricato, nessuno store duck-typed: store reale, prenotazione
governata reale, quote LAB reale, ledger `RESERVE` reale, stesso `job_id`, stesso
`attempt_token`. È il punto: il bypass non aveva bisogno di mentire su nulla.

Sequenza eseguita su `605a8d74` (`evidence/E15_same_attempt_authorization_reissuable.json`):

| passo | esito |
|---|---|
| `g1 = grant_dispatch(...)`, `authorize_payload`, `submit` | **riuscito** (`pv_9b604401`) |
| riga dopo il dispatch #1 | ancora **`RESERVED`** — nessun `mark_submitted` |
| `g2 = grant_dispatch(...)` stesso attempt, `submit` | **riuscito** |
| due conii **prima** di qualunque uso | **due grant distinti** |
| due **thread** concorrenti | **entrambi** ottengono l'autorizzazione |
| **sentinella** | `reached = 2`, `sent = 2` |
| claim persistito nel journal | **nessuno** |

`BLOCKER_REPRODUCED`.

---

## Il fix — la decisione torna al journal

La proprietà da imporre non era "questo oggetto non si riusa" ma:

```
ONE_ATTEMPT = AT_MOST_ONE_DISPATCH_AUTHORIZATION
```

e una proprietà del genere non può vivere in un registro Python in memoria, perché
deve sopravvivere a due processi.

### `registry/reservations.py` — `claim_dispatch_authorization`

Tabella `dispatch_claims` con **`job_id` come PRIMARY KEY**. L'ownership di un
tentativo è write-once, quindi un job ha un solo `attempt_token` e quindi un solo
claim.

In **una** transazione `BEGIN IMMEDIATE`:

1. verifica `RESERVED` senza identità remota;
2. verifica spec, operazione, `attempt_token`, `payload_digest`, provider e conto
   contro la riga persistita;
3. verifica `quote_id` presente, quote **consumata da questo job**, legata alla stessa
   operazione, alla stessa spec, a un envelope;
4. verifica il movimento di ledger `RESERVE`;
5. verifica che **nessun claim esista già**;
6. **INSERT** del claim;
7. COMMIT.

Un secondo claim è `DISPATCH_AUTHORIZATION_ALREADY_CLAIMED`, registrato in
`anomalies`. Il vincolo lo impone il **database**, quindi vale fra chiamate, fra
thread e fra **processi**.

### `adapters/base.py` — `authorize_dispatch` non legge più: claima

Delega interamente alla primitive dello store. Uno store che non la espone è
`DISPATCH_CLAIM_AUTHORITY_MISSING`: fail-closed, perché senza quella garanzia non
esiste autorizzazione.

Le verifiche **non** sono duplicate in `adapters/base.py`: due copie della stessa
regola sono due regole che prima o poi divergono.

### Le due proprietà, entrambe necessarie

| proprietà | meccanismo | controprova |
|---|---|---|
| un'autorizzazione è **one-use** | registro `_SPENT`, per identità dell'oggetto | `run_spender_boundary:O` |
| un attempt è **one-authorization** | claim persistito, `job_id` PRIMARY KEY | `run_spender_boundary:P/Q/R`, `E15` |

La prima senza la seconda lascia chiedere due chiavi originali. La seconda senza la
prima lascia riusare la stessa chiave.

---

## Semantica di crash — dichiarata, non implicita

Il fix non doveva diventare una nuova scorciatoia di retry. Non lo è:

| caso | comportamento |
|---|---|
| **A** — arresto **prima** del COMMIT del claim | nessun claim, nessuna autorizzazione. Un tentativo successivo è il **primo**, non un blind retry |
| **B** — arresto **dopo** il claim e **prima** del submit | il claim resta. Una seconda richiesta è `ALREADY_CLAIMED`, **non** un nuovo dispatch: il tentativo entra nel recovery già governato (`recover_orphaned_submits` → `SUBMIT_UNKNOWN` → riconciliazione) |
| **C** — invio incerto | `SUBMIT_UNKNOWN` preservato, zero blind retry, invariato |

**Il claim non è rilasciabile.** Se lo fosse, sarebbe esattamente la scorciatoia che
tutto il resto di questo modulo esiste per non avere.

---

## Esito dopo il fix — `59304455`

| verifica | esito | sentinella |
|---|---|---|
| dispatch #1 governato | `SUCCEEDED` | **1** |
| dispatch #2, stesso attempt, riga ancora `RESERVED` | `DISPATCH_AUTHORIZATION_ALREADY_CLAIMED` | resta **1** |
| due conii prima di qualunque uso | `DISPATCH_AUTHORIZATION_ALREADY_CLAIMED` | **0** |
| due **thread** concorrenti | 1 claim, 1 `ALREADY_CLAIMED` | **0** |
| due **PROCESSI** concorrenti, stesso file di journal | 1 claim, 1 `ALREADY_CLAIMED`, PID distinti | **0** |
| claim persistito e leggibile (`dispatch_claim`) | sì | |

Il caso multi-processo è stato **eseguito**, non simulato: `distinct_processes = 2`,
`blocked_environment = false`. È il caso che un registro in memoria non supererebbe, ed
è la ragione per cui il claim sta nel journal.

---

## Non riaperto

I fix approvati dalla Human Review 01 restano verdi e invariati: costruttore
fabbricato, slot injection, hook diretti, firma di `grant_dispatch`. I casi H e I
sono stati aggiornati perché il rifiuto ora arriva **prima e più stretto** — `H`
non può più aprire un secondo grant sullo stesso attempt per testare la rientranza
(la testa sull'oggetto attivo), `I` riceve `DISPATCH_CLAIM_AUTHORITY_MISSING` invece
di `DISPATCH_QUOTE_AUTHORITY_MISSING`. Nessun assert indebolito.

`SNAPSHOT_SEAL_WRITE_RACE` resta `STILL_OPEN`, classificazione invariata, non corretto
qui.
