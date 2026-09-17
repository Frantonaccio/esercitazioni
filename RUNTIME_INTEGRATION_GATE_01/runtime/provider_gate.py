"""FAKE MODE fail-closed.

Questo gate ammette UN solo provider: l'adapter deterministico di test del Core
(`adapters.fake.FakeAdapter`) o una sua sottoclasse. Qualunque altra richiesta
fallisce con REAL_PROVIDER_DISABLED PRIMA di:

    - leggere credenziali;
    - lanciare un subprocess provider;
    - aprire rete;
    - spendere crediti.

Non e' una convenzione: e' un controllo esplicito sul valore di `provider_mode`
e sulla classe dell'adapter. Nessun fallback: un provider sconosciuto non
"degrada" a fake, si rifiuta.
"""
from __future__ import annotations

import os

ALLOWED_PROVIDER_MODE = "fake"

# Nomi di provider che questo gate deve rifiutare esplicitamente. La lista e'
# documentale: qualunque valore diverso da "fake" e' comunque rifiutato.
REAL_PROVIDER_NAMES = frozenset({
    "higgsfield", "seedance", "kling", "cinema_studio", "cinema-studio",
    "cli", "mcp", "http", "real",
})


class RealProviderDisabled(RuntimeError):
    """Il runtime candidate non puo' raggiungere un provider reale in questo gate."""

    code = "REAL_PROVIDER_DISABLED"

    def __init__(self, requested: str):
        self.requested = requested
        super().__init__(
            f"{self.code}: provider_mode={requested!r}; ammesso solo "
            f"{ALLOWED_PROVIDER_MODE!r}. Nessuna credenziale letta, nessun "
            "subprocess, nessuna rete, nessun credito.")


def require_fake_mode(provider_mode: str) -> str:
    """Primo controllo del candidate `go`. Rifiuta tutto tranne 'fake'."""
    if not isinstance(provider_mode, str) or provider_mode != ALLOWED_PROVIDER_MODE:
        raise RealProviderDisabled(str(provider_mode))
    return provider_mode


def require_fake_adapter(adapter, fake_adapter_cls) -> None:
    """L'adapter deve essere il FakeAdapter del Core (o una sottoclasse).

    `fake_adapter_cls` e' passato dal chiamante perche' questo modulo NON importa
    il Core: l'import del Core avviene solo dopo il controllo del pin.
    """
    if not isinstance(adapter, fake_adapter_cls):
        raise RealProviderDisabled(
            f"adapter:{type(adapter).__module__}.{type(adapter).__qualname__}")
    name = str(getattr(adapter, "name", ""))
    if not name.startswith("fake"):
        raise RealProviderDisabled(f"adapter.name:{name}")


# ---------------------------------------------------------------------------
# LEGACY SPEND PATH (PROVIDER / EXECUTION BOUNDARY HARDENING, 2026-09-17).
#
# `go(..., authorization=None)` e' il percorso LEGACY_LAB: budget/envelope_units
# grezzi, nessuna quote, nessun envelope derivato, resume-as-start. Aggira
# authorization/quote/envelope/permit ed e' riprodotto come percorso spendibile
# (evidence/pre_fix/reproduction_baseline.json["LEGACY_SPEND_PATH"]). Oggi e'
# raggiungibile SOLO con FakeAdapter (REAL_PROVIDER_DISABLED su tutto il resto) ed
# e' usato dai test storici T01-T27: NON e' eliminabile in questa fase
# (BLOCKED_PROVIDER_GATE). Questo interruttore lo rende chiudibile in modo
# esplicito, verificato e fail-closed, PRIMA di qualunque effetto:
#
#   LEGACY_LAB_SPEND_PATH = "ENABLED_LAB_ONLY"   (stato attuale, LAB)
#       dal 2026-09-18: LAB_ONLY_NON_PROVIDER_CAPABLE (vedi sotto)
#   LEGACY_LAB_SPEND_PATH = "DISABLED"           (Provider Boundary Gate: obbligatorio)
#
# L'ambiente puo' solo CHIUDERE (CREATIVE_OS_LEGACY_LAB_SPEND_PATH=disabled), mai
# riaprire un percorso chiuso in codice.
# ---------------------------------------------------------------------------
#
# LEGACY SPEND PATH CLOSURE (2026-09-18). Lo stato del percorso non e' piu'
# "abilitato": e' `LAB_ONLY_NON_PROVIDER_CAPABLE`, e il nome dice esattamente cio'
# che il codice impone. Il percorso resta percorribile per il LABORATORIO (adapter
# deterministici, nessun provider: e' cio' che la suite storica R0-R1 usa e che il
# mandato autorizza a conservare), ma NON e' piu' un percorso spendibile:
#
#   - `require_legacy_lab_spend_path(adapter)` rifiuta un adapter SPENDIBILE
#     (`spend_capable`) SEMPRE, in entrambe le modalita', PRIMA del pin, PRIMA
#     dell'import del Core, PRIMA dello store: nessuna reservation, nessun permit,
#     nessuna quote, nessuno snapshot, nessun submit;
#   - il controllo e' un `getattr` sull'oggetto adapter, quindi non richiede il
#     Core in `sys.path`: non c'e' un ordine di import da azzeccare;
#   - a valle, il CORE impone lo stesso confine in modo indipendente
#     (`adapters.base.SpendCapableAdapter` + `transport.pipeline.run_job`): un
#     adapter spendibile non si dispaccia senza operazione, quote fidata ed
#     envelope. Due lati, la stessa invariante: cambiare adapter/mode/config non
#     riapre un percorso di spesa.
#
# Cio' che questo NON significa: non significa provider reale verificato, ne'
# credenziali autorizzate, ne' spend autorizzato.
# Il VALORE dell'interruttore resta quello canonico: i gate approvati
# (PROVIDER_BOUNDARY_HARDENING_01, PROVIDER_BOUNDARY_GATE_02) lo asseriscono
# LETTERALMENTE, e rinominarlo indebolirebbe un controllo storico senza aggiungere
# una sola garanzia. Cio' che cambia non e' il nome dello stato: e' la CAPABILITY,
# dichiarata a parte e imposta dal codice.
LEGACY_LAB_SPEND_PATH = "ENABLED_LAB_ONLY"
LEGACY_SPEND_PATH_ENV = "CREATIVE_OS_LEGACY_LAB_SPEND_PATH"
SPEND_CAPABLE_ATTR = "spend_capable"

# Fatto machine-readable di QUESTA fase: il percorso LEGACY_LAB non e' un percorso
# capace di provider. Non e' un'etichetta: `require_legacy_lab_spend_path` la impone.
LEGACY_LAB_PROVIDER_CAPABILITY = "LAB_ONLY_NON_PROVIDER_CAPABLE"


class LegacySpendPathDisabled(RuntimeError):
    """Il percorso LEGACY_LAB e' chiuso: solo il percorso governato puo' spendere."""

    code = "LEGACY_SPEND_PATH_DISABLED"

    def __init__(self, state: str):
        self.state = state
        super().__init__(
            f"{self.code}: percorso LEGACY_LAB (authorization=None) chiuso ({state}); "
            "solo il percorso governato (envelope derivato + quote fidata + permit) puo' spendere. "
            "Nessuna reservation, nessun permit, nessun submit.")


class LegacyPathNotProviderCapable(RuntimeError):
    """Un adapter capace di raggiungere un provider reale ha chiesto il percorso
    LEGACY_LAB. Rifiuto strutturale, non condizionato dalla modalita'."""

    code = "LEGACY_LAB_NOT_PROVIDER_CAPABLE"

    def __init__(self, adapter_repr: str):
        self.adapter = adapter_repr
        super().__init__(
            f"{self.code}: {adapter_repr} dichiara `spend_capable` e il percorso LEGACY_LAB "
            f"(authorization=None) e' LAB_ONLY_NON_PROVIDER_CAPABLE. Uno spender passa "
            f"ESCLUSIVAMENTE dal percorso governato (operazione + quote fidata + envelope + "
            f"permit). Nessun pin letto, nessun Core importato, nessuno store aperto, "
            f"nessuna reservation, nessun submit.")


def adapter_is_spend_capable(adapter) -> bool:
    """Vero se l'adapter dichiara di poter raggiungere un provider reale.

    Deliberatamente un `getattr`: non importa il Core e non isinstance-a nulla,
    cosi' il rifiuto puo' precedere il gate di pin e l'import."""
    return bool(getattr(adapter, SPEND_CAPABLE_ATTR, False))


# ---------------------------------------------------------------------------
# PROVIDER BOUNDARY MODE (OPEN-GAP CLOSURE, 2026-09-17).
#
# UN solo interruttore di MODALITA' per la postura destinata al Provider Boundary
# Gate. Quando e' INGAGGIATA, ogni percorso spendibile NON governato del Runtime e'
# chiuso fail-closed, PRIMA di qualunque effetto (nessun pin, nessun import del Core,
# nessuno store, nessuna reservation, nessun submit):
#
#   #2/#4  `go(..., authorization=None)` (LEGACY_LAB) e i suoi chiamanti
#          -> LEGACY_SPEND_PATH_DISABLED (la modalita' forza `legacy_spend_path_state`)
#   #7     helper di test che dispacciano direttamente sullo store (`tests/worker.store_call`)
#          -> PROVIDER_BOUNDARY_MODE_ENGAGED
#
# La modalita' e' DISINGAGGIATA per default: la suite storica R0-R1 (T01-T37) usa il
# percorso LEGACY_LAB e non viene alterata da questa fase. Ingaggiarla e' una
# precondizione dichiarata del Provider Boundary Gate, non un default nascosto.
#
# COSA LA MODALITA' NON PUO' CHIUDERE (dichiarato, non aggirato): i percorsi #10 e #11
# sono primitive del CORE (`transport.pipeline.run_job`, `adapters.*.submit`,
# `registry.reservations.SqliteReservationStore.reconcile`), invocabili da qualunque
# codice che abbia il Core in `sys.path` e un adapter. Nessun interruttore del Runtime
# le governa. Restano `BLOCKED_PROVIDER_GATE` / `CORE_CHANGE_REQUIRED`: la sola
# mitigazione attuale e' il confine di processo P-B01 (l'orchestrator non ha il Core
# dello spender, ne' il suo store, ne' il suo segreto). Vedi LEGACY_SPEND_PATHS_V2.md.
# ---------------------------------------------------------------------------
PROVIDER_BOUNDARY_MODE_ENV = "CREATIVE_OS_PROVIDER_BOUNDARY_MODE"
MODE_ENGAGED = "ENGAGED"
MODE_DISENGAGED = "DISENGAGED"


class ProviderBoundaryModeEngaged(RuntimeError):
    """La modalita' Provider Boundary chiude questo percorso: solo il governato puo' spendere."""

    code = "PROVIDER_BOUNDARY_MODE_ENGAGED"

    def __init__(self, entry_point: str):
        self.entry_point = entry_point
        super().__init__(
            f"{self.code}: {entry_point} e' un percorso non governato e la modalita' "
            f"Provider Boundary e' ingaggiata. Nessun effetto: nessuna reservation, "
            f"nessun permit, nessuna scrittura sullo store, nessun submit.")


def provider_boundary_mode() -> str:
    """Stato della modalita'. Solo l'ambiente puo' INGAGGIARLA; nulla la disingaggia
    se il codice la fissasse (simmetrico a LEGACY_LAB_SPEND_PATH: si puo' solo chiudere)."""
    if str(os.environ.get(PROVIDER_BOUNDARY_MODE_ENV, "")).strip().lower() == "engaged":
        return MODE_ENGAGED
    return MODE_DISENGAGED


def refuse_if_provider_boundary_mode(entry_point: str) -> str:
    """Da chiamare all'INGRESSO di un percorso non governato, prima di ogni effetto."""
    state = provider_boundary_mode()
    if state == MODE_ENGAGED:
        raise ProviderBoundaryModeEngaged(entry_point)
    return state


def legacy_lab_provider_capability() -> str:
    """Costante dichiarata + verificabile: vedi `require_legacy_lab_spend_path`."""
    return LEGACY_LAB_PROVIDER_CAPABILITY


def legacy_spend_path_state() -> str:
    if LEGACY_LAB_SPEND_PATH != "ENABLED_LAB_ONLY":
        return "DISABLED"
    # La modalita' Provider Boundary CHIUDE il percorso legacy: e' un solo interruttore
    # per l'intera postura, non due da tenere allineati a mano.
    if provider_boundary_mode() == MODE_ENGAGED:
        return "DISABLED"
    if str(os.environ.get(LEGACY_SPEND_PATH_ENV, "")).strip().lower() == "disabled":
        return "DISABLED"
    return "ENABLED_LAB_ONLY"


def require_legacy_lab_spend_path(adapter=None) -> str:
    """Chiamata da `go()` quando authorization is None, PRIMA di pin/import/store.

    Due rifiuti, in quest'ordine:
      1. adapter SPENDIBILE -> LEGACY_LAB_NOT_PROVIDER_CAPABLE. Incondizionato: non
         dipende dalla modalita', dall'ambiente o dalla configurazione. E' il senso
         del nome `LAB_ONLY_NON_PROVIDER_CAPABLE`;
      2. percorso chiuso del tutto (modalita' ingaggiata o ambiente) ->
         LEGACY_SPEND_PATH_DISABLED, come prima.
    """
    if adapter_is_spend_capable(adapter):
        raise LegacyPathNotProviderCapable(
            f"{type(adapter).__module__}.{type(adapter).__qualname__}")
    state = legacy_spend_path_state()
    if state != "ENABLED_LAB_ONLY":
        raise LegacySpendPathDisabled(state)
    return state
