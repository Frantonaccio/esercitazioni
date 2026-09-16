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
| T16 | P2 hash unchanged | SHA256(hf_batch.py) before == after | **BLOCKED**: file assente in questo ambiente |
| T17 | Core canonical unchanged | HEAD == `819e7cf`, branch main, working tree pulito | `git rev-parse` + `git status --porcelain` a fine corsa |
| T18 | durable terminal persistence | SUCCEEDED riletto da nuovo processo; nuovo GO dopo terminale = nuovo tentativo (2 righe storiche, 0 impegnato) | spawn ×4 |
| T19 | static: no duplicate control system | 0 findings AST; import dal Core = 4 attesi | `tests/static_checks.py` su `runtime/*.py` |

T19 è aggiuntivo rispetto a T01–T18: è il test statico obbligatorio del mandato §9.
