# REAL_PROVIDER_PREREQUISITES

Prerequisiti per verificare authorization, pricing e reconciliation contro un provider REALE.

**Questo documento non è un'autorizzazione.** In questa fase:
nessuna credenziale è stata letta, nessuna credenziale è stata installata, nessun provider è
stato chiamato, nessun credito è stato consumato, nessuna chiave API è presente nel repository
o nell'ambiente del gate. I requisiti `REAL_AUTHORIZATION_AND_PRICING` e
`REAL_PROVIDER_RECONCILIATION` restano `REAL_PROVIDER_REQUIRED`.

Quando un passaggio richiederebbe una credenziale o una chiamata reale, il gate si ferma con
`STOP — REAL_PROVIDER_REQUIRED` o `STOP — CREDENTIAL_REQUIRED`. Nessun mock deve fingere una
proprietà del provider reale: un `FakeAdapter` che restituisce un prezzo non è un listino, e un
report firmato con un segreto di laboratorio non è una risposta del provider.

---

## 1. Provider

| voce | contenuto |
|---|---|
| **Provider candidato** | Higgsfield (il P2 congelato `hf_batch.py` invoca `higgsfield generate create` via CLI; è l'unico provider reale nominato dalla baseline). |
| **Stato attuale nel runtime** | Irraggiungibile per costruzione: `runtime/provider_gate.py` ammette solo `provider_mode="fake"` e solo `adapters.fake.FakeAdapter` o sue sottoclassi; ogni altro valore è `REAL_PROVIDER_DISABLED` **prima** di leggere credenziali, lanciare subprocess, aprire rete o spendere crediti. |
| **Superficie da costruire** | Un `Adapter` reale conforme al Protocol del Core (`adapters/base.py`): `serialize`, `authorize_payload`, `submit`, `poll`, `fetch`, `attest_asset`, `open_stream`, più `name` e `account_id`. |
| **Vincolo di confine (P-B01)** | L'adapter reale deve essere **costruibile solo dentro il processo spender**. L'orchestrator non deve poterne istanziare uno: non ha il segreto, non ha lo store, e con la modalità Provider Boundary ingaggiata non ha percorsi non governati. |

## 2. Tipo di credenziale

| voce | contenuto |
|---|---|
| **Forma attesa** | Token/API key del provider, da custodire come il `worker_secret.json` attuale: file `0600` in una directory `0700` di proprietà dell'UID dello spender, mai nel repository, mai in `environ` di processi diversi dallo spender, mai nel ready-file, mai sul socket. |
| **Chi la legge** | Solo il daemon spender, all'avvio. |
| **Chi NON la legge** | Orchestrator, gate, test, CI, questo documento. |
| **Verifica di non-lettura** | Le probe di `composition_probe.py` (lettura del segreto, `/proc/<pid>/mem`, `/proc/<pid>/environ`, directory dei segreti, ready-file, scansione del canale) devono restare tutte `BLOCKED` anche con la credenziale reale al posto di quella fittizia. |
| **Rotazione** | Da definire: chi ruota, con quale cadenza, come si invalida un `account_id` derivato. **`POLICY_DECISION_REQUIRED`.** |

## 3. Provider account identity

| voce | contenuto |
|---|---|
| **Oggi (LAB)** | `account_id = "acct_" + sha256(secret)[:12]`: l'identità del conto **deriva dal segreto**, quindi chi non ha il segreto non la sceglie. |
| **Reale** | L'identità deve venire dal provider (id account/organizzazione/progetto restituito da un endpoint di identità), non da un hash locale. |
| **Invariante da preservare** | `provider_account` è un campo di **ownership write-once** del Core (`Job.OWNERSHIP_FIELDS`): una volta persistito non cambia. Il binding della reconciliation lo confronta (`ACCOUNT_MISMATCH`). |
| **Da verificare col provider reale** | Che l'`account_id` osservato all'avvio coincida con quello che il provider attribuisce ai job creati. |

## 4. Endpoint necessari

| scopo | cosa serve | uso nel runtime |
|---|---|---|
| **Identità account** | endpoint che restituisce l'account/organizzazione della credenziale | popola `provider_account` |
| **Listino / pricing** | endpoint o listino versionato con prezzo per SKU (modello + parametri) | alimenta la quote authority al posto di `LAB_PRICE_TABLE` |
| **Quote / preventivo** | endpoint di stima costo per una richiesta specifica, se esiste | emette la quote fidata |
| **Submit** | creazione del job generativo | `adapter.submit` |
| **Poll / stato** | stato del job per `provider_job_id` | `adapter.poll` |
| **Reconciliation autenticata** | endpoint di stato **autenticato e verificabile** per `provider_job_id`, con risposta legabile a provider, account, job remoto e payload | sostituisce `LabProviderStatusAuthority` |
| **Fetch asset** | download dell'output, con attestazione di provenienza | `adapter.fetch` + `attest_asset` |
| **Billing / consumo** | consumo effettivo per job, per il settlement | `store.settle(units=..., source=...)` |

## 5. API / SDK necessari

- SDK ufficiale o client HTTP con **timeout espliciti** su ogni chiamata (nessun default infinito).
- Serializzazione **deterministica e stabile** del payload: `adapter.serialize(spec)` deve produrre gli **stessi byte** che il trasporto invia, altrimenti P-B04 (snapshot exact-byte) non è verificabile. È il vincolo più stringente da soddisfare su un SDK di terze parti: se l'SDK ri-serializza internamente, serve un `transport` che accetti byte già serializzati.
- `authorize_payload(digest)` deve rifiutare qualunque byte diverso da quello autorizzato.
- Nessuna libreria che scriva credenziali su disco o in log.

## 6. Pricing authority

| voce | contenuto |
|---|---|
| **Oggi (LAB)** | `runtime/authorization.py:LAB_PRICE_TABLE`, SKU = modello, unità `synthetic_units`. Il client non presenta mai un importo: lo presenta e viene solo **confrontato**. |
| **Reale** | Serve una **fonte di verità versionata** del prezzo (listino del provider con versione o data di validità), acquisita dal lato spender. |
| **Requisito di binding** | La quote deve legare: operazione, spec, envelope, importo, unità, **versione del listino**, scadenza. Il Core già lo impone (`quotes.version`, `check_quote_binding`). |
| **Unità economica** | Serve una mappatura esplicita fra l'unità del provider (crediti, token, secondi di GPU) e l'unità dell'envelope. Il Core rifiuta unità incompatibili (`QuoteError`). |
| **Da decidere** | Chi possiede il listino, con quale cadenza si aggiorna, cosa succede a una quote emessa sotto un listino poi cambiato. **`POLICY_DECISION_REQUIRED`.** |

## 7. Quote semantics e price/version binding

- La quote resta **monouso** (`consumed_by`/`consumed_at`) e viene consumata **nella stessa transazione** della prenotazione: il Core lo garantisce già.
- `expires_at` deve derivare dalla validità dichiarata dal provider, non da un valore arbitrario. **`POLICY_DECISION_REQUIRED`.**
- Zero è un importo valido **solo se attestato dalla quote**, mai come fallback.
- Se il costo effettivo supera il prenotato, il Core registra `OVERSPEND_BREACH` e non tronca: comportamento da confermare come desiderato in produzione.

## 8. Reconciliation endpoint e authentication mechanism

| voce | contenuto |
|---|---|
| **Oggi (LAB)** | Report HMAC-SHA256 su campi canonici, chiave derivata da un segreto per `(provider, account)`. Da questa fase la firma e la verifica avvengono **dentro il daemon spender** (C02), con freshness obbligatoria. |
| **Reale — requisito minimo** | La risposta del provider deve essere **autenticabile** e **legabile** a: provider, account, `provider_job_id`, payload inviato, e all'identità del tentativo (`attempt_token`) o a qualcosa che vi si possa mappare 1:1. |
| **Meccanismi accettabili** | TLS con pinning + risposta firmata dal provider; oppure risposta recuperata da un endpoint autenticato con la credenziale dello spender, dove l'autenticazione del canale è la prova. |
| **Meccanismo NON accettabile** | Un webhook non firmato, o qualunque payload che il chiamante possa produrre da sé. |
| **Anti-replay** | Il nonce monouso attuale è **locale**. Con un provider reale serve un elemento di unicità che il provider stesso garantisca, oppure si mantiene il nonce locale sulla richiesta che il runtime invia. |
| **Freshness** | Il meccanismo esiste (`FreshnessPolicy`, obbligatoria). I **valori** (`max_age_s`, `max_future_skew_s`) restano `POLICY_DECISION_REQUIRED` e vanno scelti conoscendo la latenza reale e la deriva d'orologio del provider. |

## 9. Provider job identity

- `provider_job_id` è **write-once** nel Core (ownership). Deve essere l'identificatore stabile del provider, non un valore locale.
- Se il provider non restituisce un id in caso di risposta persa, `SUBMIT_UNKNOWN` resta l'unico stato onesto e la reconciliation deve poterlo **scoprire** (`PROVIDER_JOB_ID_REQUIRED`: il report deve fornire l'identità remota se il job non ce l'ha).
- Serve un modo per **cercare** un job remoto a partire da qualcosa che il runtime possiede (idempotency key), altrimenti un `SUBMIT_UNKNOWN` non è risolvibile.

## 10. Idempotency

- Serve una **idempotency key** accettata dal provider al submit, derivata dall'identità del tentativo (`attempt_token`), in modo che un retry di rete non crei due job remoti.
- Senza idempotency lato provider, la regola attuale resta l'unica sicura: **nessun retry cieco**, `SUBMIT_UNKNOWN` occupa l'identità e richiede reconciliation.

## 11. Timeout

- Timeout esplicito su submit, poll e fetch.
- `terminal_by` (deadline locale) non deve mai diventare `TIMEOUT` terminale: il Core porta a `SUBMIT_UNKNOWN` (C26-I). Da preservare.
- Da decidere: valori dei timeout, numero di poll, backoff. **`POLICY_DECISION_REQUIRED`.**

## 12. Spend ceiling

- L'envelope del Core è già un tetto **cumulativo** e transazionale: `settled + unsettled_exposure + nuova_reservation <= authorized`.
- Serve: chi apre gli envelope reali, con quale importo, per quale scope, e con quale periodicità. **`POLICY_DECISION_REQUIRED`.**
- Serve un tetto **per singola operazione** oltre a quello per envelope, se il provider può restituire costi molto superiori alla stima.

## 13. Kill switch

Già disponibili e verificati in LAB, da mantenere come precondizioni operative:

| interruttore | effetto |
|---|---|
| `provider_gate.ALLOWED_PROVIDER_MODE` | solo `fake`: un provider reale richiede una modifica **esplicita** del codice, non una variabile d'ambiente |
| `CREATIVE_OS_PROVIDER_BOUNDARY_MODE=engaged` | chiude i percorsi non governati del runtime prima di ogni effetto |
| `CREATIVE_OS_LEGACY_LAB_SPEND_PATH=disabled` | chiude il percorso LEGACY_LAB |
| envelope esaurito | `BudgetExceeded` nella transazione di prenotazione: nessun submit |

Manca, e va aggiunto prima del provider reale: un interruttore che **fermi i submit in corso** senza riavviare il daemon, e una procedura per revocare la credenziale. **`POLICY_DECISION_REQUIRED`.**

## 14. Audit requirements

Già presenti nel Core e nel runtime, da preservare:

- `anomalies` append-only (nessun UPDATE/DELETE): `RECONCILIATION`, `STALE_WRITE`, `TRANSITION_REFUSED`, `OWNERSHIP_VIOLATION`, `OVERSPEND_BREACH`, `SNAPSHOT_REFUSED_PRE_SUBMIT`, `ORPHAN_RESERVED_RECLAIMED`;
- `ledger` append-only: `RESERVE`, `SETTLE`, `SETTLE_UNKNOWN`, `SETTLEMENT_CONFLICT`, `OVERSPEND_BREACH`;
- snapshot exact-byte write-once `0444` content-addressed, con attestazione monouso immediatamente prima dell'invio;
- attestazione di freshness allegata a ogni reconciliation applicata.

Da aggiungere per il provider reale: conservazione della **risposta grezza** del provider (autenticata) accanto all'evidenza, con redazione dei segreti.

## 15. Minimal real-provider test plan

Da eseguire **solo** dopo autorizzazione umana esplicita, con credenziali reali e budget dedicato. Ordine non negoziabile: ogni passo è precondizione del successivo.

| # | test | criterio di successo | costo atteso |
|---|---|---|---|
| R1 | identità account: l'adapter reale legge la credenziale nello spender e ottiene l'account | `provider_account` non vuoto e stabile; orchestrator non legge nulla | 0 crediti |
| R2 | listino: il prezzo di uno SKU proviene dal provider, con versione | quote emessa con `version` reale | 0 crediti |
| R3 | serializzazione: `serialize(spec)` == byte effettivamente inviati | snapshot exact-byte verificato pre-send | 0 crediti (dry-run/validazione) |
| R4 | rifiuto pre-submit: un digest alterato non raggiunge il provider | `submits == 0`, settlement 0 con provenance veritiera | 0 crediti |
| R5 | **primo submit reale**, importo minimo, envelope dedicato al minimo | 1 job remoto, `provider_job_id` persistito | 1 unità minima |
| R6 | poll fino a terminale | stato terminale persistito, nessun secondo submit | 0 aggiuntivi |
| R7 | settlement: costo effettivo dal provider | `settle(units=<reale>)`, `terminal_unsettled_jobs == 0` | 0 aggiuntivi |
| R8 | idempotency: retry con la stessa chiave | nessun secondo job remoto | 0 aggiuntivi |
| R9 | `SUBMIT_UNKNOWN` indotto (timeout artificiale sul client) e risolto via reconciliation autenticata reale | stato scoperto, nessun retry cieco | 1 unità minima |
| R10 | freshness reale: report oltre la finestra scelta | `REPORT_STALE`, journal invariato | 0 |
| R11 | tetto di spesa: envelope esaurito | `BudgetExceeded`, 0 submit | 0 |
| R12 | kill switch: interruttore ingaggiato a metà sessione | nessun nuovo submit | 0 |

## 16. Rollback / stop conditions

Fermarsi immediatamente e non proseguire se:

- la credenziale risulta leggibile da un UID diverso da quello dello spender;
- `serialize` non produce i byte effettivamente inviati (P-B04 non verificabile);
- il provider non offre alcun modo autenticato di riconciliare un `SUBMIT_UNKNOWN`;
- il provider non offre idempotency e la rete può perdere risposte;
- il costo effettivo diverge dalla quote oltre una soglia decisa in anticipo;
- compare un `OVERSPEND_BREACH`;
- compare un `terminal_unsettled_jobs > 0` non riparabile;
- una qualunque probe di P-B01 passa da `BLOCKED` a `BYPASS_POSSIBLE`.

Rollback: chiudere la modalità (`CREATIVE_OS_PROVIDER_BOUNDARY_MODE=engaged`), revocare la
credenziale, azzerare l'envelope reale, conservare store, ledger, anomalie e snapshot per l'audit.

---

## Stato dichiarato

`REAL_AUTHORIZATION_AND_PRICING = REAL_PROVIDER_REQUIRED`
`REAL_PROVIDER_RECONCILIATION = REAL_PROVIDER_REQUIRED`

Nulla in questo documento significa provider ready, production ready, credenziali autorizzate,
spend autorizzato, merge autorizzato o R2 autorizzato.
