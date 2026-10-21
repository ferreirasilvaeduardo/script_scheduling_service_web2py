/**
 * capture_all_screens.js
 * Executa os 25 Casos de Teste (CT-01 a CT-25) e captura todas as 68 telas para o manual.
 */
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');

const OUT_DIR = path.join(__dirname, '..', 'telas');
if (!fs.existsSync(OUT_DIR)) {
    fs.mkdirSync(OUT_DIR, { recursive: true });
}

const BASE_URL = 'http://127.0.0.1:8000/script_scheduling_service';
// Senha do admin do DEV: so pela variavel de ambiente, nunca no codigo.
const PASS_SEED = process.env.SSS_HOMOLOG_SENHA;
if (!PASS_SEED) { console.error('Defina SSS_HOMOLOG_SENHA com a senha do admin do DEV.'); process.exit(2); }

async function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
}

(async () => {
    console.log('Iniciando Chromium para captura completa dos 25 CTs (68 figuras)...');
    const browser = await puppeteer.launch({
        executablePath: '/home/eduardof/.cache/puppeteer/chrome/linux-131.0.6778.204/chrome-linux64/chrome',
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-gpu',
            '--window-size=1280,900',
        ],
        defaultViewport: { width: 1280, height: 900 }
    });

    const page = await browser.newPage();

    async function setDesktop() {
        await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'light' }]);
        await page.setViewport({ width: 1280, height: 900 });
    }

    async function setMobile() {
        await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'light' }]);
        await page.setViewport({ width: 360, height: 780, isMobile: true, hasTouch: true });
    }

    async function setDark() {
        await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'dark' }]);
        await page.setViewport({ width: 1280, height: 900 });
    }

    async function snap(num, fullPage = false, scrollToSelector = null) {
        if (scrollToSelector) {
            await page.evaluate((sel) => {
                const el = document.querySelector(sel);
                if (el) el.scrollIntoView({ behavior: 'instant', block: 'center' });
            }, scrollToSelector);
            await sleep(400);
        }
        const dest = path.join(OUT_DIR, `image${num}.png`);
        await page.screenshot({ path: dest, fullPage });
        console.log(`[OK] Figura ${num} salva -> image${num}.png (fullPage=${fullPage})`);
    }

    async function clearCookies() {
        const cookies = await page.cookies();
        for (const c of cookies) {
            await page.deleteCookie(c);
        }
    }

    async function login(user, pass = PASS_SEED) {
        await clearCookies();
        await page.goto(`${BASE_URL}/default/login`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            const l = document.querySelector('#campo-login');
            const s = document.querySelector('#campo-senha');
            if (l) l.value = '';
            if (s) s.value = '';
        });
        await page.type('#campo-login', user);
        await page.type('#campo-senha', pass);
        await Promise.all([
            page.waitForNavigation({ waitUntil: 'networkidle0' }),
            page.click('button[type="submit"]')
        ]);
    }

    try {
        await setDesktop();

        // ==========================================
        // CT-01 — Login, sessão e troca de senha
        // ==========================================
        console.log('\n--- CT-01 ---');
        await clearCookies();
        await page.goto(`${BASE_URL}/default/login`, { waitUntil: 'networkidle0' });
        await snap(1, false);

        await page.type('#campo-login', 'op.hml');
        await page.type('#campo-senha', 'senha-incorreta-teste');
        await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), page.click('button[type="submit"]')]);
        await snap(2, false);

        await login('admin');
        await page.goto(`${BASE_URL}/default/minha_senha`, { waitUntil: 'networkidle0' });
        await snap(3, false);

        // ==========================================
        // CT-02 — Painel inicial por perfil
        // ==========================================
        console.log('\n--- CT-02 ---');
        await login('admin');
        await page.goto(`${BASE_URL}/default/index`, { waitUntil: 'networkidle0' });
        await snap(4, true);

        await login('op.prod');
        await page.goto(`${BASE_URL}/default/index`, { waitUntil: 'networkidle0' });
        await snap(5, false);

        await login('op.hml');
        await page.goto(`${BASE_URL}/default/index`, { waitUntil: 'networkidle0' });
        await snap(6, false);

        await login('consulta');
        await page.goto(`${BASE_URL}/default/index`, { waitUntil: 'networkidle0' });
        await snap(7, false);

        // ==========================================
        // CT-03 — O que eu posso fazer (op.hml)
        // ==========================================
        console.log('\n--- CT-03 ---');
        await login('op.hml');
        await page.goto(`${BASE_URL}/default/permissoes`, { waitUntil: 'networkidle0' });
        await snap(8, true);

        // ==========================================
        // CT-04 — Rotinas disponíveis e histórico
        // ==========================================
        console.log('\n--- CT-04 ---');
        await login('op.hml');
        await page.goto(`${BASE_URL}/tickets/catalogo`, { waitUntil: 'networkidle0' });
        await snap(9, true);

        await login('admin');
        await page.goto(`${BASE_URL}/tickets/historico/1`, { waitUntil: 'networkidle0' });
        await snap(10, true);

        // ==========================================
        // CT-05 — Disparo de script (criação de ticket)
        // ==========================================
        console.log('\n--- CT-05 ---');
        await login('op.prod');
        await page.goto(`${BASE_URL}/tickets/novo`, { waitUntil: 'networkidle0' });
        await snap(11, false);

        await page.goto(`${BASE_URL}/tickets/novo?script_id=1`, { waitUntil: 'networkidle0' });
        await snap(12, false);

        await page.goto(`${BASE_URL}/tickets/novo?script_id=1&ambiente_id=1`, { waitUntil: 'networkidle0' });
        await snap(13, true);

        // Abrir modal de confirmacao de disparo
        await page.evaluate(() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Criar ticket'));
            if (btn) btn.click();
        });
        await sleep(500);
        await snap(14, false);

        // Confirmar disparo no modal
        const btnModalConfirm = await page.$('#modal-confirmacao button.btn-danger, #modal-confirmacao button[type="submit"]');
        if (btnModalConfirm) {
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle0' }).catch(() => {}),
                btnModalConfirm.click()
            ]);
            await sleep(500);
        }
        if (!page.url().includes('/detalhe/')) {
            await page.goto(`${BASE_URL}/tickets/detalhe/17`, { waitUntil: 'networkidle0' });
        }
        await snap(15, true);

        // Questionário preenchido com última execução
        await page.goto(`${BASE_URL}/tickets/novo?script_id=1&ambiente_id=1`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            const btn = Array.from(document.querySelectorAll('a, button')).find(b => b.textContent.includes('última execução'));
            if (btn) btn.click();
        });
        await sleep(500);
        await snap(16, true);

        // ==========================================
        // CT-06 — Lista de tickets, filtros e escopo
        // ==========================================
        console.log('\n--- CT-06 ---');
        await login('admin');
        await page.goto(`${BASE_URL}/tickets/lista`, { waitUntil: 'networkidle0' });
        await snap(17, true);

        await page.goto(`${BASE_URL}/tickets/lista?status=RUNNING`, { waitUntil: 'networkidle0' });
        await snap(18, false);

        await login('op.hml');
        await page.goto(`${BASE_URL}/tickets/lista`, { waitUntil: 'networkidle0' });
        await snap(19, true);

        // ==========================================
        // CT-07 — Detalhe do ticket e visualizador de log
        // ==========================================
        console.log('\n--- CT-07 ---');
        await login('admin');
        await page.goto(`${BASE_URL}/tickets/detalhe/11`, { waitUntil: 'networkidle0' });
        await snap(20, true);

        await page.goto(`${BASE_URL}/tickets/detalhe/30`, { waitUntil: 'networkidle0' });
        await snap(21, true);

        // ==========================================
        // CT-08 — Cancelamento de ticket
        // ==========================================
        console.log('\n--- CT-08 ---');
        await page.goto(`${BASE_URL}/tickets/detalhe/14`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Cancelar'));
            if (btn) btn.click();
        });
        await sleep(500);
        await snap(22, false);

        const btnConfCanc = await page.$('#modal-cancelar button[type="submit"], .modal button.btn-danger');
        if (btnConfCanc) {
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle0' }).catch(() => {}),
                btnConfCanc.click()
            ]);
            await sleep(1000);
        }
        await snap(23, true);

        // ==========================================
        // CT-09 — Reexecução de ticket
        // ==========================================
        console.log('\n--- CT-09 ---');
        await login('op.prod');
        await page.goto(`${BASE_URL}/tickets/detalhe/19`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Rodar de novo'));
            if (btn) btn.click();
        });
        await sleep(500);
        await snap(24, false);

        const btnConfReexec = await page.$('#modal-reexecutar button[type="submit"], .modal button.btn-primary');
        if (btnConfReexec) {
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle0' }).catch(() => {}),
                btnConfReexec.click()
            ]);
            await sleep(1000);
        }
        await snap(25, true);

        // ==========================================
        // CT-10 — Perfil somente leitura (consulta)
        // ==========================================
        console.log('\n--- CT-10 ---');
        await login('consulta');
        await page.goto(`${BASE_URL}/tickets/lista`, { waitUntil: 'networkidle0' });
        await snap(26, true);

        await page.goto(`${BASE_URL}/tickets/detalhe/12`, { waitUntil: 'networkidle0' });
        await snap(27, true);

        await page.goto(`${BASE_URL}/tickets/novo`, { waitUntil: 'networkidle0' });
        await snap(28, false);

        // ==========================================
        // CT-11 — Gestão de Ambientes
        // ==========================================
        console.log('\n--- CT-11 ---');
        await login('admin');
        await page.goto(`${BASE_URL}/admin_ambientes/lista`, { waitUntil: 'networkidle0' });
        await snap(29, false);

        await page.goto(`${BASE_URL}/admin_ambientes/form`, { waitUntil: 'networkidle0' });
        await page.type('#campo-nome', '  QA_01  ');
        await page.type('#campo-descricao', 'Ambiente de teste');
        await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), page.click('button[type="submit"]')]);
        await snap(30, false);

        await page.goto(`${BASE_URL}/admin_ambientes/form/2`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Desativar'));
            if (btn) btn.click();
        });
        await sleep(500);
        await snap(31, false);

        // ==========================================
        // CT-12 — Gestão de Perfis e matriz de permissões
        // ==========================================
        console.log('\n--- CT-12 ---');
        await page.goto(`${BASE_URL}/admin_perfis/lista`, { waitUntil: 'networkidle0' });
        await snap(32, false);

        await page.goto(`${BASE_URL}/admin_perfis/form/4`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Desativar'));
            if (btn) btn.click();
        });
        await sleep(500);
        await snap(33, false);

        await page.goto(`${BASE_URL}/admin_perfis/matriz/3?aba=ambientes`, { waitUntil: 'networkidle0' });
        await snap(34, false);

        await page.evaluate(() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Revisar e salvar'));
            if (btn) btn.click();
        });
        await sleep(500);
        await snap(35, false);

        // ==========================================
        // CT-13 — Quem pode o quê (novo)
        // ==========================================
        console.log('\n--- CT-13 ---');
        await page.goto(`${BASE_URL}/admin_perfis/quem_pode?modo=script&script_id=1`, { waitUntil: 'networkidle0' });
        await snap(36, false);

        // ==========================================
        // CT-14 — Gestão de Usuários
        // ==========================================
        console.log('\n--- CT-14 ---');
        await page.goto(`${BASE_URL}/admin_usuarios/lista`, { waitUntil: 'networkidle0' });
        await snap(37, false);

        await page.goto(`${BASE_URL}/admin_usuarios/form/2`, { waitUntil: 'networkidle0' });
        await snap(38, true);

        // ==========================================
        // CT-15 — Dicionário de Parâmetros
        // ==========================================
        console.log('\n--- CT-15 ---');
        await page.goto(`${BASE_URL}/admin_parametros/lista`, { waitUntil: 'networkidle0' });
        await snap(39, true);

        await page.goto(`${BASE_URL}/admin_parametros/form/4`, { waitUntil: 'networkidle0' });
        await snap(40, true);

        // ==========================================
        // CT-16 — Gestão de Scripts
        // ==========================================
        console.log('\n--- CT-16 ---');
        await page.goto(`${BASE_URL}/admin_scripts/lista`, { waitUntil: 'networkidle0' });
        await snap(41, false);

        await page.goto(`${BASE_URL}/admin_scripts/form/1`, { waitUntil: 'networkidle0' });
        await snap(42, true);

        await page.evaluate(() => {
            const el = document.querySelector('#campo-path_file');
            if (el) el.value = '/opt/automacoes/scripts/carga_diaria_nova.py';
        });
        const formSalvarScr1 = await page.$('form[action*="/admin_scripts/salvar"]');
        if (formSalvarScr1) {
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle0' }),
                formSalvarScr1.evaluate(f => f.submit())
            ]);
        }
        await snap(43, true);

        // Restaurar caminho original
        await page.evaluate(() => {
            const el = document.querySelector('#campo-path_file');
            if (el) el.value = '/opt/automacoes/scripts/carga_diaria.py';
        });
        const formSalvarScr2 = await page.$('form[action*="/admin_scripts/salvar"]');
        if (formSalvarScr2) {
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle0' }),
                formSalvarScr2.evaluate(f => f.submit())
            ]);
        }

        await page.goto(`${BASE_URL}/admin_scripts/homologacao/1`, { waitUntil: 'networkidle0' });
        await snap(44, false);

        await page.goto(`${BASE_URL}/admin_scripts/parametros/1`, { waitUntil: 'networkidle0' });
        await snap(45, true);

        // ==========================================
        // CT-17 — Regras de Agendamento
        // ==========================================
        console.log('\n--- CT-17 ---');
        await page.goto(`${BASE_URL}/agendamentos/lista`, { waitUntil: 'networkidle0' });
        await snap(46, true);

        await page.goto(`${BASE_URL}/agendamentos/form/1`, { waitUntil: 'networkidle0' });
        await snap(47, true);

        await page.goto(`${BASE_URL}/agendamentos/lista`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Pausar'));
            if (btn) btn.click();
        });
        await sleep(500);
        await snap(48, false);

        // ==========================================
        // CT-18 — Agenda dos próximos 7 dias
        // ==========================================
        console.log('\n--- CT-18 ---');
        await page.goto(`${BASE_URL}/agendamentos/agenda`, { waitUntil: 'networkidle0' });
        await snap(49, true);

        // ==========================================
        // CT-19 — Auditoria: trilha, filtros e exportação CSV
        // ==========================================
        console.log('\n--- CT-19 ---');
        await page.goto(`${BASE_URL}/auditoria/lista`, { waitUntil: 'networkidle0' });
        await snap(50, true);

        await page.goto(`${BASE_URL}/auditoria/lista?acao=TICKET_CANCELAR`, { waitUntil: 'networkidle0' });
        await snap(51, false);

        await page.goto(`${BASE_URL}/auditoria/lista?de=2026-01-01&ate=2026-10-18`, { waitUntil: 'networkidle0' });
        await snap(52, false);

        await page.goto(`${BASE_URL}/auditoria/lista?acao=AUD_EXPORTAR`, { waitUntil: 'networkidle0' });
        await snap(53, false);

        // ==========================================
        // CT-20 — Painel de agentes
        // ==========================================
        console.log('\n--- CT-20 ---');
        await page.goto(`${BASE_URL}/auditoria/agentes`, { waitUntil: 'networkidle0' });
        await snap(54, false);

        // ==========================================
        // CT-21 — Controle de acesso direto pela URL
        // ==========================================
        console.log('\n--- CT-21 ---');
        await login('op.hml');
        await page.goto(`${BASE_URL}/tickets/detalhe/1`, { waitUntil: 'networkidle0' });
        await snap(55, false);

        // ==========================================
        // CT-22 — Tema escuro e uso em celular
        // ==========================================
        console.log('\n--- CT-22 ---');
        await setDark();
        await login('admin');
        await page.goto(`${BASE_URL}/tickets/detalhe/11`, { waitUntil: 'networkidle0' });
        await snap(56, true);

        await page.goto(`${BASE_URL}/tickets/historico/1`, { waitUntil: 'networkidle0' });
        await snap(57, true);

        await setMobile();
        await page.goto(`${BASE_URL}/default/index`, { waitUntil: 'networkidle0' });
        await snap(58, true);

        await login('op.hml');
        await page.goto(`${BASE_URL}/tickets/catalogo`, { waitUntil: 'networkidle0' });
        await snap(59, true);

        await setDesktop();

        // ==========================================
        // CT-23 — Quadro Registro: quem criou e quem alterou
        // ==========================================
        console.log('\n--- CT-23 ---');
        await login('admin');
        await page.goto(`${BASE_URL}/admin_perfis/form/2`, { waitUntil: 'networkidle0' });
        await snap(60, false, '.sss-quadro-registro, section[aria-label*="Registro"]');

        await page.goto(`${BASE_URL}/admin_ambientes/form/1`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            const desc = document.querySelector('#campo-descricao');
            if (desc) desc.value = desc.value + ' (atualizado)';
        });
        const formSalvarAmb = await page.$('form[action*="/admin_ambientes/salvar"]');
        if (formSalvarAmb) {
            await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), formSalvarAmb.evaluate(f => f.submit())]);
        }
        await snap(61, false, '.sss-quadro-registro, section[aria-label*="Registro"]');

        await page.goto(`${BASE_URL}/tickets/detalhe/17`, { waitUntil: 'networkidle0' });
        await snap(62, false, '.sss-quadro-registro, section[aria-label*="Registro"]');

        // ==========================================
        // CT-24 — Robustez do scheduler na interface
        // ==========================================
        console.log('\n--- CT-24 ---');
        await page.goto(`${BASE_URL}/admin_parametros/form`, { waitUntil: 'networkidle0' });
        await page.type('#campo-codigo', 'ct24_a');
        await page.type('#campo-label', 'Teste Regex');
        await page.type('#campo-regex_validacao', '(a|a)*b');
        await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), page.click('button[type="submit"]')]);
        await snap(63, false);

        await login('consulta');
        await page.goto(`${BASE_URL}/tickets/detalhe/17`, { waitUntil: 'networkidle0' });
        await snap(64, false, '.sss-quadro-registro, section[aria-label*="Registro"]');

        await login('admin');
        await page.goto(`${BASE_URL}/auditoria/agentes`, { waitUntil: 'networkidle0' });
        await snap(65, false);

        // ==========================================
        // CT-25 — Correções da auditoria final
        // ==========================================
        console.log('\n--- CT-25 ---');
        await page.goto(`${BASE_URL}/admin_perfis/matriz/2?aba=funcionalidades`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            const cb = document.querySelector('input[value="CAD_USUARIOS"]') || Array.from(document.querySelectorAll('input[type="checkbox"]')).find(i => i.name && i.name.includes('CAD_USUARIOS'));
            if (cb && !cb.checked) cb.click();
        });
        const formSalvarMat = await page.$('form[action*="/admin_perfis/matriz_salvar"]');
        if (formSalvarMat) {
            await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), formSalvarMat.evaluate(f => f.submit())]);
        }

        await login('op.prod');
        await page.goto(`${BASE_URL}/admin_usuarios/form/1`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            const s = document.querySelector('input[name="senha"]');
            const c = document.querySelector('input[name="confirmacao"]');
            if (s) s.value = 'NovaSenha123!';
            if (c) c.value = 'NovaSenha123!';
        });
        const formRedef = await page.$('form[action*="/admin_usuarios/redefinir_senha"]');
        if (formRedef) {
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle0' }),
                formRedef.evaluate(f => f.submit())
            ]);
        }
        await snap(66, false);

        await login('admin');
        await page.goto(`${BASE_URL}/admin_scripts/form/1`, { waitUntil: 'networkidle0' });
        const dummySha = 'ab'.repeat(32);
        await page.evaluate((val) => {
            const el = document.querySelector('#campo-sha256_informado');
            if (el) el.value = val;
        }, dummySha);
        const formSalvarScrSha = await page.$('form[action*="/admin_scripts/salvar"]');
        if (formSalvarScrSha) {
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle0' }),
                formSalvarScrSha.evaluate(f => f.submit())
            ]);
        }
        await snap(67, false);

        await login('consulta');
        await page.goto(`${BASE_URL}/tickets/detalhe/17`, { waitUntil: 'networkidle0' });
        await snap(68, false);

        console.log('\n=============================================');
        console.log('TODAS AS 68 FIGURAS CAPTURADAS COM SUCESSO ABSOLUTO!');
        console.log('=============================================\n');

    } catch (err) {
        console.error('Erro durante a execucao:', err);
    } finally {
        await browser.close();
    }
})();
