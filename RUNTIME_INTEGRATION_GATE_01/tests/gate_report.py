"""Contratto di REPORTING del gate (follow-up T29, 2026-09-17). Solo reporting: nessuna logica R0-R1.

Una sola authority per lo stato di un test, strutturata e tri-state:

    status        PASS | FAIL | BLOCKED
    reason_code   codice chiuso (VERIFIED, ASSERTION_FAILED, EXCEPTION, MALFORMED_RESULT,
                  EVIDENCE_MISSING, BLOCKED_<...>)
    evidence      riferimento a un file esistente sotto evidence/
    diagnostic_exit  exit diagnostico del SINGOLO test (0 verificato, 1 non verificato / bloccato,
                  2 eccezione o risultato malformato). NON e' l'exit del runner.

BLOCKED nasce SOLO da `GateBlocked` sollevata dal test per una precondizione ambientale
riconosciuta. Non si deduce da testo libero, da `actual.startswith("BLOCKED")`, dall'ID del test
o da `pass == False`. BLOCKED = requisito NON verificabile nell'ambiente corrente, NON superato.

L'evidence reference deve risolversi (realpath) DENTRO `<gate_root>/evidence/`: path assoluti,
traversal, file esistenti altrove e symlink in uscita sono rifiutati.

`pass` resta nei risultati solo come campo LEGACY derivato (`status == "PASS"`): nessun
consumer interno lo usa per ricostruire lo stato tri-state.

Stato del test != decisione del gate. `summarize()` produce la decisione complessiva e l'exit
del runner: exit 0 significa "raccolta e report completati, nessun FAIL, nessun BLOCKED fuori
policy LAB", MAI "tutti i requisiti verificati". I requisiti BLOCKED restano elencati come
NON verificati e impediscono qualunque dichiarazione di readiness reale.
"""
from __future__ import annotations

import json
import os
import re
import traceback

STATUSES = ("PASS", "FAIL", "BLOCKED")
REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Inventario CANONICO del gate: ogni ID deve comparire ESATTAMENTE una volta (insieme, non ordine).
# ID mancante, inatteso o duplicato -> GATE_INVALID (fail-closed): un gate incompleto non certifica nulla.
EXPECTED_TEST_IDS: frozenset[str] = frozenset(f"T{i:02d}" for i in range(1, 38))

# Policy LAB/MOCK: i soli BLOCKED ammessi senza rendere il gate non favorevole.
# T29 = P-B01 isolamento di privilegio: nell'ambiente corrente orchestrator e worker hanno lo
# stesso uid, il requisito non e' verificabile. Resta un gap aperto (P-B01 BLOCKED_ENVIRONMENT).
LAB_ALLOWED_BLOCKED: dict[str, frozenset[str]] = {"T29": frozenset({"BLOCKED_ENVIRONMENT"})}

GATE_COMPLETE_ALL_VERIFIED = "LAB_GATE_COMPLETE_ALL_VERIFIED"
GATE_COMPLETE_WITH_ALLOWED_BLOCKED = "LAB_GATE_COMPLETE_WITH_ALLOWED_BLOCKED"
GATE_NOT_FAVORABLE = "GATE_NOT_FAVORABLE"
GATE_INVALID = "GATE_INVALID"

RUNNER_EXIT_MEANING = {
    0: "raccolta e report completati; nessun FAIL; nessun BLOCKED fuori policy LAB. NON significa 'tutti i requisiti verificati'.",
    1: "almeno un FAIL, oppure un BLOCKED non ammesso dalla policy LAB: gate NON favorevole.",
    2: "risultati invalidi (inventario T01..T37 non esatto: ID mancanti, inattesi o duplicati; oppure struttura malformata): gate INVALIDO, fail-closed.",
}


class GateBlocked(Exception):
    """Un test la solleva quando una PRECONDIZIONE AMBIENTALE riconosciuta impedisce di
    verificare il requisito. Porta il proprio reason_code (BLOCKED_*), l'`actual` diagnostico
    e il riferimento all'evidenza gia' scritta. Non e' un esito positivo."""

    def __init__(self, reason_code: str, actual: str, evidence: str):
        self.reason_code, self.actual, self.evidence = reason_code, actual, evidence
        super().__init__(f"{reason_code}: {actual}")


def evidence_problems(evidence: str, evidence_root: str) -> list[str]:
    """Il riferimento deve essere un path RELATIVO che, risolto (realpath: symlink e `..` compresi),
    cade DENTRO la directory canonica `<evidence_root>/evidence/` ed e' un file esistente.
    Path assoluti, traversal, file esistenti altrove (tests/, runtime/, ...) e symlink che escono
    dalla directory canonica sono rifiutati (fail-closed)."""
    canonical = os.path.realpath(os.path.join(evidence_root, "evidence"))
    if os.path.isabs(evidence):
        return [f"evidence path assoluto non ammesso: {evidence!r}"]
    resolved = os.path.realpath(os.path.join(evidence_root, evidence))
    try:
        inside = os.path.commonpath([canonical, resolved]) == canonical and resolved != canonical
    except ValueError:
        inside = False
    if not inside:
        return [f"evidence fuori dalla directory canonica evidence/: {evidence!r}"]
    if not os.path.isfile(resolved):
        return [f"evidence non trovata: {evidence!r}"]
    return []


# Inventario CANONICO delle probe di T29: con UID distinti solo ESATTAMENTE queste quattro probe,
# tutte realmente bloccate, possono produrre PASS. Probe mancanti, inattese o malformate -> FAIL.
T29_EXPECTED_ATTEMPT_KEYS: frozenset[str] = frozenset({
    "read_worker_secret", "write_worker_code", "write_worker_store", "direct_dispatch_on_worker_store"})
# Forme ammesse di una probe bloccata: esattamente quelle prodotte dal test (`BLOCKED` oppure
# `BLOCKED (<diagnostica>)`). Qualunque altra stringa (es. BLOCKED_BUT_NOT_REALLY) NON e' bloccata.
T29_BLOCKED_FORM = re.compile(r"^BLOCKED(?: \([^()\n]+\))?$")


def t29_probe_blocked(value) -> bool:
    return isinstance(value, str) and T29_BLOCKED_FORM.match(value) is not None


def t29_status(same_uid: bool, attempts) -> tuple[str, str]:
    """Policy di classificazione di T29 (P-B01 isolamento di privilegio), decisione umana congelata:
    se orchestrator e worker condividono lo UID la precondizione per verificare P-B01 NON esiste ->
    BLOCKED/BLOCKED_ENVIRONMENT, QUALUNQUE sia l'esito contingente delle probe. Solo con UID
    distinti decidono le probe, e SOLO l'inventario canonico completo (T29_EXPECTED_ATTEMPT_KEYS,
    nessuna chiave mancante o inattesa) con ogni valore nella forma bloccata ammessa -> PASS.
    attempts non mapping, vuoto, incompleto, con chiavi extra o valori malformati -> FAIL."""
    if same_uid:
        return "BLOCKED", "BLOCKED_ENVIRONMENT"
    if not isinstance(attempts, dict):
        return "FAIL", "ASSERTION_FAILED"
    if set(attempts) != T29_EXPECTED_ATTEMPT_KEYS:
        return "FAIL", "ASSERTION_FAILED"
    if not all(t29_probe_blocked(attempts[k]) for k in T29_EXPECTED_ATTEMPT_KEYS):
        return "FAIL", "ASSERTION_FAILED"
    return "PASS", "VERIFIED"


def make_result(test_id: str, title: str, expected: str, *, status, reason_code, actual, evidence,
                diagnostic_exit, evidence_root: str) -> dict:
    """Costruisce UN risultato strutturato. Qualunque input malformato degrada a FAIL (fail-closed)
    conservando in `raw` cio' che e' stato ricevuto."""
    raw = {"status": status, "reason_code": reason_code, "evidence": evidence, "diagnostic_exit": diagnostic_exit}
    problems: list[str] = []
    if status not in STATUSES:
        problems.append(f"status sconosciuto {status!r}")
    if not isinstance(reason_code, str) or not REASON_RE.match(reason_code or ""):
        problems.append(f"reason_code non valido {reason_code!r}")
    elif status == "BLOCKED" and not reason_code.startswith("BLOCKED_"):
        problems.append(f"BLOCKED richiede reason_code BLOCKED_*, ricevuto {reason_code!r}")
    elif status != "BLOCKED" and reason_code.startswith("BLOCKED_"):
        problems.append(f"reason_code {reason_code!r} ammesso solo con status BLOCKED")
    if not isinstance(evidence, str) or not evidence.strip():
        problems.append("evidence assente")
    else:
        problems += evidence_problems(evidence, evidence_root)
    if not isinstance(diagnostic_exit, int) or isinstance(diagnostic_exit, bool) or diagnostic_exit < 0:
        problems.append(f"diagnostic_exit non valido {diagnostic_exit!r}")
    if problems:
        final_status = "FAIL"
        final_reason = "EVIDENCE_MISSING" if all("evidence" in p for p in problems) else "MALFORMED_RESULT"
        final_exit = 2
        actual = f"FAIL-CLOSED ({'; '.join(problems)}) — ricevuto: {actual}"
    else:
        final_status, final_reason, final_exit = status, reason_code, diagnostic_exit
    return {"id": test_id, "title": title, "expected": expected, "actual": str(actual),
            "status": final_status, "reason_code": final_reason,
            "evidence": evidence if isinstance(evidence, str) else None,
            "diagnostic_exit": final_exit,
            "pass": final_status == "PASS",     # LEGACY, derivato: mai usato per ricostruire lo stato
            "raw": raw if problems else None}


def run_and_classify(test_id: str, title: str, expected: str, fn, *, evidence_root: str, exception_evidence) -> dict:
    """Esegue `fn` e classifica. Contratto di `fn`: restituisce (actual, evidence, ok: bool)
    per PASS/FAIL; solleva GateBlocked per BLOCKED; qualunque altra eccezione e' FAIL/EXCEPTION."""
    try:
        out = fn()
        if not (isinstance(out, tuple) and len(out) == 3):
            ev = exception_evidence(test_id, {"malformed_return": repr(out)})
            return make_result(test_id, title, expected, status="FAIL", reason_code="MALFORMED_RESULT",
                               actual=f"risultato malformato: {out!r}", evidence=ev, diagnostic_exit=2,
                               evidence_root=evidence_root)
        actual, ev, ok = out
        if not isinstance(ok, bool):
            return make_result(test_id, title, expected, status="FAIL", reason_code="MALFORMED_RESULT",
                               actual=f"esito non booleano {ok!r}: {actual}", evidence=ev, diagnostic_exit=2,
                               evidence_root=evidence_root)
        return make_result(test_id, title, expected, status="PASS" if ok else "FAIL",
                           reason_code="VERIFIED" if ok else "ASSERTION_FAILED", actual=actual, evidence=ev,
                           diagnostic_exit=0 if ok else 1, evidence_root=evidence_root)
    except GateBlocked as b:
        return make_result(test_id, title, expected, status="BLOCKED", reason_code=b.reason_code,
                           actual=b.actual, evidence=b.evidence, diagnostic_exit=1, evidence_root=evidence_root)
    except Exception as e:                                          # noqa: BLE001
        ev = exception_evidence(test_id, {"trace": traceback.format_exc()})
        return make_result(test_id, title, expected, status="FAIL", reason_code="EXCEPTION",
                           actual=f"EXCEPTION {type(e).__name__}: {e}", evidence=ev, diagnostic_exit=2,
                           evidence_root=evidence_root)


def summarize(results: list[dict], policy: dict[str, frozenset[str]] | None = None,
              expected_ids: frozenset[str] | set[str] | None = None) -> dict:
    """Decisione del gate ed exit del runner, derivate SOLO da `status`/`reason_code` strutturati.
    L'inventario atteso (default: EXPECTED_TEST_IDS = T01..T37) deve coincidere ESATTAMENTE con gli ID
    osservati, ciascuno una sola volta; l'ordine non e' authority. Altrimenti GATE_INVALID."""
    policy = LAB_ALLOWED_BLOCKED if policy is None else policy
    expected = frozenset(EXPECTED_TEST_IDS if expected_ids is None else expected_ids)
    ids = [r.get("id") for r in results]
    invalid: list[str] = []
    dup = sorted({i for i in ids if ids.count(i) > 1})
    missing = sorted(expected - set(ids))
    unexpected = sorted(set(ids) - expected)
    if dup:
        invalid.append(f"ID duplicati: {dup}")
    if missing:
        invalid.append(f"ID attesi mancanti: {missing}")
    if unexpected:
        invalid.append(f"ID inattesi: {unexpected}")
    inventory = {"expected_count": len(expected), "observed_count": len(ids), "missing": missing,
                 "unexpected": unexpected, "duplicates": dup, "valid": not (dup or missing or unexpected)}
    for r in results:
        if r.get("status") not in STATUSES or not isinstance(r.get("reason_code"), str):
            invalid.append(f"{r.get('id')}: risultato non strutturato")
    passed = [r["id"] for r in results if r.get("status") == "PASS"]
    failed = [r["id"] for r in results if r.get("status") == "FAIL"]
    blocked = [{"id": r["id"], "reason_code": r.get("reason_code")} for r in results if r.get("status") == "BLOCKED"]
    blocked_ids = [b["id"] for b in blocked]
    unallowed = [b for b in blocked if b["reason_code"] not in policy.get(b["id"], frozenset())]
    if invalid:
        decision, runner_exit = GATE_INVALID, 2
    elif failed or unallowed:
        decision, runner_exit = GATE_NOT_FAVORABLE, 1
    elif blocked:
        decision, runner_exit = GATE_COMPLETE_WITH_ALLOWED_BLOCKED, 0
    else:
        decision, runner_exit = GATE_COMPLETE_ALL_VERIFIED, 0
    return {"total": len(results), "pass": len(passed), "fail": len(failed), "blocked": len(blocked),
            "inventory": inventory,
            "pass_ids": passed, "fail_ids": failed, "blocked_tests": blocked,
            "blocked_not_allowed_by_policy": unallowed, "invalid": invalid,
            "policy_allowed_blocked": {k: sorted(v) for k, v in policy.items()},
            "gate_decision": decision, "runner_exit": runner_exit,
            "runner_exit_meaning": RUNNER_EXIT_MEANING[runner_exit],
            "all_requirements_verified": (not invalid and not failed and not blocked),
            "unverified_requirements": blocked_ids + failed,
            "readiness": {"lab_mock": decision in (GATE_COMPLETE_ALL_VERIFIED, GATE_COMPLETE_WITH_ALLOWED_BLOCKED),
                          "real_provider": "NOT_DECLARED", "production": "NOT_DECLARED",
                          "security_boundary_p_b01": "VERIFIED" if ("T29" in passed) else "NOT_VERIFIED"}}


def console_line(r: dict) -> str:
    color = {"PASS": "32", "FAIL": "31", "BLOCKED": "33"}[r["status"]]
    return (f"  {r['id']} \033[{color}m{r['status']}\033[0m  {r['title']}  [{r['reason_code']} exit={r['diagnostic_exit']}]"
            f"\n       \033[2m{r['actual']}\033[0m")


def console_summary(s: dict) -> str:
    return (f"\n{s['pass']}/{s['total']} PASS · BLOCKED {[b['id'] + '/' + b['reason_code'] for b in s['blocked_tests']]} "
            f"· FAIL {s['fail_ids']}\nGATE_DECISION: {s['gate_decision']} · runner exit {s['runner_exit']} "
            f"({s['runner_exit_meaning']})\ninventario: {s['inventory']['observed_count']}/{s['inventory']['expected_count']} "
            f"valido={s['inventory']['valid']}" + (f" {s['invalid']}" if s['invalid'] else "")
            + f"\nrequisiti NON verificati: {s['unverified_requirements'] or 'nessuno'}")


def render_markdown(results: list[dict], s: dict, required_core_sha: str) -> str:
    lines = ["# TEST_RESULTS — RUNTIME INTEGRATION GATE 01", "",
             f"Core canonical: `{required_core_sha}` · provider: FakeAdapter only · crediti spesi: 0 · rete generativa: nessuna", "",
             "Stato per test (authority unica, tri-state): PASS = requisito verificato · FAIL = requisito NON superato · "
             "BLOCKED = requisito NON verificabile nell'ambiente corrente (NON superato). "
             "EXIT = exit diagnostico del singolo test, distinto dall'exit del runner.", "",
             "| TEST | TITLE | EXPECTED | ACTUAL | STATUS | REASON_CODE | EXIT | EVIDENCE |",
             "|---|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['id']} | {r['title']} | {r['expected']} | {r['actual']} | **{r['status']}** | "
                     f"`{r['reason_code']}` | {r['diagnostic_exit']} | `{r['evidence']}` |")
    lines += ["", f"**Totale: {s['pass']}/{s['total']} PASS · BLOCKED: "
              f"{[b['id'] + '/' + b['reason_code'] for b in s['blocked_tests']] or 'nessuno'} · FAIL: {s['fail_ids'] or 'nessuno'}**", "",
              f"**GATE_DECISION: `{s['gate_decision']}`** · runner exit {s['runner_exit']}: {s['runner_exit_meaning']}", "",
              f"Inventario: {s['inventory']['observed_count']}/{s['inventory']['expected_count']} atteso · valido: {s['inventory']['valid']}"
              + (f" · mancanti {s['inventory']['missing']} · inattesi {s['inventory']['unexpected']} · duplicati {s['inventory']['duplicates']}" if not s['inventory']['valid'] else ""), "",
              f"Requisiti NON verificati: {s['unverified_requirements'] or 'nessuno'} · "
              f"all_requirements_verified: {s['all_requirements_verified']} · "
              f"P-B01 security boundary: {s['readiness']['security_boundary_p_b01']} · real provider: {s['readiness']['real_provider']}", ""]
    if s["blocked_not_allowed_by_policy"] or s["invalid"]:
        lines += [f"BLOCKED fuori policy: {s['blocked_not_allowed_by_policy']} · invalid: {s['invalid']}", ""]
    return "\n".join(lines)


def write(results: list[dict], s: dict, *, gate_root: str, evidence_dir: str, required_core_sha: str) -> None:
    """RESULTS.json (results + summary) e TEST_RESULTS.md derivano dalla STESSA struttura."""
    with open(os.path.join(gate_root, "TEST_RESULTS.md"), "w", encoding="utf-8") as fh:
        fh.write(render_markdown(results, s, required_core_sha))
    with open(os.path.join(evidence_dir, "RESULTS.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema": "runtime-gate-results/2", "required_core_sha": required_core_sha,
                   "results": results, "summary": s}, fh, indent=2, ensure_ascii=False)
