#!/usr/bin/env python3
"""Summarize the signal-by-paper matrix.

Mark a paper's `sig:*` cell with `Y` only after verifying in the paper that it logged that signal.
Usage: python3 coverage.py [signal_paper_matrix.csv]
"""
import csv
import sys
from collections import Counter

path = sys.argv[1] if len(sys.argv) > 1 else "signal_paper_matrix.csv"
rows = list(csv.DictReader(open(path, newline="")))
sig_cols = [c for c in rows[0] if c.startswith("sig:")]

verified = [r for r in rows if r["verified_by"].strip()]
print(f"{len(rows)} papers, {len(verified)} verified (verified_by filled)\n")

print("Papers logging each current signal (verified rows only):")
for c in sig_cols:
    ys = [r["bib_key"] for r in verified if r[c].strip().upper() == "Y"]
    print(f"  {c[4:]:22s} {len(ys):3d}  {', '.join(ys[:4])}{' ...' if len(ys) > 4 else ''}")

unmarked = [r["bib_key"] for r in rows if not r["verified_by"].strip() and r["tier"] == "1"]
print(f"\nTier-1 papers still to verify: {len(unmarked)}")

new = Counter()
for r in verified:
    for s in r["proposed_new_signal"].split(";"):
        if s.strip():
            new[s.strip().lower()] += 1
if new:
    print("\nProposed new signals (count of papers suggesting each):")
    for s, n in new.most_common():
        print(f"  {n:3d}  {s}")
