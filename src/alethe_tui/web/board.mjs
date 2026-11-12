// Pure board helpers. Render returned source text through textContent.
import {safeText} from './state.mjs';

export const COLUMNS = [
  ['backlog','Backlog'], ['in_progress','Em progresso'],
  ['awaiting_tests','Aguardando testes'], ['testing','Em testes'],
  ['done','Pronto'], ['blocked','Bloqueado'],
];
export const TEST_COLUMNS = new Set(['awaiting_tests','testing']);

const badges = {
  running:'executando', unconfirmed:'estado não confirmado', no_diff:'sem diff',
  delivered:'entregue', delivery_unconfirmed:'entrega não comprovada',
  link_by_wave:'vínculo pela onda, a confirmar no gate',
  link_confirmed:'vínculo confirmado no gate', link_unconfirmed:'vínculo não confirmado',
  gate_rejected:'gate REJECTED', gate_blocked:'gate BLOCKED', skipped:'ignorado',
  tests_finished:'testes concluídos, aguardando gate',
};
export function badgeLabel(code, task = {}) {
  if (code === 'superseded') return `substituída pela onda ${safeText(String(task.superseded_by_wave).padStart(2,'0'))}`;
  return Object.hasOwn(badges, code) ? badges[code] : safeText(code);
}
export function pipelineActive(agents, executionId) {
  return agents.some(a => a.execution_id === executionId && a.contract === 'developer');
}
export function testerLabel(id, agents) {
  const agent = agents.find(a => a.id === id);
  if (!agent) return safeText(id);
  const roles = {planner:'Planner', developer:'Developer', reviewer:'Reviewer', qa:'QA'};
  const role = Object.hasOwn(roles, agent.role) ? roles[agent.role] : agent.role || 'função não informada';
  return safeText(`${agent.name || id} · ${role} (${agent.provider || 'provedor não informado'})`);
}
export function taskTitle(task) {
  return safeText(task.title) || 'tarefa sem descrição registrada';
}
export function columnMap(tasks) {
  return new Map(tasks.map(task => [task.id, task.column]));
}
export function planMoves(previous, tasks, {limit = 6} = {}) {
  const moves = [];
  if (previous) for (const task of tasks) {
    if (previous.has(task.id) && previous.get(task.id) !== task.column)
      moves.push({taskId:task.id, from:previous.get(task.id), to:task.column});
  }
  return {animated:moves.slice(0,limit), instant:moves.slice(limit)};
}
