#!/usr/bin/env python3
"""P-B01 + P-B02 — SPENDER DAEMON v2 (LAB, nessuna credenziale reale, nessun provider reale).

Estende il daemon della fase precedente (`PROVIDER_BOUNDARY_HARDENING_01/pbgate/spender_daemon.py`,
non modificato) con l'unica cosa che mancava alla COMPOSIZIONE (NG-06): l'AUTORITA' DI STATO
DEL PROVIDER vive DENTRO questo processo.

Cosa sta qui e non esce mai:
  - `spend_secret`        segreto di spesa (identita' del conto), come nella fase precedente;
  - `recon_secret`        segreto di RICONCILIAZIONE, nuovo: da esso deriva la chiave HMAC
                          dei report (`derive_report_key`). File 0600 in una directory 0700
                          dello spender; MAI serializzato sul canale;
  - `LabProviderStatusAuthority`  costruita qui, con quel segreto. La chiave derivata resta
                          in memoria di questo processo: non e' scritta su disco, non compare
                          nel ready-file, non attraversa il socket;
  - `reconcile_authenticated`  il VERIFICATORE gira qui, sullo store autorevole dello spender.

Cosa riceve l'orchestrator (UID distinto, autenticato con SO_PEERCRED):
  - report FIRMATI per job di cui lo spender e' proprietario (`provider_report`), con i campi
    vincolanti presi dallo STORE AUTOREVOLE, non dal client: il client non sceglie provider,
    conto, operazione, attempt_token o payload_digest;
  - l'ESITO di una riconciliazione (`reconcile_report`);
  - il solo CODICE di rifiuto delle controprove di binding (`composition_counterproof`): il
    report firmato-ma-mal-legato NON esce mai dal dominio dello spender, quindi l'op non e'
    un oracolo di firma.

Ogni risposta e' verificata prima dell'invio: non deve contenere ne' i segreti ne' la chiave
derivata (in esadecimale o in base64). Un'asserzione fallita chiude la sessione.

FRESHNESS (NG-04): la finestra e' un PARAMETRO dell'operatore (`--freshness-max-age-s`,
`--freshness-max-future-skew-s`), obbligatorio. Il daemon non sceglie una policy e non ha
default: e' il MECCANISMO a essere verificato, non un valore.
"""
from __future__ import annotations

import argparse
import base64
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

from tests.boundary_mock import validate_request           # noqa: E402  (schema storico, invariato)

# Operazioni AGGIUNTIVE di questo daemon, con le sole chiavi ammesse. Schema chiuso come
# quello storico: nessuna shell, nessun argv, nessun path, solo scalari.
DAEMON_OPS = {
    "whoami": {"op"},
    "provider_report": {"op", "job_id", "state", "remote_ref", "provider_job_id"},
    "reconcile_report": {"op", "job_id", "report_json"},
    "composition_counterproof": {"op", "job_id", "case"},
}
# Casi di controprova di BINDING, enumerati e chiusi: il daemon firma un report con UN campo
# vincolante sbagliato e tenta lui stesso la riconciliazione, restituendo solo il codice.
COUNTERPROOF_CASES = ("wrong_provider", "wrong_account", "wrong_job", "wrong_operation",
                      "wrong_attempt", "wrong_payload_digest", "replay", "stale", "from_future")
SCALAR = (str, int, bool, float, type(None))


def peer_uid(conn: socket.socket) -> tuple[int, int, int]:
    pid, uid, gid = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                                        struct.calcsize("3i")))
    return pid, uid, gid


class LineConn:
    def __init__(self, sock: socket.socket):
        self.sock, self.buf = sock, b""

    def recv(self) -> str | None:
        while b"\n" not in self.buf:
            chunk = self.sock.recv(1 << 16)
            if not chunk:
                return None
            self.buf += chunk
            if len(self.buf) > 1 << 20:
                return "PROTOCOL: messaggio troppo lungo"
        line, self.buf = self.buf.split(b"\n", 1)
        return line.decode("utf-8", errors="replace")

    def send(self, obj: dict) -> None:
        self.sock.sendall(json.dumps(obj, default=str).encode("utf-8") + b"\n")


def validate_daemon_request(raw: str):
    """Schema chiuso delle op aggiuntive. Restituisce (msg, err) come quello storico."""
    try:
        msg = json.loads(raw)
    except ValueError:
        return None, "PROTOCOL: JSON non valido"
    if not isinstance(msg, dict):
        return None, "PROTOCOL: atteso un oggetto"
    op = msg.get("op")
    if op not in DAEMON_OPS:
        return None, None                       # non e' una op di questo daemon
    extra = set(msg) - DAEMON_OPS[op]
    if extra:
        return None, f"PROTOCOL: chiavi non ammesse {sorted(extra)}"
    for k, v in msg.items():
        if not isinstance(v, SCALAR) or (isinstance(v, str) and len(v) > 65536):
            return None, f"PROTOCOL: valore non scalare o troppo lungo in {k!r}"
    if op in ("provider_report", "reconcile_report", "composition_counterproof"):
        if not isinstance(msg.get("job_id"), str) or not msg["job_id"]:
            return None, "PROTOCOL: job_id obbligatorio"
    if op == "composition_counterproof" and msg.get("case") not in COUNTERPROOF_CASES:
        return None, f"PROTOCOL: case non ammesso (ammessi: {COUNTERPROOF_CASES})"
    return msg, None


def main() -> int:                                          # noqa: C901
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--secret-dir", required=True)
    ap.add_argument("--core", required=True)
    ap.add_argument("--canary-home", required=True)
    ap.add_argument("--allowed-peer-uid", type=int, required=True)
    ap.add_argument("--ready-file", required=True)
    # NG-04: parametri, non policy. Obbligatori: il daemon non sceglie una finestra.
    ap.add_argument("--freshness-max-age-s", type=float, required=True)
    ap.add_argument("--freshness-max-future-skew-s", type=float, required=True)
    ap.add_argument("--freshness-label", required=True)
    ap.add_argument("--max-sessions", type=int, default=16)
    a = ap.parse_args()

    from tests import audit_sentinel
    audit_sentinel.install(a.canary_home)
    from runtime import go_candidate
    from runtime.authorization import (DEFAULT_LAB_AUTHORIZATION, LAB_QUOTE_UNIT,
                                       AuthorizationRefused, lab_price_for)
    from runtime.payload_snapshot import SnapshotLedger, ledger_dir_for
    from runtime.reconciliation import (FreshnessPolicy, LabProviderStatusAuthority,
                                        ReconciliationRefused, REPORT_FIELDS, nonce_dir_for,
                                        reconcile_authenticated, sign_report)
    from tests.worker import make_inputs

    # --- segreti: SOLO qui, nel dominio di questo UID ------------------------------------
    os.makedirs(a.secret_dir, mode=0o700, exist_ok=True)
    os.chmod(a.secret_dir, 0o700)
    spend_secret = "FAKE_SPENDER_SECRET_" + secrets.token_hex(16)
    recon_secret = "FAKE_RECONCILIATION_SECRET_" + secrets.token_hex(16)
    secret_path = os.path.join(a.secret_dir, "worker_secret.json")
    recon_secret_path = os.path.join(a.secret_dir, "reconciliation_secret.json")
    for path, payload in ((secret_path, {"fake_secret": spend_secret}),
                          (recon_secret_path, {"fake_reconciliation_secret": recon_secret})):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload))
        os.chmod(path, 0o600)
    account_id = "acct_" + hashlib.sha256(spend_secret.encode()).hexdigest()[:12]

    if a.core not in sys.path:
        sys.path.insert(0, a.core)
    from adapters.base import GenSpec
    from adapters.fake import FakeAdapter
    from registry.reservations import SqliteReservationStore
    from runtime.genspec_bridge import build_genspec

    os.makedirs(os.path.dirname(a.db), mode=0o700, exist_ok=True)
    authority = SqliteReservationStore(a.db)
    # P-B02 DENTRO il dominio dello spender: la chiave e' derivata qui e resta qui.
    status_authority = LabProviderStatusAuthority(recon_secret, "fake", account_id)
    freshness = FreshnessPolicy(max_age_s=a.freshness_max_age_s,
                                max_future_skew_s=a.freshness_max_future_skew_s,
                                label=a.freshness_label)
    snapshot_ledger = SnapshotLedger(ledger_dir_for(a.db))
    nonce_dir = nonce_dir_for(a.db)
    # Materiale che NON deve mai comparire in una risposta.
    key_hex = status_authority.key.hex()
    forbidden = (spend_secret, recon_secret, key_hex, key_hex.upper(),
                 base64.b64encode(status_authority.key).decode("ascii"))

    adapters: dict = {}

    def adapter_for(kind):
        if kind not in adapters:
            if kind == "fake":
                adapters[kind] = FakeAdapter(account_id=account_id)
            else:
                class Lost(FakeAdapter):
                    """La richiesta parte e la risposta si perde DOPO l'invio: e' cosi' che
                    nasce un SUBMIT_UNKNOWN (stessa semantica di tests.worker 'submit_unknown')."""

                    def submit(self, gs):
                        self.submits += 1
                        raise ConnectionResetError("risposta del provider persa dopo l'invio (mock)")
                adapters[kind] = Lost(account_id=account_id)
        return adapters[kind]

    def bound_fields(job) -> dict:
        """I campi VINCOLANTI vengono dallo STORE AUTOREVOLE, mai dal client."""
        return {"provider": job.provider, "provider_account": job.provider_account,
                "attempt_token": job.attempt_token, "payload_digest": job.payload_digest,
                "operation_id": job.operation_id, "job_id": job.job_id}

    def apply_report(report: dict, job_id: str, *, clock=None) -> dict:
        job = reconcile_authenticated(authority, adapter_for("fake"), report, job_id=job_id,
                                      key=status_authority.key, nonce_dir=nonce_dir,
                                      snapshot_ledger=snapshot_ledger, freshness=freshness,
                                      now=clock)
        return {"ok": True, "state": job.state.value, "job_id": job.job_id,
                "revision": job.revision}

    # --- socket -------------------------------------------------------------------------
    if os.path.exists(a.socket):
        os.unlink(a.socket)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(a.socket)
    os.chmod(a.socket, 0o666)
    srv.listen(4)
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("flag", True))
    with open(a.ready_file, "w", encoding="utf-8") as fh:
        # Il ready-file NON contiene ne' i segreti ne' la chiave: solo identita' e percorsi.
        json.dump({"pid": os.getpid(), "uid": os.getuid(), "gid": os.getgid(),
                   "account_id": account_id, "secret_path": secret_path,
                   "recon_secret_path": recon_secret_path, "db": a.db, "socket": a.socket,
                   "allowed_peer_uid": a.allowed_peer_uid,
                   "freshness": freshness.describe(),
                   "signing_key_on_disk": False}, fh)

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
                msg, err = validate_daemon_request(raw)
                if err:
                    conn.send({"ok": False, "refused": err, "served": served})
                    continue
                if msg is None:                     # non e' una op di questo daemon: schema storico
                    msg, err = validate_request(raw)
                    if err:
                        conn.send({"ok": False, "refused": err, "served": served,
                                   "submits": adapter_for("fake").submits})
                        continue
                out: dict
                try:
                    op = msg["op"]
                    if op == "whoami":
                        out = {"ok": True, "uid": os.getuid(), "pid": os.getpid(),
                               "account_id": account_id, "peer_uid": uid, "served": served,
                               "freshness": freshness.describe()}
                    elif op == "stop":
                        out = {"ok": True, "stopped": True, "served": served,
                               "violations": audit_sentinel.violations(), "account_id": account_id,
                               "secret_path": secret_path, "recon_secret_path": recon_secret_path,
                               "uid": os.getuid(), "audit": audit_log}
                        stop["flag"] = True
                    elif op == "provider_report":
                        # Report FIRMATO per un job di cui questo spender e' proprietario.
                        # Il client sceglie solo stato/remote_ref/provider_job_id; tutto cio'
                        # che LEGA il report al tentativo viene dallo store autorevole.
                        job = authority.get(msg["job_id"])
                        if job is None:
                            out = {"ok": False, "refused": "JOB_UNKNOWN"}
                        else:
                            f = bound_fields(job)
                            out = {"ok": True, "report": status_authority.report(
                                provider_job_id=(msg.get("provider_job_id") or "pv_remote_1"),
                                attempt_token=f["attempt_token"], payload_digest=f["payload_digest"],
                                operation_id=f["operation_id"], job_id=f["job_id"],
                                state=(msg.get("state") or "SUCCEEDED"),
                                remote_ref=(msg.get("remote_ref") or "remote:pv_remote_1"))}
                    elif op == "reconcile_report":
                        try:
                            report = json.loads(msg.get("report_json") or "null")
                        except ValueError:
                            report = None
                        try:
                            out = apply_report(report, msg["job_id"])
                        except ReconciliationRefused as e:
                            out = {"ok": False, "refused": e.code, "message": str(e)}
                    elif op == "composition_counterproof":
                        out = _counterproof(msg["case"], msg["job_id"], authority, bound_fields,
                                            status_authority, apply_report, sign_report,
                                            REPORT_FIELDS, freshness)
                    else:
                        over = {"model": msg["model"]} if msg.get("model") else {}
                        if op == "status":
                            latest = authority.find_latest_by_spec(
                                build_genspec(make_inputs(msg["prompt"], **over), GenSpec).spec_key)
                            out = {"ok": True, "latest": latest.to_dict() if latest else None}
                        elif op == "quote":
                            o = msg.get("operation_id")
                            env = DEFAULT_LAB_AUTHORIZATION.envelope_for(o)
                            authority.open_envelope(env, 100, unit=LAB_QUOTE_UNIT, scope=o.split(":")[0])
                            gs = build_genspec(make_inputs(msg["prompt"], **over), GenSpec)
                            amount = lab_price_for(gs.model)
                            out = {"ok": True, "amount": amount, "envelope_id": env,
                                   "price_source": "LAB_PRICE_TABLE", "sku": gs.model,
                                   "quote_id": authority.issue_quote(
                                       operation_id=o, spec_key=gs.spec_key, envelope_id=env,
                                       amount=amount, unit=LAB_QUOTE_UNIT)}
                        else:
                            res = go_candidate.go(
                                make_inputs(msg["prompt"], **over),
                                adapter=adapter_for(msg.get("adapter", "fake")),
                                provider_mode="fake", store_path=a.db, core_path=a.core, max_polls=3,
                                intent=msg["intent"], reason=msg.get("reason"),
                                permit_id=msg.get("permit_id"), auto_permit=msg.get("permit_id") is None,
                                operation_id=msg.get("operation_id"),
                                budget_units=(int(msg["budget_units"])
                                              if msg.get("budget_units") is not None else None),
                                envelope_id=msg.get("envelope_id"), quote_id=msg.get("quote_id"),
                                authorization=DEFAULT_LAB_AUTHORIZATION)
                            out = {"ok": True, "outcome": res.outcome, "state": res.state,
                                   "job_id": res.job_id, "governance": res.governance,
                                   "quote_id": res.quote_id, "budget_units": res.budget_units,
                                   "provider_account": res.persisted.get("provider_account"),
                                   "submits": adapter_for(msg.get("adapter", "fake")).submits}
                except go_candidate.IntentRefused as e:
                    out = {"ok": False, "error": "IntentRefused", "code": e.code, "message": str(e)}
                except AuthorizationRefused as e:
                    out = {"ok": False, "error": "AuthorizationRefused", "code": e.code, "message": str(e)}
                except Exception as e:                                      # noqa: BLE001
                    out = {"ok": False, "error": type(e).__name__, "message": str(e)}
                # Anche su errore, se l'operazione ha lasciato un tentativo persistito lo si
                # riferisce: l'orchestrator deve poter riconciliare cio' che esiste davvero.
                if not out.get("ok") and isinstance(msg, dict) and msg.get("operation_id"):
                    latest = authority.find_latest_by_operation(msg["operation_id"])
                    if latest is not None:
                        out["job_id"] = latest.job_id
                        out["state"] = latest.state.value
                # NESSUN segreto e NESSUNA chiave attraversa il canale.
                blob = json.dumps(out, default=str)
                for bad in forbidden:
                    assert bad not in blob, "SECRET_OR_KEY_IN_CHANNEL"
                conn.send(out)
                if stop["flag"]:
                    break
        except Exception:                                                   # noqa: BLE001
            audit_log.append({"event": "SESSION_ERROR", "trace": traceback.format_exc(limit=3)})
        finally:
            sock.close()
    srv.close()
    return 0


def _counterproof(case, job_id, authority, bound_fields, status_authority, apply_report,
                  sign_report, REPORT_FIELDS, freshness) -> dict:
    """Controprove di BINDING e di FRESHNESS eseguite DENTRO lo spender.

    Il daemon firma un report con UN campo sbagliato (o con un timestamp fuori finestra) e
    tenta lui stesso la riconciliazione: restituisce SOLO il codice di rifiuto. Il report
    firmato non lascia mai questo processo, quindi questa op non e' un oracolo di firma.
    """
    import secrets as _s
    import time as _t
    from runtime.reconciliation import REPORT_SCHEMA, ReconciliationRefused
    job = authority.get(job_id)
    if job is None:
        return {"ok": False, "refused": "JOB_UNKNOWN"}
    f = bound_fields(job)
    now = _t.time()
    base = {"schema": REPORT_SCHEMA, "provider": f["provider"],
            "provider_account": f["provider_account"], "provider_job_id": "pv_remote_1",
            "attempt_token": f["attempt_token"], "payload_digest": f["payload_digest"],
            "operation_id": f["operation_id"], "job_id": f["job_id"], "state": "SUCCEEDED",
            "remote_ref": "remote:pv_remote_1", "nonce": f"nonce_{_s.token_hex(16)}",
            "issued_at": now}
    target = job_id
    if case == "wrong_provider":
        base["provider"] = "higgsfield"
    elif case == "wrong_account":
        base["provider_account"] = "acct_stranger"
    elif case == "wrong_job":
        base["job_id"] = target = "res_nonexistent_1"
    elif case == "wrong_operation":
        base["operation_id"] = "lab:another_operation"
    elif case == "wrong_attempt":
        base["attempt_token"] = "att_bogus"
    elif case == "wrong_payload_digest":
        base["payload_digest"] = "0" * 64
    elif case == "stale":
        base["issued_at"] = now - (freshness.max_age_s + 60.0)
    elif case == "from_future":
        base["issued_at"] = now + (freshness.max_future_skew_s + 60.0)
    report = sign_report(status_authority.key, base)
    try:
        if case == "replay":
            # Il primo report porta il job a RUNNING (non terminale); un poll successivo lo
            # riporta in incertezza, come accade davvero. Solo cosi' il job e' ancora
            # RICONCILIABILE quando arriva il replay: a rifiutarlo e' il NONCE monouso, non
            # lo stato. E' il passo che rende la controprova significativa.
            running = dict(base, state="RUNNING")
            report = sign_report(status_authority.key, running)
            first = apply_report(report, target)
            job2 = authority.get(target)
            job2.state = type(job2.state)("SUBMIT_UNKNOWN")
            authority.put(job2)                     # poll successivo: incertezza
            second = None
            try:
                apply_report(report, target)
                second = {"refused": None}
            except ReconciliationRefused as e:
                second = {"refused": e.code}
            return {"ok": True, "case": case, "first_apply": first,
                    "back_to_unknown": authority.get(target).state.value,
                    "replay": second, "refused": second["refused"]}
        apply_report(report, target)
        return {"ok": True, "case": case, "refused": None,
                "note": "APPLICATO: la controprova NON e' fail-closed"}
    except ReconciliationRefused as e:
        return {"ok": True, "case": case, "refused": e.code, "message": str(e)}


if __name__ == "__main__":
    sys.exit(main())
