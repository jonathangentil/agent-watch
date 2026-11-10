// Optional browser verification; uses an already installed Playwright + Chromium.
// PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs CHROMIUM_EXECUTABLE=/absolute/path/to/chrome node tests/web/browser-smoke.mjs
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE);
const root=new URL('../../src/alethe_tui/web/',import.meta.url);
let offline=false;
const makeAgent=(id,execution_id='e1',extra={})=>({id,execution_id,name:id,project_id:'p1',source:'codex',task:'<img src=x onerror=alert(1)>',model:'modelo de teste',status:'running',evidence:'evento sintético',...extra});
const snap={version:1,connected:true,generated_at:'2026-01-01',projects:[{id:'p1',name:'Projeto igual',path:'/synthetic/one'},{id:'p2',name:'Projeto igual',path:'/synthetic/two'}],executions:[{id:'e1',title:'Execução igual',source:'alethe',project_id:'p1',leader_id:'lead',leader_name:'Líder',status:'running',started_at:'2026-01-02'},{id:'e2',title:'Execução igual',source:'claude',project_id:'p1',status:'unknown'},{id:'e3',title:'Execução igual',source:'codex',project_id:'p2',status:'unknown'}],agents:[makeAgent('lead'),...Array.from({length:8},(_,i)=>makeAgent(`w${i}`)),makeAgent('other','e2'),makeAgent('foreign','e3')],events:[{id:'old',kind:'delegated',execution_id:'e1',actor_id:'lead',target_id:'w0',evidence:'registro sintético'}],totals:{projects:2,executions:3,agents:11,running:9},diagnostics:[{source:'claude',status:'unavailable',message:'raiz sintética ausente',path:'/synthetic/missing'}]};
const details=[];
let browser;
try{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE});
 const page=await browser.newPage({viewport:{width:1440,height:1100},reducedMotion:'no-preference'});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://alethe.test/**',async route=>{
  const url=new URL(route.request().url());
  if(url.pathname==='/api/snapshot')return route.fulfill({status:offline?503:200,contentType:'application/json',body:JSON.stringify(snap)});
  if(url.pathname==='/api/detail'){details.push([url.searchParams.get('agent'),url.searchParams.get('kind')]);return route.fulfill({contentType:'application/json',body:JSON.stringify({text:'<script>window.injected=true</script>\n\u001b[31mPUBLIC\u001b[0m<think>PRIVATE</think>'})});}
  const name=url.pathname==='/'?'index.html':url.pathname.replace('/assets/','');
  if(!['index.html','app.js','styles.css','state.mjs','scene.mjs'].includes(name))return route.fulfill({status:404,body:''});
  return route.fulfill({contentType:name.endsWith('.css')?'text/css':name.endsWith('.html')?'text/html':'text/javascript',body:await readFile(new URL(name,root))});
 });
 await page.goto('http://alethe.test/?view=office');
 await page.waitForSelector('.sprite');
 assert.equal(await page.locator('.sprite').count(),7);
 assert.equal(await page.locator('#scene .interactions > g').count(),0,'history does not animate');
 assert.match(await page.locator('#office-count').textContent(),/8 workers/);
 await page.locator('#next').click();assert.equal(await page.locator('.sprite').count(),3);
 await page.locator('.sprite[data-agent-id="w7"]').click();
 await page.locator('[data-view="panel"]').click();
 assert.match(await page.locator('#detail-name').textContent(),/w7/);
 await page.waitForFunction(()=>document.getElementById('output').textContent.includes('PUBLIC'));
 assert.equal(await page.locator('#output script').count(),0);assert.equal(await page.evaluate(()=>window.injected),undefined);
 assert.doesNotMatch(await page.locator('#output').textContent(),/PRIVATE|\x1b/);
 await page.locator('[data-kind="result"]').click();await page.waitForTimeout(150);assert.ok(details.some(([id,kind])=>id==='w7'&&kind==='result'));
 await page.locator('[data-view="office"]').click();assert.match(await page.locator('#page-label').textContent(),/2 \/ 2/);
 await page.locator('#previous').click();
 snap.events.push({id:'new',kind:'delegated',execution_id:'e1',actor_id:'lead',target_id:'w0',evidence:'registro sintético'});
 await page.locator('#refresh').click();await page.waitForSelector('.packet');
 await page.waitForTimeout(2500);assert.equal(await page.locator('.packet').count(),0);
 await page.locator('#refresh').click();await page.waitForTimeout(150);assert.equal(await page.locator('.packet').count(),0,'same event is not replayed');
 snap.events.push({id:'available',kind:'result_available',execution_id:'e1',actor_id:'w0',target_id:'lead',evidence:'registro sintético'});
 await page.locator('#refresh').click();await page.waitForFunction(()=>document.getElementById('last-event').textContent.includes('resultado disponível'));
 assert.equal(await page.locator('.packet').count(),0,'availability never delivers');
 await page.selectOption('#project','p2');assert.match(await page.locator('#focus-label').textContent(),/e3/);
 await page.selectOption('#project','p1');await page.selectOption('#execution','e1');assert.match(await page.locator('#detail-name').textContent(),/w7/);
 // Replace, do not append characters from previous snapshots.
 snap.agents=[makeAgent('lead'),makeAgent('replacement')];await page.locator('#refresh').click();await page.waitForFunction(()=>document.querySelectorAll('.sprite').length===2);
 for(const width of [1000,720,390]){await page.setViewportSize({width,height:1000});await page.waitForTimeout(80);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`no horizontal page overflow at ${width}`);}
 await page.setViewportSize({width:1440,height:1100});
 if(process.env.SMOKE_SCREENSHOT)await page.screenshot({path:process.env.SMOKE_SCREENSHOT,fullPage:true});
 offline=true;await page.locator('#refresh').click();await page.waitForSelector('body.disconnected');assert.match(await page.locator('#connection').textContent(),/última leitura válida/);assert.equal(await page.locator('.sprite').count(),2);
 assert.deepEqual(errors,[]);console.log('PASS: context, pagination, safe detail endpoints, one-shot events, replacement, disconnect and 4 viewport sizes');
}finally{await browser?.close();}
