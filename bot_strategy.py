# bot_strategy.py


# Imports
import json
from pathlib import Path

from game_state import Allocation, Rules

# Constants
BOT_WEIGHT_FIELDS = [
    "trade_weight",
    "raid_weight",
    "guard_weight",
    "fire_weight",
    "convoy_bias",
    "ship_bias",
    "shipyard_bias",
    "fort_bias",
    "trade_guild_bias",
    "administrator_bias",
    "guard_captain_bias",
    "fire_plans_bias",
    "fishing_dock_bias",
    "fishing_boat_bias",
    "dockhouse_bias",
    "dockhand_bias",
    "dockhand_repair_bias",
    "dockhand_boatwright_bias",
    "dry_dock_bias",
    "admiralty_bias",
    "admiral_bias",
    "overtime_bias",
    "repair_bias",
    "construction_idle_bias",
]
# The build priority list defines the order in which the bot will consider purchasing projects during the buy phase.
BUILD_PROJECTS = [
    "shipyard",
    "fort",
    "trade_guild",
    "administrator",
    "fishing_dock",
    "fishing_boat",
    "dockhouse",
    "dockhand",
    "guard_captain",
    "fire_plans",
    "dry_dock",
    "admiralty",
    "admiral",
    "overtime",
]

# Strategy parameters and constants
MIN_FLEET_FOR_PROJECTS = 3 
MIN_FLEET_FOR_CONVOYS = 2 
REBUILD_FLEET_TARGET = 4
MIDGAME_START_TURN = 4
PRIORITY_PROJECT_MIN_BIAS = 0.65
TREASURE_CONVOY_MIN_BIAS = 0.25
TREASURE_CONVOY_MIN_FLEET = 3
TREASURE_CONVOY_CORE_TURNS = 6
MATCHUP_FLOOR_WIN_RATE = 0.50
DOMINANCE_CAP_PER_GAME = 60
MATCHUP_FLOOR_PENALTY = 2600
MATCHUP_FLOOR_RECOVERY_BONUS = 25000
ROBUSTNESS_ALLOWED_REGRESSION = 0.07 
ROBUSTNESS_REGRESSION_PREMIUM = 5000
ROBUSTNESS_CATASTROPHIC_REGRESSION = 0.15
PORT_LOSS_PRESSURE_PENALTY = 320
SURVIVAL_SHIPYARD_BONUS = 25
SURVIVAL_FORT_BONUS = 40
SURVIVAL_TRADE_GUILD_BONUS = 25
SURVIVAL_DRY_DOCK_BONUS = 12
SURVIVAL_ADMIRALTY_BONUS = 50
SURVIVAL_ADMIRAL_BONUS = 25
ADMIRALTY_ABANDONED_PENALTY = 120
ADMIRAL_OPEN_SLOT_PENALTY = 60
SURVIVAL_GUARD_CAPTAIN_BONUS = 8
SUSTAIN_REPAIR_BONUS = 5
SUPPLY_HEALTH_BONUS = 36
SUPPLY_CRISIS_PENALTY = 180
SUPPLY_DESERTION_PENALTY = 220
SUPPLY_UNREST_BURN_PENALTY = 280
SUPPLY_FISHING_LOSS_PENALTY = 20
SUPPLY_SURPLUS_BONUS = 4


class BotStrategy:
    """
    A class representing a bot's strategy in the game, including parameters such as trade_weight, raid_weight, guard_weight, fire_weight, build_priority, and various biases that influence the bot's decision-making during the game. Some strategies also include an opening_book that defines specific actions for the early turns of the game.
    
    Attributes:
    
    name (str): The name of the bot strategy.
        trade_weight (float): The weight for allocating ships to trade.
        raid_weight (float): The weight for allocating ships to raid.
        guard_weight (float): The weight for allocating ships to guard.
        fire_weight (float): The weight for allocating ships to fire.
        build_priority (list): The priority list for building projects.
        convoy_bias (float): The bias for using convoys in the strategy.
        ship_bias (float): The bias for purchasing ships in the strategy.
        shipyard_bias (float): The bias for purchasing the shipyard project.
        fort_bias (float): The bias for purchasing the fort project.
        trade_guild_bias (float): The bias for purchasing the trade guild project.
        administrator_bias (float): The bias for purchasing the administrator project.
        guard_captain_bias (float): The bias for purchasing the guard captain project.
        fire_plans_bias (float): The bias for purchasing the fire ship plans project.
        fishing_dock_bias (float): The bias for purchasing the fishing dock project.
        fishing_boat_bias (float): The bias for purchasing the fishing boat project.
        dockhouse_bias (float): The bias for purchasing the dockhouse project.
        dockhand_bias (float): The bias for purchasing the dockhand project.
        dockhand_repair_bias (float): The bias for using dockhands for repairs.
        dockhand_boatwright_bias (float): The bias for using dockhands for boatwright duties.
        dry_dock_bias (float): The bias for purchasing the dry dock project.
        admiralty_bias (float): The bias for purchasing the admiralty project.
        admiral_bias (float): The bias for purchasing the admiral project.
        overtime_bias (float): The bias for using admiralty overtime.
        repair_bias (float): The bias for repairing damaged ships.
        construction_idle_bias (float): The bias for leaving ships idle for construction.
        opening_book (list): A list of opening strategies that define specific actions for the early turns of the game.
        adaptive (bool): Whether the strategy should adapt based on observations during the game.
        adaptation_strength (float): The strength of the adaptation when the strategy is adaptive.
        adaptation_turns (int): The number of turns to consider for adaptation when the strategy is adaptive.
        observations (dict): A dictionary to store observations about the opponent's behavior during the game, which can be used for adaptive strategies.

        Methods:
        __init__: Initializes the BotStrategy with the specified parameters and biases.
        default_project_bias: A helper method to determine the default bias for a project based on whether it is included in the build priority.
        project_buy_bias: A method to get the bias for purchasing a specific project, taking into account whether it is in the build priority.
        choose_allocation: A method to choose how to allocate ships for the current turn based on the strategy's weights and the current game state.
        run_buy_phase: A method to execute the buy phase for the bot, making decisions on which projects to purchase and whether to launch treasure or payroll based on the strategy's parameters and the current game state.
        opening_turn: A method to determine if there is a specific opening strategy to follow for the current turn based on the opening book.
        choose_opening: A method to choose an opening strategy from the opening book, potentially considering the opponent's behavior.
        weighted_opening_choice: A helper method to choose an opening strategy from a list of openings based on their weights.
        is_ultra_aggro_opponent: A method to determine if the opponent is playing an ultra-aggressive strategy based on their early game behavior.
        is_legal_opening_allocation: A method to check if a proposed allocation of ships for an opening strategy is legal given the current game state.
        run_opening_buy_phase: A method to execute the buy phase actions defined in an opening strategy if applicable.
        run_opening_buy_action: A method to execute a specific buy action defined in an opening strategy.
            choose_dockhand_duty: A method to decide how to assign dockhands for the current turn.
            repair_damaged_raiders: A method to decide whether to use dockhands to repair damaged raiders.
            rebuild_fleet: A method to decide whether to use dockhands to rebuild the fleet if it has been heavily damaged.
            evaluate_position: A method to evaluate the current position in the game based on various factors such as fleet size, supply, and opponent's behavior.
            adjust_weights_for_position: A method to adjust the strategy's weights for allocating ships based on the evaluated position in the game.
            adjust_weights_for_observations: A method to adjust the strategy's weights based on observations of the opponent's behavior during the game.
        weighted_choice: A helper method to make a weighted random choice among the allocation options based on the strategy's weights.
            convoy_escort_guards: A method to determine how many guards to allocate for convoy escort based on the current game state and strategy parameters.
            should_consider_fire: A method to determine whether the bot should consider allocating ships to fire based on the current game state and strategy parameters.
            should_launch_payroll: A method to determine whether the bot should launch payroll based on the current game state and strategy parameters.
            should_launch_treasure: A method to determine whether the bot should launch treasure based on the current game state and strategy parameters.
        """
    def __init__(
        self,
        name,
        trade_weight,
        raid_weight,
        guard_weight,
        fire_weight,
        build_priority,
        convoy_bias,
        ship_bias,
        shipyard_bias=None,
        fort_bias=None,
        trade_guild_bias=None,
        administrator_bias=None,
        guard_captain_bias=None,
        fire_plans_bias=None,
        fishing_dock_bias=None,
        fishing_boat_bias=None,
        dockhouse_bias=None,
        dockhand_bias=None,
        dockhand_repair_bias=None,
        dockhand_boatwright_bias=None,
        dry_dock_bias=None,
        admiralty_bias=None,
        admiral_bias=None,
        overtime_bias=None,
        repair_bias=0.5,
        construction_idle_bias=0.0,
        opening_book=None,
        adaptive=False,
        adaptation_strength=0.0,
        adaptation_turns=3,
    ):
        self.name = name
        self.trade_weight = trade_weight
        self.raid_weight = raid_weight
        self.guard_weight = guard_weight
        self.fire_weight = fire_weight
        self.build_priority = build_priority
        self.convoy_bias = convoy_bias
        self.ship_bias = ship_bias
        self.shipyard_bias = self.default_project_bias("shipyard", shipyard_bias)
        self.fort_bias = self.default_project_bias("fort", fort_bias)
        self.trade_guild_bias = self.default_project_bias(
            "trade_guild",
            trade_guild_bias,
        )
        self.administrator_bias = self.default_project_bias(
            "administrator",
            administrator_bias,
        )
        self.guard_captain_bias = self.default_project_bias(
            "guard_captain",
            guard_captain_bias,
        )
        self.fire_plans_bias = self.default_project_bias("fire_plans", fire_plans_bias)
        self.fishing_dock_bias = self.default_project_bias(
            "fishing_dock",
            fishing_dock_bias,
        )
        self.fishing_boat_bias = self.default_project_bias(
            "fishing_boat",
            fishing_boat_bias,
        )
        self.dockhouse_bias = self.default_project_bias("dockhouse", dockhouse_bias)
        self.dockhand_bias = self.default_project_bias("dockhand", dockhand_bias)
        self.dockhand_repair_bias = (
            dockhand_repair_bias if dockhand_repair_bias is not None else 0.5
        )
        self.dockhand_boatwright_bias = (
            dockhand_boatwright_bias if dockhand_boatwright_bias is not None else 0.5
        )
        self.dry_dock_bias = self.default_project_bias("dry_dock", dry_dock_bias)
        self.admiralty_bias = self.default_project_bias("admiralty", admiralty_bias)
        self.admiral_bias = self.default_project_bias("admiral", admiral_bias)
        self.overtime_bias = self.default_project_bias("overtime", overtime_bias)
        self.repair_bias = repair_bias
        self.construction_idle_bias = construction_idle_bias
        self.opening_book = opening_book or []
        self.opening_choices = {}
        self.adaptive = adaptive
        self.adaptation_strength = adaptation_strength
        self.adaptation_turns = adaptation_turns
        self.observations = {}

    def default_project_bias(self, project, explicit_bias):
        if explicit_bias is not None:
            return explicit_bias
        if project in self.build_priority:
            return 1.0
        return 0.0

    def project_buy_bias(self, project):
        bias = getattr(self, f"{project}_bias")
        if project in self.build_priority:
            return max(bias, PRIORITY_PROJECT_MIN_BIAS)
        return bias

    def choose_allocation(self, game, player, opponent, rng):
        ships = player.ships
        if ships <= 0:
            return Allocation()

        opening_turn = self.opening_turn(game, player, rng)
        if opening_turn is not None:
            allocation = opening_turn.get("allocation")
            if allocation is not None and self.is_legal_opening_allocation(
                allocation,
                player,
            ):
                return Allocation(
                    trade=allocation.trade,
                    raid=allocation.raid,
                    guard=allocation.guard,
                    fire=allocation.fire,
                )

        position = self.evaluate_position(game, player, opponent)
        idle_ships = self.choose_idle_construction_labor(player, ships, position)
        ships -= idle_ships

        can_use_fire = self.should_consider_fire(player, opponent)
        weights = {
            "trade": self.trade_weight,
            "raid": self.raid_weight,
            "guard": self.guard_weight,
            "fire": self.fire_weight if can_use_fire else 0,
        }

        if player.ships <= 2:
            weights["guard"] += 1.5
            weights["fire"] = 0
        if opponent.has_treasure_at_sea:
            weights["raid"] += 2.5
        if opponent.has_payroll_at_sea:
            weights["raid"] += 2.0
        if player.has_treasure_at_sea:
            weights["guard"] += 3.5
            weights["trade"] *= 0.65
            weights["raid"] *= 0.65
        if player.has_payroll_at_sea:
            weights["guard"] += 4.0
            weights["trade"] *= 0.55
            weights["raid"] *= 0.55
        if player.supply < 0 or player.ships >= 8:
            supply_need = max(1, player.supply_need)
            weights["trade"] += min(2.5, supply_need * 0.35)
            weights["raid"] += min(1.5, supply_need * 0.2)
        if player.supply <= -3:
            weights["trade"] += 2.0
            weights["raid"] += 1.0
        if player.supply >= 4:
            weights["trade"] += 1.5
        if opponent.ships <= Rules.PORT_ATTACK_SHIPS_REQUIRED:
            weights["raid"] += 1.5
        if opponent.shipyard_started:
            weights["fire"] += 1.5
        self.adjust_weights_for_position(weights, position)
        self.adjust_weights_for_observations(weights, game, player, opponent)
        if not can_use_fire:
            weights["fire"] = 0

        allocation = {"trade": 0, "raid": 0, "guard": 0, "fire": 0}
        escort_guards = self.convoy_escort_guards(player, opponent, ships)
        allocation["guard"] = escort_guards
        ships -= escort_guards
        for _ in range(ships):
            choice = self.weighted_choice(weights, rng)
            allocation[choice] += 1

        return Allocation(
            trade=allocation["trade"],
            raid=allocation["raid"],
            guard=allocation["guard"],
            fire=allocation["fire"],
        )

    def run_buy_phase(self, game, player, opponent, rng):
        """
        Executes the buy phase for the bot, making decisions on which projects to purchase and whether to 
        launch treasure or payroll based on the strategy's parameters and the current game state. 
        This method considers the bot's opening book for early turns, repairs damaged raiders, 
        rebuilds the fleet if heavily damaged, evaluates the current position in the game, 
        and makes purchasing decisions for projects and ships based on the evaluated position and strategy biases. 
        It also decides whether to launch payroll or treasure based on the current game state and strategy parameters.
        
        Args:
            game: The current game state object, which provides information about the players, their resources, and the game status.
            player: The bot's player object, which contains information about the bot's current resources, fleet, and projects.
            opponent: The opponent player object, which contains information about the opponent's current resources, fleet, and projects.
            rng: A random number generator object used for making randomized decisions based on the strategy's biases.
            Returns:
                None: This method performs actions that affect the game state but does not return any value.
        """
        game.auto_launch_final_payroll(player)
        self.choose_dockhand_duty(game, player, opponent, rng)
        player.refresh_dockhand_repair_discount()

        if self.run_opening_buy_phase(game, player, opponent, rng):
            return

        self.repair_damaged_raiders(player, rng)
        self.rebuild_fleet(player, rng)
        position = self.evaluate_position(game, player, opponent)
        for project in self.buy_project_order():
            if not self.can_spend_on_project(player, project):
                continue
            if not self.should_spend_on_project(project, position):
                continue
            if project == "shipyard" and game.shipyard_disabled_reason(player) is None:
                if rng.random() < self.project_buy_bias("shipyard"):
                    player.start_shipyard()
            elif project == "fort" and game.fort_disabled_reason(player) is None:
                if rng.random() < self.project_buy_bias("fort"):
                    player.start_fort()
            elif (
                project == "trade_guild"
                and game.trade_guild_disabled_reason(player) is None
            ):
                if rng.random() < self.project_buy_bias("trade_guild"):
                    player.start_trade_guild()
            elif (
                project == "administrator"
                and game.administrator_disabled_reason(player) is None
            ):
                administrator_bias = self.project_buy_bias("administrator")
                if player.supply < 0 or player.ships >= 8:
                    administrator_bias += 0.25
                if rng.random() < min(1.0, administrator_bias):
                    player.hire_administrator()
            elif (
                project == "fire_plans"
                and game.fire_ship_plans_disabled_reason(player) is None
            ):
                if rng.random() < self.project_buy_bias("fire_plans"):
                    player.unlock_fire_ships()
            elif (
                project == "guard_captain"
                and game.guard_captain_disabled_reason(player) is None
            ):
                guard_captain_bias = self.project_buy_bias("guard_captain")
                if player.guard_captains >= Rules.GUARD_CAPTAIN_MAX - 2:
                    guard_captain_bias += 0.2
                if opponent.allocation.trade > 0:
                    guard_captain_bias += 0.1
                if rng.random() < min(1.0, guard_captain_bias):
                    player.hire_guard_captain()
            elif (
                project == "fishing_dock"
                and game.fishing_dock_disabled_reason(player) is None
            ):
                if rng.random() < self.project_buy_bias("fishing_dock"):
                    player.build_or_repair_fishing_dock()
            elif (
                project == "fishing_boat"
                and game.buy_fishing_boats_disabled_reason(player) is None
            ):
                if rng.random() < self.project_buy_bias("fishing_boat"):
                    reserve = self.gold_reserve(game, player, opponent)
                    boat_budget = max(0, player.gold - reserve)
                    affordable = game.affordable_fishing_boats(player, boat_budget)
                    if affordable > 0:
                        game.buy_fishing_boats(player, affordable)
            elif (
                project == "dockhouse"
                and game.dockhouse_disabled_reason(player) is None
            ):
                dockhouse_bias = self.project_buy_bias("dockhouse")
                if player.dockhands and not player.dockhouse_completed:
                    dockhouse_bias = max(dockhouse_bias, 0.9)
                elif self.has_active_construction(player) or player.ships >= 5:
                    dockhouse_bias += 0.15
                if rng.random() < min(1.0, dockhouse_bias):
                    player.start_dockhouse()
            elif (
                project == "dockhand"
                and game.dockhand_disabled_reason(player) is None
            ):
                dockhand_bias = self.project_buy_bias("dockhand")
                if self.has_active_construction(player):
                    dockhand_bias += 0.2
                if player.supply <= -1 or player.payroll_cost >= player.gold + 4:
                    dockhand_bias *= 0.4
                if rng.random() < min(1.0, dockhand_bias):
                    player.hire_dockhand()
            elif (
                project == "dry_dock"
                and game.dry_dock_disabled_reason(player) is None
            ):
                dry_dock_bias = self.project_buy_bias("dry_dock")
                if player.damaged_ships > 0 or self.raid_weight >= 3.0:
                    dry_dock_bias += 0.25
                if rng.random() < min(1.0, dry_dock_bias):
                    player.start_dry_dock()
            elif (
                project == "admiralty"
                and game.admiralty_disabled_reason(player) is None
            ):
                admiralty_bias = self.project_buy_bias("admiralty")
                if player.ships >= Rules.ADMIRAL_SHIPS_PER_SLOT:
                    admiralty_bias += 0.2
                elif player.ships >= MIN_FLEET_FOR_PROJECTS:
                    admiralty_bias += 0.1
                if self.raid_weight >= 3.0 or self.guard_weight >= 3.0:
                    admiralty_bias += 0.2
                if position["under_fleet_pressure"] or player.fort_completed:
                    admiralty_bias += 0.1
                if rng.random() < min(1.0, admiralty_bias):
                    player.start_admiralty()
            elif (
                project == "admiral"
                and game.admiral_disabled_reason(player) is None
            ):
                admiral_bias = self.project_buy_bias("admiral")
                if player.admirals < player.admiral_slots:
                    admiral_bias += 0.2
                if self.raid_weight >= 3.0 or self.guard_weight >= 3.0:
                    admiral_bias += 0.25
                if player.ships >= (player.admirals + 2) * Rules.ADMIRAL_SHIPS_PER_SLOT:
                    admiral_bias += 0.15
                if rng.random() < min(1.0, admiral_bias):
                    player.recruit_admiral()
            elif (
                project == "overtime"
                and game.admiralty_overtime_disabled_reason(player) is None
            ):
                overtime_bias = self.project_buy_bias("overtime")
                if position["under_fleet_pressure"]:
                    overtime_bias += 0.15
                if not player.shipyard_completed:
                    overtime_bias += 0.15
                if rng.random() < min(1.0, overtime_bias):
                    game.apply_best_admiralty_overtime(player)

        if self.should_launch_payroll(game, player, rng):
            player.launch_payroll(game.payroll_year)

        if self.should_launch_treasure(game, player, rng):
            player.launch_treasure()

        reserve = self.gold_reserve(game, player, opponent)
        affordable = max(0, (player.gold - reserve) // player.ship_cost)
        if affordable > 0:
            ship_buy_bias = self.ship_bias
            if position["fleet_gap"] < 0:
                ship_buy_bias += 0.2
            if position["can_threaten_port"]:
                ship_buy_bias += 0.1
            if rng.random() < min(1.0, ship_buy_bias):
                player.buy_ships(affordable)
            elif affordable > 1:
                player.buy_ships(affordable - 1)

    def opening_turn(self, game, player, rng):
        """Determines if there is a specific opening strategy to follow for the current turn based on the opening book.
        The bot will follow the opening book for the first few turns of the game (up to turn 3) 
        to execute specific strategies that are designed for the early game. After turn 3
        or if there is no opening book defined, the bot will return None, 
        indicating that it should use its regular strategy for ship allocation and purchasing decisions.
        Args:
        game: The current game state object, which provides information about the players, their resources, and the game status.
        player: The bot's player object, which contains information about the bot's current resources, fleet, and projects.
        rng: A random number generator object used for making randomized decisions based on the strategy's biases.
        Returns:
        dict or None: A dictionary containing the specific actions to take for the current turn if there is an applicable opening strategy defined in the opening book, or None if there is no specific opening strategy to follow for the current turn.
        """
        if not self.opening_book or game.turn > 3:
            return None

        key = (id(game), id(player))
        if key not in self.opening_choices:
            self.opening_choices[key] = self.choose_opening(game, player, rng)

        opening = self.opening_choices[key]
        return opening.get("turns", {}).get(game.turn)

    def choose_opening(self, game, player, rng):
        opponent = next(other for other in game.players if other is not player)
        if self.is_ultra_aggro_opponent(opponent):
            shield_openings = [
                opening
                for opening in self.opening_book
                if opening.get("anti_aggro")
            ]
            if shield_openings:
                return self.weighted_opening_choice(shield_openings, rng)
        return self.weighted_opening_choice(self.opening_book, rng)

    def weighted_opening_choice(self, openings, rng):
        total_weight = sum(max(0, opening.get("weight", 1)) for opening in openings)
        if total_weight <= 0:
            return rng.choice(openings)

        roll = rng.random() * total_weight
        running = 0
        for opening in openings:
            running += max(0, opening.get("weight", 1))
            if roll <= running:
                return opening
        return openings[-1]

    def is_ultra_aggro_opponent(self, opponent):
        return (
            opponent.ships >= 3
            and not opponent.has_treasure_at_sea
            and not opponent.shipyard_started
        )

    def is_legal_opening_allocation(self, allocation, player):
        if allocation.total > player.ships:
            return False
        if allocation.fire > 0 and not player.fire_ships_unlocked:
            return False
        return True

    def run_opening_buy_phase(self, game, player, opponent, rng):
        opening_turn = self.opening_turn(game, player, rng)
        if opening_turn is None:
            return False

        for action in opening_turn.get("buy_actions", []):
            self.run_opening_buy_action(action, game, player)
        return not opening_turn.get("continue_buy_phase", False)

    def run_opening_buy_action(self, action, game, player):
        if action == "launch_treasure":
            if game.treasure_launch_disabled_reason(player) is None:
                player.launch_treasure()
        elif action == "start_shipyard":
            if game.shipyard_disabled_reason(player) is None:
                player.start_shipyard()
        elif action == "start_fort":
            if game.fort_disabled_reason(player) is None:
                player.start_fort()
        elif action == "start_trade_guild":
            if game.trade_guild_disabled_reason(player) is None:
                player.start_trade_guild()
        elif action == "hire_administrator":
            if game.administrator_disabled_reason(player) is None:
                player.hire_administrator()
        elif action == "hire_guard_captain":
            if game.guard_captain_disabled_reason(player) is None:
                player.hire_guard_captain()
        elif action == "buy_fire_ship_plans":
            if game.fire_ship_plans_disabled_reason(player) is None:
                player.unlock_fire_ships()
        elif action == "build_fishing_dock":
            if game.fishing_dock_disabled_reason(player) is None:
                player.build_or_repair_fishing_dock()
        elif action == "start_dockhouse":
            if game.dockhouse_disabled_reason(player) is None:
                player.start_dockhouse()
        elif action == "hire_dockhand":
            if game.dockhand_disabled_reason(player) is None:
                player.hire_dockhand()
        elif action == "buy_fishing_boats":
            if game.buy_fishing_boats_disabled_reason(player) is None:
                affordable = game.affordable_fishing_boats(player)
                if affordable > 0:
                    game.buy_fishing_boats(player, affordable)
        elif action == "start_dry_dock":
            if game.dry_dock_disabled_reason(player) is None:
                player.start_dry_dock()
        elif action == "start_admiralty":
            if game.admiralty_disabled_reason(player) is None:
                player.start_admiralty()
        elif action == "recruit_admiral":
            if game.admiral_disabled_reason(player) is None:
                player.recruit_admiral()
        elif action == "admiralty_overtime":
            if game.admiralty_overtime_disabled_reason(player) is None:
                game.apply_best_admiralty_overtime(player)
        elif action == "repair_damaged_ships":
            self.repair_all_affordable_damaged_ships(player)
        elif action == "buy_ships":
            affordable = player.gold // player.ship_cost
            if affordable > 0:
                player.buy_ships(affordable)
        elif action == "buy_one_ship":
            if player.gold >= player.ship_cost:
                player.buy_ships(1)
        elif action == "stabilize_first_buy":
            self.stabilize_first_buy(game, player)

    def stabilize_first_buy(self, game, player):
        if player.ships <= 2 and game.buy_ships_disabled_reason(player) is None:
            player.buy_ships(1)
        if game.shipyard_disabled_reason(player) is None:
            player.start_shipyard()
        if game.fishing_dock_disabled_reason(player) is None:
            player.build_or_repair_fishing_dock()
        if game.guard_captain_disabled_reason(player) is None:
            player.hire_guard_captain()

    def repair_damaged_raiders(self, player, rng):
        if player.damaged_ships <= 0:
            return

        damaged_pressure = player.damaged_ships / max(1, player.ships)
        repair_score = self.repair_bias
        if player.raid_repair_cost == 0:
            repair_score = 1.0
        elif player.raid_repair_cost <= Rules.SHIPYARD_RAID_REPAIR_COST:
            repair_score += 0.3
        if damaged_pressure >= 0.25:
            repair_score += 0.3
        if player.ships <= Rules.PORT_ATTACK_SHIPS_REQUIRED:
            repair_score += 0.2

        if rng.random() < min(1.0, repair_score):
            self.repair_all_affordable_damaged_ships(player)

    def choose_dockhand_duty(self, game, player, opponent, rng):
        if not player.dockhouse_completed or not player.dockhands_full_roster:
            player.set_dockhand_duty("construction")
            return

        repair_score = self.dockhand_repair_bias
        if player.damaged_ships > 0 and player.base_raid_repair_cost > 0:
            repair_score += min(0.4, player.damaged_ships * 0.08)
        else:
            repair_score *= 0.25

        boatwright_score = self.dockhand_boatwright_bias
        if player.fishing_dock_built and not player.fishing_dock_disabled:
            boatwright_score += 0.2
        else:
            boatwright_score = 0
        if player.gold < Rules.DOCKHAND_BOATWRIGHT_COST:
            boatwright_score = 0
        if player.supply <= -2:
            boatwright_score *= 0.5

        construction_score = 0.35 + self.construction_idle_bias
        if self.has_active_construction(player):
            construction_score += 0.5
        if player.dockhouse_started and not player.dockhouse_completed:
            construction_score += 0.5

        scores = {
            "construction": max(0, construction_score),
            "repair": max(0, repair_score),
            "boatwright": max(0, boatwright_score),
        }
        player.set_dockhand_duty(self.weighted_choice(scores, rng))

    def repair_all_affordable_damaged_ships(self, player):
        if player.damaged_ships <= 0:
            return 0
        amount = player.affordable_repairs()
        if amount <= 0:
            return 0
        return player.repair_damaged_ships(amount)

    def rebuild_fleet(self, player, rng):
        if player.ships >= MIN_FLEET_FOR_PROJECTS:
            return

        affordable = player.gold // player.ship_cost
        if affordable <= 0:
            return

        needed = max(1, REBUILD_FLEET_TARGET - player.ships)
        if rng.random() < self.ship_bias:
            player.buy_ships(min(affordable, needed))

    def wants_emergency_supply_warchest(
        self,
        player,
        need,
        counted_income,
        covered,
        cost,
    ):
        if player.supply >= 0:
            return False
        if player.gold < cost:
            return False

        shortfall = max(0, need - counted_income)
        pressure = 0.0
        if player.supply <= -1:
            pressure += 0.45
        if player.supply <= -2:
            pressure += 0.25
        if player.supply <= -3:
            pressure += 0.25
        if covered >= shortfall:
            pressure += 0.1
        if player.ships >= 8:
            pressure += 0.1
        if player.has_treasure_at_sea:
            pressure -= 0.15
        if player.gold - cost < player.ship_cost and player.ships <= REBUILD_FLEET_TARGET:
            pressure -= 0.15
        return pressure >= 0.55

    def can_spend_on_project(self, player, project):
        if project == "guard_captain":
            return player.ships >= MIN_FLEET_FOR_CONVOYS
        if project == "fishing_dock":
            return player.ships >= 1
        if project == "fishing_boat":
            return player.fishing_dock_built and not player.fishing_dock_disabled
        if project == "dockhouse":
            return player.ships >= 1 or player.dockhands > 0
        if project == "dockhand":
            return player.dockhouse_completed and player.dockhands < Rules.DOCKHAND_MAX
        if project == "administrator":
            return player.trade_guild_completed and not player.administrator_hired
        if project == "dry_dock":
            return player.shipyard_completed
        if project == "admiralty":
            return player.ships >= MIN_FLEET_FOR_PROJECTS
        if project == "admiral":
            return player.admiralty_completed
        if project == "overtime":
            return player.admiralty_completed and not player.admiralty_overtime_used
        if player.ships < MIN_FLEET_FOR_PROJECTS:
            return False
        if project in {"shipyard", "fort", "trade_guild"}:
            return player.ships > 0
        return True

    def should_launch_payroll(self, game, player, rng):
        if game.payroll_launch_disabled_reason(player) is not None:
            return False
        if player.ships < MIN_FLEET_FOR_CONVOYS:
            return False

        launch_score = self.convoy_bias
        if player.supply < 0 or player.ships >= 8:
            launch_score += 0.2
        if player.ships >= 6:
            launch_score += 0.2
        if game.payroll_cycle_turn >= Rules.PAYROLL_FINAL_TURN - 1:
            launch_score += 0.4
        return rng.random() < launch_score

    def should_launch_treasure(self, game, player, rng):
        if game.treasure_launch_disabled_reason(player) is not None:
            return False
        if player.ships < MIN_FLEET_FOR_CONVOYS:
            return False

        launch_score = self.convoy_bias
        if player.supply < 0 or player.ships >= 8:
            launch_score += 0.25
        if (
            player.ships >= TREASURE_CONVOY_MIN_FLEET
            and game.turn <= TREASURE_CONVOY_CORE_TURNS
        ):
            launch_score = max(launch_score, TREASURE_CONVOY_MIN_BIAS)
        if player.treasure_value >= Rules.TREASURE_BASE_VALUE + 4:
            launch_score += 0.25
        if game.turn >= Rules.MAX_TURNS - Rules.TREASURE_TRAVEL_TURNS - 1:
            launch_score += 0.3
        return rng.random() < launch_score

    def gold_reserve(self, game, player=None, opponent=None):
        if game.turn <= 3 and self.shipyard_bias >= 0.5:
            return 2
        if player is not None and opponent is not None:
            position = self.evaluate_position(game, player, opponent)
            if position["fleet_gap"] < 0 or position["can_threaten_port"]:
                return 0
        return 0

    def buy_project_order(self):
        ordered_projects = self.build_priority[:]
        for project in BUILD_PROJECTS:
            if project not in ordered_projects:
                ordered_projects.append(project)
        return ordered_projects

    def has_active_construction(self, player):
        return any(
            [
                player.shipyard_started and not player.shipyard_completed,
                player.fort_started and not player.fort_completed,
                player.trade_guild_started and not player.trade_guild_completed,
                player.fishing_dock_started and not player.fishing_dock_built,
                player.dockhouse_started and not player.dockhouse_completed,
                player.dry_dock_started and not player.dry_dock_completed,
                player.admiralty_started and not player.admiralty_completed,
            ]
        )

    def choose_idle_construction_labor(self, player, ships, position=None):
        if not self.has_active_construction(player):
            return 0
        admiralty_under_construction = (
            player.admiralty_started and not player.admiralty_completed
        )
        if (
            (player.has_treasure_at_sea or player.has_payroll_at_sea)
            and not admiralty_under_construction
        ):
            return 0

        convoy_at_sea = player.has_treasure_at_sea or player.has_payroll_at_sea
        desired_idle = max(1, int(ships * self.construction_idle_bias + 0.999))
        if admiralty_under_construction:
            remaining_labor = Rules.ADMIRALTY_LABOR_REQUIRED - player.admiralty_labor
            admiralty_workers = 2 if remaining_labor >= 2 and ships >= 5 else 1
            if convoy_at_sea:
                desired_idle = 1 if ships >= 5 else 0
            else:
                desired_idle = max(desired_idle, admiralty_workers)
        if player.ships <= MIN_FLEET_FOR_PROJECTS:
            desired_idle = min(desired_idle, 1)
        if position is not None:
            if position["enemy_port_open"] and player.ships >= Rules.PORT_ATTACK_SHIPS_REQUIRED:
                return 0
            if position["under_fleet_pressure"]:
                desired_idle = min(desired_idle, 1)
            elif position["asset_gap"] >= 10 or position["income_edge"] > 0:
                desired_idle = min(ships, desired_idle + 1)
        if admiralty_under_construction:
            if convoy_at_sea:
                desired_idle = 1 if ships >= 5 and desired_idle > 0 else 0
            else:
                desired_idle = min(desired_idle, 2)
        return min(ships, desired_idle)

    def convoy_escort_guards(self, player, opponent, ships_available):
        if ships_available <= 0:
            return 0
        if not player.has_treasure_at_sea and not player.has_payroll_at_sea:
            return 0

        enemy_raid_capacity = opponent.ships
        if enemy_raid_capacity <= 0:
            return 0

        escort_target = min(enemy_raid_capacity, ships_available)
        if player.has_treasure_at_sea:
            escort_target = min(escort_target, max(2, player.treasure_turns_remaining))
        if player.has_payroll_at_sea:
            escort_target = min(escort_target, max(2, player.payroll_turns_remaining + 1))
        if player.has_treasure_at_sea and player.has_payroll_at_sea:
            escort_target = min(enemy_raid_capacity, ships_available)
        return escort_target

    def evaluate_position(self, game, player, opponent):
        asset_gap = player.asset_score - opponent.asset_score
        fleet_gap = player.ships - opponent.ships
        income_edge = self.economic_engine_score(player) - self.economic_engine_score(opponent)
        enemy_port_open = opponent.ships == 0
        own_port_open = player.ships == 0
        can_threaten_port = (
            enemy_port_open and player.ships >= Rules.PORT_ATTACK_SHIPS_REQUIRED
        )
        under_fleet_pressure = (
            opponent.ships >= player.ships + 2
            or own_port_open
            or (
                player.ships <= Rules.PORT_ATTACK_SHIPS_REQUIRED
                and opponent.ships >= Rules.PORT_ATTACK_SHIPS_REQUIRED
            )
        )

        return {
            "turn": game.turn,
            "asset_gap": asset_gap,
            "fleet_gap": fleet_gap,
            "income_edge": income_edge,
            "enemy_port_open": enemy_port_open,
            "own_port_open": own_port_open,
            "can_threaten_port": can_threaten_port,
            "under_fleet_pressure": under_fleet_pressure,
            "ahead": asset_gap >= 10,
            "behind": asset_gap <= -10,
        }

    def economic_engine_score(self, player):
        score = 0
        if player.shipyard_completed:
            score += 3
        elif player.shipyard_started:
            score += 1
        if player.trade_guild_completed:
            score += 3
        elif player.trade_guild_started:
            score += 1
        if player.fishing_dock_built and not player.fishing_dock_disabled:
            score += 1 + min(3, player.fishing_boats)
        if player.fort_completed:
            score += 2
        elif player.fort_started:
            score += 1
        if player.dry_dock_completed:
            score += 2
        elif player.dry_dock_started:
            score += 1
        if player.admiralty_completed:
            score += 3 + player.admirals
        elif player.admiralty_started:
            score += 1
        if player.dockhouse_completed:
            score += 1 + min(3, player.dockhands)
        elif player.dockhouse_started:
            score += 1
        if player.treasure_value > Rules.TREASURE_BASE_VALUE:
            score += 1
        return score

    def adjust_weights_for_position(self, weights, position):
        if position["turn"] < MIDGAME_START_TURN:
            return

        if position["can_threaten_port"]:
            weights["raid"] += 6.0
            weights["trade"] *= 0.35
            weights["guard"] *= 0.5
            weights["fire"] *= 0.5
            return

        if position["under_fleet_pressure"]:
            weights["guard"] += 2.5
            weights["raid"] *= 0.7
            weights["fire"] *= 0.5

        if position["fleet_gap"] >= 3:
            weights["raid"] += 1.5
        elif position["fleet_gap"] <= -2:
            weights["trade"] += 1.0
            weights["guard"] += 1.0
            weights["raid"] *= 0.75

        if position["ahead"]:
            weights["trade"] += 1.5
            weights["guard"] += 1.0
            weights["raid"] *= 0.8
        elif position["behind"]:
            weights["raid"] += 1.5

        if position["income_edge"] > 0:
            weights["trade"] += 1.0
            weights["guard"] += 0.5
        elif position["income_edge"] < 0:
            weights["raid"] += 0.75

    def observation_key(self, game, player, opponent):
        return (id(game), id(player), id(opponent))

    def observe_opponent_opening(self, game, player, opponent):
        if not self.adaptive:
            return

        observed_turn = game.turn
        if observed_turn < 1 or observed_turn > self.adaptation_turns:
            return

        key = self.observation_key(game, player, opponent)
        observations = self.observations.setdefault(key, {})
        if observed_turn in observations:
            return

        observations[observed_turn] = Allocation(
            trade=opponent.allocation.trade,
            raid=opponent.allocation.raid,
            guard=opponent.allocation.guard,
            fire=opponent.allocation.fire,
        )

    def opponent_opening_profile(self, game, player, opponent):
        observations = self.observations.get(
            self.observation_key(game, player, opponent),
            {},
        )
        profile = {"trade": 0, "raid": 0, "guard": 0, "fire": 0}
        for allocation in observations.values():
            profile["trade"] += allocation.trade
            profile["raid"] += allocation.raid
            profile["guard"] += allocation.guard
            profile["fire"] += allocation.fire
        return profile

    def adjust_weights_for_observations(self, weights, game, player, opponent):
        if not self.adaptive or self.adaptation_strength <= 0:
            return

        profile = self.opponent_opening_profile(game, player, opponent)
        total = sum(profile.values())
        if total <= 0:
            return

        strength = self.adaptation_strength
        trade_share = profile["trade"] / total
        raid_share = profile["raid"] / total
        guard_share = profile["guard"] / total
        fire_share = profile["fire"] / total

        if raid_share >= 0.40:
            weights["guard"] += 2.0 * strength
            weights["trade"] *= max(0.35, 1.0 - 0.35 * strength)
        if trade_share >= 0.45:
            weights["raid"] += 2.0 * strength
            weights["fire"] += 0.4 * strength
            weights["trade"] *= max(0.60, 1.0 - 0.15 * strength)
        if guard_share >= 0.35:
            weights["trade"] += 1.5 * strength
            weights["fire"] += 1.0 * strength
            weights["raid"] *= max(0.40, 1.0 - 0.25 * strength)
        if fire_share >= 0.10:
            weights["guard"] += 1.5 * strength
            weights["fire"] *= max(0.50, 1.0 - 0.20 * strength)

    def clear_game_memory(self, game):
        if not self.adaptive:
            return

        game_id = id(game)
        stale_keys = [key for key in self.observations if key[0] == game_id]
        for key in stale_keys:
            del self.observations[key]

    def should_spend_on_project(self, project, position):
        if position["turn"] < MIDGAME_START_TURN:
            return True
        if position["under_fleet_pressure"] and project not in {
            "shipyard",
            "fort",
            "fishing_dock",
            "dockhouse",
            "dry_dock",
            "administrator",
            "admiralty",
            "admiral",
            "overtime",
        }:
            return False
        if position["fleet_gap"] <= -2 and project not in {
            "shipyard",
            "fishing_dock",
            "dockhouse",
            "dry_dock",
            "administrator",
            "admiralty",
            "admiral",
            "overtime",
        }:
            return False
        if position["can_threaten_port"]:
            return False
        return True

    def should_consider_fire(self, player, opponent):
        if not player.fire_ships_unlocked:
            return False
        if player.ships <= MIN_FLEET_FOR_CONVOYS:
            return False
        return (
            opponent.shipyard_started
            or (
                opponent.fishing_dock_built
                and not opponent.fishing_dock_disabled
                and opponent.fishing_boats > 0
            )
            or opponent.allocation.guard > 0
        )

    def weighted_choice(self, weights, rng):
        total = sum(max(0, weight) for weight in weights.values())
        if total <= 0:
            return "trade"

        roll = rng.random() * total
        running = 0
        for choice, weight in weights.items():
            running += max(0, weight)
            if roll <= running:
                return choice
        return "trade"


def load_strategy(strategy_path):
    strategy_path = Path(strategy_path)
    with strategy_path.open(encoding="utf-8") as strategy_file:
        record = json.load(strategy_file)

    strategy_data = record.get("strategy", record)
    return BotStrategy(
        name=strategy_data.get("name", strategy_path.stem),
        trade_weight=strategy_data["trade_weight"],
        raid_weight=strategy_data["raid_weight"],
        guard_weight=strategy_data["guard_weight"],
        fire_weight=strategy_data["fire_weight"],
        build_priority=strategy_data.get("build_priority", []),
        convoy_bias=strategy_data["convoy_bias"],
        ship_bias=strategy_data["ship_bias"],
        shipyard_bias=strategy_data.get("shipyard_bias"),
        fort_bias=strategy_data.get("fort_bias"),
        trade_guild_bias=strategy_data.get("trade_guild_bias"),
        administrator_bias=strategy_data.get("administrator_bias"),
        guard_captain_bias=strategy_data.get("guard_captain_bias"),
        fire_plans_bias=strategy_data.get("fire_plans_bias"),
        fishing_dock_bias=strategy_data.get("fishing_dock_bias"),
        fishing_boat_bias=strategy_data.get("fishing_boat_bias"),
        dockhouse_bias=strategy_data.get("dockhouse_bias"),
        dockhand_bias=strategy_data.get("dockhand_bias"),
        dockhand_repair_bias=strategy_data.get("dockhand_repair_bias"),
        dockhand_boatwright_bias=strategy_data.get("dockhand_boatwright_bias"),
        dry_dock_bias=strategy_data.get("dry_dock_bias"),
        admiralty_bias=strategy_data.get("admiralty_bias"),
        admiral_bias=strategy_data.get("admiral_bias"),
        overtime_bias=strategy_data.get("overtime_bias"),
        repair_bias=strategy_data.get("repair_bias", 0.5),
        construction_idle_bias=strategy_data.get("construction_idle_bias", 0.0),
        opening_book=load_opening_book(strategy_data.get("opening_book", [])),
        adaptive=strategy_data.get("adaptive", False),
        adaptation_strength=strategy_data.get("adaptation_strength", 0.0),
        adaptation_turns=strategy_data.get("adaptation_turns", 3),
    )


def load_opening_book(opening_book_data):
    opening_book = []
    for opening_data in opening_book_data:
        turns = {}
        for turn, turn_data in opening_data.get("turns", {}).items():
            allocation_data = turn_data.get("allocation")
            allocation = None
            if allocation_data is not None:
                allocation = Allocation(
                    trade=allocation_data.get("trade", 0),
                    raid=allocation_data.get("raid", 0),
                    guard=allocation_data.get("guard", 0),
                    fire=allocation_data.get("fire", 0),
                )
            turns[int(turn)] = {
                "allocation": allocation,
                "buy_actions": turn_data.get("buy_actions", [])[:],
                "continue_buy_phase": turn_data.get("continue_buy_phase", False),
            }
        opening_book.append(
            {
                "name": opening_data.get("name", "opening"),
                "code_id": opening_data.get("code_id", ""),
                "source": opening_data.get("source", "strategy file"),
                "weight": opening_data.get("weight", 1),
                "anti_aggro": opening_data.get("anti_aggro", False),
                "turns": turns,
            }
        )
    return opening_book


def random_evolving_strategy(rng, name="Evolving"):
    build_priority = BUILD_PROJECTS[:]
    rng.shuffle(build_priority)
    build_count = rng.randint(0, len(build_priority))

    return BotStrategy(
        name=name,
        trade_weight=rng.uniform(0.0, 5.0),
        raid_weight=rng.uniform(0.0, 5.0),
        guard_weight=rng.uniform(0.0, 5.0),
        fire_weight=rng.uniform(0.0, 5.0),
        build_priority=build_priority[:build_count],
        convoy_bias=rng.random(),
        ship_bias=rng.random(),
        shipyard_bias=rng.random(),
        fort_bias=rng.random(),
        trade_guild_bias=rng.random(),
        administrator_bias=rng.random(),
        guard_captain_bias=rng.random(),
        fire_plans_bias=rng.random(),
        fishing_dock_bias=rng.random(),
        fishing_boat_bias=rng.random(),
        dockhouse_bias=rng.random(),
        dockhand_bias=rng.random(),
        dockhand_repair_bias=rng.random(),
        dockhand_boatwright_bias=rng.random(),
        dry_dock_bias=rng.random(),
        admiralty_bias=rng.random(),
        admiral_bias=rng.random(),
        overtime_bias=rng.random(),
        repair_bias=rng.random(),
        construction_idle_bias=rng.random(),
    )


def mutate_strategy(strategy, rng, mutation_scale):
    """Apply random mutations to a given strategy's weights and build priority.
    
    Args:
    strategy (BotStrategy): The original strategy to mutate.
    rng (random.Random): A random number generator instance to use for mutations.
    mutation_scale (float): The maximum amount by which to mutate each weight (e.g., 0.5 for up to ±0.5 mutation).
    Returns:
    BotStrategy: A new strategy instance with mutated weights and possibly a mutated build priority.
    """
    mutated = copy_strategy(strategy)
    for field in BOT_WEIGHT_FIELDS:
        value = getattr(mutated, field)
        value += rng.uniform(-mutation_scale, mutation_scale)
        if field.endswith("_bias"):
            value = clamp(value, 0.0, 1.0)
        else:
            value = clamp(value, 0.0, 5.0)
        setattr(mutated, field, value)

    if rng.random() < 0.35:
        mutated.build_priority = mutate_build_priority(mutated.build_priority, rng)

    return mutated


def mutate_build_priority(build_priority, rng):
    """
    Randomly add, remove, or swap a project in the build priority list.
    
    Args        build_priority (list): The current build priority list.
        rng (random.Random): A random number generator instance.
    Returns:
        list: A new build priority list with a mutation applied.

    Example:
        current_priority = ["shipyard", "fort", "trade_guild"]
        new_priority = mutate_build_priority(current_priority, rng)
        # new_priority might be:
        # - ["shipyard", "fort", "trade_guild", "admiralty"] (added "admiralty")
        # - ["fort", "trade_guild"] (removed "shipyard")
        # - ["trade_guild", "fort", "shipyard"] (swapped "shipyard" and "trade_guild")
    """
    projects = build_priority[:]
    action = rng.choice(["add", "remove", "swap"])

    if action == "add":
        available = [project for project in BUILD_PROJECTS if project not in projects]
        if available:
            projects.insert(rng.randint(0, len(projects)), rng.choice(available))
    elif action == "remove" and projects:
        projects.pop(rng.randrange(len(projects)))
    elif action == "swap" and len(projects) >= 2:
        first = rng.randrange(len(projects))
        second = rng.randrange(len(projects))
        projects[first], projects[second] = projects[second], projects[first]

    return projects


def blend_strategy(current, candidate, learning_rate):
    """
    Blend the weights and build priority of a candidate strategy into the current strategy based on a learning rate.
    
    Args:
    current (BotStrategy): The current strategy to be updated.
    candidate (BotStrategy): The candidate strategy whose traits will be blended into the current strategy.
    learning_rate (float): A value between 0 and 1 that determines how much of the candidate's traits to incorporate (e.g., 0.1 for 10% influence).
    Returns:
    BotStrategy: A new strategy instance that is a blend of the current and candidate strategies.
    Example:
        current_strategy = BotStrategy(trade_weight=2.0, raid_weight=3.0, ...)
        candidate_strategy = BotStrategy(trade_weight=4.0, raid_weight=1.0, ...)
        blended_strategy = blend_strategy(current_strategy, candidate_strategy, learning_rate=0.1)
        # blended_strategy will have trade_weight closer to 2.2 and raid_weight closer to 2.8 than the current strategy.
    """
    learned = copy_strategy(current)
    for field in BOT_WEIGHT_FIELDS:
        current_value = getattr(current, field)
        candidate_value = getattr(candidate, field)
        value = current_value + (candidate_value - current_value) * learning_rate
        if field.endswith("_bias"):
            value = clamp(value, 0.0, 1.0)
        else:
            value = clamp(value, 0.0, 5.0)
        setattr(learned, field, value)

    learned.build_priority = candidate.build_priority[:]
    return learned


def copy_strategy(strategy):
    """
    Create a deep copy of a BotStrategy instance.
    
    Args:
    strategy (BotStrategy): The strategy to copy.
    Returns:
    BotStrategy: A new instance of BotStrategy with the same values as the original.

        Example:
        original_strategy = BotStrategy(trade_weight=2.0, raid_weight=3.0, ...)
        copied_strategy = copy_strategy(original_strategy)
        # copied_strategy will have the same trade_weight and raid_weight as original_strategy, but will be a different instance in memory.
    """
    return BotStrategy(
        name=strategy.name,
        trade_weight=strategy.trade_weight,
        raid_weight=strategy.raid_weight,
        guard_weight=strategy.guard_weight,
        fire_weight=strategy.fire_weight,
        build_priority=strategy.build_priority[:],
        convoy_bias=strategy.convoy_bias,
        ship_bias=strategy.ship_bias,
        shipyard_bias=strategy.shipyard_bias,
        fort_bias=strategy.fort_bias,
        trade_guild_bias=strategy.trade_guild_bias,
        administrator_bias=strategy.administrator_bias,
        guard_captain_bias=strategy.guard_captain_bias,
        fire_plans_bias=strategy.fire_plans_bias,
        fishing_dock_bias=strategy.fishing_dock_bias,
        fishing_boat_bias=strategy.fishing_boat_bias,
        dockhouse_bias=strategy.dockhouse_bias,
        dockhand_bias=strategy.dockhand_bias,
        dockhand_repair_bias=strategy.dockhand_repair_bias,
        dockhand_boatwright_bias=strategy.dockhand_boatwright_bias,
        dry_dock_bias=strategy.dry_dock_bias,
        admiralty_bias=strategy.admiralty_bias,
        admiral_bias=strategy.admiral_bias,
        overtime_bias=strategy.overtime_bias,
        repair_bias=strategy.repair_bias,
        construction_idle_bias=strategy.construction_idle_bias,
        opening_book=strategy.opening_book,
        adaptive=strategy.adaptive,
        adaptation_strength=strategy.adaptation_strength,
        adaptation_turns=strategy.adaptation_turns,
    )


def clamp(value, minimum, maximum):
    """
    Clamp a value between a minimum and maximum range.
    
    Args:
    value (float): The value to clamp.
    minimum (float): The minimum allowed value.
    maximum (float): The maximum allowed value.
    Returns:
    float: The clamped value, guaranteed to be between minimum and maximum.
    Example:
        clamped_value = clamp(1.5, 0.0, 1.0)  # clamped_value will be 1.0
        clamped_value = clamp(-0.5, 0.0, 1.0) # clamped_value will be 0.0
        clamped_value = clamp(0.5, 0.0, 1.0)  # clamped_value will be 0.5
    """
    return max(minimum, min(maximum, value))


def strategy_record(strategy):
    """
    Convert a BotStrategy instance into a dictionary record suitable for JSON serialization.
    Args:
        strategy (BotStrategy): The strategy to convert into a record.
    Returns:    
        dict: A dictionary containing the strategy's attributes, ready for JSON serialization.
    """
    record = {
        "name": strategy.name,
        "trade_weight": strategy.trade_weight,
        "raid_weight": strategy.raid_weight,
        "guard_weight": strategy.guard_weight,
        "fire_weight": strategy.fire_weight,
        "build_priority": strategy.build_priority,
        "convoy_bias": strategy.convoy_bias,
        "ship_bias": strategy.ship_bias,
        "shipyard_bias": strategy.shipyard_bias,
        "fort_bias": strategy.fort_bias,
        "trade_guild_bias": strategy.trade_guild_bias,
        "administrator_bias": strategy.administrator_bias,
        "guard_captain_bias": strategy.guard_captain_bias,
        "fire_plans_bias": strategy.fire_plans_bias,
        "fishing_dock_bias": strategy.fishing_dock_bias,
        "fishing_boat_bias": strategy.fishing_boat_bias,
        "dockhouse_bias": strategy.dockhouse_bias,
        "dockhand_bias": strategy.dockhand_bias,
        "dockhand_repair_bias": strategy.dockhand_repair_bias,
        "dockhand_boatwright_bias": strategy.dockhand_boatwright_bias,
        "dry_dock_bias": strategy.dry_dock_bias,
        "admiralty_bias": strategy.admiralty_bias,
        "admiral_bias": strategy.admiral_bias,
        "overtime_bias": strategy.overtime_bias,
        "repair_bias": strategy.repair_bias,
        "construction_idle_bias": strategy.construction_idle_bias,
        "adaptive": strategy.adaptive,
        "adaptation_strength": strategy.adaptation_strength,
        "adaptation_turns": strategy.adaptation_turns,
    }
    if strategy.opening_book:
        record["opening_book"] = opening_book_record(strategy.opening_book)
    return record


def opening_book_record(opening_book):
    """
    Convert an opening book into a list of dictionary records suitable for JSON serialization.
    Args:
        opening_book (list): A list of opening records, where each record is a dictionary containing the opening's attributes and turn data.
    Returns:
        list: A list of dictionary records suitable for JSON serialization.
    """
    return [
        {
            "name": opening.get("name", "opening"),
            "code_id": opening.get("code_id", ""),
            "source": opening.get("source", ""),
            "weight": opening.get("weight", 1),
            "anti_aggro": opening.get("anti_aggro", False),
            "turns": {
                str(turn): opening_turn_record(turn_data)
                for turn, turn_data in opening.get("turns", {}).items()
            },
        }
        for opening in opening_book
    ]


def opening_turn_record(turn_data):
    """
    Convert turn data from an opening book into a dictionary record suitable for JSON serialization.
    Args:        turn_data (dict): A dictionary containing the turn's attributes, including "buy_actions", 
    "allocation", and "continue_buy_phase".
    Returns:
        dict: A dictionary record suitable for JSON serialization, containing the turn's attributes.
    """
    record = {
        "buy_actions": turn_data.get("buy_actions", [])[:],
    }
    allocation = turn_data.get("allocation")
    if allocation is not None:
        record["allocation"] = allocation_record(allocation)
    if turn_data.get("continue_buy_phase", False):
        record["continue_buy_phase"] = True
    return record


def allocation_record(allocation):
    """
    Convert an Allocation instance into a dictionary record suitable for JSON serialization.
    Args:
        allocation (Allocation): An instance of the Allocation class containing trade, raid, guard, and fire values.
    Returns:
        dict: A dictionary record containing the allocation's attributes, ready for JSON serialization.
    """
    return {
        "trade": allocation.trade,
        "raid": allocation.raid,
        "guard": allocation.guard,
        "fire": allocation.fire,
    }
