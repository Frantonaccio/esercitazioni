# TEST_MATRIX — RUNTIME INTEGRATION GATE 01

Esecuzione: `python3 tests/run_gate.py` (dalla directory del gate). Risultati effettivi in
`TEST_RESULTS.md` e `evidence/RESULTS.json`. Ogni test scrive `evidence/Txx_*.json`.

| TEST | TITLE | EXPECTED | METODO |
|---|---|---|---|
| T01 | correct Core pin | `CORE_PIN_OK`, `go` procede fino a SUCCEEDED | processo spawn, Core a `819e7cf` |
| T02 | wrong Core pin | `CORE_PIN_MISMATCH`; Core non importato; nessuno store creato | processo spawn pulito, `required_core_sha=deadbeef…` |
| T03 | stale old Core pin | `STALE_CORE_PIN`; Core non importato | worktree temporaneo del Core reale a `9afaddf`, rimosso a fine corsa |
| T04 | deterministic spec_key | run A == run B == run C (params riordinati) == altro processo | `build_genspec` ×3 in-process + 1 spawn |
| T05 | spec mutation changes key | 6 mutazioni semantiche → 6 chiavi diverse; 5 input accidentali rifiutati | prompt/model/ref/param/project_id/kind; timestamp/pid/tmpdir/epoch/ISO |
| T06 | happy path | 1 submit, SUCCEEDED persistito, riletto da nuovo processo, provider=fake, budget rilasciato, hash output fake | spawn go + spawn read_state |
| T07 | sequential duplicate | GO#2 = `EXISTING_LIVE_JOB`, 1 solo submit, stesso job_id | stesso adapter `never_terminal`, due `go` |
| T08 | concurrent duplicate | 1 `RESERVED_NEW` + 1 `EXISTING_LIVE_JOB`, 1 submit totale, 2 PID | 2 processi spawn con Barrier, stesso DB/spec |
| T09 | restart/resume | B: nessuna nuova reservation/submit, stesso job_id e provider_job_id, polling continua, SUCCEEDED persistito | A (latency 3, 1 poll) esce; B nuovo interprete, nuovo store, nuovo FakeAdapter |
| T10 | SUBMIT_UNKNOWN no resubmit | SUBMIT_UNKNOWN persistito; GO#2 → `EXISTING_LIVE_JOB/reconciliation-required`, 0 submit, budget non rilasciato | adapter con submit che lancia dopo l'invio |
| T11 | provider mismatch | `ProviderMismatch`, 0 submit, reservation intatta (`fake_a`/RUNNING) | job di `fake_a` vivo, `go` con `fake_b` |
| T12 | budget atomicity | envelope 100: 70 + 50 concorrenti → uno `BudgetExceeded`, impegnati ≤ 100; sequenziale idem | 2 processi con Barrier + variante sequenziale |
| T13 | invalid budget rejection | `ReservationContractError` per -1, True, 1.5, "10", envelope -5; 0 submit; 0 righe | 5 processi spawn |
| T14 | fake mode blocks real provider | `REAL_PROVIDER_DISABLED` prima di credenziali/subprocess/rete/import Core; 0 violazioni; nessun DB | sentinella audit hook + esca, `provider_mode="higgsfield"` |
| T15 | no credential read | fake go → SUCCEEDED con 0 violazioni; controprova: la sentinella rileva lettura esca, env segreta, subprocess `higgsfield` | sentinella + HOME finta con `.higgsfield/credentials.json` |
| T16 | P2 hash unchanged | SHA256(hf_batch.py) before == after == `637f3a80…3ea7d1`; 5 fonti concordi; mtime/size invariati | baseline all'avvio della corsa su `p2_handoff/…/P2_RUNTIME/hf_batch.py`, ricalcolo a fine corsa; confronto con SHA256SUMS del handoff, lock di produzione, INITIAL_STATE storico, backup `hf_batch_ORIGINAL.py` |
| T17 | Core canonical unchanged | HEAD == `819e7cf`, branch main, working tree pulito | `git rev-parse` + `git status --porcelain` a fine corsa |
| T18 | durable terminal persistence | SUCCEEDED riletto da nuovo processo; nuovo GO dopo terminale = nuovo tentativo (2 righe storiche, 0 impegnato) | spawn ×4 |
| T19 | static: no duplicate control system | 0 findings AST; import dal Core = 4 attesi | `tests/static_checks.py` su `runtime/*.py` |
| T20 | dirty Core must fail closed (ADDENDUM) | canonical+clean → pin PASS; canonical+file tracciato modificato (HEAD invariato) → `CORE_WORKTREE_DIRTY`, Core non importato; file non tracciato dentro il checkout → `CORE_WORKTREE_DIRTY`; wrong+clean → `CORE_PIN_MISMATCH`; stale+clean → `STALE_CORE_PIN` | worktree di laboratorio del Core reale a `819e7cf`, modifica deliberata, ripristino, rimozione a fine corsa; finding riprodotto PRIMA della patch in `evidence/T20_finding_reproduction_before_patch.json` |

| T21 | real hf_batch go → GenSpec mapping | 27 job reali: `prompt()`/`media()` identici al codice originale; lock: `prompt_sha256` e `sha256_sent` combaciano; `spec_key` stabile in altro processo; 4 mutazioni reali → chiavi diverse; metadati QA → stessa chiave; media MISSING rifiutato | import read-only di `hf_batch.py` originale + 11 spec reali + lock `MOTION_B1_B4C` |
| T22 | hf_batch_runtime.go on real spec via Core | GO#1 2×RESERVED_NEW + 2 submit; GO#2 2×EXISTING_LIVE_JOB 0 submit; GO#3 nuovo processo → 2×SUCCEEDED 0 submit, stessi job_id; `lock`/`quote` → REAL_PROVIDER_DISABLED; 0 violazioni | copia candidate su `spec_motion_B1_B4C.json`, sentinella attiva, `require`/`fingerprint` stubbati (tenant assente) |
| T23 | P2 handoff integrity | manifest del handoff 35 file, 0 mismatch; 2 ZIP hash registrati | `sha256sum -c` sulla copia in `p2_handoff/` |

T19 è aggiuntivo rispetto a T01–T18: è il test statico obbligatorio del mandato §9.
T20 è l'ADDENDUM della review indipendente del package `f7f07c5`: il pin verificava solo HEAD, non la pulizia dell'albero.
