# INVENTARIO COMPLETO DEI PERCORSI DI SPESA

Ricostruito **prima di qualunque modifica**, su Core `9cf9cee1` + Runtime `fea7b439`
(la coppia canonica), e riverificato sulla coppia candidate.

Due fonti, nessuna delle quali basta da sola:

- **statica** — scansione AST di `adapters/ core/ registry/ transport/ tests/` del Core
  e di `runtime/ tests/` del Runtime: `evidence/E01_spend_path_inventory_static.json`.
  Dice DOVE sono i punti; non sa cosa succede quando li si percorre.
- **dinamica** — 17 sonde, ognuna in un **processo reale**, ognuna con una SENTINELLA
  al posto del provider: `evidence/E02_pre_fix_reproduction.json` (coppia canonica) e
  `evidence/E04_provider_boundary_counterproofs.json` (coppia candidate). Dice COSA
  succede; non sa cosa ha dimenticato.

`reached` = attraversamenti del confine dello spender contati dalla sentinella.

---

## Legenda delle classi (§5 del mandato)

| classe | significato |
|---|---|
| **A** | primitive pubblica del Core, non raggiungibile dal Runtime |
| **B** | percorso di compatibilita' legacy del Runtime |
| **C** | helper per soli test |
| **D** | percorso governato, candidato alla produzione |
| **E** | primitive che puo' realmente diventare un bypass provider |

---

## Matrice

| # | entry point | repo | file / funzione | chiamanti | raggiunge submit? | raggiunge spend? | passa dal governed path? | chiamabile dal Runtime? | serve ai test? | serve al sistema? | classe | stato PRIMA | stato DOPO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `go(..., authorization=<LabAuthorization>)` | RUNTIME | `runtime/go_candidate.py:go` | `hf_batch_runtime.Batch.run_job`, worker dei test | si | si | **SI** | si | si | **si** | **D** | GOVERNED | **GOVERNED** (invariato; unico che raggiunge lo spender: `reached=1`) |
| 2 | `go(..., authorization=None)` — LEGACY_LAB | RUNTIME | `runtime/go_candidate.py:go` | `Batch.run_job`, T01–T34 | si | si (pre-fix: `reached=1`) | NO | si | **si** (T01–T34) | no | **B** | `ENABLED_LAB_ONLY`, spendibile | **LAB_ONLY_NON_PROVIDER_CAPABLE** — con uno spender: `LEGACY_LAB_NOT_PROVIDER_CAPABLE`, `reached=0`, store mai creato |
| 3 | `Batch.run_job` → `go` governato | RUNTIME | `runtime/hf_batch_runtime.py` | CLI `go` | si | si | SI | si | si | **si** | **D** | GOVERNED | **GOVERNED** |
| 4 | `Batch.run_job` → `go(authorization=None)` | RUNTIME | `runtime/hf_batch_runtime.py` | CLI `go` | si | si (pre-fix: `reached=2`, 2 asset) | NO | si | si | no | **B** | spendibile | **CHIUSO** dallo stesso rifiuto di #2 |
| 5 | `python3 hf_batch_runtime.py <spec> go` (`__main__`, adapter=None) | RUNTIME | `runtime/hf_batch_runtime.py:__main__` | shell | no | no | n/a | si | no | no | **B** | FAIL-CLOSED | FAIL-CLOSED (invariato) |
| 6 | `Batch.lock` / `Batch.quote` | RUNTIME | `runtime/hf_batch_runtime.py` | CLI | no: `_real_cli()` → `REAL_PROVIDER_DISABLED` | no | n/a | si | no | no | **B** | FAIL-CLOSED | FAIL-CLOSED (invariato) |
| 7 | `tests/worker.py:store_call` | RUNTIME | `RUNTIME_INTEGRATION_GATE_01/tests/worker.py` | T25, T27, T30–T37; pbgate; pbg2 | no (nessun adapter) | no | NO | si | **si** | no | **C** | dispacciava **qualunque** metodo (`getattr(store, method)`) | **superficie DICHIARATA**: lettura / autorita' / 2 sonde sul Core. Fuori insieme → `STORE_CALL_METHOD_NOT_ALLOWED` prima dell'import del Core e prima di aprire lo store |
| 8 | `tests/boundary_mock.py:worker_main` | RUNTIME | `RUNTIME_INTEGRATION_GATE_01/tests/boundary_mock.py` | T28 | si (governato) | si | SI | si | si | no | **D** | GOVERNED, confine di processo non dimostrato (T29 `BLOCKED_ENVIRONMENT`) | invariato |
| 9 | `spender_daemon2.py` (P-B01+P-B02, UID distinto, SO_PEERCRED) | RUNTIME | `PROVIDER_BOUNDARY_GATE_02/pbg2/spender_daemon2.py` | gate C02 | si (governato) | si | SI | no (altro UID) | si | **si** | **D** | GOVERNED + composizione verificata | invariato (C02 riverificato: PASS) |
| 10a | `transport.pipeline.run_job(adapter, spec, store)` coi soli default | CORE | `transport/pipeline.py:run_job` | chiunque abbia il Core in `sys.path` | **si** | **si** (pre-fix: `reached=1`) | NO | si | si | **si** | **E** | `CORE_CHANGE_REQUIRED` | **CHIUSO per gli SPENDER**: `SPEND_AUTHORIZATION_REQUIRED` **prima** della prenotazione — 0 righe, 0 ledger, 0 quote consumate. Per un adapter di laboratorio: invariato |
| 10b | `adapter.submit(spec)` diretto | CORE | `adapters/*.submit` | chiunque | **si** | **si** (pre-fix: `reached=1`) | NO | si | si | **si** | **E** | `CORE_CHANGE_REQUIRED` | **CHIUSO**: in `SpendCapableAdapter` `submit` e' un template method non sovrascrivibile; senza concessione → `SPEND_AUTHORIZATION_REQUIRED`, `reached=0` |
| 10c | `adapter.authorize_payload(digest)` diretto | CORE | `adapters/*.authorize_payload` | chiunque | no ma autorizza i byte al trasporto | prepara la spesa (pre-fix: `authorized_calls=1`) | NO | si | si | **si** | **E** | non inventariato prima | **CHIUSO**: stesso confine, `authorized_calls=0` |
| 10d | `transport.pipeline.run_job(..., envelope_units=N)` | CORE | `transport/pipeline.py:run_job` | chiunque | **si** | **si** (pre-fix: `reached=1`) | NO — il CLIENT sceglie il budget | si | si | si (laboratorio) | **E** | `CORE_CHANGE_REQUIRED` | **VIETATO per gli spender** (`SPEND_AUTHORIZATION_REQUIRED`); resta per il laboratorio |
| 11 | `SqliteReservationStore.reconcile(job, state, evidence)` con evidenza arbitraria | CORE | `registry/reservations.py:reconcile` | runtime, test, chiunque | no (non dispaccia) | libera l'identita' della spec → pre-fix la rispesa raggiungeva lo spender | NO | si | **si** | **si** | **A/D** | `CORE_CHANGE_REQUIRED` | `reconcile` **resta** (non dispaccia, ed e' una primitive valida). La **rispesa** che ne seguiva e' chiusa da #10a (`SPEND_AUTHORIZATION_REQUIRED`, `reached=0`). In piu': allowlist OPZIONALE `reconciliation_sources` (default inerte) che rifiuta — registrandola — una provenienza estranea |
| 14 | **`DispatchAuthorization` presentata dal chiamante** (HUMAN REVIEW 01) | CORE | `adapters/base.py`, `grant_dispatch` | chiunque abbia il Core in `sys.path` | **si** | **si** (riprodotto su `44f9ea29`: `reached=2`, `sent=2`) | NO — la capability sostituiva il journal | si | no | no | **E** | non inventariato nell'iterazione 1: era il varco | **CHIUSO**: `grant_dispatch` riceve lo STORE e rilegge il journal; il costruttore pretende un token di conio; registro dei coniati per identita' a consumo singolo. `DISPATCH_AUTHORIZATION_FORGED` / `DISPATCH_AUTHORIZATION_SPENT`, `reached=0` |
| 15 | **`_dispatch` / `_authorize_payload` invocati direttamente** | CORE | `adapters/base.py`, hook di `SpendCapableAdapter` | chiunque | **si** | **si** (riprodotto: `reached=2`) | NO | si | no | no | **E** | non inventariato nell'iterazione 1 | **CHIUSO**: `__init_subclass__` avvolge gli hook con lo stesso guard dei template method. `SPEND_AUTHORIZATION_REQUIRED` / `DISPATCH_AUTHORIZATION_FORGED`, `reached=0` |
| 16 | **stesso attempt, due autorizzazioni** (HUMAN REVIEW 02) | CORE | `adapters/base.py` + `registry/reservations.py`, `authorize_dispatch` | chiunque abbia il Core in `sys.path` | **si** | **si** (riprodotto su `605a8d74`: `reached=2`, `sent=2`, con soli fatti autorevoli) | il percorso governato veniva percorso DUE volte sullo stesso tentativo | si | no | no | **E** | non inventariato nelle iterazioni 1 e 2 | **CHIUSO**: `claim_dispatch_authorization` verifica e claima in UNA transazione, `job_id` PRIMARY KEY. `DISPATCH_AUTHORIZATION_ALREADY_CLAIMED` fra chiamate, fra thread e fra processi |
| 12 | P2 `hf_batch.py` congelato (`subprocess higgsfield generate create`) | fuori runtime | `p2_handoff/…/P2_RUNTIME/hf_batch.py` | nessuno in questo ambiente | **si, provider REALE** con CLI e credenziali | si | NO | **no** (mai importato ne' eseguito) | no | n/a | fuori perimetro | **FROZEN**: SHA256 `637f3a80…` before == after (E00/E10). Migrazione retroattiva vietata dal mandato | invariato |
| 13 | strumenti MCP Higgsfield della sessione | ambiente | non repository | operatore | si, provider reale | si | NO | no | no | n/a | fuori perimetro | **0 chiamate in questa fase** | 0 chiamate |

---

## Che cosa e' cambiato, in una riga

Prima: **sei** percorsi raggiungevano un provider/spender fuori dal governed path
(#2, #4, #10a, #10b, #10c, #10d, e #11 in composizione con #10a). La Human Review 01
ne ha trovati **altri due** che l'iterazione 1 non aveva inventariato (#14, #15):
l'autorizzazione presentata dal chiamante e gli hook di implementazione. La Human
Review 02 ne ha trovato un altro ancora (#16), il piu' sottile perche' non fabbricava
nulla: lo stesso tentativo che conia due autorizzazioni.
Dopo: **uno** lo raggiunge, ed e' #1/#3 — il governed path, **una volta per tentativo**.

## Che cosa NON e' cambiato, ed e' deliberato

`run_job`, `submit`, `authorize_payload`, `reconcile`, `budget_units` e
`envelope_units` esistono ancora, con la stessa firma, e funzionano ancora
esattamente come prima **per un adapter di laboratorio**. Il mandato chiedeva di
non eliminare un'API del Core solo perche' puo' essere usata male: il confine
distingue *chi puo' arrivare a un provider vero* da *chi non puo' arrivarci per
costruzione*, e restringe solo il primo.
