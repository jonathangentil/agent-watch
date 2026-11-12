// Optional browser verification; uses an already installed Playwright + Chromium.
// PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs CHROMIUM_EXECUTABLE=/absolute/path/to/chrome node tests/web/browser-smoke.mjs
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE);
const root=new URL('../../src/alethe_tui/web/',import.meta.url);
let offline=false;
const makeAgent=(id,execution_id='e1',extra={})=>({id,source_id:id,execution_id,name:id,project_id:'p1',source:'codex',task:'<img src=x onerror=alert(1)>',model:'modelo de teste',effort:'high',wave:'03-build',status:'running',evidence:'evento sintético',...extra});
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
  if(!['index.html','app.js','styles.css','themes.css','events.css','theme.mjs','state.mjs','scene.mjs','board.mjs','kanban.mjs','kanban.css','timeline.mjs','replay.mjs'].includes(name))return route.fulfill({status:404,body:''});
  return route.fulfill({contentType:name.endsWith('.css')?'text/css':name.endsWith('.html')?'text/html':'text/javascript',body:await readFile(new URL(name,root))});
 });
 await page.goto('http://alethe.test/?view=office');
 await page.waitForSelector('.sprite');
 assert.equal(await page.locator('#office-runs').isVisible(),true,'office has an execution sidebar');
 assert.equal(await page.locator('#office-runs button').count(),3);
 assert.match(await page.locator('.sprite[data-agent-id="w0"] title').textContent(),/modelo de teste[\s\S]*high/);
 assert.equal(await page.locator('.sprite').count(),9);
 assert.equal(await page.locator('#scene .interactions > g').count(),0,'history does not animate');
 assert.match(await page.locator('#office-count').textContent(),/8 workers/);
 assert.equal(await page.locator('#next').count(),0,'no pagination');
 await page.locator('.sprite[data-agent-id="w7"]').click();
 await page.locator('[data-view="panel"]').click();
 assert.match(await page.locator('#detail-name').textContent(),/w7/);
 assert.ok((await page.locator('#output').boundingBox()).height>=400,'output block is taller without increasing font size');
 assert.equal(await page.locator('#output').evaluate(el=>getComputedStyle(el).fontSize),'11px');
 assert.match(await page.locator('#run-tokens').textContent(),/não informado/);
 snap.agents.find(a=>a.id==='w0').tokens=1200;
 await page.locator('#refresh').click();
 await page.waitForFunction(()=>document.getElementById('run-tokens').textContent.includes('1.200'));
 assert.match(await page.locator('#run-tokens').textContent(),/parcial/);
 assert.match(await page.locator('#agents tr').filter({has:page.locator('[data-select-agent="w0"]')}).textContent(),/1.200/);
 await page.locator('#agents tr').filter({has:page.locator('[data-select-agent="w6"]')}).locator('td').nth(2).click();
 assert.match(await page.locator('#detail-name').textContent(),/w6/,'whole row selects agent');
 await page.locator('[data-select-agent="w7"]').click();
 await page.waitForFunction(()=>document.getElementById('output').textContent.includes('PUBLIC'));
 assert.equal(await page.locator('#output script').count(),0);assert.equal(await page.evaluate(()=>window.injected),undefined);
 assert.doesNotMatch(await page.locator('#output').textContent(),/PRIVATE|\x1b/);
 await page.locator('#agent-details [data-kind="result"]').click();await page.waitForTimeout(150);assert.ok(details.some(([id,kind])=>id==='w7'&&kind==='result'));
 await page.locator('[data-view="office"]').click();assert.match(await page.locator('#visible-count').textContent(),/8 agentes/);
 snap.events.push({id:'new',kind:'delegated',execution_id:'e1',actor_id:'lead',target_id:'w0',evidence:'registro sintético'});
 await page.locator('#refresh').click();await page.waitForSelector('.packet');
 assert.equal(await page.locator('.packet .envelope-body').count(),1);
 assert.equal(await page.locator('.packet').evaluate(el=>getComputedStyle(el).animationIterationCount),'3');
 const before=await page.locator('.packet').boundingBox();await page.waitForTimeout(350);
 const after=await page.locator('.packet').boundingBox();assert.ok(Math.abs(after.x-before.x)+Math.abs(after.y-before.y)>5,'letter moves along the route');
 if(process.env.MAIL_SCREENSHOT)await page.screenshot({path:process.env.MAIL_SCREENSHOT,fullPage:true});
 await page.waitForFunction(()=>!document.querySelector('.packet'),null,{timeout:6000});
 assert.equal(await page.locator('.interaction-line').count(),0,'route disappears after three passes');
 await page.locator('#refresh').click();await page.waitForTimeout(150);assert.equal(await page.locator('.packet').count(),0,'same event is not replayed');
 snap.events.push({id:'available',kind:'result_available',execution_id:'e1',actor_id:'w0',target_id:'lead',evidence:'registro sintético'});
 await page.locator('#refresh').click();await page.waitForFunction(()=>document.getElementById('last-event').textContent.includes('resultado disponível'));
 assert.equal(await page.locator('.packet').count(),0,'availability never delivers');
 assert.equal(await page.locator('.completion-envelope').count(),1,'availability shows a letter at its actor');
 await page.waitForFunction(()=>!document.querySelector('.completion-envelope'),null,{timeout:6000});
 snap.events.push({id:'delivered',kind:'result_delivered',execution_id:'e1',actor_id:'w0',target_id:'lead',evidence:'registro sintético'});
 await page.locator('#refresh').click();await page.waitForSelector('.packet');
 const route=await page.locator('.packet').evaluate(el=>el.style.offsetPath);
 assert.match(route,/M\s*321\s+232/,'return starts at the worker');assert.ok(route.includes('105 286'),'return ends at the leader');
 await page.locator('#event-mail').uncheck();assert.equal(await page.locator('.interactions > g').count(),0,'hide immediately removes current letters and paths');
 snap.events.push({id:'hidden',kind:'delegated',execution_id:'e1',actor_id:'lead',target_id:'w0',evidence:'registro sintético'});
 await page.locator('#refresh').click();await page.waitForFunction(()=>document.getElementById('last-event').textContent.includes('delegou tarefa'));
 assert.equal(await page.locator('.packet').count(),0,'hidden effects do not animate new events');
 await page.reload();await page.waitForSelector('.sprite');assert.equal(await page.locator('#event-mail').isChecked(),false,'visibility preference survives reload');
 await page.locator('#event-mail').check();assert.equal(await page.locator('.packet').count(),0,'enabling does not replay hidden or historical events');
 snap.events.push({id:'reduced',kind:'delegated',execution_id:'e1',actor_id:'lead',target_id:'w0',evidence:'registro sintético'});
 await page.locator('#reduce').check();await page.locator('#refresh').click();await page.waitForTimeout(200);assert.equal(await page.locator('.packet').count(),0,'reduced motion hides mail');
 await page.locator('#reduce').uncheck();
 // Active-only applies to both sidebars and the execution picker, including empty results.
 const initialAgents=snap.agents;
 snap.agents=snap.agents.map(a=>a.execution_id==='e1'?a:{...a,status:'turn_complete'});
 await page.locator('#refresh').click();await page.locator('#active').check();
 await page.waitForFunction(()=>document.querySelectorAll('#office-runs button').length===1);
 for(const id of ['runs','office-runs'])assert.equal(await page.locator(`#${id} button`).count(),1);
 assert.equal(await page.locator('#execution option').count(),1);
 const initialExecutions=snap.executions;
 snap.executions=snap.executions.map(e=>({...e,status:'succeeded'}));
 snap.agents=snap.agents.map(a=>({...a,status:'succeeded'}));
 await page.locator('#refresh').click();await page.waitForFunction(()=>document.querySelectorAll('#office-runs button').length===0);
 assert.equal(await page.locator('#runs button').count(),0);
 assert.equal(await page.locator('#execution').inputValue(),'');
 snap.agents=initialAgents;snap.executions=initialExecutions;
 await page.locator('#active').uncheck();await page.locator('#refresh').click();
 await page.waitForFunction(()=>document.querySelectorAll('#office-runs button').length===3);
 await page.selectOption('#source','alethe');
 assert.equal(await page.locator('#office-runs button').count(),1,'sidebar follows source');
 assert.equal(await page.locator('#runs button').count(),1,'panel sidebar follows source');
 await page.selectOption('#source','all');
 await page.selectOption('#project','p2');assert.match(await page.locator('#focus-label').textContent(),/e3/);
 await page.selectOption('#project','p1');await page.selectOption('#execution','e1');assert.match(await page.locator('#detail-name').textContent(),/w7/);
 // A long execution list must paginate inside each view's content height.
 snap.executions.push(...Array.from({length:24},(_,i)=>({id:`extra-${i}`,title:`Long execution title ${i} with multiple lines of descriptive context`,source:'alethe',project_id:'p1',status:'succeeded'})));
 await page.locator('#refresh').click();
 await page.waitForFunction(()=>document.querySelectorAll('#office-runs .run').length>20);
 for(const view of ['office','panel']){
  await page.locator(`[data-view="${view}"]`).click();
  const nav=view==='office'?'office-runs':'runs',pager=`${view}-run-pages`;
  await page.waitForFunction(id=>{const p=document.getElementById(id);return p&&!p.querySelector('[data-page-next]').disabled},pager);
  const size=await page.evaluate(view=>{const aside=document.querySelector(view==='office'?'#office-layout>aside':'#panel aside'),content=document.querySelector(view==='office'?'#office':'.panel-main');return {sidebar:aside.getBoundingClientRect().height,content:content.getBoundingClientRect().height}},view);
  assert.ok(size.sidebar<=size.content+1,`${view} sidebar must fit content`);
  const before=await page.locator(`#${nav} .run:visible`).first().textContent();
  const selected=await page.locator('#execution').inputValue();
  await page.locator(`#${pager} [data-page-next]`).click();
  assert.notEqual(await page.locator(`#${nav} .run:visible`).first().textContent(),before);
  assert.equal(await page.locator('#execution').inputValue(),selected,'paging does not change execution');
  const first=await page.locator(`#${nav} .run:visible`).first().textContent();
  await page.locator('#refresh').click();await page.waitForTimeout(100);
  assert.equal(await page.locator(`#${nav} .run:visible`).first().textContent(),first,'polling preserves page');
  await page.locator(`#${nav} .run:visible`).first().click();
  assert.notEqual(await page.locator('#execution').inputValue(),selected);
 }
 await page.locator('[data-view="office"]').click();await page.selectOption('#execution','e1');
 // Replace, do not append characters from previous snapshots.
 snap.agents=[makeAgent('lead'),makeAgent('replacement')];await page.locator('#refresh').click();await page.waitForFunction(()=>document.querySelectorAll('.sprite').length===2);
 for(const width of [1000,720,390]){
  await page.setViewportSize({width,height:1000});await page.waitForTimeout(80);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`no horizontal page overflow at ${width}`);
  for(const view of ['office','panel']){
   await page.locator(`[data-view="${view}"]`).click();
   const size=await page.evaluate(view=>({sidebar:document.querySelector(view==='office'?'#office-layout>aside':'#panel aside').getBoundingClientRect().height,content:document.querySelector(view==='office'?'#office':'.panel-main').getBoundingClientRect().height}),view);
   assert.ok(size.sidebar<=size.content+1,`${view} sidebar fits content at ${width}`);
  }
  await page.locator('[data-view="office"]').click();
 }
 await page.setViewportSize({width:1440,height:1100});
 if(process.env.SMOKE_SCREENSHOT)await page.screenshot({path:process.env.SMOKE_SCREENSHOT,fullPage:true});
 offline=true;await page.locator('#refresh').click();await page.waitForSelector('body.disconnected');assert.match(await page.locator('#connection').textContent(),/última leitura válida/);assert.equal(await page.locator('.sprite').count(),2);
 assert.deepEqual(errors,[]);console.log('PASS: context, all workers in one room, sidebar filters, row selection, safe detail endpoints, one-shot events, replacement, disconnect and 4 viewport sizes');
}finally{await browser?.close();}
