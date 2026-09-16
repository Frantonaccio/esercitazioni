# BLOCKERS_OPEN — stato a fine RUNTIME INTEGRATION GATE 01

Nessun blocker è stato chiuso da questo gate. Uno è stato aggiunto (P2 non disponibile).

| ID | titolo | stato | cosa questo gate ha fatto | cosa NON ha fatto |
|---|---|---|---|---|
| **P-B01** | credential isolation | **APERTO** | dimostrato la proprietà più semplice: in FAKE MODE nessuna lettura di `~/.higgsfield/credentials.json`, nessuna env segreta, nessun subprocess provider, nessuna rete (T14/T15, sentinella con esca e controprova) | nessun isolamento reale delle credenziali del provider |
| **P-B02** | remote reconciliation | **APERTO** | `SUBMIT_UNKNOWN` persistito e rispettato: nessun resubmit, nessuna nuova reservation, budget mantenuto, esito `EXISTING_LIVE_JOB/reconciliation-required` (T10) | nessun lookup remoto reale |
| **P-B03** | economic ledger | **APERTO** | meccanica mock del budget: `budget_units`/`envelope_units` passano al Core; 70+50 su 100 → `BudgetExceeded` (T12); valori non ammessi rifiutati (T13). Design requirement registrato sotto | nessun ledger; nessun valore Higgsfield/Meta/authority nel Core |
| **P-B04** | byte/ref safety (exact-byte snapshot del real submit) | **APERTO** | mantenuti: Core SHA, hash dei file del runtime candidate (SHA256SUMS), `spec_key`, hash del payload fake (`evidence/T06_happy_path.json`) | nessuno snapshot byte-exact di un submit reale |
| **G-N02** | semantic claim paraphrase gap | **APERTO** | nulla: gate Runtime/C26, non di semantica creativa | — |
| **P2-ABSENT** (nuovo) | `hf_batch.py`, `gate01_lab.py`, `control.py` non disponibili nell'ambiente | **APERTO — BLOCCA T16, PIN_AUDIT sui tre file, GENSPEC_MAPPING reale, `runtime/hf_batch_runtime.py`** | tutto ciò che dipende dal solo Core | il binding reale del verbo `go` |

## Economic Autonomy Model — DESIGN REQUIREMENT (non implementato)

Il layer di produzione futuro potrà avere, **sopra** il Core e senza toccarne l'aritmetica atomica:

```
authorized_envelope      → envelope_units passato a reserve_or_get_live
target_budget
tactical_reserve_pct     → riduce l'envelope effettivo prima della chiamata al Core
reserved_units           → già: SqliteReservationStore.reserved_units()
actual_units             → da Job.cost_credits al terminale
released_units           → differenza reserved - actual sul terminale
classificazioni: CREATIVE_ITERATION · PREVENTABLE_WASTE · TECHNICAL_FAILURE
```

Il Core conosce solo unità intere non negative e invarianti (`validate_units`). Le policy
(11.000 crediti Higgsfield, 1.500/video, 25% reserve, Meta Ad budget, authority budget)
restano nella Production Policy futura. **Nessuna di queste cifre è entrata nel Core né nel runtime candidate.**
