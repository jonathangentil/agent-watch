// Verificação opcional no Chromium contra a demonstração (dados fictícios); usa Playwright e Chromium já instalados.
// PLAYWRIGHT_MODULE=/caminho/playwright/index.mjs CHROMIUM_EXECUTABLE=/caminho/chrome node tests/web/kanban-replay-smoke.mjs
// Replay do Kanban no Chromium: snapshots controlados com transições sintéticas (dados fictícios).
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
const T0 = '2026-11-12T10:00:00Z', T1 = '2026-11-12T10:05:00Z', T2 = '2026-11-12T10:20:00Z';
let alethe = null, polls = 0; const liveColumn = new Map(); let untimedId = null;
const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_EXECUTABLE});
try {
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}, reducedMotion: 'no-preference'});
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.route('**/api/snapshot*', async route => {
    const response = await route.fetch(); const json = await response.json(); polls++;
    json.tasks = (json.tasks || []).map((t, i) => {
      if (t.execution_id !== alethe) return t;
      const column = liveColumn.get(t.id) || t.column;
      // Todos aparecem em Backlog em T0 e vão juntos à coluna atual em T1 (um lote grande); um deles ganha etapa extra sem horário.
      const transitions = [{column: 'backlog', at: T0, evidence: 'sintético'}];
      if (column !== 'backlog') transitions.push({column, at: T1, evidence: 'sintético'});
      if (t.id === untimedId) { transitions.push({column: 'blocked', at: null, evidence: 'sintético sem horário'}); transitions.push({column, at: T2, evidence: 'sintético'}); }
      return {...t, column, transitions};
    });
    await route.fulfill({response, json});
  });
  await page.goto(url);
  await page.waitForSelector('#board .kanban-card');
  const runs = await page.$$eval('#kanban-runs button', bs => bs.map(b => [b.dataset.runId, b.textContent]));
  alethe = runs.find(([, t]) => /alethe/i.test(t))[0];
  await page.click(`#kanban-runs button[data-run-id="${alethe}"]`);
  await wait(6000);
  const live = await page.$$eval('#board .kanban-card', cs => cs.map(c => [c.dataset.taskId, c.closest('[data-column]').dataset.column]));
  untimedId = live.find(([, c]) => c !== 'backlog')[0];
  await wait(1500);
  const cards = () => page.$$eval('#board .kanban-card', cs => cs.map(c => [c.dataset.taskId, c.closest('[data-column]').dataset.column]));

  // AC-T7-19 · botão no cabeçalho do quadro
  const startBtn = await page.$eval('#replay-start', b => ({text: b.textContent.trim(), visible: b.offsetParent !== null, inHeader: Boolean(b.closest('#kanban'))}));
  check('AC-T7-19', 'botão ▶ Replay no quadro', startBtn.text === '▶ Replay' && startBtn.visible && startBtn.inHeader, JSON.stringify(startBtn));

  // AC-T7-33 · Pausar animações desativa o botão
  await page.click('#pause'); await wait(150);
  const disabled = await page.$eval('#replay-start', b => b.disabled);
  await page.click('#pause'); await wait(150);
  const enabled = await page.$eval('#replay-start', b => !b.disabled);
  check('AC-T7-33', 'Pausar animações desativa o botão Replay', disabled && enabled, `pausado=${disabled} liberado=${enabled}`);

  // AC-T7-20, 28 · quadro vazio, barra visível e aviso exato
  const atStart = await page.evaluate(() => {
    const before = document.querySelectorAll('#board .kanban-card').length;
    const obs = new MutationObserver(() => {});
    obs.observe(document.querySelector('#board'), {childList: true, subtree: true});
    document.querySelector('#replay-start').click();
    const records = obs.takeRecords(); obs.disconnect();
    const isCard = n => n.nodeType === 1 && n.classList.contains('kanban-card');
    let present = before, minCards = before;
    for (const r of records) { present -= [...r.removedNodes].filter(isCard).length; minCards = Math.min(minCards, present); present += [...r.addedNodes].filter(isCard).length; }
    return {before, minCards, after: document.querySelectorAll('#board .kanban-card').length, bar: !document.querySelector('#replay-bar').hidden, notice: [...document.querySelectorAll('#kanban *')].some(n => n.children.length === 0 && n.textContent.trim() === 'O replay mostra só as transições registradas nos artefatos; não é uma gravação da tela.' && n.offsetParent !== null)};
  });
  check('AC-T7-20', 'Replay monta o quadro vazio (0 cartões) e inicia com a barra visível', atStart.minCards === 0 && atStart.bar, JSON.stringify(atStart));
  check('AC-T7-28', 'aviso fixo exato visível', atStart.notice);

  // AC-T7-21 · motor FLIP sem o limite de 6 no lote grande
  let maxTravel = 0;
  const perStep = new Map();
  for (let i = 0; i < 160; i++) { await wait(50); const pos = await page.$eval('#replay-position', r => r.value).catch(() => 'fim'); const n = await page.evaluate(() => document.getAnimations().filter(a => a.effect.getTiming().duration === 780).length); perStep.set(pos, Math.max(perStep.get(pos) || 0, n)); if (await page.$eval('#replay-bar', b => b.hidden)) break; }
  for (let i = 0; i < 0; i++) { await wait(50); maxTravel = Math.max(maxTravel, await page.evaluate(() => document.getAnimations().filter(a => a.effect.getTiming().duration === 780).length)); }
  maxTravel = Math.max(...perStep.values());
  check('AC-T7-21', 'lote de 8 transições em T1 vira um passo com mais de 6 viagens FLIP', perStep.get('1') > 6, `viagensPorPasso=${JSON.stringify(Object.fromEntries(perStep))}`);

  // F1 · lote grande não é cortado: as viagens do passo 1 terminam (finished), não são canceladas
  await page.click('#replay-live').catch(() => {}); await wait(300);
  await page.click('#replay-start');
  await page.evaluate(() => { window.__flights = []; window.__obs = setInterval(() => { for (const a of document.getAnimations()) if (a.effect.getTiming().duration === 780 && !a.__seen) { a.__seen = 1; const rec = {s: 'running', pos: document.querySelector('#replay-position').value, t0: performance.now()}; window.__flights.push(rec); a.finished.then(() => { rec.s = 'finished'; rec.ms = Math.round(performance.now() - rec.t0); }, () => { rec.s = 'cancelled'; rec.ms = Math.round(performance.now() - rec.t0); rec.bar = document.querySelector('#replay-bar').hidden ? 'fim' : document.querySelector('#replay-position').value; }); } }, 30); });
  let doneF1 = false; const tF1 = Date.now();
  while (!doneF1 && Date.now() - tF1 < 20000) { await wait(150); doneF1 = await page.$eval('#replay-bar', b => b.hidden); }
  const flightsF1 = await page.evaluate(() => { clearInterval(window.__obs); return window.__flights; });
  check('F1', 'lote de 8 e último lote terminam sem corte (nenhuma viagem cancelada)', flightsF1.length >= 8 && flightsF1.every(x => x.s === 'finished'), JSON.stringify(flightsF1.filter(x => x.s !== 'finished').concat(flightsF1.slice(-2))));
  // F2, F4, F7 · cartão só com dados estáveis; quadro vazio visível; relógio no início; foco
  await page.click('#replay-start');
  const early = await page.evaluate(() => ({cards: document.querySelectorAll('#board .kanban-card').length, clock: document.querySelector('#replay-clock').textContent, focus: document.activeElement?.id}));
  await wait(350);
  const stillEmpty = await page.evaluate(() => document.querySelectorAll('#board .kanban-card').length);
  await wait(900);
  const replayCard = await page.evaluate(() => { const c = document.querySelector('#board .kanban-card'); return c && {testers: c.querySelectorAll('.kanban-tester').length, chips: [...c.querySelectorAll('.kanban-chip')].map(x => x.textContent), foot: c.querySelector('.kanban-foot')?.textContent || '', flash: document.querySelectorAll('#board .kanban-card.flash').length}; });
  check('F4', "quadro vazio visível por ~0,5 s e relógio 'início do replay'", early.cards === 0 && stillEmpty === 0 && early.clock === 'início do replay', JSON.stringify({...early, stillEmpty}));
  check('F4', 'aparições do passo 0 recebem destaque', replayCard && replayCard.flash > 0, JSON.stringify(replayCard));
  check('F2', 'cartão do replay sem testador, gate, selos, revisão, tempos ou tokens', replayCard && replayCard.testers === 0 && !replayCard.chips.some(x => /gate|rev-|entreg|vínculo|substituída|executando/.test(x)) && !/tokens|sem saída|\dm \d/.test(replayCard.foot), JSON.stringify(replayCard));
  check('F7', 'foco vai para play/pausa ao iniciar', early.focus === 'replay-play', early.focus);
  await page.click('#replay-live'); await wait(200);
  check('F7', 'foco volta para ▶ Replay ao sair', await page.evaluate(() => document.activeElement?.id === 'replay-start'));
  // AC-T7-25 · relógio com horário pt-BR
  if (await page.$eval('#replay-bar', b => b.hidden)) await page.click('#replay-start');
  const expectT1 = await page.evaluate(t => new Date(t).toLocaleTimeString('pt-BR'), T1);
  const clockSeen = new Set();
  for (let i = 0; i < 40; i++) { await wait(80); clockSeen.add(await page.$eval('#replay-clock', c => c.textContent)); }
  check('AC-T7-25', 'relógio mostra o horário do passo em pt-BR', clockSeen.has(expectT1), `esperado=${expectT1} visto=${[...clockSeen].join(' | ')}`);

  // AC-T7-29, 30 · snapshots chegam durante o replay sem redesenhar o quadro
  if (await page.$eval('#replay-bar', b => b.hidden)) await page.click('#replay-start');
  await wait(300); await page.click('#replay-play'); await wait(100); // pausa a reprodução
  const paused = await page.evaluate(() => ({pos: document.querySelector('#replay-position').value, pressed: document.querySelector('#replay-play').getAttribute('aria-pressed')}));
  await page.evaluate(() => document.querySelectorAll('#board .kanban-card').forEach(c => { c.__mark = 1; }));
  const changed = live.find(([, c]) => c === 'in_progress')?.[0] || live[0][0];
  liveColumn.set(changed, 'done');
  const pollsBefore = polls; await wait(2600);
  const during = await page.evaluate(() => ({kept: [...document.querySelectorAll('#board .kanban-card')].every(c => c.__mark === 1), pos: document.querySelector('#replay-position').value, bar: !document.querySelector('#replay-bar').hidden}));
  check('AC-T7-22', 'play/pausa interrompe e mantém a posição', paused.pos === during.pos, `antes=${JSON.stringify(paused)} depois=${during.pos}`);
  check('AC-T7-30', 'snapshots durante o replay não redesenham o quadro nem encerram o replay', polls > pollsBefore && during.kept && during.bar, `polls=${polls - pollsBefore} nósMantidos=${during.kept}`);

  // AC-T7-24, 26 · barra de posição aplica o estado; passo sem horário
  const max = await page.$eval('#replay-position', r => +r.max);
  const states = [];
  for (let i = 0; i <= max; i++) {
    await page.$eval('#replay-position', (r, v) => { r.value = String(v); r.dispatchEvent(new Event('input', {bubbles: true})); r.dispatchEvent(new Event('change', {bubbles: true})); }, i);
    await wait(120);
    states.push(await page.evaluate(id => ({clock: document.querySelector('#replay-clock').textContent, col: document.querySelector(`#board .kanban-card[data-task-id="${id}"]`)?.closest('[data-column]').dataset.column, anims: document.getAnimations().filter(a => a.effect.getTiming().duration === 780).length}), untimedId));
  }
  const untimedStep = states.find(s => s.col === 'blocked');
  check('AC-T7-24', 'range de posição aplica o estado de cada passo sem animação', states.length === max + 1 && states.every(s => s.anims === 0) && Boolean(untimedStep), `passos=${states.length} colunas=${states.map(s => s.col).join(',')}`);
  check('AC-T7-26', "passo sem horário mostra 'horário não informado'", untimedStep?.clock === 'horário não informado', untimedStep?.clock);

  // AC-T7-23 · velocidades mudam o intervalo entre passos
  const measure = async speed => {
    await page.$eval('#replay-position', r => { r.value = '0'; r.dispatchEvent(new Event('input', {bubbles: true})); r.dispatchEvent(new Event('change', {bubbles: true})); });
    await page.click(`[data-replay-speed="${speed}"]`); await wait(50);
    const start = Date.now(); await page.click('#replay-play');
    let pos = '0'; while (pos === '0' && Date.now() - start < 6000) { await wait(20); pos = await page.$eval('#replay-position', r => r.value); }
    const elapsed = Date.now() - start; await page.click('#replay-play'); return elapsed;
  };
  const t1 = await measure(1), t4 = await measure(4);
  const pressed = await page.$$eval('[data-replay-speed]', bs => bs.map(b => b.dataset.replaySpeed + '=' + b.getAttribute('aria-pressed')));
  check('AC-T7-23', 'passo de 9 movimentos: 1× ≈ 2400 ms (0,78+8×0,14+0,5) e 4× ≈ 600 ms; botão ativo marcado', t1 > 2100 && t1 < 2900 && t4 > 450 && t4 < 900 && pressed.includes('4=true'), `1×=${t1}ms 4×=${t4}ms ${pressed}`);

  // AC-T7-27, 29, 31 · Voltar ao vivo mostra o estado que chegou durante o replay
  await page.click('#replay-live'); await wait(400);
  const back = await page.evaluate(id => ({bar: document.querySelector('#replay-bar').hidden, col: document.querySelector(`#board .kanban-card[data-task-id="${id}"]`)?.closest('[data-column]').dataset.column}), changed);
  check('AC-T7-27', "botão 'Voltar ao vivo' encerra o replay", back.bar);
  check('AC-T7-29', 'state recebeu o snapshot que chegou durante o replay', back.col === 'done', `coluna=${back.col}`);
  check('AC-T7-31', 'Voltar ao vivo redesenha com state.tasks()', back.col === 'done' && (await cards()).length === live.length);

  // AC-T7-32 · fim do replay volta ao quadro ao vivo
  await page.click('[data-replay-speed="4"]').catch(() => {});
  await page.click('#replay-start'); await page.click('[data-replay-speed="4"]');
  let ended = false; const t0 = Date.now();
  while (!ended && Date.now() - t0 < 15000) { await wait(150); ended = await page.$eval('#replay-bar', b => b.hidden); }
  const endCols = Object.fromEntries(await cards()); const liveNow = Object.fromEntries(live.map(([id, c]) => [id, liveColumn.get(id) || c]));
  check('AC-T7-32', 'fim do replay volta ao quadro ao vivo', ended && Object.keys(liveNow).every(id => endCols[id] === liveNow[id]), `terminou=${ended}`);

  // AC-T7-34 · Movimento reduzido reproduz só destaques
  await page.check('#reduce'); await page.click('#replay-start'); await page.click('[data-replay-speed="4"]');
  let travel = 0, flash = 0;
  for (let i = 0; i < 40; i++) { await wait(60); const r = await page.evaluate(() => ({t: document.getAnimations().filter(a => a.effect.getTiming().duration === 780).length, f: document.querySelectorAll('#board .kanban-card.flash').length})); travel = Math.max(travel, r.t); flash = Math.max(flash, r.f); }
  check('AC-T7-34', 'Movimento reduzido: só destaques, sem viagem', travel === 0 && flash > 0, `viagens=${travel} destaques=${flash}`);
  await page.click('#replay-live').catch(() => {}); await page.uncheck('#reduce');

  check('geral', 'zero erros de JavaScript', errors.length === 0, errors.join(' | '));
} finally { await browser.close(); server.kill(); }
console.log(results.join('\n'));
process.exitCode = results.some(r => r.startsWith('FAIL')) ? 1 : 0;
