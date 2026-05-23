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
- Bot strategy and tournament code is split into smaller `bot_*.py` modules;
  `bot_playtest.py` remains as a compatibility import surface.

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
- Fishing docks cost 3 gold and require 1 labor to complete.
- Fishing boats cost 2 gold each and produce 1 domestic gold per turn while docks are active.
- Fishing boats are not assignable ships and do not defend the home port.
- Fire ships can disable active fishing docks after shipyard targeting; boats survive but produce no income until the docks are repaired.
- Evolving strategies now learn fishing dock and fishing boat buy biases.

## Version 0.33

- Added `Harbor Harvest`, the v19 fishing-raider economy bot, to the default bot roster.
- Added `Reef Tyrant`, the v22 fishing-pressure hybrid, to the default bot roster.
- Added `Tide Reader`, an intra-game adaptive bot that adjusts its order weights after observing early opponent orders.
- Added `Signal Black`, the v29 apex raid-pressure bot, to the default bot roster.
- The default roster now includes an evolved bot that pairs heavy raid pressure with fishing dock snowballing.
- Added `--max-turns` as an experimental game-length override; omit it to keep the normal 12-turn game.
- Use `--max-turns 24` with self-play, training, or strategy benchmarks to test longer economic games.
- Fishing dock construction and repair now require 1 labor; boats remain gold-only once docks are active.
- Trade guilds now grant bonus trade income for every 2 completed trade ships.
- Updated `Human Shadow` from the latest recorded human-vs-AI games and current economy constants.
- Evolving strategy fitness now caps dominance against any single matchup, penalizes low worst-matchup win rates and port losses, rewards worst-matchup recovery and modest survival infrastructure, and only rejects candidates with major worst-matchup regressions.
- Build priority now gives listed projects at least a 20% effective buy bias, making evolved priority order matter even when raw project bias mutates low.

## Version 0.34

- Added raid fatigue: every 10th lifetime raid ship action damages 1 ship for that nation.
- Damaged ships still count as ships and can keep raiding, but surviving enemy guards sink damaged active raiders after normal resolution.
- Damaged ships can be repaired during the buy phase for 4 gold each, or 1 gold each with a completed shipyard.
- Added dry docks as a shipyard-gated project costing 3 gold and 2 labor; completed dry docks make raid repairs free.
- Bot training now evolves repair and dry dock biases.
- Added `Reef Bloom`, the v31 fishing-fortress economy bot, to the default bot roster.

## Version 0.40

- Mechanical refactor only; no intended gameplay, bot, training, CLI, or strategy JSON behavior changes.
- Split game state and rules into `game_state.py`.
- Split the interactive game engine into `game_engine.py`.
- Split bot strategy, roster, runtime, benchmarking, training, and dashboard code into smaller `bot_*.py` and `training_dashboard.py` modules.
- `main.py` remains the CLI entrypoint and still re-exports `Allocation`, `Game`, and `Rules` for compatibility.
- `bot_playtest.py` remains as a compatibility import surface for existing scripts and commands.

## Bot Meta Notes

### Human Shadow

- `Human Shadow` is a mirror of the current human game log, not an optimized benchmark bot.
- The current profile is based on all 16 recorded human-vs-AI games in `ai_game_log.jsonl`, with extra weight on the current fishing-dock and trade-guild rules.
- Its order mix favors very heavy trade, selective raids, meaningful guards, and almost no fire ships.
- Its buy pattern favors shipyard, trade guild, fishing docks, fishing boats, and more frequent guard captains than older versions.
- Its first three turns are selected from an opening book mined from human-won games, then it falls back to weighted play.
- After the opening, weighted bots adjust to balance of power: fleet gap, asset gap, income engine, port-kill threats, and fleet pressure.

### The Red Tide

- `The Red Tide` is a dominant exploit against the current bot population, not proof of a solved game.
- Its benchmark strength comes from extreme early raid pressure against bots that fail to survive the first wave and punish a zero-defense fleet.
- The strategy avoids early treasure launches because evolved play sees at-sea treasure as too vulnerable against raid-heavy bots.
- It also underbuilds shipyards because immediate port pressure outperforms compounding economy against the current opponent roster.
- The human counterexample in the log shows the pressure point: launch treasure early, guard through the first raids, start shipyard, let Red Tide run out of ships, then convert the economic lead into a port kill.

### Signal Black

- `Signal Black` is the v29 evolved apex pressure profile.
- It is nearly pure raid with heavy ship buying, almost no convoy play, and no real build plan.
- Its benchmark strength comes from forcing port races so efficiently that even older predator bots struggle to punish it.
- Treat it as a balance alarm and a training target, not as evidence that the game is solved.

### Tide Reader

- `Tide Reader` is an experimental intra-game learning bot.
- It records the opponent's orders from turns 1-3 and adjusts its later trade, raid, guard, and fire weights inside that game.
- It does not permanently rewrite its strategy, so each new game starts from the same baseline.
- Its baseline is intentionally balanced so the adaptation signal, not a hard-coded opening exploit, is the interesting part of the profile.

### Harbor Harvest

- `Harbor Harvest` is the v19 evolved fishing-raider profile.
- Its benchmark strength comes from suppressing opponents with heavy raids while turning safe gold into fishing docks and boats.
- It is a strong generalist against the current roster, but it remains meaningfully exploitable by dedicated port-pressure plans such as `The Red Tide`.
- Its high fort and guard captain biases rarely fire because fishing boats sit earlier in the build order and consume most spare gold.

### Reef Tyrant

- `Reef Tyrant` is the v22 evolved profile for the current fishing-dock labor and trade-guild rules.
- It combines overwhelming raid pressure with frequent fishing docks, enough boats to snowball, and occasional fort/captain support.
- Its benchmark strength comes from winning by both port pressure and asset growth, rather than collapsing into a pure port-rush or pure fishing economy.
- `The Red Tide` remains its main predator in the current roster, which keeps the profile from looking solved.

### Reef Bloom

- `Reef Bloom` is the v31 evolved fishing-fortress profile.
- It builds around fishing docks and boats, uses fire ships for control, and repairs raid fatigue rather than committing to pure raid pressure.
- Its benchmark strength comes from surviving to final scoring with a large domestic economy, not from frequent port kills.
- Its main predators are the sharp pressure bots, especially `Signal Black` and `The Red Tide`.
