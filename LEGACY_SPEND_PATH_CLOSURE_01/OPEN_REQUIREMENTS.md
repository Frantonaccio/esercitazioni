# REQUISITI APERTI DOPO QUESTA FASE

Fonte macchina: `READINESS.json`, `evidence/E12_reporting_test_result_vs_readiness.json`.

## Chiusi da questa fase

| requisito | stato | su cosa si regge |
|---|---|---|
| `LEGACY_SPEND_PATHS_CORE_PRIMITIVES` | `CLOSED_LAB_VERIFIED` | E02 (difetto riprodotto sulla coppia canonica), E03 (**18/18** unitari del confine), E04 (sentinella a 0 in ogni percorso legacy, 1 nel governato), E06 (il client non sceglie il prezzo), **E13** (autorizzazione fabbricata e hook diretti: riprodotti su `44f9ea29`, chiusi sul correttivo), **E15** (stesso attempt che conia due autorizzazioni: riprodotto su `605a8d74`, chiuso dal claim nel journal, verificato anche fra due processi reali), **E14** (threat model esplicito) |
| `LEGACY_TESTS_MIGRATION_TO_GOVERNED` | `CLOSED_LAB_VERIFIED` | E05 (LEGACY_LAB non e' capace di provider, contro cinque tentativi di riaprirlo), E07 (20/20 equivalenti governati o Core-unit), E08 (nessuna regressione, assert storici intatti) |

`CLOSED_LAB_VERIFIED` significa: verificato in **laboratorio**, con adapter
deterministici e una sentinella al posto del provider. Non significa verificato con un
provider reale, che e' un requisito diverso e resta aperto.

---

## Policy — NON decise qui, e nessun valore inventato

| requisito | stato |
|---|---|
| `RECONCILIATION_FRESHNESS_NG04_POLICY` | `POLICY_DECISION_REQUIRED` |
| `ORPHAN_RESERVED_LEASE_POLICY` | `POLICY_DECISION_REQUIRED` |

Il **meccanismo** di entrambi e' stato rieseguito e passa (E09). La **finestra** non e'
stata scelta: nessun valore e' stato introdotto — non 30 secondi, non 60 secondi, non
5 minuti, non un'ora, nessun altro. Un meccanismo che funziona senza un valore deciso
resta un requisito aperto, e chiamarlo chiuso sarebbe falso.

---

## Provider reale — fuori perimetro

| requisito | stato |
|---|---|
| `REAL_AUTHORIZATION_AND_PRICING` | `REAL_PROVIDER_REQUIRED` |
| `REAL_PROVIDER_RECONCILIATION` | `REAL_PROVIDER_REQUIRED` |

Zero provider reali, zero credenziali, zero rete generativa, zero crediti in questa
fase. Le controprove usano una sentinella, che prova **raggiungibilita'**, non spesa.

---

## Residui non toccati

| requisito | stato |
|---|---|
| `RUN_CONTAMINATION` | `NOT_RUN` — `tests/run_contamination.py` del Core **non** e' stato eseguito, deliberatamente: eseguirlo come segnale di non-regressione avrebbe rischiato di chiuderlo per sbaglio |
| `G_N02_SEMANTIC_CLAIM_PARAPHRASE` | `STILL_OPEN` |
| `RV07_SCHEDULER_RECOVERY_RESIDUAL` | `STILL_OPEN` |
| `INDEPENDENT_CI_STATUS_CHECKS` | `NOT_RUN` — nessun check di stato indipendente su questi commit |

---

## Nuovo: scoperto in questa fase, NON corretto

### `SNAPSHOT_SEAL_WRITE_RACE = STILL_OPEN`

**Classificazione Human Review 01:** `PREEXISTING` · `FAIL_CLOSED` ·
`AVAILABILITY / CONCURRENCY DEFECT` · `NO DOUBLE SPEND OBSERVED`.
Accettato come non-blocker di questa fase e indicato come **candidato naturale del
gate successivo**, dopo il merge. Non corretto qui, come da verdetto.

**Dove.** `RUNTIME_INTEGRATION_GATE_01/runtime/payload_snapshot.py`, `_write_once`.

**Cosa.** Il file viene creato con `O_EXCL` e scritto **subito dopo**. Fra `os.open` e
`os.write` esiste ed e' vuoto. Un secondo processo che riceve `FileExistsError` rilegge
immediatamente un file di 0 byte:

```
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
  payload_snapshot.py:182  in seal()  ->  prev = _read_json(seal_path)
```

La stessa finestra esiste sul file `.bin`, dove si manifesterebbe come
`DIGEST_COLLISION`.

**Quando.** Riprodotto sulla coppia **canonica** `9cf9cee1` + `fea7b439`, alla prima
esecuzione della suite storica, **prima di qualunque modifica**: e' un difetto
preesistente, non una regressione di questa fase. Intermittente (8/8 esecuzioni isolate
di T08 superate; non ripresentatosi nella corsa post-fix).

**Evidenza.** `regression/T08_pre_fix_seal_race.json`,
`regression/r0_r1_RESULTS_pre_fix.json`, `regression/r0_r1_run_gate_pre_fix.log`.

**Perche' non corretto.** E' un difetto di concorrenza del **percorso governato**
(ledger degli snapshot P-B04), non un percorso di spesa legacy. Correggerlo qui sarebbe
stato `SCOPE_EXPANSION_REQUIRED`, e il mandato vieta di aggirare uno STOP. La Human
Review 01 ha confermato la classificazione e ha chiesto esplicitamente di non
correggerlo nel delta correttivo.

**Nota della review, registrata:** il sigillo avviene PRIMA della chiamata a
`run_job` del Core, quindi il fallimento concorrente ferma l'operazione prima della
nuova reservation. E': P-B04 non puo' arrivare al provider reale con una primitive
write-once che ogni tanto scambia una scrittura concorrente per corruzione.

**Gravita'.** Fail-closed: il processo perdente si ferma con un errore e **non**
spende. Nessuna spesa doppia, nessuna autorizzazione concessa per errore. Il danno e'
di disponibilita' sotto concorrenza, non di denaro. La correzione naturale e' scrivere
su un file temporaneo nella stessa directory e poi `os.link`/`os.rename`, mantenendo la
semantica write-once — ma e' una decisione, e va presa fuori da qui.

---

## `all_requirements_verified = false`

Non e' prudenza: e' l'unica risposta vera. Esistono nove requisiti aperti nella roadmap
complessiva. Un PASS di suite non ne chiude nemmeno uno di quelli, e dichiarare il
contrario sarebbe esattamente il tipo di affermazione che questa catena di evidenza
esiste per impedire.
