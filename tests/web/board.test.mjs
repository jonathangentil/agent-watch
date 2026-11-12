import test from 'node:test';
import assert from 'node:assert/strict';
import {COLUMNS, TEST_COLUMNS, badgeLabel, pipelineActive, testerLabel, taskTitle, columnMap, planMoves} from '../../src/alethe_tui/web/board.mjs';

const task=(id,column)=>({id,column});

test('columns are exact and ordered',()=>{
  assert.deepEqual(COLUMNS,[['backlog','Backlog'],['in_progress','Em progresso'],['awaiting_tests','Aguardando testes'],['testing','Em testes'],['done','Pronto'],['blocked','Bloqueado']]);
  assert.deepEqual([...TEST_COLUMNS],['awaiting_tests','testing']);
});

test('badge labels are exact Portuguese copy',()=>{
  const labels={running:'executando',unconfirmed:'estado não confirmado',no_diff:'sem diff',delivered:'entregue',delivery_unconfirmed:'entrega não comprovada',link_by_wave:'vínculo pela onda, a confirmar no gate',link_confirmed:'vínculo confirmado no gate',link_unconfirmed:'vínculo não confirmado',superseded:'substituída pela onda 03',gate_rejected:'gate REJECTED',gate_blocked:'gate BLOCKED',skipped:'ignorado',tests_finished:'testes concluídos, aguardando gate'};
  for(const [code,label] of Object.entries(labels))assert.equal(badgeLabel(code,{superseded_by_wave:3}),label);
  assert.equal(badgeLabel('\u001b[31mnovo'), 'novo');
});

test('planMoves ignores first snapshot and new tasks',()=>{
  const tasks=[task('new','testing')];
  assert.deepEqual(planMoves(null,tasks),{animated:[],instant:[]});
  assert.deepEqual(planMoves(new Map(),tasks),{animated:[],instant:[]});
  assert.deepEqual(planMoves(columnMap(tasks),tasks),{animated:[],instant:[]});
});

test('planMoves skipping columns is a single move',()=>{
  const previous=columnMap([task('a','backlog'),task('removed','testing')]);
  const tasks=[task('a','done')];
  assert.deepEqual(planMoves(previous,tasks),{animated:[{taskId:'a',from:'backlog',to:'done'}],instant:[]});
  assert.equal(previous.get('a'),'backlog');
  assert.equal(tasks[0].column,'done');
});

test('planMoves animates at most six and the rest are instant',()=>{
  const tasks=Array.from({length:8},(_,i)=>task(String(i),'testing'));
  const previous=columnMap(tasks.map(t=>({...t,column:'awaiting_tests'})));
  const moves=planMoves(previous,tasks);
  assert.deepEqual(moves.animated.map(m=>m.taskId),['0','1','2','3','4','5']);
  assert.deepEqual(moves.instant.map(m=>m.taskId),['6','7']);
  assert.equal(planMoves(previous,tasks,{limit:0}).instant.length,8);
  assert.equal(planMoves(previous,tasks,{limit:2}).animated.length,2);
});

test('testerLabel falls back to id',()=>{
  assert.equal(testerLabel('\u001b[31mqa-missing',[]),'qa-missing');
  assert.equal(testerLabel('qa',[{id:'qa',name:'qa-1',role:'QA',provider:'codex'}]),'qa-1 · QA (codex)');
  assert.equal(testerLabel('qa',[{id:'qa',name:'\u001b[31mNome',role:null,provider:null}]),'Nome · função não informada (provedor não informado)');
});

test('taskTitle is inert',()=>{
  assert.equal(taskTitle({title:'\u001b[31m<img onerror=x>'}),'<img onerror=x>');
  assert.equal(taskTitle({title:'public<think>private</think>'}),'public[conteúdo interno oculto]');
  assert.equal(taskTitle({}),'tarefa sem descrição registrada');
  assert.equal(taskTitle({title:''}),'tarefa sem descrição registrada');
});

test('pipelineActive detects developer contract',()=>{
  const agents=[{execution_id:'e',contract:'developer'},{execution_id:'other',contract:'qa'}];
  assert.equal(pipelineActive(agents,'e'),true);
  assert.equal(pipelineActive(agents,'other'),false);
  assert.equal(pipelineActive([], 'e'),false);
});

test('testerLabel formats canonical roles and sanitizes metadata',()=>{
  assert.equal(testerLabel('qa',[{id:'qa',name:'qa-1',role:'qa',provider:'\u001b[31mcodex'}]),'qa-1 · QA (codex)');
  assert.equal(testerLabel('r',[{id:'r',name:'review-1',role:'reviewer',provider:'claude'}]),'review-1 · Reviewer (claude)');
});
