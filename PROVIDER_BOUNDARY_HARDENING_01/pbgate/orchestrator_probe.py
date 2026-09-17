#!/usr/bin/env python3
"""P-B01 — ORCHESTRATOR PROBE: gira con UID DISTINTO dallo spender, senza capability,
con no_new_privs. Fa due cose e riferisce tutto in JSON su stdout:

  1. SESSIONE DI PROTOCOLLO legittima via socket Unix (quote -> submit new_attempt ->
     resume -> status -> whoami): dimostra che il percorso governato funziona
     attraverso il confine e che il segreto non attraversa il canale.

  2. TENTATIVI DI BYPASS, esattamente le quattro probe canoniche di T29
     (gate_report.T29_EXPECTED_ATTEMPT_KEYS) piu' probe aggiuntive:
       read_worker_secret                 open() del file segreto dello spender
       write_worker_code                  os.access(W_OK) + open('a') sui sorgenti del worker/daemon
       write_worker_store                 os.access(W_OK) + apertura sqlite in scrittura dello store
       direct_dispatch_on_worker_store    go_candidate.go IN-PROCESS contro lo store dello spender
       (extra) issue_quote_on_worker_store, own_store_dispatch_account, kill_spender,
               read_spender_proc_environ, connect_as_other_uid (eseguita a parte dal gate)
     Ogni probe riporta "BLOCKED (<diagnostica>)" oppure "BYPASS_POSSIBLE": e' il
     KERNEL che decide (DAC su UID/mode), non un `if` del mock.

Nessuna credenziale reale, nessun provider reale, 0 crediti.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import traceback

GATE01 = os.environ.get("RUNTIME_GATE_ROOT", "/home/user/esercitazioni/RUNTIME_INTEGRATION_GATE_01")
if GATE01 not in sys.path:
    sys.path.insert(0, GATE01)


def session(sock_path: str, messages: list[dict]) -> list[dict]:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    f = s.makefile("rwb", buffering=0)
    replies = []
    for m in messages:
        f.write((m if isinstance(m, str) else json.dumps(m)).encode("utf-8") + b"\n")
        line = f.readline()
        replies.append(json.loads(line) if line else {"ok": False, "error": "EOF"})
    s.close()
    return replies


def blocked(e: BaseException) -> str:
    return f"BLOCKED ({type(e).__name__})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", required=True)
    ap.add_argument("--secret-path", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--core", required=True)
    ap.add_argument("--spender-pid", type=int, required=True)
    ap.add_argument("--own-db", required=True)
    ap.add_argument("--worker-code", nargs="+", required=True)
    ap.add_argument("--mode", choices=("full", "peer_only", "stop"), default="full")
    a = ap.parse_args()
    out: dict = {"uid": os.getuid(), "gid": os.getgid(), "pid": os.getpid(),
                 "no_new_privs": _no_new_privs(), "caps": _caps()}

    # ---------------------------------------------------------------- 1. protocollo
    try:
        if a.mode == "peer_only":
            out["protocol"] = session(a.socket, [{"op": "whoami"}])
        elif a.mode == "stop":
            out["protocol"] = session(a.socket, [{"op": "stop"}])
        else:
            R = {}
            r = session(a.socket, [{"op": "whoami"},
                                   {"op": "quote", "prompt": "boundary uid", "operation_id": "T29:uid"}])
            R["whoami"], R["quote"] = r
            qid = R["quote"].get("quote_id")
            r = session(a.socket, [
                {"op": "submit", "prompt": "boundary uid", "operation_id": "T29:uid", "quote_id": qid},        # senza intent -> PROTOCOL
                {"op": "submit", "prompt": "boundary uid", "operation_id": "T29:uid", "intent": "new_attempt",
                 "reason": "INITIAL_GENERATION", "quote_id": qid},                                            # prima spesa governata
                {"op": "submit", "prompt": "boundary uid", "operation_id": "T29:uid", "intent": "resume"},   # resume = stesso attempt
                {"op": "status", "prompt": "boundary uid"},
                {"op": "quote", "prompt": "boundary uid", "operation_id": "T29:uid", "amount": 1},          # importo dal client -> PROTOCOL
                {"op": "shell", "cmd": "higgsfield generate create x"},                                     # shell -> PROTOCOL
            ])
            (R["no_intent"], R["first"], R["resume"], R["status"], R["amount_from_client"], R["shell"]) = r
            out["protocol"] = R
            out["secret_in_channel"] = "FAKE_SPENDER_SECRET" in json.dumps(R)
    except Exception:                                                           # noqa: BLE001
        out["protocol_error"] = traceback.format_exc(limit=3)
    if a.mode in ("peer_only", "stop"):
        print(json.dumps(out, default=str))
        return 0

    # ---------------------------------------------------------------- 2. bypass probes
    attempts: dict = {}
    extra: dict = {}
    try:
        with open(a.secret_path, encoding="utf-8") as fh:
            attempts["read_worker_secret"] = "BYPASS_POSSIBLE" if "FAKE_SPENDER_SECRET" in fh.read() else "BLOCKED"
    except OSError as e:
        attempts["read_worker_secret"] = blocked(e)
    wc = []
    for path in a.worker_code:
        if os.access(path, os.W_OK):
            wc.append("BYPASS_POSSIBLE")
            continue
        try:
            with open(path, "a", encoding="utf-8"):
                pass
            wc.append("BYPASS_POSSIBLE")
        except OSError as e:
            wc.append(blocked(e))
    attempts["write_worker_code"] = ("BYPASS_POSSIBLE" if any(x == "BYPASS_POSSIBLE" for x in wc)
                                     else f"BLOCKED ({len(wc)} files, PermissionError)")
    if os.access(a.db, os.W_OK):
        attempts["write_worker_store"] = "BYPASS_POSSIBLE"
    else:
        try:
            import sqlite3
            with sqlite3.connect(a.db) as c:
                c.execute("CREATE TABLE IF NOT EXISTS probe_bypass(x)")
            attempts["write_worker_store"] = "BYPASS_POSSIBLE"
        except Exception as e:                                                  # noqa: BLE001
            attempts["write_worker_store"] = blocked(e)
    # dispatch DIRETTO sullo store dello spender, in-process (bypassa il socket)
    try:
        if a.core not in sys.path:
            sys.path.insert(0, a.core)
        from tests import worker
        direct = worker.run_go(a.db, "privilege direct", max_polls=3, operation_id="T29:direct",
                               core_path=a.core, governed=False)
        extra["direct_dispatch_detail"] = {k: direct.get(k) for k in ("ok", "error", "message", "state", "submits", "transport_sent")}
        attempts["direct_dispatch_on_worker_store"] = ("BYPASS_POSSIBLE" if direct.get("state") == "SUCCEEDED"
                                                       else f"BLOCKED ({direct.get('error')})")
    except Exception as e:                                                      # noqa: BLE001
        attempts["direct_dispatch_on_worker_store"] = blocked(e)
    # --- probe aggiuntive (non entrano nell'inventario canonico di t29_status) ---
    try:
        from tests import worker
        q = worker.store_call(a.db, a.core, "issue_lab_quote", "privilege quote", "T29:q", None)
        extra["issue_quote_on_worker_store"] = ("BYPASS_POSSIBLE" if q.get("ok") else f"BLOCKED ({q.get('error')})")
    except Exception as e:                                                      # noqa: BLE001
        extra["issue_quote_on_worker_store"] = blocked(e)
    try:
        from tests import worker
        own = worker.run_go(a.own_db, "own store", max_polls=3, operation_id="T29:own", core_path=a.core, governed=False)
        extra["own_store_dispatch"] = {"state": own.get("state"), "provider_account": (own.get("persisted") or {}).get("provider_account"),
                                       "error": own.get("error"),
                                       "note": "spesa possibile SOLO sul proprio store con il proprio FakeAdapter: conto diverso da quello dello spender"}
    except Exception as e:                                                      # noqa: BLE001
        extra["own_store_dispatch"] = blocked(e)
    try:
        os.kill(a.spender_pid, 0)
        os.kill(a.spender_pid, 15)
        extra["kill_spender"] = "BYPASS_POSSIBLE"
    except OSError as e:
        extra["kill_spender"] = blocked(e)
    try:
        with open(f"/proc/{a.spender_pid}/environ", "rb") as fh:
            fh.read(10)
        extra["read_spender_proc_environ"] = "BYPASS_POSSIBLE"
    except OSError as e:
        extra["read_spender_proc_environ"] = blocked(e)
    try:
        os.listdir(os.path.dirname(a.secret_path))
        extra["list_secret_dir"] = "BYPASS_POSSIBLE"
    except OSError as e:
        extra["list_secret_dir"] = blocked(e)
    try:
        snap_dir = a.db + ".snapshots"
        os.listdir(snap_dir)
        extra["read_snapshot_ledger"] = "BYPASS_POSSIBLE"
    except OSError as e:
        extra["read_snapshot_ledger"] = blocked(e)
    out["attempts"] = attempts
    out["extra_probes"] = extra
    print(json.dumps(out, default=str))
    return 0


def _no_new_privs() -> str | None:
    try:
        for line in open("/proc/self/status", encoding="utf-8"):
            if line.startswith("NoNewPrivs:"):
                return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def _caps() -> dict:
    caps = {}
    try:
        for line in open("/proc/self/status", encoding="utf-8"):
            if line.startswith(("CapEff:", "CapPrm:", "CapBnd:")):
                k, v = line.split(":", 1)
                caps[k] = v.strip()
    except OSError:
        pass
    return caps


if __name__ == "__main__":
    sys.exit(main())
