import json
import multiprocessing
import random
from concurrent.futures import ProcessPoolExecutor
from collections import defaultdict
from pathlib import Path

from bot_roster import default_bot_strategies
from bot_runtime import SelfPlayGame
from bot_strategy import load_strategy


def process_pool_context():
    try:
        return multiprocessing.get_context("fork")
    except ValueError:
        return None


def evaluate_strategy_file(
    strategy_path,
    games_per_opponent=100,
    seed=None,
    output_path=None,
    workers=1,
):
    rng = random.Random(seed)
    workers = max(1, int(workers or 1))
    strategy = load_strategy(strategy_path)
    opponents = default_bot_strategies()
    rows = []

    print(f"\n=== STRATEGY BENCHMARK: {strategy.name} ===")
    print(f"Strategy file: {strategy_path}")
    if seed is not None:
        print(f"Seed: {seed}")
    print(f"Games per opponent: {games_per_opponent}")
    if workers > 1:
        print(f"Workers: {workers}")

    rows = benchmark_strategy(strategy, opponents, games_per_opponent, rng, workers)

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
        "win_turns_total": 0,
        "loss_turns_total": 0,
        "score_total": 0,
        "opponent_score_total": 0,
        "admiralty_completed": 0,
        "admirals_total": 0,
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
        player = game.players[strategy_index]
        if player.admiralty_completed:
            stats["admiralty_completed"] += 1
        stats["admirals_total"] += player.admirals

        if result["winner_index"] == strategy_index:
            stats["wins"] += 1
            stats["win_turns_total"] += result["turns"]
            if result["win_type"] == "port":
                stats["port_wins"] += 1
        elif result["winner_index"] is None:
            stats["draws"] += 1
        else:
            stats["losses"] += 1
            stats["loss_turns_total"] += result["turns"]
            if result["win_type"] == "port":
                stats["port_losses"] += 1

    return stats


def print_strategy_benchmark(rows):
    print(
        "\nOpponent         Games  Wins  Losses  Draws  Win rate  "
        "Port wins  Port losses  Avg turns  Win turns  Loss turns  Avg assets  Opp avg  Admty  Avg adm"
    )
    print(
        "---------------  -----  ----  ------  -----  --------  "
        "---------  -----------  ---------  ---------  ----------  ----------  -------  -----  -------"
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
            "win_turns_total",
            "loss_turns_total",
            "score_total",
            "opponent_score_total",
            "admiralty_completed",
            "admirals_total",
        ]:
            totals[key] += row[key]

    total_row = dict(totals)
    total_row["opponent"] = "TOTAL"
    print_strategy_benchmark_row(total_row)


def print_strategy_benchmark_row(row):
    games = row["games"]
    win_rate = row["wins"] / games if games else 0
    avg_turns = row["turns_total"] / games if games else 0
    avg_win_turns = row["win_turns_total"] / row["wins"] if row["wins"] else 0
    avg_loss_turns = row["loss_turns_total"] / row["losses"] if row["losses"] else 0
    avg_score = row["score_total"] / games if games else 0
    avg_opponent_score = row["opponent_score_total"] / games if games else 0
    admiralty_rate = row.get("admiralty_completed", 0) / games if games else 0
    avg_admirals = row.get("admirals_total", 0) / games if games else 0

    print(
        f"{row['opponent']:<15}  {games:>5}  {row['wins']:>4}  "
        f"{row['losses']:>6}  {row['draws']:>5}  "
        f"{win_rate * 100:>7.1f}%  {row['port_wins']:>9}  "
        f"{row['port_losses']:>11}  {avg_turns:>9.1f}  "
        f"{avg_win_turns:>9.1f}  {avg_loss_turns:>10.1f}  "
        f"{avg_score:>10.1f}  {avg_opponent_score:>7.1f}  "
        f"{admiralty_rate * 100:>4.0f}%  {avg_admirals:>7.1f}"
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
        "avg_win_turns",
        "avg_loss_turns",
        "avg_assets",
        "avg_opponent_assets",
        "admiralty_completed_rate",
        "avg_admirals",
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
                f"{row['win_turns_total'] / row['wins'] if row['wins'] else 0:.6f}",
                f"{row['loss_turns_total'] / row['losses'] if row['losses'] else 0:.6f}",
                f"{row['score_total'] / games if games else 0:.6f}",
                f"{row['opponent_score_total'] / games if games else 0:.6f}",
                f"{row.get('admiralty_completed', 0) / games if games else 0:.6f}",
                f"{row.get('admirals_total', 0) / games if games else 0:.6f}",
            ]
            output_file.write(",".join(str(value) for value in values))
            output_file.write("\n")


def benchmark_strategy(strategy, opponents, games_per_opponent, rng, workers=1):
    workers = max(1, int(workers or 1))
    if workers <= 1 or len(opponents) <= 1:
        return [
            evaluate_head_to_head(strategy, opponent, games_per_opponent, rng)
            for opponent in opponents
        ]

    seeds = [rng.randrange(2**63) for _ in opponents]
    tasks = [
        (strategy, opponent, games_per_opponent, seed)
        for opponent, seed in zip(opponents, seeds)
    ]
    with ProcessPoolExecutor(
        max_workers=min(workers, len(opponents)),
        mp_context=process_pool_context(),
    ) as executor:
        return list(executor.map(evaluate_head_to_head_worker, tasks))


def evaluate_head_to_head_worker(args):
    strategy, opponent, games_per_opponent, seed = args
    return evaluate_head_to_head(
        strategy,
        opponent,
        games_per_opponent,
        random.Random(seed),
    )
