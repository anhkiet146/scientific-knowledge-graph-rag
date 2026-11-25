"""Shared page-level input for batch and upload; no inferred table reconstruction."""
import copy
from pathlib import Path
try:
    from .workflow_io import file_hash
except ImportError:
    from workflow_io import file_hash


def attach_pdf_pages(document,pdf_path):
    from pypdf import PdfReader
    if not isinstance(document,dict):raise ValueError('Document metadata must be an object')
    path=Path(pdf_path).resolve()
    reader=PdfReader(str(path))
    if not reader.pages:raise ValueError('PDF has no pages')
    result=copy.deepcopy(document)
    pages=[{'section_title':f'Original PDF page {i}','category':'pdf_page','page':i,
            'content':page.extract_text(extraction_mode='layout') or ''}
           for i,page in enumerate(reader.pages,1)]
    result['sections']=pages
    result['pdf_evidence']={'path':str(path),'sha256':file_hash(path),'parser':'pypdf layout',
        'pages':len(pages),'empty_pages':[p['page'] for p in pages if not p['content'].strip()],
        'limitations':'Column order, rotated text, formulas and image-only content still require review. No cells inferred.'}
    return result
