"""AUTHORITY UNICA — COORDINATED CORE + RUNTIME INTEGRATION (NG-05).

Estende, senza duplicarlo, il vocabolario approvato dalla Human Review
(`PROVIDER_BOUNDARY_GATE_02/pbg2/readiness.py`): gli stati dei requisiti e l'invariante
fail-closed vengono importati da li'. Qui cambiano il registro dei requisiti di QUESTA fase
e la sezione `pair_readiness`, che e' la domanda nuova:

    A. TEST SUITE RESULT   — i test hanno prodotto l'esito atteso?
    B. PHASE READINESS     — i requisiti della fase sono chiusi?
    C. PAIR READINESS      — esiste una coppia Core+Runtime coerente e promuovibile?

`core_runtime_pair_ready` puo' diventare vero anche con altri requisiti aperti: e' una
domanda sulla COERENZA della coppia, non sulla chiusura della fase (decisione esplicita
della Human Review). `merge_authorized` no: pretende coppia pronta, zero requisiti aperti
E un'autorizzazione umana separata che il codice non si concede mai.
"""
from __future__ import annotations

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PBG2 = os.path.join(REPO, "PROVIDER_BOUNDARY_GATE_02")
if _PBG2 not in sys.path:
    sys.path.insert(0, _PBG2)

from pbg2.readiness import (  # noqa: E402  (vocabolario approvato, importato non copiato)
    BLOCKED_ENVIRONMENT, BLOCKED_PROVIDER_GATE, CORE_CHANGE_REQUIRED, CREDENTIAL_REQUIRED,
    NOT_RUN, NOT_VERIFIED, OPEN_CONSERVATIVE_LIMITATION, OPEN_STATES,
    POLICY_DECISION_REQUIRED, REAL_PROVIDER_REQUIRED, REQUIREMENT_STATES, STILL_OPEN,
    VERIFIED_LAB, ReportingInconsistent)

TEST_SUITE_ALL_PASS = "ALL_TESTS_PASS"
TEST_SUITE_FAILED = "TESTS_FAILED"
TEST_SUITE_BLOCKED = "TESTS_BLOCKED_BY_ENVIRONMENT"
TEST_SUITE_INVALID = "TEST_INVENTORY_INVALID"

PHASE_COMPLETE_WITH_OPEN_GAPS = "LAB_GATE_COMPLETE_WITH_OPEN_GAPS"
PHASE_COMPLETE_ALL_VERIFIED = "LAB_GATE_COMPLETE_ALL_VERIFIED"
PHASE_NOT_FAVORABLE = "PHASE_GATE_NOT_FAVORABLE"
PHASE_INVALID = "PHASE_GATE_INVALID"
PHASE_DECISIONS_ALLOWING_MAX_STATE = (PHASE_COMPLETE_ALL_VERIFIED, PHASE_COMPLETE_WITH_OPEN_GAPS)

MAX_STATE = "CORE_RUNTIME_PAIR_READY_FOR_HUMAN_REVIEW"
NOT_READY = "NOT_READY"

PAIR_READINESS_KEYS = ("core_candidate_ready", "runtime_candidate_ready",
                       "pin_points_to_core_candidate", "runtime_consumes_core_candidate",
                       "core_runtime_pair_ready", "merge_authorized")
CORE_REVIEW_STATE = "APPROVED_PROPOSAL — NOT_MERGE_AUTHORIZED"

NOT_IMPLIED = ["provider reale verificato", "provider ready", "production ready",
               "credenziali autorizzate", "spend autorizzato", "merge autorizzato",
               "R2 autorizzato", "chiusura degli altri open requirements"]

# `scope`: this_phase | future_gate | other_phase
REQUIREMENTS: tuple[dict, ...] = (
    {"id": "APPROVED_INPUT_REALITY_LOCK", "scope": "this_phase", "evidence_tests": ("D00",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "Reality Lock sugli input approvati (Core main/candidate, Runtime main/reviewed, P2)",
     "note": "8/8 verifiche. Nessun APPROVED_INPUT_DRIFT."},
    {"id": "CORE_PIN_POINTS_TO_CANDIDATE", "scope": "this_phase", "evidence_tests": ("D01",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "REQUIRED_CORE_SHA punta al Core candidate approvato, fail-closed su tutto il resto",
     "note": "Candidate pulito -> CORE_PIN_OK. Baseline vecchia -> STALE_CORE_PIN (non "
             "MISMATCH generico: e' un Core VECCHIO, e il runtime lo dice). Candidate sporco -> "
             "CORE_WORKTREE_DIRTY. Path assente / SHA sbagliato -> CORE_PIN_MISMATCH. "
             "`go()` contro la baseline si ferma PRIMA dell'import e senza creare lo store."},
    {"id": "RUNTIME_CONSUMES_CORE_CANDIDATE", "scope": "this_phase", "evidence_tests": ("D01", "D06"),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "Il Runtime consuma realmente `mark_refused_pre_submit`",
     "note": "Unico call site: go_candidate._refuse_pre_submit. Il percorso a due transazioni "
             "reconcile -> settle e' RIMOSSO dal caso pre-submit; `settle` non e' piu' chiamata "
             "dal runtime; `reconcile` resta solo per il report autenticato P-B02."},
    {"id": "NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY", "scope": "this_phase",
     "evidence_tests": ("D02", "D03", "D04", "D05"),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "NG-05 — atomicita' della terminalizzazione pre-submit, end-to-end Runtime -> Core",
     "note": "SERIALIZATION_DRIFT e IDENTITY_DRIFT: FAILED + settlement 0 + 1 riga di ledger + "
             "1 anomalia, in UNA transazione, con provenance veritiera. Crash prima del COMMIT "
             "del Core: nulla di parziale, e la chiusura ritentata riesce. Vista obsoleta: CAS "
             "fail-closed, nessun doppio settlement. Non-RESERVED e identita' remota persistita: "
             "rifiutati. Era CORE_CHANGE_REQUIRED."},
    {"id": "NG03_PRE_SUBMIT_SETTLEMENT_PROVENANCE", "scope": "this_phase",
     "evidence_tests": ("D06", "D07"),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "NG-03 — provenance veritiera preservata dall'integrazione",
     "note": "`TRANSPORT_ATTESTED_NOT_SENT` resta esclusiva del percorso con attestazione reale "
             "(controprova positiva: quel percorso la registra ancora). Il Core la RIFIUTA come "
             "`source` del percorso pre-submit, quindi l'invariante e' ora imposta da entrambi i lati."},
    {"id": "SUBMIT_UNKNOWN_NO_ZERO_SETTLEMENT", "scope": "this_phase", "evidence_tests": ("D08",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "Invio incerto: resta SUBMIT_UNKNOWN, nessun settlement zero, nessun blind retry",
     "note": "L'API atomica rifiuta un job non RESERVED: un invio che puo' essere avvenuto non "
             "diventa gratis. RESUME non crea un nuovo attempt ne' un nuovo submit."},
    {"id": "MECHANISM_REGRESSIONS_ON_CANDIDATE", "scope": "this_phase", "evidence_tests": ("D09",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "P-B04, P-B01+P-B02, NG-04, legacy spend paths, orphan lease rieseguiti sul Core candidate",
     "note": "Nessun test storico indebolito: stessi asserti, Core diverso."},
    {"id": "R0_R1_NO_REGRESSION", "scope": "this_phase", "evidence_tests": ("D10",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "Nessuna regressione R0-R1 (T01-T37) contro il Core candidate",
     "note": "Stessa forma della baseline: 36/37 PASS, 0 FAIL, T29 BLOCKED_ENVIRONMENT per policy."},
    {"id": "P2_FREEZE_AND_BASELINE_UNTOUCHED", "scope": "this_phase", "evidence_tests": ("D11",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "P2 invariato, Core main e Runtime main intatti, nessun tag",
     "note": "Il Core candidate non e' stato modificato oltre il commit approvato."},
    {"id": "EVIDENCE_CHAIN_INTEGRITY", "scope": "this_phase", "evidence_tests": ("D12",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "Catena di provenance preservata (code sha / evidence head / provenance esterna)",
     "note": "Stessa struttura approvata dalla Human Review: nessun `runtime_commit`, "
             "SHA256SUMS copre MANIFEST.json, nessun .pyc nel package."},

    # ---- aperti: invariati per decisione esplicita della Human Review ----
    {"id": "RECONCILIATION_FRESHNESS_NG04_POLICY", "scope": "future_gate", "evidence_tests": ("D09",),
     "declared": POLICY_DECISION_REQUIRED, "fallback": POLICY_DECISION_REQUIRED,
     "title": "NG-04 — POLICY: valori della finestra",
     "note": "Meccanismo verificato anche sul Core candidate. Nessun valore scelto: servono "
             "clock semantics, latenza e timing reali del provider."},
    {"id": "ORPHAN_RESERVED_LEASE_POLICY", "scope": "this_phase", "evidence_tests": ("D09",),
     "declared": POLICY_DECISION_REQUIRED, "fallback": POLICY_DECISION_REQUIRED,
     "title": "Orphan lease — POLICY: finestra, attore, evidenze, classi ammesse",
     "note": "Meccanismo verificato anche sul Core candidate. `RECLAIM_POLICY = NOT_AUTHORIZED`."},
    {"id": "LEGACY_SPEND_PATHS_CORE_PRIMITIVES", "scope": "future_gate", "evidence_tests": ("D09",),
     "declared": CORE_CHANGE_REQUIRED, "fallback": CORE_CHANGE_REQUIRED,
     "title": "Legacy #10/#11: primitive del Core raggiungibili senza passare dal Runtime",
     "note": "PROBLEMA DISTINTO da NG-05. Il Core candidate aggiunge una primitive, non ne "
             "governa l'accesso: `transport.pipeline.run_job`, `adapter.submit` e "
             "`store.reconcile` raw restano raggiungibili. Non chiuso da questa integrazione."},
    {"id": "LEGACY_TESTS_MIGRATION_TO_GOVERNED", "scope": "future_gate", "evidence_tests": ("D09",),
     "declared": STILL_OPEN, "fallback": STILL_OPEN,
     "title": "Migrazione dei test storici T01-T27 al percorso governato",
     "note": "PROBLEMA DISTINTO da NG-05. Invariato."},
    {"id": "REAL_AUTHORIZATION_AND_PRICING", "scope": "future_gate", "evidence_tests": (),
     "declared": REAL_PROVIDER_REQUIRED, "fallback": REAL_PROVIDER_REQUIRED,
     "title": "Authorization / pricing reali del provider",
     "note": "Fuori scope: nessun provider reale, nessuna credenziale, 0 crediti."},
    {"id": "REAL_PROVIDER_RECONCILIATION", "scope": "future_gate", "evidence_tests": (),
     "declared": REAL_PROVIDER_REQUIRED, "fallback": REAL_PROVIDER_REQUIRED,
     "title": "Reconciliation verificata contro un provider reale",
     "note": "Fuori scope."},
    {"id": "CORE_RUNTIME_MERGE_AUTHORIZATION", "scope": "this_phase", "evidence_tests": ("D11",),
     "declared": STILL_OPEN, "fallback": STILL_OPEN,
     "title": "Autorizzazione umana al merge della coppia Core+Runtime",
     "note": "Non e' un fatto tecnico e il codice non se la concede: serve una Human Merge "
             "Authorization separata. `merge_authorized = false` finche' non arriva."},

    # ---- altre fasi ----
    {"id": "RUN_CONTAMINATION", "scope": "other_phase", "evidence_tests": (),
     "declared": NOT_RUN, "fallback": NOT_RUN, "title": "run_contamination",
     "note": "Input Tenant assente."},
    {"id": "G_N02_SEMANTIC_CLAIM_PARAPHRASE", "scope": "other_phase", "evidence_tests": (),
     "declared": STILL_OPEN, "fallback": STILL_OPEN, "title": "G-N02", "note": "Non toccato."},
    {"id": "RV07_SCHEDULER_RECOVERY_RESIDUAL", "scope": "other_phase", "evidence_tests": (),
     "declared": STILL_OPEN, "fallback": STILL_OPEN, "title": "RV07", "note": "Non toccato."},
    {"id": "INDEPENDENT_CI_STATUS_CHECKS", "scope": "other_phase", "evidence_tests": (),
     "declared": NOT_RUN, "fallback": NOT_RUN, "title": "Status check CI indipendenti",
     "note": "Assenti sul branch."},
)


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


def build_pair_readiness(*, reqs: list[dict], all_tests_passed: bool,
                         all_requirements_verified: bool, facts: dict | None) -> dict:
    """Ogni campo e' CALCOLATO da fatti osservati dal gate, nessuno e' asserito a mano."""
    f = dict(facts or {})
    verified = {r["id"] for r in reqs if not r["open"]}

    core_candidate_ready = bool(f.get("core_candidate_sha") == f.get("approved_core_candidate")
                                and f.get("core_candidate_clean")
                                and f.get("core_candidate_suites_pass"))
    runtime_candidate_ready = bool(
        all_tests_passed
        and {"APPROVED_INPUT_REALITY_LOCK", "R0_R1_NO_REGRESSION",
             "P2_FREEZE_AND_BASELINE_UNTOUCHED"} <= verified)
    pin_points_to_core_candidate = bool(f.get("required_core_sha")
                                        and f.get("required_core_sha") == f.get("core_candidate_sha"))
    runtime_consumes_core_candidate = bool(f.get("runtime_uses_atomic_api")
                                           and not f.get("runtime_still_uses_two_transactions"))
    ng05_e2e = "NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY" in verified
    ng03_preserved = "NG03_PRE_SUBMIT_SETTLEMENT_PROVENANCE" in verified

    core_runtime_pair_ready = bool(core_candidate_ready and runtime_candidate_ready
                                   and pin_points_to_core_candidate
                                   and runtime_consumes_core_candidate
                                   and ng05_e2e and ng03_preserved)
    merge_authorized = bool(core_runtime_pair_ready and all_requirements_verified
                            and f.get("human_merge_authorization") is True)

    blockers = []
    for cond, code in ((core_candidate_ready, "CORE_CANDIDATE_NOT_READY"),
                       (runtime_candidate_ready, "RUNTIME_CANDIDATE_NOT_READY"),
                       (pin_points_to_core_candidate, "PIN_DOES_NOT_POINT_TO_CANDIDATE"),
                       (runtime_consumes_core_candidate, "RUNTIME_DOES_NOT_CONSUME_CORE_CANDIDATE"),
                       (ng05_e2e, "NG05_END_TO_END_NOT_VERIFIED"),
                       (ng03_preserved, "NG03_NOT_PRESERVED")):
        if not cond:
            blockers.append(code)
    merge_blockers = list(blockers)
    if not all_requirements_verified:
        merge_blockers.append("OPEN_REQUIREMENTS")
    if f.get("human_merge_authorization") is not True:
        merge_blockers.append("HUMAN_MERGE_AUTHORIZATION_ABSENT")

    return {
        "core_candidate_ready": core_candidate_ready,
        "runtime_candidate_ready": runtime_candidate_ready,
        "pin_points_to_core_candidate": pin_points_to_core_candidate,
        "runtime_consumes_core_candidate": runtime_consumes_core_candidate,
        "core_runtime_pair_ready": core_runtime_pair_ready,
        "merge_authorized": merge_authorized,
        "core_review_state": CORE_REVIEW_STATE,
        "ng05_end_to_end_verified": ng05_e2e,
        "ng03_preserved": ng03_preserved,
        "required_core_sha": f.get("required_core_sha"),
        "core_candidate_sha": f.get("core_candidate_sha"),
        "runtime_candidate_branch": f.get("runtime_candidate_branch"),
        "human_merge_authorization": f.get("human_merge_authorization", False),
        "pair_blockers": blockers,
        "merge_blockers": merge_blockers,
        "meaning": "la coppia Core+Runtime e' COERENTE e promuovibile? Vero quando il Runtime "
                   "consuma davvero l'API del Core candidate, il pin vi punta, NG-05 e' "
                   "dimostrato end-to-end e NG-03 e' preservato. NON implica la chiusura degli "
                   "altri open requirements, e NON e' un'autorizzazione al merge.",
        "pair_ready_does_not_imply": ["chiusura degli altri open requirements",
                                      "merge autorizzato", "provider reale", "production ready"],
    }


def build(results: list[dict], suite: dict, pair_facts: dict | None = None) -> dict:
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

    pair = build_pair_readiness(reqs=reqs, all_tests_passed=all_tests_passed,
                                all_requirements_verified=all_requirements_verified,
                                facts=pair_facts)

    def by_state(*states):
        return [r["id"] for r in open_all if r["state"] in states]

    max_state = (MAX_STATE if phase_decision in PHASE_DECISIONS_ALLOWING_MAX_STATE
                 and pair["core_runtime_pair_ready"] else NOT_READY)
    report = {
        "schema": "core-runtime-integration-ng05-readiness/1",
        "test_suite": {
            "inventory": inventory, "total": suite["total"], "pass": suite["pass"],
            "fail": suite["fail"], "blocked": suite["blocked"], "pass_ids": passed,
            "fail_ids": failed, "blocked_tests": blocked, "all_tests_passed": all_tests_passed,
            "test_suite_decision": test_decision,
            "meaning": "i test hanno prodotto l'esito atteso. NON significa che i requisiti "
                       "siano chiusi ne' che il merge sia autorizzato.",
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
            "verified_requirements": [r["id"] for r in verified],
            "requirements": reqs,
            "max_state": max_state,
            "max_state_meaning": "coppia Core+Runtime coerente, pronta per Human Review. "
                                 "NON e' un'autorizzazione al merge.",
            "meaning": "i requisiti della fase sono chiusi?",
            "not_implied": NOT_IMPLIED,
        },
        "pair_readiness": pair,
        "runner_exit": 0 if all_tests_passed else (2 if test_decision == TEST_SUITE_INVALID else 1),
    }
    report["runner_exit_meaning"] = {
        0: "tutti i test hanno prodotto l'esito atteso. NON significa merge autorizzato.",
        1: "almeno un test FAIL o BLOCKED.",
        2: "inventario dei test non valido: report invalido, fail-closed.",
    }[report["runner_exit"]]
    validate(report)
    return report


def validate(report: dict) -> dict:
    ts, pr = report.get("test_suite", {}), report.get("phase_readiness", {})
    pair = report.get("pair_readiness")
    blocking = pr.get("open_requirements_blocking_all_verified") or []
    open_ids = {r["id"] for r in (pr.get("open_requirements") or [])}
    verified_ids = set(pr.get("verified_requirements") or [])
    if pr.get("all_requirements_verified") and blocking:
        raise ReportingInconsistent(f"all_requirements_verified=true con requisiti aperti: {blocking}")
    if pr.get("all_requirements_verified") and not ts.get("all_tests_passed"):
        raise ReportingInconsistent("all_requirements_verified=true con test non tutti PASS")
    if open_ids & verified_ids:
        raise ReportingInconsistent(
            f"requisiti contemporaneamente aperti e verificati: {sorted(open_ids & verified_ids)}")
    if ts.get("all_tests_passed") and (ts.get("fail_ids") or ts.get("blocked_tests")):
        raise ReportingInconsistent("all_tests_passed=true con FAIL o BLOCKED presenti")
    for r in (pr.get("requirements") or []):
        if (r["state"] in OPEN_STATES) != bool(r["open"]):
            raise ReportingInconsistent(f"{r['id']}: flag `open` incoerente con lo stato {r['state']}")
    if not isinstance(pair, dict):
        raise ReportingInconsistent("pair_readiness assente")
    for k in PAIR_READINESS_KEYS:
        if not isinstance(pair.get(k), bool):
            raise ReportingInconsistent(f"pair_readiness.{k} assente o non booleano")
    if pair["core_runtime_pair_ready"] and pair["pair_blockers"]:
        raise ReportingInconsistent(
            f"core_runtime_pair_ready=true con blockers: {pair['pair_blockers']}")
    if pair["core_runtime_pair_ready"] and not (pair["pin_points_to_core_candidate"]
                                                and pair["runtime_consumes_core_candidate"]
                                                and pair["ng05_end_to_end_verified"]
                                                and pair["ng03_preserved"]):
        raise ReportingInconsistent(
            "core_runtime_pair_ready=true senza pin, consumo, NG-05 end-to-end o NG-03 preservato")
    if pair["merge_authorized"] and not pair["core_runtime_pair_ready"]:
        raise ReportingInconsistent("merge_authorized=true con coppia non pronta")
    if pair["merge_authorized"] and not pr.get("all_requirements_verified"):
        raise ReportingInconsistent("merge_authorized=true con requisiti aperti")
    if pair["merge_authorized"] and pair.get("human_merge_authorization") is not True:
        raise ReportingInconsistent("merge_authorized=true senza autorizzazione umana esplicita")
    if not pair["merge_authorized"] and not pair.get("merge_blockers"):
        raise ReportingInconsistent("merge_authorized=false senza merge_blockers dichiarati")
    if pr.get("max_state") not in (MAX_STATE, NOT_READY):
        raise ReportingInconsistent(f"max_state sconosciuto: {pr.get('max_state')!r}")
    if pr.get("max_state") == MAX_STATE and not pair["core_runtime_pair_ready"]:
        raise ReportingInconsistent("max_state di coppia senza core_runtime_pair_ready")
    return report


def machine_readable_gaps(report: dict) -> dict:
    return {r["id"]: r["state"] for r in report["phase_readiness"]["requirements"]}


def console(report: dict) -> str:
    ts, pr, pa = report["test_suite"], report["phase_readiness"], report["pair_readiness"]
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
        f"   aperti: {pr['open_requirements_blocking_all_verified'] or 'nessuno'}",
        f"   POLICY_DECISION_REQUIRED: {pr['policy_decision_required'] or 'nessuno'}",
        f"   REAL_PROVIDER_REQUIRED:   {pr['real_provider_required'] or 'nessuno'}",
        f"   CORE_CHANGE_REQUIRED:     {pr['core_change_required'] or 'nessuno'}",
        "",
        f"C. PAIR READINESS   core_candidate_ready = {str(pa['core_candidate_ready']).lower()} · "
        f"runtime_candidate_ready = {str(pa['runtime_candidate_ready']).lower()}",
        f"   pin_points_to_core_candidate = {str(pa['pin_points_to_core_candidate']).lower()} · "
        f"runtime_consumes_core_candidate = {str(pa['runtime_consumes_core_candidate']).lower()}",
        f"   core_runtime_pair_ready = {str(pa['core_runtime_pair_ready']).lower()} · "
        f"merge_authorized = {str(pa['merge_authorized']).lower()}",
        f"   pair blockers: {pa['pair_blockers'] or 'nessuno'} · merge blockers: {pa['merge_blockers']}",
        f"   stato massimo: {pr['max_state']}",
        "",
        f"runner exit {report['runner_exit']}: {report['runner_exit_meaning']}",
    ])


def markdown(report: dict) -> list[str]:
    ts, pr, pa = report["test_suite"], report["phase_readiness"], report["pair_readiness"]
    lines = ["## A. TEST SUITE RESULT", "",
             "| inventario | PASS | FAIL | BLOCKED | all_tests_passed | decisione |",
             "|---|---|---|---|---|---|",
             f"| {ts['inventory']['observed_count']}/{ts['inventory']['expected_count']} "
             f"(valido: {ts['inventory']['valid']}) | {ts['pass']} | {ts['fail']} | {ts['blocked']} | "
             f"**{str(ts['all_tests_passed']).lower()}** | `{ts['test_suite_decision']}` |", "",
             f"_{ts['meaning']}_", "",
             "## B. PHASE / REQUIREMENT READINESS", "",
             f"**`all_requirements_verified = {str(pr['all_requirements_verified']).lower()}`** · "
             f"**`phase_gate_decision = {pr['phase_gate_decision']}`** · stato massimo: "
             f"`{pr['max_state']}`", "",
             "| REQUISITO | SCOPE | STATO | EVIDENZA | NOTA |", "|---|---|---|---|---|"]
    for r in pr["requirements"]:
        ev = ", ".join(r["evidence_tests"]) or "—"
        lines.append(f"| {r['id']} | {r['scope']} | **`{r['state']}`** | {ev} | {r['note']} |")
    lines += ["", "## C. PAIR READINESS", "", "| campo | valore |", "|---|---|"]
    for k in PAIR_READINESS_KEYS:
        lines.append(f"| `{k}` | **`{str(pa[k]).lower()}`** |")
    lines += [f"| `core_review_state` | `{pa['core_review_state']}` |",
              f"| `required_core_sha` | `{pa['required_core_sha']}` |",
              f"| `core_candidate_sha` | `{pa['core_candidate_sha']}` |",
              f"| `human_merge_authorization` | `{str(pa['human_merge_authorization']).lower()}` |",
              "",
              f"Pair blockers: {', '.join('`' + b + '`' for b in pa['pair_blockers']) or 'nessuno'}. "
              f"Merge blockers: {', '.join('`' + b + '`' for b in pa['merge_blockers'])}.", "",
              f"_{pa['meaning']}_", "",
              "`core_runtime_pair_ready` **non implica**: "
              + ", ".join(pa["pair_ready_does_not_imply"]) + ".", "",
              "Nulla di quanto sopra significa " + ", ".join(NOT_IMPLIED) + ".", ""]
    return lines
