import contextlib
import io
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from main import Allocation, Game, Rules

AI_GAME_LOG_PATH = Path("ai_game_log.jsonl")


class BotStrategy:
    def __init__(
        self,
        name,
        trade_weight,
        raid_weight,
        guard_weight,
        fire_weight,
        build_priority,
        convoy_bias,
        ship_bias,
    ):
        self.name = name
        self.trade_weight = trade_weight
        self.raid_weight = raid_weight
        self.guard_weight = guard_weight
        self.fire_weight = fire_weight
        self.build_priority = build_priority
        self.convoy_bias = convoy_bias
        self.ship_bias = ship_bias

    def choose_allocation(self, game, player, opponent, rng):
        ships = player.ships
        if ships <= 0:
            return Allocation()

        weights = {
            "trade": self.trade_weight,
            "raid": self.raid_weight,
            "guard": self.guard_weight,
            "fire": self.fire_weight if player.fire_ships_unlocked else 0,
        }

        if opponent.has_treasure_at_sea:
            weights["raid"] += 2.5
        if opponent.has_payroll_at_sea:
            weights["raid"] += 2.0
        if player.has_treasure_at_sea:
            weights["guard"] += 2.0
        if player.has_payroll_at_sea:
            weights["guard"] += 2.5
        if opponent.ships <= Rules.PORT_ATTACK_SHIPS_REQUIRED:
            weights["raid"] += 1.5
        if opponent.shipyard_started:
            weights["fire"] += 1.5
        if game.turn <= 3 and any(
            [
                player.shipyard_started and not player.shipyard_completed,
                player.fort_started and not player.fort_completed,
                player.trade_guild_started and not player.trade_guild_completed,
            ]
        ):
            ships = max(0, ships - rng.choice([1, 1, 2]))

        allocation = {"trade": 0, "raid": 0, "guard": 0, "fire": 0}
        for _ in range(ships):
            choice = self.weighted_choice(weights, rng)
            allocation[choice] += 1

        return Allocation(
            trade=allocation["trade"],
            raid=allocation["raid"],
            guard=allocation["guard"],
            fire=allocation["fire"],
        )

    def run_buy_phase(self, game, player, opponent, rng):
        game.auto_launch_final_payroll(player)

        for project in self.build_priority:
            if project == "shipyard" and game.shipyard_disabled_reason(player) is None:
                player.start_shipyard()
            elif project == "fort" and game.fort_disabled_reason(player) is None:
                player.start_fort()
            elif (
                project == "trade_guild"
                and game.trade_guild_disabled_reason(player) is None
            ):
                player.start_trade_guild()
            elif (
                project == "fire_plans"
                and game.fire_ship_plans_disabled_reason(player) is None
            ):
                player.unlock_fire_ships()

        if self.should_launch_payroll(game, player, rng):
            player.launch_payroll()

        if self.should_launch_treasure(game, player, rng):
            player.launch_treasure()

        reserve = self.gold_reserve(game)
        affordable = max(0, (player.gold - reserve) // player.ship_cost)
        if affordable > 0:
            if rng.random() < self.ship_bias:
                player.buy_ships(affordable)
            elif affordable > 1:
                player.buy_ships(affordable - 1)

    def should_launch_payroll(self, game, player, rng):
        if game.payroll_launch_disabled_reason(player) is not None:
            return False

        launch_score = self.convoy_bias
        if player.ships >= 6:
            launch_score += 0.2
        if game.turn >= Rules.PAYROLL_FINAL_TURN - 1:
            launch_score += 0.4
        return rng.random() < launch_score

    def should_launch_treasure(self, game, player, rng):
        if game.treasure_launch_disabled_reason(player) is not None:
            return False

        launch_score = self.convoy_bias
        if player.treasure_value >= Rules.TREASURE_BASE_VALUE + 4:
            launch_score += 0.25
        if game.turn >= Rules.MAX_TURNS - Rules.TREASURE_TRAVEL_TURNS - 1:
            launch_score += 0.3
        return rng.random() < launch_score

    def gold_reserve(self, game):
        if game.turn <= 3 and "shipyard" in self.build_priority:
            return 2
        return 0

    def weighted_choice(self, weights, rng):
        total = sum(max(0, weight) for weight in weights.values())
        if total <= 0:
            return "trade"

        roll = rng.random() * total
        running = 0
        for choice, weight in weights.items():
            running += max(0, weight)
            if roll <= running:
                return choice
        return "trade"


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

        return self.result()

    def play_bot_turn(self):
        player_one, player_two = self.players
        strategy_one, strategy_two = self.strategies

        player_one.allocation = strategy_one.choose_allocation(
            self, player_one, player_two, self.rng
        )
        player_two.allocation = strategy_two.choose_allocation(
            self, player_two, player_one, self.rng
        )

        self.resolve_orders()
        if self.game_over:
            return

        self.apply_port_labor()
        self.advance_convoys()
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


class PlayVsAIGame(Game):
    def __init__(self, human_name, strategy, rng):
        super().__init__([human_name, f"AI {strategy.name}"])
        self.human = self.players[0]
        self.ai = self.players[1]
        self.strategy = strategy
        self.rng = rng
        self.turn_records = []

    def play_turn(self):
        print(f"\n=== {self.current_month.upper()} ({self.turn}/{Rules.MAX_TURNS}) ===")
        self.show_state()
        before_snapshot = self.snapshot_turn()

        self.show_player_economy(self.human)
        self.human.allocation = self.prompt_allocation(self.human)
        print(f"\n{self.ai.name} writes sealed orders.")
        self.ai.allocation = self.strategy.choose_allocation(
            self, self.ai, self.human, self.rng
        )

        orders_snapshot = self.snapshot_turn()
        self.reveal_orders()
        self.resolve_orders()
        if self.game_over:
            after_snapshot = self.snapshot_turn()
            self.record_turn(before_snapshot, orders_snapshot, after_snapshot)
            return
        self.pause_after_resolution()
        self.apply_port_labor()
        self.advance_convoys()
        self.buy_phase()
        after_snapshot = self.snapshot_turn()
        self.record_turn(before_snapshot, orders_snapshot, after_snapshot)
        self.show_turn_summary(before_snapshot, after_snapshot, orders_snapshot)

    def buy_phase(self):
        print("\n=== BUY PHASE ===")
        self.run_buy_menu(self.human)
        print(f"\n{self.ai.name} takes its buy phase.")
        self.strategy.run_buy_phase(self, self.ai, self.human, self.rng)
        print(f"{self.ai.name} finishes the buy phase.")
        self.show_state()

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
        "fire_ships_unlocked": player.fire_ships_unlocked,
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


def default_bot_strategies():
    return [
        BotStrategy(
            name="Merchant",
            trade_weight=4.0,
            raid_weight=0.8,
            guard_weight=1.8,
            fire_weight=0.2,
            build_priority=["shipyard", "trade_guild"],
            convoy_bias=0.75,
            ship_bias=0.75,
        ),
        BotStrategy(
            name="Privateer",
            trade_weight=1.4,
            raid_weight=4.0,
            guard_weight=1.1,
            fire_weight=1.2,
            build_priority=["fire_plans", "shipyard"],
            convoy_bias=0.35,
            ship_bias=0.95,
        ),
        BotStrategy(
            name="Builder",
            trade_weight=2.4,
            raid_weight=1.1,
            guard_weight=2.0,
            fire_weight=0.4,
            build_priority=["shipyard", "fort", "trade_guild"],
            convoy_bias=0.55,
            ship_bias=0.65,
        ),
        BotStrategy(
            name="Admiral",
            trade_weight=2.2,
            raid_weight=2.2,
            guard_weight=2.1,
            fire_weight=0.8,
            build_priority=["shipyard", "fire_plans", "fort"],
            convoy_bias=0.6,
            ship_bias=0.85,
        ),
        BotStrategy(
            name="Opportunist",
            trade_weight=2.0,
            raid_weight=2.8,
            guard_weight=1.4,
            fire_weight=0.9,
            build_priority=["shipyard", "trade_guild", "fire_plans"],
            convoy_bias=0.5,
            ship_bias=0.9,
        ),
    ]


def strategy_names():
    return [strategy.name for strategy in default_bot_strategies()]


def find_strategy(name):
    normalized_name = name.strip().lower()
    for strategy in default_bot_strategies():
        if strategy.name.lower() == normalized_name:
            return strategy

    available = ", ".join(strategy_names())
    raise ValueError(f"Unknown AI strategy '{name}'. Available strategies: {available}.")


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
        "\nStrategy       Games  Wins  Draws  Port wins  Win rate  "
        "Avg turns  Avg assets  Avg ships"
    )
    print(
        "-------------  -----  ----  -----  ---------  --------  "
        "---------  ----------  ---------"
    )
    for win_rate, avg_score, avg_ships, avg_turns, name, row in rows:
        print(
            f"{name:<13}  {row['games']:>5}  {row['wins']:>4}  "
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
