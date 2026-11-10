import {spawn} from 'node:child_process';
import {readFile,mkdtemp,writeFile,mkdir,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE);
const root=process.cwd(),temp=await mkdtemp(path.join(tmpdir(),'alethe-live-check-')),infoPath=path.join(temp,'session.json');
const processServer=spawn(path.join(root,'.venv/bin/python'),['tests/web/serve_fixture.py',infoPath],{env:{...process.env,PYTHONPATH:path.join(root,'src')},stdio:['ignore','ignore','inherit']});
let browser;
try{
 let info;for(let n=0;n<100;n++){try{info=JSON.parse(await readFile(infoPath,'utf8'));break}catch{}await new Promise(r=>setTimeout(r,50))}assert.ok(info,'servidor iniciou');
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE});
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(info.url);await page.waitForSelector('.sprite');
 assert.equal(await page.title(),'Agent Watch · monitor de agentes');
 assert.equal(await page.locator('.brand').textContent(),'AGENT WATCH');
 assert.ok((await page.locator('#scene').textContent()).includes('AGENT WATCH'));
 const snap=await page.evaluate(async()=>await (await fetch('/api/snapshot')).json());
 assert.deepEqual([...new Set(snap.agents.map(a=>a.source))].sort(),['alethe','claude','codex']);assert.equal(snap.projects.length,2);assert.equal(snap.executions.length,3);
 assert.match(await page.locator('#connection').textContent(),/DEMONSTRAÇÃO/);
 const selected=await page.locator('#detail-name').textContent();await page.locator('[data-view="panel"]').click();assert.equal(await page.locator('#detail-name').textContent(),selected);
 const backgrounds=[];
 for(const theme of ['aura','light','current']){
  await page.selectOption('#theme',theme);
  backgrounds.push(await page.evaluate(()=>getComputedStyle(document.body).backgroundColor));
  await page.reload();await page.waitForSelector('.sprite',{state:'attached'});
  assert.equal(await page.locator('#theme').inputValue(),theme);
  assert.equal(await page.locator('#detail-name').textContent(),selected);
  await page.locator('[data-view="office"]').click();
  const floor=await page.locator('#scene pattern rect').evaluate(el=>getComputedStyle(el).fill);
  assert.ok(floor.startsWith('rgb('));
  if(process.env.THEME_SCREENSHOTS){await page.screenshot({path:path.join(process.env.THEME_SCREENSHOTS,`${theme}-office.png`),fullPage:true});await page.locator('[data-view="panel"]').click();await page.screenshot({path:path.join(process.env.THEME_SCREENSHOTS,`${theme}-panel.png`),fullPage:true});}
 }
 assert.equal(new Set(backgrounds).size,3,'três fundos distintos');
 await page.locator('[data-view="office"]').click();
 const group=snap.executions.find(e=>e.source==='alethe');await page.selectOption('#execution',group.id);
 const wave=path.join(info.root,'alethe/demonstracao/02-extra');await mkdir(wave,{recursive:true});
 const timestamp=new Date().toISOString();
 await writeFile(path.join(wave,'plan.json'),JSON.stringify({workers:[{id:'new-worker',task:'Nova tarefa sintética'}]}));
 await writeFile(path.join(wave,'state.json'),JSON.stringify({status:'running',startedAt:timestamp,workers:{'new-worker':{status:'running',startedAt:timestamp,cwd:snap.executions.find(e=>e.source==='alethe').project_path}}}));
 await page.waitForFunction(async()=>{const s=await(await fetch('/api/snapshot')).json();return s.agents.some(a=>a.source_id==='new-worker')},null,{timeout:5000});
 await page.waitForFunction(()=>document.getElementById('last-event').textContent.includes('delegou'),null,{timeout:5000});
 await page.locator('[data-view="panel"]').click();await page.waitForSelector('[data-select-agent]');
 assert.equal(await page.locator('#agents button').count(),8);
 assert.deepEqual(errors,[]);
 if(process.env.SMOKE_SCREENSHOT)await page.screenshot({path:process.env.SMOKE_SCREENSHOT,fullPage:true});
 console.log('PASS: Agent Watch, três temas persistentes, HTTP real, três leitores, múltiplos projetos, troca de interface e descoberta/evento de nova onda em até 5s.');
}finally{await browser?.close();processServer.kill('SIGTERM');await new Promise(r=>processServer.once('exit',r));await rm(temp,{recursive:true,force:true})}
