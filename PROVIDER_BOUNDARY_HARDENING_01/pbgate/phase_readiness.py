"""AUTHORITY UNICA DI CLASSIFICAZIONE (Human Review 02 — `PHASE_READINESS_REPORTING_INCONSISTENT`).

Il difetto corretto qui: il report diceva nello stesso JSON `all_requirements_verified = true` e
`gate_decision = LAB_GATE_COMPLETE_ALL_VERIFIED` mentre elencava requisiti `STILL_OPEN`,
`BLOCKED_PROVIDER_GATE` e `NOT_VERIFIED`. Sono due domande diverse e non vanno fuse:

    A. TEST SUITE RESULT   — i test del gate hanno prodotto l'esito atteso?
                             13/13 PASS significa questo, e SOLO questo.
    B. PHASE READINESS     — i requisiti della fase sono chiusi?
                             `B08 PASS` significa "il gate ha verificato che l'orphan lease resta
                             STILL_OPEN": e' un test superato su un requisito APERTO.

Questo modulo e' l'unica sede in cui quelle due risposte vengono calcolate. Console, RESULTS.json,
TEST_RESULTS.md, MANIFEST.json e la sezione di stato del README derivano tutti da `build(...)`:
nessuno di essi ricalcola, riformula o riassume per conto proprio.

INVARIANTE FAIL-CLOSED (`validate`): `all_requirements_verified` puo' essere vero solo se NESSUN
requisito in scope per questa fase e' aperto E tutti i test sono PASS. Qualunque altra combinazione
solleva `ReportingInconsistent` e rende il report invalido — non esiste un percorso che produca
"tutto verificato" mentre un requisito e' `STILL_OPEN` o `BLOCKED_PROVIDER_GATE`.

Lo stato dichiarato di ogni requisito NON e' scritto a mano: e' `declared` solo se i test che lo
sostengono sono PASS, altrimenti degrada a `fallback` (sempre uno stato aperto). Un test che
fallisce non puo' quindi lasciare in piedi una classificazione "verificata".
"""
from __future__ import annotations

# ---------------------------------------------------------------- stati dei requisiti
VERIFIED_LAB = "VERIFIED_LAB"                                # chiuso nel perimetro LAB di questa fase
STILL_OPEN = "STILL_OPEN"                                    # aperto, rinviato per decisione esplicita
BLOCKED_PROVIDER_GATE = "BLOCKED_PROVIDER_GATE"              # da chiudere prima del Provider Boundary Gate
OPEN_CONSERVATIVE_LIMITATION = "OPEN_CONSERVATIVE_LIMITATION"  # limite noto, comportamento conservativo
NOT_VERIFIED = "NOT_VERIFIED"                                # non dimostrato dai test correnti
NOT_RUN = "NOT_RUN"                                          # non eseguibile/non eseguito in questa fase

REQUIREMENT_STATES = (VERIFIED_LAB, STILL_OPEN, BLOCKED_PROVIDER_GATE,
                      OPEN_CONSERVATIVE_LIMITATION, NOT_VERIFIED, NOT_RUN)
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

MAX_STATE = "PROVIDER_EXECUTION_BOUNDARY_HARDENING_READY_FOR_HUMAN_REVIEW"
NOT_READY = "NOT_READY"

# Il lavoro della fase puo' essere completo anche con gap esplicitamente rinviati (decisione di
# Human Review 02): lo stato massimo resta raggiungibile con `PHASE_COMPLETE_WITH_OPEN_GAPS`.
PHASE_DECISIONS_ALLOWING_MAX_STATE = (PHASE_COMPLETE_ALL_VERIFIED, PHASE_COMPLETE_WITH_OPEN_GAPS)


class ReportingInconsistent(RuntimeError):
    """Il report afferma insieme cose incompatibili. Fail-closed: il report e' invalido."""


# ---------------------------------------------------------------- registro dei requisiti di fase
# `scope`: this_phase  -> requisito di questa fase
#          future_gate -> requisito rinviato al Provider Boundary Gate
#          other_phase -> requisito di ALTRE fasi (elencato, non imputato a questa)
# Contano per `all_requirements_verified` sia `this_phase` sia `future_gate`: un requisito
# `BLOCKED_PROVIDER_GATE` e' aperto, e nessuna combinazione puo' dichiarare "tutto verificato"
# mentre resta aperto (Human Review 02). Solo `other_phase` non e' imputato a questa fase.
# `declared`: stato se i test in `evidence_tests` sono tutti PASS; `fallback`: stato altrimenti.
REQUIREMENTS: tuple[dict, ...] = (
    {"id": "P_B01_PRIVILEGE_BOUNDARY", "scope": "this_phase", "evidence_tests": ("B01", "B02"),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "P-B01 — confine di privilegio orchestrator/spender (UID distinti, DAC, SO_PEERCRED)",
     "note": "LAB_VERIFIED_UID_BOUNDARY, approvato in perimetro LAB da Human Review 01. Non chiude il "
             "boundary di produzione (adapter reale nello spender, credenziali reali, hardening del daemon)."},
    {"id": "P_B02_BINDING_AUTHENTICATION", "scope": "this_phase", "evidence_tests": ("B03", "B04"),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "P-B02 — binding e autenticazione HMAC della reconciliation",
     "note": "LAB_VERIFIED_BINDING_AUTH_ONLY: verificati binding e autenticazione. NON copre la "
             "composizione con P-B01 (requisito separato) ne' il provider reale."},
    {"id": "P_B04_EXACT_BYTE_SNAPSHOT", "scope": "this_phase", "evidence_tests": ("B05", "B06"),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "P-B04 — snapshot exact-byte immutabile e verificato prima dell'invio",
     "note": "Ledger write-once nel dominio dello spender; non e' WORM hardware."},
    {"id": "NG03_PRE_SUBMIT_SETTLEMENT_PROVENANCE", "scope": "this_phase", "evidence_tests": ("B12", "B06"),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "NG-03 — provenance veritiera del settlement zero nel rifiuto pre-submit",
     "note": "Chiuso: rifiuto a mark_submitting -> RUNTIME_PRE_SUBMIT_REFUSED_NOT_DISPATCHED; "
             "rifiuto dentro submit -> TRANSPORT_ATTESTED_NOT_SENT (invariato)."},
    {"id": "LEGACY_SPEND_PATHS_INVENTORY_AND_SWITCH", "scope": "this_phase", "evidence_tests": ("B07",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "Legacy spend paths — inventario completo e interruttore fail-closed",
     "note": "Verificati l'inventario (13 entry point) e la chiusura fail-closed dell'interruttore. "
             "La CHIUSURA dei percorsi residui e' un requisito separato e aperto."},
    {"id": "P2_FREEZE_AND_CORE_PIN", "scope": "this_phase", "evidence_tests": ("B00", "B11"),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "P2 frozen (before == after) e Core pin/tree invariati",
     "note": "Core non modificato, nessun branch Core, main intoccato."},
    {"id": "R0_R1_NO_REGRESSION", "scope": "this_phase", "evidence_tests": ("B10",),
     "declared": VERIFIED_LAB, "fallback": NOT_VERIFIED,
     "title": "Nessuna regressione R0-R1 (T01-T37) sul runtime modificato",
     "note": "36/37 PASS con T29/BLOCKED_ENVIRONMENT per policy (mock same-UID invariato), 0 FAIL."},

    # ---- requisiti APERTI: elencati, con lo stato che NON puo' diventare verificato qui ----
    {"id": "ORPHAN_RESERVED_LEASE", "scope": "this_phase", "evidence_tests": ("B08",),
     "declared": STILL_OPEN, "fallback": STILL_OPEN,
     "title": "Orphan RESERVED lease — nessuna reclaim autorizzata",
     "note": "B08 PASS significa che il gate ha VERIFICATO che il gap resta aperto: riprodotto, stati "
             "formalizzati, zero blind retry, RECLAIM_POLICY = NOT_AUTHORIZED (decisione di Human Review 01). "
             "Chiusura: serve una lease authority (finestra, attore, evidenza)."},
    {"id": "LEGACY_SPEND_PATHS_PROVIDER_GATE", "scope": "future_gate", "evidence_tests": ("B07",),
     "declared": BLOCKED_PROVIDER_GATE, "fallback": BLOCKED_PROVIDER_GATE,
     "title": "Legacy spend paths — chiusura dei percorsi residui prima del Provider Boundary Gate",
     "note": "Residui: LEGACY_LAB (usato da T01-T27), helper di test same-UID, primitive del Core, "
             "store.reconcile raw, P2 frozen fuori runtime. Vedi LEGACY_SPEND_PATHS.md."},
    {"id": "P_B02_P_B01_COMPOSITION", "scope": "this_phase", "evidence_tests": ("B03", "B04", "B01"),
     "declared": NOT_VERIFIED, "fallback": NOT_VERIFIED,
     "title": "P-B02 composta con P-B01 — reconciliation autenticata DENTRO lo spender isolato",
     "note": "NG-06: in B03/B04 segreto e chiave sono fixture del processo di test, non del daemon. "
             "La custodia del segreto e' un requisito di design, non un fatto dimostrato."},
    {"id": "RECONCILIATION_FRESHNESS_NG04", "scope": "future_gate", "evidence_tests": (),
     "declared": STILL_OPEN, "fallback": STILL_OPEN,
     "title": "NG-04 — freshness dei report di riconciliazione (max_age_s obbligatorio e fail-closed)",
     "note": "Oggi opzionale: il nonce monouso impedisce il riuso, non l'eta'. Non implementato in "
             "questo delta per decisione esplicita di Human Review 02."},
    {"id": "NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY", "scope": "this_phase", "evidence_tests": ("B12",),
     "declared": OPEN_CONSERVATIVE_LIMITATION, "fallback": OPEN_CONSERVATIVE_LIMITATION,
     "title": "NG-05 — atomicita' della terminalizzazione pre-submit (due transazioni)",
     "note": "Limite dichiarato e conservativo, NON blocker per questo gate LAB (Human Review 02): "
             "un'interruzione lascia un terminale non regolato con esposizione mantenuta, visibile e "
             "riparabile (settle idempotente). API additiva del Core proposta, non necessaria."},
    {"id": "REAL_AUTHORIZATION_AND_PRICING", "scope": "future_gate", "evidence_tests": ("B09",),
     "declared": NOT_VERIFIED, "fallback": NOT_VERIFIED,
     "title": "Authorization / pricing reali del provider",
     "note": "B09 verifica lo stato LAB dell'autorita'. Nessuna verifica contro sistemi reali: "
             "'real provider authorization' e 'real pricing verified' restano NOT_VERIFIED."},
    {"id": "REAL_PROVIDER_RECONCILIATION", "scope": "future_gate", "evidence_tests": (),
     "declared": NOT_VERIFIED, "fallback": NOT_VERIFIED,
     "title": "Reconciliation verificata contro un provider reale",
     "note": "Fuori scope di questa fase per mandato (nessun provider reale, nessuna credenziale)."},
    {"id": "RUN_CONTAMINATION", "scope": "other_phase", "evidence_tests": (),
     "declared": NOT_RUN, "fallback": NOT_RUN,
     "title": "run_contamination", "note": "Input Tenant assente: non eseguito."},
    {"id": "G_N02_SEMANTIC_CLAIM_PARAPHRASE", "scope": "other_phase", "evidence_tests": (),
     "declared": STILL_OPEN, "fallback": STILL_OPEN,
     "title": "G-N02 — semantic claim paraphrase", "note": "Fuori scope, non toccato."},
    {"id": "RV07_SCHEDULER_RECOVERY_RESIDUAL", "scope": "other_phase", "evidence_tests": (),
     "declared": STILL_OPEN, "fallback": STILL_OPEN,
     "title": "RV07 — residuo scheduler/recovery",
     "note": "Non toccato. P-B02 fornisce l'uscita autenticata da SUBMIT_UNKNOWN, ma nessuno scheduler la invoca."},
    {"id": "INDEPENDENT_CI_STATUS_CHECKS", "scope": "other_phase", "evidence_tests": (),
     "declared": NOT_RUN, "fallback": NOT_RUN,
     "title": "Status check CI indipendenti", "note": "Assenti sul branch, come nella fase precedente."},
)


# ---------------------------------------------------------------- costruzione del report
def classify_requirements(passed_ids) -> list[dict]:
    """Stato di ogni requisito, derivato dall'esito dei test che lo sostengono."""
    passed = set(passed_ids)
    out = []
    for r in REQUIREMENTS:
        missing = sorted(set(r["evidence_tests"]) - passed)
        state = r["declared"] if not missing else r["fallback"]
        reason = "EVIDENCE_TESTS_PASSED" if not missing else "EVIDENCE_TESTS_NOT_PASSED"
        if state not in REQUIREMENT_STATES:
            raise ReportingInconsistent(f"{r['id']}: stato sconosciuto {state!r}")
        out.append({"id": r["id"], "title": r["title"], "scope": r["scope"], "state": state,
                    "open": state in OPEN_STATES,
                    "counts_for_phase_readiness": r["scope"] in ("this_phase", "future_gate"),
                    "evidence_tests": list(r["evidence_tests"]), "evidence_tests_not_passed": missing,
                    "reason_code": reason, "note": r["note"]})
    return out


def build(results: list[dict], suite: dict) -> dict:
    """UNICO punto in cui nascono le due decisioni. `suite` e' il summary strutturato dei test
    (tests/gate_report.summarize): da li' si prendono SOLO i fatti sui test."""
    passed = [r["id"] for r in results if r.get("status") == "PASS"]
    failed = [r["id"] for r in results if r.get("status") == "FAIL"]
    blocked = [{"id": r["id"], "reason_code": r.get("reason_code")} for r in results if r.get("status") == "BLOCKED"]
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

    report = {
        "schema": "provider-boundary-phase-readiness/1",
        "test_suite": {
            "inventory": inventory, "total": suite["total"], "pass": suite["pass"], "fail": suite["fail"],
            "blocked": suite["blocked"], "pass_ids": passed, "fail_ids": failed, "blocked_tests": blocked,
            "all_tests_passed": all_tests_passed, "test_suite_decision": test_decision,
            "meaning": "i test del gate hanno prodotto l'esito atteso. NON significa che i requisiti di "
                       "fase siano chiusi: un test PASS puo' verificare che un requisito resta APERTO.",
        },
        "phase_readiness": {
            "all_requirements_verified": all_requirements_verified,
            "phase_gate_decision": phase_decision,
            "open_requirements": [{k: r[k] for k in ("id", "state", "scope", "title", "note")} for r in open_all],
            "open_requirements_blocking_all_verified": [r["id"] for r in open_blocking],
            "open_requirements_this_phase": [r["id"] for r in open_all if r["scope"] == "this_phase"],
            "open_requirements_future_gate": [r["id"] for r in open_all if r["scope"] == "future_gate"],
            "open_requirements_other_phase": [r["id"] for r in open_all if r["scope"] == "other_phase"],
            "verified_requirements": [r["id"] for r in verified],
            "requirements": reqs,
            "max_state": MAX_STATE if phase_decision in PHASE_DECISIONS_ALLOWING_MAX_STATE else NOT_READY,
            "meaning": "i requisiti della fase sono chiusi? `all_requirements_verified` e' vero SOLO se "
                       "nessun requisito di questa fase o del Provider Boundary Gate e' aperto (STILL_OPEN, "
                       "BLOCKED_PROVIDER_GATE, NOT_VERIFIED, NOT_RUN, OPEN_CONSERVATIVE_LIMITATION) e tutti i "
                       "test sono PASS.",
            "not_implied": ["provider ready", "production ready", "credenziali autorizzate",
                            "spend autorizzato", "merge autorizzato", "R2 autorizzato"],
        },
        "runner_exit": 0 if all_tests_passed else (2 if test_decision == TEST_SUITE_INVALID else 1),
    }
    report["runner_exit_meaning"] = {
        0: "tutti i test del gate hanno prodotto l'esito atteso. NON significa 'tutti i requisiti di fase verificati': vedi phase_readiness.",
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
        raise ReportingInconsistent(
            f"all_requirements_verified=true con requisiti aperti: {blocking}")
    # invariante esplicito richiesto da Human Review 02: nessun STILL_OPEN / BLOCKED_PROVIDER_GATE
    # imputabile alla fase puo' coesistere con "tutto verificato".
    if pr.get("all_requirements_verified"):
        for r in (pr.get("requirements") or []):
            if r.get("state") in (STILL_OPEN, BLOCKED_PROVIDER_GATE) and r.get("counts_for_phase_readiness"):
                raise ReportingInconsistent(
                    f"all_requirements_verified=true mentre {r['id']} e' {r['state']}")
    if pr.get("all_requirements_verified") and not ts.get("all_tests_passed"):
        raise ReportingInconsistent("all_requirements_verified=true con test non tutti PASS")
    if pr.get("phase_gate_decision") == PHASE_COMPLETE_ALL_VERIFIED and not pr.get("all_requirements_verified"):
        raise ReportingInconsistent("decisione di fase ALL_VERIFIED senza all_requirements_verified")
    if open_ids & verified_ids:
        raise ReportingInconsistent(f"requisiti contemporaneamente aperti e verificati: {sorted(open_ids & verified_ids)}")
    if ts.get("all_tests_passed") and (ts.get("fail_ids") or ts.get("blocked_tests")):
        raise ReportingInconsistent("all_tests_passed=true con FAIL o BLOCKED presenti")
    for r in (pr.get("requirements") or []):
        if (r["state"] in OPEN_STATES) != bool(r["open"]):
            raise ReportingInconsistent(f"{r['id']}: flag `open` incoerente con lo stato {r['state']}")
    return report


# ---------------------------------------------------------------- rendering (deriva, non ricalcola)
def machine_readable_gaps(report: dict) -> dict:
    """Mappa id -> stato, per MANIFEST.json e per chiunque legga il bundle a macchina."""
    return {r["id"]: r["state"] for r in report["phase_readiness"]["requirements"]}


def console(report: dict) -> str:
    ts, pr = report["test_suite"], report["phase_readiness"]
    lines = [
        "",
        f"A. TEST SUITE   {ts['pass']}/{ts['total']} PASS · FAIL {ts['fail_ids'] or 'nessuno'} · "
        f"BLOCKED {[b['id'] + '/' + b['reason_code'] for b in ts['blocked_tests']] or 'nessuno'} · "
        f"inventario {ts['inventory']['observed_count']}/{ts['inventory']['expected_count']} valido={ts['inventory']['valid']}",
        f"   all_tests_passed = {str(ts['all_tests_passed']).lower()} · test_suite_decision = {ts['test_suite_decision']}",
        "",
        f"B. PHASE READINESS   all_requirements_verified = {str(pr['all_requirements_verified']).lower()} · "
        f"phase_gate_decision = {pr['phase_gate_decision']}",
        f"   aperti che impediscono ALL_VERIFIED: {pr['open_requirements_blocking_all_verified'] or 'nessuno'}",
        f"     - di questa fase: {pr['open_requirements_this_phase'] or 'nessuno'}",
        f"     - rinviati al Provider Boundary Gate: {pr['open_requirements_future_gate'] or 'nessuno'}",
        f"   di altre fasi (elencati, non imputati): {pr['open_requirements_other_phase'] or 'nessuno'}",
        f"   stato massimo: {pr['max_state']}",
        "",
        f"runner exit {report['runner_exit']}: {report['runner_exit_meaning']}",
    ]
    return "\n".join(lines)


def markdown(report: dict) -> list[str]:
    ts, pr = report["test_suite"], report["phase_readiness"]
    lines = ["## A. TEST SUITE RESULT", "",
             f"| inventario | PASS | FAIL | BLOCKED | all_tests_passed | test_suite_decision |",
             "|---|---|---|---|---|---|",
             f"| {ts['inventory']['observed_count']}/{ts['inventory']['expected_count']} "
             f"(valido: {ts['inventory']['valid']}) | {ts['pass']} | {ts['fail']} | {ts['blocked']} | "
             f"**{str(ts['all_tests_passed']).lower()}** | `{ts['test_suite_decision']}` |", "",
             f"_{ts['meaning']}_", "",
             "## B. PHASE / REQUIREMENT READINESS", "",
             f"**`all_requirements_verified = {str(pr['all_requirements_verified']).lower()}`** · "
             f"**`phase_gate_decision = {pr['phase_gate_decision']}`** · stato massimo: `{pr['max_state']}`", "",
             f"_{pr['meaning']}_", "",
             "| REQUISITO | SCOPE | STATO | EVIDENZA | NOTA |", "|---|---|---|---|---|"]
    for r in pr["requirements"]:
        ev = ", ".join(r["evidence_tests"]) or "—"
        lines.append(f"| {r['id']} | {r['scope']} | **`{r['state']}`** | {ev} | {r['note']} |")
    lines += ["", f"Requisiti aperti che impediscono `all_requirements_verified`: "
                  f"{pr['open_requirements_blocking_all_verified'] or 'nessuno'} "
                  f"(di questa fase: {pr['open_requirements_this_phase'] or 'nessuno'}; rinviati al Provider "
                  f"Boundary Gate: {pr['open_requirements_future_gate'] or 'nessuno'}). Di altre fasi, elencati "
                  f"ma non imputati a questa: {pr['open_requirements_other_phase'] or 'nessuno'}.", "",
              "Nulla di quanto sopra significa provider ready, production ready, credenziali autorizzate, "
              "spend autorizzato, merge autorizzato o R2 autorizzato.", ""]
    return lines


README_BEGIN = "<!-- READINESS:BEGIN (generato da pbgate/phase_readiness.py — non modificare a mano) -->"
README_END = "<!-- READINESS:END -->"


def readme_block(report: dict) -> str:
    ts, pr = report["test_suite"], report["phase_readiness"]
    return "\n".join([
        README_BEGIN,
        "## Stato (authority unica: `pbgate/phase_readiness.py`)", "",
        f"**A. Test suite** — {ts['pass']}/{ts['total']} PASS, FAIL {ts['fail']}, BLOCKED {ts['blocked']}, "
        f"inventario {ts['inventory']['observed_count']}/{ts['inventory']['expected_count']} valido: "
        f"`all_tests_passed = {str(ts['all_tests_passed']).lower()}`, `test_suite_decision = {ts['test_suite_decision']}`.", "",
        f"**B. Phase readiness** — `all_requirements_verified = {str(pr['all_requirements_verified']).lower()}`, "
        f"`phase_gate_decision = {pr['phase_gate_decision']}`, stato massimo `{pr['max_state']}`.", "",
        "Requisiti aperti che impediscono `all_requirements_verified`: "
        + (", ".join(f"`{i}`" for i in pr["open_requirements_blocking_all_verified"]) or "nessuno") + ".",
        "", "Di questa fase: " + (", ".join(f"`{i}`" for i in pr["open_requirements_this_phase"]) or "nessuno")
        + ". Rinviati al Provider Boundary Gate: "
        + (", ".join(f"`{i}`" for i in pr["open_requirements_future_gate"]) or "nessuno") + ".",
        "", "Un test PASS su un requisito aperto significa che il gate ha verificato che quel requisito "
        "resta aperto: non lo chiude. Dettaglio per requisito in `TEST_RESULTS.md` e `OPEN_GAPS.md`.",
        README_END])
