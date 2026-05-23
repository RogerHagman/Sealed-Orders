import contextlib
import io
import json
import random
import select
import sys
import termios
import tty
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from main import Allocation, Game, Rules

AI_GAME_LOG_PATH = Path("ai_game_log.jsonl")
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
                if rng.random() < self.project_buy_bias("guard_captain"):
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


class SelfPlayGame(Game):
    def __init__(self, player_names, strategies, rng):
        super().__init__(player_names)
        self.strategies = strategies
        self.rng = rng

    def play_silent(self):
        with contextlib.redirect_stdout(io.StringIO()):
            while self.turn <= Rules.MAX_TURNS and not self.game_over:
                self.play_bot_turn()
                self.turn += 1

        result = self.result()
        for strategy in self.strategies:
            strategy.clear_game_memory(self)
        return result

    def play_bot_turn(self):
        player_one, player_two = self.players
        strategy_one, strategy_two = self.strategies

        player_one.allocation = strategy_one.choose_allocation(
            self, player_one, player_two, self.rng
        )
        player_two.allocation = strategy_two.choose_allocation(
            self, player_two, player_one, self.rng
        )
        strategy_one.observe_opponent_opening(self, player_one, player_two)
        strategy_two.observe_opponent_opening(self, player_two, player_one)

        self.resolve_orders()
        if self.game_over:
            return

        self.apply_port_labor()
        self.advance_convoys()
        strategy_one.run_buy_phase(self, player_one, player_two, self.rng)
        strategy_two.run_buy_phase(self, player_two, player_one, self.rng)

    def result(self):
        player_one, player_two = self.players
        if self.port_destroyer is player_one:
            winner_index = 0
            win_type = "port"
        elif self.port_destroyer is player_two:
            winner_index = 1
            win_type = "port"
        elif player_one.asset_score > player_two.asset_score:
            winner_index = 0
            win_type = "assets"
        elif player_two.asset_score > player_one.asset_score:
            winner_index = 1
            win_type = "assets"
        else:
            winner_index = None
            win_type = "draw"

        return {
            "winner_index": winner_index,
            "win_type": win_type,
            "turns": min(self.turn, Rules.MAX_TURNS),
            "scores": [player.asset_score for player in self.players],
            "ships": [player.ships for player in self.players],
        }

    def clear_between_players(self):
        pass


class PlayVsAIGame(Game):
    def __init__(self, human_name, strategy, rng):
        super().__init__([human_name, f"AI {strategy.name}"])
        self.human = self.players[0]
        self.ai = self.players[1]
        self.strategy = strategy
        self.rng = rng
        self.turn_records = []

    def play_turn(self):
        print(f"\n=== {self.current_month.upper()} ({self.turn}/{Rules.MAX_TURNS}) ===")
        self.show_state()
        before_snapshot = self.snapshot_turn()

        self.show_player_economy(self.human)
        self.human.allocation = self.prompt_allocation(self.human)
        print(f"\n{self.ai.name} writes sealed orders.")
        self.ai.allocation = self.strategy.choose_allocation(
            self, self.ai, self.human, self.rng
        )
        self.strategy.observe_opponent_opening(self, self.ai, self.human)

        orders_snapshot = self.snapshot_turn()
        self.reveal_orders()
        self.resolve_orders()
        if self.game_over:
            after_snapshot = self.snapshot_turn()
            self.record_turn(before_snapshot, orders_snapshot, after_snapshot)
            return
        self.pause_after_resolution()
        self.apply_port_labor()
        self.advance_convoys()
        self.buy_phase()
        after_snapshot = self.snapshot_turn()
        self.record_turn(before_snapshot, orders_snapshot, after_snapshot)
        self.show_turn_summary(before_snapshot, after_snapshot, orders_snapshot)

    def buy_phase(self):
        print("\n=== BUY PHASE ===")
        self.run_buy_menu(self.human)
        print(f"\n{self.ai.name} takes its buy phase.")
        self.strategy.run_buy_phase(self, self.ai, self.human, self.rng)
        print(f"{self.ai.name} finishes the buy phase.")
        self.show_state()

    def record_turn(self, before_snapshot, orders_snapshot, after_snapshot):
        self.turn_records.append(
            {
                "turn": self.turn,
                "month": self.current_month,
                "before": snapshot_record(before_snapshot),
                "orders": snapshot_record(orders_snapshot),
                "after": snapshot_record(after_snapshot),
            }
        )


def write_ai_game_record(game, strategy, seed, log_path=AI_GAME_LOG_PATH):
    log_path = Path(log_path)
    record = build_ai_game_record(game, strategy, seed)
    if log_path.parent != Path("."):
        log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, sort_keys=True))
        log_file.write("\n")

    print(f"\nAI game recorded in {log_path}.")


def build_ai_game_record(game, strategy, seed):
    human = game.human
    ai = game.ai
    winner = ai_game_winner(game)

    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "rules_version": Rules.VERSION,
        "ai_strategy": strategy.name,
        "seed": seed,
        "turns": min(game.turn, Rules.MAX_TURNS),
        "win_type": ai_game_win_type(game),
        "winner": winner,
        "human_won": winner == "human",
        "ai_won": winner == "ai",
        "players": {
            "human": player_record(human),
            "ai": player_record(ai),
        },
        "turns_detail": game.turn_records,
    }


def ai_game_winner(game):
    human = game.human
    ai = game.ai

    if game.port_destroyer is human:
        return "human"
    if game.port_destroyer is ai:
        return "ai"
    if human.asset_score > ai.asset_score:
        return "human"
    if ai.asset_score > human.asset_score:
        return "ai"
    return "draw"


def ai_game_win_type(game):
    if game.port_destroyer is not None:
        return "port"
    if game.human.asset_score == game.ai.asset_score:
        return "draw"
    return "assets"


def player_record(player):
    return {
        "name": player.name,
        "gold": player.gold,
        "ships": player.ships,
        "asset_score": player.asset_score,
        "shipyard_started": player.shipyard_started,
        "shipyard_completed": player.shipyard_completed,
        "fort_started": player.fort_started,
        "fort_completed": player.fort_completed,
        "trade_guild_started": player.trade_guild_started,
        "trade_guild_completed": player.trade_guild_completed,
        "fishing_dock_started": player.fishing_dock_started,
        "fishing_dock_labor": player.fishing_dock_labor,
        "fishing_dock_built": player.fishing_dock_built,
        "fishing_dock_disabled": player.fishing_dock_disabled,
        "fishing_boats": player.fishing_boats,
        "raid_actions_total": player.raid_actions_total,
        "damaged_ships": player.damaged_ships,
        "raid_damage_events": player.raid_damage_events,
        "raid_repairs_total": player.raid_repairs_total,
        "damaged_raiders_sunk": player.damaged_raiders_sunk,
        "dry_dock_started": player.dry_dock_started,
        "dry_dock_labor": player.dry_dock_labor,
        "dry_dock_completed": player.dry_dock_completed,
        "fire_ships_unlocked": player.fire_ships_unlocked,
        "guard_captains": player.guard_captains,
        "treasure_value": player.treasure_value,
        "treasure_at_sea": player.has_treasure_at_sea,
        "payroll_launched": player.payroll_launched,
        "payroll_at_sea": player.has_payroll_at_sea,
    }


def snapshot_record(snapshot):
    return {
        player_name: {
            key: value_record(value)
            for key, value in player_snapshot.items()
        }
        for player_name, player_snapshot in snapshot.items()
    }


def value_record(value):
    if isinstance(value, Allocation):
        return {
            "trade": value.trade,
            "raid": value.raid,
            "guard": value.guard,
            "fire": value.fire,
            "total": value.total,
        }

    return value


HUMAN_WON_OPENING_BOOK = [
    {
        "name": "treasure_shipyard_shield",
        "source": "Human wins vs Port Reaper and The Red Tide",
        "anti_aggro": True,
        "turns": {
            1: {
                "allocation": Allocation(guard=3),
                "buy_actions": ["launch_treasure", "start_shipyard"],
            },
            2: {
                "allocation": Allocation(guard=2),
                "buy_actions": [],
            },
            3: {
                "allocation": Allocation(guard=1),
                "buy_actions": ["launch_treasure", "buy_ships"],
            },
        },
    },
    {
        "name": "trade_guard_shipyard",
        "source": "Human win vs Bastion Corsair",
        "anti_aggro": True,
        "turns": {
            1: {
                "allocation": Allocation(guard=3),
                "buy_actions": ["launch_treasure", "start_shipyard"],
            },
            2: {
                "allocation": Allocation(trade=2, guard=1),
                "buy_actions": [],
            },
            3: {
                "allocation": Allocation(),
                "buy_actions": ["launch_treasure", "buy_ships"],
            },
        },
    },
    {
        "name": "balanced_treasure_pressure",
        "source": "Human wins vs Black Ledger and Builder",
        "turns": {
            1: {
                "allocation": Allocation(trade=1, raid=1, guard=1),
                "buy_actions": ["launch_treasure", "buy_ships"],
            },
            2: {
                "allocation": Allocation(trade=1, guard=3),
                "buy_actions": [],
            },
            3: {
                "allocation": Allocation(trade=2, guard=2),
                "buy_actions": ["launch_treasure", "buy_ships"],
            },
        },
    },
    {
        "name": "raid_treasure_snowball",
        "source": "Human wins vs Privateer and Merchant",
        "turns": {
            1: {
                "allocation": Allocation(raid=3),
                "buy_actions": ["launch_treasure", "buy_ships"],
            },
            2: {
                "allocation": Allocation(raid=2, guard=2),
                "buy_actions": ["start_shipyard"],
            },
            3: {
                "allocation": Allocation(trade=1, raid=3, guard=1),
                "buy_actions": ["launch_treasure", "start_trade_guild", "buy_ships"],
            },
        },
    },
    {
        "name": "dock_guard_treasure",
        "source": "Current-rule human wins vs Admiral and Opportunist",
        "turns": {
            1: {
                "allocation": Allocation(guard=3),
                "buy_actions": ["launch_treasure", "build_fishing_dock", "buy_ships"],
            },
            2: {
                "allocation": Allocation(raid=2, guard=2),
                "buy_actions": [],
            },
            3: {
                "allocation": Allocation(raid=3),
                "buy_actions": ["buy_fire_ship_plans", "launch_treasure", "buy_ships"],
            },
        },
    },
    {
        "name": "guild_dock_buildout",
        "source": "Current-rule human win vs Corsair Spark",
        "turns": {
            1: {
                "allocation": Allocation(guard=3),
                "buy_actions": ["start_trade_guild", "build_fishing_dock"],
            },
            2: {
                "allocation": Allocation(),
                "buy_actions": [],
            },
            3: {
                "allocation": Allocation(raid=3),
                "buy_actions": ["start_shipyard", "hire_guard_captain"],
            },
        },
    },
    {
        "name": "guard_captain_harbor_lock",
        "source": "Current-rule human win vs Harbor Lock",
        "turns": {
            1: {
                "allocation": Allocation(trade=3),
                "buy_actions": ["launch_treasure", "buy_ships"],
            },
            2: {
                "allocation": Allocation(trade=1, guard=4),
                "buy_actions": ["hire_guard_captain"],
            },
            3: {
                "allocation": Allocation(trade=1, raid=1, guard=3),
                "buy_actions": [
                    "start_shipyard",
                    "build_fishing_dock",
                    "hire_guard_captain",
                    "buy_fire_ship_plans",
                ],
            },
        },
    },
]


def default_bot_strategies():
    return [
        BotStrategy(
            name="Merchant",
            trade_weight=4.0,
            raid_weight=0.8,
            guard_weight=1.8,
            fire_weight=0.2,
            build_priority=[
                "shipyard",
                "trade_guild",
                "fishing_dock",
                "fishing_boat",
                "guard_captain",
                "fort",
            ],
            convoy_bias=0.75,
            ship_bias=0.75,
            shipyard_bias=0.85,
            fort_bias=0.15,
            trade_guild_bias=0.7,
            fishing_dock_bias=0.65,
            fishing_boat_bias=0.7,
            guard_captain_bias=0.12,
            fire_plans_bias=0.05,
            construction_idle_bias=0.55,
        ),
        BotStrategy(
            name="Privateer",
            trade_weight=1.4,
            raid_weight=4.0,
            guard_weight=1.1,
            fire_weight=1.2,
            build_priority=[
                "fire_plans",
                "shipyard",
                "fishing_dock",
                "guard_captain",
                "fort",
            ],
            convoy_bias=0.35,
            ship_bias=0.95,
            shipyard_bias=0.45,
            fort_bias=0.08,
            trade_guild_bias=0.03,
            fishing_dock_bias=0.12,
            fishing_boat_bias=0.08,
            guard_captain_bias=0.05,
            fire_plans_bias=0.55,
            construction_idle_bias=0.35,
        ),
        BotStrategy(
            name="Builder",
            trade_weight=2.4,
            raid_weight=1.1,
            guard_weight=2.0,
            fire_weight=0.4,
            build_priority=[
                "shipyard",
                "fort",
                "trade_guild",
                "fishing_dock",
                "fishing_boat",
                "guard_captain",
            ],
            convoy_bias=0.55,
            ship_bias=0.65,
            shipyard_bias=0.85,
            fort_bias=0.7,
            trade_guild_bias=0.55,
            fishing_dock_bias=0.45,
            fishing_boat_bias=0.45,
            guard_captain_bias=0.15,
            fire_plans_bias=0.08,
            construction_idle_bias=0.8,
        ),
        BotStrategy(
            name="Admiral",
            trade_weight=2.2,
            raid_weight=2.2,
            guard_weight=2.1,
            fire_weight=0.8,
            build_priority=[
                "shipyard",
                "fire_plans",
                "fort",
                "fishing_dock",
                "guard_captain",
            ],
            convoy_bias=0.6,
            ship_bias=0.85,
            shipyard_bias=0.7,
            fort_bias=0.35,
            trade_guild_bias=0.15,
            fishing_dock_bias=0.25,
            fishing_boat_bias=0.2,
            guard_captain_bias=0.12,
            fire_plans_bias=0.45,
            construction_idle_bias=0.55,
        ),
        BotStrategy(
            name="Opportunist",
            trade_weight=2.0,
            raid_weight=2.8,
            guard_weight=1.4,
            fire_weight=0.9,
            build_priority=["shipyard", "trade_guild", "fire_plans"],
            convoy_bias=0.5,
            ship_bias=0.9,
        ),
        BotStrategy(
            name="Human Shadow",
            trade_weight=5.2,
            raid_weight=1.0,
            guard_weight=1.05,
            fire_weight=0.06,
            build_priority=[
                "shipyard",
                "trade_guild",
                "fishing_dock",
                "fishing_boat",
                "guard_captain",
                "fort",
                "fire_plans",
            ],
            convoy_bias=0.65,
            ship_bias=0.9,
            shipyard_bias=0.72,
            fort_bias=0.35,
            trade_guild_bias=0.6,
            fishing_dock_bias=0.7,
            fishing_boat_bias=0.75,
            guard_captain_bias=0.35,
            fire_plans_bias=0.4,
            construction_idle_bias=0.72,
            opening_book=HUMAN_WON_OPENING_BOOK,
        ),
        BotStrategy(
            name="Tide Reader",
            trade_weight=2.4,
            raid_weight=2.4,
            guard_weight=2.0,
            fire_weight=0.8,
            build_priority=[
                "shipyard",
                "trade_guild",
                "fishing_dock",
                "fishing_boat",
                "fire_plans",
                "guard_captain",
                "fort",
            ],
            convoy_bias=0.45,
            ship_bias=0.8,
            shipyard_bias=0.55,
            fort_bias=0.25,
            trade_guild_bias=0.4,
            fishing_dock_bias=0.55,
            fishing_boat_bias=0.55,
            guard_captain_bias=0.18,
            fire_plans_bias=0.35,
            construction_idle_bias=0.6,
            adaptive=True,
            adaptation_strength=1.0,
            adaptation_turns=3,
        ),
        BotStrategy(
            name="Port Reaper",
            trade_weight=1.4,
            raid_weight=3.33,
            guard_weight=0.05,
            fire_weight=3.07,
            build_priority=[],
            convoy_bias=0.03,
            ship_bias=0.74,
        ),
        BotStrategy(
            name="Harbor Lock",
            trade_weight=4.72,
            raid_weight=0.68,
            guard_weight=3.6,
            fire_weight=2.0,
            build_priority=[],
            convoy_bias=0.18,
            ship_bias=0.9,
        ),
        BotStrategy(
            name="Corsair Spark",
            trade_weight=4.4,
            raid_weight=4.01,
            guard_weight=1.55,
            fire_weight=4.31,
            build_priority=[],
            convoy_bias=0.69,
            ship_bias=0.16,
        ),
        BotStrategy(
            name="Storm Reaver",
            trade_weight=2.84,
            raid_weight=3.95,
            guard_weight=2.19,
            fire_weight=4.61,
            build_priority=[],
            convoy_bias=0.32,
            ship_bias=0.74,
        ),
        BotStrategy(
            name="Iron Tempest",
            trade_weight=2.61,
            raid_weight=4.06,
            guard_weight=2.4,
            fire_weight=4.44,
            build_priority=[],
            convoy_bias=0.04,
            ship_bias=0.8,
        ),
        BotStrategy(
            name="Black Ledger",
            trade_weight=0.76,
            raid_weight=4.8,
            guard_weight=0.93,
            fire_weight=2.28,
            build_priority=[],
            convoy_bias=0.0,
            ship_bias=0.64,
            shipyard_bias=0.43,
            fort_bias=0.02,
            trade_guild_bias=0.12,
            guard_captain_bias=0.08,
            fire_plans_bias=0.12,
            construction_idle_bias=0.74,
        ),
        BotStrategy(
            name="Bastion Corsair",
            trade_weight=0.74,
            raid_weight=4.58,
            guard_weight=0.21,
            fire_weight=1.7,
            build_priority=[],
            convoy_bias=0.0,
            ship_bias=0.46,
            shipyard_bias=0.23,
            fort_bias=0.21,
            trade_guild_bias=0.08,
            guard_captain_bias=0.01,
            fire_plans_bias=0.04,
            construction_idle_bias=0.69,
        ),
        BotStrategy(
            name="Harbor Harvest",
            trade_weight=0.17,
            raid_weight=4.88,
            guard_weight=2.10,
            fire_weight=0.22,
            build_priority=[
                "fishing_dock",
                "shipyard",
                "fire_plans",
                "fishing_boat",
            ],
            convoy_bias=0.00,
            ship_bias=0.40,
            shipyard_bias=0.07,
            fort_bias=0.74,
            trade_guild_bias=0.29,
            fishing_dock_bias=1.00,
            fishing_boat_bias=0.99,
            guard_captain_bias=0.41,
            fire_plans_bias=0.34,
            construction_idle_bias=0.61,
        ),
        BotStrategy(
            name="Reef Tyrant",
            trade_weight=0.19,
            raid_weight=4.66,
            guard_weight=0.01,
            fire_weight=0.27,
            build_priority=[
                "fishing_boat",
                "fort",
                "fishing_dock",
                "shipyard",
                "fire_plans",
                "trade_guild",
            ],
            convoy_bias=0.00,
            ship_bias=0.80,
            shipyard_bias=0.04,
            fort_bias=0.24,
            trade_guild_bias=0.06,
            fishing_dock_bias=0.91,
            fishing_boat_bias=0.70,
            guard_captain_bias=0.10,
            fire_plans_bias=0.94,
            construction_idle_bias=0.72,
        ),
        BotStrategy(
            name="Reef Bloom",
            trade_weight=0.00,
            raid_weight=1.12,
            guard_weight=0.09,
            fire_weight=3.74,
            build_priority=[
                "fishing_dock",
                "dry_dock",
                "fishing_boat",
                "shipyard",
                "guard_captain",
                "fort",
                "fire_plans",
            ],
            convoy_bias=0.00,
            ship_bias=0.14,
            shipyard_bias=0.10,
            fort_bias=0.82,
            trade_guild_bias=0.00,
            guard_captain_bias=0.18,
            fire_plans_bias=0.15,
            fishing_dock_bias=0.99,
            fishing_boat_bias=0.97,
            dry_dock_bias=0.68,
            repair_bias=0.83,
            construction_idle_bias=0.43,
        ),
        BotStrategy(
            name="The Red Tide",
            trade_weight=0.33,
            raid_weight=4.89,
            guard_weight=0.00,
            fire_weight=1.41,
            build_priority=["shipyard"],
            convoy_bias=0.00,
            ship_bias=0.85,
            shipyard_bias=0.25,
            fort_bias=0.06,
            trade_guild_bias=0.01,
            guard_captain_bias=0.00,
            fire_plans_bias=0.00,
            construction_idle_bias=0.85,
        ),
        BotStrategy(
            name="Signal Black",
            trade_weight=0.02,
            raid_weight=4.16,
            guard_weight=0.02,
            fire_weight=0.17,
            build_priority=[],
            convoy_bias=0.01,
            ship_bias=0.89,
            shipyard_bias=0.03,
            fort_bias=0.03,
            trade_guild_bias=0.00,
            guard_captain_bias=0.08,
            fire_plans_bias=0.00,
            fishing_dock_bias=0.00,
            fishing_boat_bias=0.90,
            construction_idle_bias=0.46,
        ),
    ]


def strategy_names():
    return [strategy.name for strategy in default_bot_strategies()]


def find_strategy(name):
    normalized_name = name.strip().lower()
    for strategy in default_bot_strategies():
        if strategy.name.lower() == normalized_name:
            return strategy

    available = ", ".join(strategy_names())
    raise ValueError(f"Unknown AI strategy '{name}'. Available strategies: {available}.")


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


def play_vs_ai(
    human_name="England",
    strategy_name="Privateer",
    seed=None,
    log_path=AI_GAME_LOG_PATH,
):
    rng = random.Random(seed)
    strategy = find_strategy(strategy_name)
    game = PlayVsAIGame(human_name=human_name, strategy=strategy, rng=rng)
    print(f"\nYou are facing AI {strategy.name}.")
    game.play()
    write_ai_game_record(game, strategy, seed, log_path=log_path)


def summarize_ai_games(log_path=AI_GAME_LOG_PATH):
    log_path = Path(log_path)
    if not log_path.exists():
        print(f"No AI game log found at {log_path}.")
        return

    stats = defaultdict(
        lambda: {
            "games": 0,
            "human_wins": 0,
            "ai_wins": 0,
            "draws": 0,
            "turns_total": 0,
            "human_score_total": 0,
            "ai_score_total": 0,
        }
    )

    with log_path.open(encoding="utf-8") as log_file:
        for line in log_file:
            if not line.strip():
                continue
            record = json.loads(line)
            row = stats[record["ai_strategy"]]
            row["games"] += 1
            row["turns_total"] += record["turns"]
            row["human_score_total"] += record["players"]["human"]["asset_score"]
            row["ai_score_total"] += record["players"]["ai"]["asset_score"]

            if record["winner"] == "human":
                row["human_wins"] += 1
            elif record["winner"] == "ai":
                row["ai_wins"] += 1
            else:
                row["draws"] += 1

    print_ai_game_summary(log_path, stats)


def print_ai_game_summary(log_path, stats):
    print(f"\n=== HUMAN VS AI HISTORY: {log_path} ===")
    print(
        "\nAI strategy   Games  Human wins  AI wins  Draws  "
        "Human win rate  Avg turns  Avg human  Avg AI"
    )
    print(
        "------------  -----  ----------  -------  -----  "
        "--------------  ---------  ---------  ------"
    )

    for strategy_name, row in sorted(stats.items()):
        games = row["games"]
        human_win_rate = row["human_wins"] / games if games else 0
        avg_turns = row["turns_total"] / games if games else 0
        avg_human_score = row["human_score_total"] / games if games else 0
        avg_ai_score = row["ai_score_total"] / games if games else 0
        print(
            f"{strategy_name:<12}  {games:>5}  {row['human_wins']:>10}  "
            f"{row['ai_wins']:>7}  {row['draws']:>5}  "
            f"{human_win_rate * 100:>13.1f}%  {avg_turns:>9.1f}  "
            f"{avg_human_score:>9.1f}  {avg_ai_score:>6.1f}"
        )


def evaluate_strategy_file(strategy_path, games_per_opponent=100, seed=None, output_path=None):
    rng = random.Random(seed)
    strategy = load_strategy(strategy_path)
    opponents = default_bot_strategies()
    rows = []

    print(f"\n=== STRATEGY BENCHMARK: {strategy.name} ===")
    print(f"Strategy file: {strategy_path}")
    if seed is not None:
        print(f"Seed: {seed}")
    print(f"Games per opponent: {games_per_opponent}")

    for opponent in opponents:
        row = evaluate_head_to_head(strategy, opponent, games_per_opponent, rng)
        rows.append(row)

    print_strategy_benchmark(rows)
    if output_path is not None:
        write_strategy_benchmark(rows, output_path)


def evaluate_head_to_head(strategy, opponent, games, rng):
    stats = {
        "opponent": opponent.name,
        "games": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "port_wins": 0,
        "port_losses": 0,
        "turns_total": 0,
        "score_total": 0,
        "opponent_score_total": 0,
    }

    for game_index in range(games):
        if game_index % 2 == 0:
            player_names = [strategy.name, opponent.name]
            strategies = [strategy, opponent]
            strategy_index = 0
        else:
            player_names = [opponent.name, strategy.name]
            strategies = [opponent, strategy]
            strategy_index = 1

        game = SelfPlayGame(player_names, strategies, rng)
        result = game.play_silent()
        opponent_index = 1 - strategy_index

        stats["games"] += 1
        stats["turns_total"] += result["turns"]
        stats["score_total"] += result["scores"][strategy_index]
        stats["opponent_score_total"] += result["scores"][opponent_index]

        if result["winner_index"] == strategy_index:
            stats["wins"] += 1
            if result["win_type"] == "port":
                stats["port_wins"] += 1
        elif result["winner_index"] is None:
            stats["draws"] += 1
        else:
            stats["losses"] += 1
            if result["win_type"] == "port":
                stats["port_losses"] += 1

    return stats


def print_strategy_benchmark(rows):
    print(
        "\nOpponent         Games  Wins  Losses  Draws  Win rate  "
        "Port wins  Port losses  Avg turns  Avg assets  Opp avg"
    )
    print(
        "---------------  -----  ----  ------  -----  --------  "
        "---------  -----------  ---------  ----------  -------"
    )

    totals = defaultdict(int)
    for row in rows:
        print_strategy_benchmark_row(row)
        for key in [
            "games",
            "wins",
            "losses",
            "draws",
            "port_wins",
            "port_losses",
            "turns_total",
            "score_total",
            "opponent_score_total",
        ]:
            totals[key] += row[key]

    total_row = dict(totals)
    total_row["opponent"] = "TOTAL"
    print_strategy_benchmark_row(total_row)


def print_strategy_benchmark_row(row):
    games = row["games"]
    win_rate = row["wins"] / games if games else 0
    avg_turns = row["turns_total"] / games if games else 0
    avg_score = row["score_total"] / games if games else 0
    avg_opponent_score = row["opponent_score_total"] / games if games else 0

    print(
        f"{row['opponent']:<15}  {games:>5}  {row['wins']:>4}  "
        f"{row['losses']:>6}  {row['draws']:>5}  "
        f"{win_rate * 100:>7.1f}%  {row['port_wins']:>9}  "
        f"{row['port_losses']:>11}  {avg_turns:>9.1f}  "
        f"{avg_score:>10.1f}  {avg_opponent_score:>7.1f}"
    )


def write_strategy_benchmark(rows, output_path):
    output_path = Path(output_path)
    if output_path.parent != Path("."):
        output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix.lower() == ".csv":
        write_strategy_benchmark_csv(rows, output_path)
    else:
        with output_path.open("w", encoding="utf-8") as output_file:
            json.dump(rows, output_file, indent=2, sort_keys=True)
            output_file.write("\n")

    print(f"\nStrategy benchmark written to {output_path}.")


def write_strategy_benchmark_csv(rows, output_path):
    headers = [
        "opponent",
        "games",
        "wins",
        "losses",
        "draws",
        "win_rate",
        "port_wins",
        "port_losses",
        "avg_turns",
        "avg_assets",
        "avg_opponent_assets",
    ]
    with output_path.open("w", encoding="utf-8") as output_file:
        output_file.write(",".join(headers))
        output_file.write("\n")
        for row in rows:
            games = row["games"]
            values = [
                row["opponent"],
                games,
                row["wins"],
                row["losses"],
                row["draws"],
                f"{row['wins'] / games if games else 0:.6f}",
                row["port_wins"],
                row["port_losses"],
                f"{row['turns_total'] / games if games else 0:.6f}",
                f"{row['score_total'] / games if games else 0:.6f}",
                f"{row['opponent_score_total'] / games if games else 0:.6f}",
            ]
            output_file.write(",".join(str(value) for value in values))
            output_file.write("\n")


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


def evaluate_strategy(strategy, opponents, games_per_opponent, rng):
    stats = {
        "games": 0,
        "wins": 0,
        "draws": 0,
        "ports": 0,
        "score_total": 0,
        "opponent_score_total": 0,
        "turns_total": 0,
        "shipyard_started": 0,
        "shipyard_completed": 0,
        "fort_started": 0,
        "fort_completed": 0,
        "trade_guild_started": 0,
        "trade_guild_completed": 0,
        "fishing_dock_built": 0,
        "fishing_dock_active": 0,
        "fishing_boats_total": 0,
        "dry_dock_started": 0,
        "dry_dock_completed": 0,
        "damaged_ships_total": 0,
        "raid_actions_total": 0,
        "raid_damage_events_total": 0,
        "raid_repairs_total": 0,
        "damaged_raiders_sunk_total": 0,
        "guard_captain_games": 0,
        "guard_captains_total": 0,
        "port_losses": 0,
        "dominance_cap_penalty": 0,
        "matchup_floor_penalty": 0,
        "matchup_recovery_bonus": 0,
        "port_loss_pressure_penalty": 0,
        "survival_infra_bonus": 0,
        "min_matchup_win_rate": 1.0,
        "fitness": 0,
    }

    for opponent in opponents:
        matchup = {
            "games": 0,
            "wins": 0,
            "ports": 0,
        }
        matchup_fitness_start = stats["fitness"]
        for game_index in range(games_per_opponent):
            if game_index % 2 == 0:
                player_names = ["Evolving", opponent.name]
                strategies = [strategy, opponent]
                evolving_index = 0
            else:
                player_names = [opponent.name, "Evolving"]
                strategies = [opponent, strategy]
                evolving_index = 1

            game = SelfPlayGame(player_names, strategies, rng)
            result = game.play_silent()
            evolving_score = result["scores"][evolving_index]
            opponent_score = result["scores"][1 - evolving_index]
            margin = evolving_score - opponent_score
            capped_margin = clamp(margin, -50, 50)

            stats["games"] += 1
            matchup["games"] += 1
            stats["score_total"] += evolving_score
            stats["opponent_score_total"] += opponent_score
            stats["turns_total"] += result["turns"]
            stats["fitness"] += capped_margin
            player = game.players[evolving_index]
            if player.shipyard_started or player.shipyard_completed:
                stats["shipyard_started"] += 1
            if player.shipyard_completed:
                stats["shipyard_completed"] += 1
                stats["survival_infra_bonus"] += SURVIVAL_SHIPYARD_BONUS
                stats["fitness"] += SURVIVAL_SHIPYARD_BONUS
            if player.fort_started or player.fort_completed:
                stats["fort_started"] += 1
            if player.fort_completed:
                stats["fort_completed"] += 1
                stats["survival_infra_bonus"] += SURVIVAL_FORT_BONUS
                stats["fitness"] += SURVIVAL_FORT_BONUS
            if player.trade_guild_started or player.trade_guild_completed:
                stats["trade_guild_started"] += 1
            if player.trade_guild_completed:
                stats["trade_guild_completed"] += 1
            if player.fishing_dock_built:
                stats["fishing_dock_built"] += 1
            if player.fishing_dock_built and not player.fishing_dock_disabled:
                stats["fishing_dock_active"] += 1
            stats["fishing_boats_total"] += player.fishing_boats
            if player.dry_dock_started or player.dry_dock_completed:
                stats["dry_dock_started"] += 1
            if player.dry_dock_completed:
                stats["dry_dock_completed"] += 1
            stats["damaged_ships_total"] += player.damaged_ships
            stats["raid_actions_total"] += player.raid_actions_total
            stats["raid_damage_events_total"] += player.raid_damage_events
            stats["raid_repairs_total"] += player.raid_repairs_total
            stats["damaged_raiders_sunk_total"] += player.damaged_raiders_sunk
            if player.guard_captains:
                stats["guard_captain_games"] += 1
            stats["guard_captains_total"] += player.guard_captains
            captain_bonus = player.guard_captains * SURVIVAL_GUARD_CAPTAIN_BONUS
            stats["survival_infra_bonus"] += captain_bonus
            stats["fitness"] += captain_bonus

            if result["winner_index"] == evolving_index:
                stats["wins"] += 1
                matchup["wins"] += 1
                stats["fitness"] += 250
                if result["win_type"] == "port":
                    stats["ports"] += 1
                    matchup["ports"] += 1
                    stats["fitness"] += 40
            elif result["winner_index"] is None:
                stats["draws"] += 1
                stats["fitness"] += 30
            else:
                stats["fitness"] -= 250
                if result["win_type"] == "port":
                    stats["port_losses"] += 1
                    port_loss_penalty = 120 + PORT_LOSS_PRESSURE_PENALTY
                    stats["port_loss_pressure_penalty"] += PORT_LOSS_PRESSURE_PENALTY
                    stats["fitness"] -= port_loss_penalty

        matchup_fitness = stats["fitness"] - matchup_fitness_start
        apply_matchup_pressure(stats, matchup, matchup_fitness)

    apply_matchup_recovery_bonus(stats)
    return stats


def apply_matchup_pressure(stats, matchup, matchup_fitness):
    if matchup["games"] == 0:
        return

    win_rate = matchup["wins"] / matchup["games"]
    stats["min_matchup_win_rate"] = min(stats["min_matchup_win_rate"], win_rate)

    dominance_cap = matchup["games"] * DOMINANCE_CAP_PER_GAME
    dominance_cap_penalty = max(0, matchup_fitness - dominance_cap)

    floor_gap = max(0, MATCHUP_FLOOR_WIN_RATE - win_rate)
    floor_penalty = int(floor_gap * matchup["games"] * MATCHUP_FLOOR_PENALTY)

    stats["dominance_cap_penalty"] += dominance_cap_penalty
    stats["matchup_floor_penalty"] += floor_penalty
    stats["fitness"] -= dominance_cap_penalty + floor_penalty


def apply_matchup_recovery_bonus(stats):
    recovery_bonus = int(
        stats["min_matchup_win_rate"] * MATCHUP_FLOOR_RECOVERY_BONUS
    )
    stats["matchup_recovery_bonus"] = recovery_bonus
    stats["fitness"] += recovery_bonus


def passes_robustness_gate(current_stats, candidate_stats):
    current_min = current_stats.get("min_matchup_win_rate", 0)
    candidate_min = candidate_stats.get("min_matchup_win_rate", 0)
    fitness_gain = candidate_stats["fitness"] - current_stats["fitness"]
    regression = current_min - candidate_min

    if candidate_min >= current_min:
        return True
    if current_min >= MATCHUP_FLOOR_WIN_RATE and candidate_min >= MATCHUP_FLOOR_WIN_RATE:
        return True
    if regression <= ROBUSTNESS_ALLOWED_REGRESSION:
        return True
    if (
        candidate_min >= MATCHUP_FLOOR_WIN_RATE
        and fitness_gain >= ROBUSTNESS_REGRESSION_PREMIUM
    ):
        return True
    if (
        regression < ROBUSTNESS_CATASTROPHIC_REGRESSION
        and fitness_gain >= ROBUSTNESS_REGRESSION_PREMIUM
    ):
        return True
    return False


def train_evolving_strategy(
    generations=25,
    games_per_bot=6,
    learning_rate=0.25,
    mutation_scale=1.0,
    seed=None,
    output_path=None,
    graph_path=None,
    history_path=None,
    show_weights=False,
    weights_interval=1,
    dashboard=False,
    dashboard_history=12,
    dashboard_benchmark_games=100,
):
    learning_rate = clamp(learning_rate, 0.0, 1.0)
    rng = random.Random(seed)
    opponents = default_bot_strategies()
    current = None
    current_stats = None
    history = []
    terminal_settings = prepare_dashboard_terminal(dashboard)

    try:
        print(f"\n=== EVOLVING STRATEGY TRAINING: {generations} GENERATION(S) ===")
        if seed is not None:
            print(f"Seed: {seed}")
        print(f"Learning rate: {learning_rate}, mutation scale: {mutation_scale}")

        while True:
            current = random_evolving_strategy(rng)
            current_stats = evaluate_strategy(current, opponents, games_per_bot, rng)
            plateau_generations = 0
            dashboard_message = "Press h for controls."
            recent_lines = []
            if dashboard:
                recent_lines.append(training_status_line(0, "initial", current_stats))
                render_training_dashboard(
                    generation=0,
                    generations=generations,
                    status="initial",
                    stats=current_stats,
                    strategy=current,
                    recent_lines=recent_lines,
                    learning_rate=learning_rate,
                    mutation_scale=mutation_scale,
                    games_per_bot=games_per_bot,
                    plateau_generations=plateau_generations,
                    dashboard_message=dashboard_message,
                )
            else:
                print_evolving_strategy("Initial random strategy", current, current_stats)
            history = [
                training_history_record(
                    generation=0,
                    status="initial",
                    stats=current_stats,
                    strategy=current,
                )
            ]
            start_new_run = False

            for generation in range(1, generations + 1):
                if dashboard:
                    command_result = handle_dashboard_input(
                        rng,
                        opponents,
                        current,
                        current_stats,
                        learning_rate,
                        mutation_scale,
                        games_per_bot,
                    )
                    (
                        current,
                        current_stats,
                        learning_rate,
                        mutation_scale,
                        games_per_bot,
                        dashboard_message,
                        dashboard_command,
                    ) = command_result
                    if dashboard_command == "new":
                        start_new_run = True
                        break
                    if dashboard_command == "restart":
                        plateau_generations = 0
                        recent_lines.append(
                            training_status_line(generation - 1, "restart", current_stats)
                        )
                        recent_lines = recent_lines[-dashboard_history:]
                        render_training_dashboard(
                            generation=generation - 1,
                            generations=generations,
                            status="restart",
                            stats=current_stats,
                            strategy=current,
                            recent_lines=recent_lines,
                            learning_rate=learning_rate,
                            mutation_scale=mutation_scale,
                            games_per_bot=games_per_bot,
                            plateau_generations=plateau_generations,
                            dashboard_message=dashboard_message,
                        )

                candidate = mutate_strategy(current, rng, mutation_scale)
                candidate_stats = evaluate_strategy(candidate, opponents, games_per_bot, rng)

                if candidate_stats["fitness"] > current_stats["fitness"]:
                    if not passes_robustness_gate(current_stats, candidate_stats):
                        status = "fragile"
                    else:
                        blended = blend_strategy(current, candidate, learning_rate)
                        blended_stats = evaluate_strategy(blended, opponents, games_per_bot, rng)
                        if blended_stats["fitness"] > current_stats["fitness"]:
                            if passes_robustness_gate(current_stats, blended_stats):
                                current = blended
                                current_stats = blended_stats
                                status = "learned"
                            else:
                                status = "fragile"
                        else:
                            status = "kept"
                else:
                    status = "kept"

                if status == "learned":
                    plateau_generations = 0
                else:
                    plateau_generations += 1

                status_line = training_status_line(generation, status, current_stats)
                recent_lines.append(status_line)
                recent_lines = recent_lines[-dashboard_history:]
                if dashboard:
                    render_training_dashboard(
                        generation=generation,
                        generations=generations,
                        status=status,
                        stats=current_stats,
                        strategy=current,
                        recent_lines=recent_lines,
                        learning_rate=learning_rate,
                        mutation_scale=mutation_scale,
                        games_per_bot=games_per_bot,
                        plateau_generations=plateau_generations,
                        dashboard_message=dashboard_message,
                    )
                else:
                    print(status_line)
                    if should_print_live_weights(show_weights, weights_interval, generation, status):
                        print(f"         {strategy_compact_line(current)}")
                history.append(
                    training_history_record(
                        generation=generation,
                        status=status,
                        stats=current_stats,
                        strategy=current,
                    )
                )

            if start_new_run:
                continue

            if dashboard:
                finish_choice = wait_for_dashboard_finish_choice(
                    rng=rng,
                    opponents=opponents,
                    terminal_settings=terminal_settings,
                    generation=generations,
                    generations=generations,
                    stats=current_stats,
                    strategy=current,
                    recent_lines=recent_lines,
                    learning_rate=learning_rate,
                    mutation_scale=mutation_scale,
                    games_per_bot=games_per_bot,
                    plateau_generations=plateau_generations,
                    benchmark_games=dashboard_benchmark_games,
                    seed=seed,
                    history=history,
                )
                if finish_choice == "new":
                    continue
                break
            else:
                break
    finally:
        restore_dashboard_terminal(terminal_settings)

    if dashboard:
        print()
    print_evolving_strategy("Final evolved strategy", current, current_stats)
    if output_path is not None:
        write_evolved_strategy(current, current_stats, output_path, seed, history)
    if history_path is not None:
        write_training_history(history, history_path)
    if graph_path is not None:
        write_training_graph(history, graph_path)

    return current


def training_status_line(generation, status, stats):
    return (
        f"Gen {generation:>3}: {status:<7} "
        f"fitness {stats['fitness']:>7.1f}, "
        f"wins {stats['wins']:>3}/{stats['games']}, "
        f"min matchup {stats['min_matchup_win_rate'] * 100:>4.0f}%, "
        f"avg assets {average(stats, 'score_total'):>5.1f}"
    )


def should_print_live_weights(show_weights, weights_interval, generation, status):
    if not show_weights:
        return False
    if status == "learned":
        return True
    if weights_interval <= 0:
        return False
    return generation % weights_interval == 0


def strategy_compact_line(strategy):
    return (
        "weights "
        f"T/R/G/F={strategy.trade_weight:.2f}/"
        f"{strategy.raid_weight:.2f}/"
        f"{strategy.guard_weight:.2f}/"
        f"{strategy.fire_weight:.2f}; "
        "buy "
        f"convoy={strategy.convoy_bias:.2f}, "
        f"ship={strategy.ship_bias:.2f}; "
        "infra "
        f"yard={strategy.shipyard_bias:.2f}, "
        f"fort={strategy.fort_bias:.2f}, "
        f"guild={strategy.trade_guild_bias:.2f}, "
        f"dock={strategy.fishing_dock_bias:.2f}, "
        f"boat={strategy.fishing_boat_bias:.2f}, "
        f"dry={strategy.dry_dock_bias:.2f}, "
        f"repair={strategy.repair_bias:.2f}, "
        f"idle={strategy.construction_idle_bias:.2f}; "
        f"priority={strategy.build_priority}"
    )


def prepare_dashboard_terminal(dashboard):
    if not dashboard or not sys.stdin.isatty():
        return None
    settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    return settings


def restore_dashboard_terminal(settings):
    if settings is not None:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)


def handle_dashboard_input(
    rng,
    opponents,
    current,
    current_stats,
    learning_rate,
    mutation_scale,
    games_per_bot,
):
    key = read_dashboard_key()
    if key is None:
        return (
            current,
            current_stats,
            learning_rate,
            mutation_scale,
            games_per_bot,
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
    elif key == "r":
        current = random_evolving_strategy(rng)
        current_stats = evaluate_strategy(current, opponents, games_per_bot, rng)
        message = "restarted from a fresh random strategy"
        return (
            current,
            current_stats,
            learning_rate,
            mutation_scale,
            games_per_bot,
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
            "starting a new run",
            "new",
        )
    elif key == "h":
        message = "controls: [] lr, -/+ mutation, g/G games, r restart, n new run"
    else:
        message = f"ignored key {key!r}; press h for controls"

    return (
        current,
        current_stats,
        learning_rate,
        mutation_scale,
        games_per_bot,
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
    rng,
    opponents,
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
    seed,
    history,
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
                write_evolved_strategy(strategy, stats, output_path, seed, history)
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
            )
            benchmark_rows = benchmark_strategy(strategy, opponents, benchmark_games, rng)
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


def benchmark_strategy(strategy, opponents, games_per_opponent, rng):
    return [
        evaluate_head_to_head(strategy, opponent, games_per_opponent, rng)
        for opponent in opponents
    ]


def gauge(value, minimum, maximum, width=18):
    if maximum <= minimum:
        ratio = 0.0
    else:
        ratio = (value - minimum) / (maximum - minimum)
    ratio = clamp(ratio, 0.0, 1.0)
    filled = round(ratio * width)
    return "[" + "#" * filled + "." * (width - filled) + "]"


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
):
    print("\033[2J\033[H", end="")
    print(f"=== EVOLVING STRATEGY DASHBOARD ({generation}/{generations}) ===")
    win_rate = stats["wins"] / stats["games"] if stats["games"] else 0
    min_matchup = stats.get("min_matchup_win_rate", 0)
    avg_assets = average(stats, "score_total")
    print(
        f"status={status}  "
        f"plateau={plateau_generations} gen  "
        f"fitness={stats['fitness']:.1f}  "
        f"wins={stats['wins']}/{stats['games']} ({win_rate * 100:.1f}%)  "
        f"min={min_matchup * 100:.1f}%  "
        f"assets={avg_assets:.1f}  "
        f"opp={average(stats, 'opponent_score_total'):.1f}"
    )
    print(
        f"knobs: lr={learning_rate:.2f}  mutation={mutation_scale:.2f}  "
        f"games/opponent={games_per_bot}  message={dashboard_message}"
    )
    print(
        f"gauges: win {gauge(win_rate, 0, 1)}  "
        f"min {gauge(min_matchup, 0, 1)}  "
        f"plateau {gauge(min(plateau_generations, 100), 0, 100)}"
    )
    print(
        f"ports={stats['ports']}  "
        f"port_losses={stats.get('port_losses', 0)}  "
        f"damage={average(stats, 'raid_damage_events_total'):.1f}/game  "
        f"repairs={average(stats, 'raid_repairs_total'):.1f}/game  "
        f"sunk_damaged={average(stats, 'damaged_raiders_sunk_total'):.1f}/game"
    )
    print()
    print(
        "orders: "
        f"trade={strategy.trade_weight:.2f}  "
        f"raid={strategy.raid_weight:.2f}  "
        f"guard={strategy.guard_weight:.2f}  "
        f"fire={strategy.fire_weight:.2f}"
    )
    print(
        "buy:    "
        f"convoy={strategy.convoy_bias:.2f}  "
        f"ship={strategy.ship_bias:.2f}  "
        f"idle={strategy.construction_idle_bias:.2f}  "
        f"repair={strategy.repair_bias:.2f}"
    )
    print(
        "infra:  "
        f"yard={strategy.shipyard_bias:.2f}  "
        f"fort={strategy.fort_bias:.2f}  "
        f"guild={strategy.trade_guild_bias:.2f}  "
        f"captain={strategy.guard_captain_bias:.2f}  "
        f"fire_plans={strategy.fire_plans_bias:.2f}"
    )
    print(
        "econ:   "
        f"fishing_dock={strategy.fishing_dock_bias:.2f}  "
        f"boat={strategy.fishing_boat_bias:.2f}  "
        f"dry_dock={strategy.dry_dock_bias:.2f}"
    )
    print(f"priority: {strategy.build_priority}")
    print()
    if finished:
        print("controls: b benchmark  w write file  s save+exit  n new run")
    else:
        print("controls: [] lr  -/+ mutation  g/G games  r restart  n new run  h help")
    print("recent:")
    for line in recent_lines:
        print(f"  {line}")
    if finished:
        print()
        print(f"benchmark games/opponent: {benchmark_games}")
        if benchmark_rows is None:
            print("benchmark: not run yet")
        else:
            print("benchmark:")
            for line in dashboard_benchmark_lines(benchmark_rows):
                print(f"  {line}")
    print(flush=True)


def dashboard_benchmark_lines(rows, weakest_count=8):
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
            "score_total",
            "opponent_score_total",
        ]:
            total[key] += row[key]

    total_games = total["games"]
    total_win_rate = total["wins"] / total_games if total_games else 0
    total_avg_assets = total["score_total"] / total_games if total_games else 0
    lines = [
        f"TOTAL {total['wins']}/{total_games} "
        f"({total_win_rate * 100:.1f}%)  "
        f"port losses {total['port_losses']}  "
        f"avg assets {total_avg_assets:.1f}"
    ]

    weakest = sorted(
        rows,
        key=lambda row: (
            row["wins"] / row["games"] if row["games"] else 0,
            -row["port_losses"],
        ),
    )[:weakest_count]
    for row in weakest:
        games = row["games"]
        win_rate = row["wins"] / games if games else 0
        avg_assets = row["score_total"] / games if games else 0
        lines.append(
            f"{row['opponent']:<15} {win_rate * 100:>5.1f}%  "
            f"W/L/D {row['wins']}/{row['losses']}/{row['draws']}  "
            f"PL {row['port_losses']}  assets {avg_assets:.1f}"
        )
    return lines


def print_evolving_strategy(label, strategy, stats):
    print(f"\n{label}:")
    print(
        f"  weights: trade={strategy.trade_weight:.2f}, "
        f"raid={strategy.raid_weight:.2f}, guard={strategy.guard_weight:.2f}, "
        f"fire={strategy.fire_weight:.2f}"
    )
    print(
        f"  buy: build_priority={strategy.build_priority}, "
        f"convoy_bias={strategy.convoy_bias:.2f}, ship_bias={strategy.ship_bias:.2f}"
    )
    print(
        f"  infrastructure: shipyard={strategy.shipyard_bias:.2f}, "
        f"fort={strategy.fort_bias:.2f}, "
        f"trade_guild={strategy.trade_guild_bias:.2f}, "
        f"guard_captain={strategy.guard_captain_bias:.2f}, "
        f"fire_plans={strategy.fire_plans_bias:.2f}, "
        f"fishing_dock={strategy.fishing_dock_bias:.2f}, "
        f"fishing_boat={strategy.fishing_boat_bias:.2f}, "
        f"dry_dock={strategy.dry_dock_bias:.2f}, "
        f"repair={strategy.repair_bias:.2f}, "
        f"idle={strategy.construction_idle_bias:.2f}"
    )
    print(
        f"  results: fitness={stats['fitness']:.1f}, "
        f"wins={stats['wins']}/{stats['games']}, draws={stats['draws']}, "
        f"port wins={stats['ports']}, port losses={stats.get('port_losses', 0)}, "
        f"min matchup={stats.get('min_matchup_win_rate', 0) * 100:.1f}%, "
        f"avg turns={average(stats, 'turns_total'):.1f}, "
        f"avg assets={average(stats, 'score_total'):.1f}, "
        f"avg opponent={average(stats, 'opponent_score_total'):.1f}"
    )
    print(
        f"  matchup pressure: dominance cap={stats.get('dominance_cap_penalty', 0)}, "
        f"floor penalty={stats.get('matchup_floor_penalty', 0)}, "
        f"recovery bonus={stats.get('matchup_recovery_bonus', 0)}"
    )
    print(
        f"  survival pressure: port loss penalty="
        f"{stats.get('port_loss_pressure_penalty', 0)}, "
        f"infra bonus={stats.get('survival_infra_bonus', 0)}"
    )
    print(
        f"  infra use: forts {stats.get('fort_completed', 0)}/{stats['games']}, "
        f"shipyards {stats.get('shipyard_completed', 0)}/{stats['games']}, "
        f"guilds {stats.get('trade_guild_completed', 0)}/{stats['games']}, "
        f"fishing docks {stats.get('fishing_dock_active', 0)}/{stats['games']}, "
        f"dry docks {stats.get('dry_dock_completed', 0)}/{stats['games']}, "
        f"boats avg {average(stats, 'fishing_boats_total'):.1f}, "
        f"raid actions avg {average(stats, 'raid_actions_total'):.1f}, "
        f"damage events avg {average(stats, 'raid_damage_events_total'):.1f}, "
        f"repairs avg {average(stats, 'raid_repairs_total'):.1f}, "
        f"sunk damaged avg {average(stats, 'damaged_raiders_sunk_total'):.1f}, "
        f"damaged avg {average(stats, 'damaged_ships_total'):.1f}, "
        f"captains {stats.get('guard_captain_games', 0)}/{stats['games']} "
        f"(avg {average(stats, 'guard_captains_total'):.1f})"
    )


def average(stats, key):
    if stats["games"] == 0:
        return 0
    return stats[key] / stats["games"]


def training_history_record(generation, status, stats, strategy):
    return {
        "generation": generation,
        "status": status,
        "fitness": stats["fitness"],
        "games": stats["games"],
        "wins": stats["wins"],
        "draws": stats["draws"],
        "port_wins": stats["ports"],
        "port_losses": stats.get("port_losses", 0),
        "dominance_cap_penalty": stats.get("dominance_cap_penalty", 0),
        "matchup_floor_penalty": stats.get("matchup_floor_penalty", 0),
        "matchup_recovery_bonus": stats.get("matchup_recovery_bonus", 0),
        "port_loss_pressure_penalty": stats.get("port_loss_pressure_penalty", 0),
        "survival_infra_bonus": stats.get("survival_infra_bonus", 0),
        "min_matchup_win_rate": stats.get("min_matchup_win_rate", 0),
        "win_rate": stats["wins"] / stats["games"] if stats["games"] else 0,
        "avg_turns": average(stats, "turns_total"),
        "avg_assets": average(stats, "score_total"),
        "avg_opponent_assets": average(stats, "opponent_score_total"),
        "shipyard_started_rate": average(stats, "shipyard_started"),
        "shipyard_completed_rate": average(stats, "shipyard_completed"),
        "fort_started_rate": average(stats, "fort_started"),
        "fort_completed_rate": average(stats, "fort_completed"),
        "trade_guild_started_rate": average(stats, "trade_guild_started"),
        "trade_guild_completed_rate": average(stats, "trade_guild_completed"),
        "fishing_dock_built_rate": average(stats, "fishing_dock_built"),
        "fishing_dock_active_rate": average(stats, "fishing_dock_active"),
        "avg_fishing_boats": average(stats, "fishing_boats_total"),
        "dry_dock_started_rate": average(stats, "dry_dock_started"),
        "dry_dock_completed_rate": average(stats, "dry_dock_completed"),
        "avg_damaged_ships": average(stats, "damaged_ships_total"),
        "avg_raid_actions": average(stats, "raid_actions_total"),
        "avg_raid_damage_events": average(stats, "raid_damage_events_total"),
        "avg_raid_repairs": average(stats, "raid_repairs_total"),
        "avg_damaged_raiders_sunk": average(stats, "damaged_raiders_sunk_total"),
        "guard_captain_rate": average(stats, "guard_captain_games"),
        "avg_guard_captains": average(stats, "guard_captains_total"),
        "strategy": strategy_record(strategy),
    }


def write_evolved_strategy(strategy, stats, output_path, seed, history=None):
    output_path = Path(output_path)
    if output_path.parent != Path("."):
        output_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "rules_version": Rules.VERSION,
        "seed": seed,
        "strategy": strategy_record(strategy),
        "training_results": stats,
    }
    if history is not None:
        record["history"] = history

    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(record, output_file, indent=2, sort_keys=True)
        output_file.write("\n")

    print(f"\nEvolved strategy written to {output_path}.")


def write_training_history(history, history_path):
    history_path = Path(history_path)
    if history_path.parent != Path("."):
        history_path.parent.mkdir(parents=True, exist_ok=True)

    if history_path.suffix.lower() == ".csv":
        write_training_history_csv(history, history_path)
    else:
        with history_path.open("w", encoding="utf-8") as history_file:
            json.dump(history, history_file, indent=2, sort_keys=True)
            history_file.write("\n")

    print(f"Training history written to {history_path}.")


def write_training_history_csv(history, history_path):
    headers = [
        "generation",
        "status",
        "fitness",
        "games",
        "wins",
        "draws",
        "port_wins",
        "port_losses",
        "dominance_cap_penalty",
        "matchup_floor_penalty",
        "matchup_recovery_bonus",
        "port_loss_pressure_penalty",
        "survival_infra_bonus",
        "min_matchup_win_rate",
        "win_rate",
        "avg_turns",
        "avg_assets",
        "avg_opponent_assets",
        "shipyard_started_rate",
        "shipyard_completed_rate",
        "fort_started_rate",
        "fort_completed_rate",
        "trade_guild_started_rate",
        "trade_guild_completed_rate",
        "fishing_dock_built_rate",
        "fishing_dock_active_rate",
        "avg_fishing_boats",
        "dry_dock_started_rate",
        "dry_dock_completed_rate",
        "avg_damaged_ships",
        "avg_raid_actions",
        "avg_raid_damage_events",
        "avg_raid_repairs",
        "avg_damaged_raiders_sunk",
        "guard_captain_rate",
        "avg_guard_captains",
        "trade_weight",
        "raid_weight",
        "guard_weight",
        "fire_weight",
        "convoy_bias",
        "ship_bias",
        "shipyard_bias",
        "fort_bias",
        "trade_guild_bias",
        "fishing_dock_bias",
        "fishing_boat_bias",
        "dry_dock_bias",
        "repair_bias",
        "guard_captain_bias",
        "fire_plans_bias",
        "construction_idle_bias",
        "build_priority",
    ]
    with history_path.open("w", encoding="utf-8") as history_file:
        history_file.write(",".join(headers))
        history_file.write("\n")
        for row in history:
            strategy = row["strategy"]
            values = [
                row["generation"],
                row["status"],
                row["fitness"],
                row["games"],
                row["wins"],
                row["draws"],
                row["port_wins"],
                row["port_losses"],
                row["dominance_cap_penalty"],
                row["matchup_floor_penalty"],
                row["matchup_recovery_bonus"],
                row["port_loss_pressure_penalty"],
                row["survival_infra_bonus"],
                f"{row['min_matchup_win_rate']:.6f}",
                f"{row['win_rate']:.6f}",
                f"{row['avg_turns']:.6f}",
                f"{row['avg_assets']:.6f}",
                f"{row['avg_opponent_assets']:.6f}",
                f"{row['shipyard_started_rate']:.6f}",
                f"{row['shipyard_completed_rate']:.6f}",
                f"{row['fort_started_rate']:.6f}",
                f"{row['fort_completed_rate']:.6f}",
                f"{row['trade_guild_started_rate']:.6f}",
                f"{row['trade_guild_completed_rate']:.6f}",
                f"{row['fishing_dock_built_rate']:.6f}",
                f"{row['fishing_dock_active_rate']:.6f}",
                f"{row['avg_fishing_boats']:.6f}",
                f"{row['dry_dock_started_rate']:.6f}",
                f"{row['dry_dock_completed_rate']:.6f}",
                f"{row['avg_damaged_ships']:.6f}",
                f"{row['avg_raid_actions']:.6f}",
                f"{row['avg_raid_damage_events']:.6f}",
                f"{row['avg_raid_repairs']:.6f}",
                f"{row['avg_damaged_raiders_sunk']:.6f}",
                f"{row['guard_captain_rate']:.6f}",
                f"{row['avg_guard_captains']:.6f}",
                f"{strategy['trade_weight']:.6f}",
                f"{strategy['raid_weight']:.6f}",
                f"{strategy['guard_weight']:.6f}",
                f"{strategy['fire_weight']:.6f}",
                f"{strategy['convoy_bias']:.6f}",
                f"{strategy['ship_bias']:.6f}",
                f"{strategy['shipyard_bias']:.6f}",
                f"{strategy['fort_bias']:.6f}",
                f"{strategy['trade_guild_bias']:.6f}",
                f"{strategy['fishing_dock_bias']:.6f}",
                f"{strategy['fishing_boat_bias']:.6f}",
                f"{strategy['dry_dock_bias']:.6f}",
                f"{strategy['repair_bias']:.6f}",
                f"{strategy['guard_captain_bias']:.6f}",
                f"{strategy['fire_plans_bias']:.6f}",
                f"{strategy['construction_idle_bias']:.6f}",
                "|".join(strategy["build_priority"]),
            ]
            history_file.write(",".join(str(value) for value in values))
            history_file.write("\n")


def write_training_graph(history, graph_path):
    graph_path = Path(graph_path)
    if graph_path.parent != Path("."):
        graph_path.parent.mkdir(parents=True, exist_ok=True)

    svg = training_graph_svg(history)
    with graph_path.open("w", encoding="utf-8") as graph_file:
        graph_file.write(svg)

    print(f"Training graph written to {graph_path}.")


def training_graph_svg(history):
    width = 900
    height = 520
    left = 70
    right = 30
    top = 40
    bottom = 70
    chart_width = width - left - right
    chart_height = height - top - bottom
    max_generation = max(row["generation"] for row in history) or 1

    points = []
    for row in history:
        x = left + (row["generation"] / max_generation) * chart_width
        y = top + (1.0 - row["win_rate"]) * chart_height
        points.append((x, y))

    point_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    circles = "\n".join(
        (
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4">'
            f"<title>Generation {row['generation']}: "
            f"{row['win_rate'] * 100:.1f}% win rate, "
            f"fitness {row['fitness']:.1f}</title></circle>"
        )
        for (x, y), row in zip(points, history)
    )
    labels = svg_axis_labels(left, top, chart_width, chart_height, max_generation)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <style>
    text {{ font-family: Arial, sans-serif; fill: #1f2933; }}
    .axis {{ stroke: #1f2933; stroke-width: 2; }}
    .grid {{ stroke: #d8dee9; stroke-width: 1; }}
    polyline {{ fill: none; stroke: #0b6bcb; stroke-width: 3; }}
    circle {{ fill: #0b6bcb; stroke: white; stroke-width: 2; }}
  </style>
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="{width / 2:.0f}" y="24" text-anchor="middle" font-size="20" font-weight="700">Evolving Strategy Win Rate</text>
  <line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + chart_height}"/>
  <line class="axis" x1="{left}" y1="{top + chart_height}" x2="{left + chart_width}" y2="{top + chart_height}"/>
  {labels}
  <polyline points="{point_text}"/>
  {circles}
  <text x="{left + chart_width / 2:.0f}" y="{height - 20}" text-anchor="middle" font-size="14">Generation</text>
  <text x="20" y="{top + chart_height / 2:.0f}" text-anchor="middle" font-size="14" transform="rotate(-90 20 {top + chart_height / 2:.0f})">Win rate</text>
</svg>
"""


def svg_axis_labels(left, top, chart_width, chart_height, max_generation):
    labels = []
    for step in range(0, 6):
        rate = step / 5
        y = top + (1 - rate) * chart_height
        labels.append(
            f'<line class="grid" x1="{left}" y1="{y:.1f}" '
            f'x2="{left + chart_width}" y2="{y:.1f}"/>'
        )
        labels.append(
            f'<text x="{left - 10}" y="{y + 5:.1f}" text-anchor="end" '
            f'font-size="12">{rate * 100:.0f}%</text>'
        )

    for step in range(0, 6):
        generation = round(max_generation * step / 5)
        x = left + (generation / max_generation) * chart_width
        labels.append(
            f'<text x="{x:.1f}" y="{top + chart_height + 22}" '
            f'text-anchor="middle" font-size="12">{generation}</text>'
        )

    return "\n  ".join(labels)


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


def run_self_play(games=100, seed=None):
    rng = random.Random(seed)
    strategies = default_bot_strategies()
    stats = defaultdict(
        lambda: {
            "games": 0,
            "wins": 0,
            "draws": 0,
            "ports": 0,
            "turns_total": 0,
            "score_total": 0,
            "ships_total": 0,
        }
    )

    for _ in range(games):
        chosen = [rng.choice(strategies), rng.choice(strategies)]
        game = SelfPlayGame(["Bot A", "Bot B"], chosen, rng)
        result = game.play_silent()

        for index, strategy in enumerate(chosen):
            row = stats[strategy.name]
            row["games"] += 1
            row["turns_total"] += result["turns"]
            row["score_total"] += result["scores"][index]
            row["ships_total"] += result["ships"][index]

            if result["winner_index"] == index:
                row["wins"] += 1
                if result["win_type"] == "port":
                    row["ports"] += 1
            elif result["winner_index"] is None:
                row["draws"] += 1

    print_self_play_report(games, seed, stats)


def print_self_play_report(games, seed, stats):
    print(f"\n=== SELF-PLAY REPORT: {games} GAME(S) ===")
    if seed is not None:
        print(f"Seed: {seed}")

    rows = []
    for name, row in stats.items():
        games_played = row["games"]
        win_rate = row["wins"] / games_played if games_played else 0
        avg_turns = row["turns_total"] / games_played if games_played else 0
        avg_score = row["score_total"] / games_played if games_played else 0
        avg_ships = row["ships_total"] / games_played if games_played else 0
        rows.append((win_rate, avg_score, avg_ships, avg_turns, name, row))

    rows.sort(reverse=True)
    print(
        "\nStrategy         Games  Wins  Draws  Port wins  Win rate  "
        "Avg turns  Avg assets  Avg ships"
    )
    print(
        "---------------  -----  ----  -----  ---------  --------  "
        "---------  ----------  ---------"
    )
    for win_rate, avg_score, avg_ships, avg_turns, name, row in rows:
        print(
            f"{name:<15}  {row['games']:>5}  {row['wins']:>4}  "
            f"{row['draws']:>5}  {row['ports']:>9}  "
            f"{win_rate * 100:>7.1f}%  {avg_turns:>9.1f}  "
            f"{avg_score:>10.1f}  {avg_ships:>9.1f}"
        )

    if not rows:
        return

    best = rows[0]
    print("\nHuman-facing lessons:")
    print(
        f"- Best bot archetype: {best[4]} "
        f"({best[0] * 100:.1f}% win rate, {best[1]:.1f} average assets)."
    )
    print(
        "- Watch convoy timing: bots that raid at-sea treasure and payroll "
        "swing games hard."
    )
    print(
        "- Early shipyards usually matter because cheaper ships compound over "
        "the full year."
    )
    print(
        "- Guards are most valuable when protecting payroll or treasure, not "
        "as a permanent default."
    )
    print(
        "- If the opponent neglects ships, concentrated raids can threaten "
        "a sudden port kill."
    )
