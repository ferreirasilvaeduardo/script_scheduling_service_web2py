// Telas do CR-021b2 na aplicacao com o backend FAKE: matriz, homologacao, vinculos, regra e disparo.
'use strict';

const h = require('./common');

const SHOTS = h.shots('screens_b');
const { BASE, check, focused, modalOpen } = h;
const login = (browser, options) => h.login(browser, options);

async function matrix(page) {
  await page.goto(BASE + '/admin_profiles/matrix/2');
  const root = page.locator('[data-component="permissionMatrix"]');
  const status = root.locator('[data-ref="statusText"]');
  check('matriz: sem alteracao no inicio', (await status.textContent()) === 'Nenhuma alteração pendente.');
  check('matriz: aba Funcionalidades aberta', (await root.locator('[data-panel="funcs"]').isVisible()) &&
    !(await root.locator('[data-panel="ambs"]').isVisible()));
  const counter = root.locator('[data-counter="funcs"]');
  const before = parseInt(await counter.textContent(), 10);
  const box = root.locator('[data-panel="funcs"] input[type="checkbox"]:not(:disabled)').first();
  const wasChecked = await box.isChecked();
  await box.setChecked(!wasChecked);
  check('matriz: contador acompanha', parseInt(await counter.textContent(), 10) === before + (wasChecked ? -1 : 1));
  check('matriz: 1 alteracao pendente', (await status.textContent()) === '1 alteração pendente.');
  await root.locator('[data-action="openTab"][data-tab="scrs"]').click();
  check('matriz: trocar de aba', (await root.locator('[data-panel="scrs"]').isVisible()) &&
    (await root.locator('[data-tab="scrs"]').getAttribute('aria-selected')) === 'true');
  const search = root.locator('[data-action="filterScripts"]');
  await search.fill('zzzz-nada');
  check('matriz: busca sem resultado', await root.locator('[data-panel="scrs"] [data-no-result]').isVisible());
  await search.fill('');
  const group = root.locator('[data-panel="scrs"] [data-action="markGroup"]').first();
  const gid = await group.getAttribute('data-group');
  await group.click();
  const states = await root.locator('fieldset[data-group="' + gid + '"] input[type="checkbox"]:not(:disabled)').evaluateAll((els) => els.map((e) => e.checked));
  check('matriz: marcar todos do grupo', states.length > 0 && states.every((v) => v === states[0]));
  await root.locator('[data-action="open"]').click();
  const summary = await root.locator('[data-ref="summary"] li').allTextContents();
  check('matriz: modal com o resumo +/-', (await modalOpen(page)) && summary.length >= 1 && summary.every((r) => /^[+-]/.test(r)), JSON.stringify(summary));
  check('matriz: salvar habilitado com alteracao', !(await root.locator('[data-ref="save"]').isDisabled()));
  check('matriz: foco no Cancelar', await focused(root.locator('[data-ref="cancel"]')));
  await page.keyboard.press('Escape');
  check('matriz: Esc fecha e devolve o foco', !(await modalOpen(page)) && await focused(root.locator('[data-ref="trigger"]')));
  await root.locator('[data-action="open"]').click();
  await Promise.all([page.waitForNavigation(), root.locator('[data-ref="save"]').click()]);
  check('matriz: salvar grava', (await page.locator('.sss-alert').allTextContents()).join(' ').length > 0, page.url());
  await page.goto(BASE + '/admin_profiles/matrix/2');
  await page.locator('[data-component="permissionMatrix"] [data-action="open"]').click();
  check('matriz: sem alteracao, salvar desabilitado', await page.locator('[data-component="permissionMatrix"] [data-ref="save"]').isDisabled() &&
    await page.locator('[data-component="permissionMatrix"] [data-ref="noChanges"]').isVisible());
  await page.screenshot({ path: SHOTS + '/matriz.png' });
}

async function homologation(page) {
  await page.goto(BASE + '/admin_scripts/homologation/1');
  const root = page.locator('[data-component="scriptHomologation"]');
  const boxes = root.locator('input[name="environments"]:not(:disabled)');
  let target = null;
  for (let i = 0; i < await boxes.count(); i++) {
    const b = boxes.nth(i);
    if ((await b.isChecked()) && parseInt(await b.getAttribute('data-schedules'), 10) > 0) { target = b; break; }
  }
  if (!target) { target = boxes.first(); }
  const name = await target.getAttribute('data-name');
  const checkedBefore = await target.isChecked();
  await target.setChecked(!checkedBefore);
  await root.locator('[data-action="open"]').click();
  const rows = await root.locator('[data-ref="summary"] li').allTextContents();
  check('homologacao: resumo com o ambiente', JSON.stringify(rows) === JSON.stringify([(checkedBefore ? '-' : '+') + name]), JSON.stringify(rows));
  const sched = parseInt(await target.getAttribute('data-schedules'), 10) || 0;
  if (checkedBefore && sched > 0) {
    check('homologacao: aviso de agendamentos afetados', (await root.locator('[data-ref="affected"]').isVisible()) &&
      (await root.locator('[data-ref="affectedText"]').textContent()).startsWith(sched + ' agendamento(s)'));
  } else {
    check('homologacao: sem aviso quando nada e afetado', !(await root.locator('[data-ref="affected"]').isVisible()));
  }
  await root.locator('.btn-close').click();
  await target.setChecked(checkedBefore);
  await root.locator('[data-action="open"]').click();
  check('homologacao: desfeito = sem alteracao', (await root.locator('[data-ref="noChanges"]').isVisible()) &&
    (await root.locator('[data-ref="save"]').isDisabled()));
  await page.keyboard.press('Escape');
}

async function scriptLinks(page) {
  await page.goto(BASE + '/admin_scripts/parameters/1');
  const root = page.locator('[data-component="scriptLinks"]');
  const rows = root.locator('[data-ref="rows"] > li');
  const hidden = root.locator('[data-ref="linksJson"]');
  const links = () => hidden.inputValue().then(JSON.parse);
  const initial = await links();
  check('vinculos: linhas iniciais iguais ao JSON', (await rows.count()) === initial.length && initial.length > 0, String(initial.length));
  const codes = () => rows.locator('[data-part="code"]').allTextContents();
  const c0 = await codes();
  if (c0.length >= 2) {
    await rows.nth(0).locator('[data-part="down"]').click();
    const c1 = await codes();
    check('vinculos: descer troca a ordem', c1[0] === c0[1] && c1[1] === c0[0]);
    check('vinculos: foco segue o botao Descer da linha movida', await focused(rows.nth(1).locator('[data-part="down"]')));
    check('vinculos: JSON na nova ordem', (await links())[0].parameter_id === initial[1].parameter_id);
    await rows.nth(1).locator('[data-part="up"]').click();
    check('vinculos: subir desfaz', JSON.stringify(await codes()) === JSON.stringify(c0));
  }
  await rows.nth(0).locator('[data-part="required"]').setChecked(!initial[0].required);
  check('vinculos: obrigatorio no JSON', (await links())[0].required === !initial[0].required);
  const sub = rows.nth(0).locator('[data-part="sub"]');
  if (await sub.getAttribute('type') === 'text') {
    await sub.fill('valor<b>x</b>');
    check('vinculos: digitar mantem o foco e grava no JSON', (await focused(sub)) && (await links())[0].default_value_override === 'valor<b>x</b>');
  }
  const search = root.locator('[data-ref="search"]');
  const results = root.locator('[data-ref="results"] [data-part="add"]');
  const nResults = await results.count();
  check('vinculos: busca lista parametros nao vinculados', nResults > 0 && nResults <= 15, String(nResults));
  const addCode = await results.first().locator('[data-part="code"]').textContent();
  await search.fill(addCode);
  await results.first().click();
  check('vinculos: incluir acrescenta no fim', (await codes()).slice(-1)[0] === addCode);
  check('vinculos: incluido sai da busca', !(await root.locator('[data-ref="results"] [data-part="code"]').allTextContents()).includes(addCode));
  check('vinculos: foco volta para a busca', await focused(search));
  await search.fill('zzzz-nada');
  check('vinculos: busca vazia avisa', await root.locator('[data-ref="noResults"]').isVisible());
  await search.fill('');
  const before = await rows.count();
  await rows.nth(before - 1).locator('[data-part="remove"]').click();
  check('vinculos: remover a ultima', (await rows.count()) === before - 1);
  check('vinculos: foco no Remover anterior', await focused(rows.nth(before - 2).locator('[data-part="remove"]')));
  check('vinculos: removido volta para a busca', (await root.locator('[data-ref="results"] [data-part="code"]').allTextContents()).includes(addCode));
  await root.locator('[data-action="preview"]').click();
  await page.waitForFunction(() => !document.querySelector('[data-ref="previewButton"]').disabled);
  const text = root.locator('[data-ref="previewText"]');
  const errs = root.locator('[data-ref="previewErrors"]');
  check('vinculos: previa mostra o comando ou os erros', (await text.isVisible()) || (await errs.isVisible()));
  check('vinculos: HTML digitado nao vira elemento', (await root.locator('b').count()) === 0);
  await page.screenshot({ path: SHOTS + '/vinculos.png', fullPage: true });
}

async function scheduleRule(page) {
  await page.goto(BASE + '/schedules/form?script_id=1&environment=PRODUCAO');
  const root = page.locator('[data-component="scheduleRule"]');
  const type = root.locator('[data-ref="type"]');
  const visible = (sel) => root.locator(sel).isVisible();
  const expect = {
    ONCE: { '#field-end_date': false, '#field-run_time': false, '#field-month_day': false, 'fieldset[data-types="WEEKLY"]': false, '#field-cron_expression': false },
    DAILY: { '#field-end_date': true, '#field-run_time': true, '#field-month_day': false, 'fieldset[data-types="WEEKLY"]': false, '#field-cron_expression': false },
    WEEKLY: { '#field-end_date': true, '#field-run_time': true, '#field-month_day': false, 'fieldset[data-types="WEEKLY"]': true, '#field-cron_expression': false },
    MONTHLY: { '#field-end_date': true, '#field-run_time': true, '#field-month_day': true, 'fieldset[data-types="WEEKLY"]': false, '#field-cron_expression': false },
    CRON: { '#field-end_date': true, '#field-run_time': false, '#field-month_day': false, 'fieldset[data-types="WEEKLY"]': false, '#field-cron_expression': true }
  };
  for (const t of Object.keys(expect)) {
    await type.selectOption(t);
    let ok = true;
    const got = {};
    for (const sel of Object.keys(expect[t])) {
      got[sel] = await visible(sel);
      if (got[sel] !== expect[t][sel]) { ok = false; }
    }
    check('regra: campos de ' + t, ok, JSON.stringify(got));
  }
  await type.selectOption('DAILY');
  await root.locator('#field-end_date').fill('2027-01-01T00:00');
  await type.selectOption('ONCE');
  check('regra: UNICA limpa o fim', (await root.locator('#field-end_date').inputValue()) === '');
  check('regra: rotulo do inicio muda', await root.locator('span[data-types="ONCE"]').first().isVisible());
  await type.selectOption('DAILY');
  await root.locator('#field-run_time').fill('08:30');
  await page.waitForFunction(() => document.querySelectorAll('[data-ref="dates"] li').length > 0, null, { timeout: 5000 });
  const dates = await root.locator('[data-ref="dates"] li').allTextContents();
  check('regra: previa com datas', dates.length > 0 && (await root.locator('[data-ref="description"]').isVisible()), JSON.stringify(dates.slice(0, 2)));
  check('regra: calculando escondido ao fim', !(await root.locator('[data-ref="loading"]').isVisible()));
  await type.selectOption('CRON');
  await root.locator('#field-cron_expression').fill('isso nao e cron');
  await page.waitForFunction(() => document.querySelectorAll('[data-ref="errors"] li').length > 0, null, { timeout: 5000 });
  check('regra: previa com erro', (await root.locator('[data-ref="errors"]').isVisible()) && !(await root.locator('[data-ref="dates"]').isVisible()));
  await page.screenshot({ path: SHOTS + '/regra.png', fullPage: true });
}

async function ticketTrigger(page) {
  await page.goto(BASE + '/tickets/new?script_id=1&environment=PRODUCAO');
  const form = page.locator('[data-component="ticketTrigger"]');
  await form.locator('[data-action="open"]').click();
  check('disparo: modal abre com foco no Cancelar', (await modalOpen(page)) && await focused(form.locator('[data-ref="cancel"]')));
  await page.waitForFunction(() => {
    const s = document.querySelector('[data-ref="summary"]');
    const e = document.querySelector('[data-ref="errors"]');
    return !s.hidden || !e.hidden;
  }, null, { timeout: 5000 });
  const hasSummary = await form.locator('[data-ref="summary"]').isVisible();
  if (hasSummary) {
    check('disparo: resumo com script e ambiente', ((await form.locator('[data-ref="script"]').textContent()).length > 0) &&
      (await form.locator('[data-ref="environment"]').textContent()) === 'PRODUCAO');
    check('disparo: comando montado', (await form.locator('[data-ref="command"]').textContent()).length > 0);
  } else {
    check('disparo: erros do resumo listados', (await form.locator('[data-ref="errors"] li').count()) > 0,
      (await form.locator('[data-ref="errors"]').textContent()));
  }
  check('disparo: carregando escondido ao fim', !(await form.locator('[data-ref="loading"]').isVisible()));
  await page.screenshot({ path: SHOTS + '/disparo.png' });
  await page.keyboard.press('Escape');
  check('disparo: Esc fecha e devolve o foco', !(await modalOpen(page)) && await focused(form.locator('[data-ref="trigger"]')));
  await page.route('**/tickets/preview**', (route) => route.abort());
  await form.locator('[data-action="open"]').click();
  await page.waitForFunction(() => !document.querySelector('[data-ref="errors"]').hidden, null, { timeout: 5000 });
  check('disparo: falha de rede mostra erro', (await form.locator('[data-ref="errors"]').textContent()).includes('Não foi possível montar o resumo'));
  check('disparo: resumo anterior escondido', !(await form.locator('[data-ref="summary"]').isVisible()));
  await page.unroute('**/tickets/preview**');
  page.problems = page.problems.filter((p) => !p.includes('ERR_FAILED') && !p.includes('Failed to load resource'));
  await form.locator('[data-action="close"]').first().click();
  if (hasSummary) {
    await form.locator('[data-action="open"]').click();
    await page.waitForFunction(() => !document.querySelector('[data-ref="summary"]').hidden, null, { timeout: 5000 });
    await Promise.all([page.waitForNavigation(), form.locator('button[type="submit"]').click()]);
    check('disparo: criar ticket envia o formulario', /tickets\/detail\/\d+/.test(page.url()), page.url());
  }
}

async function layouts(browser) {
  for (const scheme of ['light', 'dark']) {
    for (const width of [390, 1280]) {
      const page = await login(browser, { colorScheme: scheme, viewport: { width, height: 844 } });
      for (const path of ['/admin_profiles/matrix/2', '/admin_scripts/homologation/1', '/admin_scripts/parameters/1',
        '/schedules/form?script_id=1&environment=PRODUCAO', '/tickets/new?script_id=1&environment=PRODUCAO']) {
        await page.goto(BASE + path);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
        check('layout ' + scheme + ' ' + width + ' ' + path + ': sem rolagem horizontal', !overflow);
      }
      await page.locator('[data-component="ticketTrigger"] [data-action="open"]').click();
      await page.waitForTimeout(600);
      await page.screenshot({ path: SHOTS + '/disparo-' + scheme + '-' + width + '.png' });
      check('layout ' + scheme + ' ' + width + ': console limpo', page.problems.length === 0, page.problems.join(' | '));
      await page.context().close();
    }
  }
}

(async () => {
  const browser = await h.chromium.launch();
  const page = await login(browser);
  await h.run([matrix, homologation, scriptLinks, scheduleRule, ticketTrigger].map((f) => {
    const step = () => f(page);
    Object.defineProperty(step, 'name', { value: f.name });
    return step;
  }));
  await layouts(browser);
  check('console sem erros nem violacao de CSP', page.problems.length === 0, page.problems.join(' | '));
  await browser.close();
  process.exit(h.report());
})();
