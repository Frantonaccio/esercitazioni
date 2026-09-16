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
