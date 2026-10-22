/**
 * capture_evidence.js
 * Evidencias reais da homologacao (2026-10-22): executa os casos de teste do manual de UI Freeze adaptados ao
 * banco DEV (Oracle) e ao agente real, captura as figuras e confere na propria pagina o resultado esperado.
 *
 * Uso (servidor web do DEV no ar, agente real no ar):
 *   node capture_evidence.js            -> todos os CTs, na ordem
 *   node capture_evidence.js CT-01 CT-05 -> so os CTs pedidos (o estado fica em <saida>/state.json)
 *
 * Senhas: nunca no codigo nem no log.
 *   - senha inicial dos usuarios do seed: lida do docs/DEPLOYMENT.md (secao 5.3, documentada);
 *   - senha nova do admin (troca valida do CT-01): arquivo SSS_ADMIN_NEW_PASSWORD_FILE (padrao ~/.sss_homolog_pw, 0600).
 * Saida: SSS_EVIDENCE_DIR (padrao dev/homologation/evidence_20261022): fig_NN.png, results.json, state.json.
 */
const fs = require('fs');
const os = require('os');
const path = require('path');

function loadPuppeteer() {
    const candidates = [process.env.PUPPETEER_MODULE, 'puppeteer',
        path.join(os.homedir(), '.npm/_npx/668c188756b835f3/node_modules/puppeteer')].filter(Boolean);
    for (const c of candidates) {
        try { return require(c); } catch (e) { /* tenta o proximo */ }
    }
    console.error('Puppeteer nao encontrado (defina PUPPETEER_MODULE).');
    process.exit(2);
}
const puppeteer = loadPuppeteer();

const APP = path.resolve(__dirname, '..', '..', '..');
const BASE_URL = process.env.SSS_BASE_URL || 'http://127.0.0.1:18000/script_scheduling_service';
const OUT_DIR = process.env.SSS_EVIDENCE_DIR || path.join(APP, 'dev', 'homologation', 'evidence_20261022');
const CHROME = process.env.SSS_CHROME ||
    path.join(os.homedir(), '.cache/puppeteer/chrome/linux-131.0.6778.204/chrome-linux64/chrome');
const INPUT = path.join(APP, 'input');
const STAMP = 'HOMOLOG_20261022';

const deployDoc = fs.readFileSync(path.join(APP, 'docs', 'DEPLOYMENT.md'), 'utf8');
const SEED_PASS = (deployDoc.match(/senha inicial `([^`]+)`/) || [])[1];
const NEW_PASS_FILE = process.env.SSS_ADMIN_NEW_PASSWORD_FILE || path.join(os.homedir(), '.sss_homolog_pw');
const NEW_PASS = fs.existsSync(NEW_PASS_FILE) ? fs.readFileSync(NEW_PASS_FILE, 'utf8').replace(/\s+$/, '') : null;
if (!SEED_PASS || !NEW_PASS) {
    console.error('Senha inicial (DEPLOYMENT.md) ou arquivo da senha nova do admin ausente.');
    process.exit(2);
}

fs.mkdirSync(OUT_DIR, { recursive: true });
const STATE_FILE = path.join(OUT_DIR, 'state.json');
const RESULTS_FILE = path.join(OUT_DIR, 'results.json');
const state = fs.existsSync(STATE_FILE) ? JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')) : { adminNew: false, tickets: {} };
const results = fs.existsSync(RESULTS_FILE) ? JSON.parse(fs.readFileSync(RESULTS_FILE, 'utf8')) : {};
function saveState() { fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2)); }
function saveResults() { fs.writeFileSync(RESULTS_FILE, JSON.stringify(results, null, 2)); }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let browser;
let page;
let ct = null; // CT corrente

function passOf(user) {
    return user === 'admin' && state.adminNew ? NEW_PASS : SEED_PASS;
}

function begin(id, title) {
    ct = id;
    results[id] = { title, checks: [], figures: [], notes: [], started_at: new Date().toISOString() };
    console.log(`\n=== ${id} — ${title} ===`);
}

function check(desc, ok, detail) {
    const item = { desc, ok: !!ok };
    if (detail !== undefined && detail !== null && detail !== '') item.detail = String(detail).slice(0, 400);
    results[ct].checks.push(item);
    console.log(`${ok ? '  [OK]    ' : '  [NAO OK]'} ${desc}${item.detail ? ' — ' + item.detail : ''}`);
    return !!ok;
}

function note(text) {
    results[ct].notes.push(text);
    console.log('  [nota] ' + text);
}

async function text() {
    return page.evaluate(() => document.body ? document.body.innerText : '');
}

async function has(...needles) {
    const t = await text();
    return needles.every((n) => t.includes(n));
}

async function expectText(desc, ...needles) {
    const t = await text();
    const missing = needles.filter((n) => !t.includes(n));
    return check(desc, missing.length === 0, missing.length ? 'faltou: ' + missing.join(' | ') : '');
}

async function expectNoText(desc, ...needles) {
    const t = await text();
    const found = needles.filter((n) => t.includes(n));
    return check(desc, found.length === 0, found.length ? 'apareceu: ' + found.join(' | ') : '');
}

async function snap(caption, opts = {}) {
    const n = results[ct].figures.length + 1;
    if (opts.selector) {
        await page.evaluate((sel) => {
            const el = document.querySelector(sel);
            if (el) el.scrollIntoView({ behavior: 'instant', block: 'center' });
        }, opts.selector);
        await sleep(300);
    }
    const file = `${ct}_${n}.png`;
    await page.screenshot({ path: path.join(OUT_DIR, file), fullPage: !!opts.full });
    results[ct].figures.push({ n, file, caption, url: page.url().replace(BASE_URL, ''), at: new Date().toISOString() });
    saveResults();
    console.log(`  [fig] ${caption} -> ${file}`);
}

async function go(p) {
    // O detalhe do ticket se recarrega sozinho quando a situacao muda; uma navegacao interrompida e repetida.
    for (let i = 0; i < 3; i++) {
        try {
            const resp = await page.goto(BASE_URL + p, { waitUntil: 'networkidle0' });
            return resp ? resp.status() : 0;
        } catch (err) {
            if (!String(err).includes('ERR_ABORTED') || i === 2) throw err;
            await sleep(1500);
        }
    }
    return 0;
}

async function clearCookies() {
    const client = await page.target().createCDPSession();
    await client.send('Network.clearBrowserCookies');
}

async function login(user, pass) {
    await clearCookies();
    await go('/default/login');
    await page.$eval('#field-login', (e) => { e.value = ''; });
    await page.type('#field-login', user);
    await page.type('#field-password', pass === undefined ? passOf(user) : pass);
    await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), page.click('form button[type="submit"]')]);
    return !page.url().includes('/default/login');
}

async function setViewport(kind) {
    await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: kind === 'dark' ? 'dark' : 'light' }]);
    if (kind === 'mobile') {
        await page.setViewport({ width: 360, height: 780, isMobile: true, hasTouch: true });
    } else {
        await page.setViewport({ width: 1280, height: 900 });
    }
}

// Clica no primeiro elemento visivel (seletor) cujo texto contem `label`.
async function clickText(selector, label, opts = {}) {
    const handles = await page.$$(selector);
    for (const h of handles) {
        const ok = await h.evaluate((e, l) => {
            const r = e.getBoundingClientRect();
            return e.innerText && e.innerText.includes(l) && r.width > 0 && r.height > 0;
        }, label);
        if (ok) {
            if (opts.navigate) {
                await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), h.click()]);
            } else {
                await h.click();
                await sleep(opts.wait || 600);
            }
            return true;
        }
    }
    return false;
}

// Botao de submit visivel dentro do modal aberto.
async function confirmModal() {
    const btns = await page.$$('.modal button[type="submit"]');
    for (const b of btns) {
        const visible = await b.evaluate((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
        if (visible) {
            await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), b.click()]);
            return true;
        }
    }
    return false;
}

async function fill(selector, value) {
    await page.$eval(selector, (e, v) => {
        if (e.tagName === 'SELECT') {
            e.value = v;
        } else {
            e.value = v;
        }
        e.dispatchEvent(new Event('input', { bubbles: true }));
        e.dispatchEvent(new Event('change', { bubbles: true }));
    }, value);
}

// Envia o formulario cujo action contem `actionPart`, pelo botao de submit dele (como o usuario).
async function submit(actionPart) {
    const form = await page.$(`form[action*="${actionPart}"]`);
    if (!form) return false;
    const btn = await form.$('button[type="submit"]:not([formaction])');
    await Promise.all([
        page.waitForNavigation({ waitUntil: 'networkidle0' }),
        btn ? btn.click() : form.evaluate((f) => f.requestSubmit()),
    ]);
    return true;
}

function ticketFromUrl() {
    const m = page.url().match(/\/tickets\/detail\/(\d+)/);
    return m ? parseInt(m[1], 10) : null;
}

// Disparo pelo assistente (etapas 1 a 3) e confirmacao no modal; devolve o id do ticket criado.
async function createTicket(scriptName, env, answers, opts = {}) {
    await go('/tickets/new');
    const okScript = await clickText('a.sss-choice', scriptName, { navigate: true });
    if (!okScript) return null;
    const okEnv = await clickText('a.sss-choice', env, { navigate: true });
    if (!okEnv) return null;
    for (const [code, value] of Object.entries(answers)) {
        await fill(`[name="p_${code}"]`, value);
    }
    if (opts.priority) await fill('#field-priority', String(opts.priority));
    if (opts.scheduledAt) await fill('#field-scheduled_at', opts.scheduledAt);
    await clickText('button[data-summary-trigger]', 'Criar ticket', { wait: 1500 });
    if (opts.beforeConfirm) await opts.beforeConfirm();
    await confirmModal();
    return ticketFromUrl();
}

async function ticketStatus(id) {
    await go(`/tickets/detail/${id}`);
    return text();
}

async function waitStatus(id, labels, timeoutS) {
    const end = Date.now() + timeoutS * 1000;
    let t = '';
    while (Date.now() < end) {
        t = await ticketStatus(id);
        if (labels.some((l) => t.includes(l))) return t;
        await sleep(3000);
    }
    return t;
}

// ---------------------------------------------------------------------------------------------
// Massa: tickets reais criados pelas telas e executados pelo agente srv-linux-local-01
// ---------------------------------------------------------------------------------------------
const FILE_CLIENTES = path.join(INPUT, 'gfpreprod', 'contar_linhas_arquivo', 'clientes_20261022.txt');
const FILE_NOTAS = path.join(INPUT, 'clone6', 'contar_linhas_arquivo', 'notas_20261022.txt');
const FILE_EXTRATO = path.join(INPUT, 'clone2', 'gerar_hash_arquivo', 'extrato_20261022.csv');
const DIR_LOTE = path.join(INPUT, 'gfpreprod', 'zipar_arquivos', 'lote_20261022');
const FILE_INEXISTENTE = path.join(INPUT, 'gfpreprod', 'contar_linhas_arquivo', 'arquivo_que_nao_existe.txt');

const CTS = {};

CTS['CT-01'] = async () => {
    begin('CT-01', 'Login, sessão e troca de senha');
    await clearCookies();
    await go('/');
    check('Endereço raiz redireciona para Entrar', page.url().includes('/default/login'), page.url().replace(BASE_URL, ''));
    await expectText('Faixa amarela do ambiente DEV no topo', 'AMBIENTE DEV');
    await snap('Tela de login');
    const okFalha = !(await login('op.hml', 'senha-incorreta-homolog'));
    check('Senha incorreta não entra', okFalha);
    await expectText('Mensagem genérica, sem dizer se o erro foi no login ou na senha',
        'Usuário ou senha incorretos.', 'Confira o que digitou e tente de novo.');
    await snap('Mensagem após senha incorreta');
    const okEspacos = await login('  op.hml  ', SEED_PASS);
    check('Login com espaços em volta entra (o login é limpo antes da validação)', okEspacos, page.url().replace(BASE_URL, ''));

    await login('admin');
    await go('/default/my_password');
    await fill('#field-current_password', passOf('admin'));
    await fill('#field-new_password', NEW_PASS);
    await fill('#field-confirmation', NEW_PASS + 'x');
    await submit('/default/my_password');
    await expectText('Confirmação divergente: campo destacado com mensagem em português',
        'A confirmação não confere com a nova senha.');
    check('Confirmação divergente marca o campo como inválido',
        await page.$('#field-confirmation.is-invalid') !== null);
    await snap('Tela Minha senha com a confirmação divergente');
    await fill('#field-current_password', passOf('admin'));
    await fill('#field-new_password', NEW_PASS);
    await fill('#field-confirmation', NEW_PASS);
    await submit('/default/my_password');
    const trocou = await has('Senha alterada com sucesso.');
    check('Troca válida: mensagem de sucesso e a sessão continua ativa',
        trocou && !page.url().includes('/default/login'), page.url().replace(BASE_URL, ''));
    if (trocou) { state.adminNew = true; saveState(); }
    note('A senha do admin passou a ser a senha escolhida pelo responsável pela homologação (os demais usuários continuam com a senha inicial).');
    const st405 = await page.evaluate(async (u) => (await fetch(u, { method: 'GET', credentials: 'same-origin' })).status,
        BASE_URL + '/default/logout');
    check('GET em /default/logout não faz logout (405)', st405 === 405, 'status ' + st405);
    await clickText('form[action*="/default/logout"] button', 'Sair', { navigate: true });
    await expectText('Sair volta ao login com "Você saiu do sistema."', 'Você saiu do sistema.');
    check('Depois de Sair a página é a de login', page.url().includes('/default/login'));
    const okNova = await login('admin');
    check('admin entra com a senha nova', okNova);
};

CTS['CT-02'] = async () => {
    begin('CT-02', 'Painel inicial por perfil');
    await login('admin');
    await go('/default/index');
    await expectText('admin: cartões de disparo, tickets 24 h, meus tickets, agendamentos e saúde dos agentes',
        'Disparar script', 'Tickets nas últimas 24 horas', 'Meus últimos tickets', 'Próximos agendamentos', 'Saúde dos agentes');
    await expectText('admin: menu com Administração', 'Administração');
    await snap('Painel inicial do admin', { full: true });
    await login('op.prod');
    await go('/default/index');
    await expectText('op.prod: disparo, tickets 24 h e meus tickets', 'Disparar script', 'Tickets nas últimas 24 horas', 'Meus últimos tickets');
    await expectNoText('op.prod: sem agendamentos, agentes e Administração', 'Próximos agendamentos', 'Saúde dos agentes', 'Administração');
    await snap('Painel inicial do op.prod');
    await login('op.hml');
    await go('/default/index');
    await expectText('op.hml: disparo, tickets 24 h e meus tickets', 'Disparar script', 'Tickets nas últimas 24 horas', 'Meus últimos tickets');
    await expectNoText('op.hml: sem Administração', 'Administração');
    await snap('Painel inicial do op.hml');
    await login('consulta');
    await go('/default/index');
    await expectText('consulta: tickets 24 h e meus tickets', 'Tickets nas últimas 24 horas', 'Meus últimos tickets');
    await expectNoText('consulta: sem Disparar script e sem Rotinas disponíveis', 'Disparar script', 'Rotinas disponíveis');
    await snap('Painel inicial do consulta');
};

CTS['CT-03'] = async () => {
    begin('CT-03', 'O que eu posso fazer');
    await login('op.hml');
    await go('/default/permissions');
    await expectText('Quadros do perfil e a frase de mais acesso',
        'Precisa de mais acesso? Fale com o administrador do sistema.');
    await expectText('op.hml: ambientes do perfil (CLONE6, CLONE7 e GFPREPROD)', 'CLONE6', 'CLONE7', 'GFPREPROD');
    await expectNoText('op.hml: CLONE1 e CLONE2 (fora do perfil) não aparecem', 'CLONE1', 'CLONE2');
    await snap('O que eu posso fazer (op.hml)', { full: true });
    const okRodar = await clickText('a', 'Rodar em GFPREPROD', { navigate: true });
    check('O botão Rodar em… abre o disparo já na etapa 3', okRodar && page.url().includes('environment=GFPREPROD'),
        page.url().replace(BASE_URL, ''));
    await login('consulta');
    await go('/default/permissions');
    await expectText('consulta: ainda não pode rodar scripts', 'Você ainda não pode rodar scripts.');
    await login('admin');
    await go('/default/permissions');
    await expectText('admin: frase de administrador', 'administrador');
};

CTS['CT-04'] = async () => {
    begin('CT-04', 'Rotinas disponíveis e histórico do script');
    await login('op.hml');
    await go('/tickets/catalog');
    await expectText('Cartões com perguntas, última execução e botões', 'Perguntas que faz', 'Última execução', 'Ver histórico');
    await page.type('#search-routine', 'hash');
    await sleep(500);
    const visiveis = await page.$$eval('li.sss-card-routine', (as) => as.filter((a) => a.offsetParent !== null).map((a) => a.innerText.split('\n')[0]));
    check('A busca filtra na hora', visiveis.length > 0 && visiveis.length < 14, visiveis.join(', '));
    await page.$eval('input[type="search"]', (e) => { e.value = 'xyz-nao-existe'; e.dispatchEvent(new Event('input', { bubbles: true })); });
    await sleep(500);
    await expectText('Sem resultado: "Nenhuma rotina corresponde à busca."', 'Nenhuma rotina corresponde à busca.');
    await page.$eval('input[type="search"]', (e) => { e.value = ''; e.dispatchEvent(new Event('input', { bubbles: true })); });
    await sleep(400);
    await snap('Rotinas disponíveis (op.hml)', { full: true });
    await login('admin');
    const sid = state.scripts && state.scripts.contar_linhas_arquivo;
    if (sid) {
        await go(`/tickets/history/${sid}`);
        await expectText('Histórico: resumo, gráfico de 30 dias e números', 'Pedidos por dia', 'Deram certo', 'Deram erro');
        await snap('Histórico do contar_linhas_arquivo', { full: true });
    } else {
        check('Histórico do script (id do script conhecido)', false, 'execute a preparação da massa antes');
    }
    await login('consulta');
    const st = await go('/tickets/catalog');
    await expectText('consulta: acesso negado (403)', 'Você não tem permissão para abrir esta página.', '403');
    check('Status HTTP 403', st === 403, 'status ' + st);
};

CTS['MASSA'] = async () => {
    begin('MASSA', 'Preparação da massa: tickets reais criados pelas telas e executados pelo agente');
    await login('admin');
    await go('/tickets/new');
    state.scripts = await page.$$eval('a.sss-choice', (as) => {
        const m = {};
        for (const a of as) {
            const id = (a.getAttribute('href').match(/script_id=(\d+)/) || [])[1];
            const name = a.innerText.trim().split('\n')[0].trim();
            if (id) m[name] = parseInt(id, 10);
        }
        return m;
    });
    saveState();
    check('Scripts do seed disponíveis no disparo do admin', Object.keys(state.scripts).length === 14,
        Object.keys(state.scripts).join(', '));
    const plano = [
        ['ok_hml', 'op.hml', 'contar_linhas_arquivo', 'GFPREPROD', { caminho_arquivo: FILE_CLIENTES }],
        ['erro_hml', 'op.hml', 'contar_linhas_arquivo', 'GFPREPROD', { caminho_arquivo: FILE_INEXISTENTE }],
        ['ok_clone6', 'op.hml', 'contar_linhas_arquivo', 'CLONE6', { caminho_arquivo: FILE_NOTAS }],
        ['ok_prod', 'op.prod', 'gerar_hash_arquivo', 'CLONE2', { arq_origem: FILE_EXTRATO }],
        ['ok_admin', 'admin', 'gerar_hash_arquivo', 'CLONE2', { arq_origem: FILE_EXTRATO }],
    ];
    for (const [key, user, script, env, answers] of plano) {
        await login(user);
        const id = await createTicket(script, env, answers);
        state.tickets[key] = id;
        saveState();
        check(`Ticket ${key} criado por ${user} (${script} em ${env})`, !!id, id ? '#' + id : page.url().replace(BASE_URL, ''));
    }
    await login('admin');
    for (const [key] of plano) {
        const id = state.tickets[key];
        if (!id) continue;
        const t = await waitStatus(id, ['Deu certo', 'Deu erro', 'Cancelado'], 120);
        const sit = ['Deu certo', 'Deu erro', 'Cancelado'].find((l) => t.includes(l)) || 'sem final';
        state.tickets[key + '_status'] = sit;
        check(`Ticket #${id} (${key}) executado pelo agente: ${sit}`, key.startsWith('erro') ? sit === 'Deu erro' : sit === 'Deu certo');
    }
    saveState();
};

function localIso(offsetMin) {
    const d = new Date(Date.now() + offsetMin * 60000);
    const p = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

// Ticket longo (compactacao de 3 GB de texto, nivel 9: cerca de 4 minutos) para as telas de "Rodando" e o cancelamento em execucao.
async function startLongTicket(key) {
    await login('admin');
    const destino = path.join(INPUT, 'gfpreprod', 'zipar_arquivos', 'saida', `lote_20261022_${key}.zip`);
    const id = await createTicket('zipar_arquivos', 'GFPREPROD',
        { arq_origem: DIR_LOTE, arq_destino: destino, nivel_compressao: '9' });
    state.tickets[key] = id;
    saveState();
    const t = await waitStatus(id, ['Rodando'], 90);
    check(`Ticket longo #${id} (zipar_arquivos, 3 GB de texto, nível 9) rodando no agente`, t.includes('Rodando'));
    return id;
}

CTS['CT-05'] = async () => {
    begin('CT-05', 'Disparo de script (criação de ticket)');
    await login('op.prod');
    await go('/tickets/new');
    const nomes = await page.$$eval('a.sss-choice', (as) => as.map((a) => a.innerText.trim().split('\n')[0].trim()));
    check('Etapa 1: só scripts ativos autorizados ao perfil e homologados (os 14 utilitários)', nomes.length === 14, nomes.join(', '));
    await snap('Etapa 1: escolha do script', { full: true });
    await clickText('a.sss-choice', 'gerar_hash_arquivo', { navigate: true });
    const envs = await page.$$eval('a.sss-choice', (as) => as.map((a) => a.innerText.trim().split('\n')[0].trim()));
    check('Etapa 2: ambientes ativos do perfil em que o script está homologado', envs.length === 5, envs.join(', '));
    await snap('Etapa 2: escolha do ambiente');
    await clickText('a.sss-choice', 'CLONE2', { navigate: true });
    await fill('[name="p_arq_origem"]', FILE_EXTRATO);
    const prios = await page.$$eval('#field-priority option', (os) => os.map((o) => o.value));
    check('A lista de prioridades do op.prod começa em 2 (a 1 é só de administradores)', prios[0] === '2' && !prios.includes('1'), prios.join(','));
    await clickText('.sss-preview button', 'Pré-visualizar', { wait: 1500 });
    await expectText('Prévia do comando com o interpretador e o caminho completo do script',
        '/opt/automacoes/scripts/utilitarios/gerar_hash_arquivo.py');
    await snap('Etapa 3: questionário e prévia do comando', { full: true });
    await clickText('button[data-summary-trigger]', 'Criar ticket', { wait: 1500 });
    await expectText('Confirmação com a frase-resumo e o comando que será executado',
        'Vamos rodar', 'gerar_hash_arquivo', 'CLONE2', 'Comando que será executado');
    await snap('Confirmação do disparo, com o resumo');
    note('O destaque "AMBIENTE DE PRODUÇÃO" (botão vermelho e selo) só aparece para o ambiente chamado PRODUCAO (ticket_service.PRODUCTION_ENVIRONMENT); nenhum ambiente do DEV tem esse nome, então ele não aparece nos dados reais.');
    await confirmModal();
    const id = ticketFromUrl();
    state.tickets.ct05 = id;
    saveState();
    await expectText('Mensagem "Ticket #N criado com sucesso."', `Ticket #${id} criado com sucesso.`);
    await expectText('Detalhe com o que aconteceu, o que fazer agora, as etapas e o arquivo do script',
        'O que aconteceu', 'O que fazer agora', 'Pedido criado', 'Na fila', '/opt/automacoes/scripts/utilitarios/gerar_hash_arquivo.py');
    await snap('Ticket criado (detalhe)', { full: true });
    const fim = await waitStatus(id, ['Deu certo', 'Deu erro'], 120);
    check(`Ticket #${id} executado pelo agente real até o fim`, fim.includes('Deu certo'));
    await go(`/tickets/new?script_id=${state.scripts.gerar_hash_arquivo}&environment=CLONE2`);
    await clickText('a', 'última execução', { navigate: true });
    await expectText('Aviso de respostas carregadas da última execução', 'Carregamos as respostas da sua última execução.');
    const valor = await page.$eval('[name="p_arq_origem"]', (e) => e.value);
    check('Campos preenchidos com as respostas do ticket anterior', valor === FILE_EXTRATO, valor);
    check('Nada é criado até confirmar (a página continua no disparo)', page.url().includes('/tickets/new'));
    await snap('Questionário preenchido com a última execução', { full: true });
};

CTS['CT-06'] = async () => {
    begin('CT-06', 'Lista de tickets, filtros e escopo');
    await startLongTicket('longo1');
    await login('admin');
    await go('/tickets/index');
    await expectText('admin vê tickets de vários ambientes', 'GFPREPROD', 'CLONE2', 'CLONE6');
    await snap('Lista de tickets (admin)', { full: true });
    await go('/tickets/index?status=RUNNING');
    const linhas = await page.$$eval('table tbody tr', (trs) => trs.map((t) => t.innerText));
    check('Filtro pela situação Rodando mostra só tickets rodando', linhas.length > 0 && linhas.every((l) => l.includes('Rodando')),
        linhas.length + ' linha(s)');
    await snap('Filtro pela situação Rodando');
    await go('/tickets/index');
    await page.click('#auto-refresh');
    await sleep(12000);
    await expectText('Atualização automática: "Atualizada às HH:MM:SS"', 'Atualizada às');
    await login('op.hml');
    await go('/tickets/index');
    await expectNoText('op.hml não vê tickets de CLONE1 e CLONE2', 'CLONE2', 'CLONE1');
    await snap('Lista de tickets do op.hml: só os ambientes do perfil', { full: true });
};

CTS['CT-07'] = async () => {
    begin('CT-07', 'Detalhe do ticket e visualizador de log');
    let longo = state.tickets.longo1;
    if (!longo || !(await (async () => { await login('admin'); return ticketStatus(longo); })()).includes('Rodando')) {
        longo = await startLongTicket('longo1');
    }
    await login('admin');
    await go(`/tickets/detail/${longo}`);
    await expectText('Ticket rodando: frase "Está rodando agora. Começou há …" e as etapas', 'Está rodando agora. Começou há', 'Rodando');
    await sleep(4000);
    await snap('Detalhe do ticket rodando, com log', { full: true });
    const dl = await page.$eval('a[download^="ticket_"]', (a) => a.getAttribute('download'));
    check('Baixar log baixa ticket_<id>.log', dl === `ticket_${longo}.log`, dl);
    note('Os scripts PYTHON3 rodam com -I e saída em buffer: o log de um script Python aparece quando o buffer descarrega (no fim); scripts SH/BASH escrevem na hora.');
    // Exibicao segura: o caminho com marcacao HTML volta no log como texto
    await login('op.hml');
    const xss = path.join(INPUT, 'gfpreprod', 'contar_linhas_arquivo', '<script>alert(1)</script> <b>negrito</b>.txt');
    const idx = await createTicket('contar_linhas_arquivo', 'GFPREPROD', { caminho_arquivo: xss });
    state.tickets.xss = idx;
    saveState();
    let dialog = false;
    page.once('dialog', async (d) => { dialog = true; await d.dismiss(); });
    await waitStatus(idx, ['Deu erro', 'Deu certo'], 120);
    await sleep(4000);
    await expectText('Marcação HTML do log aparece como texto', '<script>alert(1)</script> <b>negrito</b>');
    check('Nenhum script executado e nenhum negrito aplicado', !dialog && (await page.$$eval('.sss-log b, pre b', (b) => b.length)) === 0);
    await login('admin');
    await go(`/tickets/detail/${state.tickets.erro_hml}`);
    await expectText('Ticket com erro: o que aconteceu, o que fazer e o detalhe técnico', 'Deu erro', 'O que aconteceu', 'O que fazer agora', 'EXIT_ERROR');
    await snap('Detalhe de ticket que deu erro', { full: true });
};

CTS['CT-08'] = async () => {
    begin('CT-08', 'Cancelamento de ticket');
    const longo = await startLongTicket('longo2');
    await login('admin');
    await go(`/tickets/detail/${longo}`);
    const page2 = await browser.newPage();
    const cookies = await page.cookies();
    await page2.setCookie(...cookies);
    await page2.goto(`${BASE_URL}/tickets/detail/${longo}`, { waitUntil: 'networkidle0' });
    await page.bringToFront();
    await clickText('button', 'Cancelar este pedido');
    await expectText('A janela explica o efeito do cancelamento de um ticket rodando', `Cancelar o pedido #${longo}`);
    await snap('Confirmação de cancelamento');
    await confirmModal();
    await expectText('Rodando: "Cancelamento solicitado ao agente; ele vai encerrar a execução."',
        'Cancelamento solicitado ao agente; ele vai encerrar a execução.');
    // segunda aba, aberta antes do pedido
    await page2.bringToFront();
    const btns = await page2.$$('button');
    for (const b of btns) {
        if ((await b.evaluate((e) => e.innerText)).includes('Cancelar este pedido')) { await b.click(); break; }
    }
    await sleep(600);
    const sub = await page2.$$('.modal button[type="submit"]');
    for (const s of sub) {
        if (await s.evaluate((e) => e.getBoundingClientRect().width > 0)) {
            await Promise.all([page2.waitForNavigation({ waitUntil: 'networkidle0' }), s.click()]);
            break;
        }
    }
    const t2 = await page2.evaluate(() => document.body.innerText);
    check('Segunda aba (aberta antes do pedido): "O cancelamento já havia sido solicitado." ou "O ticket já estava encerrado."',
        t2.includes('O cancelamento já havia sido solicitado.') || t2.includes('O ticket já estava encerrado.'));
    await page.bringToFront();
    const fim = await waitStatus(longo, ['Cancelado'], 90);
    check(`Ticket #${longo} cancelado pelo agente real (processo encerrado)`, fim.includes('Cancelado'));
    await sleep(3000);
    await snap('Ticket após o pedido de cancelamento', { full: true });
    await expectNoText('O botão Cancelar este pedido some do ticket terminado', 'Cancelar este pedido');
    await page2.close();
    // ticket esperando (agendado para daqui a 2 horas) do op.prod
    await login('op.prod');
    const esp = await createTicket('gerar_hash_arquivo', 'CLONE2', { arq_origem: FILE_EXTRATO }, { scheduledAt: localIso(120) });
    state.tickets.esperando = esp;
    saveState();
    await expectText('Ticket agendado fica Esperando', 'Esperando');
    await clickText('button', 'Cancelar este pedido');
    await confirmModal();
    await expectText('Esperando: o ticket fica Cancelado imediatamente', 'Cancelado');
    note('Cada pedido de cancelamento gera TICKET_CANCEL na auditoria (conferido no CT-19).');
};

CTS['CT-09'] = async () => {
    begin('CT-09', 'Reexecução de ticket');
    await login('op.prod');
    const orig = state.tickets.ok_prod;
    await go(`/tickets/detail/${orig}`);
    await clickText('button', 'Rodar de novo');
    await expectText('A janela explica que um novo pedido será criado com as mesmas respostas', 'Um novo pedido será criado com as mesmas respostas');
    await snap('Confirmação de reexecução');
    await confirmModal();
    const novo = ticketFromUrl();
    state.tickets.rerun = novo;
    saveState();
    await expectText('"Ticket #N criado como reexecução do ticket #orig."', `Ticket #${novo} criado como reexecução do ticket #${orig}.`);
    await snap('Ticket criado por reexecução', { full: true });
    await waitStatus(novo, ['Deu certo', 'Deu erro'], 120);
    await go(`/tickets/detail/${orig}`);
    await expectText('O ticket original lista a reexecução', `#${novo}`);
    // cadastro mudou: parametro obrigatorio novo no gerar_hash_arquivo
    await login('admin');
    await go(`/admin_scripts/parameters/${state.scripts.gerar_hash_arquivo}`);
    const linksAntes = await page.$eval('[data-links]', (e) => e.getAttribute('data-links'));
    state.linksGerarHash = linksAntes;
    saveState();
    const avail = JSON.parse(await page.$eval('[data-available]', (e) => e.getAttribute('data-available')));
    const extra = avail.find((p) => p.code === 'termo_busca');
    const atuais = JSON.parse(linksAntes).map((l) => ({ parameter_id: l.id, required: l.required, default_value_override: l.default_value_override || '',
        keep_secret: l.sensitive && l.has_override && !l.default_value_override }));
    atuais.push({ parameter_id: extra.id, required: true, default_value_override: '', keep_secret: false });
    await page.$eval('input[name="links_json"]', (e, v) => { e.value = v; }, JSON.stringify(atuais));
    await page.$eval('form[action*="save_parameters"]', (f) => f.submit());
    await page.waitForNavigation({ waitUntil: 'networkidle0' });
    await expectText('Vínculo obrigatório novo (termo_busca) salvo no gerar_hash_arquivo', 'Parâmetros salvos:', 'termo_busca');
    await login('op.prod');
    await go(`/tickets/detail/${orig}`);
    await clickText('button', 'Rodar de novo');
    await confirmModal();
    await expectText('Cadastro mudou: volta ao formulário com o aviso', 'Não foi possível reexecutar automaticamente');
    check('Nenhum ticket criado (continua no disparo)', page.url().includes('/tickets/new'), page.url().replace(BASE_URL, ''));
    await login('admin');
    await go(`/admin_scripts/parameters/${state.scripts.gerar_hash_arquivo}`);
    const restaura = JSON.parse(linksAntes).map((l) => ({ parameter_id: l.id, required: l.required, default_value_override: l.default_value_override || '',
        keep_secret: l.sensitive && l.has_override && !l.default_value_override }));
    await page.$eval('input[name="links_json"]', (e, v) => { e.value = v; }, JSON.stringify(restaura));
    await page.$eval('form[action*="save_parameters"]', (f) => f.submit());
    await page.waitForNavigation({ waitUntil: 'networkidle0' });
    const depois = await page.$eval('[data-links]', (e) => JSON.parse(e.getAttribute('data-links')).map((l) => l.code).join(','));
    check('Vínculo desfeito ao final (cadastro restaurado)', !depois.includes('termo_busca'), depois);
    await login('op.prod');
    await go(`/tickets/detail/${state.tickets.ok_admin}`);
    await expectNoText('Ticket de outro usuário: sem o botão Rodar de novo', 'Rodar de novo');
};

CTS['CT-10'] = async () => {
    begin('CT-10', 'Perfil somente leitura (consulta)');
    await login('consulta');
    await go('/tickets/index');
    await expectText('A lista mostra tickets dos ambientes do perfil', 'GFPREPROD', 'CLONE2');
    await snap('Lista de tickets do consulta', { full: true });
    await go(`/tickets/detail/${state.tickets.ok_hml}`);
    await expectNoText('Detalhe sem Cancelar e sem Rodar de novo', 'Cancelar este pedido', 'Rodar de novo');
    await expectText('O log é visível', 'Log');
    await snap('Detalhe sem ações para o consulta', { full: true });
    const st = await go('/tickets/new');
    await expectText('Disparo direto pela URL: acesso negado', 'Você não tem permissão para abrir esta página.');
    check('Status HTTP 403', st === 403, 'status ' + st);
    await snap('Página de acesso negado (403) no disparo');
};

// Fecha o modal aberto sem confirmar (Esc, como o usuario).
async function closeModal() {
    await page.keyboard.press('Escape');
    await sleep(400);
}

// Id do registro a partir da lista (link de edicao na linha que contem `name`).
async function idFromList(listPath, name, linkPart) {
    await go(listPath);
    return page.$$eval('table tbody tr', (trs, args) => {
        for (const tr of trs) {
            const cells = Array.from(tr.querySelectorAll('td')).map((td) => td.innerText.trim());
            if (cells.includes(args.name) || tr.innerText.split(/\s+/).includes(args.name)) {
                const a = Array.from(tr.querySelectorAll('a')).find((x) => x.getAttribute('href').includes(args.linkPart));
                const m = a && a.getAttribute('href').match(/\/(\d+)(?:$|\?)/);
                if (m) return parseInt(m[1], 10);
            }
        }
        return null;
    }, { name, linkPart });
}

async function registroTexto() {
    return page.evaluate(() => {
        const sec = document.querySelector('section[aria-labelledby="title-record"]');
        return sec ? sec.innerText.replace(/\s+/g, ' ').trim() : '';
    });
}

async function errorOf(field) {
    // components/form_field.html usa o sufixo -erro; os formularios proprios (disparo, regra) usam -error.
    return page.$eval(`#field-${field}-erro, #field-${field}-error`, (e) => e.innerText.trim()).catch(() => '');
}

const RUN = (() => { const d = new Date(); return String(d.getHours()).padStart(2, '0') + String(d.getMinutes()).padStart(2, '0'); })();
const ENV_NOVO = `${STAMP}_${RUN}`;  // ambiente criado no CT-11 (fica inativo no fim); um por rodada
const PRF_NOVO = STAMP + '_P';   // perfil criado no CT-25 (somente leitura de usuarios)
const PRM_SIGILOSO = 'documento_cliente_hml';

CTS['CT-11'] = async () => {
    begin('CT-11', 'Gestão de Ambientes');
    await login('admin');
    await go('/admin_environments/index');
    await expectText('Lista com os ambientes do DEV', 'CLONE1', 'CLONE2', 'CLONE6', 'CLONE7', 'GFPREPROD');
    await snap('Lista de ambientes');
    await go('/admin_environments/form');
    await fill('#field-name', '  QA_01  ');
    await fill('#field-description', 'Ambiente de teste');
    await submit('/admin_environments/save');
    await expectText('Nome com espaços em volta recusado e aviso no topo',
        'Não use espaços no início nem no fim.', 'Alguns campos precisam de correção.');
    await snap('Identificador com espaços recusado');
    await go('/admin_environments/form');
    await fill('#field-name', ENV_NOVO);
    await fill('#field-description', 'Ambiente criado na homologação de 22/10/2026');
    await submit('/admin_environments/save');
    await expectText('Inclusão válida: mensagem de sucesso', 'Ambiente salvo com sucesso.');
    const envId = await idFromList(`/admin_environments/index?name=${ENV_NOVO}`, ENV_NOVO, '/admin_environments/form/');
    state.envNovo = envId;
    saveState();
    check(`Ambiente ${ENV_NOVO} gravado`, !!envId, '#' + envId);
    await go(`/admin_environments/form/${envId}`);
    await fill('#field-description', 'Ambiente criado na homologação de 22/10/2026 (descrição alterada)');
    await submit('/admin_environments/save');
    await expectText('Alteração: mensagem de sucesso', 'Ambiente salvo com sucesso.');
    await go(`/admin_environments/form/${envId}`);
    const registroAntes = await registroTexto();
    await sleep(1100);
    await submit('/admin_environments/save');
    await go(`/admin_environments/form/${envId}`);
    const registroDepois = await registroTexto();
    check('Salvar sem mudança não grava nada (o quadro Registro não muda)', registroAntes && registroAntes === registroDepois, registroDepois);
    const gfId = await idFromList('/admin_environments/index', 'GFPREPROD', '/admin_environments/form/');
    await go(`/admin_environments/form/${gfId}`);
    await clickText('button', 'Desativar');
    await expectText('A desativação mostra o impacto antes de confirmar', 'Desativar ambiente');
    await snap('Confirmação de desativação de ambiente');
    await closeModal();
    await go(`/admin_environments/form/${envId}`);
    await clickText('button', 'Desativar');
    await confirmModal();
    await expectText(`Ambiente ${ENV_NOVO} desativado ao final (não recebe execuções)`, 'Inativo');
    note(`O ambiente ${ENV_NOVO} fica cadastrado e inativo como evidência (inclusão, alteração e desativação na auditoria).`);
};

CTS['CT-12'] = async () => {
    begin('CT-12', 'Gestão de Perfis e matriz de permissões');
    await login('admin');
    await go('/admin_profiles/index');
    await expectText('Lista com os 4 perfis do seed', 'ADMINISTRATOR', 'OPERATOR_PROD', 'OPERATOR_HML', 'READ_ONLY');
    await snap('Lista de perfis');
    const ro = await idFromList('/admin_profiles/index', 'READ_ONLY', '/admin_profiles/form/');
    await go(`/admin_profiles/form/${ro}`);
    await clickText('button', 'Desativar');
    await expectText('A confirmação diz o efeito e quem é afetado',
        'Os usuários deste perfil perdem o acesso e têm a sessão encerrada no próximo clique.', 'consulta');
    await snap('Desativação de perfil com usuários afetados');
    await closeModal();
    const hml = await idFromList('/admin_profiles/index', 'OPERATOR_HML', '/admin_profiles/form/');
    state.profiles = Object.assign(state.profiles || {}, { READ_ONLY: ro, OPERATOR_HML: hml });
    await go(`/admin_profiles/matrix/${hml}`);
    await clickText('button[data-tab]', 'Ambientes');
    const marcou = await page.evaluate(() => {
        const toggle = (name, txt) => {
            const box = Array.from(document.querySelectorAll(`input[name="${name}"]`))
                .find((i) => (i.closest('label, li, tr, div') || i.parentElement).innerText.includes(txt));
            if (box) box.click();
            return !!box;
        };
        return toggle('ambs', 'CLONE7') && toggle('funcs', 'VIEW_AUDIT');
    });
    check('Marcações feitas na matriz (−CLONE7, +VIEW_AUDIT)', marcou);
    await sleep(400);
    await expectText('Contador de alterações pendentes', '2 alterações pendentes.');
    await snap('Matriz de permissões (aba Ambientes)');
    await clickText('button', 'Revisar e salvar');
    await expectText('Resumo da revisão no formato +código / -amb:nome', '+VIEW_AUDIT', '-amb:CLONE7');
    await snap('Revisão das alterações da matriz');
    await closeModal();
    note('A revisão foi cancelada: a matriz do OPERATOR_HML não foi alterada neste CT.');
    const adm = await idFromList('/admin_profiles/index', 'ADMINISTRATOR', '/admin_profiles/form/');
    state.profiles.ADMINISTRATOR = adm;
    saveState();
    await go(`/admin_profiles/form/${adm}`);
    const temDesativar = await clickText('button', 'Desativar');
    if (temDesativar) {
        await confirmModal();
        await expectText('Desativar o próprio perfil é negado', 'Você não pode desativar o seu próprio perfil.');
    } else {
        check('O próprio perfil não oferece Desativar', true);
    }
    await go(`/admin_profiles/form/${adm}`);
    await page.$eval('[name="is_admin"]', (e) => { if (e.type === 'checkbox') e.checked = false; else e.value = 'N'; });
    await submit('/admin_profiles/save');
    await expectText('Remover o acesso administrativo do próprio perfil é negado',
        'Você não pode remover o acesso administrativo do seu próprio perfil.');
};

CTS['CT-13'] = async () => {
    begin('CT-13', 'Quem pode o quê');
    await login('admin');
    await go(`/admin_profiles/who_can?script=${state.scripts.contar_linhas_arquivo}`);
    await expectText('Por script: perfis ativos, por quê, onde e usuários ativos', 'ADMINISTRATOR', 'OPERATOR_PROD', 'OPERATOR_HML');
    await snap('Quem pode o quê: perfis que podem rodar o contar_linhas_arquivo', { full: true });
    const gf = await page.$$eval('#field-environment option', (os) => (os.find((o) => o.innerText.trim() === 'GFPREPROD') || {}).value);
    await go(`/admin_profiles/who_can?environment=${gf}`);
    await expectText('Por ambiente: quem roda o quê no GFPREPROD', 'GFPREPROD', 'OPERATOR_HML');
    const ok = await clickText('table a', 'OPERATOR_HML', { navigate: true });
    check('O nome do perfil leva à matriz de permissões', ok && page.url().includes('/admin_profiles/matrix/'), page.url().replace(BASE_URL, ''));
    await login('op.prod');
    const st = await go('/admin_profiles/who_can');
    check('op.prod: acesso negado (403)', st === 403 && (await has('Você não tem permissão para abrir esta página.')), 'status ' + st);
};

CTS['CT-14'] = async () => {
    begin('CT-14', 'Gestão de Usuários');
    // bloqueio real do consulta: 5 tentativas erradas pelo login
    for (let i = 0; i < 5; i++) await login('consulta', 'senha-errada-ct14');
    await expectText('Depois de 5 falhas a conta fica bloqueada', 'Houve muitas tentativas com a senha errada.');
    await login('admin');
    await go('/admin_users/index');
    await expectText('Lista com os 4 usuários do seed', 'admin', 'op.prod', 'op.hml', 'consulta');
    await snap('Lista de usuários');
    await go('/admin_users/index?state=B');
    await expectText('Filtro Bloqueados mostra o consulta', 'consulta');
    const prod = await idFromList('/admin_users/index', 'op.prod', '/admin_users/form/');
    const cons = await idFromList('/admin_users/index', 'consulta', '/admin_users/form/');
    const admId = await idFromList('/admin_users/index', 'admin', '/admin_users/form/');
    state.users = { op_prod: prod, consulta: cons, admin: admId };
    saveState();
    await go(`/admin_users/form/${prod}`);
    await clickText('button', 'Desativar');
    await expectText('Desativar mostra a confirmação', 'Desativar usuário op.prod');
    await closeModal();
    await fill('#field-password', 'curta');
    await fill('#field-confirmation', 'curta');
    await clickText('button', 'Redefinir senha');
    await confirmModal();
    await expectText('Senha fora da política é recusada com a explicação', 'Mínimo de 12 caracteres');
    await go(`/admin_users/form/${prod}`);
    await fill('#field-password', SEED_PASS);
    await fill('#field-confirmation', SEED_PASS);
    await clickText('button', 'Redefinir senha');
    await confirmModal();
    await expectNoText('Senha válida aceita (a senha nunca aparece na tela)', SEED_PASS);
    note('A redefinição do op.prod usou a própria senha inicial, para o usuário continuar com a senha documentada.');
    await go(`/admin_users/form/${prod}`);
    await snap('Edição de usuário', { full: true });
    await fill('#field-name', 'Operador\tProducao');
    await submit('/admin_users/save');
    await expectText('Texto livre com caractere de controle é recusado com explicação', 'caracteres de controle');
    await go(`/admin_users/form/${cons}`);
    await clickText('button', 'Desbloquear');
    await confirmModal();
    await expectText('Desbloquear: mensagem de sucesso', 'Usuário consulta desbloqueado.');
    const okCons = await login('consulta');
    check('consulta volta a entrar depois do desbloqueio', okCons);
    await login('admin');
    await go(`/admin_users/form/${admId}`);
    const temDes = await clickText('button', 'Desativar');
    if (temDes) {
        await confirmModal();
        await expectText('Desativar o próprio usuário é negado', 'não pode');
    } else {
        check('O próprio usuário não oferece Desativar', true);
    }
};

CTS['CT-15'] = async () => {
    begin('CT-15', 'Dicionário de Parâmetros');
    await login('admin');
    await go('/admin_parameters/index?size=50');
    await expectText('Lista com os parâmetros do seed', 'arq_origem', 'caminho_arquivo', 'tipo_hash');
    await snap('Lista de parâmetros', { full: true });
    let pid = await idFromList(`/admin_parameters/index?code=${PRM_SIGILOSO}`, PRM_SIGILOSO, '/admin_parameters/form/');
    if (!pid) {
        await go('/admin_parameters/form');
        await fill('#field-code', PRM_SIGILOSO);
        await fill('#field-label', 'Documento do cliente (CPF)');
        await fill('#field-description', 'Somente os 11 números do CPF.');
        await fill('#field-component_type', 'TEXT');
        await fill('#field-param_flag', '--documento');
        await fill('#field-validation_regex', '^[0-9]{11}$');
        await page.$eval('[name="sensitive"]', (e) => { if (e.type === 'checkbox') e.checked = true; else e.value = 'Y'; });
        await submit('/admin_parameters/save');
        await expectText('Parâmetro sigiloso incluído', 'Parâmetro salvo com sucesso.');
        pid = await idFromList(`/admin_parameters/index?code=${PRM_SIGILOSO}`, PRM_SIGILOSO, '/admin_parameters/form/');
    }
    state.prmSigiloso = pid;
    saveState();
    await go(`/admin_parameters/form/${pid}`);
    await expectText('Parâmetro sigiloso com o aviso de credenciais',
        'Não use parâmetros para senhas ou credenciais. Elas ficam visíveis no processo do servidor.');
    await fill('#field-test_value', '12345678901');
    await clickText('button', 'Testar', { wait: 1500 });
    const okValido = await text();
    await fill('#field-test_value', 'abc');
    await clickText('button', 'Testar', { wait: 1500 });
    const okInvalido = await text();
    check('Testar: valor válido aceito e inválido recusado com mensagem', okValido !== okInvalido);
    await snap('Parâmetro sigiloso', { full: true });
    note(`O parâmetro ${PRM_SIGILOSO} fica cadastrado (sem vínculo com scripts) como evidência.`);
};

CTS['CT-16'] = async () => {
    begin('CT-16', 'Gestão de Scripts, homologação e vínculo de parâmetros');
    await login('admin');
    await go('/admin_scripts/index');
    await expectText('Lista com o caminho completo de cada script', '/opt/automacoes/scripts/utilitarios/');
    await snap('Lista de scripts');
    const sid = state.scripts.contar_linhas_arquivo;
    const original = '/opt/automacoes/scripts/utilitarios/contar_linhas_arquivo.sh';
    await go(`/admin_scripts/form/${sid}`);
    const campo = await page.$eval('#field-path_file', (e) => e.value);
    check('Arquivo do script com o caminho completo', campo === original, campo);
    await expectText('Ajuda do campo com o exemplo de caminho', '/opt/automacoes/scripts/');
    await snap('Edição de script com o caminho completo', { full: true });
    const casos = [
        ['contar_linhas_arquivo.sh', 'Informe o caminho completo do arquivo, começando por /'],
        ['/opt/automacoes/../scripts/contar.sh', "O caminho não pode conter '..'."],
        ['/etc/passwd', 'Scripts não podem ficar em pastas do sistema'],
        ['/opt/automacoes/scripts/', 'Escreva o caminho sem // repetida, sem /./ e sem / no fim.'],
    ];
    for (const [valor, msg] of casos) {
        await go(`/admin_scripts/form/${sid}`);
        await fill('#field-path_file', valor);
        await submit('/admin_scripts/save');
        check(`Caminho "${valor}" recusado`, (await errorOf('path_file')).includes(msg), await errorOf('path_file'));
    }
    await go(`/admin_scripts/form/${sid}`);
    await fill('#field-name', 'App');
    await submit('/admin_scripts/save');
    check('Nome "App" recusado como reservado', (await errorOf('name')).includes('Este nome é reservado pelo sistema.'), await errorOf('name'));
    await go(`/admin_scripts/form/${sid}`);
    await fill('#field-path_file', '/opt/automacoes/scripts/utilitarios/contar_linhas_arquivo_nova.sh');
    await submit('/admin_scripts/save');
    await expectText('Arquivo que não existe neste servidor: salvo, com a nota de que o agente confere na execução',
        'Script salvo com sucesso.', 'agente');
    await snap('Script salvo com a nota de conferência pelo agente');
    await go(`/admin_scripts/form/${sid}`);
    await fill('#field-path_file', original);
    await submit('/admin_scripts/save');
    await go(`/admin_scripts/form/${sid}`);
    const atual = await page.$eval('#field-path_file', (e) => e.value);
    check('Caminho original restaurado', atual === original, atual);
    await go(`/admin_scripts/homologation/${sid}`);
    await expectText('Homologação por ambiente com os 5 ambientes ativos', 'CLONE1', 'CLONE2', 'CLONE6', 'CLONE7', 'GFPREPROD');
    await snap('Homologação por ambiente');
    await go(`/admin_scripts/parameters/${sid}`);
    await clickText('button', 'Pré-visualizar', { wait: 1500 });
    await expectText('Vínculo de parâmetros com a prévia do comando', 'caminho_arquivo');
    await snap('Vínculo de parâmetros', { full: true });
};

function hhmm(offsetMin) {
    const d = new Date(Date.now() + offsetMin * 60000);
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
}

async function scheduleRow(name) {
    return page.$$eval('table tbody tr', (trs, n) => {
        const tr = trs.find((t) => t.innerText.includes(n));
        return tr ? tr.innerText : '';
    }, name);
}

// Formulario de modal de estado (pausar/retomar) da linha da regra, pelo id oculto.
async function ruleAction(p, action, ruleId) {
    const forms = await p.$$(`form[action*="/schedules/${action}"]`);
    for (const f of forms) {
        const id = await f.$eval('input[name="id"]', (e) => e.value).catch(() => '');
        if (id === String(ruleId)) {
            await Promise.all([p.waitForNavigation({ waitUntil: 'networkidle0' }), f.evaluate((x) => x.submit())]);
            return true;
        }
    }
    return false;
}

const RULE = `${STAMP}_DIARIA_${RUN}`;

CTS['CT-17'] = async () => {
    begin('CT-17', 'Regras de Agendamento');
    await login('admin');
    const sid = state.scripts.contar_linhas_arquivo;
    await go(`/schedules/form?script_id=${sid}&environment=GFPREPROD`);
    await fill('#field-recurrence_type', 'CRON');
    await fill('#field-cron_expression', '61 * * * *');
    await fill('[name="name"]', RULE + '_CRON');
    await fill('[name="p_caminho_arquivo"]', FILE_CLIENTES);
    await submit('/schedules/save');
    check('CRON inválido recusado com explicação', (await errorOf('cron_expression')) !== '', await errorOf('cron_expression'));
    await go(`/schedules/form?script_id=${sid}&environment=GFPREPROD`);
    await fill('#field-recurrence_type', 'CRON');
    await fill('#field-cron_expression', '0 0 31 2 *');
    await fill('[name="name"]', RULE + '_CRON');
    await fill('[name="p_caminho_arquivo"]', FILE_CLIENTES);
    await submit('/schedules/save');
    check('Data inexistente (31/02 no CRON) recusada com explicação', (await errorOf('cron_expression')) !== '', await errorOf('cron_expression'));
    // regra diaria real, com a primeira execucao em poucos minutos (o agente cria o ticket)
    await go(`/schedules/form?script_id=${sid}&environment=GFPREPROD`);
    const hora = hhmm(4);
    await fill('[name="name"]', RULE);
    await fill('#field-recurrence_type', 'DAILY');
    await fill('#field-run_time', hora);
    await fill('#field-start_date', localIso(1));
    await fill('[name="p_caminho_arquivo"]', FILE_CLIENTES);
    await sleep(2500);
    await expectText('Prévia das próximas execuções coerente com a regra', `às ${hora}`);
    await snap('Edição de regra com prévia', { full: true });
    await submit('/schedules/save');
    await expectText('Regra salva com sucesso', 'Regra de agendamento salva com sucesso.');
    await go(`/schedules/index?name=${RULE}`);
    const ruleId = await page.$$eval('table tbody tr a', (as, n) => {
        const a = as.find((x) => x.closest('tr').innerText.includes(n) && /\/schedules\/form\/\d+/.test(x.getAttribute('href')));
        return a ? parseInt(a.getAttribute('href').match(/form\/(\d+)/)[1], 10) : null;
    }, RULE);
    state.rule = { id: ruleId, name: RULE, hora };
    saveState();
    check(`Regra ${RULE} gravada (diária às ${hora})`, !!ruleId, '#' + ruleId);
    await go('/schedules/index');
    await snap('Lista de regras de agendamento', { full: true });
    await go(`/schedules/index?name=${RULE}`);
    await clickText('button', 'Pausar');
    await expectText('Confirmação de pausa', 'Pausar');
    await snap('Confirmação de pausa');
    await confirmModal();
    await expectText('Pausar: mensagem e situação Pausado', `Regra ${RULE} pausada.`, 'Pausado');
    await go(`/schedules/index?name=${RULE}`);
    await clickText('button', 'Retomar');
    await confirmModal();
    await expectText('Retomar recalcula a próxima execução', `Regra ${RULE} retomada.`);
};

CTS['CT-18'] = async () => {
    begin('CT-18', 'Agenda dos próximos 7 dias');
    await login('admin');
    await go('/schedules/agenda');
    await expectText('Agenda com a regra ativa, recorrência em palavras e o aviso de previsão',
        state.rule.name, 'Regras pausadas não aparecem aqui.');
    await snap('Agenda dos próximos 7 dias', { full: true });
    const ok = await clickText('a', state.rule.name, { navigate: true });
    check('O nome da regra leva ao formulário dela', ok && page.url().includes(`/schedules/form/${state.rule.id}`), page.url().replace(BASE_URL, ''));
    await login('op.prod');
    const st = await go('/schedules/agenda');
    check('op.prod: acesso negado (403)', st === 403, 'status ' + st);
    // execucao real criada pela regra: o agente desdobra a regra no horario e gera o ticket
    await login('admin');
    const fim = Date.now() + 8 * 60000;
    let linha = '';
    while (Date.now() < fim) {
        await go('/tickets/index?source=agendamento');
        linha = await page.$$eval('table tbody tr', (trs) => (trs[0] ? trs[0].innerText : ''));
        if (linha.includes('contar_linhas_arquivo') && linha.includes('agend.')) break;
        await sleep(15000);
    }
    check(`Ticket criado pela regra às ${state.rule.hora} aparece com o selo "agend."`, linha.includes('agend.'), linha.replace(/\s+/g, ' '));
    await snap('Ticket criado pela regra de agendamento (selo agend.)');
};

CTS['CT-19'] = async () => {
    begin('CT-19', 'Auditoria: trilha, filtros e exportação CSV');
    await login('admin');
    await go('/audit/index');
    await expectText('Trilha com o período padrão', 'Trilha de auditoria');
    await snap('Trilha de auditoria', { full: true });
    await go('/audit/index?action=TICKET_CANCEL');
    await expectText('Cancelamentos do CT-08 como TICKET_CANCEL, um por pedido', 'TICKET_CANCEL', 'sinalizado');
    await snap('Filtro por ação TICKET_CANCEL', { full: true });
    const d = new Date(Date.now() - 120 * 86400000);
    const de = d.toISOString().slice(0, 10);
    await go(`/audit/index?date_from=${de}`);
    await expectText('Período acima de 90 dias sem filtro seletivo é recusado', 'Corrija os filtros destacados.', 'O período máximo é de 90 dias.');
    await snap('Período acima do limite');
    await go(`/audit/index?date_from=${de}&actor=admin`);
    await expectNoText('Com o ator informado, o período longo é aceito', 'Corrija os filtros destacados.');
    await go('/audit/index');
    const csv = await page.evaluate(async () => {
        const f = document.querySelector('form[action*="/audit/export"]');
        const r = await fetch(f.action, { method: 'POST', body: new FormData(f), credentials: 'same-origin' });
        const buf = await r.arrayBuffer();
        return { status: r.status, cd: r.headers.get('content-disposition'), ct: r.headers.get('content-type'),
            head: new TextDecoder('utf-8').decode(buf.slice(0, 300)) };
    });
    check('CSV: nome auditoria_AAAAMMDD_HHMMSS.csv', /auditoria_\d{8}_\d{6}\.csv/.test(csv.cd || ''), csv.cd);
    check('CSV: separador ; e cabeçalho em português', (csv.head || '').includes(';') && /Data|Ator|Ação/.test(csv.head), (csv.head || '').split('\n')[0]);
    await go('/audit/index?action=AUDIT_EXPORT');
    await expectText('A exportação aparece na trilha como AUDIT_EXPORT, com filtros e linhas', 'AUDIT_EXPORT', 'linhas');
    await snap('Exportação registrada na trilha');
};

CTS['CT-20'] = async () => {
    begin('CT-20', 'Painel de agentes');
    await login('admin');
    await go('/audit/agents');
    await expectText('Agente real srv-linux-local-01 com saúde, heartbeat, ambientes e interpretadores',
        'srv-linux-local-01', 'GFPREPROD', 'PYTHON3');
    await expectText('Legenda de saúde e limiares', 'Legenda');
    await sleep(17000);
    await expectText('A tela se atualiza sozinha ("Atualizado às …")', 'Atualizado às');
    await snap('Painel de agentes', { full: true });
    note('No DEV há um único agente real; os estados Atrasado, Em risco e Offline do manual vinham de agentes simulados pelo FAKE.');
};

CTS['CT-21'] = async () => {
    begin('CT-21', 'Controle de acesso direto pela URL');
    await login('op.prod');
    for (const p of ['/admin_users/index', '/audit/index', '/schedules/agenda', '/admin_profiles/who_can']) {
        const st = await go(p);
        check(`op.prod em ${p}: acesso negado (403)`, st === 403 && (await has('Você não tem permissão para abrir esta página.')), 'status ' + st);
    }
    await login('op.hml');
    const st404 = await go(`/tickets/detail/${state.tickets.ok_prod}`);
    check(`op.hml no ticket #${state.tickets.ok_prod} (CLONE2, fora do escopo): 404`, st404 === 404, 'status ' + st404);
    await snap('Erro 404 em ticket fora do escopo');
    await go('/default/permissions');
    const html = await page.content();
    check('Telas de consulta não vazam o catálogo (nem CLONE1/CLONE2 no HTML do op.hml)', !html.includes('CLONE2') && !html.includes('CLONE1'));
    await login('consulta');
    const stc = await go('/tickets/catalog');
    check('consulta em /tickets/catalog: 403', stc === 403, 'status ' + stc);
    await clearCookies();
    await go('/default/login?next=https://exemplo.invalido');
    await page.type('#field-login', 'op.hml');
    await page.type('#field-password', passOf('op.hml'));
    await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), page.click('form button[type="submit"]')]);
    check('Login com next externo abre o Painel inicial, nunca o site externo', page.url().startsWith(BASE_URL), page.url());
};

CTS['CT-22'] = async () => {
    begin('CT-22', 'Tema escuro e uso em celular');
    await login('admin');
    await setViewport('dark');
    await go(`/tickets/detail/${state.tickets.ct05}`);
    await snap('Tema escuro (detalhe do ticket)', { full: true });
    await go(`/tickets/history/${state.scripts.contar_linhas_arquivo}`);
    await snap('Tema escuro (histórico com gráfico)', { full: true });
    await setViewport('mobile');
    await go('/default/index');
    let largura = await page.evaluate(() => document.documentElement.scrollWidth);
    check('360 px: painel inicial sem rolagem horizontal', largura <= 360, largura + ' px');
    await snap('Painel inicial em 360 px', { full: true });
    await login('op.hml');
    await go('/tickets/catalog');
    largura = await page.evaluate(() => document.documentElement.scrollWidth);
    check('360 px: rotinas disponíveis sem rolagem horizontal', largura <= 360, largura + ' px');
    await snap('Rotinas disponíveis em 360 px', { full: true });
    await setViewport('desktop');
};

CTS['CT-23'] = async () => {
    begin('CT-23', 'Quadro Registro: quem criou e quem alterou');
    await login('admin');
    const roPrf = await idFromList('/admin_profiles/index', 'READ_ONLY', '/admin_profiles/form/');
    await go(`/admin_profiles/form/${roPrf}`);
    const r1 = await registroTexto();
    note('READ_ONLY no lugar do OPERATOR_PROD do manual: a matriz do OPERATOR_PROD é alterada pelo CT-25 (MANAGE_USERS concedida e retirada), o que atualiza a última alteração do perfil.');
    check('Perfil do seed: criado pelo Sistema (instalação) e nunca alterado', r1.includes('Sistema') && r1.includes('Nunca alterado'), r1);
    await snap('Perfil nunca alterado', { selector: 'section[aria-labelledby="title-record"]' });
    if (state.envNovo) {
        await go(`/admin_environments/form/${state.envNovo}`);
        const r2 = await registroTexto();
        check('Ambiente alterado pela tela: última alteração por admin', r2.includes('por admin'), r2);
        await snap('Ambiente alterado pela tela', { selector: 'section[aria-labelledby="title-record"]' });
    }
    await go(`/tickets/detail/${state.tickets.ok_prod}`);
    const r3 = await registroTexto();
    check('Ticket: criado por op.prod; última alteração pelo agente que finalizou', r3.includes('op.prod') && r3.includes('srv-linux-local-01'), r3);
    await snap('Quadro Registro no detalhe do ticket', { selector: 'section[aria-labelledby="title-record"]' });
    await go('/admin_environments/form');
    check('Inclusão não mostra o quadro Registro', !(await registroTexto()));
};

CTS['CT-24'] = async () => {
    begin('CT-24', 'Robustez do scheduler na interface');
    await login('admin');
    const tentativas = [['ct24_a', '(a|a)*b', false], ['ct24_b', '^(\\w|\\d)+$', false], [`ct24_valor_${RUN}`, '^\\d+(\\.\\d{1,2})?$', true]];
    for (const [code, rx, aceita] of tentativas) {
        await go('/admin_parameters/form');
        await fill('#field-code', code);
        await fill('#field-label', 'Teste de regex ' + code);
        await fill('#field-component_type', 'TEXT');
        await fill('#field-validation_regex', rx);
        await submit('/admin_parameters/save');
        if (aceita) {
            await expectText(`Regex ${rx} aceita`, 'Parâmetro salvo com sucesso.');
        } else {
            const e = await errorOf('validation_regex');
            check(`Regex ${rx} recusada no campo`, e.includes('A expressão regular foi recusada'), e);
            if (code === 'ct24_a') await snap('Regex recusada no Dicionário de Parâmetros');
        }
    }
    await go(`/admin_parameters/form/${state.prmSigiloso}`);
    await page.$eval('[name="sensitive"]', (e) => { if (e.type === 'checkbox') e.checked = false; else e.value = 'N'; });
    await submit('/admin_parameters/save');
    await expectText('Sigiloso não volta atrás', 'Um parâmetro sigiloso não pode deixar de ser sigiloso');
    // data alem de 366 dias no disparo
    await go(`/tickets/new?script_id=${state.scripts.contar_linhas_arquivo}&environment=GFPREPROD`);
    await fill('[name="p_caminho_arquivo"]', FILE_CLIENTES);
    await fill('#field-scheduled_at', localIso(400 * 1440));
    await page.$eval('#form-ticket', (f) => f.submit());
    await page.waitForNavigation({ waitUntil: 'networkidle0' });
    check('Data além de 366 dias recusada no campo Agendar para', (await errorOf('scheduled_at')).includes('Escolha uma data até') ||
        (await has('Escolha uma data até')), await errorOf('scheduled_at'));
    // conflito de pausa em duas abas
    await go(`/schedules/index?name=${state.rule.name}`);
    const page2 = await browser.newPage();
    await page2.setCookie(...(await page.cookies()));
    await page2.goto(`${BASE_URL}/schedules/index?name=${state.rule.name}`, { waitUntil: 'networkidle0' });
    await page.bringToFront();
    await ruleAction(page, 'pause', state.rule.id);
    await expectText('Primeira aba: regra pausada', `Regra ${state.rule.name} pausada.`);
    await page2.bringToFront();
    await ruleAction(page2, 'pause', state.rule.id);
    const t2 = await page2.evaluate(() => document.body.innerText);
    check('Segunda aba: "A regra já está pausada."', t2.includes('A regra já está pausada.'));
    await page2.close();
    await page.bringToFront();
    await go(`/schedules/form/${state.rule.id}`);
    await expectText('Formulário da regra pausada mostra quem pausou e o motivo', 'Pausado manualmente', 'admin');
    await go(`/schedules/index?name=${state.rule.name}`);
    await ruleAction(page, 'resume', state.rule.id);
    await expectText('Regra retomada ao final', `Regra ${state.rule.name} retomada.`);
    note('Responsável inativo: no DEV as regras são do admin (o op.hml não tem Regras de Agendamento), então o cenário do manual não se aplica sem mudar permissões; coberto pelos testes automatizados.');
    note('Link simbólico (CR-011): os 14 scripts do DEV rodaram por /opt/automacoes/scripts/utilitarios, que é um link para dev/scripts/utilitarios; o agente executou o arquivo real (comportamento atual; o manual de 18/10 previa recusa).');
    // quadro Registro por perfil
    await login('consulta');
    await go(`/tickets/detail/${state.tickets.ok_prod}`);
    const rc = await registroTexto();
    check('consulta: o criador aparece como "outra pessoa"', rc.includes('outra pessoa') && !rc.includes('op.prod'), rc);
    await snap('Quadro Registro visto pelo perfil consulta', { selector: 'section[aria-labelledby="title-record"]' });
    await login('op.prod');
    await go(`/tickets/detail/${state.tickets.ok_prod}`);
    const rp = await registroTexto();
    check('op.prod: "por você"', rp.includes('você'), rp);
    await login('admin');
    await go('/audit/agents');
    await snap('Quadros de atenção da tela de agentes', { full: true });
};

CTS['CT-25'] = async () => {
    begin('CT-25', 'Correções da auditoria final');
    await login('admin');
    const prodPrf = await idFromList('/admin_profiles/index', 'OPERATOR_PROD', '/admin_profiles/form/');
    const toggleFunc = async (code) => {
        await go(`/admin_profiles/matrix/${prodPrf}`);
        await page.evaluate((c) => {
            const box = Array.from(document.querySelectorAll('input[name="funcs"]'))
                .find((i) => (i.closest('label, li, tr, div') || i.parentElement).innerText.includes(c));
            if (box) box.click();
        }, code);
        await page.$eval('form[action*="save_matrix"]', (f) => f.submit());
        await page.waitForNavigation({ waitUntil: 'networkidle0' });
    };
    await toggleFunc('MANAGE_USERS');
    await expectText('Permissões salvas: +MANAGE_USERS', 'Permissões salvas: +MANAGE_USERS');
    await login('op.prod');
    const admId = state.users.admin;
    await go(`/admin_users/form/${state.users.op_prod}`);
    const opcoes = await page.$$eval('#field-profile_id option', (os) => os.map((o) => o.innerText));
    check('op.prod não vê ADMINISTRATOR entre os perfis', !opcoes.some((o) => o.includes('ADMINISTRATOR')), opcoes.join(', '));
    await go(`/admin_users/form/${admId}`);
    await fill('#field-password', 'NovaSenhaRecusada123!');
    await fill('#field-confirmation', 'NovaSenhaRecusada123!');
    await clickText('button', 'Redefinir senha');
    await confirmModal();
    await expectText('Redefinir a senha do admin é recusado para quem não é administrador',
        'Só um administrador pode alterar um usuário administrador');
    await snap('Redefinição de senha de administrador recusada');
    await login('admin');
    await toggleFunc('MANAGE_USERS');
    await expectText('Permissão removida ao final: -MANAGE_USERS', 'Permissões salvas: -MANAGE_USERS');
    await go('/admin_parameters/form');
    await fill('#field-code', 'ct25_largo');
    await fill('#field-label', 'Regex larga');
    await fill('#field-component_type', 'TEXT');
    await fill('#field-validation_regex', '\\w{0,100}\\w{0,100}\\w{0,100}x');
    await submit('/admin_parameters/save');
    const e = await errorOf('validation_regex');
    check('Regex com mais de 2 quantificadores largos é recusada', e.includes('quantificadores'), e);
    note('O campo SHA-256 do script foi retirado pelo CR-011 (20/10); o item E4 do manual não se aplica mais.');
    await login('consulta');
    await go(`/tickets/detail/${state.tickets.ok_prod}`);
    await expectText('Cabeçalho do ticket: "solicitado por outra pessoa"', 'solicitado por outra pessoa');
    await expectNoText('Nenhum login de terceiros no detalhe', 'op.prod');
    await snap('Solicitante mascarado para o perfil consulta');
    // Sair encerra a sessao em todos os navegadores
    const ctx2 = await browser.createBrowserContext();
    const p2 = await ctx2.newPage();
    await p2.goto(`${BASE_URL}/default/login`, { waitUntil: 'networkidle0' });
    await p2.type('#field-login', 'op.prod');
    await p2.type('#field-password', passOf('op.prod'));
    await Promise.all([p2.waitForNavigation({ waitUntil: 'networkidle0' }), p2.click('form button[type="submit"]')]);
    await login('op.prod');
    await clickText('form[action*="/default/logout"] button', 'Sair', { navigate: true });
    await expectText('Primeiro navegador: "Você saiu do sistema."', 'Você saiu do sistema.');
    await p2.goto(`${BASE_URL}/tickets/index`, { waitUntil: 'networkidle0' });
    const t2 = await p2.evaluate(() => document.body.innerText);
    check('Segundo navegador volta ao login com "Seu acesso mudou e a sessão foi encerrada."',
        t2.includes('Seu acesso mudou e a sessão foi encerrada.'), p2.url().replace(BASE_URL, ''));
    await ctx2.close();
};

CTS['ENCERRAMENTO'] = async () => {
    begin('ENCERRAMENTO', 'Encerramento: regras da homologação pausadas (ficam como evidência, sem rodar)');
    await login('admin');
    await go(`/schedules/index?name=${STAMP}`);
    const ids = await page.$$eval('form[action*="/schedules/pause"] input[name="id"]', (es) => es.map((e) => e.value));
    for (const id of ids) {
        await go(`/schedules/index?name=${STAMP}`);
        await ruleAction(page, 'pause', id);
    }
    await go(`/schedules/index?name=${STAMP}`);
    const ativas = await page.$$eval('form[action*="/schedules/pause"]', (fs) => fs.length);
    check(`Regras ${STAMP}_* pausadas (${ids.length} nesta etapa)`, ativas === 0, ativas + ' ativa(s) restante(s)');
    await snap('Regras da homologação pausadas ao final', { full: true });
};

const ORDER = ['CT-01', 'CT-02', 'CT-03', 'MASSA', 'CT-04', 'CT-05', 'CT-06', 'CT-07', 'CT-08', 'CT-09', 'CT-10',
    'CT-11', 'CT-12', 'CT-13', 'CT-14', 'CT-15', 'CT-16', 'CT-17', 'CT-18', 'CT-19', 'CT-20', 'CT-21', 'CT-22',
    'CT-23', 'CT-24', 'CT-25', 'ENCERRAMENTO'];

module.exports = { CTS };

// ---------------------------------------------------------------------------------------------
async function main() {
    const wanted = process.argv.slice(2);
    browser = await puppeteer.launch({
        executablePath: CHROME, headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu', '--window-size=1280,900'],
        defaultViewport: { width: 1280, height: 900 },
    });
    page = await browser.newPage();
    page.setDefaultNavigationTimeout(60000);
    await setViewport('desktop');
    const ids = wanted.length ? wanted : ORDER;
    try {
        for (const id of ids) {
            if (!CTS[id]) { console.error('CT desconhecido: ' + id); continue; }
            try {
                await CTS[id]();
            } catch (err) {
                if (ct === id) check('Execução do roteiro sem erro', false, err && err.stack ? err.stack.split('\n').slice(0, 3).join(' ') : err);
                console.error(err);
            } finally {
                if (results[id]) results[id].finished_at = new Date().toISOString();
                saveResults();
                saveState();
            }
        }
    } finally {
        await browser.close();
    }
}

if (require.main === module) {
    main();
}
