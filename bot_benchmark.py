# bot_benchmark.py
"""
Module for benchmarking bot strategies against the default bot roster.
Provides functions to evaluate a strategy file against the default bot roster,
collecting detailed statistics on wins, losses, turns, scores, and other metrics.
Results can be printed in a formatted table and optionally saved to a JSON or CSV file formats.
"""

# Imports
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
    """
    Get a multiprocessing context that supports forking, or return None if not available.
    This is used to ensure that the ProcessPoolExecutor can fork processes on platforms that support it,
    which can be more efficient for CPU-bound tasks. On platforms that do not support forking (like Windows), 
    it will fall back to the default context.
    """
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
    """
    Evaluate a strategy file against the default bot roster and collect benchmark statistics.
    
    Args:
        strategy_path (str): Path to the strategy JSON file to evaluate.
        games_per_opponent (int): Number of games to play against each opponent strategy.
        seed (int, optional): Random seed for reproducibility. If None, a random seed will be used.
        output_path (str, optional): Path to save the benchmark results as JSON or CSV. If None, results will not be saved.
        workers (int, optional): Number of worker processes to use for parallel evaluation. Defaults to 1 (no parallelism).
    """
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
    """Evaluate a head-to-head matchup between two strategies over a specified number of games, 
    collecting detailed statistics.
    Args:
        strategy: The strategy being evaluated.
        opponent: The opponent strategy to benchmark against.
        games: The number of games to play in the head-to-head matchup.
        rng: A random.Random instance for reproducibility.
    Returns (dict):
        A dictionary containing detailed statistics about the head-to-head matchup, including wins, 
        losses, draws, turns, scores, and various in-game metrics.
    """
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
        "dockhouse_completed": 0,
        "dockhouse_burned": 0,
        "dockhands_total": 0,
        "dockhand_idle_turns": 0,
        "dockhand_discounted_repairs": 0,
        "dockhand_boatwright_boats": 0,
        "supply_total": 0,
        "supply_crises": 0,
        "supply_desertions_total": 0,
        "supply_unrest_burns": 0,
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
        if player.dockhouse_completed:
            stats["dockhouse_completed"] += 1
        if player.dockhouse_burned:
            stats["dockhouse_burned"] += 1
        stats["dockhands_total"] += player.dockhands
        stats["dockhand_idle_turns"] += player.dockhand_idle_turns
        stats["dockhand_discounted_repairs"] += player.dockhand_discounted_repairs
        stats["dockhand_boatwright_boats"] += player.dockhand_boatwright_boats
        stats["supply_total"] += player.supply
        stats["supply_crises"] += player.supply_crises
        stats["supply_desertions_total"] += player.supply_desertions_total
        stats["supply_unrest_burns"] += player.supply_unrest_burns

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
    """Print a formatted benchmark table for a strategy's performance against multiple opponents"""
    print(
        "\nOpponent         Games  Wins  Losses  Draws  Win rate  "
        "Port wins  Port losses  Avg turns  Win turns  Loss turns  Avg assets  Opp avg  Supply  Crisis"
    )
    print(
        "---------------  -----  ----  ------  -----  --------  "
        "---------  -----------  ---------  ---------  ----------  ----------  -------  ------  ------"
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
            "dockhouse_completed",
            "dockhouse_burned",
            "dockhands_total",
            "dockhand_idle_turns",
            "dockhand_discounted_repairs",
            "dockhand_boatwright_boats",
            "supply_total",
            "supply_crises",
            "supply_desertions_total",
            "supply_unrest_burns",
        ]:
            totals[key] += row[key]

    total_row = dict(totals)
    total_row["opponent"] = "TOTAL"
    print_strategy_benchmark_row(total_row)


def print_strategy_benchmark_row(row):
    """Print a single row of the strategy benchmark table with calculated metrics
    based on the raw statistics collected for that opponent.
    
    Args:
        row (dict): A dictionary containing raw statistics for a single opponent matchup, including:
            - opponent: The name of the opponent strategy.
            - games: Total number of games played against this opponent.
            - wins: Number of wins against this opponent.
            - losses: Number of losses against this opponent.
            - draws: Number of draws against this opponent.
            - port_wins: Number of wins achieved by capturing the port.
            - port_losses: Number of losses suffered by the opponent capturing the port.
            - turns_total: Total number of turns taken across all games against this opponent.
            - win_turns_total: Total number of turns taken in games that were won.
            - loss_turns_total: Total number of turns taken in games that were lost.
            - score_total: Total score accumulated across all games against this opponent.
            - opponent_score_total: Total score accumulated by the opponent across all games.
            - admiralty_completed: Number of games where the Admiralty was completed.
            - admirals_total: Total number of admirals recruited across all games.
            - dockhouse_completed: Number of games where the Dockhouse was completed.
            - dockhouse_burned: Number of games where the Dockhouse was burned.
            - dockhands_total: Total number of dockhands recruited across all games.
            - dockhand_idle_turns: Total number of turns where dockhands were idle across all games.
            - dockhand_discounted_repairs: Total number of discounted repairs performed by dockhands across all games.
            - dockhand_boatwright_boats: Total number of boats built by dockhands acting as boatwrights across all games.
            - supply_total: Total supply accumulated across all games.
            - supply_crises: Total number of supply crises experienced across all games.
            - supply_desertions_total: Total number of desertions due to supply issues across all games.
            - supply_unrest_burns: Total number of times supply unrest caused burns across all games.
    Returns:
        None: This function prints the formatted row directly to the console and does not return any value
    """
    games = row["games"]
    win_rate = row["wins"] / games if games else 0
    avg_turns = row["turns_total"] / games if games else 0
    avg_win_turns = row["win_turns_total"] / row["wins"] if row["wins"] else 0
    avg_loss_turns = row["loss_turns_total"] / row["losses"] if row["losses"] else 0
    avg_score = row["score_total"] / games if games else 0
    avg_opponent_score = row["opponent_score_total"] / games if games else 0
    avg_supply = row.get("supply_total", 0) / games if games else 0
    avg_crises = row.get("supply_crises", 0) / games if games else 0

    print(
        f"{row['opponent']:<15}  {games:>5}  {row['wins']:>4}  "
        f"{row['losses']:>6}  {row['draws']:>5}  "
        f"{win_rate * 100:>7.1f}%  {row['port_wins']:>9}  "
        f"{row['port_losses']:>11}  {avg_turns:>9.1f}  "
        f"{avg_win_turns:>9.1f}  {avg_loss_turns:>10.1f}  "
        f"{avg_score:>10.1f}  {avg_opponent_score:>7.1f}  "
        f"{avg_supply:>6.1f}  {avg_crises:>6.1f}"
    )


def write_strategy_benchmark(rows, output_path):
    """
    Write the strategy benchmark results to a JSON or CSV file, creating parent directories if needed.
    Args:        rows (list): A list of dictionaries containing benchmark statistics for each opponent matchup.
        output_path (str):  The file path where the benchmark results should be saved. \
                            The file format (JSON or CSV) is determined by the file extension. \
                            If the parent directories do not exist, they will be created automatically.
    Returns: 
        None: This function writes the benchmark results to the specified file and does not return any value.
    """
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
    # TODO: consider refactoring this function to take a config object instead of a long parameter list
    """
    Write the strategy benchmark results to a CSV file with calculated metrics based on the raw statistics collected for each opponent matchup.
    Args:        rows (list): A list of dictionaries containing raw statistics for each opponent matchup, including:
            - opponent: The name of the opponent strategy.
            - games: Total number of games played against this opponent.
            - wins: Number of wins against this opponent.
            - losses: Number of losses against this opponent.
            - draws: Number of draws against this opponent.
            - port_wins: Number of wins achieved by capturing the port.
            - port_losses: Number of losses suffered by the opponent capturing the port.
            - turns_total: Total number of turns taken across all games against this opponent.
            - win_turns_total: Total number of turns taken in games that were won.
            - loss_turns_total: Total number of turns taken in games that were lost.
            - score_total: Total score accumulated across all games against this opponent.
            - opponent_score_total: Total score accumulated by the opponent across all games.
            - admiralty_completed: Number of games where the Admiralty was completed.
            - admirals_total: Total number of admirals recruited across all games.
            - dockhouse_completed: Number of games where the Dockhouse was completed.
            - dockhouse_burned: Number of games where the Dockhouse was burned.
            - dockhands_total: Total number of dockhands recruited across all games.
            - dockhand_idle_turns: Total number of turns where dockhands were idle across all games.
            - dockhand_discounted_repairs: Total number of discounted repairs performed by dockhands across all games.
            - dockhand_boatwright_boats: Total number of boats built by dockhands acting as boatwrights across all games.
            - supply_total: Total supply accumulated across all games.
            - supply_crises: Total number of supply crises experienced across all games.
            - supply_desertions_total: Total number of desertions due to supply issues across all games.
            - supply_unrest_burns: Total number of times supply unrest caused burns across all games.
        output_path (str): The file path where the CSV benchmark results should be saved. If the parent directories do not exist, they will be created automatically.
    Returns:
        None: This function writes the benchmark results to the specified CSV file and does not return any value.
    """
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
        "dockhouse_completed_rate",
        "dockhouse_burned_rate",
        "avg_dockhands",
        "avg_dockhand_idle_turns",
        "avg_dockhand_discounted_repairs",
        "avg_dockhand_boatwright_boats",
        "avg_supply",
        "avg_supply_crises",
        "avg_supply_desertions",
        "avg_supply_unrest_burns",
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
                f"{row.get('dockhouse_completed', 0) / games if games else 0:.6f}",
                f"{row.get('dockhouse_burned', 0) / games if games else 0:.6f}",
                f"{row.get('dockhands_total', 0) / games if games else 0:.6f}",
                f"{row.get('dockhand_idle_turns', 0) / games if games else 0:.6f}",
                f"{row.get('dockhand_discounted_repairs', 0) / games if games else 0:.6f}",
                f"{row.get('dockhand_boatwright_boats', 0) / games if games else 0:.6f}",
                f"{row.get('supply_total', 0) / games if games else 0:.6f}",
                f"{row.get('supply_crises', 0) / games if games else 0:.6f}",
                f"{row.get('supply_desertions_total', 0) / games if games else 0:.6f}",
                f"{row.get('supply_unrest_burns', 0) / games if games else 0:.6f}",
            ]
            output_file.write(",".join(str(value) for value in values))
            output_file.write("\n")


def benchmark_strategy(strategy, opponents, games_per_opponent, rng, workers=1):
    """
    Benchmark a strategy against a list of opponent strategies, optionally using parallel processing.
    Args:        strategy: The strategy to benchmark.
        opponents: A list of opponent strategies to benchmark against.
        games_per_opponent: The number of games to play against each opponent strategy.
        rng: A random.Random instance for reproducibility.
        workers: The number of worker processes to use for parallel evaluation. Defaults to 1 (no parallelism).
    Returns:
        A list of dictionaries containing benchmark statistics for each opponent matchup.
    """

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
    """Worker function to evaluate a head-to-head matchup in a separate process.
    Args:    args (tuple): A tuple containing the strategy, opponent, number of games, and random seed for the matchup.
    Returns:    dict: A dictionary containing detailed statistics about the head-to-head matchup, 
                as returned by the evaluate_head_to_head function.
    """
    strategy, opponent, games_per_opponent, seed = args
    return evaluate_head_to_head(
        strategy,
        opponent,
        games_per_opponent,
        random.Random(seed),
    )
