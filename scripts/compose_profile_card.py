#!/usr/bin/env python3
"""
compose_profile_card.py
=======================

Combine the ASCII portrait and the "about me" terminal into ONE SVG, so the two
windows always share a top edge and a bottom edge.

Why one image
-------------
The README used to put the portrait <img> and a ```console code block side by
side in a table. The image scales with the column width, but the code block's
height is fixed by GitHub's font size, so the two only lined up at one exact
viewport width. Drawing both windows on the same canvas makes them scale
together: whatever width GitHub renders the card at, they end on the same line.

How it works
------------
* The portrait SVG (from make_ascii_portrait.py) is nested as-is inside a
  <svg> whose viewBox crops to just its character grid, so its own window
  chrome is clipped away and both windows get identical chrome drawn here.
* The about text reveals line by line with the same SMIL clip-wipe the
  portrait uses, finishing at about the same time the portrait does.

Usage
-----
    python scripts/compose_profile_card.py art/kymani-ascii.svg art/profile-card.svg

Edit ABOUT below to change the text. If you add or remove lines, check that the
last line still sits above the bottom bar (the script fails loudly if not).
Bump the ?v= query on the README's <img> after regenerating, since GitHub
caches README images hard.
"""

from __future__ import annotations

import html
import re
import sys

# ── Content ──────────────────────────────────────────────────────────────────
# ("cmd", text) renders as a prompt line, ("out", text) as output, None as a gap.
ABOUT = [
    ("cmd", "whoami"),
    ("out", "Kymani Jarrett, Software Engineer"),
    None,
    ("cmd", "education"),
    ("out", "B.S. Information Technology & Cybersecurity"),
    ("out", "University of Cincinnati, May 2028"),
    None,
    ("cmd", "experience --latest"),
    ("out", "Cloud Data Engineer Intern @ The J.M. Smucker Co."),
    ("out", "Shipped data infrastructure as code to production"),
    ("out", "on AWS across a portfolio of iconic consumer brands."),
    None,
    ("cmd", "ls ~/projects"),
    ("out", "Vigil     ETL observability for AWS Glue pipelines."),
    ("out", "          Anomaly detection, RBAC, audit logging."),
    ("out", "Clausify  AI contract analysis that scores each"),
    ("out", "          clause for risk against standard terms."),
    None,
    ("cmd", "cat ~/.involvement"),
    ("out", "Corporate Outreach Chair | ColorStack@UC"),
    ("out", "Programming Chair | UBSA"),
    ("out", "Secretary | Bearcat Buddies Advisory Council"),
    ("out", "Resident Advisor | Resident Edu. & Dev."),
]
LEFT_TITLE = "kymani@github: ~ $ ./portrait.sh"
RIGHT_TITLE = "kymani@github: ~ $ ./about.sh"
LEFT_FOOTER = ("whoami", "Kymani Jarrett")
RIGHT_FOOTER = ("open", "kymanij.vercel.app")

# ── Geometry ─────────────────────────────────────────────────────────────────
W, H = 860, 560          # whole card; GitHub renders it at roughly 1:1 on desktop
GAP = 16                 # space between the two windows
TOP = 30                 # title bar height (same as the portrait generator)
BOTTOM = 36              # footer bar height
PAD = 12                 # inner padding
ART_VIEWBOX = (18, 36, 628, 960)   # crop of the 664x1042 portrait: grid only

FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
FS = 13.5                # about text size
LH = 20                  # about line height
CHAR_W = FS * 0.6        # monospace advance, for the overflow check

BG_TOP, BG_BOTTOM = "#111722", "#0D1117"
BORDER, MUTED, TEXT, OUT, ACCENT = "#30363D", "#7D8590", "#C9D1D9", "#79C0FF", "#22D3EE"

START, STEP, WIPE = 0.2, 0.28, 0.22   # about text timing (seconds)


def window(x: float, w: float, title: str, footer: tuple[str, str], cursor_id: str) -> str:
    """Rounded terminal window with traffic lights, a title bar, and a footer prompt.

    The title is centered in the space to the right of the traffic lights, so it
    never collides with them in the narrower portrait window.
    """
    fy = H - BOTTOM
    prompt = f"kymani@github:~$ {footer[0]} "
    cursor_x = x + PAD + 8 + (len(prompt) + len(footer[1])) * 13 * 0.6 + 2
    return f"""
<rect x="{x}" y="0" width="{w}" height="{H}" rx="12" fill="url(#cardbg)"/>
<rect x="{x + .5}" y=".5" width="{w - 1}" height="{H - 1}" rx="12" fill="none" stroke="{BORDER}"/>
<line x1="{x}" y1="{TOP}" x2="{x + w}" y2="{TOP}" stroke="{BORDER}"/>
<circle cx="{x + 20}" cy="15" r="5" fill="#FF5F56"/>
<circle cx="{x + 36}" cy="15" r="5" fill="#FFBD2E"/>
<circle cx="{x + 52}" cy="15" r="5" fill="#27C93F"/>
<text x="{x + 64 + (w - 64) / 2}" y="19" fill="{MUTED}" font-size="12" text-anchor="middle">{html.escape(title)}</text>
<line x1="{x}" y1="{fy}" x2="{x + w}" y2="{fy}" stroke="{BORDER}"/>
<text x="{x + PAD + 8}" y="{fy + 23}" fill="{MUTED}" font-size="13" xml:space="preserve">{html.escape(prompt)}<tspan fill="{ACCENT}">{html.escape(footer[1])}</tspan></text>
<rect id="{cursor_id}" x="{cursor_x:.1f}" y="{fy + 11}" width="8" height="14" fill="{ACCENT}"><animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.51;1" dur="1s" repeatCount="indefinite"/></rect>"""


def portrait_body(svg: str) -> str:
    """Inner markup of the portrait SVG with its ids namespaced to avoid clashes."""
    inner = re.sub(r"^.*?<svg[^>]*>", "", svg, count=1, flags=re.S)
    inner = re.sub(r"</svg>\s*$", "", inner)
    inner = re.sub(r'id="([^"]+)"', r'id="p-\1"', inner)
    return re.sub(r"url\(#([^)]+)\)", r"url(#p-\1)", inner)


def about_lines(x0: float, y0: float, max_w: float) -> str:
    out, t, y = [], START, y0
    for i, line in enumerate(ABOUT):
        if line is None:
            y += LH
            continue
        kind, text = line
        shown = ("$ " + text) if kind == "cmd" else text
        if len(shown) * CHAR_W > max_w:
            sys.exit(f"about line too wide for the window: {shown!r}")
        if kind == "cmd":
            body = f'<tspan fill="{MUTED}">$ </tspan><tspan fill="{TEXT}">{html.escape(text)}</tspan>'
        else:
            body = html.escape(text)
        out.append(
            f'<clipPath id="a{i}"><rect x="{x0}" y="{y - FS}" height="{LH}" width="0">'
            f'<animate attributeName="width" from="0" to="{max_w}" begin="{t:.2f}s" dur="{WIPE}s" fill="freeze"/>'
            f"</rect></clipPath>"
            f'<text clip-path="url(#a{i})" x="{x0}" y="{y}" fill="{OUT}" font-size="{FS}" xml:space="preserve">{body}</text>'
        )
        t += STEP
        y += LH
    return "\n".join(out), y


def main(src: str, dst: str) -> None:
    portrait = open(src, encoding="utf-8").read()

    vx, vy, vw, vh = ART_VIEWBOX
    art_h = H - TOP - BOTTOM - 2 * PAD
    art_w = art_h * vw / vh
    left_w = art_w + 2 * PAD
    right_x = left_w + GAP
    right_w = W - right_x

    text_x = right_x + PAD + 8
    lines, last_baseline = about_lines(text_x, TOP + PAD + FS + 6, right_w - 2 * (PAD + 8))
    if last_baseline - LH + 6 > H - BOTTOM - 4:
        sys.exit("about text runs into the footer; remove a line or reduce LH")

    card = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t" font-family="{FONT}">
<title id="t">Kymani Jarrett: ASCII portrait beside a terminal listing education, latest experience, projects, and involvement</title>
<defs><linearGradient id="cardbg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{BG_TOP}"/><stop offset="1" stop-color="{BG_BOTTOM}"/></linearGradient></defs>
{window(0, left_w, LEFT_TITLE, LEFT_FOOTER, "cur-left")}
<svg x="{PAD}" y="{TOP + PAD}" width="{art_w:.1f}" height="{art_h}" viewBox="{vx} {vy} {vw} {vh}" preserveAspectRatio="xMidYMid meet">
{portrait_body(portrait)}
</svg>
{window(right_x, right_w, RIGHT_TITLE, RIGHT_FOOTER, "cur-right")}
{lines}
</svg>
"""
    with open(dst, "w", encoding="utf-8") as f:
        f.write(card)
    print(f"wrote {dst}: {W}x{H}, left window {left_w:.0f}px, right window {right_w:.0f}px")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
