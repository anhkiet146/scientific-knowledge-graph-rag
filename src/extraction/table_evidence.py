"""Coordinate-bound table evidence. No OCR, inferred values, or graph approval."""
import math
from pathlib import Path
try:
    from .workflow_io import canonical_hash,file_hash
except ImportError:
    from workflow_io import canonical_hash,file_hash


def valid_box(value,width,height):
    if (not isinstance(value,(list,tuple)) or len(value)!=4
        or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in value)):
        raise ValueError('Finite four-coordinate box required')
    x0,y0,x1,y1=value
    if not 0<=x0<x1<=width or not 0<=y0<y1<=height:raise ValueError('Box outside page or inverted')
    return tuple(value)


def overlaps(a,b):
    return min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1])


def assign_words(words,cells,width,height):
    """Any word crossing a cell boundary blocks that cell; never clip a number."""
    boxes={};result={}
    for cell in cells:
        key=cell.get('id')
        if not isinstance(key,str) or not key or key in boxes:raise ValueError('Unique cell IDs required')
        box=valid_box(cell['bbox'],width,height)
        if any(overlaps(box,b) for b in boxes.values()):raise ValueError('Overlapping cell boxes')
        boxes[key]=box;result[key]={'id':key,'role':cell['role'],'bbox':list(box),'words':[],'issues':[]}
    for word in words:
        box=valid_box([word['x0'],word['top'],word['x1'],word['bottom']],width,height)
        if not isinstance(word.get('text'),str):raise ValueError('Word text required')
        for key,b in boxes.items():
            if not overlaps(box,b):continue
            record=result[key]
            if not (b[0]<=box[0] and b[1]<=box[1] and box[2]<=b[2] and box[3]<=b[3]):
                record['issues'].append('word_crosses_cell_boundary');continue
            record['words'].append({'text':word['text'],'bbox':list(box)})
            if '\ufffd' in word['text']:record['issues'].append('corrupt_pdf_text_requires_ocr_or_transcription')
    for record in result.values():
        ordered=sorted(record['words'],key=lambda w:(round(w['bbox'][1],1),w['bbox'][0]))
        record['words']=ordered
        record['derived_text']=' '.join(w['text'] for w in ordered)
        if not ordered:record['issues'].append('empty_cell')
        record['issues']=sorted(set(record['issues']))
    return result


def extract_table(pdf_path,spec):
    import pdfplumber
    path=Path(pdf_path);digest=file_hash(path)
    if spec.get('source_sha256')!=digest:raise ValueError('Table specification belongs to another PDF')
    page_number=spec.get('page')
    if isinstance(page_number,bool) or not isinstance(page_number,int) or page_number<1:raise ValueError('One-based page required')
    with pdfplumber.open(path) as document:
        if page_number>len(document.pages):raise ValueError('Page outside PDF')
        page=document.pages[page_number-1]
        dimensions={'width':page.width,'height':page.height}
        cells=assign_words(page.extract_words(x_tolerance=1,y_tolerance=2),spec['cells'],page.width,page.height)
        for cell in cells.values():
            b=cell['bbox']
            cell['glyphs']=[{'text':c['text'],'bbox':[c['x0'],c['top'],c['x1'],c['bottom']],'size':c['size']}
                for c in page.chars if b[0]<=c['x0']<c['x1']<=b[2] and b[1]<=c['top']<c['bottom']<=b[3]
                and c['text'].strip()]
    for cell in cells.values():
        cell['evidence_id']='cell_'+canonical_hash([digest,page_number,cell['bbox'],cell['words']])[:24]
    observations=[];seen=set()
    for observation in spec['observations']:
        oid=observation.get('id')
        if not isinstance(oid,str) or not oid or oid in seen:raise ValueError('Unique observation IDs required')
        seen.add(oid);refs=observation.get('cells')
        if not isinstance(refs,dict) or not {'caption','endpoint','object','value'}<=set(refs):
            raise ValueError('Explicit caption, endpoint, object and value cells required')
        if set(refs)-{'caption','endpoint','object','value','unit','condition','condition_label','uncertainty','reporting_note'}:
            raise ValueError('Unknown table field role')
        if any(not isinstance(k,str) or k not in cells for k in refs.values()):raise ValueError('Unknown cell reference')
        if any(cells[key]['role']!=field for field,key in refs.items()):raise ValueError('Cell role mismatch')
        issues=sorted({issue for key in refs.values() for issue in cells[key]['issues']})
        observations.append({'id':oid,'cell_refs':refs,
            'derived_fields':{field:cells[key]['derived_text'] for field,key in refs.items()},
            'issues':issues,'status':'blocked_source_text' if issues else 'pending_layout_and_semantic_review'})
    return {'protocol_id':'coordinate-table-evidence-v1','source_sha256':digest,'page':page_number,
        'page_dimensions':dimensions,'extractor_sha256':file_hash(Path(__file__)),
        'pdfplumber_version':pdfplumber.__version__,'word_settings':{'x_tolerance':1,'y_tolerance':2},
        'spec_sha256':canonical_hash(spec),'table_id':spec['table_id'],'cells':list(cells.values()),
        'observations':observations,'approved_for_graph':False,'actual_api_calls':0,
        'limitations':'Explicit development layout only; derived text is not an exact source quote. Word coordinates retained. Clean cells are not semantic approval. Corrupt characters are not repaired.'}
