# BASELINE PAIR — Core / Runtime

| Repo | Branch | SHA | Ruolo |
|---|---|---|---|
| `Frantonaccio/creative-os` | `main` | `740ee979300fe20a9382992528604dee70cb2fcf` | Core canonico, **invariato** in questa fase (nessun branch Core creato; HEAD e working tree verificati prima e dopo: B00/B11, regressione T17/T20) |
| `Frantonaccio/esercitazioni` | `main` | `39c82968fbfb3f3b7ba9fcfe9dc317ea0da9e74e` | Runtime canonico di partenza (baseline R0-R1 merged) |
| `Frantonaccio/esercitazioni` | `claude/provider-boundary-hardening-c1k77q` | (SHA del commit candidato: vedi `MANIFEST.json`, campo `runtime_candidate_sha`, se popolato al momento della consegna) | Runtime candidato di questa fase, discende da `39c82968` |

Pin Runtime → Core: `REQUIRED_CORE_SHA = "740ee979300fe20a9382992528604dee70cb2fcf"` (`runtime/core_pin.py`), invariato.
Nessuna scrittura su `main`. Nessun merge, tag, release, deploy, force-push.
