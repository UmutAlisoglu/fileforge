import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

// Optional developer check. Playwright is not shipped in the Windows app.
// It can be installed in this checkout, or reused from the surrounding website.
const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require('playwright')); }
catch {
  const website = process.env.FILEFORGE_SITE_ROOT || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
  ({ chromium } = createRequire(path.join(website, 'package.json'))('playwright'));
}
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, '.qa', 'browser');
await fs.mkdir(output, { recursive: true });
const base = process.env.FILEFORGE_TEST_URL || 'http://127.0.0.1:8765';
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' });
const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, acceptDownloads: true });
const page = await context.newPage();
const ownedJobs = new Set();
const errors = [], external = [];
let tracking = false;
page.on('pageerror', failure => errors.push(failure.message));
page.on('console', message => { if(message.type()==='error' && /content security|refused|uncaught/i.test(message.text())) errors.push(message.text()); });
page.on('request', request => { if(tracking && !request.url().startsWith(base) && !request.url().startsWith('blob:')) external.push(request.url()); });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function waitJob(id) {
  const started = Date.now();
  while(Date.now()-started<120000) {
    const response = await context.request.get(`${base}/api/jobs/${id}`);
    assert.equal(response.status(),200);
    const job = await response.json();
    if(['completed','failed','cancelled'].includes(job.status)) { assert.equal(job.status,'completed',job.error || job.stage); return job; }
    await pause(250);
  }
  throw new Error(`Job ${id} did not finish.`);
}
async function choose(tool) {
  await page.locator(`#navigation [data-tool="${tool}"]`).click();
  const expected = tool==='image'?'Convert images':tool==='video'?'Compress video':await page.locator(`#navigation [data-tool="${tool}"] .nav-label`).textContent();
  assert.equal(await page.locator('#converter-title').textContent(),expected);
}
async function submit() {
  const pending = page.waitForResponse(response=>response.url()===`${base}/api/jobs` && response.request().method()==='POST');
  await page.locator('#convert-button').click();
  const response = await pending;
  assert.equal(response.status(),202,await response.text());
  const { id } = await response.json(); ownedJobs.add(id);
  const job = await waitJob(id);
  await page.locator(`[data-job-id="${id}"].completed`).waitFor();
  return job;
}
async function preview(job) {
  await page.locator(`[data-job-id="${job.id}"] [data-preview]`).click();
  const image = page.locator(`[data-job-id="${job.id}"] .result-preview img`);
  await image.waitFor();
  await image.evaluate(element=>element.decode());
  assert.ok(await image.evaluate(element=>element.naturalWidth>0));
}
try {
  await page.goto('about:blank');
  const png = await page.evaluate(()=>{const canvas=document.createElement('canvas');canvas.width=400;canvas.height=300;const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,400,300);ctx.fillStyle='#624bc5';ctx.fillRect(70,40,250,200);ctx.fillStyle='#e8b267';ctx.fillRect(120,90,140,110);return canvas.toDataURL('image/png').split(',')[1];});
  const image1=path.join(output,'artwork.png'),image2=path.join(output,'artwork-two.png');
  await fs.writeFile(image1,Buffer.from(png,'base64'));await fs.writeFile(image2,Buffer.from(png,'base64'));
  await page.setContent('<style>@page{size:A4;margin:30px}.sheet{page-break-after:always;font:30px Arial;color:#624bc5}.sheet:last-child{page-break-after:auto}</style><div class="sheet">FIRST PAGE</div><div class="sheet">SECOND PAGE</div><div class="sheet">THIRD PAGE</div>');
  const pdf1=path.join(output,'three-pages.pdf');await page.pdf({path:pdf1,preferCSSPageSize:true,printBackground:true});
  await page.setContent('<h1 style="font:30px Arial">OTHER DOCUMENT</h1>');
  const pdf2=path.join(output,'one-page.pdf');await page.pdf({path:pdf2,format:'A4'});
  tracking=true;
  await page.goto(base+'/native/');await page.locator('#navigation [data-tool]').first().waitFor();
  assert.equal(await page.locator('#navigation [data-tool]').count(),9);
  assert.equal(await page.locator('.tool-card').count(),9);
  await page.screenshot({path:path.join(output,'desktop-directory.png'),fullPage:true});
  await page.locator('#tool-search').fill('png to pdf');assert.equal(await page.locator('.tool-card').count(),1);
  assert.equal(await page.locator('.tool-card').getAttribute('data-tool'),'image');
  await page.locator('.tool-card').click();assert.equal(await page.locator('#image-format').inputValue(),'pdf');
  await page.locator('#tool-search').fill('JPG → PNG');assert.equal(await page.locator('.tool-card').count(),1);
  await page.locator('.tool-card').click();assert.equal(await page.locator('#image-format').inputValue(),'png');
  await page.locator('#tool-search').fill('SVG → PNG');assert.equal(await page.locator('.tool-card').count(),0);
  await page.locator('#tool-search').fill('PDF to SVG');assert.equal(await page.locator('.tool-card').count(),0);
  await page.locator('#tool-search').fill('TIFF to JPEG');assert.equal(await page.locator('.tool-card').count(),1);
  await page.locator('.tool-card').click();assert.equal(await page.locator('#image-format').inputValue(),'jpg');
  await page.locator('#tool-search').fill('');await page.locator('[data-category="PDFs"]').click();assert.equal(await page.locator('.tool-card').count(),3);await page.locator('[data-category="All"]').click();
  console.log('PASS: Nine searchable tools, category filters, matching output presets and unsupported directions.');

  await choose('image');await page.locator('#file-input').setInputFiles([image1,image2]);assert.equal(await page.locator('.selected-file').count(),2);
  await page.locator('#image-format').selectOption('png');await page.locator('#image-width').fill('200');
  const batch=await submit();assert.match(batch.output_name,/\.zip$/);assert.ok(batch.output_size>0);
  assert.equal(await page.locator('.selected-file').count(),0);
  console.log('PASS: Image batch submits through the local job queue and produces a ZIP.');

  await choose('crop');await page.locator('#file-input').setInputFiles(image1);await page.locator('#crop-canvas').waitFor({state:'visible'});
  const box=await page.locator('#crop-canvas').boundingBox();await page.mouse.move(box.x+box.width*.1,box.y+box.height*.1);await page.mouse.down();await page.mouse.move(box.x+box.width*.8,box.y+box.height*.8);await page.mouse.up();assert.ok(Number(await page.locator('#crop-width').inputValue())<400);
  await page.locator('#crop-x').fill('100');await page.locator('#crop-y').fill('50');await page.locator('#crop-width').fill('120');await page.locator('#crop-height').fill('80');
  await page.screenshot({path:path.join(output,'desktop-crop.png'),fullPage:true});
  const crop=await submit();await preview(crop);assert.match(crop.output_name,/-cropped\.png$/);
  const cropImage=page.locator(`[data-job-id="${crop.id}"] .result-preview img`);assert.deepEqual(await cropImage.evaluate(image=>[image.naturalWidth,image.naturalHeight]),[120,80]);
  await page.locator('#file-input').setInputFiles(image1);await page.locator('#crop-canvas').waitFor({state:'visible'});await page.locator('#clear-files').click();assert.equal(await page.locator('#crop-workspace').isVisible(),false);assert.equal(await page.locator('#convert-button').isDisabled(),true);
  console.log('PASS: Drag and exact crop, real output preview, and source cleanup.');

  await choose('background');await page.locator('#file-input').setInputFiles(image1);await page.locator('#background-fill').selectOption('transparent');const background=await submit();await preview(background);assert.match(background.output_name,/\.png$/);
  console.log('PASS: Background removal job and typed image preview.');
  await choose('trace');await page.locator('#file-input').setInputFiles(image1);await page.locator('#trace-detail').selectOption('simple');const svg=await submit();await preview(svg);assert.match(svg.output_name,/\.svg$/);
  const svgResponse=await context.request.get(`${base}/api/jobs/${svg.id}/preview`);assert.match(svgResponse.headers()['content-type'],/image\/svg\+xml/);assert.match(await svgResponse.text(),/<path/);
  console.log('PASS: SVG tracing, vector paths and safe result preview.');

  await choose('pdfimages');await page.locator('#file-input').setInputFiles(pdf1);await page.locator('#pdf-pages').fill('2');await page.locator('#pdf-edge').selectOption('1200');const rendered=await submit();await preview(rendered);assert.match(rendered.output_name,/page-0002\.png$/);
  await page.locator('#file-input').setInputFiles(pdf1);await page.locator('#pdf-pages').fill('1-2');const renderedBatch=await submit();assert.match(renderedBatch.output_name,/\.zip$/);
  console.log('PASS: PDF page selection, PNG preview and multi-page ZIP.');

  await choose('organize');await page.locator('#file-input').setInputFiles([pdf1,pdf2]);
  const loading=page.waitForResponse(response=>response.url()===`${base}/api/jobs`&&response.request().method()==='POST');await page.locator('#load-pages').click();const previewJob=await (await loading).json();ownedJobs.add(previewJob.id);
  await page.locator('.page-card').nth(3).waitFor();assert.equal(await page.locator('.page-card').count(),4);
  await page.waitForFunction(()=>!document.querySelector('#load-pages').disabled);
  assert.equal((await context.request.get(`${base}/api/jobs/${previewJob.id}`)).status(),404);ownedJobs.delete(previewJob.id);
  assert.equal(await page.locator(`[data-job-id="${previewJob.id}"]`).count(),0);
  const thumb=page.locator('.page-card img').first();assert.match(await thumb.getAttribute('src'),/^blob:/);await thumb.evaluate(image=>image.decode());
  await page.locator('[data-page-select="0"]').uncheck();await page.locator('[data-page-rotate="1"]').click();assert.match(await page.locator('[data-page-id="1"] img').getAttribute('style'),/90deg/);
  await page.locator('[data-page-move="3"][data-offset="-1"]').click();assert.equal(await page.locator('.page-card').nth(2).getAttribute('data-page-id'),'3');
  await page.screenshot({path:path.join(output,'desktop-organizer.png'),fullPage:true});
  const organized=await submit();assert.match(organized.output_name,/\.pdf$/);assert.ok(organized.output_size>0);assert.equal(await page.locator('.page-card').count(),0);
  console.log('PASS: PDF thumbnails, hidden preview cleanup, selection/reorder/rotation and PDF export.');

  await choose('merge');await page.locator('#file-input').setInputFiles([pdf1,pdf2]);const merged=await submit();assert.match(merged.output_name,/\.pdf$/);
  const csv=path.join(output,'table.csv');await fs.writeFile(csv,'Name,Value\nAlpha,42\nBeta,23\n');await choose('spreadsheet');await page.locator('#file-input').setInputFiles(csv);const spreadsheet=await submit();assert.match(spreadsheet.output_name,/\.pdf$/);
  await choose('video');assert.equal(await page.locator('#target-mb').inputValue(),'25');await page.locator('[data-size="10"]').click();assert.equal(await page.locator('#target-mb').inputValue(),'10');
  console.log('PASS: Existing PDF merge, spreadsheet export and video settings.');

  for(const width of [320,390,768,1440]){await page.setViewportSize({width,height:900});await choose('image');await page.evaluate(()=>scrollTo(0,0));assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`Overflow at ${width}px`);if(width===390)await page.screenshot({path:path.join(output,'desktop-mobile.png'),fullPage:true});}
  assert.deepEqual(external,[],'App requested an external service.');assert.deepEqual(errors,[],'Browser or CSP errors.');
  console.log('PASS: Responsive layouts, no external requests and no browser/CSP errors.');
} finally {
  for(const id of ownedJobs){try{const response=await context.request.get(`${base}/api/jobs/${id}`);if(response.ok()){const job=await response.json();if(!['completed','failed','cancelled'].includes(job.status))await context.request.post(`${base}/api/jobs/${id}/cancel`);else await context.request.delete(`${base}/api/jobs/${id}`);}}catch{}}
  await browser.close();
}
