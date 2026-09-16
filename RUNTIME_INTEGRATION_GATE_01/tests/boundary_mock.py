"""P-B01 — SPENDER BOUNDARY MOCK (solo laboratorio, nessuna credenziale reale).

Principio: l'ORCHESTRATOR propone intenti strutturati; il WORKER (spender) e'
l'unico componente che possiede il segreto fittizio, costruisce l'adapter,
consuma i permessi e chiama il trasporto fittizio attraverso il Core.

    orchestrator  --JSON (Pipe)-->  worker  --run_job-->  Core  --> MockTransport

Il worker accetta SOLO messaggi JSON con uno schema chiuso (`ALLOWED_OPS`,
chiavi ammesse, valori scalari). Nessuna shell, nessun argv, nessun path.
Un messaggio fuori schema viene rifiutato PRIMA di qualunque azione.

COSA QUESTO MOCK DIMOSTRA (VERIFIED, livello protocollo):
  - il worker non esegue comandi arbitrari (rifiuto + 0 subprocess, sentinella);
  - un permesso di nuovo tentativo e' consumato una sola volta (replay rifiutato);
  - un nuovo tentativo senza motivo e' rifiutato;
  - il segreto non attraversa mai il protocollo (le risposte non lo contengono);
  - l'identita' del conto deriva dal segreto del worker, non da un campo del client;
  - (CR-01) ogni richiesta spendibile porta un operation_id;
  - (CR-02/CR-08) l'ENVELOPE e' derivato dallo scope dell'operazione
    (autorizzazione fidata LAB); l'IMPORTO deriva ESCLUSIVAMENTE dal listino
    fidato LAB del worker (`LAB_PRICE_TABLE`, SKU = modello): il client puo'
    chiedere una quote, non fissarne l'importo (`amount` nel messaggio quote ->
    PROTOCOL refused); `budget_units` presentato al submit viene solo
    confrontato. Una quote gratuita esiste solo come fixture fidata a prezzo
    zero (`fake_model_free`).

COSA QUESTO MOCK NON DIMOSTRA (BLOCKED_ENVIRONMENT, dichiarato dal test):
  - che l'orchestrator NON POSSA leggere il segreto, modificare il worker o
    invocare direttamente il dispatch: i due processi girano con lo stesso
    utente sullo stesso filesystem. Il test T29 tenta esplicitamente questi
    bypass e li registra come POSSIBILI. Un `if` in Python non e' un confine
    di privilegio.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys

GATE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if GATE_ROOT not in sys.path:
    sys.path.insert(0, GATE_ROOT)

ALLOWED_OPS = ("submit", "quote", "status", "stop")
ALLOWED_KEYS = {
    "submit": {"op", "prompt", "model", "intent", "reason", "permit_id", "operation_id",
               "budget_units", "envelope_id", "adapter", "quote_id"},
    "quote": {"op", "prompt", "model", "operation_id"},     # CR-08: nessun `amount` dal client
    "status": {"op", "prompt", "model"},
    "stop": {"op"},
}
SCALAR = (str, int, bool, type(None))


def validate_request(raw) -> tuple[dict | None, str | None]:
    """Schema chiuso: JSON oggetto, op ammessa, solo chiavi ammesse, solo scalari."""
    if not isinstance(raw, str):
        return None, "PROTOCOL: solo stringhe JSON"
    try:
        msg = json.loads(raw)
    except ValueError:
        return None, "PROTOCOL: JSON non valido"
    if not isinstance(msg, dict):
        return None, "PROTOCOL: atteso un oggetto"
    op = msg.get("op")
    if op not in ALLOWED_OPS:
        return None, f"PROTOCOL: op {op!r} non ammessa (ammesse: {ALLOWED_OPS})"
    extra = set(msg) - ALLOWED_KEYS[op]
    if extra:
        return None, f"PROTOCOL: chiavi non ammesse {sorted(extra)}"
    if op == "submit":
        # DELTA 03: al confine dello spender NON esiste un intent implicito spendibile.
        # `submit` senza `intent` esplicito e' rifiutato a livello di protocollo, prima
        # di qualunque effetto economico (nessun go(), nessuna quote, nessun submit).
        intent = msg.get("intent")
        if intent is None:
            return None, "PROTOCOL: INTENT_REQUIRED (submit senza intent esplicito: resume | new_attempt)"
        if intent not in ("resume", "new_attempt"):
            return None, f"PROTOCOL: INTENT_REQUIRED (intent {intent!r} non ammesso: resume | new_attempt)"
    for k, v in msg.items():
        if not isinstance(v, SCALAR) or isinstance(v, str) and len(v) > 512:
            return None, f"PROTOCOL: valore non scalare o troppo lungo in {k!r}"
    if op == "submit":
        if not isinstance(msg.get("prompt"), str) or not msg["prompt"]:
            return None, "PROTOCOL: prompt obbligatorio"
        if msg.get("adapter", "fake") not in ("fake", "lost"):
            return None, "PROTOCOL: adapter non ammesso"
    return msg, None


def worker_main(conn, db: str, core_path: str, secret_dir: str, canary_home: str) -> None:
    """Processo SPENDER. Possiede il segreto fittizio; non lo rivela mai."""
    from tests import audit_sentinel
    audit_sentinel.install(canary_home)
    from runtime import go_candidate
    from runtime.authorization import (DEFAULT_LAB_AUTHORIZATION, LAB_QUOTE_UNIT,
                                       AuthorizationRefused, lab_price_for)
    from tests.worker import make_inputs
    os.makedirs(secret_dir, exist_ok=True)
    secret = "FAKE_SPENDER_SECRET_" + secrets.token_hex(16)
    secret_path = os.path.join(secret_dir, "worker_secret.json")
    with open(secret_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"fake_secret": secret}))
    os.chmod(secret_path, 0o600)
    # L'identita' del conto deriva dal segreto: chi non ha il segreto non la sceglie.
    account_id = "acct_" + hashlib.sha256(secret.encode()).hexdigest()[:12]
    if core_path not in sys.path:
        sys.path.insert(0, core_path)
    from adapters.base import GenSpec
    from adapters.fake import FakeAdapter
    from registry.reservations import SqliteReservationStore
    from runtime.genspec_bridge import build_genspec
    adapters = {}
    authority = SqliteReservationStore(db)     # lato AUTORITA': envelope e quote li scrive il worker

    def adapter_for(kind):
        if kind not in adapters:
            if kind == "fake":
                adapters[kind] = FakeAdapter(account_id=account_id)
            else:
                class Lost(FakeAdapter):
                    def submit(self, gs):
                        self.submits += 1
                        raise TimeoutError("risposta persa (mock)")
                adapters[kind] = Lost(account_id=account_id)
        return adapters[kind]

    served = 0
    while True:
        raw = conn.recv()
        served += 1
        msg, err = validate_request(raw)
        if err:
            # DELTA 03: anche il rifiuto di protocollo riferisce i submit (evidenza "zero effetti")
            conn.send({"ok": False, "refused": err, "served": served, "submits": adapter_for("fake").submits})
            continue
        if msg["op"] == "stop":
            conn.send({"ok": True, "stopped": True, "served": served,
                       "violations": audit_sentinel.violations(),
                       "account_id": account_id, "secret_path": secret_path})
            return
        over = {"model": msg["model"]} if msg.get("model") else {}
        try:
            if msg["op"] == "status":
                latest = authority.find_latest_by_spec(
                    build_genspec(make_inputs(msg["prompt"], **over), GenSpec).spec_key)
                conn.send({"ok": True, "latest": latest.to_dict() if latest else None})
                continue
            if msg["op"] == "quote":
                # QUOTE FIDATA (CR-08): emessa dal worker, importo SOLO dal listino fidato
                # LAB (SKU = modello), legata a operazione/spec/envelope derivato/unita'.
                op = msg.get("operation_id")
                env = DEFAULT_LAB_AUTHORIZATION.envelope_for(op)
                authority.open_envelope(env, 100, unit=LAB_QUOTE_UNIT, scope=op.split(":")[0])
                gs = build_genspec(make_inputs(msg["prompt"], **over), GenSpec)
                amount = lab_price_for(gs.model)
                qid = authority.issue_quote(operation_id=op, spec_key=gs.spec_key, envelope_id=env,
                                            amount=amount, unit=LAB_QUOTE_UNIT)
                conn.send({"ok": True, "quote_id": qid, "amount": amount, "envelope_id": env,
                           "price_source": "LAB_PRICE_TABLE", "sku": gs.model})
                continue
            res = go_candidate.go(
                make_inputs(msg["prompt"], **over), adapter=adapter_for(msg.get("adapter", "fake")),
                provider_mode="fake", store_path=db, core_path=core_path, max_polls=3,
                intent=msg["intent"], reason=msg.get("reason"),    # DELTA 03: mai un default
                permit_id=msg.get("permit_id"), auto_permit=msg.get("permit_id") is None,
                operation_id=msg.get("operation_id"),
                # CR-02: l'importo NON e' scelto dal client. Se lo presenta, viene solo
                # confrontato con la quote; se lo omette, vale la quote. Mai "or 0".
                budget_units=(int(msg["budget_units"]) if msg.get("budget_units") is not None else None),
                envelope_id=msg.get("envelope_id"), quote_id=msg.get("quote_id"),
                authorization=DEFAULT_LAB_AUTHORIZATION)
            out = {"ok": True, "outcome": res.outcome, "state": res.state, "job_id": res.job_id,
                   "reservation_outcome": res.reservation_outcome, "permit_id": res.permit_id,
                   "provider_account": res.persisted.get("provider_account"),
                   "governance": res.governance, "envelope_id": res.envelope_id,
                   "quote_id": res.quote_id, "budget_units": res.budget_units,
                   "resumed": res.resumed, "spec_key": res.spec_key,
                   "requested_spec_key": res.requested_spec_key,
                   "legacy_resume_as_start": res.legacy_resume_as_start,
                   "submits": adapter_for(msg.get("adapter", "fake")).submits}
        except go_candidate.IntentRefused as e:
            out = {"ok": False, "error": "IntentRefused", "code": e.code, "message": str(e)}
        except AuthorizationRefused as e:
            out = {"ok": False, "error": "AuthorizationRefused", "code": e.code, "message": str(e)}
        except Exception as e:                              # noqa: BLE001
            out = {"ok": False, "error": type(e).__name__, "message": str(e)}
        # Il conteggio dei submit dell'adapter e' evidenza anche nei rifiuti.
        out.setdefault("submits", adapter_for(msg.get("adapter", "fake")).submits)
        # Il segreto non deve MAI comparire in una risposta.
        assert secret not in json.dumps(out, default=str)
        conn.send(out)
