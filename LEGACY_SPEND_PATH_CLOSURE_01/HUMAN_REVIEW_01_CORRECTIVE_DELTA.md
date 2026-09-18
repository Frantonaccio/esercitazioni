# HUMAN REVIEW 01 — DELTA CORRETTIVO

**Verdetto ricevuto:** `HUMAN_REVIEW_HOLD — DISPATCH_AUTHORIZATION_FORGEABLE`
**Stato dopo questo delta:** vedi `READINESS.json`

---

## Il blocker, senza attenuanti

Il primo candidate (`44f9ea29`) dichiarava che `DispatchAuthorization` non è
falsificabile perché deriva dal journal autorevole. Il codice però esponeva
contemporaneamente:

- `DispatchAuthorization` come dataclass **costruibile**;
- `grant_dispatch(adapter, auth)` che **accettava quell'oggetto**;
- `submit()` / `authorize_payload()` che consideravano il grant **sufficiente**.

Il che significa che l'autorizzazione derivava dal journal **per convenzione del
chiamante** — cioè non ne derivava affatto. La suite verificava grant scaduto,
rientranza, altra spec, altro digest e journal alterato, ma non costruiva mai
direttamente un'autorizzazione falsa. Era il varco, ed era proprio la proprietà che
la fase voleva dimostrare.

### Riprodotto, non ipotizzato

Sonde `P11`/`P12` eseguite contro il candidate revisionato `44f9ea29`
(`evidence/E13_forged_dispatch_authorization.json`):

| tentativo | esito su `44f9ea29` |
|---|---|
| controesempio esatto della review (`DispatchAuthorization(...)` + `grant_dispatch` + `submit`) | **riuscito**, `pv_e46492dd` |
| `grant_dispatch(adapter, auth)` a due argomenti | **grant aperto** |
| oggetto fabbricato infilato nello slot della concessione | **riuscito** |
| `_dispatch` / `_authorize_payload` con autorizzazione fabbricata | **riusciti** |
| **sentinella** | `reached=2`, `sent=2` (P11) · `reached=2` (P12) |

`BLOCKER_REPRODUCED`.

---

## Il fix — tre meccanismi, deliberatamente ridondanti

### 1. `grant_dispatch` non riceve più un'autorizzazione

```python
grant_dispatch(adapter, store, job_id, *, spec_key, payload_digest, attempt_token)
```

Riceve lo **store autorevole** e l'identità del tentativo, e chiama internamente
`authorize_dispatch(store, ...)`. L'unica strada supportata per aprire il cancello
implica una **nuova lettura del journal**. Non esiste una firma alternativa che
accetti una capability: se esistesse, sarebbe quella che verrebbe usata.

Verificato per introspezione, non per fiducia: `run_spender_boundary:N` asserisce la
firma e che la vecchia chiamata a due argomenti sollevi `TypeError`.

### 2. `DispatchAuthorization` non è costruibile dall'esterno

Il costruttore pretende un token di conio privato del modulo — **identità di un
oggetto**, non un booleano né una stringa. Il controesempio letterale della review
fallisce qui, con `DISPATCH_AUTHORIZATION_FORGED`, prima ancora di arrivare al grant.

### 3. Registro dei coniati, per identità, a consumo singolo

`@dataclass(frozen=True, eq=False)`: due autorizzazioni con gli stessi campi **non
sono** la stessa autorizzazione. Ogni varco — il grant, i due template method, i due
hook — verifica che l'oggetto sia nel registro di ciò che `authorize_dispatch` ha
davvero coniato, e che non sia già stato consumato. Chi aggira i primi due meccanismi
costruendo l'oggetto con `object.__new__` e infilandolo nello slot si ferma qui.

In più: un'autorizzazione **legittima** vale per un solo tentativo. Fuori dal suo
`with` è `DISPATCH_AUTHORIZATION_SPENT` — un replay è una seconda spesa.

---

## La seconda superficie: gli hook di implementazione

La review chiedeva di classificarli, non di far finta che il trattino basso li
protegga. Sono stati **protetti** e **classificati**.

`__init_subclass__` avvolge `_dispatch` e `_authorize_payload` della sottoclasse con
lo stesso guard dei template method. La sottoclasse non deve ricordarsi di nulla e
non può disapplicarlo se non ridefinendo l'hook — che verrebbe a sua volta avvolto.
`run_spender_boundary:M` asserisce che il flag `__lspc_guarded__` sia presente su
entrambi.

E resta dichiarato, in `THREAT_MODEL.md` e nel docstring del modulo, che contro
codice arbitrariamente malevolo eseguito con la stessa identità dello spender il
confine non è questo: è P-B01.

---

## Esito dopo il fix

| tentativo | esito su `605a8d74` | sentinella |
|---|---|---|
| controesempio esatto della review | `DISPATCH_AUTHORIZATION_FORGED` | 0 |
| `grant_dispatch(adapter, auth)` | `TypeError` — la firma non esiste | 0 |
| oggetto fabbricato nello slot | `DISPATCH_AUTHORIZATION_FORGED` | 0 |
| `_dispatch` / `_authorize_payload` senza concessione | `SPEND_AUTHORIZATION_REQUIRED` | 0 |
| `_dispatch` / `_authorize_payload` con autorizzazione fabbricata nello slot | `DISPATCH_AUTHORIZATION_FORGED` | 0 |
| autorizzazione **legittima** riusata | `DISPATCH_AUTHORIZATION_SPENT` | invariata |
| percorso **governato** | `SUCCEEDED` | **1** |

---

## Una nota su `bypass_constructor`

Nell'evidenza il tentativo `bypass_constructor` risulta *non rifiutato* in entrambe
le esecuzioni, e non è una svista: costruire un oggetto Python con `object.__new__` è
sempre possibile e nessun controllo può vietarlo. Ciò che conta è che quell'oggetto
**non apra nulla** — ed è esattamente ciò che misura `slot_injection`, che sul
correttivo è `DISPATCH_AUTHORIZATION_FORGED` con sentinella a 0.

Registrare il tentativo come riuscito invece di nasconderlo è il punto: l'evidenza
deve dire cosa è successo, non cosa ci fa comodo.

---

## Cosa NON è cambiato

- gli assert storici: nessuno indebolito, `tests/run_gate.py` intatto;
- `SNAPSHOT_SEAL_WRITE_RACE`: resta `STILL_OPEN`, non corretto qui, come da verdetto;
- le policy NG-04 e orphan lease: nessun valore deciso;
- i commit già revisionati: nessun amend, nessun force-push. `44f9ea29` e `ad2f9c07`
  restano dove sono, e i due delta correttivi sono commit nuovi sugli stessi branch.
