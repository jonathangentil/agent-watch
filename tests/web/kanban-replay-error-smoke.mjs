// Verificação opcional no Chromium contra a demonstração (dados fictícios); usa Playwright e Chromium já instalados.
// PLAYWRIGHT_MODULE=/caminho/playwright/index.mjs CHROMIUM_EXECUTABLE=/caminho/chrome node tests/web/kanban-replay-error-smoke.mjs
// AC-T7-40: exceção ao iniciar o replay desfaz o estado e redesenha o quadro ao vivo (dados fictícios).
import {spawn} from 'node:child_process';
const repo = new URL('../../', import.meta.url).pathname.replace(/\/$/, '');
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE);
const server = spawn(`${repo}/.venv/bin/python`, ['-m', 'alethe_tui', '--web', '--demo', '--kanban', '--no-open'], {cwd: repo, env: {...process.env, PYTHONPATH: `${repo}/src`}});
const url = await new Promise((res, rej) => { let b = ''; server.stdout.on('data', d => { b += d; const m = b.match(/http:\/\/\S+/); if (m) res(m[0]); }); setTimeout(() => rej(new Error('sem URL')), 8000); });
const wait = ms => new Promise(r => setTimeout(r, ms)); const out = [];
const check = (id, n, ok, d = '') => out.push(`${ok ? 'PASS' : 'FAIL'} ${id} · ${n}${d ? ' · ' + d : ''}`);
let broken = false;
const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_EXECUTABLE});
try {
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const pageErrors = []; page.on('pageerror', e => pageErrors.push(e.message));
  await page.route('**/api/snapshot*', async route => { const r = await route.fetch(); const j = await r.json(); if (broken) j.tasks = j.tasks.map((t, i) => i === 0 ? {...t, transitions: [{column: 'backlog', at: 'data inválida'}, null, 7]} : t); await route.fulfill({response: r, json: j}); });
  await page.goto(url); await page.waitForSelector('#board .kanban-card');
  const runs = await page.$$eval('#kanban-runs button', bs => bs.map(b => [b.dataset.runId, b.textContent]));
  await page.click(`#kanban-runs button[data-run-id="${runs.find(([, t]) => /alethe/i.test(t))[0]}"]`); await wait(5500);
  // Quebra o replay de forma determinística: buildTimeline recebe transições malformadas e, se isso não lançar, forçamos uma exceção em play.
  broken = true; await wait(1500);
  const live = await page.$$eval('#board .kanban-card', cs => cs.map(c => c.dataset.taskId).sort());
  const forced = await page.evaluate(() => { const orig = Map.prototype.get; let thrown = false;
    // Faz a primeira leitura feita durante startReplay lançar, simulando falha interna no início.
    Map.prototype.get = function (...a) { if (!thrown && window.__arm) { thrown = true; window.__arm = false; Map.prototype.get = orig; throw new Error('falha simulada no início do replay'); } return orig.apply(this, a); };
    window.__arm = true; try { document.querySelector('#replay-start').click(); } catch (e) { return 'propagou: ' + e.message; } finally { Map.prototype.get = orig; window.__arm = false; } return thrown ? 'lançada e contida' : 'não lançou'; });
  await wait(1500);
  const after = await page.evaluate(() => ({bar: document.querySelector('#replay-bar').hidden, start: document.querySelector('#replay-start').hidden, cards: [...document.querySelectorAll('#board .kanban-card')].map(c => c.dataset.taskId).sort()}));
  check('AC-T7-40', 'exceção no início do replay desfaz o estado e redesenha o quadro ao vivo', forced === 'lançada e contida' && after.bar && !after.start && JSON.stringify(after.cards) === JSON.stringify(live), `${forced} · barra oculta=${after.bar} · cartões=${after.cards.length}/${live.length}`);
  broken = false; await wait(1500);
  await page.click('#replay-start'); await wait(700);
  const again = await page.evaluate(() => !document.querySelector('#replay-bar').hidden);
  check('AC-T7-40', 'replay volta a funcionar depois da falha', again);
  await page.click('#replay-live').catch(() => {});
  check('geral', 'falha não deixa o quadro ao vivo parado (render segue redesenhando)', await page.evaluate(() => document.querySelectorAll('#board .kanban-card').length > 0), pageErrors.join(' | '));
} finally { await browser.close(); server.kill(); }
console.log(out.join('\n')); process.exitCode = out.some(r => r.startsWith('FAIL')) ? 1 : 0;
