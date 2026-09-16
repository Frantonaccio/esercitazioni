# PIN_AUDIT — vecchi pin del Core (`9afaddf`) → canonical (`819e7cf`)

Nuovo pin canonical: `819e7cfedb0f6641dc797e7993bec79462ac8df6`
Pin storico: `9afaddf3cec1e8baf9600ed8dc0461e7adccb5c7` (commit iniziale del Core, antenato di `819e7cf`)

Metodo: `grep -r 9afaddf` su tutto il filesystem del container e sulla storia git (`git log -S`) dei
repository raggiungibili (`creative-os`, `vf-tenant-valorefarmacia`, `esercitazioni`).
Nessun search/replace: ogni occorrenza è classificata singolarmente.

| FILE | ROLE | ACTIVE? | OLD PIN | EXPECTED NEW PIN | CLASS | ACTION |
|---|---|---|---|---|---|---|
| `hf_batch.py` (P2) | runtime reale del verbo `go` | **sconosciuto: file non disponibile** | presunto `9afaddf` (da mandato) | `819e7cf` | NOT_VERIFIABLE (P2 assente) | NESSUNA. Da classificare nel prossimo gate leggendo il file reale. Se ACTIVE_RUNTIME_DEPENDENCY → aggiornare **nella copia** `runtime/hf_batch_runtime.py`, mai nell'originale |
| `gate01_lab.py` | test tool storico del Gate 01 | **sconosciuto: file non disponibile** | presunto `9afaddf` | `819e7cf` | NOT_VERIFIABLE (assente) | NESSUNA. Se è solo evidenza storica → non toccare; se serve → copia qualificata + rerun |
| `control.py` (Production Control Pack) | control plane storico | **sconosciuto: file non disponibile** | presunto `9afaddf` | `819e7cf` | NOT_VERIFIABLE (assente) | NESSUNA. Non è nel percorso `go → Core` costruito da questo gate (vedi ARCHITECTURE.md): classificazione attesa `NOT_IN_ACTIVE_PATH` da confermare sul file reale |
| `test_control.py` | test storico con falso-verde noto | assente | — | — | NOT_VERIFIABLE | NESSUNA. Una sua esecuzione diretta non vale come prova (mandato §19) |
| `vf-tenant-valorefarmacia/TENANT_CONFIG.json` → `core_dependency.CORE_DEPENDENCY_COMMIT_SHA` | dichiarazione del Core su cui il tenant gira | sì, ma **NON nel percorso di questo runtime gate** (il gate non carica TENANT_CONFIG) | `9afaddf3cec1e8baf9600ed8dc0461e7adccb5c7` | `819e7cfedb0f6641dc797e7993bec79462ac8df6` | STALE_PIN / NOT_IN_ACTIVE_PATH | **NON modificato** (repository tenant canonico, fuori mandato). Da aggiornare con mandato tenant separato: la nota stessa nel file dice "se diverge dal CORE_COMMIT_SHA corrente, la divergenza va dichiarata, non ignorata" — dichiarata qui |
| `creative-os` (codice e governance) | Core | — | nessuna occorrenza di `9afaddf` nei file | — | — | nessuna |

## Controllo di versione nel runtime candidate

Il controllo NON è stato rimosso: è stato **rafforzato** in `runtime/core_pin.py`.

| input | esito | test |
|---|---|---|
| Core checkout a `819e7cf` | `CORE_PIN_OK` → `go` procede | T01 PASS |
| SHA casuale (`deadbeef…`) | `CORE_PIN_MISMATCH` → nessun import del Core, nessuno store creato | T02 PASS |
| Core checkout reale a `9afaddf` (worktree temporaneo, poi rimosso) | `STALE_CORE_PIN` → nessun import del Core | T03 PASS |
| Core checkout a `819e7cf` con `transport/pipeline.py` modificato e non committato (HEAD invariato) | `CORE_WORKTREE_DIRTY` → nessun import del Core | T20 PASS (ADDENDUM) |
| Core checkout a `819e7cf` con un file `.py` non tracciato dentro `adapters/` | `CORE_WORKTREE_DIRTY` → nessun import del Core | T20 PASS |
| `git status` non disponibile sul checkout | `CORE_WORKTREE_DIRTY` (fail-closed, non verificabile = sporco) | T20 verdetto puro |

Lo SHA osservato si legge dal checkout (`git rev-parse HEAD`), non da un file dichiarativo; la pulizia
dell'albero da `git status --porcelain --untracked-files=all` sullo stesso checkout (file ignorati da
`.gitignore`, es. `__pycache__`, non contano; ciò che sta fuori dal checkout non è visto da git).
Ordine dei verdetti: identità prima (STALE/MISMATCH), poi pulizia (DIRTY).
Il gate avviene **prima** di `sys.path.insert(core_path)`: un Core non autorizzato non viene
nemmeno importato (`core_imported=False` in evidence T02/T03).
