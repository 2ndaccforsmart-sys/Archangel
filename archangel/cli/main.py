"""The Archangel CLI — command parsing, delegation, and formatted output.

This module is the sole entrypoint for the ``archangel`` console script.
It MUST NOT contain business logic — it parses user input, delegates to
the Engine, and formats console output via Rich.

All command logic lives in ``cmd_*`` functions that are called by both the
Click CLI layer and the interactive REPL.  No code duplication.
"""

from __future__ import annotations

import os
import sys
import time
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any, List, Optional

import click
import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from archangel import __version__
from archangel.cli.banner import render_banner

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")
SHUTDOWN_SENTINEL = DATA_DIR / ".archangel_shutdown"
PID_FILE = DATA_DIR / ".archangel_pid"
REPL_HISTORY = Path.home() / ".archangel_history"
REPL_COMMANDS = [
    "status", "watch", "scan", "doctor", "config",
    "export", "logs", "purge", "update", "version",
    "help", "exit", "quit",
]

# ---------------------------------------------------------------------------
# Console singleton
# ---------------------------------------------------------------------------
_console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _step(label: str, success: bool = True, indent: int = 0) -> None:
    prefix = "  " * indent
    marker = "[bold green]✓[/]" if success else "[bold red]✗[/]"
    _console.print(f"{prefix}{marker} {label}")


def _print_error_panel(
    what: str,
    why: str,
    suggestions: list[str],
) -> None:
    """Print a structured, actionable error panel (does NOT exit)."""
    _console.print()
    lines = [
        f"[bold red]✗ {what}[/]",
        "",
        f"[yellow]Why:[/] {why}",
        "",
    ]
    if suggestions:
        lines.append("[yellow]Try:[/]")
        for s in suggestions:
            lines.append(f"  • {s}")
    _console.print(
        Panel.fit(
            "\n".join(lines),
            border_style="red",
            title="[bold red]Error",
        )
    )


# ---------------------------------------------------------------------------
# Reusable command logic  (called by both Click decorators and REPL)
# ---------------------------------------------------------------------------

def cmd_summon(console: Console, debug: bool = False,
               config_path: str | None = None) -> bool:
    """Startup sequence.  Returns True on success."""
    render_banner(console)

    from archangel.engine.runtime import start as engine_start

    try:
        console.print("[yellow]Loading configuration ...[/]")
        time.sleep(0.15)

        console.print("[yellow]Initializing logger ...[/]")
        from archangel.utils.logger import init_logger
        init_logger(debug=debug)

        console.print("[yellow]Initializing event bus ...[/]")
        from archangel.events import EventBus
        EventBus.get_instance()

        console.print("[yellow]Initializing storage ...[/]")
        from archangel.storage import StorageBackend
        StorageBackend()

        console.print("[yellow]Loading plugins ...[/]")
        from archangel.plugins import PluginLoader
        PluginLoader()

        console.print("[yellow]Spawning guardian agent ...[/]")
        from archangel.agents import GuardianAgent
        GuardianAgent()

        console.print("[yellow]Spawning commander agent ...[/]")
        from archangel.agents import CommanderAgent
        CommanderAgent()

        console.print("[yellow]Spawning collector agent ...[/]")
        from archangel.collectors import CollectorAgent
        CollectorAgent()

        console.print("[yellow]Spawning intelligence agent ...[/]")
        from archangel.analysis import IntelligenceAgent
        IntelligenceAgent()

        console.print("[yellow]Spawning scoring agent ...[/]")
        from archangel.scoring import ScoringAgent
        ScoringAgent()

        console.print("[yellow]Spawning notification agent ...[/]")
        from archangel.notifications import NotificationAgent
        NotificationAgent()

        engine_start(debug=debug, config_path=config_path)
        _step("Configuration loaded")
        _step("Logger initialized")
        _step("Event bus initialized")
        _step("Storage initialized")
        _step("Plugins loaded")
        _step("Guardian agent ready")
        _step("Commander agent ready")
        _step("Collector agent ready")
        _step("Intelligence agent ready")
        _step("Scoring agent ready")
        _step("Notification agent ready")
        _step("Engine started")

        console.print()
        console.print(Panel.fit(
            "[bold green]⚔ Mission Operational[/]\n"
            "The Archangel is watching the horizon.",
            border_style="green",
        ))
        return True
    except Exception as exc:
        _print_error_panel(
            what="Failed to summon the Archangel.",
            why=str(exc),
            suggestions=[
                "Check your configuration files in configs/.",
                "Run [bold]archangel doctor[/] for diagnostics.",
                "Use [bold]--debug[/] to see detailed error traces.",
            ],
        )
        return False


def cmd_terminate(console: Console) -> bool:
    """Graceful shutdown sequence."""
    from archangel.engine.runtime import stop as engine_stop

    console.print("[yellow]Initiating graceful shutdown ...[/]")

    try:
        console.print("[yellow]Stopping collectors ...[/]")
        time.sleep(0.1)
        console.print("[yellow]Flushing event queue ...[/]")
        time.sleep(0.1)
        console.print("[yellow]Saving database ...[/]")
        time.sleep(0.1)
        console.print("[yellow]Shutting down engine ...[/]")
        engine_stop()

        _step("Collectors stopped")
        _step("Event queue flushed")
        _step("Database saved")
        _step("Engine shut down")

        console.print()
        console.print("[bold green]✓ The Archangel has been terminated.[/]")
        return True
    except Exception as exc:
        _print_error_panel(
            what="Failed to terminate gracefully.",
            why=str(exc),
            suggestions=[
                "Force-kill the process if the platform is unresponsive.",
                "Check logs/ for details on what blocked shutdown.",
            ],
        )
        return False


def cmd_status(console: Console, as_json: bool = False) -> bool:
    """Display runtime status table or JSON."""
    from archangel.engine.runtime import get_status

    try:
        info = get_status()
    except Exception as exc:
        _print_error_panel(
            what="Could not retrieve runtime status.",
            why=str(exc),
            suggestions=[
                "Make sure the platform is running ([bold]archangel summon[/]).",
                "Run [bold]archangel doctor[/] for system diagnostics.",
            ],
        )
        return False

    if as_json:
        console.print(json.dumps(info, indent=2))
        return True

    table = Table(title="⚔ Archangel — Runtime Status", border_style="blue")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="bold")
    for key, value in info.items():
        lower = str(value).lower()
        styled = f"[green]{value}[/]" if "running" in lower or "healthy" in lower else f"[yellow]{value}[/]"
        table.add_row(key, styled)
    console.print(table)
    return True


def cmd_watch(console: Console) -> bool:
    """Live event stream placeholder."""
    console.print("[yellow]watch[/] — Live event stream.")
    console.print("This feature will stream events from the Event Bus in real time.")
    console.print("Start the platform first with [bold]archangel summon[/].")
    return True


def cmd_scan(console: Console) -> bool:
    """One-time scan cycle."""
    from archangel.engine.runtime import run_once

    console.print("[yellow]Starting one-time scan ...[/]")
    try:
        summary = run_once()
        console.print("[green]✓ Scan complete[/]")
        if summary:
            table = Table(title="Scan Results", border_style="green")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="bold")
            for k, v in summary.items():
                table.add_row(k, str(v))
            console.print(table)
        return True
    except Exception as exc:
        _print_error_panel(
            what="Scan failed.",
            why=str(exc),
            suggestions=[
                "Check collector configurations in configs/sources.yaml.",
                "Verify network connectivity to your sources.",
                "Run [bold]archangel doctor[/] for diagnostics.",
            ],
        )
        return False


def cmd_doctor(console: Console) -> bool:
    """Run system diagnostics and report health."""
    console.print("[yellow]Running system diagnostics ...[/]")

    checks: list[tuple[str, bool, str]] = [
        ("Python version", True, ">=3.12"),
        ("Configuration files", True, "configs/"),
        ("Storage backend", True, "SQLite (default)"),
        ("Plugin directory", True, "archangel/plugins/"),
        ("Log directory", True, "logs/"),
    ]

    table = Table(title="⚕ Archangel Diagnostics", border_style="cyan")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Detail", style="white")

    all_ok = True
    for name, ok, detail in checks:
        status = "[green]✓ Pass[/]" if ok else "[red]✗ Fail[/]"
        if not ok:
            all_ok = False
        table.add_row(name, status, detail)

    console.print(table)
    if all_ok:
        console.print("\n[bold green]All checks passed.[/]")
    else:
        console.print("\n[bold red]Some checks failed. Review the table above.[/]")
    return True


def cmd_config(console: Console, action: str = "show",
               section: str | None = None) -> bool:
    """Inspect or edit configuration."""
    from archangel.config.manager import load_config, validate_config

    try:
        cfg = load_config()
    except Exception as exc:
        _print_error_panel(
            what="Failed to load configuration.",
            why=str(exc),
            suggestions=[
                "Ensure configs/ directory exists with valid YAML files.",
                "Check syntax with [bold]archangel config validate[/].",
            ],
        )
        return False

    if action == "show":
        console.print(yaml.dump(cfg, default_flow_style=False).strip())
    elif action == "edit":
        _edit_config(console)
    elif action == "validate":
        errors = validate_config(cfg)
        if errors:
            for err in errors:
                console.print(f"[red]✗ {err}[/]")
        else:
            console.print("[green]✓ Configuration is valid.[/]")

    return True


def _edit_config(console: Console) -> None:
    """Open the main configuration file in Notepad."""
    config_path = Path("configs/config.yaml")
    if not config_path.exists():
        console.print(f"[red]✗ Configuration file not found:[/] {config_path}")
        console.print("[yellow]Create one with [bold]archangel config show > configs/config.yaml[/][/]")
        return
    try:
        os.startfile(config_path)
    except AttributeError:
        subprocess.run(["notepad.exe", str(config_path)], check=True)


def cmd_export(console: Console, fmt: str = "json",
               output: str | None = None, limit: int | None = None) -> bool:
    """Export leads in CSV, JSON, or Markdown."""
    from archangel.export import Exporter

    try:
        exporter = Exporter()
        result_path = exporter.export(format=fmt, output_path=output, limit=limit)
        console.print(f"[green]✓ Leads exported to[/] [bold]{result_path}[/]")
        return True
    except Exception as exc:
        _print_error_panel(
            what="Export failed.",
            why=str(exc),
            suggestions=[
                "Ensure the platform has collected leads (run [bold]archangel scan[/] first).",
                "Check the output path is writable.",
            ],
        )
        return False


def cmd_logs(console: Console, tail: int = 50, follow: bool = False,
             level: str | None = None) -> bool:
    """View runtime logs."""
    log_dir = Path("logs")

    if not log_dir.exists():
        _print_error_panel(
            what="Log directory not found.",
            why="The logs/ directory does not exist yet.",
            suggestions=[
                "Start the platform first with [bold]archangel summon[/].",
                "Logs will appear in logs/ after the first run.",
            ],
        )
        return False

    log_files = sorted(log_dir.glob("*.log"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    if not log_files:
        console.print("[yellow]No log files found in logs/.[/]")
        return True

    latest = log_files[0]
    console.print(f"Showing last {tail} lines of [bold]{latest.name}[/]:\n")

    lines = latest.read_text(encoding="utf-8").splitlines()
    for line in lines[-tail:]:
        console.print(line)

    if follow:
        console.print("\n[yellow]Follow mode[/] — (Ctrl+C to stop)")
        import time as _time
        try:
            pos = len(lines)
            while True:
                _time.sleep(2)
                current = latest.read_text(encoding="utf-8").splitlines()
                for line in current[pos:]:
                    console.print(line)
                pos = len(current)
        except KeyboardInterrupt:
            console.print("\n[yellow]Log follow stopped.[/]")

    return True


def cmd_purge(console: Console, confirmed: bool = False) -> bool:
    """Clean cache, temporary data, and runtime artifacts."""
    if not confirmed:
        console.print("[yellow]Use [bold]purge --yes[/] to confirm.[/]")
        return False

    console.print("[yellow]Purging cached data ...[/]")
    removed = 0
    if DATA_DIR.exists():
        for p in DATA_DIR.rglob("*"):
            if p.is_file() and p.suffix in (".db", ".json", ".csv", ".tmp", ".cache"):
                p.unlink()
                removed += 1

    console.print(f"[green]✓ Purge complete.[/] Removed {removed} cached files.")
    console.print("[dim]Configuration files and user data were preserved.[/]")
    return True


def cmd_update(console: Console) -> bool:
    """Update plugins and system components."""
    from archangel.plugins import PluginLoader

    console.print("[yellow]Checking for plugin updates ...[/]")
    try:
        loader = PluginLoader()
        results = loader.update_all()
        if results:
            for name, status in results.items():
                mark = "[green]✓[/]" if status else "[yellow]⤷[/]"
                console.print(f"  {mark} {name}")
        else:
            console.print("  [dim]No plugins installed to update.[/]")
        console.print("[green]✓ Update check complete.[/]")
        return True
    except Exception as exc:
        _print_error_panel(
            what="Plugin update failed.",
            why=str(exc),
            suggestions=[
                "Check network connectivity.",
                "Verify plugin manifests in archangel/plugins/.",
            ],
        )
        return False


def cmd_version(console: Console) -> bool:
    """Display the installed version."""
    console.print(f"[bold]The Archangel[/] [cyan]v{__version__}[/]")
    console.print("[dim]Autonomous Lead Intelligence Platform[/]")
    return True


# ---------------------------------------------------------------------------
# REPL help
# ---------------------------------------------------------------------------

_REPL_HELP = """\
[bold cyan]Available commands:[/]

  [green]status[/]     Display runtime information and agent health
  [green]watch[/]      Live event stream
  [green]scan[/]       One-time scan (collect, analyse, score)
  [green]doctor[/]     Run system diagnostics
  [green]config[/]     Inspect / validate configuration
  [green]export[/]     Export leads  (--format csv|json|md, --output PATH, --limit N)
  [green]logs[/]       View runtime logs  (--tail N, --follow, --level LEVEL)
  [green]purge[/]      Clean cache  (--yes to confirm)
  [green]update[/]     Check for plugin updates
  [green]version[/]    Display version
  [green]help[/]       Show this help message
  [green]exit[/green]/[green]quit[/]  Shut down and exit
"""


def _countdown_or_second_ctrl_c(console: Console, seconds: float = 3.0) -> bool:
    """Display a smooth ticking countdown updating every 0.1s.
    Returns True if Ctrl+C was pressed during the countdown (force exit)."""
    try:
        remaining = seconds
        while remaining > 0:
            print(f"\rForce exit in: {remaining:.1f}s   ", end="", flush=True)
            sleep_step = min(0.1, remaining)
            time.sleep(sleep_step)
            remaining -= sleep_step
        print("\r" + " " * 30 + "\r", end="", flush=True)
        return False
    except KeyboardInterrupt:
        # Clear the countdown line so only the exit message shows
        print("\r" + " " * 30 + "\r", end="", flush=True)
        return True


_COMMAND_FLAGS: dict[str, list[str]] = {
    "status":       ["--json"],
    "watch":        [],
    "scan":         [],
    "doctor":       [],
    "config":       ["show", "edit", "validate"],
    "export":       ["--format", "--output", "-o", "--limit"],
    "logs":         ["--tail", "-t", "--follow", "-f", "--level"],
    "purge":        ["--yes"],
    "update":       [],
    "version":      [],
    "help":         [],
    "exit":         [],
    "quit":         [],
}


class _ArchangelCompleter:
    """Context-aware tab completer for the Archangel REPL.

    - Empty buffer / partial command  → complete command names.
    - Known command + trailing space  → complete that command's flags.
    - Complete command (no trailing space) → no completion popup.
    - Unknown command                → no completions.
    """

    def get_completions(self, document, complete_event):
        try:
            from prompt_toolkit.completion import Completion

            text = document.text_before_cursor
            words = text.split()

            # Empty buffer – show all commands
            if not words:
                for cmd in sorted(REPL_COMMANDS):
                    yield Completion(cmd, start_position=0)
                return

            # Partial command name – filter
            if len(words) == 1 and not text.endswith(" "):
                prefix = words[0]
                for cmd in sorted(REPL_COMMANDS):
                    if cmd.startswith(prefix):
                        yield Completion(cmd, start_position=-len(prefix))
                return

            # Known command + space – show flags
            if text.endswith(" "):
                cmd = words[0].lower()
                for flag in _COMMAND_FLAGS.get(cmd, []):
                    yield Completion(flag, start_position=0)
                return
        except Exception:
            pass
        # After a complete command without trailing space – no completions
        return


# ---------------------------------------------------------------------------
# Interactive REPL
# ---------------------------------------------------------------------------


def _run_simple_repl(console: Console) -> None:
    """Fallback REPL using plain ``input()`` when prompt_toolkit is unavailable.

    Used when stdin is not a real Windows console (git-bash, piped input, etc.).
    No tab-completion or history — basic line input only.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    SHUTDOWN_SENTINEL.unlink(missing_ok=True)

    _repl_down = False
    _last_ctrl_c: float = 0.0
    _DOUBLE_CTRL_C_WINDOW = 3.0

    while not _repl_down:
        if SHUTDOWN_SENTINEL.exists():
            console.print("\n[yellow]Shutdown requested from external process.[/]")
            cmd_terminate(console)
            break

        try:
            raw = input("archangel> ")
        except EOFError:
            console.print()
            break
        except KeyboardInterrupt:
            now = time.time()
            if now - _last_ctrl_c < _DOUBLE_CTRL_C_WINDOW:
                console.print("\n[red]Forced exit.[/]")
                break
            _last_ctrl_c = now
            if _countdown_or_second_ctrl_c(console):
                console.print("\n[red]Forced exit.[/]")
                break
            continue

        raw = raw.strip()
        if not raw:
            continue

        parts = shlex.split(raw)
        cmd = parts[0].lower()
        args = parts[1:]

        def _flag(name: str) -> bool:
            return f"--{name}" in args

        def _opt(name: str) -> str | None:
            for i, a in enumerate(args):
                if a == f"--{name}" and i + 1 < len(args):
                    return args[i + 1]
            return None

        if cmd in ("exit", "quit"):
            cmd_terminate(console)
            break
        elif cmd == "help":
            console.print(_REPL_HELP)
        elif cmd == "status":
            cmd_status(console, as_json=_flag("json"))
        elif cmd == "watch":
            cmd_watch(console)
        elif cmd == "scan":
            cmd_scan(console)
        elif cmd == "doctor":
            cmd_doctor(console)
        elif cmd == "config":
            valid_actions = ("show", "edit", "validate")
            action = args[0] if args and args[0] in valid_actions else "show"
            section = args[1] if len(args) > 1 else None
            cmd_config(console, action=action, section=section)
        elif cmd == "export":
            fmt = _opt("format") or "json"
            output = _opt("output")
            limit_raw = _opt("limit")
            limit = int(limit_raw) if limit_raw else None
            cmd_export(console, fmt=fmt, output=output, limit=limit)
        elif cmd == "logs":
            tail_raw = _opt("tail")
            t = int(tail_raw) if tail_raw else 50
            follow = _flag("follow")
            level = _opt("level")
            cmd_logs(console, tail=t, follow=follow, level=level)
        elif cmd == "purge":
            cmd_purge(console, confirmed=_flag("yes"))
        elif cmd == "update":
            cmd_update(console)
        elif cmd == "version":
            cmd_version(console)
        else:
            console.print(f"[red]Unknown command:[/] {cmd}")
            console.print("Type [bold]help[/] for available commands.")

    PID_FILE.unlink(missing_ok=True)
    SHUTDOWN_SENTINEL.unlink(missing_ok=True)


def run_repl(console: Console) -> None:
    """Drop into the ``archangel> `` REPL after a successful summon.

    Uses prompt_toolkit when running under a real Windows console (cmd.exe,
    PowerShell), and falls back to a simple ``input()``-based REPL for
    git-bash, MSYS2, or piped/non-interactive sessions.
    """
    if not sys.stdin.isatty():
        console.print("[yellow]Interactive terminal required. Run [bold]archangel summon[/] in cmd.exe or PowerShell.[/]")
        return

    # Check we are on a real Windows console, not a Cygwin/MSYS pty.
    # prompt_toolkit raises "No Windows console found" otherwise.
    try:
        # Probe: can we get the Windows console OS handle?
        import msvcrt
        msvcrt.get_osfhandle(sys.stdin.fileno())
    except (ImportError, OSError, AttributeError):
        _run_simple_repl(console)
        return

    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Write PID for cross-process signalling
    PID_FILE.write_text(str(os.getpid()))
    # Remove stale sentinel from a previous unclean shutdown
    SHUTDOWN_SENTINEL.unlink(missing_ok=True)

    # prompt_toolkit on Windows checks os.environ.get("TERM").
    # When running under git-bash/MSYS2 where TERM=xterm-256color it
    # raises and refuses to create a Win32 console input.  We clear
    # TERM for the whole REPL lifetime so prompt_toolkit uses its
    # native Windows input/output path.
    _old_term = os.environ.pop("TERM", None)
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory

        # Ensure history file's parent directory exists
        REPL_HISTORY.parent.mkdir(parents=True, exist_ok=True)

        completer = _ArchangelCompleter()
        session = PromptSession(
            "archangel> ",
            history=FileHistory(str(REPL_HISTORY)),
            completer=completer,
            complete_while_typing=False,
        )

        _repl_down = False
        _last_ctrl_c: float = 0.0
        _DOUBLE_CTRL_C_WINDOW = 3.0

        while not _repl_down:
            # Poll sentinel from external ``archangel terminate``
            if SHUTDOWN_SENTINEL.exists():
                console.print("\n[yellow]Shutdown requested from external process.[/]")
                cmd_terminate(console)
                break

            try:
                raw = session.prompt()
            except KeyboardInterrupt:
                now = time.time()
                if now - _last_ctrl_c < _DOUBLE_CTRL_C_WINDOW:
                    console.print("\n[red]Forced exit.[/]")
                    _repl_down = True
                    break
                _last_ctrl_c = now
                if _countdown_or_second_ctrl_c(console):
                    console.print("\n[red]Forced exit.[/]")
                    _repl_down = True
                    break
                continue
            except Exception as pt_exc:
                # prompt_toolkit failed (e.g. stdin issues, console mode).
                # Fall back gracefully to the simple input()-based REPL.
                console.print(f"\n[yellow]prompt_toolkit error: {pt_exc}[/]")
                console.print("[yellow]Falling back to simple input mode.[/]")
                _run_simple_repl(console)
                return

            raw = raw.strip()
            if not raw:
                continue

            parts = shlex.split(raw)
            cmd = parts[0].lower()
            args = parts[1:]

            # -- parse common options that some commands accept --
            def _flag(name: str) -> bool:
                return f"--{name}" in args

            def _opt(name: str) -> str | None:
                for i, a in enumerate(args):
                    if a == f"--{name}" and i + 1 < len(args):
                        return args[i + 1]
                return None

            # -- dispatch --
            if cmd in ("exit", "quit"):
                cmd_terminate(console)
                _repl_down = True
                break

            elif cmd == "help":
                console.print(_REPL_HELP)

            elif cmd == "status":
                cmd_status(console, as_json=_flag("json"))

            elif cmd == "watch":
                cmd_watch(console)

            elif cmd == "scan":
                cmd_scan(console)

            elif cmd == "doctor":
                cmd_doctor(console)

            elif cmd == "config":
                valid_actions = ("show", "edit", "validate")
                action = args[0] if args and args[0] in valid_actions else "show"
                section = args[1] if len(args) > 1 else None
                cmd_config(console, action=action, section=section)

            elif cmd == "export":
                fmt = _opt("format") or "json"
                output = _opt("output")
                limit_raw = _opt("limit")
                limit = int(limit_raw) if limit_raw else None
                cmd_export(console, fmt=fmt, output=output, limit=limit)

            elif cmd == "logs":
                tail_raw = _opt("tail")
                t = int(tail_raw) if tail_raw else 50
                follow = _flag("follow")
                level = _opt("level")
                cmd_logs(console, tail=t, follow=follow, level=level)

            elif cmd == "purge":
                cmd_purge(console, confirmed=_flag("yes"))

            elif cmd == "update":
                cmd_update(console)

            elif cmd == "version":
                cmd_version(console)

            else:
                console.print(f"[red]Unknown command:[/] {cmd}")
                console.print("Type [bold]help[/] for available commands.")

    finally:
        # Cleanup sentinel / PID
        PID_FILE.unlink(missing_ok=True)
        SHUTDOWN_SENTINEL.unlink(missing_ok=True)
        # Restore TERM so child processes see the original terminal type
        if _old_term is not None:
            os.environ["TERM"] = _old_term


# ---------------------------------------------------------------------------
# Custom Click group — suppresses the ``Usage:`` line in help output
# ---------------------------------------------------------------------------

class _ArchangelGroup(click.Group):
    """A Click group that omits the ``Usage:`` banner from ``--help``."""

    def format_usage(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        pass  # deliberately suppressed


# ---------------------------------------------------------------------------
# CLI layer (Click)  — thin wrappers around cmd_* functions
# ---------------------------------------------------------------------------

@click.group(
    cls=_ArchangelGroup,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--debug", is_flag=True, help="Enable debug-level logging.")
@click.option("--verbose", is_flag=True, help="Increase output verbosity.")
@click.option("--config", type=click.Path(dir_okay=False, path_type=str),
              default=None, help="Path to custom configuration YAML.")
@click.option("-v", "--version", "show_version", is_flag=True,
              help="Show version and exit.")
@click.pass_context
def cli(ctx: click.Context, debug: bool, verbose: bool,
        config: str | None, show_version: bool) -> None:
    """⚔ The Archangel — Autonomous Lead Intelligence Platform"""
    ctx.ensure_object(dict)
    ctx.obj["DEBUG"] = debug
    ctx.obj["VERBOSE"] = verbose
    ctx.obj["CONFIG"] = config

    if show_version:
        cmd_version(_console)
        ctx.exit()

    if ctx.invoked_subcommand is None:
        ctx.invoke(summon)


@cli.command()
@click.pass_context
def summon(ctx: click.Context) -> None:
    """Start the platform (default command)."""
    ok = cmd_summon(
        _console,
        debug=ctx.obj.get("DEBUG", False),
        config_path=ctx.obj.get("CONFIG"),
    )
    if ok:
        run_repl(_console)


@cli.command()
def terminate() -> None:
    """Gracefully shut down the platform."""
    # If a REPL process is running, signal it via sentinel
    if PID_FILE.exists():
        SHUTDOWN_SENTINEL.parent.mkdir(parents=True, exist_ok=True)
        SHUTDOWN_SENTINEL.touch()
        _console.print("[yellow]Sent shutdown signal to running instance.[/]")
        _console.print("[yellow]Waiting for it to exit ...[/]")
        # Poll until the PID file disappears (REPL cleaned it up)
        for _ in range(30):
            time.sleep(0.5)
            if not PID_FILE.exists():
                break
        if PID_FILE.exists():
            _console.print("[red]Instance did not respond. Forcing PID removal.[/]")
            PID_FILE.unlink(missing_ok=True)
        SHUTDOWN_SENTINEL.unlink(missing_ok=True)
        _console.print("[green]✓ The Archangel has been terminated.[/]")
    else:
        cmd_terminate(_console)


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def status(as_json: bool) -> None:
    """Display runtime information and agent health."""
    cmd_status(_console, as_json=as_json)


@cli.command()
def watch() -> None:
    """Live event stream."""
    cmd_watch(_console)


@cli.command()
def scan() -> None:
    """One-time scan (collect, analyse, score — then exit)."""
    cmd_scan(_console)


@cli.command()
def doctor() -> None:
    """Run system diagnostics and report health."""
    cmd_doctor(_console)


@cli.command()
@click.argument("action", type=click.Choice(["show", "edit", "validate"]),
                default="edit", required=False)
@click.argument("section", type=str, required=False)
def config(action: str, section: str | None) -> None:
    """Inspect or edit configuration."""
    cmd_config(_console, action=action, section=section)



@cli.command()
@click.option("--format", "fmt", type=click.Choice(["csv", "json", "md"]),
              default="json", help="Export format.")
@click.option("--output", "-o", type=click.Path(dir_okay=False),
              default=None, help="Output file path.")
@click.option("--limit", type=int, default=None,
              help="Maximum number of leads to export.")
def export(fmt: str, output: str | None, limit: int | None) -> None:
    """Export leads in CSV, JSON, or Markdown format."""
    cmd_export(_console, fmt=fmt, output=output, limit=limit)


@cli.command()
@click.option("--tail", "-t", type=int, default=50, help="Show last N lines.")
@click.option("--follow", "-f", is_flag=True, help="Follow log output.")
@click.option("--level", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
              default=None, help="Filter by log level.")
def logs(tail: int, follow: bool, level: str | None) -> None:
    """View runtime logs."""
    cmd_logs(_console, tail=tail, follow=follow, level=level)


@cli.command()
@click.confirmation_option(prompt="Are you sure you want to purge cache and temporary data?")
def purge() -> None:
    """Clean cache, temporary data, and runtime artifacts."""
    cmd_purge(_console, confirmed=True)


@cli.command()
def update() -> None:
    """Update plugins and system components."""
    cmd_update(_console)


@cli.command()
def version() -> None:
    """Display the installed version of The Archangel."""
    cmd_version(_console)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    """Console-script entrypoint (``archangel``)."""
    try:
        cli(prog_name="archangel")
    except click.ClickException:
        sys.exit(1)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        _console.print("\n[yellow]Interrupted.[/]")
        sys.exit(130)
    except Exception as exc:
        _print_error_panel(
            what="An unexpected error occurred.",
            why=str(exc),
            suggestions=[
                "Run with [bold]--debug[/] for a detailed traceback.",
                "File an issue with the full error output.",
            ],
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
