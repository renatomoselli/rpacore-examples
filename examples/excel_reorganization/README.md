# Excel Reorganization Example

## Overview

`excel_reorganization` is a local file-in/file-out workflow:

1. `LoadSalesData` reads and validates CSV rows.
2. `GroupByMonth` groups durable JSON-safe state and records expected subtotals.
3. `BuildOutputSheets` writes the workbook through a temporary file and records an output artifact.
4. `VerifyOutput` validates the generated workbook against durable expected state.

The example uses current RPA Core APIs:

- durable workflow values are stored in `ctx.state`
- config values are read through `ctx.require_config`
- downstream state dependencies use `ctx.require_state`
- generated workbooks are recorded with `ctx.add_artifact`
- deterministic data and verification failures use `BusinessException(stop=True)`
- technical file and workbook write failures use `SystemException`

## Runtime Boundaries

The workflow keeps runtime handles out of transaction state. Workbook objects and file handles stay local to the skill that owns them. Persisted state contains only paths, rows, grouping dictionaries, expected month keys, expected subtotals, and JSON-safe metadata.

`main.py` owns config loading, config validation, transaction construction, final transaction persistence, and failed-output cleanup. Skills own their local data validation and artifact production.

## Verification Coverage

The tests cover:

- config validation and path containment
- missing, empty, sparse, and malformed CSV inputs
- grouping, sorting, date revalidation, and expected subtotals
- atomic workbook output behavior and temp-file cleanup
- workbook structure, metadata, missing output, and subtotal verification
- failure cleanup and persistence behavior in `main.py`
