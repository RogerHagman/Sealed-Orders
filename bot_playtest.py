import contextlib
import io
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from main import Allocation, Game, Rules

AI_GAME_LOG_PATH = Path("ai_game_log.jsonl")
BOT_WEIGHT_FIELDS = [
    "trade_weight",
    "raid_weight",
    "guard_weight",
    "fire_weight",
    "convoy_bias",
    "ship_bias",
]
BUILD_PROJECTS = ["shipyard", "fort", "trade_guild", "fire_plans"]


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
        BotStrategy(
            name="Human Shadow",
            trade_weight=1.2,
            raid_weight=3.3,
            guard_weight=1.5,
            fire_weight=0.8,
            build_priority=["shipyard", "fire_plans"],
            convoy_bias=0.65,
            ship_bias=0.85,
        ),
        BotStrategy(
            name="Port Reaper",
            trade_weight=1.4,
            raid_weight=3.33,
            guard_weight=0.05,
            fire_weight=3.07,
            build_priority=[],
            convoy_bias=0.03,
            ship_bias=0.74,
        ),
        BotStrategy(
            name="Harbor Lock",
            trade_weight=4.72,
            raid_weight=0.68,
            guard_weight=3.6,
            fire_weight=2.0,
            build_priority=[],
            convoy_bias=0.18,
            ship_bias=0.9,
        ),
        BotStrategy(
            name="Corsair Spark",
            trade_weight=4.4,
            raid_weight=4.01,
            guard_weight=1.55,
            fire_weight=4.31,
            build_priority=[],
            convoy_bias=0.69,
            ship_bias=0.16,
        ),
        BotStrategy(
            name="Storm Reaver",
            trade_weight=2.84,
            raid_weight=3.95,
            guard_weight=2.19,
            fire_weight=4.61,
            build_priority=[],
            convoy_bias=0.32,
            ship_bias=0.74,
        ),
        BotStrategy(
            name="Iron Tempest",
            trade_weight=2.61,
            raid_weight=4.06,
            guard_weight=2.4,
            fire_weight=4.44,
            build_priority=[],
            convoy_bias=0.04,
            ship_bias=0.8,
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


def load_strategy(strategy_path):
    strategy_path = Path(strategy_path)
    with strategy_path.open(encoding="utf-8") as strategy_file:
        record = json.load(strategy_file)

    strategy_data = record.get("strategy", record)
    return BotStrategy(
        name=strategy_data.get("name", strategy_path.stem),
        trade_weight=strategy_data["trade_weight"],
        raid_weight=strategy_data["raid_weight"],
        guard_weight=strategy_data["guard_weight"],
        fire_weight=strategy_data["fire_weight"],
        build_priority=strategy_data.get("build_priority", []),
        convoy_bias=strategy_data["convoy_bias"],
        ship_bias=strategy_data["ship_bias"],
    )


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


def evaluate_strategy_file(strategy_path, games_per_opponent=100, seed=None, output_path=None):
    rng = random.Random(seed)
    strategy = load_strategy(strategy_path)
    opponents = default_bot_strategies()
    rows = []

    print(f"\n=== STRATEGY BENCHMARK: {strategy.name} ===")
    print(f"Strategy file: {strategy_path}")
    if seed is not None:
        print(f"Seed: {seed}")
    print(f"Games per opponent: {games_per_opponent}")

    for opponent in opponents:
        row = evaluate_head_to_head(strategy, opponent, games_per_opponent, rng)
        rows.append(row)

    print_strategy_benchmark(rows)
    if output_path is not None:
        write_strategy_benchmark(rows, output_path)


def evaluate_head_to_head(strategy, opponent, games, rng):
    stats = {
        "opponent": opponent.name,
        "games": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "port_wins": 0,
        "port_losses": 0,
        "turns_total": 0,
        "score_total": 0,
        "opponent_score_total": 0,
    }

    for game_index in range(games):
        if game_index % 2 == 0:
            player_names = [strategy.name, opponent.name]
            strategies = [strategy, opponent]
            strategy_index = 0
        else:
            player_names = [opponent.name, strategy.name]
            strategies = [opponent, strategy]
            strategy_index = 1

        game = SelfPlayGame(player_names, strategies, rng)
        result = game.play_silent()
        opponent_index = 1 - strategy_index

        stats["games"] += 1
        stats["turns_total"] += result["turns"]
        stats["score_total"] += result["scores"][strategy_index]
        stats["opponent_score_total"] += result["scores"][opponent_index]

        if result["winner_index"] == strategy_index:
            stats["wins"] += 1
            if result["win_type"] == "port":
                stats["port_wins"] += 1
        elif result["winner_index"] is None:
            stats["draws"] += 1
        else:
            stats["losses"] += 1
            if result["win_type"] == "port":
                stats["port_losses"] += 1

    return stats


def print_strategy_benchmark(rows):
    print(
        "\nOpponent       Games  Wins  Losses  Draws  Win rate  "
        "Port wins  Port losses  Avg turns  Avg assets  Opp avg"
    )
    print(
        "-------------  -----  ----  ------  -----  --------  "
        "---------  -----------  ---------  ----------  -------"
    )

    totals = defaultdict(int)
    for row in rows:
        print_strategy_benchmark_row(row)
        for key in [
            "games",
            "wins",
            "losses",
            "draws",
            "port_wins",
            "port_losses",
            "turns_total",
            "score_total",
            "opponent_score_total",
        ]:
            totals[key] += row[key]

    total_row = dict(totals)
    total_row["opponent"] = "TOTAL"
    print_strategy_benchmark_row(total_row)


def print_strategy_benchmark_row(row):
    games = row["games"]
    win_rate = row["wins"] / games if games else 0
    avg_turns = row["turns_total"] / games if games else 0
    avg_score = row["score_total"] / games if games else 0
    avg_opponent_score = row["opponent_score_total"] / games if games else 0

    print(
        f"{row['opponent']:<13}  {games:>5}  {row['wins']:>4}  "
        f"{row['losses']:>6}  {row['draws']:>5}  "
        f"{win_rate * 100:>7.1f}%  {row['port_wins']:>9}  "
        f"{row['port_losses']:>11}  {avg_turns:>9.1f}  "
        f"{avg_score:>10.1f}  {avg_opponent_score:>7.1f}"
    )


def write_strategy_benchmark(rows, output_path):
    output_path = Path(output_path)
    if output_path.parent != Path("."):
        output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix.lower() == ".csv":
        write_strategy_benchmark_csv(rows, output_path)
    else:
        with output_path.open("w", encoding="utf-8") as output_file:
            json.dump(rows, output_file, indent=2, sort_keys=True)
            output_file.write("\n")

    print(f"\nStrategy benchmark written to {output_path}.")


def write_strategy_benchmark_csv(rows, output_path):
    headers = [
        "opponent",
        "games",
        "wins",
        "losses",
        "draws",
        "win_rate",
        "port_wins",
        "port_losses",
        "avg_turns",
        "avg_assets",
        "avg_opponent_assets",
    ]
    with output_path.open("w", encoding="utf-8") as output_file:
        output_file.write(",".join(headers))
        output_file.write("\n")
        for row in rows:
            games = row["games"]
            values = [
                row["opponent"],
                games,
                row["wins"],
                row["losses"],
                row["draws"],
                f"{row['wins'] / games if games else 0:.6f}",
                row["port_wins"],
                row["port_losses"],
                f"{row['turns_total'] / games if games else 0:.6f}",
                f"{row['score_total'] / games if games else 0:.6f}",
                f"{row['opponent_score_total'] / games if games else 0:.6f}",
            ]
            output_file.write(",".join(str(value) for value in values))
            output_file.write("\n")


def random_evolving_strategy(rng, name="Evolving"):
    build_priority = BUILD_PROJECTS[:]
    rng.shuffle(build_priority)
    build_count = rng.randint(0, len(build_priority))

    return BotStrategy(
        name=name,
        trade_weight=rng.uniform(0.0, 5.0),
        raid_weight=rng.uniform(0.0, 5.0),
        guard_weight=rng.uniform(0.0, 5.0),
        fire_weight=rng.uniform(0.0, 5.0),
        build_priority=build_priority[:build_count],
        convoy_bias=rng.random(),
        ship_bias=rng.random(),
    )


def mutate_strategy(strategy, rng, mutation_scale):
    mutated = copy_strategy(strategy)
    for field in BOT_WEIGHT_FIELDS:
        value = getattr(mutated, field)
        value += rng.uniform(-mutation_scale, mutation_scale)
        if field.endswith("_bias"):
            value = clamp(value, 0.0, 1.0)
        else:
            value = clamp(value, 0.0, 5.0)
        setattr(mutated, field, value)

    if rng.random() < 0.35:
        mutated.build_priority = mutate_build_priority(mutated.build_priority, rng)

    return mutated


def mutate_build_priority(build_priority, rng):
    projects = build_priority[:]
    action = rng.choice(["add", "remove", "swap"])

    if action == "add":
        available = [project for project in BUILD_PROJECTS if project not in projects]
        if available:
            projects.insert(rng.randint(0, len(projects)), rng.choice(available))
    elif action == "remove" and projects:
        projects.pop(rng.randrange(len(projects)))
    elif action == "swap" and len(projects) >= 2:
        first = rng.randrange(len(projects))
        second = rng.randrange(len(projects))
        projects[first], projects[second] = projects[second], projects[first]

    return projects


def blend_strategy(current, candidate, learning_rate):
    learned = copy_strategy(current)
    for field in BOT_WEIGHT_FIELDS:
        current_value = getattr(current, field)
        candidate_value = getattr(candidate, field)
        value = current_value + (candidate_value - current_value) * learning_rate
        if field.endswith("_bias"):
            value = clamp(value, 0.0, 1.0)
        else:
            value = clamp(value, 0.0, 5.0)
        setattr(learned, field, value)

    learned.build_priority = candidate.build_priority[:]
    return learned


def copy_strategy(strategy):
    return BotStrategy(
        name=strategy.name,
        trade_weight=strategy.trade_weight,
        raid_weight=strategy.raid_weight,
        guard_weight=strategy.guard_weight,
        fire_weight=strategy.fire_weight,
        build_priority=strategy.build_priority[:],
        convoy_bias=strategy.convoy_bias,
        ship_bias=strategy.ship_bias,
    )


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def evaluate_strategy(strategy, opponents, games_per_opponent, rng):
    stats = {
        "games": 0,
        "wins": 0,
        "draws": 0,
        "ports": 0,
        "score_total": 0,
        "opponent_score_total": 0,
        "turns_total": 0,
        "fitness": 0,
    }

    for opponent in opponents:
        for game_index in range(games_per_opponent):
            if game_index % 2 == 0:
                player_names = ["Evolving", opponent.name]
                strategies = [strategy, opponent]
                evolving_index = 0
            else:
                player_names = [opponent.name, "Evolving"]
                strategies = [opponent, strategy]
                evolving_index = 1

            game = SelfPlayGame(player_names, strategies, rng)
            result = game.play_silent()
            evolving_score = result["scores"][evolving_index]
            opponent_score = result["scores"][1 - evolving_index]
            margin = evolving_score - opponent_score

            stats["games"] += 1
            stats["score_total"] += evolving_score
            stats["opponent_score_total"] += opponent_score
            stats["turns_total"] += result["turns"]
            stats["fitness"] += margin

            if result["winner_index"] == evolving_index:
                stats["wins"] += 1
                stats["fitness"] += 100
                if result["win_type"] == "port":
                    stats["ports"] += 1
                    stats["fitness"] += 15
            elif result["winner_index"] is None:
                stats["draws"] += 1
                stats["fitness"] += 30
            else:
                stats["fitness"] -= 40

    return stats


def train_evolving_strategy(
    generations=25,
    games_per_bot=6,
    learning_rate=0.25,
    mutation_scale=1.0,
    seed=None,
    output_path=None,
    graph_path=None,
    history_path=None,
):
    learning_rate = clamp(learning_rate, 0.0, 1.0)
    rng = random.Random(seed)
    opponents = default_bot_strategies()
    current = random_evolving_strategy(rng)
    current_stats = evaluate_strategy(current, opponents, games_per_bot, rng)

    print(f"\n=== EVOLVING STRATEGY TRAINING: {generations} GENERATION(S) ===")
    if seed is not None:
        print(f"Seed: {seed}")
    print(f"Learning rate: {learning_rate}, mutation scale: {mutation_scale}")
    print_evolving_strategy("Initial random strategy", current, current_stats)
    history = [
        training_history_record(
            generation=0,
            status="initial",
            stats=current_stats,
            strategy=current,
        )
    ]

    for generation in range(1, generations + 1):
        candidate = mutate_strategy(current, rng, mutation_scale)
        candidate_stats = evaluate_strategy(candidate, opponents, games_per_bot, rng)

        if candidate_stats["fitness"] > current_stats["fitness"]:
            blended = blend_strategy(current, candidate, learning_rate)
            blended_stats = evaluate_strategy(blended, opponents, games_per_bot, rng)
            if blended_stats["fitness"] > current_stats["fitness"]:
                current = blended
                current_stats = blended_stats
                status = "learned"
            else:
                status = "kept"
        else:
            status = "kept"

        print(
            f"Gen {generation:>3}: {status:<7} "
            f"fitness {current_stats['fitness']:>7.1f}, "
            f"wins {current_stats['wins']:>3}/{current_stats['games']}, "
            f"avg assets {average(current_stats, 'score_total'):>5.1f}"
        )
        history.append(
            training_history_record(
                generation=generation,
                status=status,
                stats=current_stats,
                strategy=current,
            )
        )

    print_evolving_strategy("Final evolved strategy", current, current_stats)
    if output_path is not None:
        write_evolved_strategy(current, current_stats, output_path, seed, history)
    if history_path is not None:
        write_training_history(history, history_path)
    if graph_path is not None:
        write_training_graph(history, graph_path)

    return current


def print_evolving_strategy(label, strategy, stats):
    print(f"\n{label}:")
    print(
        f"  weights: trade={strategy.trade_weight:.2f}, "
        f"raid={strategy.raid_weight:.2f}, guard={strategy.guard_weight:.2f}, "
        f"fire={strategy.fire_weight:.2f}"
    )
    print(
        f"  buy: build_priority={strategy.build_priority}, "
        f"convoy_bias={strategy.convoy_bias:.2f}, ship_bias={strategy.ship_bias:.2f}"
    )
    print(
        f"  results: fitness={stats['fitness']:.1f}, "
        f"wins={stats['wins']}/{stats['games']}, draws={stats['draws']}, "
        f"port wins={stats['ports']}, avg turns={average(stats, 'turns_total'):.1f}, "
        f"avg assets={average(stats, 'score_total'):.1f}, "
        f"avg opponent={average(stats, 'opponent_score_total'):.1f}"
    )


def average(stats, key):
    if stats["games"] == 0:
        return 0
    return stats[key] / stats["games"]


def training_history_record(generation, status, stats, strategy):
    return {
        "generation": generation,
        "status": status,
        "fitness": stats["fitness"],
        "games": stats["games"],
        "wins": stats["wins"],
        "draws": stats["draws"],
        "port_wins": stats["ports"],
        "win_rate": stats["wins"] / stats["games"] if stats["games"] else 0,
        "avg_turns": average(stats, "turns_total"),
        "avg_assets": average(stats, "score_total"),
        "avg_opponent_assets": average(stats, "opponent_score_total"),
        "strategy": strategy_record(strategy),
    }


def write_evolved_strategy(strategy, stats, output_path, seed, history=None):
    output_path = Path(output_path)
    if output_path.parent != Path("."):
        output_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "rules_version": Rules.VERSION,
        "seed": seed,
        "strategy": strategy_record(strategy),
        "training_results": stats,
    }
    if history is not None:
        record["history"] = history

    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(record, output_file, indent=2, sort_keys=True)
        output_file.write("\n")

    print(f"\nEvolved strategy written to {output_path}.")


def write_training_history(history, history_path):
    history_path = Path(history_path)
    if history_path.parent != Path("."):
        history_path.parent.mkdir(parents=True, exist_ok=True)

    if history_path.suffix.lower() == ".csv":
        write_training_history_csv(history, history_path)
    else:
        with history_path.open("w", encoding="utf-8") as history_file:
            json.dump(history, history_file, indent=2, sort_keys=True)
            history_file.write("\n")

    print(f"Training history written to {history_path}.")


def write_training_history_csv(history, history_path):
    headers = [
        "generation",
        "status",
        "fitness",
        "games",
        "wins",
        "draws",
        "port_wins",
        "win_rate",
        "avg_turns",
        "avg_assets",
        "avg_opponent_assets",
        "trade_weight",
        "raid_weight",
        "guard_weight",
        "fire_weight",
        "convoy_bias",
        "ship_bias",
        "build_priority",
    ]
    with history_path.open("w", encoding="utf-8") as history_file:
        history_file.write(",".join(headers))
        history_file.write("\n")
        for row in history:
            strategy = row["strategy"]
            values = [
                row["generation"],
                row["status"],
                row["fitness"],
                row["games"],
                row["wins"],
                row["draws"],
                row["port_wins"],
                f"{row['win_rate']:.6f}",
                f"{row['avg_turns']:.6f}",
                f"{row['avg_assets']:.6f}",
                f"{row['avg_opponent_assets']:.6f}",
                f"{strategy['trade_weight']:.6f}",
                f"{strategy['raid_weight']:.6f}",
                f"{strategy['guard_weight']:.6f}",
                f"{strategy['fire_weight']:.6f}",
                f"{strategy['convoy_bias']:.6f}",
                f"{strategy['ship_bias']:.6f}",
                "|".join(strategy["build_priority"]),
            ]
            history_file.write(",".join(str(value) for value in values))
            history_file.write("\n")


def write_training_graph(history, graph_path):
    graph_path = Path(graph_path)
    if graph_path.parent != Path("."):
        graph_path.parent.mkdir(parents=True, exist_ok=True)

    svg = training_graph_svg(history)
    with graph_path.open("w", encoding="utf-8") as graph_file:
        graph_file.write(svg)

    print(f"Training graph written to {graph_path}.")


def training_graph_svg(history):
    width = 900
    height = 520
    left = 70
    right = 30
    top = 40
    bottom = 70
    chart_width = width - left - right
    chart_height = height - top - bottom
    max_generation = max(row["generation"] for row in history) or 1

    points = []
    for row in history:
        x = left + (row["generation"] / max_generation) * chart_width
        y = top + (1.0 - row["win_rate"]) * chart_height
        points.append((x, y))

    point_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    circles = "\n".join(
        (
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4">'
            f"<title>Generation {row['generation']}: "
            f"{row['win_rate'] * 100:.1f}% win rate, "
            f"fitness {row['fitness']:.1f}</title></circle>"
        )
        for (x, y), row in zip(points, history)
    )
    labels = svg_axis_labels(left, top, chart_width, chart_height, max_generation)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <style>
    text {{ font-family: Arial, sans-serif; fill: #1f2933; }}
    .axis {{ stroke: #1f2933; stroke-width: 2; }}
    .grid {{ stroke: #d8dee9; stroke-width: 1; }}
    polyline {{ fill: none; stroke: #0b6bcb; stroke-width: 3; }}
    circle {{ fill: #0b6bcb; stroke: white; stroke-width: 2; }}
  </style>
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="{width / 2:.0f}" y="24" text-anchor="middle" font-size="20" font-weight="700">Evolving Strategy Win Rate</text>
  <line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + chart_height}"/>
  <line class="axis" x1="{left}" y1="{top + chart_height}" x2="{left + chart_width}" y2="{top + chart_height}"/>
  {labels}
  <polyline points="{point_text}"/>
  {circles}
  <text x="{left + chart_width / 2:.0f}" y="{height - 20}" text-anchor="middle" font-size="14">Generation</text>
  <text x="20" y="{top + chart_height / 2:.0f}" text-anchor="middle" font-size="14" transform="rotate(-90 20 {top + chart_height / 2:.0f})">Win rate</text>
</svg>
"""


def svg_axis_labels(left, top, chart_width, chart_height, max_generation):
    labels = []
    for step in range(0, 6):
        rate = step / 5
        y = top + (1 - rate) * chart_height
        labels.append(
            f'<line class="grid" x1="{left}" y1="{y:.1f}" '
            f'x2="{left + chart_width}" y2="{y:.1f}"/>'
        )
        labels.append(
            f'<text x="{left - 10}" y="{y + 5:.1f}" text-anchor="end" '
            f'font-size="12">{rate * 100:.0f}%</text>'
        )

    for step in range(0, 6):
        generation = round(max_generation * step / 5)
        x = left + (generation / max_generation) * chart_width
        labels.append(
            f'<text x="{x:.1f}" y="{top + chart_height + 22}" '
            f'text-anchor="middle" font-size="12">{generation}</text>'
        )

    return "\n  ".join(labels)


def strategy_record(strategy):
    return {
        "name": strategy.name,
        "trade_weight": strategy.trade_weight,
        "raid_weight": strategy.raid_weight,
        "guard_weight": strategy.guard_weight,
        "fire_weight": strategy.fire_weight,
        "build_priority": strategy.build_priority,
        "convoy_bias": strategy.convoy_bias,
        "ship_bias": strategy.ship_bias,
    }


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
