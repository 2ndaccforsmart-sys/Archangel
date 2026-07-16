"""Obscura-based web scraper for Archangel."""

import subprocess
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class ObscuraScraper:
    """Web scraper using the Obscura headless browser."""

    def __init__(self):
        self._obscura = shutil.which("obscura")
        if not self._obscura:
            local = Path(__file__).resolve().parents[2] / "tools" / "obscura" / "obscura.exe"
            if local.exists():
                self._obscura = str(local)

    def _run(self, args: list[str], timeout: int = 30) -> str:
        if not self._obscura:
            return "Error: obscura binary not found in PATH or tools/obscura/"
        try:
            result = subprocess.run(
                [self._obscura] + args,
                capture_output=True, timeout=timeout
            )
            try:
                stdout = result.stdout.decode("utf-8", errors="replace").strip()
            except Exception:
                stdout = result.stdout.decode("latin-1", errors="replace").strip()
            if result.returncode == 0:
                return stdout
            try:
                stderr = result.stderr.decode("utf-8", errors="replace").strip()
            except Exception:
                stderr = result.stderr.decode("latin-1", errors="replace").strip()
            return f"Error: {stderr}"
        except subprocess.TimeoutExpired:
            return "Error: obscura command timed out"
        except Exception as exc:
            return f"Error: {exc}"

    def fetch_text(self, url: str, timeout: int = 30) -> str:
        return self._run(["fetch", url, "--dump", "text", "--timeout", str(timeout)], timeout + 10)

    def fetch_html(self, url: str, timeout: int = 30) -> str:
        return self._run(["fetch", url, "--dump", "html", "--timeout", str(timeout)], timeout + 10)

    def fetch_links(self, url: str, timeout: int = 30) -> str:
        return self._run(["fetch", url, "--dump", "links", "--timeout", str(timeout)], timeout + 10)

    def fetch_eval(self, url: str, js: str, timeout: int = 30) -> str:
        return self._run(["fetch", url, "--eval", js, "--timeout", str(timeout)], timeout + 10)

    def fetch_markdown(self, url: str, timeout: int = 30) -> str:
        return self._run(["fetch", url, "--dump", "markdown", "--timeout", str(timeout)], timeout + 10)
