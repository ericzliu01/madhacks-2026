# Literature signal matrix

`signal_paper_matrix.csv` has one row per paper (42 rows: Tier 1 and 2 picks from the four `.bib` exports, triaged **from titles only**, plus Amar 2005 and Brehmer & Munzner 2013, which are in no bib).

## How to fill it in
1. Read the paper (abstract plus methods section). Don't rely on an LLM summary: earlier Asta summaries had wrong links and generic categories.
2. For each `sig:*` column, write `Y` if the paper logged that signal, `N` if it clearly did not, and leave it blank if unclear.
3. Fill `other_signals_logged` (things we don't capture), `inferred_or_predicted`, `validated_against` (eye tracking, self-report, task success, expert labels), and `N_and_setting`.
4. Put anything we should add to the extension in `proposed_new_signal`, separated by `;`.
5. Put your initials in `verified_by`. Only verified rows count in the summary.

## Summarize
```bash
python3 coverage.py
```
It shows how many verified papers support each signal we currently record, which Tier 1 papers remain, and which new signals are suggested most often.

## Notes
- Duplicates merged: Ma 2025 (`Ma2025NotEWD`/`NotEWJ`), Gu 2023 (`Gu2023HowDAE`/`HowDAU`).
- Some bib years differ from the proceedings year (e.g. CHI 2026 entries tagged 2025). Fix before citing.
- Tiers are a guess from titles. Move papers between tiers as you read.
