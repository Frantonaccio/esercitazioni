# REALITY LOCK — COORDINATED CORE + RUNTIME INTEGRATION (NG-05)

Eseguito **prima di qualunque write**, riverificato a fine fase (D00 before, D11 after).
Evidenza: `evidence/D00_reality_lock_approved_inputs.json`,
`evidence/D11_p2_freeze_and_baselines_untouched.json`.

## Gli 8 controlli richiesti

| # | verifica | richiesto | osservato | esito |
|---|---|---|---|---|
| 1 | Core `main` | `740ee979300fe20a9382992528604dee70cb2fcf` | coincide | ✓ |
| 2 | Core candidate branch | `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` su `harden/provider-boundary-core-atomicity-2026-09-17` | coincide | ✓ |
| 3 | Runtime `main` | `0698279703ab959625ac4e84ee636bc5b93b45fd` | coincide | ✓ |
| 4 | Runtime reviewed branch | `4a73cdad18034e7c1bd9842a37e34e0273f9325a` | coincide | ✓ |
| 5 | Core candidate discende dalla baseline Core | — | `merge-base --is-ancestor` vero | ✓ |
| 6 | Runtime reviewed discende dalla baseline Runtime | — | `merge-base --is-ancestor` vero | ✓ |
| 7 | P2 frozen | `637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1` | coincide | ✓ |
| 8 | working tree puliti | Core baseline e Core candidate | entrambi vuoti | ✓ |

Più: il branch di integrazione discende dal reviewed head (`integration_branch_from_reviewed_head`).

**Esito: nessun `APPROVED_INPUT_DRIFT`.**

## Branch di lavoro

| repo | branch | ruolo |
|---|---|---|
| RUNTIME `Frantonaccio/esercitazioni` | **`integrate/provider-boundary-core-runtime-2026-09-17`** | branch dedicato di questa integrazione, creato dal reviewed head `4a73cdad` |
| CORE `Frantonaccio/creative-os` | `harden/provider-boundary-core-atomicity-2026-09-17` | candidate approvato, **nessun nuovo commit** |

Il branch di sessione imposto dal classifier resta
`claude/provider-boundary-gate-closure-gd6b3g` e porta il lavoro già revisionato: non è stato
toccato da questa fase. L'integrazione vive sul branch dedicato richiesto dalla review.

## Layout dei due Core

Il Core candidate vive in un **worktree separato** (`/home/user/creative-os-atomicity`); il tree
canonico (`/home/user/creative-os`) resta su `main` a `740ee979`, pulito. Il runtime importa il
Core da `CREATIVE_OS_CORE_PATH`: puntato al candidate, `CORE_PIN_OK`; puntato alla baseline,
`STALE_CORE_PIN` **prima dell'import**.

## Stato a fine fase (D11)

| | |
|---|---|
| P2 before == after == canonico | ✓ `637f3a80…` |
| Core `main` | ✓ `740ee979…`, working tree pulito |
| Core candidate | ✓ `9cf9cee1…`, **non modificato da questo delta** |
| Runtime `main` | ✓ `0698279…` |
| Bundle approvato `PROVIDER_BOUNDARY_GATE_02` | ✓ non toccato (`git status` vuoto sul percorso) |
| Bundle v3 `PROVIDER_BOUNDARY_HARDENING_01` | ✓ non toccato |
| Tag | ✓ 0 su entrambi i repository |
| Materiale credenziale nel bundle | ✓ nessuno |

Nessuna delle verifiche sopra significa provider reale, production ready, credenziali
autorizzate, spend autorizzato, **merge autorizzato** o R2 autorizzato.
