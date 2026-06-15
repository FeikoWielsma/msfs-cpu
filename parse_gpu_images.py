#!/usr/bin/env python3
"""
Parse Tom's Hardware MSFS 2024 GPU benchmark screenshots into CSV.

Each image is a horizontal bar chart with two bars per GPU:
  - Light bar (outer): Average FPS (number shown at right end)
  - Dark bar (inner): 1% Low FPS (number shown inside bar)

Usage:
    python parse_gpu_images.py [--glob 'gpu/*_1440p*.png'] [--out out.csv]

Requires: anthropic, Pillow (pip install anthropic pillow)
"""

import argparse
import base64
import csv
import json
import re
import sys
from pathlib import Path

import anthropic

PROMPT = """This is a Tom's Hardware GPU benchmark chart for Flight Simulator 2024.
Extract all GPU benchmark data shown. Each GPU has two values:
- Average FPS: the number printed at the right end of the full (lighter) bar
- 1% Low FPS: the number printed inside the shorter dark portion of the bar

Return a JSON array, one object per GPU row, with these keys:
  "gpu": GPU name exactly as shown (e.g. "RTX 5070 Ti")
  "avg": Average FPS as a number
  "low1": 1% Low FPS as a number

Return ONLY the JSON array, no other text."""


def encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode()


def parse_filename(path: Path) -> tuple[str, str]:
    """Extract (resolution, date) from filename like '5070Ti_1440pUltra_March 4, 2025.png'."""
    stem = path.stem
    parts = stem.split("_")
    resolution = ""
    date_str = ""
    for p in parts:
        if "1440p" in p:
            resolution = "1440p"
        elif "1080p" in p:
            resolution = "1080p"
        elif "4K" in p or "2160p" in p:
            resolution = "4K"
    # Last part(s) are the date
    # e.g. "March 4, 2025" or "September 26, 2025"
    date_parts = []
    for p in parts:
        if re.search(r'\d{4}', p):
            date_parts.append(p)
        elif date_parts or re.match(r'[A-Z][a-z]+', p) and len(p) > 4:
            date_parts.append(p)
    date_raw = " ".join(date_parts).strip(" ,")
    # Try to parse date
    from datetime import datetime
    for fmt in ("%B %d, %Y", "%B %d %Y", "%B %Y"):
        try:
            date_str = datetime.strptime(date_raw, fmt).strftime("%Y-%m-%d")
            break
        except ValueError:
            continue
    if not date_str:
        date_str = date_raw
    return resolution, date_str


def extract_preset(path: Path) -> str:
    stem = path.stem
    if "Ultra" in stem:
        return "Ultra"
    if "High" in stem:
        return "High"
    if "Medium" in stem:
        return "Medium"
    return ""


def parse_image(client: anthropic.Anthropic, path: Path) -> list[dict]:
    image_data = encode_image(path)
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    )
    text = response.content[0].text.strip()
    # Strip markdown fences if present
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def main():
    parser = argparse.ArgumentParser(description="Parse GPU benchmark images to CSV")
    parser.add_argument("--glob", default="gpu/*_1440p*.png", help="Glob for image files")
    parser.add_argument("--out", default="msfs24_gpu_data.csv", help="Output CSV path")
    args = parser.parse_args()

    images = sorted(Path(".").glob(args.glob))
    if not images:
        print(f"No images found matching: {args.glob}", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic()

    fieldnames = ["GPU", "Resolution", "Preset", "Avg", "P1", "Date", "SourceImage"]
    rows = []

    for img_path in images:
        resolution, date_str = parse_filename(img_path)
        preset = extract_preset(img_path)
        print(f"Parsing {img_path.name} ({resolution} {preset}, {date_str})...")
        try:
            entries = parse_image(client, img_path)
            for e in entries:
                rows.append({
                    "GPU": e["gpu"],
                    "Resolution": resolution,
                    "Preset": preset,
                    "Avg": e["avg"],
                    "P1": e["low1"],
                    "Date": date_str,
                    "SourceImage": img_path.name,
                })
            print(f"  -> {len(entries)} GPUs extracted")
        except Exception as ex:
            print(f"  ERROR: {ex}", file=sys.stderr)

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
