import json
import multiprocessing
import random
import time
from concurrent.futures import ProcessPoolExecutor
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from game_state import Rules
from bot_benchmark import benchmark_strategy
from bot_roster import default_bot_strategies
from bot_runtime import SelfPlayGame
from bot_strategy import (
    BOT_WEIGHT_FIELDS,
    DOMINANCE_CAP_PER_GAME,
    MATCHUP_FLOOR_PENALTY,
    MATCHUP_FLOOR_RECOVERY_BONUS,
    MATCHUP_FLOOR_WIN_RATE,
    PORT_LOSS_PRESSURE_PENALTY,
    ROBUSTNESS_ALLOWED_REGRESSION,
    ROBUSTNESS_CATASTROPHIC_REGRESSION,
    ROBUSTNESS_REGRESSION_PREMIUM,
    SUSTAIN_REPAIR_BONUS,
    SURVIVAL_ADMIRAL_BONUS,
    SURVIVAL_ADMIRALTY_BONUS,
    SURVIVAL_DRY_DOCK_BONUS,
    SURVIVAL_FORT_BONUS,
    SURVIVAL_GUARD_CAPTAIN_BONUS,
    SURVIVAL_SHIPYARD_BONUS,
    SURVIVAL_TRADE_GUILD_BONUS,
    blend_strategy,
    clamp,
    copy_strategy,
    mutate_strategy,
    random_evolving_strategy,
    strategy_record,
)
from training_dashboard import (
    handle_dashboard_input,
    prepare_dashboard_terminal,
    render_training_dashboard,
    restore_dashboard_terminal,
    wait_for_dashboard_finish_choice,
)


def process_pool_context():
    try:
        return multiprocessing.get_context("fork")
    except ValueError:
        return None


def empty_evaluation_stats():
    return {
        "games": 0,
        "wins": 0,
        "draws": 0,
        "ports": 0,
        "score_total": 0,
        "opponent_score_total": 0,
        "turns_total": 0,
        "shipyard_started": 0,
        "shipyard_completed": 0,
        "fort_started": 0,
        "fort_completed": 0,
        "trade_guild_started": 0,
        "trade_guild_completed": 0,
        "fishing_dock_built": 0,
        "fishing_dock_active": 0,
        "fishing_boats_total": 0,
        "dry_dock_started": 0,
        "dry_dock_completed": 0,
        "admiralty_started": 0,
        "admiralty_completed": 0,
        "admiralty_overtime_used": 0,
        "admiral_games": 0,
        "admirals_total": 0,
        "damaged_ships_total": 0,
        "raid_actions_total": 0,
        "raid_damage_events_total": 0,
        "raid_repairs_total": 0,
        "damaged_raiders_sunk_total": 0,
        "raid_skirmish_damage_total": 0,
        "raid_skirmish_sunk_total": 0,
        "guard_captain_games": 0,
        "guard_captains_total": 0,
        "guard_captain_ship_captures_total": 0,
        "port_losses": 0,
        "dominance_cap_penalty": 0,
        "matchup_floor_penalty": 0,
        "matchup_recovery_bonus": 0,
        "port_loss_pressure_penalty": 0,
        "survival_infra_bonus": 0,
        "min_matchup_win_rate": 1.0,
        "fitness": 0,
    }


def evaluate_strategy(
    strategy,
    opponents,
    games_per_opponent,
    rng,
    workers=1,
    executor=None,
):
    if workers and workers > 1 and len(opponents) > 1:
        return evaluate_strategy_parallel(
            strategy,
            opponents,
            games_per_opponent,
            rng,
            workers,
            executor,
        )

    stats = empty_evaluation_stats()
    for opponent in opponents:
        matchup_stats, matchup = evaluate_matchup_raw(
            strategy,
            opponent,
            games_per_opponent,
            rng,
        )
        merge_evaluation_stats(stats, matchup_stats)
        matchup_fitness = matchup_stats["fitness"]
        apply_matchup_pressure(stats, matchup, matchup_fitness)

    apply_matchup_recovery_bonus(stats)
    return stats


def evaluate_strategy_parallel(
    strategy,
    opponents,
    games_per_opponent,
    rng,
    workers,
    executor=None,
):
    seeds = [rng.randrange(2**63) for _ in opponents]
    stats = empty_evaluation_stats()
    max_workers = min(workers, len(opponents))
    tasks = [
        (copy_strategy(strategy), opponent, games_per_opponent, seed)
        for opponent, seed in zip(opponents, seeds)
    ]
    if executor is None:
        with ProcessPoolExecutor(
            max_workers=max_workers,
            mp_context=process_pool_context(),
        ) as local_executor:
            apply_parallel_matchups(stats, local_executor, tasks)
    else:
        apply_parallel_matchups(stats, executor, tasks)

    apply_matchup_recovery_bonus(stats)
    return stats


def apply_parallel_matchups(stats, executor, tasks):
    for matchup_stats, matchup in executor.map(evaluate_matchup_worker, tasks):
        merge_evaluation_stats(stats, matchup_stats)
        apply_matchup_pressure(stats, matchup, matchup_stats["fitness"])


def evaluate_matchup_worker(args):
    strategy, opponent, games_per_opponent, seed = args
    return evaluate_matchup_raw(
        strategy,
        opponent,
        games_per_opponent,
        random.Random(seed),
    )


def evaluate_matchup_raw(strategy, opponent, games_per_opponent, rng):
    stats = empty_evaluation_stats()
    matchup = {
        "games": 0,
        "wins": 0,
        "ports": 0,
    }
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
        add_game_to_evaluation_stats(stats, matchup, game, result, evolving_index)

    return stats, matchup


def add_game_to_evaluation_stats(stats, matchup, game, result, evolving_index):
    evolving_score = result["scores"][evolving_index]
    opponent_score = result["scores"][1 - evolving_index]
    margin = evolving_score - opponent_score
    capped_margin = clamp(margin, -50, 50)

    stats["games"] += 1
    matchup["games"] += 1
    stats["score_total"] += evolving_score
    stats["opponent_score_total"] += opponent_score
    stats["turns_total"] += result["turns"]
    stats["fitness"] += capped_margin
    player = game.players[evolving_index]
    if player.shipyard_started or player.shipyard_completed:
        stats["shipyard_started"] += 1
    if player.shipyard_completed:
        stats["shipyard_completed"] += 1
        stats["survival_infra_bonus"] += SURVIVAL_SHIPYARD_BONUS
        stats["fitness"] += SURVIVAL_SHIPYARD_BONUS
    if player.fort_started or player.fort_completed:
        stats["fort_started"] += 1
    if player.fort_completed:
        stats["fort_completed"] += 1
        stats["survival_infra_bonus"] += SURVIVAL_FORT_BONUS
        stats["fitness"] += SURVIVAL_FORT_BONUS
    if player.trade_guild_started or player.trade_guild_completed:
        stats["trade_guild_started"] += 1
    if player.trade_guild_completed:
        stats["trade_guild_completed"] += 1
        stats["survival_infra_bonus"] += SURVIVAL_TRADE_GUILD_BONUS
        stats["fitness"] += SURVIVAL_TRADE_GUILD_BONUS
    if player.fishing_dock_built:
        stats["fishing_dock_built"] += 1
    if player.fishing_dock_built and not player.fishing_dock_disabled:
        stats["fishing_dock_active"] += 1
    stats["fishing_boats_total"] += player.fishing_boats
    if player.dry_dock_started or player.dry_dock_completed:
        stats["dry_dock_started"] += 1
    if player.dry_dock_completed:
        stats["dry_dock_completed"] += 1
        stats["survival_infra_bonus"] += SURVIVAL_DRY_DOCK_BONUS
        stats["fitness"] += SURVIVAL_DRY_DOCK_BONUS
    if player.admiralty_started or player.admiralty_completed:
        stats["admiralty_started"] += 1
    if player.admiralty_completed:
        stats["admiralty_completed"] += 1
        stats["survival_infra_bonus"] += SURVIVAL_ADMIRALTY_BONUS
        stats["fitness"] += SURVIVAL_ADMIRALTY_BONUS
    if player.admiralty_overtime_used:
        stats["admiralty_overtime_used"] += 1
    if player.admirals:
        stats["admiral_games"] += 1
    stats["admirals_total"] += player.admirals
    stats["damaged_ships_total"] += player.damaged_ships
    stats["raid_actions_total"] += player.raid_actions_total
    stats["raid_damage_events_total"] += player.raid_damage_events
    stats["raid_repairs_total"] += player.raid_repairs_total
    repair_bonus = player.raid_repairs_total * SUSTAIN_REPAIR_BONUS
    stats["survival_infra_bonus"] += repair_bonus
    stats["fitness"] += repair_bonus
    stats["damaged_raiders_sunk_total"] += player.damaged_raiders_sunk
    stats["raid_skirmish_damage_total"] += player.raid_skirmish_damage
    stats["raid_skirmish_sunk_total"] += player.raid_skirmish_sunk
    if player.guard_captains:
        stats["guard_captain_games"] += 1
    stats["guard_captains_total"] += player.guard_captains
    stats["guard_captain_ship_captures_total"] += (
        player.guard_captain_ship_captures
    )
    captain_bonus = player.guard_captains * SURVIVAL_GUARD_CAPTAIN_BONUS
    stats["survival_infra_bonus"] += captain_bonus
    stats["fitness"] += captain_bonus
    admiral_bonus = player.admirals * SURVIVAL_ADMIRAL_BONUS
    stats["survival_infra_bonus"] += admiral_bonus
    stats["fitness"] += admiral_bonus

    if result["winner_index"] == evolving_index:
        stats["wins"] += 1
        matchup["wins"] += 1
        stats["fitness"] += 250
        if result["win_type"] == "port":
            stats["ports"] += 1
            matchup["ports"] += 1
            stats["fitness"] += 40
    elif result["winner_index"] is None:
        stats["draws"] += 1
        stats["fitness"] += 30
    else:
        stats["fitness"] -= 250
        if result["win_type"] == "port":
            stats["port_losses"] += 1
            port_loss_penalty = 120 + PORT_LOSS_PRESSURE_PENALTY
            stats["port_loss_pressure_penalty"] += PORT_LOSS_PRESSURE_PENALTY
            stats["fitness"] -= port_loss_penalty


def merge_evaluation_stats(total, addition):
    for key, value in addition.items():
        if key == "min_matchup_win_rate":
            total[key] = min(total[key], value)
        else:
            total[key] += value


def apply_matchup_pressure(stats, matchup, matchup_fitness):
    if matchup["games"] == 0:
        return

    win_rate = matchup["wins"] / matchup["games"]
    stats["min_matchup_win_rate"] = min(stats["min_matchup_win_rate"], win_rate)

    dominance_cap = matchup["games"] * DOMINANCE_CAP_PER_GAME
    dominance_cap_penalty = max(0, matchup_fitness - dominance_cap)

    floor_gap = max(0, MATCHUP_FLOOR_WIN_RATE - win_rate)
    floor_penalty = int(floor_gap * matchup["games"] * MATCHUP_FLOOR_PENALTY)

    stats["dominance_cap_penalty"] += dominance_cap_penalty
    stats["matchup_floor_penalty"] += floor_penalty
    stats["fitness"] -= dominance_cap_penalty + floor_penalty


def apply_matchup_recovery_bonus(stats):
    recovery_bonus = int(
        stats["min_matchup_win_rate"] * MATCHUP_FLOOR_RECOVERY_BONUS
    )
    stats["matchup_recovery_bonus"] = recovery_bonus
    stats["fitness"] += recovery_bonus


def passes_robustness_gate(current_stats, candidate_stats):
    current_min = current_stats.get("min_matchup_win_rate", 0)
    candidate_min = candidate_stats.get("min_matchup_win_rate", 0)
    fitness_gain = candidate_stats["fitness"] - current_stats["fitness"]
    regression = current_min - candidate_min

    if candidate_min >= current_min:
        return True
    if current_min >= MATCHUP_FLOOR_WIN_RATE and candidate_min >= MATCHUP_FLOOR_WIN_RATE:
        return True
    if regression <= ROBUSTNESS_ALLOWED_REGRESSION:
        return True
    if (
        candidate_min >= MATCHUP_FLOOR_WIN_RATE
        and fitness_gain >= ROBUSTNESS_REGRESSION_PREMIUM
    ):
        return True
    if (
        regression < ROBUSTNESS_CATASTROPHIC_REGRESSION
        and fitness_gain >= ROBUSTNESS_REGRESSION_PREMIUM
    ):
        return True
    return False



def fresh_evolving_strategy_stats(
    rng,
    opponents,
    games_per_bot,
    workers=1,
    executor=None,
):
    strategy = random_evolving_strategy(rng)
    return strategy, evaluate_strategy(
        strategy,
        opponents,
        games_per_bot,
        rng,
        workers,
        executor,
    )


def train_evolving_strategy(
    generations=25,
    games_per_bot=6,
    learning_rate=0.25,
    mutation_scale=1.0,
    seed=None,
    output_path=None,
    graph_path=None,
    history_path=None,
    show_weights=False,
    weights_interval=1,
    dashboard=False,
    dashboard_history=12,
    dashboard_benchmark_games=100,
    dashboard_window=100,
    initial_strategy=None,
    seed_branch_chance=0.0,
    workers=1,
):
    learning_rate = clamp(learning_rate, 0.0, 1.0)
    seed_branch_chance = clamp(seed_branch_chance, 0.0, 1.0)
    workers = max(1, int(workers or 1))
    dashboard_window = max(25, int(dashboard_window or 100))
    rng = random.Random(seed)
    opponents = default_bot_strategies()
    current = None
    current_stats = None
    history = []
    terminal_settings = prepare_dashboard_terminal(dashboard)
    evaluation_executor = None
    if workers > 1 and len(opponents) > 1:
        evaluation_executor = ProcessPoolExecutor(
            max_workers=min(workers, len(opponents)),
            mp_context=process_pool_context(),
        )

    try:
        print(f"\n=== EVOLVING STRATEGY TRAINING: {generations} GENERATION(S) ===")
        if seed is not None:
            print(f"Seed: {seed}")
        print(f"Learning rate: {learning_rate}, mutation scale: {mutation_scale}")
        if workers > 1:
            print(f"Training workers: {workers}")

        while True:
            run_started_at = time.monotonic()
            current = (
                copy_strategy(initial_strategy)
                if initial_strategy is not None
                else random_evolving_strategy(rng)
            )
            current_stats = evaluate_strategy(
                current,
                opponents,
                games_per_bot,
                rng,
                workers,
                evaluation_executor,
            )
            plateau_generations = 0
            dashboard_message = "Press h for controls."
            recent_lines = []
            plateau_reference_stats = None
            training_events = deque(maxlen=dashboard_window)
            if dashboard:
                recent_lines.append(training_status_line(0, "initial", current_stats))
                render_training_dashboard(
                    generation=0,
                    generations=generations,
                    status="initial",
                    stats=current_stats,
                    strategy=current,
                    recent_lines=recent_lines,
                    learning_rate=learning_rate,
                    mutation_scale=mutation_scale,
                    games_per_bot=games_per_bot,
                    plateau_generations=plateau_generations,
                    dashboard_message=dashboard_message,
                    previous_stats=None,
                    training_events=training_events,
                    run_started_at=run_started_at,
                    seed_branch_chance=seed_branch_chance,
                    workers=workers,
                    dashboard_window=dashboard_window,
                )
            else:
                initial_label = (
                    f"Initial strategy ({current.name})"
                    if initial_strategy is not None
                    else "Initial random strategy"
                )
                print_evolving_strategy(initial_label, current, current_stats)
            history = [
                training_history_record(
                    generation=0,
                    status="initial",
                    stats=current_stats,
                    strategy=current,
                )
            ]
            start_new_run = False

            generation = 1
            while generation <= generations:
                incumbent_stats = dict(current_stats)
                if dashboard:
                    command_result = handle_dashboard_input(
                        current,
                        current_stats,
                        learning_rate,
                        mutation_scale,
                        games_per_bot,
                        generations,
                        generation,
                        dashboard_window,
                        lambda active_games: fresh_evolving_strategy_stats(
                            rng,
                            opponents,
                            active_games,
                            workers,
                            evaluation_executor,
                        ),
                    )
                    (
                        current,
                        current_stats,
                        learning_rate,
                        mutation_scale,
                        games_per_bot,
                        generations,
                        new_dashboard_window,
                        dashboard_message,
                        dashboard_command,
                    ) = command_result
                    if new_dashboard_window != dashboard_window:
                        dashboard_window = new_dashboard_window
                        training_events = deque(
                            training_events,
                            maxlen=dashboard_window,
                        )
                    if dashboard_command == "new":
                        start_new_run = True
                        break
                    if dashboard_command == "restart":
                        run_started_at = time.monotonic()
                        plateau_generations = 0
                        plateau_reference_stats = None
                        training_events.clear()
                        recent_lines.append(
                            training_status_line(generation - 1, "restart", current_stats)
                        )
                        recent_lines = recent_lines[-dashboard_history:]
                        render_training_dashboard(
                            generation=generation - 1,
                            generations=generations,
                            status="restart",
                            stats=current_stats,
                            strategy=current,
                            recent_lines=recent_lines,
                            learning_rate=learning_rate,
                            mutation_scale=mutation_scale,
                            games_per_bot=games_per_bot,
                            plateau_generations=plateau_generations,
                            dashboard_message=dashboard_message,
                            previous_stats=None,
                            training_events=training_events,
                            run_started_at=run_started_at,
                            seed_branch_chance=seed_branch_chance,
                            workers=workers,
                            dashboard_window=dashboard_window,
                        )

                branch_from_seed = (
                    initial_strategy is not None
                    and seed_branch_chance > 0
                    and rng.random() < seed_branch_chance
                )
                candidate_base = (
                    copy_strategy(initial_strategy)
                    if branch_from_seed
                    else current
                )
                candidate = mutate_strategy(candidate_base, rng, mutation_scale)
                candidate_stats = evaluate_strategy(
                    candidate,
                    opponents,
                    games_per_bot,
                    rng,
                    workers,
                    evaluation_executor,
                )
                candidate_improved = candidate_stats["fitness"] > current_stats["fitness"]

                if candidate_improved:
                    if not passes_robustness_gate(current_stats, candidate_stats):
                        status = "fragile"
                    else:
                        blended = blend_strategy(current, candidate, learning_rate)
                        blended_stats = evaluate_strategy(
                            blended,
                            opponents,
                            games_per_bot,
                            rng,
                            workers,
                            evaluation_executor,
                        )
                        if blended_stats["fitness"] > current_stats["fitness"]:
                            if passes_robustness_gate(current_stats, blended_stats):
                                current = blended
                                current_stats = blended_stats
                                status = "learned"
                            else:
                                status = "fragile"
                        else:
                            status = "kept"
                else:
                    status = "kept"

                if status == "learned":
                    plateau_generations = 0
                    plateau_reference_stats = incumbent_stats
                else:
                    plateau_generations += 1
                training_events.append(
                    {
                        "status": status,
                        "candidate_improved": candidate_improved,
                        "seed_branch": branch_from_seed,
                    }
                )

                status_line = training_status_line(generation, status, current_stats)
                recent_lines.append(status_line)
                recent_lines = recent_lines[-dashboard_history:]
                if dashboard:
                    render_training_dashboard(
                        generation=generation,
                        generations=generations,
                        status=status,
                        stats=current_stats,
                        strategy=current,
                        recent_lines=recent_lines,
                        learning_rate=learning_rate,
                        mutation_scale=mutation_scale,
                        games_per_bot=games_per_bot,
                        plateau_generations=plateau_generations,
                        dashboard_message=dashboard_message,
                        previous_stats=plateau_reference_stats,
                        training_events=training_events,
                        run_started_at=run_started_at,
                        seed_branch_chance=seed_branch_chance,
                        workers=workers,
                        dashboard_window=dashboard_window,
                    )
                else:
                    print(status_line)
                    if should_print_live_weights(show_weights, weights_interval, generation, status):
                        print(f"         {strategy_compact_line(current)}")
                history.append(
                    training_history_record(
                        generation=generation,
                        status=status,
                        stats=current_stats,
                        strategy=current,
                    )
                )
                generation += 1

            if start_new_run:
                continue

            if dashboard:
                finish_choice = wait_for_dashboard_finish_choice(
                    terminal_settings=terminal_settings,
                    generation=generations,
                    generations=generations,
                    stats=current_stats,
                    strategy=current,
                    recent_lines=recent_lines,
                    learning_rate=learning_rate,
                    mutation_scale=mutation_scale,
                    games_per_bot=games_per_bot,
                    plateau_generations=plateau_generations,
                    benchmark_games=dashboard_benchmark_games,
                    previous_stats=plateau_reference_stats,
                    training_events=training_events,
                    run_started_at=run_started_at,
                    seed_branch_chance=seed_branch_chance,
                    workers=workers,
                    dashboard_window=dashboard_window,
                    benchmark_callback=lambda active_games: benchmark_strategy(
                        current,
                        opponents,
                        active_games,
                        rng,
                        workers,
                    ),
                    save_callback=lambda output_path: write_evolved_strategy(
                        current,
                        current_stats,
                        output_path,
                        seed,
                        history,
                    ),
                )
                if finish_choice == "new":
                    continue
                break
            else:
                break
    finally:
        if evaluation_executor is not None:
            evaluation_executor.shutdown()
        restore_dashboard_terminal(terminal_settings)

    if dashboard:
        print()
    print_evolving_strategy("Final evolved strategy", current, current_stats)
    if output_path is not None:
        write_evolved_strategy(current, current_stats, output_path, seed, history)
    if history_path is not None:
        write_training_history(history, history_path)
    if graph_path is not None:
        write_training_graph(history, graph_path)

    return current


def training_status_line(generation, status, stats):
    return (
        f"Gen {generation:>3}: {status:<7} "
        f"fitness {stats['fitness']:>7.1f}, "
        f"wins {stats['wins']:>3}/{stats['games']}, "
        f"min matchup {stats['min_matchup_win_rate'] * 100:>4.0f}%, "
        f"avg assets {average(stats, 'score_total'):>5.1f}"
    )


def should_print_live_weights(show_weights, weights_interval, generation, status):
    if not show_weights:
        return False
    if status == "learned":
        return True
    if weights_interval <= 0:
        return False
    return generation % weights_interval == 0


def strategy_compact_line(strategy):
    return (
        "weights "
        f"T/R/G/F={strategy.trade_weight:.2f}/"
        f"{strategy.raid_weight:.2f}/"
        f"{strategy.guard_weight:.2f}/"
        f"{strategy.fire_weight:.2f}; "
        "buy "
        f"convoy={strategy.convoy_bias:.2f}, "
        f"ship={strategy.ship_bias:.2f}; "
        "infra "
        f"yard={strategy.shipyard_bias:.2f}, "
        f"fort={strategy.fort_bias:.2f}, "
        f"guild={strategy.trade_guild_bias:.2f}, "
        f"dock={strategy.fishing_dock_bias:.2f}, "
        f"boat={strategy.fishing_boat_bias:.2f}, "
        f"dry={strategy.dry_dock_bias:.2f}, "
        f"adm={strategy.admiralty_bias:.2f}, "
        f"admiral={strategy.admiral_bias:.2f}, "
        f"overtime={strategy.overtime_bias:.2f}, "
        f"repair={strategy.repair_bias:.2f}, "
        f"idle={strategy.construction_idle_bias:.2f}; "
        f"priority={strategy.build_priority}"
    )


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
        f"  infrastructure: shipyard={strategy.shipyard_bias:.2f}, "
        f"fort={strategy.fort_bias:.2f}, "
        f"trade_guild={strategy.trade_guild_bias:.2f}, "
        f"guard_captain={strategy.guard_captain_bias:.2f}, "
        f"fire_plans={strategy.fire_plans_bias:.2f}, "
        f"fishing_dock={strategy.fishing_dock_bias:.2f}, "
        f"fishing_boat={strategy.fishing_boat_bias:.2f}, "
        f"dry_dock={strategy.dry_dock_bias:.2f}, "
        f"admiralty={strategy.admiralty_bias:.2f}, "
        f"admiral={strategy.admiral_bias:.2f}, "
        f"overtime={strategy.overtime_bias:.2f}, "
        f"repair={strategy.repair_bias:.2f}, "
        f"idle={strategy.construction_idle_bias:.2f}"
    )
    print(
        f"  results: fitness={stats['fitness']:.1f}, "
        f"wins={stats['wins']}/{stats['games']}, draws={stats['draws']}, "
        f"port wins={stats['ports']}, port losses={stats.get('port_losses', 0)}, "
        f"min matchup={stats.get('min_matchup_win_rate', 0) * 100:.1f}%, "
        f"avg turns={average(stats, 'turns_total'):.1f}, "
        f"avg assets={average(stats, 'score_total'):.1f}, "
        f"avg opponent={average(stats, 'opponent_score_total'):.1f}"
    )
    print(
        f"  matchup pressure: dominance cap={stats.get('dominance_cap_penalty', 0)}, "
        f"floor penalty={stats.get('matchup_floor_penalty', 0)}, "
        f"recovery bonus={stats.get('matchup_recovery_bonus', 0)}"
    )
    print(
        f"  survival pressure: port loss penalty="
        f"{stats.get('port_loss_pressure_penalty', 0)}, "
        f"infra bonus={stats.get('survival_infra_bonus', 0)}"
    )
    print(
        f"  infra use: forts {stats.get('fort_completed', 0)}/{stats['games']}, "
        f"shipyards {stats.get('shipyard_completed', 0)}/{stats['games']}, "
        f"guilds {stats.get('trade_guild_completed', 0)}/{stats['games']}, "
        f"fishing docks {stats.get('fishing_dock_active', 0)}/{stats['games']}, "
        f"dry docks {stats.get('dry_dock_completed', 0)}/{stats['games']}, "
        f"admiralties {stats.get('admiralty_completed', 0)}/{stats['games']}, "
        f"overtime {stats.get('admiralty_overtime_used', 0)}/{stats['games']}, "
        f"admirals {stats.get('admiral_games', 0)}/{stats['games']} "
        f"(avg {average(stats, 'admirals_total'):.1f}), "
        f"boats avg {average(stats, 'fishing_boats_total'):.1f}, "
        f"raid actions avg {average(stats, 'raid_actions_total'):.1f}, "
        f"damage events avg {average(stats, 'raid_damage_events_total'):.1f}, "
        f"skirmish damage avg {average(stats, 'raid_skirmish_damage_total'):.1f}, "
        f"skirmish sunk avg {average(stats, 'raid_skirmish_sunk_total'):.1f}, "
        f"repairs avg {average(stats, 'raid_repairs_total'):.1f}, "
        f"sunk damaged avg {average(stats, 'damaged_raiders_sunk_total'):.1f}, "
        f"damaged avg {average(stats, 'damaged_ships_total'):.1f}, "
        f"smugglers captured avg "
        f"{average(stats, 'guard_captain_ship_captures_total'):.1f}, "
        f"captains {stats.get('guard_captain_games', 0)}/{stats['games']} "
        f"(avg {average(stats, 'guard_captains_total'):.1f})"
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
        "port_losses": stats.get("port_losses", 0),
        "dominance_cap_penalty": stats.get("dominance_cap_penalty", 0),
        "matchup_floor_penalty": stats.get("matchup_floor_penalty", 0),
        "matchup_recovery_bonus": stats.get("matchup_recovery_bonus", 0),
        "port_loss_pressure_penalty": stats.get("port_loss_pressure_penalty", 0),
        "survival_infra_bonus": stats.get("survival_infra_bonus", 0),
        "min_matchup_win_rate": stats.get("min_matchup_win_rate", 0),
        "win_rate": stats["wins"] / stats["games"] if stats["games"] else 0,
        "avg_turns": average(stats, "turns_total"),
        "avg_assets": average(stats, "score_total"),
        "avg_opponent_assets": average(stats, "opponent_score_total"),
        "shipyard_started_rate": average(stats, "shipyard_started"),
        "shipyard_completed_rate": average(stats, "shipyard_completed"),
        "fort_started_rate": average(stats, "fort_started"),
        "fort_completed_rate": average(stats, "fort_completed"),
        "trade_guild_started_rate": average(stats, "trade_guild_started"),
        "trade_guild_completed_rate": average(stats, "trade_guild_completed"),
        "fishing_dock_built_rate": average(stats, "fishing_dock_built"),
        "fishing_dock_active_rate": average(stats, "fishing_dock_active"),
        "avg_fishing_boats": average(stats, "fishing_boats_total"),
        "dry_dock_started_rate": average(stats, "dry_dock_started"),
        "dry_dock_completed_rate": average(stats, "dry_dock_completed"),
        "admiralty_started_rate": average(stats, "admiralty_started"),
        "admiralty_completed_rate": average(stats, "admiralty_completed"),
        "admiralty_overtime_rate": average(stats, "admiralty_overtime_used"),
        "admiral_rate": average(stats, "admiral_games"),
        "avg_admirals": average(stats, "admirals_total"),
        "avg_damaged_ships": average(stats, "damaged_ships_total"),
        "avg_raid_actions": average(stats, "raid_actions_total"),
        "avg_raid_damage_events": average(stats, "raid_damage_events_total"),
        "avg_raid_skirmish_damage": average(stats, "raid_skirmish_damage_total"),
        "avg_raid_skirmish_sunk": average(stats, "raid_skirmish_sunk_total"),
        "avg_raid_repairs": average(stats, "raid_repairs_total"),
        "avg_damaged_raiders_sunk": average(stats, "damaged_raiders_sunk_total"),
        "guard_captain_rate": average(stats, "guard_captain_games"),
        "avg_guard_captains": average(stats, "guard_captains_total"),
        "avg_guard_captain_ship_captures": average(
            stats,
            "guard_captain_ship_captures_total",
        ),
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
        "port_losses",
        "dominance_cap_penalty",
        "matchup_floor_penalty",
        "matchup_recovery_bonus",
        "port_loss_pressure_penalty",
        "survival_infra_bonus",
        "min_matchup_win_rate",
        "win_rate",
        "avg_turns",
        "avg_assets",
        "avg_opponent_assets",
        "shipyard_started_rate",
        "shipyard_completed_rate",
        "fort_started_rate",
        "fort_completed_rate",
        "trade_guild_started_rate",
        "trade_guild_completed_rate",
        "fishing_dock_built_rate",
        "fishing_dock_active_rate",
        "avg_fishing_boats",
        "dry_dock_started_rate",
        "dry_dock_completed_rate",
        "admiralty_started_rate",
        "admiralty_completed_rate",
        "admiralty_overtime_rate",
        "admiral_rate",
        "avg_admirals",
        "avg_damaged_ships",
        "avg_raid_actions",
        "avg_raid_damage_events",
        "avg_raid_skirmish_damage",
        "avg_raid_skirmish_sunk",
        "avg_raid_repairs",
        "avg_damaged_raiders_sunk",
        "guard_captain_rate",
        "avg_guard_captains",
        "avg_guard_captain_ship_captures",
        "trade_weight",
        "raid_weight",
        "guard_weight",
        "fire_weight",
        "convoy_bias",
        "ship_bias",
        "shipyard_bias",
        "fort_bias",
        "trade_guild_bias",
        "fishing_dock_bias",
        "fishing_boat_bias",
        "dry_dock_bias",
        "admiralty_bias",
        "admiral_bias",
        "overtime_bias",
        "repair_bias",
        "guard_captain_bias",
        "fire_plans_bias",
        "construction_idle_bias",
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
                row["port_losses"],
                row["dominance_cap_penalty"],
                row["matchup_floor_penalty"],
                row["matchup_recovery_bonus"],
                row["port_loss_pressure_penalty"],
                row["survival_infra_bonus"],
                f"{row['min_matchup_win_rate']:.6f}",
                f"{row['win_rate']:.6f}",
                f"{row['avg_turns']:.6f}",
                f"{row['avg_assets']:.6f}",
                f"{row['avg_opponent_assets']:.6f}",
                f"{row['shipyard_started_rate']:.6f}",
                f"{row['shipyard_completed_rate']:.6f}",
                f"{row['fort_started_rate']:.6f}",
                f"{row['fort_completed_rate']:.6f}",
                f"{row['trade_guild_started_rate']:.6f}",
                f"{row['trade_guild_completed_rate']:.6f}",
                f"{row['fishing_dock_built_rate']:.6f}",
                f"{row['fishing_dock_active_rate']:.6f}",
                f"{row['avg_fishing_boats']:.6f}",
                f"{row['dry_dock_started_rate']:.6f}",
                f"{row['dry_dock_completed_rate']:.6f}",
                f"{row['admiralty_started_rate']:.6f}",
                f"{row['admiralty_completed_rate']:.6f}",
                f"{row['admiralty_overtime_rate']:.6f}",
                f"{row['admiral_rate']:.6f}",
                f"{row['avg_admirals']:.6f}",
                f"{row['avg_damaged_ships']:.6f}",
                f"{row['avg_raid_actions']:.6f}",
                f"{row['avg_raid_damage_events']:.6f}",
                f"{row['avg_raid_skirmish_damage']:.6f}",
                f"{row['avg_raid_skirmish_sunk']:.6f}",
                f"{row['avg_raid_repairs']:.6f}",
                f"{row['avg_damaged_raiders_sunk']:.6f}",
                f"{row['guard_captain_rate']:.6f}",
                f"{row['avg_guard_captains']:.6f}",
                f"{row['avg_guard_captain_ship_captures']:.6f}",
                f"{strategy['trade_weight']:.6f}",
                f"{strategy['raid_weight']:.6f}",
                f"{strategy['guard_weight']:.6f}",
                f"{strategy['fire_weight']:.6f}",
                f"{strategy['convoy_bias']:.6f}",
                f"{strategy['ship_bias']:.6f}",
                f"{strategy['shipyard_bias']:.6f}",
                f"{strategy['fort_bias']:.6f}",
                f"{strategy['trade_guild_bias']:.6f}",
                f"{strategy['fishing_dock_bias']:.6f}",
                f"{strategy['fishing_boat_bias']:.6f}",
                f"{strategy['dry_dock_bias']:.6f}",
                f"{strategy['admiralty_bias']:.6f}",
                f"{strategy['admiral_bias']:.6f}",
                f"{strategy['overtime_bias']:.6f}",
                f"{strategy['repair_bias']:.6f}",
                f"{strategy['guard_captain_bias']:.6f}",
                f"{strategy['fire_plans_bias']:.6f}",
                f"{strategy['construction_idle_bias']:.6f}",
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
