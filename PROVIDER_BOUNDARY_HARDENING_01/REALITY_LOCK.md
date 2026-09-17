# REALITY LOCK — PROVIDER / EXECUTION BOUNDARY HARDENING (2026-09-17)

Eseguito PRIMA di qualunque modifica. Stato reale verificato via git, non via documenti.

| Check | Atteso | Osservato | Esito |
|---|---|---|---|
| Core `Frantonaccio/creative-os` branch | `main` | `main` (clone fresco, `git branch --show-current`) | OK |
| Core HEAD | `740ee979300fe20a9382992528604dee70cb2fcf` | `740ee979300fe20a9382992528604dee70cb2fcf` | OK |
| Core working tree | pulito | `git status --porcelain` vuoto | OK |
| Runtime `Frantonaccio/esercitazioni` `origin/main` | `39c82968fbfb3f3b7ba9fcfe9dc317ea0da9e74e` | `39c82968fbfb3f3b7ba9fcfe9dc317ea0da9e74e` (`git fetch origin main`) | OK |
| Runtime checkout di partenza | == `origin/main` | HEAD `39c82968…` sul branch di sessione `claude/provider-boundary-hardening-c1k77q`, `origin/main..HEAD` vuoto | OK |
| Runtime working tree | pulito | `git status --porcelain` vuoto | OK |
| Commit locali non pubblicati che cambiano la baseline | nessuno | nessuno | OK |
| `REQUIRED_CORE_SHA` in `RUNTIME_INTEGRATION_GATE_01/runtime/core_pin.py:34` | `740ee979300fe20a9382992528604dee70cb2fcf` | `740ee979300fe20a9382992528604dee70cb2fcf` | OK |
| P2 frozen `p2_handoff/…/P2_RUNTIME/hf_batch.py` (before) | `637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1` | `637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1` (anche `LAB/hf_batch_ORIGINAL.py`) | OK |
| Handoff ZIP | SHA256 `d5f4985803053d8c7e0bdb7aa2caf4258c46615086dc2b67bc1c7e4292383186` | identico; `sha256sum -c SHA256SUMS` interno: 7/7 OK | OK |

Nessuna divergenza: nessun `CANONICAL_BASELINE_DRIFT`.

Note operative (non divergenze):
- Il Core e' stato clonato shallow e poi approfondito (`git fetch --depth=1000 origin main`, 15 commit) perche' T03/T20 del gate storico creano un worktree sul commit stale `9afaddf`. HEAD e working tree invariati.
- Branch git di lavoro: `claude/provider-boundary-hardening-c1k77q` (branch designato dalla sessione; il nome consigliato nel mandato `harden/provider-boundary-runtime-2026-09-17` non e' stato usato perche' la sessione ha un branch di destinazione vincolato). Nessuna scrittura su `main`.
- Nessun branch Core creato: il Core NON cambia in questa fase.
