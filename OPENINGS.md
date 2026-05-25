# Sealed Orders Opening Principles

Openings in Sealed Orders are not fixed scripts for the whole game. They are the
first three turns of tempo, risk, and information. A good opening book gives a
bot or player a strong first posture, then hands control back to normal judgment
once the board has declared itself.

## Core Principles

- **Initiative matters.** Raid pressure, early treasure, and shipyard tempo all
  force the opponent to answer your plan instead of freely building theirs.
- **Treasure is a two-turn commitment.** Launching the 10-gold treasure fleet is
  powerful, but it must be protected for both travel turns. A bot that launches
  treasure should expect to guard while it is at sea.
- **Triple guard is not passive.** It denies the aggressive meta, protects early
  convoy lines, and can make raiders spend ships for little or no gain.
- **Triple raid is pressure, not a whole economy.** It can punish greedy trade or
  exposed ports, but raid fatigue and damaged ships mean the line needs a way to
  stabilize.
- **Triple trade is a counterweight.** It is there to punish opponents who over-
  guard or over-respect raid, not to replace defense as the default plan.
- **Shipyard tempo is the clean delayed line.** Staying home, starting shipyard,
  and delaying treasure can be correct when the opponent is likely to attack the
  convoy immediately.
- **Logistics becomes a real late-game front.** In 24-month games, large fleets
  need trade, raid steals, treasure arrivals, or enough fishing cover to keep the
  supply meter out of crisis.
- **Buy actions are conditional.** Opening-book buy actions are attempted in
  order; illegal or unaffordable actions are skipped.

## Named Opening Lines

These names are used directly inside the reusable `NASH_CORE_OPENING_BOOK`.
The older `nash_*` IDs are kept as `code_id` metadata so notes, logs, and older
analysis can still line up.

### Harbor Vault (`nash_triple_guard`)

- Suggested book mix: `45%`
- Current code weight: `45`
- Turn 1 orders: `Trade 0, Raid 0, Guard 3, Fire 0`
- Turn 1 buy line: launch treasure, then stabilize with shipyard/fishing
  docks/guard captain as gold allows
- Turn 2 line: protect the treasure fleet; retry treasure if it failed to
  launch; then resume normal buys
- Three-turn roster EV: `25.25 Assets+Gold`
- Nash-matrix role: stabilizer and anti-aggro response

Harbor Vault is the clean default into a violent field. It does not win the
head-to-head Nash matrix by itself, but it was the best three-turn economic
line against the current roster.

### Red Sail Gambit (`nash_triple_raid`)

- Suggested book mix: `40%`
- Current code weight: `40`
- Turn 1 orders: `Trade 0, Raid 3, Guard 0, Fire 0`
- Turn 1 buy line: launch treasure, then stabilize with early infrastructure
- Turn 2 line: pivot into treasure protection unless a tactical raid remains
  obvious
- Three-turn roster EV: `24.02 Assets+Gold`
- Nash-matrix role: pressure equilibrium line

Red Sail Gambit is the hard-to-exploit pressure line. In the opener-vs-opener
matrix, this was the Nash winner among both old and new openers.

### Merchant's Bluff (`nash_triple_trade`)

- Suggested book mix: `10%`
- Current code weight: `10`
- Turn 1 orders: `Trade 3, Raid 0, Guard 0, Fire 0`
- Turn 1 buy line: launch treasure, then stabilize
- Turn 2 line: protect/rebuild depending on how hard the opponent attacked
- Three-turn roster EV: `23.19 Assets+Gold`
- Nash-matrix role: value counterweight

Merchant's Bluff punishes opponents who over-guard against Red Sail Gambit. It
has a real ceiling, but should stay low-frequency because pure raid pressure can
make it collapse.

### Silent Yard (`nash_yard_hold`)

- Suggested book mix: `5%`
- Current code weight: `5`
- Turn 1 orders: `Trade 0, Raid 0, Guard 3, Fire 0`
- Turn 1 buy line: start shipyard, then buy one ship if affordable
- Turn 2 line: launch treasure, buy one ship if affordable, then resume normal
  buys
- Three-turn roster EV: `19.87 Assets+Gold`
- Nash-matrix role: experimental delayed-economy line

Silent Yard is the slowest current line. It may still matter as a specific
anti-chaos branch, but the short-horizon EV says it should be much rarer than
the current implementation weight.

## EV And Mix Notes

The first study forced each new opening line against the current roster for
three turns. The goal was to maximize final `Assets + Gold`.

| Named line | Code ID | Roster EV | Assets | Gold |
| --- | --- | ---: | ---: | ---: |
| Harbor Vault | `nash_triple_guard` | `25.25` | `21.67` | `3.58` |
| Red Sail Gambit | `nash_triple_raid` | `24.02` | `21.30` | `2.72` |
| Merchant's Bluff | `nash_triple_trade` | `23.19` | `20.65` | `2.54` |
| Silent Yard | `nash_yard_hold` | `19.87` | `19.03` | `0.84` |

The second study treated the openers as a direct opener-vs-opener zero-sum
matrix, using:

```text
payoff = our final (Assets + Gold) - opponent final (Assets + Gold)
```

That matrix favored Red Sail Gambit much more strongly than the roster EV did.
Against only the new book, the approximate Nash solution was:

| Line | Nash pressure mix |
| --- | ---: |
| Red Sail Gambit | `100%` |
| Harbor Vault | `0%` |
| Merchant's Bluff | `0%` |
| Silent Yard | `0%` |

Against old and new openers combined, the same pressure result appeared:

| Line | Nash pressure mix |
| --- | ---: |
| Red Sail Gambit | `100%` |

That does not mean the practical book should be pure raid. It means Red Sail
Gambit is the least exploitable pressure line in a narrow three-turn mirror
matrix. The recommended practical mix keeps Harbor Vault because the roster
meta still rewards stable treasure protection.

Suggested practical mix for the shared book:

| Named line | Suggested mix |
| --- | ---: |
| Harbor Vault | `45%` |
| Red Sail Gambit | `40%` |
| Merchant's Bluff | `10%` |
| Silent Yard | `5%` |

Equivalent relative code weights:

```python
Harbor Vault     45
Red Sail Gambit  40
Merchant's Bluff 10
Silent Yard       5
```

## Legacy Opener Matrix

The old raw-allocation study is still useful because it shows the underlying
threat relationships before the buy scripts take over.

| Old opener | Pure EV vs uniform old field |
| --- | ---: |
| `old_3_raid` | `+6.74` |
| `old_3_guard` | `+1.77` |
| `old_2_raid_1_guard` | `+0.75` |
| `old_2_trade_1_guard` | `-0.50` |
| `old_3_trade` | `-0.85` |
| `old_2_guard_1_trade` | `-1.35` |
| `old_2_guard_1_raid` | `-2.94` |
| `old_111_balanced` | `-3.30` |

Approximate old-opener Nash mix:

| Old opener | Mix |
| --- | ---: |
| `old_3_raid` | `95.6%` |
| `old_3_trade` | `4.3%` |

The old matrix is why the named book cannot ignore raid pressure. Triple guard
is economically excellent against the roster, but triple raid is the forcing
move that shapes the game tree.

## Nash Core Opening Book

Future bots can use the shared book with:

```python
from bot_openings import NASH_CORE_OPENING_BOOK

BotStrategy(
    ...,
    opening_book=NASH_CORE_OPENING_BOOK,
)
```

The current weights are relative selection weights, not percentages. The book
contains four named lines. Each line also keeps its old `nash_*` code ID as
metadata.

### Harbor Vault

- Weight: `45`
- Code ID: `nash_triple_guard`
- Turn 1 orders: `Guard 3`
- Turn 1 buy intent: launch treasure, then stabilize with early infrastructure
- Turn 2 buy intent: retry treasure if it did not launch, then resume normal buy
- Strengths: best default into an aggressive field; protects the treasure line
- Risks: can miss early raid/trade value if the opponent is also peaceful

### Red Sail Gambit

- Weight: `40`
- Code ID: `nash_triple_raid`
- Turn 1 orders: `Raid 3`
- Turn 1 buy intent: launch treasure, then stabilize
- Turn 2 buy intent: retry treasure if needed, then resume normal buy
- Strengths: punishes greedy trade, contests initiative, can threaten weak ports
- Risks: raid fatigue and guard counters can blunt the line quickly

### Merchant's Bluff

- Weight: `10`
- Code ID: `nash_triple_trade`
- Turn 1 orders: `Trade 3`
- Turn 1 buy intent: launch treasure, then stabilize
- Turn 2 buy intent: retry treasure if needed, then resume normal buy
- Strengths: value counterweight against opponents over-guarding the raid range
- Risks: exposed to pure raid and early port pressure

### Silent Yard

- Weight: `5`
- Code ID: `nash_yard_hold`
- Turn 1 orders: `Guard 3`
- Turn 1 buy intent: start shipyard, then buy one ship if affordable
- Turn 2 buy intent: launch treasure, buy one ship if affordable, then resume normal buy
- Strengths: safer delayed-economy line; keeps the treasure fleet off the sea for
  one turn while establishing shipyard tempo
- Risks: lower immediate ceiling than a successful turn-1 treasure launch

## Practical Notes

- A treasure launch should change the next two allocations. If treasure or
  payroll is at sea, guards are not optional window dressing; they are the escort.
- The supply meter rewards steady sea income. A big fleet that stops earning
  can slide into damage, desertion, burned infrastructure, and fishing losses,
  while strong surplus can power up trade guilds and completed trade ships.
- A bot can still have its own personality after the opener. `Nash Fireline`
  remains raid/fire-heavy, while `Nash Admiral` remains more defensive and
  infrastructure-minded.
- Human-proven lines still exist in `HUMAN_WON_OPENING_BOOK`; they are tactical
  examples from logged wins, not the first reusable doctrine.
