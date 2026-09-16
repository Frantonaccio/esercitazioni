# Protocollo operativo candidato

## Scopo e autorità

Versione 0.1.0, 16 settembre 2026. Destinazione: progetto Creative OS su Claude Code,
non libreria personale Perplexity. Pacchetto da revisionare prima dell'installazione.
Non sostituisce Core, tenant, registro asset o `hf_batch.py`.

La skill è l'interfaccia linguistica. I controlli devono stare nel percorso di
esecuzione. I test misurano il comportamento di quel percorso, non l'obbedienza
generale di un modello. Nessuna installazione, spesa di generazione, invio a Drive,
pubblicazione, modifica P2 o commit è implicita nell'uso del pacchetto.

## Fonti e ownership

| Oggetto | Fonte autorevole | Divieto |
|---|---|---|
| Procedura, schema, enforcement | Core, versione esplicita | Duplicarla nella skill |
| Brand, claim, cast, policy | Tenant attivo | Travasare decisioni da altri tenant |
| Job e tentativi | Registry operativo esistente | Usare la chat come stato |
| Media e reference | Asset store e hash dei byte | Usare un nome file come identità |
| Risultati commerciali | CRM e misurazione esistenti | Inferire conversioni dalla bellezza |
| Timing overlay | `text_layers.json` se canonico nel job | Copiarlo da tabelle narrative |
| Approvazione umana | Evento autenticato con scope | Auto-approvarsi con un booleano |

Nel mock, SQLite è un journal temporaneo, le autorizzazioni e gli identificativi
sono fixture. Non è proposto come nuovo registry di produzione.

## Contratto della skill completa

### Ingresso

Task autorizzato con tenant e job espliciti; scopo (audit, mock, preproduzione,
produzione approvata, ripresa); limiti; identificatore della decisione umana;
radici dei repository. Se manca un dato risolvibile dai file, cercalo nelle fonti
canoniche. Se mancante o contraddittorio, restituisci `BLOCKED`, senza inventarlo.

### Boot e Context Pack

1. Risolvi i percorsi reali, branch, commit, stato dirty e policy attiva.
2. Apri documenti Core, config e documenti tenant richiesti dal boot esistente.
3. Risolvi brief, cast, claim e vincoli di scena approvati per il job.
4. Registra file letti, SHA256, provenienza e questioni irrisolte.
5. Costruisci un manifest serializzabile, identico dopo riavvio.
6. Congela il contesto esatto autorizzato. Una working tree non riproducibile
   resta candidata: non dichiararla un runtime canonico.

Completion: Boot Report + Context Pack con hash coerenti e scope esplicito.
Un Boot Report è una traccia di caricamento, non prova di comprensione del modello.

### Quote e lock

Il lock deve legare tenant, job, versione del controllo, input, modello,
parametri, riferimento all'autorizzazione, quote, scadenze e budget.
La quote deve riguardare esattamente la richiesta congelata. Una variazione
richiede invalidazione e nuovo passaggio autorizzato, non un aggiornamento silenzioso.
Nel deployment, budget totale e prenotazioni concorrenti richiedono contabilità
atomica. Il mock verifica soltanto il limite del singolo job.

### Submit e riconciliazione

Persisti la prenotazione prima della chiamata. Ricontrolla gli input immediatamente
prima del submit e invia gli stessi byte verificati, non percorsi mutabili riletti.
Riconcilia lo stato con API autenticata: webhook o schermata sono segnali.
Su timeout del submit, conserva `SUBMIT_UNKNOWN`; su polling non conclusivo
conserva `RECONCILE_REQUIRED`. Nessuno dei due autorizza un retry di generazione.

Il mock riutilizza `FakeAdapter` e `GenSpec` del Core. Il suo risultato è un payload
testuale sintetico: il MIME dichiarato dal FakeAdapter non lo trasforma in immagine.
Il mock non implementa un servizio esterno di riconciliazione dopo crash:
dimostra persistenza dell'incertezza e blocco del doppio submit.

### Assembly e QA

Le fasi reali restano fuori dall'eseguibile v0.1:
- assembly dai manifest, con hash degli input e versione del renderer;
- verifica dei tempi da `text_layers.json` e dell'export, non da una tabella VO;
- controllo tecnico del media decodificato;
- review percettiva per scena con frame/timestamp, vincolo e osservazione;
- review strategica su funzione narrativa, claim e chiarezza;
- Human Gate sul medesimo hash di export valutato.

Schema minimo QA proposto:

```json
{
  "job_id": "JOB",
  "asset_sha256": "HASH_EXPORT",
  "reviewer_id": "IDENTITA_REVIEWER",
  "scope": "VISUAL_REVIEW",
  "findings": [
    {
      "scene_id": "B5",
      "constraint_id": "OWNER_ACTIVE_CHOICE",
      "result": "NOT_VERIFIED",
      "timestamp_ms": null,
      "evidence_asset_sha256": null,
      "observation": "Export non ancora disponibile"
    }
  ]
}
```

Un PASS richiede evidenza pertinente; una riga di JSON ben formata non prova la
correttezza dell'osservazione. Chi sviluppa il guard non certifica da solo
l'indipendenza della review. Nessun test mock rilascia il video.

### Learning e ripresa

Salva eventi con asset/run, versione delle regole, errore osservato, rimedio testato
e decisione. Gli esperimenti restano candidati finché superano il confronto e
l'approvazione prevista. Non promuovere una preferenza di singolo tenant a regola
universale, né trasformare un giudizio estetico in evidenza commerciale.

Dopo compattazione: rileggi task state, Context Pack, ultimi eventi e blocchi.
Confronta versioni; continua dalla prima azione ancora autorizzata. Mai riavviare
la produzione per mancanza di memoria conversazionale.

### Uscita e stop

Report con stato, runtime, input/output hash, risultati dei controlli, unknown,
prossima azione permessa. `MOCK_TECHNICAL_PASS` non equivale a
`READY_FOR_HUMAN_GATE`, `APPROVED`, `PUBLISHED` o test del provider reale.
Un fallimento deve lasciare una traccia, non essere cancellato dalla memoria.

## Sicurezza reale da implementare

Le istruzioni e l'hook di Claude non sono una barriera globale. Se la stessa
identità di sistema può leggere segreti e chiamare provider direttamente, il
wrapper è aggirabile. Il rilascio reale richiede worker autorizzato, credenziali
non accessibili ai percorsi alternativi, autorizzazioni verificate e controlli
nel servizio. Il mock non simula questa separazione di privilegi.
