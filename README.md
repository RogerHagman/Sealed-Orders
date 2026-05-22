# Sealed-Orders

## Version 0.07

- Trade ships that are not intercepted or forced to smuggle complete trade.
- A shipyard can be started during the buy phase for 5 gold.
- A shipyard requires 5 labor to complete.
- Each ship left in port for a turn contributes 1 labor to an active shipyard.
- Once complete, the shipyard permanently lowers that nation's ship purchase cost by 1 gold.
- Completed shipyards count as 5 value in final asset scoring.

## Version 0.08

- Fire ships are a sealed order alongside trade, raid, and guard.
- Each successful fire ship burns 1 enemy guard ship before raid-vs-guard battles.
- Successful fire ships are lost after burning enemy guards.
- A surviving fire ship destroys the enemy shipyard if no guards can oppose it.
- Fire ships withdraw safely if there are no enemy guards or shipyard in position.

## Version 0.09

- Fire ships now require a 5 gold buy-phase upgrade before they can be assigned.
- Nations that have not bought fire ship plans cannot assign fire ships in sealed orders.

## Version 0.10

- A nation wins immediately by destroying the enemy home port.
- A home port can be destroyed when the defender has 0 ships and the attacker has at least 5 active raid ships after combat.
- Raid-vs-guard battles now use overwhelming force.
- A force at least 50% larger destroys up to 2 enemy ships in the encounter.
- A force at least 100% larger destroys all enemy ships in the encounter.

## Version 0.11

- Forts can be started during the buy phase for 10 gold.
- A fort requires 10 labor to complete.
- Idle ships apply labor to shipyards first, then forts.
- A completed fort blocks 1 shipyard-bound fire ship each turn.
- A completed fort raises the raid force needed to destroy the home port from 5 to 10.
- Completed forts count as 10 value in final asset scoring.

## Version 0.12

- Base ship cost increases from 5 to 6 gold.
- A completed shipyard lowers ship cost from 6 to 5 gold.
- Trade guilds can be started during the buy phase for 8 gold.
- A trade guild requires 6 labor to complete.
- Idle ships apply labor to shipyards first, then forts, then trade guilds.
- A completed trade guild adds bonus gold from completed trade each turn.
- Trade guild bonus is 1 gold minimum when at least 1 trade ship completes trade, then +1 gold per full 5 completed trade ships.
- Completed trade guilds count as 8 value in final asset scoring.

## Version 0.13

- Buy phase now uses a repeatable numbered action menu.
- Unavailable buy-phase actions stay visible with disabled reasons.
- Players can take multiple buy-phase actions before choosing Done.
- Final-month payroll still launches automatically before menu actions.

## Version 0.14

- End-of-turn summaries show gold, ships, asset, and order ledgers.
- Summaries include changed convoy, infrastructure, and fire ship plan statuses.
- The summary appears after both players finish the buy phase.

## Version 0.15

- Added a non-interactive self-play tournament mode.
- Run `python3 main.py --self-play 100` to let bot strategies play 100 games.
- Add `--seed 1` for repeatable results while tuning strategies or rules.
- The report ranks bot archetypes by win rate, average turns, average assets, and port wins.
- Bot strategy and tournament code lives in `bot_playtest.py`.

## Version 0.16

- Added human-vs-AI mode.
- Run `python3 main.py --play-ai` to face the default Privateer AI.
- Use `--ai-strategy Merchant`, `Privateer`, `Builder`, `Admiral`, or `Opportunist`.
- Add `--seed 1` for repeatable AI choices while testing.

## Version 0.17

- Human-vs-AI games are recorded after completion.
- Records are appended as JSON lines to `ai_game_log.jsonl` by default.
- Use `--ai-log path/to/file.jsonl` to choose a different log file.
- Each record includes the AI strategy, winner, final scores, and turn-by-turn orders.
- Run `python3 main.py --ai-log-summary` to summarize recorded human-vs-AI results.

## Version 0.18

- Added evolving strategy training from random initial weights.
- Run `python3 main.py --train-evolving 25 --learning-rate 0.25`.
- The trainer mutates candidate strategies, evaluates them against the bot roster, and blends toward better candidates.
- Use `--training-games` and `--mutation-scale` to tune how noisy or exploratory training should be.
- Use `--evolved-output evolved_strategy.json` to save the final learned weights.

## Version 0.19

- Evolving strategy training can now export learning curves.
- Use `--training-history training.csv` or `training.json` for per-generation metrics.
- Use `--training-graph training.svg` to create a browser-viewable win-rate graph.

## Version 0.20

- Added `Human Shadow`, a bot profile inferred from recorded human-vs-Privateer games.
- Evolving strategy training now includes `Human Shadow` in the default opponent roster.
