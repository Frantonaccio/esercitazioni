"""Acceptance tests of the local MOCK guard; no real generation or visual QA."""
import copy
import json
import multiprocessing
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from control import Blocked, Control, fixture, fingerprint

CORE = None


def read_in_new_process(db, queue):
    # Brand-new interpreter reads the durable journal, not a conversation or object.
    with sqlite3.connect(db) as c:
        queue.put(c.execute("SELECT state FROM jobs").fetchone()[0])


class Acceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 1000.0
        self.m = fixture(self.root, self.now)
        self.fake, self.spec = CORE
        self.c = self.controller()

    def controller(self):
        return Control(self.root / "journal.db", self.root, "DEMO_ONLY",
                       self.fake, self.spec, clock=lambda: self.now)

    def lock(self):
        self.c.lock(self.m)

    def refused_before_provider(self, code):
        with patch.object(self.fake, "submit") as submit:
            with self.assertRaisesRegex(Blocked, code):
                self.c.submit(self.m)
            submit.assert_not_called()

    def test_valid_mock_never_claims_visual_approval(self):
        self.lock()
        r = self.c.submit(self.m)
        self.assertEqual(r["state"], "MOCK_TECHNICAL_PASS")
        self.assertEqual(len(r["output_hash"]), 64)
        with self.c.connect() as db:
            d = json.loads(db.execute("SELECT detail FROM events ORDER BY sequence DESC").
                           fetchone()[0])
        self.assertEqual(d["visual_qa"], "NOT_VERIFIED")
        self.assertFalse(d["media"])

    def test_missing_lock(self):
        self.refused_before_provider("LOCK_MISSING")

    def test_budget_missing(self):
        self.lock()
        del self.m["budget_units"]
        self.refused_before_provider("BUDGET_MISSING")

    def test_budget_boolean_rejected(self):
        self.m["budget_units"] = True
        self.refused_before_provider("BUDGET_MISSING")

    def test_budget_negative_rejected(self):
        self.m["budget_units"] = -1
        self.refused_before_provider("BUDGET_MISSING")

    def test_over_budget(self):
        self.m["budget_units"] = 0
        self.refused_before_provider("OVER_BUDGET")

    def test_reference_changed(self):
        self.lock()
        (self.root / "reference.txt").write_text("different", encoding="utf-8")
        self.refused_before_provider("FILE_HASH_MISMATCH")

    def test_missing_file(self):
        (self.root / "policy.txt").unlink()
        self.refused_before_provider("CONTEXT_FILE_MISSING")

    def test_timing_changed(self):
        self.lock()
        (self.root / "timing.txt").write_text("wrong cue", encoding="utf-8")
        self.refused_before_provider("FILE_HASH_MISMATCH")

    def test_expired_lock(self):
        self.lock()
        self.now = 1700
        self.refused_before_provider("LOCK_EXPIRED")

    def test_expired_quote(self):
        self.lock()
        self.now = 1350
        self.refused_before_provider("QUOTE_EXPIRED")

    def test_wrong_tenant(self):
        self.m["tenant_id"] = "OTHER"
        self.refused_before_provider("TENANT_MISMATCH")

    def test_wrong_core(self):
        self.m["core_sha"] = "b" * 40
        self.refused_before_provider("CORE_VERSION_NOT_TESTED")

    def test_real_provider_denied(self):
        self.m["provider"] = "real"
        self.refused_before_provider("REAL_PROVIDER_DISABLED")

    def test_real_mode_denied(self):
        self.m["mode"] = "PRODUCTION"
        self.refused_before_provider("REAL_PROVIDER_DISABLED")

    def test_unapproved_brief(self):
        self.m["mock_authorization"] = False
        self.refused_before_provider("AUTHORIZATION_MISSING")

    def test_unknown_policy(self):
        self.m["policy_id"] = "NEW_POLICY"
        self.refused_before_provider("POLICY_NOT_ALLOWED")

    def test_missing_scene_constraint(self):
        self.m["scenes"][0]["must_show"] = []
        self.refused_before_provider("SCENE_CONSTRAINTS_MISSING")

    def test_duplicate_scene(self):
        self.m["scenes"].append(copy.deepcopy(self.m["scenes"][0]))
        self.refused_before_provider("SCENE_ID_INVALID")

    def test_path_escape(self):
        self.m["files"][0]["path"] = "../outside"
        self.refused_before_provider("PATH_ESCAPE")

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as other:
            out = Path(other) / "secret"
            out.write_text("secret", encoding="utf-8")
            link = self.root / "escape"
            link.symlink_to(out)
            self.m["files"][0]["path"] = "escape"
            self.refused_before_provider("PATH_ESCAPE")

    def test_changed_prompt_invalidates_quote(self):
        self.lock()
        self.m["prompt"] = "a different request"
        self.refused_before_provider("QUOTE_STALE")

    def test_changed_manifest_even_with_refreshed_quote(self):
        self.lock()
        self.m["prompt"] = "different"
        self.m["quote"]["request_fingerprint"] = fingerprint({
            k: self.m[k] for k in ("tenant_id", "job_id", "prompt", "model",
                                   "provider", "files", "scenes")})
        self.refused_before_provider("LOCK_INPUT_MISMATCH")

    def test_idempotent_lock(self):
        self.lock()
        self.lock()
        with self.c.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)

    def test_cannot_overwrite_lock(self):
        self.lock()
        self.m["budget_units"] += 1
        with self.assertRaisesRegex(Blocked, "LOCK_ALREADY_EXISTS"):
            self.lock()

    def test_duplicate_submit(self):
        self.lock()
        self.c.submit(self.m)
        self.refused_before_provider("DUPLICATE_OR_UNCERTAIN_SUBMIT")

    def test_concurrent_submit_only_one_provider_call(self):
        self.lock()
        original = self.fake.submit
        with patch.object(self.fake, "submit", autospec=True,
                          side_effect=original) as submit:
            def run(_):
                try:
                    return self.controller().submit(self.m)["state"]
                except Blocked as e:
                    return str(e)
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(run, range(2)))
            self.assertEqual(submit.call_count, 1)
            self.assertIn("MOCK_TECHNICAL_PASS", results)
            self.assertIn("DUPLICATE_OR_UNCERTAIN_SUBMIT", results)

    def test_lost_submit_response_never_retries(self):
        self.lock()
        r = self.c.submit(self.m, fault="timeout_after_accept")
        self.assertEqual(r["state"], "SUBMIT_UNKNOWN")
        self.c = self.controller()
        self.refused_before_provider("DUPLICATE_OR_UNCERTAIN_SUBMIT")

    def test_poll_timeout_never_retries(self):
        self.lock()
        r = self.c.submit(self.m, fault="poll_timeout")
        self.assertEqual(r["state"], "RECONCILE_REQUIRED")
        self.refused_before_provider("DUPLICATE_OR_UNCERTAIN_SUBMIT")

    def test_corrupt_output(self):
        self.lock()
        r = self.c.submit(self.m, fault="corrupt")
        self.assertEqual(r["state"], "INTEGRITY_FAILED")
        self.assertIsNone(r["output_hash"])

    def test_cost_mismatch(self):
        self.lock()
        r = self.c.submit(self.m, fault="cost_mismatch")
        self.assertEqual(r["state"], "COST_MISMATCH")

    def test_fresh_process_reads_durable_state(self):
        self.lock()
        self.c.submit(self.m, fault="timeout_after_accept")
        ctx = multiprocessing.get_context("spawn")
        q = ctx.Queue()
        p = ctx.Process(target=read_in_new_process, args=(self.c.db, q))
        p.start()
        p.join(10)
        if p.is_alive():
            p.terminate()
            p.join()
            self.fail("child failed to return")
        self.assertEqual(p.exitcode, 0)
        self.assertEqual(q.get(timeout=2), "SUBMIT_UNKNOWN")
        q.close()

    def test_context_not_reconstructed_from_chat(self):
        self.lock()
        reconstructed = json.loads(json.dumps(self.m))
        other = self.controller()
        self.assertEqual(other.submit(reconstructed)["state"], "MOCK_TECHNICAL_PASS")

    def test_second_validation_stops_drift_before_submit(self):
        self.lock()
        original = self.c.validate
        count = 0
        def validate(m):
            nonlocal count
            count += 1
            if count == 2:
                (self.root / "reference.txt").write_text("late drift", encoding="utf-8")
            return original(m)
        with patch.object(self.c, "validate", side_effect=validate):
            self.refused_before_provider("FILE_HASH_MISMATCH")
        self.assertEqual(self.c.status(self.m["job_id"])["state"],
                         "BLOCKED_AFTER_RESERVATION")
