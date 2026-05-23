from game_state import Allocation, Nation, ResolutionResult, Rules, UI


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
        self.damaged_raider_cleanup = {}

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
            "raid_fatigue_status": player.raid_fatigue_status,
            "dry_dock_status": player.dry_dock_status,
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
            self.print_status_change(
                "Raid fatigue",
                before,
                after,
                "raid_fatigue_status",
            )
            self.print_status_change("Dry dock", before, after, "dry_dock_status")
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
        self.damaged_raider_cleanup = {}
        for player in self.players:
            player.reset_fort_fire_blocks()

        self.port_labor = {
            player: max(0, player.ships - player.allocation.total)
            for player in self.players
        }
        for player in self.players:
            self.apply_raid_fatigue(player)

        self.resolve_fire_ships(attacker=player_one, defender=player_two)
        self.resolve_fire_ships(attacker=player_two, defender=player_one)
        self.prepare_damaged_raider_cleanup(raider=player_one, guarder=player_two)
        self.prepare_damaged_raider_cleanup(raider=player_two, guarder=player_one)
        self.resolve_raid_guard_battle(raider=player_one, guarder=player_two)
        self.resolve_raid_guard_battle(raider=player_two, guarder=player_one)

        if self.resolve_port_destruction(attacker=player_one, defender=player_two):
            return
        if self.resolve_port_destruction(attacker=player_two, defender=player_one):
            return

        result_one = self.resolve_income(trader=player_one, opponent=player_two)
        result_two = self.resolve_income(trader=player_two, opponent=player_one)
        self.resolve_damaged_raider_cleanup(raider=player_one, guarder=player_two)
        self.resolve_damaged_raider_cleanup(raider=player_two, guarder=player_one)

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
        attacker.cap_damaged_ships()
        defender.cap_damaged_ships()

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
                attacker.cap_damaged_ships()
                print(
                    f" - {defender.name}'s fort blocks 1 fire ship "
                    "before it reaches the shipyard."
                )
                print(f" - {attacker.name} loses 1 fire ship.")

        if attacker.allocation.fire > 0 and defender.shipyard_started:
            shipyard_attack = 1
            attacker.allocation.fire -= shipyard_attack
            attacker.ships -= shipyard_attack
            attacker.cap_damaged_ships()
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
            attacker.cap_damaged_ships()
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
        raider.cap_damaged_ships()
        guarder.cap_damaged_ships()
        self.record_damaged_raider_battle_losses(
            raider,
            guarder,
            raider_losses,
            guarder_losses,
        )

        if raider_losses == 0 and guarder_losses == 0:
            print(" - Even light forces disengage. No ships sink or reach trade.")
            return

        if raider_losses:
            print(f" - {raider.name} loses {raider_losses} raid ship(s).")
        if guarder_losses:
            print(f" - {guarder.name} loses {guarder_losses} guard ship(s).")

    def apply_raid_fatigue(self, player):
        damage_added = player.record_raid_actions(player.allocation.raid)
        if damage_added:
            print(
                f"\n{player.name}'s raiders strain their hulls: "
                f"{damage_added} ship(s) become damaged "
                f"({player.damaged_ships} damaged total)."
            )

    def prepare_damaged_raider_cleanup(self, raider, guarder):
        self.damaged_raider_cleanup[(raider, guarder)] = {
            "damaged_raiders": min(raider.damaged_ships, raider.allocation.raid),
            "surviving_guards": guarder.allocation.guard,
        }

    def record_damaged_raider_battle_losses(
        self,
        raider,
        guarder,
        raider_losses,
        guarder_losses,
    ):
        cleanup = self.damaged_raider_cleanup.get((raider, guarder))
        if cleanup is None:
            return

        cleanup["damaged_raiders"] = max(
            0,
            cleanup["damaged_raiders"] - raider_losses,
        )
        cleanup["surviving_guards"] = max(
            0,
            cleanup["surviving_guards"] - guarder_losses,
        )

    def resolve_damaged_raider_cleanup(self, raider, guarder):
        cleanup = self.damaged_raider_cleanup.get((raider, guarder), {})
        damaged_active_raiders = min(
            cleanup.get("damaged_raiders", 0),
            raider.damaged_ships,
        )
        surviving_guards = cleanup.get("surviving_guards", 0)
        losses = min(damaged_active_raiders, surviving_guards)
        if losses <= 0:
            return

        raider.allocation.raid = max(0, raider.allocation.raid - losses)
        raider.ships -= losses
        raider.damaged_ships -= losses
        raider.damaged_raiders_sunk += losses
        print(
            f"\n{guarder.name}'s remaining guards catch damaged raiders: "
            f"{losses} damaged ship(s) from {raider.name} sink."
        )

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
            port_labor -= fishing_dock_labor
            dry_dock_labor = player.add_dry_dock_labor(port_labor)

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

            if dry_dock_labor:
                any_labor = True
                print(
                    f"{player.name} applies {dry_dock_labor} labor to the "
                    f"dry dock ({player.dry_dock_labor}/"
                    f"{Rules.DRY_DOCK_LABOR_REQUIRED})."
                )
                if player.dry_dock_completed:
                    print(
                        f"{player.name}'s dry dock is complete. "
                        "Damaged raiders repair for free."
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

            if (
                not dry_dock_labor
                and player.dry_dock_started
                and not player.dry_dock_completed
            ):
                print(f"{player.name} has no idle ships to work on the dry dock.")

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
                "Repair damaged ships",
                self.repair_damaged_ships_action,
                self.repair_damaged_ships_disabled_reason(player),
            ),
            (
                "10",
                "Start dry dock",
                self.start_dry_dock_action,
                self.dry_dock_disabled_reason(player),
            ),
            (
                "11",
                "Launch treasure convoy",
                self.launch_treasure_action,
                self.treasure_launch_disabled_reason(player),
            ),
            (
                "12",
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

    def repair_damaged_ships_disabled_reason(self, player):
        if player.damaged_ships <= 0:
            return "no damaged ships"
        if player.raid_repair_cost > 0 and player.gold < player.raid_repair_cost:
            return f"too expensive ({player.raid_repair_cost} gold needed)"
        return None

    def dry_dock_disabled_reason(self, player):
        if player.dry_dock_completed:
            return "already completed"
        if player.dry_dock_started:
            return "already started"
        if not player.shipyard_completed:
            return "requires completed shipyard"
        if player.gold < Rules.DRY_DOCK_COST:
            return f"too expensive ({Rules.DRY_DOCK_COST} gold needed)"
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

    def start_dry_dock_action(self, player):
        player.start_dry_dock()
        print(UI.success(
            f"{player.name} starts a dry dock. Idle ships will add labor "
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

    def repair_damaged_ships_action(self, player):
        cost = player.raid_repair_cost
        if cost == 0:
            affordable = player.damaged_ships
        else:
            affordable = min(player.damaged_ships, player.gold // cost)

        while True:
            amount = self.prompt_non_negative_int(
                f"{player.name}, repair damaged ships for {cost} gold each "
                f"(damaged: {player.damaged_ships}, affordable: {affordable}): "
            )

            if amount <= affordable:
                repaired = player.repair_damaged_ships(amount)
                if repaired:
                    print(UI.success(
                        f"{player.name} repairs {repaired} damaged ship(s)."
                    ))
                else:
                    print(f"{player.name} repairs no ships.")
                return

            print(UI.warning(
                f"{player.name} can only repair {affordable} damaged ship(s)."
            ))

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
