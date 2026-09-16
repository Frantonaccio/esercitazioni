"""P2 FINAL PRODUCTION — batch runner with ONE preventive runtime lock per coherent batch (E058, E062, E067).

usage: python3 hf_batch.py <spec.json> lock|quote|go|qa
  lock   MEMORY PRE-FLIGHT, then logs/<batch>_RUNTIME_LOCK.json (core/tenant SHA + clean/dirty, policy, rules, script,
         spec, every reference/start image hash, final prompts, provider/model/params, must_show/must_not_show)
  quote  fingerprint must equal the lock; print cost per job and total
  go     fingerprint checked before every submit; 1 attempt per job, 0 retry, never overwrites; RUN_INVALIDATED if it changes
  qa     merge qa/<batch>_QA.json into logs/<batch>_PRODUCTION_TRACE.json
The manifest proves the inputs actually used; it does not promise bit-identical generative output.
"""
import concurrent.futures as cf
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

RUN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PILOT = os.path.dirname(os.path.dirname(RUN))
WORK = os.path.dirname(PILOT)
TENANT = os.path.join(WORK, "VF_REPO_WORKSPACE", "vf-tenant")
CORE = os.path.join(WORK, "VF_REPO_WORKSPACE", "creative-os")
LAB = os.path.join(os.path.dirname(os.path.abspath(__file__)))  # gate01_lab accanto allo script
RULES = ["CLAUDE.md", "TENANT_CONFIG.json", "LEARNINGS/CREATIVE_SYNAPSE.md", "LEARNINGS/HUMAN_GATE_EVENTS.jsonl",
         "BENCHMARKS/AD02_B_SUCCESS.json", "BENCHMARKS/P2_RISERVATEZZA_NEGATIVE.json", "CAST/CANONICAL_OWNER.json",
         "CAST/P2_CONSULTANT.json", "CONCEPTS/P2_PRIMA_SI_PARLA_V2/SCENE_CONSTRAINTS.json",
         "CONCEPTS/P2_PRIMA_SI_PARLA_V2/VO_CANDIDATE_P2_V4_SHORT.txt", "RUNTIME/PREVENTIVE_RUNTIME_MANIFEST_TEMPLATE.json",
         "RUNTIME/CHECKPOINT_STATUS_INDEX.json"]
LOCK_IO = threading.Lock()


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def sha_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout.strip()


def repo_state(repo):
    d = git(repo, "status", "--porcelain", "--untracked-files=all").splitlines()
    return {"path": repo, "sha": git(repo, "rev-parse", "HEAD"), "branch": git(repo, "branch", "--show-current"),
            "working_tree": "DIRTY" if d else "CLEAN", "dirty_files": d}


def resolve(ref):
    if ref.startswith("PILOT:"):
        return os.path.join(PILOT, ref[6:])
    if ref.startswith("RUN:"):
        return os.path.join(RUN, ref[4:])
    raise ValueError(ref)


class Batch:
    def __init__(self, spec_path):
        self.spec_path = os.path.abspath(spec_path)
        self.spec = json.load(open(self.spec_path, encoding="utf-8"))
        self.name = self.spec["batch"]
        self.lock_path = os.path.join(RUN, "logs", f"{self.name}_RUNTIME_LOCK.json")
        self.trace_path = os.path.join(RUN, "logs", f"{self.name}_PRODUCTION_TRACE.json")

    def prompt(self, job):
        return " ".join(self.spec["prompt_blocks"][b] for b in job.get("prefix_blocks", [])) + (" " if job.get("prefix_blocks") else "") + \
            job["prompt"] + "".join(" " + self.spec["prompt_blocks"][b] for b in job.get("suffix_blocks", []))

    def media(self, job):
        out = []
        for r in job.get("references", []):
            out.append(("--image-references", r, resolve(self.spec["anchors"][r])))
        if job.get("start_image"):
            out.append(("--start-image", "START", resolve(job["start_image"])))
        return out

    def args(self, job):
        a = ["--prompt", self.prompt(job)]
        for k, v in job["params"].items():
            a += [f"--{k}", str(v).lower() if isinstance(v, bool) else str(v)]
        for flag, _, path in self.media(job):
            a += [flag, path]
        return a

    def fingerprint(self):
        t, c = repo_state(TENANT), repo_state(CORE)
        media = {}
        for j in self.spec["jobs"]:
            for _, rid, path in self.media(j):
                media[f"{j['asset']}:{rid}"] = sha_file(path) if os.path.exists(path) else "MISSING"
        parts = {"tenant": [t["sha"], t["dirty_files"]], "core": [c["sha"], c["dirty_files"]],
                 "rules": {r: sha_file(os.path.join(TENANT, r)) for r in RULES},
                 "scripts": {f: sha_file(os.path.join(RUN, "scripts", f)) for f in ("hf_batch.py", "preflight.py")},
                 "spec": sha_file(self.spec_path), "media": media}
        return sha_text(json.dumps(parts, sort_keys=True)), parts

    def lock(self):
        r = subprocess.run([sys.executable, os.path.join(RUN, "scripts", "preflight.py"), "--pillar", "P2_RISERVATEZZA",
                            "--prompts", self.spec_path])
        if r.returncode != 0:
            sys.exit("PRE-FLIGHT BLOCK — no lock, no quote, no generation")
        fp, parts = self.fingerprint()
        missing = [k for k, v in parts["media"].items() if v == "MISSING"]
        if missing:
            sys.exit(f"BLOCK — media missing: {missing}")
        index = json.load(open(os.path.join(TENANT, "RUNTIME/CHECKPOINT_STATUS_INDEX.json"), encoding="utf-8"))
        state = lambda rel: sorted({e["state"] for e in index["entries"] if e["path"].split("#")[0] == rel}) or ["UNINDEXED"]
        cfg = json.load(open(os.path.join(TENANT, "TENANT_CONFIG.json"), encoding="utf-8"))
        pol = cfg["boot_paths"]["ACTIVE_POLICY"]
        tenant = repo_state(TENANT)
        tenant["pushed"] = git(TENANT, "rev-parse", f"origin/{tenant['branch']}") == tenant["sha"]
        core = repo_state(CORE)
        core.update(role_in_run="nessuno per la generazione", not_active_candidates=[{"ref": "7ea87fd265090a4f82977fd4745ef659378d319e", "status": "RULE_NOT_ACTIVE"}])
        client = subprocess.run(["higgsfield", "--version"], capture_output=True, text=True).stdout.strip()
        jobs = []
        for j in self.spec["jobs"]:
            p = self.prompt(j)
            jobs.append({"asset": j["asset"], "beat": j["beat"], "kind": j["kind"], "provider": "higgsfield", "provider_client": client,
                         "model": j["model"], "params": j["params"],
                         "media": [{"role": flag.strip("-"), "id": rid, "path": os.path.relpath(path, PILOT), "sha256_sent": sha_file(path),
                                    "local_transformations": [], "provider_side_processing": "NOT_VERIFIABLE"} for flag, rid, path in self.media(j)],
                         "prompt_final": p, "prompt_sha256": sha_text(p), "must_show": j["must_show"], "must_not_show": j["must_not_show"],
                         "edit_use": j.get("edit_use")})
        lock = {"schema": "VF_PREVENTIVE_RUNTIME_MANIFEST_v0.1", "lock_id": f"{self.spec['run_id']}_{self.name}_LOCK_{time.strftime('%Y%m%dT%H%M%S')}",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "runtime_mode": "EXPERIMENTAL_FROM_EXACT_COMMIT",
                "authority": self.spec["authority"],
                "scope_note": "Il manifest dimostra gli input realmente usati. NON promette riproducibilità bit-identical dell'output generativo.",
                "core": core, "tenant": tenant,
                "policy": {"id": cfg["active_policy_id"], "path": pol, "sha256": sha_file(os.path.join(TENANT, pol)), "modified": False},
                "rules_loaded": [{"path": r, "sha256": parts["rules"][r], "state": state(r)} for r in RULES],
                "scripts": [{"path": f"scripts/{f}", "sha256": s} for f, s in parts["scripts"].items()],
                "spec": {"path": os.path.relpath(self.spec_path, RUN), "sha256": parts["spec"]},
                "preflight": {"path": "logs/PREFLIGHT.json", "sha256": sha_file(os.path.join(RUN, "logs", "PREFLIGHT.json"))},
                "fingerprint_sha256": fp, "jobs": jobs}
        json.dump(lock, open(self.lock_path, "w"), indent=1, ensure_ascii=False)
        print(f"LOCK {lock['lock_id']} · fingerprint {fp[:16]}")
        print(f"  tenant {tenant['sha']} {tenant['working_tree']} {tenant['dirty_files']} pushed={tenant['pushed']}")
        print(f"  core   {core['sha']} {core['working_tree']} · policy {lock['policy']['id']} {lock['policy']['sha256'][:12]}")
        for j in jobs:
            print(f"  {j['asset']:22} {j['model']} {j['params']} media " + ", ".join(f"{m['id']}={m['sha256_sent'][:10]}" for m in j["media"]))

    def require(self):
        if not os.path.exists(self.lock_path):
            sys.exit("NO LOCK — run lock first")
        lock = json.load(open(self.lock_path, encoding="utf-8"))
        fp, _ = self.fingerprint()
        if fp != lock["fingerprint_sha256"]:
            json.dump({"run_verdict": "RUN_INVALIDATED", "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "lock": lock["fingerprint_sha256"], "now": fp},
                      open(os.path.join(RUN, "logs", f"{self.name}_RUN_INVALIDATED_{time.strftime('%H%M%S')}.json"), "w"), indent=1)
            sys.exit("RUN_INVALIDATED — working tree changed after the lock: regenerate the lock")
        return lock

    def quote(self):
        lock = self.require()
        total = 0.0
        for j in self.spec["jobs"]:
            r = subprocess.run(["higgsfield", "generate", "cost", j["model"]] + self.args(j), capture_output=True, text=True)
            m = re.search(r"([\d.]+)\s*credits", r.stdout)
            c = float(m.group(1)) if m else None
            total += c or 0
            print(f"{j['asset']:22} {j['model']} {j['params'].get('duration', '')}  {c} credits" + ("" if m else f"  !! {(r.stdout + r.stderr).strip()[:300]}"))
        bal = subprocess.run(["higgsfield", "account", "status"], capture_output=True, text=True).stdout
        b = re.search(r"([\d.]+)\s*credits", bal)
        b = float(b.group(1)) if b else None
        print(f"LOCK HELD {lock['fingerprint_sha256'][:16]} · TOTALE {total} · saldo {b} · previsto {None if b is None else round(b - total, 2)}")

    def run_job(self, j, lock):
        rec = next(dict(x) for x in lock["jobs"] if x["asset"] == j["asset"])
        with LOCK_IO:
            fp, _ = self.fingerprint()
        rec["fingerprint_at_submit"] = fp
        if fp != lock["fingerprint_sha256"]:
            rec["run_status"] = "RUN_INVALIDATED"
            return rec
        ext = "png" if j["kind"] == "image" else "mp4"
        dest = os.path.join(RUN, "stills" if j["kind"] == "image" else "clips", f"{j['asset']}.{ext}")
        if os.path.exists(dest):
            rec["run_status"] = "EXISTS_NOT_OVERWRITTEN"
            return rec
        t0 = time.time()
        r = subprocess.run(["higgsfield", "generate", "create", j["model"]] + self.args(j) + ["--wait", "--wait-timeout", "40m", "--json"],
                           capture_output=True, text=True)
        open(os.path.join(RUN, "logs", f"{j['asset']}.stdout.json"), "w").write(r.stdout)
        open(os.path.join(RUN, "logs", f"{j['asset']}.stderr.txt"), "w").write(r.stderr)
        rec.update(attempt=1, rc=r.returncode, seconds=round(time.time() - t0, 1))
        try:
            job = json.loads(r.stdout)
            job = job[0] if isinstance(job, list) else job
            rec["job_id"], url = job.get("id"), job.get("result_url")
        except Exception:
            url = None
        if r.returncode != 0 or not url:
            rec["run_status"] = "CLIENT_FAILED_CHECK_SERVER"
            return rec
        urllib.request.urlretrieve(url, dest)
        rec.update(run_status="GENERATED", source_url=url,
                   output={"path": os.path.relpath(dest, RUN), "sha256": sha_file(dest), "bytes": os.path.getsize(dest)}, qa=[])
        return rec

    def go(self):
        lock = self.require()
        bal = lambda: (lambda m: float(m.group(1)) if m else None)(re.search(r"([\d.]+)\s*credits", subprocess.run(["higgsfield", "account", "status"], capture_output=True, text=True).stdout))
        b0 = bal()
        with cf.ThreadPoolExecutor(max_workers=self.spec.get("parallel", 4)) as ex:
            recs = list(ex.map(lambda j: self.run_job(j, lock), self.spec["jobs"]))
        b1 = bal()
        fp_after, _ = self.fingerprint()
        held = fp_after == lock["fingerprint_sha256"] and all(x["run_status"] != "RUN_INVALIDATED" for x in recs)
        trace = {k: v for k, v in lock.items() if k != "jobs"}
        trace.update(trace_created_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"), lock_sha256=sha_file(self.lock_path), retries=0, jobs=recs,
                     balance={"before": b0, "after": b1, "spent": None if None in (b0, b1) else round(b0 - b1, 2)},
                     fingerprint_after_run=fp_after, run_verdict="LOCK_HELD" if held else "RUN_INVALIDATED")
        json.dump(trace, open(self.trace_path, "w"), indent=1, ensure_ascii=False)
        for x in recs:
            print(f"{x['asset']:22} {x['run_status']} job={x.get('job_id')} {x.get('seconds')}s {x.get('output', {}).get('sha256', '')[:16]}")
        print(f"balance {b0} -> {b1} · {trace['run_verdict']}")

    def lab(self):
        """MOCK_ONLY (INTEGRATION GATE 01). Nessuna rete, nessun credito, nessuna credenziale.
        Esercita lock -> reservation -> submit -> reconcile sui contratti GIA' nel Core."""
        lock = self.require()                       # stesso fingerprint dei verbi reali
        sys.path.insert(0, LAB)
        import gate01_lab as L
        core = L.load_core(CORE)
        snap_dir = os.path.join(RUN, "logs", f"{self.name}_LAB_SNAPSHOTS")
        store = L.DurableJobStore(os.path.join(RUN, "logs", f"{self.name}_LAB.db"), core)
        cap = int(self.spec.get("lab_budget_units", 1000))
        out = []
        for j in self.spec["jobs"]:
            refs = [L.snapshot(p, snap_dir) for _, _, p in self.media(j)]
            fp_now, _ = self.fingerprint()
            if fp_now != lock["fingerprint_sha256"]:
                out.append({"asset": j["asset"], "state": "BLOCKED_INPUT_DRIFT"})
                continue
            out.append({"asset": j["asset"], **L.run_mock_job(
                core, store, job_id=f"{self.name}:{j['asset']}", model="fake_model_v1",
                prompt=self.prompt(j), refs=[(s, d) for s, d in refs],
                units=1, budget_cap=cap, snap_dir=snap_dir)})
        trace = {"mode": "MOCK_ONLY", "control_version": L.CONTROL_VERSION,
                 "core_sha": core["sha"], "lock_fingerprint": lock["fingerprint_sha256"],
                 "jobs": out, "production": "NOT_ENABLED", "visual_qa": "NOT_VERIFIED"}
        json.dump(trace, open(os.path.join(RUN, "logs", f"{self.name}_LAB.json"), "w"),
                  indent=1, ensure_ascii=False)
        for o in out:
            print(f"{o['asset']:22} {o['state']} {o.get('job_id','')}")

    def qa(self):
        trace = json.load(open(self.trace_path, encoding="utf-8"))
        qa_path = os.path.join(RUN, "qa", f"{self.name}_QA.json")
        qa = json.load(open(qa_path, encoding="utf-8"))
        for j in trace["jobs"]:
            j["qa"] = qa["assets"].get(j["asset"], {}).get("checks", [])
        trace["qa_source"] = {"path": os.path.relpath(qa_path, RUN), "sha256": sha_file(qa_path)}
        json.dump(trace, open(self.trace_path, "w"), indent=1, ensure_ascii=False)
        print("QA merged into", self.trace_path)


if __name__ == "__main__":
    b = Batch(sys.argv[1])
    verb = sys.argv[2]
    if verb not in ("lock", "quote", "go", "qa", "lab"):
        sys.exit(f"verbo sconosciuto: {verb}")
    getattr(b, verb)()
