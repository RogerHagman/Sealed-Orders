import select
import sys
import termios
import tty
from collections import defaultdict

from bot_strategy import clamp


def prepare_dashboard_terminal(dashboard):
    if not dashboard or not sys.stdin.isatty():
        return None
    settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    return settings


def restore_dashboard_terminal(settings):
    if settings is not None:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)


def handle_dashboard_input(
    current,
    current_stats,
    learning_rate,
    mutation_scale,
    games_per_bot,
    restart_callback,
):
    key = read_dashboard_key()
    if key is None:
        return (
            current,
            current_stats,
            learning_rate,
            mutation_scale,
            games_per_bot,
            "Press h for controls.",
            "none",
        )

    if key == "[":
        learning_rate = clamp(learning_rate - 0.01, 0.0, 1.0)
        message = f"learning rate lowered to {learning_rate:.2f}"
    elif key == "]":
        learning_rate = clamp(learning_rate + 0.01, 0.0, 1.0)
        message = f"learning rate raised to {learning_rate:.2f}"
    elif key == "-":
        mutation_scale = max(0.0, mutation_scale - 0.05)
        message = f"mutation scale lowered to {mutation_scale:.2f}"
    elif key in {"+", "="}:
        mutation_scale += 0.05
        message = f"mutation scale raised to {mutation_scale:.2f}"
    elif key == "g":
        games_per_bot = max(1, games_per_bot - 5)
        message = f"training games lowered to {games_per_bot}"
    elif key == "G":
        games_per_bot += 5
        message = f"training games raised to {games_per_bot}"
    elif key == "r":
        current, current_stats = restart_callback(games_per_bot)
        message = "restarted from a fresh random strategy"
        return (
            current,
            current_stats,
            learning_rate,
            mutation_scale,
            games_per_bot,
            message,
            "restart",
        )
    elif key in {"n", "N"}:
        return (
            current,
            current_stats,
            learning_rate,
            mutation_scale,
            games_per_bot,
            "starting a new run",
            "new",
        )
    elif key == "h":
        message = "controls: [] lr, -/+ mutation, g/G games, r restart, n new run"
    else:
        message = f"ignored key {key!r}; press h for controls"

    return (
        current,
        current_stats,
        learning_rate,
        mutation_scale,
        games_per_bot,
        message,
        "none",
    )


def read_dashboard_key():
    if not sys.stdin.isatty():
        return None
    readable, _, _ = select.select([sys.stdin], [], [], 0)
    if not readable:
        return None
    return sys.stdin.read(1)


def wait_for_dashboard_finish_choice(
    terminal_settings,
    generation,
    generations,
    stats,
    strategy,
    recent_lines,
    learning_rate,
    mutation_scale,
    games_per_bot,
    plateau_generations,
    benchmark_games,
    benchmark_callback,
    save_callback,
):
    if not sys.stdin.isatty():
        return "save"

    message = "finished: b benchmark, w write file, s save+exit, n new run"
    benchmark_rows = None
    while True:
        render_training_dashboard(
            generation=generation,
            generations=generations,
            status="finished",
            stats=stats,
            strategy=strategy,
            recent_lines=recent_lines,
            learning_rate=learning_rate,
            mutation_scale=mutation_scale,
            games_per_bot=games_per_bot,
            plateau_generations=plateau_generations,
            dashboard_message=message,
            finished=True,
            benchmark_games=benchmark_games,
            benchmark_rows=benchmark_rows,
        )
        key = sys.stdin.read(1)
        if key in {"s", "S", "\r", "\n"}:
            return "save"
        if key in {"n", "N", "r", "R"}:
            return "new"
        if key in {"w", "W"}:
            output_path = prompt_dashboard_line(
                terminal_settings,
                "\nSave current strategy as JSON file: ",
            )
            if output_path:
                save_callback(output_path)
                message = f"saved checkpoint to {output_path}"
            else:
                message = "save cancelled"
        elif key in {"b", "B"}:
            render_training_dashboard(
                generation=generation,
                generations=generations,
                status="benchmarking",
                stats=stats,
                strategy=strategy,
                recent_lines=recent_lines,
                learning_rate=learning_rate,
                mutation_scale=mutation_scale,
                games_per_bot=games_per_bot,
                plateau_generations=plateau_generations,
                dashboard_message=f"running benchmark: {benchmark_games} games/opponent",
                finished=True,
                benchmark_games=benchmark_games,
                benchmark_rows=benchmark_rows,
            )
            benchmark_rows = benchmark_callback(benchmark_games)
            message = "benchmark complete: b rerun, w write file, s save+exit, n new run"
        else:
            message = "press b benchmark, w write file, s save+exit, or n new run"


def prompt_dashboard_line(terminal_settings, prompt):
    restore_dashboard_terminal(terminal_settings)
    try:
        return input(prompt).strip()
    finally:
        if terminal_settings is not None:
            tty.setcbreak(sys.stdin.fileno())


def gauge(value, minimum, maximum, width=18):
    if maximum <= minimum:
        ratio = 0.0
    else:
        ratio = (value - minimum) / (maximum - minimum)
    ratio = clamp(ratio, 0.0, 1.0)
    filled = round(ratio * width)
    return "[" + "#" * filled + "." * (width - filled) + "]"


def average(stats, key):
    if stats["games"] == 0:
        return 0
    return stats[key] / stats["games"]


def render_training_dashboard(
    generation,
    generations,
    status,
    stats,
    strategy,
    recent_lines,
    learning_rate,
    mutation_scale,
    games_per_bot,
    plateau_generations,
    dashboard_message,
    finished=False,
    benchmark_games=None,
    benchmark_rows=None,
):
    print("\033[2J\033[H", end="")
    print(f"=== EVOLVING STRATEGY DASHBOARD ({generation}/{generations}) ===")
    win_rate = stats["wins"] / stats["games"] if stats["games"] else 0
    min_matchup = stats.get("min_matchup_win_rate", 0)
    avg_assets = average(stats, "score_total")
    print(
        f"status={status}  "
        f"plateau={plateau_generations} gen  "
        f"fitness={stats['fitness']:.1f}  "
        f"wins={stats['wins']}/{stats['games']} ({win_rate * 100:.1f}%)  "
        f"min={min_matchup * 100:.1f}%  "
        f"assets={avg_assets:.1f}  "
        f"opp={average(stats, 'opponent_score_total'):.1f}"
    )
    print(
        f"knobs: lr={learning_rate:.2f}  mutation={mutation_scale:.2f}  "
        f"games/opponent={games_per_bot}  message={dashboard_message}"
    )
    print(
        f"gauges: win {gauge(win_rate, 0, 1)}  "
        f"min {gauge(min_matchup, 0, 1)}  "
        f"plateau {gauge(min(plateau_generations, 100), 0, 100)}"
    )
    print(
        f"ports={stats['ports']}  "
        f"port_losses={stats.get('port_losses', 0)}  "
        f"damage={average(stats, 'raid_damage_events_total'):.1f}/game  "
        f"repairs={average(stats, 'raid_repairs_total'):.1f}/game  "
        f"sunk_damaged={average(stats, 'damaged_raiders_sunk_total'):.1f}/game  "
        f"smugglers={average(stats, 'guard_captain_ship_captures_total'):.1f}/game"
    )
    print()
    print(
        "orders: "
        f"trade={strategy.trade_weight:.2f}  "
        f"raid={strategy.raid_weight:.2f}  "
        f"guard={strategy.guard_weight:.2f}  "
        f"fire={strategy.fire_weight:.2f}"
    )
    print(
        "buy:    "
        f"convoy={strategy.convoy_bias:.2f}  "
        f"ship={strategy.ship_bias:.2f}  "
        f"idle={strategy.construction_idle_bias:.2f}  "
        f"repair={strategy.repair_bias:.2f}"
    )
    print(
        "infra:  "
        f"yard={strategy.shipyard_bias:.2f}  "
        f"fort={strategy.fort_bias:.2f}  "
        f"guild={strategy.trade_guild_bias:.2f}  "
        f"captain={strategy.guard_captain_bias:.2f}  "
        f"fire_plans={strategy.fire_plans_bias:.2f}"
    )
    print(
        "econ:   "
        f"fishing_dock={strategy.fishing_dock_bias:.2f}  "
        f"boat={strategy.fishing_boat_bias:.2f}  "
        f"dry_dock={strategy.dry_dock_bias:.2f}"
    )
    print(f"priority: {strategy.build_priority}")
    print()
    if finished:
        print("controls: b benchmark  w write file  s save+exit  n new run")
    else:
        print("controls: [] lr  -/+ mutation  g/G games  r restart  n new run  h help")
    print("recent:")
    for line in recent_lines:
        print(f"  {line}")
    if finished:
        print()
        print(f"benchmark games/opponent: {benchmark_games}")
        if benchmark_rows is None:
            print("benchmark: not run yet")
        else:
            print("benchmark:")
            for line in dashboard_benchmark_lines(benchmark_rows):
                print(f"  {line}")
    print(flush=True)


def dashboard_benchmark_lines(rows, weakest_count=8):
    total = defaultdict(int)
    for row in rows:
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
            total[key] += row[key]

    total_games = total["games"]
    total_win_rate = total["wins"] / total_games if total_games else 0
    total_avg_assets = total["score_total"] / total_games if total_games else 0
    lines = [
        f"TOTAL {total['wins']}/{total_games} "
        f"({total_win_rate * 100:.1f}%)  "
        f"port losses {total['port_losses']}  "
        f"avg assets {total_avg_assets:.1f}"
    ]

    weakest = sorted(
        rows,
        key=lambda row: (
            row["wins"] / row["games"] if row["games"] else 0,
            -row["port_losses"],
        ),
    )[:weakest_count]
    for row in weakest:
        games = row["games"]
        win_rate = row["wins"] / games if games else 0
        avg_assets = row["score_total"] / games if games else 0
        lines.append(
            f"{row['opponent']:<15} {win_rate * 100:>5.1f}%  "
            f"W/L/D {row['wins']}/{row['losses']}/{row['draws']}  "
            f"PL {row['port_losses']}  assets {avg_assets:.1f}"
        )
    return lines
