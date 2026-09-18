# COMPATIBILITA' DELLA COPPIA CORE + RUNTIME

## Gli SHA

| | repo | branch | SHA |
|---|---|---|---|
| base canonica CORE | `Frantonaccio/creative-os` | `main` | `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` |
| base canonica RUNTIME | `Frantonaccio/esercitazioni` | `main` | `fea7b439a63a0100a732e21af4dfde6b8edd0951` |
| **candidate CORE** | `Frantonaccio/creative-os` | `harden/legacy-spend-core-2026-09-18` | `593044556e0097172526883dc0a8887f0369b109` |
| candidate CORE, iterazione 2 (revisionata) | idem | idem | `605a8d746fdafbfc33456ec6f26fa942947a43b9` — ora `STALE_CORE_PIN` |
| candidate CORE, iterazione 1 (revisionata) | idem | idem | `44f9ea29cea112dfb30c752e5519498e25044c19` — ora `STALE_CORE_PIN` |
| **candidate RUNTIME (code sha)** | `Frantonaccio/esercitazioni` | `claude/legacy-spend-path-closure-c50coy` | `b2dd6db8af4e31e704b88cdc6c3e5b1fea28ee7f` |
| candidate RUNTIME, iterazioni precedenti | idem | idem | `ad2f9c072b2a…`, `434e0ea58d85…` |
| **candidate RUNTIME (evidence head)** | idem | idem | il commit che pubblica questo bundle — distinto dal code sha per costruzione |

Entrambi i candidate **discendono** dalla rispettiva base canonica
(`merge-base --is-ancestor`, verificato in `E00`).

## Perche' vanno insieme, e non separatamente

Il Runtime candidate **pretende** un'invariante che solo il Core candidate porta.

`runtime/provider_gate.require_legacy_lab_spend_path(adapter)` rifiuta un adapter
`spend_capable` — ma "spend_capable" e' una **dichiarazione**. Da sola, una
dichiarazione la si aggira: basta non dichiararla. Cio' che rende il rifiuto una
garanzia e' che, dietro, il **Core** impone lo stesso confine a prescindere da cosa il
Runtime abbia visto (`E05`, tentativo "wrapper che nasconde la capability": rifiutato
dal Core con `SPEND_AUTHORIZATION_REQUIRED`, non dal Runtime).

Quindi:

| combinazione | esito |
|---|---|
| Runtime candidate + Core candidate | **compatibile**: la garanzia esiste da entrambi i lati |
| Runtime candidate + Core `9cf9cee1` | **rifiutato dal pin**, `STALE_CORE_PIN`, prima dell'import. Non e' un errore a meta' percorso: e' un rifiuto con un codice che dice perche' |
| Runtime candidate + Core `44f9ea29` | **rifiutato dal pin**, `STALE_CORE_PIN`. Quel Core ha il confine, ma l'autorizzazione che lo apriva era costruibile dal chiamante: un runtime che promette il contrario non puo' girarci sopra |
| Runtime candidate + Core `605a8d74` | **rifiutato dal pin**, `STALE_CORE_PIN`. Li' l'autorizzazione non era falsificabile, ma lo STESSO tentativo poteva coniarne due e dispacciare due volte |
| Runtime `fea7b439` + Core candidate | tecnicamente eseguibile, ma il pin del Runtime storico chiede `9cf9cee1` e quindi rifiuta con `CORE_PIN_MISMATCH`. Anche se lo si forzasse, il Runtime storico non conosce `LEGACY_LAB_NOT_PROVIDER_CAPABLE`: la meta' Runtime della garanzia mancherebbe |

Per questo il pin si e' spostato su `59304455`, e `9cf9cee1`, `44f9ea29` e
`605a8d74` sono tutti in `KNOWN_STALE_CORE_SHAS`: un Core a quello SHA non e' sconosciuto, e' **vecchio**, e va
rifiutato con un esito che lo dica. E' lo stesso criterio applicato quando il pin si
sposto' da `740ee979` a `9cf9cee1`.

## Verifica eseguita

| controllo | evidenza | esito |
|---|---|---|
| `REQUIRED_CORE_SHA` == Core HEAD | `E10` | ✓ |
| `9cf9cee1` → `STALE_CORE_PIN` | `E10` | ✓ |
| `44f9ea29` → `STALE_CORE_PIN` | `E10` | ✓ |
| `605a8d74` → `STALE_CORE_PIN` | `E10` | ✓ |
| SHA sconosciuto → `CORE_PIN_MISMATCH` | `E10` | ✓ |
| tree sporco sullo SHA giusto → `CORE_WORKTREE_DIRTY` | `E10` | ✓ |
| T01/T02/T03/T17/T20 della suite storica (pin, stale, dirty, canonical) | `E08` | ✓ |
| suite del Core sul candidate | `E09` | 9/9 + **18/18** del confine |
| R0-R1 del Runtime sulla coppia | `E08` | 36/37, T29 blocked per policy |

## Nessuna delle righe sopra significa

provider reale verificato, credenziali autorizzate, spend autorizzato, production
ready, **merge autorizzato** o R2 autorizzato.
