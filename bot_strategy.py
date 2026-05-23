import json
from pathlib import Path

from game_state import Allocation, Rules


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
    "guard_captain_bias",
    "fire_plans_bias",
    "fishing_dock_bias",
    "fishing_boat_bias",
    "dry_dock_bias",
    "repair_bias",
    "construction_idle_bias",
]
BUILD_PROJECTS = [
    "shipyard",
    "fort",
    "trade_guild",
    "fishing_dock",
    "fishing_boat",
    "guard_captain",
    "fire_plans",
    "dry_dock",
]
MIN_FLEET_FOR_PROJECTS = 3
MIN_FLEET_FOR_CONVOYS = 2
REBUILD_FLEET_TARGET = 4
MIDGAME_START_TURN = 4
PRIORITY_PROJECT_MIN_BIAS = 0.20
MATCHUP_FLOOR_WIN_RATE = 0.35
DOMINANCE_CAP_PER_GAME = 180
MATCHUP_FLOOR_PENALTY = 350
MATCHUP_FLOOR_RECOVERY_BONUS = 60000
ROBUSTNESS_ALLOWED_REGRESSION = 0.05
ROBUSTNESS_REGRESSION_PREMIUM = 12000
ROBUSTNESS_CATASTROPHIC_REGRESSION = 0.15
PORT_LOSS_PRESSURE_PENALTY = 80
SURVIVAL_SHIPYARD_BONUS = 20
SURVIVAL_FORT_BONUS = 20
SURVIVAL_GUARD_CAPTAIN_BONUS = 8


class BotStrategy:
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
        guard_captain_bias=None,
        fire_plans_bias=None,
        fishing_dock_bias=None,
        fishing_boat_bias=None,
        dry_dock_bias=None,
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
        self.dry_dock_bias = self.default_project_bias("dry_dock", dry_dock_bias)
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
            weights["guard"] += 2.0
        if player.has_payroll_at_sea:
            weights["guard"] += 2.5
        if opponent.ships <= Rules.PORT_ATTACK_SHIPS_REQUIRED:
            weights["raid"] += 1.5
        if opponent.shipyard_started:
            weights["fire"] += 1.5
        self.adjust_weights_for_position(weights, position)
        self.adjust_weights_for_observations(weights, game, player, opponent)
        if not can_use_fire:
            weights["fire"] = 0

        allocation = {"trade": 0, "raid": 0, "guard": 0, "fire": 0}
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
        game.auto_launch_final_payroll(player)

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
                project == "dry_dock"
                and game.dry_dock_disabled_reason(player) is None
            ):
                dry_dock_bias = self.project_buy_bias("dry_dock")
                if player.damaged_ships > 0 or self.raid_weight >= 3.0:
                    dry_dock_bias += 0.25
                if rng.random() < min(1.0, dry_dock_bias):
                    player.start_dry_dock()

        if self.should_launch_payroll(game, player, rng):
            player.launch_payroll()

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
                return rng.choice(shield_openings)
        return rng.choice(self.opening_book)

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
        return True

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
        elif action == "hire_guard_captain":
            if game.guard_captain_disabled_reason(player) is None:
                player.hire_guard_captain()
        elif action == "buy_fire_ship_plans":
            if game.fire_ship_plans_disabled_reason(player) is None:
                player.unlock_fire_ships()
        elif action == "build_fishing_dock":
            if game.fishing_dock_disabled_reason(player) is None:
                player.build_or_repair_fishing_dock()
        elif action == "buy_fishing_boats":
            if game.buy_fishing_boats_disabled_reason(player) is None:
                affordable = game.affordable_fishing_boats(player)
                if affordable > 0:
                    game.buy_fishing_boats(player, affordable)
        elif action == "start_dry_dock":
            if game.dry_dock_disabled_reason(player) is None:
                player.start_dry_dock()
        elif action == "repair_damaged_ships":
            self.repair_all_affordable_damaged_ships(player)
        elif action == "buy_ships":
            affordable = player.gold // player.ship_cost
            if affordable > 0:
                player.buy_ships(affordable)

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

    def repair_all_affordable_damaged_ships(self, player):
        if player.damaged_ships <= 0:
            return 0
        if player.raid_repair_cost == 0:
            amount = player.damaged_ships
        else:
            amount = min(player.damaged_ships, player.gold // player.raid_repair_cost)
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

    def can_spend_on_project(self, player, project):
        if project == "guard_captain":
            return player.ships >= MIN_FLEET_FOR_CONVOYS
        if project == "fishing_dock":
            return player.ships >= 1
        if project == "fishing_boat":
            return player.fishing_dock_built and not player.fishing_dock_disabled
        if project == "dry_dock":
            return player.shipyard_completed
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
        if player.ships >= 6:
            launch_score += 0.2
        if game.turn >= Rules.PAYROLL_FINAL_TURN - 1:
            launch_score += 0.4
        return rng.random() < launch_score

    def should_launch_treasure(self, game, player, rng):
        if game.treasure_launch_disabled_reason(player) is not None:
            return False
        if player.ships < MIN_FLEET_FOR_CONVOYS:
            return False

        launch_score = self.convoy_bias
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
                player.dry_dock_started and not player.dry_dock_completed,
            ]
        )

    def choose_idle_construction_labor(self, player, ships, position=None):
        if not self.has_active_construction(player):
            return 0

        desired_idle = max(1, int(ships * self.construction_idle_bias + 0.999))
        if player.ships <= MIN_FLEET_FOR_PROJECTS:
            desired_idle = min(desired_idle, 1)
        if position is not None:
            if position["enemy_port_open"] and player.ships >= Rules.PORT_ATTACK_SHIPS_REQUIRED:
                return 0
            if position["under_fleet_pressure"]:
                desired_idle = min(desired_idle, 1)
            elif position["asset_gap"] >= 10 or position["income_edge"] > 0:
                desired_idle = min(ships, desired_idle + 1)
        return min(ships, desired_idle)

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
            "dry_dock",
        }:
            return False
        if position["fleet_gap"] <= -2 and project not in {
            "shipyard",
            "fishing_dock",
            "dry_dock",
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
        guard_captain_bias=strategy_data.get("guard_captain_bias"),
        fire_plans_bias=strategy_data.get("fire_plans_bias"),
        fishing_dock_bias=strategy_data.get("fishing_dock_bias"),
        fishing_boat_bias=strategy_data.get("fishing_boat_bias"),
        dry_dock_bias=strategy_data.get("dry_dock_bias"),
        repair_bias=strategy_data.get("repair_bias", 0.5),
        construction_idle_bias=strategy_data.get("construction_idle_bias", 0.0),
        adaptive=strategy_data.get("adaptive", False),
        adaptation_strength=strategy_data.get("adaptation_strength", 0.0),
        adaptation_turns=strategy_data.get("adaptation_turns", 3),
    )


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
        guard_captain_bias=rng.random(),
        fire_plans_bias=rng.random(),
        fishing_dock_bias=rng.random(),
        fishing_boat_bias=rng.random(),
        dry_dock_bias=rng.random(),
        repair_bias=rng.random(),
        construction_idle_bias=rng.random(),
    )


def mutate_strategy(strategy, rng, mutation_scale):
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
        guard_captain_bias=strategy.guard_captain_bias,
        fire_plans_bias=strategy.fire_plans_bias,
        fishing_dock_bias=strategy.fishing_dock_bias,
        fishing_boat_bias=strategy.fishing_boat_bias,
        dry_dock_bias=strategy.dry_dock_bias,
        repair_bias=strategy.repair_bias,
        construction_idle_bias=strategy.construction_idle_bias,
        opening_book=strategy.opening_book,
        adaptive=strategy.adaptive,
        adaptation_strength=strategy.adaptation_strength,
        adaptation_turns=strategy.adaptation_turns,
    )


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def strategy_record(strategy):
    return {
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
        "guard_captain_bias": strategy.guard_captain_bias,
        "fire_plans_bias": strategy.fire_plans_bias,
        "fishing_dock_bias": strategy.fishing_dock_bias,
        "fishing_boat_bias": strategy.fishing_boat_bias,
        "dry_dock_bias": strategy.dry_dock_bias,
        "repair_bias": strategy.repair_bias,
        "construction_idle_bias": strategy.construction_idle_bias,
        "adaptive": strategy.adaptive,
        "adaptation_strength": strategy.adaptation_strength,
        "adaptation_turns": strategy.adaptation_turns,
    }
