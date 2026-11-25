#!/usr/bin/env python
"""Prints what the catalogue actually contains, counted from its own files.

    python tools/kara/totals.py

Reads `index.json` for the songs and `songs/times.csv` for the wall clock, so the
numbers are the published ones and the measured ones, not a retyped summary.
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    index = json.load(open(os.path.join(ROOT, "index.json")))
    songs = index["songs"]

    packed = sum(song["pack"]["bytes"] for song in songs)
    by_licence = {}
    for song in songs:
        kind = song["licence"]["type"]
        by_licence[kind] = by_licence.get(kind, 0) + 1

    durations = sorted(song["durationMs"] for song in songs)
    median_ms = durations[len(durations) // 2]

    times_path = os.path.join(ROOT, "songs", "times.csv")
    wall = 0
    measured = 0
    if os.path.exists(times_path):
        for row in list(csv.DictReader(open(times_path))):
            try:
                wall += int(row.get("total_s") or 0)
                measured += 1
            except ValueError:
                continue

    print(f"songs            {len(songs)}")
    print(f"packed bytes     {packed:,} ({packed / 1e6:.1f} MB)")
    print(f"median length    {median_ms / 1000:.0f}s")
    print(f"licences         " + ", ".join(f"{k} {v}" for k, v in sorted(by_licence.items())))
    print(f"wall clock       {wall:,}s ({wall / 3600:.1f} h) over {measured} measured runs")
    if measured:
        print(f"per song         {wall / measured:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
