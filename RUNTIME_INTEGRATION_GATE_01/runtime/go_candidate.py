"""Candidate del verbo `go` di hf_batch, ricablato sul Core C26.

    go(...)
      1. FAKE MODE gate           -> REAL_PROVIDER_DISABLED se non 'fake'
      2. CORE PIN gate            -> CORE_PIN_MISMATCH / STALE_CORE_PIN / CORE_WORKTREE_DIRTY
                                     (pin allo SHA Git reale del Core promosso + working tree
                                      pulito; nessun digest LAB sostituisce lo SHA)
      3. import del Core          -> solo dopo 1 e 2
      4. GenSpec dal bridge       -> solo dati deterministici
      5. SqliteReservationStore   -> file in RUNTIME_INTEGRATION_GATE_01/state/
      6. OPERAZIONE (CR-01/CR-09) -> `operation_id` OBBLIGATORIO. RESUME rilegge l'ultimo
                                     tentativo dell'OPERAZIONE e lo riprende con `resume_job`
                                     del Core: NESSUNA nuova quote/permit/reservation, NESSUN
                                     nuovo submit (SUBMIT_UNKNOWN e RESERVED restano tali),
                                     ownership verificata; il risultato riferisce il job
                                     realmente ripreso (`spec_key = latest.spec_key`,
                                     `requested_spec_key` a parte). DELTA 03: nel percorso
                                     GOVERNED, RESUME senza attempt persistito = rifiuto
                                     NO_EXISTING_ATTEMPT (RESUME non e' START); la PRIMA spesa
                                     e ogni NEW_ATTEMPT richiedono intent="new_attempt" con
                                     motivo esplicito + permesso monouso legato all'operazione
                                     e passano dall'autorizzazione economica. Resume-as-start
                                     resta SOLO LEGACY_LAB, marcato `legacy_resume_as_start`.
                                     Il Core rifiuta una spec viva sotto un'altra operazione
                                     (OperationConflict) e un'operazione incerta con spec diversa
                                     (OperationBusy): cambiare run/modello/spec senza operation_id
                                     non e' possibile, perche' senza operation_id non si parte.
      1b. LEGACY SPEND PATH       -> authorization=None (LEGACY_LAB) e' ammesso SOLO se
                                     provider_gate.LEGACY_LAB_SPEND_PATH lo consente
                                     (LEGACY_SPEND_PATH_DISABLED altrimenti, prima di ogni effetto)
      7c. SNAPSHOT (P-B04)        -> byte canonici del payload persistiti write-once e sigillati
                                     (runtime/payload_snapshot.py); a mark_submitting legati
                                     all'attempt; riverificati byte per byte prima del send
      7. AUTORIZZAZIONE (CR-02)   -> percorso GOVERNATO (authorization dato): envelope DERIVATO dallo
                                     scope dell'operazione (un envelope presentato viene solo
                                     validato); importo DERIVATO da una quote fidata (quote_id),
                                     mai scelto dal client; zero solo se attestato dalla quote.
                                     Percorso LEGACY_LAB (authorization=None): budget/envelope_units
                                     grezzi, SOLO test di compatibilita', riferito come tale.
      8. Core run_job(...)        -> reserve_or_get_live -> submit -> poll -> put
      9. GoResult                 -> stato persistito, letto dallo store

COSA QUESTO MODULO NON FA (ed e' verificato dal test AST T19):
  - non chiama find_live_by_spec;
  - non chiama adapter.submit;
  - non definisce stati di job, esiti di prenotazione, budget;
  - non apre sqlite3, non scrive SQL, non tiene una reservation JSON parallela;
  - non usa metodi/argomenti dello store non dichiarati dal Protocol del Core (CR-03).

`ReservationObserver` e' un proxy trasparente sullo store del Core: registra
l'esito che il CORE ha deciso in `reserve_or_get_live`, cosi' il runtime puo'
riferirlo senza rifare la lettura "c'e' un job vivo?" per conto suo. Delega
tutto, non decide nulla.

NOTA SU hf_batch.py: questo modulo e' il candidate del solo percorso
`go -> Core`. E' innestato nella copia `runtime/hf_batch_runtime.py` del vero
P2 hf_batch.py (SHA256 637f3a80…3ea7d1, handoff 2026-09-16) tramite
`runtime/hf_batch_bridge.py`, che deriva `GoInputs` dai dati reali del job.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from runtime.authorization import AuthorizationRefused, LabAuthorization
from runtime.core_pin import REQUIRED_CORE_SHA, require_core_verdict
from runtime.genspec_bridge import GoInputs, build_genspec
from runtime.payload_snapshot import (PayloadSnapshotError, SnapshotBinding, SnapshotLedger,
                                      install_snapshot_guard, ledger_dir_for)
from runtime.provider_gate import (require_fake_adapter, require_fake_mode,
                                   require_legacy_lab_spend_path)

GATE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(GATE_ROOT, "state")
DEFAULT_CORE_PATH = os.environ.get("CREATIVE_OS_CORE_PATH", "/home/user/creative-os")

INTENT_RESUME = "resume"
INTENT_NEW_ATTEMPT = "new_attempt"
INTENTS = (INTENT_RESUME, INTENT_NEW_ATTEMPT)
GOVERNED_LAB = "GOVERNED_LAB"      # envelope derivato + quote fidata (CR-02)
LEGACY_LAB = "LEGACY_LAB"          # budget/envelope_units grezzi: SOLO compatibilita'/test


class IntentRefused(RuntimeError):
    """L'intento non e' eseguibile cosi' com'e': nessun submit, nessuna reservation."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass
class GoResult:
    """Cio' che `go` riferisce. Ogni valore viene dal Core o dallo store, mai inventato."""
    reservation_outcome: str        # RESERVED_NEW | EXISTING_LIVE_JOB (deciso dal Core) | NONE (resume di un terminale)
    job_id: str
    provider_job_id: str | None
    provider: str
    state: str                      # JobState.value persistito
    spec_key: str
    core_sha: str
    store_path: str
    persisted: dict[str, Any] = field(default_factory=dict)
    intent: str = INTENT_RESUME
    resumed_terminal: bool = False  # RESUME di un'operazione gia' conclusa: nessun submit
    permit_id: str | None = None
    operation_id: str | None = None
    core_pin: str = "CORE_PIN_OK"   # unico esito che supera il gate (SHA reale + tree pulito)
    governance: str = LEGACY_LAB    # GOVERNED_LAB | LEGACY_LAB
    envelope_id: str | None = None
    quote_id: str | None = None
    budget_units: int | None = None  # importo effettivamente prenotato (dalla quote se governato)
    resumed: bool = False           # CR-09: tentativo esistente ripreso (nessuna nuova spesa/dispatch)
    requested_spec_key: str | None = None   # la spec presentata in QUESTA chiamata (audit); mai attribuita al job ripreso
    # DELTA 03: `resume` su un'operazione SENZA attempt ha avviato una prima spesa. Questo
    # accade SOLO nel percorso LEGACY_LAB (compatibilita' T01-T23/P2) ed e' marcato qui;
    # nel percorso GOVERNED e' un rifiuto fail-closed (NO_EXISTING_ATTEMPT), mai un avvio.
    legacy_resume_as_start: bool = False
    # P-B04: snapshot exact-byte del payload autorizzato (sigillo + attestazione pre-send), se
    # questa chiamata ha raggiunto il trasporto. None su resume/EXISTING_LIVE_JOB.
    payload_snapshot: dict | None = None

    @property
    def outcome(self) -> str:
        """Etichetta di sintesi per il chiamante di hf_batch."""
        if self.resumed_terminal:
            return f"RESUMED/{self.state}"
        if self.reservation_outcome == "EXISTING_LIVE_JOB":
            if self.state == "SUBMIT_UNKNOWN":
                return "EXISTING_LIVE_JOB/reconciliation-required"
            if self.state == "RESERVED":
                return "EXISTING_LIVE_JOB/reserved-no-dispatch"   # CR-09: nessun submit automatico, nessun lease
            if self.state in ("SUCCEEDED", "FAILED", "TIMEOUT"):
                return self.state            # job di un altro chiamante, portato a terminale dal poll
            return "EXISTING_LIVE_JOB"
        return self.state


class ReservationObserver:
    """Proxy sullo store del Core. Registra l'esito deciso dal Core, delega tutto.

    P-B04 (PROVIDER / EXECUTION BOUNDARY HARDENING): a `mark_submitting` — l'istante in cui
    il Core persiste chi tenta cosa, PRIMA di autorizzare i byte e PRIMA del marcatore di
    invio — il proxy verifica che il digest calcolato dal Core coincida con lo snapshot
    exact-byte sigillato dal runtime, lega lo snapshot all'attempt (job_id + attempt_token,
    write-once) e arma il guard del trasporto per QUESTO thread. Una deriva qui e' un
    rifiuto PRIMA di qualunque effetto esterno: l'attempt viene chiuso come
    rifiutato-prima-dell'invio (settlement 0 attestato) tramite il percorso esplicito del
    Core (`mark_refused_before_send`), cosi' il rifiuto non lascia una RESERVED orfana."""

    def __init__(self, inner):
        self._inner = inner
        self._snapshot = None
        self.last_outcome = None

    def attach_snapshot(self, binding: SnapshotBinding) -> None:
        self._snapshot = binding

    def reserve_or_get_live(self, spec, **kw):
        outcome, job = self._inner.reserve_or_get_live(spec, **kw)
        self.last_outcome = outcome
        return outcome, job

    def mark_submitting(self, job, **kw):
        if self._snapshot is not None:
            try:
                self._snapshot.bind(job, kw)
            except PayloadSnapshotError as e:
                now = kw.get("now")
                reason = f"snapshot guard: {e} (rifiutato prima di autorizzare/inviare)"
                self._inner.record_anomaly(job.job_id, "SNAPSHOT_REFUSED_BEFORE_SEND",
                                           {"code": e.code, "message": str(e),
                                            "core_digest": kw.get("payload_digest"),
                                            "sealed_digest": self._snapshot.digest}, now)
                self._inner.mark_refused_before_send(job, reason, now)
                raise
        return self._inner.mark_submitting(job, **kw)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _snapshot_report(seal: dict, proof: dict | None, ledger: SnapshotLedger) -> dict:
    """Evidenza P-B04 riferita dal runtime: sigillo + (se l'invio e' avvenuto) attestazione pre-send."""
    return {"ledger_dir": ledger.root, "digest": seal["digest"], "bytes": seal["bytes"],
            "sealed_at": seal.get("sealed_at"), "opkey": seal.get("opkey"),
            "send_verified": proof is not None,
            "send_attestation": (proof or {}).get("send_attestation"),
            "persisted_mode": (proof or {}).get("persisted_mode")}


def _ensure_core_on_path(core_path: str) -> None:
    if core_path not in sys.path:
        sys.path.insert(0, core_path)


def go(inputs: GoInputs, *, adapter, provider_mode: str, store_path: str,
       core_path: str = DEFAULT_CORE_PATH, required_core_sha: str = REQUIRED_CORE_SHA,
       budget_units: int | None = None, envelope_units: int | None = None,
       max_polls: int = 20, clock=time.time,
       intent: str = INTENT_RESUME, reason: str | None = None,
       permit_id: str | None = None, auto_permit: bool = False,
       operation_id: str | None = None, envelope_id: str | None = None,
       quote_id: str | None = None, authorization: LabAuthorization | None = None) -> GoResult:
    """Candidate `go`. Fail-closed su provider, pin, operazione e autorizzazione; poi consuma il Core."""
    # 1) FAKE MODE: prima di tutto, prima di qualunque import del Core.
    require_fake_mode(provider_mode)
    if intent not in INTENTS:
        raise IntentRefused("UNKNOWN_INTENT", f"intento {intent!r} non ammesso: {INTENTS}")
    # CR-01: nessuna operazione spendibile senza identita' di operazione.
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise IntentRefused("OPERATION_ID_REQUIRED",
                            "operation_id obbligatorio per ogni operazione (RESUME e NEW_ATTEMPT)")
    # 1b) LEGACY SPEND PATH: il percorso LEGACY_LAB (authorization=None) e' chiudibile
    #     fail-closed (provider_gate.LEGACY_LAB_SPEND_PATH). Verificato PRIMA di pin, import,
    #     store: se chiuso, nessun effetto di alcun tipo (LEGACY_SPEND_PATH_DISABLED).
    if authorization is None:
        require_legacy_lab_spend_path()
    # 2) CORE PIN: il Core non autorizzato non viene nemmeno importato.
    verdict = require_core_verdict(core_path, required_core_sha)
    core_sha = verdict.observed
    core_pin = verdict.code
    # 3) Import del Core canonical.
    _ensure_core_on_path(core_path)
    from adapters.base import GenSpec                       # noqa: WPS433
    from adapters.fake import FakeAdapter                   # noqa: WPS433
    from registry.reservations import SqliteReservationStore  # noqa: WPS433
    from transport.pipeline import resume_job, run_job      # noqa: WPS433
    # 3b) L'adapter deve essere il FakeAdapter del Core o una sottoclasse.
    require_fake_adapter(adapter, FakeAdapter)
    # 4) Spec deterministica.
    spec = build_genspec(inputs, GenSpec)
    # 5) Store durevole di riferimento, confinato in state/.
    store_path = os.path.abspath(store_path)
    if not store_path.startswith(STATE_DIR + os.sep):
        raise ValueError(f"store fuori da state/: {store_path}")
    os.makedirs(os.path.dirname(store_path), exist_ok=True)
    observer = ReservationObserver(SqliteReservationStore(store_path))
    store = observer
    # 6) INTENTO sull'OPERAZIONE (RV03 + CR-01). Il Core dice qual e' l'ultimo
    #    tentativo di QUESTA operazione, qualunque spec avesse.
    latest = store.find_latest_by_operation(operation_id)
    governance = GOVERNED_LAB if authorization is not None else LEGACY_LAB
    legacy_resume_as_start = False
    if intent == INTENT_RESUME:
        if latest is not None:
            # CR-09: RESUME/RECOVERY di un tentativo GIA' AUTORIZZATO. Nessuna nuova
            # quote, nessun permit, nessuna reservation, nessun nuovo submit: il Core
            # riprende il job persistito (ownership verificata) e lo riferisce cosi'
            # com'e'. La spec presentata e' solo audit (`requested_spec_key`).
            was_terminal = latest.state.terminal
            job = resume_job(adapter, latest.job_id, store, clock=clock, max_polls=max_polls)
            persisted = store.get(job.job_id)
            return GoResult(
                reservation_outcome="NONE" if was_terminal else "EXISTING_LIVE_JOB",
                job_id=persisted.job_id, provider_job_id=persisted.provider_job_id,
                provider=persisted.provider, state=persisted.state.value,
                spec_key=persisted.spec_key, core_sha=core_sha, store_path=store_path,
                persisted=persisted.to_dict(), intent=intent, resumed_terminal=was_terminal,
                operation_id=persisted.operation_id, core_pin=core_pin, governance=governance,
                envelope_id=None, quote_id=persisted.quote_id, budget_units=None,
                resumed=True, requested_spec_key=spec.spec_key)
        # DELTA 03 (HUMAN REVIEW): RESUME usa ESCLUSIVAMENTE un attempt persistito. Senza
        # attempt, RESUME non e' START: nel percorso GOVERNED e' un rifiuto fail-closed
        # PRIMA di qualunque effetto (nessun envelope, quote, permit, reservation, ledger,
        # submit). La prima spesa richiede intent="new_attempt" con reason esplicito.
        if authorization is not None:
            raise IntentRefused(
                "NO_EXISTING_ATTEMPT",
                f"nessun tentativo persistito per l'operazione {operation_id!r}: RESUME non "
                f"autorizza una prima spesa (prima generazione = intent='new_attempt' con reason)")
        # LEGACY_LAB ONLY (compatibilita' T01-T23 / P2): resume-as-start, marcato nel risultato.
        legacy_resume_as_start = True
        used_permit = None
    else:
        if not reason or not isinstance(reason, str):
            raise IntentRefused("REASON_REQUIRED", "un nuovo tentativo richiede un motivo esplicito")
        if latest is not None and latest.state.live:
            raise IntentRefused(
                "LIVE_OR_UNCERTAIN_ATTEMPT",
                f"il tentativo {latest.job_id} e' {latest.state.value}: nessun nuovo submit "
                f"finche' non e' concluso o riconciliato (usare RESUME)")
        if permit_id is None and not auto_permit:
            raise IntentRefused("PERMIT_REQUIRED",
                                "nuovo tentativo senza permesso e senza delega automatica")
        used_permit = permit_id     # None = delega: emesso al punto 7b, DOPO l'autorizzazione economica
    # 7) AUTORIZZAZIONE ECONOMICA (CR-02).
    if authorization is not None:
        if envelope_units is not None:
            raise AuthorizationRefused("LEGACY_ENVELOPE_UNITS_FORBIDDEN",
                                       "envelope_units grezzo non ammesso nel percorso governato")
        envelope_id = authorization.validate_envelope(operation_id, envelope_id)
        if quote_id is None:
            raise AuthorizationRefused("QUOTE_REQUIRED",
                                       "nessuna quote fidata presentata: nessun importo, nessun submit")
        q = store.quote(quote_id)
        if q is None:
            raise AuthorizationRefused("QUOTE_UNKNOWN", f"quote sconosciuta: {quote_id}")
        if q.get("consumed_by"):
            raise AuthorizationRefused("QUOTE_ALREADY_CONSUMED",
                                       f"quote {quote_id} gia' consumata da {q['consumed_by']}: "
                                       f"nuova spesa = nuova quote")
        # importo: SOLO dalla quote. Un importo presentato dal client viene confrontato,
        # mai adottato. Zero e' valido solo perche' la quote lo attesta.
        amount = int(q["amount"])
        if budget_units is not None and budget_units != amount:
            raise AuthorizationRefused(
                "BUDGET_NOT_QUOTED",
                f"importo presentato {budget_units} diverso dalla quote {quote_id} ({amount} {q['unit']})")
        # il binding completo (operazione, spec, envelope, importo, scadenza) e' lo
        # stesso controllo che il Core ripete nella transazione di prenotazione.
        try:
            store.check_quote_binding(q, quote_id=quote_id, operation_id=operation_id,
                                      spec_key=spec.spec_key, envelope_id=envelope_id,
                                      budget_units=amount, now=clock())
        except Exception as e:                              # noqa: BLE001
            raise AuthorizationRefused("QUOTE_BINDING", str(e)) from e
        budget_units = amount
    else:
        budget_units = 0 if budget_units is None else budget_units
    # 7b) Delega (DELTA 03: emessa SOLO dopo che l'autorizzazione economica e' passata, cosi'
    #     un rifiuto pre-reservation non lascia permessi emessi): permesso distinto, monouso
    #     e LEGATO all'operazione; e' il Core a consumarlo nella prenotazione.
    if intent == INTENT_NEW_ATTEMPT and used_permit is None:
        used_permit = store.issue_permit(spec.spec_key, reason, operation_id=operation_id)
    # 7c) P-B04: SNAPSHOT EXACT-BYTE. I byte che il trasporto inviera' (adapter.serialize:
    #     la stessa funzione che il Core chiama in run_job) sono persistiti write-once,
    #     content-addressed, sigillati per operazione/spec/provider/conto. A mark_submitting
    #     il proxy lega lo snapshot all'attempt; immediatamente prima del send il guard del
    #     trasporto rilegge i byte persistiti e li confronta byte per byte (vedi
    #     runtime/payload_snapshot.py). Qualunque scarto -> rifiuto PRIMA del marcatore.
    provider_account = str(getattr(adapter, "account_id", "") or "")
    ledger = SnapshotLedger(ledger_dir_for(store_path))
    seal = ledger.seal(adapter.serialize(spec), operation_id=operation_id, spec_key=spec.spec_key,
                       provider=adapter.name, provider_account=provider_account, now=clock())
    guard = install_snapshot_guard(adapter)
    observer.attach_snapshot(SnapshotBinding(ledger, guard, operation_id=operation_id,
                                             provider=adapter.name, provider_account=provider_account,
                                             digest=seal["digest"], clock=clock))
    # 8) Il Core fa tutto: prenotazione atomica (operazione, permesso, quote,
    #    envelope), submit, poll, persistenza.
    job = run_job(adapter, spec, store, clock=clock, max_polls=max_polls,
                  budget_units=budget_units, envelope_units=envelope_units,
                  envelope_id=envelope_id, permit_id=used_permit, operation_id=operation_id,
                  quote_id=quote_id)
    # 9) Lo stato riferito e' quello PERSISTITO, riletto dallo store.
    persisted = store.get(job.job_id)
    return GoResult(
        reservation_outcome=store.last_outcome.value,
        job_id=job.job_id, provider_job_id=persisted.provider_job_id,
        provider=persisted.provider, state=persisted.state.value,
        spec_key=spec.spec_key, core_sha=core_sha, store_path=store_path,
        persisted=persisted.to_dict(), intent=intent, permit_id=used_permit,
        operation_id=persisted.operation_id, core_pin=core_pin, governance=governance,
        envelope_id=envelope_id, quote_id=persisted.quote_id, budget_units=budget_units,
        resumed=False, requested_spec_key=spec.spec_key,
        legacy_resume_as_start=legacy_resume_as_start,
        payload_snapshot=_snapshot_report(seal, guard.last_proof, ledger))
