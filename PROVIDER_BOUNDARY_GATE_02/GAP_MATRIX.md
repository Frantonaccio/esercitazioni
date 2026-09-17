# GAP MATRIX — PROVIDER BOUNDARY GATE / OPEN-GAP CLOSURE (PHASE A)

Prodotta PRIMA di qualunque write di correzione, sul Runtime canonico
`0698279703ab959625ac4e84ee636bc5b93b45fd` e sul Core canonico
`740ee979300fe20a9382992528604dee70cb2fcf`.

Evidenza grezza: `evidence/pre_fix/reproduction_*.json` (driver: `pbg2/reproduce.py`,
worker: `pbg2/repro_workers.py`). Ogni riproduzione gira in un **processo reale**
(`multiprocessing spawn`), mai in-process nel driver.

MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUCTION.

---

## 1. `LEGACY_SPEND_PATHS_PROVIDER_GATE` — `REPRODUCED`

| campo | contenuto |
|---|---|
| **requisito** | Nessun percorso capace di raggiungere submit/spend deve poter bypassare governed authorization, quote authority, envelope, permit, operation/attempt identity, exact-byte snapshot, spender boundary, economic ledger. |
| **file/function reali** | `runtime/go_candidate.py:go` (ramo `authorization is None`); `runtime/provider_gate.py:legacy_spend_path_state`, `require_legacy_lab_spend_path`; `tests/worker.py:store_call`, `run_go`; `creative-os/transport/pipeline.py:run_job`; `creative-os/registry/reservations.py:reconcile`. |
| **call path reale** | `go(..., authorization=None)` → `require_legacy_lab_spend_path()` (passa: `ENABLED_LAB_ONLY`) → `require_core_verdict` → `SqliteReservationStore` → `ledger.seal` → `run_job` → `adapter.submit`. |
| **prova di riproduzione** | `reproduction_legacy_spend_paths.json`. `legacy_lab_switch.open`: `state=SUCCEEDED`, `submits=1`, `governance=LEGACY_LAB`, `quote_id=null`, `envelope_id=null`, `permit_id=null`, `budget_units=0`, `legacy_resume_as_start=true`. `test_helper_store_call`: `store_call("reserve_or_get_live_by_prompt_op")` → `RESERVED_NEW` fuori dal governed path. `core_primitives_direct`: `transport.pipeline.run_job` diretta → `SUCCEEDED`, `submits=1`; `store.reconcile` raw con evidenza `{"source":"chiunque","remote_ref":"pv:di_qualcun_altro"}` → **accettata**, `FAILED`. |
| **stato** | `REPRODUCED` |
| **rischio** | Con un provider reale, un percorso non governato spende senza quote authority, senza envelope, senza permit e senza snapshot exact-byte. Il costo non ha autorità che lo attesti. |
| **fix minimo** | Interruttore di modalità unico e fail-closed (`PROVIDER_BOUNDARY_MODE`) verificato **prima di ogni effetto**, che chiude insieme i percorsi del Runtime (#2, #4, #7). I percorsi #10/#11 sono primitive del **Core**: non chiudibili dal Runtime senza modifica del Core (vedi §6). |
| **test necessario** | Inventario aggiornato (statico AST + dinamico) + controprova per ogni entry point con modalità aperta/chiusa. |

---

## 2. `P_B02_P_B01_COMPOSITION` — `REPRODUCED`

| campo | contenuto |
|---|---|
| **requisito** | Segreto e signing key confinati nel dominio spender; orchestrator che non può leggerli né forgiare un report valido. |
| **file/function reali** | `PROVIDER_BOUNDARY_HARDENING_01/pbgate/spender_daemon.py` (schema chiuso: `boundary_mock.ALLOWED_OPS` + `DAEMON_OPS`); `runtime/reconciliation.py:derive_report_key`, `LabProviderStatusAuthority.key`, `reconcile_authenticated`. |
| **call path reale** | In B03/B04 della fase precedente: `run_boundary_gate.b03` → `pb_worker.make_report(secret, …)` → `pb_worker.reconcile(...)`, **tutto nel processo del gate**. Il daemon spender non ha alcun percorso verso `reconcile_authenticated`. |
| **prova di riproduzione** | `reproduction_pb01_pb02_composition.json`. Statico: `daemon_allowed_ops = ["quote","status","stop","submit","whoami"]`, `daemon_has_reconciliation_op = false`, `daemon_calls_reconcile_authenticated = false`, `key_is_public_property = true`, `derive_report_key_is_public = true`. Dinamico: `forge_with_leaked_key` — un processo qualunque che ottiene `LabProviderStatusAuthority.key` (esposta dall'API) firma un report e la riconciliazione **lo applica**: `{"applied": true, "state": "SUCCEEDED"}`. |
| **stato** | `REPRODUCED` |
| **rischio** | La custodia del segreto è una proprietà del processo chiamante, non della firma. Con un provider reale, chiunque condivida il dominio del chiamante può attestare esiti remoti mai avvenuti. |
| **fix minimo** | Spostare l'autorità di firma **dentro** il daemon spender (segreto generato lì, chiave mai serializzata sul canale) ed esporre `report` / `reconcile` come operazioni dello schema chiuso; l'orchestrator riceve esiti, non chiavi. |
| **test necessario** | 11 controprove del mandato (§7) eseguite dall'orchestrator con UID distinto, più un quarto UID non autorizzato. |

---

## 3. `RECONCILIATION_FRESHNESS_NG04` — `REPRODUCED`

| campo | contenuto |
|---|---|
| **requisito** | Nel percorso destinato al Provider Boundary Gate la freshness non può restare opzionale. |
| **file/function reali** | `runtime/reconciliation.py:reconcile_authenticated`, parametro `max_age_s: float \| None = None`, riga `if max_age_s is not None and now - float(report["issued_at"]) > max_age_s`. |
| **call path reale** | `reconcile_authenticated(...)` — nessun chiamante del runtime passa `max_age_s` (`go_candidate` non riconcilia report; il daemon non chiama la funzione). |
| **prova di riproduzione** | `reproduction_ng04_freshness.json`. **A**: report firmato con `issued_at = 0.0` (1970), `max_age_s=None` → `applied = true`, stato `SUCCEEDED`. **B**: `issued_at = 2000000000.0` (nel futuro), `max_age_s = 60.0` → `now - issued_at` è negativo, il confronto `> max_age_s` non scatta → `applied = true`. |
| **stato** | `REPRODUCED` (entrambi gli assi: opzionalità **e** timestamp futuro non gestito) |
| **rischio** | Un report autenticato catturato e mai consumato resta valido per sempre; un emittente con orologio avanti (o malevolo) aggira qualunque finestra. |
| **fix minimo** | Politica di freshness **obbligatoria e parametrica**: il chiamante deve fornirla esplicitamente, l'assenza è un rifiuto. Copre: max age, timestamp futuro, clock skew tollerato, `issued_at` malformato/assente, boundary della finestra. Il **valore** della finestra non viene scelto qui. |
| **test necessario** | Otto casi del mandato + boundary esatto (`age == max_age` e `age == max_age + ε`), con la policy passata come parametro e mai come default nascosto. |

---

## 4. `NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY` — `REPRODUCED` + `CORE_CHANGE_REQUIRED`

| campo | contenuto |
|---|---|
| **requisito** | Verificare se il Core canonico offre già una primitive che ottenga in UNA transazione terminalizzazione + settlement zero + provenance parametrica e veritiera + ledger + anomaly/evidence + CAS/revision safety. |
| **file/function reali** | `creative-os/registry/reservations.py`: `mark_refused_before_send`, `reconcile`, `settle`, `_set_state`; `runtime/go_candidate.py:ReservationObserver._refuse_pre_submit`. |
| **call path reale** | `ReservationObserver.mark_submitting` → `SnapshotBinding.bind` solleva → `_refuse_pre_submit` → `store.reconcile(job, FAILED, evidence)` **(transazione 1)** → `store.settle(job_id, units=0, source=…)` **(transazione 2)**. |
| **prova di riproduzione** | `reproduction_ng05_atomicity.json`. **Superficie del Core** (letta con `inspect`, non dalla documentazione): `single_transaction_primitive_with_parametric_provenance = []`. Nel dettaglio: `mark_refused_before_send` scrive stato + `settled_units` + riga `SETTLE` in una sola transazione ma con `hardcoded_sources = ["TRANSPORT_ATTESTED_NOT_SENT"]` e `settlement_source_parametric = false`; `reconcile` scrive lo stato ma **non** `settled_units` e **non** la riga di ledger, e non accetta `extra_sql` dal chiamante; `settle` scrive `settled_units` con `source` parametrica ma **non** lo stato e **non è nel Protocol** `ReservationStore`. L'unico punto che compone le due scritture, `_set_state(..., extra_sql=…)`, è privato. **Finestra riprodotta con morte reale del processo** (`os._exit(7)` fra le due chiamate, exitcode osservato `7`): riga finale `state=FAILED`, `settled_units=null`, `settlement_source=null`, `revision=3`; totali `terminal_unsettled_jobs: 0 → 1`, `unsettled_exposure_units` resta `10`. |
| **stato** | `REPRODUCED` · `CORE_CHANGE_REQUIRED` |
| **rischio** | Conservativo (l'esposizione resta impegnata, `settle` è idempotente), quindi **non** un rischio economico di sottostima; è un terminale non regolato visibile in `terminal_unsettled_jobs`. Il rischio è di audit e di rumore operativo. |
| **fix minimo** | API **additiva** del Core `mark_refused_pre_submit(job, reason, *, source, evidence, now)`: identica a `mark_refused_before_send` ma con provenance parametrica, su un branch Core dedicato. **Nessuna modifica a Core `main`**, nessun abuso di `mark_refused_before_send`, nessuna provenance falsa. Il Runtime **non** viene commutato: resta pinnato a `740ee979` e conserva il percorso conservativo finché la modifica Core non è approvata e mergiata. |
| **test necessario** | Test nel Core branch: singola transazione (crash hook prima del COMMIT → nulla applicato), provenance parametrica registrata, CAS sulla revisione, transizione ammessa, riga di ledger coerente, rifiuto di una `source` vuota. |

---

## 5. `ORPHAN_RESERVED_LEASE` — `REPRODUCED`

| campo | contenuto |
|---|---|
| **requisito** | Separare nettamente meccanismo e policy; non convertire il requisito in CLOSED perché il meccanismo esiste. |
| **file/function reali** | `runtime/orphan_lease.py` (API pubblica: `RESERVED_NO_INTENT`, `RESERVED_WITH_INTENT`, `NOT_RESERVED`, `RECLAIM_POLICY`, `classify_attempt`, `inventory`); `creative-os/registry/reservations.py:recover_orphaned_submits`, `due_for_reconcile`, `_set_state`. |
| **call path reale** | `reserve_or_get_live` committa `RESERVED` → il processo muore prima di `mark_submitting` → nessun campo di intento persistito. |
| **prova di riproduzione** | `reproduction_orphan_lease.json`. `has_lease_mechanism = false` (nessun simbolo `lease*`/`reclaim*` oltre alla costante). `classify_no_intent`: `class=RESERVED_NO_INTENT`, `exits_available=[]`, `reclaim_policy=NOT_AUTHORIZED`. Uscite tentate: `resume` → `EXISTING_LIVE_JOB/reserved-no-dispatch` con `submits=0`; `new_attempt` → `LIVE_OR_UNCERTAIN_ATTEMPT`; `recover_orphaned_submits` → `[]`; reconciliation autenticata → `OWNERSHIP_INCOMPLETE`. |
| **stato** | `REPRODUCED` |
| **rischio** | L'identità dell'operazione resta occupata per sempre; con budget non nullo l'esposizione resta impegnata (nella riproduzione il budget è 0 perché la prenotazione avviene via `reserve_or_get_live` grezza: `reserved_units = 0`). |
| **fix minimo** | Meccanismo **parametrico** di lease: ownership, lease timestamp, lease identity, authority esplicita, fencing token + CAS sulla revisione, recovery, zero blind retry, sicurezza in concorrenza e su crash durante il reclaim. Il meccanismo **non deve scegliere** finestra, attore, evidenze o stati ammessi: senza policy esplicita rifiuta. |
| **test necessario** | Meccanismo esercitato con policy iniettata nel test; controprove: policy assente → rifiuto; corsa con `mark_submitting` (chi perde ottiene `StaleWrite`); fencing token stantio; crash durante il reclaim; nessun nuovo attempt creato. |

---

## 6. `REAL_AUTHORIZATION_AND_PRICING` / `REAL_PROVIDER_RECONCILIATION` — `REAL_PROVIDER_REQUIRED`

Non riproducibili né chiudibili in questa fase per mandato: richiedono provider reale,
credenziali reali e consumo di crediti, tutti **fuori scope**. Nessuna chiamata a provider è
stata effettuata, nessuna credenziale letta o installata. Deliverable sostitutivo:
`REAL_PROVIDER_PREREQUISITES.md`.

---

## Premesse del mandato verificate

| premessa | esito |
|---|---|
| «`max_age_s` è opzionale» | **VERA** (`default None`, riprodotto) — e **più ampia del dichiarato**: anche con `max_age_s` fornita, un `issued_at` nel futuro passa. |
| «il percorso veritiero usa `reconcile` → `settle` in due transazioni» | **VERA** (riprodotto con morte reale del processo). |
| «il Core potrebbe già offrire una primitive a transazione singola» | **FALSA**: nessuna primitive con provenance parametrica. `CORE_CHANGE_REQUIRED`. |
| «B03/B04 espongono segreto e chiave nel processo di test» | **VERA**, e il daemon spender non ha alcuna operazione di reconciliation. |
| «`LEGACY_LAB` è ancora spendibile» | **VERA** con l'interruttore nello stato di default `ENABLED_LAB_ONLY`. |
| «esiste una reclaim policy da implementare» | **NON ASSUNTA**: nessuna reclaim esiste e nessuna viene inventata qui. |

## Perimetro dichiarato

Nessuno stato in questa matrice significa provider ready, production ready, credenziali
autorizzate, spend autorizzato, merge autorizzato o R2 autorizzato.
