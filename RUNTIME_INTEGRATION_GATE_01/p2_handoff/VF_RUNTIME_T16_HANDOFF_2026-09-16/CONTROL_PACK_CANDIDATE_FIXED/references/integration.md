# Integrazione sul sistema esistente

## Baseline effettivamente disponibile

Verifica locale del 16 settembre 2026, non verifica live del Mac.
Core in checkout pulito: `9afaddf3cec1e8baf9600ed8dc0461e7adccb5c7`.
Sono stati letti `core/boot.py`, `core/schema.py`, `adapters/base.py`,
`adapters/fake.py`, `registry/contracts.py` e `transport/pipeline.py`.
Esistono già boot, schema, fake provider, trasporto e contratti registry.
Il candidato importa `FakeAdapter` e `GenSpec`: non ne crea copie divergenti.

`hf_batch.py` non è presente fra i file locali individuati. La sua implementazione
e i comandi citati dall'operatore del Mac restano da ispezionare. Nessuna modifica
è stata applicata ai due repository locali o al tenant. Nessuna PR è stata aggiornata.

Il pin serve a rendere ripetibile questo test, NON suggerisce di retrocedere il
Core operativo a quel commit. Un Core diverso richiede diff, compatibilità,
rerun e decisione sul nuovo pin. Non cambiare la costante solo per sbloccare i test.

## Mandato per Claude Code sul Mac

1. Leggi questa integrazione, `protocol.md` e lo stato reale del progetto.
2. Produci un audit con path, SHA, dirty files, entry point provider, chi possiede
   credenziali, registry effettivo, meccanismo append-only e autorizzazioni.
3. Apri `hf_batch.py` e individua le funzioni reali per lock, quote, submit,
   reconcile e QA. Non assumere che i nomi CLI coincidano con funzioni Python.
4. Mappa ogni controllo di questo candidato sul punto equivalente già presente.
   Riusa ciò che c'è; sposta il controllo nel Core solo se realmente riutilizzabile.
5. Esegui il laboratorio su checkout compatibile e scrivi il rapporto.
6. Prepara un diff minimo d'integrazione, con mock come unico provider consentito.
   Non modificare branch/versioni, installare la skill, creare commit o fare push
   senza autorizzazione specifica. Non introdurre un nuovo registry.
7. Esegui test esistenti e aggiuntivi; documenta ogni bypass e gap non risolto.
8. Consegna audit, diff, rapporti e piano rollback. Fermati al gate d'integrazione.

Output verificabile: tabella requisito → file/funzione reali → modifica minima →
test → risultato → gap. Un file presente non è una regola attiva.

## Punti di inserimento proposti, non patch già applicate

| Punto | Responsabilità | Prova richiesta |
|---|---|---|
| Dopo boot | Context Pack risolto, hash e versioni | Drift di file rilevato |
| Prima quote | Spec completa e autorizzata | Quote legata a fingerprint |
| Dentro submit del wrapper | Lock, budget, input, reservation atomica | Zero chiamate su input invalido |
| Dopo timeout | Reconcile, senza retry cieco | Una sola richiesta esterna |
| Dopo fetch | Hash e decodifica media | Payload corrotto bloccato |
| Prima Human Gate | QA dell'export contro vincoli | Unknown non promosso a PASS |
| Dopo decisione | Eventi e package coerenti | Approvazione lega hash e scope |

## Confini dei test consegnati

**Implementato e testabile:** lock immutabile nel journal del laboratorio; hash di
file e quote; tenant; scadenze; budget per job; reservation SQLite prima del submit;
blocchi doppio submit anche concorrente; stato leggibile da nuovo processo;
timeout e corruzione simulati; risultato mai dichiarato QA visiva.

**Non implementato / non certificato:** integrazione `hf_batch.py`; hook installati;
approvazioni autenticate; segreti isolati; append-only resistente a manomissione
da parte dell'utente OS; budget cumulativo; quote provider reale; timeout API reale;
reconcile remoto dopo crash; snapshot atomico dei byte inviati; casting; esame dei
pixel; assembly; timing EDL; Drive LATEST/SUPERSEDED; performance pubblicitaria.

I test di persistenza riproducono perdita degli oggetti in memoria e nuovo
interprete, NON una sessione reale di Claude dopo compattazione.
Il manifest fixture ha un tenant SHA sintetico: non prova che il tenant Mac sia
pulito. Le scene hanno vincoli strutturali, non una valutazione semantica automatica.
Il sistema locale è fidato: un processo con accesso al DB può alterarlo o chiamare
direttamente il FakeAdapter. Non esiste pretesa di sicurezza contro quell'attore.

## Test di accettazione necessari prima della modalità reale

| ID | Esperimento | Criterio |
|---|---|---|
| LIVE-01 | Nuova sessione Claude con solo job ID | Riprende stato senza ricostruzione dalla chat |
| LIVE-02 | Compattazione dopo submit | Riconcilia; non effettua secondo submit |
| LIVE-03 | Cambio reference tra lock e invio | Byte inviati identici al lock oppure blocco |
| LIVE-04 | Provider alternativo da shell/skill/MCP | Credenziali non disponibili o servizio rifiuta |
| LIVE-05 | Due job concorrenti sul budget totale | Somma prenotazioni non supera plafond |
| LIVE-06 | Risposta persa dopo accettazione | Lookup autenticato per chiave; niente retry cieco |
| LIVE-07 | Manifest o approvazione contraffatti | Verifica autenticità e rifiuta |
| LIVE-08 | Export sostituito dopo QA | Human Gate non può approvare il nuovo hash |
| LIVE-09 | Vincolo visivo non osservabile | NOT_VERIFIED, nessuna promozione automatica |
| LIVE-10 | Claim non autorizzato con parole diverse | Review semantica + policy impediscono rilascio |
| LIVE-11 | Runtime aggiornato senza qualificazione | Blocco fino a regression suite e gate |
| LIVE-12 | Rollback e restore in ambiente isolato | Stato, hash e decisioni recuperati coerentemente |

Questi test sono requisiti di rilascio, non esiti già ottenuti.

## Destinazione e rollback

Destinazione proposta della skill sottile: `.claude/skills/creative-os-production-control/`
nel repository che già ospita il bootstrap del progetto. La scelta tra checkout Core
condiviso e project root va risolta nell'audit per non duplicare l'autorità.
Il codice qui allegato resta laboratorio: l'eventuale estrazione dei controlli nel
Core avviene solo nel diff approvato. Non inserire fixture di tenant nella policy.

Rollback proposto: ripristina versione precedente di skill/controlli, conserva gli
eventi e le reservation esistenti, disabilita submit fino alla riconciliazione dei
job incerti. Non cancellare la memoria dei fallimenti per far passare un test.
