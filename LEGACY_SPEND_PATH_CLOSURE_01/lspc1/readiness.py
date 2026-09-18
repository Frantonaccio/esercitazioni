"""READINESS — due domande diverse, due oggetti diversi.

    A. TEST SUITE RESULT      i test hanno prodotto l'esito atteso?
    B. REQUIREMENT READINESS  il requisito e' davvero chiuso?

Confonderle e' il modo piu' rapido di dichiarare pronto un sistema che non lo e'.
Un PASS puo' dimostrare che un requisito resta POLICY_DECISION_REQUIRED (nessun
valore deciso) o REAL_PROVIDER_REQUIRED (nessun provider reale coinvolto): in
entrambi i casi l'esito della suite e' corretto E il requisito resta aperto.

`all_requirements_verified` e' FALSE finche' esiste anche un solo requisito
aperto nella roadmap complessiva. Non e' una formula prudente: e' l'unica vera.
"""
from __future__ import annotations

import subprocess

# Requisiti che questa fase CHIUDE, se e solo se i passi corrispondenti sono PASS.
CLOSES = {
    # E13 e' entrato con la Human Review 01: senza la controprova dell'autorizzazione
    # fabbricata, `CORE_PRIMITIVES` non si puo' dichiarare chiuso — era esattamente il
    # blocker. E14 (threat model) e' il suo complemento: dire cosa il confine NON
    # protegge fa parte del chiuderlo. E15 e' entrato con la Human Review 02: un
    # attempt che conia due autorizzazioni e' un secondo dispatch, e nessuna delle
    # controprove precedenti lo copriva.
    "LEGACY_SPEND_PATHS_CORE_PRIMITIVES": ("E02", "E03", "E04", "E06", "E13", "E14", "E15"),
    "LEGACY_TESTS_MIGRATION_TO_GOVERNED": ("E05", "E07", "E08"),
}

# Requisiti che questa fase NON tocca, e che devono restare esattamente cosi'.
UNTOUCHED = {
    "RECONCILIATION_FRESHNESS_NG04_POLICY": "POLICY_DECISION_REQUIRED",
    "ORPHAN_RESERVED_LEASE_POLICY": "POLICY_DECISION_REQUIRED",
    "REAL_AUTHORIZATION_AND_PRICING": "REAL_PROVIDER_REQUIRED",
    "REAL_PROVIDER_RECONCILIATION": "REAL_PROVIDER_REQUIRED",
    "RUN_CONTAMINATION": "NOT_RUN",
    "G_N02_SEMANTIC_CLAIM_PARAPHRASE": "STILL_OPEN",
    "RV07_SCHEDULER_RECOVERY_RESIDUAL": "STILL_OPEN",
    "INDEPENDENT_CI_STATUS_CHECKS": "NOT_RUN",
}

# Scoperto in questa fase, fuori dal perimetro autorizzato: dichiarato, non corretto.
DISCOVERED = {
    "SNAPSHOT_SEAL_WRITE_RACE": "STILL_OPEN",
}


def _git(*args, cwd: str) -> str:
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True).stdout.strip()


def build(results: list[dict], *, core_path: str, repo: str) -> dict:
    by_id = {r["id"]: r for r in results}
    passed = {k for k, v in by_id.items() if v["pass"]}
    total = len(results)

    requirements = dict(UNTOUCHED)
    requirements.update(DISCOVERED)
    closed, still_open = [], []
    for req, steps in CLOSES.items():
        if all(s in passed for s in steps):
            requirements[req] = "CLOSED_LAB_VERIFIED"
            closed.append(req)
        else:
            missing = [s for s in steps if s not in passed]
            requirements[req] = f"STILL_OPEN (passi non superati: {', '.join(missing)})"
            still_open.append(req)

    open_reqs = sorted(k for k, v in requirements.items() if v != "CLOSED_LAB_VERIFIED")
    all_pass = len(passed) == total

    phase_state = ("LEGACY_SPEND_PATHS_CLOSED — READY_FOR_HUMAN_REVIEW"
                   if all_pass and not still_open
                   else "LEGACY_SPEND_PATHS_NOT_CLOSED — WORK_INCOMPLETE")

    return {
        "schema": "legacy-spend-path-closure-readiness/1",
        "phase_state": phase_state,
        "phase_state_meaning": (
            "Stato MASSIMO consentito dal mandato quando entrambi i gap sono chiusi. "
            "Non significa provider ready, production ready, NG-04 decisa, orphan lease "
            "decisa, provider reale verificato, credenziali autorizzate, spend autorizzato, "
            "merge autorizzato, R2 autorizzato. Serve Human Review separata."),

        # ---------------------------------------------------------- A
        "test_suite_result": {
            "question": "i test hanno prodotto l'esito atteso?",
            "total": total, "pass": len(passed), "fail": total - len(passed),
            "fail_ids": sorted(set(by_id) - passed),
            "answer": "SI" if all_pass else "NO",
        },

        # ---------------------------------------------------------- B
        "requirement_readiness": {
            "question": "il requisito e' davvero chiuso?",
            "requirements": requirements,
            "closed_by_this_phase": sorted(closed),
            "open": open_reqs,
            "all_requirements_verified": False,
            "all_requirements_verified_reason": (
                "Esistono requisiti aperti nella roadmap complessiva (policy non decise, "
                "provider reale non coinvolto, contaminazione e CI indipendente non eseguite, "
                "piu' un difetto preesistente scoperto in questa fase). Un PASS di suite non "
                "li chiude, e dichiararlo sarebbe falso."),
        },

        "explicitly_not_claimed": {
            "provider_ready": False, "production_ready": False,
            "ng04_policy_decided": False, "orphan_lease_policy_decided": False,
            "real_provider_verified": False, "credentials_authorized": False,
            "spend_authorized": False, "merge_authorized": False, "r2_authorized": False,
            "human_merge_authorization": False,
        },

        "evidence_chain": {
            "canonical_base": {
                "core_main": "9cf9cee1a751f7a2ad6c768574ff5aa38d8db515",
                "runtime_main": "fea7b439a63a0100a732e21af4dfde6b8edd0951"},
            "code_sha": {"core": _git("rev-parse", "HEAD", cwd=core_path),
                         "runtime": _git("rev-parse", "HEAD", cwd=repo)},
            "real_branch": {"core": _git("rev-parse", "--abbrev-ref", "HEAD", cwd=core_path),
                            "runtime": _git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo)},
            "evidence_head_sha": ("assegnato dal commit che pubblica questo bundle; distinto da "
                                  "code_sha per costruzione"),
        },

        "spend_accounting": {"credits_spent": 0, "real_providers_called": 0,
                             "generative_network_calls": 0, "credentials_read": 0},
    }
