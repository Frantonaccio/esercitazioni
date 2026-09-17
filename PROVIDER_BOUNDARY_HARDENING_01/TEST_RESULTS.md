# TEST_RESULTS — PROVIDER / EXECUTION BOUNDARY GATE 01

Core canonical: `740ee979300fe20a9382992528604dee70cb2fcf` · Runtime baseline: `39c82968fbfb3f3b7ba9fcfe9dc317ea0da9e74e` · provider: FakeAdapter only · crediti spesi: 0 · rete generativa: nessuna · credenziali reali: nessuna

Stato per test (authority unica, tri-state): PASS = requisito verificato in LAB · FAIL = requisito NON superato · BLOCKED = requisito NON verificabile nell'ambiente corrente (NON superato).

| TEST | TITLE | EXPECTED | ACTUAL | STATUS | REASON_CODE | EXIT | EVIDENCE |
|---|---|---|---|---|---|---|---|
| B00 | Reality Lock | Core HEAD canonico e pulito; Runtime origin/main canonico; pin; P2 frozen | Core 740ee979300f clean=True · Runtime origin/main 39c82968fbfb (HEAD 39c82968fbfb discende=True) · pin 740ee979300f · P2 637f3a803ee38d04 | **PASS** | `VERIFIED` | 0 | `evidence/B00_reality_lock.json` |
| B10 | R0-R1 regression (run_gate.py T01-T37) on hardened runtime | 36 PASS, T29 BLOCKED_ENVIRONMENT, 0 FAIL, inventario 37/37 | run_gate.py: exit 0 · 36/37 PASS · BLOCKED ['T29/BLOCKED_ENVIRONMENT'] · FAIL [] · inventario valido True · T19 statico PASS | **PASS** | `VERIFIED` | 0 | `evidence/B10_regression_r0_r1.json` |
| B01 | P-B01 real privilege boundary (distinct UIDs) | orchestrator uid != spender uid, 0 caps, no_new_privs; 4 probe canoniche BLOCKED; peer uid autenticato; spesa governata via socket; segreto mai nel canale | uid orchestrator 65531 (caps 0000000000000000, nnp=1) vs spender 65532 · probe canoniche: {'read_worker_secret': 'BLOCKED (PermissionError)', 'write_worker_code': 'BLOCKED (3 files, PermissionError)', 'write_worker_store': 'BLOCKED (OperationalError)', 'direct_dispatch_on_worker_store': 'BLOCKED (OperationalError)'} -> PASS/VERIFIED · terzo uid -> PEER_UID_NOT_AUTHORIZED · prima spesa via socket -> SUCCEEDED conto acct_1aebf3f17cab · resume -> RESUMED/SUCCEEDED · check falliti: nessuno | **PASS** | `VERIFIED` | 0 | `evidence/B01_privilege_boundary_uid.json` |
| B02 | P-B01 same-UID control stays BLOCKED | t29_status(same_uid) -> BLOCKED_ENVIRONMENT; T29 storico e di regressione BLOCKED | same-uid -> BLOCKED_ENVIRONMENT qualunque probe · uid distinti: 4/4 BLOCKED -> PASS, 3/4 o 1 bypass -> FAIL · T29 storico BLOCKED_ENVIRONMENT · T29 regressione BLOCKED_ENVIRONMENT | **PASS** | `VERIFIED` | 0 | `evidence/B02_same_uid_control.json` |
| B03 | P-B02 authenticated reconciliation: binding fail-closed | 16 controprove rifiutate con journal invariato; report valido -> stato scoperto con evidenza firmata | 16 controprove fail-closed (journal invariato: True) · scarti: nessuno · report valido -> SUCCEEDED (provider_job_id pv_remote_1, evidenza firmata registrata) · u2 dopo i rifiuti -> FAILED | **PASS** | `VERIFIED` | 0 | `evidence/B03_reconciliation_authenticated.json` |
| B04 | P-B02 replay / other operation / snapshot audit | replay -> REPLAY; report valido di altro job -> JOB_MISMATCH; RESERVED senza intento -> OWNERSHIP_INCOMPLETE; snapshot mancante -> SNAPSHOT_AUDIT_FAILED | N1 -> RUNNING · incertezza -> replay N1 -> REPLAY · nuovo report -> SUCCEEDED · report valido di altro job -> JOB_MISMATCH · RESERVED senza intento -> OWNERSHIP_INCOMPLETE · snapshot bind rimosso -> SNAPSHOT_AUDIT_FAILED · unico chiamante runtime di store.reconcile: ['reconciliation.py'] | **PASS** | `VERIFIED` | 0 | `evidence/B04_reconciliation_replay_cross_operation.json` |
| B05 | P-B04 exact-byte snapshot | byte persistiti == canonici; sha256(file) == digest job; 0444; seal/bind/send; resume 0 file; API write-once/altra op/token/2o invio rifiutati | go -> SUCCEEDED (1 invio, trasporto SnapshotGuardedTransport) · byte persistiti == canonici ricalcolati: True · sha256(file)==digest job: True · mode 0o444 · seal/bind/send presenti (4 file) · resume: 0 nuovi file · API: overwrite rifiutato, altra op -> SEAL_MISSING, token errato -> ATTEMPT_NOT_BOUND, 2o invio -> SEND_ALREADY_ATTESTED, reorder -> SNAPSHOT_MISSING | **PASS** | `VERIFIED` | 0 | `evidence/B05_snapshot_exact_byte.json` |
| B06 | P-B04 counterproofs refused before send | nested/drift/reorder/sostituzione/missing/corrupt -> sent_count 0, FAILED settlement 0, nessun SUBMIT_UNKNOWN; pre-fix raggiungeva l'invio | 6 controprove: tutte rifiutate PRIMA del marcatore (sent_count 0), FAILED con settlement 0 attestato, nessun SUBMIT_UNKNOWN · pre-fix lo stesso caso 'substitute' raggiungeva l'invio (sent_count 1, SUBMIT_UNKNOWN) · adapter corretto dopo i rifiuti -> SUCCEEDED · check falliti: nessuno | **PASS** | `VERIFIED` | 0 | `evidence/B06_snapshot_counterproofs.json` |
| B07 | Legacy spend paths inventory + fail-closed switch | interruttore chiuso -> LEGACY_SPEND_PATH_DISABLED prima di import/store; governato invariato; hf_batch legacy 0 submit; __main__ mai al provider; P2 frozen non importato | inventario statico: 22 file con hit · legacy aperto -> RealProviderDisabled (solo FakeAdapter) · legacy chiuso -> LEGACY_SPEND_PATH_DISABLED (Core importato: False, store creato: False) · governato con legacy chiuso -> SUCCEEDED · hf_batch legacy chiuso -> LEGACY_SPEND_PATH_DISABLED (0 submit) · __main__ go/lock/quote -> NO LOCK / REAL_PROVIDER_DISABLED ×2 · P2 frozen non importato · check falliti: nessuno | **PASS** | `VERIFIED` | 0 | `evidence/B07_legacy_spend_paths.json` |
| B08 | Orphan RESERVED lease: reproduction + classification | RESERVED_NO_INTENT senza uscite; 0 submit; new_attempt rifiutato; recover ignora; reconcile OWNERSHIP_INCOMPLETE; con intento -> SUBMIT_UNKNOWN; reclaim NOT_AUTHORIZED | orfana senza intento: classe RESERVED_NO_INTENT, uscite [] · resume -> EXISTING_LIVE_JOB/reserved-no-dispatch (0 submit) · new_attempt -> LIVE_OR_UNCERTAIN_ATTEMPT · recover -> [] · reconcile autenticata -> OWNERSHIP_INCOMPLETE · con intento (crash exit 4) -> RESERVED_WITH_INTENT -> recover SUBMIT_UNKNOWN · reclaim: NOT_AUTHORIZED · GAP: STILL_OPEN | **PASS** | `VERIFIED` | 0 | `evidence/B08_orphan_reserved_lease.json` |
| B09 | Authorization / pricing authority (LAB state) | autorita' LAB nello spender; orchestrator non emette quote ne' scrive lo store; importo dal client rifiutato; real: NOT_VERIFIED | autorita' LAB (listino {'fake_model_v1': 10, 'fake_model_v2': 12, 'fake_model_free': 0}, envelope per scope) vive nello spender · orchestrator: quote sullo store spender -> BLOCKED (OperationalError), scrittura store -> BLOCKED (OperationalError), importo dal client -> PROTOCOL: chiavi non ammesse [ · real authorization/pricing: NOT_VERIFIED | **PASS** | `VERIFIED` | 0 | `evidence/B09_authority_lab_state.json` |
| B11 | P2 freeze after + Core pin/tree + static checks | P2 before == after == canonico; Core HEAD canonico pulito; static checks 0 findings | P2 before 637f3a803ee38d04 == after 637f3a803ee38d04 == canonico · Core 740ee979300f clean=True · static checks ok=True (0 findings) | **PASS** | `VERIFIED` | 0 | `evidence/B11_p2_freeze_core_pin_after.json` |

**Totale: 12/12 PASS · BLOCKED: nessuno · FAIL: nessuno**

**GATE_DECISION: `LAB_GATE_COMPLETE_ALL_VERIFIED`** · runner exit 0: raccolta e report completati; nessun FAIL; nessun BLOCKED fuori policy LAB. NON significa 'tutti i requisiti verificati'.

Inventario: 12/12 · valido: True

Readiness:

- lab_mock: `True`
- real_provider: `NOT_DECLARED`
- production: `NOT_DECLARED`
- security_boundary_p_b01: `LAB_VERIFIED_UID_BOUNDARY`
- p_b02_authenticated_reconciliation: `LAB_VERIFIED`
- p_b04_exact_byte_snapshot: `LAB_VERIFIED`
- legacy_spend_paths: `INVENTORIED_SWITCH_VERIFIED_RESIDUAL_BLOCKED_PROVIDER_GATE`
- orphan_reserved_lease: `STILL_OPEN (riprodotto, classificato, nessuna reclaim)`
- authorization_pricing: `LAB_ONLY`
- max_state: `PROVIDER_EXECUTION_BOUNDARY_HARDENING_READY_FOR_HUMAN_REVIEW`

Nulla di quanto sopra significa provider ready, production ready, credenziali autorizzate, spend autorizzato, merge autorizzato o R2 autorizzato.
