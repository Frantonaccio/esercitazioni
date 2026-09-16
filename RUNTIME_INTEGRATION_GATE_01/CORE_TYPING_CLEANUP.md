# CORE_TYPING_CLEANUP — `transport.pipeline.run_job`: `JobStore` → `ReservationStore`

## Verifica sul codice canonical (`819e7cf`)

`transport/pipeline.py`:
- riga 17: `from adapters.base import (..., JobState, JobStore, ProviderMismatch, ReservationOutcome)`
- riga 39: `def run_job(adapter: GenerationAdapter, spec: GenSpec, store: JobStore, *, ...)`

`run_job` usa esclusivamente `reserve_or_get_live`, `mark_submitted`, `mark_submit_unknown`,
`put`, `expire`: i cinque metodi del Protocol `ReservationStore` (`adapters/base.py`).
`JobStore` è la classe di riferimento in memoria; l'annotazione sottostima il contratto reale e
nasconde che `SqliteReservationStore` (che NON eredita da `JobStore`) è l'argomento previsto.
**Cleanup confermato.**

## Realizzazione

| voce | valore |
|---|---|
| worktree | `/home/user/creative-os-typing-cleanup` |
| branch | `chore/pipeline-reservationstore-annotation` (base `819e7cf`) |
| commit locale | `6b0eae802733ac15d6ff09d987e5bbdea13fd8d2` |
| diff | 2 righe di import + 1 riga di annotazione; **nessuna modifica comportamentale** (`evidence/CORE_TYPING_CLEANUP_6b0eae8.patch`) |
| stato | **NOT MERGED · NOT PUSHED** (accesso al Core in sola lettura in questa sessione; il merge richiede mandato successivo) |

```diff
-from adapters.base import (GeneratedAsset, GenerationAdapter, GenSpec, Job,
-                             JobState, JobStore, ProviderMismatch, ReservationOutcome)
+from adapters.base import (GeneratedAsset, GenerationAdapter, GenSpec, Job,
+                             JobState, ProviderMismatch, ReservationOutcome,
+                             ReservationStore)
...
-def run_job(adapter: GenerationAdapter, spec: GenSpec, store: JobStore, *,
+def run_job(adapter: GenerationAdapter, spec: GenSpec, store: ReservationStore, *,
```

## Regressioni sul worktree (log in `evidence/CORE_TYPING_CLEANUP_regressions.log`)

| suite | esito |
|---|---|
| `tests/run_reservation.py` | 10/10 · exit 0 |
| `tests/run_block2.py` | 18/18 · exit 0 |
| `tests/run_review_pr2.py` | R1–R4 NOT_CONFIRMED · exit 0 |
| `tests/run_review_pr2_final.py` | R5–R6 NOT_CONFIRMED · exit 0 |
| `tests/run_boot_paths.py` | OK · exit 0 |
| `tests/run_case_collision.py` | 0 collisioni · exit 0 |
| `tests/run_golden.py` | 1 REJECT · 1 PASS · exit 0 |
| `tests/run_contamination.py` (termini del tenant) | exit 0 |

## Indipendenza dal runtime gate

Il runtime candidate e tutta la matrice T01–T19 girano contro il Core canonical `819e7cf`
(`CREATIVE_OS_CORE_PATH=/home/user/creative-os`), **non** contro il worktree del cleanup.
Il gate non pretende un nuovo Core SHA.

## Rollback

`git -C /home/user/creative-os worktree remove /home/user/creative-os-typing-cleanup && git -C /home/user/creative-os branch -D chore/pipeline-reservationstore-annotation`
