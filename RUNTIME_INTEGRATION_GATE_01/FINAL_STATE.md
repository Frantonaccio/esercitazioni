# FINAL_STATE — RUNTIME INTEGRATION GATE 01

## STATUS: **BLOCKED**

Motivo unico: **P2 non è disponibile in questo ambiente**. `hf_batch.py`, `gate01_lab.py` e
`control.py` non esistono nel container né in alcun repository raggiungibile. Senza il file reale:
- T16 (P2 hash before/after) non è calcolabile;
- il binding reale `go → GoInputs` (GENSPEC_MAPPING) non è derivabile;
- `runtime/hf_batch_runtime.py` non può essere una copia di nulla;
- il PIN_AUDIT sui tre file resta NOT_VERIFIABLE.

Tutto ciò che dipende dal solo Core è **costruito, provato e verde**: il candidate `go` consuma
il Core C26 senza duplicarlo e si comporta correttamente sotto concorrenza (2 processi),
crash/restart e risposta incerta, senza poter toccare un provider reale.

`READY_FOR_RUNTIME_INTEGRATION_REVIEW` **non** è dichiarato: il mandato lo lega alla verifica di
P2 (§24: "se P2 cambia → BLOCKED anche se tutti i test runtime sono verdi"; qui P2 non è
verificabile affatto).

## Stato finale verificato

| voce | valore |
|---|---|
| Core canonical HEAD | `819e7cfedb0f6641dc797e7993bec79462ac8df6` · `main` · working tree pulito (T17) |
| Core canonical modificato dal lavoro funzionale | **no** (0 file) |
| worktree temporaneo `9afaddf` (T03) | creato e rimosso nella stessa corsa; `git worktree list` = canonical + cleanup |
| Core typing cleanup | branch `chore/pipeline-reservationstore-annotation`, commit `6b0eae80…`, 8 suite exit 0, **NOT MERGED** |
| P2 `hf_batch.py` SHA256 before / after | **non calcolabile / non calcolabile** (file assente) · 0 file P2 modificati (nessun file P2 presente) |
| matrice | 18/19 PASS · T16 BLOCKED · 0 FAIL (`TEST_RESULTS.md`) |
| provider usato | `FakeAdapter` (Core) e sottoclassi di laboratorio `fake_a`/`fake_b`/`UnknownSubmitFake` |
| crediti spesi | 0 |
| Higgsfield (CLI, MCP, credenziali, rete) | mai invocato, mai letto, mai aperto (T14/T15 con sentinella) |
| store durevole | `SqliteReservationStore` in `state/*.db`, solo laboratorio |

## Cosa serve per riaprire il gate e arrivare a READY_FOR_RUNTIME_INTEGRATION_REVIEW

Una sola cosa: **rendere leggibile P2** nella sessione (copia in sola lettura di `hf_batch.py`,
`gate01_lab.py`, `control.py`, con il loro SHA256 calcolato sull'originale). Con quei file:
1. calcolare il full SHA256 di `hf_batch.py` e confrontarlo con `637f3a80…`;
2. compilare GENSPEC_MAPPING con la provenienza reale dei sei campi;
3. creare `runtime/hf_batch_runtime.py` come copia e innestare `go_candidate.go`;
4. completare PIN_AUDIT sui tre file e rieseguire la matrice (T16 incluso).

Nessun'altra parte del package deve essere rifatta.

## Stati NON dichiarati

PRODUCTION_READY · LIVE_ENABLED · PROVIDER_ENABLED · HIGGSFIELD_READY · DEPLOYED — nessuno.
