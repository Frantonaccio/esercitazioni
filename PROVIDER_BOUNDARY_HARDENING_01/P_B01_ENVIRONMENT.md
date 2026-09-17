# P-B01 — DESIGN ESEGUIBILE, ISTRUZIONI PER L'AMBIENTE, EVIDENZA

## Cosa e' stato dimostrato (B01, `evidence/B01_privilege_boundary_uid.json`)
Confine di privilegio **reale**, applicato dal kernel (DAC su UID/mode, `SO_PEERCRED`, `no_new_privs`), fra:
- **spender daemon** (`pbgate/spender_daemon.py`), UID 65532, unico detentore del segreto fittizio (dir `0700`,
  file `0600`), dello store autorevole, del ledger snapshot P-B04 e dei nonce P-B02; costruisce l'adapter; esegue
  SOLO `go` governato; emette quote dal listino LAB; autentica il peer: accetta **un solo UID** (65531);
- **orchestrator probe** (`pbgate/orchestrator_probe.py`), UID 65531, `CapEff=0`, `NoNewPrivs=1` (sudo/setuid
  inefficaci), parla solo via socket Unix (JSON newline-delimited, schema chiuso di `boundary_mock.validate_request`).

Probe canoniche T29 (policy congelata `gate_report.t29_status`, UID distinti): `read_worker_secret`,
`write_worker_code` (3 sorgenti), `write_worker_store`, `direct_dispatch_on_worker_store` → tutte `BLOCKED (…)` →
`PASS/VERIFIED`. Probe aggiuntive: emissione quote sullo store spender, kill del daemon, lettura `/proc/<pid>/environ`,
listing della secret dir, lettura del ledger snapshot → tutte BLOCKED. Un terzo UID (65530) che si connette al socket
→ `PEER_UID_NOT_AUTHORIZED` prima di leggere un byte. Spesa governata via socket: `SUCCEEDED` sul conto del daemon,
snapshot `send_verified`; `resume` → `RESUMED/SUCCEEDED` senza nuovo submit; segreto mai nel canale; sentinella 0 violazioni.
Controllo (B02): la modalita' same-UID resta `BLOCKED_ENVIRONMENT` (T29 storico e di regressione).

## Cosa NON significa
- Non e' un provider reale, non e' una credenziale reale, non e' produzione: segreto fittizio, `FakeAdapter`, 0 crediti.
- Il gate (operatore) gira come root per creare UID/directory e leggere lo store a fine test: e' il ruolo
  dell'installatore, non dell'orchestrator. Un operatore root puo' sempre tutto; il confine dimostrato e' fra
  orchestrator e spender **non privilegiati**.
- `T29` del gate storico resta `BLOCKED_ENVIRONMENT`: descrive correttamente la configurazione same-UID del mock
  storico, che non e' stata modificata.

## Precondizioni dell'ambiente (rilevate automaticamente da B01; altrimenti `BLOCKED_ENVIRONMENT`, mai PASS simulato)
- euid 0 con `CAP_SETUID`, `CAP_SETGID`, `CAP_CHOWN`; `setpriv` (util-linux) disponibile;
- possibilita' di usare UID numerici senza voce in passwd (default 65530/65531/65532; override `PB01_*_UID`);
- filesystem con DAC standard e directory del repository traversabili (0755) dagli UID LAB;
- `git` ≥ 2.35.2: per gli UID LAB il pin del Core richiede `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory
  GIT_CONFIG_VALUE_0=*` (il repository e' di root: "dubious ownership"); il gate lo imposta.

## Come eseguire in un ambiente idoneo
```
cd /home/user/esercitazioni/PROVIDER_BOUNDARY_HARDENING_01
CREATIVE_OS_CORE_PATH=/home/user/creative-os PYTHONDONTWRITEBYTECODE=1 python3 pbgate/run_boundary_gate.py
```
Il daemon puo' anche essere avviato a mano (vedi `--help` di `spender_daemon.py`) sotto `setpriv --reuid=<spender>
--regid=<spender> --clear-groups --inh-caps=-all --bounding-set=-all --no-new-privs`; il probe sotto lo stesso wrapper
con `--reuid=<orchestrator>`.

## Cosa resta per un confine di produzione (fuori scope, per Human Review)
- adapter reale costruibile SOLO nello spender; credenziali reali montate solo nel suo dominio (secret store/KMS);
- container/daemon di sistema con unit hardening (systemd `DynamicUser`, `NoNewPrivileges`, `ProtectSystem`) o
  namespace separati; socket con ACL di gruppo invece di `0666`+peer check;
- chiusura dei percorsi `BLOCKED_PROVIDER_GATE` di `LEGACY_SPEND_PATHS.md`.
