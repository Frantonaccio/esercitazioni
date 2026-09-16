# PIN_AUDIT — vecchi pin del Core (`9afaddf`) → canonical (`819e7cf`)

Nuovo pin canonical: `819e7cfedb0f6641dc797e7993bec79462ac8df6`
Pin storico: `9afaddf3cec1e8baf9600ed8dc0461e7adccb5c7` (commit iniziale del Core, antenato di `819e7cf`)

Metodo: `grep -r 9afaddf` sul container, sulla storia git dei repository raggiungibili e su tutti i file del handoff
P2 (`p2_handoff/VF_RUNTIME_T16_HANDOFF_2026-09-16`). Nessun search/replace: ogni occorrenza classificata singolarmente.

| FILE | ROLE | ACTIVE? | OLD PIN | EXPECTED NEW PIN | CLASS | ACTION |
|---|---|---|---|---|---|---|
| `P2_RUNTIME/hf_batch.py` (SHA `637f3a80…`) | runtime storico di produzione P2 | **no** per la generazione: non pinna un SHA, **registra** `repo_state(CORE)` nel lock con `role_in_run: "nessuno per la generazione"` e `not_active_candidates: 7ea87fd` (riga 121) | nessuno hardcoded; il lock reale registra `9afaddf CLEAN` | — | HISTORICAL_EVIDENCE | **non modificato** (T16). Il candidate `runtime/hf_batch_runtime.py` eredita `repo_state(CORE)` invariato (solo evidenza nel lock) e ottiene il gate reale su `819e7cf` + clean tree da `go_candidate → core_pin` |
| `runtime/hf_batch_runtime.py` (copia candidate) | runtime candidate | **sì** | — | `819e7cf` via `runtime/core_pin.REQUIRED_CORE_SHA` | ACTIVE_RUNTIME_DEPENDENCY | pin applicato consapevolmente **nella copia** attraverso `go_candidate.go` (T01/T02/T03/T20/T22) |
| `P2_RUNTIME/preflight.py` | pre-flight di memoria P2 | no (non nel percorso `go → Core`) | nessuno | — | HISTORICAL_EVIDENCE | nessuna |
| `LAB/gate01_lab.py` (riga 34 `CORE_SHA_PIN = "9afaddf…"`; `DurableJobStore`, `check_transition`, `run_mock_job`) | vecchio lab: reservation/JobState/budget **paralleli** al Core | **no** | `9afaddf` | — | STALE_UNUSED / ARCHIVE_ONLY (superato da C26) | **non modificato, non copiato, non importato**. Nota: già allora `load_core` rifiutava `CORE_DIRTY`; T20 riporta la stessa proprietà nel gate |
| `LAB/hf_batch_lab.py` (verbo `lab` che importa `gate01_lab`) | vecchio lab | no | via `gate01_lab` | — | STALE_UNUSED / ARCHIVE_ONLY | non modificato, non copiato |
| `LAB/test_gate01.py` | test del vecchio lab | no | — | — | TEST_ONLY (storico) | non eseguito come prova, non modificato |
| `CONTROL_PACK_ORIGINAL/scripts/control.py` (riga 20 `CORE_SHA = "9afaddf…"`, righe 55/96 `CORE_VERSION_NOT_TESTED`) | Production Control Pack originale (`_cowork_inbox`) | **no**: `hf_batch.py` non lo importa né lo invoca (0 riferimenti a `control`), non è nel percorso `go → Core` | `9afaddf` | — | STALE_PIN / NOT_IN_ACTIVE_PATH | **non modificato** (pacchetto storico verificato) |
| `CONTROL_PACK_CANDIDATE_FIXED/scripts/control.py` (stesso pin; in più guard Python ≥ 3.9) | candidate corretto del pack | no | `9afaddf` | — | STALE_PIN / NOT_IN_ACTIVE_PATH | **non modificato**; nessuna copia creata in questo gate perché non serve al percorso; `selftest`/`demo` non rieseguiti (mandato §19: "se NON serve: NON modificarlo") |
| `CONTROL_PACK_*/scripts/test_control.py` | test del pack (falso-verde storico nell'originale) | no | — | — | TEST_ONLY | non usato come prova |
| `EVIDENCE/MOTION_B1_B4C_RUNTIME_LOCK.json` (`core.sha = 9afaddf`, `CLEAN`) | lock di produzione reale | — | `9afaddf` | — | HISTORICAL_EVIDENCE | **non modificato**; usato in T21/T22 come fonte di `prompt_sha256` e `sha256_sent` |
| `EVIDENCE/INTEGRATION_GATE_01_initial_state.txt` (`creative-os main 9afaddf dirty=0`) | stato iniziale del vecchio gate | — | `9afaddf` | — | HISTORICAL_EVIDENCE | non modificato |
| `EVIDENCE/DIFF_*.patch`, `CONTROL_PACK_*/SKILL.md`, `references/*.md` | diff e documentazione del pack | — | `9afaddf` citato | — | HISTORICAL_EVIDENCE | non modificati |
| `vf-tenant-valorefarmacia/TENANT_CONFIG.json` → `core_dependency.CORE_DEPENDENCY_COMMIT_SHA` | dichiarazione del Core del tenant | non nel percorso di questo gate | `9afaddf` | `819e7cf` | STALE_PIN / NOT_IN_ACTIVE_PATH | **non modificato** (repo tenant canonico, fuori mandato); divergenza dichiarata qui |
| `creative-os` (codice e governance) | Core | — | nessuna occorrenza | — | — | nessuna |

## Controllo di versione nel runtime candidate

Il controllo NON è stato rimosso: è stato **rafforzato** in `runtime/core_pin.py`, ed è l'unico pin attivo.

| input | esito | test |
|---|---|---|
| Core checkout a `819e7cf`, pulito | `CORE_PIN_OK` → `go` procede | T01, T22 PASS |
| SHA casuale (`deadbeef…`) | `CORE_PIN_MISMATCH` → nessun import del Core, nessuno store creato | T02 PASS |
| Core checkout reale a `9afaddf` (worktree temporaneo, poi rimosso) | `STALE_CORE_PIN` → nessun import del Core | T03 PASS |
| Core a `819e7cf` con `transport/pipeline.py` modificato e non committato (HEAD invariato) | `CORE_WORKTREE_DIRTY` → nessun import | T20 PASS |
| Core a `819e7cf` con un `.py` non tracciato dentro `adapters/` | `CORE_WORKTREE_DIRTY` → nessun import | T20 PASS |
| `git status` non disponibile sul checkout | `CORE_WORKTREE_DIRTY` (fail-closed) | T20 verdetto puro |

Lo SHA osservato si legge dal checkout (`git rev-parse HEAD`), la pulizia da `git status --porcelain
--untracked-files=all` sullo stesso checkout. Ordine dei verdetti: identità prima (STALE/MISMATCH), poi pulizia.
Il gate avviene **prima** di `sys.path.insert(core_path)`.
