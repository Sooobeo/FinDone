# FinDone theory workbook data

This directory is generated from
`output/html/findone_theory_workbook_ross_integrated_30q.html` by:

```text
python tools/admin_import_workbook.py
```

The importer pins and validates the reviewed source SHA-256, then writes a
small index plus one JSON file per unit. The Admin UI loads only the selected
unit, rather than sending the full standalone HTML to the browser.

Do not hand-edit the JSON files. Regenerate them from the reviewed workbook.
