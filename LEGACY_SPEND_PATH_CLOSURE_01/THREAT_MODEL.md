# THREAT MODEL DEL CONFINE DELLO SPENDER

Machine-readable: `lspc1/threat_model.py` → `evidence/E14_threat_model.json`.

Richiesto dalla Human Review 01. Serve a rendere esplicita una distinzione che,
restando implicita, diventa una pretesa: **quale confine protegge da cosa**, e cosa
nessuno dei due pretende di fermare.

La regola che tiene insieme il documento, e che la review ha formulato meglio di
quanto avessi fatto io: non si può chiamare «strutturale» un confine e allo stesso
tempo ignorare i metodi che stanno dietro la struttura.

---

## 1. Il confine del CORE

`adapters.base.SpendCapableAdapter` + `authorize_dispatch` + `grant_dispatch` + il
guard sugli hook, più i controlli di `transport.pipeline.run_job`.
**Imposto da:** codice del Core, nello stesso processo del chiamante.

| minaccia | cosa | evidenza |
|---|---|---|
| `SUPPORTED_ENTRY_POINT_OUT_OF_GOVERNANCE` | un entry point supportato chiamato fuori dal percorso governato | `E04`, `run_spender_boundary:D` |
| `DIRECT_SUBMIT` | `adapter.submit(spec)` diretto | `E04`, `run_spender_boundary:B` |
| `DIRECT_AUTHORIZE_PAYLOAD` | `adapter.authorize_payload(digest)` diretto | `E04`, `run_spender_boundary:C` |
| `RUN_JOB_WITHOUT_GOVERNED_INPUTS` | `run_job` senza operazione/quote/envelope, e con `envelope_units` (budget del client) | `E06`, `run_spender_boundary:D/E` |
| `CALLER_CONSTRUCTED_CAPABILITY` | una `DispatchAuthorization` costruita dal chiamante — **il blocker della review** | `E13`, `run_spender_boundary:L/N` |
| `CAPABILITY_BUILT_BYPASSING_CONSTRUCTOR` | la stessa, fabbricata aggirando `__post_init__` | `E13`, `run_spender_boundary:L` |
| `CAPABILITY_REPLAY` | un'autorizzazione **legittima** riusata dopo il proprio `with` | `run_spender_boundary:O` |
| `DIRECT_IMPLEMENTATION_HOOKS` | `_dispatch` / `_authorize_payload` invocati direttamente | `E13`, `run_spender_boundary:M` |
| `CAPABILITY_MASKING_WRAPPER` | un wrapper che dichiara `spend_capable = False` e delega allo spender | `E05` |
| `ACCIDENTAL_UNGOVERNED_INTEGRATION` | codice nuovo che chiama il Core senza sapere del percorso governato | `E04`, `E06` |

### Perché tre meccanismi e non uno

1. **`grant_dispatch` rilegge il journal.** Non riceve un'autorizzazione: riceve lo
   store autorevole e l'identità del tentativo, e chiama `authorize_dispatch` da sé.
   Non esiste una firma alternativa che accetti una capability — se esistesse,
   sarebbe quella che verrebbe usata.
2. **Il costruttore pretende un token di conio** privato del modulo. Il controesempio
   letterale della review fallisce qui, con `DISPATCH_AUTHORIZATION_FORGED`.
3. **Registro dei coniati, per identità, a consumo singolo.** `eq=False`: due
   autorizzazioni con gli stessi campi non sono la stessa autorizzazione. Chi aggira
   i primi due meccanismi — costruendo l'oggetto con `object.__new__` e infilandolo
   nello slot — si ferma qui.

### Perché un booleano non basterebbe

`issued_by_authorize_dispatch = True` è un campo che chiunque scrive. Una dataclass
`frozen` rende l'oggetto **immutabile**, non **autentico**. L'autenticità, qui, è
l'identità dell'oggetto più la sua presenza in un registro privato.

---

## 2. Il confine di PROCESSO — P-B01

UID distinto per l'orchestrator, nessuna capability, `no_new_privs`, segreto e store
leggibili solo nel dominio dello spender, `SO_PEERCRED` sul canale.
**Imposto da:** il kernel.

| minaccia | evidenza |
|---|---|
| `ORCHESTRATOR_READS_CREDENTIALS` — l'orchestrator prova a leggere il segreto | `PROVIDER_BOUNDARY_HARDENING_01: B01`, T29 |
| `ACCESS_TO_SPENDER_STORE_OR_SECRET` — scrittura sullo store o lettura del segreto, cioè l'unico modo di fabbricare davvero le righe da cui `authorize_dispatch` deriva l'autorizzazione | `PROVIDER_BOUNDARY_GATE_02: C02`, `E09` |
| `UNAUTHORIZED_PROCESS_OR_UID` — un processo o UID non autorizzato al canale | `PROVIDER_BOUNDARY_GATE_02: C02` |

---

## 3. Cosa NESSUNO dei due pretende di fermare

### `ARBITRARY_MALICIOUS_CODE_SAME_IDENTITY`

Codice arbitrariamente malevolo eseguito **nello stesso processo**, con la stessa
identità e le stesse credenziali dello spender.

In Python il trattino basso non è un confine di sicurezza: chi esegue nel processo
può importare un nome privato, riscrivere un attributo di classe o sostituire un
modulo. Nessun controllo scritto in Python può impedirlo, e fingere il contrario
sarebbe la bugia più pericolosa di tutto questo documento.

**Mitigazione:** P-B01. Quel codice non gira nel dominio dello spender:
l'orchestrator non ha il segreto, non ha lo store, non ha l'UID.

**Residuo:** se un attaccante ottiene esecuzione di codice **dentro** il dominio
dello spender, ha già le credenziali. Il confine del Core non è l'ultima linea, e non
è mai stato pensato per esserlo.

### `FABRICATED_STORE_OBJECT`

Un chiamante che passa a `grant_dispatch` un oggetto duck-typed al posto dello store
autorevole, e gli fa dire ciò che vuole.

Il Core non può sapere quale oggetto sia «il vero journal»: può solo pretendere che i
fatti vengano riletti da ciò che gli viene dato. `run_job` passa lo store reale;
sostituirlo richiede esecuzione di codice nel processo, cioè il caso sopra.

---

## 4. Come si legge questa tabella quando arriverà un provider vero

Il confine del Core è ciò che impedisce a un'**integrazione** di raggiungere il
provider fuori governance: codice nuovo, un test, un helper, una capability
presentata al posto di una derivata. È molto, ed è la parte che si rompe davvero
nella vita di tutti i giorni.

Il confine che impedisce a un **attaccante** di raggiungerlo è P-B01, ed è il kernel
a imporlo.

Chiamarli con lo stesso nome li indebolirebbe entrambi.
