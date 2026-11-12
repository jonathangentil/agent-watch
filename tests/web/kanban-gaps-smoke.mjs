// Verificação opcional no Chromium contra a demonstração (dados fictícios); usa Playwright e Chromium já instalados.
// PLAYWRIGHT_MODULE=/caminho/playwright/index.mjs CHROMIUM_EXECUTABLE=/caminho/chrome node tests/web/kanban-gaps-smoke.mjs
// Lacunas apontadas pelo QA da etapa 2: cada verificação traz o id do critério e os valores medidos.
import {spawn} from 'node:child_process';
const repo = new URL('../../', import.meta.url).pathname.replace(/\/$/, '');
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE);
const server = spawn(`${repo}/.venv/bin/python`, ['-m', 'alethe_tui', '--web', '--demo', '--kanban', '--no-open'],
  {cwd: repo, env: {...process.env, PYTHONPATH: `${repo}/src`}});
const url = await new Promise((resolve, reject) => {
  let buf = ''; server.stdout.on('data', d => { buf += d; const m = buf.match(/http:\/\/\S+/); if (m) resolve(m[0]); });
  setTimeout(() => reject(new Error('sem URL')), 8000);
});
const results = [];
const check = (id, name, ok, detail = '') => results.push(`${ok ? 'PASS' : 'FAIL'} ${id} · ${name}${detail ? ' · ' + detail : ''}`);
const wait = ms => new Promise(r => setTimeout(r, ms));
const EVIL = '\u001b[31m<img src=x onerror="window.__xss=1"><b>x</b>';
const columns = new Map(); const taskPatch = new Map(); const agentPatch = new Map();
const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_EXECUTABLE});
try {
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}, reducedMotion: 'no-preference'});
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  let last = null;
  await page.route('**/api/snapshot*', async route => {
    const response = await route.fetch(); const json = await response.json();
    json.tasks = (json.tasks || []).map(t => ({...t, ...(taskPatch.get(t.id) || {}), ...(columns.has(t.id) ? {column: columns.get(t.id)} : {})}));
    json.agents = (json.agents || []).map(a => ({...a, ...(agentPatch.get(a.id) || {})}));
    last = json; await route.fulfill({response, json});
  });
  await page.goto(url);
  await page.waitForSelector('#board .kanban-card');
  const runs = await page.$$eval('#kanban-runs button', bs => bs.map(b => [b.dataset.runId, b.textContent]));
  const alethe = runs.find(([, t]) => /alethe/i.test(t))[0];
  await page.click(`#kanban-runs button[data-run-id="${alethe}"]`);
  await wait(6000);
  const own = () => last.tasks.filter(t => t.execution_id === alethe);
  const agentOf = t => last.agents.find(a => a.id === t.agent_id);

  // AC-T6-2 · coluna vazia mostra 'nenhuma tarefa'
  const empty = await page.$$eval('#board [data-column]', cs => cs.filter(c => !c.querySelector('.kanban-card')).map(c => [c.dataset.column, c.querySelector('.kanban-empty')?.textContent]));
  check('AC-T6-2', "coluna vazia mostra 'nenhuma tarefa'", empty.length > 0 && empty.every(([, t]) => t === 'nenhuma tarefa'), JSON.stringify(empty));

  // AC-T6-4 · revisão, testador, selos, cor do marcador, tempo, silêncio e tokens parciais
  const withTester = own().find(t => t.testers?.length && t.revision);
  const tokenTask = own().find(t => t.id !== withTester?.id);
  agentPatch.set(tokenTask.agent_id, {tokens: 1234, tokens_partial: true, idle_seconds: 42, started_at: new Date(Date.now() - 65000).toISOString(), finished_at: null});
  await wait(2200);
  const cardInfo = await page.evaluate(([a, b]) => {
    const read = id => { const c = document.querySelector(`#board .kanban-card[data-task-id="${id}"]`); return c && {chips: [...c.querySelectorAll('.kanban-chip')].map(x => x.textContent), text: c.textContent, foot: c.querySelector('.kanban-foot')?.textContent, status: c.dataset.status, marker: getComputedStyle(c.querySelector('.kanban-marker')).backgroundColor}; };
    return {tester: read(a), tokens: read(b)};
  }, [withTester.id, tokenTask.id]);
  const badgeTexts = {gate_rejected: 'gate REJECTED', superseded: 'substituída pela onda', delivery_unconfirmed: 'entrega não comprovada', delivered: 'entregue', running: 'executando', link_by_wave: 'vínculo pela onda', link_confirmed: 'vínculo confirmado'};
  const expectedBadges = withTester.badges.filter(b => badgeTexts[b]).map(b => badgeTexts[b]);
  check('AC-T6-4', 'etiqueta de revisão, linha do testador e selos traduzidos', cardInfo.tester.chips.some(c => c === withTester.revision) && /⟳ testando:/.test(cardInfo.tester.text) && expectedBadges.every(b => cardInfo.tester.chips.some(c => c.startsWith(b))), `rev=${withTester.revision} selos=${JSON.stringify(expectedBadges)} chips=${JSON.stringify(cardInfo.tester.chips)}`);
  check('AC-T6-4', 'rodapé com tempo, silêncio e tokens parciais', /1m 0\ds/.test(cardInfo.tokens.foot) && /42/.test(cardInfo.tokens.foot) && /1\.234/.test(cardInfo.tokens.foot) && /parcial/.test(cardInfo.tokens.foot), cardInfo.tokens.foot);
  const colors = await page.evaluate(() => { const s = getComputedStyle(document.documentElement); const probe = v => { const d = document.createElement('div'); d.style.background = `var(${v})`; document.body.append(d); const c = getComputedStyle(d).backgroundColor; d.remove(); return c; }; return {green: probe('--green'), red: probe('--red'), amber: probe('--amber')}; });
  const markers = await page.$$eval('#board .kanban-card', cs => cs.map(c => [c.dataset.status, c.dataset.taskColumn, getComputedStyle(c.querySelector('.kanban-marker')).backgroundColor]));
  const want = (s, col) => col === 'blocked' ? 'red' : ['running', 'succeeded', 'turn_complete'].includes(s) ? 'green' : ['failed', 'timed_out', 'interrupted', 'stopped'].includes(s) ? 'red' : 'amber';
  check('AC-T6-4', 'cor do marcador conforme o estado da tarefa (Bloqueado vermelho; demais pelo status do agente)', markers.every(([s, col, c]) => c === colors[want(s, col)]), JSON.stringify([...new Set(markers.map(m => m.join('=')))]));
  agentPatch.clear();

  // AC-T6-5 · todos os campos de dados inertes (cartão e painel)
  const victim = own()[0];
  taskPatch.set(victim.id, {title: EVIL, revision: EVIL, column_evidence: EVIL, testers: [EVIL]});
  agentPatch.set(victim.agent_id, {name: EVIL, role: EVIL, provider: EVIL, model: EVIL, wave: EVIL, source: EVIL});
  await wait(2200);
  await page.click(`#board .kanban-card[data-task-id="${victim.id}"] .kanban-open`); await wait(600);
  const inert = await page.evaluate(id => {
    const c = document.querySelector(`#board .kanban-card[data-task-id="${id}"]`), d = document.querySelector('#kanban-detail');
    return {xss: window.__xss === 1, markup: c.querySelectorAll('img,b').length + d.querySelectorAll('img,b').length, ansi: /\u001b/.test(c.textContent + d.textContent), literal: (c.textContent.match(/<img/g) || []).length, detail: /<img/.test(d.textContent)};
  }, victim.id);
  check('AC-T6-5', 'título, revisão, testador, nome, função, provedor, modelo, onda, origem e evidência inertes', !inert.xss && inert.markup === 0 && !inert.ansi && inert.literal >= 5 && inert.detail, JSON.stringify(inert));
  taskPatch.clear(); agentPatch.clear(); await page.click('#kanban-close'); await wait(1500);

  // AC-T6-6 · clique no cartão seleciona task.agent_id e o painel mostra título, selos e evidência
  const pick = own().find(t => t.badges.length);
  await page.click(`#board .kanban-card[data-task-id="${pick.id}"] .kanban-open`); await wait(700);
  const detail = await page.evaluate(() => ({name: document.querySelector('#kanban-detail-name').textContent, badges: document.querySelector('#kanban-badges').textContent, evidence: document.querySelector('#kanban-evidence').textContent, selected: document.querySelector('#board .kanban-card.selected')?.dataset.taskId}));
  const pickAgent = agentOf(pick);
  check('AC-T6-6', 'clique seleciona o agente da tarefa e mostra título, selos e evidência', detail.selected === pick.id && detail.name.includes(pickAgent.name) && detail.evidence === pick.column_evidence && pick.badges.filter(b => badgeTexts[b]).every(b => detail.badges.includes(badgeTexts[b])), `${detail.name} · selos=${detail.badges} · evidência ok=${detail.evidence === pick.column_evidence}`);
  await page.click('#kanban-close'); await wait(300);

  // AC-T6-7 · keyframes completos, offsets, easing, assentamento e vizinhos
  const mv = own().find(t => t.column !== 'done');
  columns.set(mv.id, 'done');
  let travel = null, neighbor = null;
  for (let i = 0; i < 40 && !travel; i++) { await wait(80); [travel, neighbor] = await page.evaluate(() => { const all = document.getAnimations(); const t = all.find(a => a.effect.getTiming().duration === 780), n = all.find(a => a.effect.getTiming().duration === 280); const pack = a => a && {easing: a.effect.getTiming().easing, delay: a.effect.getTiming().delay, frames: a.effect.getKeyframes().map(k => ({offset: +k.computedOffset.toFixed(2), transform: k.transform}))}; return [pack(t), pack(n)]; }); }
  const offsets = travel?.frames.map(f => f.offset);
  const frames = travel?.frames.map(f => f.transform) || [];
  check('AC-T6-7', 'keyframes: levantar (0,15 · escala 1,04 · −2°), viagem (0,82 · 1,5°), assentar (0,93 · escala 0,99), soltar (1 · none); easing cubic-bezier(.45,.05,.25,1)',
    JSON.stringify(offsets) === '[0,0.15,0.82,0.93,1]' && /scale\(1\.04\) rotate\(-2deg\)/.test(frames[1]) && /rotate\(1\.5deg\)/.test(frames[2]) && /scale\(0\.99\)|scale\(\.99\)/.test(frames[3]) && frames[4] === 'none' && /0\.45, 0\.05, 0\.25, 1/.test(travel.easing),
    `offsets=${JSON.stringify(offsets)} easing=${travel?.easing} frames=${JSON.stringify(frames)}`);
  check('AC-T6-7', 'vizinhos: 280 ms com cubic-bezier(.2,.8,.2,1) até transform none', neighbor && /0\.2, 0\.8, 0\.2, 1/.test(neighbor.easing) && neighbor.frames.at(-1).transform === 'none', JSON.stringify(neighbor));
  await wait(1800);

  // AC-T6-9 · viagem termina na borda visível do quadro quando o destino está fora da área
  await page.setViewportSize({width: 768, height: 1000}); await wait(400);
  await page.$eval('#board', b => { b.scrollLeft = 0; });
  const off = own().find(t => !['blocked', 'done'].includes(t.column) && !columns.has(t.id));
  columns.set(off.id, 'blocked');
  let edge = null;
  for (let i = 0; i < 40 && !edge; i++) {
    await wait(80);
    edge = await page.evaluate(() => {
      const a = document.getAnimations().find(x => x.effect.getTiming().duration === 780); if (!a) return null;
      a.pause(); a.currentTime = a.effect.getTiming().delay + 779;
      const r = a.effect.target.getBoundingClientRect(), b = document.querySelector('#board').getBoundingClientRect();
      const out = {flightRight: Math.round(r.right), flightLeft: Math.round(r.left), boardRight: Math.round(b.right), boardLeft: Math.round(b.left)}; a.play(); return out;
    });
  }
  await wait(1500);
  const scroll = await page.$eval('#board', b => b.scrollLeft);
  check('AC-T6-9', 'fim da viagem dentro da borda visível do quadro, sem rolagem automática', edge && edge.flightRight <= edge.boardRight + 1 && edge.flightLeft >= edge.boardLeft - 1 && edge.flightRight >= edge.boardRight - 40 && scroll === 0, `${JSON.stringify(edge)} scrollLeft=${scroll}`);
  await page.setViewportSize({width: 1440, height: 1000}); await wait(300);

  // AC-T6-10 · preferências compartilhadas com o Escritório
  await page.check('#reduce'); await page.click('#pause'); await wait(200);
  await page.click('#office-tab'); await wait(300);
  const office = await page.evaluate(() => ({reduceControls: document.querySelectorAll('#reduce').length, reduce: document.querySelector('#reduce').checked, paused: document.querySelector('#pause').getAttribute('aria-pressed'), body: [...document.body.classList].filter(c => ['paused', 'reduced'].includes(c))}));
  await page.click('#kanban-tab'); await wait(300);
  const back = await page.evaluate(() => ({reduce: document.querySelector('#reduce').checked, paused: document.querySelector('#pause').getAttribute('aria-pressed')}));
  check('AC-T6-10', 'Pausar e Movimento reduzido são as mesmas preferências no Escritório e no Kanban', office.reduceControls === 1 && office.reduce && office.paused === 'true' && office.body.includes('paused') && office.body.includes('reduced') && back.reduce && back.paused === 'true', `${JSON.stringify(office)} → ${JSON.stringify(back)}`);
  await page.uncheck('#reduce'); await page.click('#pause');

  // AC-T6-13 · barra lateral igual à do Escritório, com os mesmos filtros
  const compare = async () => { await page.click('#office-tab'); await wait(250); const o = await page.$$eval('#office-runs button', bs => bs.map(b => b.dataset.runId + '|' + b.textContent)); await page.click('#kanban-tab'); await wait(250); const k = await page.$$eval('#kanban-runs button', bs => bs.map(b => b.dataset.runId + '|' + b.textContent)); return {o, k}; };
  const plain = await compare();
  await page.check('#active'); await wait(200); const act = await compare();
  await page.uncheck('#active'); await page.selectOption('#source', 'codex'); await wait(200); const src = await compare();
  await page.selectOption('#source', 'all');
  const same = x => JSON.stringify(x.o) === JSON.stringify(x.k);
  check('AC-T6-13', 'lista lateral idêntica à do Escritório sem filtro, com Apenas ativos e com Origem', same(plain) && same(act) && same(src) && act.k.length <= plain.k.length && src.k.every(r => /codex/i.test(r)), `todas=${plain.k.length} ativas=${act.k.length} codex=${src.k.length}`);

  check('geral', 'zero erros de JavaScript', errors.length === 0, errors.join(' | '));
} finally { await browser.close(); server.kill(); }
console.log(results.join('\n'));
process.exitCode = results.some(r => r.startsWith('FAIL')) ? 1 : 0;
