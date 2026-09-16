"""Mappa REALE `hf_batch.py go` -> `GoInputs` -> Core `GenSpec`.

Derivata dal vero P2 `hf_batch.py` (SHA256 637f3a80…3ea7d1) e dalle spec reali
`spec*.json` del run P2_PRIMA_SI_PARLA_RUN_20260915_FINAL_PRODUCTION.

Cosa il verbo `go` originale ha in mano al submit (Batch.run_job -> subprocess
`higgsfield generate create <model> <args>`):

    job["kind"]                     -> "image" | "video"          (solo per ext/dest)
    job["model"]                    -> argv[3]                    (gpt_image_2 / seedance_2_0)
    Batch.prompt(job)               -> --prompt                   (prefix_blocks + prompt + suffix_blocks)
    job["params"]                   -> --<k> <v>                  (aspect_ratio, resolution, quality |
                                                                   duration, generate_audio, mode)
    Batch.media(job)                -> --image-references <path>  per job["references"] via spec["anchors"]
                                       --start-image <path>       per job["start_image"]
    spec["run_id"]                  -> identita' del run di produzione

PROVENIENZA CAMPO PER CAMPO (vedi GENSPEC_MAPPING.md):

    GenSpec.kind        <- job["kind"]
    GenSpec.model       <- job["model"]
    GenSpec.prompt      <- Batch.prompt(job)   (== lock.jobs[].prompt_final, sha == prompt_sha256)
    GenSpec.params      <- job["params"]        (valori nativi: bool resta bool; la CLI li
                                                 serializzava con str(v).lower(), qui non serve)
    GenSpec.refs        <- per ogni media in ordine CLI: "<role>:<id>:<sha256 del file inviato>"
                           (role = image-references | start-image; sha256 == lock.media[].sha256_sent)
    GenSpec.project_id  <- spec["run_id"]

NON entrano nella spec (non sono input del provider):
    asset, beat, must_show, must_not_show, edit_use, authority, batch, parallel,
    identity_anchor (duplicato di anchors), prefix/suffix_blocks come nomi (entrano
    gia' risolti nel prompt), provider, provider_client, lock_id, created_at,
    fingerprint_sha256, job_id, seconds, balance, output.

`prompt()` e `media()` qui sotto sono la trascrizione ESATTA delle due funzioni
del vero hf_batch.py; il test T21 dimostra l'uguaglianza chiamando il codice
originale (read-only) sulle 11 spec reali.
"""
from __future__ import annotations

import re
from typing import Callable, Mapping

from runtime.genspec_bridge import GenSpecBridgeError, GoInputs

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def prompt(spec: Mapping, job: Mapping) -> str:
    """Identico a hf_batch.Batch.prompt (P2 637f3a80)."""
    return " ".join(spec["prompt_blocks"][b] for b in job.get("prefix_blocks", [])) + \
        (" " if job.get("prefix_blocks") else "") + job["prompt"] + \
        "".join(" " + spec["prompt_blocks"][b] for b in job.get("suffix_blocks", []))


def media(spec: Mapping, job: Mapping) -> list[tuple[str, str, str]]:
    """Identico a hf_batch.Batch.media, senza risolvere il path su disco.

    Restituisce (flag, id, ref) nello stesso ordine della CLI: prima le
    --image-references nell'ordine di job["references"], poi --start-image.
    `ref` e' il riferimento simbolico PILOT:/RUN: della spec, non un path assoluto.
    """
    out = []
    for r in job.get("references", []):
        out.append(("--image-references", r, spec["anchors"][r]))
    if job.get("start_image"):
        out.append(("--start-image", "START", job["start_image"]))
    return out


def go_inputs_from_job(spec: Mapping, job: Mapping,
                       media_sha256: Callable[[str, str, str], str]) -> GoInputs:
    """Costruisce GoInputs dal job reale.

    `media_sha256(flag, id, ref)` restituisce lo sha256 dei byte del file che il
    verbo `go` invierebbe (in produzione: sha_file(resolve(ref)); nel lab: il
    valore `sha256_sent` registrato nel RUNTIME_LOCK). E' l'unico dato che non
    sta nella spec: e' nel file, e il file e' cio' che il provider riceve.
    """
    refs = []
    for flag, rid, ref in media(spec, job):
        sha = media_sha256(flag, rid, ref)
        if not isinstance(sha, str) or not _SHA256.match(sha):
            raise GenSpecBridgeError(
                f"{job.get('asset')}: sha256 mancante o non valido per {flag} {rid} ({ref}); "
                "hf_batch.lock avrebbe bloccato con 'media missing'")
        refs.append(f"{flag.lstrip('-')}:{rid}:{sha}")
    return GoInputs(kind=job["kind"], model=job["model"], prompt=prompt(spec, job),
                    params=dict(job["params"]), refs=tuple(refs), project_id=spec["run_id"])


def media_sha_from_lock(lock: Mapping) -> Callable[[str, str, str], str]:
    """Resolver di laboratorio: gli sha256_sent registrati dal lock P2 reale."""
    table: dict[tuple[str, str], str] = {}
    for j in lock["jobs"]:
        for m in j["media"]:
            table[(j["asset"], m["role"], m["id"])] = m["sha256_sent"]

    def _for_asset(asset: str):
        def resolver(flag: str, rid: str, ref: str) -> str:
            return table.get((asset, flag.lstrip("-"), rid), "MISSING")
        return resolver
    return _for_asset
