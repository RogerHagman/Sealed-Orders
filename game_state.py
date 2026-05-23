import os
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


class Rules:
    VERSION = "0.40"
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
    RAID_ACTIONS_PER_DAMAGE = 10
    RAID_REPAIR_COST = 4
    SHIPYARD_RAID_REPAIR_COST = 1
    DRY_DOCK_COST = 3
    DRY_DOCK_LABOR_REQUIRED = 2
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
        treasure_growth=0,
    ):
        self.trade_income = trade_income
        self.fishing_income = fishing_income
        self.stolen_income = stolen_income
        self.confiscated_income = confiscated_income
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
        self.fort_started = False
        self.fort_completed = False
        self.fort_labor = 0
        self.fort_fire_blocks_remaining = 0
        self.trade_guild_started = False
        self.trade_guild_completed = False
        self.trade_guild_labor = 0
        self.fire_ships_unlocked = False
        self.guard_captains = 0
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
        self.dry_dock_started = False
        self.dry_dock_labor = 0
        self.dry_dock_completed = False

    def status_report(self):
        print(
            f"{UI.paint(self.name, 'magenta', bold=True)}: "
            f"{UI.paint(str(self.gold), self.gold_color, bold=True)} gold, "
            f"{UI.paint(str(self.ships), 'cyan', bold=True)} ships, "
            f"{UI.paint(str(self.asset_score), 'yellow', bold=True)} assets"
        )
        print(
            f"  {UI.field('Treasure')} "
            f"{self.treasure_value} gold{self.treasure_status}"
        )
        print(f"  {UI.field('Payroll')} {self.payroll_status}")
        print(f"  {UI.field('Shipyard')} {self.shipyard_status}")
        print(f"  {UI.field('Fort')} {self.fort_status}")
        print(f"  {UI.field('Trade guild')} {self.trade_guild_status}")
        print(f"  {UI.field('Fishing')} {self.fishing_status}")
        print(f"  {UI.field('Raid fatigue')} {self.raid_fatigue_status}")
        print(f"  {UI.field('Dry dock')} {self.dry_dock_status}")
        print(f"  {UI.field('Fire ships')} {self.fire_ship_status}")
        print(f"  {UI.field('Guard captains')} {self.guard_captain_status}")

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

    def destroy_shipyard(self):
        self.shipyard_started = False
        self.shipyard_completed = False
        self.shipyard_labor = 0

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
        if self.trade_guild_completed:
            cost *= 100 - Rules.TRADE_GUILD_PAYROLL_DISCOUNT_PERCENT
            cost = (cost + 99) // 100

        return cost

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

        confiscations = (
            self.guard_captains * Rules.GUARD_CAPTAIN_CONFISCATIONS_PER_TURN
        )
        defense = self.guard_captain_port_defense
        if defense:
            return (
                f"{status}, confiscates {confiscations} smuggle gold, "
                f"+{defense} port defense"
            )
        return f"{status}, confiscates {confiscations} smuggle gold"

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
