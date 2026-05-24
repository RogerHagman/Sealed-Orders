from game_state import Allocation


# Opening book fields:
# - weight: relative chance of selecting this line from the book.
# - anti_aggro: preferred line when the opponent looks like early all-in pressure.
# - turns: scripted turns, keyed by turn number.
# - allocation: sealed orders for that turn; omit for buy-only follow-up turns.
# - buy_actions: ordered buy-phase actions; unavailable actions are skipped.
# - continue_buy_phase: run normal bot buy logic after scripted buy_actions.

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


NASH_CORE_OPENING_BOOK = [
    {
        "name": "Harbor Vault",
        "code_id": "nash_triple_guard",
        "source": "Solved triple-opener spread",
        "weight": 45,
        "turns": {
            1: {
                "allocation": Allocation(guard=3),
                "buy_actions": ["launch_treasure", "stabilize_first_buy"],
            },
            2: {
                "buy_actions": ["launch_treasure"],
                "continue_buy_phase": True,
            },
        },
    },
    {
        "name": "Red Sail Gambit",
        "code_id": "nash_triple_raid",
        "source": "Solved triple-opener spread",
        "weight": 40,
        "turns": {
            1: {
                "allocation": Allocation(raid=3),
                "buy_actions": ["launch_treasure", "stabilize_first_buy"],
            },
            2: {
                "buy_actions": ["launch_treasure"],
                "continue_buy_phase": True,
            },
        },
    },
    {
        "name": "Merchant's Bluff",
        "code_id": "nash_triple_trade",
        "source": "Solved triple-opener spread",
        "weight": 10,
        "turns": {
            1: {
                "allocation": Allocation(trade=3),
                "buy_actions": ["launch_treasure", "stabilize_first_buy"],
            },
            2: {
                "buy_actions": ["launch_treasure"],
                "continue_buy_phase": True,
            },
        },
    },
    {
        "name": "Silent Yard",
        "code_id": "nash_yard_hold",
        "source": "Solved triple-opener spread plus shipyard hold branch",
        "weight": 5,
        "turns": {
            1: {
                "allocation": Allocation(guard=3),
                "buy_actions": ["start_shipyard", "buy_one_ship"],
            },
            2: {
                "buy_actions": ["launch_treasure", "buy_one_ship"],
                "continue_buy_phase": True,
            },
        },
    },
]


# Compatibility alias for older imports and notes.
NASH_ADMIRAL_OPENING_BOOK = NASH_CORE_OPENING_BOOK
