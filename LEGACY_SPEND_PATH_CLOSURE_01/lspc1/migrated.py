"""MIGRAZIONE DEI TEST STORICI AL PERCORSO GOVERNATO.

Per ogni test della suite R0-R1 che usava il percorso `go(authorization=None)`
(LEGACY_LAB) esiste qui un equivalente che verifica la STESSA proprieta'
semantica passando dal percorso GOVERNATO — envelope derivato dallo scope,
quote fidata emessa dall'AUTORITA', permesso monouso, identita' di operazione —
oppure, quando cio' che il test verifica e' una primitive BASSA del Core, un
equivalente a livello di CORE.

DUE REGOLE CHE QUESTA SUITE NON VIOLA:

  1. gli assert storici non vengono indeboliti per far passare qualcosa. Dove il
     percorso governato produce un esito DIVERSO, l'esito diverso e' asserito
     esplicitamente e la differenza e' dichiarata nella matrice di migrazione
     (`LEGACY_TEST_MIGRATION_MATRIX.md`), con il motivo. In ogni caso la
     differenza e' nella direzione di un controllo IN PIU', mai in meno;
  2. `tests/run_gate.py` NON viene toccato. La suite storica resta la base di
     non-regressione, bit per bit: e' cio' che rende confrontabili i due esiti.

Cosa questa suite dimostra, in una riga: i test storici NON hanno bisogno di un
percorso spendibile non governato. Cio' che verificavano e' verificabile — e qui
e' verificato — dal percorso governato o dal Core.

Nessun provider reale, nessuna credenziale, nessun credito.
"""
from __future__ import annotations

import multiprocessing
import os
import sys

BUNDLE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BUNDLE_ROOT not in sys.path:
    sys.path.insert(0, BUNDLE_ROOT)

from lspc1 import workers                                           # noqa: E402

CTX = multiprocessing.get_context("spawn")
CORE = os.environ.get("CREATIVE_OS_CORE_PATH", "/home/user/creative-os")
if CORE not in sys.path:
    sys.path.insert(0, CORE)
FIRST = dict(intent="new_attempt", reason="INITIAL_GENERATION", auto_permit=True)

CASES: list[tuple[str, str, str]] = []      # (id, titolo, atteso) — riempita sotto


def run(fn, *a, timeout: int = 180, **k) -> dict:
    q = CTX.Queue()
    p = CTX.Process(target=workers._entry, args=(q, fn, a, k))
    p.start()
    p.join(timeout)
    if p.is_alive():
        p.terminate()
        return {"ok": False, "error": "TIMEOUT_PROCESS"}
    return q.get(timeout=10)


def concurrent(jobs: list[tuple]) -> list[dict]:
    barrier = CTX.Barrier(len(jobs))
    q = CTX.Queue()
    ps = []
    for fn, a, k in jobs:
        p = CTX.Process(target=workers._entry, args=(q, fn, a, dict(k, barrier=barrier)))
        p.start()
        ps.append(p)
    outs = [q.get(timeout=180) for _ in ps]
    for p in ps:
        p.join(30)
    return outs


_DBS: dict[str, str] = {}


def db(name: str) -> str:
    """Store del caso migrato. Azzerato UNA volta per esecuzione, alla prima
    richiesta: ricrearlo a ogni chiamata cancellerebbe cio' che il caso sta
    verificando (ed e' esattamente il genere di errore che un test deve non fare)."""
    key = "m" + name.lower()
    if key not in _DBS:
        _DBS[key] = workers.state_db(key)
    return _DBS[key]


def gov(name: str, prompt: str, **kw) -> dict:
    return run(workers.gov_run, CORE, db(name), prompt, **kw)


def run_crash(fn, *a, **k) -> dict:
    """Processo che muore DI PROPOSITO (os._exit): non mette nulla in coda, e la
    coda vuota e' parte dell'evidenza. Stessa forma del test storico T30."""
    q = CTX.Queue()
    p = CTX.Process(target=workers._entry, args=(q, fn, a, k))
    p.start()
    p.join(120)
    return {"exitcode": p.exitcode, "queue_empty": q.empty()}


def state(name: str) -> dict:
    return run(workers.read_state, CORE, db(name))


# ===========================================================================
# M01  <- T01   pin corretto, `go` procede
# ===========================================================================
def m01() -> tuple[str, bool, dict]:
    r = gov("01", "pin ok", op="M01:asset", amount=10, max_polls=3, **FIRST)
    from runtime.core_pin import REQUIRED_CORE_SHA, verify_core_pin
    pure = verify_core_pin(REQUIRED_CORE_SHA).code
    ok = (r.get("ok") is True and r.get("core_sha") is None or True)     # core_sha non riferito da gov_run
    ok = (r.get("ok") is True and r.get("state") == "SUCCEEDED"
          and r.get("core_pin") == "CORE_PIN_OK" and pure == "CORE_PIN_OK"
          and r.get("governance") == "GOVERNED_LAB")
    return (f"core_pin={r.get('core_pin')} verdict={pure} state={r.get('state')} "
            f"governance={r.get('governance')}"), ok, {"go": r, "pure_verdict": pure}


# ===========================================================================
# M04  <- T04   spec_key deterministico, anche da un altro processo
# ===========================================================================
def m04() -> tuple[str, bool, dict]:
    from adapters.base import GenSpec
    from runtime.genspec_bridge import GoInputs, build_genspec
    from tests.worker import make_inputs
    a = build_genspec(make_inputs("deterministico"), GenSpec)
    b = build_genspec(make_inputs("deterministico"), GenSpec)
    c = build_genspec(GoInputs(kind="image", model="fake_model_v1", prompt="deterministico",
                               params={"duration_s": 5, "aspect_ratio": "9:16"},
                               refs=["ref_element_001"], project_id="GATE01_LAB"), GenSpec)
    r = gov("04", "deterministico", op="M04:asset", amount=10, max_polls=1, **FIRST)
    ok = (a.spec_key == b.spec_key == c.spec_key == r.get("spec_key")
          and r.get("governance") == "GOVERNED_LAB")
    return (f"A==B==C==altro_processo: {ok} ({a.spec_key[:16]}…)"), ok, {
        "run_A": a.spec_key, "run_B": b.spec_key, "run_C_reordered": c.spec_key,
        "run_other_process": r.get("spec_key"), "go": r}


# ===========================================================================
# M06  <- T06   happy path, durabilita', esposizione azzerata
# ===========================================================================
def m06() -> tuple[str, bool, dict]:
    r = gov("06", "happy path", op="M06:asset", amount=10, authorized=100,
            adapter_kw={"latency_polls": 2}, max_polls=5, **FIRST)
    s = state("06")
    rows = s.get("rows", [])
    ok = (r.get("ok") and r.get("reservation_outcome") == "RESERVED_NEW"
          and r.get("state") == "SUCCEEDED" and r.get("submits") == 1
          and r.get("provider") == "fake" and r.get("provider_job_id")
          and len(rows) == 1 and rows[0]["state"] == "SUCCEEDED"
          and rows[0]["job_id"] == r.get("job_id") and rows[0]["spec_key"] == r.get("spec_key")
          and s.get("reserved_units") == 0
          # in piu' rispetto allo storico: l'importo viene dalla quote, ed e' consumata
          and r.get("budget_units") == 10 and s.get("quotes_consumed") == 1
          and rows[0]["budget_units"] == 10)
    return (f"state={r.get('state')} submits={r.get('submits')} restart_read="
            f"{rows[0]['state'] if rows else None} reserved_after=0 · importo dalla quote="
            f"{r.get('budget_units')} (quote consumate {s.get('quotes_consumed')})"), ok, {
        "go": r, "restart_read": s}


# ===========================================================================
# M07  <- T07   stessa spec mentre il job e' VIVO
# ===========================================================================
def m07() -> tuple[str, bool, dict]:
    r1 = gov("07", "sequenziale", op="M07:asset", amount=10,
             adapter_kw={"never_terminal": True}, max_polls=1, **FIRST)
    # 2a chiamata: stessa operazione, tentativo VIVO -> il Core restituisce il job vivo.
    r2 = gov("07", "sequenziale", op="M07:asset", issue_quote=False, max_polls=1)
    s = state("07")
    ok = (r1.get("reservation_outcome") == "RESERVED_NEW"
          and r2.get("reservation_outcome") == "EXISTING_LIVE_JOB"
          and r2.get("submits") == 0 and r1.get("job_id") == r2.get("job_id")
          and r1.get("provider_job_id") == r2.get("provider_job_id")
          and len(s.get("rows", [])) == 1)
    return (f"GO#1={r1.get('reservation_outcome')} GO#2={r2.get('outcome')} "
            f"submits GO#2={r2.get('submits')} stesso job_id="
            f"{r1.get('job_id') == r2.get('job_id')}"), ok, {"go1": r1, "go2": r2, "state": s}


# ===========================================================================
# M08  <- T08   duplicato CONCORRENTE (due processi reali)
# ===========================================================================
def m08() -> tuple[str, bool, dict]:
    d = db("08")
    q = run(workers.gov_authority, CORE, d, "authority_quote",
            prompt="concorrente", operation_id="M08:asset", envelope="ENV_M08",
            amount=10, authorized=1000)
    qid = q["result"]["quote_id"]
    outs = concurrent([
        (workers.gov_run, (CORE, d, "concorrente"),
         dict(op="M08:asset", quote_id=qid, adapter_kw={"never_terminal": True}, max_polls=1,
              intent="new_attempt", reason="INITIAL_GENERATION", auto_permit=True)),
        (workers.gov_run, (CORE, d, "concorrente"),
         dict(op="M08:asset", quote_id=qid, adapter_kw={"never_terminal": True}, max_polls=1,
              intent="new_attempt", reason="INITIAL_GENERATION", auto_permit=True)),
    ])
    s = state("08")
    outcomes = sorted(o.get("reservation_outcome") or o.get("code") or o.get("error", "?")
                      for o in outs)
    submits = sum(o.get("submits") or 0 for o in outs)
    rows = s.get("rows", [])
    # Una sola quote per l'operazione: il secondo processo non puo' ne' duplicare la
    # spesa ne' consumarla due volte. Il vincitore prenota; il perdente e' rifiutato
    # dalla quote gia' consumata o riceve il job vivo. In ogni caso: UN submit, UNA riga.
    ok = (submits == 1 and len(rows) == 1 and rows[0]["provider_job_id"]
          and len({o.get("pid") for o in outs}) == 2
          and s.get("quotes_consumed") == 1
          and "RESERVED_NEW" in outcomes)
    return (f"outcomes={outcomes} submit totali={submits} processi="
            f"{len({o.get('pid') for o in outs})} righe={len(rows)} quote consumate="
            f"{s.get('quotes_consumed')}/1"), ok, {"processes": outs, "state": s, "quote": qid}


# ===========================================================================
# M09  <- T09   restart / resume
# ===========================================================================
def m09() -> tuple[str, bool, dict]:
    a = gov("09", "restart", op="M09:asset", amount=10, adapter_kw={"latency_polls": 3},
            max_polls=1, **FIRST)
    mid = state("09")
    b = gov("09", "restart", op="M09:asset", issue_quote=False,
            adapter_kw={"latency_polls": 3}, max_polls=5)
    end = state("09")
    ok = (a.get("submits") == 1 and b.get("submits") == 0 and b.get("resumed") is True
          and a.get("job_id") == b.get("job_id")
          and a.get("provider_job_id") == b.get("provider_job_id")
          and len(end.get("rows", [])) == 1
          and end["rows"][0]["state"] in ("SUCCEEDED", "RUNNING")
          and a.get("pid") != b.get("pid")
          and end.get("quotes_consumed") == 1)      # il resume NON consuma una seconda quote
    return (f"A: submits={a.get('submits')} stato={a.get('state')} · B (nuovo processo): "
            f"submits={b.get('submits')} resumed={b.get('resumed')} stesso job={a.get('job_id') == b.get('job_id')} "
            f"· righe={len(end.get('rows', []))} · quote consumate={end.get('quotes_consumed')}"), ok, {
        "go_a": a, "mid": mid, "go_b": b, "end": end}


# ===========================================================================
# M10  <- T10   SUBMIT_UNKNOWN: nessun re-submit, budget NON rilasciato
# ===========================================================================
def m10() -> tuple[str, bool, dict]:
    r1 = gov("10", "submit unknown", op="M10:asset", amount=30, authorized=100,
             adapter_kind="submit_unknown", **FIRST)
    mid = state("10")
    r2 = gov("10", "submit unknown", op="M10:asset", issue_quote=False, max_polls=3)
    end = state("10")
    ok = (r1.get("error") == "ConnectionResetError" and r1.get("submits") == 1
          and mid["rows"][0]["state"] == "SUBMIT_UNKNOWN" and mid["reserved_units"] == 30
          and r2.get("reservation_outcome") == "EXISTING_LIVE_JOB"
          and r2.get("outcome") == "EXISTING_LIVE_JOB/reconciliation-required"
          and r2.get("submits") == 0 and r2.get("state") == "SUBMIT_UNKNOWN"
          and end["reserved_units"] == 30 and len(end["rows"]) == 1
          and end["rows"][0]["job_id"] == mid["rows"][0]["job_id"]
          and end.get("quotes_consumed") == 1)
    return (f"GO#1 -> {mid['rows'][0]['state']} (impegnati {mid['reserved_units']} dalla quote) | "
            f"GO#2 -> {r2.get('outcome')} submits={r2.get('submits')} impegnati ancora "
            f"{end['reserved_units']}"), ok, {"go1": r1, "after_go1": mid, "go2": r2,
                                              "after_go2": end}


# ===========================================================================
# M11  <- T11   provider mismatch: reservation intatta
# ===========================================================================
def m11() -> tuple[str, bool, dict]:
    a = gov("11", "mismatch", op="M11:asset", amount=10, adapter_kind="fake_a",
            adapter_kw={"never_terminal": True}, max_polls=1, **FIRST)
    b = gov("11", "mismatch", op="M11:asset", issue_quote=False, adapter_kind="fake_b",
            adapter_kw={"never_terminal": True}, max_polls=1)
    end = state("11")
    ok = (a.get("provider") == "fake_a" and a.get("state") == "RUNNING"
          and b.get("error") == "ProviderMismatch" and b.get("submits") == 0
          and len(end["rows"]) == 1 and end["rows"][0]["provider"] == "fake_a"
          and end["rows"][0]["state"] == "RUNNING")
    return (f"fake_a RUNNING | fake_b -> {b.get('error')} submits={b.get('submits')} "
            f"reservation intatta={end['rows'][0]['provider']}/{end['rows'][0]['state']}"), ok, {
        "go_fake_a": a, "go_fake_b": b, "state": end}


# ===========================================================================
# M12  <- T12   atomicita' del budget — GOVERNATO (envelope + quote)
# ===========================================================================
def m12() -> tuple[str, bool, dict]:
    """Storico: `envelope_units=100` grezzo, 70+50. Qui: UN envelope da 100
    autorizzate e DUE quote fidate (70 e 50) su due operazioni distinte. La
    somma eccede l'autorizzato: uno dei due deve essere rifiutato, e l'impegnato
    non puo' superare 100. Stessa invariante, autorita' diversa."""
    d = db("12")
    qa = run(workers.gov_authority, CORE, d, "authority_quote",
             prompt="budget A", operation_id="M12:a", envelope="ENV_M12", amount=70,
             authorized=100)
    qb = run(workers.gov_authority, CORE, d, "authority_quote",
             prompt="budget B", operation_id="M12:b", envelope="ENV_M12", amount=50,
             authorized=100)
    outs = concurrent([
        (workers.gov_run, (CORE, d, "budget A"),
         dict(op="M12:a", envelope="ENV_M12", quote_id=qa["result"]["quote_id"],
              adapter_kw={"never_terminal": True}, max_polls=1, intent="new_attempt",
              reason="INITIAL_GENERATION", auto_permit=True)),
        (workers.gov_run, (CORE, d, "budget B"),
         dict(op="M12:b", envelope="ENV_M12", quote_id=qb["result"]["quote_id"],
              adapter_kw={"never_terminal": True}, max_polls=1, intent="new_attempt",
              reason="INITIAL_GENERATION", auto_permit=True)),
    ])
    end = state("12")
    errors = sorted(o.get("error", "OK") for o in outs)
    reserved = end["reserved_units"]
    ok = (errors.count("BudgetExceeded") == 1 and errors.count("OK") == 1
          and reserved <= 100 and reserved in (50, 70) and len(end["rows"]) == 1)
    # variante sequenziale deterministica
    d2 = db("12b")
    qa2 = run(workers.gov_authority, CORE, d2, "authority_quote",
              prompt="budget A", operation_id="M12b:a", envelope="ENV_M12b", amount=70,
              authorized=100)
    qb2 = run(workers.gov_authority, CORE, d2, "authority_quote",
              prompt="budget B", operation_id="M12b:b", envelope="ENV_M12b", amount=50,
              authorized=100)
    s1 = run(workers.gov_run, CORE, d2, "budget A", op="M12b:a", envelope="ENV_M12b",
             quote_id=qa2["result"]["quote_id"], adapter_kw={"never_terminal": True},
             max_polls=1, **FIRST)
    s2 = run(workers.gov_run, CORE, d2, "budget B", op="M12b:b", envelope="ENV_M12b",
             quote_id=qb2["result"]["quote_id"], adapter_kw={"never_terminal": True},
             max_polls=1, **FIRST)
    end2 = run(workers.read_state, CORE, d2)
    ok = ok and s1.get("ok") and s2.get("error") == "BudgetExceeded" and end2["reserved_units"] == 70
    return (f"concorrente: {errors} impegnati={reserved}/100 | sequenziale: A ok, "
            f"B={s2.get('error')} impegnati={end2['reserved_units']}"), ok, {
        "concurrent": outs, "concurrent_state": end, "sequential": [s1, s2],
        "sequential_state": end2}


# ===========================================================================
# M13  <- T13   budget non ammesso — CORE_UNIT (primitive `validate_units`)
# ===========================================================================
def m13() -> tuple[str, bool, dict]:
    """Cio' che T13 verifica e' una PRIMITIVE BASSA del Core: `validate_units`
    rifiuta un budget negativo, booleano, float o stringa, prima di qualunque
    scrittura. Nel percorso governato il client non presenta piu' un importo — lo
    riceve dalla quote — quindi quel rifiuto non e' piu' raggiungibile DA LI', e
    pretendere il contrario significherebbe tenere in vita un percorso dove il
    client sceglie il prezzo. Il test si sposta dove la proprieta' vive davvero.

    In piu': si verifica che l'AUTORITA' non possa emettere una quote con quegli
    stessi valori — cioe' che il rifiuto non sia stato spostato, ma esteso."""
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    from adapters.base import GenSpec, ReservationContractError, validate_units
    from registry.reservations import SqliteReservationStore
    from runtime.genspec_bridge import build_genspec
    from tests.worker import make_inputs
    cases = {}
    for label, units in (("negative", -1), ("bool", True), ("float", 1.5), ("str", "10")):
        try:
            validate_units(units, None)
            cases[label] = {"refused": False}
        except ReservationContractError as e:
            cases[label] = {"refused": True, "error": "ReservationContractError",
                            "message": str(e)[:120]}
    try:
        validate_units(1, -5)
        cases["negative_envelope"] = {"refused": False}
    except ReservationContractError as e:
        cases["negative_envelope"] = {"refused": True, "error": "ReservationContractError",
                                      "message": str(e)[:120]}
    # nessuna scrittura: lo store resta vuoto anche provando la prenotazione reale
    d = db("13")
    store = SqliteReservationStore(d)
    spec = build_genspec(make_inputs("invalid"), GenSpec)
    store_refusals = {}
    for label, units in (("negative", -1), ("bool", True), ("float", 1.5), ("str", "10")):
        try:
            store.reserve_or_get_live(spec, budget_units=units, now=1.0, operation_id="M13:a")
            store_refusals[label] = "ACCETTATO"
        except ReservationContractError as e:
            store_refusals[label] = f"ReservationContractError: {str(e)[:60]}"
        except Exception as e:                              # noqa: BLE001
            store_refusals[label] = f"{type(e).__name__}: {str(e)[:60]}"
    # e l'autorita' non puo' emettere una quote con quei valori
    quote_refusals = {}
    for label, amount in (("negative", -1), ("bool", True), ("float", 1.5), ("str", "10")):
        try:
            store.issue_quote(operation_id="M13:a", spec_key=spec.spec_key,
                              envelope_id="ENV_M13", amount=amount)
            quote_refusals[label] = "ACCETTATA"
        except Exception as e:                              # noqa: BLE001
            quote_refusals[label] = type(e).__name__
    end = run(workers.read_state, CORE, d)
    ok = (all(c["refused"] for c in cases.values())
          and all(v.startswith("ReservationContractError") for v in store_refusals.values())
          and all(v == "ReservationContractError" for v in quote_refusals.values())
          and end["rows"] == [])
    return (f"{len(cases)} valori non ammessi -> ReservationContractError (funzione pura, "
            f"prenotazione del Core e emissione della quote), 0 submit, 0 righe"), ok, {
        "validate_units": cases, "reserve_or_get_live": store_refusals,
        "issue_quote": quote_refusals, "state": end}


# ===========================================================================
# M18  <- T18   terminale durevole + nuovo tentativo con permesso
# ===========================================================================
def m18() -> tuple[str, bool, dict]:
    r = gov("18", "terminale", op="M18:asset", amount=10, adapter_kw={"latency_polls": 1},
            max_polls=3, **FIRST)
    s1 = state("18")
    r2 = gov("18", "terminale", op="M18:asset", issue_quote=False,
             adapter_kw={"latency_polls": 1}, max_polls=3)
    s2 = state("18")
    r3 = gov("18", "terminale", op="M18:asset", amount=10, adapter_kw={"latency_polls": 1},
             max_polls=3, intent="new_attempt", reason="CREATIVE_ITERATION", auto_permit=True)
    s3 = state("18")
    ok = (r.get("state") == "SUCCEEDED" and s1["rows"][0]["state"] == "SUCCEEDED"
          and s1["rows"][0]["cost_credits"] == 4.0
          and r2.get("resumed_terminal") is True and r2.get("submits") == 0
          and r2.get("job_id") == r.get("job_id") and len(s2["rows"]) == 1
          and r3.get("reservation_outcome") == "RESERVED_NEW"
          and r3.get("job_id") != r.get("job_id") and r3.get("permit_id")
          and r3.get("submits") == 1 and len(s3["rows"]) == 2
          and all(x["state"] == "SUCCEEDED" for x in s3["rows"])
          and s3["reserved_units"] == 0
          # in piu': il nuovo tentativo ha richiesto una NUOVA quote
          and s3.get("quotes_consumed") == 2)
    return (f"SUCCEEDED letto da nuovo processo; replay = {r2.get('outcome')} (0 submit, 1 riga); "
            f"new_attempt con permesso = {r3.get('reservation_outcome')} ({len(s3['rows'])} righe, "
            f"0 impegnato, {s3.get('quotes_consumed')} quote consumate)"), ok, {
        "go": r, "read_new_process": s1, "go_replay_resume": r2, "after_resume": s2,
        "go_new_attempt": r3, "history": s3}


# ===========================================================================
# M22  <- T22   hf_batch su spec REALE, attraverso il Core
# ===========================================================================
def m22() -> tuple[str, bool, dict]:
    d = db("22")
    a = run(workers.gov_hf_batch, CORE, d, namespace="M22", amount=10, max_polls=5,
            intent="new_attempt", reason="INITIAL_GENERATION", auto_permit=True, timeout=240)
    b = run(workers.gov_hf_batch, CORE, d, namespace="M22", amount=10, max_polls=5,
            issue_quotes=False, timeout=240)
    s = state("22")
    jobs_a = a.get("traces", [{}])[0].get("jobs", []) if a.get("ok") else []
    jobs_b = b.get("traces", [{}])[0].get("jobs", []) if b.get("ok") else []
    ok = (a.get("ok") and b.get("ok")
          and len(jobs_a) == 2 and a.get("submits") == 2
          and all(j["reservation_outcome"] == "RESERVED_NEW" for j in jobs_a)
          and all(j["governance"] == "GOVERNED_LAB" for j in jobs_a)
          and all(j["quote_id"] for j in jobs_a)
          and all(j["operation_id"].startswith("M22:") for j in jobs_a)
          and b.get("submits") == 0 and all(j["resumed"] for j in jobs_b)
          and len(s.get("rows", [])) == 2
          and s.get("quotes_consumed") == 2)
    return (f"round#1: {len(jobs_a)} RESERVED_NEW governati, {a.get('submits')} submit, quote "
            f"legate per asset · round#2 (nuovo processo): {b.get('submits')} submit, tutti "
            f"resumed · righe={len(s.get('rows', []))}"), ok, {"round1": a, "round2": b,
                                                               "state": s}


# ===========================================================================
# M24  <- T24   RESUME dopo terminale (anche da nuovo processo): zero submit
# ===========================================================================
def m24() -> tuple[str, bool, dict]:
    a = gov("24", "resume", op="M24:asset", amount=10, max_polls=3, **FIRST)
    b = gov("24", "resume", op="M24:asset", issue_quote=False, max_polls=3)
    c = gov("24", "resume", op="M24:asset", issue_quote=False, max_polls=3,
            inputs_over={"project_id": "ALTRO_RUN"})
    d_ = gov("24", "resume", op="M24:other", amount=10, max_polls=3, **FIRST)
    s = state("24")
    f1 = gov("24", "resume-failed", op="M24:failed", amount=10, adapter_kw={"fail": True},
             max_polls=3, **FIRST)
    f2 = gov("24", "resume-failed", op="M24:failed", issue_quote=False, max_polls=3)
    end = state("24")
    ok = (a.get("state") == "SUCCEEDED" and a.get("submits") == 1
          and b.get("resumed_terminal") is True and b.get("submits") == 0
          and b.get("job_id") == a.get("job_id") and b.get("outcome") == "RESUMED/SUCCEEDED"
          and a.get("pid") != b.get("pid")
          and c.get("resumed_terminal") is True and c.get("submits") == 0
          and c.get("job_id") == a.get("job_id")
          and d_.get("reservation_outcome") == "RESERVED_NEW" and d_.get("submits") == 1
          and len(s["rows"]) == 2
          and f1.get("state") == "FAILED" and f2.get("resumed_terminal") is True
          and f2.get("submits") == 0
          # in piu': nessun resume ha consumato una quote
          and end.get("quotes_consumed") == 3)
    return (f"GO#1 SUCCEEDED (1 submit) · replay nuovo processo -> {b.get('outcome')} "
            f"submits={b.get('submits')} · altro run stessa operazione -> {c.get('outcome')} "
            f"submits={c.get('submits')} · altra operazione -> {d_.get('reservation_outcome')} · "
            f"FAILED replay -> {f2.get('outcome')} submits={f2.get('submits')} · quote consumate "
            f"{end.get('quotes_consumed')} = 3 spese, 0 resume"), ok, {
        "go1": a, "replay_new_process": b, "other_run_same_operation": c,
        "other_operation": d_, "state": s, "failed": f1, "failed_replay": f2, "end": end}


# ===========================================================================
# M25  <- T25   nuovo tentativo: motivo + permesso monouso, legato all'operazione
# ===========================================================================
def m25() -> tuple[str, bool, dict]:
    d = db("25")
    a = gov("25", "attempt", op="M25:asset", amount=10, max_polls=3, **FIRST)
    no_reason = gov("25", "attempt", op="M25:asset", amount=10, max_polls=3,
                    intent="new_attempt", auto_permit=True)
    no_permit = gov("25", "attempt", op="M25:asset", amount=10, max_polls=3,
                    intent="new_attempt", reason="CREATIVE_ITERATION")
    no_op = run(workers.gov_run, CORE, d, "attempt", op="M25:asset", amount=10, max_polls=3,
                intent="new_attempt", reason="CREATIVE_ITERATION", auto_permit=True,
                quote_id=None, issue_quote=False)
    # `operation_id=None` non e' esprimibile da gov_run (lo scope deriva dall'operazione):
    # il rifiuto CR-01 e' verificato direttamente sul contratto di `go`.
    no_op = run(workers.gov_run, CORE, d, "attempt", op="", amount=10, max_polls=3,
                intent="new_attempt", reason="CREATIVE_ITERATION", auto_permit=True,
                issue_quote=False)
    b = gov("25", "attempt", op="M25:asset", amount=10, max_polls=3,
            intent="new_attempt", reason="CREATIVE_ITERATION", auto_permit=True)
    replay = gov("25", "attempt", op="M25:asset", amount=10, max_polls=3,
                 intent="new_attempt", reason="CREATIVE_ITERATION", permit_id=b.get("permit_id"))
    p2 = run(workers.gov_authority, CORE, d, "issue_permit", "unused", "CREATIVE_ITERATION",
             operation_id="M25:asset")
    permit_other = gov("25", "attempt", op="M25:altro", amount=10, max_polls=3,
                       intent="new_attempt", reason="CREATIVE_ITERATION",
                       permit_id=p2.get("result"))
    permit = run(workers.gov_authority, CORE, d, "permit", b.get("permit_id"))
    s = state("25")
    ok = (a.get("state") == "SUCCEEDED"
          and no_reason.get("error") == "IntentRefused" and no_reason.get("code") == "REASON_REQUIRED"
          and no_reason.get("submits") == 0
          and no_permit.get("error") == "IntentRefused" and no_permit.get("code") == "PERMIT_REQUIRED"
          and no_permit.get("submits") == 0
          and no_op.get("error") == "IntentRefused" and no_op.get("code") == "OPERATION_ID_REQUIRED"
          and no_op.get("submits") == 0
          and permit_other.get("error") == "PermitError" and permit_other.get("submits") == 0
          and b.get("reservation_outcome") == "RESERVED_NEW" and b.get("submits") == 1
          and b.get("permit_id")
          and replay.get("error") == "PermitError" and replay.get("submits") == 0
          and permit["result"]["consumed_by"] == b.get("job_id")
          and len(s["rows"]) == 2
          and [x["state"] for x in s["rows"]] == ["SUCCEEDED", "SUCCEEDED"])
    return (f"senza motivo -> {no_reason.get('code')} · senza permesso -> {no_permit.get('code')} · "
            f"senza operazione -> {no_op.get('code')} · con permesso -> "
            f"{b.get('reservation_outcome')} · replay permesso -> {replay.get('error')} · "
            f"permit(OP_A) con OP_B -> {permit_other.get('error')} · storico {len(s['rows'])}"), ok, {
        "go1": a, "no_reason": no_reason, "no_permit": no_permit, "no_operation": no_op,
        "new_attempt": b, "permit_replay": replay, "permit": permit,
        "permit_other_operation": permit_other, "state": s}


# ===========================================================================
# M26  <- T26   SUBMIT_UNKNOWN blocca i fallback di run e modello
# ===========================================================================
def m26() -> tuple[str, bool, dict]:
    lost = gov("26", "unknown", op="M26:asset", amount=10, adapter_kind="submit_unknown", **FIRST)
    same = gov("26", "unknown", op="M26:asset", issue_quote=False, max_polls=3)
    other_run = gov("26", "unknown", op="M26:asset", issue_quote=False, max_polls=3,
                    inputs_over={"project_id": "ALTRO_RUN"}, intent="new_attempt",
                    reason="CREATIVE_ITERATION", auto_permit=True)
    other_model = gov("26", "unknown", op="M26:asset", issue_quote=False, max_polls=3,
                      inputs_over={"model": "fake_model_v2"}, intent="new_attempt",
                      reason="CREATIVE_ITERATION", auto_permit=True)
    s = state("26")
    ok = (lost.get("error") == "ConnectionResetError" and lost.get("submits") == 1
          and same.get("outcome") == "EXISTING_LIVE_JOB/reconciliation-required"
          and same.get("submits") == 0
          and other_run.get("error") in ("IntentRefused", "OperationBusy")
          and other_run.get("submits") == 0
          and other_model.get("error") in ("IntentRefused", "OperationBusy")
          and other_model.get("submits") == 0
          and len(s["rows"]) == 1 and s["rows"][0]["state"] == "SUBMIT_UNKNOWN")
    return (f"risposta persa -> SUBMIT_UNKNOWN · stessa spec -> {same.get('outcome')} "
            f"(0 submit) · altro run -> {other_run.get('code') or other_run.get('error')} · "
            f"altro modello -> {other_model.get('code') or other_model.get('error')} · "
            f"righe={len(s['rows'])}"), ok, {"lost": lost, "same": same,
                                             "other_run": other_run, "other_model": other_model,
                                             "state": s}


# ===========================================================================
# M27  <- T27   ledger CUMULATIVO attraverso il runtime
# ===========================================================================
def m27() -> tuple[str, bool, dict]:
    """Storico: tre job regolati saturano l'envelope, il quarto e' rifiutato con
    zero job vivi, e cio' che non e' regolato resta esposto."""
    d = db("27")
    jobs = []
    for i, amount in enumerate((30, 30, 30), start=1):
        q = run(workers.gov_authority, CORE, d, "authority_quote",
                prompt=f"ledger {i}", operation_id=f"M27:{i}", envelope="ENV_M27",
                amount=amount, authorized=100)
        r = run(workers.gov_run, CORE, d, f"ledger {i}", op=f"M27:{i}", envelope="ENV_M27",
                quote_id=q["result"]["quote_id"], max_polls=5, **FIRST)
        run(workers.gov_authority, CORE, d, "settle", r.get("job_id"), units=amount,
            source="PROVIDER_SETTLEMENT_LAB")
        jobs.append(r)
    totals_before = run(workers.gov_authority, CORE, d, "ledger_totals", "ENV_M27")
    q4 = run(workers.gov_authority, CORE, d, "authority_quote",
             prompt="ledger 4", operation_id="M27:4", envelope="ENV_M27", amount=30,
             authorized=100)
    r4 = run(workers.gov_run, CORE, d, "ledger 4", op="M27:4", envelope="ENV_M27",
             quote_id=q4["result"]["quote_id"], max_polls=5, **FIRST)
    s = state("27")
    # un quinto job NON regolato: l'esposizione resta, anche a terminale
    q5 = run(workers.gov_authority, CORE, d, "authority_quote",
             prompt="ledger 5", operation_id="M27:5", envelope="ENV_M27b", amount=10,
             authorized=100)
    r5 = run(workers.gov_run, CORE, d, "ledger 5", op="M27:5", envelope="ENV_M27b",
             quote_id=q5["result"]["quote_id"], max_polls=5, **FIRST)
    totals_b = run(workers.gov_authority, CORE, d, "ledger_totals", "ENV_M27b")
    tb = totals_before.get("result", {})
    tb5 = totals_b.get("result", {})
    ok = (all(j.get("state") == "SUCCEEDED" for j in jobs)
          and tb.get("settled_units") == 90
          and r4.get("error") == "BudgetExceeded" and r4.get("submits") == 0
          and s.get("reserved_units") == 0
          and r5.get("state") == "SUCCEEDED"
          and tb5.get("unsettled_exposure_units") == 10
          and tb5.get("terminal_unsettled_jobs") == 1)
    return (f"3 job regolati: settled={tb.get('settled_units')}/100 · quarto -> "
            f"{r4.get('error')} con 0 vivi · non regolato a terminale: esposizione "
            f"{tb5.get('unsettled_exposure_units')} mantenuta "
            f"({tb5.get('terminal_unsettled_jobs')} job)"), ok, {
        "settled_jobs": jobs, "totals_after_3": tb, "fourth": r4, "state": s,
        "unsettled": r5, "totals_unsettled": tb5}


# ===========================================================================
# M30  <- T30   recovery: crash DOPO l'invio, PRIMA del journal
# ===========================================================================
def m30() -> tuple[str, bool, dict]:
    d = db("30")
    crashed = run_crash(workers.gov_run, CORE, d, "recovery", op="M30:asset", amount=10,
                        crash_after_send=True, max_polls=3, **FIRST)
    mid = state("30")
    rec = run(workers.gov_authority, CORE, d, "recover_orphaned_submits", 10.0)
    after = state("30")
    replay = gov("30", "recovery", op="M30:asset", issue_quote=False, max_polls=3)
    end = state("30")
    row_mid = mid["rows"][0] if mid.get("rows") else {}
    own = mid["ownership"][0] if mid.get("ownership") else {}
    ok = (crashed.get("exitcode") == 4 and crashed.get("queue_empty") is True
          and row_mid.get("state") == "RESERVED" and row_mid.get("provider") == "fake"
          and own.get("provider_account") == "fake_acct_a" and own.get("attempt_token")
          and rec.get("ok") and len(rec.get("result") or []) == 1
          and rec["result"][0]["state"] == "SUBMIT_UNKNOWN"
          and after["rows"][0]["state"] == "SUBMIT_UNKNOWN"
          and replay.get("submits") == 0
          and replay.get("outcome") == "EXISTING_LIVE_JOB/reconciliation-required"
          and len(end["rows"]) == 1)
    return (f"crash exit={crashed.get('exitcode')} dopo l'invio -> riga {row_mid.get('state')} "
            f"con ownership/token persistiti · recovery -> "
            f"{after['rows'][0]['state']} · replay: submits={replay.get('submits')} "
            f"({replay.get('outcome')})"), ok, {"crashed": crashed, "mid": mid,
                                                "recovery": rec, "after": after,
                                                "replay": replay, "end": end}


# ===========================================================================
# M33  <- T33   identita' fra operazioni
# ===========================================================================
def m33() -> tuple[str, bool, dict]:
    d = db("33")
    a = gov("33", "cross", op="M33A:asset", amount=10, adapter_kw={"never_terminal": True},
            max_polls=1, **FIRST)
    # OP_B chiede la STESSA spec, viva sotto OP_A: rifiuto del Core
    qb = run(workers.gov_authority, CORE, d, "authority_quote",
             prompt="cross", operation_id="M33B:asset", envelope="ENV_M33B", amount=10,
             authorized=1000)
    b = run(workers.gov_run, CORE, d, "cross", op="M33B:asset", envelope="ENV_M33B",
            quote_id=qb["result"]["quote_id"], adapter_kw={"never_terminal": True},
            max_polls=1, **FIRST)
    ra = gov("33", "cross", op="M33A:asset", issue_quote=False, max_polls=3)
    rb = run(workers.gov_run, CORE, d, "cross", op="M33B:asset", envelope="ENV_M33B",
             issue_quote=False, max_polls=3)
    s = state("33")
    ok = (a.get("reservation_outcome") == "RESERVED_NEW"
          and b.get("error") == "OperationConflict" and b.get("submits") == 0
          and ra.get("job_id") == a.get("job_id")
          and (rb.get("code") == "NO_EXISTING_ATTEMPT" or rb.get("job_id") != a.get("job_id"))
          and len(s["rows"]) == 1)
    return (f"OP_B su spec viva di OP_A -> {b.get('error')} (0 submit) · RESUME(OP_A) riprende "
            f"{ra.get('job_id')} · RESUME(OP_B) -> {rb.get('code') or rb.get('job_id')} · "
            f"righe={len(s['rows'])}"), ok, {"op_a": a, "op_b": b, "resume_a": ra,
                                             "resume_b": rb, "state": s}


# ===========================================================================
# M34  <- T34   namespace di operazione per work order
# ===========================================================================
def m34() -> tuple[str, bool, dict]:
    d = db("34")
    a = run(workers.gov_hf_batch, CORE, d, namespace="M34A", amount=10, rounds=2,
            intent="new_attempt", reason="INITIAL_GENERATION", auto_permit=True, timeout=240)
    b = run(workers.gov_hf_batch, CORE, d, namespace="M34B", amount=10,
            intent="new_attempt", reason="INITIAL_GENERATION", auto_permit=True, timeout=240)
    s = state("34")
    ja = a.get("traces", [{}])[0].get("jobs", []) if a.get("ok") else []
    jb = b.get("traces", [{}])[0].get("jobs", []) if b.get("ok") else []
    ops_a = sorted({j["operation_id"] for j in ja})
    ops_b = sorted({j["operation_id"] for j in jb})
    round2 = a.get("traces", [{}, {}])[1].get("jobs", []) if len(a.get("traces", [])) > 1 else []
    ok = (a.get("ok") and b.get("ok")
          and ops_a == ["M34A:B1_NEW_CLIP", "M34A:B4C_NEW_CLIP"]
          and ops_b == ["M34B:B1_NEW_CLIP", "M34B:B4C_NEW_CLIP"]
          and all(j["resumed"] for j in round2)
          and all(j["reservation_outcome"] == "RESERVED_NEW" for j in jb)
          and len(s["rows"]) == 4
          and len({r["spec_key"] for r in s["rows"]}) == 2)
    return (f"WO_A operazioni {ops_a} stabili in 2 round (round#2 resumed) · WO_B stessi asset "
            f"-> {ops_b} RESERVED_NEW · righe={len(s['rows'])} su "
            f"{len({r['spec_key'] for r in s['rows']})} spec distinte"), ok, {
        "wo_a": a, "wo_b": b, "state": s}


# ===========================================================================
# M37  <- T37   RESUME non e' START — ora in OGNI percorso
# ===========================================================================
def m37() -> tuple[str, bool, dict]:
    """Storico: nel percorso GOVERNED, `resume` senza attempt e' rifiutato
    (NO_EXISTING_ATTEMPT); resume-as-start restava SOLO in LEGACY_LAB, marcato.

    Qui si asserisce lo stesso rifiuto governato E il fatto nuovo: nel percorso
    LEGACY_LAB resume-as-start esiste ancora per il LABORATORIO (adapter non
    spendibile), ma non e' piu' un percorso capace di provider — con uno SPENDER
    il rifiuto arriva prima di tutto. L'asserzione storica non e' indebolita: e'
    la stessa, piu' una."""
    first = gov("37", "d03 first", op="M37:a", amount=10, max_polls=3)      # resume, nessun attempt
    q = run(workers.gov_authority, CORE, db("37"), "authority_quote", prompt="d03 first", operation_id="M37:a", envelope="ENV_M37",
            amount=10, authorized=1000)
    first_q = run(workers.gov_run, CORE, db("37"), "d03 first", op="M37:a",
                  quote_id=q["result"]["quote_id"], max_polls=3)           # anche CON quote
    started = gov("37", "d03 first", op="M37:a", amount=10, max_polls=3, **FIRST)
    s = state("37")
    # LEGACY_LAB: adapter di laboratorio -> resume-as-start ancora possibile
    lab = run(workers.p2_legacy_with_lab_adapter, CORE, workers.state_db("m37lab"),
              prompt="m37 lab resume as start")
    # LEGACY_LAB: SPENDER -> rifiutato prima di ogni effetto
    spender = run(workers.p1_legacy_with_spender, CORE, workers.state_db("m37spender"),
                  prompt="m37 spender resume as start")
    ok = (first.get("code") == "NO_EXISTING_ATTEMPT" and first.get("submits") == 0
          and first_q.get("code") == "NO_EXISTING_ATTEMPT" and first_q.get("submits") == 0
          and started.get("reservation_outcome") == "RESERVED_NEW" and started.get("submits") == 1
          and len(s["rows"]) == 1
          and lab.get("ok") is True and lab.get("legacy_resume_as_start") is True
          and spender.get("code") == "LEGACY_LAB_NOT_PROVIDER_CAPABLE"
          and spender.get("sentinel_zero") is True)
    return (f"governed resume senza attempt -> {first.get('code')} (anche con quote valida: "
            f"{first_q.get('code')}) · prima spesa solo new_attempt -> "
            f"{started.get('reservation_outcome')} · LEGACY_LAB con adapter di laboratorio: "
            f"resume-as-start={lab.get('legacy_resume_as_start')} · LEGACY_LAB con SPENDER -> "
            f"{spender.get('code')}, sentinella 0"), ok, {
        "governed_resume_no_attempt": first, "governed_resume_with_quote": first_q,
        "new_attempt": started, "state": s, "legacy_lab_adapter": lab,
        "legacy_lab_spender": spender}


MIGRATED = (
    ("M01", "T01", "pin corretto, `go` procede (governato)", m01),
    ("M04", "T04", "spec_key deterministico anche da altro processo (governato)", m04),
    ("M06", "T06", "happy path + durabilita' + esposizione azzerata (governato)", m06),
    ("M07", "T07", "duplicato sequenziale su spec viva (governato)", m07),
    ("M08", "T08", "duplicato concorrente, 2 processi reali (governato)", m08),
    ("M09", "T09", "restart/resume: nessuna nuova spesa (governato)", m09),
    ("M10", "T10", "SUBMIT_UNKNOWN: nessun re-submit, budget non rilasciato (governato)", m10),
    ("M11", "T11", "provider mismatch: reservation intatta (governato)", m11),
    ("M12", "T12", "atomicita' del budget: envelope + quote (governato)", m12),
    ("M13", "T13", "budget non ammesso: primitive del Core (CORE_UNIT)", m13),
    ("M18", "T18", "terminale durevole + nuovo tentativo con permesso (governato)", m18),
    ("M22", "T22", "hf_batch su spec reale attraverso il Core (governato)", m22),
    ("M24", "T24", "RESUME dopo terminale: zero submit (governato)", m24),
    ("M25", "T25", "nuovo tentativo: motivo + permesso monouso legato (governato)", m25),
    ("M26", "T26", "SUBMIT_UNKNOWN blocca i fallback di run/modello (governato)", m26),
    ("M27", "T27", "ledger cumulativo attraverso il runtime (governato)", m27),
    ("M30", "T30", "recovery: crash dopo invio, prima del journal (governato)", m30),
    ("M33", "T33", "identita' fra operazioni (governato)", m33),
    ("M34", "T34", "namespace di operazione per work order (governato)", m34),
    ("M37", "T37", "RESUME non e' START, in ogni percorso (governato + legacy)", m37),
)
