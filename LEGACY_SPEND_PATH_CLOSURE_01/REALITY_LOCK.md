# REALITY LOCK

Eseguito **prima di qualunque write**, riverificato a fine fase.
Evidenza: `evidence/E00_reality_lock.json`, `evidence/E10_core_pin_and_p2_freeze.json`,
`evidence/E11_evidence_chain_integrity.json`.

## I controlli richiesti dal mandato

| # | verifica | richiesto | osservato | esito |
|---|---|---|---|---|
| 1 | CORE `main` remoto | `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` | coincide | ✓ |
| 2 | RUNTIME `main` remoto | `fea7b439a63a0100a732e21af4dfde6b8edd0951` | coincide | ✓ |
| 3 | Runtime pin `REQUIRED_CORE_SHA` all'ingresso | `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` | coincide | ✓ |
| 4 | P2 congelato | `637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1` | coincide (before == after) | ✓ |
| 5 | working tree CORE pulito | vuoto | vuoto | ✓ |
| 6 | working tree RUNTIME pulito | vuoto fuori da questo bundle | vuoto fuori da questo bundle | ✓ |
| 7 | nessun commit locale non pubblicato che cambi la baseline | — | i branch candidate **discendono** dai due `main` (`merge-base --is-ancestor`) | ✓ |
| 8 | tag | 0 su entrambi | 0 su entrambi | ✓ |

**Esito: nessun `CANONICAL_BASELINE_DRIFT`.**

## Un chiarimento che vale la pena mettere per iscritto

La baseline canonica e' cio' che i due `main` **remoti** portano. Il lavoro di questa
fase vive su branch dedicati che ne discendono, e li' il pin del Runtime si sposta sul
Core candidate: questo **non** e' drift della baseline, e' il modo in cui una coppia
Core+Runtime si muove insieme. La verifica che conta e' `merge-base --is-ancestor`, ed
e' registrata in `E00`.

## Branch reali

| repo | branch richiesto dal mandato | branch REALE | motivo |
|---|---|---|---|
| CORE `Frantonaccio/creative-os` | `harden/legacy-spend-core-2026-09-18` | **`harden/legacy-spend-core-2026-09-18`** | coincide |
| RUNTIME `Frantonaccio/esercitazioni` | `harden/legacy-spend-runtime-2026-09-18` | **`claude/legacy-spend-path-closure-c50coy`** | il classifier della sessione impone questo nome e vieta di pubblicare su un branch diverso. Riportato come richiesto da §15 del mandato. |

Nessuna scrittura su `main`. Nessun merge, force-push, rebase, squash, amend, tag,
release o deploy.

## Autorita' dello stato corrente

Ordine applicato, come da handoff:

1. Git remoto verificato;
2. handoff post-merge corrente;
3. evidenza di questa fase;
4. evidenza storica **solo** per il momento che documenta.

Il `READINESS.json` storico con `merge_authorized=false` e
`human_merge_authorization=false` non e' stato letto come stato corrente e **non e'
stato modificato**. I bundle `PROVIDER_BOUNDARY_HARDENING_01`,
`PROVIDER_BOUNDARY_GATE_02` e `CORE_RUNTIME_INTEGRATION_01` risultano intatti a fine
fase (`E11`).
