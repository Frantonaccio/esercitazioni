# RUNTIME DIFF COORDINATO — NG-05

Base: reviewed head `4a73cdad18034e7c1bd9842a37e34e0273f9325a`.
Branch: `integrate/provider-boundary-core-runtime-2026-09-17`.

```
 RUNTIME_INTEGRATION_GATE_01/runtime/core_pin.py     | 18 ++++--
 RUNTIME_INTEGRATION_GATE_01/runtime/go_candidate.py | 63 +++++++++++-----------
 2 files changed, 46 insertions(+), 35 deletions(-)
```

Due file. Nessun altro file del **codice funzionale** del Runtime è stato toccato.

---

## 1. `runtime/go_candidate.py` — consumo dell'API approvata

`ReservationObserver._refuse_pre_submit`, l'unico punto che chiude un rifiuto pre-submit.

**Rimosso** (due transazioni):

```python
self._inner.reconcile(job, type(job.state)("FAILED"), evidence, now=now)
report["terminalized"] = True
...
if report["terminalized"]:
    report["settlement"] = self._inner.settle(job.job_id, units=0,
                                              source=PRE_SUBMIT_REFUSAL_SOURCE, now=now)
    report["settled"] = True
```

**Aggiunto** (una transazione):

```python
self._inner.mark_refused_pre_submit(
    job, reason, source=PRE_SUBMIT_REFUSAL_SOURCE, evidence=evidence,
    now=now if now is not None else self._snapshot.clock())
report.update(terminalized=True, settled=True, atomic=True)
```

Cosa **non** è cambiato, deliberatamente:

- l'osservazione fail-closed che dimostra `NOT_DISPATCHED`
  (`SnapshotBinding.observe_not_dispatched` + `not_dispatched`): se i fatti osservati non
  provano che nessun invio è possibile, il runtime **non terminalizza e non regola nulla** e
  registra `PRE_SUBMIT_REFUSAL_NOT_PROVABLE`;
- la provenance `RUNTIME_PRE_SUBMIT_REFUSED_NOT_DISPATCHED` e il
  `remote_ref = none:never_dispatched`;
- l'evidenza allegata, con i fatti osservati e `transport_attestation: null`;
- l'anomalia `SNAPSHOT_REFUSED_PRE_SUBMIT` con il report completo;
- il divieto di `TRANSPORT_ATTESTED_NOT_SENT` su questo percorso.

Il report del runtime guadagna due campi osservabili: `atomic: true` e
`core_api: "mark_refused_pre_submit"`. Servono al gate per verificare *quale* percorso è stato
davvero usato, invece di dedurlo.

Il ramo di errore si semplifica: con una sola transazione non esiste più un passo intermedio da
riparare. `StaleWrite` / `TransitionRefused` significano che **nulla** è stato applicato.

## 2. `runtime/core_pin.py` — il pin segue l'API

```python
-REQUIRED_CORE_SHA = "740ee979300fe20a9382992528604dee70cb2fcf"
+REQUIRED_CORE_SHA = "9cf9cee1a751f7a2ad6c768574ff5aa38d8db515"

 KNOWN_STALE_CORE_SHAS = frozenset({
     "9afaddf3cec1e8baf9600ed8dc0461e7adccb5c7",   # commit iniziale del Core
+    "740ee979300fe20a9382992528604dee70cb2fcf",   # baseline precedente: PADRE del candidate
 })
```

Perché la baseline entra fra i pin **stantii** e non resta un mismatch generico: un runtime che
consuma `mark_refused_pre_submit` contro il Core `740ee979` fallirebbe con `AttributeError` a
metà percorso, dopo l'import e dopo aver aperto lo store. Classificarla come *vecchia* fa
fallire il gate **prima dell'import**, con un codice che dice il perché.

### Matrice del pin, verificata (D01)

| situazione | esito |
|---|---|
| Core candidate, tree pulito | `CORE_PIN_OK` |
| Core baseline `740ee979` | `STALE_CORE_PIN` |
| Core candidate con un file non tracciato | `CORE_WORKTREE_DIRTY` |
| path inesistente | `CORE_PIN_MISMATCH` |
| SHA arbitrario (funzione pura) | `CORE_PIN_MISMATCH` |
| candidate di nuovo pulito | `CORE_PIN_OK` |

`go()` contro la baseline vecchia: rifiutato con `STALE_CORE_PIN`, **senza creare lo store** e
senza importare il Core.

## 3. Cosa NON è stato modificato

| | |
|---|---|
| Core candidate `9cf9cee1` | invariato. Nessun `APPROVED_CORE_CANDIDATE_INSUFFICIENT`: l'API approvata è bastata. |
| Core `main` | invariato, tree pulito |
| `runtime/payload_snapshot.py` | invariato: il guard P-B04 e i fatti osservati sono quelli approvati |
| `runtime/reconciliation.py` | invariato: NG-04 e P-B02 restano quelli approvati |
| `runtime/orphan_lease.py` | invariato: il reclaim conserva la propria sequenza a due transazioni, requisito separato |
| `runtime/provider_gate.py`, `authorization.py`, `genspec_bridge.py`, `hf_batch_*.py` | invariati |
| `tests/` del gate storico, `boundary_mock.py`, `run_gate.py` | invariati: nessun test storico indebolito |
| `PROVIDER_BOUNDARY_GATE_02/`, `PROVIDER_BOUNDARY_HARDENING_01/` | invariati (verificato da D11) |
| P2 frozen | invariato |

## 4. Contratto statico

`tests/static_checks.run(<core candidate>)` → `ok: true`, 0 findings: il runtime usa solo metodi
e argomenti dichiarati dal Protocol del Core candidate (CR-03). Contro il Core baseline lo stesso
controllo fallirebbe — ed è esattamente perché il pin si è spostato.
