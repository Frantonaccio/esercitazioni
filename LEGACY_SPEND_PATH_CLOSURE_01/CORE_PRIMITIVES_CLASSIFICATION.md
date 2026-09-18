# CLASSIFICAZIONE DELLE PRIMITIVE DEL CORE

Il mandato e' esplicito: **non** eliminare un'API del Core solo perche' potrebbe
essere usata male. Per ciascuna primitive si determina **prima** dove sta il problema:

| | |
|---|---|
| **A** | primitive Core troppo permissiva |
| **B** | Runtime che la espone fuori governance |
| **C** | test/helper che la invoca direttamente |
| **D** | primitive interna valida, non raggiungibile dal futuro provider path |

e si preferisce sempre il fix minimo.

---

## 1. `transport.pipeline.run_job` — classe **A**

**Diagnosi.** Non e' il Runtime a esporla male: e' la primitive stessa a essere troppo
permissiva. `run_job(adapter, spec, store)` accetta i soli default — nessuna
operazione, nessuna quote, nessun envelope — e prenota, autorizza i byte e dispaccia.
Chiunque abbia il Core in `sys.path` e un adapter puo' spendere.

**Fix minimo applicato.** La firma non cambia. Il comportamento non cambia per un
adapter di **laboratorio**. Cambia solo per un adapter che dichiara `spend_capable`:

- **prima** della prenotazione, `require_governed_dispatch_inputs` pretende
  `operation_id`, `quote_id`, `envelope_id` e **vieta** `envelope_units` (il budget
  scelto dal client). Rifiuto a effetto zero: 0 righe, 0 ledger, 0 quote consumate;
- **dopo** `mark_submitting` e **prima** di `authorize_payload`, `authorize_dispatch`
  rilegge dal journal autorevole i fatti che autorizzano il dispatch.

**Cosa e' stato preservato.** R0-R1 (47/47 nel Core, 36/37 nel Runtime, T29 blocked
per policy come a baseline), NG-03, NG-05, P-B03, P-B04, `resume_job`, `ingest`,
`budget_units`, `envelope_units`, il percorso di laboratorio.

**Controprova esplicita.** `tests/run_spender_boundary.py` casi D, E, F, K.

---

## 2. `adapter.submit` e `adapter.authorize_payload` — classe **A**

**Diagnosi.** Sono IL confine. Finche' `submit` e' un metodo qualunque, un adapter
reale e' dispacciabile da qualunque riga di codice che possa costruirlo.

**Fix minimo applicato.** `adapters.base.SpendCapableAdapter`: un adapter che puo'
raggiungere un provider reale ne deriva, e per quella classe `submit` e
`authorize_payload` diventano **template method non sovrascrivibili**.
`__init_subclass__` rifiuta, **a tempo di definizione della classe**, sia l'override
sia un ordine di risoluzione che scavalchi il confine. Non e' una convenzione da
ricordare: e' un `TypeError`.

L'autore dell'adapter implementa `_dispatch(spec, auth)` e
`_authorize_payload(digest, auth)`, che vengono chiamati **dopo** la verifica.

**Cosa NON pretende di fare.** Non impedisce a un `FakeAdapter` di laboratorio di
essere usato direttamente. E' deliberato, verificato e dichiarato: la distinzione e'
`spend_capable`, cioe' "questo adapter puo' arrivare a un provider vero", e sta
all'autore dell'adapter dichiararla — esattamente come sta a lui non mettere una
chiave API dentro un `FakeAdapter`.

**Controprova esplicita.** Casi A, B, C, H; piu' `E05` (una sottoclasse che prova a
riprendersi `submit` non esiste: `TypeError`).

---

## 3. Come l'autorizzazione non e' falsificabile

> **HUMAN REVIEW 01.** Nella prima stesura questa sezione era vera per *intenzione* e
> falsa per *costruzione*: `DispatchAuthorization` era una dataclass costruibile e
> `grant_dispatch(adapter, auth)` accettava l'oggetto senza rileggere nulla. Il
> controesempio della review raggiungeva la sentinella. Riprodotto in `E13`, corretto
> in `605a8d74`. Dettaglio in `HUMAN_REVIEW_01_CORRECTIVE_DELTA.md`.

Tre meccanismi, deliberatamente ridondanti:

1. **`grant_dispatch` rilegge il journal.** Non riceve un'autorizzazione: riceve lo
   STORE AUTOREVOLE e l'identita' del tentativo, e chiama `authorize_dispatch` da se'.
   Non esiste una firma alternativa che accetti una capability presentata dal
   chiamante — se esistesse, sarebbe quella che verrebbe usata (`run_spender_boundary:N`).
2. **Il costruttore pretende un token di conio** privato del modulo: l'identita' di un
   oggetto, non un booleano ne' una stringa. Il controesempio letterale della review
   fallisce qui con `DISPATCH_AUTHORIZATION_FORGED` (`run_spender_boundary:L`).
3. **Registro dei coniati, per identita', a consumo singolo.** `eq=False`: due
   autorizzazioni con gli stessi campi non sono la stessa autorizzazione. Chi aggira i
   primi due costruendo l'oggetto con `object.__new__` e infilandolo nello slot si
   ferma qui. E un'autorizzazione LEGITTIMA vale per un solo tentativo: fuori dal suo
   `with` e' `DISPATCH_AUTHORIZATION_SPENT` (`run_spender_boundary:O`).

`DispatchAuthorization` **non e' un token che il chiamante costruisce**: e' un fatto
riletto dal journal autorevole. Per ottenerla servono, nella riga persistita:

- stato `RESERVED` senza identita' remota (siamo davvero pre-submit);
- `operation_id` presente;
- `attempt_token` e `payload_digest` presenti e **coincidenti** con quelli che il Core
  sta per usare;
- `provider` / `provider_account` coincidenti con l'adapter;
- `quote_id` presente, quote esistente, **consumata da QUESTO job**, legata alla stessa
  operazione, alla stessa spec, a un envelope;
- una riga di ledger `RESERVE` per questo job.

Tutto cio' nasce **solo** dentro `reserve_or_get_live`, in una transazione che consuma
la quote e impegna l'envelope. Fabbricarlo significherebbe scrivere a mano nel database
dello spender — gia' fuori dal modello di minaccia dichiarato in
`registry/reservations.py`, ed esattamente cio' che il confine di processo P-B01 nega
all'orchestrator.

La concessione (`grant_dispatch`) e' **thread-local per istanza**, non rientrante, e
vive solo dentro il `with`: copre `authorize_payload` + `submit` di **quel** tentativo
e non presta la propria autorizzazione a nessun altro (`Batch.go` dispaccia job in
thread paralleli con lo stesso adapter — il confine non deve attraversarlo).

### Gli hook di implementazione

`_dispatch` e `_authorize_payload` sono hook Python, e in Python il trattino basso non
e' un confine di sicurezza. Non sono stati lasciati scoperti *ne'* dichiarati fuori
perimetro: `__init_subclass__` li **avvolge** con lo stesso guard dei template method.
La sottoclasse non deve ricordarsi di nulla e non puo' disapplicarlo se non
ridefinendo l'hook — che verrebbe a sua volta avvolto (`run_spender_boundary:M`).

Cio' che resta fuori perimetro e' dichiarato in `THREAT_MODEL.md`: codice
arbitrariamente malevolo eseguito con la stessa identita' dello spender. Contro quello
il confine e' P-B01, e non e' mai stato preteso il contrario.

**Controprova esplicita.** Caso G: otto manomissioni della riga persistita, otto
rifiuti parlanti (`DISPATCH_ATTEMPT_TOKEN_MISMATCH`, `DISPATCH_PAYLOAD_DIGEST_MISMATCH`,
`DISPATCH_OWNERSHIP_MISMATCH` ×2, `DISPATCH_JOB_UNKNOWN`,
`DISPATCH_QUOTE_NOT_CONSUMED_BY_JOB`, `DISPATCH_LEDGER_RESERVE_MISSING`,
`DISPATCH_QUOTE_REQUIRED`), sentinella sempre a 0.

---

## 4. `SqliteReservationStore.reconcile` — classe **D**, con un'aggiunta opzionale

**Diagnosi.** `reconcile` **non dispaccia**: non ha un adapter, non chiama `submit`,
non tocca il trasporto. Cio' che faceva di male era liberare l'identita' di una spec
con un'evidenza qualunque, rendendo possibile una **rispesa** — e la rispesa passava
da `run_job`. Chiuso `run_job` per gli spender, la rispesa non raggiunge piu' nessuno:
`E04.reconcile_cannot_lead_to_spend` la mostra fermarsi con
`SPEND_AUTHORIZATION_REQUIRED` e sentinella a 0.

Quindi: **la primitive resta**. Restringerla come se fosse un percorso di spesa
sarebbe stato un fix nel posto sbagliato.

**Aggiunta minima, default inerte.** `SqliteReservationStore(path,
reconciliation_sources=(...))`: allowlist **opzionale** delle provenienze ammesse.
Default `None` = nessuna restrizione, comportamento identico al Core `9cf9cee1` (la
suite storica e ogni chiamante esistente non sono toccati). Quando e' impostata, una
provenienza estranea e' rifiutata **e registrata** (`RECONCILIATION_SOURCE_REFUSED`,
append-only), e lo stato del job resta quello che era.

Non e' cio' che impedisce a `reconcile` di raggiungere uno spender — quello lo fa il
confine — ma toglie il percorso con cui si liberava l'identita' di una spec
dichiarando una fonte qualunque.

**Controprova esplicita.** Caso J; `E04.reconcile_allowlist_refuses_forged_evidence`.

---

## 5. `tests/worker.py:store_call` — classe **C**

**Diagnosi.** Helper del **Runtime**, non del Core. Non spendeva (non c'e' adapter), ma
dispacciava `getattr(store, method)`: superficie aperta per omissione.

**Fix minimo applicato.** Superficie **dichiarata** in tre insiemi — `READ_ONLY`,
`AUTHORITY` (aprire un envelope, emettere quote e permessi, regolare, recuperare un
submit orfano: il ruolo che i test simulano), `CORE_PROBE` (due sonde esplicite sulla
prenotazione del Core) — e nient'altro. Un metodo fuori insieme e' rifiutato **prima**
dell'import del Core e **prima** di aprire lo store.

Le transizioni di stato (`put`, `reconcile`, `mark_*`, `expire`) non sono piu' nella
superficie: chi vuole provarle prova il **Core**, come fanno i suoi test.

**Controprova esplicita.** `E04.store_call_surface_declared`.

---

## 6. `go(..., authorization=None)` — classe **B**

**Diagnosi.** Percorso del **Runtime**, non del Core: compatibilita' di laboratorio per
la suite storica. Il mandato autorizza a conservarlo, purche' diventi
**strutturalmente e testabilmente** `LAB_ONLY_NON_PROVIDER_CAPABLE`.

**Fix minimo applicato.** `require_legacy_lab_spend_path(adapter)` rifiuta un adapter
`spend_capable` **sempre**: in entrambe le modalita', qualunque cosa dica l'ambiente,
prima del pin e prima dell'import del Core (il controllo e' un `getattr`, quindi non
ha un ordine di import da azzeccare). Il **valore** storico dell'interruttore
(`ENABLED_LAB_ONLY`) **non e' stato rinominato**: i gate approvati lo asseriscono
letteralmente, e rinominarlo avrebbe indebolito un controllo storico senza aggiungere
una sola garanzia. Cio' che e' nuovo e' la **capability**, dichiarata a parte
(`LEGACY_LAB_PROVIDER_CAPABILITY`) e imposta dal codice.

**Controprova esplicita.** `E05`: modalita' ingaggiata, modalita' disingaggiata,
ambiente che forza "enabled", sottoclasse che riprende `submit`, wrapper che **mente**
sulla capability — cinque tentativi, cinque rifiuti, sentinella sempre a 0.
