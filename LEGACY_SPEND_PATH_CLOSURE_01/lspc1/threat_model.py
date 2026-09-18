"""THREAT MODEL del confine dello spender — machine-readable.

Richiesto dalla Human Review 01. Serve a rendere esplicita una distinzione che
altrimenti resta implicita e, restando implicita, diventa una pretesa: quale
confine protegge da cosa, e cosa nessuno dei due pretende di fermare.

La regola che tiene insieme il documento: non si puo' chiamare "strutturale" un
confine e allo stesso tempo ignorare i metodi che stanno dietro la struttura. O
sono protetti, o sono dichiarati fuori dal perimetro — e in questa fase sono
protetti, ma il perimetro resta dichiarato lo stesso, perche' in Python il
trattino basso non e' un confine di sicurezza.
"""
from __future__ import annotations

MODEL = {
    "schema": "spender-boundary-threat-model/1",
    "date": "2026-09-18",
    "phase": "LEGACY SPEND PATH CLOSURE — HUMAN REVIEW 01 corrective delta",

    "core_boundary": {
        "what_it_is": ("`adapters.base.SpendCapableAdapter` + `authorize_dispatch` + "
                       "`grant_dispatch` + il guard sugli hook, piu' i controlli di "
                       "`transport.pipeline.run_job`."),
        "enforced_by": "codice del Core, nello stesso processo del chiamante",
        "protects_against": [
            {"id": "SUPPORTED_ENTRY_POINT_OUT_OF_GOVERNANCE",
             "what": "un entry point supportato chiamato fuori dal percorso governato",
             "evidence": ["E04.core_run_job_direct_refused", "run_spender_boundary:D"]},
            {"id": "DIRECT_SUBMIT",
             "what": "`adapter.submit(spec)` invocato direttamente",
             "evidence": ["E04.adapter_submit_direct_refused", "run_spender_boundary:B"]},
            {"id": "DIRECT_AUTHORIZE_PAYLOAD",
             "what": "`adapter.authorize_payload(digest)` invocato direttamente",
             "evidence": ["E04.adapter_authorize_payload_direct_refused", "run_spender_boundary:C"]},
            {"id": "RUN_JOB_WITHOUT_GOVERNED_INPUTS",
             "what": "`run_job` senza operazione, quote fidata o envelope; e con "
                     "`envelope_units`, cioe' con il budget scelto dal client",
             "evidence": ["E06", "run_spender_boundary:D", "run_spender_boundary:E"]},
            {"id": "CALLER_CONSTRUCTED_CAPABILITY",
             "what": "una `DispatchAuthorization` costruita dal chiamante e presentata "
                     "come autorizzazione — il blocker della Human Review 01",
             "evidence": ["E13.counterexample_refused", "run_spender_boundary:L",
                          "run_spender_boundary:N"]},
            {"id": "CAPABILITY_BUILT_BYPASSING_CONSTRUCTOR",
             "what": "la stessa, fabbricata aggirando `__post_init__`: il registro dei "
                     "coniati e' per IDENTITA', non per uguaglianza di campi",
             "evidence": ["E13.slot_injection_refused", "run_spender_boundary:L"]},
            {"id": "SAME_ATTEMPT_MULTIPLE_MINT",
             "what": ("lo STESSO tentativo che conia due autorizzazioni distinte, entrambe "
                      "valide, usando SOLO API supportate e il journal autorevole reale — il "
                      "blocker della Human Review 02. Non e' codice malevolo: e' misuse "
                      "possibile dall'API, quindi tocca al confine del Core fermarlo."),
             "closed_by": ("`claim_dispatch_authorization`: verifica E claim in UNA "
                           "transazione, `job_id` come PRIMARY KEY. Vale fra chiamate, fra "
                           "thread e fra PROCESSI, perche' l'autorita' e' il file del journal, "
                           "non la memoria di un interprete."),
             "evidence": ["E15.blocker_reproduced", "E15.blocker_closed",
                          "run_spender_boundary:P", "run_spender_boundary:Q",
                          "run_spender_boundary:R"]},
            {"id": "CAPABILITY_REPLAY",
             "what": "un'autorizzazione LEGITTIMA riusata dopo il proprio `with`",
             "evidence": ["run_spender_boundary:O"]},
            {"id": "DIRECT_IMPLEMENTATION_HOOKS",
             "what": "`_dispatch` / `_authorize_payload` invocati direttamente. Il guard "
                     "e' applicato dalla BASE in `__init_subclass__`: la sottoclasse non "
                     "deve ricordarsene, e non puo' disapplicarlo",
             "evidence": ["E13.hooks_refused", "run_spender_boundary:M"]},
            {"id": "CAPABILITY_MASKING_WRAPPER",
             "what": "un wrapper che dichiara `spend_capable = False` e delega allo "
                     "spender: il confine non sta sul wrapper, sta sullo spender",
             "evidence": ["E05.masking_the_capability_does_not_help"]},
            {"id": "ACCIDENTAL_UNGOVERNED_INTEGRATION",
             "what": "errori di integrazione: codice nuovo che chiama il Core senza "
                     "sapere che esiste un percorso governato",
             "evidence": ["E04", "E06"]},
        ],
    },

    "process_boundary_p_b01": {
        "what_it_is": ("confine di PROCESSO: UID distinto per l'orchestrator, nessuna "
                       "capability, `no_new_privs`, segreto e store leggibili solo nel "
                       "dominio dello spender, `SO_PEERCRED` sul canale."),
        "enforced_by": "kernel",
        "protects_against": [
            {"id": "ORCHESTRATOR_READS_CREDENTIALS",
             "what": "l'orchestrator prova a leggere il segreto dello spender",
             "evidence": ["PROVIDER_BOUNDARY_HARDENING_01: B01", "T29 (BLOCKED_ENVIRONMENT)"]},
            {"id": "ACCESS_TO_SPENDER_STORE_OR_SECRET",
             "what": "scrittura sullo store o lettura del segreto del dominio spender — "
                     "cioe' l'unico modo di fabbricare davvero le righe da cui "
                     "`authorize_dispatch` deriva l'autorizzazione",
             "evidence": ["PROVIDER_BOUNDARY_GATE_02: C02", "E09.composition_pb01_pb02"]},
            {"id": "UNAUTHORIZED_PROCESS_OR_UID",
             "what": "un processo o un UID non autorizzato che si presenta al canale",
             "evidence": ["PROVIDER_BOUNDARY_GATE_02: C02"]},
        ],
    },

    "explicitly_not_protected_against": [
        {"id": "ARBITRARY_MALICIOUS_CODE_SAME_IDENTITY",
         "what": ("codice arbitrariamente malevolo eseguito NELLO STESSO PROCESSO, con la "
                  "stessa identita' e le stesse credenziali dello spender."),
         "why": ("in Python il trattino basso non e' un confine di sicurezza: chi esegue "
                 "nel processo puo' importare un nome privato, riscrivere un attributo di "
                 "classe o sostituire un modulo. Nessun controllo scritto in Python puo' "
                 "impedirlo, e fingere il contrario sarebbe la bugia piu' pericolosa di "
                 "tutto questo documento."),
         "mitigation": ("P-B01: quel codice non gira nel dominio dello spender. "
                        "L'orchestrator non ha il segreto, non ha lo store, non ha l'UID."),
         "residual": ("se un attaccante ottiene esecuzione di codice DENTRO il dominio "
                      "dello spender, ha gia' le credenziali: il confine del Core non e' "
                      "l'ultima linea, e non e' mai stato pensato per esserlo.")},
        {"id": "FABRICATED_STORE_OBJECT",
         "what": ("un chiamante che passa a `grant_dispatch` un oggetto duck-typed al posto "
                  "dello store autorevole, e gli fa dire cio' che vuole."),
         "why": ("il Core non puo' sapere quale oggetto sia \"il vero journal\": puo' solo "
                 "pretendere che i fatti vengano riletti da cio' che gli viene dato. "
                 "`run_job` passa lo store reale; sostituirlo richiede esecuzione di "
                 "codice nel processo, cioe' il caso sopra."),
         "mitigation": "P-B01, piu' il fatto che lo store reale e' un file che solo lo "
                       "spender puo' scrivere.",
         "residual": "coincide con ARBITRARY_MALICIOUS_CODE_SAME_IDENTITY."},
    ],

    "two_distinct_properties": {
        "ONE_AUTHORIZATION_IS_ONE_USE": (
            "un'autorizzazione gia' consumata non si riusa. Registro `_SPENT`, per "
            "identita' dell'oggetto. Controprova: `run_spender_boundary:O`."),
        "ONE_ATTEMPT_IS_AT_MOST_ONE_AUTHORIZATION": (
            "un tentativo non conia due autorizzazioni. Claim persistito nel journal con "
            "`job_id` come PRIMARY KEY. Controprove: `run_spender_boundary:P/Q/R`, `E15`."),
        "why_both": ("la prima senza la seconda lascia chiedere due chiavi originali per la "
                     "stessa camera; la seconda senza la prima lascia riusare la stessa "
                     "chiave. Sono proprieta' diverse, ed entrambe necessarie."),
    },

    "crash_semantics": {
        "A_before_claim_commit": "nessun claim, nessuna autorizzazione. Un tentativo "
                                 "successivo e' il primo, non un blind retry.",
        "B_after_claim_before_submit": ("il claim resta. Una seconda richiesta e' "
                                        "DISPATCH_AUTHORIZATION_ALREADY_CLAIMED, non un nuovo "
                                        "dispatch: il tentativo entra nel recovery gia' "
                                        "governato (recover_orphaned_submits -> SUBMIT_UNKNOWN "
                                        "-> riconciliazione)."),
        "C_uncertain_submit": "SUBMIT_UNKNOWN preservato, zero blind retry, invariato.",
        "claim_is_not_releasable": ("rilasciarlo sarebbe la scorciatoia di retry che tutto il "
                                    "resto del modulo esiste per non avere."),
    },

    "design_note": {
        "why_three_mechanisms": (
            "grant che rilegge il journal, costruttore che pretende un token di conio, "
            "registro dei coniati per identita' con consumo singolo. Sono ridondanti di "
            "proposito: il primo chiude la strada supportata, il secondo il controesempio "
            "letterale della review, il terzo tutto cio' che aggira i primi due senza "
            "arrivare all'esecuzione arbitraria di codice."),
        "why_not_a_boolean": (
            "`issued_by_authorize_dispatch = True` e' un campo che chiunque scrive. Una "
            "dataclass frozen rende l'oggetto immutabile, non autentico. L'autenticita' "
            "qui e' l'IDENTITA' dell'oggetto piu' la sua presenza in un registro privato, "
            "e `eq=False` impedisce che due oggetti con gli stessi campi si scambino."),
    },
}

REQUIRED_SECTIONS = ("core_boundary", "process_boundary_p_b01",
                     "explicitly_not_protected_against", "design_note")
REQUIRED_CORE_THREATS = ("DIRECT_SUBMIT", "DIRECT_AUTHORIZE_PAYLOAD",
                         "RUN_JOB_WITHOUT_GOVERNED_INPUTS", "CALLER_CONSTRUCTED_CAPABILITY",
                         "DIRECT_IMPLEMENTATION_HOOKS", "CAPABILITY_MASKING_WRAPPER",
                         "SUPPORTED_ENTRY_POINT_OUT_OF_GOVERNANCE",
                         "SAME_ATTEMPT_MULTIPLE_MINT", "CAPABILITY_REPLAY")


def verify() -> dict:
    core_ids = {t["id"] for t in MODEL["core_boundary"]["protects_against"]}
    checks = {
        "all_sections_present": all(s in MODEL for s in REQUIRED_SECTIONS),
        "core_threats_covered": all(t in core_ids for t in REQUIRED_CORE_THREATS),
        "process_boundary_declared": bool(MODEL["process_boundary_p_b01"]["protects_against"]),
        "same_identity_malicious_code_declared_out_of_scope": any(
            t["id"] == "ARBITRARY_MALICIOUS_CODE_SAME_IDENTITY"
            for t in MODEL["explicitly_not_protected_against"]),
        "every_core_threat_cites_evidence": all(
            t.get("evidence") for t in MODEL["core_boundary"]["protects_against"]),
    }
    return {"checks": checks, "ok": all(checks.values()), "model": MODEL}
