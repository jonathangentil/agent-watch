import test from 'node:test';
import assert from 'node:assert/strict';
import {MonitorState} from '../../src/alethe_tui/web/state.mjs';
import {buildScene,animateEvent,identityColor} from '../../src/alethe_tui/web/scene.mjs';
// Minimal inert SVG DOM: no browser dependency; actual layout is checked by browser-smoke.mjs.
class Node {
 constructor(tag){this.tag=tag;this.attributes={};this.children=[];this.style={};this.listeners={};this.dataset={};this.textContent='';this.classList={add:c=>this.setAttribute('class',`${this.attributes.class||''} ${c}`),remove:c=>this.setAttribute('class',(this.attributes.class||'').split(' ').filter(x=>x!==c).join(' '))};}
 setAttribute(k,v){this.attributes[k]=v;if(k==='data-agent-id')this.dataset.agentId=v;}
 append(...nodes){this.children.push(...nodes);for(const node of nodes)node.parent=this;}
 remove(){this.parent.children=this.parent.children.filter(n=>n!==this);}
 addEventListener(type,fn){this.listeners[type]=fn;}
 querySelectorAll(selector){const matches=n=>selector.startsWith('.')?(n.attributes.class||'').split(' ').includes(selector.slice(1)):n.tag===selector;return this.children.flatMap(n=>[...(matches(n)?[n]:[]),...n.querySelectorAll(selector)]);}
 set innerHTML(_){throw new Error('Active markup prohibited');}
}
const fixture=()=>({version:1,connected:true,totals:{},projects:[{id:'p'}],executions:[{id:'e',project_id:'p',leader_id:'lead',leader_name:'principal'}],agents:[{id:'lead',execution_id:'e',status:'unknown'},...Array.from({length:8},(_,i)=>({id:`a${i}`,execution_id:'e',source:'codex',name:i===0?'<script>unsafe</script>':`agente ${i}`,status:i===0?'running':'unknown'}))],events:[],diagnostics:[]});
function setup(){globalThis.document={createElementNS:(_,tag)=>new Node(tag)};const state=new MonitorState();state.apply(fixture());return state;}
test('SVG contains all current workers and one separate leader; click selects the exact ID',()=>{const state=setup();let selected;const scene=buildScene(state,id=>selected=id);const sprites=scene.root.querySelectorAll('.sprite');assert.equal(sprites.length,9);assert.equal(scene.positions.size,9);assert.equal(sprites.filter(n=>(n.attributes.class||'').includes('running')).length,1);sprites.find(n=>n.dataset.agentId==='a0').listeners.click();assert.equal(selected,'a0');const title=sprites.find(n=>n.dataset.agentId==='a0').querySelectorAll('title')[0];assert.match(title.textContent,/<script>unsafe<\/script>/);assert.equal(title.children.length,0);});
test('room grows for every worker and replaced snapshots do not accumulate sprites',()=>{const state=setup();const initial=buildScene(state,()=>{});assert.equal(initial.root.querySelectorAll('.sprite').length,9);assert.equal(initial.root.attributes.viewBox,'0 0 960 680');const wider=buildScene(state,()=>{},4);assert.equal(wider.root.attributes.viewBox,'0 0 1190 500');assert.equal(wider.positions.size,9);state.apply({...fixture(),agents:[{id:'new',execution_id:'e',status:'unknown'}]});const scene=buildScene(state,()=>{});assert.deepEqual([...scene.positions.keys()],['lead','new']);assert.equal(scene.root.querySelectorAll('.running').length,0);assert.equal(identityColor('new'),identityColor('new'));});
test('only an interaction draws a delivery packet; missing endpoints and reduced motion do not',t=>{t.mock.timers.enable({apis:['setTimeout']});const scene=buildScene(setup(),()=>{});animateEvent(scene,{actor_id:'lead',target_id:'a0',effect:'interaction',kind:'delegated'});assert.equal(scene.overlay.querySelectorAll('.packet').length,1);t.mock.timers.tick(2400);assert.equal(scene.overlay.children.length,0);animateEvent(scene,{actor_id:'lead',target_id:'missing',effect:'interaction',kind:'message'});animateEvent(scene,{actor_id:'lead',target_id:'a0',effect:'interaction',kind:'message'},true);assert.equal(scene.overlay.children.length,0);});
test('result availability signals only its actor and never draws a delivery',t=>{t.mock.timers.enable({apis:['setTimeout']});const scene=buildScene(setup(),()=>{});animateEvent(scene,{actor_id:'a0',target_id:'lead',effect:'completion',kind:'result_available'});assert.equal(scene.root.querySelectorAll('.result').length,1);assert.equal(scene.overlay.children.length,0);t.mock.timers.tick(2200);assert.equal(scene.root.querySelectorAll('.result').length,0);});
test('generic orchestrator without a recorded identity never claims active work',()=>{const state=setup();const snapshot=fixture();snapshot.executions[0]={id:'e',project_id:'p',leader_status:'running'};snapshot.agents=[];state.apply(snapshot);const scene=buildScene(state,()=>{});assert.equal(scene.root.querySelectorAll('.running').length,0);assert.equal(scene.positions.size,0);assert.match(scene.root.querySelectorAll('title')[0].textContent,/identidade não informada.*estado não confirmado/);});

test('worker hover exposes model, effort, wave and task with missing values explicit',()=>{
 const state=setup();const data=fixture();
 Object.assign(data.agents[1],{name:'Developer',model:'example-model',effort:'high',wave:'03-build',source_id:'task-8',task:'Implement endpoint'});
 state.apply(data);const scene=buildScene(state,()=>{});
 const title=scene.root.querySelectorAll('.sprite').find(n=>n.dataset.agentId==='a0').querySelectorAll('title')[0].textContent;
 for(const expected of ['example-model','high','03-build','task-8','Implement endpoint'])assert.ok(title.includes(expected));
 const missing=scene.root.querySelectorAll('.sprite').find(n=>n.dataset.agentId==='a1').querySelectorAll('title')[0].textContent;
 assert.match(missing,/Modelo: não informado/);assert.match(missing,/Effort: não informado/);
 assert.ok(scene.root.querySelectorAll('text').some(n=>n.textContent.includes('03-build')));
});
