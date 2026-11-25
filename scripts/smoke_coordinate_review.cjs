// Browser fixture only: exports are kept in memory and never become human labels.
const fs=require('node:fs/promises'),path=require('node:path'),{pathToFileURL}=require('node:url');
const {chromium}=require(process.argv[2]);
(async()=>{
  const html=path.resolve(process.argv[3]),out=path.resolve(process.argv[4]);
  await fs.mkdir(out,{recursive:true});
  const browser=await chromium.launch({channel:'chrome',headless:true});
  try{
    const context=await browser.newContext({viewport:{width:1450,height:1000},acceptDownloads:true});
    await context.route(/^https?:/,route=>route.abort());
    const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(pathToFileURL(html).href);await page.waitForSelector('#measurement td');
    const count=await page.locator('#pick option').count();if(count!==57)throw Error('Expected 57 records');
    if(!(await page.locator('#sourcePreview image').getAttribute('href')).startsWith('data:image/png;base64,'))throw Error('Missing source image');
    if(await page.locator('#sourcePreview rect').count()<4)throw Error('Missing cell highlights');
    await page.screenshot({path:path.join(out,'review_blank.png'),fullPage:true});
    await page.selectOption('#pick','45');await page.screenshot({path:path.join(out,'review_oil_blank.png'),fullPage:true});
    await page.selectOption('#pick','0');
    await page.selectOption('#status','approved');await page.click('#save');
    if(!(await page.locator('#message').innerText()).includes('Cần tên'))throw Error('Missing approval guard');
    await page.fill('#reviewer','Synthetic browser test — not a human review');
    await page.fill('#notes','Synthetic test only; discard these decisions.');
    for(const id of ['layout_correct','measurement_correct','footnote_and_reporting_note_checked'])await page.selectOption('#'+id,'true');
    const [download]=await Promise.all([page.waitForEvent('download'),page.click('#save')]);
    const bytes=await fs.readFile(await download.path());await download.delete();const draft=JSON.parse(bytes);
    if(draft.records[0].review.status!=='approved'||draft.records.slice(1).some(r=>r.review.status!=='unreviewed'))throw Error('Record isolation failed');
    await page.click('#next');if(await page.inputValue('#status')!=='unreviewed')throw Error('Navigation leaked review');
    await page.setInputFiles('#load',{name:'synthetic.json',mimeType:'application/json',buffer:bytes});
    await page.waitForFunction(()=>document.getElementById('message').textContent.includes('Đã nhập'));
    const altered=structuredClone(draft);altered.records[0].candidate_sha256='tampered';
    await page.setInputFiles('#load',{name:'tampered.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(altered))});
    await page.waitForFunction(()=>document.getElementById('message').textContent.includes('Hash hoặc nguồn đã đổi'));
    if(errors.length)throw Error(errors.join('\n'));
    await fs.writeFile(path.join(out,'browser_smoke.json'),JSON.stringify({records:count,navigation:true,export_import:true,tamper_rejected:true,blank_approval_rejected:true,page_errors:errors,synthetic_decisions_saved:false},null,2));
    console.log('Browser smoke passed; synthetic decisions discarded.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
