import io
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

    def play(self):
        UI.section(f"SEALED ORDERS v{Rules.VERSION}", "magenta")
        UI.bullet("Assign ships to Trade, Raid, Guard, and Fire.", "cyan")
        UI.bullet(f"Highest total assets after {Rules.MAX_TURNS} turns wins.", "yellow")
        UI.bullet("Treasure and payroll convoys create delayed, raidable payouts.")
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
        self.show_bulletin("Port Labor", self.apply_port_labor)
        self.show_bulletin("Convoy Arrivals", self.advance_convoys)
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
            [(player.name, player.status_lines()) for player in self.players]
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
            ]
        ):
            return self.accent_bulletin_nations(UI.accent_amounts(line, "red"))
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
                UI.amount(allocation.fire)
                if player.fire_ships_unlocked or allocation.fire
                else UI.muted("locked")
            )
            lines.extend(
                [
                    "",
                    UI.paint(player.name, "magenta", bold=True),
                    f"  Trade {UI.amount(allocation.trade)}   Raid {UI.amount(allocation.raid)}",
                    f"  Guard {UI.amount(allocation.guard)}   Fire {fire_value}",
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
            self.add_status_change(
                lines, "Raid fatigue", before, after, "raid_fatigue_status"
            )
            self.add_status_change(lines, "Dry dock", before, after, "dry_dock_status")
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
        lines = []
        if self.buy_baseline(player) is not None:
            lines.append(self.purchase_summary_line(player))
        lines.extend(
            [
                f"  {UI.field('Assets')} {UI.amount(player.asset_score, color='yellow')}{UI.delta(self.buy_delta(player, 'asset_score'))} "
                f"(shipyard value: {player.shipyard_value}, "
                f"fort value: {player.fort_value}, "
                f"trade guild value: {player.trade_guild_value})",
                f"  {UI.field('Economy')} Trade income: {UI.amount(Rules.TRADE_INCOME, 'gold')}, "
                f"smuggle income: {UI.amount(Rules.SMUGGLE_INCOME, 'gold')}, "
                f"fishing boat income: {UI.amount(Rules.FISHING_BOAT_INCOME, 'gold')}",
                f"  {UI.field('Ships')} {UI.amount(player.ships)}{UI.delta(self.buy_delta(player, 'ships'))}; cost: {UI.amount(player.ship_cost, 'gold')}, "
                f"ship value: {UI.amount(Rules.SHIP_COST, 'gold')}",
                f"  {UI.field('Fishing')} Docks: {UI.amount(Rules.FISHING_DOCK_COST, 'gold')}, "
                f"{UI.amount(Rules.FISHING_DOCK_LABOR_REQUIRED, 'labor')}; "
                f"boats: {UI.amount(Rules.FISHING_BOAT_COST, 'gold')} each",
            ]
        )
        if not player.payroll_launched:
            lines.append(
                f"  {UI.field('Payroll cost')} {UI.amount(player.payroll_cost, 'gold')}"
            )
        lines.extend(
            [
                f"  {UI.field('Treasure')} {player.treasure_value} gold{player.treasure_status}",
                f"  {UI.field('Raid fatigue')} {player.raid_fatigue_status}",
                f"  {UI.field('Port defences')} {player.port_defense_status}",
                f"  {UI.field('Dry dock')} {player.dry_dock_status}",
                f"  {UI.field('Captains')} {player.guard_captain_status}",
            ]
        )
        lines.extend(self.harbor_upgrade_art_lines(player))
        return lines

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
        guild = style(
            "Guild [$]",
            player.trade_guild_completed,
            player.trade_guild_started,
            False,
            "green",
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
        fire = style("Fire >>>", player.fire_ships_unlocked, False, False, "red")
        captain_marks = " ".join(
            UI.paint("/|\\", "magenta", bold=True)
            if index < player.guard_captains
            else UI.muted("/|\\")
            for index in range(Rules.GUARD_CAPTAIN_MAX)
        )

        return [
            "",
            UI.field("Harbor works"),
            f"  {yard}    {fort}    {guild}",
            f"  {fishing}    {dry_dock}    {fire}",
            f"  Capt {captain_marks}",
            f"  {self.convoy_art_line(player)}",
        ]

    def convoy_art_line(self, player):
        treasure = f"T{UI.amount(player.treasure_value)}"
        if player.has_treasure_at_sea:
            treasure = UI.paint(f"Treasure -> {player.treasure_turns_remaining}", "yellow", bold=True)
        else:
            treasure = UI.paint(f"Treasure {treasure}", "green", bold=True)

        if player.has_payroll_at_sea:
            payroll = UI.paint(f"Payroll -> {player.payroll_turns_remaining}", "yellow", bold=True)
        elif player.payroll_launched:
            payroll = UI.paint("Payroll done", "green", bold=True)
        elif self.turn < Rules.PAYROLL_START_TURN:
            payroll = UI.muted("Payroll locked")
        elif self.turn > Rules.PAYROLL_FINAL_TURN:
            payroll = UI.paint("Payroll overdue", "red", bold=True)
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
                "dry dock",
                player.dry_dock_started and not player.dry_dock_completed,
                player.dry_dock_labor,
                Rules.DRY_DOCK_LABOR_REQUIRED,
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
                    "Trade: earn gold.",
                    "Raid: steal trade, pressure ports.",
                    "Guard: protect lanes and catch smugglers.",
                    "Fire: burn guards and infrastructure when unlocked.",
                "Unassigned ships become port workers for construction projects.",
                ],
                info_lines=self.player_economy_lines(player),
                info_title="Harbor Details",
                clear=True,
                include_state=True,
            )
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
                value = UI.amount(values[field])
                control_lines.append(f"{marker} {field:<6} {value}")
            if not player.fire_ships_unlocked:
                control_lines.append(UI.muted("  Fire   locked"))
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
        input("\nPress Enter to continue to port labor, convoy arrivals, and buy phase...")
        print()

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
                f"\n{raider.name}'s {raid_strength} raid ship(s) find no "
                f"{guarder.name} guard screen."
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

        required_raids = defender.port_attack_threshold

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
        remaining_trade -= raid_intercepts
        stolen_trade_income = raid_intercepts * Rules.TRADE_INCOME
        stolen_income += stolen_trade_income

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
        smuggle_income = paid_smuggled_trade * Rules.SMUGGLE_INCOME
        confiscated_income = confiscated_trade * Rules.SMUGGLE_INCOME

        normal_income = remaining_trade * Rules.TRADE_INCOME
        trade_bonus = self.calculate_trade_guild_bonus(trader, remaining_trade)
        fishing_income = trader.fishing_income
        trade_income = smuggle_income + normal_income + trade_bonus
        treasure_growth = int(trade_income * Rules.TREASURE_TRADE_PERCENT)

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
            captured_smuggling_ships=captured_smuggling_ships,
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
                not dry_dock_labor
                and player.dry_dock_started
                and not player.dry_dock_completed
            ):
                print(f"{player.name} has no port workers to work on the dry dock.")

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
        self.buy_phase_baselines = {}
        for player in self.players:
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

    def start_dry_dock_action(self, player):
        player.start_dry_dock()
        print(UI.success(
            f"{player.name} starts a dry dock. Port workers will add labor "
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
                f"{player.name} starts fishing docks. Port workers will add labor "
                "on future turns."
            ))

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
        if cost == 0:
            affordable = player.damaged_ships
        else:
            affordable = min(player.damaged_ships, player.gold // cost)
        menu_amount = self.prompt_amount_menu(
            player,
            f"Repair damaged ships for {cost} gold each.",
            affordable,
            "ships",
            self.player_economy_lines(player),
        )
        if menu_amount is not None:
            player.repair_damaged_ships(menu_amount)
            return

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
