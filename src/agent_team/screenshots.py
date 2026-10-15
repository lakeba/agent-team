"""Headless browser screenshots of a page at desktop and true phone width, and of deck slides.

Uses an installed Chromium-family browser (Chrome, Edge, Chromium, Brave) with a throwaway
profile. Headless windows can't be narrower than about 500px, so phone shots load the page in
an iframe of the target width and crop. Pillow (optional) splits tall pages into sections.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "google-chrome", "chromium", "chromium-browser", "microsoft-edge",
]
SLIDE_RE = re.compile(r'<section[^>]*class="[^"]*\bslide\b', re.I)


def find_browser(explicit: str = "") -> str:
    for c in ([explicit] if explicit else []) + CANDIDATES:
        path = c if os.path.isabs(c) else shutil.which(c)
        if path and os.path.exists(path):
            return path
    return ""


class Shooter:
    def __init__(self, browser: str):
        self.browser = browser
        self.profile = tempfile.mkdtemp()

    def close(self):
        shutil.rmtree(self.profile, ignore_errors=True)

    def _run(self, *args: str, text: bool = False):
        return subprocess.run([self.browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                               "--no-first-run", "--allow-file-access-from-files",
                               f"--user-data-dir={self.profile}", "--virtual-time-budget=3000", *args],
                              capture_output=True, text=text, timeout=90)

    def _measure(self, url: str, width: int) -> int:
        r = self._run(f"--window-size={width},900", "--dump-dom", url, text=True)
        m = re.search(r"<title>H=(\d+)</title>", r.stdout)
        return min(int(m.group(1)), 16000) if m else 2400

    def page(self, html: Path, png: Path, width: int) -> int:
        """Full-page screenshot at `width`. Returns the page height, or 0 on failure."""
        narrow = width < 500
        probe = html.parent / f".probe-{width}.html"
        inner = html.name
        if narrow:
            body = (f'<iframe id="f" src="{inner}" style="border:0;display:block;width:{width}px;height:900px">'
                    "</iframe><script>document.getElementById('f').addEventListener('load',function(){"
                    "var h=this.contentDocument.documentElement.scrollHeight;this.style.height=h+'px';"
                    "document.title='H='+h;});</script>")
            probe.write_text(f'<!doctype html><html><body style="margin:0">{body}</body></html>', encoding="utf-8")
        else:
            page = html.read_text(encoding="utf-8")
            script = ("<script>addEventListener('load',()=>{document.title='H='+"
                      "document.documentElement.scrollHeight})</script>")
            probe.write_text(page.replace("</body>", script + "</body>") if "</body>" in page else page + script,
                             encoding="utf-8")
        try:
            height = self._measure(probe.as_uri(), width if not narrow else 600)
            target = probe if narrow else html
            self._run(f"--window-size={600 if narrow else width},{height}", f"--screenshot={png}", target.as_uri())
        finally:
            probe.unlink(missing_ok=True)
        if not png.exists():
            return 0
        if narrow:
            _crop(png, width, height)
        return height

    def slide(self, deck: Path, n: int, png: Path) -> bool:
        self._run("--window-size=1280,720", f"--screenshot={png}", f"{deck.as_uri()}#{n}")
        return png.exists()


def _crop(png: Path, width: int, height: int) -> None:
    try:
        from PIL import Image
    except ImportError:
        return
    with Image.open(png) as img:
        img.crop((0, 0, width, min(height, img.height))).save(png)


def sections(png: Path, tile: int) -> list[Path]:
    try:
        from PIL import Image
    except ImportError:
        return [png]
    with Image.open(png) as img:
        w, h = img.size
        if h <= tile:
            return [png]
        out = []
        for i, y in enumerate(range(0, h, tile), start=1):
            part = png.with_name(f"{png.stem}-{i}.png")
            img.crop((0, y, w, min(y + tile, h))).save(part)
            out.append(part)
        return out


def capture(root: Path, site: str, deck: str, out: Path, browser: str) -> list[tuple[str, Path]]:
    out.mkdir(parents=True, exist_ok=True)
    shooter, shots = Shooter(browser), []
    try:
        site_path = root / site if site else None
        if site_path and site_path.exists():
            for label, w, tile in [("desktop 1440px", 1440, 1600), ("phone 390px", 390, 2400)]:
                png = out / f"site-{w}.png"
                h = shooter.page(site_path, png, w)
                if h:
                    parts = sections(png, tile)
                    shots += [(f"Website, {label}, section {i} of {len(parts)} (page {h}px tall)", p)
                              for i, p in enumerate(parts, 1)]
        deck_path = root / deck if deck else None
        if deck_path and deck_path.exists():
            count = min(len(SLIDE_RE.findall(deck_path.read_text(encoding="utf-8"))), 12)
            for n in range(1, count + 1):
                png = out / f"slide-{n:02d}.png"
                if shooter.slide(deck_path, n, png):
                    shots.append((f"Deck slide {n} of {count}", png))
    finally:
        shooter.close()
    return shots
