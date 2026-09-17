# MATRICE DELLE REGRESSIONI

Tutto rieseguito contro la **coppia candidate** (Core `44f9ea29` + Runtime del branch
di questa fase). Evidenza: `evidence/E08_regression_r0_r1.json`,
`evidence/E09_mechanism_and_core_regressions.json`, `regression/`.

## Il confronto che conta

Non "il post-fix passa", ma **pre-fix vs post-fix nello stesso ambiente**. Per questo
la suite storica e' stata eseguita **prima** di toccare una riga
(`regression/r0_r1_RESULTS_pre_fix.json`, `regression/r0_r1_run_gate_pre_fix.log`) e
di nuovo alla fine (`regression/r0_r1_RESULTS_post_fix.json`,
`regression/r0_r1_run_gate_post_fix.log`).

---

## R0-R1 · T01–T37 (Runtime)

| | pre-fix (coppia canonica, stesso ambiente) | post-fix (coppia candidate) | baseline dichiarata dal handoff |
|---|---|---|---|
| totale | 37 | **37** | 37 |
| PASS | 35 | **36** | 36 |
| FAIL | **T08** | **nessuno** | 0 |
| BLOCKED | T29 `BLOCKED_ENVIRONMENT` | **T29 `BLOCKED_ENVIRONMENT`** | T29 `BLOCKED_ENVIRONMENT` |
| inventario | valido | **valido** | — |

**Regressioni introdotte da questa fase: nessuna.**

T29 mantiene la propria semantica storica (`BLOCKED_ENVIRONMENT`): l'ambiente del
runner resta same-UID, come a baseline. Non e' stato ne' forzato ne' riclassificato.

### Il FAIL pre-fix di T08 — un difetto PREESISTENTE, non una regressione

Alla prima esecuzione, **prima di qualunque modifica**, T08 ("concurrent duplicate",
due processi reali) e' fallito sulla coppia canonica con:

```
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
  runtime/payload_snapshot.py:182  in seal()  ->  prev = _read_json(seal_path)
```

Causa: `_write_once` apre con `O_EXCL` e **poi** scrive. Fra `os.open` e `os.write`
il file esiste ed e' vuoto; un secondo processo riceve `FileExistsError` e rilegge
subito un file di 0 byte. Stessa finestra sul file `.bin` (che diventerebbe
`DIGEST_COLLISION`).

Stato accertato:

- **riproducibile** con la traccia sopra, sul codice canonico, senza mie modifiche;
- **intermittente**: 8 esecuzioni isolate di T08 su 8 hanno superato
  (`regression/T08_pre_fix_seal_race.json` conserva l'esito fallito);
- **non** si e' ripresentato nella corsa post-fix, che ha dato 36/37.

Perche' non e' stato corretto qui: e' un difetto di concorrenza del **percorso
governato** (ledger degli snapshot P-B04), non un percorso di spesa legacy. Correggerlo
sarebbe `SCOPE_EXPANSION_REQUIRED`, e il mandato dice di non aggirare gli STOP. E'
dichiarato come requisito aperto nuovo: `SNAPSHOT_SEAL_WRITE_RACE = STILL_OPEN`
(`OPEN_REQUIREMENTS.md`).

---

## Meccanismi gia' approvati, rieseguiti sul candidate

Con **le stesse funzioni** del gate approvato (`pbg2.run_gate2` c02/c03/c04/c05);
le evidenze sono scritte in `evidence/mechanisms/` di questo bundle, quelle approvate
non sono state toccate.

| meccanismo | esito |
|---|---|
| P-B01 + P-B02 composition (UID distinto, `SO_PEERCRED`, autorita' di firma confinata) | **PASS** |
| NG-04 freshness mechanism | **PASS** (meccanismo; la **policy** resta `POLICY_DECISION_REQUIRED`) |
| legacy spend paths v2 | **PASS** |
| orphan reserved lease mechanism | **PASS** (meccanismo; la **policy** resta `POLICY_DECISION_REQUIRED`) |

`C04` continua ad asserire `core_primitives_reachable_in_both_modes = true`: e' un
controllo del **Runtime**, e per il Runtime quelle primitive restano raggiungibili — a
chiuderle e' il Core, che quel gate non conosce. Non e' una contraddizione: e'
esattamente la ragione per cui il requisito si chiamava `CORE_CHANGE_REQUIRED`.

## Suite del CORE sul candidate

| suite | esito |
|---|---|
| `run_r0_r1_hardening` | **47/47** |
| `run_reservation` | **10/10** |
| `run_block2` | **18/18** |
| `run_golden` | PASS |
| `run_boot_paths` | PASS |
| `run_case_collision` | PASS |
| `run_review_pr2` | PASS |
| `run_review_pr2_final` | PASS |
| `run_ng05_pre_submit_atomicity` | PASS |
| `run_spender_boundary` (nuova) | **11/11** |
| `run_contamination` | **NON eseguita** — `RUN_CONTAMINATION` resta `NOT_RUN` per mandato, e non va chiusa incidentalmente |

## Pin del Core e P2

| | |
|---|---|
| `REQUIRED_CORE_SHA` == Core HEAD | ✓ `44f9ea29cea112dfb30c752e5519498e25044c19` |
| `9cf9cee1…` (baseline precedente) ora `STALE_CORE_PIN` | ✓ |
| SHA sconosciuto → `CORE_PIN_MISMATCH` | ✓ |
| tree sporco sullo SHA giusto → `CORE_WORKTREE_DIRTY` | ✓ |
| P2 `hf_batch.py` before == after == `637f3a80…3ea7d1` | ✓ |

## Migrazione dei test storici

20 equivalenti (19 `GOVERNED_PATH` + 1 `CORE_UNIT`): **20/20 PASS**.
Dettaglio in `LEGACY_TEST_MIGRATION_MATRIX.md`.
