"""LAB_ONLY — autorizzazione fidata di test per il runtime governato (CR-02).

Il client (orchestrator, hf_batch `go`) NON sceglie l'envelope e NON sceglie
l'importo. Entrambi derivano da un'autorita' fidata:

  - l'ENVELOPE e' derivato dallo SCOPE dell'operazione (`operation_id` =
    "<scope>:<asset>") tramite una configurazione fidata; un envelope
    presentato dal client viene solo VALIDATO contro quello derivato;
  - l'IMPORTO deriva da una QUOTE FIDATA (`store.issue_quote`, emessa dal lato
    worker/autorita') legata a operation_id, spec_key, envelope_id, importo,
    unita', versione e scadenza. Il client presenta al massimo un `quote_id`.
    Zero non e' mai un fallback: e' valido solo se attestato dalla quote.

Questa e' una configurazione di LABORATORIO: nessun valore reale di credito,
nessuna policy di tenant, nessun Human Authorization system. Serve a provare
il BINDING, non a decidere budget.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


class AuthorizationRefused(RuntimeError):
    """L'autorizzazione fidata non copre la richiesta: nessuna reservation, nessun submit."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def scope_of(operation_id: str) -> str:
    """Lo scope di un'operazione e' la parte prima dei due punti ("MOTION_B1_B4C:B1_NEW_CLIP")."""
    return operation_id.split(":", 1)[0]


@dataclass(frozen=True)
class LabAuthorization:
    """LAB_ONLY. Mappa scope -> envelope_id autorizzato. Immutabile."""
    envelope_by_scope: Mapping[str, str] = field(default_factory=dict)
    label: str = "LAB_ONLY"

    def envelope_for(self, operation_id: str | None) -> str:
        if not isinstance(operation_id, str) or ":" not in operation_id:
            raise AuthorizationRefused("OPERATION_ID_REQUIRED",
                                       "operation_id obbligatorio nella forma '<scope>:<asset>'")
        env = self.envelope_by_scope.get(scope_of(operation_id))
        if not env:
            raise AuthorizationRefused("ENVELOPE_NOT_AUTHORIZED",
                                       f"nessun envelope autorizzato per lo scope "
                                       f"{scope_of(operation_id)!r}")
        return env

    def validate_envelope(self, operation_id: str, presented: str | None) -> str:
        """Il client puo' nominare l'envelope, non sceglierlo: deve coincidere con
        quello derivato dallo scope. Un envelope valido ma fuori scope e' rifiutato."""
        derived = self.envelope_for(operation_id)
        if presented is not None and presented != derived:
            raise AuthorizationRefused(
                "ENVELOPE_OUT_OF_SCOPE",
                f"envelope {presented!r} non e' quello autorizzato per lo scope "
                f"{scope_of(operation_id)!r} ({derived!r})")
        return derived


# Configurazione fidata di laboratorio. Gli envelope vanno aperti nello store
# (`open_envelope`) dal lato autorita' prima dell'uso: qui c'e' solo il binding.
DEFAULT_LAB_AUTHORIZATION = LabAuthorization({
    "MOTION_B1_B4C": "ENV_LAB_MOTION_B1_B4C",
    "lab": "ENV_LAB",
    "T31": "ENV_T31", "T32": "ENV_T32", "T28": "ENV_T28", "T29": "ENV_T29",
    "T24": "ENV_T24", "T25": "ENV_T25", "T26": "ENV_T26", "T30": "ENV_T30",
    "T35": "ENV_T35", "T36": "ENV_T36", "T37": "ENV_T37",
    # CR-10: work order distinti (namespace logico), budget comune su un envelope.
    "WOA": "ENV_LAB_WO", "WOB": "ENV_LAB_WO", "WO_A": "ENV_LAB_WO", "WO_B": "ENV_LAB_WO",
})

# CR-08 — LISTINO FIDATO LAB (LAB_ONLY). Il prezzo di una quote deriva SOLO da qui,
# per SKU = modello della spec. Il client non presenta MAI un importo. Un
# modello senza prezzo non ottiene una quote. `fake_model_free` e' la fixture
# fidata a prezzo zero: e' cosi' che si prova una quote gratuita.
LAB_QUOTE_UNIT = "synthetic_units"
LAB_PRICE_TABLE = {
    "fake_model_v1": 10,
    "fake_model_v2": 12,
    "fake_model_free": 0,
}


def lab_price_for(model: str) -> int:
    if model not in LAB_PRICE_TABLE:
        raise AuthorizationRefused("NO_LAB_PRICE", f"nessun prezzo fidato per il modello {model!r}")
    return LAB_PRICE_TABLE[model]
