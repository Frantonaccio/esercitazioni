---
name: creative-os-production-control
description: "Controlla preparazione e ripresa dei job Creative OS con contesto canonico, lock, trace e Human Gate. Usa per avviare, riprendere o verificare una produzione; non per brainstorming libero o pubblicazione. Questa versione esegue soltanto test con provider fittizio."
compatibility: "Python 3.10+, Git e checkout Creative OS verificato. Nessuna dipendenza Python esterna, nessun provider reale."
metadata:
  version: "0.1.0-candidate"
  target: "Claude Code; shared Creative OS procedures"
---

# Creative OS Production Control

## Confine

Sei l'operatore di un protocollo, non la fonte delle autorizzazioni.
Questa skill è CANDIDATE e MOCK_ONLY: non installarla o abilitarla automaticamente.
Non modificare P2, policy, learning canonico, credenziali o provider.
Non confondere checksum, presenza dei file o test del mock con qualità del video,
autenticazione dell'approvatore o prova di lettura/comprensione da parte del modello.

## Procedura

1. Prima di integrare o avviare un lavoro leggi `references/protocol.md`.
   Per audit, interfacce, condizioni di rilascio e limiti leggi anche
   `references/integration.md`. Arrestati se il percorso canonico non è risolto.
2. Identifica tenant, job, brief approvato, policy attiva, cast, vincoli per scena,
   versioni di Core e tenant, reference e fonti di timing. Produci un Boot Report
   con file effettivamente aperti e loro hash. Non ricostruire i fatti dalla chat.
3. Per verificare questo candidato esegui, dalla directory della skill:
   `python scripts/control.py --core-root /percorso/creative-os selftest`.
   Per una prova completa senza produzione esegui:
   `python scripts/control.py --core-root /percorso/creative-os demo`.
   I due comandi usano fixture temporanee, non il tenant reale.
4. Prima di proporre un submit reale richiedi l'integrazione e i test del percorso
   esistente descritti in `references/integration.md`. In questa versione il
   percorso reale resta `RULE_NOT_ACTIVE`: non sostituirlo con un comando provider,
   browser, SDK o skill generativa alternativa.
5. Alla ripresa recupera manifest e stato persistito, ricontrolla versione e
   fingerprint, riconcilia gli esiti incerti. Non effettuare un nuovo submit
   per risolvere un timeout. La chat non è lo stato del job.
6. Valuta l'asset reale contro ogni vincolo identificato. Se non puoi verificarlo,
   registra `NOT_VERIFIED`. Un hash corretto non è una QA visiva.
7. Consegna stato, prove, problemi aperti e prossima azione autorizzabile.
   Non promuovere a definitivo un learning non approvato. Nessuna pubblicazione
   o spesa è autorizzata dall'esito dei test.

## Output obbligatorio

```text
MODE: MOCK_ONLY | INTEGRATION_AUDIT
TENANT / JOB:
CORE_SHA / TENANT_SHA:
CONTEXT_FINGERPRINT:
FILES_ACTUALLY_READ:
STATE:
TEST_EVIDENCE:
UNVERIFIED:
NEXT_ALLOWED_ACTION:
```

Esempio: «Riprendi il job dopo compattazione» richiede leggere stato e manifest,
non generare nuovamente. «Inventiamo tre angoli creativi» non richiede questa skill
finché non diventa una richiesta di produzione.

Il codice `scripts/control.py` implementa solo il laboratorio descritto.
`scripts/test_control.py` ne verifica gli invarianti. Il rapporto dei test non
certifica hook attivi, isolamento credenziali o comportamento di Claude sul Mac.
