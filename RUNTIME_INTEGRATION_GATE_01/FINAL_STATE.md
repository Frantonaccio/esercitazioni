# FINAL_STATE — RUNTIME INTEGRATION GATE 01

## STATUS: **READY_FOR_RUNTIME_INTEGRATION_REVIEW**

Il verbo `go` del vero P2 `hf_batch.py` (SHA256 `637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1`),
copiato in `runtime/hf_batch_runtime.py`, consuma il Core canonical `819e7cf` (C26) attraverso `go_candidate` e si
comporta correttamente su spec reali sotto concorrenza (2 processi), crash/restart, risposta incerta e provider mismatch,
senza poter raggiungere Higgsfield. Matrice **23/23 PASS**, 0 BLOCKED, 0 FAIL.

Non dichiarato: PRODUCTION_READY · LIVE_ENABLED · PROVIDER_ENABLED · HIGGSFIELD_READY · DEPLOYED.

## Cronologia del gate

| commit | contenuto |
|---|---|
| `f7f07c5` | gate iniziale: candidate `go`, pin gate, fake-mode gate, bridge, T01–T19 (18 PASS, T16 BLOCKED per P2-ABSENT) |
| `042de1f` | addendum T20: `CORE_WORKTREE_DIRTY` fail-closed |
| questo commit | resume da handoff P2: T16 chiuso, mapping reale (T21), copia `hf_batch_runtime.py` innestata (T22), integrità handoff (T23) |

## Stato finale verificato

| voce | valore |
|---|---|
| branch | `claude/runtime-integration-gate-01-n8l0y7` (ripreso da `042de1f`) |
| Core canonical HEAD | `819e7cfedb0f6641dc797e7993bec79462ac8df6` · `main` · working tree pulito (T17) |
| Core canonical modificato | **no** (0 file) |
| Core typing cleanup | branch `chore/pipeline-reservationstore-annotation`, commit `6b0eae80…`, 8 suite exit 0, **NOT MERGED** |
| P2 `hf_batch.py` SHA256 before / after | `637f3a80…3ea7d1` / `637f3a80…3ea7d1` (T16): baseline calcolata all'avvio della corsa, ricalcolata a fine corsa, uguale allo SHA dichiarato da 4 fonti indipendenti (mandato, `SHA256SUMS` del handoff, `scripts[].sha256` del lock di produzione, `INITIAL_STATE` storico) e al backup `LAB/hf_batch_ORIGINAL.py`; mtime e size invariati |
| P2 originale sul Mac | fuori git (`VF_PILOT_OUTPUTS/P2_PRIMA_SI_PARLA/RUN_20260915_FINAL_PRODUCTION/scripts/hf_batch.py`), non in questo ambiente: attestato dalle 4 fonti sopra, 0 modifiche possibili da qui |
| handoff | copia read-only in `p2_handoff/`, manifest 35 file 0 mismatch (T23); ZIP hash in `evidence/HANDOFF_ZIPS.sha256` |
| matrice | 23/23 PASS (`TEST_RESULTS.md`) |
| provider usato | `FakeAdapter` (Core) e sottoclassi di laboratorio |
| crediti spesi | 0 |
| Higgsfield (CLI, MCP, credenziali, rete) | mai invocato, mai letto, mai aperto (T14/T15/T22 con sentinella; `lock`/`quote` → `REAL_PROVIDER_DISABLED`) |
| store durevole | `SqliteReservationStore` in `state/*.db`, solo laboratorio |
| audit decision ZIP | copiato in `p2_handoff/VF_ARTIFACT_AUDIT_DECISION_2026-09-16.md` come **riferimento**: nessun cleanup, delete, move o merge eseguito sulla sua base |

## Risultati chiave del resume

- **T16**: before == after == dichiarato, 5 fonti concordi.
- **T21**: 27 job reali in 11 spec: `prompt()`/`media()` del bridge identici al codice originale eseguito read-only;
  per i 2 job del lock di produzione `prompt_sha256` e `sha256_sent` combaciano; `spec_key` stabile in un altro
  processo; 4 mutazioni reali (blocco di prompt, `duration`, byte della start image, `run_id`) → 4 chiavi diverse;
  metadati QA (`edit_use`, `must_show`, `beat`) → stessa chiave; media mancante → rifiuto.
- **T22**: `hf_batch_runtime.Batch.go()` su `spec_motion_B1_B4C.json`: GO#1 → 2×`RESERVED_NEW`, 2 submit fake;
  GO#2 → 2×`EXISTING_LIVE_JOB`, 0 submit; GO#3 in **nuovo processo** con nuovo adapter → riprende gli stessi
  `job_id`/`provider_job_id`, 0 submit, 2×`SUCCEEDED` persistiti; `run_verdict=LOCK_HELD`; `lock`/`quote` →
  `REAL_PROVIDER_DISABLED`; 0 violazioni della sentinella in tutti i processi.
- **T19** esteso alla copia: `run_job` non chiama `subprocess`/`urllib`/`os.system`; la CLI è raggiungibile solo da
  funzioni che iniziano con `_real_cli()`.

## Cosa la review deve decidere

Vedi BLOCKERS_OPEN.md §"Punti da decidere": regola "batch concluso non si rigenera", ruolo del lock preventivo
accanto al Core, pin del tenant. Poi, con mandato separato: repository runtime dedicato (non creato qui) e
Runtime Hardening / Provider Boundary Gate.
