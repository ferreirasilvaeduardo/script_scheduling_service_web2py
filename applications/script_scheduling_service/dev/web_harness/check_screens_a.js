// Telas do CR-021b1 na aplicacao com o backend FAKE: lista de tickets, agentes, Entrada, log e parametro.
'use strict';

const h = require('./common');

const SHOTS = h.shots('screens_a');
const { BASE, check } = h;
const login = (browser, options) => h.login(browser, options);

async function ticketsRefresh(page) {
  await page.goto(BASE + '/tickets/index');
  const root = page.locator('[data-component="ticketsRefresh"]');
  const status = root.locator('[data-ref="status"]');
  const toggle = root.locator('[data-ref="toggle"]');
  check('tickets: desligada no inicio', !(await toggle.isChecked()) && (await status.textContent()) === 'Atualização automática desligada.');
  const marker = await root.locator('[data-sss-fragment="tickets"]').evaluate((el) => { el.setAttribute('data-old', '1'); return true; });
  await toggle.check();
  check('tickets: ligada mostra o intervalo', (await status.textContent()) === 'Atualização a cada 10 segundos.');
  await page.waitForTimeout(10800);
  check('tickets: fragmento trocado pelo do servidor', marker && (await root.locator('[data-sss-fragment="tickets"][data-old]').count()) === 0 &&
    (await root.locator('[data-sss-fragment="tickets"] table').count()) === 1);
  check('tickets: horario da atualizacao', /^Atualizada às \d\d:\d\d:\d\d\.$/.test(await status.textContent()), await status.textContent());
  await toggle.uncheck();
  check('tickets: desligar volta o texto', (await status.textContent()) === 'Atualização automática desligada.');
}

async function agents(page) {
  await page.goto(BASE + '/audit/agents');
  const root = page.locator('[data-component="agentsRefresh"]');
  const status = root.locator('[data-ref="status"]');
  const interval = await root.getAttribute('data-interval');
  check('agentes: texto inicial com horario e intervalo',
    new RegExp('^Atualizado às \\d\\d:\\d\\d:\\d\\d\\. Atualização automática a cada ' + interval + ' segundos\\.$').test(await status.textContent()),
    await status.textContent());
  const details = root.locator('details[data-agent]');
  const hasDetails = (await details.count()) > 0;
  if (hasDetails) { await details.first().evaluate((el) => { el.open = true; }); }
  const code = hasDetails ? await details.first().getAttribute('data-agent') : null;
  await root.locator('[data-sss-fragment="agentes"]').evaluate((el) => el.setAttribute('data-old', '1'));
  await page.waitForTimeout(parseInt(interval, 10) * 1000 + 1500);
  check('agentes: fragmento trocado', (await root.locator('[data-sss-fragment="agentes"][data-old]').count()) === 0);
  if (hasDetails) {
    check('agentes: lista aberta continua aberta', await root.locator('details[data-agent="' + code + '"]').evaluate((el) => el.open));
  }
  // Falha do servidor: interrompe e avisa.
  await page.route('**/audit/agents.load**', (route) => route.fulfill({ status: 500, body: 'x' }));
  await page.waitForTimeout(parseInt(interval, 10) * 1000 + 1500);
  check('agentes: erro interrompe', (await status.textContent()) === 'Atualização automática interrompida. Recarregue a página.');
  check('agentes: erro avisa por toast', (await page.locator('.sss-toast-error').count()) === 1);
  await page.unroute('**/audit/agents.load**');
  page.problems = page.problems.filter((p) => !p.includes('500'));
}

async function inputs(page) {
  await page.goto(BASE + '/inputs/index?environment=PRODUCAO&script_id=1');
  const root = page.locator('[data-component="inputUpload"]');
  check('entrada: formulario de envio presente', (await root.count()) === 1, page.url());
  if (!(await root.count())) { return; }
  const modal = root.locator('[data-ref="modal"]');
  await root.locator('input[type="file"]').setInputFiles({ name: 'teste.txt', mimeType: 'text/plain', buffer: Buffer.from('abc') });
  await root.locator('[data-ref="replace"]').check();
  await root.locator('[data-ref="submit"]').click();
  check('entrada: substituir pede confirmacao', await modal.isVisible());
  check('entrada: foco no Cancelar', await root.locator('[data-ref="cancel"]').evaluate((el) => document.activeElement === el));
  await page.keyboard.press('Escape');
  check('entrada: Esc fecha e devolve o foco ao Enviar', !(await modal.isVisible()) &&
    await root.locator('[data-ref="submit"]').evaluate((el) => document.activeElement === el));
  await root.locator('[data-ref="submit"]').click();
  let posted = null;
  page.on('request', (r) => { if (r.method() === 'POST' && r.url().includes('/inputs/upload')) { const buf = r.postDataBuffer(); posted = buf ? buf.toString('latin1') : ''; } });
  await Promise.all([page.waitForNavigation(), root.locator('[data-action="confirm"]').click()]);
  // O Playwright nao expoe o corpo multipart com arquivo: confere o POST e a resposta do servidor.
  check('entrada: confirmar envia o formulario', posted !== null &&
    (await page.locator('.sss-alert').allTextContents()).join(' ').includes('Arquivo enviado'));
  check('entrada: modal fechado e sem modal-open', !(await page.evaluate(() => document.body.classList.contains('modal-open'))));
}

async function logViewer(page) {
  await page.goto(BASE + '/tickets/detail/17');
  const root = page.locator('[data-component="logViewer"]');
  const area = root.locator('[data-ref="area"]');
  await page.waitForFunction(() => /Log completo|Acompanhando/.test(document.querySelector('[data-ref="statusText"]').textContent), null, { timeout: 15000 });
  const text = await area.textContent();
  check('log: texto carregado por partes', text.length > 65536, String(text.length));
  check('log: terminal termina em Log completo', (await root.locator('[data-ref="statusText"]').textContent()) === 'Log completo.');
  check('log: pausar desabilitado no fim', await root.locator('[data-ref="pause"]').isDisabled());
  check('log: rolado ate o fim (seguir)', await area.evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight <= 8));
  await area.evaluate((el) => { el.scrollTop = 0; el.dispatchEvent(new Event('scroll')); });
  check('log: rolar para cima desmarca Seguir', !(await root.locator('[data-ref="follow"]').isChecked()));
  await root.locator('[data-ref="follow"]').check();
  check('log: marcar Seguir rola ao fim', await area.evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight <= 8));
  check('log: html do log fica texto', (await area.locator('*').count()) === 0);
  await page.screenshot({ path: SHOTS + '/log.png' });

  // Ticket em andamento: pausar e retomar.
  await page.goto(BASE + '/tickets/index?status=RUNNING');
  const link = page.locator('a[href*="/tickets/detail/"]').first();
  if (!(await link.count())) { check('log: ticket RUNNING no seed', false); return; }
  await Promise.all([page.waitForNavigation(), link.click()]);
  const runRoot = page.locator('[data-component="logViewer"]');
  await page.waitForFunction(() => document.querySelector('[data-ref="statusText"]').textContent === 'Acompanhando a execução.', null, { timeout: 15000 });
  check('log: badge com a classe da situacao', (await runRoot.locator('[data-ref="badge"]').getAttribute('class')).split(' ').length === 2);
  await runRoot.locator('[data-action="togglePause"]').click();
  check('log: pausar', (await runRoot.locator('[data-ref="pauseLabel"]').textContent()) === 'Retomar' &&
    (await runRoot.locator('[data-ref="statusText"]').textContent()) === 'Atualização pausada.');
  await runRoot.locator('[data-action="togglePause"]').click();
  check('log: retomar', (await runRoot.locator('[data-ref="pauseLabel"]').textContent()) === 'Pausar');
  await page.route('**/logs/chunk**', (route) => route.fulfill({ status: 404, body: 'x' }));
  await page.waitForTimeout(4000);
  check('log: 404 encerra com mensagem', (await runRoot.locator('[data-ref="statusText"]').textContent()) === 'Não foi possível acompanhar o log deste ticket. Recarregue a página.');
  await page.unroute('**/logs/chunk**');
  page.problems = page.problems.filter((p) => !p.includes('404'));
}

async function parameterForm(page) {
  await page.goto(BASE + '/admin_parameters/form');
  const root = page.locator('[data-component="parameterForm"]');
  const type = root.locator('[data-ref="type"]');
  const options = root.locator('[data-ref="optionsBox"]');
  const regexBox = root.locator('[data-ref="regexBox"]');
  const hidden = root.locator('[data-ref="options"]');
  check('parametro: Texto mostra regex e esconde opcoes', (await regexBox.isVisible()) && !(await options.isVisible()));
  await type.selectOption('SELECT');
  check('parametro: Lista mostra opcoes com uma linha', (await options.isVisible()) && !(await regexBox.isVisible()) &&
    (await root.locator('.sss-options-row').count()) === 1);
  check('parametro: regex desabilitada fora de Texto', await root.locator('#field-validation_regex').isDisabled());
  const row = (i) => root.locator('[data-ref="optionRows"] .sss-options-row').nth(i);
  await row(0).locator('[data-field="value"]').fill('2');
  await row(0).locator('[data-field="label"]').fill('Dois');
  check('parametro: digitar mantem o foco', await row(0).locator('[data-field="label"]').evaluate((el) => document.activeElement === el));
  await root.locator('[data-action="addRow"]').click();
  await row(1).locator('[data-field="value"]').fill('1');
  await row(1).locator('[data-field="label"]').fill('Um "aspas"');
  check('parametro: JSON na ordem do usuario', (await hidden.inputValue()) === '{"2":"Dois","1":"Um \\"aspas\\""}', await hidden.inputValue());
  await root.locator('[data-action="addRow"]').click();
  await row(1).locator('[data-action="removeRow"]').click();
  check('parametro: remover tira a linha certa', (await root.locator('.sss-options-row').count()) === 2 &&
    (await row(0).locator('[data-field="value"]').inputValue()) === '2' && (await row(1).locator('[data-field="value"]').inputValue()) === '');
  check('parametro: foco no Remover que ocupou o lugar', await row(1).locator('[data-action="removeRow"]').evaluate((el) => document.activeElement === el));
  check('parametro: linha vazia nao entra no JSON', (await hidden.inputValue()) === '{"2":"Dois"}', await hidden.inputValue());
  await row(1).locator('[data-action="removeRow"]').click();
  check('parametro: remover a ultima linha leva o foco a anterior', await row(0).locator('[data-action="removeRow"]').evaluate((el) => document.activeElement === el));
  await row(0).locator('[data-action="removeRow"]').click();
  check('parametro: lista vazia leva o foco ao Adicionar', await root.locator('[data-ref="addOption"]').evaluate((el) => document.activeElement === el));
  check('parametro: lista vazia manda JSON vazio', (await hidden.inputValue()) === '');
  await type.selectOption('TEXT');
  check('parametro: fora de Lista o JSON vai vazio', (await hidden.inputValue()) === '');
  await root.locator('[data-ref="sensitive"]').check();
  check('parametro: sigiloso mostra aviso e mascara o padrao', (await root.locator('[data-ref="sensitiveWarning"]').isVisible()) &&
    (await root.locator('[data-ref="defaultValue"]').getAttribute('type')) === 'password');
  await root.locator('[data-ref="sensitive"]').uncheck();
  check('parametro: desmarcar volta', !(await root.locator('[data-ref="sensitiveWarning"]').isVisible()) &&
    (await root.locator('[data-ref="defaultValue"]').getAttribute('type')) === 'text');
  await root.locator('#field-validation_regex').fill('[0-9]+');
  await root.locator('[data-ref="testValue"]').fill('123');
  await root.locator('[data-action="test"]').click();
  await page.waitForFunction(() => document.querySelector('[data-ref="testResult"]').textContent !== '');
  const res = root.locator('[data-ref="testResult"]');
  check('parametro: testar valor valido', (await res.getAttribute('class')).includes('sss-test-ok') && (await res.textContent()).startsWith('Válido.'), await res.textContent());
  await root.locator('[data-ref="testValue"]').fill('abc');
  await root.locator('[data-action="test"]').click();
  await page.waitForFunction(() => document.querySelector('[data-ref="testResult"]').className.includes('sss-test-error'));
  check('parametro: testar valor invalido', !(await res.getAttribute('class')).includes('sss-test-ok'), await res.textContent());
  check('parametro: botao Testar reabilitado', !(await root.locator('[data-ref="testButton"]').isDisabled()));
  await page.screenshot({ path: SHOTS + '/parametro.png', fullPage: true });
}

async function layouts(browser) {
  for (const scheme of ['light', 'dark']) {
    for (const width of [390, 1280]) {
      const page = await login(browser, { colorScheme: scheme, viewport: { width, height: 844 } });
      for (const path of ['/admin_parameters/form', '/tickets/detail/17', '/tickets/index', '/audit/agents']) {
        await page.goto(BASE + path);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
        check('layout ' + scheme + ' ' + width + ' ' + path + ': sem rolagem horizontal', !overflow);
      }
      await page.goto(BASE + '/admin_parameters/form');
      await page.locator('[data-ref="type"]').selectOption('SELECT');
      await page.screenshot({ path: SHOTS + '/parametro-' + scheme + '-' + width + '.png', fullPage: true });
      check('layout ' + scheme + ' ' + width + ': console limpo', page.problems.length === 0, page.problems.join(' | '));
      await page.context().close();
    }
  }
}

(async () => {
  const browser = await h.chromium.launch();
  const page = await login(browser);
  await h.run([ticketsRefresh, agents, inputs, logViewer, parameterForm].map((f) => {
    const step = () => f(page);
    Object.defineProperty(step, 'name', { value: f.name });
    return step;
  }));
  await layouts(browser);
  check('console sem erros nem violacao de CSP', page.problems.length === 0, page.problems.join(' | '));
  await browser.close();
  process.exit(h.report());
})();
