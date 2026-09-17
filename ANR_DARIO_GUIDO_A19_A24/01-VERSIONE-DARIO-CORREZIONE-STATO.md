# Dario: su quale versione gira davvero, e perche' non e' quella scritta in STATO

Verificato il 17 settembre 2026 leggendo ElevenLabs, non la documentazione.

## Il fatto

| | Valore |
|---|---|
| Versione live di Dario | `agtvrsn_6001m2mmtqdffr29b04n3b3wcf4a` |
| Scritta in `STATO-2026-09-17.md` come live | `agtvrsn_3001m2keg1she5grhkv2qxvbwwyx` (v2.11.2p) |
| Scritta in `STATO-2026-09-15-A7a.md` come "versione mergiata" | `agtvrsn_4801m2ke81wpfcw8t70masm74fvt` |

Le tre sigle sono tutte reali e tutte dello stesso agente. Due sono vecchie di un giorno.

Confermato anche dalle chiamate: le tre conversazioni di Dario di stamattina
(`conv_7101m2q9ckmee4ztew5hkm8zm847`, `conv_7401m2q8a63ke7qvnjwkaf5ecf27`,
`conv_6101m2q88nb2f898e7ds7azqr17g`) riportano tutte
`version_id: agtvrsn_6001m2mmtqdffr29b04n3b3wcf4a`.

## Perche'

Il branch principale di Dario (`agtbrch_2401khbptw8kf4h8ad0yb5x3esgz`) ha questa catena:

| seq | versione | quando (ora di Roma) | che cosa e' |
|---|---|---|---|
| 59 | `agtvrsn_4501m21nr3c1eb8ssphrv9be83ce` | 9/9 | v2.11.2m, il rollback |
| 60 | `agtvrsn_3001m2keg1she5grhkv2qxvbwwyx` | 15/9 23:10 | merge del branch `v2.11.2o-A7`, cioe' la 2p |
| 61 | `agtvrsn_8701m2mgq52re0tts69nvq8aw778` | 16/9 09:08 | "New version of your agent." |
| 62 | `agtvrsn_6001m2mmtqdffr29b04n3b3wcf4a` | **16/9 10:20** | **live adesso** |

`agtvrsn_4801m2ke81wpfcw8t70masm74fvt` e' la seq 13 del branch `v2.11.2o-A7`,
cioe' la versione **da cui** e' stato fatto il merge. La seq 60 e' la versione
**nata dal** merge. L'addendum del 15/9 ha annotato la prima, STATO la seconda:
nessuna delle due e' sbagliata, sono due lati dello stesso merge. Solo che il 16/9
ne sono arrivate altre due sopra.

Le due versioni in piu' non sono un merge e non toccano il prompt. Sono i due
salvataggi di A3, la rotazione del secret, fatti via API: ogni scrittura
sull'agente crea una nuova versione, anche quando cambia un solo header.
Diff campo per campo:

- seq 60 -> seq 61: `platform_settings.workspace_overrides.conversation_initiation_client_data_webhook.request_headers["x-agent-secret"]`
  passa dal valore in chiaro `01a88ce5…` al riferimento a secret `EOyZ5ERs9FfReqZwvy7p`.
  E' il punto 6 di A3, "adesso nessun valore sta scritto in chiaro nella configurazione".
- seq 61 -> seq 62: lo stesso header passa da `EOyZ5ERs9FfReqZwvy7p` a
  `U2rqmO9kJKwIRPz1TI5F`, cioe' `agent-secret-2026-09`. E' A3 chiusa "alle 10:20 del 16/9",
  come scrive STATO stesso. L'orario della versione e' 10:20:14.

Nessun'altra differenza. Il prompt e' **identico byte a byte** nelle tre versioni:
50.068 caratteri, sha256 `c187e77d2926bffeaf8f61dd34dafaf565e95f61d94c01b1000505435eaeaaae`.

## Quindi

**Dario sta eseguendo il prompt 2p.** Il comportamento in produzione e' quello
approvato il 15/9. Quello che e' sbagliato in STATO non e' il prompt: e' il
puntatore di versione, rimasto indietro di due scritture perche' A3 e' stata
annotata come lavoro sui secret e non come nuova versione dell'agente.

La causa e' strutturale, non una svista: su ElevenLabs "versione dell'agente" e
"versione del prompt" non sono la stessa cosa, e STATO le tratta come se lo fossero.

## Correzione da fare in STATO

Nella tabella "In produzione", riga "Versione live", colonna Dario, sostituire:

> **v2.11.2p** `agtvrsn_3001m2keg1she5grhkv2qxvbwwyx` (merge `v2.11.2o-A7`, 15/9)

con:

> **v2.11.2p** — prompt `c187e77d…`, 50.068 char. Versione agente live:
> `agtvrsn_6001m2mmtqdffr29b04n3b3wcf4a` (16/9 10:20, A3: secret del webhook di
> contesto). Merge della 2p: `agtvrsn_3001m2keg1she5grhkv2qxvbwwyx` (15/9 23:10),
> dal branch `v2.11.2o-A7` versione `agtvrsn_4801m2ke81wpfcw8t70masm74fvt`.

## Due cose trovate mentre verificavo

**Il rollback di Dario scritto in STATO riaprirebbe A3.** La riga dice
v2.11.2m `agtvrsn_4501m21nr3c1eb8ssphrv9be83ce`. Quella versione ha ancora
l'`x-agent-secret` del webhook di contesto **in chiaro** (`01a88ce5…`).
Ripristinarla rimetterebbe un secret in chiaro nella configurazione e annullerebbe
il punto 6 di A3. Se serve un rollback di prompt alla 2m, va fatto ricreando la 2m
sopra la configurazione attuale, non ripuntando a quella versione.

**Il rollback di Guido e' etichettato male ma punta al posto giusto.** STATO dice
v3.1.2d `agtvrsn_3701m2mmtwaee0h9j6tqmzvhzyrq`. Quella sigla e' la seq 50 del
branch di Guido, creata il 16/9 alle 10:20:19, cioe' la 3.1.2d **dopo** la
rotazione del secret. La 3.1.2d "pura" e' `agtvrsn_3201m1rayv0ze6xrqr9bhe0zynzn`
e porta ancora il secret vecchio, che il 16/9 alle 15:05 e' stato cancellato:
ripristinare quella romperebbe i tool. Il puntatore va tenuto com'e', cambiando
solo l'etichetta in "v3.1.2d + secret 2026-09".

Regola che ne esce, da mettere in `CLAUDE.md`: **il puntatore di versione si
rilegge da ElevenLabs ogni volta che si apre una sessione**, e ogni lavoro che
scrive sull'agente, anche solo su un header, aggiorna quella riga di STATO.
