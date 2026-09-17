# Voci nuove per `docs/REGISTRO.md` — A20, A21, A22, A23, A24

Aperte il 17 settembre 2026. Ogni voce ha la prova nei transcript delle cinque
chiamate di stamattina (10:33–10:58, ora di Roma), lette per intero su ElevenLabs.
Nessuna di queste voci e' stata implementata: sono aperte, con la causa isolata.

Le cinque chiamate, in ordine:

| # | ora | agente | conversazione | versione |
|---|---|---|---|---|
| 1 | 10:33:59 | Guido | `conv_8701m2q80gqsetetf18pxw4p8hzt` | `agtvrsn_3101m2n9sne9fw59fmg8fwscdqrj` |
| 2 | 10:37:15 | Guido | `conv_9501m2q86hqtfa7tsxq8y3q3wh0r` | `agtvrsn_3101m2n9sne9fw59fmg8fwscdqrj` |
| 3 | 10:38:24 | Dario | `conv_6101m2q88nb2f898e7ds7azqr17g` | `agtvrsn_6001m2mmtqdffr29b04n3b3wcf4a` |
| 4 | 10:39:14 | Dario | `conv_7401m2q8a63ke7qvnjwkaf5ecf27` | `agtvrsn_6001m2mmtqdffr29b04n3b3wcf4a` |
| 5 | 10:58:04 | Dario | `conv_7101m2q9ckmee4ztew5hkm8zm847` | `agtvrsn_6001m2mmtqdffr29b04n3b3wcf4a` |

---

## A20 — Paziente con appuntamento gia' fissato: Dario fa lo stesso il triage

**Stato:** aperta, P1. **Agente:** Dario. **Prova:** chiamata 4.

Il contesto iniettato diceva `appuntamento_esiste: "si"`, codice `671881`,
mercoledi' 30 settembre alle 16:30 presso Farmacia Tommaseo. Dario ha aperto bene
("Vedo che ha un appuntamento…"), poi per cinque minuti ha risposto a domande sul
protocollo e ha chiamato `salva_triage_telefonico` con `lead_id: "671881"` e
`triage_result: "qualified"`. Il paziente ha dovuto ricordarglielo lui:
«Si', lei non mi doveva far un teletriage?», e solo li' Dario ha risposto
«Dato che ha gia' l'appuntamento fissato, non e' necessario ripetere il triage».

**Comportamento voluto:** se il contesto dice che un appuntamento esiste, Dario lo
dice, rimanda al **02 8239 6996** per qualunque cosa riguardi quell'appuntamento,
non fa triage e non risponde a domande sul protocollo.

**Causa isolata, due istruzioni che si contraddicono nel prompt live:**

- REGOLA ZERO, ramo A, caso "Ha gia' un appuntamento = si": «poi FIX P0-14.
  **NON fare il triage se gia' fatto**, NON chiedere il numero.»
- FIX P0-14: «Se il triage **NON e' ancora completo** → "Le faccio solo le ultime
  domande veloci, cosi' il Dottore arriva preparato." e riprendi dalla domanda giusta.»

La prima dice di non farlo, la seconda dice di farlo quando non risulta completo.
Su un lead che non ha mai fatto il triage, la seconda vince. Il modello non sta
sbagliando: sta seguendo P0-14.

**Il numero non c'e' in questo ramo.** `02 8239 6996` compare una volta sola nel
prompt (riga 555), dentro il Caso 1 "Voglio cambiare data / spostare appuntamento".
Chi ha un appuntamento ma non chiede di spostarlo non passa mai da li'.

**Prossima mossa:** un cambio solo, dopo A19. Riscrivere il ramo "appuntamento
esistente" come definizione unica, togliendo da P0-14 la clausola sul triage
incompleto e portando il 6996 dentro quel ramo. Test nuovo prima della sonda.

---

## A21 — Dario spiega il protocollo e dice "ANR90" ad alta voce

**Stato:** aperta, P0 (rischio di claim). **Agente:** Dario. **Prova:** chiamata 4.

Detto dall'agente, verbatim:

- «La valutazione uditiva del **Protocollo ANR90** e' un percorso gratuito di
  rieducazione uditiva condotto dal Dottor Antonaccio.»
- «L'obiettivo principale del Protocollo ANR90 non e' solo farle sentire i suoni,
  ma proprio aiutarla a comprenderli meglio… **E' un lavoro di rieducazione per il
  suo cervello.**»
- «Il fatto che lei senta i rumori ma non riesca a distinguere le parole e'
  **proprio il segnale principale per cui questo protocollo e' indicato**.»

La terza frase e' la piu' grave: "indicato" davanti a un sintomo riferito e' una
indicazione clinica, non una informazione commerciale. La seconda descrive un
meccanismo fisiologico.

**Comportamento voluto:** nessuna spiegazione del protocollo e nessun claim.
Una frase sola, sempre la stessa, sul fatto che si lavora sulla comprensione del
parlato nel rumore; poi rimando al Dottore. Il nome "ANR90" non si pronuncia mai.

**Causa isolata:** il prompt live glielo fa dire in cinque punti diversi
(righe 128, 169, 322, 329, 402), inclusa l'apertura standard e il micro-pitch
«Il Protocollo ANR90 e' un percorso di rieducazione uditiva…». La deflection
generale rimanda al Dottore ma non copre le domande sul protocollo, che la
sezione "Deflection — Domande fuori ambito" non elenca fra quelle fuori ambito.

**Prossima mossa:** non e' un cambio singolo, sono cinque punti piu' la deflection.
Va in Dario 3.0 come requisito, non come patch sulla 2p.

---

## A22 — Guido pronuncia il congedo al primo rifiuto ma non chiude

**Stato:** aperta, P1. **Agente:** Guido. **Prova:** chiamata 2.

Ricostruzione dai tempi del transcript:

| t | chi | che cosa |
|---|---|---|
| 9s | paziente | «No, non voglio parlare con la macchina, lasciatemi stare.» |
| 12s | Guido | «Mi dispiace. Nell'SMS di conferma trova il link per fare tutto con calma. Buona giornata.» — **nessun `end_call`** |
| 24s | Guido | «Mi sente?» (dopo 10,7 secondi di silenzio) |
| 28s | paziente | «Eh, si', si', mi ha detto che non voglio parlare con la macchina.» |
| 31s | Guido | ripete la stessa frase di congedo — **ancora nessun `end_call`** |
| 42s | paziente | «Chiudi la chiamata, chiudila.» |
| 45s | Guido | `end_call`, motivazione: «ha mostrato ostilita'/rifiuto per il secondo turno consecutivo» |

**Il difetto non e' la soglia, e' il tool che non parte.** La sezione OSTILITA' della
3.1.4b copre gia' "ostilita' *o rifiuto* senza richiesta" e dice di chiudere con
`end_call` nello stesso turno. Al primo rifiuto Guido ha detto la frase giusta,
al secondo l'ha ripetuta, e ha chiamato `end_call` solo quando il paziente glielo
ha ordinato. La firma e' la stessa di ND-1 gia' misurata su Dario e su F1b:
il testo pronunciabile viene pronunciato, il tool non viene invocato.

Il paziente e' rimasto in linea 36 secondi in piu' del necessario, dopo aver detto
tre volte di voler chiudere, e si e' pure sentito chiedere «Mi sente?».

**Attenzione — questa voce tocca una decisione gia' presa.** Il 16/9 Francesco ha
deciso su C2 che «il prompt resta com'e', si chiude al secondo turno di ostilita'
dopo una scusa. Un paziente anziano e frustrato non si chiude alla prima parola».
C2 parla di **insulti**; A22 parla di **rifiuto di parlare con un sistema
automatico**, che e' un caso diverso e in cui trattenere il paziente non serve a
nessuno. Prima di scrivere qualunque riga serve la conferma esplicita che la
chiusura al primo rifiuto vale per il rifiuto e non tocca la regola sugli insulti.

**Prossima mossa:** confermata la distinzione, un test che conta i turni fra il
primo rifiuto e `end_call`, baseline sul live, poi un cambio solo.

---

## A23 — `cerca_lead_telefono` chiamato col numero dell'agente

**Stato:** aperta, P0. **Agente:** Dario. **Prova:** chiamata 5.

Primo tool call della chiamata:

```
cerca_lead_telefono({"phone": "+14254090642"})
→ {"found":false,"message":"Nessun lead trovato con questo numero."}
```

`+14254090642` e' il numero ElevenLabs di Dario, cioe' `system__called_number`.
Il chiamante era `+393246685466`. Dario ha quindi detto «non riesco a trovare la
sua richiesta con questo numero. Potrebbe aver usato un numero diverso?» e ha fatto
dettare al paziente il proprio numero — cosa che REGOLA ZERO vieta esplicitamente
a chi e' riconosciuto. Alla seconda chiamata col numero giusto il lead e' stato
trovato subito. Dieci turni e quaranta secondi persi, e un paziente riconosciuto
trattato come sconosciuto.

**Causa isolata, strutturale.** Nella definizione del tool
(`tool_5701khbrb8n6feash7p22aj6qtav`) il parametro `phone` ha
`dynamic_variable: ""`: lo scrive il modello. Il prompt gli dice di usare
`{{system__caller_id}}`, ma nell'intestazione del contesto, dodici righe sopra,
c'e' scritto `{{system__called_number}}`. Il modello ha copiato quello sbagliato.

Il tool gemello non ha questo problema: in `salva_triage_telefonico` il parametro
`phone` e' legato a `dynamic_variable: "system__caller_id"`, quindi il modello non
lo scrive e non puo' sbagliarlo.

**Prossima mossa:** legare `phone` di `cerca_lead_telefono` a `system__caller_id`
come in `salva_triage_telefonico`. **Un vincolo da risolvere prima:** REGOLA ZERO
prevede il caso legittimo «il paziente dice lui di aver usato un altro numero», che
con un parametro legato diventa impossibile. Servono due strade nella stessa
chiamata, per esempio un secondo parametro opzionale `phone_dichiarato` usato solo
in quel caso. Da decidere prima di scrivere, e' un cambio di contratto del tool.

---

## A24 — "Paziente da chiamata" pronunciato come nome proprio

**Stato:** aperta, P1. **Agente:** Dario (il contesto e' condiviso con Guido).
**Prova:** chiamate 3 e 4.

Detto dall'agente, due volte:

> «**Buongiorno Paziente da chiamata**, sono Dario, l'assistente del Dottor
> Antonaccio. Vedo che ha un appuntamento mercoledi' 30 settembre 2026 alle 16:30
> presso Farmacia Tommaseo.»

Il contesto iniettato portava `chiamante_nome: "Paziente da chiamata"`. Nella
chiamata 1 delle 10:33, sullo stesso numero, il valore era `chiamante_nome:
"Prova Cowork"`: due segnaposto diversi, entrambi pronunciabili, entrambi arrivati
fino alla voce.

**Causa isolata, due lati.**

- A monte: `agent-call-context` restituisce come nome il segnaposto scritto sul
  lead. Lo stesso valore torna anche da `cerca_lead_telefono`
  (`"name":"Paziente da chiamata"`), quindi il difetto e' nel dato, non nel webhook.
- Nel prompt: REGOLA ZERO, righe 83-84, «Nel tuo primo turno parlato, se sei
  riconosciuto, **pronunci comunque il nome**: "Buongiorno {{chiamante_nome}}, …"».
  Non c'e' nessuna condizione su che cosa contenga quella variabile.

**Prossima mossa:** la chiusura pulita e' a monte — il contesto non manda un nome
quando sul lead c'e' un segnaposto, e Dario cade sul saluto senza nome, che gia'
esiste. Serve una finestra Lovable e il diff prima: e' fuori dal perimetro di
ElevenLabs. Come rete di sicurezza, in Dario 3.0 il nome si pronuncia solo se
sembra un nome di persona. Nessun cambio sulla 2p.
