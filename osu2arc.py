#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path


def parse_osu(path):
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    section = ""
    keys = 4
    timings = []
    objects = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if not line or line.startswith("//"):
            continue
        if section == "Difficulty":
            if line.startswith("CircleSize:"):
                keys = int(float(line.split(":", 1)[1]))
        elif section == "TimingPoints":
            parts = line.split(",")
            if len(parts) < 7 or parts[6] != "1":
                continue
            beat = float(parts[1])
            if beat > 0:
                timings.append((int(round(float(parts[0]))), 60000.0 / beat))
        elif section == "HitObjects":
            parts = line.split(",")
            if len(parts) < 5:
                continue
            x = int(float(parts[0]))
            time = int(float(parts[2]))
            kind = int(parts[3])
            if kind & 128:
                end = int(float(parts[5].split(":")[0])) if len(parts) > 5 else time
                objects.append((time, max(end, time), x, True))
            elif kind & 1:
                objects.append((time, time, x, False))
    if not timings:
        timings = [(0, 120.0)]
    timings.sort()
    objects.sort(key=lambda o: (o[0], o[2]))
    return keys, timings, objects


def convert(path, out, keys_expected=4):
    keys, timings, objects = parse_osu(path)
    if keys != keys_expected:
        raise SystemExit(f"{path}: {keys}K, only {keys_expected}K mania is supported")
    lane_width = 512.0 / keys
    lines = ["AudioOffset:0", "-"]
    for offset, bpm in timings:
        lines.append(f"timing({offset},{bpm:.2f},4.00);")
    seen = set()
    taps = 0
    holds = 0
    for start, end, x, hold in objects:
        column = min(keys - 1, max(0, int(x / lane_width)))
        lane = column + 1
        if (start, lane) in seen:
            continue
        seen.add((start, lane))
        if hold and end - start >= 10:
            lines.append(f"hold({start},{end},{lane});")
            holds += 1
        else:
            lines.append(f"({start},{lane});")
            taps += 1
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return taps, holds


def main():
    parser = argparse.ArgumentParser(
        prog="osu2arc", description="osu!mania 4K to Arcaea aff converter")
    parser.add_argument("input", nargs="+", help=".osu file(s)")
    parser.add_argument("-o", "--output", help="output .aff path, or a directory for several inputs")
    parser.add_argument("--keys", type=int, default=4, help="expected mania key count (default 4)")
    args = parser.parse_args()

    inputs = [Path(p) for p in args.input]
    out_dir = None
    if args.output:
        candidate = Path(args.output)
        if len(inputs) > 1 or candidate.is_dir() or candidate.suffix == "":
            out_dir = candidate
            out_dir.mkdir(parents=True, exist_ok=True)

    for src in inputs:
        if out_dir:
            dst = out_dir / (src.stem + ".aff")
        elif args.output:
            dst = Path(args.output)
        else:
            dst = src.with_suffix(".aff")
        taps, holds = convert(src, dst, args.keys)
        print(f"{src.name}: {taps} taps, {holds} holds -> {dst}")


if __name__ == "__main__":
    sys.exit(main())
