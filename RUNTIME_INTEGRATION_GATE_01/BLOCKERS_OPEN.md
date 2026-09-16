# BLOCKERS_OPEN — stato a fine RUNTIME INTEGRATION GATE 01 (resume da handoff P2)

Nessuno dei blocker di prodotto è stato chiuso da questo gate. Il blocker di ambiente P2-ABSENT è chiuso.

| ID | titolo | stato | cosa questo gate ha fatto | cosa NON ha fatto |
|---|---|---|---|---|
| **P-B01** | credential isolation | **APERTO** | in FAKE MODE nessuna lettura di `~/.higgsfield/credentials.json`, nessuna env segreta, nessun subprocess provider, nessuna rete (T14/T15/T22, sentinella con esca e controprova); `lock`/`quote` della copia → `REAL_PROVIDER_DISABLED` prima di ogni subprocess | nessun isolamento reale delle credenziali del provider |
| **P-B02** | remote reconciliation | **APERTO** | `SUBMIT_UNKNOWN` persistito e rispettato: nessun resubmit, nessuna nuova reservation, budget mantenuto (T10); il `CLIENT_FAILED_CHECK_SERVER` dell'originale mappa qui | nessun lookup remoto reale |
| **P-B03** | economic ledger | **APERTO** | meccanica mock: `budget_units`/`envelope_units` passano al Core (T12/T13); design requirement sotto | nessun ledger; nessun valore Higgsfield/Meta/authority nel Core; il saldo CLI dell'originale non è sostituito |
| **P-B04** | byte/ref safety | **APERTO** | catena di hash mantenuta: Core SHA, hash dei file runtime (SHA256SUMS), `spec_key`, refs con `sha256_sent` reali dei media (T21), hash payload fake (T06) | nessuno snapshot byte-exact di un submit reale; `urlretrieve`/`output.sha256` dell'originale non reimplementati (spetta a `transport.pipeline.ingest`) |
| **G-N02** | semantic claim paraphrase gap | **APERTO** | nulla: gate Runtime/C26 | — |
| ~~P2-ABSENT~~ | P2 non disponibile | **CHIUSO** (handoff `VF_RUNTIME_T16_HANDOFF_2026-09-16.zip`, SHA `7d7c93af…0512`) | T16 chiuso, mapping reale (T21), copia candidate provata (T22), integrità handoff (T23) | — |

## Punti da decidere in review (non blocker, ma differenze semantiche)

1. "1 tentativo, mai sovrascrivere" era una guardia sul file: nel candidate l'identità è del Core e un nuovo `go` dopo
   un terminale è un nuovo tentativo autorizzato (C26-E). Dove vive la regola "batch concluso non si rigenera"?
2. `role_in_run` del Core nel lock P2 era "nessuno per la generazione"; nel candidate il Core **è** il control plane
   della generazione. Il lock preventivo (`fingerprint`) resta accanto, non sopra.
3. `vf-tenant-valorefarmacia/TENANT_CONFIG.json` dichiara ancora `CORE_DEPENDENCY_COMMIT_SHA = 9afaddf`: mandato tenant separato.

## Economic Autonomy Model — DESIGN REQUIREMENT (non implementato)

```
authorized_envelope      → envelope_units passato a reserve_or_get_live
target_budget
tactical_reserve_pct     → riduce l'envelope effettivo prima della chiamata al Core
reserved_units           → già: SqliteReservationStore.reserved_units()
actual_units             → da Job.cost_credits al terminale
released_units           → reserved - actual sul terminale
classificazioni: CREATIVE_ITERATION · PREVENTABLE_WASTE · TECHNICAL_FAILURE
```

Il Core conosce solo unità intere non negative e invarianti. Le policy (11.000 crediti Higgsfield, 1.500/video,
25% reserve, Meta Ad budget, authority budget) restano nella Production Policy futura. Nessuna di queste cifre è
entrata nel Core né nel runtime candidate.
