# Bloomberg Manual Pull Instructions

Bloomberg is a future validation layer, not a dependency for the current build.
At school, manually export CSVs for the locked event IDs and save them under:

`data/imports/bloomberg/manual_csv/`

Use the template filenames exactly. Do not commit raw Bloomberg data. After
pulling files, run:

```bash
python3 scripts/validate_bloomberg_csv_imports.py
```

Then review `07_bloomberg_csv_ingestion_status.md`. Only after schema and
coverage are acceptable should the analysis be rerun with Bloomberg as an
explicit source.
