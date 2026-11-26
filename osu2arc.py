#!/usr/bin/env python3
import argparse
import sys
import zipfile
from pathlib import Path


def parse_osu(text):
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


def convert_text(text, name, out, keys_expected=4):
    keys, timings, objects = parse_osu(text)
    if keys != keys_expected:
        raise SystemExit(f"{name}: {keys}K, only {keys_expected}K mania is supported")
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
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return taps, holds


def read_osu(path):
    return path.read_text(encoding="utf-8-sig", errors="replace")


def convert_osu(src, dst, keys):
    return convert_text(read_osu(src), src.name, dst, keys)


def convert_osz(src, out_dir, keys):
    results = []
    with zipfile.ZipFile(src) as archive:
        members = [m for m in archive.namelist()
                   if m.lower().endswith(".osu") and not m.startswith("__MACOSX/")]
        if not members:
            raise SystemExit(f"{src.name}: no .osu inside")
        for member in sorted(members):
            text = archive.read(member).decode("utf-8-sig", errors="replace")
            dst = out_dir / (Path(member).stem + ".aff")
            taps, holds = convert_text(text, member, dst, keys)
            results.append((member, dst, taps, holds))
    return results


def main():
    parser = argparse.ArgumentParser(
        prog="osu2arc", description="osu!mania 4K to Arcaea aff converter")
    parser.add_argument("input", nargs="+", help=".osu or .osz file(s)")
    parser.add_argument("-o", "--output", help="output .aff path, or a directory for several inputs")
    parser.add_argument("--keys", type=int, default=4, help="expected mania key count (default 4)")
    args = parser.parse_args()

    inputs = [Path(p) for p in args.input]
    forced = Path(args.output) if args.output else None
    single_file_out = bool(forced and forced.suffix and len(inputs) == 1
                           and inputs[0].suffix.lower() != ".osz")

    for src in inputs:
        if src.suffix.lower() == ".osz":
            out_dir = forced if forced else src.parent
            for member, dst, taps, holds in convert_osz(src, out_dir, args.keys):
                print(f"{src.name}:{member}: {taps} taps, {holds} holds -> {dst}")
            continue
        if single_file_out:
            dst = forced
        elif forced:
            dst = forced / (src.stem + ".aff")
        else:
            dst = src.with_suffix(".aff")
        taps, holds = convert_osu(src, dst, args.keys)
        print(f"{src.name}: {taps} taps, {holds} holds -> {dst}")


if __name__ == "__main__":
    sys.exit(main())
