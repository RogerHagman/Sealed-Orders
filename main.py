import argparse
import sys

from game_engine import Game
from game_state import Allocation, Rules, UI

if __name__ == "__main__":
    sys.modules["main"] = sys.modules[__name__]


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
        default="artifacts/logs/ai_game_log.jsonl",
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
        "--train-start-strategy",
        help=(
            "start --train-evolving from a named roster bot or strategy JSON "
            "instead of a random strategy"
        ),
    )
    parser.add_argument(
        "--seed-branch-chance",
        type=float,
        default=0.0,
        help=(
            "chance per generation to mutate from --train-start-strategy "
            "instead of the current incumbent"
        ),
    )
    parser.add_argument(
        "--training-workers",
        type=int,
        default=1,
        help="CPU worker processes for --train-evolving simulation batches",
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
        "--show-training-weights",
        action="store_true",
        help="print live strategy weights during --train-evolving",
    )
    parser.add_argument(
        "--training-weights-interval",
        type=int,
        default=1,
        help="generation interval for --show-training-weights; learned generations always print",
    )
    parser.add_argument(
        "--training-dashboard",
        action="store_true",
        help="redraw a live top-style dashboard during --train-evolving",
    )
    parser.add_argument(
        "--training-dashboard-history",
        type=int,
        default=12,
        help="number of recent generation lines shown in --training-dashboard",
    )
    parser.add_argument(
        "--training-dashboard-benchmark-games",
        type=int,
        default=100,
        help="games per opponent for dashboard benchmarks after --train-evolving",
    )
    parser.add_argument(
        "--training-dashboard-window",
        type=int,
        default=100,
        help="rolling health window for --training-dashboard yield/fragility/candidate metrics",
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
        "--eval-workers",
        type=int,
        default=1,
        help="CPU worker processes for --evaluate-strategy benchmarks",
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
            workers=args.eval_workers,
        )
    elif args.train_evolving is not None:
        from bot_playtest import train_evolving_strategy
        from bot_roster import find_strategy
        from bot_strategy import load_strategy

        initial_strategy = None
        if args.train_start_strategy:
            try:
                initial_strategy = find_strategy(args.train_start_strategy)
            except ValueError:
                initial_strategy = load_strategy(args.train_start_strategy)

        train_evolving_strategy(
            generations=args.train_evolving,
            games_per_bot=args.training_games,
            learning_rate=args.learning_rate,
            mutation_scale=args.mutation_scale,
            seed=args.seed,
            output_path=args.evolved_output,
            history_path=args.training_history,
            graph_path=args.training_graph,
            show_weights=args.show_training_weights,
            weights_interval=args.training_weights_interval,
            dashboard=args.training_dashboard,
            dashboard_history=args.training_dashboard_history,
            dashboard_benchmark_games=args.training_dashboard_benchmark_games,
            dashboard_window=args.training_dashboard_window,
            initial_strategy=initial_strategy,
            seed_branch_chance=args.seed_branch_chance,
            workers=args.training_workers,
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
