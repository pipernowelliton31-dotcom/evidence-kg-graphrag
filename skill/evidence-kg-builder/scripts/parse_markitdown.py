"""Optional MarkItDown reading views with the unchanged native provenance ledger.

Run this entry instead of `kg_pipeline.py parse`; all downstream commands are shared.
"""
from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
import re
import shutil
import sys
from pathlib import Path

from kg_core import (CONFIG, ENGINE_VERSION, SCHEMA_VERSION, ContractError, canonical,
                     clean, empty_alignment, engine_signature, ident, read_json,
                     require, save_state, write_json)
from parse_documents import Adapter, SUPPORTED, dependency_versions, hash_file


def require_converter():
    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise ContractError('Optional parser requires: python -m pip install -r requirements-markitdown.txt') from exc
    return MarkItDown(enable_plugins=False)


class MarkdownAdapter(Adapter):
    def __init__(self, document, path, work, config, converter):
        super().__init__(document, path, work, config)
        self.converter = converter

    def markdown(self):
        text = clean(self.converter.convert(str(self.path)).markdown).strip()
        require(bool(text), 'MarkItDown returned an empty reading view')
        output = self.work / 'markdown' / (self.document['document_id'] + '.md')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + '\n', encoding='utf-8')
        self.document['markdown_ref'] = output.relative_to(self.work).as_posix()
        return text

    def docx(self):
        super().docx()
        markdown = self.markdown()
        if not self.units:
            self.add(markdown, {'section': [], 'precision': 'document_markdown'},
                     warnings=['xml_blocks_unavailable'])

    def xlsx(self):
        super().xlsx()
        self.markdown()  # Supplemental only: formulas, hidden data and exact cells stay native.

    def pptx(self):
        super().pptx()
        markdown = self.markdown()
        chunks = re.split(r'<!--\s*Slide number:\s*(\d+)\s*-->', markdown)
        slide_md = {int(chunks[i]): chunks[i + 1].strip()
                    for i in range(1, len(chunks) - 1, 2)}
        native_units, self.units = self.units, []
        slides = {}
        for unit in native_units:
            slides.setdefault(unit['locator']['slide'], []).append(unit)
        for slide, units in slides.items():
            first = units[0]
            if not slide_md.get(slide):
                for unit in units:
                    unit['parse_warnings'].append('markitdown_slide_unavailable: native_reading_view_used')
                self.units.extend(units)
                continue
            content = slide_md[slide]
            ledger = copy.deepcopy(first.get('structured', {}))
            notes = clean(ledger.get('notes', '')).strip()
            if notes and notes not in content:
                content += '\n\nNotes: ' + notes
            for shape in ledger.get('shapes', []):
                if shape.get('chart'):
                    content += '\n\nChart: ' + canonical(shape['chart'])
            locator = {key: value for key, value in first['locator'].items() if key != 'part'}
            self.add(content, locator, assets=first['asset_refs'],
                     warnings=first['parse_warnings'], structured=ledger)


def parse_manifest(manifest_path, work, config=None, fresh=False):
    """Keep the native state contract and add backend-specific cache metadata."""
    converter = require_converter()
    manifest_path, work = Path(manifest_path).resolve(), Path(work).resolve()
    manifest = read_json(manifest_path)
    require(isinstance(manifest, dict) and isinstance(manifest.get('files'), list)
            and bool(manifest['files']), 'Manifest needs nonempty files array')
    root = (manifest_path.parent / manifest.get('root', '.')).resolve()
    config = {**CONFIG, **(config or {}), 'parser_backend': 'markitdown',
              'parser_adapter_signature': hash_file(__file__)}
    require(config['max_chars'] >= 500 and config['max_rows'] >= 1, 'Invalid parsing budgets')
    documents, paths, seen = [], {}, set()
    for item in manifest['files']:
        require(isinstance(item, dict) and isinstance(item.get('path'), str), 'Manifest entry needs path')
        path = (root / item['path']).resolve()
        require(path.is_file(), 'Missing input: ' + str(path))
        require(path not in seen, 'Duplicate input file')
        require(not path.is_relative_to(work), 'Work directory must not contain input files')
        seen.add(path)
        role = item.get('role', 'corpus')
        require(role in {'corpus', 'questions', 'reference'}, 'Unknown input role')
        require(role != 'corpus' or path.suffix.lower() in SUPPORTED, 'Unsupported corpus format')
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError as exc:
            raise ContractError('Input path escapes manifest root') from exc
        sha = hash_file(path)
        did = ident('doc', [relative, sha])
        documents.append({'document_id': did, 'path': relative, 'sha256': sha,
                          'format': path.suffix.lower().lstrip('.'), 'role': role,
                          'parse_status': 'excluded' if role != 'corpus' else 'pending'})
        paths[did] = path
    versions = dependency_versions()
    for package in ['markitdown', 'mammoth', 'pandas', 'lxml', 'beautifulsoup4']:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = 'missing'
    signature = engine_signature()  # Unchanged core must accept this state in downstream commands.
    fingerprint = ident('run', [ENGINE_VERSION, signature, documents, config, versions])
    state_path = work / 'state.json'
    if state_path.exists():
        previous = read_json(state_path)
        if previous.get('fingerprint') == fingerprint and not fresh:
            return previous, True
        archive = work / 'archive' / ident('checkpoint', [previous.get('fingerprint'),
                        previous.get('audit'), previous.get('extractions')])
        archive.mkdir(parents=True, exist_ok=True)
        for name in ['state.json', '00_document_units.json', '00_extraction_plan.json',
                     '01_mentions.json', '02_entity_map.json', '03_canonical_facts.json',
                     '04_knowledge_graph.json']:
            existing = work / name
            if existing.is_file():
                shutil.copy2(existing, archive / name)
                existing.unlink()
    units = []
    work.mkdir(parents=True, exist_ok=True)
    for document in documents:
        if document['role'] != 'corpus':
            continue
        adapter = MarkdownAdapter(document, paths[document['document_id']], work, config, converter)
        try:
            units.extend(adapter.run())
            document['parse_status'] = 'parsed'
        except Exception as exc:
            document['parse_status'] = 'failed'
            document['parse_error'] = f'{type(exc).__name__}: {exc}'
            units.extend(adapter.units)
    state = {'schema_version': SCHEMA_VERSION, 'engine_version': ENGINE_VERSION,
             'engine_signature': signature, 'fingerprint': fingerprint, 'config': config,
             'parser_versions': versions, 'source_root': str(root), 'documents': documents,
             'units': units, 'extractions': {}, 'alignment': empty_alignment(),
             'audit': [{'action': 'parse', 'fingerprint': fingerprint, 'parser_backend': 'markitdown'}]}
    write_json(work / '00_document_units.json',
               {'fingerprint': fingerprint, 'documents': documents, 'units': units})
    save_state(work, state)
    return state, False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--work', required=True)
    parser.add_argument('--fresh', action='store_true')
    parser.add_argument('--max-chars', type=int, default=CONFIG['max_chars'])
    parser.add_argument('--max-rows', type=int, default=CONFIG['max_rows'])
    args = parser.parse_args()
    state, cached = parse_manifest(args.manifest, args.work,
                                  {'max_chars': args.max_chars, 'max_rows': args.max_rows}, args.fresh)
    failures = [d for d in state['documents'] if d['parse_status'] == 'failed']
    print(json.dumps({'ok': not failures, 'parser_backend': 'markitdown',
                      'fingerprint': state['fingerprint'], 'cached': cached,
                      'documents': [{'path': d['path'], 'role': d['role'],
                                     'status': d['parse_status'], 'error': d.get('parse_error')}
                                    for d in state['documents']],
                      'unit_count': len(state['units']), 'parser_versions': state['parser_versions'],
                      'next': 'prepare', 'work': str(Path(args.work).resolve())}, ensure_ascii=False))
    return 2 if failures else 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        sys.exit(main())
    except (ContractError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc), 'error_type': type(exc).__name__}, ensure_ascii=False))
        sys.exit(2)
