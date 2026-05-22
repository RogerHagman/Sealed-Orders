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
- Run `python3 main.py --play-ai` to choose an AI opponent.
- Run `python3 main.py --play-ai` without `--ai-strategy` to choose an opponent from a menu.
- Use `--ai-strategy "Privateer"` or another bot name to skip the menu.
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

## Version 0.21

- Added evolved strategy benchmarking against the full bot roster.
- Run `python3 main.py --evaluate-strategy evolved_strategy.json --eval-games 500`.
- Use `--eval-output benchmark.csv` or `benchmark.json` to save per-opponent results.

## Version 0.22

- Added `Storm Reaver`, the v4 evolved generalist, to the default bot roster.
- New training and benchmark runs now include `Storm Reaver`.

## Version 0.23

- Infrastructure balance pass to test broader strategic branches.
- Fort labor reduced from 10 to 5, while port defense rises from +5 to +10.
- Shipyard labor reduced from 5 to 3, and ship discount rises from 1 to 2.
- Trade guild cost reduced from 8 to 6, labor from 6 to 5, and bonus step from 5 to 3.

## Version 0.24

- Added `Iron Tempest`, the v6 evolved generalist, to the default bot roster.
- Payroll launch now costs 1 gold per ship and can take a nation below 0 gold.
- Completed trade guilds reduce payroll launch cost by 25%, rounded up.

## Version 0.25

- Restored fort cost and labor to 10 after the temporary infrastructure stress test.
- Evolving strategies now learn infrastructure buy biases and construction idle labor bias directly.
- Training history now records infrastructure start/completion rates.

## Version 0.26

- Completed forts now drive off up to 2 active raid ships before convoy capture or trade interception.
- Fort harbor guns repel raiders without destroying ships or changing open-sea guard battles.

## Version 0.27

- Added guard captains as repeatable buy-phase hires costing 3 gold each, up to 5.
- Guard captains confiscate 1 gold each from enemy trade ships that smuggle past this nation's guards.
- Guard captains add +1 home port defense each only while their nation also has a completed fort.
- Evolving strategies now learn a guard captain buy bias and training history records captain use.

## Version 0.28

- Added `Black Ledger`, the v11 infrastructure-raider hybrid, to the default bot roster.
- Human-vs-AI mode now shows a strategy selection menu when `--ai-strategy` is omitted.

## Version 0.29

- Updated `Human Shadow` from the latest recorded human-vs-AI games.
- Human Shadow now favors shipyard, guard captain, and fort play with more balanced trade, raid, and guard orders.

## Version 0.30

- Added `Bastion Corsair`, the v12 fort-raider hybrid, to the default bot roster.

## Version 0.31

- Added terminal color and cleaner section headers for the interactive game UI.
- Reworked public state, economy, buy phase, turn summary, and final score presentation for easier scanning.
- Color automatically stays off when output is redirected or `NO_COLOR` is set.

## Version 0.32

- Added fishing docks as a cheap domestic economy upgrade.
- Fishing boats cost 2 gold each and produce 1 domestic gold per turn while docks are active.
- Fishing boats are not assignable ships and do not defend the home port.
- Fire ships can disable active fishing docks after shipyard targeting; boats survive but produce no income until the docks are repaired.
- Evolving strategies now learn fishing dock and fishing boat buy biases.

## Bot Meta Notes

### Human Shadow

- `Human Shadow` is a mirror of the current human game log, not an optimized benchmark bot.
- The current profile is based on all 9 recorded human-vs-AI games in `ai_game_log.jsonl`.
- Its order mix favors heavy trade, selective raids, meaningful guards, and almost no fire ships.
- Its buy pattern favors frequent shipyard and trade guild play, with occasional forts and rare captains or fire plans.
- Its first three turns are selected from an opening book mined from human-won games, then it falls back to weighted play.
- After the opening, weighted bots adjust to balance of power: fleet gap, asset gap, income engine, port-kill threats, and fleet pressure.

### The Red Tide

- `The Red Tide` is a dominant exploit against the current bot population, not proof of a solved game.
- Its benchmark strength comes from extreme early raid pressure against bots that fail to survive the first wave and punish a zero-defense fleet.
- The strategy avoids early treasure launches because evolved play sees at-sea treasure as too vulnerable against raid-heavy bots.
- It also underbuilds shipyards because immediate port pressure outperforms compounding economy against the current opponent roster.
- The human counterexample in the log shows the pressure point: launch treasure early, guard through the first raids, start shipyard, let Red Tide run out of ships, then convert the economic lead into a port kill.
