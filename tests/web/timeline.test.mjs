import test from 'node:test';
import assert from 'node:assert/strict';
import {buildTimeline,boardAt} from '../../src/alethe_tui/web/timeline.mjs';

const at=seconds=>new Date(Date.UTC(2026,0,1)+seconds*1000).toISOString();
const task=(id,transitions)=>({id,column:transitions.at(-1)?.column,transitions});
const move=(column,seconds)=>({column,at:seconds===null?null:at(seconds),evidence:'fixture'});

test('orders by recorded time and first move appears from null',()=>{
  const tasks=[task('b',[move('backlog',4),move('done',8)]),task('a',[move('in_progress',0)])];
  const original=structuredClone(tasks),timeline=buildTimeline(tasks);
  assert.deepEqual(timeline.steps.map(s=>[s.at,s.moves]),[
    [at(0),[{taskId:'a',from:null,to:'in_progress'}]],
    [at(4),[{taskId:'b',from:null,to:'backlog'}]],
    [at(8),[{taskId:'b',from:'backlog',to:'done'}]]
  ]);
  assert.deepEqual(tasks,original);
});
test('batches moves within one real second',()=>{
  const timeline=buildTimeline([task('a',[move('backlog',0)]),task('b',[move('backlog',0.9)]),task('c',[move('done',1)]),task('d',[move('done',1.1)])]);
  assert.deepEqual(timeline.steps.map(s=>s.moves.map(m=>m.taskId)),[['a','b','c'],['d']]);
  assert.equal(timeline.steps[0].at,at(0));
});
test('pause never exceeds half a second',()=>{
  const {steps}=buildTimeline([task('a',[move('backlog',0),move('done',600)])]);
  assert.equal(steps[1].offset-steps[0].offset,0.78+0.5);
});
test('untimed transition follows its predecessor with null at',()=>{
  const timeline=buildTimeline([task('a',[move('backlog',0),move('in_progress',null),move('testing',null),move('done',10)]),task('b',[move('backlog',0.1)])]);
  assert.deepEqual(timeline.steps.map(s=>[s.at,s.moves.map(m=>[m.taskId,m.from,m.to])]),[
    [at(0),[['a',null,'backlog'],['b',null,'backlog']]],
    [null,[['a','backlog','in_progress']]],
    [null,[['a','in_progress','testing']]],
    [at(10),[['a','testing','done']]]
  ]);
});
test('final board equals current task columns',()=>{
  const tasks=[task('a',[move('backlog',0),move('done',5)]),task('b',[move('in_progress',null),move('blocked',null)])];
  const timeline=buildTimeline(tasks);
  assert.deepEqual(boardAt(timeline,-1),new Map());
  assert.deepEqual(boardAt(timeline,timeline.steps.length-1),new Map([['b','blocked'],['a','done']]));
  assert.deepEqual(boardAt(timeline,0),new Map([['b','in_progress']]));
  const board=boardAt(timeline,0);board.clear();
  assert.equal(boardAt(timeline,0).size,1);
});
test('duration formula',()=>{
  const timeline=buildTimeline([task('a',Array.from({length:30},(_,i)=>move(i%2?'done':'backlog',i*5)))]);
  assert.equal(timeline.steps.length,30);
  assert.ok(Math.abs(timeline.duration-37.9)<1e-10);
  assert.ok(Math.abs(timeline.steps[29].offset-37.12)<1e-10);
});
test('empty tasks give zero duration',()=>{
  assert.deepEqual(buildTimeline([]),{steps:[],duration:0});
  assert.deepEqual(buildTimeline([{id:'a',transitions:[]}]),{steps:[],duration:0});
});
test('custom timing controls batching offsets and duration',()=>{
  const timeline=buildTimeline([task('a',[move('backlog',0),move('in_progress',1),move('done',2)])],{batchWindow:0.5,travel:0.4,maxPause:0.2});
  assert.deepEqual(timeline.steps.map(s=>s.offset),[0,0.4+0.2,2*(0.4+0.2)]);
  assert.ok(Math.abs(timeline.duration-1.6)<1e-10);
});
test('leading untimed transitions keep logical order before the first recorded move',()=>{
  const timeline=buildTimeline([task('a',[move('backlog',null),move('in_progress',null),move('done',5)])]);
  assert.deepEqual(timeline.steps.map(s=>s.at),[null,null,at(5)]);
  assert.deepEqual(timeline.steps.map(s=>s.moves[0].from),[null,'backlog','in_progress']);
  assert.deepEqual(boardAt(timeline,1),new Map([['a','in_progress']]));
});
test('equal timestamps preserve task order and the final move of each task',()=>{
  const timeline=buildTimeline([task('a',[move('backlog',0),move('in_progress',0),move('done',0)]),task('b',[move('blocked',0)])]);
  assert.equal(timeline.steps.length,1);
  assert.deepEqual(timeline.steps[0].moves.map(m=>[m.taskId,m.from,m.to]),[['a',null,'backlog'],['a','backlog','in_progress'],['a','in_progress','done'],['b',null,'blocked']]);
  assert.deepEqual(boardAt(timeline,0),new Map([['a','done'],['b','blocked']]));
});
test('untimed successor follows the complete recorded batch without splitting it',()=>{
  const tasks=[
    task('a',[move('backlog',0),move('in_progress',10),move('testing',null),move('done',20)]),
    ...['b','c','d','e','f','g','h'].map(id=>task(id,[move('backlog',0),move('blocked',10)])),
    task('i',[move('backlog',0)])
  ];
  const timeline=buildTimeline(tasks);
  assert.deepEqual(timeline.steps.map(step=>[step.at,step.moves.length]),[[at(0),9],[at(10),8],[null,1],[at(20),1]]);
  assert.deepEqual(timeline.steps[1].moves,[
    {taskId:'a',from:'backlog',to:'in_progress'},
    ...['b','c','d','e','f','g','h'].map(taskId=>({taskId,from:'backlog',to:'blocked'}))
  ]);
  assert.deepEqual(timeline.steps[2].moves,[{taskId:'a',from:'in_progress',to:'testing'}]);
  assert.deepEqual(timeline.steps[3].moves,[{taskId:'a',from:'testing',to:'done'}]);
  assert.equal(boardAt(timeline,1).get('a'),'in_progress');
  assert.equal(boardAt(timeline,2).get('a'),'testing');
  assert.equal(boardAt(timeline,3).get('a'),'done');
  assert.deepEqual(timeline.steps.map(step=>Number(step.offset.toFixed(2))),[0,2.4,4.66,5.94]);
  assert.ok(Math.abs(timeline.duration-6.72)<1e-10);
});
test('a recorded successor waits for its untimed predecessor within the batch window',()=>{
  const timeline=buildTimeline([task('a',[move('backlog',0),move('in_progress',null),move('done',0.5)]),task('b',[move('blocked',0.1)])]);
  assert.deepEqual(timeline.steps.map(step=>[step.at,step.moves.map(m=>[m.taskId,m.to])]),[
    [at(0),[['a','backlog'],['b','blocked']]],
    [null,[['a','in_progress']]],
    [at(0.5),[['a','done']]]
  ]);
  assert.deepEqual(boardAt(timeline,2),new Map([['a','done'],['b','blocked']]));
});

test('batch duration covers every staggered move and omits only the final pause',()=>{
  const tasks=['a','b','c','d','e','f','g','h'].map(id=>task(id,[move('backlog',0),move('done',10)]));
  const timeline=buildTimeline(tasks);
  assert.deepEqual(timeline.steps.map(step=>Number(step.offset.toFixed(2))),[0,2.26]);
  assert.ok(Math.abs(timeline.duration-4.02)<1e-10);
  const custom=buildTimeline(tasks,{travel:0.4,stagger:0.1,maxPause:0.2});
  assert.ok(Math.abs(custom.steps[1].offset-1.3)<1e-10);
  assert.ok(Math.abs(custom.duration-2.4)<1e-10);
});
test('out-of-order timestamps never reverse a task logical transitions',()=>{
  const timeline=buildTimeline([task('a',[move('in_progress',10),move('done',0)]),task('b',[move('backlog',5)])]);
  assert.deepEqual(timeline.steps.map(step=>step.moves.map(m=>[m.taskId,m.from,m.to])),[
    [['b',null,'backlog']],
    [['a',null,'in_progress'],['a','in_progress','done']]
  ]);
  assert.deepEqual(boardAt(timeline,timeline.steps.length-1),new Map([['b','backlog'],['a','done']]));
});
