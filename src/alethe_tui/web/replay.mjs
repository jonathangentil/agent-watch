// Times are remaining milliseconds at 1×; timers and the monotonic clock are injectable.
export function createReplay({timeline,apply,schedule,cancel,onTick,onEnd,now=()=>performance.now(),maxPause=0.5}){
  let index=-1,playing=false,speed=1,handle=null,ended=false,initialized=false,remaining=null,startedAt=0;
  const last=timeline.steps.length-1;
  function clear(save=false){
    if(handle===null)return;
    if(save)remaining=Math.max(0,remaining-(now()-startedAt)*speed);
    cancel(handle);handle=null;
  }
  function pause(){clear(true);playing=false;}
  function stop(){if(ended)return;pause();ended=true;onEnd();}
  function show(animate){apply(index,animate);onTick(index);}
  function queue(){
    if(!playing||ended)return;
    if(remaining===null){
      const current=timeline.steps[index],next=timeline.steps[index+1];
      // Keep the final pause too: the browser may present the final frame after the nominal travel time.
      remaining=Math.max(0,index<0?maxPause:next?next.offset-current.offset:timeline.duration-current.offset+maxPause)*1000;
    }
    startedAt=now();
    handle=schedule(()=>{handle=null;remaining=null;if(!playing||ended)return;if(index===last){stop();return;}index++;show(true);queue();},remaining/speed);
  }
  return {
    play(){if(playing||ended)return;if(last<0){stop();return;}playing=true;if(!initialized){initialized=true;show(false);}queue();},
    pause,
    seek(value){if(ended||!Number.isFinite(value))return;clear();remaining=null;initialized=true;index=Math.max(-1,Math.min(last,Math.trunc(value)));show(false);queue();},
    setSpeed(value){if(![1,2,4].includes(value))return;clear(true);speed=value;queue();},
    stop,
    get index(){return index;},
    get playing(){return playing;}
  };
}

// Use allowlists: final snapshot metadata cannot establish facts at a replayed instant.
export function replayCardData(tasks,agents,columns){
  const pick=(value,keys)=>Object.fromEntries(keys.filter(key=>Object.hasOwn(value,key)).map(key=>[key,value[key]]));
  return {
    tasks:tasks.filter(task=>columns.has(task.id)).map(task=>({...pick(task,['id','agent_id','title']),column:columns.get(task.id)})),
    agents:agents.map(agent=>pick(agent,['id','name','role','contract','source','provider','model','wave','wave_index']))
  };
}

export function replayEffects(step,animate,reduced){
  const animated=[],flash=[];if(!animate)return {animated,flash};
  const moves=new Map();for(const move of step?.moves||[]){const first=moves.get(move.taskId);moves.set(move.taskId,{...move,from:first?first.from:move.from});}
  for(const move of moves.values())if(reduced||move.from===null)flash.push(move.taskId);else animated.push(move);
  return {animated,flash};
}

export function replayClock(timeline,index){
  if(index===-1)return 'início do replay';
  const step=timeline.steps[index];return step?.at?new Date(step.at).toLocaleTimeString('pt-BR'):'horário não informado';
}

// Mount owns the UI state; restore must clear it even if mounting or the first apply fails.
export function startReplaySession({mount,restore,focusPlay,focusStart}){
  let controller=null,finished=false;
  function finish(){if(finished)return;finished=true;try{restore();}finally{focusStart();}}
  try{controller=mount(finish);focusPlay();controller.play();return controller;}
  catch{try{controller?.stop();}finally{finish();}return null;}
}

const replayFooters=new WeakMap();
export function setReplayPresentation(root,active){
  if(active){
    let footers=replayFooters.get(root);if(!footers){footers=new Map();replayFooters.set(root,footers);}
    for(const footer of root.querySelectorAll('.kanban-foot')){footers.set(footer,footer.parentNode);footer.remove();}
  }else{
    // renderBoard retains references to these nodes; reattach only cards still in this board.
    for(const [footer,parent] of replayFooters.get(root)||[])if(root.contains(parent))parent.append(footer);
    replayFooters.delete(root);
  }
  for(const node of root.querySelectorAll('.kanban-marker'))node.style.display=active?'none':'';
  if(active)for(const node of root.querySelectorAll('.kanban-who'))node.removeAttribute('title');
}
