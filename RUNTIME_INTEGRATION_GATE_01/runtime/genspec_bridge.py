"""Ponte fra i dati che il verbo `go` possiede al submit e la `GenSpec` del Core.

REGOLE
- La struttura della spec e' quella del Core (`adapters.base.GenSpec`): qui non
  si inventa una struttura nuova, si popola quella canonica.
- Solo dati REALI e DETERMINISTICI: stessi input bloccati -> stesso spec_key.
- I dati accidentali (timestamp, PID, directory temporanee, valori casuali,
  contatori di run) sono RIFIUTATI per contratto, non solo evitati per buona
  volonta'. Un input che li contiene non produce una spec.
- `spec_key` e' calcolato dal Core. Questo modulo NON lo ricalcola e NON lo
  altera: la semantica dello spec_key e' C26 e non si tocca.

PROVENIENZA DEI CAMPI — STATO: PENDING_P2_BINDING
Il vero `hf_batch.py` (P2) non e' disponibile in questo ambiente, quindi la
mappa "campo di hf_batch -> campo di GenSpec" NON e' stata derivata dal codice
reale. Questo modulo fissa il CONTRATTO di ingresso (`GoInputs`, sei campi che
coincidono con quelli di GenSpec) e le invarianti di determinismo. Il binding
dei sei campi ai dati reali di `go` resta un passo del prossimo gate, da fare
leggendo hf_batch.py. Vedi GENSPEC_MAPPING.md.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

# Chiavi che, se presenti nei params, denunciano un dato accidentale.
FORBIDDEN_PARAM_KEYS = frozenset({
    "timestamp", "ts", "time", "created_at", "now", "date",
    "pid", "process_id", "run_id", "session_id", "request_id",
    "tmp", "tmpdir", "temp_dir", "tempdir", "workdir", "cwd",
    "seed_random", "nonce", "uuid", "random",
})

# Un valore che sembra un path temporaneo o un identificativo di run.
_ACCIDENTAL_VALUE = re.compile(
    r"(^/tmp/|^/var/folders/|/T/tmp[a-z0-9_]+|\btmp[a-z0-9]{6,}\b|"
    r"\b\d{10}(\.\d+)?\b|"                                   # epoch seconds
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})",             # ISO datetime
    re.IGNORECASE)


class GenSpecBridgeError(ValueError):
    """Gli input non producono una spec deterministica."""


@dataclass(frozen=True)
class GoInputs:
    """Dati che il verbo `go` ha al momento del submit. Sei campi, quelli di GenSpec.

    Nessun campo derivato dal momento dell'esecuzione: se un dato non e' noto
    PRIMA di premere `go`, non appartiene alla spec.
    """
    kind: str                                   # image | video | audio
    model: str                                  # identificativo modello richiesto
    prompt: str                                 # prompt bloccato
    params: Mapping[str, Any] = field(default_factory=dict)   # parametri semantici
    refs: tuple[str, ...] = ()                  # reference/element id riusati
    project_id: str = "DEMO_TEST"               # tenant/progetto


def _reject_accidental(path: str, value: Any) -> None:
    if isinstance(value, Mapping):
        for k, v in value.items():
            if str(k).lower() in FORBIDDEN_PARAM_KEYS:
                raise GenSpecBridgeError(
                    f"{path}.{k}: chiave accidentale non ammessa nella spec")
            _reject_accidental(f"{path}.{k}", v)
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _reject_accidental(f"{path}[{i}]", v)
    elif isinstance(value, float) and value != value:          # NaN
        raise GenSpecBridgeError(f"{path}: NaN non e' deterministico")
    elif isinstance(value, str) and _ACCIDENTAL_VALUE.search(value):
        raise GenSpecBridgeError(
            f"{path}: valore che sembra un timestamp o un path temporaneo: {value!r}")
    elif not isinstance(value, (str, int, float, bool, type(None))):
        raise GenSpecBridgeError(
            f"{path}: tipo {type(value).__name__} non serializzabile in modo canonico")


def _freeze(value: Any) -> Any:
    """Copia canonica: dict ordinati, tuple -> list, nessun oggetto vivo."""
    if isinstance(value, Mapping):
        return {str(k): _freeze(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_freeze(v) for v in value]
    return value


def build_genspec(inputs: GoInputs, genspec_cls):
    """Costruisce la `GenSpec` del Core dagli input di `go`.

    `genspec_cls` e' `adapters.base.GenSpec`, passato dal chiamante: questo
    modulo non importa il Core, perche' l'import del Core e' subordinato al
    controllo del pin.
    """
    for name in ("kind", "model", "prompt", "project_id"):
        v = getattr(inputs, name)
        if not isinstance(v, str) or not v.strip():
            raise GenSpecBridgeError(f"{name}: stringa non vuota obbligatoria")
        _reject_accidental(name, v)
    if inputs.kind not in ("image", "video", "audio"):
        raise GenSpecBridgeError(f"kind non ammesso: {inputs.kind!r}")
    if not isinstance(inputs.params, Mapping):
        raise GenSpecBridgeError("params deve essere un mapping")
    _reject_accidental("params", inputs.params)
    refs = tuple(inputs.refs)
    for i, r in enumerate(refs):
        if not isinstance(r, str) or not r:
            raise GenSpecBridgeError(f"refs[{i}]: id di reference non valido")
        _reject_accidental(f"refs[{i}]", r)
    params = _freeze(inputs.params)
    # Controprova: la spec deve essere serializzabile in modo canonico.
    json.dumps(params, sort_keys=True, ensure_ascii=False)
    return genspec_cls(kind=inputs.kind, model=inputs.model, prompt=inputs.prompt,
                       params=params, refs=refs, project_id=inputs.project_id)
