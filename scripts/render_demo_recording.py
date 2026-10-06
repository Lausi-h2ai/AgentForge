"""Render the captured offline event record as a labeled animated GIF."""

import argparse
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def font(size):
    for candidate in ("DejaVuSansMono.ttf", "C:/Windows/Fonts/consola.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "docs/evidence/offline-demo.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/evidence/offline-demo.gif")
    args = parser.parse_args()
    report = json.loads(args.input.read_text(encoding="utf-8"))
    if report["mode"] != "offline-scripted" or report["live_model_calls"] != 0:
        raise ValueError("This renderer is only for the labeled offline demo")
    frames = []
    for count in range(1, len(report["events"]) + 1):
        frame = Image.new("RGB", (1120, 600), "#101827")
        draw = ImageDraw.Draw(frame)
        draw.text((36, 24), "AgentForge", fill="#ffffff", font=font(30))
        draw.text(
            (36, 74), "OFFLINE SCRIPTED DEMO  |  0 model calls", fill="#fbbf24", font=font(20)
        )
        draw.line((36, 116, 1084, 116), fill="#334155", width=2)
        y = 140
        for i, event in enumerate(report["events"][:count], 1):
            for line in textwrap.wrap(f"{i}. {event}", width=82):
                draw.text((36, y), line, fill="#86efac" if i == count else "#cbd5e1", font=font(20))
                y += 30
            y += 16
        draw.text(
            (36, 552),
            "Real stages + tools + persisted state | Scripted agent responses",
            fill="#94a3b8",
            font=font(18),
        )
        frames.append(frame.convert("P", palette=Image.ADAPTIVE, colors=32))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        args.output,
        save_all=True,
        append_images=frames[1:],
        duration=[1600] * (len(frames) - 1) + [4000],
        loop=0,
        disposal=2,
    )
    # Static final frame helps visual inspection and non-animated previews.
    frames[-1].save(args.output.with_suffix(".png"))
    print(f"Rendered {len(frames)} captured events: {args.output}")


if __name__ == "__main__":
    main()
