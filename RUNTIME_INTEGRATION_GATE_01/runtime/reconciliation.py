"""P-B02 — RECONCILIATION AUTENTICATA E LEGATA ALL'IDENTITA' (Runtime, LAB).

Cosa il Core offre (registry/reservations.SqliteReservationStore.reconcile, CR-05):
un percorso ESPLICITO che porta RESERVED/SUBMIT_UNKNOWN a uno stato scoperto da
un'evidenza, registrata come anomalia 'RECONCILIATION'. L'unica precondizione
del Core e' che l'evidenza abbia `source` e `remote_ref` non vuoti.

Cosa mancava (riprodotto pre-fix, evidence/pre_fix/reproduction_baseline.json["P-B02"]):
una evidenza qualunque, di chiunque, che nomina un altro provider, un altro
conto, un altro job remoto e un altro token viene accettata; la stessa evidenza
riproposta su un altro job di un'altra operazione viene accettata di nuovo.

Questo modulo NON cambia il Core: mette DAVANTI a `store.reconcile` un
verificatore fail-closed. La riconciliazione avviene solo se:

  1. il REPORT e' ben formato e AUTENTICATO: HMAC-SHA256 sui campi canonici con
     una chiave derivata dal segreto dello spender per (provider, conto). E' l'
     equivalente LAB di "risposta autenticata del provider": chi non ha il segreto
     dello spender non puo' produrre un report valido (l'orchestrator non lo ha);
  2. il job esiste nello store AUTOREVOLE ed e' in uno stato riconciliabile
     (RESERVED con intento di submit persistito, oppure SUBMIT_UNKNOWN);
  3. l'ADAPTER che riconcilia e' il proprietario del job (provider + conto: la
     stessa regola di transport.pipeline._check_ownership);
  4. il report e' LEGATO al job persistito: provider, provider_account,
     provider_job_id (se noto), attempt_token, payload_digest, operation_id,
     job_id — TUTTI devono coincidere;
  5. (P-B04) lo snapshot exact-byte legato a quell'attempt esiste ed e' integro;
  6. il NONCE del report non e' mai stato consumato: claim write-once (O_EXCL)
     nella directory `<store_path>.reconciliation/` — un replay fallisce anche se
     tutto il resto e' valido;
  7. lo stato di destinazione e' uno stato che un provider puo' riferire.

Solo allora si chiama `store.reconcile(job, state, evidence)`: e' il Core a
validare la transizione (RECONCILIATION_TRANSITIONS), il CAS sulla revisione e a
registrare l'evidenza. Ogni rifiuto e' `ReconciliationRefused(code)` PRIMA di
qualunque scrittura sul journal.

Questo e' un hardening LAB: la chiave e la firma sono un equivalente
verificabile dell'interlocutore autenticato, NON una verifica contro un provider
reale. Nessun claim di "real provider reconciliation".
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time

REPORT_SCHEMA = "lab-provider-status-report/1"
REPORT_FIELDS = ("schema", "provider", "provider_account", "provider_job_id", "attempt_token",
                 "payload_digest", "operation_id", "job_id", "state", "remote_ref", "nonce", "issued_at")
RECONCILABLE_STATES = ("RESERVED", "SUBMIT_UNKNOWN")
REPORTABLE_STATES = ("SUBMITTED", "RUNNING", "SUCCEEDED", "FAILED", "TIMEOUT")
EVIDENCE_SOURCE = "LAB_AUTHENTICATED_PROVIDER_REPORT"
NONCE_DIR_SUFFIX = ".reconciliation"
_KEY_CONTEXT = b"vf-reconciliation-report-key/1"


class ReconciliationRefused(RuntimeError):
    """Il report non prova nulla su QUESTO job: nessuna transizione, journal intatto."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def nonce_dir_for(store_path: str) -> str:
    return os.path.abspath(store_path) + NONCE_DIR_SUFFIX


def derive_report_key(secret: str | bytes, provider: str, provider_account: str) -> bytes:
    """Chiave di autenticazione dei report, derivata dal segreto dello spender per
    (provider, conto). Il segreto non lascia mai lo spender; la chiave nemmeno."""
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    if not secret or not provider or not provider_account:
        raise ReconciliationRefused("KEY_CONTEXT_REQUIRED", "segreto, provider e conto obbligatori")
    msg = _KEY_CONTEXT + b"|" + provider.encode("utf-8") + b"|" + provider_account.encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).digest()


def canonical_report_bytes(fields: dict) -> bytes:
    body = {k: fields.get(k) for k in REPORT_FIELDS}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_report(key: bytes, fields: dict) -> dict:
    report = {k: fields.get(k) for k in REPORT_FIELDS}
    report["signature"] = hmac.new(key, canonical_report_bytes(report), hashlib.sha256).hexdigest()
    return report


def verify_report_signature(key: bytes, report: dict) -> bool:
    sig = report.get("signature")
    if not isinstance(sig, str) or not sig:
        return False
    expected = hmac.new(key, canonical_report_bytes(report), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


class LabProviderStatusAuthority:
    """Equivalente LAB dell'endpoint di stato autenticato del provider, per UN conto.
    Vive dal lato dello spender (che possiede il segreto). Emette report firmati."""

    def __init__(self, secret: str | bytes, provider: str, provider_account: str):
        self.provider, self.provider_account = provider, provider_account
        self._key = derive_report_key(secret, provider, provider_account)

    @property
    def key(self) -> bytes:
        return self._key

    def report(self, *, provider_job_id: str, attempt_token: str, payload_digest: str,
               operation_id: str, job_id: str, state: str, remote_ref: str,
               now: float | None = None, nonce: str | None = None) -> dict:
        return sign_report(self._key, {
            "schema": REPORT_SCHEMA, "provider": self.provider,
            "provider_account": self.provider_account, "provider_job_id": provider_job_id,
            "attempt_token": attempt_token, "payload_digest": payload_digest,
            "operation_id": operation_id, "job_id": job_id, "state": state,
            "remote_ref": remote_ref, "nonce": nonce or f"nonce_{secrets.token_hex(16)}",
            "issued_at": time.time() if now is None else now})


def _check_report_shape(report) -> dict:
    if not isinstance(report, dict):
        raise ReconciliationRefused("REPORT_MALFORMED", "report non e' un mapping")
    for k in REPORT_FIELDS:
        v = report.get(k)
        if k == "issued_at":
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise ReconciliationRefused("REPORT_MALFORMED", f"campo {k!r} assente o non numerico")
        elif k == "provider_job_id":
            if v is not None and not isinstance(v, str):
                raise ReconciliationRefused("REPORT_MALFORMED", f"campo {k!r} non stringa")
        elif not isinstance(v, str) or not v:
            raise ReconciliationRefused("REPORT_MALFORMED", f"campo {k!r} assente o vuoto")
    if report["schema"] != REPORT_SCHEMA:
        raise ReconciliationRefused("REPORT_MALFORMED", f"schema {report['schema']!r} non ammesso")
    return report


def _claim_nonce(nonce_dir: str, nonce: str, payload: dict) -> str:
    """Claim WRITE-ONCE del nonce: O_EXCL. Un nonce gia' consumato -> REPLAY."""
    os.makedirs(nonce_dir, mode=0o700, exist_ok=True)
    path = os.path.join(nonce_dir, hashlib.sha256(nonce.encode("utf-8")).hexdigest() + ".json")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        raise ReconciliationRefused("REPLAY", f"nonce {nonce[:12]}… gia' consumato: report riproposto")
    try:
        os.write(fd, json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))
    finally:
        os.close(fd)
    return path


def reconcile_authenticated(store, adapter, report, *, job_id: str, key: bytes, nonce_dir: str,
                            snapshot_ledger=None, now: float | None = None,
                            max_age_s: float | None = None):
    """Verifica tutto, poi (e solo poi) `store.reconcile`. Restituisce il Job aggiornato.
    `job_id` e' il job che il CHIAMANTE intende riconciliare: un report valido ma di un altro
    job/operazione non viene mai applicato altrove (JOB_MISMATCH)."""
    now = time.time() if now is None else now
    report = _check_report_shape(report)
    if not isinstance(job_id, str) or not job_id:
        raise ReconciliationRefused("JOB_ID_REQUIRED", "job_id di destinazione obbligatorio")
    if report["job_id"] != job_id:
        raise ReconciliationRefused(
            "JOB_MISMATCH", f"il report riguarda {report['job_id']!r}, destinazione {job_id!r}: "
                            f"una risposta valida di un altro job/operazione non si applica qui")
    # 1. autenticazione dell'interlocutore (equivalente LAB)
    if not verify_report_signature(key, report):
        raise ReconciliationRefused("UNAUTHENTICATED", "firma del report assente o non valida")
    if max_age_s is not None and now - float(report["issued_at"]) > max_age_s:
        raise ReconciliationRefused("REPORT_STALE", "report troppo vecchio")
    if report["state"] not in REPORTABLE_STATES:
        raise ReconciliationRefused("TARGET_STATE_NOT_ALLOWED",
                                    f"stato {report['state']!r} non riferibile da un provider")
    # 2. job autorevole, stato riconciliabile
    job = store.get(job_id)
    if job is None:
        raise ReconciliationRefused("JOB_UNKNOWN", f"job {job_id!r} sconosciuto allo store autorevole")
    if job.state.value not in RECONCILABLE_STATES:
        raise ReconciliationRefused("NOT_RECONCILABLE", f"job {job.job_id} in stato {job.state.value}")
    if not (job.provider and job.provider_account and job.attempt_token and job.payload_digest):
        raise ReconciliationRefused(
            "OWNERSHIP_INCOMPLETE",
            f"job {job.job_id}: nessun intento di submit persistito (provider/conto/token/digest assenti): "
            f"nulla e' stato inviato, nulla da riconciliare con un provider")
    # 3. l'adapter che riconcilia e' il proprietario (provider + conto)
    account = str(getattr(adapter, "account_id", "") or "")
    if getattr(adapter, "name", None) != job.provider or account != job.provider_account:
        raise ReconciliationRefused(
            "ADAPTER_NOT_OWNER", f"adapter {getattr(adapter, 'name', None)}/{account} non e' il proprietario "
                                 f"di {job.job_id} ({job.provider}/{job.provider_account})")
    # 4. binding del report al job persistito
    checks = (("PROVIDER_MISMATCH", report["provider"], job.provider),
              ("ACCOUNT_MISMATCH", report["provider_account"], job.provider_account),
              ("OPERATION_MISMATCH", report["operation_id"], job.operation_id),
              ("JOB_MISMATCH", report["job_id"], job.job_id),
              ("ATTEMPT_TOKEN_MISMATCH", report["attempt_token"], job.attempt_token),
              ("PAYLOAD_DIGEST_MISMATCH", report["payload_digest"], job.payload_digest))
    for code, got, expected in checks:
        if got != expected:
            raise ReconciliationRefused(code, f"report {got!r} != job {expected!r}")
    if job.provider_job_id:
        if report["provider_job_id"] != job.provider_job_id:
            raise ReconciliationRefused(
                "PROVIDER_JOB_ID_MISMATCH", f"report {report['provider_job_id']!r} != job {job.provider_job_id!r}")
    elif not report["provider_job_id"]:
        raise ReconciliationRefused("PROVIDER_JOB_ID_REQUIRED",
                                    "il job non ha identita' remota: il report deve fornirla")
    # 5. P-B04: lo snapshot exact-byte di QUESTO attempt esiste ed e' integro
    snapshot_audit = None
    if snapshot_ledger is not None:
        snapshot_audit = snapshot_ledger.audit(
            digest=job.payload_digest, operation_id=job.operation_id, provider=job.provider,
            provider_account=job.provider_account, job_id=job.job_id, attempt_token=job.attempt_token)
        if not snapshot_audit["ok"]:
            raise ReconciliationRefused("SNAPSHOT_AUDIT_FAILED",
                                        f"snapshot dell'attempt non verificabile: {snapshot_audit['problems']}")
    # 6. replay: nonce monouso (claim write-once, prima della scrittura sul journal)
    nonce_path = _claim_nonce(nonce_dir, report["nonce"], {"job_id": job.job_id, "state": report["state"],
                                                          "remote_ref": report["remote_ref"], "at": now})
    # 7. percorso esplicito del Core (transizione, CAS, evidenza registrata)
    target = type(job.state)(report["state"])
    evidence = {"source": EVIDENCE_SOURCE, "remote_ref": report["remote_ref"],
                "provider_job_id": report["provider_job_id"],
                "report": {k: report[k] for k in REPORT_FIELDS},
                "signature_verified": True, "verifier": {"provider": adapter.name, "provider_account": account},
                "nonce_claim": os.path.basename(nonce_path), "snapshot_audit": snapshot_audit}
    return store.reconcile(job, target, evidence, now=now)
