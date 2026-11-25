"""Build a local review page; no network, prefilled labels, or graph writes."""
import argparse
import base64
import io
import json
import os
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from coordinate_review import load_context


PAGE='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rà soát bảng phát triển</title><style>
body{font:16px system-ui;margin:24px;color:#172536;background:#f5f7fa}button,input,select,textarea{font:inherit;padding:8px;margin:4px 0}button{cursor:pointer}header{max-width:1100px}main{display:grid;grid-template-columns:minmax(360px,1fr) minmax(360px,1fr);gap:20px}section{background:white;padding:18px;border-radius:10px}label{display:block;margin:9px 0}textarea{box-sizing:border-box;width:100%;min-height:90px}#sourcePreview{width:100%;height:auto;border:1px solid #ddd;margin-top:15px}td,th{padding:7px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}table{width:100%;border-collapse:collapse}small{color:#536273}details{margin:9px 0}#message{color:#a32b22}@media(max-width:850px){main{grid-template-columns:1fr}}
</style><header><h1>Rà soát số đo từ bảng PDF</h1>
<p>57 bản ghi phát triển, chưa phải gold độc lập. Kiểm tra bố cục, số đo và chú thích trước khi chọn đồng ý. Trang này không ghi graph hoặc gửi dữ liệu lên mạng.</p>
<p>Tải JSON để lưu trước khi đóng trang. Nhập JSON để tiếp tục. Nếu PDF không hiển thị, mở bằng liên kết nguồn.</p>
<button id="prev">← Trước</button> <select id="pick" aria-label="Chọn bản ghi"></select> <button id="next">Sau →</button>
<button id="save">Tải JSON kiểm duyệt</button> <label>Nhập JSON đã lưu <input id="load" type="file" accept=".json"></label><p id="progress"></p><p id="message" role="status"></p></header>
<main><section><h2 id="title"></h2><table id="measurement"></table><p id="annotation"></p><details><summary>Bằng chứng từng trường</summary><div id="sources"></div></details>
<label>Người rà soát <input id="reviewer" autocomplete="name"></label>
<label>Bố cục hàng/cột <select id="layout_correct"></select></label>
<label>Giá trị, đơn vị, object và điều kiện <select id="measurement_correct"></select></label>
<label>Chú thích thống kê và reporting note <select id="footnote_and_reporting_note_checked"></select></label>
<label>Quyết định <select id="status"><option value="unreviewed">Chưa rà soát</option><option value="approved">Đồng ý bản ghi</option><option value="rejected">Từ chối</option><option value="needs_revision">Cần sửa</option></select></label>
<label>Ghi chú và lý do <textarea id="notes"></textarea></label><small>Đồng ý cần cả ba kiểm tra đạt, tên người rà soát và ghi chú. Không có lựa chọn đồng ý tất cả.</small>
</section><section><a id="pdfLink" target="_blank" rel="noopener">Mở PDF nguồn đầy đủ</a><p>Khung xanh đánh dấu các ô đang dùng. Ảnh là bản render bảng từ PDF, không phải bảng dựng lại từ số đo.</p><svg id="sourcePreview" role="img" aria-label="Bảng nguồn và các ô đang rà soát"></svg></section></main>
<script id="data" type="application/json">__DATA__</script><script>
'use strict';
const data=JSON.parse(document.getElementById('data').textContent),base=data.template;
let draft=structuredClone(base),index=0;
const $=id=>document.getElementById(id),flags=['layout_correct','measurement_correct','footnote_and_reporting_note_checked'];
for(const flag of flags){for(const [v,t] of [['','Chưa kiểm tra'],['true','Đạt'],['false','Không đạt']]){const o=document.createElement('option');o.value=v;o.textContent=t;$(flag).append(o);}}
data.rows.forEach((row,i)=>{const o=document.createElement('option');o.value=i;o.textContent=(i+1)+' · '+row.job_id+' · '+row.candidate.observation_id;$('pick').append(o);});
function progress(){const counts={};for(const r of draft.records)counts[r.review.status]=(counts[r.review.status]||0)+1;$('progress').textContent=JSON.stringify(counts);}
function render(){const row=data.rows[index],c=row.candidate,r=draft.records[index].review;
$('pick').value=index;$('title').textContent=row.job_id+' · '+c.observation_id;$('measurement').replaceChildren();
for(const [field,value] of Object.entries(c.measurement||{})){const tr=document.createElement('tr'),a=document.createElement('th'),b=document.createElement('td');a.textContent=field;b.textContent=value||'(không có trong ô đã chọn)';tr.append(a,b);$('measurement').append(tr);}
$('annotation').textContent='Footnote: '+(c.footnote_marker||'—')+' · '+(c.reporting_note||'')+' · '+c.status;
$('sources').replaceChildren();for(const [field,entry] of Object.entries(c.field_provenance||{})){const h=document.createElement('h3');h.textContent=field+' · '+entry.rule;$('sources').append(h);for(const key of entry.cell_ids){const cell=row.cells[key],p=document.createElement('p');p.textContent=key+' ['+cell.bbox.join(', ')+'] '+cell.derived_text;$('sources').append(p);}}
for(const key of ['reviewer','notes','status'])$(key).value=r[key];for(const flag of flags)$(flag).value=r[flag]===null?'':String(r[flag]);
const url=row.pdf+'#page='+row.page;$('pdfLink').href=url;
const preview=data.previews[row.job_id],svg=$('sourcePreview'),ns='http://www.w3.org/2000/svg';svg.replaceChildren();svg.setAttribute('viewBox','0 0 '+preview.width+' '+preview.height);
const image=document.createElementNS(ns,'image');image.setAttribute('href',preview.png);image.setAttribute('width',preview.width);image.setAttribute('height',preview.height);svg.append(image);
for(const key of new Set(Object.values(c.source_cell_refs))){const b=row.cells[key].bbox,rect=document.createElementNS(ns,'rect');rect.setAttribute('x',b[0]-preview.x0);rect.setAttribute('y',b[1]-preview.y0);rect.setAttribute('width',b[2]-b[0]);rect.setAttribute('height',b[3]-b[1]);rect.setAttribute('fill','none');rect.setAttribute('stroke','#1766cc');rect.setAttribute('stroke-width','0.8');svg.append(rect);}progress();}
function store(){const r=draft.records[index].review;for(const key of ['reviewer','notes','status'])r[key]=$(key).value;for(const flag of flags)r[flag]=$(flag).value===''?null:$(flag).value==='true';progress();}
for(const key of ['reviewer','notes','status',...flags])$(key).addEventListener('input',store);
$('pick').onchange=()=>{store();index=Number($('pick').value);render();};
$('prev').onclick=()=>{store();index=Math.max(0,index-1);render();};$('next').onclick=()=>{store();index=Math.min(data.rows.length-1,index+1);render();};
function check(value){if(value.manifest_sha256!==base.manifest_sha256||value.purpose!==base.purpose||!Array.isArray(value.records)||value.records.length!==base.records.length)throw Error('Sai manifest hoặc thiếu bản ghi.');
const byId=new Map(value.records.map(r=>[r.review_id,r]));if(byId.size!==base.records.length)throw Error('ID trùng.');
value.records=base.records.map(b=>{const r=byId.get(b.review_id);if(!r||Object.keys(r).sort().join()!==Object.keys(b).sort().join())throw Error('Sai ID/trường.');for(const key of Object.keys(b))if(key!=='review'&&r[key]!==b[key])throw Error('Hash hoặc nguồn đã đổi.');
const v=r.review;if(!v||Object.keys(v).sort().join()!==Object.keys(b.review).sort().join()||!['unreviewed','approved','rejected','needs_revision'].includes(v.status)||typeof v.reviewer!=='string'||typeof v.notes!=='string'||flags.some(k=>v[k]!==null&&typeof v[k]!=='boolean'))throw Error('Phiếu không hợp lệ.');
if(v.status!=='unreviewed'&&(!v.reviewer.trim()||!v.notes.trim()))throw Error('Cần tên và ghi chú cho bản ghi đã rà soát.');
const source=data.rows.find(x=>x.candidate.review_id===b.review_id);if(v.status==='approved'&&(source.candidate.status==='blocked'||flags.some(k=>v[k]!==true)))throw Error('Chưa đạt cả ba kiểm tra.');return r;});return value;}
$('save').onclick=()=>{try{store();check(draft);const url=URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='coordinate_review.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('message').textContent='Đã xuất JSON. Dùng bộ kiểm tra Python trước khi sử dụng kết quả.';}catch(e){$('message').textContent=e.message;}};
$('load').onchange=async()=>{try{const f=$('load').files[0];if(!f)return;if(f.size>8*1024*1024)throw Error('File quá lớn.');const value=check(JSON.parse(await f.text()));draft=value;render();$('message').textContent='Đã nhập phiếu.';}catch(e){$('message').textContent=e.message;}};
render();
</script></html>'''


def build(pilot,output):
    pilot=Path(pilot).resolve();output=Path(output).resolve()
    if output.exists() or output.is_relative_to(pilot):raise ValueError('Fresh review page outside pilot required')
    template,context=load_context(pilot);rows=[];previews={}
    for record in template['records']:
        key,candidate,bundle=context[record['review_id']]
        pdf=pilot/'sources'/key/'pdf.pdf'
        if key not in previews:
            from PIL import Image
            converter=shutil.which('pdftoppm')
            if not converter:raise RuntimeError('pdftoppm is required for source previews')
            table=bundle['table_evidence'];page=str(table['page'])
            with tempfile.TemporaryDirectory() as tmp:
                prefix=Path(tmp)/'page'
                subprocess.run([converter,'-f',page,'-l',page,'-singlefile','-scale-to','2000','-png',str(pdf),str(prefix)],check=True,capture_output=True)
                image=Image.open(prefix.with_suffix('.png')).convert('RGB')
                sx=image.width/table['page_dimensions']['width'];sy=image.height/table['page_dimensions']['height']
                boxes=[c['bbox'] for c in table['cells']]
                x0=max(0,int((min(b[0] for b in boxes)-7)*sx));y0=max(0,int((min(b[1] for b in boxes)-7)*sy))
                x1=min(image.width,int((max(b[2] for b in boxes)+7)*sx)+1);y1=min(image.height,int((max(b[3] for b in boxes)+7)*sy)+1)
                cropped=image.crop((x0,y0,x1,y1));buffer=io.BytesIO();cropped.save(buffer,format='PNG')
                previews[key]={'png':'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode(),
                    'x0':x0/sx,'y0':y0/sy,'width':(x1-x0)/sx,'height':(y1-y0)/sy}
        link=quote(os.path.relpath(pdf,output.parent).replace('\\','/'),safe='/')
        rows.append({'job_id':key,'candidate':candidate,'pdf':link,'page':bundle['table_evidence']['page'],
            'cells':{c['id']:c for c in bundle['table_evidence']['cells']}})
    payload=json.dumps({'template':template,'rows':rows,'previews':previews},ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(PAGE.replace('__DATA__',payload),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();build(args.pilot,args.output)
