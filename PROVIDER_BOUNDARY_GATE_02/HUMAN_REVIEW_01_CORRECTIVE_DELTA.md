# DELTA CORRETTIVO — HUMAN REVIEW 01

Verdetto ricevuto:

```
HUMAN_REVIEW_HOLD — EVIDENCE_CHAIN_AND_CORE_RUNTIME_PAIR_NOT_READY
```

Questo delta è **reporting/evidence-only**. Non riapre il lavoro funzionale già verificato,
non modifica i meccanismi approvati, non mergia nulla, non inizia l'integrazione Core+Runtime.

## Cosa NON è stato toccato

| approvato dalla review | stato |
|---|---|
| `P_B02_P_B01_COMPOSITION = VERIFIED_LAB` | invariato |
| `RECONCILIATION_FRESHNESS_NG04_MECHANISM = VERIFIED_LAB` | invariato |
| `ORPHAN_RESERVED_LEASE_MECHANISM = VERIFIED_LAB` | invariato |
| `LEGACY_SPEND_PATHS_RUNTIME_CLOSURE = VERIFIED_LAB` | invariato |
| NG-05 Core delta | invariato: `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` |
| regressione R0-R1 | invariata: 36/37 PASS, 0 FAIL, T29 `BLOCKED_ENVIRONMENT` per policy |
| P2 frozen | invariato: `637f3a80…` |
| Core pin baseline | invariato: `740ee979…` |

**Diff funzionale del Runtime: zero righe cambiate.** I 4 file rivisti dalla Human Review
(`runtime/reconciliation.py`, `runtime/orphan_lease.py`, `runtime/provider_gate.py`,
`tests/worker.py`) non sono stati toccati da questo delta: sono ancora quelli del commit
`runtime_code_sha`. Verificato da C11 (§ Regressione del delta).

---

# BLOCKER 1 — EVIDENCE CHAIN AMBIGUOUS

## Il difetto, riconosciuto

1. `MANIFEST.json` era dentro lo ZIP e **non** era coperto da `SHA256SUMS`.
2. Il manifest dichiarava `runtime_commit = e845b744a4af3a143b1b1e710016726c57ad6c39`.
3. Il branch remoto puntava a `555e1f4819ca076f535bab008c8f619d9cacf114`.
4. I due SHA erano legittimamente diversi (`555e1f48` aggiunge manifest e checksum), ma il
   nome generico `runtime_commit` non lo diceva.

Il rilievo è corretto: fra tre settimane nessuno deve dover fare archeologia su Git per
capire quale dei due SHA porta il codice.

## La correzione

### La catena, non self-referenziale

Il vincolo di fondo: **un manifest committato non può dichiarare lo SHA del commit che lo
contiene.** Fingere di saperlo è esattamente ciò che ha prodotto l'ambiguità. La catena si
spezza quindi in due livelli, e il secondo vive fuori dal repository.

```
1. COMMIT CODICE      runtime_code_sha
   diff funzionale del Runtime — ciò che la Human Review ha revisionato

2. COMMIT EVIDENCE    runtime_evidence_head_sha
   aggiunge MANIFEST.json + SHA256SUMS + i documenti di questo delta
   MANIFEST.json dichiara runtime_code_sha (lo conosce)
   MANIFEST.json NON dichiara runtime_evidence_head_sha, e lo dice:
       "runtime_evidence_head_sha": "DECLARED_IN_EXTERNAL_PROVENANCE"

3. PROVENANCE.json    ESTERNA, generata DOPO il commit evidence, MAI committata
   è l'unico posto in cui i due SHA compaiono insieme, con lo SHA256 dello ZIP,
   di MANIFEST.json e di SHA256SUMS

4. SHA256SUMS.EXTERNAL  copre PROVENANCE.json e lo ZIP
```

### Chiavi disambiguate nel manifest

| chiave | significato |
|---|---|
| `runtime_code_sha` | commit con il diff **funzionale** del Runtime |
| `runtime_evidence_head_sha` | `DECLARED_IN_EXTERNAL_PROVENANCE` (valore reale nella provenance esterna) |
| `runtime_branch` | `claude/provider-boundary-gate-closure-gd6b3g` |
| `canonical_runtime_base_sha` | `0698279703ab959625ac4e84ee636bc5b93b45fd` |

La chiave generica **`runtime_commit` è bandita**: il verificatore la rifiuta con
`AMBIGUOUS_MANIFEST_KEY`.

### Copertura di `SHA256SUMS`

`SHA256SUMS` copre **ogni file committato del bundle, incluso `MANIFEST.json`**, escluso
soltanto se stesso (unico file che non può coprirsi). Gli artefatti esterni
(`PROVENANCE.json`, `SHA256SUMS.EXTERNAL`) non sono committati e non vi compaiono.

Ordine di generazione, perché i checksum siano veri: si scrive il manifest, **poi** si
calcolano i checksum, **poi** si committa. Qualunque scrittura successiva li invaliderebbe.

### Il test automatico richiesto

`pbg2/bundle_provenance.py:verify` — verificatore fail-closed, esercitato da **C10** con 12
controprove su bundle finti, uno rotto per volta:

| caso | codice atteso e osservato |
|---|---|
| bundle ben formato | *nessun problema* |
| file committato non in `SHA256SUMS` | `MISSING_FROM_SUMS` |
| checksum extra | `EXTRA_IN_SUMS` |
| mismatch | `CHECKSUM_MISMATCH` |
| **`MANIFEST.json` non coperto** (il difetto del package v1) | `MANIFEST_NOT_COVERED`, `MISSING_FROM_SUMS` |
| chiave ambigua `runtime_commit` | `AMBIGUOUS_MANIFEST_KEY` |
| chiave disambiguata mancante | `MANIFEST_KEY_MISSING` |
| **`runtime_code_sha == runtime_evidence_head_sha`** | `CODE_SHA_EQUALS_EVIDENCE_HEAD` |
| **HEAD del branch ≠ `runtime_evidence_head_sha`** | `HEAD_NOT_EVIDENCE_HEAD` |
| provenance coerente con HEAD reale | *nessun problema* |
| `merge_readiness` assente | `MERGE_READINESS_MISSING` |
| `merge_authorized=true` senza coppia pronta | `MERGE_AUTHORIZED_WITHOUT_PAIR` |

Gli SHA usati nei casi 8 e 9 sono **reali** e in relazione di discendenza, così l'unico
difetto misurato è quello che il caso vuole misurare.

Lo stesso verificatore gira sul bundle **vero** in `pbg2/make_bundle.py package`, dopo il
commit evidence, contro i file realmente tracciati da Git (`git ls-files`), e il suo esito
finisce dentro `PROVENANCE.json` (`bundle_verification`).

### Procedura di confezionamento

```bash
python3 pbg2/run_gate2.py            # C00..C10
python3 pbg2/make_bundle.py manifest # MANIFEST.json, poi SHA256SUMS
git add -A && git commit             # -> runtime_evidence_head_sha
python3 pbg2/make_bundle.py package  # verifica + ZIP + PROVENANCE.json + SHA256SUMS.EXTERNAL
```

`runtime_code_sha` non è scritto a mano: è derivato da Git come l'ultimo commit che tocca
`RUNTIME_INTEGRATION_GATE_01/runtime/` o `RUNTIME_INTEGRATION_GATE_01/tests/`.

---

# BLOCKER 2 — CORE/RUNTIME PAIR NON PROMOVIBILE

## Accettato senza riserve

Il Core candidate `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` è
**`APPROVED_PROPOSAL — NOT_MERGE_AUTHORIZED`**.

Il ragionamento della review è corretto e non c'è nulla da difendere: il Runtime candidate
resta pinnato a `740ee979`, continua deliberatamente a usare `reconcile → settle` e **non**
usa `mark_refused_pre_submit`. Portare Core `main` a `9cf9cee1` renderebbe la baseline
incoerente **per costruzione**: il Runtime canonico pretenderebbe ancora il vecchio SHA.

Core `main` non è stato toccato. Nessun merge è stato eseguito né preparato.

## `merge_readiness` — machine-readable

Aggiunta a `pbg2/readiness.py`, presente in `READINESS.json`, `evidence/RESULTS.json`,
`MANIFEST.json`, `PROVENANCE.json` e `TEST_RESULTS.md` sezione C. **Ogni campo è calcolato
da fatti osservati**, nessuno è asserito a mano.

| campo | valore | perché |
|---|---|---|
| `runtime_candidate_ready` | `true` | test tutti PASS, Reality Lock, R0-R1 e P2 freeze verificati |
| `core_candidate_ready` | `true` | branch dedicato, base canonica, tree pulito, 9/9 suite PASS |
| **`core_runtime_pair_ready`** | **`false`** | il Runtime non consuma il Core candidate e il pin punta alla baseline |
| **`merge_authorized`** | **`false`** | coppia non pronta, requisiti aperti, nessuna autorizzazione umana |

`blockers`:
`RUNTIME_DOES_NOT_CONSUME_CORE_CANDIDATE`, `REQUIRED_CORE_SHA_PINNED_TO_BASELINE_NOT_CANDIDATE`,
`OPEN_REQUIREMENTS`, `HUMAN_MERGE_AUTHORIZATION_ABSENT`.

### Invarianti fail-closed

`readiness.validate` solleva `ReportingInconsistent` se:

- `merge_authorized=true` con `core_runtime_pair_ready=false`;
- `merge_authorized=true` con requisiti aperti;
- `merge_authorized=true` senza `human_merge_authorization` esplicita — che il codice **non
  si concede mai**;
- `core_runtime_pair_ready=true` mentre il Runtime non consuma il candidate o il pin non vi
  punta;
- `merge_authorized=false` senza `blockers` dichiarati.

Cinque controprove in C09 (11 in totale sul reporting), tutte sollevano.

## Integrazione coordinata: documentata, NON iniziata

In `merge_readiness.next_integration_required`, nell'ordine dato dalla review:

1. partire dal Core candidate approvato `9cf9cee1…`;
2. aggiornare il Runtime perché consumi `mark_refused_pre_submit`;
3. aggiornare `REQUIRED_CORE_SHA` al nuovo Core candidate SHA;
4. rimuovere il percorso `reconcile → settle` per il caso NG-05;
5. dimostrare atomicità end-to-end Runtime → Core;
6. rieseguire NG-03 provenance, NG-05 atomicity, P-B04 snapshot, P-B01/P-B02 composition,
   R0-R1, P2 freeze;
7. produrre una coppia candidate Core+Runtime **indivisibile** per Human Review.

`not_implemented_here`: questo delta è reporting/evidence-only. Nessuno dei sette punti è
stato eseguito.

---

# POLICY DECISIONS — invariate

Nessun valore è stato scelto. `RECONCILIATION_FRESHNESS_NG04_POLICY` e
`ORPHAN_RESERVED_LEASE_POLICY` restano **`POLICY_DECISION_REQUIRED`**.

Il codice non contiene 30 secondi, 60 secondi, 5 minuti, 1 ora né alcun altro valore: i
parametri usati nei test si chiamano `LAB_TEST_PARAMETER_NOT_A_POLICY_DECISION` e
`LAB_GATE_PARAMETER_NOT_A_POLICY_DECISION`, e il daemon spender li riceve come argomenti
**obbligatori** da riga di comando.

# LEGACY CORE PRIMITIVES — invariati

`LEGACY_SPEND_PATHS_CORE_PRIMITIVES = CORE_CHANGE_REQUIRED`
`LEGACY_TESTS_MIGRATION_TO_GOVERNED = STILL_OPEN`

Sono problemi **distinti** da NG-05 e il Core delta non li risolve. Nessun documento di
questo bundle sostiene il contrario.

---

# REPORTING

```
all_tests_passed          = true      (11/11 PASS, 0 FAIL, 0 BLOCKED, inventario 11/11 valido)
all_requirements_verified = false
phase_gate_decision       = LAB_GATE_COMPLETE_WITH_OPEN_GAPS
max_state                 = PROVIDER_BOUNDARY_GATE_PRE_REAL_READY_FOR_HUMAN_REVIEW
                            ^ stato di LAVORO con open gaps, NON merge authorization
core_runtime_pair_ready   = false
merge_authorized          = false
```

# REGRESSIONE DEL DELTA CORRETTIVO

Verificata da **C11**:

| verifica | esito |
|---|---|
| diff funzionale del Runtime identico a quello revisionato | ✓ (0 righe cambiate in `runtime/` e `tests/` dopo `runtime_code_sha`) |
| Core candidate identico a `9cf9cee1…` | ✓ |
| Runtime branch code commit invariato | ✓ |
| Core `main` invariato | ✓ `740ee979`, tree pulito |
| Runtime `main` invariato | ✓ `0698279` |
| P2 invariato | ✓ `637f3a80` |
| nessun provider, nessuna credenziale, nessuna spesa | ✓ |

# CONSEGNA

Bundle v2 con manifest corretto, `SHA256SUMS` completo, provenance esterna,
`SHA256SUMS.EXTERNAL`, riferimenti code/evidence-head non ambigui, `merge_readiness`
strutturata, open requirements invariati, Core proposal chiaramente non merge-authorized.

**Non mergiato. Integrazione Core+Runtime non iniziata. STOP.**
