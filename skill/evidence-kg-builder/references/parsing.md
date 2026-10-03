# Parsing and provenance

## Common output

Every corpus file becomes DocumentUnits with:

- `content_md`: a compact LLM-facing reading view;
- `locator`: page / Sheet / row / cell / slide / section / table position;
- `structured`: a machine-facing ledger when the format has useful structure;
- `asset_refs`: images only when visual inspection is actually needed.

Do not confuse `structured` with semantic KG extraction. It is source structure and provenance.

## Format policy

- DOCX: parse paragraphs/headings/tables from OOXML and keep embedded images as visual assets. Word pagination is not invented.
- XLSX: use openpyxl directly; retain raw/cached values, formulas, comments, merged ranges, hidden rows/columns/Sheets and header candidates. Do not run a redundant MarkItDown conversion just to recreate the same cells.
- PPTX: preserve slide text, tables, charts, notes, shapes, images and connector metadata. Connector geometry alone is not a business relation.
- PDF: read the text layer and detected tables first. Render a page image only when the text layer is weak or the page contains raster imagery. Do not render every text-heavy page by default.
- Images: retain the original asset for host multimodal inspection. Do not add local OCR.

## Batching

Structured row batches are sized mainly by their readable row content, not by duplicating the full internal JSON ledger into the LLM budget. Default parse budgets are approximately 12k characters and 80 table rows; atomic rows are never truncated.

## Evidence

Locator provenance is authoritative. Exact quote matching is useful but not a reason to discard a source-supported fact when Office/PDF layout cleanup changed whitespace or separators. Evidence may be marked `exact`, `normalized`, or `locator_only`.

## Performance

Parsing should avoid duplicate work. The most important shortcuts are:

- no redundant XLSX MarkItDown pass;
- lazy PDF page rendering;
- semantic overlays for free-text spreadsheet cells instead of re-sending whole rows.
