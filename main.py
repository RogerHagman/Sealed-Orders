import uuid
import random


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
        self.order = ShipOrder.IDLE  # default each turn

    def __repr__(self):
        return f"Ship({self.id}, crew={self.crew}, order={self.order})"

class ShipOrder:
    IDLE = "idle"
    TRADE = "trade"
    BLOCKADE = "blockade"
    ATTACK = "attack"
    PATROL = "patrol"


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

    def buy_crew(self, ship, crew_amount):
        """
        Buys crew in multiples of 10. Each 10 crew costs 1 gold.
        """
        blocks = crew_amount // 10
        cost = blocks * Rules.CREW_COST
        if self.gold >= cost:
            self.gold -= cost
            ship.crew += blocks * 10
            print(f" 🧑‍✈️ {self.name} recruited {blocks * 10} crew for ship {ship.id} (cost {cost} gold)")
        else:
            print(f" ⚠️ {self.name} can't afford to buy {crew_amount} crew (needs {cost} gold)")

    def assign_orders(self, assignments):
        """
        assignments: dict of {ship_id: (order_type, target_or_tier)}
        Example: { 'a1b2c3': ('trade', 10), 'd4e5f6': ('blockade', 'Spain') }
        """
        for ship in self.ships:
            if ship.id in assignments:
                order, target = assignments[ship.id]

                if order == ShipOrder.TRADE:
                    trade_tier = target  # target is actually trade tier (5, 10, 20)
                    if trade_tier not in Rules.TRADE_MISSION_COSTS:
                        print(f" ⚠️ Invalid trade tier: {trade_tier}")
                        continue
                    if self.gold < trade_tier:
                        print(f" ⚠️ {self.name} can't afford to fund trade mission of tier {trade_tier}")
                        continue
                    self.gold -= trade_tier
                    ship.trade_tier = trade_tier
                    ship.order = (ShipOrder.TRADE, None)
                    print(f" 💼 {self.name} assigned ship {ship.id} to trade (tier {trade_tier}), paid {trade_tier} gold")
                else:
                    ship.order = (order, target)


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
        
        # Upkeep phase
        for nation in self.nations:
            Upkeep.apply(nation)

        # Elimination check for blockaded nations
        for nation in self.nations[:]:  # copy to allow removal
            if nation.blockade_turns >= Rules.MAX_BLOCKADE_TURNS:
                print(f"\n💀 {nation.name} has been blockaded for {Rules.MAX_BLOCKADE_TURNS} turns and is eliminated!")
                self.nations.remove(nation)

        self.turn += 1
        self.show_economy()
    def resolve_blockades(self):
        print("\n⚔️ RESOLVING BLOCKADES...")
        blockades = {}
        patrols = {}

        # Collect orders
        for nation in self.nations:
            for ship in nation.ships:
                order, target = ship.order if isinstance(ship.order, tuple) else (ship.order, None)
                if order == ShipOrder.BLOCKADE:
                    blockades.setdefault(target, []).append(ship)
                elif order == ShipOrder.PATROL:
                    patrols.setdefault(nation.name, []).append(ship)

        for target_name, blockading_ships in blockades.items():
            patrol_force = patrols.get(target_name, [])
            blockading_crew = sum(ship.crew for ship in blockading_ships)
            patrol_crew = sum(ship.crew for ship in patrol_force)

            print(f"\n🎯 Blockade Attempt on {target_name}:")
            print(f" - Blockading crew: {blockading_crew}")
            print(f" - Patrolling crew: {patrol_crew}")

            target_nation = self.find_nation(target_name)
            if not target_nation:
                print(f" ❌ Error: Nation {target_name} not found!")
                continue

            if patrol_crew >= 3 * blockading_crew:
                print(" 💥 Patrol force overwhelms the blockade! Blockading ship(s) are sunk.")
                # Remove blockading ships from their owner's list
                for ship in blockading_ships:
                    owner = ship.owner
                    owner.ships = [s for s in owner.ships if s != ship]
                    print(f"   - Ship {ship.id} sunk.")
                target_nation.is_blockaded = False
                target_nation.blockade_turns = 0  # optional: reset counter
            elif patrol_crew >= blockading_crew:
                print(" ✅ Blockade repelled by patrol.")
                target_nation.is_blockaded = False
                target_nation.blockade_turns = 0
            else:
                print(" ❌ Blockade succeeds.")
                target_nation.is_blockaded = True
                target_nation.blockade_turns += 1
                print(f" - {target_name} has been blockaded for {target_nation.blockade_turns} turn(s)")


    def resolve_trades(self):
        print("\n💰 RESOLVING TRADE MISSIONS...")
        for nation in self.nations:
            for ship in nation.ships:
                order, _ = ship.order if isinstance(ship.order, tuple) else (ship.order, None)
                if order == ShipOrder.TRADE:
                    tier = ship.trade_tier
                    min_return, max_return = Rules.TRADE_RETURN_RANGES[tier]
                    profit = random.randint(min_return, max_return)
                    nation.gold += profit
                    print(f" - {nation.name}'s Ship {ship.id} completed trade mission (Tier {tier}) and earned {profit} gold.")


    def find_nation(self, name):
        for nation in self.nations:
            if nation.name == name:
                return nation
        return None
    def reveal_orders(self):
        print("\n📜 REVEALING SEALED ORDERS")
        for nation in self.nations:
            print(f"\n{nation.name.upper()}'s SHIPS:")
            for ship in nation.ships:
                order, target = ship.order if isinstance(ship.order, tuple) else (ship.order, None)
                if order == ShipOrder.BLOCKADE or order == ShipOrder.ATTACK:
                    print(f" - Ship {ship.id} will {order} {target}")
                else:
                    print(f" - Ship {ship.id} will {order}")

# Reset game
game = Game(["England", "Spain"])
england = game.nations[0]
spain = game.nations[1]
england_ship = england.ships[0]
spain_ship = spain.ships[0]

game.show_economy()

# Simulate 5 turns
for i in range(5):
    print(f"\n--- TURN {game.turn} ---")

    # England blockades Spain every turn
    england.assign_orders({
        england_ship.id: (ShipOrder.BLOCKADE, "Spain")
    })

    if i < 4:
        # Spain trades (Tier 10)
        spain.assign_orders({
            spain_ship.id: (ShipOrder.TRADE, 10)
        })
    else:
        # Turn 5: Spain buys crew and patrols
        spain.buy_crew(spain_ship, 20)  # buys +20 crew → 30 total
        spain.assign_orders({
            spain_ship.id: (ShipOrder.PATROL, None)
        })

    game.reveal_orders()
    game.resolve_blockades()
    game.resolve_trades()
    game.advance_turn()

    # Early end if England is eliminated (e.g., ship sunk)
    if not england.ships:
        print("\n☠️ England’s ship was sunk. Blockade lifted. Simulation complete.")
        break

    if not any(n.name == "Spain" for n in game.nations):
        print("\n💀 Spain has been eliminated. Simulation complete.")
        break
