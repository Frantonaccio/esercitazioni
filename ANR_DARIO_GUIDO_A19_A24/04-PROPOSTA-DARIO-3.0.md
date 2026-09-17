# Dario 3.0 — proposta di riscrittura da zero

Da leggere dopo la tabella di A19. Non e' scritto niente: questa e' la proposta,
serve un "ok" prima di aprire il branch.

## Perche' riscrivere invece di continuare a correggere

La 2p e' 50.068 caratteri. Il tetto che avevi messo era 50.100: A19, che e' un
blocco solo, lo sfonda di 2.700 caratteri. Ogni voce nuova da qui in poi fa la
stessa cosa.

E non e' una questione di spazio. Le cinque chiamate di stamattina mostrano tre
difetti che nascono **da istruzioni che si contraddicono fra loro**, non da
istruzioni mancanti:

- A20: REGOLA ZERO dice "NON fare il triage se gia' fatto", FIX P0-14 dice di
  farlo se non risulta completo. Il modello segue la seconda.
- A19: la sezione Deflection manda al Dottore tutte le domande con parole
  cliniche dentro; un sintomo acuto e' una domanda con parole cliniche dentro.
  Il modello ha fatto quello che c'era scritto.
- A22 su Guido: la regola dice di chiudere con `end_call` nello stesso turno, il
  modello dice la frase e non chiama il tool.

Trentanove blocchi FIX numerati, scritti in sette mesi, ognuno corretto quando e'
stato scritto. Nessun modello tiene insieme trentanove eccezioni. Le contraddizioni
non si tolgono una alla volta: si tolgono riscrivendo.

## I due lavori, e nient'altro

Dario 3.0 fa due cose. Tutto quello che non e' una di queste due si chiude.

**Lavoro 1 — Il triage.** Solo per chi NON ha gia' un appuntamento. Cinque
domande, una per turno, nell'ordine; se la visita e' a domicilio, dopo le domande
l'indirizzo e il CAP; salvataggio; chiusura. E' il lavoro che porta valore.

**Lavoro 2 — Lo smistamento.** Per tutti gli altri, in un turno o due: si dice
dove andare e si chiude. Ha gia' un appuntamento -> 02 8239 6996. Vuole il
Dottore, o non vuole parlare con una macchina -> il Dottore la richiama, chiusura.
Chiede per un'altra persona -> privacy, chiusura. Chiede prezzi, marche,
concorrenti, com'e' fatto il percorso -> una frase sola, poi chiusura o ritorno
alla domanda. Non trovo il lead -> il sito, chiusura.

Quello che oggi c'e' e in 3.0 **non c'e' piu'**: il micro-pitch sul protocollo, il
recupero di chi nega il form con l'offerta "le spiego in 30 secondi", la
spiegazione di che cos'e' il percorso, le risposte sui costi, il cambio di
modalita' fra farmacia e domicilio a meta' chiamata, la gestione degli
spostamenti. Sono tutti lavori di qualcun altro: del sito, di Guido, o tuoi.

## Come entrano A19–A24

| Voce | Come diventa requisito |
|---|---|
| A19 | Blocco unico in testa, prima dei due lavori: interrompe entrambi. E' il testo gia' misurato, si porta cosi' com'e'. |
| A20 | Sparisce come caso: "ha gia' un appuntamento" e' il primo bivio del prompt e manda al Lavoro 2. Il triage non e' raggiungibile da li'. |
| A21 | Il nome del percorso non compare nel testo parlato. Una frase sola, fissa, sulla comprensione del parlato nel rumore, poi il Dottore. Nessuna spiegazione, nessun meccanismo, nessun "indicato". |
| A22 | Non tocca Dario. Resta su Guido come voce separata, con la conferma che serve. |
| A23 | Non e' prompt: e' il parametro `phone` del tool, da legare a `system__caller_id`. Va chiuso prima, altrimenti 3.0 eredita il difetto. |
| A24 | Il nome si pronuncia solo se e' un nome di persona. La chiusura pulita resta a monte, nel contesto. |

## Il conto dei caratteri

| Parte | Caratteri |
|---|---|
| Contesto e regole sui fatti | 1.400 |
| A19, bandiera rossa | 2.000 |
| Identita', tono, una domanda per turno | 700 |
| Bivio iniziale e Lavoro 2, smistamento | 2.200 |
| Lavoro 1, triage in farmacia e a domicilio | 2.600 |
| Chiusura, salvataggio, silenzio | 900 |
| **Totale** | **9.800** |

Sotto i 10.000. Il taglio viene dal togliere, non dall'abbreviare: spariscono
trentanove intestazioni FIX, la cronologia delle patch in testa (2.900 caratteri
di sola storia), i doppioni fra REGOLA ZERO e i FIX, e i tre lavori che passano ad
altri.

## Come si misura

Riscrivere da zero **non si misura con un gate**: non c'e' un cambio singolo da
isolare, e il criterio "totale >= live" non dice niente su un prompt diverso.

La strada onesta e' in tre passi:

1. La suite dei test di Dario che gia' esiste diventa il contratto: 3.0 deve
   passare quello che passa la 2p. Prima si misura la 2p su tutta la suite a 15
   run per test, e quella tabella diventa il riferimento.
2. Test nuovi per A19, A20, A21, e per i due lavori. Un test per comportamento.
3. 3.0 misurata sugli stessi test, stessi run. Si mergia solo se non perde niente
   e vince dove deve vincere.

Costa circa 1.400 run, cioe' 1.200.000 crediti, il doppio di tutto quello che
abbiamo speso il 16/9. Sei al 41% del tetto di 6.500.000: ci sta, ma va deciso
sapendolo.

## Quello che mi serve da te prima di scrivere una riga

1. I due lavori sono questi due, o il secondo lo vedi diverso?
2. Il perimetro che esce da Dario (prezzi, spiegazione del percorso, recupero di
   chi nega il form) va davvero via, o qualcosa resta?
3. La spesa di misura va bene?
