# OPEN GAPS — DOPO PROVIDER / EXECUTION BOUNDARY HARDENING (2026-09-17)

Stato massimo consentito raggiunto in LAB: `PROVIDER_EXECUTION_BOUNDARY_HARDENING_READY_FOR_HUMAN_REVIEW`.
Nessuno stato qui sotto significa provider ready, production ready, credenziali autorizzate, spend autorizzato,
merge autorizzato o R2 autorizzato.

| Gap | Stato pre-fase | Stato post-fase (LAB) | Cosa resta / condizione di chiusura |
|---|---|---|---|
| **P-B01** separazione di privilegio | `BLOCKED_ENVIRONMENT` (same-UID) | **`LAB_VERIFIED_UID_BOUNDARY`** (B01 PASS: UID distinti, orchestrator senza capability e `no_new_privs`, DAC del kernel su segreto/store/codice/daemon, `SO_PEERCRED`, terzo UID rifiutato; B02: la modalita' same-UID resta `BLOCKED_ENVIRONMENT`) | Human Review del design (`P_B01_ENVIRONMENT.md`). Per produzione: adapter reale costruibile solo nello spender, credenziali reali solo nel suo dominio, unit/container hardening, ACL sul socket. T29 storico resta BLOCKED per policy (mock same-UID non modificato). |
| **P-B02** reconciliation autenticata | `STILL_OPEN` | **`LAB_VERIFIED (binding + autenticazione)`** (B03/B04: report HMAC; binding a provider/conto/provider_job_id/attempt_token/payload_digest/operation/job; ownership dell'adapter; nonce monouso; audit snapshot; 16 controprove + replay + altra operazione fail-closed, journal invariato) | **Perimetro corretto dopo Human Review 01**: cio' che e' verificato e' il BINDING e l'AUTENTICAZIONE. La COMPOSIZIONE con P-B01 **non e' dimostrata**: in B03/B04 segreto e chiave sono fixture del processo di test, non del daemon spender isolato, e l'API espone la chiave derivata (`derive_report_key`, `LabProviderStatusAuthority.key`): la custodia dipende dal processo chiamante, non dalla firma. "Real provider reconciliation": NOT_VERIFIED. Percorso raw `store.reconcile` del Core ancora permissivo per chi scrive sullo store: `BLOCKED_PROVIDER_GATE` (LEGACY #11). Freshness: vedi NG-04. |
| **P-B04** snapshot exact-byte | `STILL_OPEN` | **`LAB_VERIFIED`** (B05/B06/B12: byte canonici persistiti write-once `0444` content-addressed, sigillo, binding all'attempt, verifica byte-per-byte immediatamente prima del send con attestazione monouso, audit in reconciliation; 6 controprove rifiutate PRIMA del marcatore con settlement 0 attestato; pre-fix lo stesso caso raggiungeva l'invio) | Immutabilita' = write-once + content-addressed + verifica a ogni lettura, nel dominio dello spender (P-B01); non e' WORM hardware. Un attore con i privilegi dello spender puo' alterare il ledger: rilevato (DIGEST_MISMATCH/SNAPSHOT_MISSING → nessun invio), non impedito. Un adapter reale dovra' esporre `serialize`/`transport` con la stessa semantica del `FakeAdapter`. |
| **Legacy spend paths** | OPEN FOR INVENTORY | **INVENTORIATI (13 entry point, `LEGACY_SPEND_PATHS.md`) + interruttore fail-closed verificato** (B07) | Residuo `BLOCKED_PROVIDER_GATE`: #2/#4 `LEGACY_LAB` (aperto in LAB perche' usato da T01-T27; chiusura = `LEGACY_LAB_SPEND_PATH="DISABLED"` + migrazione test storici), #7 helper same-UID, #10 primitive Core, #11 `store.reconcile` raw, #12 P2 frozen (fuori runtime). |
| **Orphan RESERVED lease** | `STILL_OPEN` | **`STILL_OPEN`** (B08: riprodotto, stati formalizzati `RESERVED_NO_INTENT`/`RESERVED_WITH_INTENT`, classificazione read-only, zero uscite esistenti, zero blind retry, reconciliation autenticata → `OWNERSHIP_INCOMPLETE`) | Decisione umana su lease authority (finestra, attore, evidenza); policy candidata in `ORPHAN_LEASE.md`. Nessuna reclaim implementata. |
| **Authorization / pricing authority** | non verificata | **`LAB_ONLY`** (B09: autorita' nello spender, orchestrator non emette quote ne' scrive lo store, importo dal client rifiutato) | `real provider authorization`: NOT_VERIFIED · `real pricing verified`: NOT_VERIFIED. |
| **G-N02** semantic claim paraphrase | `STILL_OPEN` | `STILL_OPEN` (fuori scope, non toccato) | — |
| **RV07** scheduler/recovery residual | `STILL_OPEN` | `STILL_OPEN` (non toccato; nota: P-B02 fornisce l'uscita autenticata da SUBMIT_UNKNOWN, ma nessuno scheduler la invoca) | — |
| **run_contamination** | `NOT_RUN` | `NOT_RUN` (input Tenant assente) | — |
| **CI** | assente | assente (nessuno status check indipendente sul branch) | — |

Gap chiusi da questo delta correttivo:
- **NG-03** (blocker Human Review 01, `PRE_SEND_PROVENANCE_MISMATCH`): **CHIUSO**. Il rifiuto a `mark_submitting`
  non usa piu' `mark_refused_before_send` e non registra piu' `TRANSPORT_ATTESTED_NOT_SENT`: usa
  `store.reconcile` + `store.settle` con `source = RUNTIME_PRE_SUBMIT_REFUSED_NOT_DISPATCHED` e i fatti osservati
  allegati, oppure non terminalizza affatto se quei fatti non concordano. Verificato da B12 (5 controprove),
  B06 e B04. Nessuna modifica del Core richiesta. Dettagli: `CORRECTIVE_DELTA_NG03.md`.

Gap aperti emersi o precisati in questa fase:
- **NG-01** il gate storico e il nuovo gate girano come root (operatore): la riproducibilita' del confine P-B01 in un
  ambiente senza `CAP_SETUID` restituisce `BLOCKED_ENVIRONMENT` (per costruzione, mai PASS simulato).
- **NG-02** `ledger.seal` avviene prima di `run_job`: una prenotazione rifiutata (BudgetExceeded, OperationBusy…) lascia
  file `.bin/.seal` senza attempt nel ledger (nessun effetto economico; rumore di audit). Da decidere se pulire o conservare.
- **NG-04** FRESHNESS dei report di riconciliazione: `max_age_s` e' OPZIONALE (default `None`). Un report valido e
  mai consumato resta accettabile indefinitamente; il nonce monouso impedisce il riuso, non l'eta'. Renderlo
  obbligatorio e fail-closed e' una **precondizione del futuro Provider Boundary Gate**. `OPEN` per decisione
  esplicita di Human Review 01 (non richiesto in questo delta correttivo).
- **NG-05** ATOMICITA' del rifiuto pre-submit: la terminalizzazione veritiera usa due transazioni
  (`reconcile`, poi `settle`) invece della singola transazione di `mark_refused_before_send`. Un'interruzione fra
  le due lascia un terminale non regolato, con esposizione mantenuta (conservativo), visibile in
  `terminal_unsettled_jobs` e riparabile (`settle` idempotente). Proposta per Human Review, **non necessaria** alla
  correttezza semantica: API additiva del Core `mark_refused_pre_submit(job, reason, *, source, evidence)`, identica
  a `mark_refused_before_send` ma con provenance parametrica. Nessuna write sul Core effettuata.
- **NG-06** COMPOSIZIONE P-B01 + P-B02 non dimostrata: nessun test esercita la riconciliazione autenticata
  *dentro* il daemon spender isolato (B03/B04 girano nel processo del gate con segreto/chiave come fixture).
