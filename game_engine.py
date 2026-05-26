import io
import math
import random
import shutil
import sys
import termios
import tty
from contextlib import redirect_stdout

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
        self.buy_phase_baselines = {}
        self.admiral_interventions = {}
        self.supply_income = {}

    def play(self):
        UI.section(f"SEALED ORDERS v{Rules.VERSION}", "magenta")
        UI.bullet("Assign ships to Trade, Raid, Guard, and Fire.", "cyan")
        UI.bullet(f"Highest total assets after {Rules.MAX_TURNS} turns wins.", "yellow")
        UI.bullet("Treasure and payroll convoys create delayed, raidable payouts.")
        UI.bullet("Sea income keeps fleets supplied; shortages create attrition.")
        UI.bullet("Unassigned ships become port workers for construction projects.")
        UI.bullet("Fire ships and guard captains are buy-phase upgrades.")

        while self.turn <= Rules.MAX_TURNS and not self.game_over:
            self.play_turn()
            self.turn += 1

        self.show_final_scores()

    def play_turn(self):
        UI.clear_screen()
        UI.section(f"{self.current_month.upper()} ({self.turn}/{Rules.MAX_TURNS})")
        self.show_state()
        before_snapshot = self.snapshot_turn()

        for player in self.players:
            self.pause_for_private_entry(player)
            player.allocation = self.prompt_allocation(player)

        orders_snapshot = self.snapshot_turn()
        self.clear_between_players()
        self.reveal_orders()
        self.show_bulletin("Resolution", self.resolve_orders)
        if self.game_over:
            return
        self.pause_after_resolution()
        self.show_bulletin("Convoy Arrivals", self.advance_convoys)
        self.show_bulletin("Supply", self.apply_supply)
        self.show_bulletin("Port Labor", self.apply_port_labor)
        self.buy_phase()
        after_snapshot = self.snapshot_turn()
        self.show_turn_summary(before_snapshot, after_snapshot, orders_snapshot)

    def show_state(self):
        UI.subheading("Harbor State")
        self.print_player_panels(
            [
                (player.name, self.player_compact_status_lines(player))
                for player in self.players
            ]
        )

    def print_full_state(self):
        UI.subheading("Harbor State")
        self.print_player_panels(
            [(player.name, self.player_status_lines(player)) for player in self.players]
        )

    def buy_baseline(self, player):
        return self.buy_phase_baselines.get(player)

    def buy_delta(self, player, key):
        baseline = self.buy_baseline(player)
        if baseline is None:
            return 0
        return self.snapshot_player(player)[key] - baseline[key]

    def player_compact_status_lines(self, player):
        gold_delta = self.buy_delta(player, "gold")
        ships_delta = self.buy_delta(player, "ships")
        asset_delta = self.buy_delta(player, "asset_score")
        lines = player.compact_status_lines()
        lines[0] = (
            f"{UI.amount(player.gold, 'gold', player.gold_color)}{UI.delta(gold_delta)}  "
            f"{UI.amount(player.ships, 'ships')}{UI.delta(ships_delta)}  "
            f"{UI.amount(player.asset_score, 'assets', 'yellow')}{UI.delta(asset_delta)}"
        )
        lines[2] = f"Payroll: {self.player_payroll_status(player)}"
        return lines

    def player_status_lines(self, player):
        lines = player.status_lines()
        lines[2] = f"{UI.field('Payroll')} {self.player_payroll_status(player)}"
        return lines

    def print_player_panels(self, titled_lines):
        terminal = shutil.get_terminal_size((120, 36))
        width = max(80, terminal.columns)
        content_width = min(width, 150)
        if len(titled_lines) == 2 and content_width >= 96:
            left_width = max(38, (content_width - 2) // 2)
            right_width = content_width - left_width - 2
            left = UI.panel(titled_lines[0][0], titled_lines[0][1], left_width, wrap=True)
            right = UI.panel(titled_lines[1][0], titled_lines[1][1], right_width, wrap=True)
            target_height = max(len(left), len(right))
            left = UI.pad_panel_height(left, left_width, target_height)
            right = UI.pad_panel_height(right, right_width, target_height)
            for line in UI.combine_panels(left, right):
                print(line)
            return

        for title, lines in titled_lines:
            for line in UI.panel(title, lines, content_width, wrap=True):
                print(line)

    def show_bulletin(self, title, callback):
        orders_snapshot = None
        if title.lower() == "resolution":
            orders_snapshot = {
                player: Allocation(
                    player.allocation.trade,
                    player.allocation.raid,
                    player.allocation.guard,
                    player.allocation.fire,
                )
                for player in self.players
            }
        output = io.StringIO()
        with redirect_stdout(output):
            callback()

        lines = []
        previous_line = None
        for raw_line in output.getvalue().splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("===") and line.endswith("==="):
                continue
            if lines and self.bulletin_needs_separator(previous_line, line):
                lines.append("")
            lines.append(self.format_bulletin_line(line))
            previous_line = line

        if not lines:
            lines = ["No report."]

        terminal = shutil.get_terminal_size((120, 36))
        width = min(max(80, terminal.columns), 150)
        control_lines = [
            "Review the report.",
            "Press Enter when prompted to continue.",
        ]
        if title.lower() == "resolution":
            control_lines = self.sealed_orders_control_lines(orders_snapshot)
        self.render_play_area(
            phase=title,
            control_lines=control_lines,
            info_lines=lines,
            info_title="Bulletin Board",
            clear=True,
            include_state=True,
            width=width,
        )

    def format_bulletin_line(self, line):
        lower = line.lower()
        if line.endswith(":") and not line.startswith("-"):
            return self.accent_bulletin_nations(line[:-1]) + UI.paint(":", "cyan", bold=True)

        if "fishing boats" in lower or "fishing income" in lower:
            return self.accent_bulletin_nations(UI.accent_amounts(line, "blue"))
        if any(
            phrase in lower
            for phrase in [
                "intercepted",
                "captured",
                "steals",
                "loses",
                "sink",
                "destroyed",
                "burn",
                "damaged",
                "mutiny",
                "desertion",
                "unrest",
                "crisis",
                "forfeits",
                "confiscates all fishing",
            ]
        ):
            return self.accent_bulletin_nations(UI.accent_amounts(line, "red"))
        if "supply" in lower:
            return self.accent_bulletin_nations(UI.accent_amounts(line, "yellow"))
        if "smuggle" in lower:
            return self.accent_bulletin_nations(UI.accent_amounts(line, "magenta"))
        if "confiscat" in lower or "guard captains catch" in lower:
            return self.accent_bulletin_nations(UI.accent_amounts(line, "yellow"))
        if any(
            phrase in lower
            for phrase in [
                "complete trade",
                "trade guild bonus",
                "evades raiders",
                "arrives",
                "earns",
            ]
        ):
            return self.accent_bulletin_nations(UI.accent_amounts(line, "green"))
        if (
            lower.startswith("- no ")
            or " launches no " in lower
            or " sends no " in lower
            or "no port labor" in lower
            or "no convoys" in lower
            or "catch no" in lower
        ):
            return self.accent_bulletin_nations(UI.muted(line))
        return self.accent_bulletin_nations(UI.accent_amounts(line))

    def accent_bulletin_nations(self, line):
        if not UI.enabled:
            return line
        colors = ["cyan", "magenta"]
        highlighted = line
        player_colors = {
            player: colors[index % len(colors)]
            for index, player in enumerate(self.players)
        }
        players_by_length = sorted(
            self.players,
            key=lambda player: len(player.name),
            reverse=True,
        )
        for player in players_by_length:
            color = player_colors[player]
            highlighted = highlighted.replace(
                player.name,
                UI.paint(player.name, color, bold=True),
            )
        return highlighted

    def bulletin_needs_separator(self, previous_line, line):
        if previous_line is None:
            return False
        lower = line.lower()
        previous_lower = previous_line.lower()
        if line.endswith(":"):
            return True
        if " earns " in lower and " earns " not in previous_lower:
            return True
        if "remaining guards catch damaged raiders" in lower:
            return True
        return False

    def sealed_orders_control_lines(self, orders_snapshot=None):
        lines = [
            UI.paint("Sealed Orders Revealed", "magenta", bold=True),
            UI.muted("Active commitments are locked in."),
        ]
        for player in self.players:
            allocation = (
                orders_snapshot[player]
                if orders_snapshot and player in orders_snapshot
                else player.allocation
            )
            fire_value = (
                UI.order_amount("Fire", allocation.fire)
                if player.fire_ships_unlocked or allocation.fire
                else UI.muted("locked")
            )
            lines.extend(
                [
                    "",
                    UI.paint(player.name, "magenta", bold=True),
                    f"  {UI.order_label('Trade')} {UI.order_amount('Trade', allocation.trade)}   "
                    f"{UI.order_label('Raid')} {UI.order_amount('Raid', allocation.raid)}",
                    f"  {UI.order_label('Guard')} {UI.order_amount('Guard', allocation.guard)}   "
                    f"{UI.order_label('Fire')} {fire_value}",
                ]
            )
        lines.extend(["", UI.muted("Read the bulletin for the clash-by-clash result.")])
        return lines

    def render_play_area(
        self,
        phase,
        control_lines,
        info_lines,
        info_title="Information",
        clear=True,
        include_state=True,
        width=None,
    ):
        if clear:
            UI.clear_screen()
        print(UI.paint(f"=== {phase.upper()} ({self.current_month}) ===", "cyan", bold=True))
        if include_state:
            self.show_state()

        terminal = shutil.get_terminal_size((120, 36))
        content_width = width or min(max(80, terminal.columns), 150)
        if content_width >= 96:
            left_width = max(34, int(content_width * 0.38))
            right_width = content_width - left_width - 2
            control = UI.panel("Control", control_lines, left_width, wrap=True)
            info = UI.panel(info_title, info_lines, right_width, wrap=True)
            target_height = max(len(control), len(info))
            control = UI.pad_panel_height(control, left_width, target_height)
            info = UI.pad_panel_height(info, right_width, target_height)
            for line in UI.combine_panels(control, info):
                print(line)
        else:
            for line in UI.panel("Control", control_lines, content_width, wrap=True):
                print(line)
            for line in UI.panel(info_title, info_lines, content_width, wrap=True):
                print(line)

    def read_menu_key(self):
        char = sys.stdin.read(1)
        if char in {"\r", "\n"}:
            return "enter"
        if char in {"\x7f", "\b"}:
            return "backspace"
        if char == "\x1b":
            rest = sys.stdin.read(2)
            if rest == "[A":
                return "up"
            if rest == "[B":
                return "down"
            if rest == "[C":
                return "right"
            if rest == "[D":
                return "left"
            return "escape"
        return char

    def with_cbreak(self, callback):
        if not sys.stdin.isatty():
            return callback()
        settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setcbreak(sys.stdin.fileno())
            return callback()
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)

    def snapshot_turn(self):
        return {player.name: self.snapshot_player(player) for player in self.players}

    def snapshot_player(self, player):
        return {
            "gold": player.gold,
            "ships": player.ships,
            "asset_score": player.asset_score,
            "treasure_status": f"{player.treasure_value} gold{player.treasure_status}",
            "payroll_status": self.player_payroll_status(player),
            "shipyard_status": player.shipyard_status,
            "fort_status": player.fort_status,
            "trade_guild_status": player.trade_guild_status,
            "fishing_status": player.fishing_status,
            "dockhouse_status": player.dockhouse_status,
            "dockhand_status": player.dockhand_status,
            "supply_status": player.supply_status,
            "raid_fatigue_status": player.raid_fatigue_status,
            "dry_dock_status": player.dry_dock_status,
            "admiralty_status": player.admiralty_status,
            "admiral_status": player.admiral_status,
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
        UI.clear_screen()
        UI.section(f"END OF {self.current_month.upper()} SUMMARY", "blue")
        summary_panels = []
        for player in self.players:
            before = before_snapshot[player.name]
            after = after_snapshot[player.name]
            orders = orders_snapshot[player.name]
            lines = [
                f"Orders: {orders['allocation']}",
                f"Gold: {self.format_delta(before['gold'], after['gold'])}",
                f"Ships: {self.format_delta(before['ships'], after['ships'])}",
                f"Assets: "
                f"{self.format_delta(before['asset_score'], after['asset_score'])}",
            ]
            self.add_status_change(lines, "Treasure", before, after, "treasure_status")
            self.add_status_change(lines, "Payroll", before, after, "payroll_status")
            self.add_status_change(lines, "Shipyard", before, after, "shipyard_status")
            self.add_status_change(lines, "Fort", before, after, "fort_status")
            self.add_status_change(
                lines,
                "Trade guild",
                before,
                after,
                "trade_guild_status",
            )
            self.add_status_change(lines, "Fishing", before, after, "fishing_status")
            self.add_status_change(lines, "Dockhouse", before, after, "dockhouse_status")
            self.add_status_change(lines, "Dock hands", before, after, "dockhand_status")
            self.add_status_change(lines, "Supply", before, after, "supply_status")
            self.add_status_change(
                lines, "Raid fatigue", before, after, "raid_fatigue_status"
            )
            self.add_status_change(lines, "Dry dock", before, after, "dry_dock_status")
            self.add_status_change(lines, "Admiralty", before, after, "admiralty_status")
            self.add_status_change(lines, "Admirals", before, after, "admiral_status")
            self.add_status_change(
                lines, "Fire ships", before, after, "fire_ship_status"
            )
            self.add_status_change(
                lines, "Guard captains", before, after, "guard_captain_status"
            )
            summary_panels.append((player.name, lines))
        self.print_player_panels(summary_panels)

    def format_delta(self, before, after):
        delta = after - before
        sign = "+" if delta >= 0 else ""
        color = "green" if delta > 0 else "red" if delta < 0 else "dim"
        return f"{before} -> {after} ({UI.paint(f'{sign}{delta}', color, bold=True)})"

    def print_status_change(self, label, before, after, key):
        if before[key] == after[key]:
            return

        print(f"  {label}: {before[key]} -> {after[key]}")

    def add_status_change(self, lines, label, before, after, key):
        if before[key] == after[key]:
            return

        lines.append(f"{label}: {before[key]} -> {after[key]}")

    @property
    def current_month(self):
        month = Rules.MONTHS[(self.turn - 1) % len(Rules.MONTHS)]
        year = ((self.turn - 1) // len(Rules.MONTHS)) + 1
        if year == 1:
            return month
        return f"{month}, Year {year}"

    @property
    def payroll_year(self):
        return (self.turn - 1) // len(Rules.MONTHS)

    @property
    def payroll_cycle_turn(self):
        return ((self.turn - 1) % len(Rules.MONTHS)) + 1

    def payroll_launched_this_year(self, player):
        return self.payroll_year in player.payroll_launch_years

    def payroll_window_text(self):
        start_month = Rules.MONTHS[Rules.PAYROLL_START_TURN - 1]
        final_month = Rules.MONTHS[Rules.PAYROLL_FINAL_TURN - 1]
        return f"{start_month}-{final_month}"

    def player_payroll_status(self, player):
        if player.has_payroll_at_sea:
            return (
                f"{player.payroll_value} gold at sea, arrives in "
                f"{player.payroll_turns_remaining} turn(s)"
            )
        if self.payroll_launched_this_year(player):
            return "completed this year"
        if self.payroll_cycle_turn < Rules.PAYROLL_START_TURN:
            return f"must launch between {self.payroll_window_text()}"
        final_month = Rules.MONTHS[Rules.PAYROLL_FINAL_TURN - 1]
        if self.payroll_cycle_turn >= Rules.PAYROLL_FINAL_TURN:
            return "launches automatically this month"
        return f"must launch by {final_month}"

    def show_player_economy(self, player):
        self.render_play_area(
            phase=f"{player.name}'s Command",
            control_lines=[
                f"{player.name}, review your harbor.",
                "Enter orders or buy actions in the control prompt below.",
            ],
            info_lines=self.player_economy_lines(player),
            info_title="Harbor Details",
            clear=True,
            include_state=True,
        )

    def player_economy_lines(self, player):
        opponent = self.opponent_for(player)
        smuggle_bonus = 0
        if opponent is not None and opponent.supply <= -1:
            smuggle_bonus = max(0, Rules.TRADE_INCOME - Rules.SMUGGLE_INCOME)
        smuggle_income_text = UI.amount(Rules.SMUGGLE_INCOME)
        if smuggle_bonus:
            smuggle_income_text += f" {UI.paint(f'+{smuggle_bonus}', 'magenta', bold=True)}"
        smuggle_income_text += " gold"
        trade_bonus = 1 if player.supply >= 5 else 0
        trade_income_text = UI.amount(Rules.TRADE_INCOME)
        if trade_bonus:
            trade_income_text += f" {UI.paint(f'+{trade_bonus}', 'green', bold=True)}"
        trade_income_text += " gold"
        guild_note = ""
        if player.trade_guild_completed:
            guild_note = ", guild bonus x2" if player.supply >= 4 else ", guild bonus active"
        elif player.supply >= 4:
            guild_note = ", needs guild for +5"
        lines = []
        if self.buy_baseline(player) is not None:
            lines.append(self.purchase_summary_line(player))
        lines.extend(
            [
                f"  {UI.field('Assets')} {UI.amount(player.asset_score, color='yellow')}{UI.delta(self.buy_delta(player, 'asset_score'))} "
                f"(shipyard value: {player.shipyard_value}, "
                f"fort value: {player.fort_value}, "
                f"trade guild value: {player.trade_guild_value}, "
                f"dockhouse value: {player.dockhouse_value}, "
                f"dry dock value: {player.dry_dock_value}, "
                f"admiralty value: {player.admiralty_value})",
                f"  {UI.field('Economy')} Trade income: {trade_income_text}, "
                f"smuggle income: {smuggle_income_text}, "
                f"fishing boat income: {UI.amount(Rules.FISHING_BOAT_INCOME, 'gold')}"
                f"{guild_note}",
                f"  {UI.field('Supply cover')} War chest: "
                f"{player.supply_warchest_markup} gold per missing supply "
                f"when already below 0 supply",
                f"  {UI.field('Ships')} {UI.amount(player.ships)}{UI.delta(self.buy_delta(player, 'ships'))}; cost: {UI.amount(player.ship_cost, 'gold')}, "
                f"ship value: {UI.amount(Rules.SHIP_COST, 'gold')}",
                f"  {UI.field('Fishing')} Docks: {UI.amount(Rules.FISHING_DOCK_COST, 'gold')}, "
                f"{UI.amount(Rules.FISHING_DOCK_LABOR_REQUIRED, 'labor')}; "
                f"boats: {UI.amount(Rules.FISHING_BOAT_COST, 'gold')} each",
                f"  {UI.field('Dockhouse')} {player.dockhouse_status}",
                f"  {UI.field('Dock hands')} {player.dockhand_status}",
            ]
        )
        if not self.payroll_launched_this_year(player):
            lines.append(
                f"  {UI.field('Payroll cost')} {UI.amount(player.payroll_cost, 'gold')}"
            )
        lines.extend(
            [
                f"  {UI.field('Treasure')} {player.treasure_value} gold{player.treasure_status}; "
                f"{player.treasure_growth_ticker}",
                f"  {UI.field('Supply')} {player.supply_status}",
                f"  {UI.field('Raid fatigue')} {player.raid_fatigue_status}",
                f"  {UI.field('Port defences')} {player.port_defense_status}",
                f"  {UI.field('Dry dock')} {player.dry_dock_status}",
                f"  {UI.field('Admiralty')} {player.admiralty_status}",
                f"  {UI.field('Admirals')} {player.admiral_status}",
                f"  {UI.field('Captains')} {player.guard_captain_status}",
            ]
        )
        lines.extend(self.harbor_upgrade_art_lines(player))
        return lines

    def opponent_for(self, player):
        for candidate in self.players:
            if candidate is not player:
                return candidate
        return None

    def harbor_upgrade_art_lines(self, player):
        def style(text, active=False, started=False, destroyed=False, color="green"):
            if destroyed:
                return UI.paint(text, "red", bold=True)
            if active:
                return UI.paint(text, color, bold=True)
            if started:
                return UI.paint(text, "yellow", bold=True)
            return UI.muted(text)

        yard = style(
            "Yard _|=|_",
            player.shipyard_completed,
            player.shipyard_started,
            player.shipyard_destroyed,
            "green",
        )
        fort = style("Fort /###\\", player.fort_completed, player.fort_started, False, "yellow")
        guild_text = "Guild [$]"
        if player.administrator_hired:
            guild_text = "Guild [$]+[A]"
        guild = style(
            guild_text,
            player.trade_guild_completed,
            player.trade_guild_started,
            False,
            "green",
        )
        dockhouse = style(
            "Hands [##]",
            player.dockhouse_completed,
            player.dockhouse_started,
            player.dockhouse_burned,
            "yellow",
        )
        fishing = style(
            "Docks ~|_|~",
            player.fishing_dock_built and not player.fishing_dock_disabled,
            player.fishing_dock_started and not player.fishing_dock_built,
            player.fishing_dock_disabled,
            "blue",
        )
        dry_dock = style(
            "Dry <_U_>",
            player.dry_dock_completed,
            player.dry_dock_started,
            False,
            "cyan",
        )
        admiralty = style(
            "Adm /\\^/\\",
            player.admiralty_completed,
            player.admiralty_started,
            False,
            "white",
        )
        fire = style("Fire >>>", player.fire_ships_unlocked, False, False, "red")
        captain_marks = " ".join(
            UI.paint("/|\\", "magenta", bold=True)
            if index < player.guard_captains
            else UI.muted("/|\\")
            for index in range(Rules.GUARD_CAPTAIN_MAX)
        )
        admiral_marks = " ".join(
            UI.paint("<^>", "white", bold=True)
            if index < player.admirals
            else UI.muted("<^>")
            for index in range(Rules.ADMIRAL_MAX)
        )

        return [
            "",
            UI.field("Harbor works"),
            self.supply_effect_art_line(player),
            f"  {yard}    {fort}    {guild}",
            f"  {fishing}    {dockhouse}    {dry_dock}    {admiralty}",
            f"  {fire}",
            f"  Hands {self.dockhand_art(player)}",
            f"  Capt {captain_marks}",
            f"  Adm  {admiral_marks}",
            f"  {self.convoy_art_line(player)}",
        ]

    def dockhand_art(self, player):
        marks = []
        for index in range(Rules.DOCKHAND_MAX):
            mark = "[]"
            if index < player.dockhands:
                color = "yellow" if player.dockhouse_completed else "red"
                marks.append(UI.paint(mark, color, bold=True))
            else:
                marks.append(UI.muted(mark))
        return " ".join(marks)

    def supply_effect_art_line(self, player):
        if not player.last_supply_events:
            return f"  Supply {UI.muted('no recent effects')}"
        return (
            f"  Supply "
            f"{player.supply_event_summary}"
        )

    def convoy_art_line(self, player):
        treasure = f"T{UI.amount(player.treasure_value)}"
        if player.has_treasure_at_sea:
            treasure = UI.paint(f"Treasure -> {player.treasure_turns_remaining}", "yellow", bold=True)
        else:
            treasure = UI.paint(f"Treasure {treasure}", "green", bold=True)

        if player.has_payroll_at_sea:
            payroll = UI.paint(f"Payroll -> {player.payroll_turns_remaining}", "yellow", bold=True)
        elif self.payroll_launched_this_year(player):
            payroll = UI.paint("Payroll done", "green", bold=True)
        elif self.payroll_cycle_turn < Rules.PAYROLL_START_TURN:
            payroll = UI.muted("Payroll locked")
        elif self.payroll_cycle_turn >= Rules.PAYROLL_FINAL_TURN:
            payroll = UI.paint("Payroll auto", "yellow", bold=True)
        else:
            payroll = UI.paint("Payroll ready", "cyan", bold=True)

        return f"Convoys {treasure}  {payroll}"

    def purchase_summary_line(self, player):
        baseline = self.buy_baseline(player)
        if baseline is None:
            return UI.muted("No buy-phase changes yet.")

        deltas = []
        for label, key in [
            ("gold", "gold"),
            ("ships", "ships"),
            ("assets", "asset_score"),
        ]:
            delta = self.buy_delta(player, key)
            if delta:
                deltas.append(f"{label} {UI.delta(delta).strip()}")

        status_changes = []
        current = self.snapshot_player(player)
        for label, key in [
            ("shipyard", "shipyard_status"),
            ("fort", "fort_status"),
            ("guild", "trade_guild_status"),
            ("fishing", "fishing_status"),
            ("dry dock", "dry_dock_status"),
            ("admiralty", "admiralty_status"),
            ("admirals", "admiral_status"),
            ("fire", "fire_ship_status"),
            ("captains", "guard_captain_status"),
        ]:
            if current[key] != baseline[key]:
                status_changes.append(label)

        if status_changes:
            deltas.append("changed " + ", ".join(status_changes))

        if not deltas:
            return UI.muted("Buy-phase changes: none yet.")
        return "Buy-phase changes: " + "; ".join(deltas)

    def idle_labor_preview(self, player, port_workers):
        remaining = port_workers
        preview = []
        projects = [
            (
                "shipyard",
                player.shipyard_started and not player.shipyard_completed,
                player.shipyard_labor,
                Rules.SHIPYARD_LABOR_REQUIRED,
            ),
            (
                "fort",
                player.fort_started and not player.fort_completed,
                player.fort_labor,
                Rules.FORT_LABOR_REQUIRED,
            ),
            (
                "trade guild",
                player.trade_guild_started and not player.trade_guild_completed,
                player.trade_guild_labor,
                Rules.TRADE_GUILD_LABOR_REQUIRED,
            ),
            (
                "fishing docks",
                (
                    player.fishing_dock_started
                    and not player.fishing_dock_built
                    and not player.fishing_dock_disabled
                ),
                player.fishing_dock_labor,
                Rules.FISHING_DOCK_LABOR_REQUIRED,
            ),
            (
                "dockhouse",
                player.dockhouse_started and not player.dockhouse_completed,
                player.dockhouse_labor,
                Rules.DOCKHOUSE_LABOR_REQUIRED,
            ),
            (
                "dry dock",
                player.dry_dock_started and not player.dry_dock_completed,
                player.dry_dock_labor,
                Rules.DRY_DOCK_LABOR_REQUIRED,
            ),
            (
                "admiralty",
                player.admiralty_started and not player.admiralty_completed,
                player.admiralty_labor,
                Rules.ADMIRALTY_LABOR_REQUIRED,
            ),
        ]

        for name, active, current_labor, required_labor in projects:
            if not active or remaining <= 0:
                continue
            applied = min(remaining, required_labor - current_labor)
            if applied > 0:
                preview.append(
                    f"{UI.amount(applied, 'labor')} to {name} "
                    f"({current_labor + applied}/{required_labor})"
                )
                remaining -= applied

        if port_workers <= 0:
            return "No port workers available for construction."
        if preview:
            if remaining:
                preview.append(f"{UI.amount(remaining, 'worker')} with no project")
            return "Port labor: " + "; ".join(preview)
        return "Port workers have no active construction project."

    def pause_for_private_entry(self, player):
        self.clear_between_players()
        input(f"{player.name}, press Enter when you are ready to enter sealed orders...")

    def prompt_allocation(self, player):
        if sys.stdin.isatty():
            return self.with_cbreak(lambda: self.prompt_allocation_menu(player))

        while True:
            self.render_play_area(
                phase=f"{player.name}'s Orders",
                control_lines=[
                    f"Assign up to {UI.amount(player.ships, 'ships')}.",
                    f"{UI.order_label('Trade')}: earn gold.",
                    f"{UI.order_label('Raid')}: steal trade, pressure ports.",
                    f"{UI.order_label('Guard')}: protect lanes and catch smugglers.",
                    f"{UI.order_label('Fire')}: burn guards and infrastructure when unlocked.",
                "Unassigned ships become port workers for construction projects.",
                ],
                info_lines=self.player_economy_lines(player),
                info_title="Harbor Details",
                clear=True,
                include_state=True,
            )
            trade = self.prompt_non_negative_int(f"{UI.order_label('Trade')} ships: ")
            raid = self.prompt_non_negative_int(f"{UI.order_label('Raid')} ships: ")
            guard = self.prompt_non_negative_int(f"{UI.order_label('Guard')} ships: ")
            fire = 0
            if player.fire_ships_unlocked:
                fire = self.prompt_non_negative_int(f"{UI.order_label('Fire')} ships: ")
            else:
                print(f"{UI.order_label('Fire')} ships: locked")
            allocation = Allocation(trade, raid, guard, fire)

            if allocation.total <= player.ships:
                idle = player.ships - allocation.total
                if idle:
                    print(self.idle_labor_preview(player, idle))
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

    def prompt_amount_menu(self, player, title, max_amount, unit, detail_lines):
        if not sys.stdin.isatty():
            return None

        value = 0
        digit_buffer = ""
        message = "Use left/right, digits, Enter to confirm."
        while True:
            control_lines = [
                title,
                f"Maximum: {UI.amount(max_amount, unit)}",
                f"Selected: {UI.amount(value, unit)}",
                "Left/right adjust. Type digits then Enter to set.",
            ]
            if digit_buffer:
                control_lines.append(f"Input: {UI.paint(digit_buffer, 'yellow', bold=True)}")
            control_lines.append(message)
            self.render_play_area(
                phase=f"{player.name}'s Buy Phase",
                control_lines=control_lines,
                info_lines=detail_lines,
                info_title="Harbor Details",
                clear=True,
                include_state=True,
            )

            key = self.with_cbreak(self.read_menu_key)
            if key == "left":
                value = max(0, value - 1)
                digit_buffer = ""
            elif key == "right":
                value = min(max_amount, value + 1)
                digit_buffer = ""
            elif key and key.isdigit():
                digit_buffer += key
            elif key == "backspace":
                digit_buffer = digit_buffer[:-1]
            elif key == "enter":
                if digit_buffer:
                    candidate = int(digit_buffer)
                    digit_buffer = ""
                    if candidate > max_amount:
                        message = UI.warning(f"Maximum is {max_amount}.")
                    else:
                        value = candidate
                        message = "Value set. Press Enter again to confirm."
                    continue
                return value
            elif key == "escape":
                digit_buffer = ""
                value = 0
                message = "Selection cleared."
            else:
                message = "Use left/right, digits, or Enter."

    def prompt_allocation_menu(self, player):
        fields = ["Trade", "Raid", "Guard"]
        if player.fire_ships_unlocked:
            fields.append("Fire")
        values = {field: 0 for field in fields}
        selected = 0
        digit_buffer = ""
        message = "Use arrows, number keys, Enter to confirm."

        while True:
            total = sum(values.values())
            port_workers = player.ships - total
            control_lines = [
                f"{player.name}, assign up to {UI.amount(player.ships, 'ships')}.",
                f"Orders: {UI.amount(total)}  Port workers: {UI.amount(port_workers)}",
                "Up/down select, left/right adjust.",
                "Type digits then Enter to set selected row.",
                self.idle_labor_preview(player, port_workers),
            ]
            for index, field in enumerate(fields):
                marker = UI.paint(">", "green", bold=True) if index == selected else " "
                value = UI.order_amount(field, values[field])
                control_lines.append(f"{marker} {UI.order_label(field, 6)} {value}")
            if not player.fire_ships_unlocked:
                control_lines.append(
                    f"  {UI.order_label('Fire', 6)} {UI.muted('locked')}"
                )
            control_lines.append(
                f"  {'Port':<6} {UI.amount(port_workers)} {UI.muted('(automatic)')}"
            )
            if digit_buffer:
                control_lines.append(f"Input: {UI.paint(digit_buffer, 'yellow', bold=True)}")
            control_lines.append(message)

            self.render_play_area(
                phase=f"{player.name}'s Orders",
                control_lines=control_lines,
                info_lines=self.player_economy_lines(player),
                info_title="Harbor Details",
                clear=True,
                include_state=True,
            )

            key = self.read_menu_key()
            if key == "up":
                selected = (selected - 1) % len(fields)
                digit_buffer = ""
            elif key == "down":
                selected = (selected + 1) % len(fields)
                digit_buffer = ""
            elif key == "left":
                field = fields[selected]
                if values[field] > 0:
                    values[field] -= 1
                    message = "Updated allocation."
                else:
                    message = UI.warning(f"{field} is already 0.")
                digit_buffer = ""
            elif key == "right":
                field = fields[selected]
                if port_workers > 0:
                    values[field] += 1
                    message = "Updated allocation."
                else:
                    message = UI.warning("No unassigned ships remain.")
                digit_buffer = ""
            elif key in {"t", "T"} and "Trade" in fields:
                selected = fields.index("Trade")
                digit_buffer = ""
            elif key in {"r", "R"} and "Raid" in fields:
                selected = fields.index("Raid")
                digit_buffer = ""
            elif key in {"g", "G"} and "Guard" in fields:
                selected = fields.index("Guard")
                digit_buffer = ""
            elif key in {"f", "F"} and "Fire" in fields:
                selected = fields.index("Fire")
                digit_buffer = ""
            elif key and key.isdigit():
                digit_buffer += key
            elif key == "backspace":
                digit_buffer = digit_buffer[:-1]
            elif key == "enter":
                if digit_buffer:
                    field = fields[selected]
                    requested = int(digit_buffer)
                    digit_buffer = ""
                    if requested > player.ships:
                        message = UI.warning(
                            f"{field} cannot exceed {player.ships} ships."
                        )
                    else:
                        other_ordered = sum(
                            amount
                            for name, amount in values.items()
                            if name != field
                        )
                        if requested + other_ordered > player.ships:
                            message = UI.warning(
                                f"{field} can be at most {player.ships - other_ordered}."
                            )
                        else:
                            values[field] = requested
                            message = "Value set."
                    continue
                return Allocation(
                    trade=values.get("Trade", 0),
                    raid=values.get("Raid", 0),
                    guard=values.get("Guard", 0),
                    fire=values.get("Fire", 0),
                )
            elif key == "escape":
                message = "Escape ignored; press Enter to confirm legal orders."
            else:
                message = "Use arrows, digits, or Enter."

    def clear_between_players(self):
        UI.clear_screen()
        if not UI.enabled:
            print("\n" * 40)

    def reveal_orders(self):
        UI.clear_screen()
        UI.section("REVEALING SEALED ORDERS", "magenta")
        self.print_player_panels(
            [
                (
                    UI.paint(player.name, "magenta", bold=True),
                    [f"Orders: {player.allocation}"],
                )
                for player in self.players
            ]
        )

    def pause_after_resolution(self):
        input("\nPress Enter to continue to convoys, supply, port labor, and buy phase...")
        print()

    def resolve_orders(self):
        UI.section("RESOLUTION", "red")
        player_one, player_two = self.players
        self.damaged_raider_cleanup = {}
        self.admiral_interventions = {player: player.admirals for player in self.players}
        for player in self.players:
            player.reset_fort_fire_blocks()

        self.port_labor = {
            player: max(0, player.ships - player.allocation.total)
            for player in self.players
        }
        self.supply_income = {
            player: {
                "trade": 0,
                "stolen": 0,
                "treasure": 0,
                "fishing": 0,
            }
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
        self.resolve_raider_skirmish(player_one, player_two)
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
        self.supply_income[player_one]["trade"] += result_one.supply_trade_income
        self.supply_income[player_one]["stolen"] += result_two.supply_stolen_income
        self.supply_income[player_one]["fishing"] += result_one.supply_fishing_income
        self.supply_income[player_two]["trade"] += result_two.supply_trade_income
        self.supply_income[player_two]["stolen"] += result_one.supply_stolen_income
        self.supply_income[player_two]["fishing"] += result_two.supply_fishing_income

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

        if fire_strength == 0:
            print(f"\n{attacker.name} launches no fire ships.")
            return

        print(f"\n{attacker.name}'s fire ships bear down on {defender.name}:")

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

        if raid_strength == 0:
            print(f"\n{raider.name} sends no raiders toward {guarder.name}.")
            return
        if guard_strength == 0:
            print(
                f"\n{raider.name}'s {raid_strength} raid ship(s) find "
                f"{guarder.name}'s sea lanes unguarded."
            )
            return

        print(f"\n{raider.name}'s raiders meet {guarder.name}'s guards:")

        raider_losses = 0
        guarder_losses = 0

        if raid_strength > guard_strength:
            guarder_losses = self.calculate_overwhelming_losses(
                stronger=raid_strength,
                weaker=guard_strength,
                engaged_ships=engaged_ships,
            )
            guarder_losses = self.apply_admiral_overwhelming_bonus(
                commander=raider,
                target=guarder,
                losses=guarder_losses,
                engaged_ships=engaged_ships,
            )
        elif guard_strength > raid_strength:
            raider_losses = self.calculate_overwhelming_losses(
                stronger=guard_strength,
                weaker=raid_strength,
                engaged_ships=engaged_ships,
            )
            raider_losses = self.apply_admiral_overwhelming_bonus(
                commander=guarder,
                target=raider,
                losses=raider_losses,
                engaged_ships=engaged_ships,
            )
        elif raid_strength >= 2:
            raider_losses = 1
            guarder_losses = 1

        raider_result = self.apply_admiral_battle_losses(
            player=raider,
            role="raid",
            requested_losses=raider_losses,
        )
        guarder_result = self.apply_admiral_battle_losses(
            player=guarder,
            role="guard",
            requested_losses=guarder_losses,
        )
        raider_losses = raider_result["sunk"]
        guarder_losses = guarder_result["sunk"]

        raider.allocation.raid -= engaged_ships
        guarder.allocation.guard -= engaged_ships
        self.record_damaged_raider_battle_losses(
            raider,
            guarder,
            raider_losses,
            guarder_losses,
        )

        if (
            raider_losses == 0
            and guarder_losses == 0
            and not raider_result["saved"]
            and not guarder_result["saved"]
        ):
            print(" - Even light forces disengage. No ships sink or reach trade.")
            return

        if raider_losses:
            print(f" - {raider.name} loses {raider_losses} raid ship(s).")
        if raider_result["saved"]:
            print(
                f" - {raider.name}'s admiral saves 1 ship; "
                "it becomes damaged instead of sinking."
            )
        if guarder_losses:
            print(f" - {guarder.name} loses {guarder_losses} guard ship(s).")
        if guarder_result["saved"]:
            print(
                f" - {guarder.name}'s admiral saves 1 ship; "
                "it becomes damaged instead of sinking."
            )

    def resolve_raider_skirmish(self, player_one, player_two):
        raid_one = player_one.allocation.raid
        raid_two = player_two.allocation.raid
        engaged_ships = min(raid_one, raid_two)

        if engaged_ships <= 0:
            return

        print(
            f"\n{player_one.name}'s raiders cross wakes with "
            f"{player_two.name}'s raiders:"
        )

        hits_one = 0
        hits_two = 0
        if raid_one > raid_two:
            hits_two = self.calculate_overwhelming_losses(
                stronger=raid_one,
                weaker=raid_two,
                engaged_ships=engaged_ships,
            )
            hits_two = self.apply_admiral_overwhelming_bonus(
                commander=player_one,
                target=player_two,
                losses=hits_two,
                engaged_ships=engaged_ships,
                effect_label="skirmish hits",
            )
        elif raid_two > raid_one:
            hits_one = self.calculate_overwhelming_losses(
                stronger=raid_two,
                weaker=raid_one,
                engaged_ships=engaged_ships,
            )
            hits_one = self.apply_admiral_overwhelming_bonus(
                commander=player_two,
                target=player_one,
                losses=hits_one,
                engaged_ships=engaged_ships,
                effect_label="skirmish hits",
            )
        elif raid_one >= 2:
            hits_one = 1
            hits_two = 1
        else:
            print(" - Lone raiders shadow each other and break off.")
            return

        result_one = self.apply_raider_skirmish_hits(player_one, player_two, hits_one)
        result_two = self.apply_raider_skirmish_hits(player_two, player_one, hits_two)

        player_one.allocation.raid -= engaged_ships
        player_two.allocation.raid -= engaged_ships

        if not any(
            [
                result_one["damaged"],
                result_one["sunk"],
                result_two["damaged"],
                result_two["sunk"],
            ]
        ):
            print(" - The raiders maneuver for position, then scatter.")
            return

        self.print_raider_skirmish_result(player_one, result_one)
        self.print_raider_skirmish_result(player_two, result_two)

    def apply_raider_skirmish_hits(self, player, opponent, hits):
        active_raiders = player.allocation.raid
        engaged_raiders = min(active_raiders, opponent.allocation.raid)
        damaged_engaged = min(player.damaged_ships, engaged_raiders)
        sunk = min(damaged_engaged, hits)
        damaged = min(hits - sunk, engaged_raiders - damaged_engaged)

        player.ships -= sunk
        player.damaged_ships -= sunk
        player.damaged_ships += damaged
        player.raid_skirmish_damage += damaged
        player.raid_skirmish_sunk += sunk
        player.damaged_raiders_sunk += sunk
        player.cap_damaged_ships()

        cleanup = self.damaged_raider_cleanup.get((player, opponent))
        if cleanup is not None:
            cleanup["damaged_raiders"] = max(
                0,
                cleanup["damaged_raiders"] - damaged_engaged,
            )

        return {
            "hits": hits,
            "damaged": damaged,
            "sunk": sunk,
            "damaged_engaged": damaged_engaged,
        }

    def print_raider_skirmish_result(self, player, result):
        if result["sunk"]:
            print(
                f" - {player.name}'s already-damaged raider(s) cannot take "
                f"the strain: {result['sunk']} ship(s) sink."
            )
        if result["damaged"]:
            print(
                f" - {player.name} takes {result['damaged']} skirmish hit(s); "
                f"{result['damaged']} raid ship(s) become damaged."
            )

    def apply_admiral_overwhelming_bonus(
        self,
        commander,
        target,
        losses,
        engaged_ships,
        effect_label="losses",
    ):
        if losses != 2 or self.admiral_interventions.get(commander, 0) <= 0:
            return losses
        boosted_losses = min(3, engaged_ships)
        if boosted_losses <= losses:
            return losses
        self.admiral_interventions[commander] -= 1
        print(
            f" - {commander.name}'s admiral presses the advantage: "
            f"{target.name} faces {boosted_losses} {effect_label} "
            f"instead of {losses}."
        )
        return boosted_losses

    def apply_admiral_battle_losses(self, player, role, requested_losses):
        active_ships = getattr(player.allocation, role)
        damaged_active = min(player.damaged_ships, active_ships)
        damaged_sunk = min(damaged_active, requested_losses)
        undamaged_losses = max(0, requested_losses - damaged_sunk)
        saved = 0
        if undamaged_losses > 0 and self.admiral_interventions.get(player, 0) > 0:
            saved = 1
            undamaged_losses -= 1
            self.admiral_interventions[player] -= 1

        sunk = damaged_sunk + undamaged_losses
        player.ships -= sunk
        player.damaged_ships -= damaged_sunk
        player.damaged_ships += saved
        player.cap_damaged_ships()
        return {"sunk": sunk, "saved": saved, "damaged_sunk": damaged_sunk}

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

        conscripts = self.admiralty_conscript_defense(defender)
        required_raids = defender.port_attack_threshold + conscripts

        if attacker.allocation.raid < required_raids:
            return False

        self.game_over = True
        self.port_destroyer = attacker
        self.port_destroyed = defender
        defense_parts = [defender.port_defense_status]
        if conscripts:
            defense_parts.append(f"+{conscripts} Admiralty conscripts")
        print(
            f"\n{attacker.name} sends {attacker.allocation.raid} raid ship(s) "
            f"against {defender.name}'s undefended home port "
            f"({required_raids} required: {'; '.join(defense_parts)})."
        )
        print(f"{defender.name}'s home port is destroyed.")
        return True

    def admiralty_conscript_defense(self, defender):
        if not defender.admiralty_completed:
            return 0
        return max(0, self.port_labor.get(defender, 0))

    def resolve_income(self, trader, opponent):
        trader.last_treasure_growth = 0
        trader.last_treasure_growth_boost = 0
        remaining_trade = trader.allocation.trade
        starting_trade = remaining_trade
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
        active_raids -= raid_intercepts
        remaining_trade -= raid_intercepts
        stolen_trade_income = raid_intercepts * Rules.TRADE_INCOME
        stolen_income += stolen_trade_income
        opponent.allocation.raid = active_raids

        smuggled_trade = min(opponent.allocation.guard, remaining_trade)
        remaining_trade -= smuggled_trade
        captured_smuggling_ships = 0
        if (
            smuggled_trade > 0
            and opponent.guard_captains >= Rules.GUARD_CAPTAIN_SHIP_CAPTURE_THRESHOLD
        ):
            captured_smuggling_ships = min(
                smuggled_trade,
                Rules.GUARD_CAPTAIN_SHIP_CAPTURES_PER_TURN,
            )
            trader.ships -= captured_smuggling_ships
            opponent.ships += captured_smuggling_ships
            trader.cap_damaged_ships()
            opponent.guard_captain_ship_captures += captured_smuggling_ships
            confiscated_trade = 0
        else:
            confiscated_trade = min(
                smuggled_trade,
                opponent.guard_captains * Rules.GUARD_CAPTAIN_CONFISCATIONS_PER_TURN,
            )
        paid_smuggled_trade = (
            smuggled_trade - confiscated_trade - captured_smuggling_ships
        )
        smuggle_rate = Rules.TRADE_INCOME if opponent.supply <= -1 else Rules.SMUGGLE_INCOME
        smuggle_income = paid_smuggled_trade * smuggle_rate
        smuggle_boost_income = max(
            0,
            smuggle_income - paid_smuggled_trade * Rules.SMUGGLE_INCOME,
        )
        confiscated_income = confiscated_trade * smuggle_rate

        normal_income = remaining_trade * Rules.TRADE_INCOME
        trade_bonus = self.calculate_trade_guild_bonus(trader, remaining_trade)
        base_trade_bonus = 0
        if trader.trade_guild_completed and remaining_trade > 0:
            base_trade_bonus = max(1, remaining_trade // Rules.TRADE_GUILD_BONUS_STEP)
        guild_boost_income = max(0, trade_bonus - base_trade_bonus)
        supply_trade_bonus = 0
        if trader.supply >= 5 and remaining_trade > 0:
            supply_trade_bonus = remaining_trade
        fishing_income = trader.fishing_income
        trade_income = smuggle_income + normal_income + trade_bonus + supply_trade_bonus
        boosted_income = smuggle_boost_income + guild_boost_income + supply_trade_bonus
        unboosted_trade_income = max(0, trade_income - boosted_income)
        treasure_growth = int(trade_income * Rules.TREASURE_TRADE_PERCENT)
        treasure_growth_boost = max(
            0,
            treasure_growth
            - int(unboosted_trade_income * Rules.TREASURE_TRADE_PERCENT),
        )

        if starting_trade <= 0:
            print(" - No trade ships sail this turn.")
        elif raid_intercepts:
            print(
                f" - {raid_intercepts} trade ship(s) intercepted by raids; "
                f"{opponent.name} steals {stolen_trade_income} gold."
            )
        elif active_raids:
            print(" - Raiders patrol the lanes but catch no trade ships.")

        if smuggled_trade:
            print(
                f" - {smuggled_trade} trade ship(s) smuggle past guards for "
                f"{smuggle_income} gold."
            )
            if opponent.supply <= -1 and paid_smuggled_trade:
                print(
                    f" - {opponent.name}'s supply strain opens the lanes; "
                    "smugglers earn full trade income."
                )
        if confiscated_income:
            print(
                f" - Guard captains catch {confiscated_trade} smuggler(s); "
                f"{opponent.name} confiscates {confiscated_income} gold."
            )
        if captured_smuggling_ships:
            print(
                f" - Veteran guard captains seize {captured_smuggling_ships} "
                f"smuggling ship(s); {opponent.name} adds them to the fleet."
            )
        if remaining_trade:
            print(
                f" - {remaining_trade} trade ship(s) complete trade for "
                f"{normal_income} gold."
            )
        if trade_bonus:
            print(f" - Trade guild bonus adds {trade_bonus} gold.")
        if supply_trade_bonus:
            print(
                f" - Full supply reserves add {supply_trade_bonus} gold "
                "to completed trade."
            )
        if fishing_income:
            print(
                f" - Fishing boats bring in {fishing_income} domestic gold."
            )
        elif trader.fishing_boats and trader.fishing_dock_disabled:
            print(" - Fishing boats are idle while the docks are disabled.")

        if treasure_growth and not trader.has_treasure_at_sea:
            trader.treasure_value += treasure_growth
            trader.last_treasure_growth = treasure_growth
            trader.last_treasure_growth_boost = treasure_growth_boost
            print(f" - Treasure route grows by {treasure_growth} gold.")
        elif treasure_growth:
            print(" - Treasure route does not grow while its convoy is at sea.")

        return ResolutionResult(
            trade_income=trade_income,
            fishing_income=fishing_income,
            stolen_income=stolen_income,
            confiscated_income=confiscated_income,
            captured_smuggling_ships=captured_smuggling_ships,
            treasure_growth=treasure_growth,
            supply_trade_income=trade_income,
            supply_stolen_income=stolen_income,
            supply_fishing_income=fishing_income,
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

        bonus = max(1, completed_trade // Rules.TRADE_GUILD_BONUS_STEP)
        if trader.supply >= 4:
            bonus *= 2
        return bonus

    def apply_supply(self):
        UI.section("SUPPLY", "yellow")
        for player in self.players:
            ledger = self.supply_income.get(player, {})
            trade = ledger.get("trade", 0)
            stolen = ledger.get("stolen", 0)
            treasure = ledger.get("treasure", 0)
            fishing = ledger.get("fishing", 0)
            counted_fishing = fishing // 2
            counted_income = trade + stolen + treasure + counted_fishing
            need = player.supply_need
            warchest_supply, warchest_cost = self.offer_emergency_supply_warchest(
                player,
                need,
                counted_income,
            )
            effective_counted_income = counted_income + warchest_supply
            change = self.calculate_supply_change(
                player.supply,
                need,
                effective_counted_income,
            )
            change = self.cap_supply_change_for_turn(change)
            previous_supply = player.supply
            if previous_supply >= 0 and change < 0:
                change = -1
            player.supply = self.clamp_supply(player, player.supply + change)
            warchest_text = ""
            if warchest_supply:
                warchest_text = (
                    f", {warchest_supply} war chest for {warchest_cost} gold"
                )
            print(
                f"{player.name} supply: need {need}, covered by {effective_counted_income} "
                f"({trade} trade, {stolen} stolen, {treasure} treasure, "
                f"{counted_fishing} fishing credit{warchest_text}); "
                f"{previous_supply:+d} -> {player.supply:+d}."
            )
            missed_need = effective_counted_income < need
            events = self.apply_supply_effects(player, previous_supply, missed_need)
            player.last_supply_events = events[:]
            self.print_supply_queue(player, previous_supply, player.supply, events)

    def offer_emergency_supply_warchest(self, player, need, counted_income):
        if self.turn <= 1:
            return 0, 0
        if need <= 0 or counted_income >= need:
            return 0, 0
        if player.supply >= 0:
            return 0, 0
        shortfall = need - counted_income
        markup = player.supply_warchest_markup
        cost = shortfall * markup
        if player.gold < cost:
            return 0, 0
        if not self.wants_emergency_supply_warchest(
            player,
            need,
            counted_income,
            shortfall,
            cost,
        ):
            return 0, 0
        player.gold -= cost
        return shortfall, cost

    def wants_emergency_supply_warchest(
        self,
        player,
        need,
        counted_income,
        covered,
        cost,
    ):
        if not sys.stdin.isatty():
            return False

        markup = player.supply_warchest_markup
        control_lines = [
            f"{player.name}'s quartermaster requests emergency stores.",
            f"Spend {cost} gold to cover {covered} missing supply? [y/N]",
        ]
        info_lines = [
            UI.paint("=== EMERGENCY SUPPLY COUNCIL ===", "yellow", bold=True),
            (
                f"The harbor bells sound: sea income covers "
                f"{UI.amount(counted_income, color='yellow')}/{need} supply."
            ),
            (
                f"The treasury can break its war seal for "
                f"{UI.amount(markup, 'gold', 'yellow')} per missing supply."
            ),
            (
                f"Release {UI.amount(cost, 'gold', 'yellow')} now to add "
                f"{UI.amount(covered, 'supply', 'green')} before attrition is judged."
            ),
        ]
        with redirect_stdout(sys.__stdout__):
            self.render_play_area(
                phase="Emergency Supply",
                control_lines=control_lines,
                info_lines=info_lines,
                info_title="Bulletin Board",
                clear=True,
                include_state=True,
            )
            response = input(f"{player.name}, open the war chest? [y/N] ")
        return response.strip().lower() in {"y", "yes"}

    def clamp_supply(self, player, supply):
        maximum = Rules.SUPPLY_MAX if player.trade_guild_completed else 4
        return max(Rules.SUPPLY_MIN, min(maximum, supply))

    def calculate_supply_change(self, current_supply, need, counted_income):
        if need <= 0:
            return 1 if current_supply < 0 else 0
        if counted_income < need:
            if current_supply < -1:
                return -1
            if current_supply < 0:
                return -1
            if counted_income * 5 <= need:
                return -2
            return -1
        if current_supply >= 3:
            return 1 if counted_income >= need * 5 else 0
        if current_supply >= 2:
            return 1 if counted_income >= need * 5 else 0
        if current_supply >= 0:
            if counted_income >= need * 5:
                return 2
            if counted_income >= need * 2:
                return 1
            return 0
        if counted_income >= need * 5:
            return 3
        if counted_income >= need * 2:
            return 2
        return -1

    def cap_supply_change_for_turn(self, change):
        if self.turn <= 3:
            cap = 1
        elif self.turn <= 8:
            cap = 2
        else:
            cap = 3
        return max(-cap, min(cap, change))

    def apply_supply_effects(self, player, previous_supply, missed_need):
        if player.supply >= 4:
            events = []
            if player.trade_guild_completed:
                events.append("Guild x2")
                print(
                    f" - {player.name}'s stocked warehouses energize trade "
                    "guild routes."
                )
            if player.supply >= 5:
                events.append("Trade +1")
                print(
                    f" - {player.name}'s full reserves add 1 gold to each "
                    "completed trade ship."
                )
            return events
        if player.supply >= 0:
            return []

        events = ["Smg+"]
        print(
            f" - {player.name}'s supply strain helps enemy smugglers earn "
            "full trade income."
        )
        if not missed_need:
            print(
                f" - {player.name}'s supply strain stabilizes this month; "
                "no crisis effect triggers."
            )
            return events

        player.supply_crises += 1
        if previous_supply >= 0:
            print(
                f" - {player.name} has slipped into shortage, but no attrition "
                "hits yet."
            )
            return events
        if player.supply == -2:
            event = self.apply_supply_light_damage(player)
            if event:
                events.append(event)
        elif player.supply == -3:
            losses = self.apply_supply_desertion(player, Rules.SUPPLY_DESERTION_PERCENT)
            if losses:
                events.append(f"Ship -{losses}")
            elif self.admirals_fully_administer_fleet(player):
                events.append("Adm -desert")
            elif player.ships <= 0:
                events.append("No ships")
            event = self.apply_supply_fishing_loss(player, dock_absorbs=True)
            if event:
                events.append(event)
        elif player.supply == -4:
            burn = self.burn_supply_infrastructure(
                player,
                captains_can_quell=True,
            )
            if burn:
                if burn in {"unrest quelled", "captains quelled"}:
                    events.append(self.supply_token(burn))
                else:
                    events.append(f"Burn:{self.supply_token(burn)}")
            else:
                losses = self.apply_supply_desertion(
                    player,
                    Rules.SUPPLY_HEAVY_DESERTION_PERCENT,
                )
                if losses:
                    events.append(f"Ship -{losses}")
                elif self.admirals_fully_administer_fleet(player):
                    events.append("Adm -desert")
                elif player.ships <= 0:
                    events.append("No ships")
        elif player.supply <= -5:
            event = self.apply_supply_fishing_loss(player, confiscated=True)
            if event:
                events.append(event)
            burn = self.burn_supply_infrastructure(
                player,
                cheapest=player.guard_captains >= Rules.GUARD_CAPTAIN_MAX,
            )
            if burn:
                if burn in {"unrest quelled", "captains quelled"}:
                    events.append(self.supply_token(burn))
                else:
                    events.append(f"Burn:{self.supply_token(burn)}")
            losses = self.apply_supply_desertion(player, Rules.SUPPLY_HEAVY_DESERTION_PERCENT)
            if losses:
                events.append(f"Ship -{losses}")
            elif self.admirals_fully_administer_fleet(player):
                events.append("Adm -desert")
            elif player.ships <= 0:
                events.append("No ships")
        return events

    def print_supply_queue(self, player, previous_supply, current_supply, events):
        event_text = (
            ", ".join(player.format_supply_event(event) for event in events)
            if events
            else "no attrition"
        )
        color = "green" if current_supply > previous_supply else (
            "red" if current_supply < previous_supply else "yellow"
        )
        print(
            " > "
            f"{player.name} supply queue: "
            f"{UI.paint(f'{previous_supply:+d}->{current_supply:+d}', color, bold=True)}; "
            f"{event_text}."
        )

    def apply_supply_light_damage(self, player):
        if player.ships > 0:
            damaged = min(
                player.ships - player.damaged_ships,
                max(1, math.ceil(player.ships * Rules.SUPPLY_LIGHT_DAMAGE_PERCENT)),
            )
            if damaged > 0:
                player.damaged_ships += damaged
                player.raid_damage_events += damaged
                print(
                    f" - Short rations damage {damaged} ship(s) in "
                    f"{player.name}'s fleet."
                )
                return f"Dmg +{damaged}"
        return self.apply_supply_fishing_loss(player)

    def apply_supply_desertion(self, player, percent):
        if player.ships <= 0:
            return 0
        percent = self.admiralty_desertion_percent(player, percent)
        if percent <= 0:
            print(
                f" - {player.name}'s Admiralty staff prevents supply desertion."
            )
            return 0
        losses = player.remove_ships_for_supply(max(1, math.ceil(player.ships * percent)))
        if losses:
            print(
                f" - Supply desertion costs {player.name} {losses} ship(s)."
            )
        return losses

    def admiralty_desertion_percent(self, player, percent):
        if not self.admirals_fully_administer_fleet(player):
            return percent
        if percent <= Rules.SUPPLY_DESERTION_PERCENT:
            return 0
        if percent >= Rules.SUPPLY_HEAVY_DESERTION_PERCENT:
            return Rules.SUPPLY_DESERTION_PERCENT
        return percent

    def admirals_fully_administer_fleet(self, player):
        return (
            player.admiralty_completed
            and player.admiral_slots > 0
            and player.admirals >= player.admiral_slots
        )

    def apply_supply_fishing_loss(self, player, dock_absorbs=False, confiscated=False):
        if not player.fishing_boats:
            return None
        if dock_absorbs and player.fishing_dock_built and not player.fishing_dock_disabled:
            lost_income = player.fishing_income
            player.disable_fishing_dock()
            player.gold -= lost_income
            player.supply_fishing_losses += lost_income
            print(
                f" - Fishing docks absorb unrest; {player.name} loses "
                f"{lost_income} fishing income until repairs."
            )
            return f"Fish -{lost_income} Dock!"
        lost_income = player.fishing_income if confiscated else player.fishing_income // 2
        if lost_income <= 0:
            return None
        player.gold -= lost_income
        player.supply_fishing_losses += lost_income
        if confiscated:
            print(
                f" - Crisis confiscates all fishing income from {player.name} "
                f"({lost_income} gold)."
            )
            return f"Fish -{lost_income}"
        else:
            print(
                f" - Supply disruption forfeits half of {player.name}'s "
                f"fishing income ({lost_income} gold)."
            )
            return f"Fish -{lost_income}"

    def supply_burn_candidates(self, player):
        candidates = []
        if player.shipyard_completed:
            candidates.append(("shipyard", Rules.SHIPYARD_COST + Rules.SHIPYARD_LABOR_REQUIRED))
        if player.fort_completed:
            candidates.append(("fort", Rules.FORT_COST + Rules.FORT_LABOR_REQUIRED))
        if player.trade_guild_completed:
            candidates.append(("trade guild", Rules.TRADE_GUILD_COST + Rules.TRADE_GUILD_LABOR_REQUIRED))
        if player.fishing_dock_built and not player.fishing_dock_disabled:
            candidates.append(("fishing docks", Rules.FISHING_DOCK_COST + Rules.FISHING_DOCK_LABOR_REQUIRED))
        if player.dockhouse_completed:
            candidates.append(("dockhouse", Rules.DOCKHOUSE_COST + Rules.DOCKHOUSE_LABOR_REQUIRED))
        if player.dry_dock_completed:
            candidates.append(("dry dock", Rules.DRY_DOCK_COST + Rules.DRY_DOCK_LABOR_REQUIRED))
        if player.fire_ships_unlocked:
            candidates.append(("fire ship plans", Rules.FIRE_SHIP_UPGRADE_COST))
        if player.admiralty_completed:
            candidates.append(("admiralty", Rules.ADMIRALTY_COST + Rules.ADMIRALTY_LABOR_REQUIRED))
        return candidates

    def burn_supply_infrastructure(self, player, cheapest=False, captains_can_quell=False):
        candidates = self.supply_burn_candidates(player)
        if not candidates:
            return False
        if captains_can_quell and player.guard_captains >= Rules.GUARD_CAPTAIN_MAX:
            print(
                f" - {player.name}'s full guard-captain roster contains the unrest "
                "before infrastructure burns."
            )
            return "captains quelled"
        if self.admiralty_quells_unrest(player):
            return "unrest quelled"
        if cheapest:
            target = min(candidates, key=lambda candidate: candidate[1])[0]
        else:
            weights = [1 / cost for _, cost in candidates]
            target = random.choices(candidates, weights=weights, k=1)[0][0]
        if target == "shipyard":
            player.burn_shipyard()
        elif target == "fort":
            player.burn_fort()
        elif target == "trade guild":
            player.burn_trade_guild()
        elif target == "fishing docks":
            player.burn_fishing_dock()
        elif target == "dockhouse":
            player.burn_dockhouse()
        elif target == "dry dock":
            player.burn_dry_dock()
        elif target == "fire ship plans":
            player.burn_fire_plans()
        elif target == "admiralty":
            player.burn_admiralty()
        player.supply_unrest_burns += 1
        print(f" - Civil unrest burns {player.name}'s {target}.")
        return target

    def admiralty_quells_unrest(self, player):
        if not player.admiralty_completed or player.admiralty_unrest_response_used:
            return False
        player.admiralty_unrest_response_used = True
        print(
            f" - {player.name}'s Admiralty restores order before unrest can "
            "burn infrastructure."
        )
        return True

    def supply_token(self, target):
        return {
            "shipyard": "Yard",
            "fort": "Fort",
            "trade guild": "Guild",
            "fishing docks": "Dock",
            "dockhouse": "Hand",
            "dry dock": "Dry",
            "fire ship plans": "Fire",
            "admiralty": "Adm",
            "unrest quelled": "Adm!",
            "captains quelled": "Capt!",
        }.get(target, target)

    def apply_port_labor(self):
        UI.section("PORT LABOR", "blue")
        any_labor = False

        for player in self.players:
            if player.dockhands and not player.dockhouse_completed:
                player.dockhand_idle_turns += 1
            port_labor = self.port_labor.get(player, 0) + player.dockhand_construction_labor
            shipyard_labor = player.add_shipyard_labor(port_labor)
            port_labor -= shipyard_labor
            fort_labor = player.add_fort_labor(port_labor)
            port_labor -= fort_labor
            trade_guild_labor = player.add_trade_guild_labor(port_labor)
            port_labor -= trade_guild_labor
            fishing_dock_labor = player.add_fishing_dock_labor(port_labor)
            port_labor -= fishing_dock_labor
            dockhouse_labor = player.add_dockhouse_labor(port_labor)
            port_labor -= dockhouse_labor
            dry_dock_labor = player.add_dry_dock_labor(port_labor)
            port_labor -= dry_dock_labor
            admiralty_labor = player.add_admiralty_labor(port_labor)
            boatwright_boats = player.apply_dockhand_boatwright()

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

            if dockhouse_labor:
                any_labor = True
                print(
                    f"{player.name} applies {dockhouse_labor} labor to the "
                    f"dockhouse ({player.dockhouse_labor}/"
                    f"{Rules.DOCKHOUSE_LABOR_REQUIRED})."
                )
                if player.dockhouse_completed:
                    print(
                        f"{player.name}'s dockhouse is complete. "
                        "Dock hands can now be hired."
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

            if boatwright_boats:
                any_labor = True
                print(
                    f"{player.name}'s dock hands build {boatwright_boats} "
                    f"fishing boat(s) for "
                    f"{boatwright_boats * Rules.DOCKHAND_BOATWRIGHT_COST} gold."
                )

            if admiralty_labor:
                any_labor = True
                print(
                    f"{player.name} applies {admiralty_labor} labor to the "
                    f"admiralty ({player.admiralty_labor}/"
                    f"{Rules.ADMIRALTY_LABOR_REQUIRED})."
                )
                if player.admiralty_completed:
                    print(
                        f"{player.name}'s admiralty is complete. "
                        "Admirals and overtime are now available."
                    )

            if not shipyard_labor and player.shipyard_started and not player.shipyard_completed:
                print(f"{player.name} has no port workers to work on the shipyard.")

            if not fort_labor and player.fort_started and not player.fort_completed:
                print(f"{player.name} has no port workers to work on the fort.")

            if (
                not trade_guild_labor
                and player.trade_guild_started
                and not player.trade_guild_completed
            ):
                print(f"{player.name} has no port workers to work on the trade guild.")

            if (
                not fishing_dock_labor
                and player.fishing_dock_started
                and not player.fishing_dock_built
            ):
                print(f"{player.name} has no port workers to work on the fishing docks.")

            if (
                not dockhouse_labor
                and player.dockhouse_started
                and not player.dockhouse_completed
            ):
                print(f"{player.name} has no port workers to work on the dockhouse.")

            if (
                not dry_dock_labor
                and player.dry_dock_started
                and not player.dry_dock_completed
            ):
                print(f"{player.name} has no port workers to work on the dry dock.")

            if (
                not admiralty_labor
                and player.admiralty_started
                and not player.admiralty_completed
            ):
                print(f"{player.name} has no port workers to work on the admiralty.")

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
                    self.supply_income.setdefault(player, {}).setdefault("treasure", 0)
                    self.supply_income[player]["treasure"] += payout
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
        self.buy_phase_baselines = {}
        for player in self.players:
            player.refresh_dockhand_repair_discount()
            self.buy_phase_baselines[player] = self.snapshot_player(player)
            self.run_buy_menu(player)

        self.buy_phase_baselines = {}
        UI.clear_screen()
        self.show_state()

    def run_buy_menu(self, player):
        self.auto_launch_final_payroll(player)
        if sys.stdin.isatty():
            return self.run_buy_menu_interactive(player)

        while True:
            actions = self.buy_menu_actions(player)
            action_lines = [f"{player.name}, choose a buy-phase action."]
            for choice, label, _action, disabled_reason in actions:
                if disabled_reason:
                    action_lines.append(
                        UI.muted(f"{choice}. {label:<24} - {disabled_reason}")
                    )
                else:
                    action_lines.append(
                        f"{UI.paint(choice + '.', 'green', bold=True)} "
                        f"{label}"
                    )
            action_lines.append(f"{UI.paint('0.', 'green', bold=True)} Done")
            self.render_play_area(
                phase=f"{player.name}'s Buy Phase",
                control_lines=action_lines,
                info_lines=self.player_economy_lines(player),
                info_title="Harbor Details",
                clear=True,
                include_state=True,
            )

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

    def run_buy_menu_interactive(self, player):
        selected = 0
        digit_buffer = ""
        message = "Use arrows, type a number, Enter to choose."

        while True:
            actions = self.buy_menu_actions(player)
            menu_items = actions + [("0", "Done", None, None)]
            selected = min(selected, len(menu_items) - 1)
            control_lines = [f"{player.name}, choose a buy-phase action."]
            control_lines.append("Up/down select, digits jump, Enter chooses.")
            if digit_buffer:
                control_lines.append(f"Input: {UI.paint(digit_buffer, 'yellow', bold=True)}")
            for index, (choice, label, _action, disabled_reason) in enumerate(menu_items):
                marker = UI.paint(">", "green", bold=True) if index == selected else " "
                line = f"{marker} {choice}. {label}"
                if disabled_reason:
                    line = UI.muted(f"{line:<32} - {disabled_reason}")
                elif choice == "0":
                    line = UI.paint(line, "green", bold=True)
                control_lines.append(line)
            control_lines.append(message)

            self.render_play_area(
                phase=f"{player.name}'s Buy Phase",
                control_lines=control_lines,
                info_lines=self.player_economy_lines(player),
                info_title="Harbor Details",
                clear=True,
                include_state=True,
            )

            key = self.with_cbreak(self.read_menu_key)
            if key == "up":
                selected = (selected - 1) % len(menu_items)
                digit_buffer = ""
            elif key == "down":
                selected = (selected + 1) % len(menu_items)
                digit_buffer = ""
            elif key and key.isdigit():
                digit_buffer += key
                matching = [
                    index
                    for index, (choice, _label, _action, _disabled) in enumerate(menu_items)
                    if choice == digit_buffer
                ]
                if matching:
                    selected = matching[0]
            elif key == "backspace":
                digit_buffer = digit_buffer[:-1]
            elif key == "enter":
                if digit_buffer:
                    matching = [
                        index
                        for index, (choice, _label, _action, _disabled) in enumerate(menu_items)
                        if choice == digit_buffer
                    ]
                    if not matching:
                        message = UI.warning(f"No action {digit_buffer}.")
                        digit_buffer = ""
                        continue
                    selected = matching[0]
                    digit_buffer = ""

                choice, label, action, disabled_reason = menu_items[selected]
                if choice == "0":
                    print(f"{player.name} finishes the buy phase.")
                    return
                if disabled_reason:
                    message = UI.warning(f"{label} unavailable: {disabled_reason}.")
                    continue
                action(player)
                message = f"{label} complete."
            elif key == "escape":
                digit_buffer = ""
                message = "Input cleared."
            else:
                message = "Use arrows, digits, or Enter."

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
                "Hire administrator",
                self.hire_administrator_action,
                self.administrator_disabled_reason(player),
            ),
            (
                "6",
                "Build/repair fishing docks",
                self.fishing_dock_action,
                self.fishing_dock_disabled_reason(player),
            ),
            (
                "7",
                "Start dockhouse",
                self.start_dockhouse_action,
                self.dockhouse_disabled_reason(player),
            ),
            (
                "8",
                "Hire dock hand",
                self.hire_dockhand_action,
                self.dockhand_disabled_reason(player),
            ),
            (
                "9",
                "Assign dock hands",
                self.assign_dockhands_action,
                self.assign_dockhands_disabled_reason(player),
            ),
            (
                "10",
                "Buy fishing boats",
                self.buy_fishing_boats_action,
                self.buy_fishing_boats_disabled_reason(player),
            ),
            (
                "11",
                "Hire guard captain",
                self.hire_guard_captain_action,
                self.guard_captain_disabled_reason(player),
            ),
            (
                "12",
                "Buy fire ship plans",
                self.buy_fire_ship_plans_action,
                self.fire_ship_plans_disabled_reason(player),
            ),
            (
                "13",
                "Repair damaged ships",
                self.repair_damaged_ships_action,
                self.repair_damaged_ships_disabled_reason(player),
            ),
            (
                "14",
                "Start dry dock",
                self.start_dry_dock_action,
                self.dry_dock_disabled_reason(player),
            ),
            (
                "15",
                "Start admiralty",
                self.start_admiralty_action,
                self.admiralty_disabled_reason(player),
            ),
            (
                "16",
                "Recruit admiral",
                self.recruit_admiral_action,
                self.admiral_disabled_reason(player),
            ),
            (
                "17",
                "Admiralty overtime",
                self.admiralty_overtime_action,
                self.admiralty_overtime_disabled_reason(player),
            ),
            (
                "18",
                "Launch treasure convoy",
                self.launch_treasure_action,
                self.treasure_launch_disabled_reason(player),
            ),
            (
                "19",
                "Launch payroll convoy",
                self.launch_payroll_action,
                self.payroll_launch_disabled_reason(player),
            ),
        ]

    def buy_ships_disabled_reason(self, player):
        if player.gold < player.ship_cost:
            return f"needs {player.ship_cost} gold"
        return None

    def shipyard_disabled_reason(self, player):
        if player.shipyard_completed:
            return "already completed"
        if player.shipyard_started:
            return "already started"
        if player.gold < Rules.SHIPYARD_COST:
            return f"needs {Rules.SHIPYARD_COST} gold"
        return None

    def fort_disabled_reason(self, player):
        if player.fort_completed:
            return "already completed"
        if player.fort_started:
            return "already started"
        if player.gold < Rules.FORT_COST:
            return f"needs {Rules.FORT_COST} gold"
        return None

    def trade_guild_disabled_reason(self, player):
        if player.trade_guild_completed:
            return "already completed"
        if player.trade_guild_started:
            return "already started"
        if player.gold < Rules.TRADE_GUILD_COST:
            return f"needs {Rules.TRADE_GUILD_COST} gold"
        return None

    def administrator_disabled_reason(self, player):
        if not player.trade_guild_completed:
            return "needs completed trade guild"
        if player.administrator_hired:
            return "already hired"
        if player.gold < Rules.ADMINISTRATOR_COST:
            return f"needs {Rules.ADMINISTRATOR_COST} gold"
        return None

    def fire_ship_plans_disabled_reason(self, player):
        if player.fire_ships_unlocked:
            return "already unlocked"
        if player.gold < Rules.FIRE_SHIP_UPGRADE_COST:
            return f"needs {Rules.FIRE_SHIP_UPGRADE_COST} gold"
        return None

    def guard_captain_disabled_reason(self, player):
        if player.guard_captains >= Rules.GUARD_CAPTAIN_MAX:
            return "maximum hired"
        if player.gold < Rules.GUARD_CAPTAIN_COST:
            return f"needs {Rules.GUARD_CAPTAIN_COST} gold"
        return None

    def fishing_dock_disabled_reason(self, player):
        if player.fishing_dock_built and not player.fishing_dock_disabled:
            return "already active"
        if player.fishing_dock_started and not player.fishing_dock_built:
            return "already under construction"
        if player.gold < Rules.FISHING_DOCK_COST:
            return f"needs {Rules.FISHING_DOCK_COST} gold"
        return None

    def buy_fishing_boats_disabled_reason(self, player):
        if not player.fishing_dock_built:
            return "requires fishing docks"
        if player.fishing_dock_disabled:
            return "repair fishing docks first"
        if player.gold < Rules.FISHING_BOAT_COST:
            return f"needs {Rules.FISHING_BOAT_COST} gold"
        return None

    def dockhouse_disabled_reason(self, player):
        if player.dockhouse_completed:
            return "already completed"
        if player.dockhouse_started:
            return "already started"
        if player.gold < Rules.DOCKHOUSE_COST:
            return f"needs {Rules.DOCKHOUSE_COST} gold"
        return None

    def dockhand_disabled_reason(self, player):
        if not player.dockhouse_completed:
            return "needs completed dockhouse"
        if player.dockhands >= Rules.DOCKHAND_MAX:
            return "maximum hired"
        if player.gold < Rules.DOCKHAND_COST:
            return f"needs {Rules.DOCKHAND_COST} gold"
        return None

    def assign_dockhands_disabled_reason(self, player):
        if not player.dockhouse_completed:
            return "needs completed dockhouse"
        if not player.dockhands_full_roster:
            return f"needs {Rules.DOCKHAND_MAX} dock hands"
        return None

    def repair_damaged_ships_disabled_reason(self, player):
        if player.damaged_ships <= 0:
            return "no damaged ships"
        if player.raid_repair_cost > 0 and player.affordable_repairs() <= 0:
            return f"needs {player.raid_repair_cost} gold"
        return None

    def dry_dock_disabled_reason(self, player):
        if player.dry_dock_completed:
            return "already completed"
        if player.dry_dock_started:
            return "already started"
        if not player.shipyard_completed:
            return "needs completed shipyard"
        if player.gold < Rules.DRY_DOCK_COST:
            return f"needs {Rules.DRY_DOCK_COST} gold"
        return None

    def admiralty_disabled_reason(self, player):
        if player.admiralty_completed:
            return "already completed"
        if player.admiralty_started:
            return "already started"
        if player.gold < Rules.ADMIRALTY_COST:
            return f"needs {Rules.ADMIRALTY_COST} gold"
        return None

    def admiral_disabled_reason(self, player):
        if not player.admiralty_completed:
            return "needs completed admiralty"
        if player.admirals >= Rules.ADMIRAL_MAX:
            return "maximum recruited"
        if player.admirals >= player.admiral_slots:
            required_ships = (player.admirals + 1) * Rules.ADMIRAL_SHIPS_PER_SLOT
            return f"requires {required_ships} ships for next slot"
        if player.gold < Rules.ADMIRAL_COST:
            return f"needs {Rules.ADMIRAL_COST} gold"
        return None

    def admiralty_overtime_disabled_reason(self, player):
        if not player.admiralty_completed:
            return "needs completed admiralty"
        if player.admiralty_overtime_used:
            return "already used"
        targets = self.admiralty_overtime_targets(player)
        if not targets:
            return "no eligible project"
        if all(player.gold < target["cost"] for target in targets):
            cheapest = min(target["cost"] for target in targets)
            return f"needs {cheapest} gold"
        return None

    def treasure_launch_disabled_reason(self, player):
        if player.has_treasure_at_sea:
            return "convoy already at sea"

        latest_launch_turn = Rules.MAX_TURNS - Rules.TREASURE_TRAVEL_TURNS
        if self.turn > latest_launch_turn:
            return "too late"

        return None

    def payroll_launch_disabled_reason(self, player):
        if player.has_payroll_at_sea:
            return "convoy already at sea"

        if self.payroll_launched_this_year(player):
            return "already launched this year"

        if self.payroll_cycle_turn < Rules.PAYROLL_START_TURN:
            return "too early"

        if self.payroll_cycle_turn >= Rules.PAYROLL_FINAL_TURN:
            return "launches automatically this month"

        return None

    def buy_ships_action(self, player):
        affordable = player.gold // player.ship_cost
        menu_amount = self.prompt_amount_menu(
            player,
            f"Buy ships for {player.ship_cost} gold each.",
            affordable,
            "ships",
            self.player_economy_lines(player),
        )
        if menu_amount is not None:
            player.buy_ships(menu_amount)
            return

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
            f"{player.name} starts a shipyard. Port workers will add labor "
            f"on future turns."
        ))

    def start_fort_action(self, player):
        player.start_fort()
        print(UI.success(
            f"{player.name} starts a fort. Port workers will add labor "
            f"on future turns."
        ))

    def start_trade_guild_action(self, player):
        player.start_trade_guild()
        print(UI.success(
            f"{player.name} starts a trade guild. Port workers will add labor "
            f"on future turns."
        ))

    def hire_administrator_action(self, player):
        player.hire_administrator()
        print(UI.success(
            f"{player.name} hires an administrator. Emergency supply now costs "
            f"{player.supply_warchest_markup} gold per missing supply, and payroll "
            f"rises by {Rules.ADMINISTRATOR_PAYROLL_COST}."
        ))

    def start_dry_dock_action(self, player):
        player.start_dry_dock()
        print(UI.success(
            f"{player.name} starts a dry dock. Port workers will add labor "
            f"on future turns."
        ))

    def start_admiralty_action(self, player):
        player.start_admiralty()
        print(UI.success(
            f"{player.name} starts an admiralty. Port workers will add labor "
            f"on future turns."
        ))

    def recruit_admiral_action(self, player):
        player.recruit_admiral()
        print(UI.success(
            f"{player.name} recruits an admiral "
            f"({player.admirals}/{Rules.ADMIRAL_MAX})."
        ))

    def admiralty_overtime_action(self, player):
        targets = [
            target
            for target in self.admiralty_overtime_targets(player)
            if player.gold >= target["cost"]
        ]
        if not targets:
            print(UI.warning("No affordable overtime project is available."))
            return

        target = self.prompt_admiralty_overtime_target(player, targets)
        if target is None:
            return
        self.apply_admiralty_overtime(player, target["key"])

    def admiralty_overtime_targets(self, player):
        targets = []

        def add(key, label, base_cost, eligible):
            if eligible:
                targets.append(
                    {
                        "key": key,
                        "label": label,
                        "base_cost": base_cost,
                        "cost": base_cost * 2,
                    }
                )

        add(
            "shipyard",
            "Shipyard",
            Rules.SHIPYARD_COST,
            not player.shipyard_completed,
        )
        add("fort", "Fort", Rules.FORT_COST, not player.fort_completed)
        add(
            "trade_guild",
            "Trade guild",
            Rules.TRADE_GUILD_COST,
            not player.trade_guild_completed,
        )
        add(
            "fishing_dock",
            "Fishing docks",
            Rules.FISHING_DOCK_COST,
            not player.fishing_dock_built or player.fishing_dock_disabled,
        )
        add(
            "dockhouse",
            "Dockhouse",
            Rules.DOCKHOUSE_COST,
            not player.dockhouse_completed,
        )
        add(
            "dry_dock",
            "Dry dock",
            Rules.DRY_DOCK_COST,
            player.shipyard_completed and not player.dry_dock_completed,
        )
        add(
            "fire_plans",
            "Fire ship plans",
            Rules.FIRE_SHIP_UPGRADE_COST,
            not player.fire_ships_unlocked,
        )
        return targets

    def prompt_admiralty_overtime_target(self, player, targets):
        if sys.stdin.isatty():
            return self.with_cbreak(
                lambda: self.prompt_admiralty_overtime_target_menu(player, targets)
            )

        print(f"{player.name}, choose an overtime project:")
        for index, target in enumerate(targets, start=1):
            print(f"{index}. {target['label']} ({target['cost']} gold)")
        while True:
            choice = self.prompt_non_negative_int("Overtime project (0 cancels): ")
            if choice == 0:
                print("Overtime cancelled.")
                return None
            if 1 <= choice <= len(targets):
                return targets[choice - 1]
            print(UI.warning("Choose one of the listed projects."))

    def prompt_admiralty_overtime_target_menu(self, player, targets):
        selected = 0
        message = "Choose a project for one-time Admiralty overtime."
        while True:
            control_lines = [
                f"{player.name}, choose an overtime project.",
                "Pay double base gold cost; labor is completed instantly.",
                "Up/down select, digits jump, Enter chooses.",
                "",
            ]
            for index, target in enumerate(targets):
                prefix = ">" if index == selected else " "
                line = (
                    f"{prefix} {index + 1}. {target['label']} "
                    f"- {target['cost']} gold"
                )
                control_lines.append(UI.success(line) if index == selected else line)
            control_lines.append("  0. Cancel")
            if message:
                control_lines.extend(["", message])

            self.render_play_area(
                phase=f"{player.name}'s Admiralty Overtime",
                control_lines=control_lines,
                info_lines=self.player_economy_lines(player),
                info_title="Harbor Details",
                clear=True,
                include_state=True,
            )
            key = self.read_menu_key()
            if key == "up":
                selected = (selected - 1) % len(targets)
            elif key == "down":
                selected = (selected + 1) % len(targets)
            elif key == "enter":
                return targets[selected]
            elif key == "0":
                return None
            elif key.isdigit():
                choice = int(key)
                if 1 <= choice <= len(targets):
                    selected = choice - 1
                    return targets[selected]
                message = UI.warning("No such project.")
            else:
                message = "Use arrows, digits, or Enter."

    def apply_best_admiralty_overtime(self, player):
        affordable_targets = [
            target
            for target in self.admiralty_overtime_targets(player)
            if player.gold >= target["cost"]
        ]
        if not affordable_targets:
            return False
        order = {
            "shipyard": 0,
            "dry_dock": 1,
            "fort": 2,
            "trade_guild": 3,
            "fishing_dock": 4,
            "dockhouse": 5,
            "fire_plans": 6,
        }
        target = min(affordable_targets, key=lambda item: order.get(item["key"], 99))
        self.apply_admiralty_overtime(player, target["key"], announce=False)
        return True

    def apply_admiralty_overtime(self, player, target_key, announce=True):
        target = next(
            (
                target
                for target in self.admiralty_overtime_targets(player)
                if target["key"] == target_key
            ),
            None,
        )
        if target is None or player.admiralty_overtime_used or player.gold < target["cost"]:
            return False

        player.gold -= target["cost"]
        player.admiralty_overtime_used = True
        if target_key == "shipyard":
            player.shipyard_started = True
            player.shipyard_completed = True
            player.shipyard_labor = Rules.SHIPYARD_LABOR_REQUIRED
            player.shipyard_destroyed = False
        elif target_key == "fort":
            player.fort_started = True
            player.fort_completed = True
            player.fort_labor = Rules.FORT_LABOR_REQUIRED
        elif target_key == "trade_guild":
            player.trade_guild_started = True
            player.trade_guild_completed = True
            player.trade_guild_labor = Rules.TRADE_GUILD_LABOR_REQUIRED
        elif target_key == "fishing_dock":
            player.fishing_dock_started = False
            player.fishing_dock_labor = Rules.FISHING_DOCK_LABOR_REQUIRED
            player.fishing_dock_built = True
            player.fishing_dock_disabled = False
        elif target_key == "dockhouse":
            player.dockhouse_started = True
            player.dockhouse_completed = True
            player.dockhouse_labor = Rules.DOCKHOUSE_LABOR_REQUIRED
            player.dockhouse_burned = False
        elif target_key == "dry_dock":
            player.dry_dock_started = True
            player.dry_dock_completed = True
            player.dry_dock_labor = Rules.DRY_DOCK_LABOR_REQUIRED
        elif target_key == "fire_plans":
            player.fire_ships_unlocked = True

        if announce:
            print(UI.success(
                f"{player.name}'s Admiralty overtime completes "
                f"{target['label']} for {target['cost']} gold."
            ))
        return True

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
                f"{player.name} starts fishing docks. Port workers will add labor "
                "on future turns."
            ))

    def start_dockhouse_action(self, player):
        player.start_dockhouse()
        print(UI.success(
            f"{player.name} starts a dockhouse. Port workers will add labor "
            "on future turns."
        ))

    def hire_dockhand_action(self, player):
        player.hire_dockhand()
        print(UI.success(
            f"{player.name} hires a dock hand "
            f"({player.dockhands}/{Rules.DOCKHAND_MAX})."
        ))

    def assign_dockhands_action(self, player):
        duties = [
            ("construction", "Construction", "all dock hands add port labor"),
            ("repair", "Repair crew", "next repairs are 1 gold cheaper, up to 5 ships"),
            (
                "boatwright",
                "Boatwright",
                "build fishing boats for 1 gold each; requires active docks",
            ),
        ]
        if sys.stdin.isatty():
            duty = self.with_cbreak(lambda: self.prompt_dockhand_duty_menu(player, duties))
        else:
            print(f"{player.name}, choose dock hand duty:")
            for index, (_key, label, help_text) in enumerate(duties, start=1):
                disabled_reason = self.dockhand_duty_disabled_reason(player, _key)
                suffix = f" - {disabled_reason}" if disabled_reason else f" - {help_text}"
                line = f"{index}. {label}{suffix}"
                print(UI.muted(line) if disabled_reason else line)
            duty = None
            while duty is None:
                choice = self.prompt_non_negative_int("Dock hand duty (0 cancels): ")
                if choice == 0:
                    return
                if 1 <= choice <= len(duties):
                    selected_duty = duties[choice - 1][0]
                    disabled_reason = self.dockhand_duty_disabled_reason(
                        player,
                        selected_duty,
                    )
                    if disabled_reason:
                        print(UI.warning(f"Duty unavailable: {disabled_reason}."))
                        continue
                    duty = selected_duty
                else:
                    print(UI.warning("Choose one of the listed duties."))
        if duty is None:
            return
        player.set_dockhand_duty(duty)
        player.refresh_dockhand_repair_discount()
        print(UI.success(f"{player.name}'s dock hands switch to {duty}."))

    def prompt_dockhand_duty_menu(self, player, duties):
        selected = 0
        message = "Choose the full-roster dock hand duty."
        while True:
            control_lines = [
                f"{player.name}, assign dock hands.",
                "Special duties use all 5 dock hands for the turn.",
                "Up/down select, digits jump, Enter chooses.",
                "",
            ]
            for index, (key, label, help_text) in enumerate(duties):
                prefix = ">" if index == selected else " "
                current = " current" if key == player.dockhand_duty else ""
                disabled_reason = self.dockhand_duty_disabled_reason(player, key)
                suffix = f" - {disabled_reason}" if disabled_reason else f" - {help_text}"
                line = f"{prefix} {index + 1}. {label}{current}{suffix}"
                if disabled_reason:
                    control_lines.append(UI.muted(line))
                else:
                    control_lines.append(UI.success(line) if index == selected else line)
            control_lines.append("  0. Cancel")
            if message:
                control_lines.extend(["", message])
            self.render_play_area(
                phase=f"{player.name}'s Dock Hands",
                control_lines=control_lines,
                info_lines=self.player_economy_lines(player),
                info_title="Harbor Details",
                clear=True,
                include_state=True,
            )
            key = self.read_menu_key()
            if key == "up":
                selected = (selected - 1) % len(duties)
            elif key == "down":
                selected = (selected + 1) % len(duties)
            elif key == "enter":
                selected_duty = duties[selected][0]
                disabled_reason = self.dockhand_duty_disabled_reason(
                    player,
                    selected_duty,
                )
                if disabled_reason:
                    message = UI.warning(f"Duty unavailable: {disabled_reason}.")
                    continue
                return selected_duty
            elif key == "0":
                return None
            elif key.isdigit():
                choice = int(key)
                if 1 <= choice <= len(duties):
                    selected = choice - 1
                    selected_duty = duties[selected][0]
                    disabled_reason = self.dockhand_duty_disabled_reason(
                        player,
                        selected_duty,
                    )
                    if disabled_reason:
                        message = UI.warning(f"Duty unavailable: {disabled_reason}.")
                        continue
                    return selected_duty
                message = UI.warning("No such duty.")
            else:
                message = "Use arrows, digits, or Enter."

    def dockhand_duty_disabled_reason(self, player, duty):
        if duty == "construction":
            return None
        if duty == "repair":
            if player.damaged_ships <= 0:
                return "no damaged ships"
            if player.base_raid_repair_cost <= 0:
                return "repairs already free"
            return None
        if duty == "boatwright":
            if not player.fishing_dock_built or player.fishing_dock_disabled:
                return "needs active fishing docks"
            if player.gold < Rules.DOCKHAND_BOATWRIGHT_COST:
                return f"needs {Rules.DOCKHAND_BOATWRIGHT_COST} gold"
            return None
        return "unknown duty"

    def buy_fishing_boats_action(self, player):
        affordable = self.affordable_fishing_boats(player)
        menu_amount = self.prompt_amount_menu(
            player,
            f"Buy fishing boats for {Rules.FISHING_BOAT_COST} gold each.",
            affordable,
            "boats",
            self.player_economy_lines(player),
        )
        if menu_amount is not None:
            self.buy_fishing_boats(player, menu_amount)
            return

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
        affordable = player.affordable_repairs()
        menu_amount = self.prompt_amount_menu(
            player,
            f"Repair damaged ships from {cost} gold each.",
            affordable,
            "ships",
            self.player_economy_lines(player),
        )
        if menu_amount is not None:
            player.repair_damaged_ships(menu_amount)
            return

        while True:
            amount = self.prompt_non_negative_int(
                f"{player.name}, repair damaged ships from {cost} gold each "
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
        if (
            player.has_payroll_at_sea
            or self.payroll_launched_this_year(player)
            or self.payroll_cycle_turn < Rules.PAYROLL_FINAL_TURN
        ):
            return

        cost = player.launch_payroll(self.payroll_year)
        print(UI.warning(
            f"{player.name}'s payroll convoy launches automatically "
            f"with {player.payroll_value} gold after paying {cost} gold."
        ))

    def launch_payroll_action(self, player):
        cost = player.launch_payroll(self.payroll_year)
        print(UI.success(
            f"{player.name} launches payroll convoy with "
            f"{player.payroll_value} gold after paying {cost} gold."
        ))

    def prompt_yes_no(self, prompt):
        raw_value = input(prompt).strip().lower()
        return raw_value in {"y", "yes"}

    def show_final_scores(self):
        UI.clear_screen()
        UI.section("FINAL SCORES", "yellow")
        score_panels = []
        for player in self.players:
            score_panels.append(
                (
                    player.name,
                    [
                        f"Gold: {UI.amount(player.gold, color=player.gold_color)}",
                        f"Ships: {UI.amount(player.ships)} ({UI.amount(player.ship_value, 'value', 'yellow')})",
                        f"Shipyard: {UI.amount(player.shipyard_value, 'value', 'yellow')}",
                        f"Fort: {UI.amount(player.fort_value, 'value', 'yellow')}",
                        f"Trade guild: {UI.amount(player.trade_guild_value, 'value', 'yellow')}",
                        (
                            "Fishing: "
                            f"{UI.amount(player.fishing_dock_value + player.fishing_boat_value, 'value', 'yellow')}"
                        ),
                        f"Dry dock: {UI.amount(player.dry_dock_value, 'value', 'yellow')}",
                        f"Admiralty: {UI.amount(player.admiralty_value, 'value', 'yellow')}",
                        f"Admirals: {UI.amount(player.admirals)}",
                        f"Guard captains: {UI.amount(player.guard_captains)}",
                        (
                            "Total assets: "
                            f"{UI.amount(player.asset_score, color='yellow')}"
                        ),
                    ],
                )
            )
        self.print_player_panels(score_panels)

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
