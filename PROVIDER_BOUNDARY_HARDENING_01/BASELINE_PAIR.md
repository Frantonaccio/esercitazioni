# BASELINE PAIR — Core / Runtime · REFERENCE NON AMBIGUE (bundle v2)

## Coppia canonica (invariata)
| Repo | Branch | SHA | Ruolo |
|---|---|---|---|
| `Frantonaccio/creative-os` | `main` | `740ee979300fe20a9382992528604dee70cb2fcf` | **Core canonico**, invariato: nessun branch Core creato, nessuna write. HEAD e working tree verificati prima (B00) e dopo (B11), piu' regressione T17/T20. |
| `Frantonaccio/esercitazioni` | `main` | `39c82968fbfb3f3b7ba9fcfe9dc317ea0da9e74e` | **`canonical_runtime_base_sha`**: baseline R0-R1 merged da cui discende il candidato. `main` non e' stato toccato. |

## Reference del candidato (richieste da Human Review 01)
| Nome | Significato | Dove e' dichiarato |
|---|---|---|
| `runtime_branch` | branch di lavoro: `claude/provider-boundary-hardening-c1k77q` | `MANIFEST.json`, `PROVENANCE.json` |
| `canonical_runtime_base_sha` | `39c82968fbfb3f3b7ba9fcfe9dc317ea0da9e74e` (Runtime `main`) | `MANIFEST.json`, `PROVENANCE.json` |
| `runtime_code_sha` | commit che contiene **codice + evidenza + documenti** di questo bundle | `MANIFEST.json` (lo cita: il manifest e' nel commit successivo) |
| `runtime_evidence_head_sha` | HEAD del branch dopo il commit che aggiunge `MANIFEST.json` e `SHA256SUMS` | **`PROVENANCE.json`** (file esterno, generato DOPO quel commit: nessuna self-reference impossibile) |

Perche' due commit: un manifest che dichiarasse il proprio commit sarebbe self-referenziale. Il commit del codice
(`runtime_code_sha`) e' citato dal manifest; l'HEAD finale (`runtime_evidence_head_sha`) e' dichiarato solo nel file
esterno `PROVENANCE.json`, incluso nello ZIP con il proprio `SHA256SUMS.EXTERNAL`.

Nessun merge, tag, release, deploy, force-push. Pin Runtime → Core invariato:
`REQUIRED_CORE_SHA = "740ee979300fe20a9382992528604dee70cb2fcf"` (`runtime/core_pin.py`).
