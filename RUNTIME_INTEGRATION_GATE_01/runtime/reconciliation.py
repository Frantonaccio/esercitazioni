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
     una chiave derivata da un segreto per (provider, conto). E' l'equivalente LAB
     di "risposta autenticata del provider": chi non possiede quel segreto non puo'
     produrre un report che superi la verifica;
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

PERIMETRO DI CIO' CHE E' VERIFICATO (HUMAN REVIEW 01 — correzione di classificazione):

  VERIFICATO (B03/B04)  il BINDING e l'AUTENTICAZIONE HMAC: un report non firmato, firmato
                        con un'altra chiave, alterato dopo la firma, riferito ad altro
                        provider/conto/job/operazione/token/digest, o riproposto (nonce
                        gia' consumato) non produce alcuna transizione.
  NON VERIFICATO        la COMPOSIZIONE con P-B01: in B03/B04 il segreto e la chiave sono
                        FIXTURE di test, create e usate nel processo del gate, NON dentro
                        il daemon spender isolato. Che il segreto e la chiave non escano mai
                        dal dominio dello spender e' un requisito di DESIGN di questa fase,
                        non un fatto dimostrato dai test correnti; l'API stessa espone la
                        chiave derivata (`LabProviderStatusAuthority.key`, `derive_report_key`),
                        quindi la custodia dipende da chi la invoca e da dove.
  NON VERIFICATO        il provider reale: nessuna verifica contro un sistema di provider.
                        Nessun claim di "real provider reconciliation".
  MECCANISMO (NG-04)    FRESHNESS: dal PROVIDER BOUNDARY GATE — OPEN-GAP CLOSURE la freshness NON
                        e' piu' opzionale. `reconcile_authenticated` pretende una
                        `FreshnessPolicy` esplicita: ometterla e' un rifiuto
                        (`FRESHNESS_POLICY_REQUIRED`), non un permesso. Il MECCANISMO e'
                        verificato qui; il VALORE della finestra (`max_age_s`,
                        `max_future_skew_s`) resta una decisione umana: il modulo non
                        definisce alcuna policy di default (vedi NG04_FRESHNESS.md,
                        `POLICY_DECISION_REQUIRED`).
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


# ---------------------------------------------------------------------------
# NG-04 — FRESHNESS: MECCANISMO (qui) vs POLICY (decisione umana, non qui).
#
# MECCANISMO = la capacita' tecnica di imporre una finestra temporale fail-closed
# su un report autenticato. E' quello che questo modulo fornisce e che i test
# verificano, parametricamente.
#
# POLICY = i VALORI della finestra (quanti secondi di eta' massima, quanto skew
# futuro tollerare). NON sono definiti qui e non esiste un default: nessuna
# costante 30s/60s/5min. Un chiamante che non porta una policy esplicita viene
# RIFIUTATO (`FRESHNESS_POLICY_REQUIRED`) — l'assenza di decisione non e' un
# permesso. Vedi `NG04_FRESHNESS.md`: `POLICY_DECISION_REQUIRED`.
# ---------------------------------------------------------------------------
_REQUIRED = object()            # sentinella: "nessuna policy fornita", distinta da None


class FreshnessPolicy:
    """Finestra di validita' temporale di un report, PARAMETRICA e fail-closed.

    Due limiti, entrambi obbligatori ed espliciti:

      `max_age_s`          eta' massima ammessa: `now - issued_at <= max_age_s`.
      `max_future_skew_s`  anticipo massimo tollerato sull'orologio dell'emittente:
                           `issued_at - now <= max_future_skew_s`. Senza questo
                           limite un `issued_at` nel futuro rende l'eta' negativa e
                           quindi sempre "fresca" (difetto riprodotto pre-fix).

    `label` e' obbligatoria e serve a rendere tracciabile CHI ha deciso i valori:
    l'evidenza registrata dice sempre sotto quale policy il report e' stato accettato.
    Zero e' un valore ammesso ed e' il piu' stretto possibile (nessun anticipo
    tollerato / il report deve essere dello stesso istante); non e' un default.
    """

    __slots__ = ("max_age_s", "max_future_skew_s", "label")

    def __init__(self, *, max_age_s: float, max_future_skew_s: float, label: str):
        for name, value in (("max_age_s", max_age_s), ("max_future_skew_s", max_future_skew_s)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ReconciliationRefused(
                    "FRESHNESS_POLICY_INVALID", f"{name} deve essere numerico, ricevuto {value!r}")
            if value != value or value in (float("inf"), float("-inf")):        # NaN / inf
                raise ReconciliationRefused(
                    "FRESHNESS_POLICY_INVALID", f"{name} non finito: {value!r}")
            if value < 0:
                raise ReconciliationRefused(
                    "FRESHNESS_POLICY_INVALID", f"{name} negativo: {value!r}")
        if not isinstance(label, str) or not label.strip():
            raise ReconciliationRefused(
                "FRESHNESS_POLICY_INVALID",
                "label obbligatoria: la policy deve dichiarare chi ha deciso i valori")
        self.max_age_s = float(max_age_s)
        self.max_future_skew_s = float(max_future_skew_s)
        self.label = label

    def describe(self) -> dict:
        return {"label": self.label, "max_age_s": self.max_age_s,
                "max_future_skew_s": self.max_future_skew_s}

    def check(self, issued_at, now: float) -> dict:
        """Solleva `ReconciliationRefused` se il report non e' fresco. Restituisce
        l'attestazione da allegare all'evidenza quando lo e'.

        Confini (deliberati, verificati dai test):
          `age == max_age_s`            -> AMMESSO (la finestra e' chiusa a destra)
          `age == max_age_s + eps`      -> REPORT_STALE
          `-skew == -max_future_skew_s` -> AMMESSO
          `issued_at` oltre lo skew     -> REPORT_FROM_FUTURE
        """
        if issued_at is None:
            raise ReconciliationRefused("REPORT_TIMESTAMP_MISSING",
                                        "report privo di `issued_at`: eta' non verificabile")
        if isinstance(issued_at, bool) or not isinstance(issued_at, (int, float)):
            raise ReconciliationRefused(
                "REPORT_TIMESTAMP_MALFORMED",
                f"`issued_at` non numerico: {type(issued_at).__name__}")
        issued_at = float(issued_at)
        if issued_at != issued_at or issued_at in (float("inf"), float("-inf")):
            raise ReconciliationRefused("REPORT_TIMESTAMP_MALFORMED",
                                        f"`issued_at` non finito: {issued_at!r}")
        age = now - issued_at
        if -age > self.max_future_skew_s:
            raise ReconciliationRefused(
                "REPORT_FROM_FUTURE",
                f"report emesso {-age:.6f}s nel futuro, skew tollerato "
                f"{self.max_future_skew_s}s (policy {self.label!r})")
        if age > self.max_age_s:
            raise ReconciliationRefused(
                "REPORT_STALE",
                f"report vecchio di {age:.6f}s, massimo {self.max_age_s}s "
                f"(policy {self.label!r})")
        return {"policy": self.describe(), "issued_at": issued_at, "checked_at": now,
                "age_s": age, "verdict": "FRESH"}


def derive_report_key(secret: str | bytes, provider: str, provider_account: str) -> bytes:
    """Chiave di autenticazione dei report, derivata da un segreto per (provider, conto).

    NOTA DI PERIMETRO (HUMAN REVIEW 01): nel design di questa fase il segreto vive solo nel
    processo spender (P-B01) e la chiave e' derivata li'. Questa funzione NON impone quella
    custodia — la garantisce l'isolamento del processo che la chiama, non la firma. I test
    B03/B04 la usano come fixture fuori dal daemon: dimostrano il binding e l'autenticazione,
    non la custodia del segreto."""
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
    Nel design va istanziata SOLO dal lato spender, che possiede il segreto; la classe non
    puo' imporlo (espone `key`), quindi la custodia e' una proprieta' del processo che la
    costruisce, non di questa API. Vedi il perimetro dichiarato in testa al modulo."""

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
            # NG-04: la semantica del timestamp ha UNA sola autorita', `FreshnessPolicy.check`
            # (assente / malformato / nel futuro / troppo vecchio, con codici distinti). Qui si
            # verifica solo che il campo sia presente e canonicalizzabile per la firma.
            if k not in report:
                raise ReconciliationRefused("REPORT_TIMESTAMP_MISSING", "campo 'issued_at' assente")
            if not isinstance(v, (int, float, str, type(None))):
                raise ReconciliationRefused("REPORT_TIMESTAMP_MALFORMED",
                                            f"campo {k!r} non canonicalizzabile: {type(v).__name__}")
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
                            freshness=_REQUIRED):
    """Verifica tutto, poi (e solo poi) `store.reconcile`. Restituisce il Job aggiornato.
    `job_id` e' il job che il CHIAMANTE intende riconciliare: un report valido ma di un altro
    job/operazione non viene mai applicato altrove (JOB_MISMATCH).

    NG-04: `freshness` e' una `FreshnessPolicy` OBBLIGATORIA. Non ha default e `None` non e'
    ammesso: l'assenza di una decisione sulla finestra e' un rifiuto
    (`FRESHNESS_POLICY_REQUIRED`), mai un permesso. Il modulo non sceglie i valori."""
    now = time.time() if now is None else now
    if freshness is _REQUIRED or freshness is None:
        raise ReconciliationRefused(
            "FRESHNESS_POLICY_REQUIRED",
            "nessuna FreshnessPolicy fornita: la finestra di validita' del report e' una "
            "decisione esplicita (max_age_s + max_future_skew_s). Senza di essa non si "
            "riconcilia nulla.")
    if not isinstance(freshness, FreshnessPolicy):
        raise ReconciliationRefused(
            "FRESHNESS_POLICY_INVALID",
            f"freshness deve essere una FreshnessPolicy, ricevuto {type(freshness).__name__}")
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
    # NG-04: la freshness si valuta DOPO l'autenticazione (un report non autenticato non
    # merita un verdetto sull'eta') e PRIMA di qualunque lettura dello store.
    freshness_attestation = freshness.check(report.get("issued_at"), now)
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
                "nonce_claim": os.path.basename(nonce_path), "snapshot_audit": snapshot_audit,
                "freshness": freshness_attestation}
    return store.reconcile(job, target, evidence, now=now)
