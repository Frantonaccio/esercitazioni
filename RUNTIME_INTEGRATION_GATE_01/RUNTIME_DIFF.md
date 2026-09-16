# RUNTIME_DIFF — differenze fra runtime originale (P2) e runtime candidate

## Diff testuale: NON PRODUCIBILE

`hf_batch.py` (P2) non è disponibile in questo ambiente. Non esiste
`runtime/hf_batch_runtime.py` perché non esiste un originale da cui copiarlo; creare un file con
quel nome senza l'originale sarebbe una finzione.

## Diff semantico (ciò che il candidate cambia nel percorso `go`, da applicare nella copia)

| aspetto | runtime originale (atteso dal mandato) | runtime candidate (`runtime/go_candidate.py`) |
|---|---|---|
| decisione "c'è già un job vivo?" | pattern `find_live_by_spec → if none → submit` (race per costruzione) | **assente**: `run_job` del Core → `reserve_or_get_live` atomica |
| stato del job | JobState/reservation JSON locali | `adapters.base.JobState` persistito da `SqliteReservationStore` |
| budget | calcolo locale | `budget_units` / `envelope_units` passati a `run_job`; aritmetica nel Core |
| submit | chiamata diretta al provider | solo il Core chiama `adapter.submit`, solo su `RESERVED_NEW` |
| provider | Higgsfield CLI/MCP | `FakeAdapter` obbligatorio; altri → `REAL_PROVIDER_DISABLED` |
| pin del Core | `9afaddf` (presunto) | `819e7cf` richiesto; `9afaddf` → `STALE_CORE_PIN` |
| esito riferito | stato in memoria | stato **riletto dallo store** dopo `run_job` |
| risposta incerta al submit | non nota | `SUBMIT_UNKNOWN` (Core), nessun retry, budget mantenuto |
| restart | non nota | nuovo processo riprende lo stesso job dal file (T09) |

## File del candidate (hash SHA256 in `SHA256SUMS`)

| file | ruolo |
|---|---|
| `runtime/core_pin.py` | gate del pin: OK / STALE / MISMATCH, prima dell'import |
| `runtime/provider_gate.py` | fake mode fail-closed |
| `runtime/genspec_bridge.py` | `GoInputs` → `GenSpec`, rifiuto dei dati accidentali |
| `runtime/go_candidate.py` | il verbo `go` candidato; `ReservationObserver` (proxy di sola delega) |

## Cosa il diff reale dovrà mostrare (prossimo gate)

Nella copia `runtime/hf_batch_runtime.py`: rimozione del blocco find-then-submit e del
submit diretto nel verbo `go`, sostituiti da una sola chiamata a `go_candidate.go(...)`;
aggiornamento consapevole del pin; nessun'altra modifica.
