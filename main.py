import argparse
import os
import sys

if __name__ == "__main__":
    sys.modules["main"] = sys.modules[__name__]


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
    VERSION = "0.33"
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
        return payout, mutiny_losses

    def calculate_mutiny_losses(self):
        if self.ships == 0:
            return 0
        return max(1, int(self.ships * Rules.PAYROLL_MUTINY_PERCENT + 0.999))


class Game:
    def __init__(self, player_names):
        if len(player_names) != 2:
            raise ValueError("Sealed Orders MVP requires exactly two players.")

        self.players = [Nation(name) for name in player_names]
        self.turn = 1
        self.port_labor = {}
        self.game_over = False
        self.port_destroyer = None
        self.port_destroyed = None

    def play(self):
        UI.section(f"SEALED ORDERS v{Rules.VERSION}", "magenta")
        UI.bullet("Assign ships to Trade, Raid, Guard, and Fire.", "cyan")
        UI.bullet(f"Highest total assets after {Rules.MAX_TURNS} turns wins.", "yellow")
        UI.bullet("Treasure and payroll convoys create delayed, raidable payouts.")
        UI.bullet("Idle ships can finish shipyards, forts, and trade guilds.")
        UI.bullet("Fire ships and guard captains are buy-phase upgrades.")

        while self.turn <= Rules.MAX_TURNS and not self.game_over:
            self.play_turn()
            self.turn += 1

        self.show_final_scores()

    def play_turn(self):
        UI.section(f"{self.current_month.upper()} ({self.turn}/{Rules.MAX_TURNS})")
        self.show_state()
        before_snapshot = self.snapshot_turn()

        for player in self.players:
            self.pause_for_private_entry(player)
            player.allocation = self.prompt_allocation(player)

        orders_snapshot = self.snapshot_turn()
        self.clear_between_players()
        self.reveal_orders()
        self.resolve_orders()
        if self.game_over:
            return
        self.pause_after_resolution()
        self.apply_port_labor()
        self.advance_convoys()
        self.buy_phase()
        after_snapshot = self.snapshot_turn()
        self.show_turn_summary(before_snapshot, after_snapshot, orders_snapshot)

    def show_state(self):
        UI.subheading("Public State")
        for player in self.players:
            player.status_report()

    def snapshot_turn(self):
        return {player.name: self.snapshot_player(player) for player in self.players}

    def snapshot_player(self, player):
        return {
            "gold": player.gold,
            "ships": player.ships,
            "asset_score": player.asset_score,
            "treasure_status": f"{player.treasure_value} gold{player.treasure_status}",
            "payroll_status": player.payroll_status,
            "shipyard_status": player.shipyard_status,
            "fort_status": player.fort_status,
            "trade_guild_status": player.trade_guild_status,
            "fishing_status": player.fishing_status,
            "fire_ship_status": player.fire_ship_status,
            "guard_captain_status": player.guard_captain_status,
            "allocation": Allocation(
                player.allocation.trade,
                player.allocation.raid,
                player.allocation.guard,
                player.allocation.fire,
            ),
        }

    def show_turn_summary(self, before_snapshot, after_snapshot, orders_snapshot):
        UI.section(f"END OF {self.current_month.upper()} SUMMARY", "blue")
        for player in self.players:
            before = before_snapshot[player.name]
            after = after_snapshot[player.name]
            orders = orders_snapshot[player.name]
            UI.subheading(player.name, "magenta")
            print(f"  Orders: {orders['allocation']}")
            print(f"  Gold: {self.format_delta(before['gold'], after['gold'])}")
            print(f"  Ships: {self.format_delta(before['ships'], after['ships'])}")
            print(
                f"  Assets: "
                f"{self.format_delta(before['asset_score'], after['asset_score'])}"
            )
            self.print_status_change("Treasure", before, after, "treasure_status")
            self.print_status_change("Payroll", before, after, "payroll_status")
            self.print_status_change("Shipyard", before, after, "shipyard_status")
            self.print_status_change("Fort", before, after, "fort_status")
            self.print_status_change("Trade guild", before, after, "trade_guild_status")
            self.print_status_change("Fishing", before, after, "fishing_status")
            self.print_status_change("Fire ships", before, after, "fire_ship_status")
            self.print_status_change(
                "Guard captains",
                before,
                after,
                "guard_captain_status",
            )

    def format_delta(self, before, after):
        delta = after - before
        sign = "+" if delta >= 0 else ""
        color = "green" if delta > 0 else "red" if delta < 0 else "dim"
        return f"{before} -> {after} ({UI.paint(f'{sign}{delta}', color, bold=True)})"

    def print_status_change(self, label, before, after, key):
        if before[key] == after[key]:
            return

        print(f"  {label}: {before[key]} -> {after[key]}")

    @property
    def current_month(self):
        month = Rules.MONTHS[(self.turn - 1) % len(Rules.MONTHS)]
        year = ((self.turn - 1) // len(Rules.MONTHS)) + 1
        if year == 1:
            return month
        return f"{month}, Year {year}"

    def show_player_economy(self, player):
        UI.section(f"{player.name}'s Economy - {self.current_month}", "blue")
        player.status_report()
        print(
            f"  {UI.field('Assets')} {UI.paint(str(player.asset_score), 'yellow', bold=True)} "
            f"(shipyard value: {player.shipyard_value}, "
            f"fort value: {player.fort_value}, "
            f"trade guild value: {player.trade_guild_value})"
        )
        print(
            f"  {UI.field('Economy')} Trade income: {Rules.TRADE_INCOME} gold, "
            f"smuggle income: {Rules.SMUGGLE_INCOME} gold, "
            f"fishing boat income: {Rules.FISHING_BOAT_INCOME} gold"
        )
        print(
            f"  {UI.field('Ships')} Cost: {player.ship_cost} gold, "
            f"ship value: {Rules.SHIP_COST} gold"
        )
        print(
            f"  {UI.field('Fishing')} Docks: {Rules.FISHING_DOCK_COST} gold, "
            f"{Rules.FISHING_DOCK_LABOR_REQUIRED} labor; "
            f"boats: {Rules.FISHING_BOAT_COST} gold each"
        )
        if not player.payroll_launched:
            print(f"  {UI.field('Payroll cost')} {player.payroll_cost} gold")

    def pause_for_private_entry(self, player):
        self.clear_between_players()
        input(f"{player.name}, press Enter when you are ready to enter sealed orders...")
        self.show_player_economy(player)

    def prompt_allocation(self, player):
        while True:
            print(f"\n{player.name}, assign up to {player.ships} ships.")
            trade = self.prompt_non_negative_int("Trade ships: ")
            raid = self.prompt_non_negative_int("Raid ships: ")
            guard = self.prompt_non_negative_int("Guard ships: ")
            fire = 0
            if player.fire_ships_unlocked:
                fire = self.prompt_non_negative_int("Fire ships: ")
            else:
                print("Fire ships: locked")
            allocation = Allocation(trade, raid, guard, fire)

            if allocation.total <= player.ships:
                return allocation

            print(
                UI.danger(
                    f"Invalid allocation: assigned {allocation.total} ships, "
                    f"but only {player.ships} are available."
                )
            )

    def prompt_non_negative_int(self, prompt):
        while True:
            raw_value = input(prompt).strip()
            try:
                value = int(raw_value)
            except ValueError:
                print(UI.warning("Please enter a whole number."))
                continue

            if value < 0:
                print(UI.warning("Please enter zero or a positive number."))
                continue

            return value

    def clear_between_players(self):
        print("\n" * 40)

    def reveal_orders(self):
        UI.section("REVEALING SEALED ORDERS", "magenta")
        for player in self.players:
            print(f"{UI.paint(player.name, 'magenta', bold=True)}: {player.allocation}")

    def pause_after_resolution(self):
        input("\nPress Enter to continue to port labor, convoy arrivals, and buy phase...")

    def resolve_orders(self):
        UI.section("RESOLUTION", "red")
        player_one, player_two = self.players
        for player in self.players:
            player.reset_fort_fire_blocks()

        self.port_labor = {
            player: max(0, player.ships - player.allocation.total)
            for player in self.players
        }

        self.resolve_fire_ships(attacker=player_one, defender=player_two)
        self.resolve_fire_ships(attacker=player_two, defender=player_one)
        self.resolve_raid_guard_battle(raider=player_one, guarder=player_two)
        self.resolve_raid_guard_battle(raider=player_two, guarder=player_one)

        if self.resolve_port_destruction(attacker=player_one, defender=player_two):
            return
        if self.resolve_port_destruction(attacker=player_two, defender=player_one):
            return

        result_one = self.resolve_income(trader=player_one, opponent=player_two)
        result_two = self.resolve_income(trader=player_two, opponent=player_one)

        player_one_income = (
            result_one.trade_income
            + result_one.fishing_income
            + result_two.stolen_income
            + result_two.confiscated_income
        )
        player_two_income = (
            result_two.trade_income
            + result_two.fishing_income
            + result_one.stolen_income
            + result_one.confiscated_income
        )

        player_one.gold += player_one_income
        player_two.gold += player_two_income

        print(
            f"\n{player_one.name} earns {player_one_income} gold total "
            f"({result_one.trade_income} trade, {result_one.fishing_income} fishing, "
            f"{result_two.stolen_income} stolen, "
            f"{result_two.confiscated_income} confiscated)."
        )
        print(
            f"{player_two.name} earns {player_two_income} gold total "
            f"({result_two.trade_income} trade, {result_two.fishing_income} fishing, "
            f"{result_one.stolen_income} stolen, "
            f"{result_one.confiscated_income} confiscated)."
        )

    def resolve_fire_ships(self, attacker, defender):
        fire_strength = attacker.allocation.fire
        guard_strength = defender.allocation.guard

        print(f"\n{attacker.name}'s fire ships approach {defender.name}'s guards:")

        if fire_strength == 0:
            print(" - No fire ships launched.")
            return

        burned_guards = min(fire_strength, guard_strength)
        shipyard_attack = 0
        fishing_dock_attack = 0
        blocked_fire = 0

        attacker.allocation.fire -= burned_guards
        defender.allocation.guard -= burned_guards
        attacker.ships -= burned_guards
        defender.ships -= burned_guards

        if burned_guards:
            print(
                f" - {burned_guards} fire ship(s) burn "
                f"{burned_guards} guard ship(s)."
            )
            print(f" - {attacker.name} loses {burned_guards} fire ship(s).")

        if (
            attacker.allocation.fire > 0
            and (
                defender.shipyard_started
                or (
                    defender.fishing_dock_built
                    and not defender.fishing_dock_disabled
                )
            )
        ):
            if defender.block_shipyard_fire():
                blocked_fire = 1
                attacker.allocation.fire -= blocked_fire
                attacker.ships -= blocked_fire
                print(
                    f" - {defender.name}'s fort blocks 1 fire ship "
                    "before it reaches the shipyard."
                )
                print(f" - {attacker.name} loses 1 fire ship.")

        if attacker.allocation.fire > 0 and defender.shipyard_started:
            shipyard_attack = 1
            attacker.allocation.fire -= shipyard_attack
            attacker.ships -= shipyard_attack
            defender.destroy_shipyard()
            print(
                f" - 1 fire ship reaches port and destroys "
                f"{defender.name}'s shipyard."
            )
            print(f" - {attacker.name} loses 1 fire ship.")

        if (
            attacker.allocation.fire > 0
            and defender.fishing_dock_built
            and not defender.fishing_dock_disabled
        ):
            fishing_dock_attack = 1
            attacker.allocation.fire -= fishing_dock_attack
            attacker.ships -= fishing_dock_attack
            defender.disable_fishing_dock()
            print(
                f" - 1 fire ship burns {defender.name}'s fishing docks. "
                "Fishing boats survive, but income stops until repairs."
            )
            print(f" - {attacker.name} loses 1 fire ship.")

        if (
            burned_guards == 0
            and shipyard_attack == 0
            and fishing_dock_attack == 0
            and blocked_fire == 0
        ):
            print(
                " - No guards, shipyard, or active fishing docks are in position. "
                "The fire ships withdraw."
            )

    def resolve_raid_guard_battle(self, raider, guarder):
        raid_strength = raider.allocation.raid
        guard_strength = guarder.allocation.guard
        engaged_ships = min(raid_strength, guard_strength)

        print(f"\n{raider.name}'s raiders meet {guarder.name}'s guards:")

        if raid_strength == 0 or guard_strength == 0:
            print(" - No battle.")
            return

        raider_losses = 0
        guarder_losses = 0

        if raid_strength > guard_strength:
            guarder_losses = self.calculate_overwhelming_losses(
                stronger=raid_strength,
                weaker=guard_strength,
                engaged_ships=engaged_ships,
            )
        elif guard_strength > raid_strength:
            raider_losses = self.calculate_overwhelming_losses(
                stronger=guard_strength,
                weaker=raid_strength,
                engaged_ships=engaged_ships,
            )
        elif raid_strength >= 2:
            raider_losses = 1
            guarder_losses = 1

        raider.allocation.raid -= engaged_ships
        guarder.allocation.guard -= engaged_ships
        raider.ships -= raider_losses
        guarder.ships -= guarder_losses

        if raider_losses == 0 and guarder_losses == 0:
            print(" - Even light forces disengage. No ships sink or reach trade.")
            return

        if raider_losses:
            print(f" - {raider.name} loses {raider_losses} raid ship(s).")
        if guarder_losses:
            print(f" - {guarder.name} loses {guarder_losses} guard ship(s).")

    def calculate_overwhelming_losses(self, stronger, weaker, engaged_ships):
        if stronger >= weaker * 2:
            return engaged_ships
        if stronger * 2 >= weaker * 3:
            return min(2, engaged_ships)
        return 1

    def resolve_port_destruction(self, attacker, defender):
        if defender.ships > 0:
            return False

        required_raids = Rules.PORT_ATTACK_SHIPS_REQUIRED
        if defender.fort_completed:
            required_raids += Rules.FORT_PORT_DEFENSE
            required_raids += defender.guard_captain_port_defense

        if attacker.allocation.raid < required_raids:
            return False

        self.game_over = True
        self.port_destroyer = attacker
        self.port_destroyed = defender
        print(
            f"\n{attacker.name} sends {attacker.allocation.raid} raid ship(s) "
            f"against {defender.name}'s undefended home port "
            f"({required_raids} required)."
        )
        print(f"{defender.name}'s home port is destroyed.")
        return True

    def resolve_income(self, trader, opponent):
        remaining_trade = trader.allocation.trade
        active_raids = opponent.allocation.raid
        stolen_income = 0
        confiscated_income = 0

        print(f"\n{trader.name}'s trade and convoys:")
        active_raids = self.apply_fort_raid_blocks(trader, active_raids)

        if trader.has_treasure_at_sea and active_raids > 0:
            treasure_stolen = trader.capture_treasure()
            stolen_income += treasure_stolen
            active_raids -= 1
            print(
                f" - Treasure convoy captured; {opponent.name} steals "
                f"{treasure_stolen} gold."
            )
        elif trader.has_treasure_at_sea:
            print(
                f" - Treasure convoy worth {trader.treasure_value} gold "
                f"evades raiders."
            )

        if trader.has_payroll_at_sea and active_raids > 0:
            payroll_stolen, mutiny_losses = trader.capture_payroll()
            stolen_income += payroll_stolen
            active_raids -= 1
            print(
                f" - Payroll convoy captured; {opponent.name} steals "
                f"{payroll_stolen} gold and {trader.name} loses "
                f"{mutiny_losses} ship(s) to mutiny."
            )
        elif trader.has_payroll_at_sea:
            print(
                f" - Payroll convoy worth {trader.payroll_value} gold "
                f"evades raiders."
            )

        raid_intercepts = min(active_raids, remaining_trade)
        remaining_trade -= raid_intercepts
        stolen_trade_income = raid_intercepts * Rules.TRADE_INCOME
        stolen_income += stolen_trade_income

        smuggled_trade = min(opponent.allocation.guard, remaining_trade)
        remaining_trade -= smuggled_trade
        confiscated_trade = min(
            smuggled_trade,
            opponent.guard_captains * Rules.GUARD_CAPTAIN_CONFISCATIONS_PER_TURN,
        )
        paid_smuggled_trade = smuggled_trade - confiscated_trade
        smuggle_income = paid_smuggled_trade * Rules.SMUGGLE_INCOME
        confiscated_income = confiscated_trade * Rules.SMUGGLE_INCOME

        normal_income = remaining_trade * Rules.TRADE_INCOME
        trade_bonus = self.calculate_trade_guild_bonus(trader, remaining_trade)
        fishing_income = trader.fishing_income
        trade_income = smuggle_income + normal_income + trade_bonus
        treasure_growth = int(trade_income * Rules.TREASURE_TRADE_PERCENT)

        print(
            f" - {raid_intercepts} trade ship(s) intercepted by raids; "
            f"{opponent.name} steals {stolen_trade_income} gold."
        )
        print(
            f" - {smuggled_trade} trade ship(s) smuggle past guards for "
            f"{smuggle_income} gold."
        )
        if confiscated_income:
            print(
                f" - Guard captains catch {confiscated_trade} smuggler(s); "
                f"{opponent.name} confiscates {confiscated_income} gold."
            )
        print(
            f" - {remaining_trade} trade ship(s) complete trade for "
            f"{normal_income} gold."
        )
        if trade_bonus:
            print(f" - Trade guild bonus adds {trade_bonus} gold.")
        if fishing_income:
            print(
                f" - Fishing boats bring in {fishing_income} domestic gold."
            )
        elif trader.fishing_boats and trader.fishing_dock_disabled:
            print(" - Fishing boats are idle while the docks are disabled.")

        if treasure_growth and not trader.has_treasure_at_sea:
            trader.treasure_value += treasure_growth
            print(f" - Treasure route grows by {treasure_growth} gold.")
        elif treasure_growth:
            print(" - Treasure route does not grow while its convoy is at sea.")

        return ResolutionResult(
            trade_income=trade_income,
            fishing_income=fishing_income,
            stolen_income=stolen_income,
            confiscated_income=confiscated_income,
            treasure_growth=treasure_growth,
        )

    def apply_fort_raid_blocks(self, trader, active_raids):
        if not trader.fort_completed or active_raids <= 0:
            return active_raids

        blocked_raids = min(active_raids, Rules.FORT_RAID_BLOCKS_PER_TURN)
        print(
            f" - Fort guns drive off {blocked_raids} raid ship(s) "
            "from the harbor approaches."
        )
        return active_raids - blocked_raids

    def calculate_trade_guild_bonus(self, trader, completed_trade):
        if not trader.trade_guild_completed or completed_trade <= 0:
            return 0

        return max(1, completed_trade // Rules.TRADE_GUILD_BONUS_STEP)

    def apply_port_labor(self):
        UI.section("PORT LABOR", "blue")
        any_labor = False

        for player in self.players:
            port_labor = self.port_labor.get(player, 0)
            shipyard_labor = player.add_shipyard_labor(port_labor)
            port_labor -= shipyard_labor
            fort_labor = player.add_fort_labor(port_labor)
            port_labor -= fort_labor
            trade_guild_labor = player.add_trade_guild_labor(port_labor)
            port_labor -= trade_guild_labor
            fishing_dock_labor = player.add_fishing_dock_labor(port_labor)

            if shipyard_labor:
                any_labor = True
                print(
                    f"{player.name} applies {shipyard_labor} labor to the shipyard "
                    f"({player.shipyard_labor}/{Rules.SHIPYARD_LABOR_REQUIRED})."
                )
                if player.shipyard_completed:
                    print(
                        f"{player.name}'s shipyard is complete. "
                        f"Ships now cost {player.ship_cost} gold."
                    )

            if fort_labor:
                any_labor = True
                print(
                    f"{player.name} applies {fort_labor} labor to the fort "
                    f"({player.fort_labor}/{Rules.FORT_LABOR_REQUIRED})."
                )
                if player.fort_completed:
                    print(f"{player.name}'s fort is complete.")

            if trade_guild_labor:
                any_labor = True
                print(
                    f"{player.name} applies {trade_guild_labor} labor to the "
                    f"trade guild ({player.trade_guild_labor}/"
                    f"{Rules.TRADE_GUILD_LABOR_REQUIRED})."
                )
                if player.trade_guild_completed:
                    print(f"{player.name}'s trade guild is complete.")

            if fishing_dock_labor:
                any_labor = True
                print(
                    f"{player.name} applies {fishing_dock_labor} labor to the "
                    f"fishing docks ({player.fishing_dock_labor}/"
                    f"{Rules.FISHING_DOCK_LABOR_REQUIRED})."
                )
                if player.fishing_dock_built:
                    print(
                        f"{player.name}'s fishing docks are complete. "
                        "Fishing boats can now be bought."
                    )

            if not shipyard_labor and player.shipyard_started and not player.shipyard_completed:
                print(f"{player.name} has no idle ships to work on the shipyard.")

            if not fort_labor and player.fort_started and not player.fort_completed:
                print(f"{player.name} has no idle ships to work on the fort.")

            if (
                not trade_guild_labor
                and player.trade_guild_started
                and not player.trade_guild_completed
            ):
                print(f"{player.name} has no idle ships to work on the trade guild.")

            if (
                not fishing_dock_labor
                and player.fishing_dock_started
                and not player.fishing_dock_built
            ):
                print(f"{player.name} has no idle ships to work on the fishing docks.")

        if not any_labor:
            print("No port labor is applied this turn.")

    def advance_convoys(self):
        UI.section("CONVOY ARRIVALS", "yellow")
        any_convoys = False

        for player in self.players:
            if player.has_treasure_at_sea:
                any_convoys = True
                player.treasure_turns_remaining -= 1
                if player.treasure_turns_remaining == 0:
                    payout = player.complete_treasure()
                    print(f"{player.name}'s treasure convoy arrives for {payout} gold.")
                else:
                    print(
                        f"{player.name}'s treasure convoy is "
                        f"{player.treasure_turns_remaining} turn(s) from port."
                    )

            if player.has_payroll_at_sea:
                any_convoys = True
                player.payroll_turns_remaining -= 1
                if player.payroll_turns_remaining == 0:
                    payout = player.complete_payroll()
                    print(
                        f"{player.name}'s payroll convoy arrives safely "
                        f"({payout} gold delivered)."
                    )
                else:
                    print(
                        f"{player.name}'s payroll convoy is "
                        f"{player.payroll_turns_remaining} turn(s) from port."
                    )

        if not any_convoys:
            print("No convoys arrive this turn.")

    def buy_phase(self):
        UI.section("BUY PHASE", "green")
        for player in self.players:
            self.run_buy_menu(player)

        self.show_state()

    def run_buy_menu(self, player):
        self.auto_launch_final_payroll(player)

        while True:
            self.show_player_economy(player)
            actions = self.buy_menu_actions(player)
            UI.subheading(f"{player.name}, choose a buy-phase action.", "green")
            for choice, label, _action, disabled_reason in actions:
                if disabled_reason:
                    print(
                        UI.muted(
                            f"{choice}. {label:<24} - {disabled_reason}"
                        )
                    )
                else:
                    print(
                        f"{UI.paint(choice + '.', 'green', bold=True)} "
                        f"{label}"
                    )
            print(f"{UI.paint('0.', 'green', bold=True)} Done")

            raw_choice = input(f"{player.name}, action: ").strip()
            if raw_choice == "0":
                print(f"{player.name} finishes the buy phase.")
                return

            selected_action = None
            for choice, _label, action, disabled_reason in actions:
                if raw_choice == choice:
                    selected_action = (action, disabled_reason)
                    break

            if selected_action is None:
                print(UI.warning("Please choose a listed number."))
                continue

            action, disabled_reason = selected_action
            if disabled_reason:
                print(UI.warning(f"That action is unavailable: {disabled_reason}."))
                continue

            action(player)

    def buy_menu_actions(self, player):
        return [
            ("1", "Buy ships", self.buy_ships_action, self.buy_ships_disabled_reason(player)),
            (
                "2",
                "Start shipyard",
                self.start_shipyard_action,
                self.shipyard_disabled_reason(player),
            ),
            ("3", "Start fort", self.start_fort_action, self.fort_disabled_reason(player)),
            (
                "4",
                "Start trade guild",
                self.start_trade_guild_action,
                self.trade_guild_disabled_reason(player),
            ),
            (
                "5",
                "Build/repair fishing docks",
                self.fishing_dock_action,
                self.fishing_dock_disabled_reason(player),
            ),
            (
                "6",
                "Buy fishing boats",
                self.buy_fishing_boats_action,
                self.buy_fishing_boats_disabled_reason(player),
            ),
            (
                "7",
                "Hire guard captain",
                self.hire_guard_captain_action,
                self.guard_captain_disabled_reason(player),
            ),
            (
                "8",
                "Buy fire ship plans",
                self.buy_fire_ship_plans_action,
                self.fire_ship_plans_disabled_reason(player),
            ),
            (
                "9",
                "Launch treasure convoy",
                self.launch_treasure_action,
                self.treasure_launch_disabled_reason(player),
            ),
            (
                "10",
                "Launch payroll convoy",
                self.launch_payroll_action,
                self.payroll_launch_disabled_reason(player),
            ),
        ]

    def buy_ships_disabled_reason(self, player):
        if player.gold < player.ship_cost:
            return f"too expensive ({player.ship_cost} gold needed)"
        return None

    def shipyard_disabled_reason(self, player):
        if player.shipyard_completed:
            return "already completed"
        if player.shipyard_started:
            return "already started"
        if player.gold < Rules.SHIPYARD_COST:
            return f"too expensive ({Rules.SHIPYARD_COST} gold needed)"
        return None

    def fort_disabled_reason(self, player):
        if player.fort_completed:
            return "already completed"
        if player.fort_started:
            return "already started"
        if player.gold < Rules.FORT_COST:
            return f"too expensive ({Rules.FORT_COST} gold needed)"
        return None

    def trade_guild_disabled_reason(self, player):
        if player.trade_guild_completed:
            return "already completed"
        if player.trade_guild_started:
            return "already started"
        if player.gold < Rules.TRADE_GUILD_COST:
            return f"too expensive ({Rules.TRADE_GUILD_COST} gold needed)"
        return None

    def fire_ship_plans_disabled_reason(self, player):
        if player.fire_ships_unlocked:
            return "already unlocked"
        if player.gold < Rules.FIRE_SHIP_UPGRADE_COST:
            return f"too expensive ({Rules.FIRE_SHIP_UPGRADE_COST} gold needed)"
        return None

    def guard_captain_disabled_reason(self, player):
        if player.guard_captains >= Rules.GUARD_CAPTAIN_MAX:
            return "maximum hired"
        if player.gold < Rules.GUARD_CAPTAIN_COST:
            return f"too expensive ({Rules.GUARD_CAPTAIN_COST} gold needed)"
        return None

    def fishing_dock_disabled_reason(self, player):
        if player.fishing_dock_built and not player.fishing_dock_disabled:
            return "already active"
        if player.fishing_dock_started and not player.fishing_dock_built:
            return "already under construction"
        if player.gold < Rules.FISHING_DOCK_COST:
            return f"too expensive ({Rules.FISHING_DOCK_COST} gold needed)"
        return None

    def buy_fishing_boats_disabled_reason(self, player):
        if not player.fishing_dock_built:
            return "requires fishing docks"
        if player.fishing_dock_disabled:
            return "repair fishing docks first"
        if player.gold < Rules.FISHING_BOAT_COST:
            return f"too expensive ({Rules.FISHING_BOAT_COST} gold needed)"
        return None

    def treasure_launch_disabled_reason(self, player):
        if player.has_treasure_at_sea:
            return "convoy already at sea"

        latest_launch_turn = Rules.MAX_TURNS - Rules.TREASURE_TRAVEL_TURNS
        if self.turn > latest_launch_turn:
            return "too late"

        return None

    def payroll_launch_disabled_reason(self, player):
        if player.payroll_launched:
            return "already launched"

        if self.turn < Rules.PAYROLL_START_TURN:
            return "too early"

        if self.turn >= Rules.PAYROLL_FINAL_TURN:
            return "launches automatically this month"

        return None

    def buy_ships_action(self, player):
        affordable = player.gold // player.ship_cost

        while True:
            amount = self.prompt_non_negative_int(
                f"{player.name}, buy ships for {player.ship_cost} gold each "
                f"(affordable: {affordable}): "
            )

            if amount <= affordable:
                player.buy_ships(amount)
                if amount:
                    print(UI.success(f"{player.name} buys {amount} ship(s)."))
                else:
                    print(f"{player.name} buys no ships.")
                return

            print(UI.warning(f"{player.name} can only afford {affordable} ship(s)."))

    def start_shipyard_action(self, player):
        player.start_shipyard()
        print(UI.success(
            f"{player.name} starts a shipyard. Idle ships will add labor "
            f"on future turns."
        ))

    def start_fort_action(self, player):
        player.start_fort()
        print(UI.success(
            f"{player.name} starts a fort. Idle ships will add labor "
            f"on future turns."
        ))

    def start_trade_guild_action(self, player):
        player.start_trade_guild()
        print(UI.success(
            f"{player.name} starts a trade guild. Idle ships will add labor "
            f"on future turns."
        ))

    def buy_fire_ship_plans_action(self, player):
        player.unlock_fire_ships()
        print(UI.success(f"{player.name} can assign fire ships starting next turn."))

    def hire_guard_captain_action(self, player):
        player.hire_guard_captain()
        print(UI.success(
            f"{player.name} hires a guard captain "
            f"({player.guard_captains}/{Rules.GUARD_CAPTAIN_MAX})."
        ))

    def fishing_dock_action(self, player):
        was_disabled = player.fishing_dock_disabled
        player.build_or_repair_fishing_dock()
        if was_disabled:
            print(UI.success(f"{player.name} repairs the fishing docks."))
        else:
            print(UI.success(
                f"{player.name} starts fishing docks. Idle ships will add labor "
                "on future turns."
            ))

    def buy_fishing_boats_action(self, player):
        affordable = self.affordable_fishing_boats(player)

        while True:
            amount = self.prompt_non_negative_int(
                f"{player.name}, buy fishing boats for "
                f"{Rules.FISHING_BOAT_COST} gold each "
                f"(affordable: {affordable}): "
            )

            if amount <= affordable:
                self.buy_fishing_boats(player, amount)
                if amount:
                    print(UI.success(
                        f"{player.name} buys {amount} fishing boat(s)."
                    ))
                else:
                    print(f"{player.name} buys no fishing boats.")
                return

            print(UI.warning(
                f"{player.name} can only afford {affordable} fishing boat(s)."
            ))

    def affordable_fishing_boats(self, player, gold_budget=None):
        if gold_budget is None:
            gold_budget = player.gold
        return max(0, gold_budget // Rules.FISHING_BOAT_COST)

    def buy_fishing_boats(self, player, amount):
        player.buy_fishing_boats(amount)

    def launch_treasure_action(self, player):
        player.launch_treasure()
        print(UI.success(
            f"{player.name} launches a treasure convoy worth "
            f"{player.treasure_value} gold."
        ))

    def auto_launch_final_payroll(self, player):
        if player.payroll_launched or self.turn < Rules.PAYROLL_FINAL_TURN:
            return

        cost = player.launch_payroll()
        print(UI.warning(
            f"{player.name}'s payroll convoy launches automatically "
            f"with {player.payroll_value} gold after paying {cost} gold."
        ))

    def launch_payroll_action(self, player):
        cost = player.launch_payroll()
        print(UI.success(
            f"{player.name} launches payroll convoy with "
            f"{player.payroll_value} gold after paying {cost} gold."
        ))

    def prompt_yes_no(self, prompt):
        raw_value = input(prompt).strip().lower()
        return raw_value in {"y", "yes"}

    def show_final_scores(self):
        UI.section("FINAL SCORES", "yellow")
        for player in self.players:
            print(
                f"{UI.paint(player.name, 'magenta', bold=True)}: "
                f"{player.gold} gold + "
                f"{player.ships} ships ({player.ship_value} value) + "
                f"shipyard ({player.shipyard_value} value) + "
                f"fort ({player.fort_value} value) + "
                f"trade guild ({player.trade_guild_value} value) + "
                f"fishing ({player.fishing_dock_value + player.fishing_boat_value} value) + "
                f"guard captains ({player.guard_captains}) = "
                f"{UI.paint(str(player.asset_score), 'yellow', bold=True)} total assets"
            )

        player_one, player_two = self.players
        if self.port_destroyer is not None:
            print(
                UI.success(
                    f"\n{self.port_destroyer.name} wins by destroying "
                    f"{self.port_destroyed.name}'s home port!"
                )
            )
            return

        if player_one.asset_score > player_two.asset_score:
            print(UI.success(f"\n{player_one.name} wins!"))
        elif player_two.asset_score > player_one.asset_score:
            print(UI.success(f"\n{player_two.name} wins!"))
        else:
            print(UI.warning("\nThe game ends in a draw."))


def prompt_player_names():
    names = []
    defaults = ["England", "Spain"]

    UI.section("PLAYER SETUP", "magenta")
    print("Enter player names, or press Enter to use the default names.")
    for index, default in enumerate(defaults, start=1):
        name = input(f"Player {index} name [{default}]: ").strip()
        names.append(name or default)

    return names


def prompt_human_name():
    name = input("Your nation name [England]: ").strip()
    return name or "England"


def prompt_ai_strategy(strategy_names):
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


if __name__ == "__main__":
    UI.prepare_terminal()
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
        default="ai_game_log.jsonl",
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
        try:
            Rules.set_max_turns(args.max_turns)
        except ValueError as error:
            parser.error(str(error))

    if args.evaluate_strategy is not None:
        from bot_playtest import evaluate_strategy_file

        evaluate_strategy_file(
            strategy_path=args.evaluate_strategy,
            games_per_opponent=args.eval_games,
            seed=args.seed,
            output_path=args.eval_output,
        )
    elif args.train_evolving is not None:
        from bot_playtest import train_evolving_strategy

        train_evolving_strategy(
            generations=args.train_evolving,
            games_per_bot=args.training_games,
            learning_rate=args.learning_rate,
            mutation_scale=args.mutation_scale,
            seed=args.seed,
            output_path=args.evolved_output,
            history_path=args.training_history,
            graph_path=args.training_graph,
        )
    elif args.ai_log_summary:
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
        game = Game(prompt_player_names())
        game.play()
