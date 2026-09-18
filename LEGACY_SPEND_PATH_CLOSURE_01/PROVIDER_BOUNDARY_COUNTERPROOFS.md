# CONTROPROVE DEL CONFINE PROVIDER — la sentinella

Evidenza: `evidence/E02_pre_fix_reproduction.json` (coppia canonica),
`evidence/E04_provider_boundary_counterproofs.json` (coppia candidate),
`evidence/E05_legacy_lab_only_non_provider_capable.json`,
`evidence/E06_legacy_envelope_budget_paths.json`.

## Il problema di provare un fatto su un provider reale senza un provider reale

Il mandato vieta provider reali, credenziali, rete e crediti. E chiede di dimostrare
un fatto che riguarda un provider reale: che non sia raggiungibile fuori dal percorso
governato.

Al posto del provider c'e' una **sentinella**: un adapter che, dove ci sarebbe la
chiamata al provider, incrementa un contatore.

```
reached               attraversamenti del dispatch
authorized_calls      attraversamenti dell'autorizzazione del payload
transport.sent        marcatore di invio del trasporto fittizio del Core
transport.authorized  digest autorizzati al trasporto (effetto anche senza invio)
```

`sentinel_zero` e' vero solo se **tutti e quattro** sono a zero.

La sentinella si costruisce sul Core che trova: sulla baseline `9cf9cee1` e' un
`FakeAdapter` che dichiara `spend_capable` e conta; sul candidate deriva da
`SpendCapableAdapter` e implementa i due hook **oltre** il confine. Stessa sonda, due
Core: e' cosi' che si vede la differenza invece di dichiararla.

---

## PRIMA — coppia canonica `9cf9cee1` + `fea7b439`

Se nessun percorso avesse raggiunto lo spender, questa fase sarebbe stata senza
oggetto. Tutti e sei l'hanno raggiunto:

| sonda | percorso | esito | sentinella |
|---|---|---|---|
| P1 | `go(authorization=None)` con uno spender | **SUCCEEDED** | `reached=1`, `sent=1` |
| P4 | `transport.pipeline.run_job` coi soli default | **SUCCEEDED** | `reached=1`, `sent=1` |
| P4env | `run_job(..., envelope_units=1000)` (budget del client) | **SUCCEEDED** | `reached=1`, `sent=1` |
| P5 | `adapter.submit(spec)` diretto | confine **attraversato**, poi il trasporto rifiuta il digest non autorizzato | `reached=1` |
| P6 | `adapter.authorize_payload(d)` diretto | **accettato** | `authorized_calls=1` |
| P7 | `reconcile` con evidenza fabbricata, poi rispesa | reconcile **accettato**, rispesa **SUCCEEDED** | `reached=1`, `sent=1` |
| P10 | `hf_batch.Batch.go` legacy su spec reale, 2 asset | **SUCCEEDED** ×2 | `reached=2`, `sent=2` |
| P8 | `store_call("reconcile")` | dispacciato davvero (l'errore e' quello del metodo reale) | superficie non dichiarata |

---

## DOPO — coppia candidate `605a8d74` + `434e0ea5`

| sonda | percorso | esito | sentinella | effetti sullo store |
|---|---|---|---|---|
| P1 | `go(authorization=None)` con uno spender | `LEGACY_LAB_NOT_PROVIDER_CAPABLE` | **0** | store **mai creato** |
| P1pin | idem, con `required_core_sha` deliberatamente **sbagliato** | `LEGACY_LAB_NOT_PROVIDER_CAPABLE` (non `CORE_PIN_MISMATCH`) | **0** | store mai creato |
| P2 | `go(authorization=None)` con adapter di **laboratorio** | `SUCCEEDED` | n/a | funziona, come deve |
| P3 | `go` **governato** con lo spender | `SUCCEEDED` | **1** | 1 riga, quote consumata |
| P4 | `run_job` coi soli default | `SPEND_AUTHORIZATION_REQUIRED` | **0** | 0 righe, 0 ledger, 0 quote |
| P4env | `run_job(..., envelope_units=…)` | `SPEND_AUTHORIZATION_REQUIRED` | **0** | 0 righe |
| P5 | `adapter.submit(spec)` diretto | `SPEND_AUTHORIZATION_REQUIRED` | **0** | — |
| P6 | `adapter.authorize_payload(d)` diretto | `SPEND_AUTHORIZATION_REQUIRED` | **0** | — |
| P7 | `reconcile` fabbricato + rispesa | reconcile accettato (non dispaccia); **rispesa** `SPEND_AUTHORIZATION_REQUIRED` | **0** | nessuna nuova spesa |
| P7al | idem, store aperto con allowlist | reconcile **rifiutato**, stato resta `RESERVED`, rifiuto **registrato** | **0** | — |
| P8 | `store_call("reconcile")` | `STORE_CALL_METHOD_NOT_ALLOWED` | n/a | store **mai aperto**, Core **mai importato** |
| P10 | `hf_batch` legacy con uno spender | `LEGACY_LAB_NOT_PROVIDER_CAPABLE` | **0** | store mai creato |

### `P1pin` merita una riga a parte

Passando uno SHA richiesto sbagliato, il rifiuto **resta**
`LEGACY_LAB_NOT_PROVIDER_CAPABLE` e non diventa `CORE_PIN_MISMATCH`. Il confine
precede il gate di pin — e quindi precede l'import del Core, l'apertura dello store,
la prenotazione, lo snapshot e tutto il resto. Non e' un dettaglio di ordine: e' la
differenza fra "fallisce prima di ogni effetto esterno" e "fallisce, prima o poi".

---

## "Basta cambiare adapter, modalita' o configurazione?" — cinque tentativi

`E05`. In tutti e cinque la sentinella resta a **0**.

| tentativo | esito |
|---|---|
| modalita' Provider Boundary **INGAGGIATA** | `LEGACY_LAB_NOT_PROVIDER_CAPABLE` |
| modalita' **DISINGAGGIATA** (default storico) | `LEGACY_LAB_NOT_PROVIDER_CAPABLE` — il rifiuto non dipende dalla modalita' |
| ambiente che forza `CREATIVE_OS_LEGACY_LAB_SPEND_PATH=enabled` | `LEGACY_LAB_NOT_PROVIDER_CAPABLE` — l'ambiente puo' solo chiudere, mai riaprire |
| sottoclasse che **riprende** `submit` | `TypeError` **a tempo di definizione della classe**: la classe non esiste |
| wrapper che **mente** sulla capability (`spend_capable = False`, delega allo spender) e supera il FAKE MODE gate | `SPEND_AUTHORIZATION_REQUIRED` — il confine del Core non sta sul wrapper, sta sullo spender, ed e' li' che la concessione manca. Sentinella interna: `reached=0`, `sent=0` |

L'ultimo e' il tentativo piu' onesto contro un confine dichiarativo: mentire sulla
dichiarazione. Sulla coppia **canonica** funzionava (`reached=1`, `sent=1`, e
l'ownership veniva contestata **dopo** l'invio). Sulla candidate no.

---

## I percorsi economici legacy

`E06`. Il client non sceglie il prezzo, e il budget grezzo non arriva al confine:

| verifica | esito |
|---|---|
| `envelope_units` a un adapter spendibile, dal **Core** | `SPEND_AUTHORIZATION_REQUIRED`, 0 righe |
| `envelope_units` nel percorso **governato** del Runtime | `LEGACY_ENVELOPE_UNITS_FORBIDDEN` |
| il client presenta un importo **diverso** dalla quote | `BUDGET_NOT_QUOTED`, 0 submit |
| il client **omette** l'importo | riceve quello della quote (10), non uno di default |
| `budget_units` / `envelope_units` per un adapter di laboratorio | **funzionano**, invariati |
| `envelope_units` raggiunge il confine dello spender? | `reached = 0` |

---

## HUMAN REVIEW 01 — l'oggetto che apre il cancello

La review ha trovato cio' che le controprove sopra **non** coprivano: nessuna
costruiva direttamente una `DispatchAuthorization` falsa. `E13` lo fa, contro
entrambi i Core.

### Sul candidate revisionato `44f9ea29` — BLOCKER_REPRODUCED

| tentativo | esito | sentinella |
|---|---|---|
| controesempio esatto della review | **riuscito** (`pv_e46492dd`) | `reached=2`, `sent=2` |
| `grant_dispatch(adapter, auth)` a due argomenti | **grant aperto** | |
| oggetto fabbricato infilato nello slot | **riuscito** | |
| `_dispatch` / `_authorize_payload` con autorizzazione fabbricata | **riusciti** | `reached=2` |

### Sul delta correttivo `605a8d74`

| tentativo | esito | sentinella |
|---|---|---|
| controesempio esatto della review | `DISPATCH_AUTHORIZATION_FORGED` | **0** |
| `grant_dispatch(adapter, auth)` | `TypeError` — la firma non esiste piu' | **0** |
| oggetto fabbricato nello slot | `DISPATCH_AUTHORIZATION_FORGED` | **0** |
| `_dispatch` / `_authorize_payload` senza concessione | `SPEND_AUTHORIZATION_REQUIRED` | **0** |
| `_dispatch` / `_authorize_payload` con autorizzazione fabbricata nello slot | `DISPATCH_AUTHORIZATION_FORGED` | **0** |
| autorizzazione **legittima** riusata | `DISPATCH_AUTHORIZATION_SPENT` | invariata |
| percorso **governato** | `SUCCEEDED` | **1** |

Nell'evidenza il tentativo `bypass_constructor` risulta *non rifiutato* in entrambe le
esecuzioni: costruire un oggetto Python e' sempre possibile e nessun controllo puo'
vietarlo. Cio' che conta e' che quell'oggetto non apra nulla, ed e' cio' che misura
`slot_injection`. Registrarlo come riuscito invece di nasconderlo e' il punto.

## Cosa queste controprove NON dimostrano

Non dimostrano che un provider reale funzioni, ne' che sia sicuro accenderlo. Non sono
un test di un provider: sono un test di **raggiungibilita'**. E non dimostrano nulla
contro codice arbitrariamente malevolo eseguito con la stessa identita' dello spender:
quello e' P-B01, e la distinzione e' scritta in `THREAT_MODEL.md`. `REAL_AUTHORIZATION_AND_PRICING`
e `REAL_PROVIDER_RECONCILIATION` restano `REAL_PROVIDER_REQUIRED`, e questa fase non
li tocca.
