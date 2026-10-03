# Optional MarkItDown parsing route

Use this route only when the user chooses MarkItDown. Native parsing remains the default; its implementation and dependencies are unchanged.

## Entry

From the Skill directory:

```bash
python -m pip install -r requirements-markitdown.txt
python scripts/parse_markitdown.py --manifest <inputs.json> --work <separate-work> --fresh
```

The entry accepts `--max-chars` and `--max-rows` with the same defaults as native parsing. Exit 0 means all corpus documents parsed successfully; exit 2 includes a JSON error or per-document failure. Missing optional dependencies are reported before checkpoints are created. Question and reference files are excluded.

## Reading views and provenance

| Format | Optional behavior | Authoritative structure |
| --- | --- | --- |
| DOCX | Full Markdown saved to `markdown/<document_id>.md`; document-level fallback only if OOXML yields no units | Native paragraphs, sections, tables and image assets |
| XLSX | Full Markdown saved as a supplementary reading file | Unchanged native cells, formulas, caches, comments, hidden rows/columns/Sheets and merged ranges |
| PPTX | Per-slide MarkItDown reading view; native notes and chart values retained | Native slide locators, shape/table/chart/connector metadata and images |
| PDF | Same text, table and lazy rendering route as native | Page/table/bbox locators |
| Images | Same original asset for host multimodal inspection | Image locator and original bytes |
| TXT / MD | Same native text units | Document locator |

Full-document Markdown does not create artificial page numbers or exact cell provenance. DOCX and XLSX Markdown files are supplementary; the normal downstream task content continues to use the precise native units. PPTX reading text changes and its unit IDs are recalculated. A missing slide marker uses the native slide text with an explicit warning. A failed or empty document conversion marks that corpus document as failed; partial native units are not reported as a successful parse.

## Checkpoints

Outputs follow the existing state / DocumentUnit contract. The cache fingerprint additionally includes `parser_backend`, the optional adapter's source hash and conversion dependency versions. The core engine signature stays unchanged so the existing downstream commands can load this state.

Use separate work directories for native and MarkItDown runs. A changed input, adapter or dependency invalidates the optional cache; old checkpoint JSON files are archived. Inputs are never moved or removed. `--fresh` restarts this route and clears accepted extraction/alignment from the active state.

## Model boundary

Parsing does not call a model. No OCR, embedding or graph database is added. Host visual review is still required for image content. OpenRouter is an optional local test harness; the competition host is intended to use Teleagent's native model, and Teleagent execution has not been tested.
