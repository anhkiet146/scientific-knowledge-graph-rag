"""Conservative coordinate measurement candidates; no silent unit conversion."""
import re
try:
    from .strict_validation import SCALAR
    from .workflow_io import canonical_hash
except ImportError:
    from strict_validation import SCALAR
    from workflow_io import canonical_hash

UNITS=('sec','s','%','µg/mL','μg/mL','mg/mL')
NUMERIC=re.compile(rf'^(?P<value>{SCALAR})(?:\s*±\s*(?P<uncertainty>{SCALAR}))?(?P<tail>.*?)$')


def superscript_markers(cell):
    digits=[g for g in cell.get('glyphs',[]) if re.fullmatch('[0-9]',g['text'])]
    if not digits:return set()
    baseline=max(g['bbox'][3] for g in digits);size=max(g['size'] for g in digits)
    return {g['text'] for g in cell.get('glyphs',[]) if re.fullmatch('[a-z]',g['text'])
        and g['size']<.9*size and g['bbox'][3]<baseline-.5}


def parse_numeric(text,*,header='',footnotes=()):
    if not isinstance(text,str) or '\ufffd' in text:raise ValueError('Invalid source text')
    match=NUMERIC.fullmatch(text.strip())
    if not match:raise ValueError('Unsupported numerical cell')
    tail=match['tail'].strip();marker=''
    # A letter is a footnote only when its superscript geometry was established.
    if tail and tail not in UNITS and tail[-1] in footnotes:
        marker=tail[-1];tail=tail[:-1].strip()
    if tail and tail not in UNITS:raise ValueError('Unrecognised unit or annotation')
    label='';unit=''
    if header:
        hm=re.fullmatch(r'([^()]+)\s*\(([^()]+)\)',header.strip())
        if not hm or hm[2].strip() not in UNITS:raise ValueError('Unrecognised unit header')
        label=hm[1].strip();unit=hm[2].strip()
    if tail and unit and tail!=unit:raise ValueError('Conflicting inline and header units')
    if match['uncertainty'] and match['uncertainty'].lstrip().startswith(('-','−')):
        raise ValueError('Negative uncertainty is not supported')
    return {'value':match['value'],'uncertainty':match['uncertainty'] or '',
            'unit':tail or unit,'footnote_marker':marker,'measurement_label':label}


def build_candidates(table):
    cells={c['id']:c for c in table['cells']}
    if len(cells)!=len(table['cells']):raise ValueError('Duplicate source cell IDs')
    rows=[];seen=set()
    for observation in table['observations']:
        oid=observation['id']
        if oid in seen:raise ValueError('Duplicate observation ID')
        seen.add(oid);refs=observation['cell_refs'];fields=observation['derived_fields']
        if set(refs)!=set(fields) or any(key not in cells or cells[key]['derived_text']!=fields[field]
            or cells[key]['role']!=field for field,key in refs.items()):raise ValueError('Source cell mapping changed')
        issues=sorted({i for key in refs.values() for i in cells[key]['issues']})
        record={'observation_id':oid,'source_cell_refs':refs,'source_sha256':table['source_sha256'],
            'table_id':table['table_id'],'page':table['page'],'issues':issues,'measurement':None}
        if not issues:
            try:
                if fields.get('uncertainty'):raise ValueError('Separate uncertainty cells not supported yet')
                if fields.get('condition') and not fields.get('condition_label'):
                    raise ValueError('Condition requires its source header')
                parsed=parse_numeric(fields['value'],header=fields.get('unit',''),
                    footnotes=superscript_markers(cells[refs['value']]))
                record['measurement']={'endpoint':' '.join(filter(None,[parsed['measurement_label'],fields['endpoint']])),
                    'value':parsed['value'],'unit':parsed['unit'],'object':fields['object'],
                    'condition':' '.join(filter(None,[fields.get('condition_label',''),fields.get('condition','')])),
                    'uncertainty':parsed['uncertainty'],'source_report':'table'}
                record['footnote_marker']=parsed['footnote_marker']
                record['reporting_note']=fields.get('reporting_note','')
            except ValueError as exc:record['issues'].append(str(exc))
        record['status']='blocked' if record['issues'] else 'pending_layout_and_semantic_review'
        rows.append(record)
    return {'protocol_id':'coordinate-measurement-candidates-v1','source_sha256':table['source_sha256'],
        'table_evidence_sha256':canonical_hash(table),'candidates':rows,'approved_for_graph':False,
        'actual_api_calls':0,'limitations':'Derived fields bound to table cells. Not independent gold, not an approved graph payload. Superscript marker retained; statistical meaning not inferred.'}
