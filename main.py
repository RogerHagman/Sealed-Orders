class Rules:
    VERSION = "0.14"
    STARTING_GOLD = 5
    STARTING_SHIPS = 3
    TRADE_INCOME = 2
    SMUGGLE_INCOME = 1
    SHIP_COST = 6
    SHIPYARD_COST = 5
    SHIPYARD_LABOR_REQUIRED = 5
    SHIPYARD_DISCOUNT = 1
    SHIPYARD_ASSET_VALUE = 5
    FIRE_SHIP_UPGRADE_COST = 5
    PORT_ATTACK_SHIPS_REQUIRED = 5
    FORT_COST = 10
    FORT_LABOR_REQUIRED = 10
    FORT_ASSET_VALUE = 10
    FORT_PORT_DEFENSE = 5
    FORT_FIRE_BLOCKS_PER_TURN = 1
    TRADE_GUILD_COST = 8
    TRADE_GUILD_LABOR_REQUIRED = 6
    TRADE_GUILD_ASSET_VALUE = 8
    TRADE_GUILD_BONUS_STEP = 5
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
    PAYROLL_MUTINY_PERCENT = 0.25


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
    def __init__(self, trade_income=0, stolen_income=0, treasure_growth=0):
        self.trade_income = trade_income
        self.stolen_income = stolen_income
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

    def status_report(self):
        print(f"{self.name}: {self.gold} gold, {self.ships} ships")
        print(f"  Treasure route: {self.treasure_value} gold{self.treasure_status}")
        print(f"  Payroll: {self.payroll_status}")
        print(f"  Shipyard: {self.shipyard_status}")
        print(f"  Fort: {self.fort_status}")
        print(f"  Trade guild: {self.trade_guild_status}")
        print(f"  Fire ships: {self.fire_ship_status}")

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
    def asset_score(self):
        return (
            self.gold
            + self.ship_value
            + self.shipyard_value
            + self.fort_value
            + self.trade_guild_value
        )

    @property
    def has_treasure_at_sea(self):
        return self.treasure_turns_remaining > 0

    @property
    def has_payroll_at_sea(self):
        return self.payroll_turns_remaining > 0

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
            return "completed"
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
    def fire_ship_status(self):
        if self.fire_ships_unlocked:
            return "available"
        return f"locked ({Rules.FIRE_SHIP_UPGRADE_COST} gold upgrade)"

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
        self.payroll_value = self.ships * Rules.PAYROLL_VALUE_PER_SHIP
        self.payroll_turns_remaining = Rules.PAYROLL_TRAVEL_TURNS

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
        print(f"\n=== SEALED ORDERS v{Rules.VERSION} ===")
        print("Assign ships to Trade, Raid, Guard, and Fire.")
        print("Highest total assets after 12 months wins: gold + ship value.")
        print("Treasure convoys can be launched for a delayed payout.")
        print("Payroll must launch once between May-August, or it launches in August.")
        print("Idle ships can build a shipyard that lowers future ship costs.")
        print("Fire ships are unlocked with a buy-phase upgrade.")

        while self.turn <= Rules.MAX_TURNS and not self.game_over:
            self.play_turn()
            self.turn += 1

        self.show_final_scores()

    def play_turn(self):
        print(f"\n=== {self.current_month.upper()} ({self.turn}/{Rules.MAX_TURNS}) ===")
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
        print("\nPublic state:")
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
            "fire_ship_status": player.fire_ship_status,
            "allocation": Allocation(
                player.allocation.trade,
                player.allocation.raid,
                player.allocation.guard,
                player.allocation.fire,
            ),
        }

    def show_turn_summary(self, before_snapshot, after_snapshot, orders_snapshot):
        print(f"\n=== END OF {self.current_month.upper()} SUMMARY ===")
        for player in self.players:
            before = before_snapshot[player.name]
            after = after_snapshot[player.name]
            orders = orders_snapshot[player.name]
            print(f"\n{player.name}")
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
            self.print_status_change("Fire ships", before, after, "fire_ship_status")

    def format_delta(self, before, after):
        delta = after - before
        sign = "+" if delta >= 0 else ""
        return f"{before} -> {after} ({sign}{delta})"

    def print_status_change(self, label, before, after, key):
        if before[key] == after[key]:
            return

        print(f"  {label}: {before[key]} -> {after[key]}")

    @property
    def current_month(self):
        return Rules.MONTHS[self.turn - 1]

    def show_player_economy(self, player):
        print(f"\n{player.name}'s economy - {self.current_month}")
        player.status_report()
        print(
            f"  Asset score if game ended now: {player.asset_score} "
            f"(shipyard value: {player.shipyard_value}, "
            f"fort value: {player.fort_value}, "
            f"trade guild value: {player.trade_guild_value})"
        )
        print(
            f"  Trade income: {Rules.TRADE_INCOME} gold, "
            f"smuggle income: {Rules.SMUGGLE_INCOME} gold"
        )
        print(
            f"  Ship cost: {player.ship_cost} gold, "
            f"ship value: {Rules.SHIP_COST} gold"
        )

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
                f"Invalid allocation: assigned {allocation.total} ships, "
                f"but only {player.ships} are available."
            )

    def prompt_non_negative_int(self, prompt):
        while True:
            raw_value = input(prompt).strip()
            try:
                value = int(raw_value)
            except ValueError:
                print("Please enter a whole number.")
                continue

            if value < 0:
                print("Please enter zero or a positive number.")
                continue

            return value

    def clear_between_players(self):
        print("\n" * 40)

    def reveal_orders(self):
        print("\n=== REVEALING SEALED ORDERS ===")
        for player in self.players:
            print(f"{player.name}: {player.allocation}")

    def pause_after_resolution(self):
        input("\nPress Enter to continue to port labor, convoy arrivals, and buy phase...")

    def resolve_orders(self):
        print("\n=== RESOLUTION ===")
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

        player_one_income = result_one.trade_income + result_two.stolen_income
        player_two_income = result_two.trade_income + result_one.stolen_income

        player_one.gold += player_one_income
        player_two.gold += player_two_income

        print(
            f"\n{player_one.name} earns {player_one_income} gold total "
            f"({result_one.trade_income} trade, {result_two.stolen_income} stolen)."
        )
        print(
            f"{player_two.name} earns {player_two_income} gold total "
            f"({result_two.trade_income} trade, {result_one.stolen_income} stolen)."
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

        if attacker.allocation.fire > 0 and defender.shipyard_started:
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

        if burned_guards == 0 and shipyard_attack == 0 and blocked_fire == 0:
            print(" - No guards or shipyard are in position. The fire ships withdraw.")

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

        print(f"\n{trader.name}'s trade and convoys:")

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
        smuggle_income = smuggled_trade * Rules.SMUGGLE_INCOME

        normal_income = remaining_trade * Rules.TRADE_INCOME
        trade_bonus = self.calculate_trade_guild_bonus(trader, remaining_trade)
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
        print(
            f" - {remaining_trade} trade ship(s) complete trade for "
            f"{normal_income} gold."
        )
        if trade_bonus:
            print(f" - Trade guild bonus adds {trade_bonus} gold.")

        if treasure_growth and not trader.has_treasure_at_sea:
            trader.treasure_value += treasure_growth
            print(f" - Treasure route grows by {treasure_growth} gold.")
        elif treasure_growth:
            print(" - Treasure route does not grow while its convoy is at sea.")

        return ResolutionResult(
            trade_income=trade_income,
            stolen_income=stolen_income,
            treasure_growth=treasure_growth,
        )

    def calculate_trade_guild_bonus(self, trader, completed_trade):
        if not trader.trade_guild_completed or completed_trade <= 0:
            return 0

        return max(1, completed_trade // Rules.TRADE_GUILD_BONUS_STEP)

    def apply_port_labor(self):
        print("\n=== PORT LABOR ===")
        any_labor = False

        for player in self.players:
            port_labor = self.port_labor.get(player, 0)
            shipyard_labor = player.add_shipyard_labor(port_labor)
            port_labor -= shipyard_labor
            fort_labor = player.add_fort_labor(port_labor)
            port_labor -= fort_labor
            trade_guild_labor = player.add_trade_guild_labor(port_labor)

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

        if not any_labor:
            print("No port labor is applied this turn.")

    def advance_convoys(self):
        print("\n=== CONVOY ARRIVALS ===")
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
        print("\n=== BUY PHASE ===")
        for player in self.players:
            self.run_buy_menu(player)

        self.show_state()

    def run_buy_menu(self, player):
        self.auto_launch_final_payroll(player)

        while True:
            self.show_player_economy(player)
            actions = self.buy_menu_actions(player)
            print(f"\n{player.name}, choose a buy-phase action.")
            for choice, label, _action, disabled_reason in actions:
                if disabled_reason:
                    print(f"{choice}. {label} - {disabled_reason}")
                else:
                    print(f"{choice}. {label}")
            print("0. Done")

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
                print("Please choose a listed number.")
                continue

            action, disabled_reason = selected_action
            if disabled_reason:
                print(f"That action is unavailable: {disabled_reason}.")
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
                "Buy fire ship plans",
                self.buy_fire_ship_plans_action,
                self.fire_ship_plans_disabled_reason(player),
            ),
            (
                "6",
                "Launch treasure convoy",
                self.launch_treasure_action,
                self.treasure_launch_disabled_reason(player),
            ),
            (
                "7",
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
                    print(f"{player.name} buys {amount} ship(s).")
                else:
                    print(f"{player.name} buys no ships.")
                return

            print(f"{player.name} can only afford {affordable} ship(s).")

    def start_shipyard_action(self, player):
        player.start_shipyard()
        print(
            f"{player.name} starts a shipyard. Idle ships will add labor "
            f"on future turns."
        )

    def start_fort_action(self, player):
        player.start_fort()
        print(
            f"{player.name} starts a fort. Idle ships will add labor "
            f"on future turns."
        )

    def start_trade_guild_action(self, player):
        player.start_trade_guild()
        print(
            f"{player.name} starts a trade guild. Idle ships will add labor "
            f"on future turns."
        )

    def buy_fire_ship_plans_action(self, player):
        player.unlock_fire_ships()
        print(f"{player.name} can assign fire ships starting next turn.")

    def launch_treasure_action(self, player):
        player.launch_treasure()
        print(
            f"{player.name} launches a treasure convoy worth "
            f"{player.treasure_value} gold."
        )

    def auto_launch_final_payroll(self, player):
        if player.payroll_launched or self.turn < Rules.PAYROLL_FINAL_TURN:
            return

        player.launch_payroll()
        print(
            f"{player.name}'s payroll convoy launches automatically "
            f"with {player.payroll_value} gold."
        )

    def launch_payroll_action(self, player):
        player.launch_payroll()
        print(
            f"{player.name} launches payroll convoy with "
            f"{player.payroll_value} gold."
        )

    def prompt_yes_no(self, prompt):
        raw_value = input(prompt).strip().lower()
        return raw_value in {"y", "yes"}

    def show_final_scores(self):
        print("\n=== FINAL SCORES ===")
        for player in self.players:
            print(
                f"{player.name}: {player.gold} gold + "
                f"{player.ships} ships ({player.ship_value} value) + "
                f"shipyard ({player.shipyard_value} value) + "
                f"fort ({player.fort_value} value) + "
                f"trade guild ({player.trade_guild_value} value) = "
                f"{player.asset_score} total assets"
            )

        player_one, player_two = self.players
        if self.port_destroyer is not None:
            print(
                f"\n{self.port_destroyer.name} wins by destroying "
                f"{self.port_destroyed.name}'s home port!"
            )
            return

        if player_one.asset_score > player_two.asset_score:
            print(f"\n{player_one.name} wins!")
        elif player_two.asset_score > player_one.asset_score:
            print(f"\n{player_two.name} wins!")
        else:
            print("\nThe game ends in a draw.")


def prompt_player_names():
    names = []
    defaults = ["England", "Spain"]

    print("Enter player names, or press Enter to use the default names.")
    for index, default in enumerate(defaults, start=1):
        name = input(f"Player {index} name [{default}]: ").strip()
        names.append(name or default)

    return names


if __name__ == "__main__":
    game = Game(prompt_player_names())
    game.play()
