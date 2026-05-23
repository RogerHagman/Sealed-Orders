import os
import select
import sys
import termios
import tty
from collections import defaultdict

from bot_strategy import clamp


COLOR_ENABLED = sys.stdout.isatty() and "NO_COLOR" not in os.environ
COLORS = {
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
    "white": "37",
    "dim": "2",
}


def paint(text, color=None, bold=False):
    if not COLOR_ENABLED:
        return text
    codes = []
    if bold:
        codes.append("1")
    if color in COLORS:
        codes.append(COLORS[color])
    if not codes:
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"


def rate_color(rate):
    if rate < 0.5:
        return "red"
    if rate < 0.7:
        return "yellow"
    if rate < 0.85:
        return "cyan"
    return "green"


def pressure_color(value, warning, danger):
    if value >= danger:
        return "red"
    if value >= warning:
        return "yellow"
    if value <= 0:
        return "green"
    return None


def candidate_pressure_band(value):
    if value < 0.03:
        return "frozen", "red"
    if value < 0.10:
        return "cold", "yellow"
    if value <= 0.30:
        return "healthy", "green"
    if value <= 0.50:
        return "hot", "cyan"
    return "noisy", "red"


def yield_color(value):
    if value <= 0:
        return "red"
    if value < 0.02:
        return "yellow"
    if value <= 0.08:
        return "green"
    return "cyan"


def fragility_band(value, total_candidates):
    if total_candidates == 0:
        return "none", "dim"
    if value < 0.20:
        return "low", "green"
    if value < 0.45:
        return "watch", "yellow"
    if value < 0.60:
        return "high", "yellow"
    return "blocked", "red"


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
    previous_stats,
    training_events,
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
            previous_stats=previous_stats,
            training_events=training_events,
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
                previous_stats=previous_stats,
                training_events=training_events,
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
    color = rate_color(ratio)
    return paint("[" + "#" * filled + "." * (width - filled) + "]", color)


def inverse_gauge(value, minimum, maximum, width=18):
    if maximum <= minimum:
        ratio = 0.0
    else:
        ratio = (value - minimum) / (maximum - minimum)
    ratio = clamp(ratio, 0.0, 1.0)
    filled = round(ratio * width)
    color = "green"
    if ratio >= 0.75:
        color = "red"
    elif ratio >= 0.4:
        color = "yellow"
    return paint("[" + "#" * filled + "." * (width - filled) + "]", color)


def average(stats, key):
    if stats["games"] == 0:
        return 0
    return stats[key] / stats["games"]


def delta_text(current, previous, precision=1, suffix="", lower_is_better=False):
    if previous is None:
        return ""

    delta = current - previous
    if abs(delta) < 0.5 * (10 ** -precision):
        return paint(f" (+0{suffix})", "dim")

    better = delta < 0 if lower_is_better else delta > 0
    color = "green" if better else "red"
    sign = "+" if delta > 0 else ""
    return paint(f" ({sign}{delta:.{precision}f}{suffix})", color, bold=True)


def stat_rate(stats, numerator_key):
    if stats["games"] == 0:
        return 0
    return stats.get(numerator_key, 0) / stats["games"]


def plateau_label(plateau_generations):
    if plateau_generations == 0:
        return "fresh"
    if plateau_generations < 25:
        return "settling"
    if plateau_generations < 100:
        return "stalled"
    return "stuck"


def plateau_color(plateau_generations):
    if plateau_generations == 0:
        return "green"
    if plateau_generations < 25:
        return "cyan"
    if plateau_generations < 100:
        return "yellow"
    return "red"


def training_health(stats, previous_stats, plateau_generations):
    if previous_stats is None:
        return "scouting", "cyan"

    fitness_delta = stats["fitness"] - previous_stats["fitness"]
    win_delta = (stat_rate(stats, "wins") - stat_rate(previous_stats, "wins")) * 100
    min_delta = (
        stats.get("min_matchup_win_rate", 0)
        - previous_stats.get("min_matchup_win_rate", 0)
    ) * 100
    port_loss_delta = (
        stat_rate(stats, "port_losses") - stat_rate(previous_stats, "port_losses")
    ) * 100

    score = 0
    if fitness_delta > 0:
        score += 1
    elif fitness_delta < 0:
        score -= 1
    if win_delta > 1:
        score += 1
    elif win_delta < -1:
        score -= 1
    if min_delta > 1:
        score += 1
    elif min_delta < -1:
        score -= 1
    if port_loss_delta < -1:
        score += 1
    elif port_loss_delta > 1:
        score -= 1

    if score >= 3:
        label, color = "surging", "green"
    elif score >= 1:
        label, color = "improving", "green"
    elif score <= -2:
        label, color = "regressing", "red"
    elif plateau_generations >= 100:
        label, color = "stale", "red"
    elif plateau_generations >= 25:
        label, color = "flat", "yellow"
    else:
        label, color = "mixed", "yellow"

    return label, color


def training_window_stats(events):
    total = len(events)
    counts = {"learned": 0, "fragile": 0, "kept": 0}
    candidate_improved = 0
    for event in events:
        status = event.get("status")
        if status in counts:
            counts[status] += 1
        if event.get("candidate_improved"):
            candidate_improved += 1

    learned = counts["learned"]
    fragile = counts["fragile"]
    kept = counts["kept"]
    yield_rate = learned / total if total else 0
    fragility = fragile / (fragile + learned) if fragile + learned else 0
    candidate_pressure = candidate_improved / total if total else 0

    pressure_label, pressure_color_name = candidate_pressure_band(candidate_pressure)

    if total == 0:
        mode, color = "warming", "cyan"
    elif candidate_pressure < 0.03:
        mode, color = "frozen", "red"
    elif yield_rate >= 0.04 and fragility < 0.35:
        mode, color = "healthy", "green"
    elif candidate_pressure < 0.10:
        mode, color = "cold", "yellow"
    elif fragility >= 0.6:
        mode, color = "constrained", "red"
    elif candidate_pressure > 0.50:
        mode, color = "noisy", "red"
    elif kept / total >= 0.85:
        mode, color = "stale", "yellow"
    else:
        mode, color = "volatile", "yellow"

    return {
        "total": total,
        "learned": learned,
        "fragile": fragile,
        "kept": kept,
        "yield_rate": yield_rate,
        "fragility": fragility,
        "candidate_pressure": candidate_pressure,
        "candidate_pressure_label": pressure_label,
        "candidate_pressure_color": pressure_color_name,
        "mode": mode,
        "color": color,
    }


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
    previous_stats=None,
    training_events=None,
):
    print("\033[2J\033[H", end="")
    print(
        paint(
            f"=== EVOLVING STRATEGY DASHBOARD ({generation}/{generations}) ===",
            "cyan",
            bold=True,
        )
    )
    win_rate = stats["wins"] / stats["games"] if stats["games"] else 0
    min_matchup = stats.get("min_matchup_win_rate", 0)
    avg_assets = average(stats, "score_total")
    previous_win_rate = stat_rate(previous_stats, "wins") if previous_stats else None
    previous_min_matchup = (
        previous_stats.get("min_matchup_win_rate", 0)
        if previous_stats
        else None
    )
    previous_assets = (
        average(previous_stats, "score_total") if previous_stats else None
    )
    previous_opp_assets = (
        average(previous_stats, "opponent_score_total") if previous_stats else None
    )
    status_color = {
        "learned": "green",
        "fragile": "red",
        "benchmarking": "yellow",
        "finished": "cyan",
        "restart": "magenta",
    }.get(status)
    port_losses = stats.get("port_losses", 0)
    port_loss_rate = port_losses / stats["games"] if stats["games"] else 0
    port_losses_text = paint(
        f"port_losses={port_losses}",
        pressure_color(port_loss_rate, 0.05, 0.2),
        bold=port_loss_rate >= 0.2,
    )
    plateau_status = plateau_label(plateau_generations)
    health_label, health_color = training_health(
        stats,
        previous_stats,
        plateau_generations,
    )
    window = training_window_stats(training_events or [])
    yield_text = paint(
        f"{window['yield_rate'] * 100:.1f}%",
        yield_color(window["yield_rate"]),
    )
    fragility_label, fragility_color = fragility_band(
        window["fragility"],
        window["fragile"] + window["learned"],
    )
    fragility_text = paint(
        f"{window['fragility'] * 100:.1f}% {fragility_label}",
        fragility_color,
    )
    candidate_pressure_text = paint(
        f"{window['candidate_pressure'] * 100:.1f}% {window['candidate_pressure_label']}",
        window["candidate_pressure_color"],
        bold=window["candidate_pressure_label"] in {"frozen", "healthy", "noisy"},
    )
    print(
        f"status={paint(status, status_color, bold=bool(status_color))}  "
        f"plateau={paint(f'{plateau_status}({plateau_generations})', plateau_color(plateau_generations), bold=plateau_generations >= 100)}  "
        f"health={paint(health_label, health_color, bold=True)}  "
        f"fitness={stats['fitness']:.1f}"
        f"{delta_text(stats['fitness'], previous_stats['fitness'] if previous_stats else None, precision=1)}  "
        f"wins={stats['wins']}/{stats['games']} "
        f"{paint(f'{win_rate * 100:.1f}%', rate_color(win_rate), bold=True)}"
        f"{delta_text(win_rate * 100, previous_win_rate * 100 if previous_win_rate is not None else None, precision=1, suffix='%')}  "
        f"min={paint(f'{min_matchup * 100:.1f}%', rate_color(min_matchup), bold=True)}"
        f"{delta_text(min_matchup * 100, previous_min_matchup * 100 if previous_min_matchup is not None else None, precision=1, suffix='%')}  "
        f"assets={avg_assets:.1f}"
        f"{delta_text(avg_assets, previous_assets, precision=1)}  "
        f"opp={average(stats, 'opponent_score_total'):.1f}"
        f"{delta_text(average(stats, 'opponent_score_total'), previous_opp_assets, precision=1, lower_is_better=True)}"
    )
    print(
        f"{paint('knobs:', 'blue', bold=True)} "
        f"lr={learning_rate:.2f}  mutation={mutation_scale:.2f}  "
        f"games/opponent={games_per_bot}  "
        f"message={paint(dashboard_message, 'white')}"
    )
    print(
        f"{paint('gauges:', 'blue', bold=True)} win {gauge(win_rate, 0, 1)}  "
        f"min {gauge(min_matchup, 0, 1)}  "
        f"plateau {inverse_gauge(min(plateau_generations, 100), 0, 100)}"
    )
    print(
        f"{paint('window:', 'blue', bold=True)} "
        f"n={window['total']}  "
        f"yield={yield_text}  "
        f"fragility={fragility_text}  "
        f"candidate_pressure={candidate_pressure_text}  "
        f"learned/fragile/kept={window['learned']}/{window['fragile']}/{window['kept']}  "
        f"mode={paint(window['mode'], window['color'], bold=True)}"
    )
    print(
        f"ports={paint(str(stats['ports']), 'green' if stats['ports'] else None)}  "
        f"{port_losses_text}"
        f"{delta_text(port_loss_rate * 100, stat_rate(previous_stats, 'port_losses') * 100 if previous_stats else None, precision=1, suffix='pp', lower_is_better=True)}  "
        f"damage={average(stats, 'raid_damage_events_total'):.1f}/game"
        f"{delta_text(average(stats, 'raid_damage_events_total'), average(previous_stats, 'raid_damage_events_total') if previous_stats else None, precision=1, lower_is_better=True)}  "
        f"repairs={average(stats, 'raid_repairs_total'):.1f}/game"
        f"{delta_text(average(stats, 'raid_repairs_total'), average(previous_stats, 'raid_repairs_total') if previous_stats else None, precision=1)}  "
        f"sunk_damaged={average(stats, 'damaged_raiders_sunk_total'):.1f}/game"
        f"{delta_text(average(stats, 'damaged_raiders_sunk_total'), average(previous_stats, 'damaged_raiders_sunk_total') if previous_stats else None, precision=1, lower_is_better=True)}  "
        f"smugglers={average(stats, 'guard_captain_ship_captures_total'):.1f}/game"
        f"{delta_text(average(stats, 'guard_captain_ship_captures_total'), average(previous_stats, 'guard_captain_ship_captures_total') if previous_stats else None, precision=1)}"
    )
    print()
    print(
        f"{paint('orders:', 'blue', bold=True)} "
        f"trade={strategy.trade_weight:.2f}  "
        f"raid={strategy.raid_weight:.2f}  "
        f"guard={strategy.guard_weight:.2f}  "
        f"fire={strategy.fire_weight:.2f}"
    )
    print(
        f"{paint('buy:', 'blue', bold=True):<15}"
        f"convoy={strategy.convoy_bias:.2f}  "
        f"ship={strategy.ship_bias:.2f}  "
        f"idle={strategy.construction_idle_bias:.2f}  "
        f"repair={strategy.repair_bias:.2f}"
    )
    print(
        f"{paint('infra:', 'blue', bold=True):<15}"
        f"yard={strategy.shipyard_bias:.2f}  "
        f"fort={strategy.fort_bias:.2f}  "
        f"guild={strategy.trade_guild_bias:.2f}  "
        f"captain={strategy.guard_captain_bias:.2f}  "
        f"fire_plans={strategy.fire_plans_bias:.2f}"
    )
    print(
        f"{paint('econ:', 'blue', bold=True):<15}"
        f"fishing_dock={strategy.fishing_dock_bias:.2f}  "
        f"boat={strategy.fishing_boat_bias:.2f}  "
        f"dry_dock={strategy.dry_dock_bias:.2f}"
    )
    print(f"priority: {strategy.build_priority}")
    print()
    if finished:
        print(paint("controls:", "magenta", bold=True), "b benchmark  w write file  s save+exit  n new run")
    else:
        print(paint("controls:", "magenta", bold=True), "[] lr  -/+ mutation  g/G games  r restart  n new run  h help")
    print(paint("recent:", "blue", bold=True))
    for line in recent_lines:
        print(f"  {line}")
    if finished:
        print()
        print(paint(f"benchmark games/opponent: {benchmark_games}", "cyan", bold=True))
        if benchmark_rows is None:
            print("benchmark: not run yet")
        else:
            print(paint("benchmark:", "cyan", bold=True))
            for line in dashboard_benchmark_lines(benchmark_rows):
                print(line)
    print(flush=True)


def dashboard_benchmark_lines(rows, weakest_count=None):
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
            "win_turns_total",
            "loss_turns_total",
            "score_total",
            "opponent_score_total",
        ]:
            total[key] += row[key]

    total_row = dict(total)
    total_row["opponent"] = "TOTAL"
    lines = [
        "Opponent         Games  Wins  Losses  Draws  Win rate  "
        "Port wins  Port losses  Avg turns  Win turns  Loss turns  Avg assets  Opp avg",
        "---------------  -----  ----  ------  -----  --------  "
        "---------  -----------  ---------  ---------  ----------  ----------  -------",
    ]
    for row in rows:
        lines.append(dashboard_benchmark_row(row))
    lines.append(dashboard_benchmark_row(total_row, total=True))
    return lines


def dashboard_benchmark_row(row, total=False):
    games = row["games"]
    win_rate = row["wins"] / games if games else 0
    avg_turns = row["turns_total"] / games if games else 0
    avg_win_turns = row["win_turns_total"] / row["wins"] if row["wins"] else 0
    avg_loss_turns = row["loss_turns_total"] / row["losses"] if row["losses"] else 0
    avg_score = row["score_total"] / games if games else 0
    avg_opponent_score = row["opponent_score_total"] / games if games else 0
    port_loss_rate = row["port_losses"] / games if games else 0
    port_win_rate = row["port_wins"] / games if games else 0

    opponent = f"{row['opponent']:<15}"
    if total:
        opponent = paint(opponent, "white", bold=True)
    win_rate_text = paint(
        f"{win_rate * 100:>7.1f}%",
        rate_color(win_rate),
        bold=win_rate < 0.5 or win_rate >= 0.85,
    )
    port_wins = paint(
        f"{row['port_wins']:>9}",
        "green" if port_win_rate >= 0.2 else None,
        bold=port_win_rate >= 0.5,
    )
    port_losses = paint(
        f"{row['port_losses']:>11}",
        pressure_color(port_loss_rate, 0.05, 0.2),
        bold=port_loss_rate >= 0.2,
    )
    avg_score_text = paint(
        f"{avg_score:>10.1f}",
        "green" if avg_score > avg_opponent_score * 1.5 and games else None,
    )
    avg_opponent_text = paint(
        f"{avg_opponent_score:>7.1f}",
        "red" if avg_opponent_score > avg_score * 1.5 and games else None,
    )

    return (
        f"{opponent}  {games:>5}  {row['wins']:>4}  "
        f"{row['losses']:>6}  {row['draws']:>5}  "
        f"{win_rate_text}  {port_wins}  "
        f"{port_losses}  {avg_turns:>9.1f}  "
        f"{avg_win_turns:>9.1f}  {avg_loss_turns:>10.1f}  "
        f"{avg_score_text}  {avg_opponent_text}"
    )
