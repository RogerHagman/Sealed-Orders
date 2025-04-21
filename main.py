import uuid

class Rules:
    # === Food System ===
    FOOD_COST = 1  # Standard food cost per unit
    BLOCKADED_FOOD_COST = 2  # Doubled food cost when blockaded

    PORT_FOOD_PER_TURN = 1  # Port consumes 1 food per turn
    INITIAL_PORT_FOOD = 5  # Port starts with 5 food
    PORT_RESUPPLY_RATE = 1  # Gains 1 food per turn if not blockaded

    CREW_FOOD_COST = 1 / 10  # 1 food per 10 crew per turn
    MIN_CREW = 10  # Minimum crew per ship

    # === Economy ===
    STARTING_GOLD = 10
    STARTING_CREW = 10
    STARTING_SHIPS = 1

    CREW_COST = 1  # 10 crew per 1 gold
    SHIP_COST = 10  # Cost of new ship
    FOOD_UNIT_COST = 1  # If buying manually

    # === Trade Missions ===
    TRADE_MISSION_COSTS = [5, 10, 20]
    TRADE_RETURN_RANGES = {
        5: (7, 9),
        10: (13, 18),
        20: (27, 35)
    }
    TRADE_FAILURE_CHANCE = 0.1  # Failure if detected

    # === Blockade Mechanics ===
    BLOCKADE_COST = 1
    MAX_BLOCKADE_TURNS = 5
    BLOCKADE_BREAK_ALLOWED = True

    # === Combat & Detection ===
    DETECTION_BASE_CHANCE = 0.5
    GREAT_SEA_BATTLE_ENABLED = True
    CREW_UPKEEP_PER_10 = 1
    BLOCKADED_CREW_UPKEEP_PER_10 = 2

class Ship:
    def __init__(self, owner, crew=Rules.MIN_CREW):
        self.id = str(uuid.uuid4())[:8]
        self.owner = owner
        self.crew = crew
        self.status = "idle"  # idle, trading, blockading, etc.

    def __repr__(self):
        return f"Ship({self.id}, crew={self.crew}, status={self.status})"

class Nation:
    def __init__(self, name):
        self.name = name
        self.gold = Rules.STARTING_GOLD
        self.port_food = Rules.INITIAL_PORT_FOOD
        self.ships = [Ship(owner=self) for _ in range(Rules.STARTING_SHIPS)]
        self.blockade_turns = 0
        self.is_blockaded = False

    def resupply_port(self):
        if not self.is_blockaded:
            self.port_food += Rules.PORT_RESUPPLY_RATE

    def consume_port_food(self):
        self.port_food = max(0, self.port_food - Rules.PORT_FOOD_PER_TURN)

    def status_report(self):
        print(f"\n=== {self.name.upper()} ===")
        print(f"Gold: {self.gold}")
        print(f"Port Food: {self.port_food}")
        print(f"Ships: {len(self.ships)}")
        for ship in self.ships:
            print(f"  - {ship}")
class Upkeep:
    @staticmethod
    def apply(nation):
        print(f"\n⏳ Applying upkeep for {nation.name}...")

        # Resupply port (if not blockaded)
        if not nation.is_blockaded:
            nation.resupply_port()
            print(f" - Port resupplied with {Rules.PORT_RESUPPLY_RATE} food (now: {nation.port_food})")
        else:
            print(f" - Port is blockaded, no resupply.")

        # Consume 1 food from port
        nation.consume_port_food()
        print(f" - Port consumed {Rules.PORT_FOOD_PER_TURN} food (remaining: {nation.port_food})")

        # Calculate upkeep for each ship's crew
        total_upkeep = 0
        rate_per_10 = (
            Rules.BLOCKADED_CREW_UPKEEP_PER_10 if nation.is_blockaded else Rules.CREW_UPKEEP_PER_10
        )

        for ship in nation.ships:
            crew_blocks = ship.crew // 10
            cost = crew_blocks * rate_per_10
            total_upkeep += cost
            print(f" - Ship {ship.id} with {ship.crew} crew: {cost} gold upkeep")

        print(f" - Total upkeep: {total_upkeep}")

        if nation.gold >= total_upkeep:
            nation.gold -= total_upkeep
        else:
            print(f" ⚠️ Not enough gold to pay full crew upkeep!")
            nation.gold = 0  # Or implement consequences for shortfall

        print(f" => {nation.name} now has {nation.gold} gold and {nation.port_food:.1f} food left.")




class Game:
    def __init__(self, nation_names):
        self.nations = [Nation(name) for name in nation_names]
        self.turn = 1

    def show_economy(self):
        print(f"\n=== GAME STATE: TURN {self.turn} ===")
        for nation in self.nations:
            nation.status_report()

    def advance_turn(self):
        print(f"\n🔄 ADVANCING TO TURN {self.turn}")
        for nation in self.nations:
            Upkeep.apply(nation)
        self.turn += 1
        self.show_economy()

# Example usage:
game = Game(["England", "Spain"])
game.show_economy()
# Simulate 3 turns
for _ in range(3):
    game.advance_turn()