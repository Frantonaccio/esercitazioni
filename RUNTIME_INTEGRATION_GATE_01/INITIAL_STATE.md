# INITIAL_STATE — RUNTIME INTEGRATION GATE 01

Data: 2026-09-16 (UTC) · Ambiente: sessione Claude Code remota (container effimero)
Mandato: `hf_batch.py go → CORE C26 → ReservationStore → FakeAdapter` · MOCK ONLY · ZERO CREDITS

## A. Core canonical — VERIFICATO

| voce | atteso | osservato | esito |
|---|---|---|---|
| repository | `Frantonaccio/creative-os` | clonato in `/home/user/creative-os` | OK |
| branch | `main` | `main` | OK |
| HEAD | `819e7cfedb0f6641dc797e7993bec79462ac8df6` | `819e7cfedb0f6641dc797e7993bec79462ac8df6` | OK |
| working tree | CLEAN | `git status --porcelain` vuoto | OK |
| PR #2 | MERGED | HEAD è il merge commit di `feat/core-atomic-reservation-c26` | OK |
| suite baseline | tutte exit 0 | `run_reservation` 10/10 · `run_block2` 18/18 · `run_review_pr2` R1–R4 NOT_CONFIRMED · `run_review_pr2_final` R5–R6 NOT_CONFIRMED · `run_boot_paths` OK · `run_case_collision` 0 collisioni · `run_golden` 1 REJECT · 1 PASS | OK |

Contratti C26 presenti nel Core e consumati dal runtime (nessuno ricostruito):
`ReservationStore` (Protocol), `SqliteReservationStore`, `run_job`, `JobState`,
`ReservationOutcome`, `BudgetExceeded`, `ProviderMismatch`, `ReservationContractError`,
`validate_units`, `GenSpec.spec_key`, `SUBMIT_UNKNOWN`, `expire → SUBMIT_UNKNOWN`,
`put` (durable poll persistence).

## B. P2 — NON DISPONIBILE IN QUESTO AMBIENTE

| voce | osservato |
|---|---|
| `hf_batch.py` | **non esiste** su disco (`find / -name hf_batch.py` → nessun risultato), non è in nessun repository GitHub raggiungibile dalla sessione (`creative-os`, `vf-tenant-valorefarmacia`, storia git inclusa) |
| SHA256 storico | prefix `637f3a80…` noto solo dal mandato; **full hash non disponibile** |
| SHA256 attuale | **non calcolabile**: nessun file |
| baseline registrata | NESSUNA. Non si dichiara un match che non si può dimostrare |
| modifiche a P2 | 0 (nessun file P2 è mai stato presente in questo ambiente) |

P2 vive sulla macchina locale dell'operatore. Vale la regola del mandato §2:
**Core/P2 non coincidono con lo stato atteso → il gate chiude BLOCKED** sulla parte P2,
mentre tutto ciò che dipende dal solo Core è stato costruito e provato (vedi FINAL_STATE.md).

## C. File runtime cercati

| file | esito |
|---|---|
| `gate01_lab.py` | non trovato in nessun percorso né repository raggiungibile |
| `control.py` (Production Control Pack) | non trovato |
| `test_control.py` | non trovato |
| altri file con `9afaddf` | **uno solo**: `vf-tenant-valorefarmacia/TENANT_CONFIG.json` (`core_dependency.CORE_DEPENDENCY_COMMIT_SHA`) — vedi PIN_AUDIT.md |

Il commit `9afaddf3cec1e8baf9600ed8dc0461e7adccb5c7` è il **commit iniziale del Core**
(`git merge-base --is-ancestor 9afaddf HEAD` → vero). Un pin a `9afaddf` è quindi un Core
VECCHIO, non sconosciuto: il gate lo classifica `STALE_CORE_PIN`.

## D. Provider e credenziali

| verifica | osservato |
|---|---|
| Higgsfield CLI (`which higgsfield`, `which hf`) | **non installata** in questo container |
| `~/.higgsfield/credentials.json` | **non esiste** |
| variabili d'ambiente `HIGGSFIELD*` / `SEEDANCE*` / `KLING*` | nessuna |
| MCP server Higgsfield | connesso alla sessione come strumento, **mai invocato** (nessuna chiamata `mcp__Higgsfield__*` in tutta la sessione) |
| rete generativa | nessuna: l'unico traffico di rete della sessione è `git clone`/`fetch` verso GitHub |
| crediti spesi | 0 |

Poiché la CLI non esiste, la prova "esiste ma non viene invocata" è sostituita da una prova
più forte e strumentata: una sentinella `sys.addaudithook` con esca (`HOME` finta contenente
`.higgsfield/credentials.json` e `HIGGSFIELD_API_KEY` canary) — vedi T14/T15.

## E. Ambiente isolato creato

```
/home/user/esercitazioni/RUNTIME_INTEGRATION_GATE_01/     (fuori da P2, fuori dal Core canonical)
  runtime/    core_pin.py · provider_gate.py · genspec_bridge.py · go_candidate.py
  tests/      run_gate.py · worker.py · audit_sentinel.py · static_checks.py
  evidence/   T01…T19 JSON · RESULTS.json · patch e log del cleanup typing
  state/      *.db SqliteReservationStore (solo laboratorio)
```

Worktree Core separato per il cleanup typing: `/home/user/creative-os-typing-cleanup`
(branch `chore/pipeline-reservationstore-annotation`, base `819e7cf`).

Rollback del gate: cancellare `RUNTIME_INTEGRATION_GATE_01/` e
`git -C /home/user/creative-os worktree remove /home/user/creative-os-typing-cleanup`.
