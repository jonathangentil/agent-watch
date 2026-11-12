// Verificação opcional no Chromium contra a demonstração (dados fictícios); usa Playwright e Chromium já instalados.
// PLAYWRIGHT_MODULE=/caminho/playwright/index.mjs CHROMIUM_EXECUTABLE=/caminho/chrome node tests/web/kanban-criteria-smoke.mjs
// Critérios de interface do Kanban no Chromium, com snapshots controlados (dados fictícios da demonstração).
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
const overrides = new Map(); let titleOverride = null;
const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_EXECUTABLE});
const wait = ms => new Promise(r => setTimeout(r, ms));
try {
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}, reducedMotion: 'no-preference'});
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.route('**/api/snapshot*', async route => {
    const response = await route.fetch(); const json = await response.json();
    json.tasks = (json.tasks || []).map(t => ({...t, ...(overrides.has(t.id) ? {column: overrides.get(t.id)} : {}), ...(titleOverride && titleOverride.id === t.id ? {title: titleOverride.title} : {})}));
    await route.fulfill({response, json});
  });
  await page.goto(url);
  await page.waitForSelector('#board .kanban-card');
  const runs = await page.$$eval('#kanban-runs button', bs => bs.map(b => [b.dataset.runId, b.textContent]));
  const alethe = runs.find(([, t]) => /alethe/i.test(t));
  await page.click(`#kanban-runs button[data-run-id="${alethe[0]}"]`);
  await wait(6000); // deixa o advance() da demonstração terminar antes dos movimentos controlados
  const tasks = () => page.$$eval('#board .kanban-card', cs => cs.map(c => ({id: c.dataset.taskId, column: c.closest('[data-column]').dataset.column})));
  const animations = () => page.evaluate(() => document.getAnimations().map(a => ({t: a.effect.getTiming(), k: JSON.stringify(a.effect.getKeyframes?.() || []), target: a.effect.target?.className || ''})));

  // AC-T6-4 · cartão B
  const card = await page.evaluate(() => {
    const c = document.querySelector('#board .kanban-card'); const title = c.querySelector('.kanban-title');
    return {clamp: getComputedStyle(title).webkitLineClamp, chips: [...c.querySelectorAll('.kanban-chip')].map(x => x.textContent), who: c.querySelector('.kanban-who')?.textContent, marker: Boolean(c.querySelector('.kanban-marker')), foot: c.querySelector('.kanban-foot')?.textContent};
  });
  check('AC-T6-4', 'cartão B: título em 3 linhas, responsável, etiquetas e rodapé', card.clamp === '3' && card.marker && card.who && card.chips.some(x => /alethe|claude|codex/.test(x)) && card.chips.some(x => /onda/.test(x)) && /tokens/.test(card.foot) && /(não informado|\d)/.test(card.foot), JSON.stringify(card));

  // AC-T6-5 · texto adversarial inerte e título longo limitado
  const victim = (await tasks())[0].id;
  titleOverride = {id: victim, title: '\u001b[31m<img src=x onerror="window.__xss=1"><b>negrito</b>' + ' palavra'.repeat(80)};
  await wait(2200);
  const inert = await page.evaluate(id => {
    const c = document.querySelector(`#board .kanban-card[data-task-id="${id}"]`); const t = c.querySelector('.kanban-title');
    return {xss: window.__xss === 1, img: c.querySelectorAll('img,b').length, text: t.textContent.slice(0, 40), ansi: /\u001b/.test(t.textContent), lines: Math.round(t.getBoundingClientRect().height / parseFloat(getComputedStyle(t).lineHeight))};
  }, victim);
  check('AC-T6-5', 'título malicioso inerte, sem ANSI e limitado a 3 linhas', !inert.xss && inert.img === 0 && !inert.ansi && /<img/.test(inert.text) && inert.lines <= 3, JSON.stringify(inert));
  titleOverride = null; await wait(1200);

  // AC-T6-A11Y · sem role=button com botão dentro; botões reais e teclado
  const a11y = await page.evaluate(() => ({nested: document.querySelectorAll('#board [role=button] button, #board button button').length, open: [...document.querySelectorAll('#board .kanban-open')].every(b => b.tagName === 'BUTTON'), tester: [...document.querySelectorAll('#board .kanban-tester')].every(b => b.tagName === 'BUTTON'), testers: document.querySelectorAll('#board .kanban-tester').length}));
  check('AC-T6-A11Y', 'sem botão aninhado; abrir e testador são <button>', a11y.nested === 0 && a11y.open && a11y.tester && a11y.testers > 0, JSON.stringify(a11y));

  // AC-T6-6 · testador seleciona pelo teclado e as abas de detalhe carregam
  await page.focus('#board .kanban-tester'); await page.keyboard.press('Enter'); await wait(600);
  const testerName = await page.$eval('#board .kanban-tester', b => b.textContent);
  const detailName = await page.$eval('#kanban-detail-name', n => n.textContent);
  const opened = await page.evaluate(() => !document.querySelector('#kanban-detail').hidden);
  const kinds = {};
  for (const kind of ['output', 'task', 'result', 'error']) {
    await page.click(`#kanban-detail [data-kind="${kind}"]`); await wait(700);
    kinds[kind] = await page.$eval('#kanban-output', o => o.textContent.slice(0, 50));
  }
  check('AC-T6-6', 'Enter no testador abre o detalhe dele; quatro abas carregam', opened && kinds.output && Object.values(kinds).every(v => v && !/Carregando/.test(v)), `${testerName} → ${detailName} · ${JSON.stringify(kinds)}`);
  check('AC-T6-A11Y', 'testador acionável pelo teclado', opened);
  await page.click('#kanban-close'); await wait(200);

  // AC-T6-FOCUS e AC-T6-11 · snapshot sem mudança mantém nós e foco
  await page.evaluate(() => { const c = document.querySelector('#board .kanban-card'); c.__mark = 'same'; c.querySelector('.kanban-open').focus(); });
  await wait(2600);
  const kept = await page.evaluate(() => ({same: document.querySelector('#board .kanban-card').__mark === 'same', focus: document.activeElement?.classList.contains('kanban-open') && document.activeElement.closest('.kanban-card').__mark === 'same'}));
  check('AC-T6-FOCUS', 'dois polls sem mudança mantêm o nó e o foco do teclado', kept.same && kept.focus, JSON.stringify(kept));
  check('AC-T6-11', 'nós reaproveitados entre renders; sem fantasma', kept.same && await page.evaluate(() => document.querySelectorAll('#board .lifted').length === 0));

  // AC-T6-7 · keyframes, durações e intervalo de 140 ms
  let list = await tasks();
  const [m1, m2] = list.filter(t => t.column !== 'done').slice(0, 2);
  overrides.set(m1.id, 'done'); overrides.set(m2.id, 'done');
  let anims = [];
  for (let i = 0; i < 30 && !anims.some(a => a.t.duration === 780); i++) { await wait(100); anims = await animations(); }
  const travel = anims.filter(a => a.t.duration === 780), neighbors = anims.filter(a => a.t.duration === 280);
  const delays = travel.map(a => a.t.delay).sort((a, b) => a - b);
  check('AC-T6-7', 'viagem 780 ms com escala 1,04 e −2°; vizinhos 280 ms; 140 ms entre movimentos', travel.length === 2 && delays[1] - delays[0] === 140 && travel.every(a => /scale\(1\.04\)/.test(a.k) && /rotate\(-2deg\)/.test(a.k)) && neighbors.length > 0, `viagens=${travel.length} delays=${delays} vizinhos=${neighbors.length}`);
  await wait(1800);
  list = await tasks();
  check('AC-T6-INFLIGHT', 'cartões terminam na coluna nova depois dos polls', list.find(t => t.id === m1.id)?.column === 'done' && list.find(t => t.id === m2.id)?.column === 'done');

  // AC-T6-9 · destino fora da área visível sem rolagem automática
  await page.setViewportSize({width: 768, height: 1000}); await wait(400);
  await page.$eval('#board', b => { b.scrollLeft = 0; });
  const offscreen = list.find(t => !['blocked', 'done'].includes(t.column));
  const before = await page.$eval('#board', b => b.scrollLeft);
  overrides.set(offscreen.id, 'blocked');
  let flew = false;
  for (let i = 0; i < 30 && !flew; i++) { await wait(100); flew = (await animations()).some(a => a.t.duration === 780); }
  await wait(1500);
  const after = await page.$eval('#board', b => b.scrollLeft);
  const destVisible = await page.evaluate(id => { const c = document.querySelector(`#board .kanban-card[data-task-id="${id}"]`), b = document.querySelector('#board').getBoundingClientRect(); return c.getBoundingClientRect().left >= b.right; }, offscreen.id);
  check('AC-T6-9', 'destino fora da área: anima e o quadro não rola sozinho', flew && before === after && destVisible, `animou=${flew} scrollLeft ${before}→${after} destinoForaDaÁrea=${destVisible}`);
  await page.setViewportSize({width: 1440, height: 1000}); await wait(300);

  // AC-T6-10 · Movimento reduzido e Pausar animações
  list = await tasks();
  const r1 = list.find(t => t.column !== 'in_progress');
  await page.check('#reduce'); overrides.set(r1.id, 'in_progress');
  let reduced = {travel: 0, flash: false};
  for (let i = 0; i < 30 && !reduced.flash; i++) { await wait(100); reduced = await page.evaluate(id => ({travel: document.getAnimations().filter(a => a.effect.getTiming().duration === 780).length, flash: document.querySelector(`#board .kanban-card[data-task-id="${id}"]`)?.classList.contains('flash')}), r1.id); }
  check('AC-T6-10', 'Movimento reduzido: só destaque, sem viagem', reduced.flash && reduced.travel === 0, JSON.stringify(reduced));
  await page.uncheck('#reduce'); await page.click('#pause');
  const p1 = (await tasks()).find(t => t.column !== 'backlog');
  overrides.set(p1.id, 'backlog');
  let moved = false, anyAnim = 0;
  for (let i = 0; i < 30 && !moved; i++) { await wait(100); moved = (await tasks()).find(t => t.id === p1.id)?.column === 'backlog'; anyAnim = Math.max(anyAnim, (await animations()).filter(a => a.t.duration === 780 || a.t.duration === 280).length); }
  check('AC-T6-10', 'Pausar: troca instantânea, sem animação', moved && anyAnim === 0, `moveu=${moved} animações=${anyAnim}`);
  await page.click('#pause');

  // AC-T6-13 · barra lateral, filtros e paginação
  const all = await page.$$eval('#kanban-runs button', bs => bs.length);
  await page.check('#active'); await wait(300);
  const activeRuns = await page.$$eval('#kanban-runs button', bs => bs.map(b => b.textContent));
  await page.uncheck('#active'); await page.selectOption('#source', 'claude'); await wait(300);
  const claudeRuns = await page.$$eval('#kanban-runs button', bs => bs.map(b => b.textContent));
  await page.selectOption('#source', 'all'); await wait(200);
  const pager = await page.$eval('#kanban-run-pages [data-page-label]', n => n.textContent);
  check('AC-T6-13', 'lista lateral segue Apenas ativos e Origem; paginação presente', all >= 2 && activeRuns.length <= all && claudeRuns.length >= 1 && claudeRuns.every(t => /claude/i.test(t)) && /\d+ \/ \d+/.test(pager), `todas=${all} ativas=${activeRuns.length} claude=${claudeRuns.length} pág=${pager}`);

  check('geral', 'zero erros de JavaScript', errors.length === 0, errors.join(' | '));
} finally { await browser.close(); server.kill(); }
console.log(results.join('\n'));
process.exitCode = results.some(r => r.startsWith('FAIL')) ? 1 : 0;
