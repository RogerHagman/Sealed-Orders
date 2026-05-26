import contextlib
import io
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from game_engine import Game
from game_state import Allocation, Rules
from bot_roster import default_bot_strategies, find_strategy


AI_GAME_LOG_PATH = Path("artifacts/logs/ai_game_log.jsonl")


class SelfPlayGame(Game):
    def __init__(self, player_names, strategies, rng):
        super().__init__(player_names)
        self.strategies = strategies
        self.rng = rng

    def play_silent(self):
        with contextlib.redirect_stdout(io.StringIO()):
            while self.turn <= Rules.MAX_TURNS and not self.game_over:
                self.play_bot_turn()
                self.turn += 1

        result = self.result()
        for strategy in self.strategies:
            strategy.clear_game_memory(self)
        return result

    def play_bot_turn(self):
        player_one, player_two = self.players
        strategy_one, strategy_two = self.strategies

        player_one.allocation = strategy_one.choose_allocation(
            self, player_one, player_two, self.rng
        )
        player_two.allocation = strategy_two.choose_allocation(
            self, player_two, player_one, self.rng
        )
        strategy_one.observe_opponent_opening(self, player_one, player_two)
        strategy_two.observe_opponent_opening(self, player_two, player_one)

        self.resolve_orders()
        if self.game_over:
            return

        self.advance_convoys()
        self.apply_supply()
        self.apply_port_labor()
        strategy_one.run_buy_phase(self, player_one, player_two, self.rng)
        strategy_two.run_buy_phase(self, player_two, player_one, self.rng)

    def result(self):
        player_one, player_two = self.players
        if self.port_destroyer is player_one:
            winner_index = 0
            win_type = "port"
        elif self.port_destroyer is player_two:
            winner_index = 1
            win_type = "port"
        elif player_one.asset_score > player_two.asset_score:
            winner_index = 0
            win_type = "assets"
        elif player_two.asset_score > player_one.asset_score:
            winner_index = 1
            win_type = "assets"
        else:
            winner_index = None
            win_type = "draw"

        return {
            "winner_index": winner_index,
            "win_type": win_type,
            "turns": min(self.turn, Rules.MAX_TURNS),
            "scores": [player.asset_score for player in self.players],
            "ships": [player.ships for player in self.players],
        }

    def clear_between_players(self):
        pass

    def wants_emergency_supply_warchest(
        self,
        player,
        need,
        counted_income,
        covered,
        cost,
    ):
        strategy = self.strategies[self.players.index(player)]
        return strategy.wants_emergency_supply_warchest(
            player,
            need,
            counted_income,
            covered,
            cost,
        )


class PlayVsAIGame(Game):
    def __init__(self, human_name, strategy, rng):
        super().__init__([human_name, f"AI {strategy.name}"])
        self.human = self.players[0]
        self.ai = self.players[1]
        self.strategy = strategy
        self.rng = rng
        self.turn_records = []

    def play_turn(self):
        from game_state import UI

        UI.clear_screen()
        print(f"\n=== {self.current_month.upper()} ({self.turn}/{Rules.MAX_TURNS}) ===")
        self.show_state()
        before_snapshot = self.snapshot_turn()

        self.human.allocation = self.prompt_allocation(self.human)
        print(f"\n{self.ai.name} writes sealed orders.")
        self.ai.allocation = self.strategy.choose_allocation(
            self, self.ai, self.human, self.rng
        )
        self.strategy.observe_opponent_opening(self, self.ai, self.human)

        orders_snapshot = self.snapshot_turn()
        self.reveal_orders()
        self.show_bulletin("Resolution", self.resolve_orders)
        if self.game_over:
            after_snapshot = self.snapshot_turn()
            self.record_turn(before_snapshot, orders_snapshot, after_snapshot)
            return
        self.pause_after_resolution()
        self.show_bulletin("Convoy Arrivals", self.advance_convoys)
        self.show_bulletin("Supply", self.apply_supply)
        self.show_bulletin("Port Labor", self.apply_port_labor)
        self.buy_phase()
        after_snapshot = self.snapshot_turn()
        self.record_turn(before_snapshot, orders_snapshot, after_snapshot)
        self.show_turn_summary(before_snapshot, after_snapshot, orders_snapshot)

    def buy_phase(self):
        self.buy_phase_baselines = {self.human: self.snapshot_player(self.human)}
        self.run_buy_menu(self.human)
        from game_state import UI

        before = self.snapshot_player(self.ai)
        self.buy_phase_baselines = {self.ai: before}
        self.strategy.run_buy_phase(self, self.ai, self.human, self.rng)
        after = self.snapshot_player(self.ai)
        lines = [f"{self.ai.name} takes its buy phase."]
        self.add_status_change(lines, "Gold", before, after, "gold")
        self.add_status_change(lines, "Ships", before, after, "ships")
        self.add_status_change(lines, "Shipyard", before, after, "shipyard_status")
        self.add_status_change(lines, "Fort", before, after, "fort_status")
        self.add_status_change(lines, "Trade guild", before, after, "trade_guild_status")
        self.add_status_change(lines, "Fishing", before, after, "fishing_status")
        self.add_status_change(lines, "Supply", before, after, "supply_status")
        self.add_status_change(lines, "Raid fatigue", before, after, "raid_fatigue_status")
        self.add_status_change(lines, "Dry dock", before, after, "dry_dock_status")
        self.add_status_change(lines, "Fire ships", before, after, "fire_ship_status")
        self.add_status_change(lines, "Guard captains", before, after, "guard_captain_status")
        if len(lines) == 1:
            lines.append("No visible purchases.")
        self.render_play_area(
            phase="AI Buy Phase",
            control_lines=["AI completed its buy phase.", "Review the changes."],
            info_lines=lines,
            info_title="AI Harbor Report",
            clear=True,
            include_state=True,
        )
        input("Press Enter to continue...")
        self.buy_phase_baselines = {}
        UI.clear_screen()
        self.show_state()

    def wants_emergency_supply_warchest(
        self,
        player,
        need,
        counted_income,
        covered,
        cost,
    ):
        if player is self.ai:
            return self.strategy.wants_emergency_supply_warchest(
                player,
                need,
                counted_income,
                covered,
                cost,
            )
        return super().wants_emergency_supply_warchest(
            player,
            need,
            counted_income,
            covered,
            cost,
        )

    def record_turn(self, before_snapshot, orders_snapshot, after_snapshot):
        self.turn_records.append(
            {
                "turn": self.turn,
                "month": self.current_month,
                "before": snapshot_record(before_snapshot),
                "orders": snapshot_record(orders_snapshot),
                "after": snapshot_record(after_snapshot),
            }
        )


def write_ai_game_record(game, strategy, seed, log_path=AI_GAME_LOG_PATH):
    log_path = Path(log_path)
    record = build_ai_game_record(game, strategy, seed)
    if log_path.parent != Path("."):
        log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, sort_keys=True))
        log_file.write("\n")

    print(f"\nAI game recorded in {log_path}.")


def build_ai_game_record(game, strategy, seed):
    human = game.human
    ai = game.ai
    winner = ai_game_winner(game)

    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "rules_version": Rules.VERSION,
        "ai_strategy": strategy.name,
        "seed": seed,
        "turns": min(game.turn, Rules.MAX_TURNS),
        "win_type": ai_game_win_type(game),
        "winner": winner,
        "human_won": winner == "human",
        "ai_won": winner == "ai",
        "players": {
            "human": player_record(human),
            "ai": player_record(ai),
        },
        "turns_detail": game.turn_records,
    }


def ai_game_winner(game):
    human = game.human
    ai = game.ai

    if game.port_destroyer is human:
        return "human"
    if game.port_destroyer is ai:
        return "ai"
    if human.asset_score > ai.asset_score:
        return "human"
    if ai.asset_score > human.asset_score:
        return "ai"
    return "draw"


def ai_game_win_type(game):
    if game.port_destroyer is not None:
        return "port"
    if game.human.asset_score == game.ai.asset_score:
        return "draw"
    return "assets"


def player_record(player):
    return {
        "name": player.name,
        "gold": player.gold,
        "ships": player.ships,
        "asset_score": player.asset_score,
        "shipyard_started": player.shipyard_started,
        "shipyard_completed": player.shipyard_completed,
        "fort_started": player.fort_started,
        "fort_completed": player.fort_completed,
        "trade_guild_started": player.trade_guild_started,
        "trade_guild_completed": player.trade_guild_completed,
        "fishing_dock_started": player.fishing_dock_started,
        "fishing_dock_labor": player.fishing_dock_labor,
        "fishing_dock_built": player.fishing_dock_built,
        "fishing_dock_disabled": player.fishing_dock_disabled,
        "fishing_boats": player.fishing_boats,
        "supply": player.supply,
        "supply_need": player.supply_need,
        "supply_crises": player.supply_crises,
        "supply_desertions_total": player.supply_desertions_total,
        "supply_unrest_burns": player.supply_unrest_burns,
        "supply_fishing_losses": player.supply_fishing_losses,
        "raid_actions_total": player.raid_actions_total,
        "damaged_ships": player.damaged_ships,
        "raid_damage_events": player.raid_damage_events,
        "raid_repairs_total": player.raid_repairs_total,
        "damaged_raiders_sunk": player.damaged_raiders_sunk,
        "dry_dock_started": player.dry_dock_started,
        "dry_dock_labor": player.dry_dock_labor,
        "dry_dock_completed": player.dry_dock_completed,
        "fire_ships_unlocked": player.fire_ships_unlocked,
        "guard_captains": player.guard_captains,
        "guard_captain_ship_captures": player.guard_captain_ship_captures,
        "treasure_value": player.treasure_value,
        "treasure_at_sea": player.has_treasure_at_sea,
        "payroll_launched": player.payroll_launched,
        "payroll_at_sea": player.has_payroll_at_sea,
    }


def snapshot_record(snapshot):
    return {
        player_name: {
            key: value_record(value)
            for key, value in player_snapshot.items()
        }
        for player_name, player_snapshot in snapshot.items()
    }


def value_record(value):
    if isinstance(value, Allocation):
        return {
            "trade": value.trade,
            "raid": value.raid,
            "guard": value.guard,
            "fire": value.fire,
            "total": value.total,
        }

    return value


def play_vs_ai(
    human_name="England",
    strategy_name="Privateer",
    seed=None,
    log_path=AI_GAME_LOG_PATH,
):
    rng = random.Random(seed)
    strategy = find_strategy(strategy_name)
    game = PlayVsAIGame(human_name=human_name, strategy=strategy, rng=rng)
    print(f"\nYou are facing AI {strategy.name}.")
    game.play()
    write_ai_game_record(game, strategy, seed, log_path=log_path)


def summarize_ai_games(log_path=AI_GAME_LOG_PATH):
    log_path = Path(log_path)
    if not log_path.exists():
        print(f"No AI game log found at {log_path}.")
        return

    stats = defaultdict(
        lambda: {
            "games": 0,
            "human_wins": 0,
            "ai_wins": 0,
            "draws": 0,
            "turns_total": 0,
            "human_score_total": 0,
            "ai_score_total": 0,
        }
    )

    with log_path.open(encoding="utf-8") as log_file:
        for line in log_file:
            if not line.strip():
                continue
            record = json.loads(line)
            row = stats[record["ai_strategy"]]
            row["games"] += 1
            row["turns_total"] += record["turns"]
            row["human_score_total"] += record["players"]["human"]["asset_score"]
            row["ai_score_total"] += record["players"]["ai"]["asset_score"]

            if record["winner"] == "human":
                row["human_wins"] += 1
            elif record["winner"] == "ai":
                row["ai_wins"] += 1
            else:
                row["draws"] += 1

    print_ai_game_summary(log_path, stats)


def print_ai_game_summary(log_path, stats):
    print(f"\n=== HUMAN VS AI HISTORY: {log_path} ===")
    print(
        "\nAI strategy   Games  Human wins  AI wins  Draws  "
        "Human win rate  Avg turns  Avg human  Avg AI"
    )
    print(
        "------------  -----  ----------  -------  -----  "
        "--------------  ---------  ---------  ------"
    )

    for strategy_name, row in sorted(stats.items()):
        games = row["games"]
        human_win_rate = row["human_wins"] / games if games else 0
        avg_turns = row["turns_total"] / games if games else 0
        avg_human_score = row["human_score_total"] / games if games else 0
        avg_ai_score = row["ai_score_total"] / games if games else 0
        print(
            f"{strategy_name:<12}  {games:>5}  {row['human_wins']:>10}  "
            f"{row['ai_wins']:>7}  {row['draws']:>5}  "
            f"{human_win_rate * 100:>13.1f}%  {avg_turns:>9.1f}  "
            f"{avg_human_score:>9.1f}  {avg_ai_score:>6.1f}"
        )


def run_self_play(games=100, seed=None):
    rng = random.Random(seed)
    strategies = default_bot_strategies()
    stats = defaultdict(
        lambda: {
            "games": 0,
            "wins": 0,
            "draws": 0,
            "ports": 0,
            "turns_total": 0,
            "score_total": 0,
            "ships_total": 0,
        }
    )

    for _ in range(games):
        chosen = [rng.choice(strategies), rng.choice(strategies)]
        game = SelfPlayGame(["Bot A", "Bot B"], chosen, rng)
        result = game.play_silent()

        for index, strategy in enumerate(chosen):
            row = stats[strategy.name]
            row["games"] += 1
            row["turns_total"] += result["turns"]
            row["score_total"] += result["scores"][index]
            row["ships_total"] += result["ships"][index]

            if result["winner_index"] == index:
                row["wins"] += 1
                if result["win_type"] == "port":
                    row["ports"] += 1
            elif result["winner_index"] is None:
                row["draws"] += 1

    print_self_play_report(games, seed, stats)


def print_self_play_report(games, seed, stats):
    print(f"\n=== SELF-PLAY REPORT: {games} GAME(S) ===")
    if seed is not None:
        print(f"Seed: {seed}")

    rows = []
    for name, row in stats.items():
        games_played = row["games"]
        win_rate = row["wins"] / games_played if games_played else 0
        avg_turns = row["turns_total"] / games_played if games_played else 0
        avg_score = row["score_total"] / games_played if games_played else 0
        avg_ships = row["ships_total"] / games_played if games_played else 0
        rows.append((win_rate, avg_score, avg_ships, avg_turns, name, row))

    rows.sort(reverse=True)
    print(
        "\nStrategy         Games  Wins  Draws  Port wins  Win rate  "
        "Avg turns  Avg assets  Avg ships"
    )
    print(
        "---------------  -----  ----  -----  ---------  --------  "
        "---------  ----------  ---------"
    )
    for win_rate, avg_score, avg_ships, avg_turns, name, row in rows:
        print(
            f"{name:<15}  {row['games']:>5}  {row['wins']:>4}  "
            f"{row['draws']:>5}  {row['ports']:>9}  "
            f"{win_rate * 100:>7.1f}%  {avg_turns:>9.1f}  "
            f"{avg_score:>10.1f}  {avg_ships:>9.1f}"
        )

    if not rows:
        return

    best = rows[0]
    print("\nHuman-facing lessons:")
    print(
        f"- Best bot archetype: {best[4]} "
        f"({best[0] * 100:.1f}% win rate, {best[1]:.1f} average assets)."
    )
    print(
        "- Watch convoy timing: bots that raid at-sea treasure and payroll "
        "swing games hard."
    )
    print(
        "- Early shipyards usually matter because cheaper ships compound over "
        "the full year."
    )
    print(
        "- Guards are most valuable when protecting payroll or treasure, not "
        "as a permanent default."
    )
    print(
        "- If the opponent neglects ships, concentrated raids can threaten "
        "a sudden port kill."
    )
