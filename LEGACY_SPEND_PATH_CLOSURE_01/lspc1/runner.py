"""Esecuzione isolata delle sonde: un interprete nuovo per ogni gruppo.

Il gate chiama queste tre funzioni; ognuna lancia `lspc1.probe_main` come
processo a se', cosi' la coppia (Core, Runtime) sotto prova e' davvero quella
dichiarata e non quella che il processo del gate aveva gia' importato.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

BUNDLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(core_path: str, mode: str, gate01: str | None) -> dict:
    fd, out = tempfile.mkstemp(prefix=f"lspc1_{mode}_", suffix=".json")
    os.close(fd)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "LSPC1_PROBE_MODE": mode}
    env.pop("CREATIVE_OS_PROVIDER_BOUNDARY_MODE", None)
    env.pop("CREATIVE_OS_LEGACY_LAB_SPEND_PATH", None)
    argv = [sys.executable, "-m", "lspc1.probe_main", core_path, out]
    if gate01:
        argv.append(gate01)
    r = subprocess.run(argv, cwd=BUNDLE, env=env, capture_output=True, text=True, timeout=3600)
    try:
        with open(out, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        data = {"_runner_error": {"returncode": r.returncode, "stdout": r.stdout[-2000:],
                                  "stderr": r.stderr[-2000:]}}
    finally:
        if os.path.exists(out):
            os.remove(out)
    return data


def probe_all(core_path: str, gate01: str | None = None) -> dict:
    return _run(core_path, "probes", gate01)


def config_switches(core_path: str, gate01: str | None = None) -> dict:
    return _run(core_path, "switches", gate01)


def budget_paths(core_path: str, gate01: str | None = None) -> dict:
    return _run(core_path, "budget", gate01)


def forge_probes(core_path: str, gate01: str | None = None) -> dict:
    return _run(core_path, "forge", gate01)
