# GENSPEC_MAPPING — dati del verbo `go` → `adapters.base.GenSpec`

## Stato: PENDING_P2_BINDING (parziale)

La struttura è quella del Core, non una struttura nuova:

```python
@dataclass(frozen=True)
class GenSpec:            # adapters/base.py @ 819e7cf
    kind: str             # image | video | audio
    model: str
    prompt: str
    params: dict
    refs: tuple[str, ...]
    project_id: str
    expected_cost_credits: float | None   # NON entra nello spec_key
```

`spec_key = sha256(json canonico di {kind, model, prompt, params, refs, project_id})` —
calcolato **dal Core**. Il bridge non lo ricalcola e non ne cambia la semantica.

## Provenienza dei campi

| campo GenSpec | provenienza in `hf_batch.py go` | stato |
|---|---|---|
| `kind` | da determinare leggendo il file reale | **PENDING_P2_BINDING** |
| `model` | da determinare | **PENDING_P2_BINDING** |
| `prompt` | da determinare | **PENDING_P2_BINDING** |
| `params` | da determinare (solo parametri semantici della generazione) | **PENDING_P2_BINDING** |
| `refs` | da determinare (id di reference/element riusati) | **PENDING_P2_BINDING** |
| `project_id` | da determinare (tenant/progetto) | **PENDING_P2_BINDING** |

`hf_batch.py` non è disponibile in questo ambiente (INITIAL_STATE.md §B). Il mandato vieta di
inventare la mappa: la colonna "provenienza" resta vuota finché il file reale non è leggibile.

## Cosa è stato fissato (e provato) senza P2

`runtime/genspec_bridge.py` fissa il **contratto di ingresso** `GoInputs` — sei campi, gli stessi
di `GenSpec` — e le invarianti di determinismo che la mappa reale dovrà rispettare:

| invariante | meccanismo | test |
|---|---|---|
| stessi input bloccati → stesso `spec_key` | params canonicizzati (chiavi ordinate, tuple→list), refs come tuple; verificato in due processi distinti | T04 PASS |
| ogni mutazione semantica cambia la chiave | prompt / model / ref / param / project_id / kind → 6 chiavi diverse | T05 PASS |
| nessun dato accidentale | chiavi vietate (`timestamp`, `pid`, `run_id`, `tmpdir`, `nonce`, `uuid`, …) e valori che sembrano epoch, ISO datetime o path temporanei → `GenSpecBridgeError` | T05 PASS (5 casi rifiutati) |
| tipi solo canonici | str/int/float/bool/None/dict/list; NaN e oggetti vivi rifiutati | T05 |
| `kind` ammesso | solo `image` / `video` / `audio` | build_genspec |

## Passo successivo (prossimo gate, con P2 leggibile)

1. Leggere `hf_batch.py` e individuare la struttura che `go` possiede al submit.
2. Riempire la tabella "provenienza" campo per campo, con riga:codice.
3. Scrivere `runtime/hf_batch_runtime.py` come **copia** dell'originale e sostituire nel verbo
   `go` il submit diretto con `go_candidate.go(GoInputs(...), ...)`.
4. Rieseguire T04/T05 con gli input reali bloccati.

Nessun timestamp, PID, directory temporanea o valore casuale deve entrare in `GoInputs`:
il bridge li rifiuta per contratto, ma la selezione dei campi reali resta una decisione da
documentare sul codice vero.
