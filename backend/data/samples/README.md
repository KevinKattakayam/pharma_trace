# Sample data: NOT REAL

Files ending in `.SAMPLE.json` are **synthetic fixtures** for tests and demos. Batch numbers start
with `SMPL-`, manufacturers are marked `(FICTIONAL)`, and every record has `"dataset": "SAMPLE"`.
The API reports `is_sample_data: true` in coverage when these are loaded.

Never point `BATCH_ALERTS_DATA_PATH` at these files in production. Load real CDSCO alerts with
`python -m scripts.import_regulator_alerts` (see docs/RUNBOOK.md).
