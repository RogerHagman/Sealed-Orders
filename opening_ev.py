#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import csv
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from game_state import Allocation, Rules
from bot_roster import default_bot_strategies, find_strategy
from bot_runtime import SelfPlayGame


BUY_PACKAGES = {
    "none": [],
    "launch_treasure": ["launch_treasure"],
    "start_shipyard": ["start_shipyard"],
    "build_fishing_dock": ["build_fishing_dock"],
    "launch_treasure_shipyard": ["launch_treasure", "start_shipyard"],
    "launch_treasure_buy_ships": ["launch_treasure", "buy_ships"],
    "shipyard_buy_one": ["start_shipyard", "buy_one_ship"],
    "stabilize_first_buy": ["stabilize_first_buy"],
}


def all_allocations(max_ships: int = 3) -> list[Allocation]:
    rows = []
    for trade in range(max_ships + 1):
        for raid in range(max_ships + 1 - trade):
            for guard in range(max_ships + 1 - trade - raid):
                rows.append(Allocation(trade=trade, raid=raid, guard=guard))
    return rows


def allocation_name(a: Allocation) -> str:
    parts = []
    if a.trade:
        parts.append(f"T{a.trade}")
    if a.raid:
        parts.append(f"R{a.raid}")
    if a.guard:
        parts.append(f"G{a.guard}")
    idle = 3 - a.total
    if idle:
        parts.append(f"I{idle}")
    return "_".join(parts) or "I3"


def make_forced_opening_strategy(base_strategy, allocation, buy_package_name):
    strategy = copy.deepcopy(base_strategy)

    strategy.opening_book = [
        {
            "name": f"{allocation_name(allocation)}__{buy_package_name}",
            "weight": 1,
            "turns": {
                1: {
                    "allocation": allocation,
                    "buy_actions": BUY_PACKAGES[buy_package_name],
                    "continue_buy_phase": False,
                },
                2: {
                    "continue_buy_phase": True,
                },
                3: {
                    "continue_buy_phase": True,
                },
            },
        }
    ]

    strategy.opening_choices = {}
    return strategy


@dataclass
class OpeningStats:
    opening: str
    buy_package: str
    games: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    port_wins: int = 0
    port_losses: int = 0
    turns_total: int = 0
    score_total: float = 0.0
    opponent_score_total: float = 0.0

    def row(self, baseline_score: float | None = None) -> dict:
        avg_score = self.score_total / self.games if self.games else 0.0
        avg_opp = self.opponent_score_total / self.games if self.games else 0.0
        win_rate = self.wins / self.games if self.games else 0.0
        loss_rate = self.losses / self.games if self.games else 0.0
        draw_rate = self.draws / self.games if self.games else 0.0
        port_win_rate = self.port_wins / self.games if self.games else 0.0
        port_loss_rate = self.port_losses / self.games if self.games else 0.0
        avg_turns = self.turns_total / self.games if self.games else 0.0

        return {
            "opening": self.opening,
            "buy_package": self.buy_package,
            "games": self.games,
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
            "win_rate": win_rate,
            "loss_rate": loss_rate,
            "draw_rate": draw_rate,
            "port_wins": self.port_wins,
            "port_losses": self.port_losses,
            "port_win_rate": port_win_rate,
            "port_loss_rate": port_loss_rate,
            "avg_turns": avg_turns,
            "avg_assets": avg_score,
            "avg_opponent_assets": avg_opp,
            "asset_margin": avg_score - avg_opp,
            "ev_vs_baseline_assets": None if baseline_score is None else avg_score - baseline_score,
            "robust_ev": (
                avg_score
                - avg_opp * 0.15
                + win_rate * 100
                + port_win_rate * 60
                - port_loss_rate * 100
                - loss_rate * 40
            ),
        }


def play_one(strategy, opponent, seed, strategy_first: bool):
    rng = random.Random(seed)

    if strategy_first:
        player_names = [strategy.name, opponent.name]
        strategies = [copy.deepcopy(strategy), copy.deepcopy(opponent)]
        strategy_index = 0
    else:
        player_names = [opponent.name, strategy.name]
        strategies = [copy.deepcopy(opponent), copy.deepcopy(strategy)]
        strategy_index = 1

    game = SelfPlayGame(player_names, strategies, rng)
    result = game.play_silent()
    opponent_index = 1 - strategy_index

    return result, strategy_index, opponent_index


def eval_opening(base_strategy, opponents, allocation, buy_package, games_per_opponent, seed):
    forced = make_forced_opening_strategy(base_strategy, allocation, buy_package)
    stats = OpeningStats(opening=allocation_name(allocation), buy_package=buy_package)

    for opp_index, opponent in enumerate(opponents):
        for game_index in range(games_per_opponent):
            game_seed = hash((seed, allocation_name(allocation), buy_package, opponent.name, game_index)) & ((1 << 63) - 1)
            strategy_first = game_index % 2 == 0

            result, strategy_index, opponent_index = play_one(
                forced,
                opponent,
                game_seed,
                strategy_first,
            )

            stats.games += 1
            stats.turns_total += result["turns"]
            stats.score_total += result["scores"][strategy_index]
            stats.opponent_score_total += result["scores"][opponent_index]

            if result["winner_index"] == strategy_index:
                stats.wins += 1
                if result["win_type"] == "port":
                    stats.port_wins += 1
            elif result["winner_index"] is None:
                stats.draws += 1
            else:
                stats.losses += 1
                if result["win_type"] == "port":
                    stats.port_losses += 1

    return stats


def eval_baseline(base_strategy, opponents, games_per_opponent, seed):
    stats = OpeningStats(opening="BASELINE", buy_package="normal_bot")

    for opponent in opponents:
        for game_index in range(games_per_opponent):
            game_seed = hash((seed, "BASELINE", opponent.name, game_index)) & ((1 << 63) - 1)
            strategy_first = game_index % 2 == 0

            result, strategy_index, opponent_index = play_one(
                base_strategy,
                opponent,
                game_seed,
                strategy_first,
            )

            stats.games += 1
            stats.turns_total += result["turns"]
            stats.score_total += result["scores"][strategy_index]
            stats.opponent_score_total += result["scores"][opponent_index]

            if result["winner_index"] == strategy_index:
                stats.wins += 1
                if result["win_type"] == "port":
                    stats.port_wins += 1
            elif result["winner_index"] is None:
                stats.draws += 1
            else:
                stats.losses += 1
                if result["win_type"] == "port":
                    stats.port_losses += 1

    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="The Red Tide")
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-turns", type=int)
    parser.add_argument("--output", default="artifacts/benchmarks/opening_ev.csv")
    parser.add_argument(
        "--buy-packages",
        nargs="*",
        default=["none", "launch_treasure", "start_shipyard", "build_fishing_dock", "stabilize_first_buy"],
    )
    args = parser.parse_args()

    if args.max_turns is not None:
        Rules.set_max_turns(args.max_turns)

    base_strategy = find_strategy(args.strategy)
    opponents = [
        opponent
        for opponent in default_bot_strategies()
        if opponent.name != base_strategy.name
    ]

    print(f"Strategy: {base_strategy.name}")
    print(f"Opponents: {len(opponents)}")
    print(f"Games per opponent per opening: {args.games}")
    print(f"Buy packages: {', '.join(args.buy_packages)}")

    baseline = eval_baseline(base_strategy, opponents, args.games, args.seed)
    baseline_row = baseline.row()
    baseline_score = baseline_row["avg_assets"]

    rows = [baseline_row]

    for buy_package in args.buy_packages:
        for allocation in all_allocations(3):
            print(f"EV {allocation_name(allocation):10s} + {buy_package}")
            stats = eval_opening(
                base_strategy,
                opponents,
                allocation,
                buy_package,
                args.games,
                args.seed,
            )
            rows.append(stats.row(baseline_score=baseline_score))

    rows.sort(key=lambda r: r["robust_ev"], reverse=True)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print()
    print(f"Wrote {output_path}")
    print()
    print("Top 20 openings:")
    for r in rows[:20]:
        print(
            f"{r['opening']:10s} {r['buy_package']:22s} "
            f"win={r['win_rate']:.3f} "
            f"assets={r['avg_assets']:.1f} "
            f"margin={r['asset_margin']:.1f} "
            f"portW={r['port_win_rate']:.3f} "
            f"portL={r['port_loss_rate']:.3f} "
            f"robustEV={r['robust_ev']:.1f}"
        )


if __name__ == "__main__":
    main()