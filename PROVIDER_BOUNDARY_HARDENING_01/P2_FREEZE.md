# P2 FREEZE — before == after

| File | SHA256 |
|---|---|
| `RUNTIME_INTEGRATION_GATE_01/p2_handoff/VF_RUNTIME_T16_HANDOFF_2026-09-16/P2_RUNTIME/hf_batch.py` (before, Reality Lock) | `637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1` |
| stesso file (after, B11) | `637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1` |
| `…/LAB/hf_batch_ORIGINAL.py` (after, B11) | `637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1` |
| dichiarato dal mandato | `637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1` |

P2 resta FROZEN. Nessuna migrazione retroattiva di `hf_batch.py`. Il runtime non lo importa ne' lo esegue (B07).
Evidenza: `evidence/B00_reality_lock.json`, `evidence/B11_p2_freeze_core_pin_after.json`, regressione T16.
