#!/usr/bin/env python3
"""P-B01 — SPENDER DAEMON (LAB, nessuna credenziale reale, nessun provider reale).

E' il worker/spender di `tests/boundary_mock.py` reso un PROCESSO CON IDENTITA'
PROPRIA: il gate lo lancia con un UID distinto da quello dell'orchestrator
(`setpriv --reuid=<spender_uid> --clear-groups --inh-caps=-all --bounding-set=-all
--no-new-privs`). Tutto cio' che e' spendibile sta qui:

  - il SEGRETO fittizio (secret_dir 0700 del suo UID, file 0600): da esso deriva
    l'identita' del conto (`acct_<sha256(secret)[:12]>`);
  - lo STORE autorevole (db in una directory 0700 del suo UID) e, accanto, il
    ledger degli snapshot P-B04 e i nonce di reconciliation P-B02;
  - l'ADAPTER (FakeAdapter del Core) e la chiamata a `go_candidate.go` GOVERNATA
    (authorization fidata LAB, quote fidata emessa QUI, listino LAB).

L'orchestrator parla SOLO attraverso un socket Unix (newline-delimited JSON) con
lo schema chiuso di `boundary_mock.validate_request` (submit | quote | status |
stop, + whoami). Il daemon AUTENTICA il peer con SO_PEERCRED: accetta un solo UID
(`--allowed-peer-uid`); un peer diverso viene rifiutato prima di leggere un byte.

Cio' che rende il confine REALE (e non un `if`): il kernel. L'orchestrator, con
un altro UID e senza capability, non puo' leggere il segreto, scrivere lo store,
scrivere questo file, inviare segnali al daemon ne' leggere il suo /proc. Le
probe di `orchestrator_probe.py` lo dimostrano dal lato dell'orchestrator; il
gate (`run_boundary_gate.py`) verifica dal lato operatore.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import signal
import socket
import struct
import sys
import traceback

GATE01 = os.environ.get("RUNTIME_GATE_ROOT", "/home/user/esercitazioni/RUNTIME_INTEGRATION_GATE_01")
if GATE01 not in sys.path:
    sys.path.insert(0, GATE01)

from tests.boundary_mock import validate_request          # noqa: E402  (schema chiuso, invariato)

DAEMON_OPS = ("whoami",)            # in aggiunta ad ALLOWED_OPS del mock: identita' senza segreto


def peer_uid(conn: socket.socket) -> tuple[int, int, int]:
    pid, uid, gid = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                                          struct.calcsize("3i")))
    return pid, uid, gid


class LineConn:
    """Adatta il socket all'interfaccia usata dal worker (recv() -> str, send(dict))."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buf = b""

    def recv(self) -> str | None:
        while b"\n" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                return None
            self.buf += chunk
            if len(self.buf) > 1 << 20:
                return "PROTOCOL: messaggio troppo lungo"
        line, self.buf = self.buf.split(b"\n", 1)
        return line.decode("utf-8", errors="replace")

    def send(self, obj: dict) -> None:
        self.sock.sendall(json.dumps(obj, default=str).encode("utf-8") + b"\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--secret-dir", required=True)
    ap.add_argument("--core", required=True)
    ap.add_argument("--canary-home", required=True)
    ap.add_argument("--allowed-peer-uid", type=int, required=True)
    ap.add_argument("--ready-file", required=True)
    ap.add_argument("--max-sessions", type=int, default=8)
    a = ap.parse_args()

    from tests import audit_sentinel
    audit_sentinel.install(a.canary_home)
    from runtime import go_candidate
    from runtime.authorization import (DEFAULT_LAB_AUTHORIZATION, LAB_QUOTE_UNIT,
                                       AuthorizationRefused, lab_price_for)
    from tests.worker import make_inputs

    # --- segreto: SOLO qui, nel dominio di questo UID -----------------------------------
    os.makedirs(a.secret_dir, mode=0o700, exist_ok=True)
    os.chmod(a.secret_dir, 0o700)
    secret = "FAKE_SPENDER_SECRET_" + secrets.token_hex(16)
    secret_path = os.path.join(a.secret_dir, "worker_secret.json")
    fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"fake_secret": secret}))
    os.chmod(secret_path, 0o600)
    account_id = "acct_" + hashlib.sha256(secret.encode()).hexdigest()[:12]

    if a.core not in sys.path:
        sys.path.insert(0, a.core)
    from adapters.base import GenSpec
    from adapters.fake import FakeAdapter
    from registry.reservations import SqliteReservationStore
    from runtime.genspec_bridge import build_genspec

    os.makedirs(os.path.dirname(a.db), mode=0o700, exist_ok=True)
    authority = SqliteReservationStore(a.db)         # lato AUTORITA': envelope e quote li scrive lo spender
    adapters: dict = {}

    def adapter_for(kind):
        if kind not in adapters:
            if kind == "fake":
                adapters[kind] = FakeAdapter(account_id=account_id)
            else:
                class Lost(FakeAdapter):
                    def submit(self, gs):
                        self.submits += 1
                        raise TimeoutError("risposta persa (mock)")
                adapters[kind] = Lost(account_id=account_id)
        return adapters[kind]

    # --- socket: directory dello spender, file accessibile in connect; il peer e' autenticato ---
    if os.path.exists(a.socket):
        os.unlink(a.socket)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(a.socket)
    os.chmod(a.socket, 0o666)
    srv.listen(4)
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("flag", True))
    with open(a.ready_file, "w", encoding="utf-8") as fh:
        json.dump({"pid": os.getpid(), "uid": os.getuid(), "gid": os.getgid(),
                   "account_id": account_id, "secret_path": secret_path, "db": a.db,
                   "socket": a.socket, "allowed_peer_uid": a.allowed_peer_uid}, fh)

    audit_log: list[dict] = []
    sessions = 0
    while not stop["flag"] and sessions < a.max_sessions:
        try:
            srv.settimeout(1.0)
            try:
                sock, _ = srv.accept()
            except socket.timeout:
                continue
        except OSError:
            break
        sessions += 1
        pid, uid, gid = peer_uid(sock)
        conn = LineConn(sock)
        if uid != a.allowed_peer_uid:
            audit_log.append({"event": "PEER_REFUSED", "peer_pid": pid, "peer_uid": uid, "peer_gid": gid})
            conn.send({"ok": False, "refused": "PEER_UID_NOT_AUTHORIZED", "peer_uid": uid,
                       "allowed_peer_uid": a.allowed_peer_uid})
            sock.close()
            continue
        audit_log.append({"event": "PEER_ACCEPTED", "peer_pid": pid, "peer_uid": uid, "peer_gid": gid})
        served = 0
        try:
            while True:
                raw = conn.recv()
                if raw is None:
                    break
                served += 1
                if raw.startswith("PROTOCOL:"):
                    conn.send({"ok": False, "refused": raw, "served": served})
                    continue
                # whoami: identita' del daemon senza segreto (per l'evidenza), prima dello schema chiuso
                try:
                    probe = json.loads(raw)
                except ValueError:
                    probe = None
                if isinstance(probe, dict) and probe.get("op") == "whoami" and set(probe) == {"op"}:
                    conn.send({"ok": True, "uid": os.getuid(), "pid": os.getpid(), "account_id": account_id,
                               "peer_uid": uid, "served": served})
                    continue
                msg, err = validate_request(raw)
                if err:
                    conn.send({"ok": False, "refused": err, "served": served,
                               "submits": adapter_for("fake").submits})
                    continue
                if msg["op"] == "stop":
                    conn.send({"ok": True, "stopped": True, "served": served,
                               "violations": audit_sentinel.violations(), "account_id": account_id,
                               "secret_path": secret_path, "uid": os.getuid(), "audit": audit_log})
                    stop["flag"] = True
                    break
                over = {"model": msg["model"]} if msg.get("model") else {}
                try:
                    if msg["op"] == "status":
                        latest = authority.find_latest_by_spec(
                            build_genspec(make_inputs(msg["prompt"], **over), GenSpec).spec_key)
                        conn.send({"ok": True, "latest": latest.to_dict() if latest else None})
                        continue
                    if msg["op"] == "quote":
                        op = msg.get("operation_id")
                        env = DEFAULT_LAB_AUTHORIZATION.envelope_for(op)
                        authority.open_envelope(env, 100, unit=LAB_QUOTE_UNIT, scope=op.split(":")[0])
                        gs = build_genspec(make_inputs(msg["prompt"], **over), GenSpec)
                        amount = lab_price_for(gs.model)
                        qid = authority.issue_quote(operation_id=op, spec_key=gs.spec_key, envelope_id=env,
                                                    amount=amount, unit=LAB_QUOTE_UNIT)
                        conn.send({"ok": True, "quote_id": qid, "amount": amount, "envelope_id": env,
                                   "price_source": "LAB_PRICE_TABLE", "sku": gs.model})
                        continue
                    res = go_candidate.go(
                        make_inputs(msg["prompt"], **over), adapter=adapter_for(msg.get("adapter", "fake")),
                        provider_mode="fake", store_path=a.db, core_path=a.core, max_polls=3,
                        intent=msg["intent"], reason=msg.get("reason"),
                        permit_id=msg.get("permit_id"), auto_permit=msg.get("permit_id") is None,
                        operation_id=msg.get("operation_id"),
                        budget_units=(int(msg["budget_units"]) if msg.get("budget_units") is not None else None),
                        envelope_id=msg.get("envelope_id"), quote_id=msg.get("quote_id"),
                        authorization=DEFAULT_LAB_AUTHORIZATION)
                    out = {"ok": True, "outcome": res.outcome, "state": res.state, "job_id": res.job_id,
                           "reservation_outcome": res.reservation_outcome, "permit_id": res.permit_id,
                           "provider_account": res.persisted.get("provider_account"),
                           "governance": res.governance, "envelope_id": res.envelope_id,
                           "quote_id": res.quote_id, "budget_units": res.budget_units,
                           "resumed": res.resumed, "spec_key": res.spec_key,
                           "payload_snapshot": res.payload_snapshot,
                           "submits": adapter_for(msg.get("adapter", "fake")).submits}
                except go_candidate.IntentRefused as e:
                    out = {"ok": False, "error": "IntentRefused", "code": e.code, "message": str(e)}
                except AuthorizationRefused as e:
                    out = {"ok": False, "error": "AuthorizationRefused", "code": e.code, "message": str(e)}
                except Exception as e:                                          # noqa: BLE001
                    out = {"ok": False, "error": type(e).__name__, "message": str(e)}
                out.setdefault("submits", adapter_for(msg.get("adapter", "fake")).submits)
                assert secret not in json.dumps(out, default=str)     # il segreto non attraversa il canale
                conn.send(out)
        except Exception:                                                       # noqa: BLE001
            audit_log.append({"event": "SESSION_ERROR", "trace": traceback.format_exc(limit=3)})
        finally:
            sock.close()
    srv.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
