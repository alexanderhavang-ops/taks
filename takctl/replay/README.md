# TAKCTL Replay

Replay är en taktisk simulerings- och agentmiljö för kedjad ordergivning, rapportering och arbetsutförande.

## Source vs runtime

Replay följer strikt source/runtime-separation.

### Source
Source ligger i repo under:

- `takctl/replay/`

Här ligger endast:

- kod
- promptar
- doktrinprofiler
- seeds
- scenarion
- knowledge
- dokumentation

Source får inte användas för levande kör-state.

### Runtime
Levande replay-state ligger under:

- `/opt/tak/replay/`

Här ligger bland annat:

- `state/agents/<callsign>/state.json`
- `state/agents/<callsign>/inbox.jsonl`
- `state/agents/<callsign>/outbox.jsonl`
- `state/agents/<callsign>/decisions.jsonl`
- `state/agents/<callsign>/tasks.jsonl`
- `state/agents/<callsign>/last_*`
- `logs/`

Installern ansvarar för att skapa runtime-kataloger med rätt ägare och rätt behörigheter.

## Grundmodell

Replay använder en enkel tick-baserad modell.

### Varje tick
Varje agent körs varje tick, men LLM anropas inte per automatik varje tick.

Varje tick gäller:

1. transportkön `inbox.jsonl` pollas och konsumeras till `new_messages`
2. roten i varje arbetskedja exekveras exakt en gång
3. LLM körs bara om något av följande är sant:
   - `new_messages` är icke-tom
   - minst ett arbete blev klart detta tick
   - referee/world-state har markerat `world_changed_this_tick`
4. efter lyckat LLM-anrop skrivs `work` helt över av det nya beslutet
5. de `new_messages` som låg till grund för beslutet flyttas till `read_messages`

Det finns ingen separat smart scheduler som försöker återskapa state machine-logik ovanpå agentens state.

## Arbetsmodell

Primär arbetsmodell är:

- `work`
- `completed_work`

### `work`
`work` är en array av arbetskedjor.

Exempel:

```json
[
  [
    { "kind": "send_order" }
  ],
  [
    { "kind": "planning" }
  ],
  [
    { "kind": "execute_action" }
  ]
]
```

Varje element i `work` är en kedja.

Det enda som får exekveras är:

- `work[N][0]`

Allt längre in i kedjan är framtida arbete eller nästa steg.

### `completed_work`
`completed_work` är historik över avslutat arbete.

Det är inte en aktiv kö och inte en alternativ sanning om nuläget.

## Viktig princip

Replay ska lagra så lite härledd tillståndsdata som möjligt.

Det betyder:

- ingen separat `activity_state`
- ingen separat `active_work`
- ingen separat `planning_state`
- ingen separat `work_queue`

Sådant ska i stället härledas från primärdata:

- `work`
- `completed_work`
- inbox/outbox
- `last_order`
- `memory`
- `control`

## Inbox och outbox

Varje agent har:

- `inbox.jsonl`
- `outbox.jsonl`

### Inbox
`inbox.jsonl` är en transportkö för inkommande order och rapporter.

Vid ingest konsumeras `inbox.jsonl` till statefälten:

- `new_messages` = olästa meddelanden som kan trigga LLM
- `read_messages` = historik över meddelanden som redan har konsumerats av ett lyckat LLM-anrop
- `inbox` = kompatibilitetsspegel av `new_messages`

### Outbox
Outbox innehåller naturligt språk som ska skickas vidare via CoT/chat.

Outbox är transportkö, inte intern planeringsmodell.

## LLM-kontrakt

Replay använder LLM för beslut, inte för hela state machine-logiken.

LLM returnerar beslut som sedan översätts till `work`.

LLM ska inte styra intern exekvering direkt.

## Språkkontrakt

Replay använder två språkdomäner.

### Engelska för struktur
Engelska används för:

- JSON-nycklar
- enum-värden
- interna typer
- `kind`
- `action`
- `formation`
- `tempo`
- `engagement`
- maskinella kontrakt

### Svenska för naturligt språk
Svenska används för:

- ordertexter
- rapporter
- `message`
- `report_up`
- `order_text`
- `planning.reason`
- narrativ text
- referee-narrativ
- svensk doktrin och svenskt militärt språk

## Doktrinprofiler och promptar

Promptar och doktrin ska ligga i source, inte i Python-strängar.

Replay ska kunna stödja flera profiler.

Nuvarande svensk profil ligger under:

- `takctl/replay/prompts/swedish_home_guard/`

Det gör att andra framtida profiler kan läggas till separat, exempelvis andra nationella doktriner eller andra typer av förband.

## Konfiguration

Replay ska följa samma konfigurationsmodell som övrig takctl.

### Tillåtet
- `takctl.conf`
- `secrets.conf`

### Inte tillåtet
- miljövariabler som primär configmekanism
- spridda ad hoc-konstanter för provider, model eller path

LLM-provider, modell och secrets ska läsas via takctl-konfig.

## Roll för chefer och underställda

Chefer kommunicerar nedåt i naturligt språk.

Det som skickas i order och rapporter ska vara användbart för mottagaren, inte teknisk metadata.

Intern maskinell struktur hålls separat i replay-state.

## Referee och world state

Referee/world-state ska ses som ett separat maskininterface.

Det ska inte blandas ihop med naturligt språk mellan chefer och underställda.

Naturlig princip:

- chef ↔ underställd: naturligt språk
- replay/referee/world: maskinellt kontrakt

## Praktisk tumregel

Om något nytt statefält föreslås ska första frågan vara:

> Kan detta härledas från `work`, `completed_work`, inbox/outbox eller memory?

Om svaret är ja ska det normalt inte lagras separat.

