# Regression evaluation harness (scaffold)

**No results are reported and no real dataset is bundled.** Accuracy claims need a labelled,
consented dataset reviewed by pharmacists (docs/FINAL_REPORT.md → Requires human action).

* `cases.schema.json`: format for labelled cases (input → expected verdict/status/reasons).
* `run_eval.py`: runs cases through the real code with external services stubbed and counts
  pass/fail. It refuses files marked `"synthetic": true` unless `--allow-synthetic` is passed,
  and then labels the output `SYNTHETIC SMOKE TEST, NOT A BENCHMARK`.
* `cases.synthetic.json`: 4 hand-written smoke cases proving the harness works.

Run: `python -m eval.run_eval eval/cases.synthetic.json --allow-synthetic`
