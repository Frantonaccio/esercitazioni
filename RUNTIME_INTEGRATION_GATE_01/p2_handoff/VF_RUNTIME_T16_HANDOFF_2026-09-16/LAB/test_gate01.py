"""INTEGRATION GATE 01 — suite di accettazione del laboratorio MOCK_ONLY.

Non esegue produzione, non chiama provider reali, non legge credenziali.
Richiede il Core: se manca, questo file ESCE NON-ZERO con messaggio esplicito.
Nessun falso verde (e' la correzione 14A applicata anche a se stessi).
"""
import json
import multiprocessing
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gate01_lab as L

CORE_ROOT = os.environ.get("GATE01_CORE")
CORE = None


def read_state_in_new_process(db, job_id, q):
    """Interprete nuovo: nessun oggetto vivo, nessuna chat. Solo il journal."""
    with sqlite3.connect(db) as c:
        q.put(c.execute("SELECT state FROM jobs WHERE job_id=?", (job_id,)).fetchone()[0])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.snap = self.root / "snapshots"
        self.db = self.root / "journal.db"
        self.store = L.DurableJobStore(self.db, CORE)

    def ref(self, name="reference.bin", content=b"AUTHORIZED-BYTES"):
        p = self.root / name
        p.write_bytes(content)
        sha, dest = L.snapshot(p, self.snap)
        return p, sha, dest

    def run_job(self, job_id="job1", prompt="synthetic", refs=None, units=4,
                cap=100, fault=None):
        return L.run_mock_job(CORE, self.store, job_id=job_id, model="fake_model_v1",
                              prompt=prompt, refs=refs if refs is not None else [],
                              units=units, budget_cap=cap, snap_dir=self.snap, fault=fault)


# ---------------------------------------------------------------- item 4
class StateMachine(Base):
    def test_A_submit_without_reservation(self):
        with self.assertRaisesRegex(L.Blocked, "JOB_NOT_FOUND"):
            self.store.transition("ghost", "SUBMITTED")

    def test_B_terminal_to_running(self):
        self.store.reserve("j", "sk", 1, 100)
        self.store.transition("j", "SUBMITTED")
        self.store.transition("j", "SUCCEEDED")
        with self.assertRaisesRegex(L.IllegalTransition, "SUCCEEDED->RUNNING"):
            self.store.transition("j", "RUNNING")

    def test_C_failed_to_succeeded(self):
        self.store.reserve("j", "sk", 1, 100)
        self.store.transition("j", "SUBMITTED")
        self.store.transition("j", "FAILED")
        with self.assertRaisesRegex(L.IllegalTransition, "FAILED->SUCCEEDED"):
            self.store.transition("j", "SUCCEEDED")

    def test_D_second_submit_same_active_spec(self):
        r1 = self.run_job(job_id="a")
        r2 = L.run_mock_job(CORE, self.store, job_id="b", model="fake_model_v1",
                            prompt="synthetic", refs=[], units=4, budget_cap=100,
                            snap_dir=self.snap)
        self.assertEqual(r1["spec_key"], r2["spec_key"])
        # il primo e' terminale: non c'e' un job "vivo" da riusare, ma il journal
        # mantiene entrambi distinti e nessuno riapre il primo
        self.assertIn(r1["state"], L.TERMINAL)

    def test_D2_reservation_is_not_repeatable(self):
        self.store.reserve("j", "sk", 1, 100)
        with self.assertRaisesRegex(L.Blocked, "JOB_ALREADY_RESERVED"):
            self.store.reserve("j", "sk", 1, 100)

    def test_E_timeout_never_blind_retry(self):
        r = self.run_job(job_id="t", fault="poll_timeout")
        self.assertNotIn(r["state"], ("SUCCEEDED",))
        # stesso spec ancora vivo -> nessun secondo submit
        r2 = self.run_job(job_id="t2", fault=None)
        self.assertTrue(r2.get("idempotent"), f"secondo submit non bloccato: {r2}")

    def test_illegal_transition_table_is_explicit(self):
        self.assertEqual(L.TRANSITIONS["SUCCEEDED"], set())
        self.assertIn(L.RESERVED, L.TRANSITIONS[None])


# ---------------------------------------------------------------- item 5 + 6
class Idempotency(Base):
    def test_sequential_double_submit(self):
        self.run_job(job_id="x", fault="poll_timeout")       # resta vivo
        r2 = self.run_job(job_id="y")
        self.assertTrue(r2["idempotent"])

    def test_concurrent_double_submit_one_provider_call(self):
        calls = []
        real = CORE["FakeAdapter"].submit

        def counting(self_, spec):
            calls.append(spec.spec_key)
            return real(self_, spec)

        with patch.object(CORE["FakeAdapter"], "submit", counting):
            def go(i):
                try:
                    return self.run_job(job_id=f"c{i}", fault="poll_timeout")["state"]
                except L.Blocked as e:
                    return str(e)
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(go, range(2)))
        self.assertEqual(len(calls), 1, f"submit multipli: {calls}")

    def test_crash_after_reservation(self):
        self.store.reserve("j", "sk", 4, 100)
        fresh = L.DurableJobStore(self.db, CORE)          # processo/istanza nuova
        self.assertEqual(fresh.state_of("j"), L.RESERVED)
        self.assertEqual(fresh.find_live_by_spec("sk"), "j")

    def test_crash_after_submit(self):
        self.store.reserve("j", "sk", 4, 100)
        self.store.transition("j", "SUBMITTED")
        fresh = L.DurableJobStore(self.db, CORE)
        self.assertEqual(fresh.state_of("j"), "SUBMITTED")
        self.assertEqual(fresh.find_live_by_spec("sk"), "j")

    def test_lost_response_persists_uncertainty(self):
        r = self.run_job(job_id="u", fault="lost_response")
        self.assertEqual(r["state"], L.SUBMIT_UNKNOWN)
        fresh = L.DurableJobStore(self.db, CORE)
        self.assertEqual(fresh.state_of("u"), L.SUBMIT_UNKNOWN)
        self.assertIsNotNone(fresh.find_live_by_spec(r["spec_key"]))

    def test_reconcile_after_restart_is_authorized_only(self):
        self.run_job(job_id="u", fault="lost_response")
        fresh = L.DurableJobStore(self.db, CORE)
        fresh.transition("u", "SUCCEEDED", {"reconciled": True})   # transizione lecita
        with self.assertRaises(L.IllegalTransition):
            fresh.transition("u", "RUNNING")

    def test_fresh_process_reads_durable_state(self):
        self.run_job(job_id="p", fault="lost_response")
        ctx = multiprocessing.get_context("spawn")
        q = ctx.Queue()
        pr = ctx.Process(target=read_state_in_new_process, args=(str(self.db), "p", q))
        pr.start(); pr.join(20)
        if pr.is_alive():
            pr.terminate(); pr.join(); self.fail("processo figlio non ha risposto")
        self.assertEqual(pr.exitcode, 0)
        self.assertEqual(q.get(timeout=5), L.SUBMIT_UNKNOWN)
        q.close()


# ---------------------------------------------------------------- item 8
class ByteSnapshot(Base):
    def test_submitted_bytes_are_the_authorized_ones(self):
        p, sha, dest = self.ref()
        p.write_bytes(b"TAMPERED-AFTER-LOCK")           # il path cambia dopo il lock
        self.assertTrue(L.source_drifted(p, sha))
        r = self.run_job(job_id="s", refs=[(sha, dest)])
        sent = L.snapshot_bytes(dest, sha)
        self.assertEqual(sent, b"AUTHORIZED-BYTES")
        self.assertIn(r["state"], ("SUCCEEDED",))

    def test_corrupted_snapshot_is_blocked(self):
        p, sha, dest = self.ref()
        Path(dest).write_bytes(b"CORRUPTED")
        with self.assertRaisesRegex(L.Blocked, "SNAPSHOT_CORRUPTED"):
            L.snapshot_bytes(dest, sha)


# ---------------------------------------------------------------- item 9
class BudgetConcurrency(Base):
    def test_cumulative_reservation_refuses_second(self):
        self.store.reserve("A", "ska", 70, 100)
        with self.assertRaisesRegex(L.Blocked, "OVER_BUDGET_CUMULATIVE"):
            self.store.reserve("B", "skb", 50, 100)

    def test_concurrent_reservations_only_one_wins(self):
        def go(i):
            try:
                s = L.DurableJobStore(self.db, CORE)
                s.reserve(f"J{i}", f"sk{i}", 70 if i == 0 else 50, 100)
                return "OK"
            except L.Blocked as e:
                return str(e)
        with ThreadPoolExecutor(max_workers=2) as pool:
            res = list(pool.map(go, range(2)))
        self.assertEqual(res.count("OK"), 1, f"prenotazioni concorrenti: {res}")


# ---------------------------------------------------------------- item 10
class PolicyGate(Base):
    def setUp(self):
        super().setUp()
        self.tenant = Path(CORE_ROOT) / "examples" / "tenant_demo"
        self.policies = str(self.tenant / "policies")

    def gate(self, case):
        return L.policy_gate(CORE, str(case), "DEMO_V1", self.policies)

    def test_authorized_claim_passes(self):
        r = self.gate(self.tenant / "golden" / "demo_001_pass.json")
        self.assertEqual(r["verdict"], "PASS")

    def test_literal_unauthorized_claim_rejected(self):
        r = self.gate(self.tenant / "golden" / "demo_002_reject.json")
        self.assertEqual(r["verdict"], "REJECT")
        self.assertIn("FORBIDDEN_CLAIM:GARANZIE_DEMO", r["codes"])

    def mutate(self, extra_text, name):
        """Aggiunge una riga VO SENZA rimuovere i marker di pillar/angolo.

        La prima versione di questo test sostituiva la riga che conteneva il marker
        dell'angolo: il REJECT che ne usciva era ANGLE_NOT_SUPPORTED, non il claim.
        Un rifiuto per il motivo sbagliato non prova nulla.
        """
        case = json.loads((self.tenant / "golden" / "demo_001_pass.json").read_text())
        case["id"] = name
        anchor = case["script"]["vo"][-1]["anchor_shot"]
        case["script"]["vo"].append({"id": 99, "text": extra_text, "anchor_shot": anchor})
        p = self.root / f"{name}.json"
        p.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        return self.gate(p)

    def test_control_mutation_keeps_markers(self):
        """Controprova: la sola mutazione neutra non deve far cadere il caso."""
        r = self.mutate("Il quadro elettrico e stato revisionato a settembre.", "neutral")
        self.assertEqual(r["verdict"], "PASS", f"mutazione non neutra: {r}")

    def test_literal_forbidden_claim_still_blocks(self):
        r = self.mutate("Le garantiamo la continuita totale.", "literal")
        self.assertEqual(r["verdict"], "REJECT")
        self.assertIn("FORBIDDEN_CLAIM:GARANZIE_DEMO", r["codes"])

    def test_near_synonym_is_only_a_warning(self):
        """'garanzia' e' negli assertion_patterns: WARNING, non BLOCKER."""
        r = self.mutate("La garanzia di continuita e parte del servizio.", "near")
        self.assertEqual(r["verdict"], "PASS")
        self.assertIn("UNREGISTERED_ASSERTION:GUARANTEE", r["codes"])
        self.assertEqual(r["blockers"], [])

    def test_true_paraphrase_is_not_detected_GAP(self):
        """GAP dichiarato: una promessa equivalente, senza i pattern, non produce nulla."""
        r = self.mutate("Con noi il servizio non si interrompe mai, in nessun caso.",
                        "paraphrase")
        self.assertEqual(r["verdict"], "PASS")
        self.assertEqual(r["blockers"], [])
        self.assertEqual([c for c in r["codes"] if "CLAIM" in c or "ASSERTION" in c], [],
                         "se qui comparisse un finding, il gap sarebbe chiuso")
        Path(os.environ.get("GATE01_EVIDENCE", self.root)).joinpath(
            "GAP_POLICY_SEMANTIC_PARAPHRASE.json").write_text(
            json.dumps({"gap": "GAP_POLICY_SEMANTIC_PARAPHRASE",
                        "case": "promessa equivalente senza pattern noti",
                        "result": r}, indent=1, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- item 11
class TimingSource(Base):
    def test_single_canonical_source(self):
        canon = self.root / "text_layers.json"
        canon.write_text('{"cues":[{"i":4,"start":9.76,"end":11.91}]}', encoding="utf-8")
        derived = self.root / "narrativa.md"
        derived.write_text("| cue 4 | 9,46 | 11,46 |", encoding="utf-8")
        fp1 = L.timing_fingerprint(canon, [derived])
        derived.write_text("| cue 4 | 0,00 | 99,99 |", encoding="utf-8")
        self.assertEqual(L.timing_fingerprint(canon, [derived]), fp1,
                         "una copia narrativa non deve influenzare il runtime")
        canon.write_text('{"cues":[{"i":4,"start":9.99,"end":11.91}]}', encoding="utf-8")
        self.assertNotEqual(L.timing_fingerprint(canon, [derived]), fp1)


# ---------------------------------------------------------------- item 12
class QaBinding(Base):
    def test_qa_invalid_when_export_replaced(self):
        a, b = "a" * 64, "b" * 64
        L.qa_record(self.store, "j", a, [{"constraint": "X", "result": "PASS"}])
        self.assertEqual(L.qa_valid_for(self.store, "j", a), (True, "VALID"))
        ok, why = L.qa_valid_for(self.store, "j", b)      # stesso filename, byte diversi
        self.assertFalse(ok)
        self.assertEqual(why, "INVALID_ASSET_CHANGED")


# ---------------------------------------------------------------- item 13
class HumanGateSchema(Base):
    def record(self, **over):
        r = dict(decision_id="D1", reviewer_id="francesco", scope="VISUAL_REVIEW",
                 job_id="j", asset_sha256="c" * 64, control_version=L.CONTROL_VERSION,
                 timestamp="2026-09-16T10:00:00+02:00", decision="PASS")
        r.update(over)
        return r

    def test_complete_record_is_structural_only(self):
        r = L.human_gate_validate(self.record())
        self.assertEqual(r["binding"], "STRUCTURAL_BINDING_ONLY")
        self.assertFalse(r["authenticated"])

    def test_missing_field_invalid(self):
        for k in L.HUMAN_GATE_REQUIRED:
            with self.assertRaisesRegex(L.Blocked, "HUMAN_GATE_RECORD_INVALID"):
                L.human_gate_validate(self.record(**{k: ""}))


# ---------------------------------------------------------------- item 7
class MockOnly(Base):
    def test_no_real_provider_tokens_in_lab(self):
        src = Path(L.__file__).read_text(encoding="utf-8")
        for token in ("higgsfield", "api_key", "credentials", "urlopen", "requests"):
            self.assertNotIn(token, src.lower(), f"token vietato nel laboratorio: {token}")

    def test_provider_is_fake(self):
        r = self.run_job(job_id="mo")
        self.assertEqual(r.get("production"), "NOT_ENABLED")
        self.assertEqual(r.get("visual_qa"), "NOT_VERIFIED")


def main():
    global CORE
    if not CORE_ROOT:
        print("GATE01_CORE non impostata: questi test richiedono il Core reale.\n"
              "Uso:  GATE01_CORE=/percorso/creative-os python3 test_gate01.py",
              file=sys.stderr)
        return 2
    CORE = L.load_core(CORE_ROOT)
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
