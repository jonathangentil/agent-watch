import {MonitorState,safeText,stateLabel,elapsed,runPages,executionTokens} from '/assets/state.mjs';
import {buildScene,animateEvent,clearEventAnimations} from '/assets/scene.mjs';
import {loadTheme,saveTheme,themeId} from '/assets/theme.mjs';
const $=id=>document.getElementById(id);
let themeStorage;try{themeStorage=localStorage}catch{}
try{$('event-mail').checked=themeStorage?.getItem('agent-watch-event-mail')!=='false';}catch{/* Enabled by default without storage. */}
function applyTheme(value){const id=themeId(value);document.documentElement.dataset.theme=id;$('theme').value=id;}
applyTheme(loadTheme(themeStorage));
$('theme').onchange=()=>{applyTheme($('theme').value);saveTheme($('theme').value,themeStorage)};
window.addEventListener('storage',event=>{if(event.key==='alethe-monitor-theme')applyTheme(event.newValue);if(event.key==='agent-watch-event-mail'){$('event-mail').checked=event.newValue!=='false';applyMotion();}});
const params=new URLSearchParams(location.search);
let saved={};try{saved=JSON.parse(sessionStorage.getItem('alethe-monitor-context')||'{}')||{};}catch{/* Storage may be disabled. */}
const state=new MonitorState(saved);
if(['office','panel'].includes(params.get('view')))state.setView(params.get('view'));
if(params.get('execution'))state.executionId=params.get('execution');
if(params.has('project'))state.projectId=params.get('project');
if(params.get('agent'))state.selections.set(state.executionId,params.get('agent'));
if(params.has('compact'))document.body.classList.add('compact');
let kind='output',scene=null,paused=false,detailController=null,detailKey='',busy=false;
let connectionError='',lastSuccess=null;
const signatures=new Map();
const sidebars={panel:{page:0,selected:null,ids:''},office:{page:0,selected:null,ids:''}};
const motion=matchMedia('(prefers-reduced-motion: reduce)');$('reduce').checked=motion.matches;
motion.addEventListener('change',e=>{$('reduce').checked=e.matches;applyMotion();});
function text(id,value){$(id).textContent=safeText(value);}
const tokenText=value=>Number.isSafeInteger(value)&&value>=0?value.toLocaleString('pt-BR'):'não informado';
function el(tag,value,cls){const node=document.createElement(tag);if(value!==undefined)node.textContent=safeText(value);if(cls)node.className=cls;return node;}
function changed(key,value,render){const signature=JSON.stringify(value);if(signatures.get(key)===signature)return;signatures.set(key,signature);render();}
function persist(){try{sessionStorage.setItem('alethe-monitor-context',JSON.stringify(state.context()));}catch{/* View remains usable without storage. */}}
function choice(select,items,current){const signature=JSON.stringify(items);if(select.dataset.signature!==signature){select.replaceChildren(...items.map(([value,label])=>{const option=el('option',label);option.value=value;return option;}));select.dataset.signature=signature;}select.value=current;}
const displayName=id=>state.snapshot.agents.find(a=>a.id===id)?.name||state.snapshot.executions.find(e=>e.leader_id===id)?.leader_name||id||'não informado';
function selectAgent(id){state.selectAgent(id);render();loadDetail();}
function selectExecution(id){state.selectExecution(id);render();loadDetail();}
function updateSidebar(view){
  const nav=$(view==='office'?'office-runs':'runs'),content=view==='office'?$('office'):document.querySelector('.panel-main');
  if(!content.offsetHeight)return;
  const aside=nav.closest('aside'),pager=$(`${view}-run-pages`),sidebar=sidebars[view];
  aside.style.setProperty('--sidebar-content-height',`${content.getBoundingClientRect().height}px`);
  const buttons=[...nav.children];
  for(const button of buttons)button.hidden=false;
  const heights=buttons.map(button=>button.getBoundingClientRect().height+(parseFloat(getComputedStyle(button).marginBottom)||0));
  const pages=runPages(heights,nav.clientHeight),ids=JSON.stringify(buttons.map(button=>button.dataset.runId));
  if(sidebar.selected!==state.executionId||sidebar.ids!==ids){
    const selected=buttons.findIndex(button=>button.dataset.runId===state.executionId);
    sidebar.page=Math.max(0,pages.findIndex(page=>selected>=page.start&&selected<page.end));
  }
  sidebar.page=Math.max(0,Math.min(pages.length-1,sidebar.page));sidebar.selected=state.executionId;sidebar.ids=ids;
  const current=pages[sidebar.page];
  buttons.forEach((button,index)=>{button.hidden=index<current.start||index>=current.end;});
  pager.querySelector('[data-page-previous]').disabled=sidebar.page===0;
  pager.querySelector('[data-page-next]').disabled=sidebar.page===pages.length-1;
  pager.querySelector('[data-page-label]').textContent=`${sidebar.page+1} / ${pages.length}`;
  pager.classList.toggle('single-page',pages.length===1);
}
function updateSidebars(){for(const view of ['panel','office'])updateSidebar(view);}
function render(){
  persist();const snap=state.snapshot,run=state.execution,agent=state.agent;
  document.body.classList.toggle('disconnected',!state.connected);
  text('connection',(snap.demo?'DEMONSTRAÇÃO · dados fictícios · ':'')+(state.connected?`● Acompanhando · atualizado ${lastSuccess?.toLocaleTimeString('pt-BR')||'agora'}`:`○ Desconectado · ${connectionError||'monitor indisponível'}${lastSuccess?' · mantendo última leitura válida':''}`));
  const totals=snap.totals;
  changed('overview',totals,()=>{$('overview').replaceChildren(...[['projects','projetos monitorados'],['executions','execuções observadas'],['agents','agentes nas três fontes'],['running','agentes executando']].map(([key,label])=>{const stat=el('div',undefined,'stat');stat.append(el('b',totals[key]??'—'),el('span',label));return stat;}));});
  choice($('project'),[['','Todos os projetos'],...snap.projects.map(p=>[p.id,`${p.name} · ${p.path||p.id}`])],state.projectId);
  const executions=state.executions();
  choice($('execution'),executions.length?executions.map(e=>[e.id,`${e.project_name||e.project_id} / ${e.title} · ${e.source} · ${e.id}`]):[['','Nenhuma execução encontrada']],state.executionId);
  for(const button of document.querySelectorAll('[data-view]'))button.setAttribute('aria-selected',String(button.dataset.view===state.view));
  $('panel').hidden=state.view!=='panel';$('office').hidden=state.view!=='office';
  $('office-layout').hidden=state.view!=='office';
  text('focus-label',run?`${run.project_name||run.project_id} / ${run.title} · ${run.id}${run.project_ids?.length>1?' · múltiplos projetos':''} · agente: ${agent?.name||state.agentId||'nenhum'}`:'Nenhuma execução encontrada nas fontes observadas.');
  $('source').value=state.filters.source;$('active').checked=state.filters.active;
  if(document.activeElement!==$('search'))$('search').value=state.filters.search;
  text('filter-count',`${state.visibleAgents().length} visíveis / ${state.workers().length} workers nesta execução`);
  changed('runs',[executions,state.executionId],()=>{for(const id of ['runs','office-runs'])$(id).replaceChildren(...executions.map(e=>{const button=el('button',undefined,`run ${e.id===state.executionId?'selected':''}`);button.dataset.runId=e.id;button.title=e.title;button.setAttribute('aria-pressed',String(e.id===state.executionId));button.append(el('span',e.title),el('small',`${e.project_name||e.project_id} · ${e.source} · ${stateLabel(e.status)}`));button.onclick=()=>selectExecution(e.id);return button;}));});
  text('run-title',run?.title||'Nenhuma execução encontrada');
  text('run-meta',run?`${run.source} · ${run.id} · ${run.project_path||'diretório não informado'}`:'O monitor aguarda fontes disponíveis.');
  text('run-status',run?stateLabel(run.status):'estado não confirmado');
  const leader=snap.agents.find(a=>a.id===run?.leader_id);
  text('leader-panel',run?`Líder separado dos workers: ${leader?.name||(run.leader_id?run.leader_name:'orquestrador')||'principal'} · ${run.leader_id||'identidade não informada'} · ${stateLabel(run.leader_id?(leader?.status||run.leader_status||'unknown'):'unknown')}`:'Líder: não informado');
  const workers=state.workers();
  const counts=[['running','executando'],['queued','aguardando'],['completed','concluídos'],['failed','falhas']].map(([key,label])=>[workers.filter(a=>key==='completed'?['succeeded','turn_complete'].includes(a.status):key==='failed'?['failed','timed_out'].includes(a.status):a.status===key).length,label]);
  changed('stats',counts,()=>{$('run-stats').replaceChildren(...counts.map(([n,label])=>{const node=el('span');node.append(el('b',n),el('span',label));return node;}));});
  const usage=executionTokens(snap,run?.id);
  text('run-tokens',`${tokenText(usage.total)}${usage.total!==null&&usage.partial?' · parcial':''}`);
  text('run-token-coverage',`${usage.reported} de ${usage.agents} agentes com medição · ${usage.leaderReported?'inclui líder':'consumo do líder não informado'} · inclui cache informado, sem estimativas`);
  const visible=state.visibleAgents();
  changed('table',[visible,state.agentId,visible.map(a=>elapsed(a.started_at,a.finished_at||undefined))],()=>{
    const focusId=document.activeElement?.dataset?.selectAgent;
    const rows=visible.map(a=>{const row=el('tr',undefined,a.id===state.agentId?'selected':'');row.classList.add('agent-row');row.onclick=e=>{if(!e.target.closest('button'))selectAgent(a.id);};
      const cell=el('td');const button=el('button',a.name||a.id,'agent-button');button.dataset.selectAgent=a.id;button.onclick=()=>selectAgent(a.id);button.setAttribute('aria-pressed',String(a.id===state.agentId));cell.append(button,el('span',`${a.wave?'Onda '+a.wave+' · ':''}${a.source_id||a.id}`,'sub'),el('span',a.task||'tarefa não informada','sub'));row.append(cell);
      for(const [value,cls] of [[`${a.source} · ${a.provider||'provedor não informado'} / ${a.model||'modelo não informado'} · effort ${a.effort||'não informado'}`,null],[stateLabel(a.status),`state-${Object.hasOwn({running:1,queued:1,succeeded:1,turn_complete:1,failed:1,timed_out:1,interrupted:1},a.status)?a.status:'unknown'}`],[elapsed(a.started_at,a.finished_at||undefined),null],[a.idle_seconds==null?'não informado':`${a.idle_seconds}s`,null],[`${tokenText(a.tokens)}${a.tokens_partial&&a.tokens!==null?' · parcial':''}`,null]])row.append(el('td',value,cls));return row;});
    if(!rows.length){const row=el('tr'),cell=el('td','Nenhum worker corresponde ao filtro.');cell.colSpan=6;row.append(cell);rows.push(row);}
    $('agents').replaceChildren(...rows);
    if(focusId)[...$('agents').querySelectorAll('button')].find(b=>b.dataset.selectAgent===focusId)?.focus({preventScroll:true});
  });
  text('office-count',`${workers.length} workers · ${run?'1 líder separado':'nenhum líder'}`);
  text('office-summary',`${counts[0][0]} executando · ${counts[1][0]} aguardando · ${counts[2][0]} concluídos`);
  text('visible-count',`${visible.length} agentes visíveis`);
  const columns=Math.max(3,Math.min(6,Math.floor(($('scene').clientWidth-230)/200)||3));
  changed('scene',[run?.id,run?.leader_id,run?.leader_name,run?.leader_status,leader?.name,leader?.status,columns,visible.map(a=>[a.id,a.name,a.source,a.status,a.wave,a.source_id,a.model,a.effort,a.task]),state.agentId],()=>{scene=buildScene(state,selectAgent,columns);$('scene').replaceChildren(scene.root,scene.overlay);});
  text('detail-name',agent?`${agent.name} · ${agent.id}`:'Nenhum agente selecionado');text('detail-state',agent?stateLabel(agent.status):'estado não confirmado');
  text('detail-meta',agent?`${agent.source} · ${agent.provider||'provedor não informado'} / ${agent.model||'modelo não informado'} · effort ${agent.effort||'não informado'}\nOnda: ${agent.wave||'não informada'} · identificação: ${agent.source_id||agent.id}\nFunção: ${agent.role||'não informada'}${agent.role_evidence?' · '+agent.role_evidence:''}\nPai: ${agent.parent_id?`${displayName(agent.parent_id)} (${agent.parent_id})`:'não informado'} · diretório: ${agent.cwd||'não informado'}\nEvidência: ${agent.evidence||'estado não confirmado'} · tempo: ${elapsed(agent.started_at,agent.finished_at||undefined)} · última atividade: ${agent.last_activity||'não informada'}`:'');
  text('detail-task',agent?.task||'Tarefa não informada.');
  text('detail-metrics',`Tokens: ${tokenText(agent?.tokens)}${agent?.tokens_partial?' · parcial':''} · Custo: ${agent?.cost_usd==null?'não informado':`US$ ${agent.cost_usd}`} (quando informados pelo agente)`);
  for(const button of document.querySelectorAll('[data-kind]'))button.setAttribute('aria-selected',String(button.dataset.kind===kind));
  const events=snap.events.filter(e=>e.execution_id===state.executionId);text('event-count',`(${events.length})`);
  changed('events',[events,state.executionId],()=>{$('events').replaceChildren(...events.map(e=>el('li',`${e.timestamp||'instante não informado'} · ${eventDescription(e)} · evidência: ${e.evidence||'não informada'}`)));});
  const diagnostics=snap.diagnostics;text('diagnostic-summary',`Fontes e diagnósticos · ${diagnostics.length} registros${diagnostics.some(d=>!['ok','available'].includes(d.status))?' · verificar avisos':''}`);
  changed('diagnostics',diagnostics,()=>{$('diagnostics').replaceChildren(...(diagnostics.length?diagnostics.map(d=>el('li',`${d.source} · ${d.status} · ${d.path||'raiz não informada'} · ${d.message||'sem mensagem'}`)):[el('li','Nenhum diagnóstico informado pelo monitor.') ]));});
  updateSidebars();
}
function eventDescription(event){const labels={delegated:'delegou tarefa',message:'enviou mensagem',result_delivered:'entregou resultado',result_available:'resultado disponível',started:'início registrado',tool:'ferramenta pública',failed:'falha registrada',waiting:'espera registrada'};return `${displayName(event.actor_id)} (${event.actor_id||'ator não informado'}) · ${labels[event.kind]||event.kind}${event.target_id?` → ${displayName(event.target_id)} (${event.target_id})`:''}${event.label?` · ${event.label}`:''}`;}
function applyMotion(){document.body.classList.toggle('paused',paused);document.body.classList.toggle('reduced',$('reduce').checked);$('scene').classList.toggle('charming',$('charm').checked);$('pause').setAttribute('aria-pressed',String(paused));text('pause',paused?'▷ Retomar animações':'Ⅱ Pausar animações');if($('reduce').checked||paused||!$('event-mail').checked)clearEventAnimations(scene);}
async function loadDetail(){
  const agent=state.agent,key=`${agent?.id||''}:${kind}`;
  if(!agent){detailController?.abort();detailController=null;detailKey=key;text('output','Selecione um agente para consultar o detalhe.');return;}
  if(!state.connected){if(key!==detailKey){detailController?.abort();detailController=null;detailKey=key;text('output','Detalhe indisponível · monitor desconectado.');}return;}
  detailController?.abort();const controller=new AbortController();detailController=controller;
  if(key!==detailKey){text('output','Carregando detalhe…');$('output').scrollTop=0;detailKey=key;}
  const timeout=setTimeout(()=>controller.abort(),4500);
  try{
    const query=new URLSearchParams({agent:agent.id,kind});
    const response=await fetch(`/api/detail?${query}`,{method:'GET',credentials:'same-origin',cache:'no-store',signal:controller.signal});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const data=await response.json();if(typeof data.text!=='string')throw new Error('Resposta de detalhe incompatível');
    if(controller!==detailController||key!==`${state.agent?.id}:${kind}`)return;
    const value=safeText(data.text).slice(-65536).split('\n').slice(-2000).join('\n')||'Conteúdo não informado.';
    if($('output').textContent!==value){const scroll=$('output').scrollTop;text('output',value);$('output').scrollTop=$('follow').checked?$('output').scrollHeight:scroll;}
  }catch(error){if(controller!==detailController)return;if(controller.signal.aborted)text('output','Detalhe indisponível · tempo de resposta esgotado.');else text('output',`Detalhe indisponível · ${error.message}`);}
  finally{clearTimeout(timeout);if(controller===detailController)detailController=null;}
}
async function poll(){
  if(busy)return;busy=true;const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),4500);
  try{const response=await fetch('/api/snapshot',{method:'GET',credentials:'same-origin',cache:'no-store',signal:controller.signal});if(!response.ok)throw new Error(`HTTP ${response.status}`);const effects=state.apply(await response.json());lastSuccess=new Date();connectionError='';render();for(const event of effects){if(event.execution_id!==state.executionId)continue;text('last-event',eventDescription(event));if(state.view==='office'&&!paused&&$('event-mail').checked)animateEvent(scene,event,$('reduce').checked);}if(!detailController)void loadDetail();}
  catch(error){state.disconnect();connectionError=controller.signal.aborted?'tempo de resposta esgotado':error.message;detailController?.abort();detailController=null;render();}
  finally{clearTimeout(timeout);busy=false;}
}
$('project').onchange=()=>{state.selectProject($('project').value);render();void loadDetail();};$('execution').onchange=()=>selectExecution($('execution').value);
for(const button of document.querySelectorAll('[data-view]'))button.onclick=()=>{state.setView(button.dataset.view);if(state.view!=='office')clearEventAnimations(scene);const url=new URL(location.href);url.searchParams.set('view',state.view);history.replaceState(null,'',url);render();};
for(const button of document.querySelectorAll('[data-kind]'))button.onclick=()=>{kind=button.dataset.kind;render();void loadDetail();};
function filter(){state.setFilters({source:$('source').value,active:$('active').checked,search:$('search').value});render();}
$('source').onchange=filter;$('active').onchange=filter;$('search').oninput=filter;
$('pause').onclick=()=>{paused=!paused;applyMotion();};$('charm').onchange=applyMotion;$('reduce').onchange=applyMotion;$('refresh').onclick=poll;
$('event-mail').onchange=()=>{try{themeStorage?.setItem('agent-watch-event-mail',String($('event-mail').checked));}catch{/* Preference remains usable without storage. */}applyMotion();};
$('popout').onclick=()=>{persist();const url=new URL(location.origin+location.pathname);url.searchParams.set('compact','1');url.searchParams.set('view',state.view);url.searchParams.set('execution',state.executionId);url.searchParams.set('project',state.projectId);url.searchParams.set('agent',state.agentId);if(!window.open(url.href,'alethe-monitor-compact','width=860,height=780,resizable=yes,scrollbars=yes'))text('popout','Janela bloqueada pelo navegador');};
document.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA','BUTTON'].includes(e.target.tagName)||e.ctrlKey||e.altKey||e.metaKey)return;if(e.key==='/'){e.preventDefault();$('search').focus();}else if(e.key==='a'){$('active').checked=!$('active').checked;filter();}else if(e.key==='r')void poll();else if(e.key==='l'){const tabs=['output','task','result','error'];kind=tabs[(tabs.indexOf(kind)+1)%tabs.length];render();void loadDetail();}});
for(const view of ['panel','office']){
  $(`${view}-run-pages`).querySelector('[data-page-previous]').onclick=()=>{sidebars[view].page--;updateSidebar(view);};
  $(`${view}-run-pages`).querySelector('[data-page-next]').onclick=()=>{sidebars[view].page++;updateSidebar(view);};
}
const sidebarObserver=new ResizeObserver(updateSidebars);
sidebarObserver.observe($('office'));sidebarObserver.observe(document.querySelector('.panel-main'));
new ResizeObserver(()=>render()).observe($('scene'));
applyMotion();render();void poll();setInterval(poll,1000);
