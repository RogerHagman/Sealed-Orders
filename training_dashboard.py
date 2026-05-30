# training_dashboard.py

### Imports ###
import os
import re
import select
import shutil
import sys
import termios
import time
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
    """
    Apply ANSI color codes to the given text if color is specified and output is a terminal. 
    Supported colors include: red, green, yellow, blue, magenta, cyan, white, and dim. 
    If bold is True, the text will be rendered in bold. 
    If COLOR_ENABLED is False, the text will be returned without modification.
    Args:        text (str): The text to be colored.
        color (str, optional): The name of the color to apply. Defaults to None.
    Returns:
        str: The text with ANSI color codes applied if applicable.
    """
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


ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def visible_len(text):
    """
    Calculate the visible length of a string by removing ANSI escape codes.
    Args:
        text (str): The input string that may contain ANSI escape codes.
    Returns:
        int: The visible length of the string.
    """
    return len(ANSI_RE.sub("", str(text)))


def fit_panel_line(text, width):
    text = str(text)
    content_width = max(1, width - 4)
    if visible_len(text) > content_width:
        plain = ANSI_RE.sub("", text)
        text = plain[: max(0, content_width - 3)] + "..."
    return f"| {text}{' ' * max(0, content_width - visible_len(text))} |"


def panel(title, lines, width):
    width = max(24, width)
    title_text = f" {title} "
    top_fill = max(0, width - visible_len(title_text) - 2)
    top = "+" + title_text + "-" * top_fill + "+"
    body = [fit_panel_line(line, width) for line in lines]
    bottom = "+" + "-" * (width - 2) + "+"
    return [top, *body, bottom]


def combine_panels(left, right, gap=2):
    height = max(len(left), len(right))
    left_width = max(visible_len(line) for line in left) if left else 0
    right_width = max(visible_len(line) for line in right) if right else 0
    rows = []
    for index in range(height):
        left_line = left[index] if index < len(left) else " " * left_width
        right_line = right[index] if index < len(right) else " " * right_width
        rows.append(
            f"{left_line}{' ' * max(0, left_width - visible_len(left_line) + gap)}{right_line}"
        )
    return rows


def pad_panel_height(lines, width, target_height):
    lines = list(lines)
    while len(lines) < target_height and len(lines) >= 2:
        lines.insert(-1, fit_panel_line("", width))
    return lines


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
    use_alternate_screen = sys.stdout.isatty()
    if use_alternate_screen:
        sys.stdout.write("\033[?1049h\033[?25l\033[H\033[J")
        sys.stdout.flush()
    return {
        "termios": settings,
        "alternate_screen": use_alternate_screen,
    }


def restore_dashboard_terminal(settings):
    if settings is None:
        return
    if isinstance(settings, dict):
        if settings.get("alternate_screen"):
            sys.stdout.write("\033[?25h\033[?1049l")
            sys.stdout.flush()
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings["termios"])
    else:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)


def handle_dashboard_input(
    current,
    current_stats,
    learning_rate,
    mutation_scale,
    games_per_bot,
    generations,
    current_generation,
    dashboard_window,
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
            generations,
            dashboard_window,
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
    elif key == "e":
        generations += 100
        message = f"run extended to {generations} generations"
    elif key == "E":
        generations += 500
        message = f"run extended to {generations} generations"
    elif key == "d":
        generations = max(current_generation, generations - 100)
        message = f"run shortened to {generations} generations"
    elif key == "D":
        generations = max(current_generation, generations - 500)
        message = f"run shortened to {generations} generations"
    elif key == "v":
        dashboard_window = max(25, dashboard_window - 25)
        message = f"dashboard window lowered to {dashboard_window}"
    elif key == "V":
        dashboard_window += 25 if dashboard_window < 250 else 100
        message = f"dashboard window raised to {dashboard_window}"
    elif key == "r":
        current, current_stats = restart_callback(games_per_bot)
        message = "restarted from a fresh random strategy"
        return (
            current,
            current_stats,
            learning_rate,
            mutation_scale,
            games_per_bot,
            generations,
            dashboard_window,
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
            generations,
            dashboard_window,
            "starting a new run",
            "new",
        )
    elif key == "h":
        message = "controls: [] lr, -/+ mutation, g/G games, e/E extend, d/D shorten, v/V window, r restart, n new run"
    else:
        message = f"ignored key {key!r}; press h for controls"

    return (
        current,
        current_stats,
        learning_rate,
        mutation_scale,
        games_per_bot,
        generations,
        dashboard_window,
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
    run_started_at,
    seed_branch_chance,
    workers,
    dashboard_window,
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
            run_started_at=run_started_at,
            seed_branch_chance=seed_branch_chance,
            workers=workers,
            dashboard_window=dashboard_window,
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
                run_started_at=run_started_at,
                seed_branch_chance=seed_branch_chance,
                workers=workers,
                dashboard_window=dashboard_window,
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
            if (
                isinstance(terminal_settings, dict)
                and terminal_settings.get("alternate_screen")
            ):
                sys.stdout.write("\033[?1049h\033[?25l\033[H\033[J")
                sys.stdout.flush()


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
    return stats.get(key, 0) / stats["games"]


def format_duration(seconds):
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:d}h{minutes:02d}m"
    if minutes:
        return f"{minutes:d}m{seconds:02d}s"
    return f"{seconds:d}s"


def dashboard_timing(generation, generations, run_started_at, finished=False):
    if run_started_at is None:
        return "elapsed=--  eta=--"
    elapsed = time.monotonic() - run_started_at
    if finished or generation >= generations:
        eta_text = "done"
    elif generation <= 0:
        eta_text = "--"
    else:
        seconds_per_generation = elapsed / generation
        eta_text = format_duration(seconds_per_generation * (generations - generation))
    return f"elapsed={format_duration(elapsed)}  eta={eta_text}"


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


def plateau_label(plateau_generations, dashboard_window=100):
    fresh_threshold = max(1, dashboard_window // 100)
    settling_threshold = max(1, dashboard_window // 4)
    stuck_threshold = max(settling_threshold + 1, dashboard_window)
    if plateau_generations <= fresh_threshold:
        return "fresh"
    if plateau_generations < settling_threshold:
        return "settling"
    if plateau_generations < stuck_threshold:
        return "stalled"
    return "stuck"


def plateau_color(plateau_generations, dashboard_window=100):
    fresh_threshold = max(1, dashboard_window // 100)
    settling_threshold = max(1, dashboard_window // 4)
    stuck_threshold = max(settling_threshold + 1, dashboard_window)
    if plateau_generations <= fresh_threshold:
        return "green"
    if plateau_generations < settling_threshold:
        return "cyan"
    if plateau_generations < stuck_threshold:
        return "yellow"
    return "red"


def training_health(
    stats,
    previous_stats,
    plateau_generations,
    dashboard_window=100,
    window_stats=None,
):
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

    dashboard_window = max(1, int(dashboard_window))
    progress_ratio = plateau_generations / dashboard_window
    recent_yield = (window_stats or {}).get("yield_rate", 0)
    recent_pressure = (window_stats or {}).get("candidate_pressure", 0)

    if progress_ratio >= 1.0 and recent_yield <= 0:
        if score >= 3:
            return "banked", "cyan"
        if score >= 1:
            return "coasting", "yellow"
        if recent_pressure < 0.03:
            return "frozen", "yellow"
        if recent_pressure < 0.10:
            return "stale", "yellow"
        return "blocked", "red"

    if progress_ratio >= 0.50 and recent_yield <= 0:
        if score >= 3:
            return "banked", "cyan"
        if score >= 1:
            return "coasting", "yellow"

    if progress_ratio >= 0.25 and recent_yield <= 0:
        if score >= 3:
            return "proven", "cyan"
        if score >= 1:
            return "flat", "yellow"

    if score >= 3:
        label, color = "surging", "green"
    elif score >= 1:
        label, color = "improving", "green"
    elif score <= -2:
        label, color = "regressing", "red"
    elif plateau_generations >= dashboard_window:
        label, color = "stale", "red"
    elif plateau_generations >= max(1, dashboard_window // 4):
        label, color = "flat", "yellow"
    else:
        label, color = "mixed", "yellow"

    return label, color


def training_window_stats(events):
    total = len(events)
    counts = {"learned": 0, "fragile": 0, "kept": 0}
    candidate_improved = 0
    seed_branches = 0
    for event in events:
        status = event.get("status")
        if status in counts:
            counts[status] += 1
        if event.get("candidate_improved"):
            candidate_improved += 1
        if event.get("seed_branch"):
            seed_branches += 1

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
        "seed_branches": seed_branches,
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
    run_started_at=None,
    seed_branch_chance=0.0,
    workers=1,
    dashboard_window=100,
):
    sys.stdout.write("\033[H\033[J")
    sys.stdout.flush()
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
    dashboard_window = max(1, int(dashboard_window))
    window = training_window_stats(training_events or [])
    plateau_status = plateau_label(plateau_generations, dashboard_window)
    health_label, health_color = training_health(
        stats,
        previous_stats,
        plateau_generations,
        dashboard_window,
        window,
    )
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
    terminal = shutil.get_terminal_size((120, 36))
    width = max(80, terminal.columns)
    content_width = min(width, 150)
    left_width = max(38, (content_width - 2) // 2)
    right_width = content_width - left_width - 2

    status_lines = [
        (
            f"status={paint(status, status_color, bold=bool(status_color))}  "
            f"plateau={paint(f'{plateau_status}({plateau_generations})', plateau_color(plateau_generations, dashboard_window), bold=plateau_generations >= dashboard_window)}  "
            f"health={paint(health_label, health_color, bold=True)}  "
            f"message={paint(dashboard_message, 'white')}"
        ),
        (
            f"fitness={stats['fitness']:.1f}"
            f"{delta_text(stats['fitness'], previous_stats['fitness'] if previous_stats else None, precision=1)}  "
            f"wins={stats['wins']}/{stats['games']} "
            f"{paint(f'{win_rate * 100:.1f}%', rate_color(win_rate), bold=True)}"
            f"{delta_text(win_rate * 100, previous_win_rate * 100 if previous_win_rate is not None else None, precision=1, suffix='%')}  "
            f"min={paint(f'{min_matchup * 100:.1f}%', rate_color(min_matchup), bold=True)}"
            f"{delta_text(min_matchup * 100, previous_min_matchup * 100 if previous_min_matchup is not None else None, precision=1, suffix='%')}"
        ),
        (
            f"assets={avg_assets:.1f}"
            f"{delta_text(avg_assets, previous_assets, precision=1)}  "
            f"opp={average(stats, 'opponent_score_total'):.1f}"
            f"{delta_text(average(stats, 'opponent_score_total'), previous_opp_assets, precision=1, lower_is_better=True)}  "
            f"ports={paint(str(stats['ports']), 'green' if stats['ports'] else None)}  "
            f"{port_losses_text}"
            f"{delta_text(port_loss_rate * 100, stat_rate(previous_stats, 'port_losses') * 100 if previous_stats else None, precision=1, suffix='pp', lower_is_better=True)}"
        ),
        (
            f"lr={learning_rate:.2f}  mutation={mutation_scale:.2f}  "
            f"games/opponent={games_per_bot}  "
            f"workers={workers}  "
            f"seed-branch={seed_branch_chance * 100:.0f}%  "
            f"{dashboard_timing(generation, generations, run_started_at, finished)}"
        ),
        (
            f"win {gauge(win_rate, 0, 1)}  "
            f"min {gauge(min_matchup, 0, 1)}  "
            f"plateau {inverse_gauge(min(plateau_generations, dashboard_window), 0, dashboard_window)}"
        ),
    ]

    training_lines = [
        f"window n={window['total']}/{dashboard_window}  mode={paint(window['mode'], window['color'], bold=True)}",
        f"yield={yield_text}  candidate={candidate_pressure_text}",
        f"seed branches={window['seed_branches']}/{window['total']}",
        f"fragility={fragility_text}",
        f"learned/fragile/kept={window['learned']}/{window['fragile']}/{window['kept']}",
        (
            f"damage={average(stats, 'raid_damage_events_total'):.1f}/game"
            f"{delta_text(average(stats, 'raid_damage_events_total'), average(previous_stats, 'raid_damage_events_total') if previous_stats else None, precision=1, lower_is_better=True)}"
        ),
        (
            f"skirmish={average(stats, 'raid_skirmish_damage_total'):.1f} dmg/"
            f"{average(stats, 'raid_skirmish_sunk_total'):.1f} sunk"
        ),
        (
            f"repairs={average(stats, 'raid_repairs_total'):.1f}/game"
            f"{delta_text(average(stats, 'raid_repairs_total'), average(previous_stats, 'raid_repairs_total') if previous_stats else None, precision=1)}"
        ),
        (
            f"sunk damaged={average(stats, 'damaged_raiders_sunk_total'):.1f}/game"
            f"{delta_text(average(stats, 'damaged_raiders_sunk_total'), average(previous_stats, 'damaged_raiders_sunk_total') if previous_stats else None, precision=1, lower_is_better=True)}"
        ),
        (
            f"smugglers={average(stats, 'guard_captain_ship_captures_total'):.1f}/game"
            f"{delta_text(average(stats, 'guard_captain_ship_captures_total'), average(previous_stats, 'guard_captain_ship_captures_total') if previous_stats else None, precision=1)}"
        ),
        (
            f"admty S/C={average(stats, 'admiralty_started'):.1f}/"
            f"{average(stats, 'admiralty_completed'):.1f}  "
            f"ever/burn={average(stats, 'admiralty_ever_completed'):.1f}/"
            f"{average(stats, 'admiralty_burned'):.1f}  "
            f"adm={average(stats, 'admirals_total'):.1f}/"
            f"{average(stats, 'admiral_slots_total'):.1f} slots  "
            f"open={average(stats, 'admiral_open_slots_total'):.1f}"
            f"{delta_text(average(stats, 'admirals_total'), average(previous_stats, 'admirals_total') if previous_stats else None, precision=1)}"
        ),
        (
            f"dockhouse={average(stats, 'dockhouse_completed'):.1f}/game  "
            f"hands={average(stats, 'dockhands_total'):.1f}/game  "
            f"duty C/R/B={average(stats, 'dockhand_construction_duty'):.1f}/"
            f"{average(stats, 'dockhand_repair_duty'):.1f}/"
            f"{average(stats, 'dockhand_boatwright_duty'):.1f}"
        ),
        (
            f"supply={average(stats, 'supply_total'):.1f}/game  "
            f"crisis={average(stats, 'supply_crises'):.1f}/game  "
            f"desert={average(stats, 'supply_desertions_total'):.1f}/game  "
            f"burns={average(stats, 'supply_unrest_burns'):.1f}/game"
        ),
    ]
    strategy_lines = [
        (
            f"orders  trade={strategy.trade_weight:.2f}  raid={strategy.raid_weight:.2f}  "
            f"guard={strategy.guard_weight:.2f}  fire={strategy.fire_weight:.2f}"
        ),
        (
            f"buy     convoy={strategy.convoy_bias:.2f}  ship={strategy.ship_bias:.2f}  "
            f"idle={strategy.construction_idle_bias:.2f}  repair={strategy.repair_bias:.2f}"
        ),
        (
            f"infra   yard={strategy.shipyard_bias:.2f}  fort={strategy.fort_bias:.2f}  "
            f"guild={strategy.trade_guild_bias:.2f}  admin={strategy.administrator_bias:.2f}"
        ),
        (
            f"        captain={strategy.guard_captain_bias:.2f}  "
            f"fire_plans={strategy.fire_plans_bias:.2f}"
        ),
        (
            f"econ    fishing_dock={strategy.fishing_dock_bias:.2f}  "
            f"boat={strategy.fishing_boat_bias:.2f}  dockhouse={strategy.dockhouse_bias:.2f}"
        ),
        (
            f"hands   hire={strategy.dockhand_bias:.2f}  "
            f"repair={strategy.dockhand_repair_bias:.2f}  "
            f"boatwright={strategy.dockhand_boatwright_bias:.2f}  "
            f"dry_dock={strategy.dry_dock_bias:.2f}"
        ),
        (
            f"cmd     admiralty={strategy.admiralty_bias:.2f}  "
            f"admiral={strategy.admiral_bias:.2f}  overtime={strategy.overtime_bias:.2f}"
        ),
        f"priority {strategy.build_priority}",
    ]
    control_text = (
        "b benchmark  w write file  s save+exit  n new run"
        if finished
        else "[] lr  -/+ mutation  g/G games  e/E extend  d/D shorten  v/V window  r restart  n new run  h help"
    )

    report_lines = []
    if finished:
        report_lines.append(f"benchmark games/opponent: {benchmark_games}")
        if benchmark_rows is None:
            report_lines.append("benchmark: not run yet")
        else:
            report_lines.extend(dashboard_benchmark_lines(benchmark_rows))
    else:
        report_lines.extend(recent_lines[-12:])
    if not report_lines:
        report_lines = ["No events yet."]

    fixed_height = 1 + len(status_lines) + 2 + max(len(training_lines), len(strategy_lines)) + 4
    report_budget = max(6, terminal.lines - fixed_height)
    if finished and benchmark_rows is not None:
        report_lines = pin_benchmark_header(report_lines, report_budget)
    else:
        report_lines = report_lines[-report_budget:]

    for line in panel("Status", status_lines, content_width):
        print(line)
    if content_width >= 96:
        left = panel("Training Health", training_lines, left_width)
        right = panel("Strategy", strategy_lines, right_width)
        target_height = max(len(left), len(right))
        left = pad_panel_height(left, left_width, target_height)
        right = pad_panel_height(right, right_width, target_height)
        for line in combine_panels(left, right):
            print(line)
    else:
        for line in panel("Training Health", training_lines, content_width):
            print(line)
        for line in panel("Strategy", strategy_lines, content_width):
            print(line)
    for line in panel("Controls", [control_text], content_width):
        print(line)
    report_title = "Report" if not finished or benchmark_rows is None else "Benchmark Report"
    for line in panel(report_title, report_lines, content_width):
        print(line)
    print(flush=True)


def pin_benchmark_header(lines, budget):
    if len(lines) <= budget:
        return lines
    if len(lines) < 3 or budget <= 3:
        return lines[-budget:]

    prefix = []
    body_start = 0
    if lines[0].startswith("benchmark games/opponent:"):
        prefix.append(lines[0])
        body_start = 1

    header = lines[body_start : body_start + 2]
    body = lines[body_start + 2 :]
    body_budget = max(0, budget - len(prefix) - len(header))
    if body_budget == 0:
        return [*prefix, *header]
    return [*prefix, *header, *body[-body_budget:]]


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
            "admiralty_completed",
            "admiralty_ever_completed",
            "admiralty_burned",
            "admirals_total",
            "admiral_slots_total",
            "admiral_open_slots_total",
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
            total[key] += row.get(key, 0)

    total_row = dict(total)
    total_row["opponent"] = "TOTAL"
    lines = [
        "Opponent          Games  W-L-D          Win    Port W/L   Turns  Win/LossT  Assets/Opp  Supply/C",
        "---------------  -----  -------------  ------  ---------  -----  ---------  ----------  --------",
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
    avg_supply = row.get("supply_total", 0) / games if games else 0
    avg_crises = row.get("supply_crises", 0) / games if games else 0

    opponent = f"{row['opponent']:<15}"
    if total:
        opponent = paint(opponent, "white", bold=True)
    win_rate_text = paint(
        f"{win_rate * 100:>7.1f}%",
        rate_color(win_rate),
        bold=win_rate < 0.5 or win_rate >= 0.85,
    )
    port_record = paint(
        f"{row['port_wins']:>4}/{row['port_losses']:<4}",
        pressure_color(port_loss_rate, 0.05, 0.2),
        bold=port_loss_rate >= 0.2 or port_win_rate >= 0.5,
    )
    if port_win_rate >= 0.2 and port_loss_rate < 0.05:
        port_record = paint(
            f"{row['port_wins']:>4}/{row['port_losses']:<4}",
            "green",
            bold=port_win_rate >= 0.5,
        )
    win_loss_draw = f"{row['wins']}/{row['losses']}/{row['draws']}"
    win_loss_draw = f"{win_loss_draw:>13}"
    avg_turn_pair = f"{avg_win_turns:>4.1f}/{avg_loss_turns:<4.1f}"
    asset_pair = f"{avg_score:>5.1f}/{avg_opponent_score:<4.1f}"
    asset_pair = paint(
        asset_pair,
        "green" if avg_score > avg_opponent_score * 1.5 and games else (
            "red" if avg_opponent_score > avg_score * 1.5 and games else None
        ),
    )
    supply_pair = paint(
        f"{avg_supply:>4.1f}/{avg_crises:<3.1f}",
        "green" if avg_supply >= 2 and avg_crises < 1 else (
            "red" if avg_supply < -1 or avg_crises >= 4 else None
        ),
        bold=avg_supply >= 4 or avg_supply <= -3,
    )
    row_text = (
        f"{opponent}  {games:>5}  {win_loss_draw}  "
        f"{win_rate_text}  {port_record}  {avg_turns:>5.1f}  "
        f"{avg_turn_pair}  {asset_pair}  {supply_pair}"
    )
    return row_text
