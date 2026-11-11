import test from 'node:test';
import assert from 'node:assert/strict';
import {MonitorState, safeText, stateLabel, elapsed, runPages, executionTokens} from '../../src/alethe_tui/web/state.mjs';
const agent = (id, execution_id='e1', extra={}) => ({id,name:'mesmo nome',execution_id,project_id:'p1',source:'codex',status:'running',...extra});
const event = (id, kind='delegated', extra={}) => ({id,kind,execution_id:'e1',actor_id:'lead',target_id:'a',evidence:'registro público',...extra});
const snapshot = (extra={}) => ({version:1,connected:true,projects:[{id:'p1',name:'igual'},{id:'p2',name:'igual'}],executions:[{id:'e1',project_id:'p1',title:'igual',leader_id:'lead',status:'running',started_at:'2026-01-01'},{id:'e2',project_id:'p1',title:'igual',status:'running',started_at:'2026-02-01'},{id:'e3',project_id:'p2',title:'igual',status:'unknown'}],agents:[agent('a'),agent('b','e2'),agent('c','e3')],events:[],totals:{projects:2,executions:3,agents:3,running:3},diagnostics:[],...extra});
test('initial focus is most recent active execution; identical names remain distinct',()=>{const s=new MonitorState();s.apply(snapshot());assert.equal(s.executionId,'e2');assert.equal(s.executions().length,3);s.selectProject('p1');assert.deepEqual(s.executions().map(e=>e.id),['e1','e2']);s.selectProject('p2');assert.equal(s.executionId,'e3');assert.equal(s.snapshot.totals.agents,3);});
test('selection by ID survives reorder, polling, view changes and execution round trips',()=>{const s=new MonitorState();s.apply(snapshot({agents:[agent('a'),agent('d'),agent('b','e2')]}));s.selectExecution('e1');s.selectAgent('d');s.setView('office');s.selectExecution('e2');s.selectExecution('e1');s.apply(snapshot({agents:[agent('d'),agent('a'),agent('b','e2')]}));assert.equal(s.agentId,'d');assert.equal(s.view,'office');const restored=new MonitorState(s.context());restored.apply(s.snapshot);assert.equal(restored.agentId,'d');});
test('new execution never steals existing focus and removed IDs recover safely',()=>{const s=new MonitorState();s.apply(snapshot());s.apply(snapshot({executions:[...snapshot().executions,{id:'new',project_id:'p1',status:'running',started_at:'2027-01-01'}]}));assert.equal(s.executionId,'e2');s.apply(snapshot({executions:[snapshot().executions[0]],agents:[agent('z')]}));assert.equal(s.executionId,'e1');assert.equal(s.agentId,'z');});
test('multiproject execution is visible under either project',()=>{const s=new MonitorState();s.apply(snapshot({executions:[{id:'multi',project_id:'p1',project_ids:['p1','p2']}]}));s.selectProject('p2');assert.equal(s.executionId,'multi');});
test('all filtered workers are available in one room and leader is excluded',()=>{const s=new MonitorState();s.apply(snapshot({agents:[agent('lead'),...Array.from({length:14},(_,i)=>agent(`w${i}`))]}));s.selectExecution('e1');assert.equal(s.workers().length,14);assert.equal(s.visibleAgents().length,14);s.selectAgent('w7');assert.equal(s.agentId,'w7');s.apply(snapshot({agents:[agent('only')]}));assert.deepEqual(s.visibleAgents().map(a=>a.id),['only']);});
test('filters preserve hidden selected ID',()=>{const s=new MonitorState();s.apply(snapshot({agents:[agent('a'),agent('done','e1',{status:'succeeded',source:'claude'})]}));s.selectExecution('e1');s.selectAgent('done');s.setFilters({source:'codex',active:true,search:'mesmo'});assert.equal(s.agentId,'done');assert.deepEqual(s.visibleAgents().map(a=>a.id),['a']);s.setFilters({source:'all',active:false,search:''});assert.equal(s.agentId,'done');});
test('historical first snapshot suppressed; event IDs never replay across polling or view changes',()=>{const s=new MonitorState();assert.deepEqual(s.apply(snapshot({events:[event('old')]})),[]);assert.deepEqual(s.apply(snapshot({events:[event('old'),event('new'),event('new')]})).map(e=>e.id),['new']);s.setView('office');assert.deepEqual(s.apply(snapshot({events:[event('new')]})),[]);s.apply(snapshot());assert.deepEqual(s.apply(snapshot({events:[event('old')]})),[]);});
test('interactions require evidence and identifiable endpoints in same execution',()=>{const s=new MonitorState();s.apply(snapshot());const events=[event('valid'),event('message','message',{actor_id:'a',target_id:'lead'}),event('delivery','result_delivered',{actor_id:'a',target_id:'lead'}),event('missing','message',{target_id:null}),event('foreign','message',{target_id:'b'}),event('unproven','delegated',{evidence:''}),event('tool','tool'),event('future','invented')];assert.deepEqual(s.apply(snapshot({events})).map(e=>e.id),['valid','message','delivery']);});
test('result_available only signals actor completion, never delivery',()=>{const s=new MonitorState();s.apply(snapshot());const [e]=s.apply(snapshot({events:[event('available','result_available',{actor_id:'a',target_id:null})]}));assert.equal(e.effect,'completion');assert.equal(e.kind,'result_available');});
test('disconnection retains last valid snapshot and does not reset event cursor',()=>{const s=new MonitorState();s.apply(snapshot({events:[event('old')]}));s.disconnect();assert.equal(s.connected,false);assert.equal(s.snapshot.agents.length,3);assert.throws(()=>s.apply({version:2}),/snapshot/i);assert.deepEqual(s.apply(snapshot({events:[event('old')]})),[]);assert.equal(s.connected,true);});
test('unconfirmed states and missing timing are explicit',()=>{assert.match(stateLabel('unknown'),/não confirmado/);assert.match(stateLabel('new_state'),/new_state/);assert.equal(elapsed(null), 'não informado');assert.equal(elapsed('2026-01-01T00:00:00Z','2026-01-01T00:01:05Z'),'1m 05s');});
test('source strings are inert; terminal controls and private thinking are removed',()=>{assert.equal(safeText('\u001b[31m<img onerror=alert(1)>\u001b[0m\u0000'),'<img onerror=alert(1)>');assert.equal(safeText('public<think>private</think> ok'),'public[conteúdo interno oculto] ok');assert.equal(safeText('x<thinking>unfinished'),'x[conteúdo interno oculto]');});

test('source filters available executions and reconciles focus including mixed executions',()=>{
 const s=new MonitorState();
 s.apply(snapshot({executions:[
  {id:'e1',source:'alethe',project_id:'p1'},
  {id:'e2',source:'claude',project_id:'p1'},
  {id:'e3',source:'codex',project_id:'p2'},
 ],agents:[agent('a','e1',{source:'alethe'}),agent('child','e1',{source:'codex'}),agent('b','e2',{source:'claude'}),agent('c','e3')]}));
 s.setFilters({source:'alethe'});
 assert.deepEqual(s.executions().map(e=>e.id),['e1']);assert.equal(s.executionId,'e1');
 s.setFilters({source:'codex'});
 assert.deepEqual(s.executions().map(e=>e.id),['e1','e3']);
 s.setFilters({source:'claude'});
 assert.deepEqual(s.executions().map(e=>e.id),['e2']);assert.equal(s.executionId,'e2');
 s.setFilters({source:'all'});assert.equal(s.executions().length,3);
});

test('execution pages fit variable title heights without dropping entries',()=>{
 assert.deepEqual(runPages([80,120,70,60],200),[{start:0,end:2},{start:2,end:4}]);
 assert.deepEqual(runPages([80,120,70,60],130),[{start:0,end:1},{start:1,end:2},{start:2,end:4}]);
 assert.deepEqual(runPages([80,120,70,60],500),[{start:0,end:4}]);
 assert.deepEqual(runPages([],100),[{start:0,end:0}]);
});

test('orchestration token totals use all canonical agents and qualify missing metrics',()=>{
 const data=snapshot({agents:[agent('lead','e1',{tokens:10}),agent('a','e1',{tokens:100}),agent('a','e1',{tokens:100}),agent('b','e1',{tokens:0}),agent('foreign','e2',{tokens:999})]});
 assert.deepEqual(executionTokens(data,'e1'),{total:110,reported:3,agents:3,partial:false,leaderReported:true});
 data.agents.push(agent('unknown','e1',{tokens:null}));
 const partial=executionTokens(data,'e1');assert.equal(partial.total,110);assert.equal(partial.partial,true);assert.equal(partial.reported,3);
 data.agents=[agent('unknown','e1',{tokens:null})];
 assert.equal(executionTokens(data,'e1').total,null);
 data.agents=[agent('known','e1',{tokens:5,tokens_partial:true})];
 assert.equal(executionTokens(data,'e1').partial,true);
 assert.equal(executionTokens(data,'e1').leaderReported,false);
});

test('active-only filters executions by confirmed activity and reconciles hidden focus',()=>{
 const s=new MonitorState();
 const data=snapshot({executions:[
  {id:'running',source:'alethe',project_id:'p1',status:'running'},
  {id:'done',source:'alethe',project_id:'p1',status:'succeeded'},
  {id:'unknown',source:'codex',project_id:'p1',status:'unknown'},
  {id:'native',source:'codex',project_id:'p1',status:'unknown'},
  {id:'queued',source:'alethe',project_id:'p1',status:'queued'},
  {id:'failed',source:'alethe',project_id:'p1',status:'failed'},
 ],agents:[agent('finished','done',{status:'succeeded'}),agent('uncertain','unknown',{status:'unknown'}),agent('busy','native',{status:'running'})]});
 s.apply(data);s.selectExecution('done');s.setFilters({active:true});
 assert.deepEqual(s.executions().map(e=>e.id),['running','native','queued']);
 assert.equal(s.executionId,'running');
 s.setFilters({source:'codex'});assert.deepEqual(s.executions().map(e=>e.id),['native']);
 const ended={...data,executions:data.executions.map(e=>({...e,status:'succeeded'})),agents:data.agents.map(a=>({...a,status:'turn_complete'}))};
 s.apply(ended);assert.deepEqual(s.executions(),[]);assert.equal(s.executionId,'');
 s.setFilters({source:'all',active:false});assert.equal(s.executions().length,6);
});

test('active-only combined with source requires activity in that source for mixed executions',()=>{
 const s=new MonitorState();
 s.apply(snapshot({executions:[{id:'mixed',source:'alethe',project_id:'p1',status:'unknown'}],
  agents:[agent('done','mixed',{source:'claude',status:'turn_complete'}),agent('busy','mixed',{source:'codex',status:'running'})]}));
 s.setFilters({active:true,source:'claude'});assert.equal(s.executions().length,0);
 s.setFilters({source:'codex'});assert.deepEqual(s.executions().map(e=>e.id),['mixed']);
});
