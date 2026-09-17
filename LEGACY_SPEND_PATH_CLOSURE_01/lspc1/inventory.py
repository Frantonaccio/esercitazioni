"""INVENTARIO STATICO DEI PERCORSI DI SPESA — chi puo' arrivare a uno spender.

Scansione AST (non testuale: un commento che nomina `submit` non e' una chiamata
a `submit`) di CORE e RUNTIME, alla ricerca di ogni chiamata che possa:

    creare una reservation · creare una quote · aprire un envelope · emettere o
    consumare un permesso · autorizzare un payload · dispacciare · chiamare
    submit · raggiungere uno spender · creare un job remoto · produrre spesa ·
    usare budget_units / envelope_units · entrare in modalita' legacy.

L'inventario STATICO dice DOVE sono i punti; la verifica DINAMICA (`lspc1.workers`)
dice COSA succede davvero quando li si percorre. Nessuno dei due basta da solo:
il primo non sa cosa fallisce, il secondo non sa cosa ha dimenticato.
"""
from __future__ import annotations

import ast
import os

# Nomi che, se CHIAMATI, toccano un punto della catena di spesa.
SPEND_CALLS = {
    "run_job": "dispatch (arteria del Core)",
    "resume_job": "ripresa di un tentativo autorizzato (nessuna nuova spesa)",
    "submit": "SPENDER: invio al provider",
    "authorize_payload": "autorizzazione dei byte al trasporto",
    "reserve_or_get_live": "prenotazione atomica (identita' + budget)",
    "issue_quote": "AUTORITA': emissione di una quote fidata",
    "open_envelope": "AUTORITA': apertura di un envelope",
    "issue_permit": "AUTORITA': emissione di un permesso di nuovo tentativo",
    "settle": "AUTORITA': regolazione economica",
    "reconcile": "riconciliazione: libera l'identita' di una spec",
    "mark_submitting": "persistenza dell'intento di submit",
    "mark_submitted": "persistenza dell'identita' remota",
    "mark_refused_pre_submit": "chiusura atomica di un rifiuto pre-submit",
    "mark_refused_before_send": "chiusura con attestazione del trasporto",
    "recover_orphaned_submits": "recovery: RESERVED -> SUBMIT_UNKNOWN",
    "expire": "deadline locale -> SUBMIT_UNKNOWN",
    "go": "verbo `go` del runtime",
    "grant_dispatch": "CONFINE: concessione del dispatch",
    "authorize_dispatch": "CONFINE: autorizzazione riletta dal journal",
}
BUDGET_NAMES = ("budget_units", "envelope_units")
LEGACY_MARKERS = ("LEGACY_LAB", "authorization=None", "LEGACY_LAB_SPEND_PATH",
                  "legacy_spend_path_state", "require_legacy_lab_spend_path")


def _call_name(node: ast.AST) -> str | None:
    f = getattr(node, "func", None)
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def scan_file(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError as e:                                # noqa: BLE001
        return {"path": path, "error": f"SyntaxError: {e}"}
    calls: list[dict] = []
    budget: list[dict] = []
    enclosing: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            enclosing.append((node.lineno, getattr(node, "end_lineno", node.lineno), node.name))

    def fn_of(lineno: int) -> str:
        best = ("<module>", 10 ** 9)
        for start, end, name in enclosing:
            if start <= lineno <= end and (end - start) < best[1]:
                best = (name, end - start)
        return best[0]

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in SPEND_CALLS:
                calls.append({"call": name, "line": node.lineno, "in": fn_of(node.lineno),
                              "role": SPEND_CALLS[name]})
            for kw in node.keywords:
                if kw.arg in BUDGET_NAMES:
                    budget.append({"kwarg": kw.arg, "line": node.lineno, "in": fn_of(node.lineno),
                                   "call": name})
    legacy = [{"marker": m, "line": i + 1}
              for i, line in enumerate(src.splitlines())
              for m in LEGACY_MARKERS if m in line]
    return {"path": path, "calls": calls, "budget_kwargs": budget, "legacy_markers": legacy}


def scan_tree(root: str, subdirs: tuple[str, ...]) -> list[dict]:
    out = []
    for sub in subdirs:
        base = os.path.join(root, sub)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
            for fn in sorted(filenames):
                if fn.endswith(".py"):
                    out.append(scan_file(os.path.join(dirpath, fn)))
    return out


def summarize(files: list[dict], root: str) -> dict:
    per_file = {}
    totals: dict[str, int] = {}
    for f in files:
        rel = os.path.relpath(f["path"], root)
        if f.get("error"):
            per_file[rel] = f
            continue
        if not (f["calls"] or f["budget_kwargs"] or f["legacy_markers"]):
            continue
        per_file[rel] = {"calls": f["calls"], "budget_kwargs": f["budget_kwargs"],
                         "legacy_markers": len(f["legacy_markers"])}
        for c in f["calls"]:
            totals[c["call"]] = totals.get(c["call"], 0) + 1
    return {"root": root, "files_with_spend_surface": len(per_file),
            "call_totals": dict(sorted(totals.items())), "per_file": per_file}


def run(core_path: str, gate01_path: str, bundle_path: str) -> dict:
    core = summarize(scan_tree(core_path, ("adapters", "core", "registry", "transport", "tests")),
                     core_path)
    runtime = summarize(scan_tree(gate01_path, ("runtime", "tests")), gate01_path)
    bundle = summarize(scan_tree(bundle_path, ("lspc1",)), bundle_path)
    return {"core": core, "runtime": runtime, "closure_harness": bundle}
