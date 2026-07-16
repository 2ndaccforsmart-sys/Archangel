"""Transparent cursor overlay — shows automation position on screen."""

from __future__ import annotations

import os
import tkinter as tk
from typing import Optional

from PIL import Image, ImageTk


class CursorOverlay:
    """Transparent topmost window displaying a cursor at the automation target.

    - Always on top, click-through, no taskbar entry
    - Smooth animation to target position
    - Fading trail of last 5 positions
    """

    CURSOR_SIZE = 48
    TRAIL_LENGTH = 8
    TRAIL_COLORS = ["#FF0000", "#FF4444", "#FF6666", "#FF8888", "#FFAAAA", "#FFCCCC", "#FFEEEE", "#FFFFFF"]
    ANIMATION_STEPS = 10
    ANIMATION_DELAY_MS = 16  # ~60fps

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()  # Start hidden

        # Make window transparent, topmost, click-through
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.9)

        # Black = transparent on Windows
        try:
            self.root.attributes("-transparentcolor", "black")
        except tk.TclError:
            pass  # Not on Windows, skip

        # Set window shape (irregular cursor)
        self.root.configure(bg="black")

        # Canvas for drawing cursor + trail
        self.canvas = tk.Canvas(
            self.root,
            width=200,
            height=200,
            bg="black",
            highlightthickness=0,
        )
        self.canvas.pack()

        # Load cursor image
        self.cursor_image: Optional[ImageTk.PhotoImage] = None
        self._load_cursor()

        # Trail dots (oval IDs)
        self.trail_items: list[tuple[int, int]] = []

        # Current position — start at screen center (1920x1080)
        self._x = 960
        self._y = 540
        self._target_x = 960
        self._target_y = 540
        self._animating = False
        self._visible = False

    def _load_cursor(self) -> None:
        """Load and scale the cursor PNG."""
        cursor_path = os.path.join(os.path.dirname(__file__), "cursor.png")
        if not os.path.exists(cursor_path):
            return

        img = Image.open(cursor_path).convert("RGBA")
        img = img.resize((self.CURSOR_SIZE, self.CURSOR_SIZE), Image.LANCZOS)
        self.cursor_image = ImageTk.PhotoImage(img)

    def show(self) -> None:
        """Show the overlay window."""
        self.root.deiconify()
        self._pulse()

    def _pulse(self) -> None:
        """Continuously redraw for pulsing effect."""
        if self._visible:
            self._draw()
            self.root.after(50, self._pulse)  # 20fps for smooth pulse

    def hide(self) -> None:
        """Hide the overlay window."""
        self._visible = False
        self.root.withdraw()

    def update_position(self, x: int, y: int) -> None:
        """Move cursor to target position with smooth animation.

        Args:
            x: Target X coordinate on screen.
            y: Target Y coordinate on screen.
        """
        # Clamp to screen bounds
        x = max(0, min(x, 1920))
        y = max(0, min(y, 1080))

        self._target_x = x
        self._target_y = y

        # Add current position to trail
        self._add_trail(self._x, self._y)

        # Start animation if not already running
        if not self._animating:
            self._animating = True
            self._animate_step(0)

    def _animate_step(self, step: int) -> None:
        """Interpolate one animation frame toward target."""
        if step >= self.ANIMATION_STEPS:
            self._x = self._target_x
            self._y = self._target_y
            self._animating = False
            self._draw()
            return

        # Linear interpolation
        t = (step + 1) / self.ANIMATION_STEPS
        self._x = int(self._x + (self._target_x - self._x) * t)
        self._y = int(self._y + (self._target_y - self._y) * t)

        self._draw()
        self.root.after(self.ANIMATION_DELAY_MS, self._animate_step, step + 1)

    def _add_trail(self, x: int, y: int) -> None:
        """Add a position to the trail (keeps last N)."""
        self.trail_items.append((x, y))
        if len(self.trail_items) > self.TRAIL_LENGTH:
            self.trail_items.pop(0)

    def _draw(self) -> None:
        """Redraw canvas with trail + cursor."""
        self.canvas.delete("all")

        # Canvas center is where we draw the cursor
        cx = 100
        cy = 100

        # Draw pulsing glow ring
        import time
        pulse = abs(int(time.time() * 1000) % 1000 - 500) / 500.0  # 0.0 to 1.0
        glow_size = int(20 + pulse * 15)
        glow_alpha = int(80 + pulse * 60)
        self.canvas.create_oval(
            cx - glow_size, cy - glow_size,
            cx + glow_size, cy + glow_size,
            outline=f"#{glow_alpha:02x}0000",
            width=3,
        )

        # Draw trail (oldest first, fading)
        for i, (tx, ty) in enumerate(self.trail_items):
            color = self.TRAIL_COLORS[min(i, len(self.TRAIL_COLORS) - 1)]
            size = 6 + (i * 3)  # Older = smaller
            offset = size // 2
            # Trail positions relative to canvas center
            rel_x = cx + (tx - self._x)
            rel_y = cy + (ty - self._y)
            self.canvas.create_oval(
                rel_x - offset, rel_y - offset,
                rel_x + offset, rel_y + offset,
                fill=color, outline="",
            )

        # Draw cursor at canvas center
        if self.cursor_image:
            self.canvas.create_image(
                cx, cy,
                anchor=tk.CENTER,
                image=self.cursor_image,
            )
        else:
            # Fallback: bright red crosshair
            size = 12
            self.canvas.create_line(
                cx - size, cy, cx + size, cy,
                fill="#FF0000", width=3,
            )
            self.canvas.create_line(
                cx, cy - size, cx, cy + size,
                fill="#FF0000", width=3,
            )

        # Position window so canvas center aligns with target
        win_x = self._x - cx
        win_y = self._y - cy
        self.root.geometry(f"+{win_x}+{win_y}")

    def destroy(self) -> None:
        """Clean up the overlay window."""
        try:
            self.root.destroy()
        except tk.TclError:
            pass
