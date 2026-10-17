"""Report the records near a changed record that may be the same dive site.

    python scripts/dedup.py                    # every pair in the pool: the baseline
    python scripts/dedup.py --base origin/main # the records a pull request changes, as the check runs it

Advisory, always: it exits zero whatever it finds, and it never merges anything. Two records
the rules flag are often two real sites - a lake's sunken platform and its sunken boat, a wreck
and its bow section - and two records it misses can be one. A merge is a maintainer's pull
request.

Three rules, each a floor calibrated on the catalogue the pool was seeded from, and meant to be
tuned on what real contributions show:

- **Within 20 m, whatever the names.** Further out, most close pairs are differently named
  features of one dive lake or one reef, and flagging them would bury the real hits.
- **Within 200 m, when the names are similar**: identical once normalised, one containing the
  other (three characters or more), half the words of the shorter one shared (three letters or
  more, outside a small stop-list), or a `difflib` ratio of 0.8. Every name a record carries - `name`,
  `other_names`, an English name - is compared with every name of the other.
- **Within 5 km, when a name is identical once normalised** and is not a generic one - `Shark
  Point` exists in many countries, and seven `Diving Spot` placeholders sit in one archipelago.
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import os
import re
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pool import REPOSITORY, ROOT, Record, changed_files, site_files, summarise

NEAR_METRES = 20.0
SIMILAR_METRES = 200.0
SAME_NAME_METRES = 5000.0

_MIN_SUBSTRING = 3
_MIN_TOKEN = 3
_RATIO = 0.8

# Words two names can share without being similar. Small on purpose, and only words of
# three letters or more, since nothing shorter is compared.
STOP_WORDS = frozenset({"the", "and", "und", "von", "der", "die", "das", "den", "del", "des", "les", "van", "het"})

# A name that is not a name: two records sharing one say nothing about being one site. A
# floor a maintainer grows as contributions show more; the seven `Diving Spot` placeholders
# of Kepulauan Seribu are why it exists.
GENERIC_NAMES = frozenset(
    {
        "dive site", "dive spot", "diving site", "diving spot", "divespot", "snorkeling spot",
        "snorkelling spot", "house reef", "housereef", "hausriff", "coral garden",
        "coral gardens", "the wall", "wall", "cave", "platform", "plattform", "einstieg",
        "entry point", "terumbu karang",
    }
)  # fmt: skip

# What tells two siblings apart and nothing else: `Housereef West` and `Housereef East`,
# `instap 1` and `instap 2`. A similar pair differing only by these is flagged with a note.
_QUALIFIERS = frozenset(
    {
        "north", "south", "east", "west", "nord", "sud", "süd", "ost", "oost", "noord", "zuid",
        "norte", "sur", "este", "oeste", "n", "s", "e", "w", "ne", "nw", "se", "sw", "inner",
        "outer", "upper", "lower", "left", "right", "big", "small", "little", "great", "grand",
        "petit", "klein", "groot", "gross", "i", "ii", "iii", "iv", "v", "a", "b", "c", "d",
        "mini", "deep", "shallow", "new", "old",
    }
)  # fmt: skip

_SUMMARY_RECORDS = 50


def normalise(name: str) -> str:
    """NFKD, combining marks dropped, case-folded, every run of non-word characters a space.

    Not an ASCII strip: `[^a-z0-9]` empties every name with no Latin letter, and seventy-odd
    seed names would then all be "the same name".
    """
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(character for character in decomposed if not unicodedata.combining(character))
    return re.sub(r"\W+", " ", stripped.casefold()).strip()


def _tokens(normalised: str) -> set[str]:
    return {token for token in normalised.split() if len(token) >= _MIN_TOKEN and token not in STOP_WORDS}


def _names_similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    if len(shorter) >= _MIN_SUBSTRING and shorter in longer:
        return True
    tokens_a, tokens_b = _tokens(a), _tokens(b)
    if tokens_a and tokens_b and 2 * len(tokens_a & tokens_b) >= min(len(tokens_a), len(tokens_b)):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= _RATIO


def _qualifier_siblings(a: str, b: str) -> bool:
    difference = set(a.split()) ^ set(b.split())
    return bool(difference) and all(token in _QUALIFIERS or token.isdigit() for token in difference)


def metres_between(a: Record, b: Record) -> float:
    """Haversine, on a sphere of the mean Earth radius."""
    phi_a, phi_b = math.radians(a.latitude), math.radians(b.latitude)
    d_phi = phi_b - phi_a
    d_lambda = math.radians(b.longitude - a.longitude)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
    return 2 * 6_371_008.8 * math.asin(min(1.0, math.sqrt(h)))


@dataclass(frozen=True, slots=True)
class Flag:
    record: Record
    neighbour: Record
    metres: float
    rule: str
    note: str | None = None


def _names(record: Record) -> list[str]:
    return [name for name in dict.fromkeys(normalise(alias) for alias in record.aliases) if name]


def judge(a: Record, b: Record, metres: float) -> Flag | None:
    """The first rule a pair meets, or None."""
    if metres <= NEAR_METRES:
        return Flag(a, b, metres, "within 20 m")
    names_a, names_b = _names(a), _names(b)
    if metres <= SIMILAR_METRES:
        similar = [(x, y) for x in names_a for y in names_b if _names_similar(x, y)]
        if similar:
            siblings = all(_qualifier_siblings(x, y) for x, y in similar)
            note = "the names differ only by a qualifier, which usually means two sites" if siblings else None
            return Flag(a, b, metres, "similar name within 200 m", note)
    if metres <= SAME_NAME_METRES:
        shared = set(names_a) & set(names_b)
        if any(name not in GENERIC_NAMES for name in shared):
            return Flag(a, b, metres, "same name within 5 km")
    return None


def _close_pairs(records: list[Record], focus: set[str] | None, limit: float) -> Iterable[tuple[Record, Record, float]]:
    """Every pair within `limit` metres with at least one record in `focus` (every pair when None).

    A sweep over latitude: a degree of latitude is never shorter than ~110.5 km, so a pair
    further apart in latitude than `limit` allows cannot be within it.
    """
    window = limit / 110_500
    ordered = sorted(records, key=lambda record: record.latitude)
    for index, a in enumerate(ordered):
        for b in ordered[index + 1 :]:
            if b.latitude - a.latitude > window:
                break
            if focus is not None and a.path not in focus and b.path not in focus:
                continue
            metres = metres_between(a, b)
            if metres <= limit:
                yield a, b, metres


def _same_name_pairs(records: list[Record], focus: set[str] | None) -> Iterable[tuple[Record, Record, float]]:
    by_name: dict[str, list[Record]] = defaultdict(list)
    for record in records:
        for name in _names(record):
            by_name[name].append(record)
    seen: set[tuple[str, str]] = set()
    for group in by_name.values():
        for index, a in enumerate(group):
            for b in group[index + 1 :]:
                if a.path == b.path or (focus is not None and a.path not in focus and b.path not in focus):
                    continue
                key = (a.path, b.path) if a.path < b.path else (b.path, a.path)
                if key in seen:
                    continue
                seen.add(key)
                metres = metres_between(a, b)
                if metres <= SAME_NAME_METRES:
                    yield a, b, metres


def flags(records: list[Record], focus: set[str] | None = None) -> list[Flag]:
    """Every flagged pair, each once, oriented so that `record` is in `focus` where one is."""
    found: dict[tuple[str, str], Flag] = {}
    for a, b, metres in [*_close_pairs(records, focus, SIMILAR_METRES), *_same_name_pairs(records, focus)]:
        if focus is not None and a.path not in focus:
            a, b = b, a
        key = (a.path, b.path) if a.path < b.path else (b.path, a.path)
        if key in found:
            continue
        flag = judge(a, b, metres)
        if flag is not None:
            found[key] = flag
    return sorted(found.values(), key=lambda flag: (flag.record.path, flag.metres))


def _file_url(path: str) -> str:
    """The record's file on GitHub, which renders as a map - on the fork's branch for a pull request."""
    repository = os.environ.get("DEDUP_HEAD_REPOSITORY") or REPOSITORY
    ref = os.environ.get("DEDUP_HEAD_SHA") or "main"
    return f"https://github.com/{repository}/blob/{ref}/{path}"


def _map_url(record: Record) -> str:
    lat, lon = f"{record.latitude:.6f}", f"{record.longitude:.6f}"
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}"


def report(records: list[Record], focus: set[str]) -> str:
    """The pull request's view: per changed record, its flagged neighbours and two links."""
    found = flags(records, focus)
    by_record: dict[str, list[Flag]] = defaultdict(list)
    for flag in found:
        by_record[flag.record.path].append(flag)
        # Two changed records near each other are each the other's neighbour.
        if flag.neighbour.path in focus:
            by_record[flag.neighbour.path].append(Flag(flag.neighbour, flag.record, flag.metres, flag.rule, flag.note))
    lines = ["## Possible duplicates", ""]
    checked = sorted(path for path in focus if any(record.path == path for record in records))
    if not checked:
        return "\n".join([*lines, "No record changed."]) + "\n"
    lines.append(
        f"{len(checked)} changed record(s), {len(by_record)} with a neighbour worth a look. "
        "Advisory: nothing here fails the check."
    )
    if len(checked) > _SUMMARY_RECORDS:
        counts: dict[str, int] = defaultdict(int)
        for flag in found:
            counts[flag.rule] += 1
        lines += ["", "Too many changed records to list one by one; the pairs by rule:", ""]
        lines += [f"- {rule}: {count}" for rule, count in sorted(counts.items())]
        lines += ["", "Run `python scripts/dedup.py --base <the base branch>` locally for every pair."]
        return "\n".join(lines) + "\n"
    by_path = {record.path: record for record in records}
    for path in checked:
        record = by_path[path]
        lines += [
            "",
            f"### {record.name}",
            "",
            f"`{path}` - [the file]({_file_url(path)}) - [on OpenStreetMap]({_map_url(record)})",
            "",
        ]
        if not by_record[path]:
            lines.append("No existing record nearby by any rule.")
            continue
        lines += ["| Neighbour | Distance | Source | Rule | Path |", "| --- | --- | --- | --- | --- |"]
        for flag in by_record[path]:
            rule = f"{flag.rule}; {flag.note}" if flag.note else flag.rule
            neighbour = flag.neighbour
            lines.append(
                f"| {_cell(neighbour.name)} | {flag.metres:,.0f} m | {neighbour.source} | {rule} | "
                f"[`{neighbour.path}`]({_file_url(neighbour.path)}) |"
            )
    return "\n".join(lines) + "\n"


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def baseline(records: list[Record]) -> str:
    """Every pair in the pool, counted by rule: the number a change to the rules moves."""
    found = flags(records)
    counts: dict[str, int] = defaultdict(int)
    flagged: set[str] = set()
    for flag in found:
        counts[flag.rule] += 1
        flagged.update((flag.record.path, flag.neighbour.path))
    lines = [f"{len(records)} records, {len(found)} flagged pairs touching {len(flagged)} records:"]
    lines += [f"  {rule}: {count}" for rule, count in sorted(counts.items())]
    return "\n".join(lines) + "\n"


def load_records() -> list[Record]:
    records = []
    for path in site_files():
        try:
            feature: Any = json.loads((ROOT / path).read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if (record := summarise(path, feature)) is not None:
            records.append(record)
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report possible duplicates among the pool's records.")
    parser.add_argument("--base", help="report on the records changed between this ref and HEAD")
    args = parser.parse_args(argv)

    records = load_records()
    if args.base is None:
        print(baseline(records), end="")
        return 0

    changed = changed_files(args.base)
    focus = {path for path, status in changed.items() if path.startswith("sites/") and status != "D"}
    text = report(records, focus)
    print(text, end="")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for flag in flags(records, focus)[:10]:
            print(
                f"::notice file={flag.record.path}::{flag.neighbour.name} is {flag.metres:,.0f} m away "
                f"({flag.rule}): {flag.neighbour.path}"
            )
    if step_summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write("\n" + text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
