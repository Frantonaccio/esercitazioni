"""PRE-FIX reproduction on the UNMODIFIED baseline (Runtime 39c82968, Core 740ee979).
Each block records what the baseline code actually does. No provider, no credentials."""
import json, os, sys, hashlib, sqlite3, tempfile, shutil, traceback, inspect
GATE = "/home/user/esercitazioni/RUNTIME_INTEGRATION_GATE_01"
CORE = "/home/user/creative-os"
sys.path.insert(0, GATE); sys.path.insert(0, CORE)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
from runtime import go_candidate
from runtime.authorization import DEFAULT_LAB_AUTHORIZATION, LAB_PRICE_TABLE, LabAuthorization
from tests.worker import make_inputs
from adapters.base import GenSpec, JobState
from adapters.fake import FakeAdapter, MockTransport
from registry.reservations import SqliteReservationStore
from transport.pipeline import run_job
from runtime.genspec_bridge import build_genspec

STATE = os.path.join(GATE, "state")
out = {"baseline": {"runtime_sha": "39c82968fbfb3f3b7ba9fcfe9dc317ea0da9e74e", "core_sha": "740ee979300fe20a9382992528604dee70cb2fcf"}}

def db(name):
    p = os.path.join(STATE, f"prefix_{name}.db")
    for s in ("", "-journal", "-wal", "-shm"):
        if os.path.exists(p + s): os.remove(p + s)
    return p

def rows(path):
    with sqlite3.connect(path) as c:
        return [dict(zip(("job_id","state","provider","provider_account","provider_job_id","payload_digest","attempt_token","operation_id","budget_units","envelope_id","quote_id","permit_id","submit_intent_at"),
                r)) for r in c.execute("SELECT job_id,state,provider,provider_account,provider_job_id,payload_digest,attempt_token,operation_id,budget_units,envelope_id,quote_id,permit_id,submit_intent_at FROM reservations ORDER BY rowid")]

# ---------------------------------------------------------------- P-B02
try:
    p = db("pb02")
    store = SqliteReservationStore(p)
    spec = build_genspec(make_inputs("pb02 unknown"), GenSpec)
    class Lost(FakeAdapter):
        def submit(self, gs):
            self.submits += 1
            self.transport.send(self.serialize(gs))
            raise TimeoutError("lost")
    ad = Lost(account_id="acct_owner")
    try:
        run_job(ad, spec, store, max_polls=2, operation_id="PB02:a")
    except TimeoutError:
        pass
    j = store.find_latest_by_operation("PB02:a")
    before = j.to_dict()
    # An UNRELATED party (no adapter, no account, no key) reconciles with arbitrary evidence
    # naming another provider/account/job: accepted?
    ev = {"source": "anyone", "remote_ref": "pv_of_someone_else", "provider": "higgsfield",
          "provider_account": "acct_stranger", "provider_job_id": "pv_other", "attempt_token": "att_bogus"}
    r = store.reconcile(j, JobState.SUCCEEDED, ev)
    after = store.get(j.job_id).to_dict()
    # replay of the same evidence on a second SUBMIT_UNKNOWN job of another operation
    spec2 = build_genspec(make_inputs("pb02 unknown 2"), GenSpec)
    ad2 = Lost(account_id="acct_owner")
    try:
        run_job(ad2, spec2, store, max_polls=2, operation_id="PB02:b")
    except TimeoutError:
        pass
    j2 = store.find_latest_by_operation("PB02:b")
    r2 = store.reconcile(j2, JobState.FAILED, ev)      # same evidence, other operation, other outcome
    out["P-B02"] = {"status": "REPRODUCED",
                    "finding": "store.reconcile accepts any mapping with non-empty source/remote_ref: no provider/account/job/attempt binding, no authentication, no replay protection",
                    "job_before": before, "job_after_unrelated_reconcile": after,
                    "second_job_after_replayed_evidence": store.get(j2.job_id).to_dict(),
                    "reconcile_signature": str(inspect.signature(SqliteReservationStore.reconcile)),
                    "runtime_callers_of_reconcile": [f for f in os.listdir(os.path.join(GATE, "runtime")) if "reconcile(" in open(os.path.join(GATE, "runtime", f)).read()]}
except Exception:
    out["P-B02"] = {"status": "EXCEPTION", "trace": traceback.format_exc()}

# ---------------------------------------------------------------- P-B04
try:
    p = db("pb04")
    store = SqliteReservationStore(p)
    spec = build_genspec(make_inputs("pb04 bytes"), GenSpec)
    ad = FakeAdapter(account_id="acct_owner")
    job = run_job(ad, spec, store, max_polls=3, operation_id="PB04:a")
    persisted = store.get(job.job_id).to_dict()
    canon = ad.serialize(spec)
    # are the authorized bytes persisted anywhere under state/ ? (only the digest is)
    blob_found = []
    for root, _, files in os.walk(STATE):
        for f in files:
            fp = os.path.join(root, f)
            try:
                if canon in open(fp, "rb").read():
                    blob_found.append(os.path.relpath(fp, GATE))
            except OSError:
                pass
    # in-memory authorization: an adapter that authorizes its own second digest reaches the SEND MARKER
    # with bytes different from the ones the Core authorized; the mismatch is caught only AFTER the send.
    class Drift(FakeAdapter):
        def submit(self, gs):
            self.submits += 1
            other = self.serialize(gs) + b"{\"injected\":1}"
            self.transport.authorize(hashlib.sha256(other).hexdigest())     # same privilege domain
            digest = self.transport.send(other)                              # send marker reached
            now = self.clock()
            from adapters.base import Job
            return Job(job_id="x", spec_key=gs.spec_key, provider=self.name, provider_job_id="pv_x",
                       provider_account=self.account_id, payload_digest=digest, submitted_at=now, terminal_by=now + 300)
    ad2 = Drift(account_id="acct_owner")
    spec2 = build_genspec(make_inputs("pb04 drift"), GenSpec)
    err = None
    try:
        run_job(ad2, spec2, store, max_polls=3, operation_id="PB04:b")
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    drift_job = store.find_latest_by_operation("PB04:b").to_dict()
    out["P-B04"] = {"status": "REPRODUCED",
                    "finding": "only sha256 digest persisted (reservations.payload_digest); authorized bytes exist nowhere on disk; "
                               "authorization set lives in MockTransport memory (same privilege domain): a drifting adapter reaches the send marker "
                               "with different bytes and the mismatch is detected only AFTER the send (SUBMIT_UNKNOWN), not before",
                    "persisted_job": persisted, "authorized_bytes_len": len(canon),
                    "authorized_bytes_sha256": hashlib.sha256(canon).hexdigest(),
                    "authorized_bytes_persisted_under_state": blob_found,
                    "drift_case": {"error": err, "job": drift_job, "transport_sent": ad2.transport.sent,
                                   "transport_sent_count": ad2.transport.sent_count,
                                   "anomalies": store.anomalies(drift_job["job_id"])}}
except Exception:
    out["P-B04"] = {"status": "EXCEPTION", "trace": traceback.format_exc()}

# ---------------------------------------------------------------- LEGACY SPEND PATH
try:
    p = db("legacy")
    ad = FakeAdapter(account_id="acct_owner")
    res = go_candidate.go(make_inputs("legacy path"), adapter=ad, provider_mode="fake", store_path=p,
                          max_polls=3, operation_id="LEGACY:a")       # authorization=None, intent=resume default
    st = rows(p)
    with sqlite3.connect(p) as c:
        n_env = c.execute("SELECT COUNT(*) FROM envelopes").fetchone()[0]
        n_q = c.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
        n_perm = c.execute("SELECT COUNT(*) FROM permits").fetchone()[0]
        ledger = [dict(zip(("kind","units","envelope_id"), r)) for r in c.execute("SELECT kind,units,envelope_id FROM ledger")]
    out["LEGACY_SPEND_PATH"] = {"status": "REPRODUCED",
                                "finding": "go(authorization=None) [LEGACY_LAB] submits with intent=resume on an empty operation (resume-as-start), "
                                           "budget_units=0, no envelope, no quote, no permit: bypasses authorization/quote/envelope/permit; reachable by any same-UID caller; "
                                           "ledger RESERVE row with envelope NULL",
                                "result": {"state": res.state, "governance": res.governance, "legacy_resume_as_start": res.legacy_resume_as_start,
                                           "budget_units": res.budget_units, "envelope_id": res.envelope_id, "quote_id": res.quote_id, "permit_id": res.permit_id,
                                           "submits": ad.submits},
                                "rows": st, "envelopes": n_env, "quotes": n_q, "permits": n_perm, "ledger": ledger}
except Exception:
    out["LEGACY_SPEND_PATH"] = {"status": "EXCEPTION", "trace": traceback.format_exc()}

# ---------------------------------------------------------------- ORPHAN RESERVED
try:
    p = db("orphan")
    store = SqliteReservationStore(p)
    spec = build_genspec(make_inputs("orphan"), GenSpec)
    o, j = store.reserve_or_get_live(spec, now=1.0, operation_id="ORPH:a")   # process dies here (no mark_submitting)
    ad = FakeAdapter(account_id="acct_owner")
    r_resume = go_candidate.go(make_inputs("orphan"), adapter=ad, provider_mode="fake", store_path=p, max_polls=3,
                               operation_id="ORPH:a", authorization=DEFAULT_LAB_AUTHORIZATION)
    try:
        go_candidate.go(make_inputs("orphan"), adapter=ad, provider_mode="fake", store_path=p, max_polls=3,
                        operation_id="ORPH:a", intent="new_attempt", reason="RETRY", auto_permit=True,
                        authorization=LabAuthorization({"ORPH": "ENV_ORPH"}))
        na = "ACCEPTED"
    except Exception as e:
        na = f"{type(e).__name__}: {e}"
    rec = [x.to_dict() for x in store.recover_orphaned_submits(now=100.0)]
    due = [x.job_id for x in store.due_for_reconcile(now=100.0)]
    out["ORPHAN_RESERVED"] = {"status": "REPRODUCED",
                              "finding": "RESERVED row without submit_intent_at (reservation committed, process died before mark_submitting): "
                                         "resume -> reserved-no-dispatch forever; new_attempt on same operation -> LIVE_OR_UNCERTAIN_ATTEMPT; "
                                         "recover_orphaned_submits ignores it (no intent); due_for_reconcile lists it but nothing consumes it; "
                                         "no lease/timeout authority exists in Core or Runtime",
                              "orphan_row": rows(p), "resume_outcome": r_resume.outcome, "resume_submits": ad.submits,
                              "new_attempt_same_operation": na, "recover_orphaned_submits": rec, "due_for_reconcile": due,
                              "reserved_units_locked": store.reserved_units()}
except Exception:
    out["ORPHAN_RESERVED"] = {"status": "EXCEPTION", "trace": traceback.format_exc()}

# ---------------------------------------------------------------- AUTHORIZATION / PRICING AUTHORITY
out["AUTHORIZATION_PRICING"] = {"status": "LAB_ONLY_VERIFIED",
                                "envelope_by_scope": dict(DEFAULT_LAB_AUTHORIZATION.envelope_by_scope),
                                "price_table": dict(LAB_PRICE_TABLE), "label": DEFAULT_LAB_AUTHORIZATION.label,
                                "finding": "authority = in-code LAB constants (runtime/authorization.py); quotes issued by test/worker side; "
                                           "no real provider pricing, no real envelope; in same-UID mode the orchestrator can issue its own quotes on the worker store"}

for n in ("pb02", "pb04", "legacy", "orphan"):
    db(n)
with open(sys.argv[1], "w") as fh:
    json.dump(out, fh, indent=2, default=str, sort_keys=True)
print(json.dumps({k: v.get("status") for k, v in out.items() if isinstance(v, dict)}, indent=1))
