"""INTEGRATION GATE 01 — laboratorio MOCK_ONLY.

Dimostra che il runtime puo' usare i contratti GIA' PRESENTI nel Core invece di
riscriverli. Nessuna rete, nessun provider reale, nessuna credenziale, nessun
credito, nessuna modifica a P2.

PRINCIPIO: REUSE > INTEGRATE > PATCH > NEW COMPONENT.
Riusati dal Core senza copiarli: GenSpec, spec_key, Job, JobState, JobStore,
FakeAdapter, core.gate.evaluate, core.policy.Policy, core.schema.CreativePackage.

AGGIUNTE DEL LABORATORIO, dichiarate esplicitamente perche' il Core non le ha:
  1. DurableJobStore — il JobStore del Core e' in memoria. Qui viene avvolto da
     un journal SQLite. NON e' un secondo registry: lo schema di stato resta
     quello del Core (Job/JobState), il journal ne persiste solo i campi.
  2. Due stati di controllo assenti dal Core:
       RESERVED       — prenotazione durevole PRIMA della chiamata al provider
       SUBMIT_UNKNOWN — risposta persa dopo possibile accettazione
     Tutti gli altri stati sono quelli del Core. Non esiste una seconda macchina
     a stati: RESERVED precede SUBMITTED, SUBMIT_UNKNOWN e' un ramo di incertezza.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

CONTROL_VERSION = "gate01-lab-0.1.0"
CORE_SHA_PIN = "9afaddf3cec1e8baf9600ed8dc0461e7adccb5c7"
MIN_PYTHON = (3, 9)          # requisito reale: Path.is_relative_to (3.9), non 3.10


class Blocked(RuntimeError):
    """Rifiuto deterministico. Il codice e' la prova, non la frase."""


def require(ok, code):
    if not ok:
        raise Blocked(code)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(value) -> str:
    return digest(canonical(value).encode())


# ---------------------------------------------------------------- Core loading
def load_core(core_root: str, *, require_pin: bool = True):
    """Importa i contratti del Core. Provenienza verificata, sola lettura."""
    require(sys.version_info >= MIN_PYTHON,
            f"PYTHON_TOO_OLD_min={'.'.join(map(str, MIN_PYTHON))}")
    root = Path(core_root).resolve()

    def git(*a):
        return subprocess.check_output(["git", "-C", str(root), *a], text=True).strip()

    if require_pin:
        require(git("rev-parse", "HEAD") == CORE_SHA_PIN, "CORE_VERSION_NOT_TESTED")
    require(not git("status", "--porcelain"), "CORE_DIRTY")
    sys.path.insert(0, str(root))
    from adapters.base import GenSpec, Job, JobState, JobStore
    from adapters.fake import FakeAdapter
    from core.gate import evaluate
    from core.policy import Policy
    from core.schema import CreativePackage
    import adapters.fake
    require(Path(adapters.fake.__file__).resolve() == root / "adapters/fake.py",
            "CORE_IMPORT_MISMATCH")
    return dict(GenSpec=GenSpec, Job=Job, JobState=JobState, JobStore=JobStore,
                FakeAdapter=FakeAdapter, evaluate=evaluate, Policy=Policy,
                CreativePackage=CreativePackage, sha=git("rev-parse", "HEAD"))


# ------------------------------------------------------------- state machine
RESERVED = "RESERVED"
SUBMIT_UNKNOWN = "SUBMIT_UNKNOWN"
BLOCKED_AFTER_RESERVATION = "BLOCKED_AFTER_RESERVATION"

#: transizioni ammesse. Tutto cio' che non e' qui e' rifiutato.
TRANSITIONS = {
    None: {RESERVED},
    RESERVED: {"SUBMITTED", SUBMIT_UNKNOWN, BLOCKED_AFTER_RESERVATION},
    "SUBMITTED": {"RUNNING", "SUCCEEDED", "FAILED", "TIMEOUT"},
    "RUNNING": {"RUNNING", "SUCCEEDED", "FAILED", "TIMEOUT"},
    SUBMIT_UNKNOWN: {"SUCCEEDED", "FAILED", "TIMEOUT"},   # solo via reconcile autorizzato
    "SUCCEEDED": set(),
    "FAILED": set(),
    "TIMEOUT": set(),
    BLOCKED_AFTER_RESERVATION: set(),
}
TERMINAL = {"SUCCEEDED", "FAILED", "TIMEOUT", BLOCKED_AFTER_RESERVATION}


class IllegalTransition(Blocked):
    pass


def check_transition(old, new):
    allowed = TRANSITIONS.get(old, set())
    if new not in allowed:
        raise IllegalTransition(f"ILLEGAL_TRANSITION:{old}->{new}")


# ------------------------------------------------------------ durable journal
class DurableJobStore:
    """Avvolge JobStore del Core aggiungendo SOLO durabilita'.

    Lo stato canonico resta il dataclass Job del Core; qui se ne persistono i
    campi per poterlo reidratare in un processo nuovo. Journal di laboratorio,
    non un registry di produzione.
    """

    def __init__(self, db_path, core):
        self.db = str(db_path)
        self.core = core
        self.mem = core["JobStore"]()
        with self.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS jobs(
              job_id TEXT PRIMARY KEY, spec_key TEXT, provider TEXT,
              state TEXT, provider_job_id TEXT, submitted_at REAL,
              terminal_by REAL, polls INTEGER, cost_credits REAL,
              output_sha256 TEXT, snapshot_sha256 TEXT);
            CREATE TABLE IF NOT EXISTS events(
              seq INTEGER PRIMARY KEY, job_id TEXT, old TEXT, new TEXT,
              at REAL, detail TEXT);
            CREATE TABLE IF NOT EXISTS budget(
              job_id TEXT PRIMARY KEY, units INTEGER);
            CREATE TABLE IF NOT EXISTS qa(
              job_id TEXT, asset_sha256 TEXT, payload TEXT);
            """)
        self.rehydrate()

    def connect(self):
        return sqlite3.connect(self.db, timeout=10, isolation_level=None)

    # -- lettura
    def rehydrate(self):
        """Ricostruisce i Job del Core dal journal. Nessuna chat, nessun oggetto vivo."""
        Job, JobState = self.core["Job"], self.core["JobState"]
        with self.connect() as c:
            rows = c.execute("SELECT job_id,spec_key,provider,state,provider_job_id,"
                             "submitted_at,terminal_by,polls,cost_credits FROM jobs").fetchall()
        for r in rows:
            core_state = r[3] if r[3] in {s.value for s in JobState} else JobState.SUBMITTED.value
            j = Job(job_id=r[0], spec_key=r[1], provider=r[2], state=JobState(core_state),
                    provider_job_id=r[4], submitted_at=r[5] or 0.0,
                    terminal_by=r[6] or 0.0, polls=r[7] or 0, cost_credits=r[8])
            self.mem.put(j)
        return len(rows)

    def state_of(self, job_id):
        with self.connect() as c:
            row = c.execute("SELECT state FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return row[0] if row else None

    def find_live_by_spec(self, spec_key):
        """Idempotenza: delega la semantica al JobStore del Core, sul journal."""
        with self.connect() as c:
            row = c.execute("SELECT job_id,state FROM jobs WHERE spec_key=?",
                            (spec_key,)).fetchone()
        if row and row[1] not in TERMINAL:
            return row[0]
        return None

    # -- scrittura
    def reserve(self, job_id, spec_key, units, budget_cap, snapshot_sha=None):
        """Prenotazione ATOMICA, prima di qualunque chiamata al provider."""
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                used = c.execute("SELECT COALESCE(SUM(units),0) FROM budget").fetchone()[0]
                if used + units > budget_cap:
                    raise Blocked(f"OVER_BUDGET_CUMULATIVE used={used} req={units} cap={budget_cap}")
                if c.execute("SELECT 1 FROM jobs WHERE job_id=?", (job_id,)).fetchone():
                    raise Blocked("JOB_ALREADY_RESERVED")
                # IDEMPOTENZA AUTOREVOLE: find_live_by_spec del Core e' consultivo
                # (in memoria, non transazionale). Qui la stessa semantica viene
                # applicata DENTRO la transazione, altrimenti due thread prenotano
                # due job diversi per la stessa spec e pagano due volte.
                ph = ",".join("?" * len(TERMINAL))
                dup = c.execute(
                    f"SELECT job_id FROM jobs WHERE spec_key=? AND state NOT IN ({ph})",
                    (spec_key, *sorted(TERMINAL))).fetchone()
                if dup:
                    raise Blocked(f"DUPLICATE_ACTIVE_SPEC:{dup[0]}")
                check_transition(None, RESERVED)
                c.execute("INSERT INTO jobs(job_id,spec_key,provider,state,snapshot_sha256)"
                          " VALUES(?,?,?,?,?)", (job_id, spec_key, "fake", RESERVED, snapshot_sha))
                c.execute("INSERT INTO budget VALUES(?,?)", (job_id, units))
                c.execute("INSERT INTO events(job_id,old,new,at,detail) VALUES(?,?,?,?,?)",
                          (job_id, None, RESERVED, time.time(), canonical({"units": units})))
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise
        return RESERVED

    def transition(self, job_id, new, detail=None, job=None, output_sha=None):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                row = c.execute("SELECT state FROM jobs WHERE job_id=?", (job_id,)).fetchone()
                require(row is not None, "JOB_NOT_FOUND")
                check_transition(row[0], new)
                if job is not None:
                    c.execute("UPDATE jobs SET state=?,provider_job_id=?,submitted_at=?,"
                              "terminal_by=?,polls=?,cost_credits=?,"
                              "output_sha256=COALESCE(?,output_sha256) WHERE job_id=?",
                              (new, job.provider_job_id, job.submitted_at, job.terminal_by,
                               job.polls, job.cost_credits, output_sha, job_id))
                else:
                    c.execute("UPDATE jobs SET state=?,output_sha256=COALESCE(?,output_sha256)"
                              " WHERE job_id=?", (new, output_sha, job_id))
                c.execute("INSERT INTO events(job_id,old,new,at,detail) VALUES(?,?,?,?,?)",
                          (job_id, row[0], new, time.time(), canonical(detail or {})))
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise
        return new


# ------------------------------------------------------------- byte snapshot
def snapshot(path, snap_dir):
    """Congela i byte AUTORIZZATI. Il submit usa questi, non il path mutabile."""
    data = Path(path).read_bytes()
    sha = digest(data)
    Path(snap_dir).mkdir(parents=True, exist_ok=True)
    dest = Path(snap_dir) / sha
    if not dest.exists():
        shutil.copyfile(path, dest)
    return sha, str(dest)


def snapshot_bytes(snap_path, expected_sha):
    data = Path(snap_path).read_bytes()
    require(digest(data) == expected_sha, "SNAPSHOT_CORRUPTED")
    return data


def source_drifted(path, expected_sha):
    """True se il file originale e' cambiato dopo il lock."""
    try:
        return digest(Path(path).read_bytes()) != expected_sha
    except FileNotFoundError:
        return True


# ------------------------------------------------------------- policy gate
def policy_gate(core, case_path, policy_id, policies_root):
    """Entry point PUBBLICO del Core. Nessuna funzione privata chiamata."""
    policy = core["Policy"].load_by_id(policy_id, root=policies_root)
    pkg = core["CreativePackage"].load(case_path)
    v = core["evaluate"](pkg, policy)
    return {"verdict": v.verdict, "codes": list(v.codes),
            "blockers": [f.code for f in v.blockers],
            "warnings": [f.code for f in v.warnings]}


# ------------------------------------------------------------- timing source
def timing_fingerprint(canonical_path, derived_paths=()):
    """UNA sola sorgente canonica. Le rappresentazioni derivate non entrano."""
    return digest(Path(canonical_path).read_bytes())


# ------------------------------------------------------------- QA hash binding
def qa_record(store, job_id, asset_sha256, findings):
    payload = {"job_id": job_id, "asset_sha256": asset_sha256,
               "control_version": CONTROL_VERSION, "findings": findings}
    with store.connect() as c:
        c.execute("INSERT INTO qa VALUES(?,?,?)", (job_id, asset_sha256, canonical(payload)))
    return payload


def qa_valid_for(store, job_id, current_asset_sha256):
    """Il filename non e' identita'. Se l'export cambia, il QA precedente decade."""
    with store.connect() as c:
        row = c.execute("SELECT asset_sha256 FROM qa WHERE job_id=? ORDER BY rowid DESC",
                        (job_id,)).fetchone()
    if not row:
        return False, "NO_QA"
    return (row[0] == current_asset_sha256), ("VALID" if row[0] == current_asset_sha256
                                              else "INVALID_ASSET_CHANGED")


# ------------------------------------------------------------- Human Gate
HUMAN_GATE_REQUIRED = ("decision_id", "reviewer_id", "scope", "job_id",
                       "asset_sha256", "control_version", "timestamp", "decision")


def human_gate_validate(record):
    """STRUCTURAL_BINDING_ONLY. NON e' un'approvazione autenticata."""
    missing = [k for k in HUMAN_GATE_REQUIRED if not record.get(k)]
    if missing:
        raise Blocked(f"HUMAN_GATE_RECORD_INVALID_missing={','.join(missing)}")
    return {"binding": "STRUCTURAL_BINDING_ONLY",
            "authenticated": False,
            "record_fingerprint": fingerprint(record)}


# ------------------------------------------------------------- run mock
def run_mock_job(core, store, *, job_id, model, prompt, refs, units, budget_cap,
                 snap_dir, fault=None):
    """lock -> reservation -> submit -> reconcile, sui contratti del Core."""
    GenSpec, FakeAdapter = core["GenSpec"], core["FakeAdapter"]
    spec = GenSpec(kind="image", model=model, prompt=prompt, project_id="GATE01_MOCK",
                   refs=tuple(sha for sha, _ in refs))

    live = store.find_live_by_spec(spec.spec_key)
    if live:
        return {"job_id": live, "state": store.state_of(live),
                "idempotent": True, "spec_key": spec.spec_key}

    # byte autorizzati: si invia lo snapshot, non il path
    payload = b"".join(snapshot_bytes(p, sha) for sha, p in refs) or b"MOCK-NOT-A-MEDIA-ASSET"
    try:
        store.reserve(job_id, spec.spec_key, units, budget_cap,
                      snapshot_sha=digest(payload))
    except Blocked as e:
        if str(e).startswith("DUPLICATE_ACTIVE_SPEC:"):
            live = str(e).split(":", 1)[1]
            return {"job_id": live, "state": store.state_of(live),
                    "idempotent": True, "spec_key": spec.spec_key}
        raise

    adapter = FakeAdapter(never_terminal=(fault == "poll_timeout"),
                          corrupt=(fault == "corrupt"), payload=payload)
    try:
        job = adapter.submit(spec)
        if fault == "lost_response":
            raise TimeoutError("risposta persa dopo possibile accettazione")
    except Exception:
        store.transition(job_id, SUBMIT_UNKNOWN, {"reason": "lost_or_timeout"})
        return {"job_id": job_id, "state": SUBMIT_UNKNOWN, "idempotent": False,
                "spec_key": spec.spec_key}

    store.transition(job_id, "SUBMITTED", {"provider_job_id": job.provider_job_id}, job=job)
    for _ in range(3):
        job = adapter.poll(job)
        if job.state.terminal:
            break
        store.transition(job_id, "RUNNING", {"polls": job.polls}, job=job)
    if not job.state.terminal:
        return {"job_id": job_id, "state": store.state_of(job_id), "idempotent": False,
                "spec_key": spec.spec_key, "note": "RECONCILE_REQUIRED (Core: non terminale)"}

    out_sha = None
    if job.state.value == "SUCCEEDED":
        asset = adapter.fetch(job)
        with adapter.open_stream(asset) as s:
            data = s.read()
        out_sha = digest(data)
        if out_sha != asset.declared_sha256:
            store.transition(job_id, "FAILED", {"reason": "INTEGRITY_FAILED"}, job=job)
            return {"job_id": job_id, "state": "FAILED", "integrity": False,
                    "idempotent": False, "spec_key": spec.spec_key}
    store.transition(job_id, job.state.value, {"visual_qa": "NOT_VERIFIED", "media": False},
                     job=job, output_sha=out_sha)
    return {"job_id": job_id, "state": job.state.value, "output_sha256": out_sha,
            "idempotent": False, "spec_key": spec.spec_key,
            "visual_qa": "NOT_VERIFIED", "production": "NOT_ENABLED"}
