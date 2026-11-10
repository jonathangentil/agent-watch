import test from 'node:test';
import assert from 'node:assert/strict';
import {MonitorState} from '../../src/alethe_tui/web/state.mjs';

test('late historical discoveries never animate; proven new events animate once',()=>{
 const state=new MonitorState();
 const snapshot={version:1,connected:true,agents:[{id:'worker',execution_id:'run',source:'codex',status:'running'}],executions:[{id:'run',project_id:'p',leader_id:'lead'}],projects:[{id:'p'}],diagnostics:[],totals:{},events:[]};
 state.apply(snapshot);
 const event={id:'historical',kind:'delegated',execution_id:'run',actor_id:'lead',target_id:'worker',evidence:'metadata',is_live:false};
 assert.deepEqual(state.apply({...snapshot,events:[event]}),[]);
 const live={...event,id:'new',is_live:true};
 assert.equal(state.apply({...snapshot,events:[event,live]}).length,1);
 assert.deepEqual(state.apply({...snapshot,events:[event,live]}),[]);
});
