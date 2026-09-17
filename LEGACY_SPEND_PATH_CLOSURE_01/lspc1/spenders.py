"""SENTINELLA DEL CONFINE DELLO SPENDER — il provider reale che non c'e'.

Il mandato vieta provider reali, credenziali, rete e crediti. Serve comunque
provare un fatto che riguarda un provider reale: che non sia raggiungibile se
non dal percorso governato. Qui, al posto del provider, c'e' una SENTINELLA.

    reached           quante volte il dispatch e' stato ATTRAVERSATO
    authorized_calls  quante volte l'autorizzazione del payload e' stata attraversata
    transport.sent    marcatore di invio del trasporto fittizio del Core

In ogni percorso NON governato tutti e tre devono restare a ZERO, e il rifiuto
deve arrivare PRIMA di ciascuno di essi. Nel percorso governato `reached` sale a
1: se non salisse, la controprova non proverebbe nulla — dimostrerebbe solo che
la sentinella non e' raggiungibile da nessuno.

La sentinella si costruisce su DUE Core diversi, ed e' deliberato:

  BASELINE  `9cf9cee1` non ha il confine. La sentinella e' un `FakeAdapter` che
            dichiara `spend_capable` e conta: e' la RIPRODUZIONE PRE-FIX, e li'
            `reached` sale anche dai percorsi legacy. E' il difetto, mostrato.
  CANDIDATE il Core porta `SpendCapableAdapter`: la sentinella ne deriva e
            implementa i due hook oltre il confine. Li' `reached` puo' salire
            SOLO con una concessione emessa dal percorso governato.

Nessuna rete, nessuna credenziale, nessun credito: la sentinella non ha nemmeno
il concetto di chiave. Cio' che prova e' la RAGGIUNGIBILITA', non la spesa.
"""
from __future__ import annotations


def core_has_spender_boundary() -> bool:
    """Vero se il Core in `sys.path` porta il confine (Core candidate)."""
    import adapters.base as base
    return hasattr(base, "SpendCapableAdapter")


def sentinel_class(name: str = "fake_spender"):
    """Classe della sentinella, adeguata al Core realmente importato.

    Su entrambi i Core l'adapter e' un `FakeAdapter` (quindi supera il FAKE MODE
    gate del runtime, `require_fake_adapter`) e dichiara `spend_capable`: e'
    esattamente l'oggetto che un adapter reale sarebbe, meno il provider."""
    from adapters.fake import FakeAdapter
    import adapters.base as base

    boundary = getattr(base, "SpendCapableAdapter", None)

    if boundary is None:
        # ---------------- Core BASELINE: nessun confine da attraversare -------
        class Sentinel(FakeAdapter):
            spend_capable = True

            def __init__(self, **kw):
                FakeAdapter.__init__(self, **kw)
                self.reached = 0
                self.authorized_calls = 0
                self.grants = []

            def authorize_payload(self, digest):
                self.authorized_calls += 1
                return FakeAdapter.authorize_payload(self, digest)

            def submit(self, spec):
                self.reached += 1
                return FakeAdapter.submit(self, spec)

        Sentinel.name = name
        Sentinel.boundary = "NONE"
        return Sentinel

    # ------------------- Core CANDIDATE: il confine esiste --------------------
    class Sentinel(boundary, FakeAdapter):
        def __init__(self, **kw):
            FakeAdapter.__init__(self, **kw)
            self.reached = 0
            self.authorized_calls = 0
            self.grants = []

        def _authorize_payload(self, digest, auth):
            self.authorized_calls += 1
            self.grants.append(("authorize_payload", auth.job_id, auth.quote_id))
            return FakeAdapter.authorize_payload(self, digest)

        def _dispatch(self, spec, auth):
            self.reached += 1
            self.grants.append(("submit", auth.job_id, auth.quote_id))
            return FakeAdapter.submit(self, spec)

    Sentinel.name = name
    Sentinel.boundary = "SPEND_CAPABLE_ADAPTER"
    return Sentinel


def build_sentinel(name: str = "fake_spender", **kw):
    return sentinel_class(name)(**kw)


def observe(adapter) -> dict:
    """Fatti osservati sulla sentinella. Sempre riferiti, anche nei rifiuti: un
    rifiuto senza i contatori non dimostrerebbe che nulla e' stato attraversato."""
    if adapter is None:
        return {"built": False, "reached": None, "authorized_calls": None,
                "transport_sent": None, "transport_authorized": None, "submits": None}
    t = getattr(adapter, "transport", None)
    return {"built": True,
            "boundary": getattr(type(adapter), "boundary", "?"),
            "spend_capable": bool(getattr(adapter, "spend_capable", False)),
            "reached": getattr(adapter, "reached", None),
            "authorized_calls": getattr(adapter, "authorized_calls", None),
            "submits": getattr(adapter, "submits", None),
            "transport_sent": getattr(t, "sent_count", None),
            "transport_authorized": len(getattr(t, "authorized", ()) or ()),
            "grants": list(getattr(adapter, "grants", ()) or ())}


def zero(obs: dict) -> bool:
    """Vero se NESSUN confine e' stato attraversato: e' l'asserzione delle
    controprove. `transport_authorized` incluso: autorizzare il trasporto e' gia'
    un effetto sul confine, anche senza invio."""
    return (obs.get("reached") in (0, None)
            and obs.get("authorized_calls") in (0, None)
            and obs.get("submits") in (0, None)
            and obs.get("transport_sent") in (0, None)
            and obs.get("transport_authorized") in (0, None))
