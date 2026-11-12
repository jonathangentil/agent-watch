import test from 'node:test';
import assert from 'node:assert/strict';
import {createReplay,replayCardData,replayEffects,replayClock,startReplaySession,setReplayPresentation} from '../../src/alethe_tui/web/replay.mjs';
import {buildTimeline} from '../../src/alethe_tui/web/timeline.mjs';

const defaultTimeline={steps:[0,1.28,2.56].map(offset=>({offset,at:null,moves:[{taskId:'a',from:'backlog',to:'done'}]})),duration:3*0.78+2*0.5};
const close=(actual,expected)=>assert.ok(Math.abs(actual-expected)<1e-7,`${actual} != ${expected}`);
function setup(timeline=defaultTimeline,options={}){
  let now=0,serial=0,ends=0;const jobs=new Map(),applied=[],ticks=[];
  const replay=createReplay({timeline,now:()=>now,apply:(index,animate)=>{applied.push([index,animate,now]);options.apply?.(index,animate);},schedule:(fn,ms)=>{const id=serial++;jobs.set(id,{fn,at:now+ms,ms});return id;},cancel:id=>jobs.delete(id),onTick:index=>ticks.push(index),onEnd:()=>{ends++;options.onEnd?.();}});
  const first=()=>[...jobs].sort((a,b)=>a[1].at-b[1].at)[0];
  const next=()=>{const [id,job]=first()||[];assert.ok(job,'expected scheduled callback');jobs.delete(id);now=job.at;job.fn();};
  const advance=ms=>{const target=now+ms;while(first()?.[1].at<=target)next();now=target;};
  return {replay,jobs,applied,ticks,next,advance,get delay(){return first()?.[1].ms;},get ends(){return ends;}};
}
test('play applies steps in order with speed-scaled delays',()=>{
  const s=setup();s.replay.setSpeed(2);s.replay.play();s.replay.play();
  assert.deepEqual(s.applied,[[-1,false,0]]);assert.equal(s.jobs.size,1);close(s.delay,250);
  s.next();close(s.delay,640);s.next();s.next();
  assert.deepEqual(s.applied,[[-1,false,0],[0,true,250],[1,true,890],[2,true,1530]]);
  assert.deepEqual(s.ticks,[-1,0,1,2]);assert.equal(s.replay.index,2);
  assert.equal(s.ends,0);s.next();assert.equal(s.ends,1);assert.equal(s.replay.playing,false);
});
test('pause stops scheduling',()=>{
  const s=setup();s.replay.play();s.next();s.replay.pause();
  assert.equal(s.jobs.size,0);assert.equal(s.replay.playing,false);assert.equal(s.ends,0);
  s.replay.play();assert.equal(s.applied.length,2);s.next();assert.equal(s.replay.index,1);
});
test('seek applies without animation',()=>{
  const s=setup();s.replay.seek(1);
  assert.deepEqual(s.applied,[[1,false,0]]);assert.deepEqual(s.ticks,[1]);assert.equal(s.jobs.size,0);
  s.replay.play();s.replay.seek(-1);assert.equal(s.jobs.size,1);assert.equal(s.replay.index,-1);
  assert.deepEqual(s.applied.at(-1),[-1,false,0]);close(s.delay,500);s.next();assert.equal(s.replay.index,0);
});
test('end calls onEnd once',()=>{
  const s=setup();s.replay.play();while(s.jobs.size)s.next();
  s.replay.stop();s.replay.stop();s.replay.play();assert.equal(s.ends,1);assert.equal(s.jobs.size,0);
  const stopped=setup();stopped.replay.play();stopped.replay.stop();assert.equal(stopped.jobs.size,0);assert.equal(stopped.ends,1);
  const empty=setup({steps:[],duration:0});empty.replay.play();empty.replay.stop();assert.equal(empty.ends,1);assert.equal(empty.jobs.size,0);
});
test('invalid speed is ignored',()=>{
  const s=setup();s.replay.setSpeed(2);for(const speed of [0,-1,3,8,NaN,'4'])s.replay.setSpeed(speed);
  s.replay.play();close(s.delay,250);s.next();close(s.delay,640);
});
test('speed changes replace the pending timer and preserve position',()=>{
  const s=setup();s.replay.play();s.next();s.replay.setSpeed(4);
  assert.equal(s.jobs.size,1);close(s.delay,320);assert.equal(s.replay.index,0);
  s.next();assert.deepEqual(s.applied.at(-1),[1,true,820]);
});
test('custom timeline timing and final travel are respected',()=>{
  const s=setup({steps:[{offset:0},{offset:0.6}],duration:1});s.replay.play();s.next();
  close(s.delay,600);s.next();close(s.delay,900);s.next();assert.equal(s.ends,1);
});
test('seek clamps to the board range and rejects invalid positions',()=>{
  const s=setup();s.replay.seek(99);assert.equal(s.replay.index,2);assert.deepEqual(s.applied.at(-1),[2,false,0]);
  s.replay.seek(-99);assert.equal(s.replay.index,-1);
  for(const value of [NaN,Infinity,'1'])s.replay.seek(value);
  assert.equal(s.applied.length,2);assert.equal(s.jobs.size,0);
});
test('single step stays visible for its travel before ending',()=>{
  const s=setup({steps:[{offset:0,at:null,moves:[]}],duration:0.78});s.replay.setSpeed(4);s.replay.play();s.next();
  assert.deepEqual(s.applied,[[-1,false,0],[0,true,125]]);assert.equal(s.ends,0);close(s.delay,320);
  s.next();assert.equal(s.ends,1);
});
test('large batches finish all staggered moves before advancing or ending at every speed',()=>{
  const timeline=buildTimeline(Array.from({length:8},(_,i)=>({id:String(i),transitions:[{column:'backlog',at:'2026-01-01T00:00:00Z'},{column:'done',at:'2026-01-01T00:00:10Z'}]})));
  for(const speed of [1,2,4]){
    const s=setup(timeline);s.replay.setSpeed(speed);s.replay.play();s.next();
    close(s.delay,2260/speed);s.advance(1759/speed);assert.equal(s.replay.index,0);assert.equal(s.ends,0);
    s.next();assert.equal(s.replay.index,1);close(s.delay,2260/speed);
    s.advance(1759/speed);assert.equal(s.ends,0);s.next();assert.equal(s.ends,1);
    close(s.applied[2][2],2760/speed);
  }
});
test('empty board remains visible for half a second before the first step',()=>{
  const s=setup();s.replay.play();assert.deepEqual(s.applied,[[-1,false,0]]);
  s.advance(499);assert.equal(s.replay.index,-1);s.advance(1);assert.deepEqual(s.applied.at(-1),[0,true,500]);
});
test('pause and resume preserve the remaining step time',()=>{
  const s=setup();s.replay.play();s.next();s.advance(480);s.replay.pause();s.advance(5000);s.replay.play();
  close(s.delay,800);s.advance(799);assert.equal(s.replay.index,0);s.advance(1);assert.equal(s.replay.index,1);
});
test('speed changes preserve remaining time while playing and paused',()=>{
  const s=setup();s.replay.play();s.next();s.advance(480);s.replay.setSpeed(2);close(s.delay,400);
  s.advance(100);s.replay.pause();s.advance(3000);s.replay.setSpeed(4);assert.equal(s.jobs.size,0);s.replay.play();close(s.delay,150);
  s.advance(149);assert.equal(s.replay.index,0);s.advance(1);assert.equal(s.replay.index,1);
});
test('initial pause also preserves elapsed time across pause and speed changes',()=>{
  const s=setup();s.replay.play();s.advance(200);s.replay.pause();s.advance(1000);s.replay.setSpeed(2);s.replay.play();
  close(s.delay,150);s.advance(149);assert.equal(s.replay.index,-1);s.advance(1);assert.equal(s.replay.index,0);
});
test('replay cards contain only stable task and owner data and leave live data intact',()=>{
  const tasks=[{id:'a',agent_id:'dev',title:'Tarefa',column:'done',testers:['qa'],badges:['gate_rejected'],revision:'rev',gate:2,gate_decision:'APPROVED',updated_at:'final',column_evidence:'final'}];
  const agents=[{id:'dev',name:'Dev',role:'developer',contract:'developer',source:'alethe',provider:'codex',model:'model',wave:'01',wave_index:1,status:'succeeded',started_at:'start',finished_at:'final',idle_seconds:30,tokens:123,tokens_partial:false,cost_usd:2}];
  const original=structuredClone({tasks,agents});
  const view=replayCardData(tasks,agents,new Map([['a','backlog']]));
  assert.deepEqual(view,{tasks:[{id:'a',agent_id:'dev',title:'Tarefa',column:'backlog'}],agents:[{id:'dev',name:'Dev',role:'developer',contract:'developer',source:'alethe',provider:'codex',model:'model',wave:'01',wave_index:1}]});
  assert.deepEqual({tasks,agents},original);
  assert.deepEqual(replayCardData(tasks,agents,new Map()).tasks,[]);
});
test('appearances flash while existing moves use FLIP and seeking never highlights',()=>{
  const step={moves:[{taskId:'new',from:null,to:'backlog'},{taskId:'old',from:'backlog',to:'done'}]};
  assert.deepEqual(replayEffects(step,true,false),{animated:[step.moves[1]],flash:['new']});
  assert.deepEqual(replayEffects(step,true,true),{animated:[],flash:['new','old']});
  assert.deepEqual(replayEffects(step,false,false),{animated:[],flash:[]});
});
test('clock labels the empty board as the beginning and untimed steps as unknown',()=>{
  assert.equal(replayClock(defaultTimeline,-1),'início do replay');
  assert.equal(replayClock(defaultTimeline,0),'horário não informado');
});
test('session focuses play on entry and replay on manual or natural exit',()=>{
  for(const natural of [false,true]){
    const events=[];let s;
    const controller=startReplaySession({mount:onEnd=>{events.push('mount');s=setup(defaultTimeline,{onEnd});return s.replay;},restore:()=>events.push('live'),focusPlay:()=>events.push('play focus'),focusStart:()=>events.push('replay focus')});
    assert.equal(controller,s.replay);assert.deepEqual(events,['mount','play focus']);
    if(natural)while(s.jobs.size)s.next();else controller.stop();
    assert.deepEqual(events,['mount','play focus','live','replay focus']);assert.equal(s.jobs.size,0);
  }
});
test('failed session startup restores live state and focus without pending timers',()=>{
  for(const failure of ['mount','play']){
    let active=false,board='live',focus='start',s;
    const controller=startReplaySession({mount:onEnd=>{active=true;board='empty';if(failure==='mount')throw new Error('draw failed');s=setup(defaultTimeline,{onEnd,apply:()=>{throw new Error('apply failed');}});return s.replay;},restore:()=>{active=false;board='live';},focusPlay:()=>{focus='play';},focusStart:()=>{focus='start';}});
    assert.equal(controller,null);assert.equal(active,false);assert.equal(board,'live');assert.equal(focus,'start');assert.equal(s?.jobs.size||0,0);
  }
});

// Inert tree for presentation boundaries; no browser or source-text assertions.
class PresentationNode {
  constructor(cls,text=''){this.cls=cls;this.text=text;this.children=[];this.parentNode=null;this.style={};}
  append(...nodes){for(const node of nodes){node.remove();node.parentNode=this;this.children.push(node);}}
  remove(){if(this.parentNode){const parent=this.parentNode;parent.children=parent.children.filter(node=>node!==this);this.parentNode=null;}}
  contains(node){return node===this||this.children.some(child=>child.contains(node));}
  querySelectorAll(selector){const classes=selector.split(',').map(value=>value.slice(1));return this.children.flatMap(node=>[...(classes.includes(node.cls)?[node]:[]),...node.querySelectorAll(selector)]);}
  removeAttribute(key){delete this[key];}
  get textContent(){return this.text+this.children.map(node=>node.textContent).join('');}
}
test('replay removes temporal footers from the card tree and restores the same live nodes',()=>{
  const root=new PresentationNode('board'),card=new PresentationNode('kanban-card'),owner=new PresentationNode('kanban-who','Dev'),marker=new PresentationNode('kanban-marker'),footer=new PresentationNode('kanban-foot'),time=new PresentationNode('time','não informado · sem saída: não informado'),tokens=new PresentationNode('tokens','tokens: não informado');
  owner.title='estado não confirmado';footer.append(time,tokens);card.append(owner,marker,footer);root.append(card);
  setReplayPresentation(root,true);
  assert.equal(root.querySelectorAll('.kanban-foot').length,0);assert.equal(root.textContent,'Dev');assert.equal(marker.style.display,'none');assert.equal(owner.title,undefined);
  setReplayPresentation(root,true);assert.equal(footer.parentNode,null);
  // renderBoard retains and updates these same nodes while the footer is detached.
  time.text='2m 00s · sem saída: 3s';tokens.text='tokens: 123';
  setReplayPresentation(root,false);
  assert.equal(root.querySelectorAll('.kanban-foot')[0],footer);assert.equal(footer.parentNode,card);
  assert.match(root.textContent,/2m 00s · sem saída: 3s/);assert.match(root.textContent,/tokens: 123/);assert.equal(marker.style.display,'');
  setReplayPresentation(root,false);assert.equal(root.querySelectorAll('.kanban-foot').length,1);
});
test('replay cleanup never resurrects a card removed during playback',()=>{
  const root=new PresentationNode('board'),card=new PresentationNode('kanban-card'),footer=new PresentationNode('kanban-foot','tokens: não informado');card.append(footer);root.append(card);
  setReplayPresentation(root,true);card.remove();setReplayPresentation(root,false);
  assert.equal(root.children.length,0);assert.equal(footer.parentNode,null);
});
test('final pause prevents ending while the last animation is still finishing',()=>{
  for(const speed of [1,2,4]){
    let finished=false;
    const s=setup({steps:[{offset:0,at:null,moves:[{taskId:'a',from:'backlog',to:'done'}]}],duration:0.78},{onEnd:()=>assert.ok(finished,'last animation must finish before onEnd')});
    s.replay.setSpeed(speed);s.replay.play();s.next();
    s.advance(772/speed);assert.equal(s.ends,0);
    // The browser's final animation frame can land after the nominal 780 ms.
    s.advance(16/speed);assert.equal(s.ends,0);finished=true;
    s.advance(491/speed);assert.equal(s.ends,0);s.next();assert.equal(s.ends,1);
  }
});
