#!/usr/bin/env python3
import argparse
import math
import sys
import zipfile
from pathlib import Path


def parse_osu(text):
    section = ""
    info = {"format": 0, "keys": 4, "slider_multiplier": 1.4, "tick_rate": 1.0}
    timing = []
    objects = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if not line or line.startswith("//"):
            continue
        if section in ("General", "Difficulty", "Metadata"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key, value = key.strip(), value.strip()
            if section == "General" and key == "Mode":
                info["format"] = int(value)
            elif section == "Difficulty":
                if key == "CircleSize":
                    info["keys"] = int(float(value))
                elif key == "SliderMultiplier":
                    info["slider_multiplier"] = float(value)
                elif key == "SliderTickRate":
                    info["tick_rate"] = float(value)
        elif section == "TimingPoints":
            parts = line.split(",")
            if len(parts) < 2:
                continue
            beat = float(parts[1])
            uninherited = len(parts) > 6 and parts[6] == "1"
            timing.append((float(parts[0]), beat, uninherited))
        elif section == "HitObjects":
            parts = line.split(",")
            if len(parts) >= 5:
                objects.append(parts)
    timing.sort()
    objects.sort(key=lambda parts: (float(parts[2]), float(parts[0])))
    return info, timing, objects


def mania_aff(info, timing, objects, keys_expected=4):
    keys = info["keys"]
    if keys != keys_expected:
        raise SystemExit(f"unsupported: {keys}K mania (only {keys_expected}K)")
    lines = ["AudioOffset:0", "-"]
    for time, beat, uninherited in timing:
        if uninherited and beat > 0:
            lines.append(f"timing({int(round(time))},{60000.0 / beat:.2f},4.00);")
    if len(lines) == 2:
        lines.append("timing(0,120.00,4.00);")
    lane_width = 512.0 / keys
    seen = set()
    taps = holds = 0
    for parts in objects:
        x = float(parts[0])
        time = int(float(parts[2]))
        kind = int(parts[3])
        column = min(keys - 1, max(0, int(x / lane_width)))
        lane = column + 1
        if kind & 128:
            end = int(float(parts[5].split(":")[0])) if len(parts) > 5 else time
            end = max(end, time)
            if end - time >= 10:
                if (time, lane) in seen:
                    continue
                seen.add((time, lane))
                lines.append(f"hold({time},{end},{lane});")
                holds += 1
                continue
        elif not kind & 1:
            continue
        if (time, lane) in seen:
            continue
        seen.add((time, lane))
        lines.append(f"({time},{lane});")
        taps += 1
    return lines, {"taps": taps, "holds": holds}


def timing_state(timing, time):
    beat = 1000.0
    sv = 1.0
    for point, value, uninherited in timing:
        if point > time:
            break
        if uninherited:
            beat = value
        else:
            sv = -100.0 / value if value < 0 else 1.0
    return beat, max(sv, 0.01)


def bezier(points, samples=24):
    if len(points) < 2:
        return points
    out = []
    for i in range(samples + 1):
        t = i / samples
        layer = list(points)
        while len(layer) > 1:
            layer = [((1 - t) * a[0] + t * b[0], (1 - t) * a[1] + t * b[1])
                     for a, b in zip(layer, layer[1:])]
        out.append(layer[0])
    return out


def catmull(points, samples=16):
    if len(points) < 3:
        return points
    pts = [points[0]] + points + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for j in range(samples):
            t = j / samples
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(points[-1])
    return out


def slider_path(start, curve_type, points):
    pts = [start] + points
    if curve_type == "L" or len(pts) < 3:
        return pts
    if curve_type == "B":
        sections, current = [], [pts[0]]
        for point in pts[1:]:
            if current and point == current[-1]:
                sections.append(current)
                current = [point]
            else:
                current.append(point)
        sections.append(current)
        out = []
        for section in sections:
            sampled = bezier(section)
            out.extend(sampled if not out else sampled[1:])
        return out
    if curve_type == "C":
        return catmull(pts)
    if curve_type == "P":
        if len(pts) == 3:
            (x1, y1), (x2, y2), (x3, y3) = pts
            d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
            if abs(d) > 1e-6:
                ux = ((x1 ** 2 + y1 ** 2) * (y2 - y3) + (x2 ** 2 + y2 ** 2) * (y3 - y1)
                      + (x3 ** 2 + y3 ** 2) * (y1 - y2)) / d
                uy = ((x1 ** 2 + y1 ** 2) * (x3 - x2) + (x2 ** 2 + y2 ** 2) * (x1 - x3)
                      + (x3 ** 2 + y3 ** 2) * (x2 - x1)) / d
                radius = math.hypot(x1 - ux, y1 - uy)
                a1 = math.atan2(y1 - uy, x1 - ux)
                a2 = math.atan2(y2 - uy, x2 - ux)
                a3 = math.atan2(y3 - uy, x3 - ux)
                delta = (a3 - a1) % (2 * math.pi)
                if (a2 - a1) % (2 * math.pi) > delta:
                    delta -= 2 * math.pi
                steps = max(8, int(abs(delta) / 0.1))
                return [(ux + radius * math.cos(a1 + delta * i / steps),
                         uy + radius * math.sin(a1 + delta * i / steps))
                        for i in range(steps + 1)]
        return pts
    return pts


def path_length(points):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def point_at(points, distance):
    if distance <= 0:
        return points[0]
    walked = 0.0
    for a, b in zip(points, points[1:]):
        segment = math.hypot(b[0] - a[0], b[1] - a[1])
        if walked + segment >= distance:
            ratio = (distance - walked) / segment if segment else 0.0
            return (a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio)
        walked += segment
    return points[-1]


def to_x(px):
    return min(1.0, max(0.0, px / 512.0))


def to_y(py):
    return max(0.0, (1.0 - py / 384.0) * 1.5)


def sky_aff(info, timing, objects):
    lines = ["AudioOffset:0", "-"]
    red = [(time, beat) for time, beat, uninherited in timing if uninherited and beat > 0]
    for time, beat in red or [(0.0, 500.0)]:
        lines.append(f"timing({int(round(time))},{60000.0 / beat:.2f},4.00);")
    events = []
    slider_mult = info["slider_multiplier"]
    tick_rate = max(info["tick_rate"], 0.1)
    taps = arcs = spinners = 0
    for parts in objects:
        x = float(parts[0])
        y = float(parts[1])
        time = float(parts[2])
        kind = int(parts[3])
        if kind & 8 and not kind & (1 | 2):
            spinners += 1
            continue
        if kind & 2 and len(parts) > 7:
            curve_type, _, rest = parts[5].partition("|")
            points = []
            for item in rest.split("|"):
                if ":" in item:
                    px, py = item.split(":", 1)
                    points.append((float(px), float(py)))
            repeats = max(1, int(parts[6]))
            length = float(parts[7])
            beat, sv = timing_state(timing, time)
            per_repeat = length * beat / (100.0 * slider_mult * sv)
            total = per_repeat * repeats
            pts = slider_path((x, y), curve_type[:1], points)
            plen = path_length(pts) or 1.0
            steps = min(8, max(1, int(math.ceil(total / 400.0))))
            for i in range(steps):
                phase1 = (i / steps) * repeats
                phase2 = ((i + 1) / steps) * repeats
                frac1 = (phase1 % 1) if (phase1 % 2) < 1 else 1 - (phase1 % 1)
                frac2 = (phase2 % 1) if (phase2 % 2) < 1 else 1 - (phase2 % 1)
                p1 = point_at(pts, plen * frac1)
                p2 = point_at(pts, plen * frac2)
                start = int(round(time + total * i / steps))
                end = max(start + 1, int(round(time + total * (i + 1) / steps)))
                events.append((start, f"arc({start},{end},{to_x(p1[0]):.2f},{to_x(p2[0]):.2f},s,{to_y(p1[1]):.2f},{to_y(p2[1]):.2f},0,none,false);"))
                arcs += 1
            continue
        if kind & 1:
            at = int(round(time))
            pos = f"{to_x(x):.2f}"
            height = f"{to_y(y):.2f}"
            events.append((at, f"arc({at},{at + 1},{pos},{pos},s,{height},{height},1,none,true)[arctap({at})];"))
            taps += 1
    events.sort(key=lambda item: item[0])
    lines.extend(text for _, text in events)
    return lines, {"sky_taps": taps, "arcs": arcs, "spinners_skipped": spinners}


def convert_text(text, name, out, mode="auto", keys_expected=4):
    info, timing, objects = parse_osu(text)
    chosen = info["format"] if mode == "auto" else (3 if mode == "mania" else 0)
    if chosen == 3:
        lines, stats = mania_aff(info, timing, objects, keys_expected)
    elif chosen == 0:
        lines, stats = sky_aff(info, timing, objects)
    else:
        raise SystemExit(f"{name}: unsupported mode {info['format']}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stats, chosen


def describe(stats, mode):
    if mode == 3:
        return f"{stats['taps']} taps, {stats['holds']} holds"
    return (f"{stats['sky_taps']} sky taps, {stats['arcs']} arcs, "
            f"{stats['spinners_skipped']} spinners skipped")


def read_osu(path):
    return path.read_text(encoding="utf-8-sig", errors="replace")


def convert_osz(src, out_dir, mode, keys):
    results = []
    with zipfile.ZipFile(src) as archive:
        members = [m for m in archive.namelist()
                   if m.lower().endswith(".osu") and not m.startswith("__MACOSX/")]
        if not members:
            raise SystemExit(f"{src.name}: no .osu inside")
        for member in sorted(members):
            text = archive.read(member).decode("utf-8-sig", errors="replace")
            dst = out_dir / (Path(member).stem + ".aff")
            stats, chosen = convert_text(text, member, dst, mode, keys)
            results.append((member, dst, stats, chosen))
    return results


def main():
    parser = argparse.ArgumentParser(
        prog="osu2arc", description="osu!mania 4K / osu!standard to Arcaea aff converter")
    parser.add_argument("input", nargs="+", help=".osu or .osz file(s)")
    parser.add_argument("-o", "--output", help="output .aff path, or a directory for several inputs")
    parser.add_argument("--mode", choices=["auto", "mania", "sky"], default="auto",
                        help="conversion mode (default: auto by chart Mode)")
    parser.add_argument("--keys", type=int, default=4, help="expected mania key count (default 4)")
    args = parser.parse_args()

    inputs = [Path(p) for p in args.input]
    forced = Path(args.output) if args.output else None
    single_file_out = bool(forced and forced.suffix and len(inputs) == 1
                           and inputs[0].suffix.lower() != ".osz")

    for src in inputs:
        if src.suffix.lower() == ".osz":
            out_dir = forced if forced else src.parent
            for member, dst, stats, chosen in convert_osz(src, out_dir, args.mode, args.keys):
                print(f"{src.name}:{member}: {describe(stats, chosen)} -> {dst}")
            continue
        if single_file_out:
            dst = forced
        elif forced:
            dst = forced / (src.stem + ".aff")
        else:
            dst = src.with_suffix(".aff")
        stats, chosen = convert_text(read_osu(src), src.name, dst, args.mode, args.keys)
        print(f"{src.name}: {describe(stats, chosen)} -> {dst}")


if __name__ == "__main__":
    sys.exit(main())
