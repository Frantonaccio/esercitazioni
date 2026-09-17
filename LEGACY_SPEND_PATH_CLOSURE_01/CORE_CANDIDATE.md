# CANDIDATE DEL CORE

| | |
|---|---|
| repo | `Frantonaccio/creative-os` |
| branch | `harden/legacy-spend-core-2026-09-18` |
| SHA | `44f9ea29cea112dfb30c752e5519498e25044c19` |
| tree | `f3db85543b982a0b59c1e80af6a661bc6cab9c33` |
| parent | `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` (baseline canonica, `main`) |
| pubblicato | **si** — `git ls-remote` verificato dopo il push |
| stato di review | `CANDIDATE — NOT_MERGE_AUTHORIZED` |

`main` del Core resta **invariato** a `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515`.
Nessun merge, nessun force-push, nessun tag.

## Contenuto del delta

Additivo. Nessuna firma cambiata, nessuna API rimossa, nessun comportamento alterato
per un adapter di laboratorio. Dettaglio in `CORE_PRIMITIVES_CLASSIFICATION.md` e
`CHANGED_FILES.md`.

| file | righe |
|---|---|
| `adapters/base.py` | +326 |
| `transport/pipeline.py` | innesti in `run_job` + `import contextlib` |
| `registry/reservations.py` | `reconciliation_sources` opzionale |
| `tests/run_spender_boundary.py` | nuovo, 11 casi, 11/11 PASS |

## Come ricostruire il contenuto senza il branch

Due copie del delta viaggiano dentro questo bundle, perche' un bundle che descrive un
Core che non si puo' rileggere non e' evidenza:

| file | cosa |
|---|---|
| `evidence/CORE_DIFF_spender_boundary.patch` | `git diff 9cf9cee1 44f9ea29` |
| `evidence/CORE_CANDIDATE_0001_spender_boundary.patch` | `git format-patch -1` (include autore, data e messaggio) |

```bash
git -C creative-os checkout -b ricostruzione 9cf9cee1a751f7a2ad6c768574ff5aa38d8db515
git -C creative-os am ../evidence/CORE_CANDIDATE_0001_spender_boundary.patch
git -C creative-os rev-parse HEAD^{tree}     # deve dare f3db85543b982a0b59c1e80af6a661bc6cab9c33
```

Il **tree** coincide; lo **SHA del commit** no, ed e' corretto che sia cosi': il commit
originale e' firmato SSH e porta la propria data di committer, che `git am` non
riproduce. Cio' che va verificato e' il contenuto, e il contenuto e' il tree.

## Verifica del pin

Il Runtime candidate pinna `44f9ea29…`. Contro il Core `9cf9cee1…` il pin risponde
`STALE_CORE_PIN` **prima** dell'import — non un `AttributeError` a meta' percorso.
Vedi `PAIR_COMPATIBILITY.md` ed `evidence/E10_core_pin_and_p2_freeze.json`.

## Cosa NON significa

Che il Core candidate sia approvato, mergiabile o autorizzato. Serve **Human Review
separata**: `merge_authorized = false`, `human_merge_authorization = false`.
