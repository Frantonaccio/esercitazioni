"""MEMORY PRE-FLIGHT (E057) — must pass before any generation. Exit 1 = BLOCK.

Checks and prints: learning layer files + SHA, tenant git HEAD and dirty state, canonical cast files with reference
hash verification, positive benchmark, pillar negative learning, last REJECT events of the pillar, last Human Gate
decision, pillar-relevant principles, and that the run's prompts only reference canonical (not forbidden) assets.

usage: python3 preflight.py --pillar P2_RISERVATEZZA [--prompts ../stills_prompts.json]
env:   VF_TENANT (default: ../../../../VF_REPO_WORKSPACE/vf-tenant) · VF_PILOT_OUTPUTS (default: ../../..)
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

RUN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PILOT = os.environ.get("VF_PILOT_OUTPUTS") or os.path.dirname(os.path.dirname(RUN))
TENANT = os.environ.get("VF_TENANT") or os.path.join(os.path.dirname(PILOT), "VF_REPO_WORKSPACE", "vf-tenant")


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pillar", required=True)
    ap.add_argument("--prompts", default=os.path.join(RUN, "stills_prompts.json"))
    args = ap.parse_args()
    report, blocks = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "pillar": args.pillar, "tenant": TENANT}, []

    files = {"CLAUDE.md": "CLAUDE.md", "CREATIVE_SYNAPSE": "LEARNINGS/CREATIVE_SYNAPSE.md",
             "HUMAN_GATE_EVENTS": "LEARNINGS/HUMAN_GATE_EVENTS.jsonl", "POSITIVE_BENCHMARK": "BENCHMARKS/AD02_B_SUCCESS.json",
             "PILLAR_NEGATIVE": f"BENCHMARKS/{args.pillar}_NEGATIVE.json", "CANONICAL_OWNER": "CAST/CANONICAL_OWNER.json",
             "TENANT_CONFIG": "TENANT_CONFIG.json"}
    loaded = {}
    for k, rel in files.items():
        p = os.path.join(TENANT, rel)
        if os.path.exists(p):
            loaded[k] = {"path": rel, "sha256": sha(p)}
        else:
            loaded[k] = {"path": rel, "missing": True}
            blocks.append(f"missing {rel}")
    report["files"] = loaded
    head = subprocess.run(["git", "-C", TENANT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", TENANT, "status", "--short"], capture_output=True, text=True).stdout.strip().splitlines()
    report["tenant_git"] = {"head": head, "uncommitted_changes": dirty}

    cfg = json.load(open(os.path.join(TENANT, "TENANT_CONFIG.json"), encoding="utf-8"))
    pol = os.path.join(TENANT, cfg["boot_paths"]["ACTIVE_POLICY"])
    report["active_policy"] = {"id": cfg["active_policy_id"], "sha256": sha(pol) if os.path.exists(pol) else None}

    cast = {}
    forbidden_paths = set()
    for cf in ("CANONICAL_OWNER.json", "P2_CONSULTANT.json"):
        p = os.path.join(TENANT, "CAST", cf)
        if not os.path.exists(p):
            if cf == "CANONICAL_OWNER.json":
                blocks.append("missing CAST/CANONICAL_OWNER.json")
            continue
        c = json.load(open(p, encoding="utf-8"))
        refs = []
        for r in c["identity_references"]:
            ap_ = os.path.join(PILOT, r["path"])
            ok = os.path.exists(ap_) and sha(ap_) == r["sha256"]
            refs.append({"id": r["id"], "rank": r["rank"], "hash_ok": ok})
            if not ok:
                blocks.append(f"{c['cast_id']}: reference {r['id']} missing or hash mismatch")
        for f in c.get("forbidden_references", []):
            forbidden_paths.add(os.path.normpath(os.path.join(PILOT, f["path"])))
        cast[c["cast_id"]] = {"status": c["status"], "descriptor": c["descriptor"], "references": refs}
    report["cast"] = cast

    events = [json.loads(l) for l in open(os.path.join(TENANT, files["HUMAN_GATE_EVENTS"]), encoding="utf-8")]
    hg = [e for e in events if e.get("source_type") == "HUMAN_GATE" or (e.get("decision") and "source_type" not in e)]
    report["last_human_gate_decision"] = {k: hg[-1].get(k) for k in ("event_id", "asset", "decision", "reason")} if hg else None
    rej = [e for e in events if e.get("pillar") == args.pillar and e.get("decision") in ("REJECT", "SUPERSEDED", "PATCH")]
    report["last_pillar_rejects"] = [{k: e.get(k) for k in ("event_id", "asset", "decision")} for e in rej[-6:]]

    syn = open(os.path.join(TENANT, files["CREATIVE_SYNAPSE"]), encoding="utf-8").read()
    want = {"P2_RISERVATEZZA": ["S01", "S02", "S07", "S12", "S17", "S19", "S20", "S21", "S22"]}.get(args.pillar, ["S01", "S02", "S07", "S12"])
    rules = {}
    for sid in want:
        m = re.search(rf"\|\s*\*\*{sid}\*\*\s*\|\s*(.+?)\s*\|", syn)
        rules[sid] = re.sub(r"\*\*", "", m.group(1))[:220] if m else "MISSING"
        if not m:
            blocks.append(f"principle {sid} missing in synapse")
    report["pillar_rules"] = rules

    if os.path.exists(args.prompts):
        spec = json.load(open(args.prompts, encoding="utf-8"))
        bad = []
        for k, raw in spec.get("identity_anchor", {}).items():
            if isinstance(raw, str) and raw.startswith("PILOT:"):
                ap_ = os.path.normpath(os.path.join(PILOT, raw[6:]))
                if ap_ in forbidden_paths:
                    bad.append(k)
                if not os.path.exists(ap_):
                    blocks.append(f"prompt anchor {k} missing on disk")
        if bad:
            blocks.append(f"prompts reference forbidden assets: {bad}")
        report["prompts_checked"] = os.path.relpath(args.prompts, RUN)

    report["verdict"] = "BLOCK" if blocks else "PASS"
    report["blocks"] = blocks
    os.makedirs(os.path.join(RUN, "logs"), exist_ok=True)
    json.dump(report, open(os.path.join(RUN, "logs", "PREFLIGHT.json"), "w"), indent=1, ensure_ascii=False)

    print("=" * 78)
    print(f"MEMORY PRE-FLIGHT · {args.pillar} · {report['verdict']}")
    print(f"tenant git HEAD {head} · uncommitted: {len(dirty)} · policy {report['active_policy']['id']} {str(report['active_policy']['sha256'])[:12]}")
    for k, v in loaded.items():
        print(f"  {k:20} {v['path']:45} {'MISSING' if v.get('missing') else v['sha256'][:16]}")
    for cid, c in cast.items():
        print(f"  CAST {cid} [{c['status']}] refs: " + ", ".join(f"{r['id']}={'OK' if r['hash_ok'] else 'FAIL'}" for r in c["references"]))
    lh = report["last_human_gate_decision"]
    print(f"  last Human Gate: {lh['event_id']} {lh['decision']} · {lh['asset']}" if lh else "  last Human Gate: none")
    print("  last pillar rejects: " + ", ".join(f"{e['event_id']} {e['decision']}" for e in report["last_pillar_rejects"]))
    for sid, r in rules.items():
        print(f"  {sid}: {r[:110]}")
    for b in blocks:
        print(f"  BLOCK: {b}")
    print("=" * 78)
    sys.exit(1 if blocks else 0)


if __name__ == "__main__":
    main()
