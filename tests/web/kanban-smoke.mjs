// Verificação opcional no Chromium contra a demonstração (dados fictícios); usa Playwright e Chromium já instalados.
// PLAYWRIGHT_MODULE=/caminho/playwright/index.mjs CHROMIUM_EXECUTABLE=/caminho/chrome node tests/web/kanban-smoke.mjs
// Validação do Kanban no Chromium contra o servidor de demonstração (dados fictícios).
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
const repo = new URL('../../', import.meta.url).pathname.replace(/\/$/, '');
const out = process.env.OUT;
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE);
const server = spawn(`${repo}/.venv/bin/python`, ['-m', 'alethe_tui', '--web', '--demo', '--kanban', '--no-open'],
  {cwd: repo, env: {...process.env, PYTHONPATH: `${repo}/src`}});
const url = await new Promise((resolve, reject) => {
  let buf = '';
  server.stdout.on('data', d => { buf += d; const m = buf.match(/http:\/\/\S+/); if (m) resolve(m[0]); });
  setTimeout(() => reject(new Error('servidor não imprimiu URL')), 8000);
});
const results = [];
const check = (name, ok, detail = '') => { results.push(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ' · ' + detail : ''}`); };
const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_EXECUTABLE});
try {
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}, reducedMotion: 'no-preference'});
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto(url);
  await page.waitForSelector('#board .kanban-card', {timeout: 5000});
  // Foca a execução Alethe com pipeline (a que tem cartões de Developer).
  const runs = await page.$$eval('#kanban-runs button', bs => bs.map(b => [b.dataset.runId, b.textContent]));
  const alethe = runs.find(([, t]) => /alethe/i.test(t));
  if (alethe) await page.click(`#kanban-runs button[data-run-id="${alethe[0]}"]`);
  await page.waitForTimeout(300);
  check('view=kanban após login', new URL(page.url()).searchParams.get('view') === 'kanban', page.url().replace(/key=[^&]+/, 'key=…'));
  const heads = await page.$$eval('#board [data-column]', cs => cs.map(c => [c.dataset.column, c.querySelector('h3,h4,header')?.textContent?.trim()]));
  check('seis colunas na ordem', JSON.stringify(heads.map(h => h[0])) === JSON.stringify(['backlog','in_progress','awaiting_tests','testing','done','blocked']), JSON.stringify(heads));
  const labels = ['Backlog','Em progresso','Aguardando testes','Em testes','Pronto','Bloqueado'];
  check('rótulos exatos', heads.every((h, i) => (h[1] || '').startsWith(labels[i])), heads.map(h => h[1]).join(' | '));
  const initialAnims = await page.evaluate(() => document.getAnimations().filter(a => a.effect?.target?.closest?.('#board')).length);
  check('histórico inicial não anima', initialAnims === 0, `animações=${initialAnims}`);
  const before = await page.$$eval('#board .kanban-card', cs => Object.fromEntries(cs.map(c => [c.dataset.taskId, c.closest('[data-column]')?.dataset.column])));
  check('cartão substituído presente', await page.$('#board .kanban-card.superseded') !== null);
  // Espera o advance() da demo (4 s depois de subir) e observa animação de viagem.
  await page.evaluate(() => { window.__flights = []; });
  let sawLift = false, moved = [];
  for (let i = 0; i < 40 && !sawLift; i++) {
    await page.waitForTimeout(150);
    sawLift = await page.evaluate(() => {
      const running = document.getAnimations().filter(a => a.effect?.target?.closest?.('#board') && a.playState === 'running');
      for (const a of running) { const rec = {state: 'running'}; window.__flights.push(rec); a.finished.then(() => rec.state = 'finished', () => rec.state = 'cancelled'); }
      return running.length > 0;
    });
  }
  await page.waitForTimeout(2500);
  const flights = await page.evaluate(() => window.__flights.map(f => f.state));
  check('poll não corta animação em andamento', flights.length > 0 && flights.every(s => s === 'finished'), JSON.stringify(flights));
  const after = await page.$$eval('#board .kanban-card', cs => Object.fromEntries(cs.map(c => [c.dataset.taskId, c.closest('[data-column]')?.dataset.column])));
  moved = Object.keys(after).filter(id => before[id] && before[id] !== after[id]).map(id => `${id.slice(-24)}:${before[id]}→${after[id]}`);
  check('snapshot novo move cartão', moved.length > 0, moved.join(', '));
  check('movimento animado', sawLift);
  const ghosts = await page.evaluate(() => document.querySelectorAll('#board .lifted, #board [data-ghost], .kanban-flight').length);
  check('sem cartão fantasma após o movimento', ghosts === 0, `restos=${ghosts}`);
  if (out) await page.screenshot({path: `${out}/kanban-1440.png`, fullPage: false});
  // Detalhe: começa fechado, abre ao clicar, fecha com Esc e pelo botão.
  check('painel de detalhes começa fechado', await page.evaluate(() => document.querySelector('#kanban-detail').hidden));
  const fullWidth = await page.evaluate(() => [...document.querySelectorAll('#board [data-column]')].every(c => c.getBoundingClientRect().right <= document.querySelector('#board').getBoundingClientRect().right + 1));
  check('fechado, as seis colunas cabem a 1440 px', fullWidth);
  await page.click('#board .kanban-card');
  await page.waitForTimeout(300);
  check('clique abre o painel', await page.evaluate(() => !document.querySelector('#kanban-detail').hidden));
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  check('Esc fecha o painel', await page.evaluate(() => document.querySelector('#kanban-detail').hidden));
  await page.click('#board .kanban-card');
  await page.waitForTimeout(800);
  const detail = await page.evaluate(() => ({name: document.querySelector('#kanban-detail-name')?.textContent, evidence: document.querySelector('#kanban-evidence')?.textContent, output: document.querySelector('#kanban-output')?.textContent}));
  check('detalhe abre com evidência', Boolean(detail.name && detail.evidence), `${detail.name} · ${(detail.evidence || '').slice(0, 60)}`);
  check('detalhe carrega saída', Boolean(detail.output && !/Carregando/.test(detail.output)), (detail.output || '').slice(0, 60));
  // Execução nativa: colunas de teste recolhidas.
  const native = runs.find(([, t]) => /claude|codex/i.test(t));
  if (native) {
    await page.click(`#kanban-runs button[data-run-id="${native[0]}"]`); await page.waitForTimeout(300);
    const collapsed = await page.$$eval('#board [data-column].collapsed', cs => cs.map(c => c.dataset.column));
    check('colunas de teste recolhidas sem pipeline', JSON.stringify(collapsed) === '["awaiting_tests","testing"]', JSON.stringify(collapsed));
  }
  // Temas e larguras sem rolagem lateral da página.
  for (const theme of ['current', 'aura', 'light']) {
    await page.selectOption('#theme', theme);
    for (const width of [1440, 1024, 768, 390]) {
      await page.setViewportSize({width, height: 900}); await page.waitForTimeout(150);
      const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      check(`sem rolagem lateral · ${theme} · ${width}px`, over <= 0, `excesso=${over}`);
      if (out && width === 390 && theme === 'light') await page.screenshot({path: `${out}/kanban-390-light.png`});
    }
  }
  // Pausar: troca de aba e volta não deve deixar animação pendente.
  await page.setViewportSize({width: 1440, height: 1000});
  await page.click('#panel-tab'); await page.click('#kanban-tab'); await page.waitForTimeout(200);
  check('trocar de aba não deixa animação pendente', await page.evaluate(() => document.getAnimations().filter(a => a.effect?.target?.closest?.('#board') && a.playState === 'running').length) === 0);
  check('Painel continua funcionando', await page.evaluate(() => { document.querySelector('#panel-tab').click(); return !document.querySelector('#panel').hidden && document.querySelectorAll('#agents tr').length > 0; }));
  check('zero erros de JavaScript', errors.length === 0, errors.join(' | '));
} finally {
  await browser.close(); server.kill();
}
console.log(results.join('\n'));
process.exitCode = results.some(r => r.startsWith('FAIL')) ? 1 : 0;
