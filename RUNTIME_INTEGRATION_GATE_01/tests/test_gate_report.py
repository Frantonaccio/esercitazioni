#!/usr/bin/env python3
"""Test MIRATI del contratto di reporting (tests/gate_report.py). Nessun Core, nessun runtime,
nessun provider: solo classificazione, summary, rendering e coerenza dei conteggi.
Controprove fail-closed richieste dal mandato REPORTING T29 (2026-09-17): CP1..CP8 + CP9 (36+1);
HUMAN REVIEW di ffaa4ec8 (2026-09-17): CP10 precedenza T29, CP11 inventario T01-T37, CP12 containment evidence;
HUMAN REVIEW v3 di f01bbf52 (2026-09-17): CP13 inventario canonico delle 4 probe T29 e forma dei valori."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from tests import gate_report as gr                                   # noqa: E402

ROOT = tempfile.mkdtemp(prefix="gate_report_test_")
EVD = os.path.join(ROOT, "evidence"); os.makedirs(EVD)
CHECKS: list[tuple[str, bool, str]] = []


def ev(name: str) -> str:
    p = os.path.join(EVD, f"{name}.json")
    with open(p, "w") as fh:
        json.dump({"synthetic": name}, fh)
    return os.path.relpath(p, ROOT)


def exc_ev(tid, payload):
    p = os.path.join(EVD, f"{tid}_exception.json")
    with open(p, "w") as fh:
        json.dump(payload, fh)
    return os.path.relpath(p, ROOT)


def run(tid, fn, title="t", expected="e"):
    return gr.run_and_classify(tid, title, expected, fn, evidence_root=ROOT, exception_evidence=exc_ev)


def sm(results):
    """summarize() su un inventario esplicito pari agli ID del sottoinsieme sintetico."""
    return gr.summarize(results, expected_ids={r["id"] for r in results})


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not cond else ""))


def everywhere(results, tid, status, reason):
    """Lo stesso stato deve comparire in risultato, JSON, Markdown e console."""
    s = sm(results)
    md = gr.render_markdown(results, s, "deadbeef")
    console = "\n".join(gr.console_line(r) for r in results) + gr.console_summary(s)
    js = json.loads(json.dumps({"results": results, "summary": s}))
    r = next(x for x in js["results"] if x["id"] == tid)
    row = next(l for l in md.splitlines() if l.startswith(f"| {tid} |"))
    con = re.sub(r"\x1b\[[0-9;]*m", "", console)
    return (r["status"] == status and r["reason_code"] == reason
            and f"**{status}**" in row and f"`{reason}`" in row
            and f"{tid} {status}" in con and f"[{reason} exit=" in con)


print("CP1 PASS reale -> PASS ovunque")
r1 = run("T01", lambda: ("ok", ev("t01"), True))
check("CP1 status/reason/exit", r1["status"] == "PASS" and r1["reason_code"] == "VERIFIED" and r1["diagnostic_exit"] == 0)
check("CP1 ovunque", everywhere([r1], "T01", "PASS", "VERIFIED"))

print("CP2 FAIL reale -> FAIL ovunque")
r2 = run("T02", lambda: ("mismatch", ev("t02"), False))
check("CP2 status/reason/exit", r2["status"] == "FAIL" and r2["reason_code"] == "ASSERTION_FAILED" and r2["diagnostic_exit"] == 1)
check("CP2 ovunque", everywhere([r2], "T02", "FAIL", "ASSERTION_FAILED"))
s2 = sm([r1, r2])
check("CP2 gate non favorevole, runner exit 1", s2["gate_decision"] == gr.GATE_NOT_FAVORABLE and s2["runner_exit"] == 1)

print("CP3 T29 con precondizione ambientale riconosciuta -> BLOCKED / BLOCKED_ENVIRONMENT")
def t29_like():
    attempts = {"read_worker_secret": "BYPASS_POSSIBLE", "write_worker_code": "BYPASS_POSSIBLE",
                "write_worker_store": "BYPASS_POSSIBLE", "direct_dispatch_on_worker_store": "BYPASS_POSSIBLE"}
    raise gr.GateBlocked("BLOCKED_ENVIRONMENT", f"stesso uid (0) per orchestrator e worker; tentativi di bypass: {attempts}", ev("t29"))
r3 = run("T29", t29_like)
check("CP3 BLOCKED/BLOCKED_ENVIRONMENT, exit diagnostico 1", r3["status"] == "BLOCKED" and r3["reason_code"] == "BLOCKED_ENVIRONMENT" and r3["diagnostic_exit"] == 1)
check("CP3 ovunque", everywhere([r3], "T29", "BLOCKED", "BLOCKED_ENVIRONMENT"))
check("CP3 prova non attenuata (uid + 4 BYPASS_POSSIBLE visibili)", "stesso uid" in r3["actual"] and r3["actual"].count("BYPASS_POSSIBLE") == 4)
check("CP3 pass legacy derivato = False", r3["pass"] is False)
s3 = sm([r1, r3])
check("CP3 BLOCKED ammesso da policy: gate completo con BLOCKED, exit 0, NON tutti verificati",
      s3["gate_decision"] == gr.GATE_COMPLETE_WITH_ALLOWED_BLOCKED and s3["runner_exit"] == 0
      and s3["all_requirements_verified"] is False and s3["unverified_requirements"] == ["T29"]
      and s3["readiness"]["security_boundary_p_b01"] == "NOT_VERIFIED" and s3["readiness"]["real_provider"] == "NOT_DECLARED")

print("CP4 FAIL vero con actual che inizia con 'BLOCKED' -> resta FAIL")
r4 = run("T05", lambda: ("BLOCKED_ENVIRONMENT: testo libero che imita un blocco", ev("t05"), False))
check("CP4 FAIL/ASSERTION_FAILED nonostante il testo", r4["status"] == "FAIL" and r4["reason_code"] == "ASSERTION_FAILED")
check("CP4 ovunque", everywhere([r4], "T05", "FAIL", "ASSERTION_FAILED"))
s4 = sm([r4])
check("CP4 summary lo conta come FAIL, non BLOCKED", s4["fail_ids"] == ["T05"] and s4["blocked_tests"] == [] and s4["runner_exit"] == 1)
# anche con ID T29 e testo BLOCKED: senza GateBlocked e' FAIL
r4b = run("T29", lambda: ("BLOCKED_ENVIRONMENT: ma il test ha restituito False", ev("t29b"), False))
check("CP4b ID T29 + testo BLOCKED senza GateBlocked -> FAIL", r4b["status"] == "FAIL" and r4b["reason_code"] == "ASSERTION_FAILED")

print("CP5 eccezione inattesa dentro T29 -> FAIL, NON BLOCKED")
def t29_crash():
    raise OSError("stat fallito: secret_path None")
r5 = run("T29", t29_crash)
check("CP5 FAIL/EXCEPTION, exit 2, evidenza eccezione scritta", r5["status"] == "FAIL" and r5["reason_code"] == "EXCEPTION"
      and r5["diagnostic_exit"] == 2 and os.path.isfile(os.path.join(ROOT, r5["evidence"])))
check("CP5 ovunque", everywhere([r5], "T29", "FAIL", "EXCEPTION"))

print("CP6 stato sconosciuto / risultato malformato / evidenza assente -> fail-closed")
m1 = gr.make_result("T10", "t", "e", status="SKIPPED", reason_code="VERIFIED", actual="x", evidence=ev("t10"), diagnostic_exit=0, evidence_root=ROOT)
m2 = gr.make_result("T11", "t", "e", status="PASS", reason_code="VERIFIED", actual="x", evidence="evidence/non_esiste.json", diagnostic_exit=0, evidence_root=ROOT)
m3 = gr.make_result("T12", "t", "e", status="PASS", reason_code="VERIFIED", actual="x", evidence=None, diagnostic_exit=0, evidence_root=ROOT)
m4 = gr.make_result("T13", "t", "e", status="BLOCKED", reason_code="ENVIRONMENT", actual="x", evidence=ev("t13"), diagnostic_exit=1, evidence_root=ROOT)
m5 = gr.make_result("T14", "t", "e", status="PASS", reason_code="BLOCKED_ENVIRONMENT", actual="x", evidence=ev("t14"), diagnostic_exit=0, evidence_root=ROOT)
m6 = run("T15", lambda: ("ok", ev("t15"), None))
m7 = run("T16", lambda: "non una tupla")
m8 = gr.make_result("T17", "t", "e", status="PASS", reason_code="verified", actual="x", evidence=ev("t17"), diagnostic_exit=0, evidence_root=ROOT)
check("CP6 status sconosciuto -> FAIL/MALFORMED_RESULT", m1["status"] == "FAIL" and m1["reason_code"] == "MALFORMED_RESULT" and m1["diagnostic_exit"] == 2)
check("CP6 evidenza inesistente -> FAIL/EVIDENCE_MISSING", m2["status"] == "FAIL" and m2["reason_code"] == "EVIDENCE_MISSING")
check("CP6 evidenza None -> FAIL/EVIDENCE_MISSING", m3["status"] == "FAIL" and m3["reason_code"] == "EVIDENCE_MISSING")
check("CP6 BLOCKED senza reason BLOCKED_* -> FAIL", m4["status"] == "FAIL" and m4["reason_code"] == "MALFORMED_RESULT")
check("CP6 PASS con reason BLOCKED_* -> FAIL", m5["status"] == "FAIL")
check("CP6 esito non booleano -> FAIL/MALFORMED_RESULT", m6["status"] == "FAIL" and m6["reason_code"] == "MALFORMED_RESULT")
check("CP6 ritorno non tupla -> FAIL/MALFORMED_RESULT", m7["status"] == "FAIL" and m7["reason_code"] == "MALFORMED_RESULT")
check("CP6 reason_code fuori formato -> FAIL", m8["status"] == "FAIL" and m8["reason_code"] == "MALFORMED_RESULT")
check("CP6 raw conservato per audit", m1["raw"]["status"] == "SKIPPED")
smx = sm([{"id": "T18", "title": "t", "expected": "e", "actual": "x", "status": "MAYBE", "reason_code": "X"}])
check("CP6 summary con status non strutturato -> GATE_INVALID, exit 2", smx["gate_decision"] == gr.GATE_INVALID and smx["runner_exit"] == 2)

print("CP7 BLOCKED non previsto dalla policy LAB -> gate non favorevole")
r7a = run("T05", lambda: (_ for _ in ()).throw(gr.GateBlocked("BLOCKED_ENVIRONMENT", "blocco su test non in policy", ev("t05b"))))
r7b = run("T29", lambda: (_ for _ in ()).throw(gr.GateBlocked("BLOCKED_OTHER_REASON", "T29 con motivo non in policy", ev("t29c"))))
s7a, s7b = sm([r1, r7a]), sm([r1, r7b])
check("CP7a T05 BLOCKED_ENVIRONMENT -> GATE_NOT_FAVORABLE, exit 1", s7a["gate_decision"] == gr.GATE_NOT_FAVORABLE and s7a["runner_exit"] == 1
      and s7a["blocked_not_allowed_by_policy"] == [{"id": "T05", "reason_code": "BLOCKED_ENVIRONMENT"}])
check("CP7b T29 BLOCKED_OTHER_REASON -> GATE_NOT_FAVORABLE, exit 1", s7b["gate_decision"] == gr.GATE_NOT_FAVORABLE and s7b["runner_exit"] == 1)
check("CP7 lo stato del test resta BLOCKED (test != gate)", r7a["status"] == "BLOCKED" and r7b["status"] == "BLOCKED")

print("CP8 ogni test una sola volta; conteggi identici in JSON / Markdown / console")
mixed = [r1, r2, r3, r4]
s8 = sm(mixed)
md8 = gr.render_markdown(mixed, s8, "deadbeef")
con8 = re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(gr.console_line(r) for r in mixed) + gr.console_summary(s8))
js8 = json.loads(json.dumps({"results": mixed, "summary": s8}))
rows = [l for l in md8.splitlines() if re.match(r"^\| T\d\d \|", l)]
md_counts = (sum("**PASS**" in l for l in rows), sum("**FAIL**" in l for l in rows), sum("**BLOCKED**" in l for l in rows))
con_counts = (len(re.findall(r"^  T\d\d PASS", con8, re.M)), len(re.findall(r"^  T\d\d FAIL", con8, re.M)), len(re.findall(r"^  T\d\d BLOCKED", con8, re.M)))
js_counts = (js8["summary"]["pass"], js8["summary"]["fail"], js8["summary"]["blocked"])
direct = (sum(r["status"] == "PASS" for r in js8["results"]), sum(r["status"] == "FAIL" for r in js8["results"]), sum(r["status"] == "BLOCKED" for r in js8["results"]))
check("CP8 conteggi identici (1 PASS, 2 FAIL, 1 BLOCKED)", md_counts == con_counts == js_counts == direct == (1, 2, 1), f"md={md_counts} con={con_counts} js={js_counts}")
check("CP8 riga di totale coerente", "**Totale: 1/4 PASS" in md8 and "1/4 PASS" in con8)
check("CP8 ogni ID una sola volta nel markdown", len(rows) == 4 and len({l.split("|")[1].strip() for l in rows}) == 4)
sdup = sm([r1, dict(r1)])
check("CP8 ID duplicato -> GATE_INVALID, exit 2", sdup["gate_decision"] == gr.GATE_INVALID and sdup["runner_exit"] == 2 and "T01" in sdup["invalid"][0])

print("CP9 36 PASS + 1 BLOCKED (T29/BLOCKED_ENVIRONMENT) non diventa 37 PASS / ALL_GREEN")
full = [run(f"T{i:02d}", (lambda i=i: ("ok", ev(f"full{i}"), True))) for i in range(1, 38) if i != 29] + [r3]
s9 = gr.summarize(full)
check("CP9 36 PASS, 1 BLOCKED, 0 FAIL, totale 37", (s9["pass"], s9["blocked"], s9["fail"], s9["total"]) == (36, 1, 0, 37))
check("CP9 decisione = completo CON BLOCKED, exit 0 con significato esplicito", s9["gate_decision"] == gr.GATE_COMPLETE_WITH_ALLOWED_BLOCKED and s9["runner_exit"] == 0
      and "NON significa" in s9["runner_exit_meaning"])
check("CP9 nessuna readiness reale", s9["all_requirements_verified"] is False and s9["readiness"]["security_boundary_p_b01"] == "NOT_VERIFIED"
      and s9["readiness"]["real_provider"] == "NOT_DECLARED" and s9["readiness"]["production"] == "NOT_DECLARED")
md9 = gr.render_markdown(full, s9, "deadbeef")
check("CP9 markdown: 36/37 PASS e T29/BLOCKED_ENVIRONMENT, mai 37/37", "**Totale: 36/37 PASS · BLOCKED: ['T29/BLOCKED_ENVIRONMENT']" in md9 and "37/37 PASS" not in md9 and "Totale: 37/37" not in md9 and "Inventario: 37/37 atteso · valido: True" in md9)
# write(): JSON e MD dallo stesso oggetto
gr.write(full, s9, gate_root=ROOT, evidence_dir=EVD, required_core_sha="deadbeef")
j = json.load(open(os.path.join(EVD, "RESULTS.json")))
check("CP9 RESULTS.json contiene results + summary identici", j["summary"] == s9 and len(j["results"]) == 37 and j["schema"] == "runtime-gate-results/2")
check("CP9 T29 PASS reale -> tutti verificati", sm([run("T29", lambda: ("isolato", ev("t29ok"), True))])["all_requirements_verified"] is True)

print("CP10 T29 precedence: same_uid vince SEMPRE sulle probe (decisione umana congelata)")
ALL_BLOCKED = {"read_worker_secret": "BLOCKED (PermissionError)", "write_worker_code": "BLOCKED",
               "write_worker_store": "BLOCKED", "direct_dispatch_on_worker_store": "BLOCKED (CorePinError)"}
ALL_BYPASS = {k: "BYPASS_POSSIBLE" for k in ALL_BLOCKED}
ONE_BYPASS = dict(ALL_BLOCKED, write_worker_store="BYPASS_POSSIBLE")
check("CP10a same_uid + 4 probe BLOCKED -> BLOCKED/BLOCKED_ENVIRONMENT, NON PASS", gr.t29_status(True, ALL_BLOCKED) == ("BLOCKED", "BLOCKED_ENVIRONMENT"))
check("CP10b same_uid + 4 BYPASS_POSSIBLE -> BLOCKED/BLOCKED_ENVIRONMENT", gr.t29_status(True, ALL_BYPASS) == ("BLOCKED", "BLOCKED_ENVIRONMENT"))
check("CP10c uid distinti + almeno un BYPASS_POSSIBLE -> FAIL/ASSERTION_FAILED", gr.t29_status(False, ONE_BYPASS) == ("FAIL", "ASSERTION_FAILED")
      and gr.t29_status(False, ALL_BYPASS) == ("FAIL", "ASSERTION_FAILED"))
check("CP10d uid distinti + 4 probe BLOCKED -> PASS/VERIFIED", gr.t29_status(False, ALL_BLOCKED) == ("PASS", "VERIFIED"))
check("CP10e uid distinti + probe assenti/malformate -> FAIL (fail-closed)", gr.t29_status(False, {}) == ("FAIL", "ASSERTION_FAILED")
      and gr.t29_status(False, {"read_worker_secret": None}) == ("FAIL", "ASSERTION_FAILED"))
# stesso esito attraverso il runner: un test T29 che segue la policy con same_uid e probe tutte BLOCKED
def t29_same_uid_probes_blocked():
    st, rc = gr.t29_status(True, ALL_BLOCKED)
    if st == "BLOCKED":
        raise gr.GateBlocked(rc, f"stesso uid (0) per orchestrator e worker; tentativi di bypass: {ALL_BLOCKED}", ev("t29p"))
    return "x", ev("t29p"), st == "PASS"
r10 = run("T29", t29_same_uid_probes_blocked)
check("CP10f attraverso run_and_classify: BLOCKED/BLOCKED_ENVIRONMENT, pass legacy False", r10["status"] == "BLOCKED" and r10["reason_code"] == "BLOCKED_ENVIRONMENT" and r10["pass"] is False)

print("CP13 T29 probe inventory fail-closed (UID distinti)")
K = sorted(gr.T29_EXPECTED_ATTEMPT_KEYS)
check("CP13 inventario canonico = 4 probe attese", gr.T29_EXPECTED_ATTEMPT_KEYS == {"read_worker_secret", "write_worker_code", "write_worker_store", "direct_dispatch_on_worker_store"})
check("CP13a UID distinti + solo 1 delle 4 probe BLOCKED -> FAIL, NON PASS", gr.t29_status(False, {"read_worker_secret": "BLOCKED"}) == ("FAIL", "ASSERTION_FAILED"))
three = {k: "BLOCKED" for k in K[:3]}
check("CP13b UID distinti + 3/4 probe BLOCKED -> FAIL", gr.t29_status(False, three) == ("FAIL", "ASSERTION_FAILED"))
check("CP13c UID distinti + 4 probe BLOCKED -> PASS/VERIFIED", gr.t29_status(False, ALL_BLOCKED) == ("PASS", "VERIFIED"))
check("CP13d UID distinti + 4 BLOCKED + chiave extra -> FAIL", gr.t29_status(False, dict(ALL_BLOCKED, extra_probe="BLOCKED")) == ("FAIL", "ASSERTION_FAILED"))
check("CP13e UID distinti + chiave arbitraria foo: BLOCKED -> FAIL", gr.t29_status(False, {"foo": "BLOCKED"}) == ("FAIL", "ASSERTION_FAILED"))
check("CP13f UID distinti + valore BLOCKED_BUT_NOT_REALLY -> FAIL", gr.t29_status(False, dict(ALL_BLOCKED, write_worker_code="BLOCKED_BUT_NOT_REALLY")) == ("FAIL", "ASSERTION_FAILED")
      and gr.t29_status(False, dict(ALL_BLOCKED, write_worker_code="BLOCKEDX")) == ("FAIL", "ASSERTION_FAILED")
      and gr.t29_status(False, dict(ALL_BLOCKED, write_worker_code="BLOCKED (")) == ("FAIL", "ASSERTION_FAILED")
      and gr.t29_status(False, dict(ALL_BLOCKED, write_worker_code="blocked")) == ("FAIL", "ASSERTION_FAILED")
      and gr.t29_status(False, dict(ALL_BLOCKED, write_worker_code=" BLOCKED")) == ("FAIL", "ASSERTION_FAILED"))
nm = []
for bad in (None, "BLOCKED", ["BLOCKED"] * 4, 4, [("read_worker_secret", "BLOCKED")]):
    try:
        nm.append(gr.t29_status(False, bad))
    except Exception as e:                                          # noqa: BLE001
        nm.append(("EXC", type(e).__name__))
check("CP13g UID distinti + attempts non mapping -> FAIL, mai PASS", all(r == ("FAIL", "ASSERTION_FAILED") for r in nm), str(nm))
check("CP13h UID distinti + attempts vuoto -> FAIL", gr.t29_status(False, {}) == ("FAIL", "ASSERTION_FAILED"))
check("CP13i UID distinti + valore non stringa / None -> FAIL", gr.t29_status(False, dict(ALL_BLOCKED, read_worker_secret=None)) == ("FAIL", "ASSERTION_FAILED")
      and gr.t29_status(False, dict(ALL_BLOCKED, read_worker_secret=True)) == ("FAIL", "ASSERTION_FAILED"))
check("CP13j forme ammesse: BLOCKED e BLOCKED (<diagnostica>)", gr.t29_probe_blocked("BLOCKED") and gr.t29_probe_blocked("BLOCKED (PermissionError)")
      and gr.t29_probe_blocked("BLOCKED (CorePinError)") and not gr.t29_probe_blocked("BLOCKED ()") and not gr.t29_probe_blocked("BYPASS_POSSIBLE"))
check("CP13k precedenza conservata: same_uid + 4 BLOCKED -> BLOCKED; same_uid + 4 BYPASS -> BLOCKED; same_uid + attempts non mapping -> BLOCKED",
      gr.t29_status(True, ALL_BLOCKED) == ("BLOCKED", "BLOCKED_ENVIRONMENT") and gr.t29_status(True, ALL_BYPASS) == ("BLOCKED", "BLOCKED_ENVIRONMENT")
      and gr.t29_status(True, None) == ("BLOCKED", "BLOCKED_ENVIRONMENT"))
# attraverso il runner: policy con probe incomplete -> FAIL/ASSERTION_FAILED, mai PASS
def t29_distinct_uid_one_probe():
    st, rc = gr.t29_status(False, {"read_worker_secret": "BLOCKED"})
    return f"probe incomplete: {st}", ev("t29q"), st == "PASS"
r13 = run("T29", t29_distinct_uid_one_probe)
check("CP13l attraverso run_and_classify: FAIL/ASSERTION_FAILED", r13["status"] == "FAIL" and r13["reason_code"] == "ASSERTION_FAILED")
check("CP13m RUNNER_EXIT_MEANING[2] nomina ID mancanti/inattesi/duplicati", all(w in gr.RUNNER_EXIT_MEANING[2] for w in ("mancanti", "inattesi", "duplicati", "malformata")))

print("CP11 inventario canonico T01-T37 fail-closed (insieme esatto, ordine non authority)")
def full_pass(ids):
    return [run(i, (lambda i=i: ("ok", ev(f"inv_{i}"), True))) for i in ids]
canon = [f"T{i:02d}" for i in range(1, 38)]
check("CP11 EXPECTED_TEST_IDS == {T01..T37}", gr.EXPECTED_TEST_IDS == frozenset(canon) and len(gr.EXPECTED_TEST_IDS) == 37)
s11a = gr.summarize(full_pass(canon[:36]))                       # T37 assente, tutti PASS
check("CP11a T01-T36 tutti PASS, T37 assente -> GATE_INVALID, exit 2, NON all_verified", s11a["gate_decision"] == gr.GATE_INVALID and s11a["runner_exit"] == 2
      and s11a["all_requirements_verified"] is False and s11a["inventory"]["missing"] == ["T37"] and s11a["inventory"]["valid"] is False)
s11b = gr.summarize(full_pass(canon + ["T38"]))
check("CP11b T01-T37 + T38 -> GATE_INVALID, exit 2", s11b["gate_decision"] == gr.GATE_INVALID and s11b["runner_exit"] == 2 and s11b["inventory"]["unexpected"] == ["T38"])
import random
shuffled = canon[:]; random.Random(29).shuffle(shuffled)
s11c = gr.summarize(full_pass(shuffled))
check("CP11c T01-T37 esatti (ordine casuale) -> inventario valido, ALL_VERIFIED, exit 0", s11c["inventory"]["valid"] is True and s11c["gate_decision"] == gr.GATE_COMPLETE_ALL_VERIFIED
      and s11c["runner_exit"] == 0 and s11c["all_requirements_verified"] is True)
s11d = gr.summarize(full_pass([i for i in canon if i != "T29"]) + [r3])
check("CP11d 36 PASS + T29 BLOCKED su inventario esatto -> LAB_GATE_COMPLETE_WITH_ALLOWED_BLOCKED", s11d["gate_decision"] == gr.GATE_COMPLETE_WITH_ALLOWED_BLOCKED
      and s11d["inventory"]["valid"] is True and s11d["all_requirements_verified"] is False)
s11e = gr.summarize(full_pass(canon) + [run("T01", lambda: ("dup", ev("inv_dup"), True))])
check("CP11e T01-T37 + T01 duplicato -> GATE_INVALID, exit 2", s11e["gate_decision"] == gr.GATE_INVALID and s11e["runner_exit"] == 2 and s11e["inventory"]["duplicates"] == ["T01"])
s11f = gr.summarize([])
check("CP11f lista vuota -> GATE_INVALID, 37 mancanti, NON all_verified", s11f["gate_decision"] == gr.GATE_INVALID and len(s11f["inventory"]["missing"]) == 37 and s11f["all_requirements_verified"] is False)
md11 = gr.render_markdown(full_pass(canon[:36]), s11a, "deadbeef")
con11 = re.sub(r"\x1b\[[0-9;]*m", "", gr.console_summary(s11a))
check("CP11g inventario invalido visibile in Markdown e console", "valido: False" in md11 and "mancanti ['T37']" in md11 and "valido=False" in con11)

print("CP12 evidence path: containment reale in evidence/")
outside = os.path.join(ROOT, "tests_like"); os.makedirs(outside, exist_ok=True)
with open(os.path.join(outside, "worker.py"), "w") as fh:
    fh.write("# file esistente fuori da evidence/\n")
with open(os.path.join(ROOT, "root_file.json"), "w") as fh:
    fh.write("{}")
os.symlink(os.path.join(outside, "worker.py"), os.path.join(EVD, "link_out.json"))
def mk(evd):
    return gr.make_result("T20", "t", "e", status="PASS", reason_code="VERIFIED", actual="x", evidence=evd, diagnostic_exit=0, evidence_root=ROOT)
check("CP12a file esistente fuori evidence/ (tests_like/worker.py) -> FAIL/EVIDENCE_MISSING", mk("tests_like/worker.py")["reason_code"] == "EVIDENCE_MISSING")
check("CP12b file esistente nella root -> FAIL", mk("root_file.json")["status"] == "FAIL")
check("CP12c traversal evidence/../root_file.json -> FAIL", mk("evidence/../root_file.json")["status"] == "FAIL")
check("CP12d path assoluto (anche se dentro evidence/) -> FAIL", mk(os.path.join(EVD, "t01.json"))["status"] == "FAIL")
check("CP12e symlink dentro evidence/ che risolve fuori -> FAIL", mk("evidence/link_out.json")["status"] == "FAIL")
check("CP12f la directory evidence/ stessa -> FAIL", mk("evidence")["status"] == "FAIL" and mk("evidence/")["status"] == "FAIL")
check("CP12g file regolare dentro evidence/ -> PASS", mk("evidence/t01.json")["status"] == "PASS")
check("CP12h evidence/./t01.json normalizzato -> PASS", mk("evidence/./t01.json")["status"] == "PASS")

failed = [c for c in CHECKS if not c[1]]
print(f"\nREPORTING CONTRACT: {len(CHECKS) - len(failed)}/{len(CHECKS)} controprove superate" + (f" — FALLITE: {[c[0] for c in failed]}" if failed else ""))
sys.exit(1 if failed else 0)
