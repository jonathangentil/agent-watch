// Shared UI state: identities, never names, determine selection and event delivery.
const active = new Set(['running', 'queued']);
const labels = {queued:'aguardando',running:'executando',succeeded:'concluído',turn_complete:'turno concluído',failed:'falhou',timed_out:'tempo esgotado',interrupted:'interrompido',stopped:'parado',skipped:'ignorado',unknown:'estado não confirmado'};
export const stateLabel = status => labels[status] || `estado não confirmado (${safeText(status || 'unknown')})`;
export function safeText(value) {
  return String(value ?? '').replace(/<(think|thinking|analysis|reasoning)\b[^>]*>[\s\S]*?(?:<\/\1\s*>|$)/gi, '[conteúdo interno oculto]')
    .replace(/\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)/g,'').replace(/\x1b\[[0-?]*[ -/]*[@-~]/g,'')
    .replace(/[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]/g,'');
}
export function elapsed(start, end = new Date().toISOString()) {
  if (!start || !end) return 'não informado';
  const seconds = Math.floor((Date.parse(end) - Date.parse(start))/1000);
  if (!Number.isFinite(seconds) || seconds < 0) return 'não informado';
  return `${Math.floor(seconds/60)}m ${String(seconds%60).padStart(2,'0')}s`;
}
export function runPages(heights, availableHeight) {
  const pages=[];let start=0,used=0;
  heights.forEach((height,index)=>{
    if(index>start&&used+height>availableHeight){pages.push({start,end:index});start=index;used=0;}
    used+=height;
  });
  pages.push({start,end:heights.length});return pages;
}
export function executionTokens(snapshot, executionId) {
  const actors=[...new Map(snapshot.agents.filter(a=>a.execution_id===executionId).map(a=>[a.id,a])).values()];
  const known=actors.filter(a=>Number.isSafeInteger(a.tokens)&&a.tokens>=0);
  const leader=snapshot.executions.find(e=>e.id===executionId)?.leader_id;
  const leaderReported=Boolean(leader&&known.some(a=>a.id===leader));
  return {total:known.length?known.reduce((sum,a)=>sum+a.tokens,0):null,reported:known.length,agents:actors.length,
    partial:known.length<actors.length||known.some(a=>a.tokens_partial)||!leaderReported,leaderReported};
}
export class MonitorState {
  constructor(saved = {}) {
    this.snapshot = {agents:[],executions:[],projects:[],events:[],diagnostics:[],totals:{}};
    this.projectId = typeof saved.projectId === 'string' ? saved.projectId : '';
    this.executionId = typeof saved.executionId === 'string' ? saved.executionId : '';
    this.selections = new Map(Object.entries(saved.selections || {}));
    this.setView(saved.view);
    this.filters = {source:'all',active:false,search:'',...saved.filters};
    this.connected = false; this.seen = new Set(); this.initialized = false;
  }
  context() { return {projectId:this.projectId,executionId:this.executionId,selections:Object.fromEntries(this.selections),view:this.view,filters:this.filters}; }
  executions() {
    const matchesSource=actor=>this.filters.source==='all'||actor.source===this.filters.source;
    return this.snapshot.executions.filter(e=>{
      if(this.projectId&&e.project_id!==this.projectId&&!e.project_ids?.includes(this.projectId))return false;
      const agents=this.snapshot.agents.filter(a=>a.execution_id===e.id&&matchesSource(a));
      const ownSource=matchesSource(e);
      if(!ownSource&&!agents.length)return false;
      return !this.filters.active||(ownSource&&active.has(e.status))||agents.some(a=>active.has(a.status));
    });
  }
  get execution() { return this.executions().find(e=>e.id===this.executionId); }
  get agentId() { return this.selections.get(this.executionId) || ''; }
  get agent() { return this.snapshot.agents.find(a=>a.id===this.agentId && a.execution_id===this.executionId); }
  workers() { return this.snapshot.agents.filter(a=>a.execution_id===this.executionId && a.id!==this.execution?.leader_id); }
  tasks() { return (this.snapshot.tasks || []).filter(t=>t.execution_id===this.executionId); }
  visibleAgents() { const q=this.filters.search.toLocaleLowerCase(); return this.workers().filter(a=>(this.filters.source==='all'||a.source===this.filters.source)&&[a.name,a.id,a.source_id,a.task,a.wave,a.model,a.provider,a.effort].join(' ').toLocaleLowerCase().includes(q)); }
  setFilters(filters) { Object.assign(this.filters,filters); this.reconcile(); }
  setView(view) { this.view=['office','kanban'].includes(view)?view:'panel'; }
  selectProject(id) { this.projectId=id; this.reconcile(); }
  selectExecution(id) { if(this.executions().some(e=>e.id===id)) {this.executionId=id;this.reconcile();} }
  selectAgent(id) { if(this.snapshot.agents.some(a=>a.id===id&&a.execution_id===this.executionId)) this.selections.set(this.executionId,id); }
  reconcile() {
    if(this.projectId&&!this.snapshot.projects.some(p=>p.id===this.projectId))this.projectId='';
    const candidates=this.executions();
    if(!candidates.some(e=>e.id===this.executionId))this.executionId=[...candidates].sort((a,b)=>Number(active.has(b.status))-Number(active.has(a.status))||(Date.parse(b.started_at)||0)-(Date.parse(a.started_at)||0))[0]?.id||'';
    const agents=this.snapshot.agents.filter(a=>a.execution_id===this.executionId);
    if(!agents.some(a=>a.id===this.agentId))this.selections.set(this.executionId,this.workers()[0]?.id||agents[0]?.id||'');
  }
  apply(snapshot) {
    if(snapshot?.version!==1 || !['agents','executions','projects','events','diagnostics'].every(k=>Array.isArray(snapshot[k])) || !snapshot.totals)throw new Error('Snapshot incompatível');
    // One sprite per canonical identity, including defensive duplicate handling.
    this.snapshot={...snapshot,agents:[...new Map(snapshot.agents.map(a=>[a.id,a])).values()]};
    this.connected=snapshot.connected===true;this.reconcile();
    const effects=[];
    for(const event of snapshot.events) {
      if(!event.id || this.seen.has(event.id))continue;
      this.seen.add(event.id);
      if(!this.initialized || !this.connected || !event.evidence || event.is_live===false)continue;
      const execution=snapshot.executions.find(e=>e.id===event.execution_id);
      const known=id=>Boolean(id && (execution?.leader_id===id || this.snapshot.agents.some(a=>a.id===id&&a.execution_id===event.execution_id)));
      if(!execution || !known(event.actor_id))continue;
      if(event.kind==='result_available')effects.push({...event,effect:'completion'});
      else if(['delegated','message','result_delivered'].includes(event.kind)&&known(event.target_id)&&event.actor_id!==event.target_id)effects.push({...event,effect:'interaction'});
    }
    this.initialized=true;return effects;
  }
  disconnect() { this.connected=false; }
}
