# NG-04 — FRESHNESS DEI REPORT DI RICONCILIAZIONE

Separazione obbligatoria, richiesta dal mandato:

| | |
|---|---|
| **MECCANISMO** | La capacità tecnica di imporre una finestra temporale fail-closed. **Implementato e verificato** (C03). |
| **POLICY** | I valori concreti della finestra. **Non decisi, non suggeriti, non hardcodati**: `POLICY_DECISION_REQUIRED`. |

---

## Il difetto, riprodotto prima del fix

`evidence/pre_fix/reproduction_ng04_freshness.json`. Due assi, uno più ampio di quanto il mandato
descrivesse:

| caso | prima |
|---|---|
| **A** — `max_age_s` opzionale (`default None`) | un report firmato con `issued_at = 0.0` (1970) viene **applicato**: `{"applied": true, "state": "SUCCEEDED"}` |
| **B** — `max_age_s = 60.0` ma `issued_at` nel **futuro** (`2000000000.0`) | `now - issued_at` è negativo, quindi `> max_age_s` non scatta mai: **applicato lo stesso** |

Il nonce monouso impediva il **riuso**, non l'**età** — e non faceva nulla contro un orologio in
avanti.

---

## Il meccanismo

`RUNTIME_INTEGRATION_GATE_01/runtime/reconciliation.py`.

### `FreshnessPolicy`

```python
FreshnessPolicy(*, max_age_s: float, max_future_skew_s: float, label: str)
```

- **`max_age_s`** — età massima ammessa: `now - issued_at <= max_age_s`.
- **`max_future_skew_s`** — anticipo massimo tollerato sull'orologio dell'emittente:
  `issued_at - now <= max_future_skew_s`. Senza questo secondo limite un `issued_at` nel futuro
  rende l'età negativa e quindi sempre "fresca": è esattamente il difetto B.
- **`label`** — obbligatoria: rende tracciabile **chi** ha deciso i valori. Finisce nell'evidenza
  registrata, così ogni reconciliation applicata dice sotto quale policy è passata.

Validazione della policy stessa, fail-closed: non numerico, `NaN`, `inf`, negativo, `bool`, label
vuota → `FRESHNESS_POLICY_INVALID`. Zero è un valore **ammesso** ed è il più stretto possibile; non
è un default.

### Obbligatorietà

`reconcile_authenticated(..., freshness)` non ha default e `None` non è ammesso:

```
freshness assente  → ReconciliationRefused("FRESHNESS_POLICY_REQUIRED")
freshness = None   → ReconciliationRefused("FRESHNESS_POLICY_REQUIRED")
freshness = 60.0   → ReconciliationRefused("FRESHNESS_POLICY_INVALID")
```

**L'assenza di una decisione non è un permesso.**

### Ordine dei controlli

La freshness si valuta **dopo** l'autenticazione (un report non autenticato non merita un verdetto
sull'età) e **prima** di qualunque lettura dello store e prima del claim del nonce. Conseguenza
verificata: **un rifiuto di freshness non brucia il nonce** — lo stesso nonce resta spendibile da
un report valido successivo.

### Autorità unica sul timestamp

`_check_report_shape` non giudica più il valore di `issued_at`: verifica solo che il campo sia
presente e canonicalizzabile per la firma. Assente, malformato, nel futuro e troppo vecchio hanno
**codici distinti** e una sola sede, `FreshnessPolicy.check`.

---

## Casi verificati (C03, `evidence/C03_ng04_freshness_mechanism.json`)

Parametri di **prova** usati dal test — non una policy:
`max_age_s = 120.0`, `max_future_skew_s = 5.0`, `label = "LAB_TEST_PARAMETER_NOT_A_POLICY_DECISION"`.

| # | caso | esito atteso e osservato |
|---|---|---|
| 1 | policy omessa | `FRESHNESS_POLICY_REQUIRED` |
| 2 | policy `None` | `FRESHNESS_POLICY_REQUIRED` |
| 3 | policy di tipo sbagliato | `FRESHNESS_POLICY_INVALID` |
| 4 | `max_age_s` negativo | `FRESHNESS_POLICY_INVALID` |
| 5 | `max_age_s` `NaN` | `FRESHNESS_POLICY_INVALID` |
| 6 | `max_age_s` `inf` | `FRESHNESS_POLICY_INVALID` |
| 7 | `max_age_s` booleano | `FRESHNESS_POLICY_INVALID` |
| 8 | `label` vuota | `FRESHNESS_POLICY_INVALID` |
| 9 | report troppo vecchio | `REPORT_STALE` |
| 10 | report del 1970 | `REPORT_STALE` |
| 11 | report nel futuro oltre lo skew | `REPORT_FROM_FUTURE` |
| 12 | `issued_at` assente (firmato così) | `REPORT_TIMESTAMP_MISSING` |
| 13 | `issued_at` stringa (firmato così) | `REPORT_TIMESTAMP_MALFORMED` |
| 14 | `issued_at` booleano (firmato così) | `REPORT_TIMESTAMP_MALFORMED` |
| 15 | **confine**: `age == max_age_s` | **applicato** (finestra chiusa a destra) |
| 16 | **confine**: `age == max_age_s + 1e-3` | `REPORT_STALE` |
| 17 | **confine**: `issued_at - now == max_future_skew_s` | **applicato** |
| 18 | policy più stretta sullo stesso report | `REPORT_STALE` (il meccanismo è davvero parametrico) |
| 19 | nonce di un report rifiutato per staleness, riusato da un report fresco | **applicato** (il rifiuto non brucia il nonce) |
| 20 | replay: stesso nonce dopo un'applicazione riuscita, su job tornato riconciliabile | `REPLAY` |

Su **ogni** rifiuto: `journal_unchanged = true`.
Su ogni applicazione riuscita l'evidenza registrata porta l'attestazione:

```json
{"policy": {"label": "...", "max_age_s": 120.0, "max_future_skew_s": 5.0},
 "issued_at": 1000000.0, "checked_at": 1000000.0, "age_s": 0.0, "verdict": "FRESH"}
```

I timestamp malformati sono **firmati con il valore malformato**: alterare il campo dopo la firma
avrebbe misurato la firma, non la freshness.

---

## La policy: cosa manca e perché non è qui

Il codice non contiene alcun valore di default: nessun 30s, 60s, 5 minuti. Scegliere quei numeri
richiede fatti che questa fase non possiede:

1. **`max_age_s`** dipende dalla latenza reale fra emissione del report del provider e suo consumo,
   e dalla finestra entro cui un esito remoto è ancora rappresentativo.
2. **`max_future_skew_s`** dipende dalla deriva d'orologio tollerata fra l'emittente e lo spender, e
   dalla presenza o meno di sincronizzazione NTP garantita.
3. Entrambi dipendono da **chi** emette il report (vedi `REAL_PROVIDER_PREREQUISITES.md` §8):
   con un provider reale l'emittente non è più un'autorità di laboratorio.

Finché quei fatti non esistono, inventare un numero per far diventare verde un test sarebbe
esattamente ciò che il mandato vieta.

Nel gate, i valori usati sono **parametri di prova** dichiarati come tali
(`LAB_TEST_PARAMETER_NOT_A_POLICY_DECISION`, `LAB_GATE_PARAMETER_NOT_A_POLICY_DECISION`) e il daemon
spender li riceve come argomenti **obbligatori** da riga di comando: non ha un default.

---

## Stati

| requisito | stato |
|---|---|
| `RECONCILIATION_FRESHNESS_NG04_MECHANISM` | **`VERIFIED_LAB`** |
| `RECONCILIATION_FRESHNESS_NG04_POLICY` | **`POLICY_DECISION_REQUIRED`** |

Il meccanismo verificato **non chiude** il requisito di freshness del Provider Boundary Gate:
senza una policy scelta da un umano, la finestra non esiste.
