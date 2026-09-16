# GENSPEC_MAPPING — dati reali del verbo `go` di hf_batch → `adapters.base.GenSpec`

## Stato: **BOUND** (derivato dal vero P2 `hf_batch.py`, SHA256 `637f3a80…3ea7d1`, e dalle 11 spec reali del run finale)

Fonte: `p2_handoff/VF_RUNTIME_T16_HANDOFF_2026-09-16/P2_RUNTIME/hf_batch.py` (righe 55–71: `Batch.prompt`,
`Batch.media`, `Batch.args`; righe 171–201: `Batch.run_job`) e `SPECS/spec*.json`
(run `P2_PRIMA_SI_PARLA_RUN_20260915_FINAL_PRODUCTION`, 11 spec, 27 job: 12 image `gpt_image_2`, 15 video `seedance_2_0`).

## Cosa il verbo `go` originale ha in mano al submit

`Batch.run_job` costruisce e lancia:

```
higgsfield generate create <job.model> --prompt <Batch.prompt(job)> [--<k> <v> per job.params]
    [--image-references <resolve(spec.anchors[r])> per r in job.references] [--start-image <resolve(job.start_image)>]
    --wait --wait-timeout 40m --json
```

## Provenienza campo per campo

| GenSpec | provenienza in `hf_batch.py` | riga | note |
|---|---|---|---|
| `kind` | `job["kind"]` | 178 (`ext`/`dest`) | `image` / `video`; nell'originale decide solo estensione e cartella di output |
| `model` | `job["model"]` | 185 (argv) | `gpt_image_2`, `seedance_2_0` |
| `prompt` | `Batch.prompt(job)` = `prefix_blocks` + `job.prompt` + `suffix_blocks` risolti da `spec.prompt_blocks` | 55–57 | identico a `lock.jobs[].prompt_final`; sha256 == `prompt_sha256` del lock (T21) |
| `params` | `job["params"]` | 66–67 (`--k v`) | valori nativi: `generate_audio: false` resta bool (la CLI lo serializzava `str(v).lower()`); chiavi ordinate dal bridge |
| `refs` | `Batch.media(job)`, nell'ordine CLI: `--image-references` per `job.references` via `spec.anchors`, poi `--start-image` | 59–64 | ogni ref = `"<role>:<id>:<sha256 dei byte inviati>"`; lo sha è quello che `fingerprint()` già calcolava (`sha_file(path)`) e che il lock registra come `media[].sha256_sent` |
| `project_id` | `spec["run_id"]` | spec | identità del run di produzione autorizzato |

Esempio reale (T21, `evidence/T21_real_genspec_mapping.json`):

```
B1_NEW_CLIP  kind=video model=seedance_2_0
             params={aspect_ratio:9:16, duration:13, generate_audio:false, mode:std, resolution:1080p}
             refs=("start-image:START:a21193da…4ae65",)   ← sha256_sent del lock reale
             project_id=P2_PRIMA_SI_PARLA_RUN_20260915_FINAL_PRODUCTION
             spec_key=f4076e463c1fbcd9fb4d12b9b008931fe1c6c3074f999257cb57df18a4ae17db
```

## Cosa NON entra nella spec (non è input del provider)

`asset`, `beat`, `must_show`, `must_not_show`, `edit_use`, `authority`, `batch`, `parallel`, `identity_anchor`
(duplicato di `anchors`), i nomi dei blocchi (`prefix_blocks`/`suffix_blocks`: entrano già risolti nel prompt),
`provider`, `provider_client`, `lock_id`, `created_at`, `fingerprint_sha256`, `job_id`, `seconds`, `balance`, `output`.
T21 prova che cambiare `edit_use`/`must_show`/`beat` lascia lo `spec_key` invariato.

## Invarianti provate (T04, T05, T21)

| invariante | prova |
|---|---|
| `prompt()` e `media()` del bridge sono identici al codice originale | T21: 27/27 job, confronto chiamando `hf_batch_original.Batch` (read-only) |
| prompt == `prompt_final` del lock di produzione | T21: `prompt_sha256` combacia per `B1_NEW_CLIP` e `B4C_NEW_CLIP` |
| refs == byte realmente inviati | T21: sha nei refs == `media[].sha256_sent` del lock |
| stesso input → stesso `spec_key` in un altro processo | T21: ricalcolo in interprete separato, chiavi identiche |
| mutazione reale → chiave diversa | T21: blocco di prompt `V916`, `params.duration`, byte della start image, `run_id` → 4 chiavi diverse |
| media mancante → rifiuto | T21: `GenSpecBridgeError` (l'originale bloccava in `lock` con `media missing`) |
| nessun dato accidentale | T05: timestamp/pid/tmpdir/epoch/ISO rifiutati per contratto |

## Nota sul lock preventivo di P2

`fingerprint()`/`lock`/`require` di hf_batch (SHA di tenant, Core, regole, script, spec, media sul Mac) sono il
controllo di **deriva degli input** di P2. Non fanno parte del contratto C26 e non sono sostituiti dal Core:
nella copia candidate restano intatti; in laboratorio T22 li stubba perché i file del tenant non esistono qui.
