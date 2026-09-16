# ARCHITECTURE — percorso candidato `go → Core C26`

## Percorso realizzato

```
hf_batch GO  (candidate: runtime/go_candidate.go)
    │
    ├─ 1. provider_gate.require_fake_mode(provider_mode)     → REAL_PROVIDER_DISABLED se ≠ "fake"
    ├─ 2. core_pin.require_core(core_path)                   → CORE_PIN_MISMATCH / STALE_CORE_PIN /
    │        (A. HEAD == 819e7cf  B. working tree clean)        CORE_WORKTREE_DIRTY
    ├─ 3. import del Core (solo dopo 1 e 2)
    ├─ 3b. provider_gate.require_fake_adapter(adapter, FakeAdapter)
    ├─ 4. genspec_bridge.build_genspec(GoInputs) → adapters.base.GenSpec   (spec_key dal Core)
    ├─ 5. registry.reservations.SqliteReservationStore(state/<test>.db)    (riferimento durevole, solo lab)
    │        avvolto da ReservationObserver (proxy: registra l'esito deciso dal Core, delega tutto)
    ├─ 6. transport.pipeline.run_job(adapter, spec, store, budget_units, envelope_units)
    │        └─ store.reserve_or_get_live  →  RESERVED_NEW → adapter.submit → mark_submitted
    │                                       →  EXISTING_LIVE_JOB → (R2/R6) poll o ritorno
    │        └─ poll → store.put (R5) → terminale / expire → SUBMIT_UNKNOWN
    └─ 7. GoResult: stato PERSISTITO riletto dallo store (mai dallo stato in memoria)
```

## Cosa il runtime importa dal Core (esattamente quattro simboli, verificato da T19)

| simbolo | uso |
|---|---|
| `adapters.base.GenSpec` | struttura della spec e `spec_key` |
| `adapters.fake.FakeAdapter` | unico adapter ammesso (classe o sottoclasse) |
| `registry.reservations.SqliteReservationStore` | implementazione durevole di riferimento di `ReservationStore` |
| `transport.pipeline.run_job` | RESERVE → SUBMIT → POLL → TERMINAL |

## Cosa il runtime NON reimplementa (verificato staticamente da `tests/static_checks.py`)

| proprietà | dove vive | prova che il runtime non la duplica |
|---|---|---|
| reservation atomica | `SqliteReservationStore.reserve_or_get_live` (BEGIN IMMEDIATE + UNIQUE INDEX) | nessun `find_live_by_spec`, nessun `sqlite3`, nessun SQL in `runtime/` |
| idempotenza | `GenSpec.spec_key` + vincolo `one_live_per_spec` | nessun ricalcolo di chiave, nessuna reservation JSON |
| budget atomicity | `reserve_or_get_live(budget_units, envelope_units)` in transazione | nessuna aritmetica `used + budget > envelope` in `runtime/` |
| attempt identity | `job_id = res_<spec>_<attempt>` nel Core | nessuna generazione di job_id nel runtime |
| JobState | `adapters.base.JobState` | nessun Enum, nessuna costante di stato nel runtime |
| SUBMIT_UNKNOWN | `run_job` + `mark_submit_unknown` + `expire` | nessuna chiamata a `mark_*`/`expire` nel runtime |
| provider mismatch | `run_job` (R6) | il runtime non confronta provider |
| durable poll persistence | `run_job → store.put` (R5) | il runtime non chiama `put` |
| find-then-submit | **assente**: `reserve_or_get_live` unica porta | nessun `.submit(` nel runtime; `reserve_or_get_live` del proxy è una delega pura (1 chiamata, 0 `if`) |

## Fail-closed, non convenzione

- `provider_mode` è confrontato con la costante `"fake"`; qualunque altro valore, incluso
  `"higgsfield"`, solleva `RealProviderDisabled("REAL_PROVIDER_DISABLED")` **prima** di ogni
  import del Core, lettura di credenziali, subprocess, socket (T14: `core_imported=False`,
  0 violazioni della sentinella, nessun DB creato).
- L'adapter deve essere `isinstance(adapter, FakeAdapter)` con `name` che inizia per `fake`.
- Nessun fallback: un provider sconosciuto non degrada a fake, si rifiuta.

## Store durevole

`SqliteReservationStore` è usato **solo** come implementazione di riferimento di laboratorio.
File confinati in `RUNTIME_INTEGRATION_GATE_01/state/` (il candidate rifiuta path esterni).
Non è dichiarato storage di produzione.

## Cosa manca per chiudere il percorso (BLOCCATO da P2)

`runtime/hf_batch_runtime.py` — copia del vero `hf_batch.py` con il verbo `go` reindirizzato a
`go_candidate.go`. Senza il file originale non esiste nulla da copiare; il candidate espone
l'unica funzione che la copia dovrà chiamare.
