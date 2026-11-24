#!/usr/bin/env python
"""Reads songs/queue.csv and prints one line per row, fields joined by \\x1f.

The queue is CSV and a title may hold a comma, so `IFS=, read` is not enough:
it would split that row into nine fields. This keeps the columns aligned, and
`batch.sh` uses a unit separator that no title contains.
"""
import csv
import sys

COLUMNS = 8

with open(sys.argv[1], newline="") as handle:
    reader = csv.reader(handle)
    next(reader, None)
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        row = [cell.strip() for cell in row] + [""] * COLUMNS
        print("\x1f".join(row[:COLUMNS]))
