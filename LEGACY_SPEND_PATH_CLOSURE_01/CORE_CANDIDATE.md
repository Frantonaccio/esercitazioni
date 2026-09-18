# CANDIDATE DEL CORE

| | |
|---|---|
| repo | `Frantonaccio/creative-os` |
| branch | `harden/legacy-spend-core-2026-09-18` |
| **SHA corrente** | `593044556e0097172526883dc0a8887f0369b109` |
| SHA iterazione 2 | `605a8d746fdafbfc33456ec6f26fa942947a43b9` — `HUMAN_REVIEW_HOLD — SAME_ATTEMPT_AUTHORIZATION_REISSUABLE`, ora `STALE_CORE_PIN` |
| SHA iterazione 1 | `44f9ea29cea112dfb30c752e5519498e25044c19` — `HUMAN_REVIEW_HOLD — DISPATCH_AUTHORIZATION_FORGEABLE`, ora `STALE_CORE_PIN` |
| parent della catena | `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` (baseline canonica, `main`) |
| pubblicato | **si** — `git ls-remote` verificato dopo il push |
| stato di review | `CANDIDATE — NOT_MERGE_AUTHORIZED` |

I tre commit sono tutti sul branch, in ordine: `44f9ea29` (primo candidate),
`605a8d74` (delta correttivo HR01), `59304455` (delta correttivo HR02). Nessun amend,
nessun force-push: la storia che la review ha letto resta leggibile riga per riga.

`main` del Core resta **invariato** a `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515`.
Nessun merge, nessun force-push, nessun tag.

## Contenuto del delta

Additivo. Nessuna firma cambiata, nessuna API rimossa, nessun comportamento alterato
per un adapter di laboratorio. Dettaglio in `CORE_PRIMITIVES_CLASSIFICATION.md` e
`CHANGED_FILES.md`.

| file | righe |
|---|---|
| `adapters/base.py` | confine dello spender; nel correttivo: token di conio, registro dei coniati per identita', consumo singolo, guard sugli hook |
| `transport/pipeline.py` | innesti in `run_job`; nel correttivo: `grant_dispatch` riceve lo store |
| `registry/reservations.py` | `reconciliation_sources` opzionale; **HR02:** tabella `dispatch_claims` e `claim_dispatch_authorization`, verifica + claim in una transazione |
| `tests/run_spender_boundary.py` | nuovo — **18 casi, 18/18 PASS** (11 + L/M/N/O di HR01 + P/Q/R di HR02) |

## Come ricostruire il contenuto senza il branch

Due copie del delta viaggiano dentro questo bundle, perche' un bundle che descrive un
Core che non si puo' rileggere non e' evidenza:

| file | cosa |
|---|---|
| `evidence/CORE_DIFF_spender_boundary.patch` | `git diff 9cf9cee1 59304455` — il delta completo |
| `evidence/CORE_DIFF_human_review_01.patch` | `git diff 44f9ea29 605a8d74` — il solo delta correttivo |
| `evidence/CORE_CANDIDATE_0001_spender_boundary.patch` | `git format-patch` del primo commit (autore, data, messaggio) |
| `evidence/CORE_CANDIDATE_0002_human_review_01.patch` | `git format-patch` del delta correttivo HR01 |
| `evidence/CORE_CANDIDATE_0003_human_review_02.patch` | `git format-patch` del delta correttivo HR02 |
| `evidence/CORE_DIFF_human_review_02.patch` | `git diff 605a8d74 59304455` |

```bash
git -C creative-os checkout -b ricostruzione 9cf9cee1a751f7a2ad6c768574ff5aa38d8db515
git -C creative-os am ../evidence/CORE_CANDIDATE_0001_spender_boundary.patch \
                      ../evidence/CORE_CANDIDATE_0002_human_review_01.patch \
                      ../evidence/CORE_CANDIDATE_0003_human_review_02.patch
git -C creative-os rev-parse HEAD^{tree}     # deve dare il tree del candidate corrente
```

Il **tree** coincide; lo **SHA del commit** no, ed e' corretto che sia cosi': il commit
originale e' firmato SSH e porta la propria data di committer, che `git am` non
riproduce. Cio' che va verificato e' il contenuto, e il contenuto e' il tree.

## Verifica del pin

Il Runtime candidate pinna `59304455…`. Contro `9cf9cee1…`, `44f9ea29…` **e**
`605a8d74…` il pin risponde `STALE_CORE_PIN` **prima** dell'import — non un
`AttributeError` a meta' percorso, e non un silenzioso "funziona lo stesso" su un Core
in cui l'autorizzazione era falsificabile o lo stesso tentativo ne autorizzava due.
Vedi `PAIR_COMPATIBILITY.md` ed `evidence/E10_core_pin_and_p2_freeze.json`.

## Cosa NON significa

Che il Core candidate sia approvato, mergiabile o autorizzato. Serve **Human Review
separata**: `merge_authorized = false`, `human_merge_authorization = false`.
