"""Banner renderer — clears the terminal and displays the official Archangel ASCII art."""

import os
import shutil

from rich.console import Console
from rich.style import Style


def _get_terminal_width() -> int:
    """Return the current terminal width, falling back to 80."""
    try:
        size = shutil.get_terminal_size()
        return size.columns
    except (ValueError, OSError):
        return 80


def render_banner(console: Console | None = None) -> None:
    """Clear the terminal and render the Archangel banner in rich style."""
    if console is None:
        console = Console()

    os.system("cls" if os.name == "nt" else "clear")

    width = _get_terminal_width()

    # Clean art — no leading/trailing newlines, no inconsistent indent
    BANNER_LINES = [
        " █████╗ ██████╗  ██████╗██╗  ██╗ █████╗ ███╗   ██╗ ██████╗ ███████╗██╗",
        "██╔══██╗██╔══██╗██╔════╝██║  ██║██╔══██╗████╗  ██║██╔════╝ ██╔════╝██║",
        "███████║██████╔╝██║     ███████║███████║██╔██╗ ██║██║  ███╗█████╗  ██║",
        "██╔══██║██╔══██╗██║     ██╔══██║██╔══██║██║╚██╗██║██║   ██║██╔══╝  ██║",
        "██║  ██║██║  ██║╚██████╗██║  ██║██║  ██║██║ ╚████║╚██████╔╝███████╗███████╗",
        "╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚══════╝╚══════╝",
    ]

    TAGLINE = "Opportunity is revealed to those who seek."

    primary = Style(color="#ffffff", bold=True)
    tagline_style = Style(color="#c0c0c0", italic=True)

    # Calculate block width (longest line)
    block_width = max(len(line) for line in BANNER_LINES)
    padding = max(0, (width - block_width) // 2)
    pad_str = " " * padding

    # Print block as one centered unit
    for line in BANNER_LINES:
        console.print(pad_str + line, style=primary)

    # Center tagline
    tagline_pad = max(0, (width - len(TAGLINE)) // 2)
    console.print(" " * tagline_pad + TAGLINE, style=tagline_style)
    console.print()
