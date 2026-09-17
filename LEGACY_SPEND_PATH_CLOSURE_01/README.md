# LEGACY SPEND PATH CLOSURE + LEGACY TEST MIGRATION

**18/09/2026** · MOCK ONLY · ZERO PROVIDER REALI · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUZIONE

Fase successiva a `PROVIDER_BOUNDARY_CORE_RUNTIME_PAIR_MERGED — LAB_CANONICAL_WITH_OPEN_GAPS`.
Chiude i due gap non-provider dichiarati aperti dal handoff:

| requisito | prima | dopo |
|---|---|---|
| `LEGACY_SPEND_PATHS_CORE_PRIMITIVES` | `CORE_CHANGE_REQUIRED` | vedi `READINESS.json` |
| `LEGACY_TESTS_MIGRATION_TO_GOVERNED` | `STILL_OPEN` | vedi `READINESS.json` |

## Il bersaglio

Non era **eliminare la parola legacy**. Era:

> un futuro provider/spender reale deve essere raggiungibile **esclusivamente**
> attraverso il percorso governato.

Prima di questa fase **sei** percorsi raggiungevano uno spender fuori dal percorso
governato, e lo raggiungevano davvero: `evidence/E02_pre_fix_reproduction.json` li
riproduce sulla coppia canonica `9cf9cee1` + `fea7b439`, con una SENTINELLA al posto
del provider che conta gli attraversamenti.

Dopo, uno solo lo raggiunge, e passa da operazione, intento, quote fidata, envelope,
permesso, ledger, snapshot exact-byte, pin del Core e ownership.

## Come leggere questo bundle

| file | cosa contiene |
|---|---|
| `REALITY_LOCK.md` | gli otto controlli eseguiti **prima** di qualunque write |
| `SPEND_PATH_INVENTORY.md` | la matrice completa degli entry point (§5 del mandato) |
| `CORE_PRIMITIVES_CLASSIFICATION.md` | perche' ogni primitive del Core e' stata toccata o lasciata stare |
| `LEGACY_TEST_MIGRATION_MATRIX.md` | i 20 test storici, uno per uno, e dove vive ora cio' che verificavano |
| `PROVIDER_BOUNDARY_COUNTERPROOFS.md` | la sentinella: 0 attraversamenti nei percorsi legacy, 1 nel governato |
| `REGRESSION_MATRIX.md` | tutto cio' che e' stato rieseguito, e cosa ha detto |
| `PAIR_COMPATIBILITY.md` | perche' Core e Runtime candidate vanno insieme e non separatamente |
| `OPEN_REQUIREMENTS.md` | cio' che resta aperto, incluso un difetto **preesistente** scoperto qui |
| `TEST_RESULTS.md` | E00–E12 con EXPECTED / ACTUAL / EVIDENCE |
| `READINESS.json` | esito della suite e readiness del requisito, **separati** |
| `CHANGED_FILES.md` | ogni file toccato, con il perche' |
| `evidence/` | evidenza macchina di ogni passo, piu' i due diff (Core e Runtime) |
| `regression/` | R0-R1 pre-fix e post-fix, log inclusi |

## Come si riesegue

```bash
CREATIVE_OS_CORE_PATH=/home/user/creative-os \
PYTHONDONTWRITEBYTECODE=1 \
python3 LEGACY_SPEND_PATH_CLOSURE_01/lspc1/run_gate_e.py
```

Il gate ripristina l'albero del bundle storico `RUNTIME_INTEGRATION_GATE_01` prima e
dopo l'esecuzione: rieseguire la suite R0-R1 ne riscrive per costruzione l'evidenza,
e quella riscrittura non deve entrare qui dentro.

## Cosa questo bundle NON dichiara

Nessuno degli esiti qui dentro significa provider ready, production ready, NG-04
decisa, orphan lease decisa, provider reale verificato, credenziali autorizzate,
spend autorizzato, merge autorizzato o R2 autorizzato.

Serve **Human Review separata**.
