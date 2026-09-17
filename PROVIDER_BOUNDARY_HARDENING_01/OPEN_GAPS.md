# OPEN GAPS — DOPO PROVIDER / EXECUTION BOUNDARY HARDENING (2026-09-17)

Stato massimo consentito raggiunto in LAB: `PROVIDER_EXECUTION_BOUNDARY_HARDENING_READY_FOR_HUMAN_REVIEW`.
Nessuno stato qui sotto significa provider ready, production ready, credenziali autorizzate, spend autorizzato,
merge autorizzato o R2 autorizzato.

| Gap | Stato pre-fase | Stato post-fase (LAB) | Cosa resta / condizione di chiusura |
|---|---|---|---|
| **P-B01** separazione di privilegio | `BLOCKED_ENVIRONMENT` (same-UID) | **`LAB_VERIFIED_UID_BOUNDARY`** (B01 PASS: UID distinti, orchestrator senza capability e `no_new_privs`, DAC del kernel su segreto/store/codice/daemon, `SO_PEERCRED`, terzo UID rifiutato; B02: la modalita' same-UID resta `BLOCKED_ENVIRONMENT`) | Human Review del design (`P_B01_ENVIRONMENT.md`). Per produzione: adapter reale costruibile solo nello spender, credenziali reali solo nel suo dominio, unit/container hardening, ACL sul socket. T29 storico resta BLOCKED per policy (mock same-UID non modificato). |
| **P-B02** reconciliation autenticata | `STILL_OPEN` | **`LAB_VERIFIED`** (B03/B04: report HMAC con chiave derivata dal segreto dello spender; binding a provider/conto/provider_job_id/attempt_token/payload_digest/operation/job; ownership dell'adapter; nonce monouso; audit snapshot; 16 controprove + replay + altra operazione fail-closed, journal invariato) | "Real provider reconciliation" NON verificata: la firma e' un equivalente LAB dell'interlocutore autenticato. Il percorso raw `store.reconcile` del Core resta permissivo per chi ha accesso in scrittura allo store (fuori threat model dichiarato del Core): `BLOCKED_PROVIDER_GATE` (vedi LEGACY #11). Freshness (`max_age_s`) non imposta di default. |
| **P-B04** snapshot exact-byte | `STILL_OPEN` | **`LAB_VERIFIED`** (B05/B06: byte canonici persistiti write-once `0444` content-addressed, sigillo, binding all'attempt, verifica byte-per-byte immediatamente prima del send con attestazione monouso, audit in reconciliation; 6 controprove rifiutate PRIMA del marcatore con settlement 0 attestato; pre-fix lo stesso caso raggiungeva l'invio) | Immutabilita' = write-once + content-addressed + verifica a ogni lettura, nel dominio dello spender (P-B01); non e' WORM hardware. Un attore con i privilegi dello spender puo' alterare il ledger: rilevato (DIGEST_MISMATCH/SNAPSHOT_MISSING → nessun invio), non impedito. Un adapter reale dovra' esporre `serialize`/`transport` con la stessa semantica del `FakeAdapter`. |
| **Legacy spend paths** | OPEN FOR INVENTORY | **INVENTORIATI (13 entry point, `LEGACY_SPEND_PATHS.md`) + interruttore fail-closed verificato** (B07) | Residuo `BLOCKED_PROVIDER_GATE`: #2/#4 `LEGACY_LAB` (aperto in LAB perche' usato da T01-T27; chiusura = `LEGACY_LAB_SPEND_PATH="DISABLED"` + migrazione test storici), #7 helper same-UID, #10 primitive Core, #11 `store.reconcile` raw, #12 P2 frozen (fuori runtime). |
| **Orphan RESERVED lease** | `STILL_OPEN` | **`STILL_OPEN`** (B08: riprodotto, stati formalizzati `RESERVED_NO_INTENT`/`RESERVED_WITH_INTENT`, classificazione read-only, zero uscite esistenti, zero blind retry, reconciliation autenticata → `OWNERSHIP_INCOMPLETE`) | Decisione umana su lease authority (finestra, attore, evidenza); policy candidata in `ORPHAN_LEASE.md`. Nessuna reclaim implementata. |
| **Authorization / pricing authority** | non verificata | **`LAB_ONLY`** (B09: autorita' nello spender, orchestrator non emette quote ne' scrive lo store, importo dal client rifiutato) | `real provider authorization`: NOT_VERIFIED · `real pricing verified`: NOT_VERIFIED. |
| **G-N02** semantic claim paraphrase | `STILL_OPEN` | `STILL_OPEN` (fuori scope, non toccato) | — |
| **RV07** scheduler/recovery residual | `STILL_OPEN` | `STILL_OPEN` (non toccato; nota: P-B02 fornisce l'uscita autenticata da SUBMIT_UNKNOWN, ma nessuno scheduler la invoca) | — |
| **run_contamination** | `NOT_RUN` | `NOT_RUN` (input Tenant assente) | — |
| **CI** | assente | assente (nessuno status check indipendente sul branch) | — |

Nuovi gap emersi in questa fase:
- **NG-01** il gate storico e il nuovo gate girano come root (operatore): la riproducibilita' del confine P-B01 in un
  ambiente senza `CAP_SETUID` restituisce `BLOCKED_ENVIRONMENT` (per costruzione, mai PASS simulato).
- **NG-02** `ledger.seal` avviene prima di `run_job`: una prenotazione rifiutata (BudgetExceeded, OperationBusy…) lascia
  file `.bin/.seal` senza attempt nel ledger (nessun effetto economico; rumore di audit). Da decidere se pulire o conservare.
- **NG-03** `mark_refused_before_send` (percorso esplicito del Core) e' invocato dal runtime anche per il rifiuto a
  `mark_submitting` (SERIALIZATION_DRIFT / IDENTITY_DRIFT): attestazione "non inviato" del guard runtime, non del
  trasporto. Coerente con RV02 (nessun `authorize`, nessun `send`); da confermare in Human Review.
