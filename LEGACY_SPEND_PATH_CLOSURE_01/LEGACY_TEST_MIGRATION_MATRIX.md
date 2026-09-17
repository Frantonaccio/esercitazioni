# MATRICE DI MIGRAZIONE DEI TEST STORICI

Evidenza: `evidence/E07_legacy_test_migration.json` · codice: `lspc1/migrated.py`

## Due decisioni, dette prima

**1. `tests/run_gate.py` non e' stato toccato.** E' la base di non-regressione, ed e'
cio' che rende confrontabili i due esiti pre e post fix (`regression/`). Riscriverlo
per farlo passare sul percorso governato avrebbe distrutto proprio la misura che
serviva.

**2. I test storici non richiedono piu' un bypass SPENDIBILE.** Il requisito aperto era
questo, ed e' questo che e' stato chiuso: il percorso `LEGACY_LAB` che T01–T34 usano e'
ora `LAB_ONLY_NON_PROVIDER_CAPABLE` — un percorso verso un adapter deterministico che
**non puo'** raggiungere un provider, dimostrato in `E05` contro cinque tentativi di
riaprirlo. Quello che i test tengono in vita non e' piu' una porta laterale della
spesa: e' un adapter finto.

Per provarlo — e non solo dichiararlo — ogni test storico che usava quel percorso ha
qui un **equivalente eseguito**, sul percorso governato o sul Core. 20 casi, 20 PASS.

## Regole rispettate

- nessun assert e' stato modificato per far passare qualcosa;
- dove il percorso governato produce un esito **diverso**, l'esito diverso e' asserito
  esplicitamente, la differenza e' dichiarata qui sotto con il motivo, ed e' sempre
  nella direzione di un controllo **in piu'**;
- l'intento semantico originale e' invariato.

---

## La matrice

| test ID | comportamento originale verificato | perche' usava legacy | cosa deve continuare a provare | nuova modalita' | equivalenza semantica | esito |
|---|---|---|---|---|---|---|
| **T01** → `M01` | `CORE_PIN_OK`, `go` procede, `SUCCEEDED` | `run_go` di default era legacy | il gate di pin ammette il Core canonical pulito | **GOVERNED_PATH** | identica; in piu' `governance == GOVERNED_LAB` | PASS |
| **T04** → `M04` | `spec_key` identico fra run, riordini e processi | idem | determinismo della chiave | **GOVERNED_PATH** | identica | PASS |
| **T06** → `M06` | happy path, `SUCCEEDED` riletto da nuovo processo, impegnato 0 | `budget_units=10, envelope_units=100` grezzi | end-to-end + durabilita' + esposizione azzerata | **GOVERNED_PATH** (envelope 100 autorizzate, quote fidata da 10) | identica; in piu': l'importo **viene** dalla quote e la quote risulta consumata | PASS |
| **T07** → `M07` | 2° `go` su spec viva = `EXISTING_LIVE_JOB`, 1 submit | `go` legacy in-process | identita' della spec sotto un tentativo vivo | **GOVERNED_PATH** | identica | PASS |
| **T08** → `M08` | 2 processi concorrenti: 1 `RESERVED_NEW` + 1 `EXISTING_LIVE_JOB`, 1 submit | `run_go` legacy | prenotazione atomica sotto concorrenza reale | **GOVERNED_PATH** (una sola quote per l'operazione) | identica; in piu': la quote e' consumata **una** volta, quindi la seconda spesa e' impossibile anche economicamente | PASS |
| **T09** → `M09` | restart: nessuna nuova reservation/submit, stesso `job_id` | `run_go` legacy | ripresa durevole | **GOVERNED_PATH** | identica; in piu': il resume **non** consuma una seconda quote | PASS |
| **T10** → `M10` | `SUBMIT_UNKNOWN` persistito, 30 unita' impegnate, 0 re-submit | `budget_units=30` grezzo | incertezza conservata, budget non rilasciato | **GOVERNED_PATH** (quote fidata da **30**) | identica, stesso numero 30: l'importo lo decide l'AUTORITA', che in laboratorio e' il test | PASS |
| **T11** → `M11` | `ProviderMismatch`, 0 submit, reservation intatta | `run_go` legacy | ownership di provider | **GOVERNED_PATH** | identica | PASS |
| **T12** → `M12` | envelope 100: 70+50 → un `BudgetExceeded`, impegnato ≤ 100 | `envelope_units=100` grezzo (budget scelto dal client) | invariante economico atomico | **GOVERNED_PATH** (un envelope da 100, due quote fidate 70 e 50, due operazioni) | identica; cambia **chi** autorizza l'importo, non l'invariante | PASS |
| **T13** → `M13` | `ReservationContractError` su budget `-1` / `True` / `1.5` / `"10"`, 0 righe | `budget_units` grezzo dal client | `validate_units` rifiuta valori non ammessi prima di ogni scrittura | **CORE_UNIT** | **qui la differenza va detta**: nel percorso governato il client non presenta piu' un importo — lo riceve dalla quote — quindi da li' quel rifiuto non e' piu' raggiungibile, e pretendere il contrario significherebbe tenere in vita un percorso dove il client sceglie il prezzo. Il test si sposta dove la proprieta' vive: la funzione pura, la prenotazione del Core **e** l'emissione della quote. Tre rifiuti invece di uno | PASS |
| **T18** → `M18` | terminale durevole; replay = resume 0 submit; nuovo tentativo con permesso | `run_go` legacy | identita' per tentativo, storico conservato | **GOVERNED_PATH** | identica; in piu': il nuovo tentativo richiede una **nuova** quote (2 consumate) | PASS |
| **T22** → `M22` | `hf_batch` su spec REALE: 2 `RESERVED_NEW` + 2 submit; 2° round 0 submit | `Batch(authorization=None)` | il percorso "di produzione" del runtime attraverso il Core | **GOVERNED_PATH** (`quote_for(asset)`, envelope per work order) | identica; in piu': ogni asset ha la sua quote legata a `<namespace>:<asset>` e allo `spec_key` reale | PASS |
| **T24** → `M24` | replay dopo `SUCCEEDED`/`FAILED`, anche da nuovo processo: 0 submit | `run_go` legacy | RESUME non e' una nuova spesa | **GOVERNED_PATH** | identica; in piu': 3 quote consumate = 3 spese, 0 resume | PASS |
| **T25** → `M25` | senza motivo/permesso/operazione → rifiuto; permesso monouso; binding all'operazione | `run_go` legacy + `store_call` | RV03 + CR-01 | **GOVERNED_PATH** (+ helper di **autorita'** al posto del dispatch arbitrario) | identica su tutti i codici (`REASON_REQUIRED`, `PERMIT_REQUIRED`, `OPERATION_ID_REQUIRED`, `PermitError` ×2) | PASS |
| **T26** → `M26` | risposta persa; cambio run e modello non aggirano l'incertezza | `run_go` legacy | nessun blind retry, operazione bloccata | **GOVERNED_PATH** | identica nell'intento; il rifiuto e' `LIVE_OR_UNCERTAIN_ATTEMPT` del Runtime **prima** di `OperationBusy` del Core, cioe' **piu' presto**, non piu' debole | PASS |
| **T27** → `M27` | 3 job regolati saturano l'envelope; 4° `BudgetExceeded` con 0 vivi; non regolato resta esposto | misto | P-B03 cumulativo | **GOVERNED_PATH** | identica | PASS |
| **T29** | isolamento di privilegio dell'orchestrator | 1 `run_go` incidentale | confine di processo | **non migrato** | il test e' `BLOCKED_ENVIRONMENT` per policy (runner same-UID) e lo resta, come a baseline. Il suo `run_go` non e' cio' che verifica | BLOCKED (invariato) |
| **T30** → `M30` | crash dopo l'invio e prima del journal; recovery → `SUBMIT_UNKNOWN`; replay 0 submit | `run_go` legacy | recovery senza blind retry | **GOVERNED_PATH** | identica, compreso `exitcode == 4` e coda vuota | PASS |
| **T33** → `M33` | spec viva di OP_A non restituita a OP_B; RESUME(OP_A) ≠ RESUME(OP_B) | `run_go` legacy | CR-01 identita' fra operazioni | **GOVERNED_PATH** | identica; `RESUME(OP_B)` e' ora `NO_EXISTING_ATTEMPT` invece di aprire un secondo tentativo: piu' stretto, non piu' lasco | PASS |
| **T34** → `M34` | `<wo>:<asset>` stabile fra run, distinto fra work order, `spec_key` intatta | `run_go` + `hf_batch` legacy | CR-10 namespace di operazione | **GOVERNED_PATH** | identica: 4 righe su 2 spec distinte, round #2 tutto `resumed` | PASS |
| **T37** → `M37` | governed resume senza attempt → `NO_EXISTING_ATTEMPT`; resume-as-start solo LEGACY_LAB, marcato | 2 chiamate legacy per la marcatura | RESUME non e' START | **GOVERNED_PATH + LEGACY_LAB** | identica **piu' una**: resume-as-start esiste ancora per il laboratorio (`legacy_resume_as_start=True` con adapter finto) ma con uno SPENDER il rifiuto arriva prima di tutto (`LEGACY_LAB_NOT_PROVIDER_CAPABLE`, sentinella 0) | PASS |

---

## Le tre differenze, riassunte

Solo tre casi non producono un esito **identico** allo storico, e in tutti e tre la
direzione e' la stessa:

| caso | differenza | e' un indebolimento? |
|---|---|---|
| **M13** | il rifiuto si osserva sul Core (funzione pura + prenotazione + emissione quote) invece che dal client | no: **tre** punti di rifiuto invece di uno, e il client non puo' piu' nemmeno presentare l'importo |
| **M26** | il rifiuto e' `LIVE_OR_UNCERTAIN_ATTEMPT` del Runtime invece di `OperationBusy` del Core | no: arriva **prima**, senza toccare lo store |
| **M33** | `RESUME(OP_B)` e' `NO_EXISTING_ATTEMPT` invece di avviare un secondo tentativo | no: RESUME non e' START, che e' esattamente cio' che DELTA 03 aveva stabilito |

## Quello che questa matrice NON dice

Non dice che `tests/run_gate.py` sia stato riscritto: non lo e' stato, deliberatamente.
Non dice che il percorso `LEGACY_LAB` sia stato rimosso dal codice: non lo e' stato,
perche' il mandato autorizza a conservarlo per il laboratorio. Dice che non e' piu' un
percorso **spendibile**, e lo dice con una sentinella che conta.
