#!/usr/bin/env python3
"""P-B01 + P-B02 — ORCHESTRATOR PROBE DI COMPOSIZIONE.

Gira con UID DISTINTO da quello dello spender, senza capability, con no_new_privs.
Esegue, e riferisce in JSON su stdout, le controprove del mandato §7:

  1  orchestrator tenta di leggere il SEGRETO di riconciliazione        -> FAIL atteso
  2  orchestrator tenta di leggere la SIGNING KEY (file, /proc/mem,
     /proc/environ, ready-file, risposte del canale)                    -> FAIL atteso
  3  orchestrator FORGIA un report (firma con una chiave propria)       -> FAIL atteso
  4  UID/processo non autorizzato parla al socket (eseguito dal gate
     con un terzo UID; qui si riporta il suo esito)                     -> FAIL atteso
  5  report CORRETTO prodotto dallo spender                             -> PASS atteso
  6  replay dello stesso report                                         -> FAIL atteso
  7  wrong provider                                                     -> FAIL atteso
  8  wrong account                                                      -> FAIL atteso
  9  wrong job                                                          -> FAIL atteso
 10  wrong operation                                                    -> FAIL atteso
 11  wrong attempt                                                      -> FAIL atteso

7-11 (piu' payload_digest, stale e from_future) sono controprove di BINDING/FRESHNESS:
il report firmato-ma-mal-legato viene costruito e verificato DENTRO lo spender, che
restituisce solo il codice di rifiuto. Non esce mai materiale firmato dal dominio dello
spender, quindi l'op non e' un oracolo di firma per l'orchestrator.

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

SECRET_MARKERS = ("FAKE_SPENDER_SECRET", "FAKE_RECONCILIATION_SECRET")


def session(sock_path: str, messages: list) -> list:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    f = s.makefile("rwb", buffering=0)
    out = []
    for m in messages:
        f.write((m if isinstance(m, str) else json.dumps(m)).encode("utf-8") + b"\n")
        line = f.readline()
        out.append(json.loads(line) if line else {"ok": False, "error": "EOF"})
    s.close()
    return out


def blocked(e: BaseException) -> str:
    return f"BLOCKED ({type(e).__name__})"


def main() -> int:                                                  # noqa: C901
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", required=True)
    ap.add_argument("--spend-secret-path", required=True)
    ap.add_argument("--recon-secret-path", required=True)
    ap.add_argument("--ready-file", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--core", required=True)
    ap.add_argument("--spender-pid", type=int, required=True)
    ap.add_argument("--operation-id", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--mode", choices=("full", "peer_only", "stop"), default="full")
    a = ap.parse_args()

    out: dict = {"uid": os.getuid(), "gid": os.getgid(), "pid": os.getpid(),
                 "no_new_privs": _no_new_privs(), "caps": _caps()}
    if a.mode == "peer_only":
        try:
            out["peer_only"] = session(a.socket, [{"op": "whoami"}])
        except Exception:                                           # noqa: BLE001
            out["peer_only_error"] = traceback.format_exc(limit=3)
        print(json.dumps(out, default=str))
        return 0
    if a.mode == "stop":
        try:
            out["stop"] = session(a.socket, [{"op": "stop"}])
        except Exception:                                           # noqa: BLE001
            out["stop_error"] = traceback.format_exc(limit=3)
        print(json.dumps(out, default=str))
        return 0

    C: dict = {}
    channel_blobs: list[str] = []

    # ---------------------------------------------------------- 1. leggere il segreto
    for label, path in (("read_spend_secret", a.spend_secret_path),
                        ("read_recon_secret", a.recon_secret_path)):
        try:
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
            C[label] = ("BYPASS_POSSIBLE" if any(m in body for m in SECRET_MARKERS) else "BLOCKED")
        except OSError as e:
            C[label] = blocked(e)
    try:
        os.listdir(os.path.dirname(a.recon_secret_path))
        C["list_secret_dir"] = "BYPASS_POSSIBLE"
    except OSError as e:
        C["list_secret_dir"] = blocked(e)

    # ---------------------------------------------------------- 2. leggere la signing key
    key_probes: dict = {}
    for label, path in (("proc_mem", f"/proc/{a.spender_pid}/mem"),
                        ("proc_environ", f"/proc/{a.spender_pid}/environ"),
                        ("proc_cmdline_readable", f"/proc/{a.spender_pid}/cmdline")):
        try:
            with open(path, "rb") as fh:
                data = fh.read(4096)
            # cmdline e' leggibile per progetto (non contiene chiavi): si riferisce il contenuto
            key_probes[label] = {"readable": True, "contains_secret_marker":
                                 any(m.encode() in data for m in SECRET_MARKERS)}
        except OSError as e:
            key_probes[label] = blocked(e)
    try:
        ready = json.load(open(a.ready_file, encoding="utf-8"))
        key_probes["ready_file"] = {"readable": True, "keys": sorted(ready),
                                    "contains_key_material": any(
                                        isinstance(v, str) and (len(v) == 64 and all(
                                            c in "0123456789abcdef" for c in v))
                                        for v in ready.values()),
                                    "signing_key_on_disk": ready.get("signing_key_on_disk")}
    except OSError as e:
        key_probes["ready_file"] = blocked(e)
    try:
        key_files = [f for f in os.listdir(os.path.dirname(a.ready_file)) if "key" in f.lower()]
        key_probes["key_files_in_ipc_dir"] = key_files
    except OSError as e:
        key_probes["key_files_in_ipc_dir"] = blocked(e)
    C["read_signing_key"] = key_probes

    # ---------------------------------------------------------- sessione legittima
    report = None
    try:
        r = session(a.socket, [{"op": "whoami"},
                               {"op": "quote", "prompt": a.prompt, "operation_id": a.operation_id}])
        channel_blobs.append(json.dumps(r))
        whoami, quote = r
        out["whoami"] = whoami
        qid = quote.get("quote_id")
        r = session(a.socket, [{"op": "submit", "prompt": a.prompt, "operation_id": a.operation_id,
                                "intent": "new_attempt", "reason": "INITIAL_GENERATION",
                                "quote_id": qid, "adapter": "lost"}])
        channel_blobs.append(json.dumps(r))
        out["submit_lost"] = r[0]
        job_id = r[0].get("job_id")
        out["job_id"] = job_id
    except Exception:                                               # noqa: BLE001
        out["session_error"] = traceback.format_exc(limit=4)
        print(json.dumps(out, default=str))
        return 0

    # ---------------------------------------------------------- 3. forgiare un report
    try:
        from runtime.reconciliation import REPORT_SCHEMA, derive_report_key, sign_report
        import secrets as _s
        import time as _t
        guessed = "FAKE_RECONCILIATION_SECRET_" + "0" * 32
        key = derive_report_key(guessed, "fake", whoami.get("account_id") or "unknown")
        forged = sign_report(key, {
            "schema": REPORT_SCHEMA, "provider": "fake",
            "provider_account": whoami.get("account_id"), "provider_job_id": "pv_forged",
            "attempt_token": "att_forged", "payload_digest": "0" * 64,
            "operation_id": a.operation_id, "job_id": job_id, "state": "SUCCEEDED",
            "remote_ref": "remote:forged", "nonce": f"nonce_{_s.token_hex(16)}",
            "issued_at": _t.time()})
        r = session(a.socket, [{"op": "reconcile_report", "job_id": job_id,
                                "report_json": json.dumps(forged)}])
        channel_blobs.append(json.dumps(r))
        C["forge_report_with_own_key"] = r[0]
    except Exception:                                               # noqa: BLE001
        C["forge_report_with_own_key"] = {"error": traceback.format_exc(limit=3)}

    # ---------------------------------------------------------- 7..11 binding + freshness
    cases = ("wrong_provider", "wrong_account", "wrong_job", "wrong_operation", "wrong_attempt",
             "wrong_payload_digest", "stale", "from_future", "replay")
    binding: dict = {}
    for case in cases:
        try:
            r = session(a.socket, [{"op": "composition_counterproof", "job_id": job_id,
                                    "case": case}])
            channel_blobs.append(json.dumps(r))
            binding[case] = r[0]
        except Exception:                                           # noqa: BLE001
            binding[case] = {"error": traceback.format_exc(limit=3)}
    C["binding_counterproofs"] = binding

    # ---------------------------------------------------------- 5. report corretto + 6. replay
    try:
        r = session(a.socket, [{"op": "provider_report", "job_id": job_id, "state": "SUCCEEDED",
                                "remote_ref": "remote:pv_remote_1",
                                "provider_job_id": "pv_remote_1"}])
        channel_blobs.append(json.dumps(r))
        report = r[0].get("report")
        C["provider_report_issued"] = {"ok": r[0].get("ok"),
                                       "fields": sorted(report) if report else None}
        r = session(a.socket, [{"op": "reconcile_report", "job_id": job_id,
                                "report_json": json.dumps(report)}])
        channel_blobs.append(json.dumps(r))
        C["correct_report_from_spender"] = r[0]
        r = session(a.socket, [{"op": "reconcile_report", "job_id": job_id,
                                "report_json": json.dumps(report)}])
        channel_blobs.append(json.dumps(r))
        C["replay_same_report"] = r[0]
    except Exception:                                               # noqa: BLE001
        C["correct_report_from_spender"] = {"error": traceback.format_exc(limit=3)}

    # ---------------------------------------------------------- 2b. la chiave sul canale?
    # Ogni token esadecimale da 64 caratteri visto sul canale deve essere SPIEGABILE: o e' la
    # firma di un report emesso dallo spender, o e' un payload_digest / spec_key, o compare
    # dentro il testo di un rifiuto (le controprove nominano il valore sbagliato). Cio' che
    # resta non spiegato sarebbe materiale di chiave.
    blob = "\n".join(channel_blobs)
    sig = (report or {}).get("signature")
    explained = _explained_hex64(channel_blobs) | ({sig} if sig else set())
    C["channel_leak"] = {
        "secret_marker_in_channel": any(m in blob for m in SECRET_MARKERS),
        "signature_present_in_report": bool(sig),
        "hex64_tokens_in_channel": sorted(_hex64(blob)),
        "explained_hex64": sorted(explained),
        "unexplained_hex64": sorted(_hex64(blob) - explained),
    }
    # controprova finale: con la sola FIRMA vista sul canale, si puo' rifirmare un report?
    try:
        from runtime.reconciliation import canonical_report_bytes
        import secrets as _s
        replayed_sig = dict(report or {})
        replayed_sig["nonce"] = f"nonce_{_s.token_hex(16)}"          # nuovo nonce, firma vecchia
        r = session(a.socket, [{"op": "reconcile_report", "job_id": job_id,
                                "report_json": json.dumps(replayed_sig)}])
        C["resign_with_observed_signature"] = r[0]
        C["channel_leak"]["canonical_bytes_change_with_nonce"] = (
            canonical_report_bytes(report or {}) != canonical_report_bytes(replayed_sig))
    except Exception:                                               # noqa: BLE001
        C["resign_with_observed_signature"] = {"error": traceback.format_exc(limit=3)}

    out["counterproofs"] = C
    print(json.dumps(out, default=str))
    return 0


def _hex64(blob: str) -> set:
    import re
    return set(re.findall(r"\b[0-9a-f]{64}\b", blob))


ALLOWED_HEX64_KEYS = ("payload_digest", "spec_key", "requested_spec_key", "signature",
                      "digest", "nonce_claim")
MESSAGE_KEYS = ("message", "refused", "note", "error")


def _explained_hex64(blobs: list) -> set:
    """Token hex64 legittimi: valori di campi noti (digest, spec_key, firma) a qualunque
    profondita', piu' quelli citati dentro il testo di un rifiuto."""
    import json as _j
    import re
    out: set = set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ALLOWED_HEX64_KEYS and isinstance(v, str):
                    out.update(_hex64(v))
                if k in MESSAGE_KEYS and isinstance(v, str):
                    out.update(_hex64(v))
                if isinstance(v, str) and k.endswith("_json"):
                    try:
                        walk(_j.loads(v))
                    except ValueError:
                        out.update(re.findall(r'\\?"payload_digest\\?"\s*:\s*\\?"([0-9a-f]{64})',
                                              v))
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    for b in blobs:
        try:
            walk(_j.loads(b))
        except ValueError:
            pass
    return out


def _no_new_privs():
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
