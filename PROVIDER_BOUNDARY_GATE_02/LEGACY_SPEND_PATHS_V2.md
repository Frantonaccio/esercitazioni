# LEGACY SPEND PATH INVENTORY — v2 (riverificato sul Runtime canonico 0698279)

Inventario riverificato sul Runtime **attuale**, non ereditato dalla fase precedente.
Fonte: `evidence/C04_legacy_spend_paths_v2.json` (ricerca statica AST + testo su `runtime/` e
`tests/`, più prova **dinamica** di ogni entry point con la modalità Provider Boundary
disingaggiata e ingaggiata). Riproduzione pre-fix: `evidence/pre_fix/reproduction_legacy_spend_paths.json`.

**Target del mandato**: nessun percorso capace di raggiungere submit/spend deve poter bypassare
governed authorization, quote authority, envelope, permit, operation/attempt identity, exact-byte
snapshot, spender boundary, economic ledger.

---

## L'interruttore di modalità

Un solo interruttore per l'intera postura, verificato **prima di qualunque effetto** (nessun pin,
nessun import del Core, nessuno store, nessuna reservation, nessun submit):

```
CREATIVE_OS_PROVIDER_BOUNDARY_MODE=engaged
```

- `runtime/provider_gate.py:provider_boundary_mode()` → `ENGAGED` / `DISENGAGED`
- ingaggiato, forza `legacy_spend_path_state() == "DISABLED"`: un solo interruttore, non due da
  tenere allineati a mano;
- `refuse_if_provider_boundary_mode(entry_point)` è il punto di rifiuto per i percorsi non governati.

**Default: DISINGAGGIATA.** La suite storica R0-R1 (T01-T37) usa il percorso `LEGACY_LAB` e questa
fase non la altera (C07: 36/37 PASS, 0 FAIL, T29 `BLOCKED_ENVIRONMENT` per policy, come a baseline).
Ingaggiare la modalità è una **precondizione dichiarata** del Provider Boundary Gate, non un default
nascosto.

---

## Inventario

| # | Entry point | File / funzione | Può raggiungere spend? | Passa dal governed path? | Boundary attraversati | Stato |
|---|---|---|---|---|---|---|
| 1 | `go(..., authorization=<LabAuthorization>)` | `runtime/go_candidate.py:go` | sì (FakeAdapter; reale → `REAL_PROVIDER_DISABLED`) | **SÌ** | pin → intent → operation → envelope derivato → quote fidata → permit → reservation atomica → snapshot exact-byte → send attestato | **GOVERNED** (unico ammesso a regime; funziona in **entrambe** le modalità, verificato C04) |
| 2 | `go(..., authorization=None)` — LEGACY_LAB | `runtime/go_candidate.py:go` | sì (riprodotto: `SUCCEEDED`, `submits=1`, `quote_id=null`, `envelope_id=null`, `permit_id=null`) | **NO** | nessuno dei boundary economici | **CHIUSO fail-closed dalla modalità** → `LEGACY_SPEND_PATH_DISABLED`, `reached_spend=false` |
| 3 | `Batch.run_job` → `go` governato | `runtime/hf_batch_runtime.py` | sì (via #1) | SÌ | come #1 | **GOVERNED** |
| 4 | `Batch.run_job` → `go(authorization=None)` | `runtime/hf_batch_runtime.py` | sì (via #2) | NO | — | **CHIUSO** dallo stesso interruttore di #2 |
| 5 | `python3 hf_batch_runtime.py <spec> go` (`__main__`, adapter=None) | `runtime/hf_batch_runtime.py:__main__` | no: senza lock si ferma; con lock stubbato `go` rifiuta `adapter=None` | n/a | — | **FAIL-CLOSED** (invariato) |
| 6 | `Batch.lock` / `Batch.quote` (CLI provider reale nell'originale) | `runtime/hf_batch_runtime.py` | no: prima istruzione `_real_cli()` → `REAL_PROVIDER_DISABLED` | n/a | — | **FAIL-CLOSED** (invariato) |
| 7 | `tests/worker.py:store_call` | `RUNTIME_INTEGRATION_GATE_01/tests/worker.py` | dispaccia QUALUNQUE metodo dello store, same-UID, fuori dal governed path (riprodotto: `RESERVED_NEW`) | NO | nessuno | **CHIUSO fail-closed dalla modalità** → `PROVIDER_BOUNDARY_MODE_ENGAGED`, **prima** dell'import del Core e dell'apertura dello store (`store_created=false`) |
| 8 | `tests/boundary_mock.py:worker_main` (mock storico, stesso UID) | `RUNTIME_INTEGRATION_GATE_01/tests/boundary_mock.py` | sì (governato) | SÌ | come #1, ma senza confine di processo | GOVERNED, confine non dimostrato (T29 `BLOCKED_ENVIRONMENT` per policy; non modificato) |
| 9 | `spender_daemon2.py` (P-B01+P-B02, UID distinto, SO_PEERCRED) | `PROVIDER_BOUNDARY_GATE_02/pbg2/spender_daemon2.py` | sì (governato, unico detentore dei segreti) | SÌ | come #1 **+ confine di privilegio del kernel + autorità di firma confinata** | **GOVERNED + composizione verificata (C02)** |
| 10 | `transport.pipeline.run_job` / `adapter.submit` diretti | `creative-os/transport/pipeline.py`, `adapters/fake.py` | **sì** (riprodotto e riverificato: `SUCCEEDED`, `submits=1`) | NO | nessuno | **`CORE_CHANGE_REQUIRED`** — vedi sotto |
| 11 | `store.reconcile` raw con evidenza arbitraria | `creative-os/registry/reservations.py:reconcile` | non spende, ma **libera l'identità della spec** | NO | nessuno | **`CORE_CHANGE_REQUIRED`** — vedi sotto |
| 12 | P2 `hf_batch.py` frozen (`subprocess higgsfield generate create`) | `p2_handoff/…/P2_RUNTIME/hf_batch.py` | **sì, provider REALE** se eseguito con CLI e credenziali | NO | — | **FROZEN / FUORI RUNTIME**: SHA256 `637f3a80…` invariato (C00 before == C08 after), non importato né eseguito dal runtime. Migrazione retroattiva vietata dal mandato. |
| 13 | Strumenti MCP Higgsfield disponibili alla sessione | ambiente della sessione, non repository | sì, provider reale | NO | — | **0 chiamate in questa fase.** Non sono un percorso del runtime; annotati per completezza. |

---

## Ciò che la modalità NON può chiudere, dichiarato

I percorsi **#10** e **#11** sono **primitive del Core**. Sono invocabili da qualunque codice che
abbia il Core in `sys.path` e un adapter: nessun interruttore del *Runtime* li governa, perché pin,
intent e authorization sono concetti del Runtime, non del Core.

C04 asserisce esplicitamente questo fatto invece di nasconderlo:
`core_primitives_reachable_in_both_modes = true` è un **check che deve passare**. Un test che
dicesse il contrario sarebbe falso.

**Mitigazione attuale (l'unica reale):** il confine di processo P-B01. L'orchestrator ha un UID
distinto, nessuna capability, `no_new_privs`, e il kernel gli nega lettura del segreto, scrittura
dello store, scrittura del codice del daemon, segnali al daemon e lettura del suo `/proc`. Con un
provider reale, l'adapter sarà costruibile **solo** nel dominio dello spender: una `run_job` diretta
eseguita altrove spenderebbe solo sul proprio store con il proprio conto fittizio, senza credenziali.

**Chiusura definitiva:** richiede una modifica del **Core**, fuori dal perimetro autorizzato da
questo mandato (il quale autorizza un branch Core **solo** se NG-05 lo richiede davvero). Proposta
minima, non implementata:

- `transport.pipeline.run_job` accetta un **token di autorizzazione** emesso dal solo percorso
  governato, e rifiuta senza;
- `SqliteReservationStore.reconcile` accetta solo evidenze la cui `source` appartenga a un
  allowlist registrata all'apertura dello store, e rifiuta le altre.

Stato: **`LEGACY_SPEND_PATHS_CORE_PRIMITIVES = CORE_CHANGE_REQUIRED`.**

---

## Residuo: i test storici

Con la modalità ingaggiata, la suite T01-T27 **non può girare**: dipende da `LEGACY_LAB` (#2) e
dall'helper `store_call` (#7). Chiudere il percorso in modo definitivo in codice
(`LEGACY_LAB_SPEND_PATH = "DISABLED"`) richiede **prima** la migrazione di quei test al percorso
governato.

Stato: **`LEGACY_TESTS_MIGRATION_TO_GOVERNED = STILL_OPEN`.**

Il fatto che serva ai test storici **non** autorizza un percorso alternativo verso un provider
reale: nel Provider Boundary Gate la modalità è ingaggiata e il percorso è chiuso, punto.

---

## Sintesi degli stati

| requisito | stato |
|---|---|
| `LEGACY_SPEND_PATHS_RUNTIME_CLOSURE` | **`VERIFIED_LAB`** (#2, #4, #7 chiusi fail-closed; #1 governato funziona in entrambe le modalità) |
| `LEGACY_SPEND_PATHS_CORE_PRIMITIVES` | **`CORE_CHANGE_REQUIRED`** (#10, #11) |
| `LEGACY_TESTS_MIGRATION_TO_GOVERNED` | **`STILL_OPEN`** |

Nessuno di questi stati significa provider ready, production ready, credenziali autorizzate,
spend autorizzato, merge autorizzato o R2 autorizzato.
