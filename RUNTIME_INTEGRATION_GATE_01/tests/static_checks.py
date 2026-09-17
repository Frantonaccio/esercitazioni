"""Controllo STATICO (AST) del runtime candidate.

Il runtime deve CONSUMARE il Core, non duplicarlo. Qui si verifica sul codice,
non sulla buona fede, che in `runtime/` non esista:

  - il pattern find-then-submit (`find_live_by_spec`, chiamate a `.submit(`);
  - una macchina a stati di job parallela (Enum con stati di job);
  - un motore di budget parallelo (aritmetica su envelope/budget);
  - uno store parallelo (sqlite3, SQL, reservation JSON);
  - un `reserve_or_get_live` che DECIDE invece di delegare.
"""
from __future__ import annotations

import ast
import os
import re

GATE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_DIR = os.path.join(GATE_ROOT, "runtime")

FORBIDDEN_ATTRS = {"find_live_by_spec", "submit", "mark_submitted", "mark_submit_unknown",
                   "expire", "due_for_reconcile"}
FORBIDDEN_MODULES = {"sqlite3", "json.dump", "pickle", "shelve", "dbm", "requests",
                     "urllib", "http", "socket", "httpx", "aiohttp"}
FORBIDDEN_NAMES = {"JobState", "ReservationOutcome", "BudgetExceeded"}   # non ridefinibili
JOB_STATE_WORDS = {"RESERVED", "SUBMITTED", "RUNNING", "SUBMIT_UNKNOWN", "SUCCEEDED",
                   "FAILED", "TIMEOUT"}
SQL_RE = re.compile(r"\b(INSERT|UPDATE|DELETE|CREATE TABLE|SELECT)\b")
BUDGET_ARITH_RE = re.compile(r"(used|reserved|committed)\s*\+\s*budget|budget\w*\s*>\s*envelope")


def _iter_files():
    for name in sorted(os.listdir(RUNTIME_DIR)):
        if name.endswith(".py"):
            yield name, os.path.join(RUNTIME_DIR, name)


def _protocol_contract(core_path: str) -> dict:
    """Metodi e parametri dichiarati da ReservationStore/EconomicLedger del Core
    e firma di transport.pipeline.run_job, letti dall'AST (nessun import del Core)."""
    base = ast.parse(open(os.path.join(core_path, "adapters", "base.py"), encoding="utf-8").read())
    methods: dict[str, set[str]] = {}
    for node in base.body:
        if isinstance(node, ast.ClassDef) and node.name in ("ReservationStore", "EconomicLedger"):
            for fn in node.body:
                if isinstance(fn, ast.FunctionDef):
                    a = fn.args
                    names = {x.arg for x in a.args + a.kwonlyargs if x.arg != "self"}
                    methods[fn.name] = names
    pipe = ast.parse(open(os.path.join(core_path, "transport", "pipeline.py"), encoding="utf-8").read())
    run_job_params: set[str] = set()
    resume_job_params: set[str] = set()
    for node in pipe.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run_job":
            run_job_params = {x.arg for x in node.args.args + node.args.kwonlyargs}
        if isinstance(node, ast.FunctionDef) and node.name == "resume_job":
            resume_job_params = {x.arg for x in node.args.args + node.args.kwonlyargs}
    return {"methods": methods, "run_job_params": run_job_params, "resume_job_params": resume_job_params}


def contract_drift(core_path: str) -> list[str]:
    """CR-03: il runtime usa SOLO metodi e argomenti dichiarati dal Protocol del
    Core. Ogni `store.<m>(...)` (o `self._inner.<m>(...)`) in runtime/ deve
    esistere nel Protocol e ogni keyword passata deve essere un parametro
    dichiarato; ogni keyword passata a `run_job(...)` deve esistere nella sua firma."""
    contract = _protocol_contract(core_path)
    findings: list[str] = []
    for name, path in _iter_files():
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            recv = None
            if isinstance(f, ast.Attribute):
                if isinstance(f.value, ast.Name) and f.value.id == "store":
                    recv = "store"
                elif (isinstance(f.value, ast.Attribute) and f.value.attr == "_inner"
                      and isinstance(f.value.value, ast.Name) and f.value.value.id == "self"):
                    recv = "self._inner"
                if recv:
                    if f.attr not in contract["methods"]:
                        findings.append(f"{name}:{node.lineno}: {recv}.{f.attr} non dichiarato da ReservationStore/EconomicLedger")
                        continue
                    for kw in node.keywords:
                        if kw.arg is not None and kw.arg not in contract["methods"][f.attr]:
                            findings.append(f"{name}:{node.lineno}: {recv}.{f.attr}(..., {kw.arg}=) argomento non dichiarato")
            elif isinstance(f, ast.Name) and f.id in ("run_job", "resume_job"):
                for kw in node.keywords:
                    if kw.arg is not None and kw.arg not in contract[f"{f.id}_params"]:
                        findings.append(f"{name}:{node.lineno}: {f.id}(..., {kw.arg}=) argomento non dichiarato")
    return findings


def run(core_path: str | None = None) -> dict:
    findings: list[str] = []
    core_imports: set[str] = set()
    for name, path in _iter_files():
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src, filename=name)
        for node in ast.walk(tree):
            # 1) attributi vietati (find-then-submit e transizioni di stato)
            if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRS:
                findings.append(f"{name}:{node.lineno}: accesso a .{node.attr}")
            # 2) import vietati
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in node.names] if isinstance(node, ast.Import) \
                    else [node.module or ""]
                for m in mods:
                    if m.split(".")[0] in FORBIDDEN_MODULES or m in FORBIDDEN_MODULES:
                        findings.append(f"{name}:{node.lineno}: import di {m}")
                if isinstance(node, ast.ImportFrom) and node.module in (
                        "adapters.base", "adapters.fake", "registry.reservations",
                        "transport.pipeline"):
                    for a in node.names:
                        core_imports.add(f"{node.module}.{a.name}")
            # 3) nessuna ridefinizione di stati/esiti/eccezioni del Core
            if isinstance(node, ast.ClassDef):
                if node.name in FORBIDDEN_NAMES:
                    findings.append(f"{name}:{node.lineno}: ridefinisce {node.name}")
                bases = {getattr(b, "id", getattr(b, "attr", "")) for b in node.bases}
                if "Enum" in bases or "IntEnum" in bases:
                    findings.append(f"{name}:{node.lineno}: Enum '{node.name}' (stati paralleli?)")
                # 4) reserve_or_get_live: ammesso SOLO come delega pura
                for fn in node.body:
                    if isinstance(fn, ast.FunctionDef) and fn.name == "reserve_or_get_live":
                        calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call)]
                        delegating = [c for c in calls if isinstance(c.func, ast.Attribute)
                                      and c.func.attr == "reserve_or_get_live"
                                      and isinstance(c.func.value, ast.Attribute)
                                      and c.func.value.attr == "_inner"]
                        if len(calls) != 1 or len(delegating) != 1:
                            findings.append(
                                f"{name}:{fn.lineno}: reserve_or_get_live non e' una delega pura "
                                f"({len(calls)} chiamate)")
                        for sub in ast.walk(fn):
                            if isinstance(sub, (ast.If, ast.Compare, ast.BoolOp)):
                                findings.append(
                                    f"{name}:{sub.lineno}: reserve_or_get_live contiene logica decisionale")
            # 5) costanti con nomi di stato di job assegnate nel runtime
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id in JOB_STATE_WORDS:
                        findings.append(f"{name}:{node.lineno}: costante di stato {t.id}")
        # 6) SQL o aritmetica di budget nel sorgente
        for i, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""'):
                continue
            if SQL_RE.search(line) and ("execute" in line or "sql" in line.lower()):
                findings.append(f"{name}:{i}: SQL nel runtime")
            if BUDGET_ARITH_RE.search(line):
                findings.append(f"{name}:{i}: aritmetica di budget nel runtime")
    # 7) hf_batch_runtime.py: la CLI provider e' raggiungibile SOLO da funzioni che
    #    iniziano con _real_cli() (che solleva sempre). Nessun urllib, nessun download.
    hb = os.path.join(RUNTIME_DIR, "hf_batch_runtime.py")
    if os.path.exists(hb):
        src = open(hb, encoding="utf-8").read()
        tree = ast.parse(src)
        if "urllib" in src:
            findings.append("hf_batch_runtime.py: riferimento a urllib (download provider)")
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                seg = ast.get_source_segment(src, node) or ""
                if "higgsfield" in seg and node.name != "_real_cli":
                    first = node.body[0]
                    guarded = (isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
                               and getattr(first.value.func, "id", "") == "_real_cli")
                    if not guarded:
                        findings.append(
                            f"hf_batch_runtime.py:{node.lineno}: {node.name} tocca la CLI provider "
                            "senza _real_cli() come prima istruzione")
                if node.name == "run_job":
                    for sub in ast.walk(node):
                        if (isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name)
                                and sub.value.id in ("subprocess", "urllib", "os") and sub.attr in
                                ("run", "Popen", "call", "check_output", "system", "urlretrieve", "urlopen")):
                            findings.append(f"hf_batch_runtime.py:{sub.lineno}: run_job chiama {sub.value.id}.{sub.attr}")
    expected_core_imports = {
        "adapters.base.GenSpec", "adapters.fake.FakeAdapter",
        "registry.reservations.SqliteReservationStore", "transport.pipeline.run_job",
        "transport.pipeline.resume_job",      # CR-09: resume esplicito, non un secondo submit
        # P-B04 (PROVIDER / EXECUTION BOUNDARY HARDENING 2026-09-17): il guard dello snapshot
        # exact-byte (runtime/payload_snapshot.py) rifiuta PRIMA del marcatore di invio con la
        # stessa eccezione del contratto RV02 del Core, cosi' run_job attesta "non inviato".
        "adapters.base.PayloadBindingError"}
    unexpected = sorted(core_imports - expected_core_imports)
    missing = sorted(expected_core_imports - core_imports)
    if unexpected:
        findings.append(f"import dal Core non previsti: {unexpected}")
    if missing:
        findings.append(f"import dal Core attesi ma assenti: {missing}")
    drift = contract_drift(core_path) if core_path else ["contract drift NON verificato: core_path assente"]
    findings.extend(drift)
    return {"files": [n for n, _ in _iter_files()], "core_imports": sorted(core_imports),
            "contract_drift": drift, "findings": findings, "ok": not findings}


if __name__ == "__main__":
    import json
    print(json.dumps(run(os.environ.get("CREATIVE_OS_CORE_PATH")), indent=2))
