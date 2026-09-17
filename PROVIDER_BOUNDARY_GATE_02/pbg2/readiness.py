"""AUTHORITY UNICA DI CLASSIFICAZIONE — PROVIDER BOUNDARY GATE / OPEN-GAP CLOSURE.

Conserva l'invariante fail-closed introdotta nella fase precedente
(`PROVIDER_BOUNDARY_HARDENING_01/pbgate/phase_readiness.py`) e la estende agli stati
che questa fase richiede. Le due domande restano SEMPRE separate:

    A. TEST SUITE RESULT   — i test del gate hanno prodotto l'esito atteso?
    B. PHASE READINESS     — i requisiti della fase sono davvero chiusi?

Un test PASS puo' verificare che un requisito resta APERTO: `C05 PASS` significa
"il gate ha verificato che il MECCANISMO di lease esiste e che la POLICY resta una
decisione umana", non "l'orphan lease e' chiuso".

`all_requirements_verified = true` e' ammesso SOLO quando nessun requisito imputabile a
questa fase o al Provider Boundary Gate e' aperto E tutti i test sono PASS. Non esiste
nessun percorso che produca "tutto verificato" mentre un requisito e' aperto: `validate`
solleva `ReportingInconsistent` e il report diventa invalido.

Lo stato dichiarato di ogni requisito NON e' scritto a mano: e' `declared` solo se i test
che lo sostengono sono PASS, altrimenti degrada a `fallback` (sempre uno stato aperto).
"""
from __future__ import annotations

# ---------------------------------------------------------------- stati dei requisiti
VERIFIED_LAB = "VERIFIED_LAB"                                  # chiuso nel perimetro LAB di questa fase
STILL_OPEN = "STILL_OPEN"                                      # aperto
BLOCKED_PROVIDER_GATE = "BLOCKED_PROVIDER_GATE"                # da chiudere prima del Provider Boundary Gate
OPEN_CONSERVATIVE_LIMITATION = "OPEN_CONSERVATIVE_LIMITATION"  # limite noto, comportamento conservativo
NOT_VERIFIED = "NOT_VERIFIED"                                  # non dimostrato dai test correnti
NOT_RUN = "NOT_RUN"                                            # non eseguito in questa fase
POLICY_DECISION_REQUIRED = "POLICY_DECISION_REQUIRED"          # meccanismo pronto, valore/attore da decidere
REAL_PROVIDER_REQUIRED = "REAL_PROVIDER_REQUIRED"              # chiudibile solo con provider reale
CREDENTIAL_REQUIRED = "CREDENTIAL_REQUIRED"                    # chiudibile solo con credenziali reali
CORE_CHANGE_REQUIRED = "CORE_CHANGE_REQUIRED"                  # richiede una modifica del Core, non mergiata
BLOCKED_ENVIRONMENT = "BLOCKED_ENVIRONMENT"                    # l'ambiente non consente la dimostrazione

REQUIREMENT_STATES = (VERIFIED_LAB, STILL_OPEN, BLOCKED_PROVIDER_GATE, OPEN_CONSERVATIVE_LIMITATION,
                      NOT_VERIFIED, NOT_RUN, POLICY_DECISION_REQUIRED, REAL_PROVIDER_REQUIRED,
                      CREDENTIAL_REQUIRED, CORE_CHANGE_REQUIRED, BLOCKED_ENVIRONMENT)
OPEN_STATES = tuple(s for s in REQUIREMENT_STATES if s != VERIFIED_LAB)

# ---------------------------------------------------------------- decisioni (separate)
TEST_SUITE_ALL_PASS = "ALL_TESTS_PASS"
TEST_SUITE_FAILED = "TESTS_FAILED"
TEST_SUITE_BLOCKED = "TESTS_BLOCKED_BY_ENVIRONMENT"
TEST_SUITE_INVALID = "TEST_INVENTORY_INVALID"

PHASE_COMPLETE_WITH_OPEN_GAPS = "LAB_GATE_COMPLETE_WITH_OPEN_GAPS"
PHASE_COMPLETE_ALL_VERIFIED = "LAB_GATE_COMPLETE_ALL_VERIFIED"
PHASE_NOT_FAVORABLE = "PHASE_GATE_NOT_FAVORABLE"
PHASE_INVALID = "PHASE_GATE_INVALID"

MAX_STATE = "PROVIDER_BOUNDARY_GATE_PRE_REAL_READY_FOR_HUMAN_REVIEW"
NOT_READY = "NOT_READY"
PHASE_DECISIONS_ALLOWING_MAX_STATE = (PHASE_COMPLETE_ALL_VERIFIED, PHASE_COMPLETE_WITH_OPEN_GAPS)

NOT_IMPLIED = ["provider reale verificato", "provider ready", "production ready",
               "credenziali autorizzate", "spend autorizzato", "merge autorizzato",
               "R2 autorizzato"]


class ReportingInconsistent(RuntimeError):
    """Il report afferma insieme cose incompatibili. Fail-closed: il report e' invalido."""


# ---------------------------------------------------------------- registro dei requisiti
# `scope`: this_phase | future_gate | other_phase. Contano per `all_requirements_verified`
# sia `this_phase` sia `future_gate`. `declared`: stato se TUTTI i test in `evidence_tests`
# sono PASS; `fallback`: stato altrimenti (sempre aperto).
REQUIREMENTS: tuple[dict, ...] = (
    {"id": "REALITY_LOCK_CANONICAL", "scope": "this_phase", "evidence_tests": ("C00",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "Reality Lock: Core/Runtime agli SHA canonici, working tree puliti, pin e P2 invariati",
     "note": "Core 740ee979 · Runtime origin/main 0698279 · REQUIRED_CORE_SHA == Core · P2 637f3a80."},
    {"id": "GAP_MATRIX_PHASE_A", "scope": "this_phase", "evidence_tests": ("C01",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "PHASE A: ogni gap del mandato riprodotto sul Runtime canonico prima di ogni fix",
     "note": "5/5 REPRODUCED con processi reali. Una premessa del mandato (il Core offrirebbe gia' "
             "una primitive atomica) e' risultata FALSA ed e' documentata come tale."},
    {"id": "P_B02_P_B01_COMPOSITION", "scope": "this_phase", "evidence_tests": ("C02",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "P-B02 composta con P-B01: firma e verifica della reconciliation DENTRO lo spender isolato",
     "note": "Segreto di riconciliazione e chiave derivata vivono solo nel daemon spender (UID distinto, "
             "DAC del kernel, SO_PEERCRED); l'orchestrator non li legge, non forgia un report e non si "
             "sostituisce allo spender. NON copre il provider reale."},
    {"id": "RECONCILIATION_FRESHNESS_NG04_MECHANISM", "scope": "this_phase", "evidence_tests": ("C03",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "NG-04 — MECCANISMO di freshness fail-closed e parametrico",
     "note": "`FreshnessPolicy` obbligatoria: assenza = rifiuto. Copre eta' massima, timestamp nel "
             "futuro (clock skew), issued_at assente/malformato, replay nonce e i confini della finestra."},
    {"id": "RECONCILIATION_FRESHNESS_NG04_POLICY", "scope": "future_gate", "evidence_tests": ("C03",),
     "declared": POLICY_DECISION_REQUIRED, "fallback": POLICY_DECISION_REQUIRED,
     "title": "NG-04 — POLICY: valori della finestra (max_age_s, max_future_skew_s)",
     "note": "Nessun valore scelto né suggerito dal codice: nessun 30s/60s/5min. Serve una decisione "
             "umana, vedi NG04_FRESHNESS.md."},
    {"id": "LEGACY_SPEND_PATHS_RUNTIME_CLOSURE", "scope": "this_phase", "evidence_tests": ("C04",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "Legacy spend paths del RUNTIME chiusi fail-closed dalla modalita' Provider Boundary",
     "note": "#2/#4 (go authorization=None e Batch.run_job) e #7 (helper same-UID sullo store) rifiutati "
             "PRIMA di ogni effetto quando la modalita' e' ingaggiata. Inventario riverificato su "
             "Runtime 0698279."},
    {"id": "LEGACY_SPEND_PATHS_CORE_PRIMITIVES", "scope": "future_gate", "evidence_tests": ("C04",),
     "declared": CORE_CHANGE_REQUIRED, "fallback": CORE_CHANGE_REQUIRED,
     "title": "Legacy spend paths #10/#11: primitive del Core raggiungibili senza passare dal Runtime",
     "note": "`transport.pipeline.run_job`, `adapter.submit` e `store.reconcile` raw sono invocabili da "
             "qualunque codice con il Core in sys.path. Nessun interruttore del Runtime li governa: "
             "la sola mitigazione e' il confine di processo P-B01. Chiusura = modifica del Core, "
             "non autorizzata da questo mandato. Vedi LEGACY_SPEND_PATHS_V2.md."},
    {"id": "LEGACY_TESTS_MIGRATION_TO_GOVERNED", "scope": "future_gate", "evidence_tests": ("C04",),
     "declared": STILL_OPEN, "fallback": STILL_OPEN,
     "title": "Migrazione dei test storici T01-T27 al percorso governato",
     "note": "Con la modalita' ingaggiata la suite storica non puo' girare: dipende da LEGACY_LAB. "
             "Chiudere il percorso in modo definitivo richiede prima la migrazione dei test."},
    {"id": "ORPHAN_RESERVED_LEASE_MECHANISM", "scope": "this_phase", "evidence_tests": ("C05",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "Orphan RESERVED lease — MECCANISMO parametrico verificato",
     "note": "Ownership, lease timestamp, lease identity, authority, fencing token + CAS, recovery, "
             "zero blind retry, concorrenza e crash durante il reclaim. Il meccanismo NON sceglie la policy."},
    {"id": "ORPHAN_RESERVED_LEASE_POLICY", "scope": "this_phase", "evidence_tests": ("C05",),
     "declared": POLICY_DECISION_REQUIRED, "fallback": POLICY_DECISION_REQUIRED,
     "title": "Orphan RESERVED lease — POLICY: finestra, attore, evidenze, classi ammesse",
     "note": "`RECLAIM_POLICY = NOT_AUTHORIZED`. Il requisito NON e' chiuso dal fatto che il meccanismo "
             "esista. Vedi ORPHAN_LEASE_MECHANISM_POLICY.md."},
    {"id": "NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY", "scope": "this_phase", "evidence_tests": ("C06",),
     "declared": CORE_CHANGE_REQUIRED, "fallback": CORE_CHANGE_REQUIRED,
     "title": "NG-05 — atomicita' della terminalizzazione pre-submit",
     "note": "Il Core canonico NON offre una primitive a transazione singola con provenance parametrica "
             "(verificato leggendo il contratto reale). Delta additivo `mark_refused_pre_submit` prodotto e "
             "verificato 8/8 su branch Core dedicato, NON mergiato: Core main invariato e il Runtime resta "
             "sul percorso conservativo a due transazioni finche' la modifica non e' approvata."},
    {"id": "REAL_AUTHORIZATION_AND_PRICING", "scope": "future_gate", "evidence_tests": ("C09",),
     "declared": REAL_PROVIDER_REQUIRED, "fallback": REAL_PROVIDER_REQUIRED,
     "title": "Authorization / pricing reali del provider",
     "note": "Fuori scope per mandato: nessun provider reale, nessuna credenziale, 0 crediti. "
             "Prerequisiti documentati in REAL_PROVIDER_PREREQUISITES.md."},
    {"id": "REAL_PROVIDER_RECONCILIATION", "scope": "future_gate", "evidence_tests": ("C09",),
     "declared": REAL_PROVIDER_REQUIRED, "fallback": REAL_PROVIDER_REQUIRED,
     "title": "Reconciliation verificata contro un provider reale",
     "note": "Fuori scope per mandato. Il perimetro LAB dimostra binding, autenticazione, freshness e "
             "composizione con il confine di privilegio: nessuno di questi e' un claim sul provider reale."},
    {"id": "R0_R1_NO_REGRESSION", "scope": "this_phase", "evidence_tests": ("C07",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "Nessuna regressione R0-R1 (T01-T37) sul Runtime modificato",
     "note": "Suite storica eseguita con la modalita' Provider Boundary DISINGAGGIATA, come a baseline."},
    {"id": "P2_FREEZE_AND_CORE_PIN", "scope": "this_phase", "evidence_tests": ("C08",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "P2 frozen (before == after), Core main e pin invariati",
     "note": "Core main 740ee979 e working tree puliti a fine fase; il branch Core vive in un worktree "
             "separato e non tocca il tree canonico."},
    {"id": "PHASE_READINESS_REPORTING", "scope": "this_phase", "evidence_tests": ("C09",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "Reporting: test suite result e phase readiness separati, authority unica fail-closed",
     "note": "L'invariante della fase precedente e' preservata ed estesa ai nuovi stati "
             "(POLICY_DECISION_REQUIRED, REAL_PROVIDER_REQUIRED, CORE_CHANGE_REQUIRED)."},

    # ---- altre fasi: elencati, NON imputati a questa ----
    {"id": "RUN_CONTAMINATION", "scope": "other_phase", "evidence_tests": (),
     "declared": NOT_RUN, "fallback": NOT_RUN,
     "title": "run_contamination", "note": "Input Tenant assente: non eseguito (fuori scope)."},
    {"id": "G_N02_SEMANTIC_CLAIM_PARAPHRASE", "scope": "other_phase", "evidence_tests": (),
     "declared": STILL_OPEN, "fallback": STILL_OPEN,
     "title": "G-N02 — semantic claim paraphrase", "note": "Fuori scope, non toccato."},
    {"id": "RV07_SCHEDULER_RECOVERY_RESIDUAL", "scope": "other_phase", "evidence_tests": (),
     "declared": STILL_OPEN, "fallback": STILL_OPEN,
     "title": "RV07 — residuo scheduler/recovery",
     "note": "Non toccato. P-B02 offre l'uscita autenticata da SUBMIT_UNKNOWN, ora dimostrata dentro lo "
             "spender, ma nessuno scheduler la invoca."},
    {"id": "INDEPENDENT_CI_STATUS_CHECKS", "scope": "other_phase", "evidence_tests": (),
     "declared": NOT_RUN, "fallback": NOT_RUN,
     "title": "Status check CI indipendenti", "note": "Assenti sul branch, come nelle fasi precedenti."},
)


# ---------------------------------------------------------------- costruzione del report
def classify_requirements(passed_ids) -> list[dict]:
    passed = set(passed_ids)
    out = []
    for r in REQUIREMENTS:
        missing = sorted(set(r["evidence_tests"]) - passed)
        state = r["declared"] if not missing else r["fallback"]
        if state not in REQUIREMENT_STATES:
            raise ReportingInconsistent(f"{r['id']}: stato sconosciuto {state!r}")
        out.append({"id": r["id"], "title": r["title"], "scope": r["scope"], "state": state,
                    "open": state in OPEN_STATES,
                    "counts_for_phase_readiness": r["scope"] in ("this_phase", "future_gate"),
                    "evidence_tests": list(r["evidence_tests"]), "evidence_tests_not_passed": missing,
                    "reason_code": "EVIDENCE_TESTS_PASSED" if not missing else "EVIDENCE_TESTS_NOT_PASSED",
                    "note": r["note"]})
    return out


def build(results: list[dict], suite: dict) -> dict:
    """UNICO punto in cui nascono le due decisioni. Da `suite` si prendono SOLO fatti sui test."""
    passed = [r["id"] for r in results if r.get("status") == "PASS"]
    failed = [r["id"] for r in results if r.get("status") == "FAIL"]
    blocked = [{"id": r["id"], "reason_code": r.get("reason_code")} for r in results
               if r.get("status") == "BLOCKED"]
    inventory = suite["inventory"]
    invalid = list(suite.get("invalid") or [])
    all_tests_passed = not failed and not blocked and inventory["valid"] and not invalid

    if invalid or not inventory["valid"]:
        test_decision = TEST_SUITE_INVALID
    elif failed:
        test_decision = TEST_SUITE_FAILED
    elif blocked:
        test_decision = TEST_SUITE_BLOCKED
    else:
        test_decision = TEST_SUITE_ALL_PASS

    reqs = classify_requirements(passed)
    open_all = [r for r in reqs if r["open"]]
    open_blocking = [r for r in open_all if r["counts_for_phase_readiness"]]
    verified = [r for r in reqs if not r["open"]]
    all_requirements_verified = all_tests_passed and not open_blocking

    if test_decision == TEST_SUITE_INVALID:
        phase_decision = PHASE_INVALID
    elif not all_tests_passed:
        phase_decision = PHASE_NOT_FAVORABLE
    elif all_requirements_verified:
        phase_decision = PHASE_COMPLETE_ALL_VERIFIED
    else:
        phase_decision = PHASE_COMPLETE_WITH_OPEN_GAPS

    def by_state(*states):
        return [r["id"] for r in open_all if r["state"] in states]

    report = {
        "schema": "provider-boundary-gate-open-gap-closure-readiness/1",
        "test_suite": {
            "inventory": inventory, "total": suite["total"], "pass": suite["pass"],
            "fail": suite["fail"], "blocked": suite["blocked"], "pass_ids": passed,
            "fail_ids": failed, "blocked_tests": blocked, "all_tests_passed": all_tests_passed,
            "test_suite_decision": test_decision,
            "meaning": "i test del gate hanno prodotto l'esito atteso. NON significa che i requisiti "
                       "di fase siano chiusi: un test PASS puo' verificare che un requisito resta APERTO.",
        },
        "phase_readiness": {
            "all_requirements_verified": all_requirements_verified,
            "phase_gate_decision": phase_decision,
            "open_requirements": [{k: r[k] for k in ("id", "state", "scope", "title", "note")}
                                  for r in open_all],
            "open_requirements_blocking_all_verified": [r["id"] for r in open_blocking],
            "open_requirements_this_phase": [r["id"] for r in open_all if r["scope"] == "this_phase"],
            "open_requirements_future_gate": [r["id"] for r in open_all if r["scope"] == "future_gate"],
            "open_requirements_other_phase": [r["id"] for r in open_all if r["scope"] == "other_phase"],
            "policy_decision_required": by_state(POLICY_DECISION_REQUIRED),
            "real_provider_required": by_state(REAL_PROVIDER_REQUIRED, CREDENTIAL_REQUIRED),
            "core_change_required": by_state(CORE_CHANGE_REQUIRED),
            "blocked_provider_gate": by_state(BLOCKED_PROVIDER_GATE),
            "verified_requirements": [r["id"] for r in verified],
            "requirements": reqs,
            "max_state": MAX_STATE if phase_decision in PHASE_DECISIONS_ALLOWING_MAX_STATE else NOT_READY,
            "meaning": "i requisiti della fase sono chiusi? `all_requirements_verified` e' vero SOLO se "
                       "nessun requisito di questa fase o del Provider Boundary Gate e' aperto e tutti i "
                       "test sono PASS.",
            "not_implied": NOT_IMPLIED,
        },
        "runner_exit": 0 if all_tests_passed else (2 if test_decision == TEST_SUITE_INVALID else 1),
    }
    report["runner_exit_meaning"] = {
        0: "tutti i test del gate hanno prodotto l'esito atteso. NON significa 'tutti i requisiti di "
           "fase verificati': vedi phase_readiness.",
        1: "almeno un test FAIL o BLOCKED: suite non favorevole.",
        2: "inventario dei test non valido: report invalido, fail-closed.",
    }[report["runner_exit"]]
    validate(report)
    return report


def validate(report: dict) -> dict:
    """Invariante fail-closed. Solleva se il report afferma cose incompatibili."""
    ts, pr = report.get("test_suite", {}), report.get("phase_readiness", {})
    blocking = pr.get("open_requirements_blocking_all_verified") or []
    open_ids = {r["id"] for r in (pr.get("open_requirements") or [])}
    verified_ids = set(pr.get("verified_requirements") or [])
    if pr.get("all_requirements_verified") and blocking:
        raise ReportingInconsistent(f"all_requirements_verified=true con requisiti aperti: {blocking}")
    if pr.get("all_requirements_verified"):
        for r in (pr.get("requirements") or []):
            if r.get("state") in OPEN_STATES and r.get("counts_for_phase_readiness"):
                raise ReportingInconsistent(
                    f"all_requirements_verified=true mentre {r['id']} e' {r['state']}")
    if pr.get("all_requirements_verified") and not ts.get("all_tests_passed"):
        raise ReportingInconsistent("all_requirements_verified=true con test non tutti PASS")
    if pr.get("phase_gate_decision") == PHASE_COMPLETE_ALL_VERIFIED and not pr.get("all_requirements_verified"):
        raise ReportingInconsistent("decisione di fase ALL_VERIFIED senza all_requirements_verified")
    if open_ids & verified_ids:
        raise ReportingInconsistent(
            f"requisiti contemporaneamente aperti e verificati: {sorted(open_ids & verified_ids)}")
    if ts.get("all_tests_passed") and (ts.get("fail_ids") or ts.get("blocked_tests")):
        raise ReportingInconsistent("all_tests_passed=true con FAIL o BLOCKED presenti")
    for r in (pr.get("requirements") or []):
        if (r["state"] in OPEN_STATES) != bool(r["open"]):
            raise ReportingInconsistent(f"{r['id']}: flag `open` incoerente con lo stato {r['state']}")
    # Nessuno stato puo' implicitamente promettere provider/produzione.
    if pr.get("max_state") not in (MAX_STATE, NOT_READY):
        raise ReportingInconsistent(f"max_state sconosciuto: {pr.get('max_state')!r}")
    return report


# ---------------------------------------------------------------- rendering (deriva, non ricalcola)
def machine_readable_gaps(report: dict) -> dict:
    return {r["id"]: r["state"] for r in report["phase_readiness"]["requirements"]}


def console(report: dict) -> str:
    ts, pr = report["test_suite"], report["phase_readiness"]
    return "\n".join([
        "",
        f"A. TEST SUITE   {ts['pass']}/{ts['total']} PASS · FAIL {ts['fail_ids'] or 'nessuno'} · "
        f"BLOCKED {[b['id'] + '/' + b['reason_code'] for b in ts['blocked_tests']] or 'nessuno'} · "
        f"inventario {ts['inventory']['observed_count']}/{ts['inventory']['expected_count']} "
        f"valido={ts['inventory']['valid']}",
        f"   all_tests_passed = {str(ts['all_tests_passed']).lower()} · "
        f"test_suite_decision = {ts['test_suite_decision']}",
        "",
        f"B. PHASE READINESS   all_requirements_verified = "
        f"{str(pr['all_requirements_verified']).lower()} · phase_gate_decision = {pr['phase_gate_decision']}",
        f"   aperti che impediscono ALL_VERIFIED: {pr['open_requirements_blocking_all_verified'] or 'nessuno'}",
        f"     - di questa fase: {pr['open_requirements_this_phase'] or 'nessuno'}",
        f"     - rinviati al Provider Boundary Gate: {pr['open_requirements_future_gate'] or 'nessuno'}",
        f"   POLICY_DECISION_REQUIRED: {pr['policy_decision_required'] or 'nessuno'}",
        f"   REAL_PROVIDER_REQUIRED:   {pr['real_provider_required'] or 'nessuno'}",
        f"   CORE_CHANGE_REQUIRED:     {pr['core_change_required'] or 'nessuno'}",
        f"   di altre fasi (elencati, non imputati): {pr['open_requirements_other_phase'] or 'nessuno'}",
        f"   stato massimo: {pr['max_state']}",
        "",
        f"runner exit {report['runner_exit']}: {report['runner_exit_meaning']}",
    ])


def markdown(report: dict) -> list[str]:
    ts, pr = report["test_suite"], report["phase_readiness"]
    lines = ["## A. TEST SUITE RESULT", "",
             "| inventario | PASS | FAIL | BLOCKED | all_tests_passed | test_suite_decision |",
             "|---|---|---|---|---|---|",
             f"| {ts['inventory']['observed_count']}/{ts['inventory']['expected_count']} "
             f"(valido: {ts['inventory']['valid']}) | {ts['pass']} | {ts['fail']} | {ts['blocked']} | "
             f"**{str(ts['all_tests_passed']).lower()}** | `{ts['test_suite_decision']}` |", "",
             f"_{ts['meaning']}_", "",
             "## B. PHASE / REQUIREMENT READINESS", "",
             f"**`all_requirements_verified = {str(pr['all_requirements_verified']).lower()}`** · "
             f"**`phase_gate_decision = {pr['phase_gate_decision']}`** · stato massimo: "
             f"`{pr['max_state']}`", "",
             f"_{pr['meaning']}_", "",
             "| REQUISITO | SCOPE | STATO | EVIDENZA | NOTA |", "|---|---|---|---|---|"]
    for r in pr["requirements"]:
        ev = ", ".join(r["evidence_tests"]) or "—"
        lines.append(f"| {r['id']} | {r['scope']} | **`{r['state']}`** | {ev} | {r['note']} |")
    lines += ["",
              f"Requisiti aperti che impediscono `all_requirements_verified`: "
              f"{pr['open_requirements_blocking_all_verified'] or 'nessuno'} (di questa fase: "
              f"{pr['open_requirements_this_phase'] or 'nessuno'}; rinviati al Provider Boundary Gate: "
              f"{pr['open_requirements_future_gate'] or 'nessuno'}). Di altre fasi, elencati ma non "
              f"imputati: {pr['open_requirements_other_phase'] or 'nessuno'}.", "",
              f"- `POLICY_DECISION_REQUIRED`: {pr['policy_decision_required'] or 'nessuno'}",
              f"- `REAL_PROVIDER_REQUIRED`: {pr['real_provider_required'] or 'nessuno'}",
              f"- `CORE_CHANGE_REQUIRED`: {pr['core_change_required'] or 'nessuno'}", "",
              "Nulla di quanto sopra significa " + ", ".join(NOT_IMPLIED) + ".", ""]
    return lines
