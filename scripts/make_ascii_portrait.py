#!/usr/bin/env python3
"""
make_ascii_portrait.py
======================

Turn a portrait photo into a monochrome ASCII-art SVG that "types" itself in
like a terminal, then freezes. Drop the output in your GitHub profile README.

Why this works on GitHub
------------------------
GitHub renders an SVG referenced from a README via <img>. In that context the
browser runs SMIL animations (<animate>) and CSS animations, but NOT JavaScript.
So the reveal here is built entirely from SMIL: each text row sits inside a
<clipPath> whose rect grows from width 0 to full width, staggered top to bottom,
with a little block cursor riding the wipe edge.

Usage
-----
    pip install pillow
    python make_ascii_portrait.py photo.jpg art/kymani-ascii.svg --name "Kymani Jarrett"

Optional background removal (much cleaner result, heavier install):

    pip install "rembg[cpu]" onnxruntime
    python make_ascii_portrait.py photo.jpg art/kymani-ascii.svg --name "Kymani Jarrett" --cutout

Tuning notes
------------
* --gamma is applied as lum = (pixel/255) ** gamma, so values ABOVE 1.0 lower
  luminance and push the art denser/darker; values BELOW 1.0 brighten midtones
  into sparser characters. Lower it if the portrait reads as a dark blob.
* --white-floor forces anything brighter than that luminance to a blank space.
  Raise it toward 0.9 if the background is still speckling. It is compared
  against the post-gamma value, so retune it whenever you change --gamma.
* --cols/--rows control resolution. Wider is more detail but a bigger SVG.
  Character cells are roughly 8x15, so ~100x52 lands near 800x780 px of art.
* The grid is resized without preserving aspect ratio. Crop the source photo to
  the art's aspect (cols*8 : rows*15, ~1.03:1 at defaults) or the face flattens.

Regenerating art/kymani-ascii.svg
---------------------------------
source-photo.jpg is gitignored, so you need to supply it: a ~1.03:1 crop framed
so the head fills about 72% of the frame height, which keeps the face legible at
the 400px the README renders it at. art/kymani-ascii.svg is committed, so the
README renders fine without the photo present. These are the exact flags behind
the committed artifact:

    python scripts/make_ascii_portrait.py source-photo.jpg art/kymani-ascii.svg \
        --name "Kymani Jarrett" --handle kymani \
        --gamma 0.85 --white-floor 0.90 --cutout

--cutout is required rather than optional here. The source is an outdoor shot
with a water tower, buildings and a treeline behind the subject, and parts of
that backdrop sit at the same luminance as the face, so no --white-floor value
can separate them. Compositing onto pure white is what keeps it out of the art.

The light polo shirt lands around 0.60-0.82 luminance against a 0.07-0.41 face,
so it renders as sparse characters: a faint torso grounding a dense head. Do not
reach for --contrast to sharpen the features. The face is evenly lit and sits in
a narrow band, so raising contrast collapses the whole head into a solid block
long before it separates anything.
"""

from __future__ import annotations

import argparse
import html
import os
import sys

from PIL import Image, ImageEnhance, ImageOps

# Sparse (bright) -> dense (dark). The leading space blanks the background.
RAMP = " .`:-=+*csto#%@"

# GitHub dark-mode palette so the card sits naturally in a profile README.
BG_TOP = "#111722"
BG_BOTTOM = "#0D1117"
FRAME = "#30363D"
MUTED = "#7D8590"
INK = "#C9D1D9"
ACCENT = "#22D3EE"

CELL_W = 8
CELL_H = 15
PAD = 20
TITLEBAR_H = 30
STATUSBAR_H = 32

ROW_DUR = 0.11      # seconds for one row to wipe in
STAGGER = 0.11      # delay between consecutive rows; == ROW_DUR reads as one cursor


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Photo -> animated ASCII-art SVG.")
    p.add_argument("source", help="input photo (jpg/png)")
    p.add_argument("output", nargs="?", default="ascii-portrait.svg", help="output .svg path")
    p.add_argument("--name", default="", help="name shown in the status bar")
    p.add_argument("--handle", default="you", help="prompt handle, e.g. kymani")
    p.add_argument("--cols", type=int, default=100)
    p.add_argument("--rows", type=int, default=52)
    p.add_argument("--gamma", type=float, default=1.18)
    p.add_argument("--contrast", type=float, default=1.15)
    p.add_argument("--brightness", type=float, default=1.0)
    p.add_argument("--white-floor", type=float, default=0.82)
    p.add_argument("--cutout", action="store_true", help="remove background with rembg")
    p.add_argument("--static", action="store_true", help="emit the frozen frame, no animation")
    return p


def load_grayscale(path: str, cutout: bool) -> Image.Image:
    """Load the photo as an L-mode image, optionally isolating the subject on white."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)

    if cutout:
        try:
            from rembg import remove  # type: ignore
        except ImportError:
            sys.exit(
                "--cutout needs rembg. Install it with:\n"
                '    pip install "rembg[cpu]" onnxruntime'
            )
        cut = remove(img.convert("RGBA"))
        # Composite the subject onto pure white so the background maps to spaces.
        white = Image.new("RGBA", cut.size, (255, 255, 255, 255))
        img = Image.alpha_composite(white, cut)

    return img.convert("L")


def sample_grid(img: Image.Image, args: argparse.Namespace) -> list[str]:
    """Downsample to a cols x rows character grid using a luminance ramp."""
    img = ImageEnhance.Brightness(img).enhance(args.brightness)
    img = ImageEnhance.Contrast(img).enhance(args.contrast)
    img = img.resize((args.cols, args.rows), Image.LANCZOS)
    px = img.load()

    last = len(RAMP) - 1
    lines: list[str] = []
    for y in range(args.rows):
        chars = []
        for x in range(args.cols):
            lum = (px[x, y] / 255.0) ** args.gamma
            if lum >= args.white_floor:
                chars.append(" ")
                continue
            idx = round((1.0 - lum) * last)
            chars.append(RAMP[min(max(idx, 0), last)])
        lines.append("".join(chars))
    return lines


def render_svg(lines: list[str], args: argparse.Namespace) -> str:
    art_w = args.cols * CELL_W
    art_h = args.rows * CELL_H
    canvas_w = art_w + PAD * 2
    canvas_h = TITLEBAR_H + art_h + STATUSBAR_H + PAD
    art_top = TITLEBAR_H + PAD * 0.35
    font_size = CELL_H * 0.86

    out: list[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w}" height="{canvas_h}" '
        f'viewBox="0 0 {canvas_w} {canvas_h}" role="img" '
        f'aria-label="ASCII portrait of {html.escape(args.name or args.handle)}" '
        f'font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">'
    )

    # Window chrome
    out.append(
        '<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{BG_TOP}"/>'
        f'<stop offset="1" stop-color="{BG_BOTTOM}"/></linearGradient></defs>'
    )
    out.append(f'<rect width="{canvas_w}" height="{canvas_h}" rx="12" fill="url(#bg)"/>')
    out.append(
        f'<rect x="0.5" y="0.5" width="{canvas_w - 1}" height="{canvas_h - 1}" rx="12" '
        f'fill="none" stroke="{FRAME}" stroke-width="1"/>'
    )
    out.append(f'<line x1="0" y1="{TITLEBAR_H}" x2="{canvas_w}" y2="{TITLEBAR_H}" stroke="{FRAME}"/>')
    for i, dot in enumerate(("#FF5F56", "#FFBD2E", "#27C93F")):
        out.append(f'<circle cx="{PAD + i * 16}" cy="{TITLEBAR_H / 2}" r="5" fill="{dot}"/>')
    out.append(
        f'<text x="{canvas_w / 2}" y="{TITLEBAR_H / 2 + 4}" fill="{MUTED}" font-size="12" '
        f'text-anchor="middle">{html.escape(args.handle)}@github: ~ $ ./portrait.sh</text>'
    )

    # One <text> per row. textLength + lengthAdjust="spacing" guarantees the grid
    # stays aligned even if the viewer falls back to a different monospace font.
    for ry, line in enumerate(lines):
        row_y = art_top + ry * CELL_H
        baseline = row_y + CELL_H * 0.74
        delay = ry * STAGGER
        text = (
            f'<text xml:space="preserve" x="{PAD}" y="{baseline:.1f}" fill="{INK}" '
            f'font-size="{font_size:.1f}" textLength="{art_w}" lengthAdjust="spacing">'
            f'{html.escape(line)}</text>'
        )

        if args.static:
            out.append(text)
            continue

        out.append(
            f'<clipPath id="w{ry}"><rect x="{PAD}" y="{row_y:.1f}" height="{CELL_H}" width="0">'
            f'<animate attributeName="width" from="0" to="{art_w}" begin="{delay:.2f}s" '
            f'dur="{ROW_DUR:.2f}s" fill="freeze"/></rect></clipPath>'
        )
        out.append(f'<g clip-path="url(#w{ry})">{text}</g>')
        out.append(
            f'<rect y="{row_y + 1:.1f}" width="{CELL_W}" height="{CELL_H - 2}" '
            f'fill="{ACCENT}" opacity="0">'
            f'<animate attributeName="x" from="{PAD}" to="{PAD + art_w}" '
            f'begin="{delay:.2f}s" dur="{ROW_DUR:.2f}s" fill="freeze"/>'
            f'<set attributeName="opacity" to="0.9" begin="{delay:.2f}s"/>'
            f'<set attributeName="opacity" to="0" begin="{delay + ROW_DUR:.2f}s"/></rect>'
        )

    # Status bar with a blinking cursor
    rule_y = TITLEBAR_H + art_h + PAD * 0.35
    text_y = rule_y + 20
    label = f"{args.handle}@github:~$ whoami "
    out.append(f'<line x1="0" y1="{rule_y:.1f}" x2="{canvas_w}" y2="{rule_y:.1f}" stroke="{FRAME}"/>')
    out.append(
        f'<text x="{PAD}" y="{text_y:.1f}" fill="{MUTED}" font-size="13">'
        f'{html.escape(label)}<tspan fill="{ACCENT}">{html.escape(args.name)}</tspan></text>'
    )
    cursor_x = PAD + int((len(label) + len(args.name) + 1) * 7.2)
    out.append(
        f'<rect x="{cursor_x}" y="{text_y - 11:.1f}" width="8" height="14" fill="{ACCENT}">'
        f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.51;1" '
        f'dur="1s" repeatCount="indefinite"/></rect>'
    )

    out.append("</svg>")
    return "".join(out)


def main() -> None:
    args = build_parser().parse_args()
    img = load_grayscale(args.source, args.cutout)
    lines = sample_grid(img, args)
    svg = render_svg(lines, args)

    parent = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(parent, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(svg)

    print(f"wrote {args.output} ({len(svg):,} bytes, {args.cols}x{args.rows} chars)")


if __name__ == "__main__":
    main()
