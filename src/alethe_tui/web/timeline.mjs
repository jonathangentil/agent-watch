// Close recorded batches before inserting their untimed successors as separate steps.
export function buildTimeline(tasks,{batchWindow=1,travel=0.78,stagger=0.14,maxPause=0.5}={}){
  const roots=[],leading=[];
  for(const task of tasks){
    let from=null,previous=null,logicalTime=-Infinity;
    for(const transition of task.transitions||[]){
      const time=transition.at==null?NaN:Date.parse(transition.at);
      if(Number.isFinite(time))logicalTime=Math.max(logicalTime,time);
      const entry={at:Number.isFinite(time)?transition.at:null,time:logicalTime,move:{taskId:task.id,from,to:transition.column},before:previous?.at===null?previous:null,after:[]};
      if(entry.at!==null)roots.push(entry);
      else if(previous)previous.after.push(entry);
      else leading.push(entry);
      previous=entry;from=transition.column;
    }
  }
  roots.sort((a,b)=>a.time-b.time);
  const steps=[],emitted=new Set();let batch=[],offset=0;
  function appendStep(at,moves){steps.push({offset,at,moves});offset+=travel+(moves.length-1)*stagger+maxPause;}
  function appendUntimed(entry){
    appendStep(null,[entry.move]);emitted.add(entry);
    for(const next of entry.after)appendUntimed(next);
  }
  function flush(){
    if(!batch.length)return;
    appendStep(batch[0].at,batch.map(entry=>entry.move));
    for(const entry of batch)for(const next of entry.after)appendUntimed(next);
    batch=[];
  }
  for(const entry of leading)appendUntimed(entry);
  for(const entry of roots){
    // A later recorded move must wait for its own pending untimed predecessor.
    if(batch.length&&(entry.time-batch[0].time>batchWindow*1000||(entry.before&&!emitted.has(entry.before))))flush();
    batch.push(entry);
  }
  flush();
  return {steps,duration:steps.length?offset-maxPause:0};
}

export function boardAt(timeline,index){
  const board=new Map();
  for(let i=0;i<=index&&i<timeline.steps.length;i++)for(const move of timeline.steps[i].moves)board.set(move.taskId,move.to);
  return board;
}
