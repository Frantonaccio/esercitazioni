# REALITY LOCK — PROVIDER BOUNDARY GATE / OPEN-GAP CLOSURE (2026-09-17)

Eseguito **prima di qualunque write**, e riverificato a fine fase (C00 before, C08 after).
Evidenza: `evidence/C00_reality_lock.json`, `evidence/C08_p2_freeze_core_pin_after.json`.

## Baseline canonica richiesta

| | richiesto | osservato all'inizio | osservato alla fine |
|---|---|---|---|
| **CORE** `Frantonaccio/creative-os` branch | `main` | `main` | `main` |
| **CORE** SHA | `740ee979300fe20a9382992528604dee70cb2fcf` | **coincide** | **coincide** |
| **CORE** working tree | pulito | pulito (`git status --porcelain --untracked-files=all` vuoto) | pulito |
| **RUNTIME** `Frantonaccio/esercitazioni` `origin/main` | `0698279703ab959625ac4e84ee636bc5b93b45fd` | **coincide** | — |
| **RUNTIME** HEAD | discende dal canonico | `0698279703ab959625ac4e84ee636bc5b93b45fd` (identico) | — |
| **Runtime pin** `REQUIRED_CORE_SHA` | `740ee979300fe20a9382992528604dee70cb2fcf` | **coincide** | **coincide** |
| **P2 frozen** SHA256 `hf_batch.py` | `637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1` | **coincide** | **coincide** |

## Verifiche aggiuntive richieste dal mandato

| verifica | esito |
|---|---|
| working tree puliti | Core: pulito. Runtime: pulito all'apertura della fase. |
| nessun commit locale non pubblicato che cambi la baseline | `git log 0698279..HEAD` → **vuoto**. Il branch di lavoro partiva esattamente da `origin/main`. |
| nessuna deriva fra `main` remoto e gli SHA sopra | `git fetch origin main` → `origin/main == 0698279703ab…`. **Nessuna deriva.** |

**Nota su un ref locale stantio, riferita per completezza**: all'apertura della sessione il ref
locale `refs/heads/main` del Runtime era fermo a `8ded1c4947374a5f…`, un antenato di `origin/main`
(`git merge-base --is-ancestor main origin/main` → vero). È un ref locale non aggiornato del clone,
non una divergenza della baseline: la verifica che conta — `origin/main` contro lo SHA canonico —
coincide. Nessuna correzione automatica è stata applicata a quel ref.

**Esito: nessun `CANONICAL_BASELINE_DRIFT`.**

## Branch di lavoro

| repo | branch | note |
|---|---|---|
| RUNTIME `Frantonaccio/esercitazioni` | `claude/provider-boundary-gate-closure-gd6b3g` | branch designato per questa sessione. Nessuna scrittura su `main`. |
| CORE `Frantonaccio/creative-os` | `harden/provider-boundary-core-atomicity-2026-09-17` | creato **solo** perché NG-05 lo richiede davvero (vedi `NG05_ATOMICITY.md` §1). Vive in un **worktree separato** (`/home/user/creative-os-atomicity`): il tree canonico resta su `main` a `740ee979`, pulito. |

Core branch HEAD: `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515`, base `740ee979300fe20a9382992528604dee70cb2fcf`.

## Nota operativa sul clone del Core

Il Core era stato clonato con `--depth 1`. La suite storica R0-R1 (`tests/run_gate.py`, test T03
"stale old Core pin") crea un worktree allo SHA `9afaddf3cec1e8baf9600ed8dc0461e7adccb5c7`, assente
in un clone shallow. È stato eseguito `git fetch --depth=1 origin 9afaddf3…` per rendere disponibile
quel solo commit. Questo **non** altera `main`, il working tree o il pin: verificato da C08.

## Perimetro

Nessuna delle verifiche sopra significa provider ready, production ready, credenziali autorizzate,
spend autorizzato, merge autorizzato o R2 autorizzato.
