# bot_runtime.py
"""This module contains classes and functions for running games against the AI and simulating self-play scenarios. 
It includes functionality for recording game details, summarizing results, and integrating with bot strategies during gameplay. 
Key components include the PlayVsAIGame and SelfPlayGame classes, as well as functions for recording and summarizing AI game outcomes.

Classes:
- SelfPlayGame: A class for simulating games between two bot strategies without human interaction, used for benchmarking and training.
- PlayVsAIGame: A class for simulating a game between a human player and an AI bot, including functionality for prompting the human for input and recording the
  game details.
  Functions:
  - play_vs_ai: A function to run a game against the AI using a specified strategy and record the results.
  - summarize_ai_games: A function to read recorded AI game logs and summarize the outcomes by strategy.
  - write_ai_game_record: A function to write a detailed record of an AI game to a log file in JSON format.
  - build_ai_game_record: A function to construct a structured record of an AI game, including player details, game outcome, and turn-by-turn snapshots.
  - ai_game_winner: A function to determine the winner of an AI game based on the game state.
  - ai_game_win_type: A function to determine the type of win (port kill, asset victory, or draw) in an AI game.
  - player_record: A function to create a structured record of a player's state at the end of an AI game, including resources
    and assets.
  - snapshot_record: A function to create a structured record of the game state at a specific snapshot, including player details and allocations.
  - value_record: A helper function to convert complex values (like Allocations) into a serializable format for recording.
"""

# Imports
import contextlib
import io
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from game_engine import Game
from game_state import Allocation, Rules
from bot_roster import default_bot_strategies, find_strategy


AI_GAME_LOG_PATH = Path("artifacts/logs/ai_game_log.jsonl")


class SelfPlayGame(Game):
    """Simulates a game between two bot strategies without human interaction, used for benchmarking and training. The game runs silently without printing output, and returns a structured result at the end.
    Attributes:
    - player_names (list): A list of two strings representing the names of the players (e.g., "Bot A" and "Bot B").
    - strategies (list): A list of two BotStrategy instances representing the strategies used by each bot player.
    - rng (random.Random): A random number generator instance used for any stochastic decisions made by the bot strategies during the game.
    Methods:
    - play_silent(): Runs the game without printing any output, simulating turns until the game ends. Returns a structured result containing the winner, win type, turns taken, final scores, and ships for each player.
    - play_bot_turn(): Executes a single turn for both bot players, including choosing allocations, observing opponent openings, resolving orders, advancing convoys, applying supply and port labor, and running the buy phase for each bot strategy.
    - result(): Determines the winner of the game based on the final game state, including checking for port destruction and comparing asset scores. Returns a dictionary containing the winner index, win type, turns taken, final scores, and ships for each player.
    - clear_between_players(): A placeholder method that can be used to clear any temporary state between player turns if needed.
    - wants_emergency_supply_warchest(): A method that allows bot strategies to decide whether they want to use an emergency supply warchest based on the current game state and their strategy's logic.
    """
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

        self.advance_convoys()
        self.apply_supply()
        self.apply_port_labor()
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

    def wants_emergency_supply_warchest(
        # TODO: Likely to be legacy with the enforced autopay system below 0 supply
        self,
        player,
        need,
        counted_income,
        covered,
        cost,
    ):
        strategy = self.strategies[self.players.index(player)]
        return strategy.wants_emergency_supply_warchest(
            player,
            need,
            counted_income,
            covered,
            cost,
        )


class PlayVsAIGame(Game):
    """ 
    Simulates a game between a human player and an AI bot, including functionality for prompting the human for input and recording the game details. The game includes methods for playing turns, handling the buy phase, and recording turn-by-turn snapshots of the game state for later analysis.
    Attributes:
    - human (Player): The human player participating in the game.
    - ai (Player): The AI bot player participating in the game.
    - strategy (BotStrategy): The strategy used by the AI bot during the game.
    - rng (random.Random): A random number generator instance used for any stochastic decisions made by the AI bot strategy during the game.
    - turn_records (list): A list that stores detailed records of each turn in the game, including snapshots of the game state before and after orders are resolved
      and the orders themselves. This is used for later analysis and recording of the game.
    Methods:
    - play_turn(): Executes a single turn of the game, including prompting the human for their allocation, having the AI choose its allocation based on its strategy, resolving orders, advancing convoys,
      applying supply and port labor, and handling the buy phase for both players. It also records snapshots of the game state at key points during the turn for later analysis.
    - buy_phase(): Handles the buy phase of the turn for both the human and AI players, including prompting the human for purchases and having the AI execute its buy phase based on its strategy.
    - wants_emergency_supply_warchest(): A method that allows the AI strategy to decide whether it wants to use an emergency supply warchest based on the current game state and its strategy's logic. The human player can also be prompted for this decision if needed.
    - record_turn(): A helper method to record the details of a turn, including snapshots of the game state before and after orders are resolved, and the orders themselves. This information is stored in the turn_records list for later analysis and recording of the game.
    """
    def __init__(self, human_name, strategy, rng):
        """Initializes a PlayVsAIGame instance with a human player and an AI bot using the specified strategy and random seed.
        Args:    human_name (str): The name of the human player (e.g., "England").
                strategy (BotStrategy): The BotStrategy instance representing the AI bot's strategy for the game.
                rng (random.Random): A random number generator instance initialized with a specific seed 
                for reproducibility of any stochastic decisions made by the AI bot during the game.
        """
        super().__init__([human_name, f"AI {strategy.name}"])
        self.human = self.players[0]
        self.ai = self.players[1]
        self.strategy = strategy
        self.rng = rng
        self.turn_records = []

    def play_turn(self):
        """
        Executes a single turn of the game, including prompting the human for their allocation, having the AI choose its allocation based on its strategy, resolving orders, advancing convoys, applying supply and port labor, and handling the buy phase for both players. It also records snapshots of the game state at key points during the turn for later analysis.
        The method follows these steps:
        1. Clears the screen and displays the current turn and game state.
        2. Prompts the human player for their allocation for the turn.
        3. The AI bot chooses its allocation based on its strategy and the current game state.
        4. Both the human and AI strategies observe the opponent's opening allocation for potential strategic adjustments.
        5. Resolves the orders for the turn and checks if the game is over after resolution.
        6. If the game is not over, advances convoys, applies supply, and applies port labor effects.
        7. Handles the buy phase for both the human and AI players, including prompting the human for purchases and having the AI execute its buy phase based on its strategy.
        8. Records snapshots of the game state before and after orders are resolved, as"""
        from game_state import UI

        UI.clear_screen()
        self.orders_submitted_count = 0
        self.show_header("Orders")
        self.show_state()
        before_snapshot = self.snapshot_turn()

        self.human.allocation = self.prompt_allocation(self.human)
        self.orders_submitted_count = 1
        print(f"\n{self.ai.name} writes sealed orders.")
        self.ai.allocation = self.strategy.choose_allocation(
            self, self.ai, self.human, self.rng
        )
        self.orders_submitted_count = 2
        self.strategy.observe_opponent_opening(self, self.ai, self.human)

        orders_snapshot = self.snapshot_turn()
        self.reveal_orders()
        self.show_bulletin("Resolution", self.resolve_orders)
        if self.game_over:
            after_snapshot = self.snapshot_turn()
            self.record_turn(before_snapshot, orders_snapshot, after_snapshot)
            return
        self.pause_after_resolution()
        self.show_bulletin("Convoy Arrivals", self.advance_convoys)
        self.show_bulletin("Supply", self.apply_supply)
        self.show_bulletin("Port Labor", self.apply_port_labor)
        self.buy_phase()
        after_snapshot = self.snapshot_turn()
        self.record_turn(before_snapshot, orders_snapshot, after_snapshot)
        self.show_turn_summary(before_snapshot, after_snapshot, orders_snapshot)

    def buy_phase(self):
        """
        Handles the buy phase of the turn for both the human and AI players, including prompting the human for purchases and having the AI execute its buy phase based on its strategy. The method follows these steps:
        1. Prompts the human player to make purchases during the buy phase, allowing them to buy gold, ships, and various upgrades based on their current resources and needs.
        2. Records a baseline snapshot of the human player's state before the AI's buy phase for later comparison.
        3. The AI bot executes its buy phase based on its strategy, making purchases and upgrades as determined by the strategy's logic and the current game state.
        4. Records a snapshot of the AI player's state after the buy phase to compare against the baseline and determine what purchases were made.
        5. Displays a summary of the AI's purchases and changes to its state during the buy phase, highlighting any visible changes in resources, assets, and statuses.
        6. Prompts the user to review the AI's buy phase changes before continuing to the next turn.
        """
        self.buy_phase_baselines = {self.human: self.snapshot_player(self.human)}
        self.run_buy_menu(self.human)
        from game_state import UI

        before = self.snapshot_player(self.ai)
        self.buy_phase_baselines = {self.ai: before}
        self.strategy.run_buy_phase(self, self.ai, self.human, self.rng)
        after = self.snapshot_player(self.ai)
        lines = [f"{self.ai.name} takes its buy phase."]
        self.add_status_change(lines, "Gold", before, after, "gold")
        self.add_status_change(lines, "Ships", before, after, "ships")
        self.add_status_change(lines, "Shipyard", before, after, "shipyard_status")
        self.add_status_change(lines, "Fort", before, after, "fort_status")
        self.add_status_change(lines, "Trade guild", before, after, "trade_guild_status")
        self.add_status_change(lines, "Fishing", before, after, "fishing_status")
        self.add_status_change(lines, "Supply", before, after, "supply_status")
        self.add_status_change(lines, "Raid fatigue", before, after, "raid_fatigue_status")
        self.add_status_change(lines, "Dry dock", before, after, "dry_dock_status")
        self.add_status_change(lines, "Fire ships", before, after, "fire_ship_status")
        self.add_status_change(lines, "Guard captains", before, after, "guard_captain_status")
        if len(lines) == 1:
            lines.append("No visible purchases.")
        self.render_play_area(
            phase="AI Buy Phase",
            control_lines=["AI completed its buy phase.", "Review the changes."],
            info_lines=lines,
            info_title="AI Harbor Report",
            clear=True,
            include_state=True,
        )
        input("Press Enter to continue...")
        self.buy_phase_baselines = {}
        UI.clear_screen()
        self.show_state()

    def wants_emergency_supply_warchest(
        # TODO: Likely to be legacy with the enforced autopay system below 0 supply
        self,
        player,
        need,
        counted_income,
        covered,
        cost,
    ):
        if player is self.ai:
            return self.strategy.wants_emergency_supply_warchest(
                player,
                need,
                counted_income,
                covered,
                cost,
            )
        return super().wants_emergency_supply_warchest(
            player,
            need,
            counted_income,
            covered,
            cost,
        )

    def record_turn(self, before_snapshot, orders_snapshot, after_snapshot):
        """
        A helper method to record the details of a turn, including snapshots
        of the game state before and after orders are resolved, and the orders 
        themselves. This information is stored in the turn_records list for 
        later analysis and recording of the game.
        Args: 
            before_snapshot (dict): A snapshot of the game state before orders are resolved, including player details and allocations.
            orders_snapshot (dict): A snapshot of the game state after orders are revealed but before resolution, including player details and allocations.
            after_snapshot (dict): A snapshot of the game state after orders are resolved, including player details and allocations.
            
        Returns:    
            None: This method does not return any value but updates the turn_records attribute of the PlayVsAIGame instance with the details of the turn.
        """
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
    """
    Writes a detailed record of an AI game to a log file in JSON format. The record includes information about the game outcome, player states, and turn-by-turn snapshots for later analysis.
    Args:    game (PlayVsAIGame): The instance of the PlayVsAIGame that was played, containing all the details of the game state and turn records.
        strategy (BotStrategy): The BotStrategy instance representing the AI bot's strategy used in the game.
        seed (int): The random seed used for the game, allowing for reproducibility of the game if needed.
        log_path (str or Path): The file path where the game record should be saved. The record is appended to the file in JSON Lines format, allowing for multiple game records to be stored in the same file.
    Returns:    
        None: This function writes the game record to the specified log file and does not return any value.
    """
    log_path = Path(log_path)
    record = build_ai_game_record(game, strategy, seed)
    if log_path.parent != Path("."):
        log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, sort_keys=True))
        log_file.write("\n")

    print(f"\nAI game recorded in {log_path}.")


def build_ai_game_record(game, strategy, seed):
    """
    Constructs a structured record of an AI game,
    including player details, game outcome, 
    and turn-by-turn snapshots. This record is used 
    for logging the game in JSON format for later analysis.
    """
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
    """Determines the winner of an AI game based on the game state, 
    including checking for port destruction and comparing asset scores. 
    
    Args:    
        game (PlayVsAIGame): The instance of the PlayVsAIGame that was played, containing all the details of the game state.
    Returns:
        str: A string indicating the winner of the game, 
            which can be "human" if the human player won, "ai" if the AI bot won, or "draw" if the game ended in a tie based on asset scores.
    """
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
    """
    Determines the type of win (port kill, asset victory, or draw) in an AI game based on the game state.
    Args:    
        game (PlayVsAIGame): The instance of the PlayVsAIGame that was played, containing all the details of the game state.
    Returns:    
        str: A string indicating the type of win, which can be "port" if the win was achieved by destroying the opponent's port, "assets" if the win was achieved by having a higher asset score at the end of the game, or "draw" if the game ended in a tie based on asset scores.
    """
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
        "supply": player.supply,
        "supply_need": player.supply_need,
        "supply_crises": player.supply_crises,
        "supply_desertions_total": player.supply_desertions_total,
        "supply_unrest_burns": player.supply_unrest_burns,
        "supply_fishing_losses": player.supply_fishing_losses,
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
        "guard_captain_ship_captures": player.guard_captain_ship_captures,
        "treasure_value": player.treasure_value,
        "treasure_at_sea": player.has_treasure_at_sea,
        "payroll_launched": player.payroll_launched,
        "payroll_at_sea": player.has_payroll_at_sea,
    }


def snapshot_record(snapshot):
    """
    Creates a structured record of the game state at a specific snapshot, including player details and allocations. This is used for recording turn-by-turn snapshots in the AI game records for later analysis.
    Args:    
    snapshot (dict): A dictionary representing the game state at a specific point in time, typically including player details and their allocations for the turn. The structure of the snapshot is expected to be a
    dictionary where the keys are player names and the values are dictionaries containing player details and allocations.
    Returns:
        dict: A structured record of the game state at the snapshot, where each player's details and allocations are converted into a serializable format using the value_record helper function. The resulting dictionary is structured in a way that allows for easy analysis and comparison of game states across different turns in the AI game records.
    """
    return {
        player_name: {
            key: value_record(value)
            for key, value in player_snapshot.items()
        }
        for player_name, player_snapshot in snapshot.items()
    }


def value_record(value):
    """Helper function to convert complex values (like Allocations) into a serializable format for recording in the AI game records. If the value is an instance of Allocation, it converts it into a dictionary format that captures the relevant details of the allocation. For other types of values, it returns them as-is, assuming they are already serializable.
    Args:
        value: The value to be converted for recording. This can be of any type, but if it is an instance of Allocation, it will be converted into a dictionary format.
    Returns:    
        dict or any: If the input value is an instance of Allocation, it returns a dictionary containing
        the details of the allocation (trade, raid, guard, fire, total). For any other type of value, it returns the value as-is.
    """
    if isinstance(value, Allocation):
        return {
            "trade": value.trade,
            "raid": value.raid,
            "guard": value.guard,
            "fire": value.fire,
            "total": value.total,
        }

    return value


def play_vs_ai(
    human_name="England",
    strategy_name="Privateer",
    seed=None,
    log_path=AI_GAME_LOG_PATH,
):
    """
    Runs a game against the AI using a specified strategy and records the results. This function initializes a PlayVsAIGame with the given human player name, AI strategy, and random seed for reproducibility. It then plays the game, prints the outcome, and writes a detailed record of the game to a log file for later analysis.
    Args:
        human_name (str): The name of the human player (default is "England").
        strategy_name (str): The name of the AI strategy to use.
        seed (int, optional): The random seed for reproducibility.
        log_path (str): The path to the log file for recording game results.
    Returns:
        None: This function runs the game and records the results but does not return any value.
    """
    rng = random.Random(seed)
    strategy = find_strategy(strategy_name)
    game = PlayVsAIGame(human_name=human_name, strategy=strategy, rng=rng)
    print(f"\nYou are facing AI {strategy.name}.")
    game.play()
    write_ai_game_record(game, strategy, seed, log_path=log_path)


def summarize_ai_games(log_path=AI_GAME_LOG_PATH):
    """ 
    Reads recorded AI game logs and summarizes the outcomes by strategy. This function reads the AI game records from the specified log file, aggregates the results by AI strategy, and prints a summary of the outcomes, including the number of games played, wins for the human and AI, draws, average turns, and average scores for both players.
    Args:    log_path (str): The path to the log file containing the AI game records in JSON Lines format.
    Returns:    None: This function reads the game records, aggregates the results, and prints a summary to the console, but does not return any value.
    """
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
    """ 
    Prints a summary of AI game outcomes by strategy, including the number of games played, wins for the human and AI, draws, average turns, and average scores for both players. This function takes the aggregated statistics from the AI game records and formats them into a readable table for analysis.
    Args:
    log_path (str): The path to the log file containing the AI game records.
    stats (defaultdict): A dictionary containing the aggregated statistics for each AI strategy, including the number of games played, wins for the human and AI, draws, total turns, and total scores for both players.
    Returns:
    None: This function prints the summary to the console but does not return any value."""
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


def run_self_play(games=100, seed=None):
    """
    Simulates self-play scenarios between two bot strategies for benchmarking and training purposes. This function runs a specified number of games between randomly chosen bot strategies, aggregates the results, and prints a summary of the outcomes, including win rates, average turns, average scores, and average ships for each strategy.
    Args:    games (int): The number of self-play games to simulate (default is 100).
        seed (int, optional): The random seed for reproducibility of the self-play simulations.
    Returns:    None: This function runs the self-play simulations, aggregates the results, and prints a summary to the console, but does not return any value.
    """
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
    """
    Prints a summary report of self-play scenarios between bot strategies, including win rates, average turns, average scores, and average ships for each strategy. This function takes the aggregated statistics from the self-play simulations and formats them into a readable table for analysis, along with human-facing lessons based on the results.
    Args:    games (int): The number of self-play games that were simulated.
        seed (int, optional): The random seed that was used for the self-play simulations, if any.
        stats (defaultdict): A dictionary containing the aggregated statistics for each bot strategy, including the number of games played, wins, draws, port wins, total turns, total scores, and total ships for each strategy.
    Returns:    None: This function prints the summary report to the console but does not return any value.
    """
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
