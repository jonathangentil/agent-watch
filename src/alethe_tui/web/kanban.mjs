import {safeText,elapsed,stateLabel} from './state.mjs';
import {COLUMNS,TEST_COLUMNS,badgeLabel,testerLabel,taskTitle} from './board.mjs';

function el(tag,value,cls){const node=document.createElement(tag);if(value!==undefined)node.textContent=safeText(value);if(cls)node.className=cls;return node;}
const running=new WeakMap();
const roles={developer:'Developer',reviewer:'Reviewer',qa:'QA',planner:'Planner'};
const cards=root=>[...root.querySelectorAll('[data-task-id]')];

const parts=new WeakMap();
function setText(node,value){const text=safeText(value);if(node.textContent!==text)node.textContent=text;}
function setAttribute(node,key,value){if(node.getAttribute(key)!==value)node.setAttribute(key,value);}
function reconcileChildren(parent,nodes){
  const wanted=new Set(nodes);for(const child of [...parent.children])if(!wanted.has(child))child.remove();
  nodes.forEach((node,index)=>{if(parent.children[index]!==node)parent.insertBefore(node,parent.children[index]||null);});
}
function chips(node,values){const nodes=values.map((value,index)=>{const chip=node.children[index]||el('span',undefined,'kanban-chip');setText(chip,value);return chip;});reconcileChildren(node,nodes);}
function cardParts(node){
  let view=parts.get(node);if(view)return view;
  node.className='kanban-card';
  const open=el('button',undefined,'kanban-open');open.type='button';open.setAttribute('aria-controls','kanban-detail');
  const title=el('span',undefined,'kanban-title'),who=el('span',undefined,'kanban-who'),marker=el('span',undefined,'kanban-marker'),owner=el('span');marker.setAttribute('aria-hidden','true');who.append(marker,owner);open.append(title,who);
  const tags=el('div',undefined,'kanban-chips'),testers=el('div'),badges=el('div',undefined,'kanban-chips'),foot=el('div',undefined,'kanban-foot'),timing=el('span'),tokens=el('span');foot.append(timing,tokens);node.append(open,tags,testers,badges,foot);
  view={open,title,who,owner,tags,testers,badges,timing,tokens,testerNodes:new Map()};parts.set(node,view);return view;
}

export function renderBoard(root,{tasks,agents,selectedAgentId,pipeline,onSelect,onSelectTester}){
  const existing=new Map(cards(root).map(node=>[node.dataset.taskId,node]));
  if(!root.querySelector('[data-column]'))root.replaceChildren(...COLUMNS.map(([id,label])=>{
    const column=el('section',undefined,'kanban-column');column.dataset.column=id;
    const heading=el('h3');heading.append(el('span',label),el('span','0','kanban-count'));
    const note=el('p',undefined,'kanban-pipeline-note');
    if(TEST_COLUMNS.has(id))heading.append(el('small','só Alethe'));
    column.append(heading,note,el('div',undefined,'kanban-stack'));return column;
  }));
  const byId=new Map(agents.map(agent=>[agent.id,agent]));
  const wanted=new Set(tasks.map(task=>task.id));
  for(const [id,node] of existing)if(!wanted.has(id))node.remove();
  const grouped=new Map(COLUMNS.map(([id])=>[id,[]]));
  for(const task of tasks){
    if(!grouped.has(task.column))continue;
    const agent=byId.get(task.agent_id)||{},node=existing.get(task.id)||el('article'),view=cardParts(node);
    if(node.dataset.taskId!==task.id)node.dataset.taskId=task.id;
    node.classList.toggle('selected',task.agent_id===selectedAgentId);node.classList.toggle('superseded',Boolean(task.badges?.includes('superseded')));
    if(node.dataset.status!==(agent.status||'unknown'))node.dataset.status=agent.status||'unknown';
    if(node.dataset.taskColumn!==task.column)node.dataset.taskColumn=task.column;
    setAttribute(view.open,'aria-pressed',String(task.agent_id===selectedAgentId));view.open.onclick=()=>onSelect(task);
    node.onclick=event=>{if(!event.target.closest('button'))onSelect(task);};
    setText(view.title,taskTitle(task));
    const role=Object.hasOwn(roles,agent.contract)?roles[agent.contract]:Object.hasOwn(roles,agent.role)?roles[agent.role]:agent.role||'função não informada';
    setText(view.owner,`${agent.name||task.agent_id} · ${role}`);setAttribute(view.who,'title',stateLabel(agent.status));
    chips(view.tags,[agent.source||'origem não informada',`${agent.provider||'provedor não informado'}/${agent.model||'modelo não informado'}`,agent.wave?`onda ${agent.wave}`:agent.wave_index!=null?`onda ${String(agent.wave_index).padStart(2,'0')}`:null,task.revision,task.gate!=null?`gate ${task.gate} ${task.gate_decision||''}`:null].filter(Boolean));
    const testerIds=new Set(task.testers||[]);for(const [id,tester] of view.testerNodes)if(!testerIds.has(id)){tester.remove();view.testerNodes.delete(id);}
    const testerNodes=[...testerIds].map(id=>{let tester=view.testerNodes.get(id);if(!tester){tester=el('button',undefined,'kanban-tester');tester.type='button';view.testerNodes.set(id,tester);}setText(tester,`⟳ testando: ${testerLabel(id,agents)}`);tester.onclick=()=>onSelectTester(id);return tester;});
    reconcileChildren(view.testers,testerNodes);chips(view.badges,(task.badges||[]).map(code=>badgeLabel(code,task)));
    const tokens=Number.isSafeInteger(agent.tokens)&&agent.tokens>=0?`${agent.tokens.toLocaleString('pt-BR')}${agent.tokens_partial?' · parcial':''}`:'não informado';
    setText(view.timing,`${elapsed(agent.started_at,agent.finished_at||undefined)} · sem saída: ${agent.idle_seconds==null?'não informado':`${agent.idle_seconds}s`}`);setText(view.tokens,`tokens: ${tokens}`);
    grouped.get(task.column).push(node);
  }
  for(const column of root.children){
    const id=column.dataset.column;if(!grouped.has(id))continue;
    column.classList.toggle('collapsed',!pipeline&&TEST_COLUMNS.has(id));
    setText(column.querySelector('.kanban-count'),String(grouped.get(id).length));
    setText(column.querySelector('.kanban-pipeline-note'),!pipeline&&TEST_COLUMNS.has(id)?'sem pipeline nesta execução':'');
    const stack=column.querySelector('.kanban-stack'),nodes=grouped.get(id);
    reconcileChildren(stack,nodes.length?nodes:[stack.querySelector('.kanban-empty')||el('p','nenhuma tarefa','kanban-empty')]);
  }
}

export function measure(root){return new Map(cards(root).map(node=>[node.dataset.taskId,node.getBoundingClientRect()]));}

export function cancelMoves(root){
  const work=running.get(root);if(work){for(const animation of work.animations)animation.cancel();for(const overlay of work.overlays)overlay.remove();for(const node of work.hidden)node.style.visibility='';running.delete(root);}
  for(const node of cards(root))node.classList.remove('lifted','flash');
}

export function animateMoves(root,before,{animated,instant=[]},{reduced=false,paused=false}){
  if(!animated.length&&!instant.length)return;
  cancelMoves(root);if(paused||!animated.length)return;
  const nodes=new Map(cards(root).map(node=>[node.dataset.taskId,node]));
  if(reduced){for(const move of animated)nodes.get(move.taskId)?.classList.add('flash');return;}
  const work={animations:[],overlays:[],hidden:[]};running.set(root,work);
  const moved=new Set([...animated,...instant].map(move=>move.taskId));
  for(const [id,node] of nodes){const a=before.get(id),b=node.getBoundingClientRect();if(!a||moved.has(id))continue;const dx=a.left-b.left,dy=a.top-b.top;if(dx||dy)work.animations.push(node.animate([{transform:`translate(${dx}px,${dy}px)`},{transform:'none'}],{duration:280,easing:'cubic-bezier(.2,.8,.2,1)'}));}
  const bounds=root.getBoundingClientRect(),left=Math.max(0,bounds.left),top=Math.max(0,bounds.top),right=Math.min(innerWidth,bounds.right),bottom=Math.min(innerHeight,bounds.bottom);
  if(right<=left||bottom<=top)return;
  const overlay=el('div',undefined,'kanban-flight');overlay.inert=true;overlay.setAttribute('aria-hidden','true');Object.assign(overlay.style,{left:`${left}px`,top:`${top}px`,width:`${right-left}px`,height:`${bottom-top}px`});root.append(overlay);work.overlays.push(overlay);
  animated.forEach((move,index)=>{
    const node=nodes.get(move.taskId),a=before.get(move.taskId);if(!node||!a)return;
    const b=node.getBoundingClientRect(),ghost=node.cloneNode(true);delete ghost.dataset.taskId;ghost.classList.add('lifted');ghost.removeAttribute('tabindex');
    // Clip flights to the board viewport; an offscreen destination lands at its edge.
    const x=Math.max(left,Math.min(b.left,right-b.width)),y=Math.max(top,Math.min(b.top,bottom-b.height));
    Object.assign(ghost.style,{position:'absolute',left:`${x-left}px`,top:`${y-top}px`,width:`${b.width}px`,margin:'0'});overlay.append(ghost);node.style.visibility='hidden';work.hidden.push(node);
    const dx=a.left-x,dy=a.top-y;
    const animation=ghost.animate([
      {transform:`translate(${dx}px,${dy}px) scale(1) rotate(0deg)`,boxShadow:'0 0 0 rgba(0,0,0,0)'},
      {transform:`translate(${dx}px,${dy-6}px) scale(1.04) rotate(-2deg)`,boxShadow:'0 14px 28px rgba(0,0,0,.55)',offset:.15},
      {transform:`translate(${dx*.1}px,${dy*.1-6}px) scale(1.04) rotate(1.5deg)`,boxShadow:'0 14px 28px rgba(0,0,0,.55)',offset:.82},
      {transform:'translate(0,2px) scale(.99) rotate(0deg)',boxShadow:'0 2px 4px rgba(0,0,0,.3)',offset:.93},
      {transform:'none',boxShadow:'0 0 0 rgba(0,0,0,0)'}
    ],{duration:780,delay:index*140,easing:'cubic-bezier(.45,.05,.25,1)',fill:'backwards'});
    work.animations.push(animation);animation.onfinish=()=>{node.style.visibility='';ghost.remove();if(!overlay.children.length)overlay.remove();};
  });
}
