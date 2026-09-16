"""MOCK ONLY. Candidate guard around the existing Creative OS FakeAdapter.

No provider plugins, network API, credentials, package installs, real media.
SQLite is a disposable test journal, NOT a second production registry.
Local OS user is trusted; this is not an authorization/security boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CORE_SHA = "9afaddf3cec1e8baf9600ed8dc0461e7adccb5c7"
MIN_PYTHON = (3, 9)   # requisito reale: Path.is_relative_to (3.9). Verificato su 3.9.6.

if sys.version_info < MIN_PYTHON:
    raise SystemExit(
        f"PYTHON_TOO_OLD: richiesto >= {'.'.join(map(str, MIN_PYTHON))}, "
        f"trovato {sys.version.split()[0]}")


class Blocked(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise Blocked(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(value):
    return digest(canonical(value).encode())


def integer(value):
    return type(value) is int and value >= 0


def load_core(root):
    """Read-only provenance check before importing only the pinned fake adapter."""
    root = Path(root).resolve()
    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True).strip()
    require(git("rev-parse", "HEAD") == CORE_SHA, "CORE_VERSION_NOT_TESTED")
    require(not git("status", "--porcelain"), "CORE_DIRTY")
    sys.path.insert(0, str(root))
    from adapters.fake import FakeAdapter
    from adapters.base import GenSpec
    # Detect modules already imported from a different checkout.
    import adapters.fake
    require(Path(adapters.fake.__file__).resolve() ==
            root / "adapters/fake.py", "CORE_IMPORT_MISMATCH")
    return FakeAdapter, GenSpec


class Control:
    def __init__(self, db, root, tenant, fake_class, spec_class, clock=time.time):
        self.db, self.root = str(db), Path(root).resolve()
        self.tenant, self.fake_class = tenant, fake_class
        self.spec_class, self.clock = spec_class, clock
        with self.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS jobs(
              tenant TEXT, id TEXT, fingerprint TEXT, manifest TEXT,
              state TEXT, provider_job TEXT, output_hash TEXT,
              PRIMARY KEY(tenant,id));
            CREATE TABLE IF NOT EXISTS events(
              sequence INTEGER PRIMARY KEY, tenant TEXT, id TEXT,
              state TEXT, detail TEXT);
            """)

    def connect(self):
        return sqlite3.connect(self.db, timeout=10)

    def event(self, c, job, state, detail):
        c.execute("INSERT INTO events(tenant,id,state,detail) VALUES(?,?,?,?)",
                  (self.tenant, job, state, canonical(detail)))

    def validate(self, m):
        require(type(m) is dict, "MANIFEST_INVALID")
        require(m.get("mode") == "MOCK_ONLY", "REAL_PROVIDER_DISABLED")
        require(m.get("tenant_id") == self.tenant, "TENANT_MISMATCH")
        require(isinstance(m.get("job_id"), str) and
                re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", m["job_id"]), "JOB_INVALID")
        require(m.get("core_sha") == CORE_SHA, "CORE_VERSION_NOT_TESTED")
        require(isinstance(m.get("tenant_sha"), str) and
                re.fullmatch(r"[0-9a-f]{40}", m["tenant_sha"]), "TENANT_SHA_INVALID")
        require(m.get("policy_id") == "MOCK_POLICY_V1", "POLICY_NOT_ALLOWED")
        require(m.get("provider") == "fake", "REAL_PROVIDER_DISABLED")
        require(m.get("model") == "fake_model_v1", "MODEL_NOT_ALLOWED")
        require(isinstance(m.get("prompt"), str) and m["prompt"].strip(),
                "PROMPT_MISSING")
        require(m.get("mock_authorization") is True, "AUTHORIZATION_MISSING")
        require(type(m.get("expires_at")) in (int, float) and
                self.clock() < m["expires_at"] < float("inf"), "LOCK_EXPIRED")
        require(integer(m.get("budget_units")), "BUDGET_MISSING_OR_INVALID")
        q = m.get("quote", {})
        require(type(q) is dict and q.get("unit") == "SYNTHETIC_TEST_UNIT" and
                integer(q.get("amount")), "QUOTE_INVALID")
        require(q.get("provider") == "fake" and q.get("model") == m["model"],
                "QUOTE_PROVIDER_MISMATCH")
        require(type(q.get("expires_at")) in (int, float) and
                self.clock() < q["expires_at"] < float("inf"), "QUOTE_EXPIRED")
        require(q["amount"] <= m["budget_units"], "OVER_BUDGET")
        files = m.get("files")
        require(type(files) is list and bool(files), "CONTEXT_FILES_MISSING")
        roles, paths = set(), set()
        for f in files:
            require(type(f) is dict, "FILE_INVALID")
            rel = f.get("path")
            require(isinstance(rel, str) and rel and
                    not Path(rel).is_absolute(), "PATH_INVALID")
            p = (self.root / rel).resolve()
            require(p.is_relative_to(self.root), "PATH_ESCAPE")
            require(rel not in paths, "DUPLICATE_FILE")
            paths.add(rel)
            require(p.is_file(), "CONTEXT_FILE_MISSING")
            require(digest(p.read_bytes()) == f.get("sha256"), "FILE_HASH_MISMATCH")
            roles.add(f.get("role"))
        require({"brief", "policy", "reference", "scene_constraints",
                 "timing"} <= roles, "CONTEXT_ROLE_MISSING")
        scenes = m.get("scenes")
        require(type(scenes) is list and bool(scenes), "SCENES_MISSING")
        ids = set()
        for s in scenes:
            require(type(s) is dict and isinstance(s.get("id"), str) and
                    s["id"] and s["id"] not in ids, "SCENE_ID_INVALID")
            ids.add(s["id"])
            for k in ("must_show", "must_not_show"):
                require(type(s.get(k)) is list and len(s[k]) > 0 and
                        all(isinstance(x, str) and x.strip() for x in s[k]),
                        "SCENE_CONSTRAINTS_MISSING")
        # Quote commits to all requested generation inputs, not merely its model.
        require(q.get("request_fingerprint") == fingerprint(
            {k: m[k] for k in ("tenant_id", "job_id", "prompt", "model",
                               "provider", "files", "scenes")}), "QUOTE_STALE")
        return fingerprint(m)

    def lock(self, m):
        fp = self.validate(m)
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT fingerprint FROM jobs WHERE tenant=? AND id=?",
                            (self.tenant, m["job_id"])).fetchone()
            if row:
                require(row[0] == fp, "LOCK_ALREADY_EXISTS_DIFFERENT_INPUT")
                return self.status(m["job_id"])
            c.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?)",
                      (self.tenant, m["job_id"], fp, canonical(m), "LOCKED",
                       None, None))
            self.event(c, m["job_id"], "LOCKED", {"fingerprint": fp})
        return self.status(m["job_id"])

    def status(self, job):
        with self.connect() as c:
            row = c.execute("SELECT fingerprint,state,provider_job,output_hash "
                            "FROM jobs WHERE tenant=? AND id=?",
                            (self.tenant, job)).fetchone()
        require(row is not None, "JOB_NOT_FOUND")
        return dict(zip(("fingerprint", "state", "provider_job", "output_hash"), row))

    def submit(self, m, *, fault=None):
        """Reserve durably BEFORE invoking existing fake. Never auto-retry uncertainty."""
        require(fault in (None, "timeout_after_accept", "poll_timeout", "corrupt",
                          "cost_mismatch"), "FAULT_INVALID")
        fp = self.validate(m)
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT fingerprint,state FROM jobs WHERE tenant=? AND id=?",
                            (self.tenant, m["job_id"])).fetchone()
            require(row is not None, "LOCK_MISSING")
            require(row[0] == fp, "LOCK_INPUT_MISMATCH")
            require(row[1] == "LOCKED", "DUPLICATE_OR_UNCERTAIN_SUBMIT")
            c.execute("UPDATE jobs SET state='SUBMITTING' WHERE tenant=? AND id=?",
                      (self.tenant, m["job_id"]))
            self.event(c, m["job_id"], "SUBMITTING", {"fingerprint": fp})
        # An interruption from here leaves a durable reservation. No automatic reset.
        adapter = self.fake_class(
            never_terminal=fault == "poll_timeout",
            corrupt=fault == "corrupt", payload=b"MOCK-NOT-A-MEDIA-ASSET",
            clock=self.clock)
        spec = self.spec_class(
            kind="image", model=m["model"], prompt=m["prompt"],
            project_id=self.tenant,
            refs=tuple(f["sha256"] for f in m["files"] if f["role"] == "reference"))
        try:
            self.validate(m)  # rehash immediately before submit
        except Exception:
            self.transition(m["job_id"], "BLOCKED_AFTER_RESERVATION", {})
            raise
        try:
            job = adapter.submit(spec)
            if fault == "timeout_after_accept":
                raise TimeoutError("simulated lost submit response")
        except Exception:
            self.transition(m["job_id"], "SUBMIT_UNKNOWN", {})
            return self.status(m["job_id"])
        self.transition(m["job_id"], "SUBMITTED", {"job": job.to_dict()})
        return self.reconcile(m, job, adapter, fault=fault)

    def transition(self, job_id, state, detail, output_hash=None):
        # Internal laboratory helper, not an exposed authorization endpoint.
        with self.connect() as c:
            c.execute("UPDATE jobs SET state=?,provider_job=COALESCE(?,provider_job),"
                      "output_hash=COALESCE(?,output_hash) WHERE tenant=? AND id=?",
                      (state, canonical(detail["job"]) if "job" in detail else None,
                       output_hash, self.tenant, job_id))
            self.event(c, job_id, state, detail)

    def reconcile(self, m, job, adapter, *, fault=None):
        # Bounded polling only. A timeout is not permission to resubmit.
        for _ in range(3):
            job = adapter.poll(job)
            if job.state.terminal:
                break
        if not job.state.terminal:
            self.transition(m["job_id"], "RECONCILE_REQUIRED", {"job": job.to_dict()})
            return self.status(m["job_id"])
        self.transition(m["job_id"], "PROVIDER_TERMINAL", {"job": job.to_dict()})
        if job.state.value != "SUCCEEDED":
            self.transition(m["job_id"], "PROVIDER_FAILED", {"job": job.to_dict()})
            return self.status(m["job_id"])
        # Existing FakeAdapter reports a synthetic 4.0 fixture; NEVER a price forecast.
        actual = int(job.cost_credits) + (1 if fault == "cost_mismatch" else 0)
        if actual != m["quote"]["amount"]:
            self.transition(m["job_id"], "COST_MISMATCH", {"synthetic_actual": actual})
            return self.status(m["job_id"])
        asset = adapter.fetch(job)
        with adapter.open_stream(asset) as stream:
            data = stream.read()
        output_hash = digest(data)
        if output_hash != asset.declared_sha256:
            self.transition(m["job_id"], "INTEGRITY_FAILED", {})
        else:
            # This is intentionally never READY_FOR_HUMAN_GATE or APPROVED.
            self.transition(m["job_id"], "MOCK_TECHNICAL_PASS",
                            {"visual_qa": "NOT_VERIFIED", "media": False},
                            output_hash=output_hash)
        return self.status(m["job_id"])


def fixture(root, now):
    root = Path(root)
    files = []
    for role in ("brief", "policy", "reference", "scene_constraints", "timing"):
        p = root / (role + ".txt")
        p.write_text("SYNTHETIC TEST ONLY: " + role, encoding="utf-8")
        files.append({"path": p.name, "role": role, "sha256": digest(p.read_bytes())})
    m = dict(mode="MOCK_ONLY", tenant_id="DEMO_ONLY", job_id="mock_001",
             core_sha=CORE_SHA, tenant_sha="a" * 40, policy_id="MOCK_POLICY_V1",
             provider="fake", model="fake_model_v1", prompt="Synthetic test",
             mock_authorization=True, expires_at=now + 600, budget_units=4,
             files=files, scenes=[dict(id="S1", must_show=["subject chooses"],
                                     must_not_show=["screen facing viewer"])])
    m["quote"] = dict(unit="SYNTHETIC_TEST_UNIT", amount=4, provider="fake",
                      model="fake_model_v1", expires_at=now + 300,
                      request_fingerprint=fingerprint({k: m[k] for k in
                          ("tenant_id", "job_id", "prompt", "model", "provider",
                           "files", "scenes")}))
    return m


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--core-root", required=True)
    p.add_argument("command", choices=("demo", "selftest"))
    args = p.parse_args()
    fake, spec = load_core(args.core_root)
    if args.command == "selftest":
        import unittest
        import test_control
        test_control.CORE = (fake, spec)
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromModule(test_control))
        return 0 if result.wasSuccessful() else 1
    with tempfile.TemporaryDirectory(prefix="creative-os-mock-") as td:
        m = fixture(td, time.time())
        c = Control(Path(td) / "journal.db", td, "DEMO_ONLY", fake, spec)
        c.lock(m)
        print(json.dumps({"mode": "MOCK_ONLY", "result": c.submit(m),
                          "production": "NOT_ENABLED"}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Blocked, OSError, subprocess.CalledProcessError) as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        sys.exit(2)
