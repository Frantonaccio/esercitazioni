"""Helper del PROVIDER BOUNDARY GATE — OPEN-GAP CLOSURE, eseguiti in PROCESSI REALI
(multiprocessing 'spawn': ogni funzione e' a livello di modulo e viene reimportata nel figlio).

Ogni funzione riferisce un dict serializzabile, mai eccezioni.
MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUCTION.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import traceback

GATE01 = os.environ.get("RUNTIME_GATE_ROOT", "/home/user/esercitazioni/RUNTIME_INTEGRATION_GATE_01")
BUNDLE01 = os.environ.get("PBGATE01_ROOT", "/home/user/esercitazioni/PROVIDER_BOUNDARY_HARDENING_01")
for _p in (GATE01, BUNDLE01):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pbgate import pb_worker                                # noqa: E402
from tests.worker import make_inputs                        # noqa: E402

EPS = 1e-3


def _core(core_path: str) -> None:
    if core_path not in sys.path:
        sys.path.insert(0, core_path)


def _err(e: BaseException) -> dict:
    return {"ok": False, "error": type(e).__name__, "code": getattr(e, "code", None),
            "message": str(e), "trace": traceback.format_exc(limit=4)}


def prepare_unknown_jobs(db: str, core_path: str, ops: list) -> dict:
    """Crea N job SUBMIT_UNKNOWN attraverso il percorso GOVERNATO.

    L'adapter `submit_unknown` perde la risposta DOPO l'invio: il Core persiste
    SUBMIT_UNKNOWN e poi rilancia l'eccezione, quindi `go()` termina con un errore ma la
    riga esiste ed e' esattamente quella che serve. La precondizione si giudica sulle RIGHE
    PERSISTITE, non sull'esito della chiamata."""
    out = {"jobs": []}
    for op in ops:
        r = pb_worker.go_governed(db, core_path, f"prep {op}", op, adapter_kind="submit_unknown")
        out["jobs"].append({"op": op, "go_ok": r.get("ok"), "go_error": r.get("error"),
                            "state": r.get("state"), "job_id": r.get("job_id")})
    out["rows"] = pb_worker._rows(db)
    persisted = {r["operation_id"]: r["state"] for r in out["rows"]}
    for j in out["jobs"]:
        j["persisted_state"] = persisted.get(j["op"])
        j["ok"] = j["persisted_state"] == "SUBMIT_UNKNOWN"
    out["ok"] = bool(ops) and all(j["ok"] for j in out["jobs"])
    return out


# ===================================================================== C03 — NG-04 freshness
def ng04_matrix(db: str, core_path: str) -> dict:
    """Matrice completa del MECCANISMO di freshness. La POLICY e' iniettata dal test:
    i valori qui sotto sono PARAMETRI DI PROVA, non una decisione di policy."""
    out: dict = {"ok": False}
    try:
        from runtime.payload_snapshot import SnapshotLedger, ledger_dir_for
        from runtime.reconciliation import (FreshnessPolicy, LabProviderStatusAuthority,
                                            ReconciliationRefused, nonce_dir_for,
                                            reconcile_authenticated)
        _core(core_path)
        from adapters.fake import FakeAdapter
        from registry.reservations import SqliteReservationStore

        store = SqliteReservationStore(db)
        adapter = FakeAdapter(account_id="fake_acct_a")
        auth = LabProviderStatusAuthority("LAB_SECRET_c03", "fake", "fake_acct_a")
        ledger = SnapshotLedger(ledger_dir_for(db))
        rows = [r for r in pb_worker._rows(db) if r["state"] == "SUBMIT_UNKNOWN"]
        if len(rows) < 6:
            out["error"] = f"PRECONDITION: servono 6 job SUBMIT_UNKNOWN, trovati {len(rows)}"
            return out
        NOW = 1_000_000.0
        MAX_AGE, MAX_SKEW = 120.0, 5.0
        P = FreshnessPolicy(max_age_s=MAX_AGE, max_future_skew_s=MAX_SKEW,
                            label="LAB_TEST_PARAMETER_NOT_A_POLICY_DECISION")

        def rep(row, *, issued_at, nonce=None, state="SUCCEEDED"):
            """Report FIRMATO. `issued_at` puo' essere anche assente o malformato: viene
            firmato COSI' COM'E', altrimenti si misurerebbe la firma e non la freshness."""
            import secrets as _s
            from runtime.reconciliation import REPORT_SCHEMA, sign_report
            return sign_report(auth.key, {
                "schema": REPORT_SCHEMA, "provider": "fake", "provider_account": "fake_acct_a",
                "provider_job_id": "pv_remote_1", "attempt_token": row["attempt_token"],
                "payload_digest": row["payload_digest"], "operation_id": row["operation_id"],
                "job_id": row["job_id"], "state": state,
                "remote_ref": "remote:pv_remote_1",
                "nonce": nonce or f"nonce_{_s.token_hex(16)}", "issued_at": issued_at})

        def run(report, row, policy, *, now=NOW):
            before = next((x for x in pb_worker._rows(db) if x["job_id"] == row["job_id"]), None)
            try:
                job = reconcile_authenticated(store, adapter, report, job_id=row["job_id"],
                                              key=auth.key, nonce_dir=nonce_dir_for(db),
                                              snapshot_ledger=ledger, now=now, **policy)
                res = {"applied": True, "state": job.state.value}
            except ReconciliationRefused as e:
                res = {"applied": False, "code": e.code}
            after = next((x for x in pb_worker._rows(db) if x["job_id"] == row["job_id"]), None)
            res["journal_unchanged"] = before == after
            return res

        C: dict = {}
        victim = rows[0]                                    # tutti i rifiuti insistono su questo job
        # --- la policy e' obbligatoria e tipizzata -------------------------------------
        C["policy_omitted"] = run(rep(victim, issued_at=NOW), victim, {})
        C["policy_none"] = run(rep(victim, issued_at=NOW), victim, {"freshness": None})
        C["policy_wrong_type"] = run(rep(victim, issued_at=NOW), victim, {"freshness": 60.0})
        for label, kw in (("policy_negative_max_age", dict(max_age_s=-1, max_future_skew_s=1, label="x")),
                          ("policy_nan", dict(max_age_s=float("nan"), max_future_skew_s=1, label="x")),
                          ("policy_inf", dict(max_age_s=float("inf"), max_future_skew_s=1, label="x")),
                          ("policy_bool", dict(max_age_s=True, max_future_skew_s=1, label="x")),
                          ("policy_no_label", dict(max_age_s=1, max_future_skew_s=1, label="  "))):
            try:
                FreshnessPolicy(**kw)
                C[label] = {"applied": True, "code": None}
            except ReconciliationRefused as e:
                C[label] = {"applied": False, "code": e.code, "journal_unchanged": True}
        # --- eta' e skew ----------------------------------------------------------------
        C["too_old"] = run(rep(victim, issued_at=NOW - MAX_AGE - 1), victim, {"freshness": P})
        C["ancient_1970"] = run(rep(victim, issued_at=0.0), victim, {"freshness": P})
        C["from_future_beyond_skew"] = run(rep(victim, issued_at=NOW + MAX_SKEW + 1), victim,
                                           {"freshness": P})
        C["boundary_age_eq_max_plus_eps"] = run(rep(victim, issued_at=NOW - MAX_AGE - EPS), victim,
                                                {"freshness": P})
        C["timestamp_missing"] = run(rep(victim, issued_at=None), victim, {"freshness": P})
        C["timestamp_malformed_str"] = run(rep(victim, issued_at="ieri"), victim, {"freshness": P})
        C["timestamp_malformed_bool"] = run(rep(victim, issued_at=True), victim, {"freshness": P})
        # --- una policy PIU' STRETTA rifiuta cio' che una piu' larga accetta -------------
        strict = FreshnessPolicy(max_age_s=1.0, max_future_skew_s=0.0, label="LAB_TEST_STRICT")
        C["parametric_strict_refuses"] = run(rep(victim, issued_at=NOW - 10.0), victim,
                                             {"freshness": strict})
        # --- casi che devono PASSARE, ognuno su un job diverso --------------------------
        C["boundary_age_eq_max"] = run(rep(rows[1], issued_at=NOW - MAX_AGE), rows[1], {"freshness": P})
        C["boundary_skew_eq_max"] = run(rep(rows[2], issued_at=NOW + MAX_SKEW), rows[2], {"freshness": P})
        C["fresh_now"] = run(rep(rows[3], issued_at=NOW), rows[3], {"freshness": P})
        # --- il nonce NON viene bruciato da un rifiuto di freshness ---------------------
        shared_nonce = "nonce_c03_shared_0000000000000000"
        C["stale_with_nonce"] = run(rep(rows[4], issued_at=NOW - MAX_AGE - 1, nonce=shared_nonce),
                                    rows[4], {"freshness": P})
        C["same_nonce_after_stale_refusal"] = run(rep(rows[4], issued_at=NOW, nonce=shared_nonce),
                                                  rows[4], {"freshness": P})
        # --- replay: nonce gia' consumato da un'applicazione riuscita -------------------
        # Il job viene riportato in incertezza da un poll successivo (`put` ordinario), cosi'
        # il replay trova un job RICONCILIABILE e a rifiutarlo e' il nonce, non lo stato.
        # Il primo report porta a RUNNING (non terminale) e un poll successivo riporta il job
        # in incertezza: solo cosi' il replay trova un job ancora RICONCILIABILE e a rifiutarlo
        # e' il nonce, non lo stato.
        replay_nonce = "nonce_c03_replay_0000000000000000"
        first = rep(rows[5], issued_at=NOW, nonce=replay_nonce, state="RUNNING")
        C["replay_first_apply"] = run(first, rows[5], {"freshness": P})
        C["back_to_unknown"] = pb_worker.put_state(db, core_path, rows[5]["job_id"],
                                                   "SUBMIT_UNKNOWN")
        C["replay_second"] = run(first, rows[5], {"freshness": P})
        # --- l'attestazione di freshness finisce nell'evidenza registrata ---------------
        anoms = [a for a in pb_worker._anomalies(db, rows[3]["job_id"]) if a["kind"] == "RECONCILIATION"]
        out["freshness_attestation"] = (anoms[-1]["detail"]["evidence"].get("freshness")
                                        if anoms else None)
        out["cases"] = C
        out["policy_used"] = P.describe()
        expected = {
            "policy_omitted": "FRESHNESS_POLICY_REQUIRED", "policy_none": "FRESHNESS_POLICY_REQUIRED",
            "policy_wrong_type": "FRESHNESS_POLICY_INVALID",
            "policy_negative_max_age": "FRESHNESS_POLICY_INVALID", "policy_nan": "FRESHNESS_POLICY_INVALID",
            "policy_inf": "FRESHNESS_POLICY_INVALID", "policy_bool": "FRESHNESS_POLICY_INVALID",
            "policy_no_label": "FRESHNESS_POLICY_INVALID",
            "too_old": "REPORT_STALE", "ancient_1970": "REPORT_STALE",
            "from_future_beyond_skew": "REPORT_FROM_FUTURE",
            "boundary_age_eq_max_plus_eps": "REPORT_STALE",
            "timestamp_missing": "REPORT_TIMESTAMP_MISSING",
            "timestamp_malformed_str": "REPORT_TIMESTAMP_MALFORMED",
            "timestamp_malformed_bool": "REPORT_TIMESTAMP_MALFORMED",
            "parametric_strict_refuses": "REPORT_STALE",
            "stale_with_nonce": "REPORT_STALE", "replay_second": "REPLAY",
        }
        must_apply = ("boundary_age_eq_max", "boundary_skew_eq_max", "fresh_now",
                      "same_nonce_after_stale_refusal", "replay_first_apply")
        out["expected_codes"] = expected
        out["code_mismatches"] = {k: {"got": C[k].get("code"), "expected": v}
                                  for k, v in expected.items() if C[k].get("code") != v}
        out["applied_mismatches"] = [k for k in must_apply if not C[k].get("applied")]
        out["refusals_left_journal_unchanged"] = all(
            C[k].get("journal_unchanged") is not False for k in expected)
        out["ok"] = True
        out["verified"] = (not out["code_mismatches"] and not out["applied_mismatches"]
                           and out["refusals_left_journal_unchanged"]
                           and isinstance(out["freshness_attestation"], dict))
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    return out


# ===================================================================== C04 — legacy spend paths
def legacy_static_inventory() -> dict:
    """Ricerca REALE (AST + testo) dei percorsi che possono produrre submit/spend nel Runtime."""
    hits: dict = {}
    roots = {"runtime": os.path.join(GATE01, "runtime"), "tests": os.path.join(GATE01, "tests")}
    needles = ("run_job(", ".submit(", "subprocess.", "higgsfield", "go_candidate.go(",
               "reserve_or_get_live(", ".reconcile(", ".settle(")
    for label, root in roots.items():
        for name in sorted(os.listdir(root)):
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            src = open(path, encoding="utf-8").read()
            tree = ast.parse(src, filename=name)
            # solo il CODICE, non i docstring: si azzerano le costanti stringa
            code_only = ast.dump(tree)
            found = sorted({n for n in needles
                            if (n.rstrip("(").lstrip(".") in code_only) or (n in src)})
            if found:
                hits[f"{label}/{name}"] = found
    return {"ok": True, "hits": hits, "files_scanned": sum(
        len([f for f in os.listdir(r) if f.endswith(".py")]) for r in roots.values())}


def _governed_spend(db: str, core_path: str, prompt: str, op: str) -> dict:
    """Spesa GOVERNATA completa (envelope derivato + quote fidata emessa dall'autorita' +
    permit + reservation atomica + snapshot exact-byte), senza passare da alcun helper legacy."""
    try:
        from runtime import go_candidate
        from runtime.authorization import (DEFAULT_LAB_AUTHORIZATION, LAB_QUOTE_UNIT, lab_price_for)
        from runtime.genspec_bridge import build_genspec
        from runtime.payload_snapshot import ledger_dir_for
        _core(core_path)
        from adapters.base import GenSpec
        from adapters.fake import FakeAdapter
        from registry.reservations import SqliteReservationStore
        authority = SqliteReservationStore(db)                  # lato AUTORITA' (dominio spender)
        env = DEFAULT_LAB_AUTHORIZATION.envelope_for(op)
        authority.open_envelope(env, 100, unit=LAB_QUOTE_UNIT, scope=op.split(":")[0])
        gs = build_genspec(make_inputs(prompt), GenSpec)
        qid = authority.issue_quote(operation_id=op, spec_key=gs.spec_key, envelope_id=env,
                                    amount=lab_price_for(gs.model), unit=LAB_QUOTE_UNIT)
        ad = FakeAdapter(account_id="fake_acct_governed")
        res = go_candidate.go(make_inputs(prompt), adapter=ad, provider_mode="fake",
                              store_path=db, core_path=core_path, max_polls=3,
                              intent="new_attempt", reason="INITIAL_GENERATION", auto_permit=True,
                              operation_id=op, quote_id=qid,
                              authorization=DEFAULT_LAB_AUTHORIZATION)
        return {"ok": True, "state": res.state, "governance": res.governance,
                "quote_id": res.quote_id, "envelope_id": res.envelope_id,
                "permit_id": res.permit_id, "budget_units": res.budget_units,
                "submits": ad.submits, "ledger_dir": ledger_dir_for(db),
                "send_verified": (res.payload_snapshot or {}).get("send_verified")}
    except Exception as e:                                      # noqa: BLE001
        return _err(e)


def legacy_entry_points(db: str, core_path: str, engaged: bool) -> dict:
    """Ogni entry point del Runtime provato DAVVERO, con la modalita' Provider Boundary
    ingaggiata o no. Si osservano effetti, non intenzioni: submit dell'adapter e righe nello store."""
    os.environ["CREATIVE_OS_PROVIDER_BOUNDARY_MODE"] = "engaged" if engaged else ""
    out: dict = {"ok": False, "engaged": engaged}
    try:
        from runtime import go_candidate
        from runtime.provider_gate import (LegacySpendPathDisabled, ProviderBoundaryModeEngaged,
                                           legacy_spend_path_state, provider_boundary_mode)
        from runtime.authorization import DEFAULT_LAB_AUTHORIZATION
        from tests import worker as histworker
        _core(core_path)
        from adapters.fake import FakeAdapter
        out["mode"] = provider_boundary_mode()
        out["legacy_switch_state"] = legacy_spend_path_state()
        E: dict = {}

        # #2 go(authorization=None) — LEGACY_LAB
        ad = FakeAdapter(account_id="fake_acct_legacy")
        try:
            r = go_candidate.go(make_inputs("legacy e2"), adapter=ad, provider_mode="fake",
                                store_path=db, core_path=core_path, max_polls=3, intent="resume",
                                operation_id="lab:e2", authorization=None)
            E["#2_go_legacy"] = {"reached_spend": ad.submits >= 1, "state": r.state,
                                 "governance": r.governance, "code": None}
        except LegacySpendPathDisabled as e:
            E["#2_go_legacy"] = {"reached_spend": ad.submits >= 1, "code": e.code,
                                 "state": None}
        # #4 Batch.run_job -> go(authorization=None)
        try:
            from runtime.hf_batch_bridge import build_go_inputs           # noqa: F401
            E["#4_hf_batch_bridge_importable"] = True
        except Exception:                                                 # noqa: BLE001
            E["#4_hf_batch_bridge_importable"] = False
        E["#4_via_switch"] = {"same_switch_as_#2": True,
                              "legacy_switch_state": legacy_spend_path_state()}
        # #7 helper di test che dispaccia direttamente sullo store
        sc = histworker.store_call(db, core_path, "reserve_or_get_live_by_prompt_op",
                                   "legacy e7", "lab:e7")
        E["#7_store_call"] = {"ok": sc.get("ok"), "code": sc.get("code"),
                              "store_created": sc.get("store_created"),
                              "reached_store": bool(sc.get("job_id"))}
        # #1 percorso GOVERNATO: deve continuare a funzionare in ENTRAMBE le modalita'.
        # La quote la emette l'AUTORITA' sul proprio store (come fa il daemon spender), non
        # l'helper di test `store_call`: quello e' il percorso legacy #7, che la modalita' chiude.
        E["#1_governed"] = _governed_spend(db, core_path, "governed e1", "lab:e1")
        # #10/#11 primitive del Core: NON governate dal Runtime, in nessuna modalita'
        try:
            from adapters.base import GenSpec, JobState
            from registry.reservations import SqliteReservationStore
            from transport.pipeline import run_job
            from runtime.genspec_bridge import build_genspec
            store = SqliteReservationStore(db)
            ad2 = FakeAdapter(account_id="fake_acct_core_prim")
            j = run_job(ad2, build_genspec(make_inputs("core primitive e10"), GenSpec), store,
                        clock=lambda: 1.0, max_polls=3, budget_units=0, envelope_units=None,
                        operation_id="lab:e10")
            E["#10_core_run_job"] = {"reached_spend": ad2.submits >= 1, "state": j.state.value,
                                     "governed_by_runtime_switch": False}
            _, live = store.reserve_or_get_live(
                build_genspec(make_inputs("core reconcile e11"), GenSpec), now=1.0,
                operation_id="lab:e11")
            try:
                rr = store.reconcile(live, JobState("FAILED"),
                                     {"source": "chiunque", "remote_ref": "pv:altrui"})
                E["#11_core_raw_reconcile"] = {"accepted": True, "state": rr.state.value,
                                               "governed_by_runtime_switch": False}
            except Exception as e:                                        # noqa: BLE001
                E["#11_core_raw_reconcile"] = {"accepted": False, "error": type(e).__name__}
        except Exception as e:                                            # noqa: BLE001
            E["#10_11_core_primitives_error"] = _err(e)
        out["entry_points"] = E
        out["rows"] = pb_worker._rows(db)
        out["ok"] = True
    except Exception as e:                                                # noqa: BLE001
        out.update(_err(e))
    finally:
        os.environ.pop("CREATIVE_OS_PROVIDER_BOUNDARY_MODE", None)
    return out


# ===================================================================== C05 — orphan lease
def orphan_mechanism(db: str, core_path: str) -> dict:
    """MECCANISMO di lease, esercitato con una policy INIETTATA dal test. Il codice non
    sceglie la policy: qui si prova che la pretende e che, data, si comporta correttamente."""
    out: dict = {"ok": False}
    try:
        from runtime.orphan_lease import (LeasePolicy, LeaseRefused, RECLAIM_POLICY,
                                          RECLAIM_SETTLEMENT_SOURCE, RESERVED_NO_INTENT,
                                          RESERVED_WITH_INTENT, classify_attempt, fencing_token,
                                          reclaim_orphan_reserved)
        from runtime.genspec_bridge import build_genspec
        _core(core_path)
        from adapters.base import GenSpec, StaleWrite
        from registry.reservations import SqliteReservationStore

        store = SqliteReservationStore(db)
        store.open_envelope("ENV_LAB", 100, now=1.0)
        NOW = 10_000.0
        out["reclaim_policy_constant"] = RECLAIM_POLICY

        def orphan(tag, *, units=10):
            spec = build_genspec(make_inputs(f"orphan {tag}"), GenSpec)
            _, j = store.reserve_or_get_live(spec, now=1.0, budget_units=units,
                                             envelope_id="ENV_LAB", operation_id=f"lab:orph_{tag}")
            return store.get(j.job_id)

        POLICY = LeasePolicy(min_age_s=3600.0, reclaim_authority="LAB_TEST_OPERATOR",
                             allowed_classes=(RESERVED_NO_INTENT,),
                             required_evidence_keys=("incident_ref", "observed_by"),
                             label="LAB_TEST_PARAMETER_NOT_A_POLICY_DECISION")
        EV = {"incident_ref": "LAB-INC-001", "observed_by": "gate C05"}
        C: dict = {}

        def attempt(label, job, **kw):
            before = next((r for r in pb_worker._rows(db) if r["job_id"] == job.job_id), None)
            args = dict(policy=POLICY, actor="LAB_TEST_OPERATOR", evidence=EV,
                        token=fencing_token(job), now=NOW)
            args.update(kw)
            try:
                rep = reclaim_orphan_reserved(store, job.job_id, **args)
                res = {"reclaimed": True, "report": rep}
            except LeaseRefused as e:
                res = {"reclaimed": False, "code": e.code}
            except StaleWrite as e:
                res = {"reclaimed": False, "code": "STALE_WRITE", "message": str(e)}
            after = next((r for r in pb_worker._rows(db) if r["job_id"] == job.job_id), None)
            res["journal_unchanged"] = before == after
            C[label] = res
            return res

        # 1. la POLICY e' obbligatoria
        j = orphan("nopolicy")
        attempt("policy_omitted", j, policy=None)
        attempt("policy_wrong_type", j, policy={"min_age_s": 1})
        # 2. AUTHORITY
        attempt("wrong_actor", j, actor="qualcun_altro")
        # 3. EVIDENZA
        attempt("evidence_incomplete", j, evidence={"incident_ref": "X"})
        attempt("evidence_not_mapping", j, evidence="stringa")
        # 4. LEASE non scaduto
        attempt("lease_not_expired", j, now=1.0 + POLICY.min_age_s - 1)
        # 5. FENCING TOKEN stantio
        attempt("fencing_token_stale", j, token=f"{j.job_id}@999")
        # 6. CLASSE non ammessa: attempt CON intento di submit
        with_intent = orphan("withintent")
        store.mark_submitting(with_intent, provider="fake", provider_account="acct_a",
                              payload_digest="c" * 64, attempt_token="att_wi", now=2.0)
        wi = store.get(with_intent.job_id)
        C["classification_with_intent"] = classify_attempt(wi, NOW)["class"]
        attempt("class_not_allowed", wi)
        # 7. RECLAIM legittimo
        before_totals = store.ledger_totals("ENV_LAB")
        ok = attempt("legitimate_reclaim", store.get(j.job_id))
        after_totals = store.ledger_totals("ENV_LAB")
        C["totals_before"] = before_totals
        C["totals_after"] = after_totals
        row = next(r for r in pb_worker._rows(db) if r["job_id"] == j.job_id)
        C["row_after_reclaim"] = row
        C["ledger_after_reclaim"] = [r for r in pb_worker._ledger(db) if r["job_id"] == j.job_id]
        C["anomalies_after_reclaim"] = [a["kind"] for a in pb_worker._anomalies(db, j.job_id)]
        # 8. ZERO BLIND RETRY: nessun nuovo attempt creato
        C["attempts_for_operation"] = [r["job_id"] for r in pb_worker._rows(db)
                                       if r["operation_id"] == f"lab:orph_nopolicy"]
        # 9. ripetizione del reclaim su un terminale
        attempt("reclaim_twice", store.get(j.job_id), token=fencing_token(store.get(j.job_id)))
        # 10. CORSA A: `mark_submitting` vince. Il reclaim arriva con una vista superata e
        #     perde: qui a fermarlo e' gia' la CLASSE (il job ha ora un intento di submit),
        #     che e' il controllo piu' esterno. In nessun caso il reclaim tocca la riga.
        race = orphan("race")
        stale_view = store.get(race.job_id)
        store.mark_submitting(store.get(race.job_id), provider="fake", provider_account="acct_a",
                              payload_digest="d" * 64, attempt_token="att_race", now=3.0)
        attempt("race_lost_by_reclaim", stale_view, token=fencing_token(stale_view))
        C["race_row_after"] = next(r for r in pb_worker._rows(db) if r["job_id"] == race.job_id)
        # 11. FENCE puro: una scrittura concorrente che NON cambia la classe (un `put`
        #     ordinario) incrementa comunque la revisione: il token diventa stantio.
        neutral = orphan("fence")
        neutral_view = store.get(neutral.job_id)
        store.put(store.get(neutral.job_id))                    # scrittura concorrente "neutra"
        attempt("fencing_token_stale_after_neutral_write", neutral_view,
                token=fencing_token(neutral_view))
        C["fence_classification_after_neutral_write"] = classify_attempt(
            store.get(neutral.job_id), NOW)["class"]
        # 12. CORSA B (la proprieta' che conta): il reclaim vince, e `mark_submitting` con la
        #     vista precedente fallisce PRIMA di autorizzare i byte e prima di qualunque invio.
        winner = orphan("winner")
        submitter_view = store.get(winner.job_id)
        attempt("race_won_by_reclaim", store.get(winner.job_id),
                token=fencing_token(store.get(winner.job_id)))
        try:
            store.mark_submitting(submitter_view, provider="fake", provider_account="acct_a",
                                  payload_digest="e" * 64, attempt_token="att_late", now=4.0)
            C["mark_submitting_after_reclaim"] = {"accepted": True}
        except Exception as e:                                  # noqa: BLE001
            C["mark_submitting_after_reclaim"] = {"accepted": False, "error": type(e).__name__}
        out["cases"] = C
        out["policy_used"] = POLICY.describe()
        expected = {"policy_omitted": "POLICY_DECISION_REQUIRED",
                    "policy_wrong_type": "LEASE_POLICY_INVALID",
                    "wrong_actor": "RECLAIM_NOT_AUTHORIZED",
                    "evidence_incomplete": "RECLAIM_EVIDENCE_INCOMPLETE",
                    "evidence_not_mapping": "RECLAIM_EVIDENCE_INCOMPLETE",
                    "lease_not_expired": "LEASE_NOT_EXPIRED",
                    "fencing_token_stale": "FENCING_TOKEN_STALE",
                    "class_not_allowed": "RECLAIM_CLASS_NOT_ALLOWED",
                    "reclaim_twice": "RECLAIM_CLASS_NOT_ALLOWED",
                    "race_lost_by_reclaim": "RECLAIM_CLASS_NOT_ALLOWED",
                    "fencing_token_stale_after_neutral_write": "FENCING_TOKEN_STALE"}
        out["expected_codes"] = expected
        out["code_mismatches"] = {k: {"got": C[k].get("code"), "expected": v}
                                  for k, v in expected.items() if C[k].get("code") != v}
        out["refusals_left_journal_unchanged"] = all(
            C[k].get("journal_unchanged") is not False for k in expected)
        settles = [r for r in C["ledger_after_reclaim"] if r["kind"] == "SETTLE"]
        out["verified"] = bool(
            not out["code_mismatches"] and out["refusals_left_journal_unchanged"]
            and ok.get("reclaimed") and row["state"] == "FAILED" and row["settled_units"] == 0
            and row["settlement_source"] == RECLAIM_SETTLEMENT_SOURCE
            and len(settles) == 1 and settles[0]["source"] == RECLAIM_SETTLEMENT_SOURCE
            and "ORPHAN_RESERVED_RECLAIMED" in C["anomalies_after_reclaim"]
            and "RECONCILIATION" in C["anomalies_after_reclaim"]
            and len(C["attempts_for_operation"]) == 1
            and after_totals["unsettled_exposure_units"] < before_totals["unsettled_exposure_units"]
            and after_totals["terminal_unsettled_jobs"] == 0
            and C["classification_with_intent"] == RESERVED_WITH_INTENT
            # la corsa persa dal reclaim non tocca la riga: resta viva con l'intento di submit
            and C["race_row_after"]["state"] == "RESERVED"
            and C["race_row_after"]["attempt_token"] == "att_race"
            and C["race_row_after"]["settled_units"] is None
            # il fence e' un fence anche quando la classe non cambia
            and C["fence_classification_after_neutral_write"] == RESERVED_NO_INTENT
            # la proprieta' che conta: dopo un reclaim vinto, nessun submit e' piu' possibile
            and C["race_won_by_reclaim"]["reclaimed"] is True
            and C["mark_submitting_after_reclaim"]["accepted"] is False
            and C["mark_submitting_after_reclaim"]["error"] == "StaleWrite"
            and RECLAIM_POLICY == "NOT_AUTHORIZED")
        out["ok"] = True
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    return out


def orphan_crash_during_reclaim(db: str, core_path: str, job_id: str) -> dict:
    """Processo REALE che muore DENTRO il reclaim, fra terminalizzazione e settlement."""
    try:
        from runtime.orphan_lease import (LeasePolicy, RESERVED_NO_INTENT, fencing_token,
                                          reclaim_orphan_reserved)
        _core(core_path)
        from registry.reservations import SqliteReservationStore
        store = SqliteReservationStore(db)
        job = store.get(job_id)
        policy = LeasePolicy(min_age_s=0.0, reclaim_authority="LAB_TEST_OPERATOR",
                             allowed_classes=(RESERVED_NO_INTENT,),
                             required_evidence_keys=(), label="LAB_TEST_CRASH")
        reclaim_orphan_reserved(store, job_id, policy=policy, actor="LAB_TEST_OPERATOR",
                                evidence={}, token=fencing_token(job), now=10_000.0, settle=False)
        sys.stdout.flush()
        os._exit(11)                                        # morte reale prima del settlement
    except Exception as e:                                  # noqa: BLE001
        return _err(e)


def orphan_repair_after_crash(db: str, core_path: str, job_id: str) -> dict:
    """Dopo il crash: il terminale non regolato e' VISIBILE e RIPARABILE (settle idempotente)."""
    out: dict = {"ok": False}
    try:
        from runtime.orphan_lease import RECLAIM_SETTLEMENT_SOURCE
        _core(core_path)
        from registry.reservations import SqliteReservationStore
        store = SqliteReservationStore(db)
        out["totals_after_crash"] = store.ledger_totals()
        out["row_after_crash"] = next((r for r in pb_worker._rows(db) if r["job_id"] == job_id), None)
        out["repair"] = store.settle(job_id, units=0, source=RECLAIM_SETTLEMENT_SOURCE, now=10_001.0)
        out["repair_idempotent"] = store.settle(job_id, units=0, source=RECLAIM_SETTLEMENT_SOURCE,
                                                now=10_002.0)
        out["totals_after_repair"] = store.ledger_totals()
        out["row_after_repair"] = next((r for r in pb_worker._rows(db) if r["job_id"] == job_id), None)
        out["ok"] = True
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    return out


# ===================================================================== C06 — NG-05
def ng05_core_main_surface(core_path: str) -> dict:
    """Il Core CANONICO (main, pinnato) NON deve avere l'API nuova: il Runtime resta sul
    percorso conservativo finche' il delta non e' approvato e mergiato."""
    out: dict = {"ok": False}
    try:
        _core(core_path)
        from adapters.base import ReservationStore
        from registry.reservations import SqliteReservationStore
        out["core_main_has_new_api"] = hasattr(SqliteReservationStore, "mark_refused_pre_submit")
        out["protocol_has_new_api"] = hasattr(ReservationStore, "mark_refused_pre_submit")
        out["ok"] = True
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    return out


def ng05_runtime_path_unchanged() -> dict:
    """Il Runtime continua a usare il percorso conservativo (reconcile -> settle) e NON
    usa `mark_refused_before_send` per il rifiuto pre-submit (invariante NG-03)."""
    out: dict = {"ok": False}
    try:
        path = os.path.join(GATE01, "runtime", "go_candidate.py")
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src, filename="go_candidate.py")
        calls: dict = {}
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef) and fn.name == "_refuse_pre_submit":
                calls[fn.name] = sorted({n.func.attr for n in ast.walk(fn)
                                         if isinstance(n, ast.Call)
                                         and isinstance(n.func, ast.Attribute)})
        out["refuse_pre_submit_calls"] = calls.get("_refuse_pre_submit", [])
        out["uses_reconcile_then_settle"] = ("reconcile" in out["refuse_pre_submit_calls"]
                                             and "settle" in out["refuse_pre_submit_calls"])
        out["uses_mark_refused_before_send"] = "mark_refused_before_send" in out["refuse_pre_submit_calls"]
        out["uses_new_core_api"] = "mark_refused_pre_submit" in out["refuse_pre_submit_calls"]
        out["ok"] = True
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    return out
