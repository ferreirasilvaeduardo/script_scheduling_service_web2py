// Harness de navegador do CR-021 (somente DEV): base comum dos roteiros.
//
// Variaveis de ambiente:
//   SSS_HARNESS_URL        aplicacao com o backend FAKE (padrao http://127.0.0.1:8791/script_scheduling_service)
//   SSS_DEV_SEED_PASSWORD  senha dos usuarios do seed FAKE (obrigatoria; a mesma do servidor FAKE)
//   PW_MODULE              modulo do Playwright (padrao ~/tools/pw/node_modules/playwright)
//   SSS_HARNESS_OUT        pasta das capturas (padrao <tmp>/sss_web_harness)
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');

const BASE = process.env.SSS_HARNESS_URL || 'http://127.0.0.1:8791/script_scheduling_service';
const PASSWORD = process.env.SSS_DEV_SEED_PASSWORD;
const OUT = process.env.SSS_HARNESS_OUT || path.join(os.tmpdir(), 'sss_web_harness');
const PLAYWRIGHT = process.env.PW_MODULE || path.join(os.homedir(), 'tools/pw/node_modules/playwright');

if (!PASSWORD) {
  console.error('Defina SSS_DEV_SEED_PASSWORD (a senha do seed FAKE do servidor de teste).');
  process.exit(2);
}

const { chromium } = require(PLAYWRIGHT);
const results = [];

function check(name, ok, detail) {
  results.push({ name, ok: !!ok, detail: detail || '' });
}

function shots(suite) {
  const dir = path.join(OUT, suite);
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

// Pagina com o erro de console, o erro de script e a violacao de CSP guardados em page.problems.
async function newPage(browser, options) {
  const context = await browser.newContext(options || {});
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: new URL(BASE).origin });
  const page = await context.newPage();
  page.problems = [];
  page.on('console', (m) => { if (m.type() === 'error') page.problems.push('console: ' + m.text()); });
  page.on('pageerror', (e) => page.problems.push('pageerror: ' + e.message));
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (e) => {
      console.error('CSP: ' + e.violatedDirective + ' ' + e.blockedURI);
    });
  });
  return page;
}

async function login(browser, options, user) {
  const page = await newPage(browser, options);
  await page.goto(BASE + '/default/login');
  await page.fill('input[name="login"]', user || 'admin');
  await page.fill('input[name="password"]', PASSWORD);
  await Promise.all([page.waitForNavigation(), page.click('button[type="submit"]')]);
  return page;
}

const focused = (locator) => locator.evaluate((el) => document.activeElement === el);
const modalOpen = (page) => page.evaluate(() => document.body.classList.contains('modal-open'));

// Roda os passos na ordem; excecao num passo vira falha dele, sem parar os outros.
async function run(steps) {
  for (const step of steps) {
    try {
      await step();
    } catch (e) {
      check(step.name + ': excecao', false, e.message.split('\n')[0]);
    }
  }
}

function report() {
  let failed = 0;
  for (const r of results) {
    if (!r.ok) {
      failed++;
    }
    console.log((r.ok ? 'OK   ' : 'FALHA') + ' ' + r.name + (r.ok || !r.detail ? '' : ' -> ' + r.detail));
  }
  console.log('\n' + (results.length - failed) + '/' + results.length + ' OK');
  return failed ? 1 : 0;
}

module.exports = { BASE, chromium, check, shots, newPage, login, focused, modalOpen, run, report };
