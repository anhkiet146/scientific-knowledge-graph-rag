import argparse
import json
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import atomic_json,file_hash


def orcid_checksum(identifier):
    value=identifier.replace('-','')
    if not re.fullmatch(r'[0-9]{15}[0-9X]',value):return False
    total=0
    for digit in value[:15]:total=(total+int(digit))*2
    check=(12-total%11)%11
    return value[-1]==('X' if check==10 else str(check))


def scan(text):
    text=re.sub(r'(?<!\\)%[^\n]*','',text)
    line=lambda offset:text.count('\n',0,offset)+1
    findings=[]
    def add(code,match,detail):findings.append({'code':code,'line':line(match.start()),'detail':detail})
    if re.search(r'\\(?:input|include)\s*\{',text):
        raise ValueError('Single-file source audit only; included sources require a recursive audit')
    orcids=[]
    for match in re.finditer(r'https://orcid.org/([0-9X-]+)',text):
        valid=orcid_checksum(match[1]);orcids.append({'id':match[1],'checksum_valid':valid,'line':line(match.start()),'owner_verified':False})
        if not valid:add('invalid_orcid_checksum',match,'Check with the author; do not invent a replacement')
    for match in re.finditer(r'AUTHOR CONFIRMATION REQUIRED|provide an author-confirmed biography|final approval of this revision is pending',text):
        add('author_confirmation_pending',match,match[0])
    for match in re.finditer(r'approved the final version of the manuscript',text):
        add('approval_attestation_requires_confirmation',match,'Asserted approval must be reconciled with pending revised-manuscript approval')
    for match in re.finditer(r'\\cite\w*\{[^}]+\}\s*[,;]?\s*\\cite\w*\{[^}]+\}',text):
        add('adjacent_citations',match,'Review whether citations should be consolidated')
    for match in re.finditer(r'\\tag\*?\s*\{|\\setcounter\{(?:equation|table|figure)\}',text):
        add('manual_numbering_requires_check',match,'Verify consecutive numbering in rendered PDF')
    tables=[]
    for match in re.finditer(r'\\begin\{table\}(.*?)\\end\{table\}',text,re.S):
        body=match[1];spec=re.search(r'\\begin\{tabular\}\{([^\n]+)',body)
        raw='Measured normalization audit' in body
        borders=bool(spec and '|' in spec[1]);rows=len(re.findall(r'\\\\',body));lines=len(re.findall(r'\\hline',body))
        tables.append({'line':line(match.start()),'caption_present':'\\caption' in body,'label_present':'\\label' in body,
            'booktabs_rules':all('\\'+rule in body for rule in ['toprule','midrule','bottomrule']),
            'raw_measurement_table':raw,'vertical_borders_detected':borders,'row_breaks':rows,'hline_count':lines})
        if raw and (not borders or lines<rows+1):
            add('raw_table_grid_requires_check',match,'Raw measurement table may lack a horizontal border after each row; inspect rendered PDF')
    figure_paths=[m[1] for m in re.finditer(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}',text)]
    equations=len(re.findall(r'\\begin\{equation\}',text))
    unnumbered=len(re.findall(r'\\begin\{(?:equation\*|align\*|displaymath)\}|\\\[',text))
    declarations=re.search(r'\\section\*\{Declarations[^}]*\}(.*?)(?=\\section|\\bibliographystyle)',text,re.S)
    return {'equation_environments':equations,'unnumbered_display_blocks':unnumbered,'tables':tables,
        'figure_paths':figure_paths,'orcids':orcids,
        'declaration_items_detected':len(re.findall(r'\\item\b',declarations[1])) if declarations else 0,
        'findings':findings,'submission_ready_certified':False,
        'limits':'Single-file static source inspection; does not certify layout, rendered numbering, figure DPI/font size, author identity, template currency, all declaration requirements, or reference truth.'}


def run(tex,output):
    if output.exists():raise ValueError('Fresh output required')
    result=scan(tex.read_text(encoding='utf-8'))
    result['figures']=[{'path':p,'exists':(tex.parent/p).is_file(),'kind':'vector_pdf_needs_render_check' if p.lower().endswith('.pdf') else 'raster_needs_physical_size_and_dpi_check'} for p in result['figure_paths']]
    output.mkdir(parents=True)
    atomic_json(output/'audit.json',result)
    atomic_json(output/'manifest.json',{'source_tex':str(tex.resolve()),'tex_sha256':file_hash(tex),'code_sha256':file_hash(Path(__file__))})
    shutil.copy2(Path(__file__),output/Path(__file__).name)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--tex',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    run(**vars(p.parse_args()))
