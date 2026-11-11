import {safeText, stateLabel} from './state.mjs';
const NS='http://www.w3.org/2000/svg';
const sceneTokens={'#344437':'--room-floor','#40513f':'--room-grid','#263a2e':'--room-wall','#172b22':'--room-base','#536448':'--room-trim','#152a24':'--room-window-frame','#618473':'--room-window','#2b4436':'--room-window-bar','#2c3b2e':'--room-leader','#657451':'--room-leader-border','#9d9570':'--room-desk','#6f7355':'--room-desk-edge','#626c51':'--room-desk-leg','#1b2925':'--room-monitor','#425b50':'--room-screen-off','#688f75':'--room-screen-on','#c4dfa8':'--room-code','#c4d7ac':'--room-title','#91a78a':'--room-muted','#bacba5':'--room-muted','#d5dfbd':'--room-title','#a5b794':'--room-muted','#e1e9ce':'--room-title','#b5c6a6':'--room-muted','#bdcdae':'--room-muted'};
export function svg(tag, attrs={}, text) { const node=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs)){const token=['fill','stroke'].includes(k)&&sceneTokens[v];node.setAttribute(k,token?`var(${token}, ${v})`:String(v));}if(text!==undefined)node.textContent=safeText(text);return node; }
const rect=(x,y,width,height,fill,extra={})=>svg('rect',{x,y,width,height,fill,...extra});
export function identityColor(id) { let hash=0;for(const c of id)hash=(hash*31+c.charCodeAt(0))>>>0;return ['#b9a0db','#8ab7cf','#d6ab76','#b2c77f','#cb93a1','#7fbdac'][hash%6]; }
function agentDescription(a={}) { return `Modelo: ${a.model||'não informado'}\nEffort: ${a.effort||'não informado'}\nOnda: ${a.wave||'não informada'}\nAgente: ${a.source_id||a.id||'identidade não informada'}\nTarefa: ${a.task||'não informada'}`; }
function character(id,x,y,status,name,selected,onSelect,description='') {
  const label=`${name} · ${id||'identidade não informada'} · ${stateLabel(status)}${description?'\n'+description:''}`;
  const group=svg('g',{transform:`translate(${x} ${y})`,class:`sprite ${status==='running'?'running':''} ${selected?'selected':''}`,tabindex:0,role:'button','aria-label':label,'data-agent-id':id});
  group.append(svg('title',{},label));
  group.append(svg('ellipse',{cx:20,cy:54,rx:24,ry:7,fill:'none',stroke:'#d6edab','stroke-width':2,class:'halo'}));
  const pose=svg('g',{class:'pose','shape-rendering':'crispEdges'});
  pose.append(svg('ellipse',{cx:20,cy:54,rx:18,ry:4,fill:'#19271f',opacity:.65}));
  for(const r of [[9,7,22,8,'#38352e'],[6,15,28,17,'#e2bb98'],[6,12,5,10,'#4a4036'],[11,8,23,7,'#4a4036'],[12,25,5,3,'#bf8f74'],[12,19,4,4,'#26352b'],[25,19,4,4,'#26352b'],[9,32,23,15,identityColor(id)],[4,33,5,11,'#c79f81'],[12,47,7,7,'#4b5862'],[24,47,7,7,'#4b5862'],[10,53,10,4,'#25332e'],[24,53,10,4,'#25332e']])pose.append(rect(...r));
  pose.append(rect(32,33,6,12,'#e2bb98',{class:'hand'}));
  if(['failed','timed_out','interrupted'].includes(status))pose.append(svg('text',{x:40,y:10,fill:'#f2ba99','font-size':20},'!'));
  if(['succeeded','turn_complete'].includes(status))pose.append(svg('text',{x:40,y:10,fill:'#d5edaa','font-size':16},'✓'));
  group.append(pose);group.addEventListener('click',onSelect);group.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect();}});return group;
}
function desk(root,x,y,running) {
  root.append(rect(x-49,y+27,125,12,'#182a23',{opacity:.5}),rect(x-52,y-4,126,18,'#9d9570'),rect(x-52,y+14,126,7,'#6f7355'),rect(x-44,y+21,8,25,'#626c51'),rect(x+57,y+21,8,25,'#626c51'),rect(x-12,y-43,55,36,'#1b2925'),rect(x-8,y-39,47,27,running?'#688f75':'#425b50'),rect(x+10,y-7,9,5,'#23382c'),rect(x-3,y+1,40,5,'#bcc3a2'),rect(x+52,y-12,10,12,'#d0c3a2'));
  if(running)for(let i=0;i<3;i++)root.append(rect(x-4,y-34+i*7,26-i*5,2,'#c4dfa8'));
}
export function buildScene(state,onSelect,columns=3) {
  columns=Math.max(3,Math.min(6,Math.floor(columns)||3));
  const agents=state.visibleAgents(),width=270+columns*230,height=Math.max(500,140+Math.ceil(agents.length/columns)*180);
  const root=svg('svg',{viewBox:`0 0 ${width} ${height}`,role:'group','aria-label':'Escritório da execução selecionada'});
  const defs=svg('defs');const pattern=svg('pattern',{id:'floor',width:64,height:32,patternUnits:'userSpaceOnUse'});pattern.append(rect(0,0,64,32,'#344437'),svg('path',{d:'M0 31H64M63 0V32',stroke:'#40513f','stroke-width':1}));defs.append(pattern);root.append(defs);
  root.append(rect(0,0,width,height,'url(#floor)'),rect(0,0,width,85,'#263a2e'),rect(0,83,width,9,'#172b22'),rect(0,92,width,6,'#536448'));
  for(let x=260;x+130<width;x+=240)root.append(rect(x,15,130,54,'#152a24'),rect(x+5,20,120,43,'#618473'),rect(x+62,20,5,43,'#2b4436'),rect(x+5,40,120,4,'#2b4436'));
  root.append(svg('text',{x:28,y:38,fill:'#c4d7ac','font-size':14,'letter-spacing':3},'AGENT WATCH'),svg('text',{x:28,y:60,fill:'#91a78a','font-size':10},'OBSERVATÓRIO LOCAL'));
  // Plants, rug and separate lead desk are scenery, never additional workers.
  for(const x of [22,width-40]){root.append(rect(x,height-90,20,28,'#907b59'),rect(x-7,height-115,32,26,'#779859'),rect(x,height-131,13,37,'#91af6a'));}
  root.append(rect(26,145,180,224,'#2c3b2e'),rect(28,147,176,220,'none',{stroke:'#657451','stroke-dasharray':'3 5'}));
  root.append(svg('text',{x:50,y:172,fill:'#bacba5','font-size':10},'LÍDER / PRINCIPAL'));
  desk(root,90,245,Boolean(state.execution?.leader_id)&&state.execution?.leader_status==='running');
  const leader=state.snapshot.agents.find(a=>a.id===state.execution?.leader_id);
  const leaderId=state.execution?.leader_id;
  const positions=new Map();
  if(state.execution){root.append(character(leaderId||'',85,265,leaderId?(leader?.status||state.execution.leader_status||'unknown'):'unknown',leader?.name||state.execution.leader_name||'orquestrador',state.agentId===leaderId,()=>{if(leader)onSelect(leader.id);},agentDescription(leader)));if(leaderId)positions.set(leaderId,{x:105,y:286});
  root.append(svg('text',{x:116,y:347,'text-anchor':'middle',fill:'#d5dfbd','font-size':10},(leader?.name|| (leaderId?state.execution.leader_name:'orquestrador')||'principal').slice(0,23)),svg('text',{x:116,y:361,'text-anchor':'middle',fill:'#a5b794','font-size':8},stateLabel(leaderId?(leader?.status||state.execution.leader_status||'unknown'):'unknown')));}
  for(const [i,a] of agents.entries()) {
    const x=303+(i%columns)*230,y=193+Math.floor(i/columns)*180;
    desk(root,x,y,a.status==='running');
    const description=agentDescription(a);
    root.append(character(a.id,x-2,y+18,a.status,a.name||a.id,state.agentId===a.id,()=>onSelect(a.id),description));
    positions.set(a.id,{x:x+18,y:y+39});
    root.append(svg('text',{x:x+10,y:y+94,'text-anchor':'middle',fill:'#e1e9ce','font-size':11},(a.name||a.id).slice(0,24)),svg('text',{x:x+10,y:y+108,'text-anchor':'middle',fill:'#b5c6a6','font-size':9},`${a.source} · ${stateLabel(a.status)}`));
    const assignment=a.wave?`${a.wave} · ${a.source_id||''}`:(a.task||a.source_id||'Tarefa não informada');
    const line=svg('text',{x:x+10,y:y+122,'text-anchor':'middle',fill:'#b5c6a6','font-size':8},assignment.length>36?assignment.slice(0,35)+'…':assignment);
    line.append(svg('title',{},description));root.append(line);
  }
  if(!agents.length)root.append(svg('text',{x:575,y:260,'text-anchor':'middle',fill:'#bdcdae','font-size':13},state.execution?'Nenhum worker corresponde ao filtro.':'Aguardando execuções observadas…'));
  const overlay=svg('svg',{viewBox:`0 0 ${width} ${height}`,class:'interactions','aria-hidden':'true'});
  return {root,overlay,positions};
}
function envelope(label,returned=false,extra={}) {
  const node=svg('g',extra);
  node.append(svg('title',{},label),rect(-14,-10,28,20,returned?'#c8b5f0':'#f4dfab',{rx:2,class:'envelope-body'}),svg('path',{d:'M-13 -8L0 2L13 -8M-13 9L-4 1M13 9L4 1',fill:'none',class:'envelope-fold'}));
  if(returned)node.append(svg('text',{x:7,y:6,'font-size':11,'font-weight':'bold',class:'envelope-check'},'✓'));
  return node;
}
function removeAfterAnimation(node,remove) {
  node.addEventListener('animationend',event=>{if(event.target===node)remove();});
}
export function clearEventAnimations(scene) {
  if(!scene)return;
  scene.overlay.replaceChildren();
  for(const sprite of scene.root.querySelectorAll('.result'))sprite.classList.remove('result');
}
export function animateEvent(scene,event,reduced=false) {
  const start=scene?.positions.get(event.actor_id);if(!start||reduced)return;
  if(event.effect==='completion'){
    const sprite=[...scene.root.querySelectorAll('.sprite')].find(n=>n.dataset.agentId===event.actor_id);
    if(!sprite)return;
    sprite.classList.add('result');
    const group=svg('g',{transform:`translate(${start.x+34} ${start.y-34})`});
    const ready=envelope('Resultado disponível · entrega ao líder não confirmada',true,{class:'completion-envelope'});
    group.append(ready);scene.overlay.append(group);
    removeAfterAnimation(ready,()=>{group.remove();sprite.classList.remove('result');});return;
  }
  const end=scene.positions.get(event.target_id);if(!end||event.effect!=='interaction')return;
  const path=`M${start.x} ${start.y}Q${(start.x+end.x)/2} ${Math.min(start.y,end.y)-70} ${end.x} ${end.y}`;
  const returned=event.kind==='result_delivered';
  const group=svg('g',{'data-event-id':event.id||''});
  group.append(svg('path',{d:path,stroke:'#dcdf9e','stroke-width':2,fill:'none',class:'interaction-line'}));
  const packet=envelope(returned?'Resultado entregue':event.kind==='delegated'?'Tarefa enviada':'Mensagem enviada',returned,{class:'packet'});
  packet.style.offsetPath=`path('${path}')`;
  group.append(packet);scene.overlay.append(group);removeAfterAnimation(packet,()=>group.remove());
}
