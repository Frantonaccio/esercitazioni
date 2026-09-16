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


def run() -> dict:
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
        "registry.reservations.SqliteReservationStore", "transport.pipeline.run_job"}
    unexpected = sorted(core_imports - expected_core_imports)
    missing = sorted(expected_core_imports - core_imports)
    if unexpected:
        findings.append(f"import dal Core non previsti: {unexpected}")
    if missing:
        findings.append(f"import dal Core attesi ma assenti: {missing}")
    return {"files": [n for n, _ in _iter_files()], "core_imports": sorted(core_imports),
            "findings": findings, "ok": not findings}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
