# CONTROLLED MERGE POST R0-R1 — MERGE REPORT (2026-09-17)

Autorizzazione: HUMAN_REVIEW_APPROVED — CONTROLLED_PROMOTION CORE+RUNTIME.
Metodo: fast-forward puro (`git merge --ff-only`). Nessun merge commit, nessun rebase, nessuno squash,
nessun force-push, nessun file modificato. Il branch canonico punta ESATTAMENTE alla SHA approvata.

## Reality lock pre-merge — PASS

| voce | atteso | osservato |
|---|---|---|
| Core promotion HEAD (`promote/r0-r1-hardening-2026-09-16`, repo `Frantonaccio/creative-os`) | `740ee979300fe20a9382992528604dee70cb2fcf` | uguale (locale e `git ls-remote`) |
| Runtime promotion HEAD (`promote/r0-r1-runtime-2026-09-16`, repo `Frantonaccio/esercitazioni`) | `39c82968fbfb3f3b7ba9fcfe9dc317ea0da9e74e` | uguale (locale e `git ls-remote`) |
| Runtime pin `runtime/core_pin.py::REQUIRED_CORE_SHA` a 39c82968 | `740ee979…` | uguale |
| working tree Core / Runtime | puliti | 0 righe `git status --porcelain` |
| commit nuovi sui promotion branch dopo la Human Review | nessuno | HEAD == SHA approvata in entrambi |
| relazione con il canonico | — | Core: `main` 819e7cf è padre diretto di 740ee979; Runtime: `main` 8ded1c4 è antenato di 39c82968 (8 commit). Entrambi fast-forward, conflitti impossibili |

## Merge 1 — CORE (`Frantonaccio/creative-os`, canonico `main`) — ESEGUITO E PUBBLICATO

- pre-merge `main`: `819e7cfedb0f6641dc797e7993bec79462ac8df6`
- post-merge `main`: `740ee979300fe20a9382992528604dee70cb2fcf` (fast-forward, push `819e7cf..740ee97 main -> main`)
- merge commit: nessuno (non applicabile)
- ancestry: `git merge-base --is-ancestor 740ee979 origin/main` → OK; `740ee979^` == `819e7cf`
- tree di `main` byte-identico al tree della promotion
- changed files (819e7cf..740ee979, 7 file, +2772/-118):
  `M adapters/base.py`, `M adapters/fake.py`, `M registry/reservations.py`, `M tests/run_block2.py`,
  `A tests/run_r0_r1_hardening.py`, `M tests/run_reservation.py`, `M transport/pipeline.py`
- nessun file `.github`, `.env`, credenziali o segreti

## Merge 2 — RUNTIME (`Frantonaccio/esercitazioni`, canonico `main`) — ESEGUITO E PUBBLICATO

- pre-merge `main`: `8ded1c4947374a5fd2f925b8d27e91de51e7bbb9`
- post-merge `main`: `39c82968fbfb3f3b7ba9fcfe9dc317ea0da9e74e` (fast-forward, push `8ded1c4..39c8296 -> main`).
  Il primo tentativo di push era stato negato dal permission classifier della sessione; il push è riuscito dopo
  la ri-autorizzazione esplicita nel mandato CONTROLLED MERGE HANDOFF del 17/09/2026.
- merge commit: nessuno (non applicabile)
- ancestry: `git merge-base --is-ancestor 39c82968 origin/main` → OK; tree di `main` byte-identico alla promotion
- changed files (8ded1c4..39c82968, 124 file, +17558/-0): tutti sotto `RUNTIME_INTEGRATION_GATE_01/`
  (11 doc, 44 evidence, 37 p2_handoff, 8 runtime, 16 state, 8 tests). Nessun file fuori dalla directory del gate.

## Verifiche post-merge

| # | verifica | esito |
|---|---|---|
| 1 | Core canonico contiene 740ee979 | PASS (HEAD == 740ee979, remoto) |
| 2 | Runtime canonico contiene 39c82968 | PASS (HEAD == 39c82968, remoto) |
| 3 | Runtime pinna esattamente 740ee979 | PASS (`REQUIRED_CORE_SHA = "740ee979300fe20a9382992528604dee70cb2fcf"`) |
| 4 | nessun file inatteso nei merge | PASS (elenchi sopra; fast-forward = tree della promotion) |
| 5 | P2 invariato | PASS: `sha256(P2_RUNTIME/hf_batch.py)` = `637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1`, idem `LAB/hf_batch_ORIGINAL.py` |
| 6 | nessun provider reale abilitato | PASS (`provider_gate.ALLOWED_PROVIDER_MODE = "fake"`, lista REAL_PROVIDER_NAMES rifiutata) |
| 7 | nessuna credenziale aggiunta | PASS (scan `api_key/secret/token/HIGGSFIELD_API` sui tree: solo riferimenti documentali/test) |
| 8 | nessun deploy | PASS (nessuna azione di deploy eseguita) |
| 9 | gap esplicitamente aperti | confermati, elenco sotto |

## GitHub status checks

- `creative-os`: 0 workflow GitHub Actions, 0 check run, `main` non protetto. PR #2 (C26) merged il 2026-09-16; PR #1 aperta e non pertinente.
- `esercitazioni`: 0 workflow GitHub Actions, 0 check run, `main` non protetto, 0 PR.
- CI indipendente: ASSENTE in entrambi i repo (gap confermato).

## Osservazione (non bloccante, nessuna azione intrapresa)

`RUNTIME_INTEGRATION_GATE_01/SHA256SUMS` è il manifest del gate 01 (commit 823a268, 0 mismatch).
I 4 commit di promotion (a767513..39c82968) hanno rigenerato `TEST_RESULTS.md`, `evidence/*.json`,
`runtime/*.py`, `tests/*.py` senza aggiornare quel manifest: a 39c82968 risultano 30 file non combacianti.
Stato identico sulla promotion approvata: NON è effetto del merge. L'evidence bundle v4 verificato in
Human Review è un artefatto separato. Da trattare, se voluto, con mandato separato.

## Freeze

- Core: `main` == 740ee979, baseline canonica post-promotion. Nessun tag creato (fuori dal perimetro "esclusivamente il merge").
- Runtime: `main` == 39c82968, baseline canonica post-promotion. Nessun tag creato (tag esplicitamente non autorizzati).

## Gap ancora aperti (invariati)

P-B01 BLOCKED_ENVIRONMENT · P-B02 STILL_OPEN · P-B03 STILL_OPEN (design requirement) · P-B04 STILL_OPEN ·
G-N02 STILL_OPEN · RV07 STILL_OPEN · orphan lease STILL_OPEN · legacy spend paths · run_contamination NOT_RUN ·
authorization/pricing reali non verificati · CI indipendente assente · T29 BLOCKED_ENVIRONMENT.

## Evidence bundle v4

`R0_R1_CONTROLLED_PROMOTION_EVIDENCE(4).zip`: SHA256 esterno `38e9d7bb4bbe79a7ef0e20e025af7aad3811235be1ce829ad293bb98ec31cf8d` verificato;
SHA256SUMS interno 0 mismatch; `PROMOTION_PAIR.json` = (740ee979, 39c82968); `core_tree_hash` `c5323e86…` == tree di `creative-os/main`.

## Stato

R0_R1_CONTROLLED_PROMOTION_MERGED — BASELINE_CANONICAL (Core + Runtime).
Runtime: R0_R1_CONTROLLED_PROMOTION_MERGED — BASELINE_CANONICAL.
Non significa: production ready · provider ready · P-B01 verified · R2 authorized.
