import test from 'node:test';
import assert from 'node:assert/strict';
import {buildTimeline,boardAt} from '../../src/alethe_tui/web/timeline.mjs';
import {createReplay} from '../../src/alethe_tui/web/replay.mjs';

const at=seconds=>new Date(Date.UTC(2026,0,1)+seconds*1000).toISOString();

test('out-of-order timestamps preserve task transition order and reach the live columns',()=>{
  const tasks=[
    {id:'task-a',column:'done',transitions:[
      {column:'backlog',at:at(30)},
      {column:'in_progress',at:at(20)},
      {column:'done',at:at(10)}
    ]},
    {id:'task-b',column:'blocked',transitions:[
      {column:'backlog',at:at(5)},
      {column:'blocked',at:at(40)}
    ]}
  ];

  const timeline=buildTimeline(tasks);
  const movesForA=timeline.steps.flatMap(step=>step.moves.filter(move=>move.taskId==='task-a'));

  assert.deepEqual(movesForA.map(move=>[move.from,move.to]),[
    [null,'backlog'],
    ['backlog','in_progress'],
    ['in_progress','done']
  ]);
  assert.deepEqual(boardAt(timeline,timeline.steps.length-1),new Map([
    ['task-b','blocked'],
    ['task-a','done']
  ]));
  for(const task of tasks)assert.equal(boardAt(timeline,timeline.steps.length-1).get(task.id),task.column);
});

test('pause and speed changes preserve the current step remaining time',()=>{
  let now=0,nextId=0;
  const jobs=new Map(),applied=[];
  const timeline={steps:[{offset:0,at:null,moves:[]},{offset:1.28,at:null,moves:[]}],duration:2.56};
  const replay=createReplay({
    timeline,
    now:()=>now,
    apply:(index,animate)=>applied.push([index,animate,now]),
    schedule:(callback,delay)=>{const id=nextId++;jobs.set(id,{callback,delay,due:now+delay});return id;},
    cancel:id=>jobs.delete(id),
    onTick:()=>{},
    onEnd:()=>{}
  });

  replay.play();
  const initial=[...jobs.values()][0];
  now=initial.due;
  jobs.delete([...jobs.keys()][0]);
  initial.callback();
  now+=480;
  replay.pause();
  assert.equal(jobs.size,0);

  now+=5000;
  replay.setSpeed(2);
  replay.play();
  assert.equal([...jobs.values()][0].delay,400);
  now+=100;
  replay.pause();
  now+=3000;
  replay.setSpeed(4);
  replay.play();
  assert.equal([...jobs.values()][0].delay,150);
  assert.deepEqual(applied,[[ -1,false,0],[0,true,500]]);

  now+=[...jobs.values()][0].delay-1;
  assert.equal(replay.index,0);
  now+=1;
  const pending=[...jobs.values()][0];
  jobs.clear();
  pending.callback();
  assert.equal(replay.index,1);
});
