# P-B02 + P-B01 — COMPOSIZIONE DIMOSTRATA IN LAB

Requisito del mandato: *«Non basta avere P-B01 PASS separatamente e P-B02 PASS separatamente.»*

Stato precedente: `P_B02_P_B01_COMPOSITION = NOT_VERIFIED` (NG-06).
Stato dopo questa fase: **`VERIFIED_LAB`** (C02), nel solo perimetro dichiarato più sotto.

---

## 1. Perché non era dimostrata, riverificato

`evidence/pre_fix/reproduction_pb01_pb02_composition.json`. Due fatti letti dal codice reale:

1. **Il daemon spender non aveva alcuna operazione di reconciliation.**
   `daemon_allowed_ops = ["quote", "status", "stop", "submit", "whoami"]`,
   `daemon_has_reconciliation_op = false`, `daemon_calls_reconcile_authenticated = false`.
   La riconciliazione autenticata non veniva **mai** eseguita dentro il dominio isolato: in
   B03/B04 della fase precedente girava nel processo del gate, con segreto e chiave come
   **fixture di test**.

2. **L'API esponeva la chiave derivata.** `LabProviderStatusAuthority.key` è una `property`
   pubblica e `derive_report_key` è una funzione pubblica. Controprova dinamica: un processo
   qualunque che ottenga quella chiave firma un report che la verifica **accetta**:
   `{"applied": true, "state": "SUCCEEDED"}`.

La custodia del segreto era una proprietà del **processo chiamante**, non della firma.

---

## 2. Il fix minimo

`PROVIDER_BOUNDARY_GATE_02/pbg2/spender_daemon2.py` — estende il daemon della fase precedente
(**non modificato**, resta al suo posto) con l'unica cosa che mancava: **l'autorità di stato del
provider vive dentro il processo spender**.

Cosa sta nel dominio dello spender e non ne esce mai:

| | |
|---|---|
| `spend_secret` | segreto di spesa, da cui deriva l'identità del conto (come prima) |
| `recon_secret` | **nuovo**: segreto di riconciliazione, file `0600` in directory `0700` dell'UID dello spender |
| chiave HMAC derivata | costruita in memoria dal daemon; **mai** su disco, **mai** nel ready-file, **mai** sul socket |
| `LabProviderStatusAuthority` | istanziata qui, con quel segreto |
| `reconcile_authenticated` | il **verificatore** gira qui, sullo store autorevole dello spender |
| `FreshnessPolicy` | parametri obbligatori da riga di comando dell'operatore; il daemon non ha default |

Cosa riceve l'orchestrator (UID distinto, autenticato con `SO_PEERCRED`):

- `provider_report` — un report **firmato** per un job di cui lo spender è proprietario. Il client
  sceglie solo stato, `remote_ref` e `provider_job_id`: tutto ciò che **lega** il report al
  tentativo (provider, conto, `attempt_token`, `payload_digest`, `operation_id`, `job_id`) viene
  dallo **store autorevole**, non dal client;
- `reconcile_report` — l'**esito** di una riconciliazione;
- `composition_counterproof` — il solo **codice di rifiuto** delle controprove di binding e
  freshness. Il report firmato-ma-mal-legato viene costruito e verificato **dentro** lo spender e
  non esce mai: l'operazione non è un oracolo di firma.

Prima di ogni invio il daemon verifica che la risposta non contenga né i segreti né la chiave
derivata (esadecimale e base64). Un'asserzione fallita chiude la sessione.

---

## 3. Le controprove del mandato

`evidence/C02_pb01_pb02_composition.json`. Orchestrator con UID `65531`, spender `65532`, terzo
UID non autorizzato `65530`; orchestrator senza capability (`CapEff = 0…0`) e con
`NoNewPrivs = 1`.

| # | controprova richiesta | esito osservato |
|---|---|---|
| 1 | orchestrator tenta di leggere il **secret** | `BLOCKED (PermissionError)` — sia `recon_secret` sia `spend_secret`; directory dei segreti non elencabile |
| 2 | orchestrator tenta di leggere la **signing key** | `/proc/<pid>/mem` `BLOCKED (PermissionError)`; `/proc/<pid>/environ` `BLOCKED (PermissionError)`; ready-file leggibile ma **senza materiale di chiave** (`signing_key_on_disk: false`); nessun file di chiave su disco; **0 token esadecimali inspiegati** sul canale |
| 3 | orchestrator **forgia** un report (firma con una chiave propria) | `UNAUTHENTICATED` |
| 3b | orchestrator **rifirma** usando la firma osservata sul canale, con nonce nuovo | `UNAUTHENTICATED` (i byte canonici cambiano col nonce) |
| 4 | **UID/processo non autorizzato** parla al socket | `PEER_UID_NOT_AUTHORIZED` |
| 5 | **report corretto** prodotto dallo spender | **applicato**: `SUCCEEDED` |
| 6 | **replay** | due facce, entrambe fail-closed: l'orchestrator che ripropone il report su un job ormai terminale → `NOT_RECONCILABLE`; il replay vero su un job ancora riconciliabile, rifiutato dal **nonce monouso dentro lo spender** → `REPLAY` |
| 7 | **wrong provider** | `PROVIDER_MISMATCH` |
| 8 | **wrong account** | `ACCOUNT_MISMATCH` |
| 9 | **wrong job** | `JOB_UNKNOWN` |
| 10 | **wrong operation** | `OPERATION_MISMATCH` |
| 11 | **wrong attempt** | `ATTEMPT_TOKEN_MISMATCH` |
| + | wrong payload digest | `PAYLOAD_DIGEST_MISMATCH` |
| + | freshness composta col confine: report troppo vecchio | `REPORT_STALE` |
| + | freshness composta col confine: report nel futuro | `REPORT_FROM_FUTURE` |

Stato autorevole a fine sessione: **una sola riga**, `SUCCEEDED`, con il `provider_account` dello
spender; store e segreti di proprietà dell'UID dello spender; sentinella di audit a **zero
violazioni**.

### Sul punto 2, con precisione

L'orchestrator non ha modo di distinguere sintatticamente una chiave da un digest (entrambi 64
caratteri esadecimali). La verifica quindi è doppia:

- **lato orchestrator**: ogni token esadecimale a 64 caratteri visto sul canale dev'essere
  **spiegabile** — firma di un report emesso dallo spender, `payload_digest`, `spec_key`, o valore
  citato dentro il testo di un rifiuto. `unexplained_hex64 = []`;
- **lato spender**: il daemon asserisce, prima di ogni invio, che la risposta non contenga la
  chiave (hex e base64) né i segreti. Nessuna asserzione è scattata.

---

## 4. Perimetro dichiarato

Cosa **è** dimostrato:

- che il segreto di riconciliazione e la chiave derivata restano nel dominio dello spender, con il
  **kernel** (DAC su UID, `SO_PEERCRED`, `no_new_privs`, assenza di capability) a impedirne la
  lettura all'orchestrator — non un `if` in Python;
- che l'orchestrator non può produrre autonomamente un report valido;
- che un report firmato dallo spender viene verificato **attraverso il boundary appropriato** e
  applicato solo se legato al tentativo, fresco e non riproposto;
- che un'altra identità/UID/processo non autorizzato non può sostituirsi allo spender.

Cosa **non** è dimostrato, e non viene affermato:

- **nulla sul provider reale.** Il segreto è fittizio, l'adapter è il `FakeAdapter` del Core,
  l'autorità di stato è di laboratorio. `REAL_PROVIDER_RECONCILIATION` resta
  `REAL_PROVIDER_REQUIRED`;
- **nulla sulla produzione.** Restano da fare: adapter reale costruibile solo nello spender,
  credenziali reali solo nel suo dominio, hardening dell'unità/container, ACL sul socket;
- il gate (operatore) gira come `root`: è il ruolo dell'installatore, non dell'orchestrator. Le
  probe che contano girano tutte con l'UID dell'orchestrator, senza capability;
- le fixture B03/B04 della fase precedente **restano** ciò che erano: prova di binding e
  autenticazione, non di composizione. Non sono state modificate.

Se l'ambiente non consentisse UID distinti, C02 restituirebbe `BLOCKED_ENVIRONMENT` con
`requirement_verified: false`: non esiste un percorso che simuli un PASS.

---

## 5. Stato

**`P_B02_P_B01_COMPOSITION = VERIFIED_LAB`**

Non significa provider ready, production ready, credenziali autorizzate, spend autorizzato,
merge autorizzato o R2 autorizzato.
