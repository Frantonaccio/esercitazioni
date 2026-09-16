# TEST_RESULTS — RUNTIME INTEGRATION GATE 01

Core canonical: `819e7cfedb0f6641dc797e7993bec79462ac8df6` · provider: FakeAdapter only · crediti spesi: 0 · rete generativa: nessuna

| TEST | TITLE | EXPECTED | ACTUAL | EXIT | EVIDENCE | PASS/FAIL |
|---|---|---|---|---|---|---|
| T01 | correct Core pin | CORE_PIN_OK, go procede | core_sha=819e7cfedb0f verdict=CORE_PIN_OK state=SUCCEEDED | 0 | `evidence/T01_correct_core_pin.json` | PASS |
| T02 | wrong Core pin | CORE_PIN_MISMATCH, Core non importato, nessuno store | error=CORE_PIN_MISMATCH core_imported=False | 0 | `evidence/T02_wrong_core_pin.json` | PASS |
| T03 | stale old Core pin (9afaddf) | STALE_CORE_PIN, Core non importato | error=STALE_CORE_PIN observed=9afaddf core_imported=False | 0 | `evidence/T03_stale_core_pin.json` | PASS |
| T04 | deterministic spec_key | run A == run B == run C == altro processo | A==B==C==other_process: True (e355dd3ed48831f2…) | 0 | `evidence/T04_deterministic_spec_key.json` | PASS |
| T05 | spec mutation changes key | ogni mutazione semantica -> chiave diversa; dati accidentali rifiutati | 6 mutazioni semantiche -> 6 chiavi diverse: True; 5 input accidentali rifiutati: True | 0 | `evidence/T05_spec_mutation.json` | PASS |
| T06 | happy path | 1 submit, SUCCEEDED persistito, riletto da nuovo processo, provider=fake | state=SUCCEEDED submits=1 provider=fake restart_read=SUCCEEDED reserved_after=0 | 0 | `evidence/T06_happy_path.json` | PASS |
| T07 | sequential duplicate | GO#2 = EXISTING_LIVE_JOB, 1 solo submit | GO#1=RESERVED_NEW GO#2=EXISTING_LIVE_JOB submits=1 same_job_id=True | 0 | `evidence/T07_sequential_duplicate.json` | PASS |
| T08 | concurrent duplicate (2 processi) | 1 RESERVED_NEW + 1 EXISTING_LIVE_JOB, 1 submit totale | outcomes=['EXISTING_LIVE_JOB', 'RESERVED_NEW'] total_submits=1 pids=2 rows=1 | 0 | `evidence/T08_concurrent_duplicate.json` | PASS |
| T09 | restart/resume | B: nessuna nuova reservation/submit, stesso job_id/provider_job_id, terminale persistito | A: RUNNING polls=1 submits=1 | B (nuovo pid): EXISTING_LIVE_JOB submits=0 same_job=True -> SUCCEEDED | 0 | `evidence/T09_restart_resume.json` | PASS |
| T10 | SUBMIT_UNKNOWN no resubmit | SUBMIT_UNKNOWN persistito; GO#2 reconciliation-required, 0 submit, budget non rilasciato | GO#1 -> SUBMIT_UNKNOWN (budget impegnato 30) | GO#2 -> EXISTING_LIVE_JOB/reconciliation-required submits=0 budget ancora 30 | 0 | `evidence/T10_submit_unknown_no_resubmit.json` | PASS |
| T11 | provider mismatch | ProviderMismatch, 0 submit, reservation intatta | fake_a RUNNING | fake_b -> ProviderMismatch submits=0 reservation intatta=fake_a/RUNNING | 0 | `evidence/T11_provider_mismatch.json` | PASS |
| T12 | budget atomicity | envelope 100: 70+50 -> uno BudgetExceeded, impegnati <= 100 | concorrente: ['BudgetExceeded', 'OK'] impegnati=50/100 | sequenziale: A ok, B=BudgetExceeded impegnati=70 | 0 | `evidence/T12_budget_atomicity.json` | PASS |
| T13 | invalid budget rejection | ReservationContractError, 0 submit, 0 righe | 5 valori non ammessi -> ReservationContractError, 0 submit, 0 righe | 0 | `evidence/T13_invalid_budget_rejected.json` | PASS |
| T14 | fake mode blocks real provider | REAL_PROVIDER_DISABLED prima di credenziali/subprocess/rete/import Core | provider_mode=higgsfield -> REAL_PROVIDER_DISABLED violations=0 core_imported=False db_created=False | 0 | `evidence/T14_fake_mode_blocks_real_provider.json` | PASS |
| T15 | no credential read | 0 violazioni in fake mode; controprova: sentinella rileva l'esca | fake go -> SUCCEEDED violations=0 | controprova: sentinella rileva ['credential_file_open', 'provider_subprocess', 'secret_env_read'] | 0 | `evidence/T15_no_credential_read.json` | PASS |
| T16 | P2 hash unchanged | SHA256(hf_batch.py) before == after | before=637f3a803ee3 after=637f3a803ee3 declared=637f3a803ee3 sources_agree=True | 0 | `evidence/T16_p2_hash.json` | PASS |
| T17 | Core canonical unchanged | HEAD == 819e7cf, main, working tree pulito | HEAD=819e7cfedb0f branch=main dirty_files=0 | 0 | `evidence/T17_core_canonical_unchanged.json` | PASS |
| T18 | durable terminal persistence | SUCCEEDED riletto da nuovo processo; nuovo tentativo dopo terminale | SUCCEEDED letto da nuovo processo; nuovo GO dopo terminale = nuovo tentativo (2 righe storiche, 0 impegnato) | 0 | `evidence/T18_durable_terminal.json` | PASS |
| T19 | static: no duplicate control system (AST) | 0 findings; import dal Core = 4 attesi | findings=0 core_imports=4 | 0 | `evidence/T19_static_no_duplicate_control.json` | PASS |
| T20 | dirty Core must fail closed | canonical+clean PASS; canonical+tracked mod -> CORE_WORKTREE_DIRTY (no import); wrong+clean -> MISMATCH; stale+clean -> STALE | clean -> pin ok | tracked mod (HEAD invariato) -> CORE_WORKTREE_DIRTY core_imported=False | untracked inside -> CORE_WORKTREE_DIRTY | wrong+clean -> CORE_PIN_MISMATCH | stale+clean -> STALE_CORE_PIN | 0 | `evidence/T20_dirty_core_fail_closed.json` | PASS |
| T21 | real hf_batch go -> GenSpec mapping | 27 job reali: prompt/media identici all'originale; lock: prompt_sha256 e sha256_sent combaciano; spec_key deterministico; mutazioni reali cambiano chiave | 27 job reali in 11 spec: prompt/media == originale True; lock: prompt_sha e sha256_sent combaciano; spec_key stabile in altro processo True; 4 mutazioni reali -> chiave diversa, metadati QA -> stessa chiave True; media MISSING rifiutato True | 0 | `evidence/T21_real_genspec_mapping.json` | PASS |
| T22 | hf_batch_runtime.go on real spec via Core | 2 RESERVED_NEW + 2 submit; GO#2 EXISTING_LIVE_JOB 0 submit; nuovo processo completa SUCCEEDED; lock/quote REAL_PROVIDER_DISABLED; 0 violazioni | spec reale MOTION_B1_B4C: GO#1 2x RESERVED_NEW (2 submit) · GO#2 2x EXISTING_LIVE_JOB (0 submit) · GO#3 nuovo processo -> 2x SUCCEEDED (0 submit) · lock/quote -> REAL_PROVIDER_DISABLED · violazioni sentinella 0 | 0 | `evidence/T22_hf_batch_runtime_go_real_spec.json` | PASS |
| T23 | P2 handoff integrity | manifest 0 mismatch; ZIP hash registrati | handoff SHA256SUMS: 35 file, rc=0 (0 mismatch); 2 ZIP hash registrati | 0 | `evidence/T23_handoff_integrity.json` | PASS |

**Totale: 23/23 PASS · BLOCKED: nessuno · FAIL: nessuno**
