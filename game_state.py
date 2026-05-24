import os
import re
import sys


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
        "red": "31",
        "white": "37",
        "yellow": "33",
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
    def field(cls, text, width=15):
        return cls.label(f"{text:<{width}}")

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
    def amount(cls, value, unit="", color="cyan"):
        suffix = f" {unit}" if unit else ""
        return f"{cls.paint(str(value), color, bold=True)}{suffix}"

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
        return len(cls.ansi_pattern.sub("", str(text)))

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
            visible += 1
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
    VERSION = "0.44"
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
    FISHING_DOCK_COST = 3
    FISHING_DOCK_LABOR_REQUIRED = 1
    FISHING_DOCK_ASSET_VALUE = 3
    FISHING_BOAT_COST = 2
    FISHING_BOAT_INCOME = 1
    FISHING_BOAT_ASSET_VALUE = 2
    RAID_ACTIONS_PER_DAMAGE = 5
    RAID_REPAIR_COST = 4
    SHIPYARD_RAID_REPAIR_COST = 2
    DRY_DOCK_COST = 2
    DRY_DOCK_LABOR_REQUIRED = 1
    DRY_DOCK_ASSET_VALUE = 2
    ADMIRALTY_COST = 10
    ADMIRALTY_LABOR_REQUIRED = 5
    ADMIRALTY_ASSET_VALUE = 15
    ADMIRAL_COST = 3
    ADMIRAL_MAX = 5
    ADMIRAL_SHIPS_PER_SLOT = 10
    ADMIRAL_PAYROLL_COST = 1
    MAX_TURNS = 12
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
            f"Trade {self.trade}, Raid {self.raid}, Guard {self.guard}, "
            f"Fire {self.fire}"
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
    ):
        self.trade_income = trade_income
        self.fishing_income = fishing_income
        self.stolen_income = stolen_income
        self.confiscated_income = confiscated_income
        self.captured_smuggling_ships = captured_smuggling_ships
        self.treasure_growth = treasure_growth


class Nation:
    def __init__(self, name):
        self.name = name
        self.gold = Rules.STARTING_GOLD
        self.ships = Rules.STARTING_SHIPS
        self.allocation = Allocation()
        self.treasure_value = Rules.TREASURE_BASE_VALUE
        self.treasure_turns_remaining = 0
        self.payroll_launched = False
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
        self.fire_ships_unlocked = False
        self.guard_captains = 0
        self.guard_captain_ship_captures = 0
        self.fishing_dock_started = False
        self.fishing_dock_labor = 0
        self.fishing_dock_built = False
        self.fishing_dock_disabled = False
        self.fishing_boats = 0
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
        self.admirals = 0
        self.admiralty_overtime_used = False

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
            f"Treasure: {UI.amount(self.treasure_value, 'gold', 'yellow')}{self.treasure_status}",
            f"Payroll: {self.payroll_status}",
            f"Yard: {self.shipyard_status}",
            f"Fort: {self.fort_status}",
            f"Guild: {self.trade_guild_status}",
            f"Fishing: {self.fishing_status}",
            f"Raid: {self.raid_fatigue_status}",
            f"Port defences: {self.port_defense_status}",
            f"Dry dock: {self.dry_dock_status}",
            f"Admiralty: {self.admiralty_status}",
            f"Admirals: {self.admiral_status}",
            f"Fire: {self.fire_ship_status}",
            f"Captains: {self.guard_captain_status}",
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

    def destroy_shipyard(self):
        self.shipyard_started = False
        self.shipyard_completed = False
        self.shipyard_labor = 0
        self.shipyard_destroyed = True

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
        self.gold -= repaired * self.raid_repair_cost
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
                    f"+{captain_defense} captains "
                    f"({self.guard_captains} x {Rules.GUARD_CAPTAIN_PORT_DEFENSE})"
                )
            elif self.guard_captains:
                parts.append(f"+0 captains ({self.guard_captains} stationed)")
        elif self.guard_captains:
            parts.append(f"+0 captains ({self.guard_captains}, requires fort)")
        if self.admiralty_completed:
            parts.append("+port workers as Admiralty conscripts when attacked")
        return (
            f"{self.port_attack_threshold} raid ships to destroy port "
            f"({', '.join(parts)})"
        )

    @property
    def raid_repair_cost(self):
        if self.dry_dock_completed:
            return 0
        if self.shipyard_completed:
            return Rules.SHIPYARD_RAID_REPAIR_COST
        return Rules.RAID_REPAIR_COST

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
        if self.trade_guild_completed:
            cost *= 100 - Rules.TRADE_GUILD_PAYROLL_DISCOUNT_PERCENT
            cost = (cost + 99) // 100

        return cost

    @property
    def admiral_slots(self):
        return min(Rules.ADMIRAL_MAX, self.ships // Rules.ADMIRAL_SHIPS_PER_SLOT)

    @property
    def treasure_status(self):
        if self.has_treasure_at_sea:
            return f" at sea, arrives in {self.treasure_turns_remaining} turn(s)"
        return " ready"

    @property
    def payroll_status(self):
        if self.has_payroll_at_sea:
            return (
                f"{self.payroll_value} gold at sea, arrives in "
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
            return f"completed, ships cost {self.ship_cost} gold"
        if self.shipyard_started:
            return (
                f"under construction, {self.shipyard_labor}/"
                f"{Rules.SHIPYARD_LABOR_REQUIRED} labor"
            )
        if self.shipyard_destroyed:
            return f"burned down ({Rules.SHIPYARD_COST} gold to rebuild)"
        return (
            f"not started ({Rules.SHIPYARD_COST} gold, "
            f"{Rules.SHIPYARD_LABOR_REQUIRED} labor)"
        )

    @property
    def fort_status(self):
        if self.fort_completed:
            return (
                "completed, blocks "
                f"{Rules.FORT_RAID_BLOCKS_PER_TURN} raid ship(s)"
            )
        if self.fort_started:
            return f"under construction, {self.fort_labor}/{Rules.FORT_LABOR_REQUIRED} labor"
        return f"not started ({Rules.FORT_COST} gold, {Rules.FORT_LABOR_REQUIRED} labor)"

    @property
    def trade_guild_status(self):
        if self.trade_guild_completed:
            return "completed"
        if self.trade_guild_started:
            return (
                f"under construction, {self.trade_guild_labor}/"
                f"{Rules.TRADE_GUILD_LABOR_REQUIRED} labor"
            )
        return (
            f"not started ({Rules.TRADE_GUILD_COST} gold, "
            f"{Rules.TRADE_GUILD_LABOR_REQUIRED} labor)"
        )

    @property
    def fishing_status(self):
        if self.fishing_dock_started and not self.fishing_dock_built:
            return (
                f"docks under construction, {self.fishing_dock_labor}/"
                f"{Rules.FISHING_DOCK_LABOR_REQUIRED} labor, 0 boats"
            )
        if not self.fishing_dock_built:
            return (
                f"no docks ({Rules.FISHING_DOCK_COST} gold, "
                f"{Rules.FISHING_DOCK_LABOR_REQUIRED} labor), 0 boats"
            )
        if self.fishing_dock_disabled:
            return (
                f"docks disabled ({Rules.FISHING_DOCK_COST} gold repair), "
                f"{self.fishing_boats} boat(s), 0 income"
            )
        return (
            f"docks active, {self.fishing_boats} boat(s), "
            f"+{self.fishing_income} gold/turn"
        )

    @property
    def fire_ship_status(self):
        if self.fire_ships_unlocked:
            return "available"
        return f"locked ({Rules.FIRE_SHIP_UPGRADE_COST} gold upgrade)"

    @property
    def guard_captain_status(self):
        status = f"{self.guard_captains}/{Rules.GUARD_CAPTAIN_MAX}"
        if self.guard_captains == 0:
            return status

        if self.guard_captains >= Rules.GUARD_CAPTAIN_SHIP_CAPTURE_THRESHOLD:
            capstone = (
                "captures 1 smuggling ship instead of confiscating gold"
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
                f"{status}, confiscates {confiscations} smuggle gold, "
                f"+{defense} port defense, {capstone}"
            )
        return f"{status}, confiscates {confiscations} smuggle gold, {capstone}"

    @property
    def raid_fatigue_status(self):
        progress = self.raid_actions_total % Rules.RAID_ACTIONS_PER_DAMAGE
        return (
            f"{self.damaged_ships} damaged ship(s), "
            f"{progress}/{Rules.RAID_ACTIONS_PER_DAMAGE} toward next damage, "
            f"repair {self.raid_repair_cost} gold each"
        )

    @property
    def dry_dock_status(self):
        if self.dry_dock_completed:
            return "completed, raid repairs are free"
        if self.dry_dock_started:
            return (
                f"under construction, {self.dry_dock_labor}/"
                f"{Rules.DRY_DOCK_LABOR_REQUIRED} labor"
            )
        return (
            f"not started ({Rules.DRY_DOCK_COST} gold, "
            f"{Rules.DRY_DOCK_LABOR_REQUIRED} labor, requires shipyard)"
        )

    @property
    def admiralty_status(self):
        if self.admiralty_completed:
            overtime = "overtime used" if self.admiralty_overtime_used else "overtime ready"
            return f"completed, {overtime}"
        if self.admiralty_started:
            return (
                f"under construction, {self.admiralty_labor}/"
                f"{Rules.ADMIRALTY_LABOR_REQUIRED} labor"
            )
        return (
            f"not started ({Rules.ADMIRALTY_COST} gold, "
            f"{Rules.ADMIRALTY_LABOR_REQUIRED} labor)"
        )

    @property
    def admiral_status(self):
        if not self.admiralty_completed:
            return "locked (requires admiralty)"
        return (
            f"{self.admirals}/{Rules.ADMIRAL_MAX}, "
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
        return payout

    def capture_treasure(self):
        payout = self.treasure_value
        self.treasure_value = Rules.TREASURE_BASE_VALUE
        self.treasure_turns_remaining = 0
        return payout

    def launch_payroll(self):
        self.payroll_launched = True
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
