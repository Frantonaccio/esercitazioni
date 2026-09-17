"""P-B04 — SNAPSHOT EXACT-BYTE, IMMUTABILE E VERIFICABILE del payload autorizzato (LAB).

Cosa il Core gia' garantisce (RV02, transport/pipeline.run_job + adapters/fake.MockTransport):
il digest dei byte che il trasporto inviera' e' persistito PRIMA del submit
(`reservations.payload_digest`) e il trasporto fittizio rifiuta ogni digest non
autorizzato prima del marcatore di invio.

Cosa mancava (riprodotto pre-fix, evidence/pre_fix/reproduction_baseline.json["P-B04"]):
  - i BYTE autorizzati non esistono su disco: solo il loro sha256;
  - l'insieme dei digest autorizzati vive in memoria nel trasporto, nello stesso
    dominio di privilegio dell'adapter: un adapter che deriva puo' autorizzare da
    solo un secondo digest e RAGGIUNGERE il marcatore di invio con byte diversi;
    il mismatch e' rilevato solo DOPO l'invio (SUBMIT_UNKNOWN);
  - nessuna verifica su evidenza persistita immediatamente prima del send;
  - nessuna verifica in reconciliation/audit.

Questo modulo aggiunge, SOLO nel Runtime e senza toccare il Core:

  SnapshotLedger          ledger WRITE-ONCE su filesystem (O_EXCL, mode 0444,
                          content-addressed: il nome del file E' il digest):
                            <digest>.bin                          byte canonici esatti
                            <digest>__<opkey>.seal.json           sigillo: operation/spec/provider/conto
                            <digest>__<opkey>__<attempt_token>.bind.json binding all'attempt (job_id + token)
                            <digest>__<opkey>__<attempt_token>.send.json attestazione pre-send (monouso)
                          (bind/send sono chiavati sull'attempt_token, casuale per attempt e
                          persistito dal Core nella riga del job: un ledger residuo di un run
                          precedente non puo' collidere con un attempt nuovo)
                          Nessun file viene mai aggiornato o cancellato da questo
                          modulo: un secondo `open(O_EXCL)` sullo stesso nome fallisce.

  SnapshotGuardedTransport
                          avvolge il trasporto dell'adapter (MockTransport): il
                          marcatore di invio resta nel trasporto interno; PRIMA di
                          delegargli `send(payload)` rilegge i byte persistiti e
                          pretende: byte identici (confronto byte per byte, non solo
                          digest), digest del file == digest atteso, sigillo per QUESTA
                          operazione/provider/conto, binding a QUESTO attempt
                          (job_id + attempt_token registrati a mark_submitting),
                          attestazione non ancora emessa. Qualunque scarto ->
                          PayloadBindingError del Core PRIMA del marcatore: run_job
                          lo tratta come REFUSED_BEFORE_SEND (costo attestato 0).

L'immutabilita' e' del ledger (write-once + content-addressed + verifica a ogni
lettura), non una convenzione del chiamante. Il ledger sta accanto allo store
(`<store_path>.snapshots/`), quindi con P-B01 vive nel dominio dello spender.

Questo modulo NON importa il Core a livello di modulo: l'unica classe del Core
che usa (`adapters.base.PayloadBindingError`) e' importata lazily, dopo il pin.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time

SNAPSHOT_DIR_SUFFIX = ".snapshots"
SEAL_SCHEMA = "payload-snapshot-seal/1"
BIND_SCHEMA = "payload-snapshot-bind/1"
SEND_SCHEMA = "payload-snapshot-send-attestation/1"
_SEAL_KEYS = ("digest", "bytes", "operation_id", "spec_key", "provider", "provider_account")


class PayloadSnapshotError(RuntimeError):
    """Lo snapshot non prova che i byte da inviare siano quelli autorizzati. Nessun invio."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def ledger_dir_for(store_path: str) -> str:
    return os.path.abspath(store_path) + SNAPSHOT_DIR_SUFFIX


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def opkey(operation_id: str, provider: str, provider_account: str) -> str:
    """Chiave del contesto di autorizzazione: operazione + provider + conto."""
    raw = json.dumps([operation_id, provider, provider_account], separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _write_once(path: str, data: bytes) -> None:
    """Crea il file SOLO se non esiste (O_EXCL) e lo lascia in sola lettura (0444)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o444)


def _read(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _read_json(path: str) -> dict:
    return json.loads(_read(path).decode("utf-8"))


def _require_str(name: str, value) -> str:
    if not isinstance(value, str) or not value:
        raise PayloadSnapshotError("BINDING_FIELD_REQUIRED", f"{name} obbligatorio (stringa non vuota)")
    return value


class SnapshotLedger:
    """Ledger write-once dei payload autorizzati. Nessun UPDATE, nessun DELETE."""

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, mode=0o700, exist_ok=True)

    # ------------------------------------------------------------ path
    def bin_path(self, digest: str) -> str:
        return os.path.join(self.root, f"{digest}.bin")

    def seal_path(self, digest: str, key: str) -> str:
        return os.path.join(self.root, f"{digest}__{key}.seal.json")

    def bind_path(self, digest: str, key: str, attempt_token: str) -> str:
        return os.path.join(self.root, f"{digest}__{key}__{attempt_token}.bind.json")

    def send_path(self, digest: str, key: str, attempt_token: str) -> str:
        return os.path.join(self.root, f"{digest}__{key}__{attempt_token}.send.json")

    # ------------------------------------------------------------ seal
    def seal(self, payload: bytes, *, operation_id: str, spec_key: str, provider: str,
             provider_account: str, now: float | None = None) -> dict:
        """Persiste i byte esatti (content-addressed) e il sigillo per il contesto di
        autorizzazione. Idempotente sullo stesso (byte, contesto); un sigillo gia'
        esistente con campi diversi e' un conflitto, mai una sovrascrittura."""
        if not isinstance(payload, (bytes, bytearray)) or not payload:
            raise PayloadSnapshotError("EMPTY_PAYLOAD", "nessun byte da sigillare")
        payload = bytes(payload)
        for n, v in (("operation_id", operation_id), ("spec_key", spec_key),
                     ("provider", provider), ("provider_account", provider_account)):
            _require_str(n, v)
        digest = sha256_hex(payload)
        key = opkey(operation_id, provider, provider_account)
        bin_path = self.bin_path(digest)
        try:
            _write_once(bin_path, payload)
        except FileExistsError:
            pass
        persisted = _read(bin_path)
        if persisted != payload:
            raise PayloadSnapshotError(
                "DIGEST_COLLISION", f"il file {digest[:16]}….bin contiene byte diversi dal payload")
        seal = {"schema": SEAL_SCHEMA, "digest": digest, "bytes": len(payload),
                "operation_id": operation_id, "spec_key": spec_key, "provider": provider,
                "provider_account": provider_account, "opkey": key,
                "sealed_at": time.time() if now is None else now}
        seal_path = self.seal_path(digest, key)
        try:
            _write_once(seal_path, json.dumps(seal, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        except FileExistsError:
            prev = _read_json(seal_path)
            if {k: prev.get(k) for k in _SEAL_KEYS} != {k: seal[k] for k in _SEAL_KEYS}:
                raise PayloadSnapshotError(
                    "SEAL_CONFLICT", f"sigillo gia' esistente per {digest[:16]}… con campi diversi")
            return prev
        return seal

    # ------------------------------------------------------------ bind
    def bind_attempt(self, *, digest: str, operation_id: str, provider: str, provider_account: str,
                     job_id: str, attempt_token: str, now: float | None = None) -> dict:
        """Lega lo snapshot sigillato a UN attempt (job_id + attempt_token). Write-once:
        un attempt gia' legato non si rilega (ATTEMPT_ALREADY_BOUND)."""
        for n, v in (("digest", digest), ("operation_id", operation_id), ("provider", provider),
                     ("provider_account", provider_account), ("job_id", job_id),
                     ("attempt_token", attempt_token)):
            _require_str(n, v)
        key = opkey(operation_id, provider, provider_account)
        self._require_sealed(digest, key, operation_id, provider, provider_account)
        bind = {"schema": BIND_SCHEMA, "digest": digest, "opkey": key, "operation_id": operation_id,
                "provider": provider, "provider_account": provider_account, "job_id": job_id,
                "attempt_token": attempt_token, "bound_at": time.time() if now is None else now}
        try:
            _write_once(self.bind_path(digest, key, attempt_token),
                        json.dumps(bind, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        except FileExistsError:
            raise PayloadSnapshotError(
                "ATTEMPT_ALREADY_BOUND", f"l'attempt {job_id}/{attempt_token[:12]}… e' gia' legato a uno snapshot")
        return bind

    # ------------------------------------------------------------ verify
    def _require_sealed(self, digest: str, key: str, operation_id: str, provider: str,
                        provider_account: str) -> dict:
        bin_path = self.bin_path(digest)
        if not os.path.isfile(bin_path):
            raise PayloadSnapshotError("SNAPSHOT_MISSING", f"nessun snapshot per il digest {digest[:16]}…")
        persisted = _read(bin_path)
        if sha256_hex(persisted) != digest:
            raise PayloadSnapshotError(
                "DIGEST_MISMATCH", f"i byte persistiti di {digest[:16]}… non hanno quel digest: snapshot corrotto")
        seal_path = self.seal_path(digest, key)
        if not os.path.isfile(seal_path):
            raise PayloadSnapshotError(
                "SEAL_MISSING", f"snapshot {digest[:16]}… non sigillato per operazione {operation_id!r} "
                                f"/ provider {provider!r} / conto {provider_account!r}")
        seal = _read_json(seal_path)
        if (seal.get("digest"), seal.get("operation_id"), seal.get("provider"),
                seal.get("provider_account"), seal.get("bytes")) != (digest, operation_id, provider,
                                                                     provider_account, len(persisted)):
            raise PayloadSnapshotError("SEAL_BINDING_MISMATCH", "il sigillo non descrive questo snapshot")
        return seal

    def check(self, payload: bytes, *, operation_id: str, provider: str, provider_account: str,
              job_id: str, attempt_token: str) -> dict:
        """Tutte le verifiche, nessuna scrittura. Solleva PayloadSnapshotError al primo scarto."""
        payload = bytes(payload)
        digest = sha256_hex(payload)
        key = opkey(operation_id, provider, provider_account)
        seal = self._require_sealed(digest, key, operation_id, provider, provider_account)
        persisted = _read(self.bin_path(digest))
        if persisted != payload:
            raise PayloadSnapshotError(
                "EXACT_BYTES_MISMATCH", f"i byte da inviare non sono quelli persistiti per {digest[:16]}…")
        _require_str("attempt_token", attempt_token)
        bind_path = self.bind_path(digest, key, attempt_token)
        if not os.path.isfile(bind_path):
            raise PayloadSnapshotError(
                "ATTEMPT_NOT_BOUND", f"snapshot {digest[:16]}… non legato all'attempt {job_id}/{attempt_token[:12]}…")
        bind = _read_json(bind_path)
        if bind.get("attempt_token") != attempt_token or bind.get("digest") != digest \
                or bind.get("job_id") != job_id:
            raise PayloadSnapshotError(
                "ATTEMPT_TOKEN_MISMATCH", f"binding di {job_id} riferito a un altro attempt/token")
        mode = os.stat(self.bin_path(digest)).st_mode & 0o777
        return {"digest": digest, "bytes": len(payload), "opkey": key, "seal": seal, "bind": bind,
                "persisted_mode": oct(mode), "exact_bytes_equal": True,
                "digest_recomputed_on_persisted": True}

    def verify_before_send(self, payload: bytes, *, operation_id: str, provider: str,
                           provider_account: str, job_id: str, attempt_token: str,
                           now: float | None = None) -> dict:
        """Verifica immediatamente prima dell'invio + attestazione write-once (una per attempt)."""
        proof = self.check(payload, operation_id=operation_id, provider=provider,
                           provider_account=provider_account, job_id=job_id, attempt_token=attempt_token)
        att = {"schema": SEND_SCHEMA, "digest": proof["digest"], "opkey": proof["opkey"], "job_id": job_id,
               "attempt_token": attempt_token, "bytes": proof["bytes"],
               "verified_at": time.time() if now is None else now, "exact_bytes_equal": True}
        try:
            _write_once(self.send_path(proof["digest"], proof["opkey"], attempt_token),
                        json.dumps(att, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        except FileExistsError:
            raise PayloadSnapshotError(
                "SEND_ALREADY_ATTESTED", f"l'attempt {job_id} ha gia' un'attestazione di invio: "
                                        f"un secondo invio dello stesso attempt non e' autorizzato")
        proof["send_attestation"] = att
        return proof

    def audit(self, *, digest: str, operation_id: str, provider: str, provider_account: str,
              job_id: str, attempt_token: str | None) -> dict:
        """Audit (reconciliation / evidenza): lo snapshot bound a questo attempt esiste,
        e' integro e sigillato per questo contesto? Nessuna scrittura, nessuna eccezione."""
        problems: list[str] = []
        out = {"digest": digest, "job_id": job_id, "ok": False, "problems": problems,
               "send_attested": False}
        try:
            for n, v in (("digest", digest), ("operation_id", operation_id), ("provider", provider),
                         ("provider_account", provider_account), ("job_id", job_id)):
                _require_str(n, v)
            key = opkey(operation_id, provider, provider_account)
            self._require_sealed(digest, key, operation_id, provider, provider_account)
            persisted = _read(self.bin_path(digest))
            if not isinstance(attempt_token, str) or not attempt_token:
                problems.append("ATTEMPT_TOKEN_REQUIRED")
            else:
                bind_path = self.bind_path(digest, key, attempt_token)
                if not os.path.isfile(bind_path):
                    problems.append("ATTEMPT_NOT_BOUND")
                else:
                    bind = _read_json(bind_path)
                    if bind.get("job_id") != job_id or bind.get("digest") != digest:
                        problems.append("ATTEMPT_TOKEN_MISMATCH")
                out["send_attested"] = os.path.isfile(self.send_path(digest, key, attempt_token))
            out["bytes"] = len(persisted)
        except PayloadSnapshotError as e:
            problems.append(e.code)
        out["ok"] = not problems
        return out

    def listing(self) -> list[str]:
        return sorted(os.listdir(self.root))


class SnapshotGuardedTransport:
    """Avvolge il trasporto fittizio. Il marcatore di invio resta nel trasporto interno;
    qui si verifica lo snapshot persistito PRIMA di delegare `send`.

    Il contesto atteso (ledger + binding dell'attempt) e' THREAD-LOCAL: viene fissato
    da ReservationObserver.mark_submitting nello stesso thread che poi fa il submit
    (hf_batch_runtime esegue i job in thread paralleli sullo stesso adapter)."""

    def __init__(self, transport):
        self._transport = transport
        self._ctx = threading.local()

    # ---- attributi/proprieta' che il Core e i test leggono sul trasporto ----
    @property
    def inner(self):
        return self._transport

    @property
    def sent_count(self) -> int:
        return self._transport.sent_count

    @property
    def sent(self):
        return self._transport.sent

    @property
    def authorized(self):
        return self._transport.authorized

    @property
    def refused(self):
        return self._transport.refused

    def authorize(self, digest: str) -> None:
        self._transport.authorize(digest)

    # ---- contesto per-attempt ---------------------------------------------
    def expect(self, *, ledger: SnapshotLedger, operation_id: str, provider: str,
               provider_account: str, job_id: str, attempt_token: str, digest: str, clock) -> None:
        self._ctx.binding = {"ledger": ledger, "operation_id": operation_id, "provider": provider,
                             "provider_account": provider_account, "job_id": job_id,
                             "attempt_token": attempt_token, "digest": digest, "clock": clock}
        self._ctx.last_proof = None

    def clear(self) -> None:
        self._ctx.binding = None

    @property
    def last_proof(self):
        return getattr(self._ctx, "last_proof", None)

    # ---- il guard ---------------------------------------------------------
    def send(self, payload: bytes) -> str:
        from adapters.base import PayloadBindingError            # noqa: WPS433  (dopo il pin)
        b = getattr(self._ctx, "binding", None)
        try:
            if b is None:
                raise PayloadBindingError(
                    "snapshot guard: nessun attempt legato in questo thread (SNAPSHOT_MISSING): nessun invio")
            try:
                proof = b["ledger"].verify_before_send(
                    payload, operation_id=b["operation_id"], provider=b["provider"],
                    provider_account=b["provider_account"], job_id=b["job_id"],
                    attempt_token=b["attempt_token"], now=b["clock"]())
            except PayloadSnapshotError as e:
                raise PayloadBindingError(f"snapshot guard: {e}; nessun invio") from e
            if proof["digest"] != b["digest"]:
                raise PayloadBindingError(
                    f"snapshot guard: digest {proof['digest'][:16]}… != autorizzato {b['digest'][:16]}…")
            self._ctx.last_proof = proof
            return self._transport.send(payload)                  # <-- marcatore di invio (Core)
        finally:
            self._ctx.binding = None


_INSTALL_LOCK = threading.Lock()


def install_snapshot_guard(adapter) -> SnapshotGuardedTransport:
    """Avvolge una sola volta il trasporto dell'adapter (idempotente, thread-safe:
    hf_batch_runtime condivide un adapter fra thread paralleli)."""
    with _INSTALL_LOCK:
        t = getattr(adapter, "transport", None)
        if t is None:
            raise PayloadSnapshotError("TRANSPORT_REQUIRED", "l'adapter non espone un trasporto da vincolare")
        if isinstance(t, SnapshotGuardedTransport):
            return t
        guard = SnapshotGuardedTransport(t)
        adapter.transport = guard
        return guard


class SnapshotBinding:
    """Contesto P-B04 di UNA chiamata `go`: ledger, guard, identita' dell'adapter, digest sigillato.
    `bind(job, kw)` viene invocato dal proxy dello store a `mark_submitting` (kw = gli argomenti
    che il Core sta per persistire): verifica che il Core abbia calcolato lo STESSO digest
    sigillato dal runtime, lega lo snapshot all'attempt e arma il guard nel thread corrente."""

    def __init__(self, ledger: SnapshotLedger, guard: SnapshotGuardedTransport, *, operation_id: str,
                 provider: str, provider_account: str, digest: str, clock):
        self.ledger, self.guard = ledger, guard
        self.operation_id, self.provider, self.provider_account = operation_id, provider, provider_account
        self.digest, self.clock = digest, clock
        self.bound: dict | None = None

    def bind(self, job, kw: dict) -> dict:
        core_digest = kw.get("payload_digest")
        if core_digest != self.digest:
            raise PayloadSnapshotError(
                "SERIALIZATION_DRIFT",
                f"digest calcolato dal Core {str(core_digest)[:16]}… != snapshot sigillato "
                f"{self.digest[:16]}…: l'adapter ha serializzato byte diversi fra sigillo e submit")
        if kw.get("provider") != self.provider or kw.get("provider_account") != self.provider_account:
            raise PayloadSnapshotError(
                "IDENTITY_DRIFT", f"ownership {kw.get('provider')}/{kw.get('provider_account')} != "
                                  f"sigillo {self.provider}/{self.provider_account}")
        token = kw.get("attempt_token")
        self.bound = self.ledger.bind_attempt(
            digest=self.digest, operation_id=self.operation_id, provider=self.provider,
            provider_account=self.provider_account, job_id=job.job_id, attempt_token=token,
            now=kw.get("now"))
        self.guard.expect(ledger=self.ledger, operation_id=self.operation_id, provider=self.provider,
                          provider_account=self.provider_account, job_id=job.job_id,
                          attempt_token=token, digest=self.digest, clock=self.clock)
        return self.bound
