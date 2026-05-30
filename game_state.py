# game_state.py

### Imports ###
import math
import os
import re
import sys
import unicodedata


class UI:
    enabled = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    readable_reset = "\033[22;37m"
    readable_text = "\033[37m"
    terminal_prepared = False
    colors = {
        "blue": "34",
        "cyan": "36",
        "dim": "2",
        "green": "32",
        "magenta": "35",
        "orange": "38;5;208",
        "red": "31",
        "white": "37",
        "yellow": "33",
    }
    order_colors = {
        "trade": "green",
        "raid": "orange",
        "guard": "blue",
        "fire": "red",
    }
    symbols = {
        "gold": "◉",
        "ships": "⛵",
        "ship": "⛵",
        "assets": "◆",
        "asset": "◆",
        "value": "◆",
        "labor": "⚒",
        "worker": "⚒",
        "workers": "⚒",
        "supply": "▣",
        "trade": "⇄",
        "raid": "⚔",
        "guard": "◇",
        "fire": "※",
        "port": "⌂",
        "shipyard": "⚓",
        "yard": "⚓",
        "fort": "▰",
        "trade guild": "♜",
        "guild": "♜",
        "fishing": "≈",
        "dockhouse": "⌂",
        "dock hands": "⚒",
        "dry dock": "▱",
        "admiralty": "⌃",
        "admirals": "⌃",
        "captains": "◇",
        "convoy": "→",
        "treasure": "◉",
        "payroll": "◉",
        "complete": "✓",
        "started": "◐",
        "locked": "×",
        "warning": "!",
        "selected": "›",
        "done": "✓",
        "cancel": "×",
    }
    ansi_pattern = re.compile(r"\033\[[0-9;]*m")
    amount_pattern = re.compile(r"(?<![\w.])-?\d+(?:/\d+)?(?:\.\d+)?")

    @classmethod
    def prepare_terminal(cls):
        if cls.enabled and not cls.terminal_prepared:
            print(cls.readable_text, end="")
            cls.terminal_prepared = True

    @classmethod
    def paint(cls, text, color=None, bold=False):
        if not cls.enabled:
            return text

        codes = []
        if bold:
            codes.append("1")
        if color in cls.colors:
            codes.append(cls.colors[color])
        if not codes:
            return text
        return f"\033[{';'.join(codes)}m{text}{cls.readable_reset}"

    @classmethod
    def section(cls, title, color="cyan"):
        print()
        print(cls.paint(f"=== {title} ===", color, bold=True))

    @classmethod
    def clear_screen(cls):
        if cls.enabled:
            print("\033[2J\033[H", end="")

    @classmethod
    def subheading(cls, title, color="blue"):
        print()
        print(cls.paint(title, color, bold=True))

    @classmethod
    def bullet(cls, text, color=None):
        print(f"  {cls.paint('-', color)} {text}")

    @classmethod
    def label(cls, text):
        return cls.paint(text, "white", bold=True)

    @classmethod
    def symbol(cls, key, default=""):
        return cls.symbols.get(str(key).lower(), default)

    @classmethod
    def symbol_label(cls, key, text=None, color=None, bold=True):
        icon = cls.symbol(key)
        label = str(text if text is not None else key)
        if icon:
            label = f"{icon} {label}"
        return cls.paint(label, color, bold=bold)

    @classmethod
    def selected_marker(cls, selected=False):
        marker = cls.symbol("selected", ">") if selected else " "
        return cls.paint(marker, "green", bold=True) if selected else marker

    @classmethod
    def field(cls, text, width=15, icon=True):
        display = f"{cls.symbol(text)} {text}" if icon and cls.symbol(text) else str(text)
        padding = " " * max(0, width - cls.visible_len(display))
        return cls.label(f"{display}{padding}")

    @classmethod
    def muted(cls, text):
        return cls.paint(text, "dim")

    @classmethod
    def success(cls, text):
        return cls.paint(text, "green", bold=True)

    @classmethod
    def warning(cls, text):
        return cls.paint(text, "yellow", bold=True)

    @classmethod
    def danger(cls, text):
        return cls.paint(text, "red", bold=True)

    @classmethod
    def amount(cls, value, unit="", color="cyan", compact=True):
        if unit == "gold" and color == "cyan":
            color = "yellow"
        if unit and compact and cls.symbol(unit):
            suffix = f" {cls.symbol(unit)}"
        else:
            suffix = f" {unit}" if unit else ""
        return f"{cls.paint(str(value), color, bold=True)}{suffix}"

    @classmethod
    def payroll_gold(cls, value):
        return cls.amount(value, "gold", "blue")

    @classmethod
    def smuggle_gold(cls, value):
        return cls.amount(value, "gold", "magenta")

    @classmethod
    def order_color(cls, role):
        return cls.order_colors.get(str(role).lower(), "white")

    @classmethod
    def order_label(cls, role, width=None, icon=True):
        text = str(role)
        if icon and cls.symbol(role):
            text = f"{cls.symbol(role)} {text}"
        if width is not None:
            text = text + " " * max(0, width - cls.visible_len(text))
        return cls.paint(text, cls.order_color(role), bold=True)

    @classmethod
    def order_amount(cls, role, value):
        return cls.amount(value, color=cls.order_color(role))

    @classmethod
    def progress(cls, current, total, mode="normal"):
        if total <= 0:
            color = "green"
        elif mode == "neutral":
            color = "cyan" if current > 0 else None
        elif current <= 0:
            color = "green" if mode == "inverted" else "red"
        elif current >= total:
            color = "red" if mode == "inverted" else "green"
        elif current * 3 >= total * 2:
            color = "orange" if mode == "inverted" else "yellow"
        elif mode == "inverted":
            color = "yellow"
        else:
            color = "orange"
        return cls.paint(f"{current}/{total}", color, bold=bool(color))

    @classmethod
    def cost(cls, gold=0, labor=0):
        parts = []
        if gold:
            parts.append(cls.amount(gold, "gold", "yellow"))
        if labor:
            parts.append(cls.amount(labor, "labor"))
        return ", ".join(parts)

    @classmethod
    def delta(cls, value):
        if value == 0:
            return ""
        color = "green" if value > 0 else "red"
        sign = "+" if value > 0 else ""
        return " " + cls.paint(f"({sign}{value})", color, bold=True)

    @classmethod
    def accent_amounts(cls, text, color="cyan"):
        if not cls.enabled:
            return text
        if "\033[" in text:
            return text
        return cls.amount_pattern.sub(
            lambda match: cls.paint(match.group(0), color, bold=True),
            text,
        )

    @classmethod
    def visible_len(cls, text):
        text = cls.ansi_pattern.sub("", str(text))
        return sum(cls.char_width(character) for character in text)

    @classmethod
    def char_width(cls, character):
        if unicodedata.combining(character):
            return 0
        if unicodedata.category(character) in {"Cf", "Mn", "Me"}:
            return 0
        if unicodedata.east_asian_width(character) in {"F", "W"}:
            return 2
        return 1

    @classmethod
    def fit_panel_line(cls, text, width):
        text = str(text)
        content_width = max(1, width - 4)
        if cls.visible_len(text) > content_width:
            plain = cls.ansi_pattern.sub("", text)
            text = plain[: max(0, content_width - 3)] + "..."
        return f"| {text}{' ' * max(0, content_width - cls.visible_len(text))} |"

    @classmethod
    def wrap_panel_line(cls, text, width):
        content_width = max(1, width - 4)
        text = str(text)
        if cls.visible_len(text) <= content_width:
            return [text]

        words = text.split(" ")
        wrapped = []
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if cls.visible_len(candidate) <= content_width:
                current = candidate
                continue

            if current:
                wrapped.append(current)
                current = ""

            while cls.visible_len(word) > content_width:
                head, word = cls.split_visible(word, content_width)
                wrapped.append(head)
            current = word

        if current:
            wrapped.append(current)
        return wrapped or [""]

    @classmethod
    def split_visible(cls, text, width):
        visible = 0
        index = 0
        while index < len(text) and visible < width:
            if text[index] == "\033":
                match = cls.ansi_pattern.match(text, index)
                if match:
                    index = match.end()
                    continue
            visible += cls.char_width(text[index])
            index += 1
        return text[:index], text[index:]

    @classmethod
    def panel(cls, title, lines, width=60, wrap=False, body_height=None):
        width = max(24, width)
        title_text = f" {cls.paint(title, 'blue', bold=True)} "
        top_fill = max(0, width - cls.visible_len(title_text) - 2)
        top = "+" + title_text + "-" * top_fill + "+"
        body_text = []
        for line in lines:
            if wrap:
                body_text.extend(cls.wrap_panel_line(line, width))
            else:
                body_text.append(line)
        if body_height is not None and len(body_text) > body_height:
            hidden = len(body_text) - body_height + 1
            body_text = body_text[: max(0, body_height - 1)]
            body_text.append(cls.muted(f"... {hidden} more line(s)"))
        if body_height is not None:
            while len(body_text) < body_height:
                body_text.append("")
        body = [cls.fit_panel_line(line, width) for line in body_text]
        bottom = "+" + "-" * (width - 2) + "+"
        return [top, *body, bottom]

    @classmethod
    def fit_box_line(cls, text, width, border_color="cyan"):
        text = str(text)
        content_width = max(1, width - 4)
        if cls.visible_len(text) > content_width:
            plain = cls.ansi_pattern.sub("", text)
            text = plain[: max(0, content_width - 3)] + "..."
        padding = " " * max(0, content_width - cls.visible_len(text))
        return (
            cls.paint("│", border_color, bold=True)
            + f" {text}{padding} "
            + cls.paint("│", border_color, bold=True)
        )

    @classmethod
    def box(
        cls,
        title,
        lines,
        width=24,
        border_color="cyan",
        title_color=None,
        wrap=False,
    ):
        width = max(18, width)
        title_color = title_color or border_color
        title_text = f" {cls.paint(title, title_color, bold=True)} "
        top_fill = max(0, width - cls.visible_len(title_text) - 2)
        top = (
            cls.paint("┌", border_color, bold=True)
            + title_text
            + cls.paint("─" * top_fill + "┐", border_color, bold=True)
        )
        body_text = []
        for line in lines:
            if wrap:
                body_text.extend(cls.wrap_panel_line(line, width))
            else:
                body_text.append(line)
        body = [cls.fit_box_line(line, width, border_color) for line in body_text]
        bottom = cls.paint("└" + "─" * (width - 2) + "┘", border_color, bold=True)
        return [top, *body, bottom]

    @classmethod
    def title_box(cls, width=42, border_color="magenta", phase=None):
        width = max(34, width)
        content_width = width - 2
        phase_key = str(phase or "").lower()
        phase_titles = (
            ("resolution", "cannons roar"),
            ("convoy", "convoys inbound"),
            ("supply", "stores and strain"),
            ("labor", "hammers in port"),
            ("buy", "market tides"),
            ("orders", "hidden orders"),
            ("command", "captain's table"),
        )
        subtitle = next(
            (title for key, title in phase_titles if key in phase_key),
            "hidden orders",
        )

        def center_line(parts):
            text = "".join(parts)
            padding = max(0, content_width - cls.visible_len(text))
            left = padding // 2
            right = padding - left
            return (
                cls.paint("║", border_color, bold=True)
                + " " * left
                + text
                + " " * right
                + cls.paint("║", border_color, bold=True)
            )

        return [
            cls.paint("╔" + "═" * content_width + "╗", border_color, bold=True),
            center_line(
                [
                    cls.paint("◈", "cyan", bold=True),
                    "     ",
                    cls.paint("S E A L E D   O R D E R S", "yellow", bold=True),
                ]
            ),
            center_line(
                [
                    cls.paint("⚓", "blue", bold=True),
                    "  ",
                    cls.paint(subtitle, "white", bold=True),
                    "  ",
                    cls.paint("⚓", "blue", bold=True),
                ]
            ),
            center_line([cls.paint("open seas", "green"), cls.muted(" · sealed fates")]),
            cls.paint("╚" + "═" * content_width + "╝", border_color, bold=True),
        ]

    @classmethod
    def phase_color(cls, phase):
        phase = str(phase).lower()
        if "resolution" in phase:
            return "red"
        if "convoy" in phase:
            return "yellow"
        if "supply" in phase:
            return "orange"
        if "labor" in phase:
            return "blue"
        if "buy" in phase:
            return "green"
        if "orders" in phase:
            return "yellow"
        if "command" in phase:
            return "magenta"
        return "magenta"

    @classmethod
    def game_header(
        cls,
        month,
        phase,
        turn,
        max_turns,
        submitted=0,
        total_players=2,
        order_lines=None,
        columns=None,
    ):
        width = columns or 96
        content_width = min(max(80, width), 150)
        gap = 2
        stacked = content_width < 96
        if stacked:
            status_width = (content_width - gap) // 2
            orders_width = content_width - status_width - gap
            title_width = content_width
        else:
            status_width = max(31, min(40, int(content_width * 0.28)))
            orders_width = max(29, min(34, int(content_width * 0.24)))
            title_width = content_width - status_width - orders_width - gap * 2
        phase_color = cls.phase_color(phase)
        status = cls.box(
            "Status",
            [
                f"{cls.label('Month:')} {month}",
                f"{cls.label('Phase:')} {cls.paint(str(phase).upper(), phase_color, bold=True)}",
                f"{cls.label('Turn:')} {turn} / {max_turns}",
            ],
            width=status_width,
            border_color=phase_color,
            wrap=True,
        )
        title = cls.title_box(title_width, border_color=phase_color, phase=phase)
        order_lines = order_lines or [cls.muted("No current orders")]
        orders = cls.box(
            "Orders",
            order_lines,
            width=orders_width,
            border_color=phase_color,
            wrap=True,
        )
        target_height = max(len(status), len(title), len(orders))
        while len(status) < target_height:
            status.insert(-1, cls.fit_box_line("", status_width, phase_color))
        while len(orders) < target_height:
            orders.insert(-1, cls.fit_box_line("", orders_width, phase_color))

        rows = []
        left_title = cls.combine_panels(status, title, gap=gap)
        for index, row in enumerate(left_title):
            order_line = orders[index] if index < len(orders) else " " * orders_width
            rows.append(f"{row}{' ' * gap}{order_line}")
        if stacked:
            return [*title, *cls.combine_panels(status, orders, gap=gap)]
        return rows

    @classmethod
    def combine_panels(cls, left, right, gap=2):
        height = max(len(left), len(right))
        left_width = max(cls.visible_len(line) for line in left) if left else 0
        right_width = max(cls.visible_len(line) for line in right) if right else 0
        rows = []
        for index in range(height):
            left_line = left[index] if index < len(left) else " " * left_width
            right_line = right[index] if index < len(right) else " " * right_width
            rows.append(
                f"{left_line}{' ' * max(0, left_width - cls.visible_len(left_line) + gap)}{right_line}"
            )
        return rows

    @classmethod
    def pad_panel_height(cls, lines, width, target_height):
        lines = list(lines)
        while len(lines) < target_height and len(lines) >= 2:
            lines.insert(-1, cls.fit_panel_line("", width))
        return lines


class Rules:
    VERSION = "0.48"
    STARTING_GOLD = 10
    STARTING_SHIPS = 3
    TRADE_INCOME = 2
    SMUGGLE_INCOME = 1
    SHIP_COST = 6
    SHIPYARD_COST = 5
    SHIPYARD_LABOR_REQUIRED = 3
    SHIPYARD_DISCOUNT = 2
    SHIPYARD_ASSET_VALUE = 5
    FIRE_SHIP_UPGRADE_COST = 5
    PORT_ATTACK_SHIPS_REQUIRED = 5
    FORT_COST = 10
    FORT_LABOR_REQUIRED = 5
    FORT_ASSET_VALUE = 15
    FORT_PORT_DEFENSE = 10
    FORT_FIRE_BLOCKS_PER_TURN = 1
    FORT_RAID_BLOCKS_PER_TURN = 2
    GUARD_CAPTAIN_COST = 2
    GUARD_CAPTAIN_MAX = 5
    GUARD_CAPTAIN_PORT_DEFENSE = 1
    GUARD_CAPTAIN_CONFISCATIONS_PER_TURN = 1
    GUARD_CAPTAIN_SHIP_CAPTURE_THRESHOLD = 5
    GUARD_CAPTAIN_SHIP_CAPTURES_PER_TURN = 1
    TRADE_GUILD_COST = 6
    TRADE_GUILD_LABOR_REQUIRED = 4
    TRADE_GUILD_ASSET_VALUE = 8
    TRADE_GUILD_BONUS_STEP = 2
    ADMINISTRATOR_COST = 3
    ADMINISTRATOR_PAYROLL_COST = 1
    FISHING_DOCK_COST = 3
    FISHING_DOCK_LABOR_REQUIRED = 1
    FISHING_DOCK_ASSET_VALUE = 3
    FISHING_BOAT_COST = 2
    FISHING_BOAT_INCOME = 1
    FISHING_BOAT_ASSET_VALUE = 2
    DOCKHOUSE_COST = 4
    DOCKHOUSE_LABOR_REQUIRED = 2
    DOCKHOUSE_ASSET_VALUE = 6
    DOCKHAND_COST = 2
    DOCKHAND_MAX = 5
    DOCKHAND_PAYROLL_COST = 1
    DOCKHAND_SUPPLY_NEED = 1
    DOCKHAND_REPAIR_DISCOUNT = 1
    DOCKHAND_BOATWRIGHT_COST = 1
    RAID_ACTIONS_PER_DAMAGE = 5
    RAID_REPAIR_COST = 4
    SHIPYARD_RAID_REPAIR_COST = 2
    DRY_DOCK_COST = 2
    DRY_DOCK_LABOR_REQUIRED = 1
    DRY_DOCK_ASSET_VALUE = 2
    ADMIRALTY_COST = 7
    ADMIRALTY_LABOR_REQUIRED = 4
    ADMIRALTY_ASSET_VALUE = 15
    ADMIRAL_COST = 2
    ADMIRAL_MAX = 5
    ADMIRAL_SHIPS_PER_SLOT = 10
    ADMIRAL_PAYROLL_COST = 1
    MAX_TURNS = 24
    SUPPLY_MIN = -5
    SUPPLY_MAX = 5
    SUPPLY_SHIPS_PER_NEED = 4
    SUPPLY_LIGHT_DAMAGE_PERCENT = 0.20
    SUPPLY_DESERTION_PERCENT = 0.25
    SUPPLY_HEAVY_DESERTION_PERCENT = 0.50
    SUPPLY_WARCHEST_MARKUP = 4
    SUPPLY_ADMINISTRATOR_WARCHEST_MARKUP = 3
    MONTHS = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    TREASURE_BASE_VALUE = 10
    TREASURE_TRADE_PERCENT = 0.25
    TREASURE_TRAVEL_TURNS = 2
    PAYROLL_START_TURN = 5
    PAYROLL_FINAL_TURN = 8
    PAYROLL_TRAVEL_TURNS = 1
    PAYROLL_VALUE_PER_SHIP = 1
    PAYROLL_COST_PER_SHIP = 1
    PAYROLL_MUTINY_PERCENT = 0.25
    TRADE_GUILD_PAYROLL_DISCOUNT_PERCENT = 25

    @classmethod
    def set_max_turns(cls, max_turns):
        if max_turns < 1:
            raise ValueError("maximum turns must be at least 1")
        cls.MAX_TURNS = max_turns


class Allocation:
    def __init__(self, trade=0, raid=0, guard=0, fire=0):
        self.trade = trade
        self.raid = raid
        self.guard = guard
        self.fire = fire

    @property
    def total(self):
        return self.trade + self.raid + self.guard + self.fire

    def __repr__(self):
        return (
            f"{UI.order_label('Trade')} {UI.order_amount('Trade', self.trade)}, "
            f"{UI.order_label('Raid')} {UI.order_amount('Raid', self.raid)}, "
            f"{UI.order_label('Guard')} {UI.order_amount('Guard', self.guard)}, "
            f"{UI.order_label('Fire')} {UI.order_amount('Fire', self.fire)}"
        )


class ResolutionResult:
    def __init__(
        self,
        trade_income=0,
        fishing_income=0,
        stolen_income=0,
        confiscated_income=0,
        captured_smuggling_ships=0,
        treasure_growth=0,
        supply_trade_income=0,
        supply_stolen_income=0,
        supply_fishing_income=0,
    ):
        self.trade_income = trade_income
        self.fishing_income = fishing_income
        self.stolen_income = stolen_income
        self.confiscated_income = confiscated_income
        self.captured_smuggling_ships = captured_smuggling_ships
        self.treasure_growth = treasure_growth
        self.supply_trade_income = supply_trade_income
        self.supply_stolen_income = supply_stolen_income
        self.supply_fishing_income = supply_fishing_income


class Nation:
    def __init__(self, name):
        self.name = name
        self.gold = Rules.STARTING_GOLD
        self.ships = Rules.STARTING_SHIPS
        self.allocation = Allocation()
        self.treasure_value = Rules.TREASURE_BASE_VALUE
        self.treasure_turns_remaining = 0
        self.last_treasure_growth = 0
        self.last_treasure_growth_boost = 0
        self.payroll_launched = False
        self.payroll_launch_years = set()
        self.payroll_value = 0
        self.payroll_turns_remaining = 0
        self.shipyard_started = False
        self.shipyard_completed = False
        self.shipyard_labor = 0
        self.shipyard_destroyed = False
        self.fort_started = False
        self.fort_completed = False
        self.fort_labor = 0
        self.fort_fire_blocks_remaining = 0
        self.trade_guild_started = False
        self.trade_guild_completed = False
        self.trade_guild_labor = 0
        self.administrator_hired = False
        self.fire_ships_unlocked = False
        self.guard_captains = 0
        self.guard_captain_ship_captures = 0
        self.fishing_dock_started = False
        self.fishing_dock_labor = 0
        self.fishing_dock_built = False
        self.fishing_dock_disabled = False
        self.fishing_boats = 0
        self.dockhouse_started = False
        self.dockhouse_labor = 0
        self.dockhouse_completed = False
        self.dockhouse_burned = False
        self.dockhands = 0
        self.dockhand_duty = "construction"
        self.dockhand_repair_discount_remaining = 0
        self.dockhand_boatwright_boats = 0
        self.dockhand_discounted_repairs = 0
        self.dockhand_idle_turns = 0
        self.raid_actions_total = 0
        self.damaged_ships = 0
        self.raid_damage_events = 0
        self.raid_repairs_total = 0
        self.damaged_raiders_sunk = 0
        self.raid_skirmish_damage = 0
        self.raid_skirmish_sunk = 0
        self.dry_dock_started = False
        self.dry_dock_labor = 0
        self.dry_dock_completed = False
        self.admiralty_started = False
        self.admiralty_labor = 0
        self.admiralty_completed = False
        self.admiralty_ever_completed = False
        self.admiralty_burned = False
        self.admirals = 0
        self.admiralty_overtime_used = False
        self.admiralty_unrest_response_used = False
        self.supply = 0
        self.supply_crises = 0
        self.supply_desertions_total = 0
        self.supply_unrest_burns = 0
        self.supply_fishing_losses = 0
        self.last_supply_events = []

    def status_report(self):
        for line in self.status_lines():
            print(line)

    def status_lines(self):
        return [
            (
                f"{UI.amount(self.gold, 'gold', self.gold_color)}, "
                f"{UI.amount(self.ships, 'ships')}, "
                f"{UI.amount(self.asset_score, 'assets', 'yellow')}"
            ),
            (
                f"{UI.field('Treasure')} "
                f"{UI.amount(self.treasure_value, 'gold', 'yellow')}"
                f"{self.treasure_status}"
            ),
            f"{UI.field('Payroll')} {self.payroll_status}",
            f"{UI.field('Shipyard')} {self.shipyard_status}",
            f"{UI.field('Fort')} {self.fort_status}",
            f"{UI.field('Trade guild')} {self.trade_guild_status}",
            f"{UI.field('Fishing')} {self.fishing_status}",
            f"{UI.field('Dockhouse')} {self.dockhouse_status}",
            f"{UI.field('Dock hands')} {self.dockhand_status}",
            f"{UI.field('Supply')} {self.supply_status}",
            f"{UI.field('Raid fatigue')} {self.raid_fatigue_status}",
            f"{UI.field('Port defences')} {self.port_defense_status}",
            f"{UI.field('Dry dock')} {self.dry_dock_status}",
            f"{UI.field('Admiralty')} {self.admiralty_status}",
            f"{UI.field('Admirals')} {self.admiral_status}",
            f"{UI.field('Fire ships')} {self.fire_ship_status}",
            f"{UI.field('Guard captains')} {self.guard_captain_status}",
        ]

    def compact_status_lines(self):
        return [
            (
                f"{UI.amount(self.gold, 'gold', self.gold_color)}  "
                f"{UI.amount(self.ships, 'ships')}  "
                f"{UI.amount(self.asset_score, 'assets', 'yellow')}"
            ),
            f"{UI.symbol_label('Treasure', 'Treasure', 'yellow')}: {UI.amount(self.treasure_value, 'gold', 'yellow')}{self.treasure_status}",
            f"{UI.symbol_label('Payroll', 'Payroll', 'blue')}: {self.payroll_status}",
            f"{UI.symbol_label('Yard', 'Yard', 'green')}: {self.shipyard_status}",
            f"{UI.symbol_label('Fort', 'Fort', 'yellow')}: {self.fort_status}",
            f"{UI.symbol_label('Guild', 'Guild', 'green')}: {self.trade_guild_status}",
            f"{UI.symbol_label('Fishing', 'Fishing', 'blue')}: {self.fishing_status}",
            f"{UI.symbol_label('Dockhouse', 'Dockhouse', 'yellow')}: {self.dockhouse_status}",
            f"{UI.symbol_label('Dock hands', 'Hands', 'yellow')}: {self.dockhand_status}",
            f"{UI.symbol_label('Supply', 'Supply', 'cyan')}: {self.supply_status}",
            f"{UI.symbol_label('Raid', 'Raid', 'orange')}: {self.raid_fatigue_status}",
            f"{UI.symbol_label('Port', 'Port def', 'blue')}: {self.port_defense_status}",
            f"{UI.symbol_label('Dry dock', 'Dry dock', 'cyan')}: {self.dry_dock_status}",
            f"{UI.symbol_label('Admiralty', 'Admiralty', 'white')}: {self.admiralty_status}",
            f"{UI.symbol_label('Admirals', 'Admirals', 'white')}: {self.admiral_status}",
            f"{UI.symbol_label('Fire', 'Fire', 'red')}: {self.fire_ship_status}",
            f"{UI.symbol_label('Captains', 'Captains', 'magenta')}: {self.guard_captain_status}",
        ]

    @property
    def gold_color(self):
        if self.gold < 0:
            return "red"
        if self.gold == 0:
            return "yellow"
        return "green"

    def buy_ships(self, amount):
        cost = amount * self.ship_cost
        self.gold -= cost
        self.ships += amount

    def start_shipyard(self):
        self.gold -= Rules.SHIPYARD_COST
        self.shipyard_started = True
        self.shipyard_destroyed = False

    def unlock_fire_ships(self):
        self.gold -= Rules.FIRE_SHIP_UPGRADE_COST
        self.fire_ships_unlocked = True

    def hire_guard_captain(self):
        self.gold -= Rules.GUARD_CAPTAIN_COST
        self.guard_captains += 1

    def build_or_repair_fishing_dock(self):
        self.gold -= Rules.FISHING_DOCK_COST
        if self.fishing_dock_disabled:
            self.fishing_dock_disabled = False
            self.fishing_dock_built = False
            self.fishing_dock_started = True
            self.fishing_dock_labor = 0
        else:
            self.fishing_dock_started = True

    def buy_fishing_boats(self, amount):
        self.gold -= amount * Rules.FISHING_BOAT_COST
        self.fishing_boats += amount

    def start_dockhouse(self):
        self.gold -= Rules.DOCKHOUSE_COST
        self.dockhouse_started = True
        self.dockhouse_burned = False

    def hire_dockhand(self):
        self.gold -= Rules.DOCKHAND_COST
        self.dockhands += 1

    def set_dockhand_duty(self, duty):
        self.dockhand_duty = duty

    def add_fishing_dock_labor(self, available_labor):
        if (
            not self.fishing_dock_started
            or self.fishing_dock_built
            or self.fishing_dock_disabled
        ):
            return 0

        needed = Rules.FISHING_DOCK_LABOR_REQUIRED - self.fishing_dock_labor
        labor = min(available_labor, needed)
        self.fishing_dock_labor += labor
        if self.fishing_dock_labor >= Rules.FISHING_DOCK_LABOR_REQUIRED:
            self.fishing_dock_built = True
            self.fishing_dock_started = False
        return labor

    def start_fort(self):
        self.gold -= Rules.FORT_COST
        self.fort_started = True

    def start_trade_guild(self):
        self.gold -= Rules.TRADE_GUILD_COST
        self.trade_guild_started = True

    def start_dry_dock(self):
        self.gold -= Rules.DRY_DOCK_COST
        self.dry_dock_started = True

    def start_admiralty(self):
        self.gold -= Rules.ADMIRALTY_COST
        self.admiralty_started = True

    def recruit_admiral(self):
        self.gold -= Rules.ADMIRAL_COST
        self.admirals += 1

    def hire_administrator(self):
        self.gold -= Rules.ADMINISTRATOR_COST
        self.administrator_hired = True

    def destroy_shipyard(self):
        self.burn_shipyard()

    def burn_shipyard(self):
        self.shipyard_started = False
        self.shipyard_completed = False
        self.shipyard_labor = 0
        self.shipyard_destroyed = True

    def burn_fort(self):
        self.fort_started = False
        self.fort_completed = False
        self.fort_labor = 0
        self.fort_fire_blocks_remaining = 0

    def burn_trade_guild(self):
        self.trade_guild_started = False
        self.trade_guild_completed = False
        self.trade_guild_labor = 0
        self.administrator_hired = False

    def burn_fishing_dock(self):
        self.fishing_dock_started = False
        self.fishing_dock_built = False
        self.fishing_dock_disabled = False
        self.fishing_dock_labor = 0

    def burn_dockhouse(self):
        self.dockhouse_started = False
        self.dockhouse_completed = False
        self.dockhouse_labor = 0
        self.dockhouse_burned = True
        self.dockhand_duty = "construction"
        self.dockhand_repair_discount_remaining = 0

    def burn_dry_dock(self):
        self.dry_dock_started = False
        self.dry_dock_completed = False
        self.dry_dock_labor = 0

    def burn_fire_plans(self):
        self.fire_ships_unlocked = False

    def burn_admiralty(self):
        if self.admiralty_completed or self.admiralty_ever_completed:
            self.admiralty_burned = True
        self.admiralty_started = False
        self.admiralty_completed = False
        self.admiralty_labor = 0
        self.admiralty_overtime_used = False
        self.admiralty_unrest_response_used = False

    def disable_fishing_dock(self):
        if not self.fishing_dock_built or self.fishing_dock_disabled:
            return False
        self.fishing_dock_disabled = True
        self.fishing_dock_started = False
        self.fishing_dock_labor = 0
        return True

    def add_shipyard_labor(self, labor):
        if not self.shipyard_started or self.shipyard_completed or labor <= 0:
            return 0

        remaining_labor = Rules.SHIPYARD_LABOR_REQUIRED - self.shipyard_labor
        applied_labor = min(labor, remaining_labor)
        self.shipyard_labor += applied_labor

        if self.shipyard_labor >= Rules.SHIPYARD_LABOR_REQUIRED:
            self.shipyard_completed = True

        return applied_labor

    def add_fort_labor(self, labor):
        if not self.fort_started or self.fort_completed or labor <= 0:
            return 0

        remaining_labor = Rules.FORT_LABOR_REQUIRED - self.fort_labor
        applied_labor = min(labor, remaining_labor)
        self.fort_labor += applied_labor

        if self.fort_labor >= Rules.FORT_LABOR_REQUIRED:
            self.fort_completed = True

        return applied_labor

    def add_trade_guild_labor(self, labor):
        if not self.trade_guild_started or self.trade_guild_completed or labor <= 0:
            return 0

        remaining_labor = Rules.TRADE_GUILD_LABOR_REQUIRED - self.trade_guild_labor
        applied_labor = min(labor, remaining_labor)
        self.trade_guild_labor += applied_labor

        if self.trade_guild_labor >= Rules.TRADE_GUILD_LABOR_REQUIRED:
            self.trade_guild_completed = True

        return applied_labor

    def add_dockhouse_labor(self, labor):
        if not self.dockhouse_started or self.dockhouse_completed or labor <= 0:
            return 0

        remaining_labor = Rules.DOCKHOUSE_LABOR_REQUIRED - self.dockhouse_labor
        applied_labor = min(labor, remaining_labor)
        self.dockhouse_labor += applied_labor
        if self.dockhouse_labor >= Rules.DOCKHOUSE_LABOR_REQUIRED:
            self.dockhouse_completed = True
        return applied_labor

    def add_dry_dock_labor(self, labor):
        if not self.dry_dock_started or self.dry_dock_completed or labor <= 0:
            return 0

        remaining_labor = Rules.DRY_DOCK_LABOR_REQUIRED - self.dry_dock_labor
        applied_labor = min(labor, remaining_labor)
        self.dry_dock_labor += applied_labor

        if self.dry_dock_labor >= Rules.DRY_DOCK_LABOR_REQUIRED:
            self.dry_dock_completed = True

        return applied_labor

    def add_admiralty_labor(self, labor):
        if not self.admiralty_started or self.admiralty_completed or labor <= 0:
            return 0

        remaining_labor = Rules.ADMIRALTY_LABOR_REQUIRED - self.admiralty_labor
        applied_labor = min(labor, remaining_labor)
        self.admiralty_labor += applied_labor
        if self.admiralty_labor >= Rules.ADMIRALTY_LABOR_REQUIRED:
            self.admiralty_completed = True
            self.admiralty_ever_completed = True
        return applied_labor

    def record_raid_actions(self, raid_actions):
        if raid_actions <= 0:
            return 0

        previous_total = self.raid_actions_total
        self.raid_actions_total += raid_actions
        previous_damage = previous_total // Rules.RAID_ACTIONS_PER_DAMAGE
        new_damage = self.raid_actions_total // Rules.RAID_ACTIONS_PER_DAMAGE
        damage_added = max(0, new_damage - previous_damage)
        if damage_added:
            self.raid_damage_events += damage_added
            self.damaged_ships = min(self.ships, self.damaged_ships + damage_added)
        return damage_added

    def cap_damaged_ships(self):
        self.damaged_ships = min(self.damaged_ships, max(0, self.ships))

    def repair_damaged_ships(self, amount):
        repaired = min(amount, self.damaged_ships)
        self.gold -= self.raid_repair_total_cost(repaired)
        discounted = self.discounted_repair_count(repaired)
        if discounted:
            self.dockhand_repair_discount_remaining -= discounted
            self.dockhand_discounted_repairs += discounted
        self.damaged_ships -= repaired
        self.raid_repairs_total += repaired
        return repaired

    def reset_fort_fire_blocks(self):
        if self.fort_completed:
            self.fort_fire_blocks_remaining = Rules.FORT_FIRE_BLOCKS_PER_TURN
        else:
            self.fort_fire_blocks_remaining = 0

    def block_shipyard_fire(self):
        if self.fort_fire_blocks_remaining <= 0:
            return False

        self.fort_fire_blocks_remaining -= 1
        return True

    @property
    def ship_cost(self):
        if self.shipyard_completed:
            return Rules.SHIP_COST - Rules.SHIPYARD_DISCOUNT
        return Rules.SHIP_COST

    @property
    def ship_value(self):
        return self.ships * Rules.SHIP_COST

    @property
    def shipyard_value(self):
        if self.shipyard_completed:
            return Rules.SHIPYARD_ASSET_VALUE
        return 0

    @property
    def fort_value(self):
        if self.fort_completed:
            return Rules.FORT_ASSET_VALUE
        return 0

    @property
    def trade_guild_value(self):
        if self.trade_guild_completed:
            return Rules.TRADE_GUILD_ASSET_VALUE
        return 0

    @property
    def fishing_dock_value(self):
        if self.fishing_dock_built and not self.fishing_dock_disabled:
            return Rules.FISHING_DOCK_ASSET_VALUE
        return 0

    @property
    def fishing_boat_value(self):
        return self.fishing_boats * Rules.FISHING_BOAT_ASSET_VALUE

    @property
    def dry_dock_value(self):
        if self.dry_dock_completed:
            return Rules.DRY_DOCK_ASSET_VALUE
        return 0

    @property
    def dockhouse_value(self):
        if self.dockhouse_completed:
            return Rules.DOCKHOUSE_ASSET_VALUE
        return 0

    @property
    def admiralty_value(self):
        if self.admiralty_completed:
            return Rules.ADMIRALTY_ASSET_VALUE
        return 0

    @property
    def fishing_income(self):
        if self.fishing_dock_built and not self.fishing_dock_disabled:
            return self.fishing_boats * Rules.FISHING_BOAT_INCOME
        return 0

    @property
    def supply_need(self):
        return (
            math.ceil(self.ships / Rules.SUPPLY_SHIPS_PER_NEED)
            + self.dockhands * Rules.DOCKHAND_SUPPLY_NEED
        )

    @property
    def supply_status(self):
        status = f"{self.supply_crates()} ({self.supply:+d}), needs {self.supply_need} sea income"
        bonuses = []
        if self.supply >= 4 and self.trade_guild_completed:
            bonuses.append("trade guild x2")
        elif self.supply >= 4:
            bonuses.append("needs guild for +5")
        if self.supply >= 5:
            bonuses.append(f"trade ships +{UI.amount(1, 'gold', 'yellow')}")
        if bonuses:
            status += f", {', '.join(bonuses)}"
        if self.last_supply_events:
            status += f", {self.supply_event_summary}"
        return status

    def supply_crates(self):
        filled = max(0, min(10, self.supply + Rules.SUPPLY_MAX))
        empty = 10 - filled
        if self.supply >= 4:
            color = "green"
        elif self.supply >= 0:
            color = "yellow"
        elif self.supply <= -4:
            color = "red"
        else:
            color = "orange"
        return UI.paint("#" * filled, color, bold=True) + UI.muted("." * empty)

    @property
    def supply_event_summary(self):
        return " ".join(self.format_supply_event(event) for event in self.last_supply_events)

    def format_supply_event(self, event):
        if event == "Smg+":
            return UI.paint(event, "magenta", bold=True)
        if event.startswith("Adm"):
            return UI.paint(event, "white", bold=True)
        if event.startswith("Capt"):
            return UI.paint(event, "magenta", bold=True)
        return event

    @property
    def treasure_growth_ticker(self):
        if self.last_treasure_growth <= 0:
            return UI.muted("route +0")
        boost = min(self.last_treasure_growth, self.last_treasure_growth_boost)
        base = self.last_treasure_growth - boost
        if boost <= 0:
            return UI.paint(f"route +{self.last_treasure_growth}", "cyan", bold=True)
        parts = [UI.paint("route", "blue", bold=True)]
        if base:
            parts.append(UI.paint(f"+{base}", "cyan", bold=True))
        parts.append(UI.paint(f"+{boost}", "green", bold=True))
        return " ".join(parts)

    @property
    def guard_captain_port_defense(self):
        if self.fort_completed:
            return self.guard_captains * Rules.GUARD_CAPTAIN_PORT_DEFENSE
        return 0

    @property
    def port_attack_threshold(self):
        threshold = Rules.PORT_ATTACK_SHIPS_REQUIRED
        if self.fort_completed:
            threshold += Rules.FORT_PORT_DEFENSE
            threshold += self.guard_captain_port_defense
        return threshold

    @property
    def port_defense_status(self):
        parts = [f"{Rules.PORT_ATTACK_SHIPS_REQUIRED} base"]
        if self.fort_completed:
            parts.append(f"+{Rules.FORT_PORT_DEFENSE} fort")
            captain_defense = self.guard_captain_port_defense
            if captain_defense:
                parts.append(
                    f"+{UI.paint(captain_defense, 'magenta', bold=True)} captains "
                    f"({UI.paint(self.guard_captains, 'magenta', bold=True)} x "
                    f"{Rules.GUARD_CAPTAIN_PORT_DEFENSE})"
                )
            elif self.guard_captains:
                parts.append(
                    f"+0 captains ({UI.paint(self.guard_captains, 'magenta', bold=True)} stationed)"
                )
        elif self.guard_captains:
            parts.append(
                f"+0 captains ({UI.paint(self.guard_captains, 'magenta', bold=True)}, "
                "requires fort)"
            )
        if self.admiralty_completed:
            parts.append("+port workers as Admiralty conscripts when attacked")
        return (
            f"{self.port_attack_threshold} raid ships to destroy port "
            f"({', '.join(parts)})"
        )

    @property
    def base_raid_repair_cost(self):
        if self.dry_dock_completed:
            return 0
        if self.shipyard_completed:
            return Rules.SHIPYARD_RAID_REPAIR_COST
        return Rules.RAID_REPAIR_COST

    @property
    def raid_repair_cost(self):
        if self.dockhand_repair_discount_remaining <= 0:
            return self.base_raid_repair_cost
        return max(0, self.base_raid_repair_cost - Rules.DOCKHAND_REPAIR_DISCOUNT)

    def discounted_repair_count(self, amount):
        if self.base_raid_repair_cost <= 0:
            return 0
        return min(amount, self.dockhand_repair_discount_remaining)

    def raid_repair_total_cost(self, amount):
        discounted = self.discounted_repair_count(amount)
        full_price = max(0, amount - discounted)
        discounted_cost = max(
            0,
            self.base_raid_repair_cost - Rules.DOCKHAND_REPAIR_DISCOUNT,
        )
        return discounted * discounted_cost + full_price * self.base_raid_repair_cost

    def affordable_repairs(self):
        if self.damaged_ships <= 0:
            return 0
        if self.base_raid_repair_cost == 0:
            return self.damaged_ships

        affordable = 0
        gold = self.gold
        while affordable < self.damaged_ships:
            next_cost = (
                self.raid_repair_total_cost(affordable + 1)
                - self.raid_repair_total_cost(affordable)
            )
            if gold < next_cost:
                break
            gold -= next_cost
            affordable += 1
        return affordable

    @property
    def asset_score(self):
        return (
            self.gold
            + self.ship_value
            + self.shipyard_value
            + self.fort_value
            + self.trade_guild_value
            + self.fishing_dock_value
            + self.fishing_boat_value
            + self.dockhouse_value
            + self.dry_dock_value
            + self.admiralty_value
        )

    @property
    def has_treasure_at_sea(self):
        return self.treasure_turns_remaining > 0

    @property
    def has_payroll_at_sea(self):
        return self.payroll_turns_remaining > 0

    @property
    def payroll_cost(self):
        cost = self.ships * Rules.PAYROLL_COST_PER_SHIP
        cost += self.admirals * Rules.ADMIRAL_PAYROLL_COST
        cost += self.dockhands * Rules.DOCKHAND_PAYROLL_COST
        if self.trade_guild_completed:
            cost *= 100 - Rules.TRADE_GUILD_PAYROLL_DISCOUNT_PERCENT
            cost = (cost + 99) // 100
        if self.administrator_hired:
            cost += Rules.ADMINISTRATOR_PAYROLL_COST

        return cost

    @property
    def supply_warchest_markup(self):
        if self.trade_guild_completed and self.administrator_hired:
            return Rules.SUPPLY_ADMINISTRATOR_WARCHEST_MARKUP
        return Rules.SUPPLY_WARCHEST_MARKUP

    @property
    def admiral_slots(self):
        fleet_slots = self.ships // Rules.ADMIRAL_SHIPS_PER_SLOT
        if self.admiralty_completed:
            fleet_slots += 1
        return min(Rules.ADMIRAL_MAX, fleet_slots)

    @property
    def dockhands_active(self):
        return self.dockhouse_completed and self.dockhands > 0

    @property
    def dockhands_full_roster(self):
        return self.dockhands >= Rules.DOCKHAND_MAX

    @property
    def dockhand_construction_labor(self):
        if not self.dockhands_active:
            return 0
        if self.dockhands_full_roster and self.dockhand_duty != "construction":
            return 0
        return self.dockhands

    def refresh_dockhand_repair_discount(self):
        if (
            self.dockhands_full_roster
            and self.dockhouse_completed
            and self.dockhand_duty == "repair"
            and self.base_raid_repair_cost > 0
        ):
            self.dockhand_repair_discount_remaining = Rules.DOCKHAND_MAX
        else:
            self.dockhand_repair_discount_remaining = 0

    def dockhand_boatwright_target(self):
        if (
            not self.dockhands_full_roster
            or not self.dockhouse_completed
            or self.dockhand_duty != "boatwright"
            or not self.fishing_dock_built
            or self.fishing_dock_disabled
        ):
            return 0
        if self.dry_dock_completed:
            return 2
        return 1

    def apply_dockhand_boatwright(self):
        target = self.dockhand_boatwright_target()
        if target <= 0:
            return 0
        boats = min(target, self.gold // Rules.DOCKHAND_BOATWRIGHT_COST)
        if boats <= 0:
            return 0
        self.gold -= boats * Rules.DOCKHAND_BOATWRIGHT_COST
        self.fishing_boats += boats
        self.dockhand_boatwright_boats += boats
        return boats

    @property
    def treasure_status(self):
        if self.has_treasure_at_sea:
            return f" at sea, arrives in {self.treasure_turns_remaining} turn(s)"
        return " ready"

    @property
    def payroll_status(self):
        if self.has_payroll_at_sea:
            return (
                f"{UI.payroll_gold(self.payroll_value)} at sea, arrives in "
                f"{self.payroll_turns_remaining} turn(s)"
            )
        if self.payroll_launched:
            return "completed"
        start_month = Rules.MONTHS[Rules.PAYROLL_START_TURN - 1]
        final_month = Rules.MONTHS[Rules.PAYROLL_FINAL_TURN - 1]
        return f"must launch between {start_month}-{final_month}"

    @property
    def shipyard_status(self):
        if self.shipyard_completed:
            return f"{UI.symbol('complete')} completed, ships cost {UI.amount(self.ship_cost, 'gold', 'yellow')}"
        if self.shipyard_started:
            return (
                f"{UI.symbol('started')} building, "
                f"{UI.progress(self.shipyard_labor, Rules.SHIPYARD_LABOR_REQUIRED)} {UI.symbol('labor')}"
            )
        if self.shipyard_destroyed:
            return f"{UI.symbol('warning')} burned ({UI.amount(Rules.SHIPYARD_COST, 'gold', 'yellow')} rebuild)"
        return (
            f"{UI.symbol('locked')} not started ({UI.cost(Rules.SHIPYARD_COST, Rules.SHIPYARD_LABOR_REQUIRED)})"
        )

    @property
    def fort_status(self):
        if self.fort_completed:
            return (
                f"{UI.symbol('complete')} completed, blocks "
                f"{UI.amount(Rules.FORT_RAID_BLOCKS_PER_TURN, 'ships')} raid"
            )
        if self.fort_started:
            return (
                f"{UI.symbol('started')} building, "
                f"{UI.progress(self.fort_labor, Rules.FORT_LABOR_REQUIRED)} {UI.symbol('labor')}"
            )
        return f"{UI.symbol('locked')} not started ({UI.cost(Rules.FORT_COST, Rules.FORT_LABOR_REQUIRED)})"

    @property
    def trade_guild_status(self):
        if self.trade_guild_completed:
            if self.administrator_hired:
                return (
                    f"{UI.symbol('complete')} completed, administrator active "
                    f"(war chest {self.supply_warchest_markup}x, "
                    f"+{Rules.ADMINISTRATOR_PAYROLL_COST} payroll)"
                )
            return (
                f"{UI.symbol('complete')} completed, administrator available "
                f"({UI.amount(Rules.ADMINISTRATOR_COST, 'gold', 'yellow')}, "
                f"+{Rules.ADMINISTRATOR_PAYROLL_COST} payroll)"
            )
        if self.trade_guild_started:
            return (
                f"{UI.symbol('started')} building, "
                f"{UI.progress(self.trade_guild_labor, Rules.TRADE_GUILD_LABOR_REQUIRED)} {UI.symbol('labor')}"
            )
        return (
            f"{UI.symbol('locked')} not started ({UI.cost(Rules.TRADE_GUILD_COST, Rules.TRADE_GUILD_LABOR_REQUIRED)})"
        )

    @property
    def fishing_status(self):
        if self.fishing_dock_started and not self.fishing_dock_built:
            return (
                f"{UI.symbol('started')} docks building, "
                f"{UI.progress(self.fishing_dock_labor, Rules.FISHING_DOCK_LABOR_REQUIRED)} "
                f"{UI.symbol('labor')}, 0 boats"
            )
        if not self.fishing_dock_built:
            return (
                f"{UI.symbol('locked')} no docks ({UI.cost(Rules.FISHING_DOCK_COST, Rules.FISHING_DOCK_LABOR_REQUIRED)}), 0 boats"
            )
        if self.fishing_dock_disabled:
            return (
                f"{UI.symbol('warning')} docks disabled ({UI.amount(Rules.FISHING_DOCK_COST, 'gold', 'yellow')} repair), "
                f"{self.fishing_boats} boat(s), 0 income"
            )
        return (
            f"{UI.symbol('complete')} docks active, {self.fishing_boats} boat(s), "
            f"+{UI.amount(self.fishing_income, 'gold', 'yellow')}/turn"
        )

    @property
    def dockhouse_status(self):
        if self.dockhouse_completed:
            return f"{UI.symbol('complete')} completed"
        if self.dockhouse_started:
            return (
                f"{UI.symbol('started')} building, "
                f"{UI.progress(self.dockhouse_labor, Rules.DOCKHOUSE_LABOR_REQUIRED)} {UI.symbol('labor')}"
            )
        if self.dockhouse_burned:
            return f"{UI.symbol('warning')} burned ({UI.cost(Rules.DOCKHOUSE_COST, Rules.DOCKHOUSE_LABOR_REQUIRED)})"
        return (
            f"{UI.symbol('locked')} not started ({UI.cost(Rules.DOCKHOUSE_COST, Rules.DOCKHOUSE_LABOR_REQUIRED)})"
        )

    @property
    def dockhand_status(self):
        count = UI.progress(self.dockhands, Rules.DOCKHAND_MAX, mode="neutral")
        upkeep = (
            f"+{self.dockhands * Rules.DOCKHAND_PAYROLL_COST} payroll, "
            f"+{self.dockhands * Rules.DOCKHAND_SUPPLY_NEED} supply need"
        )
        if self.dockhands <= 0:
            return f"{count}, locked until hired"
        if not self.dockhouse_completed:
            return f"{count}, idle/no dockhouse, {upkeep}"
        if self.dockhands_full_roster:
            if self.dockhand_duty == "repair":
                duty = f"repair -1 x{Rules.DOCKHAND_MAX}"
            elif self.dockhand_duty == "boatwright":
                if not self.fishing_dock_built or self.fishing_dock_disabled:
                    duty = "boatwright idle/no docks"
                else:
                    boats = 2 if self.dry_dock_completed else 1
                    duty = f"boats {Rules.DOCKHAND_BOATWRIGHT_COST}g each x{boats}"
            else:
                duty = f"construction +{self.dockhand_construction_labor} {UI.symbol('labor')}"
            return f"{count}, {duty}, {upkeep}"
        return f"{count}, construction +{self.dockhand_construction_labor} {UI.symbol('labor')}, {upkeep}"

    @property
    def fire_ship_status(self):
        if self.fire_ships_unlocked:
            return "available"
        return f"{UI.symbol('locked')} locked ({UI.amount(Rules.FIRE_SHIP_UPGRADE_COST, 'gold', 'yellow')} upgrade)"

    @property
    def guard_captain_status(self):
        status = UI.paint(
            f"{self.guard_captains}/{Rules.GUARD_CAPTAIN_MAX}",
            "magenta",
            bold=self.guard_captains > 0,
        )
        if self.guard_captains == 0:
            return status

        if self.guard_captains >= Rules.GUARD_CAPTAIN_SHIP_CAPTURE_THRESHOLD:
            capstone = (
                f"captures {UI.amount(1, 'ships')} smuggler instead of {UI.smuggle_gold(1)}"
            )
        else:
            needed = Rules.GUARD_CAPTAIN_SHIP_CAPTURE_THRESHOLD - self.guard_captains
            capstone = f"{needed} more for smuggler ship capture"

        confiscations = (
            self.guard_captains * Rules.GUARD_CAPTAIN_CONFISCATIONS_PER_TURN
        )
        defense = self.guard_captain_port_defense
        if defense:
            return (
                f"{status}, confiscates {UI.smuggle_gold(confiscations)} smuggle, "
                f"+{defense} port defense, {capstone}"
            )
        return f"{status}, confiscates {UI.smuggle_gold(confiscations)} smuggle, {capstone}"

    @property
    def raid_fatigue_status(self):
        progress = self.raid_actions_total % Rules.RAID_ACTIONS_PER_DAMAGE
        return (
            f"{self.damaged_ships} damaged ship(s), "
            f"{UI.progress(progress, Rules.RAID_ACTIONS_PER_DAMAGE, mode='inverted')} toward next damage, "
            f"repair {UI.amount(self.raid_repair_cost, 'gold', 'yellow')} each"
        )

    @property
    def dry_dock_status(self):
        if self.dry_dock_completed:
            return f"{UI.symbol('complete')} completed, raid repairs free"
        if self.dry_dock_started:
            return (
                f"{UI.symbol('started')} building, "
                f"{UI.progress(self.dry_dock_labor, Rules.DRY_DOCK_LABOR_REQUIRED)} {UI.symbol('labor')}"
            )
        return (
            f"{UI.symbol('locked')} not started ({UI.cost(Rules.DRY_DOCK_COST, Rules.DRY_DOCK_LABOR_REQUIRED)}, requires shipyard)"
        )

    @property
    def admiralty_status(self):
        if self.admiralty_completed:
            overtime = "overtime used" if self.admiralty_overtime_used else "overtime ready"
            return f"{UI.symbol('complete')} completed, {overtime}"
        if self.admiralty_started:
            return (
                f"{UI.symbol('started')} building, "
                f"{UI.progress(self.admiralty_labor, Rules.ADMIRALTY_LABOR_REQUIRED)} {UI.symbol('labor')}"
            )
        return (
            f"{UI.symbol('locked')} not started ({UI.cost(Rules.ADMIRALTY_COST, Rules.ADMIRALTY_LABOR_REQUIRED)})"
        )

    @property
    def admiral_status(self):
        if not self.admiralty_completed:
            return "locked (requires admiralty)"
        return (
            f"{UI.progress(self.admirals, Rules.ADMIRAL_MAX, mode='neutral')}, "
            f"{self.admiral_slots} slot(s) by fleet size, "
            f"+{self.admirals * Rules.ADMIRAL_PAYROLL_COST} payroll"
        )

    def launch_treasure(self):
        self.treasure_turns_remaining = Rules.TREASURE_TRAVEL_TURNS

    def complete_treasure(self):
        payout = self.treasure_value
        self.gold += payout
        self.treasure_value = Rules.TREASURE_BASE_VALUE
        self.treasure_turns_remaining = 0
        self.last_treasure_growth = 0
        self.last_treasure_growth_boost = 0
        return payout

    def capture_treasure(self):
        payout = self.treasure_value
        self.treasure_value = Rules.TREASURE_BASE_VALUE
        self.treasure_turns_remaining = 0
        self.last_treasure_growth = 0
        self.last_treasure_growth_boost = 0
        return payout

    def launch_payroll(self, year=None):
        self.payroll_launched = True
        if year is not None:
            self.payroll_launch_years.add(year)
        cost = self.payroll_cost
        self.gold -= cost
        self.payroll_value = self.ships * Rules.PAYROLL_VALUE_PER_SHIP
        self.payroll_turns_remaining = Rules.PAYROLL_TRAVEL_TURNS
        return cost

    def complete_payroll(self):
        payout = self.payroll_value
        self.payroll_value = 0
        self.payroll_turns_remaining = 0
        return payout

    def capture_payroll(self):
        payout = self.payroll_value
        self.payroll_value = 0
        self.payroll_turns_remaining = 0
        mutiny_losses = self.calculate_mutiny_losses()
        self.ships -= mutiny_losses
        self.cap_damaged_ships()
        return payout, mutiny_losses

    def calculate_mutiny_losses(self):
        if self.ships == 0:
            return 0
        return max(1, int(self.ships * Rules.PAYROLL_MUTINY_PERCENT + 0.999))

    def remove_ships_for_supply(self, amount):
        losses = min(amount, self.ships)
        damaged_losses = min(self.damaged_ships, losses)
        self.damaged_ships -= damaged_losses
        self.ships -= losses
        self.cap_damaged_ships()
        self.supply_desertions_total += losses
        return losses
