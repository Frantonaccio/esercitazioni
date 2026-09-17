"""Helper eseguiti in PROCESSI REALI (multiprocessing 'spawn') dal PROVIDER BOUNDARY GATE.

Ogni funzione e' a livello di modulo (spawn la reimporta nel figlio) e riferisce un dict
serializzabile, mai eccezioni. Nessun provider reale, nessuna credenziale, 0 crediti.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import traceback

GATE01 = os.environ.get("RUNTIME_GATE_ROOT", "/home/user/esercitazioni/RUNTIME_INTEGRATION_GATE_01")
if GATE01 not in sys.path:
    sys.path.insert(0, GATE01)

from tests import worker                                   # noqa: E402  (helper storici R0-R1)
from tests.worker import make_inputs                       # noqa: E402


def _core(core_path: str) -> None:
    if core_path not in sys.path:
        sys.path.insert(0, core_path)


def _err(e: BaseException) -> dict:
    return {"ok": False, "error": type(e).__name__, "code": getattr(e, "code", None),
            "message": str(e), "trace": traceback.format_exc(limit=4)}


def _rows(db: str) -> list[dict]:
    cols = ("job_id", "spec_key", "state", "provider", "provider_account", "provider_job_id", "payload_digest",
            "attempt_token", "operation_id", "budget_units", "envelope_id", "quote_id", "permit_id",
            "submit_intent_at", "settled_units", "settlement_source", "revision", "error")
    with sqlite3.connect(db) as c:
        return [dict(zip(cols, r)) for r in c.execute(f"SELECT {','.join(cols)} FROM reservations ORDER BY rowid")]


def _anomalies(db: str, job_id: str | None = None) -> list[dict]:
    with sqlite3.connect(db) as c:
        q = "SELECT seq,job_id,kind,detail FROM anomalies" + (" WHERE job_id=?" if job_id else "") + " ORDER BY seq"
        rows = c.execute(q, (job_id,) if job_id else ()).fetchall()
    return [{"seq": r[0], "job_id": r[1], "kind": r[2], "detail": json.loads(r[3])} for r in rows]


def _ledger(db: str) -> list[dict]:
    with sqlite3.connect(db) as c:
        return [dict(zip(("job_id", "kind", "units", "cost_known", "source"), r))
                for r in c.execute("SELECT job_id,kind,units,cost_known,source FROM ledger ORDER BY seq")]


def read_state(db: str) -> dict:
    return {"rows": _rows(db), "anomalies": _anomalies(db), "ledger": _ledger(db)}


# ============================================================ adapter di controprova (P-B04)
def _adapter(kind: str, core_path: str, account_id: str = "fake_acct_a", ledger_dir: str | None = None):
    _core(core_path)
    import hashlib as _h
    from adapters.base import Job
    from adapters.fake import FakeAdapter

    if kind == "fake":
        return FakeAdapter(account_id=account_id)
    if kind == "submit_unknown":
        class UnknownSubmitFake(FakeAdapter):
            def submit(self, spec):
                self.submits += 1
                self.transport.send(self.serialize(spec))          # marcatore di invio raggiunto
                raise ConnectionResetError("risposta del provider persa dopo l'invio")
        return UnknownSubmitFake(account_id=account_id)
    if kind in ("drift_nested", "drift_top"):
        class Drift(FakeAdapter):
            """serialize() cambia fra la prima chiamata (sigillo runtime) e la seconda (Core run_job):
            nested -> muta un parametro annidato; top -> aggiunge un campo di primo livello."""
            calls = 0
            def serialize(self, spec):
                type(self).calls += 1
                base = super().serialize(spec)
                if type(self).calls == 1:
                    return base
                head, body = base.split(b" ", 2)[:2], base.split(b" ", 2)[2]
                obj = json.loads(body)
                if kind == "drift_nested":
                    obj["params"]["aspect_ratio"] = "16:9"          # mutazione annidata
                else:
                    obj["injected"] = 1                               # campo di primo livello
                return b" ".join(head) + b" " + json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                                          ensure_ascii=False).encode("utf-8")
        return Drift(account_id=account_id)
    if kind == "reorder":
        class Reorder(FakeAdapter):
            """submit() invia lo STESSO JSON con le chiavi in altro ordine: semanticamente uguale,
            byte diversi. Non e' cio' che e' stato autorizzato."""
            def submit(self, spec):
                self.submits += 1
                base = self.serialize(spec)
                head, body = base.split(b" ", 2)[:2], base.split(b" ", 2)[2]
                obj = json.loads(body)
                reordered = json.dumps({k: obj[k] for k in reversed(list(obj))}, separators=(",", ":"),
                                       ensure_ascii=False).encode("utf-8")
                digest = self.transport.send(b" ".join(head) + b" " + reordered)
                now = self.clock()
                return Job(job_id="x", spec_key=spec.spec_key, provider=self.name, provider_job_id="pv_x",
                           provider_account=self.account_id, payload_digest=digest, submitted_at=now,
                           terminal_by=now + 300)
        return Reorder(account_id=account_id)
    if kind == "substitute":
        class Substitute(FakeAdapter):
            """Riproduzione PRE-FIX di P-B04: autorizza da solo un secondo digest nel trasporto
            (stesso dominio di privilegio) e invia byte diversi da quelli autorizzati dal Core."""
            def submit(self, spec):
                self.submits += 1
                other = self.serialize(spec) + b"{\"injected\":1}"
                self.transport.authorize(_h.sha256(other).hexdigest())
                digest = self.transport.send(other)
                now = self.clock()
                return Job(job_id="x", spec_key=spec.spec_key, provider=self.name, provider_job_id="pv_x",
                           provider_account=self.account_id, payload_digest=digest, submitted_at=now,
                           terminal_by=now + 300)
        return Substitute(account_id=account_id)
    if kind == "identity_drift":
        class IdentityDrift(FakeAdapter):
            """`account_id` cambia DOPO la lettura fatta dal runtime per il sigillo: il Core
            persistera' un'ownership diversa da quella sigillata -> IDENTITY_DRIFT."""
            reads = 0
            @property
            def account_id(self):
                type(self).reads += 1
                return account_id if type(self).reads <= 1 else "acct_other"
            @account_id.setter
            def account_id(self, v):
                pass
        return IdentityDrift(account_id=account_id)
    if kind in ("snapshot_missing", "snapshot_corrupt"):
        class Tamper(FakeAdapter):
            """Prima del send il file .bin dello snapshot sparisce (missing) o viene corrotto
            (digest mismatch): simula evidenza persa/alterata fra sigillo e invio."""
            def submit(self, spec):
                self.submits += 1
                payload = self.serialize(spec)
                path = os.path.join(ledger_dir, _h.sha256(payload).hexdigest() + ".bin")
                if kind == "snapshot_missing":
                    os.remove(path)
                else:
                    os.chmod(path, 0o644)
                    data = bytearray(open(path, "rb").read())
                    data[len(data) // 2] ^= 0x01
                    with open(path, "wb") as fh:
                        fh.write(bytes(data))
                digest = self.transport.send(payload)
                now = self.clock()
                return Job(job_id="x", spec_key=spec.spec_key, provider=self.name, provider_job_id="pv_x",
                           provider_account=self.account_id, payload_digest=digest, submitted_at=now,
                           terminal_by=now + 300)
        return Tamper(account_id=account_id)
    raise ValueError(kind)


def go_governed(db: str, core_path: str, prompt: str, op: str, *, adapter_kind: str = "fake",
                account_id: str = "fake_acct_a", intent: str = "new_attempt", reason: str | None = "INITIAL_GENERATION",
                quote: bool = True, max_polls: int = 3, inputs_over: dict | None = None) -> dict:
    """Percorso GOVERNATO (autorizzazione LAB + quote fidata emessa dal lato autorita'), con adapter scelto."""
    from runtime import go_candidate
    from runtime.authorization import DEFAULT_LAB_AUTHORIZATION, AuthorizationRefused
    from runtime.payload_snapshot import ledger_dir_for
    _core(core_path)
    out: dict = {"pid": os.getpid()}
    adapter = None
    try:
        qid = None
        if quote and intent == "new_attempt":
            q = worker.store_call(db, core_path, "issue_lab_quote", prompt, op, inputs_over or {})
            if not q.get("ok"):
                return {"ok": False, "error": "QUOTE_SETUP_FAILED", "detail": q}
            qid = q["result"]
        adapter = _adapter(adapter_kind, core_path, account_id, ledger_dir=ledger_dir_for(db))
        res = go_candidate.go(make_inputs(prompt, **(inputs_over or {})), adapter=adapter, provider_mode="fake",
                              store_path=db, core_path=core_path, max_polls=max_polls, intent=intent,
                              reason=reason, auto_permit=True, operation_id=op, quote_id=qid,
                              authorization=DEFAULT_LAB_AUTHORIZATION)
        out.update(ok=True, outcome=res.outcome, state=res.state, job_id=res.job_id,
                   reservation_outcome=res.reservation_outcome, spec_key=res.spec_key,
                   persisted=res.persisted, payload_snapshot=res.payload_snapshot, resumed=res.resumed,
                   quote_id=qid)
    except AuthorizationRefused as e:
        out.update(ok=False, error="AuthorizationRefused", code=e.code, message=str(e))
    except go_candidate.IntentRefused as e:
        out.update(ok=False, error="IntentRefused", code=e.code, message=str(e))
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    if adapter is not None:
        t = getattr(adapter, "transport", None)
        out["submits"] = adapter.submits
        out["transport_sent_count"] = getattr(t, "sent_count", None)
        out["transport_sent"] = list(getattr(t, "sent", []) or [])
        out["transport_refused"] = list(getattr(t, "refused", []) or [])
        out["transport_guarded"] = type(t).__name__
    return out


# ============================================================ P-B04 ledger (lettura / controprove API)
def ledger_inspect(db: str, core_path: str, prompt: str, job_id: str, inputs_over: dict | None = None) -> dict:
    """Rilegge lo snapshot dal ledger e lo confronta con i byte canonici ricalcolati e con la riga del job."""
    from runtime.genspec_bridge import build_genspec
    from runtime.payload_snapshot import SnapshotLedger, ledger_dir_for, opkey
    _core(core_path)
    from adapters.base import GenSpec
    from adapters.fake import FakeAdapter
    try:
        row = next(r for r in _rows(db) if r["job_id"] == job_id)
        ledger = SnapshotLedger(ledger_dir_for(db))
        spec = build_genspec(make_inputs(prompt, **(inputs_over or {})), GenSpec)
        expected = FakeAdapter().serialize(spec)
        digest = row["payload_digest"]
        key = opkey(row["operation_id"], row["provider"], row["provider_account"])
        bin_path = ledger.bin_path(digest)
        persisted = open(bin_path, "rb").read()
        st = os.stat(bin_path)
        seal = json.load(open(ledger.seal_path(digest, key)))
        bind = json.load(open(ledger.bind_path(digest, key, row["attempt_token"])))
        send_path = ledger.send_path(digest, key, row["attempt_token"])
        send = json.load(open(send_path)) if os.path.exists(send_path) else None
        audit = ledger.audit(digest=digest, operation_id=row["operation_id"], provider=row["provider"],
                             provider_account=row["provider_account"], job_id=job_id,
                             attempt_token=row["attempt_token"])
        return {"ok": True, "job": row, "digest": digest, "bytes": len(persisted),
                "persisted_equals_recomputed_canonical": persisted == expected,
                "sha256_of_persisted_equals_job_digest": hashlib.sha256(persisted).hexdigest() == digest,
                "persisted_mode": oct(st.st_mode & 0o777), "seal": seal, "bind": bind, "send_attestation": send,
                "audit": audit, "listing": ledger.listing(), "ledger_dir": ledger.root}
    except Exception as e:                                  # noqa: BLE001
        return _err(e)


def ledger_api_counterproofs(db: str, core_path: str, prompt: str, job_id: str) -> dict:
    """Controprove a livello di API del ledger, su uno snapshot reale gia' inviato."""
    from runtime.payload_snapshot import PayloadSnapshotError, SnapshotLedger, ledger_dir_for, _write_once
    _core(core_path)
    out: dict = {}
    try:
        row = next(r for r in _rows(db) if r["job_id"] == job_id)
        ledger = SnapshotLedger(ledger_dir_for(db))
        payload = open(ledger.bin_path(row["payload_digest"]), "rb").read()
        ctx = dict(provider=row["provider"], provider_account=row["provider_account"])

        def probe(name, fn):
            try:
                r = fn()
                out[name] = {"refused": False, "result": r if isinstance(r, (dict, str)) else str(r)}
            except PayloadSnapshotError as e:
                out[name] = {"refused": True, "code": e.code}
            except FileExistsError as e:
                out[name] = {"refused": True, "code": "WRITE_ONCE_FILE_EXISTS", "detail": type(e).__name__}
        # immutabilita': riscrittura del .bin via primitiva write-once -> impossibile
        probe("overwrite_bin_write_once", lambda: _write_once(ledger.bin_path(row["payload_digest"]), b"x"))
        # sigillo idempotente sullo stesso contesto; conflitto su contesto diverso con stesso file? no: altro seal file
        probe("seal_idempotent_same_context", lambda: ledger.seal(payload, operation_id=row["operation_id"],
                                                                  spec_key=row["spec_key"], **ctx))
        probe("seal_conflict_other_spec_key", lambda: ledger.seal(payload, operation_id=row["operation_id"],
                                                                  spec_key="not_the_spec", **ctx))
        # snapshot di ALTRA operazione: sigillato solo sotto op X, verificato sotto op Y
        probe("other_operation_seal_missing", lambda: ledger.check(payload, operation_id="OTHER:op", job_id=job_id,
                                                                   attempt_token=row["attempt_token"], **ctx))
        # token errato
        probe("wrong_attempt_token", lambda: ledger.check(payload, operation_id=row["operation_id"], job_id=job_id,
                                                          attempt_token="att_wrong", **ctx))
        # seconda attestazione di invio per lo stesso attempt
        probe("second_send_same_attempt", lambda: ledger.verify_before_send(
            payload, operation_id=row["operation_id"], job_id=job_id, attempt_token=row["attempt_token"], **ctx))
        # byte diversi (reorder semantico) -> nessuno snapshot con quel digest
        head, body = payload.split(b" ", 2)[:2], payload.split(b" ", 2)[2]
        obj = json.loads(body)
        reordered = b" ".join(head) + b" " + json.dumps({k: obj[k] for k in reversed(list(obj))},
                                                       separators=(",", ":"), ensure_ascii=False).encode()
        probe("reordered_bytes", lambda: ledger.check(reordered, operation_id=row["operation_id"], job_id=job_id,
                                                      attempt_token=row["attempt_token"], **ctx))
        # audit con job di altra operazione
        out["audit_other_operation"] = ledger.audit(digest=row["payload_digest"], operation_id="OTHER:op",
                                                    job_id=job_id, attempt_token=row["attempt_token"], **ctx)
        out["ok"] = True
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    return out


def pre_submit_race(db: str, core_path: str, prompt: str, op: str) -> dict:
    """Controprova 5 (NG-03): due terminalizzazioni pre-submit concorrenti sullo stesso job.
    La seconda porta una revisione obsoleta: il Core deve rifiutarla (CAS) e il runtime non
    deve tentare alcun secondo settlement. Verifica anche l'idempotenza esplicita di settle."""
    import copy
    from runtime.authorization import DEFAULT_LAB_AUTHORIZATION, LAB_QUOTE_UNIT, lab_price_for
    from runtime.genspec_bridge import build_genspec
    from runtime.go_candidate import ReservationObserver
    from runtime.payload_snapshot import (PRE_SUBMIT_REFUSAL_SOURCE, PayloadSnapshotError, SnapshotBinding,
                                          SnapshotLedger, install_snapshot_guard, ledger_dir_for)
    _core(core_path)
    from adapters.base import GenSpec
    from adapters.fake import FakeAdapter
    from registry.reservations import SqliteReservationStore
    out: dict = {}
    try:
        inner = SqliteReservationStore(db)
        spec = build_genspec(make_inputs(prompt), GenSpec)
        env = DEFAULT_LAB_AUTHORIZATION.envelope_for(op)
        inner.open_envelope(env, 100, unit=LAB_QUOTE_UNIT, scope=op.split(":")[0])
        amount = lab_price_for(spec.model)
        qid = inner.issue_quote(operation_id=op, spec_key=spec.spec_key, envelope_id=env,
                                amount=amount, unit=LAB_QUOTE_UNIT)
        outcome, job = inner.reserve_or_get_live(spec, budget_units=amount, envelope_id=env,
                                                 operation_id=op, quote_id=qid, now=1.0)
        adapter = FakeAdapter(account_id="fake_acct_a")
        ledger = SnapshotLedger(ledger_dir_for(db))
        seal = ledger.seal(adapter.serialize(spec), operation_id=op, spec_key=spec.spec_key,
                           provider=adapter.name, provider_account=adapter.account_id, now=1.0)
        guard = install_snapshot_guard(adapter)
        observer = ReservationObserver(inner)
        observer.attach_snapshot(SnapshotBinding(ledger, guard, operation_id=op, provider=adapter.name,
                                                 provider_account=adapter.account_id,
                                                 digest=seal["digest"], clock=lambda: 2.0))
        stale = copy.copy(job)                      # la copia conserva la revisione pre-terminalizzazione
        kw = dict(provider=adapter.name, provider_account=adapter.account_id,
                  payload_digest="f" * 64,          # digest diverso dal sigillo -> SERIALIZATION_DRIFT
                  attempt_token="att_race_1", now=2.0)
        # primo scrittore: terminalizza con provenance veritiera
        try:
            observer.mark_submitting(job, **kw)
            out["first"] = {"refused": False}
        except PayloadSnapshotError as e:
            out["first"] = {"refused": True, "code": e.code, "report": observer.pre_submit_refusal}
        out["state_after_first"] = {"rows": _rows(db), "ledger": _ledger(db)}
        # secondo scrittore: stessa riga, revisione obsoleta (un altro ha gia' scritto)
        try:
            observer.mark_submitting(stale, **dict(kw, attempt_token="att_race_2"))
            out["second_stale"] = {"refused": False}
        except PayloadSnapshotError as e:
            out["second_stale"] = {"refused": True, "code": e.code, "report": observer.pre_submit_refusal}
        out["state_after_second"] = {"rows": _rows(db), "ledger": _ledger(db)}
        # idempotenza esplicita del settlement e conflitto su importo diverso
        out["settle_same_amount_again"] = inner.settle(job.job_id, units=0,
                                                       source=PRE_SUBMIT_REFUSAL_SOURCE, now=3.0)
        try:
            inner.settle(job.job_id, units=7, source="SOMEONE_ELSE", now=3.0)
            out["settle_other_amount"] = {"applied": True}
        except Exception as e:                                  # noqa: BLE001
            out["settle_other_amount"] = {"applied": False, "error": type(e).__name__, "message": str(e)}
        out["state_end"] = {"rows": _rows(db), "ledger": _ledger(db), "anomalies": _anomalies(db)}
        out["ledger_totals"] = inner.ledger_totals(env)
        out["ok"] = True
    except Exception as e:                                      # noqa: BLE001
        out.update(_err(e))
    return out


def resume_only(db: str, core_path: str, prompt: str, op: str) -> dict:
    return worker.run_go(db, prompt, operation_id=op, governed=True, max_polls=3, core_path=core_path)


def ledger_listing(db: str) -> dict:
    from runtime.payload_snapshot import ledger_dir_for
    d = ledger_dir_for(db)
    return {"dir": d, "files": sorted(os.listdir(d)) if os.path.isdir(d) else None}


# ============================================================ P-B02
def make_report(secret: str, provider: str, account: str, fields: dict, *, sign_with: dict | None = None,
                tamper: dict | None = None) -> dict:
    """Report firmato con la chiave derivata (secret, provider, account); `sign_with` firma con un'altra
    identita' (chiave sbagliata); `tamper` altera campi DOPO la firma."""
    import secrets as _s
    import time as _t
    from runtime.reconciliation import REPORT_SCHEMA, derive_report_key, sign_report
    signer = sign_with or {"secret": secret, "provider": provider, "account": account}
    key = derive_report_key(signer["secret"], signer["provider"], signer["account"])
    base = dict(schema=REPORT_SCHEMA, provider=provider, provider_account=account, provider_job_id="pv_remote_1",
                remote_ref="remote:pv_remote_1", state="SUCCEEDED", nonce=f"nonce_{_s.token_hex(16)}", issued_at=_t.time())
    base.update(fields)                       # i campi del report (anche provider/conto) sono sovrascrivibili: controprove
    rep = sign_report(key, base)
    if tamper:
        rep.update(tamper)
    return rep


def reconcile(db: str, core_path: str, secret: str, report: dict, *, job_id: str, adapter_name: str = "fake",
              adapter_account: str = "fake_acct_a", key_account: str | None = None, key_provider: str | None = None,
              with_snapshot: bool = True) -> dict:
    """Riconciliazione autenticata in un nuovo interprete. La chiave del verificatore e' quella dello
    spender per (provider, conto) dell'adapter (o `key_account` se si vuole provare il conto sbagliato)."""
    from runtime.payload_snapshot import SnapshotLedger, ledger_dir_for
    from runtime.reconciliation import ReconciliationRefused, derive_report_key, nonce_dir_for, reconcile_authenticated
    _core(core_path)
    from adapters.fake import FakeAdapter
    from registry.reservations import SqliteReservationStore
    before = next((r for r in _rows(db) if r["job_id"] == job_id), None)
    try:
        class Named(FakeAdapter):
            name = adapter_name
        adapter = Named(account_id=adapter_account)
        key = derive_report_key(secret, key_provider or adapter_name, key_account or adapter_account)
        store = SqliteReservationStore(db)
        job = reconcile_authenticated(store, adapter, report, job_id=job_id, key=key, nonce_dir=nonce_dir_for(db),
                                      snapshot_ledger=SnapshotLedger(ledger_dir_for(db)) if with_snapshot else None)
        out = {"ok": True, "state": job.state.value, "job": job.to_dict()}
    except ReconciliationRefused as e:
        out = {"ok": False, "error": "ReconciliationRefused", "code": e.code, "message": str(e)}
    except Exception as e:                                  # noqa: BLE001
        out = _err(e)
    after = next((r for r in _rows(db) if r["job_id"] == job_id), None)
    out["before"] = before
    out["after"] = after
    out["journal_unchanged"] = before == after
    out["anomalies"] = _anomalies(db, job_id)
    return out


def raw_reconcile_unauthenticated(db: str, core_path: str, job_id: str, state: str) -> dict:
    """Controprova storica: `store.reconcile` diretto con evidenza arbitraria (il percorso PRE-FIX).
    Serve a dimostrare che il gap era reale; nel runtime governato questo percorso NON e' invocato."""
    _core(core_path)
    from adapters.base import JobState
    from registry.reservations import SqliteReservationStore
    try:
        store = SqliteReservationStore(db)
        job = store.get(job_id)
        r = store.reconcile(job, JobState(state), {"source": "anyone", "remote_ref": "pv_of_someone_else"})
        return {"ok": True, "state": r.state.value}
    except Exception as e:                                  # noqa: BLE001
        return _err(e)


def put_state(db: str, core_path: str, job_id: str, state: str) -> dict:
    """Simula un poll successivo che riporta il job in incertezza (RUNNING -> SUBMIT_UNKNOWN, put ordinario)."""
    _core(core_path)
    from adapters.base import JobState
    from registry.reservations import SqliteReservationStore
    try:
        store = SqliteReservationStore(db)
        job = store.get(job_id)
        job.state = JobState(state)
        r = store.put(job)
        return {"ok": True, "state": r.state.value}
    except Exception as e:                                  # noqa: BLE001
        return _err(e)


# ============================================================ LEGACY / hf_batch
def legacy_go_disabled(db: str, core_path: str, prompt: str, op: str, *, disable: bool) -> dict:
    """Nuovo interprete: il percorso LEGACY_LAB con l'interruttore chiuso deve fermarsi PRIMA di
    importare il Core e di creare lo store."""
    if disable:
        os.environ["CREATIVE_OS_LEGACY_LAB_SPEND_PATH"] = "disabled"
    from runtime import go_candidate
    from runtime.provider_gate import LegacySpendPathDisabled, legacy_spend_path_state
    out: dict = {"switch_state": legacy_spend_path_state(), "core_imported_before": "adapters.base" in sys.modules}
    try:
        res = go_candidate.go(make_inputs(prompt), adapter=None, provider_mode="fake", store_path=db,
                              core_path=core_path, max_polls=3, operation_id=op)   # authorization=None
        out.update(ok=True, state=res.state, governance=res.governance)
    except LegacySpendPathDisabled as e:
        out.update(ok=False, error=e.code, message=str(e))
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    out["core_imported_after"] = "adapters.base" in sys.modules
    out["store_created"] = os.path.exists(db)
    return out


def hf_batch_paths(db: str, core_path: str, canary_home: str, *, disable_legacy: bool, adapter: bool) -> dict:
    """Batch di hf_batch_runtime: legacy (authorization=None) con interruttore chiuso; adapter=None come nel __main__."""
    import threading
    if disable_legacy:
        os.environ["CREATIVE_OS_LEGACY_LAB_SPEND_PATH"] = "disabled"
    from tests import audit_sentinel
    audit_sentinel.install(canary_home)
    _core(core_path)
    from runtime import hf_batch_runtime as hb
    from runtime.hf_batch_bridge import media_sha_from_lock
    from runtime.provider_gate import LegacySpendPathDisabled, RealProviderDisabled
    HANDOFF = os.path.join(GATE01, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16")
    lock = json.load(open(os.path.join(HANDOFF, "EVIDENCE", "MOTION_B1_B4C_RUNTIME_LOCK.json"), encoding="utf-8"))
    res = media_sha_from_lock(lock)
    ad = _adapter("fake", core_path) if adapter else None
    out: dict = {"disable_legacy": disable_legacy, "adapter": adapter}
    try:
        b = hb.Batch(os.path.join(HANDOFF, "SPECS", "spec_motion_B1_B4C.json"), adapter=ad, store_path=db, max_polls=3)
        current = threading.local()
        b.media_sha256 = lambda flag, rid, ref: res(current.asset)(flag, rid, ref)
        orig = b.run_job
        def run_job(j, lk):
            current.asset = j["asset"]
            return orig(j, lk)
        b.run_job = run_job
        b.require = lambda: lock
        b.fingerprint = lambda: (lock["fingerprint_sha256"], {})
        b.lock_path = os.path.join(HANDOFF, "EVIDENCE", "MOTION_B1_B4C_RUNTIME_LOCK.json")   # lock reale (come T22)
        b.trace_path = os.path.join(os.path.dirname(db), "pb07_LAB_TRACE.json")
        t = b.go()
        out.update(ok=True, run_statuses=[x["run_status"] for x in t["jobs"]],
                   governance=[x["governance"] for x in t["jobs"]],
                   legacy_resume_as_start=[x["legacy_resume_as_start"] for x in t["jobs"]])
        try:
            os.remove(b.trace_path)
        except OSError:
            pass
    except (LegacySpendPathDisabled, RealProviderDisabled) as e:
        out.update(ok=False, error=e.code, message=str(e))
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    for verb in ("lock", "quote"):
        try:
            b2 = hb.Batch(os.path.join(HANDOFF, "SPECS", "spec_motion_B1_B4C.json"), adapter=None, store_path=db)
            getattr(b2, verb)()
            out[verb] = "VERB_RAN"
        except RealProviderDisabled as e:
            out[verb] = e.code
        except Exception as e:                              # noqa: BLE001
            out[verb] = f"{type(e).__name__}: {e}"
    out["submits"] = ad.submits if ad else None
    out["violations"] = audit_sentinel.violations()
    out["store_created"] = os.path.exists(db)
    return out


# ============================================================ ORPHAN RESERVED
def orphan_scenario(db: str, core_path: str, secret: str) -> dict:
    from runtime import go_candidate
    from runtime.authorization import DEFAULT_LAB_AUTHORIZATION
    from runtime.genspec_bridge import build_genspec
    from runtime.orphan_lease import RECLAIM_POLICY, classify_attempt, inventory
    from runtime.payload_snapshot import SnapshotLedger, ledger_dir_for
    from runtime.reconciliation import LabProviderStatusAuthority, ReconciliationRefused, nonce_dir_for, reconcile_authenticated
    _core(core_path)
    from adapters.base import GenSpec
    from adapters.fake import FakeAdapter
    from registry.reservations import SqliteReservationStore
    out: dict = {}
    try:
        store = SqliteReservationStore(db)
        spec = build_genspec(make_inputs("orphan"), GenSpec)
        o, j = store.reserve_or_get_live(spec, now=1.0, operation_id="ORPH:a")   # il processo "muore" qui
        out["reservation"] = {"outcome": o.value, "job_id": j.job_id}
        out["classify_no_intent"] = classify_attempt(store.get(j.job_id), now=100.0)
        ad = FakeAdapter(account_id="fake_acct_a")
        r = go_candidate.go(make_inputs("orphan"), adapter=ad, provider_mode="fake", store_path=db, core_path=core_path,
                            max_polls=3, operation_id="ORPH:a", authorization=DEFAULT_LAB_AUTHORIZATION)
        out["resume"] = {"outcome": r.outcome, "submits": ad.submits, "resumed": r.resumed}
        try:
            go_candidate.go(make_inputs("orphan"), adapter=ad, provider_mode="fake", store_path=db, core_path=core_path,
                            max_polls=3, operation_id="ORPH:a", intent="new_attempt", reason="RETRY", auto_permit=True,
                            authorization=DEFAULT_LAB_AUTHORIZATION)
            out["new_attempt_same_operation"] = {"accepted": True}
        except go_candidate.IntentRefused as e:
            out["new_attempt_same_operation"] = {"accepted": False, "code": e.code}
        out["recover_orphaned_submits"] = [x.to_dict() for x in store.recover_orphaned_submits(now=100.0)]
        out["due_for_reconcile"] = [x.job_id for x in store.due_for_reconcile(now=100.0)]
        out["reserved_units"] = store.reserved_units()
        # reconciliation autenticata dell'orfana: nulla e' stato inviato -> OWNERSHIP_INCOMPLETE
        auth = LabProviderStatusAuthority(secret, "fake", "fake_acct_a")
        rep = auth.report(provider_job_id="pv_ghost", attempt_token="att_none", payload_digest="0" * 64,
                          operation_id="ORPH:a", job_id=j.job_id, state="FAILED", remote_ref="remote:none")
        try:
            reconcile_authenticated(store, ad, rep, job_id=j.job_id, key=auth.key, nonce_dir=nonce_dir_for(db),
                                    snapshot_ledger=SnapshotLedger(ledger_dir_for(db)))
            out["reconcile_orphan"] = {"accepted": True}
        except ReconciliationRefused as e:
            out["reconcile_orphan"] = {"accepted": False, "code": e.code}
        # controllo: RESERVED CON intento (crash dopo l'invio) e' un altro caso, con uscita
        q = CTX_QUEUE = None  # noqa: F841
        out["with_intent_case"] = "vedi crash_after_send"
        out["inventory"] = inventory(store, ["ORPH:a", "ORPH:none"], now=100.0)
        out["reclaim_policy"] = RECLAIM_POLICY
        out["rows"] = _rows(db)
        out["ok"] = True
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    return out


def crash_after_send(db: str, core_path: str) -> dict:
    """Usa l'helper storico: processo che muore dopo il marcatore di invio (exit 4)."""
    return worker.run_go(db, "crash", operation_id="ORPH:crash", crash_after_send=True, core_path=core_path)


def classify_all(db: str, core_path: str, ops: list[str]) -> dict:
    from runtime.orphan_lease import inventory
    _core(core_path)
    from registry.reservations import SqliteReservationStore
    store = SqliteReservationStore(db)
    return {"inventory": inventory(store, ops, now=100.0),
            "recovered": [x.to_dict() for x in store.recover_orphaned_submits(now=100.0)]}


def cleanup_db(db: str) -> None:
    for s in ("", "-journal", "-wal", "-shm"):
        if os.path.exists(db + s):
            os.remove(db + s)
    for s in (".snapshots", ".reconciliation"):
        shutil.rmtree(db + s, ignore_errors=True)


def _entry(q, fn, args, kwargs):
    try:
        q.put(fn(*args, **kwargs))
    except Exception as e:                                  # noqa: BLE001
        q.put({"ok": False, "error": type(e).__name__, "message": str(e), "trace": traceback.format_exc(limit=5)})
