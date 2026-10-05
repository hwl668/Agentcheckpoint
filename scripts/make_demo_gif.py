"""Render docs/demo.gif from real `agentck` output (maintainer tool, not runtime).

Usage:
    .venv/Scripts/python -m pip install pillow   # one-time
    .venv/Scripts/python scripts/make_demo_gif.py

Renders scripted terminal frames (captured from actual runs) in a
GitHub-dark window and writes docs/demo.gif plus a poster PNG.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 980, 660
BAR_H = 44
LINE_H = 22
PAD_X = 20
PAD_Y = 58

BG = (13, 17, 23)
BAR = (22, 27, 34)
FG = (201, 209, 217)
BRIGHT = (240, 246, 252)
GREEN = (63, 185, 80)
YELLOW = (210, 153, 34)
CYAN = (88, 166, 255)
GREY = (110, 118, 129)
RED = (248, 81, 73)
DOT_RED, DOT_YELLOW, DOT_GREEN = (248, 81, 73), (210, 153, 34), (63, 185, 80)

FRAME_MS = 1600

F = FG
G = GREEN
Y = YELLOW
C = CYAN
B = BRIGHT
D = GREY


def _frames():
    return [
        [  # 1 — save
            ("$ agentck save glm-cache-refactor --agent glm \\", G),
            ("    --goal \"Fix CUDA memory leak\" \\", G),
            ("    --next \"inspect Cache.evict()\" \\", G),
            ("    --test \"git rev-parse --verify HEAD\"", G),
            ("", F),
            ("Checkpoint saved: cp_20261004_161741 (label: glm-cache-refactor)", B),
            ("  branch:   main @ c3e654351b9d", F),
            ("  changes:  0 staged, 2 unstaged, 0 untracked", F),
            ("  tests:    1 recorded (1 passed, 0 failed/other)", F),
            ("  agent:    glm | goal: Fix CUDA memory leak", F),
            ("  saved to: .agentcheckpoint/checkpoints/cp_20261004_161741", D),
            ("", F),
            ("# machine-observed git facts + test evidence,", D),
            ("# agent claims stored separately", D),
        ],
        [  # 2 — verify, no drift
            ("$ agentck verify", G),
            ("", F),
            ("Checkpoint cp_20261004_161741 (label: glm-cache-refactor)", B),
            ("Created 2026-10-04T16:17:41Z — source agent: glm", D),
            ("", F),
            ("Integrity", C),
            ("✓ 10 artifacts match recorded hashes", G),
            ("", F),
            ("Repository", C),
            ("✓ same repository", G),
            ("✓ branch unchanged (main)", G),
            ("✓ HEAD unchanged (c3e654351b9d)", G),
            ("", F),
            ("Files", C),
            ("✓ src_cache.py unchanged", G),
            ("✓ test_cache.py unchanged", G),
            ("", F),
            ("Resume confidence: 100%", B),
        ],
        [  # 3 — the repo moves on
            ("$ printf \"hotfix during review\\n\" >> src_cache.py", G),
            ("", F),
            ("# ...the next agent keeps working...", D),
            ("# the checkpoint's recorded facts are now aging", D),
            ("", F),
            ("$ agentck verify", G),
        ],
        [  # 4 — verify catches the drift (the money shot)
            ("Checkpoint cp_20261004_161741 (label: glm-cache-refactor)", B),
            ("Created 2026-10-04T16:17:41Z — source agent: glm", D),
            ("", F),
            ("Integrity", C),
            ("✓ 10 artifacts match recorded hashes", G),
            ("", F),
            ("Files", C),
            ("! src_cache.py changed since checkpoint", Y),
            ("✓ test_cache.py unchanged", G),
            ("", F),
            ("Tests", C),
            ("! git rev-parse --verify HEAD", Y),
            ("  PASS at checkpoint — result is now STALE", Y),
            ("", F),
            ("Claims", C),
            ("? \"switched eviction policy to LRU\"", C),
            ("  agent-reported, not independently verified", D),
            ("", F),
            ("Resume confidence: 75%", Y),
        ],
        [  # 5 — handoff to the next agent
            ("$ agentck resume codex", G),
            ("", F),
            ("# AgentCheckpoint Resume", B),
            ("- Checkpoint: cp_20261004_161741 (glm-cache-refactor)", F),
            ("- Resume confidence: **75%**", F),
            ("", F),
            ("## Completed", C),
            ("[OBSERVED]", B),
            ("- src_cache.py (unstaged)", F),
            ("[AGENT-REPORTED]", B),
            ("- switched eviction policy to LRU", F),
            ("", F),
            ("## Verification", C),
            ("- git rev-parse --verify HEAD — PASS at checkpoint;", F),
            ("  result is now STALE (repository drifted)", Y),
            ("", F),
            ("## Drift", C),
            ("Drift detected since checkpoint:", F),
            ("  - changed: src_cache.py", Y),
        ],
    ]


def load_fonts() -> tuple:
    candidates = [
        "C:/Windows/Fonts/consola.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ]
    mono = None
    for path in candidates:
        try:
            mono = ImageFont.truetype(path, 16)
            break
        except OSError:
            continue
    if mono is None:
        mono = ImageFont.load_default()
    bold = None
    for path in ("C:/Windows/Fonts/consolab.ttf",):
        try:
            bold = ImageFont.truetype(path, 16)
            break
        except OSError:
            continue
    return mono, bold


def _draw_check(draw, x: int, y: int, color) -> None:
    draw.line([(x + 1, y + 12), (x + 5, y + 16), (x + 13, y + 3)], fill=color, width=2)


def _draw_cross(draw, x: int, y: int, color) -> None:
    draw.line([(x + 2, y + 3), (x + 12, y + 15)], fill=color, width=2)
    draw.line([(x + 12, y + 3), (x + 2, y + 15)], fill=color, width=2)


def render_frame(lines, mono, bold) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, BAR_H], fill=BAR)
    for i, color in enumerate((DOT_RED, DOT_YELLOW, DOT_GREEN)):
        cx = 24 + i * 26
        draw.ellipse([cx, BAR_H // 2 - 7, cx + 14, BAR_H // 2 + 7], fill=color)
    draw.text((W // 2 - 150, 12), "agentck — verifiable agent checkpoints", font=mono, fill=GREY)
    HEADERS = ("#", "Integrity", "Repository", "Files", "Tests", "Claims")
    y = PAD_Y
    for text, color in lines:
        font = bold if text.startswith(HEADERS) else mono
        if text.startswith(("✓ ", "✗ ")):
            marker, rest = text[:1], text[2:]
            if marker == "✓":
                _draw_check(draw, PAD_X, y, color)
            else:
                _draw_cross(draw, PAD_X, y, color)
            draw.text((PAD_X + 24, y), rest, font=font, fill=color)
        else:
            draw.text((PAD_X, y), text, font=font, fill=color)
        y += LINE_H
    return img


def main() -> None:
    mono, bold = load_fonts()
    frames = [render_frame(lines, mono, bold) for lines in _frames()]
    docs = Path(__file__).resolve().parent.parent / "docs"
    docs.mkdir(exist_ok=True)
    frames[0].save(
        docs / "demo.gif",
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=True,
    )
    frames[3].save(docs / "demo-stale.png", optimize=True)
    size = (docs / "demo.gif").stat().st_size
    print(f"wrote {docs / 'demo.gif'} ({size / 1024:.0f} KB, {len(frames)} frames)")


if __name__ == "__main__":
    main()
