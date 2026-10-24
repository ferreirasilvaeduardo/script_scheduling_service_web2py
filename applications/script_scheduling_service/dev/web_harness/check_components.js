// Componentes compartilhados (CR-021a) nas telas reais: toast, modal generico, copiar, filtros e busca.
'use strict';

const h = require('./common');

const SHOTS = h.shots('components');
const { BASE, check, focused, modalOpen } = h;

async function toasts(browser) {
  const page = await h.login(browser);
  await page.goto(BASE + '/dev/shell');
  const buttons = page.locator('[data-component="toastDemo"] [data-action="trigger"]');
  check('toastDemo: 4 botoes', (await buttons.count()) === 4);
  for (let i = 0; i < 4; i++) {
    await buttons.nth(i).click();
  }
  const items = page.locator('.sss-toasts .sss-toast');
  const classes = await items.evaluateAll((els) => els.map((e) => e.className));
  check('toast: tipos success/error/warning/info', JSON.stringify(classes) === JSON.stringify(
    ['sss-toast sss-toast-success', 'sss-toast sss-toast-error', 'sss-toast sss-toast-warning',
      'sss-toast sss-toast-info']), JSON.stringify(classes));
  await page.evaluate(() => window.SSS.toast('bogus', '<b id="injetado">x</b>'));
  check('toast: tipo desconhecido vira info', (await items.nth(4).getAttribute('class')) === 'sss-toast sss-toast-info');
  check('toast: HTML da mensagem nao vira elemento', (await page.locator('#injetado').count()) === 0);
  await items.nth(1).locator('[data-action="close"]').click();
  check('toast: fechar remove so a clicada', (await items.count()) === 4);
  await page.screenshot({ path: SHOTS + '/toasts.png' });
  await page.waitForTimeout(6300);
  check('toast: somem sozinhas em 6 s', (await items.count()) === 0);
  check('toasts: console limpo', page.problems.length === 0, page.problems.join(' | '));
  await page.context().close();
}

async function confirmation(browser) {
  const page = await h.login(browser);
  await page.goto(BASE + '/dev/components');
  const root = page.locator('[data-component="confirmation"]').first();
  const modal = root.locator('[data-ref="modal"]');
  const trigger = root.locator('[data-ref="trigger"]');
  check('confirmation: fechado no inicio', !(await modal.isVisible()));
  await trigger.click();
  check('confirmation: abre com foco no Cancelar', (await modalOpen(page)) && await focused(root.locator('[data-ref="cancel"]')));
  check('confirmation: so o modal clicado abre',
    (await page.locator('[data-component="confirmation"] [data-ref="modal"].show').count()) === 1);
  await page.keyboard.press('Escape');
  check('confirmation: Esc fecha e devolve o foco', !(await modalOpen(page)) && await focused(trigger));
  await trigger.click();
  await modal.click({ position: { x: 5, y: 5 } });
  check('confirmation: clique no fundo fecha', !(await modalOpen(page)));
  await trigger.click();
  await modal.locator('.modal-body').click();
  check('confirmation: clique dentro nao fecha', await modalOpen(page));
  await root.locator('.btn-close').click();
  check('confirmation: X fecha', !(await modalOpen(page)));
  await trigger.click();
  await Promise.all([page.waitForNavigation(), root.locator('button[type="submit"]').click()]);
  check('confirmation: POST real aceito pelo servidor (CSRF)',
    (await page.locator('.sss-alert').allTextContents()).join(' ').includes('Confirmação recebida'));
  check('confirmation: console limpo', page.problems.length === 0, page.problems.join(' | '));
  await page.context().close();
}

async function copyAndFilters(browser) {
  const page = await h.login(browser);
  await page.goto(BASE + '/dev/components');
  const copy = page.locator('[data-component="copy"]');
  const label = copy.locator('[data-ref="label"]');
  await copy.click();
  await page.waitForTimeout(150);
  check('copy: rotulo Copiado!', (await label.textContent()) === 'Copiado!');
  const copied = await page.evaluate(() => navigator.clipboard.readText()).catch(() => null);
  check('copy: area de transferencia com o texto', copied === await copy.getAttribute('data-text'), String(copied));
  await page.waitForTimeout(2100);
  check('copy: rotulo volta a Copiar', (await label.textContent()) === 'Copiar');

  const form = page.locator('[data-component="filters"]');
  await form.locator('input[name="q"]').fill('carga');
  await form.locator('select[name="status"]').selectOption('FAILED');
  await Promise.all([page.waitForNavigation(), form.locator('[data-action="clear"]').click()]);
  const url = new URL(page.url());
  check('filters: Limpar submete com os campos vazios', url.pathname.endsWith('/dev/components') &&
    url.searchParams.get('q') === '' && url.searchParams.get('status') === '' && url.searchParams.has('size'),
    page.url());
  check('copy e filters: console limpo', page.problems.length === 0, page.problems.join(' | '));
  await page.context().close();
}

async function search(browser) {
  const page = await h.login(browser);
  await page.goto(BASE + '/tickets/catalog');
  const root = page.locator('[data-component="scriptSearch"]');
  const term = root.locator('[data-ref="searchTerm"]');
  const empty = root.locator('[data-ref="noResult"]');
  const visible = () => root.locator('[data-search]:visible').count();
  const total = await visible();
  check('scriptSearch: cartoes no inicio e mensagem escondida', total > 1 && !(await empty.isVisible()), String(total));
  const name = (await root.locator('.sss-card-routine-title').first().textContent()).trim();
  await term.fill(name);
  const found = await visible();
  check('scriptSearch: filtra pelo nome', found >= 1 && found < total, `${found} de ${total}`);
  await term.fill('  ' + name.toUpperCase() + ' ');
  check('scriptSearch: ignora caixa e espacos', (await visible()) === found);
  await term.fill('zzz-nada-assim');
  check('scriptSearch: sem resultado mostra a mensagem', (await empty.isVisible()) && (await visible()) === 0);
  await term.fill('');
  check('scriptSearch: limpar volta tudo', (await visible()) === total && !(await empty.isVisible()));
  check('scriptSearch: console limpo', page.problems.length === 0, page.problems.join(' | '));
  await page.context().close();
}

async function layouts(browser) {
  for (const scheme of ['light', 'dark']) {
    for (const width of [390, 1280]) {
      const page = await h.login(browser, { colorScheme: scheme, viewport: { width, height: 844 } });
      await page.goto(BASE + '/dev/components');
      await page.locator('[data-component="confirmation"] [data-ref="trigger"]').first().click();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      check(`layout ${scheme} ${width}px: sem rolagem horizontal`, !overflow);
      check(`layout ${scheme} ${width}px: tema aplicado`,
        (await page.evaluate(() => document.documentElement.getAttribute('data-bs-theme'))) === scheme);
      await page.screenshot({ path: `${SHOTS}/modal-${scheme}-${width}.png` });
      check(`layout ${scheme} ${width}px: console limpo`, page.problems.length === 0, page.problems.join(' | '));
      await page.context().close();
    }
  }
}

(async () => {
  const browser = await h.chromium.launch();
  await h.run([toasts, confirmation, copyAndFilters, search, layouts].map((f) => {
    const step = () => f(browser);
    Object.defineProperty(step, 'name', { value: f.name });
    return step;
  }));
  await browser.close();
  process.exit(h.report());
})();
