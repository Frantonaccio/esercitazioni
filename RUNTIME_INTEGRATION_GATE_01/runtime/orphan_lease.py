"""ORPHAN RESERVED LEASE — classificazione read-only. NESSUNA policy di reclaim, NESSUN dispatch.

Riproduzione (evidence/pre_fix/reproduction_baseline.json["ORPHAN_RESERVED"]): una riga
RESERVED committata da `reserve_or_get_live` il cui processo muore PRIMA di
`mark_submitting` non ha intento di submit persistito (provider '', attempt_token
NULL, payload_digest NULL, submit_intent_at NULL). Da quel momento:

    resume                        -> EXISTING_LIVE_JOB/reserved-no-dispatch (per sempre)
    new_attempt (stessa operazione) -> LIVE_OR_UNCERTAIN_ATTEMPT (per sempre)
    recover_orphaned_submits      -> la ignora (agisce SOLO su RESERVED con intento)
    due_for_reconcile             -> la elenca; nessun consumatore la porta altrove
    reserved_units                -> il budget resta impegnato

STATI formalizzati (derivati dai campi che il Core espone su `Job`; `submit_intent_at`
non e' in `Job`, ma `mark_submitting` scrive nella STESSA transazione provider,
provider_account, payload_digest, attempt_token e submit_intent_at: i primi quattro
sono quindi il segnale equivalente):

    RESERVED_NO_INTENT    RESERVED, nessun provider/token/digest: NESSUN invio e' avvenuto
                          attraverso il percorso governato (il Core persiste l'intento PRIMA
                          di autorizzare i byte e PRIMA del marcatore di invio: RV02/RV05).
                          E' l'orfana di questo gap.
    RESERVED_WITH_INTENT  RESERVED con intento: dominio di `recover_orphaned_submits`
                          (-> SUBMIT_UNKNOWN, riconciliazione richiesta). NON e' questo gap.
    NOT_RESERVED          qualunque altro stato.

OWNERSHIP: una RESERVED_NO_INTENT ha `operation_id` (e quote/permit consumati nella
transazione di prenotazione) ma NESSUNA identita' di attempt (nessun token): non e'
distinguibile, dai soli dati persistiti, da una prenotazione VIVA fatta da un altro
processo un istante fa che sta per chiamare `mark_submitting`. L'unico
discriminante e' il TEMPO (`submitted_at` = istante della prenotazione), e una
finestra di lease non e' definita da nessuna parte (ne' Core ne' Runtime).

PERCHE' NON C'E' UNA RECLAIM QUI: una reclaim corretta e' possibile (RESERVED -> FAILED
con settlement 0 tramite il percorso esplicito del Core, protetta dal CAS sulla
revisione: se `mark_submitting` vince la corsa la reclaim ottiene StaleWrite; se
vince la reclaim, `mark_submitting` ottiene StaleWrite PRIMA di autorizzare/inviare)
ma richiede una LEASE AUTHORITY: chi fissa la finestra, chi puo' invocarla, con
quale evidenza. Questa e' una decisione umana, non del gate. Finche' non esiste:
STILL_OPEN. Qui si classifica e si riferisce, non si decide. Vedi ORPHAN_LEASE.md.

ZERO BLIND RETRY: qualunque futura reclaim NON crea un nuovo attempt: la spesa
successiva resta intent="new_attempt" + reason + quote + permit + autorizzazione.
"""
from __future__ import annotations

RESERVED_NO_INTENT = "RESERVED_NO_INTENT"
RESERVED_WITH_INTENT = "RESERVED_WITH_INTENT"
NOT_RESERVED = "NOT_RESERVED"
RECLAIM_POLICY = "NOT_AUTHORIZED"       # nessuna reclaim implementata: decisione umana pendente


def classify_attempt(job, now: float) -> dict:
    """Classificazione pura di un Job del Core. Nessun I/O, nessuna scrittura."""
    state = job.state.value
    if state != "RESERVED":
        cls = NOT_RESERVED
    elif job.provider or job.attempt_token or job.payload_digest:
        cls = RESERVED_WITH_INTENT
    else:
        cls = RESERVED_NO_INTENT
    return {"job_id": job.job_id, "operation_id": job.operation_id, "state": state, "class": cls,
            "provider": job.provider, "attempt_token": job.attempt_token,
            "payload_digest": job.payload_digest, "reserved_at": job.submitted_at,
            "age_s": (now - job.submitted_at) if job.submitted_at else None,
            "exits_available": _exits(cls), "reclaim_policy": RECLAIM_POLICY}


def _exits(cls: str) -> list[str]:
    if cls == RESERVED_WITH_INTENT:
        return ["recover_orphaned_submits -> SUBMIT_UNKNOWN", "reconcile (autenticata) -> stato scoperto"]
    if cls == RESERVED_NO_INTENT:
        return []           # nessuna uscita esistente: e' il gap
    return ["n/a"]


def inventory(store, operation_ids, now: float) -> list[dict]:
    """Ultimo attempt di ogni operazione data, classificato. Solo letture del Protocol."""
    out = []
    for op in operation_ids:
        latest = store.find_latest_by_operation(op)
        if latest is not None:
            out.append(classify_attempt(latest, now))
    return out
