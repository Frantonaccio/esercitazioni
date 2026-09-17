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

MECCANISMO vs POLICY (PROVIDER BOUNDARY GATE — OPEN-GAP CLOSURE, 2026-09-17)
---------------------------------------------------------------------------
Da questa fase il MECCANISMO esiste ed e' verificato parametricamente
(`LeasePolicy` + `reclaim_orphan_reserved`): ownership, lease timestamp, lease
identity, authority esplicita, fencing token + CAS sulla revisione, recovery,
zero blind retry, sicurezza in concorrenza e su crash.

La POLICY — quanto attendere, chi puo' reclamare, quali evidenze servono, quali
stati/classi consentono il reclaim — NON e' scelta qui e non ha default: senza
una `LeasePolicy` esplicita il meccanismo RIFIUTA (`POLICY_DECISION_REQUIRED`).
L'esistenza del meccanismo NON chiude il requisito: vedi `ORPHAN_LEASE_MECHANISM_POLICY.md`.
"""
from __future__ import annotations

RESERVED_NO_INTENT = "RESERVED_NO_INTENT"
RESERVED_WITH_INTENT = "RESERVED_WITH_INTENT"
NOT_RESERVED = "NOT_RESERVED"
RECLAIM_POLICY = "NOT_AUTHORIZED"       # nessuna POLICY decisa: decisione umana pendente

# Provenance del reclaim: e' un fatto OSSERVATO (nessun intento di submit persistito),
# non un'attestazione del trasporto e non una risposta del provider.
RECLAIM_SETTLEMENT_SOURCE = "RUNTIME_ORPHAN_RESERVED_RECLAIMED_NOT_DISPATCHED"
RECLAIM_REMOTE_REF = "none:never_dispatched"
_POLICY_REQUIRED = object()             # sentinella: "nessuna policy fornita", distinta da None


class LeaseRefused(RuntimeError):
    """Il reclaim non e' autorizzato o non e' dimostrabile: nessuna scrittura, journal intatto."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


class LeasePolicy:
    """POLICY del lease: i VALORI e gli ATTORI. Nessun default, nessun valore suggerito.

    `min_age_s`               eta' minima della prenotazione perche' sia considerabile
                              orfana. Zero e' ammesso ed e' il piu' permissivo: non e'
                              un default, va scritto.
    `reclaim_authority`       identita' dell'attore autorizzato a reclamare. Il meccanismo
                              confronta soltanto: chi decide che quell'identita' e'
                              legittima e' fuori da qui.
    `allowed_classes`         classi di attempt su cui il reclaim e' ammesso. Una classe
                              non elencata e' rifiutata; elencare `RESERVED_WITH_INTENT`
                              e' possibile ma e' una decisione umana esplicita (quel caso
                              ha gia' un'uscita: `recover_orphaned_submits`).
    `required_evidence_keys`  chiavi che l'evidenza del reclaim deve portare.
    `label`                   chi ha deciso questi valori: finisce nell'evidenza registrata.
    """

    __slots__ = ("min_age_s", "reclaim_authority", "allowed_classes", "required_evidence_keys", "label")

    def __init__(self, *, min_age_s: float, reclaim_authority: str, allowed_classes,
                 required_evidence_keys, label: str):
        if isinstance(min_age_s, bool) or not isinstance(min_age_s, (int, float)):
            raise LeaseRefused("LEASE_POLICY_INVALID", f"min_age_s non numerico: {min_age_s!r}")
        if min_age_s != min_age_s or min_age_s in (float("inf"), float("-inf")) or min_age_s < 0:
            raise LeaseRefused("LEASE_POLICY_INVALID", f"min_age_s non finito o negativo: {min_age_s!r}")
        if not isinstance(reclaim_authority, str) or not reclaim_authority.strip():
            raise LeaseRefused("LEASE_POLICY_INVALID", "reclaim_authority obbligatoria")
        classes = tuple(allowed_classes or ())
        unknown = [c for c in classes if c not in (RESERVED_NO_INTENT, RESERVED_WITH_INTENT)]
        if not classes or unknown:
            raise LeaseRefused("LEASE_POLICY_INVALID",
                               f"allowed_classes non vuota e nota: {unknown or 'vuota'}")
        keys = tuple(required_evidence_keys or ())
        if not all(isinstance(k, str) and k for k in keys):
            raise LeaseRefused("LEASE_POLICY_INVALID", "required_evidence_keys: solo stringhe non vuote")
        if not isinstance(label, str) or not label.strip():
            raise LeaseRefused("LEASE_POLICY_INVALID",
                               "label obbligatoria: la policy deve dichiarare chi ha deciso i valori")
        self.min_age_s, self.reclaim_authority = float(min_age_s), reclaim_authority
        self.allowed_classes, self.required_evidence_keys, self.label = classes, keys, label

    def describe(self) -> dict:
        return {"label": self.label, "min_age_s": self.min_age_s,
                "reclaim_authority": self.reclaim_authority,
                "allowed_classes": list(self.allowed_classes),
                "required_evidence_keys": list(self.required_evidence_keys)}


def fencing_token(job) -> str:
    """Il fence e' la REVISIONE persistita: qualunque scrittura concorrente la incrementa
    e il CAS del Core rifiuta chi presenta quella vecchia. Il token la rende esplicita e
    trasportabile (classificazione e reclaim possono avvenire in processi diversi)."""
    return f"{job.job_id}@{job.revision}"


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


# ---------------------------------------------------------------------------
# MECCANISMO DI RECLAIM (parametrico). Non sceglie la policy: la pretende.
# ---------------------------------------------------------------------------
def reclaim_orphan_reserved(store, job_id: str, *, policy=_POLICY_REQUIRED, actor: str,
                            evidence: dict, token: str, now: float, settle=True) -> dict:
    """Chiude una prenotazione orfana, senza crearne un'altra.

    ORDINE (ogni passo fail-closed, nessuna scrittura prima dell'ultimo):

      1. POLICY      assente o non `LeasePolicy` -> `POLICY_DECISION_REQUIRED`.
      2. AUTHORITY   `actor != policy.reclaim_authority` -> `RECLAIM_NOT_AUTHORIZED`.
      3. EVIDENZA    chiavi mancanti -> `RECLAIM_EVIDENCE_INCOMPLETE`.
      4. OWNERSHIP   il job e' riletto dallo store AUTOREVOLE; classe non ammessa dalla
                     policy -> `RECLAIM_CLASS_NOT_ALLOWED`. Un attempt CON intento non e'
                     un'orfana di questo gap a meno che la policy lo dica esplicitamente.
      5. FENCE       `token` deve coincidere con `fencing_token(job)` riletto ADESSO:
                     un token stantio (qualcuno ha scritto nel frattempo) ->
                     `FENCING_TOKEN_STALE`. E' il fence *esplicito*; il fence *reale* e'
                     il CAS del Core al passo 7.
      6. LEASE       `age < policy.min_age_s` -> `LEASE_NOT_EXPIRED`. L'eta' e' misurata
                     su `submitted_at` (istante della prenotazione), il solo dato di tempo
                     che il Core persiste per una RESERVED.
      7. TERMINALE   `store.reconcile(job, FAILED, evidence)`: percorso ESPLICITO del Core,
                     transizione validata, CAS sulla revisione letta al passo 4. Se un
                     `mark_submitting` concorrente vince la corsa, qui arriva `StaleWrite`
                     e il reclaim NON avviene (e viceversa: `mark_submitting` fallisce
                     PRIMA di autorizzare i byte e prima di qualunque invio).
      8. SETTLEMENT  `store.settle(units=0, source=RECLAIM_SETTLEMENT_SOURCE)`: zero
                     ATTESTATO dal fatto osservato «nessun intento di submit persistito»,
                     non da «FAILED quindi gratis».

    ZERO BLIND RETRY: nessun nuovo attempt, nessuna quote, nessun permit, nessun submit.
    La spesa successiva resta `intent="new_attempt"` + reason + quote + permit.

    LIMITE DICHIARATO (stesso di NG-05): 7 e 8 sono due transazioni. Un'interruzione fra
    le due lascia un terminale non regolato con esposizione MANTENUTA — conservativo,
    visibile in `terminal_unsettled_jobs`, riparabile (`settle` idempotente, `settle=True`
    su un job gia' regolato allo stesso importo non conta due volte).
    """
    if policy is _POLICY_REQUIRED or policy is None:
        raise LeaseRefused(
            "POLICY_DECISION_REQUIRED",
            "nessuna LeasePolicy fornita: finestra, attore, evidenze e classi ammesse sono "
            "una decisione umana. Il meccanismo non la sceglie.")
    if not isinstance(policy, LeasePolicy):
        raise LeaseRefused("LEASE_POLICY_INVALID",
                           f"policy deve essere una LeasePolicy, ricevuto {type(policy).__name__}")
    if not isinstance(actor, str) or actor != policy.reclaim_authority:
        raise LeaseRefused("RECLAIM_NOT_AUTHORIZED",
                           f"attore {actor!r} non e' l'autorita' di reclaim della policy "
                           f"{policy.label!r}")
    if not isinstance(evidence, dict):
        raise LeaseRefused("RECLAIM_EVIDENCE_INCOMPLETE", "evidenza di reclaim: atteso un mapping")
    missing = [k for k in policy.required_evidence_keys
               if not isinstance(evidence.get(k), str) or not evidence[k].strip()]
    if missing:
        raise LeaseRefused("RECLAIM_EVIDENCE_INCOMPLETE",
                           f"evidenza di reclaim incompleta: mancano {missing}")
    job = store.get(job_id)
    if job is None:
        raise LeaseRefused("JOB_UNKNOWN", f"job {job_id!r} sconosciuto allo store autorevole")
    classification = classify_attempt(job, now)
    if classification["class"] not in policy.allowed_classes:
        raise LeaseRefused(
            "RECLAIM_CLASS_NOT_ALLOWED",
            f"{job_id}: classe {classification['class']} non ammessa dalla policy "
            f"{policy.label!r} ({list(policy.allowed_classes)})")
    observed = fencing_token(job)
    if token != observed:
        raise LeaseRefused("FENCING_TOKEN_STALE",
                           f"token {token!r} != {observed!r}: la riga e' cambiata, rileggere")
    age = classification["age_s"]
    if age is None or age < policy.min_age_s:
        raise LeaseRefused("LEASE_NOT_EXPIRED",
                           f"{job_id}: eta' {age}s < min_age_s {policy.min_age_s}s "
                           f"(policy {policy.label!r})")
    full_evidence = dict(evidence)
    full_evidence.update(source=RECLAIM_SETTLEMENT_SOURCE, remote_ref=RECLAIM_REMOTE_REF,
                         reclaimed_by=actor, lease_policy=policy.describe(),
                         fencing_token=observed, observed=classification,
                         attested_by="runtime_orphan_lease", transport_attestation=None)
    report = {"job_id": job_id, "actor": actor, "policy": policy.describe(),
              "fencing_token": observed, "classification": classification,
              "terminalized": False, "settled": False, "new_attempt_created": False}
    terminal = type(job.state)("FAILED")
    updated = store.reconcile(job, terminal, full_evidence, now=now)     # CAS: puo' sollevare
    report["terminalized"] = True
    report["state"] = updated.state.value
    if settle:
        report["settlement"] = store.settle(job_id, units=0, source=RECLAIM_SETTLEMENT_SOURCE,
                                            now=now)
        report["settled"] = True
    store.record_anomaly(job_id, "ORPHAN_RESERVED_RECLAIMED", report, now)
    return report
