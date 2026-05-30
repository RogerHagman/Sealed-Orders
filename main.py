# main.py
"""Sealed Orders: a 2-player strategy game of naval warfare and intrigue."""

### Imports ###
import argparse
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path
from game_engine import Game
from game_state import Allocation, Rules, UI


if __name__ == "__main__":
    """Expose main module attributes for interactive use and testing."""
    sys.modules["main"] = sys.modules[__name__]


def prompt_player_names():
    """
    Prompt the user to enter player names, with defaults for convenience.
    Returns:
        A list of two player names.
    """
    names = []
    defaults = ["England", "Spain"]

    UI.section("PLAYER SETUP", "magenta")
    print("Enter player names, or press Enter to use the default names.")
    for index, default in enumerate(defaults, start=1):
        name = input(f"Player {index} name [{default}]: ").strip()
        names.append(name or default)

    return names


def prompt_human_name():
    """Prompt the user to enter their nation name for a human-vs-AI game."""
    name = input("Your nation name [England]: ").strip()
    return name or "England"


def prompt_ai_strategy(strategy_names):
    """
    Prompt the user to choose an AI strategy from the bot roster.
    
    Args:
        strategy_names: a list of available strategy names to choose from
        Returns:
            The chosen AI strategy name.
    """
    default_strategy = "Privateer"
    UI.section("CHOOSE AI OPPONENT", "magenta")
    for index, strategy_name in enumerate(strategy_names, start=1):
        default_marker = " [default]" if strategy_name == default_strategy else ""
        print(
            f"{UI.paint(str(index) + '.', 'green', bold=True)} "
            f"{strategy_name}{UI.muted(default_marker)}"
        )

    while True:
        choice = input(f"AI opponent [{default_strategy}]: ").strip()
        if not choice:
            return default_strategy

        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(strategy_names):
                return strategy_names[index - 1]

        for strategy_name in strategy_names:
            if strategy_name.lower() == choice.lower():
                return strategy_name

        print(UI.warning("Please choose a listed number or strategy name."))


def rules_value_text(name, value):
    """Format a Rules constant for the Seamanship's Manual."""
    if name.endswith("_PERCENT"):
        percent = int(value * 100) if isinstance(value, float) else value
        return f"{percent}%"
    if isinstance(value, float):
        return f"{value:g}"
    if "ASSET_VALUE" in name:
        return UI.amount(value, "assets", "yellow")
    if name in {
        "PAYROLL_VALUE_PER_SHIP",
        "TRADE_INCOME",
        "SMUGGLE_INCOME",
        "FISHING_BOAT_INCOME",
        "TREASURE_BASE_VALUE",
    }:
        return UI.amount(value, "gold")
    if "WARCHEST_MARKUP" in name:
        return UI.amount(value, "gold")
    if "GOLD" in name or name.endswith("_COST") or "_COST_" in name or name == "SHIPYARD_DISCOUNT":
        return UI.amount(value, "gold")
    if "LABOR" in name:
        return UI.amount(value, "labor")
    if "SHIP" in name or "SHIPS" in name:
        return UI.amount(value, "ships")
    if "SUPPLY" in name and isinstance(value, int):
        return UI.amount(value, "supply")
    return str(value)


def rules_label(name):
    return name.lower().replace("_", " ").capitalize()


def seamanship_manual_sections():
    """Build the manual from the live Rules constants."""
    return [
        (
            "Orders",
            [
                f"{UI.order_label('Trade')} earns {UI.amount(Rules.TRADE_INCOME, 'gold')} per ship and grows treasure by {int(Rules.TREASURE_TRADE_PERCENT * 100)}% of trade income.",
                f"{UI.order_label('Raid')} intercepts trade, threatens convoys, and adds raid pressure toward ship damage every {Rules.RAID_ACTIONS_PER_DAMAGE} raid actions.",
                f"{UI.order_label('Guard')} blocks raids, catches smugglers, and becomes stronger with guard captains.",
                f"{UI.order_label('Fire')} can burn guards and infrastructure once fire ship plans are purchased.",
                f"{UI.symbol_label('port', 'Port workers', 'yellow')} are unassigned ships; they apply labor to active projects in priority order.",
            ],
        ),
        (
            "Economy And Convoys",
            [
                f"Ships cost {UI.amount(Rules.SHIP_COST, 'gold')} base, or {UI.amount(Rules.SHIP_COST - Rules.SHIPYARD_DISCOUNT, 'gold')} with a completed shipyard.",
                f"Smuggling earns {UI.smuggle_gold(Rules.SMUGGLE_INCOME)} per ship, or full trade income when enemy supply is below 0.",
                f"Treasure starts at {UI.amount(Rules.TREASURE_BASE_VALUE, 'gold')} and takes {Rules.TREASURE_TRAVEL_TURNS} turns to arrive after launch.",
                f"Payroll launches during {Rules.MONTHS[Rules.PAYROLL_START_TURN - 1]}-{Rules.MONTHS[Rules.PAYROLL_FINAL_TURN - 1]}, travels {Rules.PAYROLL_TRAVEL_TURNS} turn, and pays {UI.payroll_gold(Rules.PAYROLL_VALUE_PER_SHIP)} per ship.",
                f"Captured payroll causes mutiny losses of {int(Rules.PAYROLL_MUTINY_PERCENT * 100)}% of ships, rounded up.",
            ],
        ),
        (
            "Harbor Works",
            [
                f"{UI.symbol_label('shipyard', 'Shipyard', 'green')}: {UI.cost(Rules.SHIPYARD_COST, Rules.SHIPYARD_LABOR_REQUIRED)}, value {UI.amount(Rules.SHIPYARD_ASSET_VALUE, 'assets', 'yellow')}, discounts ship repairs.",
                f"{UI.symbol_label('fort', 'Fort', 'yellow')}: {UI.cost(Rules.FORT_COST, Rules.FORT_LABOR_REQUIRED)}, value {UI.amount(Rules.FORT_ASSET_VALUE, 'assets', 'yellow')}, blocks {UI.amount(Rules.FORT_RAID_BLOCKS_PER_TURN, 'ships')} raid and {Rules.FORT_FIRE_BLOCKS_PER_TURN} fire per turn.",
                f"{UI.symbol_label('guild', 'Trade guild', 'green')}: {UI.cost(Rules.TRADE_GUILD_COST, Rules.TRADE_GUILD_LABOR_REQUIRED)}, value {UI.amount(Rules.TRADE_GUILD_ASSET_VALUE, 'assets', 'yellow')}, boosts trade and discounts payroll.",
                f"{UI.symbol_label('fishing', 'Fishing docks', 'blue')}: {UI.cost(Rules.FISHING_DOCK_COST, Rules.FISHING_DOCK_LABOR_REQUIRED)}, boats cost {UI.amount(Rules.FISHING_BOAT_COST, 'gold')} and earn {UI.amount(Rules.FISHING_BOAT_INCOME, 'gold')} each.",
                f"{UI.symbol_label('dockhouse', 'Dockhouse', 'yellow')}: {UI.cost(Rules.DOCKHOUSE_COST, Rules.DOCKHOUSE_LABOR_REQUIRED)}, value {UI.amount(Rules.DOCKHOUSE_ASSET_VALUE, 'assets', 'yellow')}, unlocks dock hands.",
                f"{UI.symbol_label('dry dock', 'Dry dock', 'cyan')}: {UI.cost(Rules.DRY_DOCK_COST, Rules.DRY_DOCK_LABOR_REQUIRED)}, value {UI.amount(Rules.DRY_DOCK_ASSET_VALUE, 'assets', 'yellow')}, makes raid repairs free.",
                f"{UI.symbol_label('admiralty', 'Admiralty', 'white')}: {UI.cost(Rules.ADMIRALTY_COST, Rules.ADMIRALTY_LABOR_REQUIRED)}, value {UI.amount(Rules.ADMIRALTY_ASSET_VALUE, 'assets', 'yellow')}, unlocks admirals and overtime.",
            ],
        ),
        (
            "Supply And Defense",
            [
                f"Supply ranges from {Rules.SUPPLY_MIN} to {Rules.SUPPLY_MAX}; without a trade guild the effective ceiling is 4.",
                f"Supply need is 1 per {UI.amount(Rules.SUPPLY_SHIPS_PER_NEED, 'ships')} plus {Rules.DOCKHAND_SUPPLY_NEED} per dock hand.",
                f"Emergency war chest auto-pays below 0 supply at {UI.amount(Rules.SUPPLY_WARCHEST_MARKUP, 'gold')} per missing supply, or {UI.amount(Rules.SUPPLY_ADMINISTRATOR_WARCHEST_MARKUP, 'gold')} with guild administrator.",
                f"Light supply damage hits {int(Rules.SUPPLY_LIGHT_DAMAGE_PERCENT * 100)}% of ships; desertion can hit {int(Rules.SUPPLY_DESERTION_PERCENT * 100)}% or {int(Rules.SUPPLY_HEAVY_DESERTION_PERCENT * 100)}%.",
                f"Home port destruction needs {UI.amount(Rules.PORT_ATTACK_SHIPS_REQUIRED, 'ships')} base raid pressure plus fort/captain defenses.",
                f"Guard captains cost {UI.amount(Rules.GUARD_CAPTAIN_COST, 'gold')}, max {Rules.GUARD_CAPTAIN_MAX}, and add {Rules.GUARD_CAPTAIN_PORT_DEFENSE} port defense each.",
            ],
        ),
        (
            "Complete Statistics",
            [
                f"{rules_label(name)}: {rules_value_text(name, value)}"
                for name, value in sorted(vars(Rules).items())
                if name.isupper() and name != "MONTHS"
            ],
        ),
    ]


def show_seamanship_manual():
    """Render a paged encyclopedia of rules and advanced statistics."""
    sections = seamanship_manual_sections()
    terminal_width = shutil.get_terminal_size((120, 36)).columns
    width = min(max(80, terminal_width), 120)

    for index, (title, lines) in enumerate(sections, start=1):
        UI.clear_screen()
        UI.section("SEAMANSHIP'S MANUAL", "cyan")
        print(UI.muted(f"Page {index}/{len(sections)}"))
        print()
        for line in UI.panel(title, lines, width=width, wrap=True):
            print(line)
        print()
        prompt = "Press Enter for next page..." if index < len(sections) else "Press Enter to return to main menu..."
        input(prompt)


def allocation_signature(allocation):
    if not allocation:
        return "unknown"
    return (
        f"{UI.symbol('trade')}{allocation.get('trade', 0)} "
        f"{UI.symbol('raid')}{allocation.get('raid', 0)} "
        f"{UI.symbol('guard')}{allocation.get('guard', 0)} "
        f"{UI.symbol('fire')}{allocation.get('fire', 0)}"
    )


def human_opening_signature(record):
    turns = record.get("turns_detail") or []
    if not turns:
        return "unknown"
    orders = turns[0].get("orders") or {}
    human_name = record.get("players", {}).get("human", {}).get("name")
    human_snapshot = orders.get(human_name) if human_name else None
    if human_snapshot is None and orders:
        human_snapshot = next(iter(orders.values()))
    return allocation_signature((human_snapshot or {}).get("allocation"))


def empty_human_record_row():
    return {
        "games": 0,
        "human_wins": 0,
        "ai_wins": 0,
        "draws": 0,
        "turns_total": 0,
        "human_score_total": 0,
        "ai_score_total": 0,
        "port_wins": 0,
        "asset_wins": 0,
    }


def read_human_records(log_path):
    log_path = Path(log_path)
    if not log_path.exists():
        return [], f"No human-vs-AI log found at {log_path}."

    records = []
    with log_path.open(encoding="utf-8") as log_file:
        for line_number, line in enumerate(log_file, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                return records, f"Stopped reading malformed record on line {line_number}."
    return records, None


def summarize_human_records(records):
    overall = empty_human_record_row()
    by_bot = defaultdict(empty_human_record_row)
    openers = defaultdict(empty_human_record_row)
    opener_counts = Counter()

    for record in records:
        bot = record.get("ai_strategy", "Unknown")
        opener = human_opening_signature(record)
        opener_counts[opener] += 1

        for row in (overall, by_bot[bot], openers[opener]):
            row["games"] += 1
            row["turns_total"] += record.get("turns", 0)
            row["human_score_total"] += record.get("players", {}).get("human", {}).get("asset_score", 0)
            row["ai_score_total"] += record.get("players", {}).get("ai", {}).get("asset_score", 0)
            if record.get("winner") == "human":
                row["human_wins"] += 1
                if record.get("win_type") == "port":
                    row["port_wins"] += 1
                elif record.get("win_type") == "assets":
                    row["asset_wins"] += 1
            elif record.get("winner") == "ai":
                row["ai_wins"] += 1
            else:
                row["draws"] += 1

    return overall, by_bot, openers, opener_counts


def human_record_line(name, row):
    games = row["games"]
    win_rate = row["human_wins"] / games if games else 0
    avg_turns = row["turns_total"] / games if games else 0
    avg_human = row["human_score_total"] / games if games else 0
    avg_ai = row["ai_score_total"] / games if games else 0
    return (
        f"{name}: {games} games, {row['human_wins']}-{row['ai_wins']}-{row['draws']}, "
        f"{win_rate * 100:.1f}% win, avg {avg_turns:.1f} turns, "
        f"assets {avg_human:.1f}/{avg_ai:.1f}"
    )


def show_human_records(log_path):
    records, warning = read_human_records(log_path)
    if not records:
        UI.clear_screen()
        UI.section("HUMAN RECORDS", "cyan")
        print(UI.warning(warning or "No human records yet."))
        print()
        print(f"Play with {UI.paint('--play-ai', 'green', bold=True)} to create records.")
        input("Press Enter to return to main menu...")
        return

    overall, by_bot, openers, opener_counts = summarize_human_records(records)
    terminal_width = shutil.get_terminal_size((120, 36)).columns
    width = min(max(80, terminal_width), 120)
    pages = [
        (
            "Overall",
            [
                human_record_line("Human", overall),
                f"Port wins: {overall['port_wins']}  Asset wins: {overall['asset_wins']}",
                f"Log: {log_path}",
                warning or "",
            ],
        ),
        (
            "Versus Bots",
            [
                human_record_line(bot, row)
                for bot, row in sorted(
                    by_bot.items(),
                    key=lambda item: (-item[1]["games"], item[0].lower()),
                )
            ],
        ),
        (
            "Openers Used",
            [
                f"{opener}: {opener_counts[opener]} used, "
                f"{(openers[opener]['human_wins'] / openers[opener]['games'] * 100 if openers[opener]['games'] else 0):.1f}% win"
                for opener, _count in opener_counts.most_common(20)
            ],
        ),
    ]

    for index, (title, lines) in enumerate(pages, start=1):
        UI.clear_screen()
        UI.section("HUMAN RECORDS", "cyan")
        print(UI.muted(f"Page {index}/{len(pages)}"))
        print()
        clean_lines = [line for line in lines if line]
        for line in UI.panel(title, clean_lines or ["No records."], width=width, wrap=True):
            print(line)
        print()
        prompt = "Press Enter for next page..." if index < len(pages) else "Press Enter to return to main menu..."
        input(prompt)


BOT_FLAVOR = {
    "Merchant": ("green", "A counting-house captain: slow pressure, heavy trade, and a clean ledger."),
    "Privateer": ("orange", "Fast knives in fog. It raids early, buys ships, and asks questions after the prize is gone."),
    "Builder": ("yellow", "Patient stone and timber. It wants a harbor that wins by refusing to collapse."),
    "Admiral": ("blue", "Balanced command doctrine with enough steel to pivot when the sea changes."),
    "Opportunist": ("magenta", "Reads the room, pockets loose coin, and turns any undefended lane into trouble."),
    "Human Shadow": ("white", "A mirror with a memory: trained on human-winning habits and happy to imitate the unpleasant parts."),
    "Tide Reader": ("cyan", "Adaptive and watchful, shifting with early evidence instead of marrying one plan."),
    "Nash Admiral": ("blue", "Bookish, defensive, and mathematically smug; it prefers not to bleed for free."),
    "Nash Fireline": ("red", "A learned fire-and-raid doctrine that treats calm seas as a temporary clerical error."),
    "Crown Ledger": ("yellow", "Imperial accounting with cannons attached: trade, captains, and command structure."),
    "Port Reaper": ("red", "All teeth, no hymnbook. It plays for the harbor kill and accepts the wreckage."),
    "Harbor Lock": ("blue", "Locks the gates, counts the tides, and dares you to find a clean raid angle."),
    "Corsair Spark": ("red", "Volatile, rich in threats, and very comfortable setting the table on fire."),
    "Storm Reaver": ("orange", "Pressure from every quarter; less a plan than a weather system with knives."),
    "Iron Tempest": ("red", "Heavy raid-fire weather. It wants damage before diplomacy has found its boots."),
    "Black Ledger": ("magenta", "A brutal red-ink accountant: raids first, records the profit later."),
    "Bastion Corsair": ("orange", "A raider with a bunker mentality; mean pressure with just enough rebuilding instinct."),
    "Harbor Harvest": ("green", "Predatory fishing economics: raids the sea while quietly turning docks into money."),
    "Reef Tyrant": ("red", "Low-trade reef violence with fishing income and fire plans lurking underneath."),
    "Reef Bloom": ("cyan", "Odd, defensive, and infrastructure-hungry; it blooms from docks and dry repairs."),
    "The Red Tide": ("red", "A crimson raid tide. It does not negotiate with ports."),
    "Signal Black": ("magenta", "Minimalist raiding doctrine: almost no ornament, just black flags on the horizon."),
    "Gray Admiralty": ("white", "Cold staff work and dockside machinery; admirals, workers, and overtime in gray ink."),
}


def bot_role_line(strategy):
    weights = [
        ("Trade", strategy.trade_weight, UI.symbol("trade")),
        ("Raid", strategy.raid_weight, UI.symbol("raid")),
        ("Guard", strategy.guard_weight, UI.symbol("guard")),
        ("Fire", strategy.fire_weight, UI.symbol("fire")),
    ]
    weights.sort(key=lambda item: item[1], reverse=True)
    top = " / ".join(f"{icon} {name} {value:.1f}" for name, value, icon in weights[:2])
    low = weights[-1]
    return f"Profile: {top}; lightest {low[2]} {low[0]} {low[1]:.1f}."


def bot_build_line(strategy):
    if not strategy.build_priority:
        return UI.muted("Builds: no fixed project priority; relies on weighted buys.")
    projects = ", ".join(strategy.build_priority[:5])
    if len(strategy.build_priority) > 5:
        projects += ", ..."
    return f"Builds: {projects}."


def bot_bias_line(strategy):
    traits = []
    if strategy.convoy_bias >= 0.7:
        traits.append("convoy-heavy")
    elif strategy.convoy_bias <= 0.15:
        traits.append("convoy-shy")
    if strategy.ship_bias >= 0.85:
        traits.append("fleet growth")
    elif strategy.ship_bias <= 0.2:
        traits.append("lean fleet")
    if getattr(strategy, "adaptive", False):
        traits.append(f"adaptive x{strategy.adaptation_strength:g}")
    if strategy.opening_book:
        traits.append(f"{len(strategy.opening_book)} book lines")
    return "Traits: " + (", ".join(traits) if traits else "standard weighted play")


def bot_meta_record_lines(strategy, row=None):
    color, flavor = BOT_FLAVOR.get(
        strategy.name,
        ("cyan", "A developing doctrine with enough sharp edges to deserve respect."),
    )
    lines = [
        UI.paint(strategy.name, color, bold=True),
        UI.paint(flavor, color),
        bot_role_line(strategy),
        bot_build_line(strategy),
        bot_bias_line(strategy),
    ]
    if row and row["games"]:
        ai_win_rate = row["ai_wins"] / row["games"]
        lines.append(
            f"Human log: {row['games']} games, AI {ai_win_rate * 100:.1f}% win, "
            f"human {row['human_wins']}-{row['ai_wins']}-{row['draws']}."
        )
    else:
        lines.append(UI.muted("Human log: no recorded games yet."))
    return lines


def show_bot_meta(log_path):
    records, _warning = read_human_records(log_path)
    _overall, by_bot, _openers, _opener_counts = summarize_human_records(records)
    strategies = sorted(
        __import__("bot_roster").default_bot_strategies(),
        key=lambda strategy: strategy.name.lower(),
    )
    terminal_width = shutil.get_terminal_size((120, 36)).columns
    width = min(max(80, terminal_width), 120)

    overview = []
    for strategy in strategies:
        row = by_bot.get(strategy.name)
        if row and row["games"]:
            ai_win_rate = row["ai_wins"] / row["games"]
            overview.append(
                f"{strategy.name}: {row['games']} human games, AI {ai_win_rate * 100:.1f}% win"
            )
        else:
            overview.append(f"{strategy.name}: no human-log games")

    pages = [("Current Bot Meta", overview)]
    pages.extend((strategy.name, bot_meta_record_lines(strategy, by_bot.get(strategy.name))) for strategy in strategies)

    for index, (title, lines) in enumerate(pages, start=1):
        UI.clear_screen()
        UI.section("BOT META", "cyan")
        print(UI.muted(f"Page {index}/{len(pages)}"))
        print()
        for line in UI.panel(title, lines, width=width, wrap=True):
            print(line)
        print()
        prompt = "Press Enter for next page..." if index < len(pages) else "Press Enter to return to main menu..."
        input(prompt)


def prompt_main_menu():
    while True:
        UI.clear_screen()
        UI.section(f"SEALED ORDERS v{Rules.VERSION}", "magenta")
        choices = [
            ("1", "Play two-player game"),
            ("2", "Play vs AI"),
            ("3", "Seamanship's Manual"),
            ("4", "Human Records"),
            ("5", "Bot Meta"),
            ("0", "Quit"),
        ]
        for key, label in choices:
            print(f"{UI.paint(key + '.', 'green', bold=True)} {label}")

        choice = input("Main menu: ").strip().lower()
        if choice in {"1", "play", "two-player", "two player"}:
            return "play"
        if choice in {"2", "ai", "play-ai", "play ai"}:
            return "play_ai"
        if choice in {"3", "manual", "seamanship", "seamanships manual", "seamanship's manual"}:
            show_seamanship_manual()
            continue
        if choice in {"4", "records", "human records", "history"}:
            return "records"
        if choice in {"5", "bots", "bot meta", "meta", "ai opponents"}:
            return "bot_meta"
        if choice in {"0", "q", "quit", "exit"}:
            return "quit"
        print(UI.warning("Please choose 1, 2, 3, 4, 5, or 0."))
        input("Press Enter to continue...")


if __name__ == "__main__":
    """Main entry point for command-line play and bot training/simulation.
    Run with --help for available options.
    
        Examples:
        - Play a human-vs-AI game with a menu choice of AI opponent:
            python main.py --play-ai
        - Train an evolving strategy for 50 generations with 10 games per bot:
            python main.py --train-evolving 50 --training-games 10
        - Summarize recorded human-vs-AI games from a log file:
            python main.py --ai-log-summary --ai-log artifacts/logs/ai_game_log.jsonl
        - Benchmark an evolved strategy against the bot roster for 100 games per opponent:
            python main.py --evaluate-strategy evolved_strategy.json --eval-games 100
    """
    UI.prepare_terminal()
    
    # Flag parsing for both play and training modes
    parser = argparse.ArgumentParser(description="Play or simulate Sealed Orders.")
    parser.add_argument(
        "--play-ai",
        action="store_true",
        help="play a human-vs-AI game",
    )
    parser.add_argument(
        "--ai-strategy",
        help="AI strategy for --play-ai; omit to choose from a menu",
    )
    parser.add_argument(
        "--ai-log",
        default="artifacts/logs/ai_game_log.jsonl",
        help="where completed human-vs-AI games are recorded",
    )
    parser.add_argument(
        "--ai-log-summary",
        action="store_true",
        help="summarize recorded human-vs-AI games",
    )
    parser.add_argument(
        "--train-evolving",
        type=int,
        metavar="GENERATIONS",
        help="train a random evolving strategy against the bot roster",
    )
    parser.add_argument(
        "--training-games",
        type=int,
        default=6,
        help="games per bot per generation for --train-evolving",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.25,
        help="blend rate toward better mutations for --train-evolving",
    )
    parser.add_argument(
        "--mutation-scale",
        type=float,
        default=1.0,
        help="random weight mutation size for --train-evolving",
    )
    parser.add_argument(
        "--train-start-strategy",
        help=(
            "start --train-evolving from a named roster bot or strategy JSON "
            "instead of a random strategy"
        ),
    )
    parser.add_argument(
        "--seed-branch-chance",
        type=float,
        default=0.0,
        help=(
            "chance per generation to mutate from --train-start-strategy "
            "instead of the current incumbent"
        ),
    )
    parser.add_argument(
        "--training-workers",
        type=int,
        default=1,
        help="CPU worker processes for --train-evolving simulation batches",
    )
    parser.add_argument(
        "--evolved-output",
        help="optional JSON file for the final --train-evolving strategy",
    )
    parser.add_argument(
        "--training-history",
        help="optional JSON or CSV file for per-generation training metrics",
    )
    parser.add_argument(
        "--training-graph",
        help="optional SVG file plotting training win rate by generation",
    )
    parser.add_argument(
        "--show-training-weights",
        action="store_true",
        help="print live strategy weights during --train-evolving",
    )
    parser.add_argument(
        "--training-weights-interval",
        type=int,
        default=1,
        help="generation interval for --show-training-weights; learned generations always print",
    )
    parser.add_argument(
        "--training-dashboard",
        action="store_true",
        help="redraw a live top-style dashboard during --train-evolving",
    )
    parser.add_argument(
        "--training-dashboard-history",
        type=int,
        default=12,
        help="number of recent generation lines shown in --training-dashboard",
    )
    parser.add_argument(
        "--training-dashboard-benchmark-games",
        type=int,
        default=100,
        help="games per opponent for dashboard benchmarks after --train-evolving",
    )
    parser.add_argument(
        "--training-dashboard-window",
        type=int,
        default=100,
        help="rolling health window for --training-dashboard yield/fragility/candidate metrics",
    )
    parser.add_argument(
        "--evaluate-strategy",
        help="benchmark an evolved strategy JSON file against the bot roster",
    )
    parser.add_argument(
        "--eval-games",
        type=int,
        default=100,
        help="games per opponent for --evaluate-strategy",
    )
    parser.add_argument(
        "--eval-output",
        help="optional JSON or CSV file for --evaluate-strategy results",
    )
    parser.add_argument(
        "--eval-workers",
        type=int,
        default=1,
        help="CPU worker processes for --evaluate-strategy benchmarks",
    )
    parser.add_argument(
        "--self-play",
        type=int,
        metavar="GAMES",
        help="run a non-interactive bot tournament for the given number of games",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="set the random seed for repeatable self-play results",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        help="experimental override for game length; default is 12",
    )
    args = parser.parse_args()

    if args.max_turns is not None:
        # Experimental option to override the default 24-turn game length for testing purposes.
        try:
            Rules.set_max_turns(args.max_turns)
        except ValueError as error:
            parser.error(str(error))

    if args.evaluate_strategy is not None:
        # Benchmark a strategy file against the bot roster and output results.
        from bot_playtest import evaluate_strategy_file

        evaluate_strategy_file(
            strategy_path=args.evaluate_strategy,
            games_per_opponent=args.eval_games,
            seed=args.seed,
            output_path=args.eval_output,
            workers=args.eval_workers,
        )
    elif args.train_evolving is not None:
        # Train an evolving strategy against the bot roster and output results.
        from bot_playtest import train_evolving_strategy
        from bot_roster import find_strategy
        from bot_strategy import load_strategy

        initial_strategy = None
        if args.train_start_strategy:
            # Allow starting from either a named bot roster strategy or a custom strategy JSON file.
            try:
                initial_strategy = find_strategy(args.train_start_strategy)
            except ValueError:
                initial_strategy = load_strategy(args.train_start_strategy)

        train_evolving_strategy(
            # TODO: consider refactoring this function to take a config object instead of a long parameter list
            generations=args.train_evolving, 
            games_per_bot=args.training_games,
            learning_rate=args.learning_rate,
            mutation_scale=args.mutation_scale,
            seed=args.seed,
            output_path=args.evolved_output,
            history_path=args.training_history,
            graph_path=args.training_graph,
            show_weights=args.show_training_weights,
            weights_interval=args.training_weights_interval,
            dashboard=args.training_dashboard,
            dashboard_history=args.training_dashboard_history,
            dashboard_benchmark_games=args.training_dashboard_benchmark_games,
            dashboard_window=args.training_dashboard_window,
            initial_strategy=initial_strategy,
            seed_branch_chance=args.seed_branch_chance,
            workers=args.training_workers,
        )
    elif args.ai_log_summary:
        # Summarize recorded human-vs-AI games from a log file and output results.
        from bot_playtest import summarize_ai_games

        summarize_ai_games(log_path=args.ai_log)
    elif args.play_ai:
        from bot_playtest import find_strategy, play_vs_ai, strategy_names

        try:
            strategy_name = args.ai_strategy or prompt_ai_strategy(strategy_names())
            find_strategy(strategy_name)
            play_vs_ai(
                human_name=prompt_human_name(),
                strategy_name=strategy_name,
                seed=args.seed,
                log_path=args.ai_log,
            )
        except ValueError as error:
            parser.error(str(error))
    elif args.self_play is not None:
        from bot_playtest import run_self_play

        run_self_play(games=args.self_play, seed=args.seed)
    else:
        while True:
            menu_choice = prompt_main_menu()
            if menu_choice == "play":
                game = Game(prompt_player_names())
                game.play()
                break
            if menu_choice == "play_ai":
                from bot_playtest import find_strategy, play_vs_ai, strategy_names

                try:
                    strategy_name = prompt_ai_strategy(strategy_names())
                    find_strategy(strategy_name)
                    play_vs_ai(
                        human_name=prompt_human_name(),
                        strategy_name=strategy_name,
                        seed=args.seed,
                        log_path=args.ai_log,
                    )
                except ValueError as error:
                    parser.error(str(error))
                break
            if menu_choice == "records":
                show_human_records(args.ai_log)
                continue
            if menu_choice == "bot_meta":
                show_bot_meta(args.ai_log)
                continue
            if menu_choice == "quit":
                print("Fair winds.")
                break
