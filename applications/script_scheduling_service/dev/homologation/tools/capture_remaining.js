/**
 * capture_remaining.js
 * Captura as figuras 43 a 68 para o manual.
 */
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');

const OUT_DIR = path.join(__dirname, '..', 'telas');
const BASE_URL = 'http://127.0.0.1:8000/script_scheduling_service';
// Senha do admin do DEV: so pela variavel de ambiente, nunca no codigo.
const PASS_SEED = process.env.SSS_HOMOLOG_PASSWORD;
if (!PASS_SEED) { console.error('Defina SSS_HOMOLOG_PASSWORD com a senha do admin do DEV.'); process.exit(2); }

async function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
}

(async () => {
    console.log('Iniciando captura das figuras 43 a 68...');
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

    async function login(user, pass = PASS_SEED) {
        await page.goto(`${BASE_URL}/default/login`, { waitUntil: 'networkidle0' });
        const jaLogado = await page.evaluate((u) => {
            const el = document.querySelector('.sss-usuario-login');
            return el && el.textContent.includes(u);
        }, user);
        if (jaLogado) return;

        const outroUser = await page.$('form[action*="/default/logout"]');
        if (outroUser) {
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle0' }),
                outroUser.evaluate(f => f.submit())
            ]);
        }

        await page.goto(`${BASE_URL}/default/login`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            document.querySelector('#campo-login').value = '';
            document.querySelector('#campo-senha').value = '';
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
        // CT-16 (continuação)
        // ==========================================
        console.log('\n--- CT-16 (Fig 43 a 45) ---');
        await login('admin');
        await page.goto(`${BASE_URL}/admin_scripts/form/1`, { waitUntil: 'networkidle0' });

        // Fig 43: Script salvo com aviso de arquivo não encontrado
        await page.evaluate(() => {
            const el = document.querySelector('#campo-path_file');
            if (el) el.value = '/opt/automacoes/scripts/carga_diaria_nova.py';
        });
        const btnSalvarScr = await page.$('form[action*="/admin_scripts/save"] button[type="submit"]');
        if (btnSalvarScr) {
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle0' }),
                btnSalvarScr.click()
            ]);
        }
        await snap(43, true);

        // Restaurar caminho original
        await page.evaluate(() => {
            const el = document.querySelector('#campo-path_file');
            if (el) el.value = '/opt/automacoes/scripts/carga_diaria.py';
        });
        const btnRestaurarScr = await page.$('form[action*="/admin_scripts/save"] button[type="submit"]');
        if (btnRestaurarScr) {
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle0' }),
                btnRestaurarScr.click()
            ]);
        }

        // Fig 44: Homologação por ambiente
        await page.goto(`${BASE_URL}/admin_scripts/homologation/1`, { waitUntil: 'networkidle0' });
        await snap(44, false);

        // Fig 45: Vínculo de parâmetros
        await page.goto(`${BASE_URL}/admin_scripts/parameters/1`, { waitUntil: 'networkidle0' });
        await snap(45, true);

        // ==========================================
        // CT-17 — Regras de Agendamento
        // ==========================================
        console.log('\n--- CT-17 (Fig 46 a 48) ---');
        // Fig 46: Lista de regras de agendamento
        await page.goto(`${BASE_URL}/schedules/index`, { waitUntil: 'networkidle0' });
        await snap(46, true);

        // Fig 47: Edição de regra com prévia
        await page.goto(`${BASE_URL}/schedules/form/1`, { waitUntil: 'networkidle0' });
        await snap(47, true);

        // Fig 48: Confirmação de pausa
        await page.goto(`${BASE_URL}/schedules/index`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Pausar'));
            if (btn) btn.click();
        });
        await sleep(500);
        await snap(48, false);

        // ==========================================
        // CT-18 — Agenda dos próximos 7 dias
        // ==========================================
        console.log('\n--- CT-18 (Fig 49) ---');
        await page.goto(`${BASE_URL}/schedules/agenda`, { waitUntil: 'networkidle0' });
        await snap(49, true);

        // ==========================================
        // CT-19 — Auditoria: trilha, filtros e exportação CSV
        // ==========================================
        console.log('\n--- CT-19 (Fig 50 a 53) ---');
        // Fig 50: Trilha de auditoria
        await page.goto(`${BASE_URL}/audit/index`, { waitUntil: 'networkidle0' });
        await snap(50, true);

        // Fig 51: Filtro por ação TICKET_CANCELAR
        await page.goto(`${BASE_URL}/audit/index?acao=TICKET_CANCELAR`, { waitUntil: 'networkidle0' });
        await snap(51, false);

        // Fig 52: Período acima do limite
        await page.goto(`${BASE_URL}/audit/index?de=2026-01-01&ate=2026-10-18`, { waitUntil: 'networkidle0' });
        await snap(52, false);

        // Fig 53: Exportação registrada na trilha
        await page.goto(`${BASE_URL}/audit/index?acao=AUD_EXPORTAR`, { waitUntil: 'networkidle0' });
        await snap(53, false);

        // ==========================================
        // CT-20 — Painel de agentes
        // ==========================================
        console.log('\n--- CT-20 (Fig 54) ---');
        await page.goto(`${BASE_URL}/audit/agents`, { waitUntil: 'networkidle0' });
        await snap(54, false);

        // ==========================================
        // CT-21 — Controle de acesso direto pela URL
        // ==========================================
        console.log('\n--- CT-21 (Fig 55) ---');
        await login('op.hml');
        await page.goto(`${BASE_URL}/tickets/detail/1`, { waitUntil: 'networkidle0' });
        await snap(55, false);

        // ==========================================
        // CT-22 — Tema escuro e uso em celular
        // ==========================================
        console.log('\n--- CT-22 (Fig 56 a 59) ---');
        await setDark();
        await login('admin');
        // Fig 56: Tema escuro (detalhe do ticket)
        await page.goto(`${BASE_URL}/tickets/detail/11`, { waitUntil: 'networkidle0' });
        await snap(56, true);

        // Fig 57: Tema escuro (histórico com gráfico)
        await page.goto(`${BASE_URL}/tickets/history/1`, { waitUntil: 'networkidle0' });
        await snap(57, true);

        // Fig 58: Painel inicial em 360 px
        await setMobile();
        await page.goto(`${BASE_URL}/default/index`, { waitUntil: 'networkidle0' });
        await snap(58, true);

        // Fig 59: Rotinas disponíveis em 360 px
        await login('op.hml');
        await page.goto(`${BASE_URL}/tickets/catalog`, { waitUntil: 'networkidle0' });
        await snap(59, true);

        await setDesktop();

        // ==========================================
        // CT-23 — Quadro Registro: quem criou e quem alterou
        // ==========================================
        console.log('\n--- CT-23 (Fig 60 a 62) ---');
        await login('admin');
        // Fig 60: Perfil nunca alterado (OPERADOR_PROD = id 2)
        await page.goto(`${BASE_URL}/admin_profiles/form/2`, { waitUntil: 'networkidle0' });
        await snap(60, false, '.sss-quadro-registro, section[aria-label*="Registro"]');

        // Fig 61: Ambiente alterado pela tela (PRODUCAO = id 1)
        await page.goto(`${BASE_URL}/admin_environments/form/1`, { waitUntil: 'networkidle0' });
        // Alterar e salvar para ter alteracao
        await page.evaluate(() => {
            const desc = document.querySelector('#campo-description');
            if (desc) desc.value = desc.value + ' (atualizado)';
        });
        const btnSalvarAmb = await page.$('form[action*="/admin_environments/save"] button[type="submit"]');
        if (btnSalvarAmb) {
            await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), btnSalvarAmb.click()]);
        }
        await snap(61, false, '.sss-quadro-registro, section[aria-label*="Registro"]');

        // Fig 62: Quadro Registro no detalhe do ticket (#17)
        await page.goto(`${BASE_URL}/tickets/detail/17`, { waitUntil: 'networkidle0' });
        await snap(62, false, '.sss-quadro-registro, section[aria-label*="Registro"]');

        // ==========================================
        // CT-24 — Robustez do scheduler na interface
        // ==========================================
        console.log('\n--- CT-24 (Fig 63 a 65) ---');
        // Fig 63: Regex recusada no Dicionário de Parâmetros
        await page.goto(`${BASE_URL}/admin_parameters/form`, { waitUntil: 'networkidle0' });
        await page.type('#campo-codigo', 'ct24_a');
        await page.type('#campo-label', 'Teste Regex');
        await page.type('#campo-regex_validacao', '(a|a)*b');
        await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), page.click('button[type="submit"]')]);
        await snap(63, false);

        // Fig 64: Quadro Registro visto pelo perfil consulta
        await login('consulta');
        await page.goto(`${BASE_URL}/tickets/detail/17`, { waitUntil: 'networkidle0' });
        await snap(64, false, '.sss-quadro-registro, section[aria-label*="Registro"]');

        // Fig 65: Quadros de atenção da tela de agentes
        await login('admin');
        await page.goto(`${BASE_URL}/audit/agents`, { waitUntil: 'networkidle0' });
        await snap(65, false);

        // ==========================================
        // CT-25 — Correções da auditoria final
        // ==========================================
        console.log('\n--- CT-25 (Fig 66 a 68) ---');
        // Fig 66: Redefinição de senha de administrador recusada
        await page.goto(`${BASE_URL}/admin_profiles/matrix/2`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            const cb = document.querySelector('input[value="CAD_USUARIOS"]') || Array.from(document.querySelectorAll('input[type="checkbox"]')).find(i => i.name && i.name.includes('CAD_USUARIOS'));
            if (cb && !cb.checked) cb.click();
        });
        const btnSalvarMat = await page.$('button[type="submit"]');
        if (btnSalvarMat) {
            await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }).catch(() => {}), btnSalvarMat.click()]);
        }

        await login('op.prod');
        await page.goto(`${BASE_URL}/admin_users/form/1`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Redefinir senha'));
            if (btn) btn.click();
        });
        await sleep(400);
        await page.type('#campo-nova_senha', 'NovaSenha123!');
        await page.type('#campo-confirmacao_senha', 'NovaSenha123!');
        const btnSubRedef = await page.$('#modal-redefinir-senha button[type="submit"], form[action*="redefinir_senha"] button[type="submit"]');
        if (btnSubRedef) {
            await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }).catch(() => {}), btnSubRedef.click()]);
        }
        await snap(66, false);

        // Fig 67: SHA-256 informado no cadastro do script
        await login('admin');
        await page.goto(`${BASE_URL}/admin_scripts/form/1`, { waitUntil: 'networkidle0' });
        const dummySha = 'ab'.repeat(32);
        await page.evaluate((val) => {
            const el = document.querySelector('#campo-sha256_informado');
            if (el) el.value = val;
        }, dummySha);
        const btnSalvarScrSha = await page.$('form[action*="/admin_scripts/save"] button[type="submit"]');
        if (btnSalvarScrSha) {
            await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }).catch(() => {}), btnSalvarScrSha.click()]);
        }
        await snap(67, false);

        // Fig 68: Solicitante mascarado para o perfil consulta
        await login('consulta');
        await page.goto(`${BASE_URL}/tickets/detail/17`, { waitUntil: 'networkidle0' });
        await snap(68, false);

        console.log('\n=============================================');
        console.log('FIGURAS 43 A 68 CAPTURADAS COM SUCESSO!');
        console.log('=============================================\n');

    } catch (err) {
        console.error('Erro durante a execucao:', err);
    } finally {
        await browser.close();
    }
})();
