"""Orchestrator — main loop: capture → analyze → act → repeat."""

from __future__ import annotations

import re
import subprocess
import time
from typing import Any

from rich.console import Console

from .screen import capture_screen, image_to_base64
from .vision import analyze_frame
from .actions import confirm_destructive, execute_action

_console = Console()


def _print_step(
    step: int,
    action: dict[str, Any],
    dry_run: bool = False,
) -> None:
    """Pretty-print the current step and action."""
    label = "[bold cyan]Step[/]"
    prefix = " [yellow]DRY RUN[/]" if dry_run else ""
    _console.print(f"\n{label} {step}:{prefix}")
    for k, v in action.items():
        _console.print(f"  [dim]{k}:[/] {v}")


def _bootstrap_task_environment(task: str) -> None:
    """Open URLs and apps found in the task string, then focus the target.

    Best-effort pre-processing so the vision loop sees the correct window
    instead of a terminal. Skips silently if nothing to open.
    """

    def _is_app_running(executable: str) -> bool:
        """Check if a process with the given name is already running."""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Get-Process '{executable}' -ErrorAction SilentlyContinue"],
                capture_output=True, text=True, timeout=5,
            )
            return bool(result.stdout.strip())
        except Exception:
            return False

    # 1. Detect URLs — anything with http, https, www, or known TLDs
    urls = re.findall(r"https?://[^\s'\"]+", task)
    # Also catch bare domains like google.com, youtube.com
    bare_domains = re.findall(
        r"(?<![a-z0-9.])([a-zA-Z0-9-]+\.(?:com|org|net|io|dev|app|gov|edu|co|uk))(?:\s|$|[\"'.,!?])",
        task,
    )
    for domain in bare_domains:
        clean = domain.rstrip(".,!?;:'\"")
        if not clean.startswith("http"):
            clean = "https://" + clean
        urls.append(clean)
    # Also catch www. patterns without scheme
    www_matches = re.findall(r"www\.[^\s'\"]+", task)
    for www in www_matches:
        if not www.startswith("http"):
            urls.append("https://" + www)

    # 2. Detect known app names
    KNOWN_APPS: dict[str, str] = {
        "notepad": "notepad",
        "chrome": "chrome",
        "firefox": "firefox",
        "edge": "msedge",
        "explorer": "explorer",
        "file explorer": "explorer",
        "code": "code",
        "vscode": "code",
        "vs code": "code",
        "spotify": "spotify",
        "discord": "discord",
        "slack": "slack",
        "terminal": "wt",
        "cmd": "cmd",
        "powershell": "powershell",
    }
    apps: list[str] = []
    close_apps: list[str] = []
    task_lower = task.lower()

    # Check for close commands
    close_match = re.search(r"close\s+(\w+)", task_lower)
    if close_match:
        app_to_close = close_match.group(1)
        for name, executable in KNOWN_APPS.items():
            if name in app_to_close:
                close_apps.append(executable)
                break
        if not close_apps:
            close_apps.append(app_to_close)

    for name, executable in KNOWN_APPS.items():
        if name in task_lower and not close_match:
            apps.append(executable)

    if close_apps:
        _console.print("[dim]Closing apps ...[/]")
        for app in close_apps:
            _console.print(f"  [dim]Closing:[/] {app}")
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Stop-Process -Name '{app}' -Force -ErrorAction SilentlyContinue"],
                capture_output=True, timeout=5,
            )
        return  # Done closing, no need to bootstrap further

    if not urls and not apps:
        return  # nothing to bootstrap

    _console.print("[dim]Bootstrapping environment ...[/]")

    # Open URLs
    for url in urls:
        clean_url = url.rstrip(".,!?;:'\"")
        _console.print(f"  [dim]Opening URL:[/] {clean_url}")
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", f"Start-Process '{clean_url}'"],
        )

    # Open apps
    for app in apps:
        if _is_app_running(app):
            _console.print(f"  [dim]Already running:[/] {app}")
            continue
        _console.print(f"  [dim]Opening app:[/] {app}")
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", f"Start-Process '{app}'"],
        )

    # Wait for windows to appear
    time.sleep(2.5)

    # Focus the most recently opened window (Alt+Tab)
    try:
        import pyautogui
        pyautogui.hotkey("alt", "tab")
        _console.print("  [dim]Focused target window[/]")
    except Exception:
        pass

    time.sleep(1.5)


def run_task(
    task: str,
    max_steps: int = 50,
    dry_run: bool = False,
    bootstrap: bool = True,
) -> str:
    """Main GUI automation loop.

    Args:
        task: Natural-language description of what to do.
        max_steps: Maximum number of actions before giving up.
        dry_run: If True, print actions without executing them.
        bootstrap: If True, auto-open URLs/apps found in the task.

    Returns:
        Summary string (success or failure message).
    """
    history: list[dict[str, Any]] = []

    _console.print(f"\n[bold]Task:[/] {task}")
    _console.print(f"[dim]Max steps: {max_steps}  |  Dry run: {dry_run}[/]")

    # Bootstrap: open URLs/apps found in the task, focus the target window
    if bootstrap:
        _bootstrap_task_environment(task)

    for step in range(1, max_steps + 1):
        # 1. Capture screen
        try:
            screenshot = capture_screen()
        except Exception as exc:
            msg = f"Screenshot failed at step {step}: {exc}"
            _console.print(f"[red]{msg}[/]")
            return msg

        # 2. Analyze with vision model
        try:
            image_b64 = image_to_base64(screenshot)
        except Exception as exc:
            msg = f"Image encoding failed: {exc}"
            _console.print(f"[red]{msg}[/]")
            return msg

        _console.print(f"\n[dim]Analyzing screenshot ({step}/{max_steps})...[/]")
        action = analyze_frame(image_b64, task, history)

        _print_step(step, action, dry_run=dry_run)

        # 3. Check if done
        if action.get("action") == "done":
            summary = action.get("summary", "Task complete.")
            _console.print(f"\n[bold green]✓ Done:[/] {summary}")
            return summary

        # 4. Execute action (with safety check for destructive ops)
        if dry_run:
            _console.print("  [dim]→ (skipped — dry run)[/]")
        else:
            # Prompt confirmation only when action is destructive
            confirmed = confirm_destructive(action)
            if not confirmed:
                _console.print("  [yellow]→ Skipped (user declined)[/]")
                continue
            execute_action(action)

        # 5. Log to history
        history.append(action)

        # 6. Wait briefly between actions so UI can respond
        time.sleep(1.0)

    msg = f"Max steps ({max_steps}) reached. Task incomplete."
    _console.print(f"[yellow]{msg}[/]")
    return msg
