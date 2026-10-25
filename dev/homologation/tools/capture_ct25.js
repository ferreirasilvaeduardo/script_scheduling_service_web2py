/**
 * capture_ct25.js
 * Captura as figuras 66, 67 e 68 (CT-25).
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
    console.log('Iniciando captura das figuras 66, 67 e 68 (CT-25)...');
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

    async function snap(num, fullPage = false) {
        const dest = path.join(OUT_DIR, `image${num}.png`);
        await page.screenshot({ path: dest, fullPage });
        console.log(`[OK] Figura ${num} salva -> image${num}.png (fullPage=${fullPage})`);
    }

    async function login(user, pass = PASS_SEED) {
        await page.goto(`${BASE_URL}/default/login`, { waitUntil: 'networkidle0' });
        const outroUser = await page.$('form[action*="/default/logout"]');
        if (outroUser) {
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle0' }),
                outroUser.evaluate(f => f.submit())
            ]);
        }
        await page.goto(`${BASE_URL}/default/login`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            document.querySelector('#field-login').value = '';
            document.querySelector('#field-password').value = '';
        });
        await page.type('#field-login', user);
        await page.type('#field-password', pass);
        await Promise.all([
            page.waitForNavigation({ waitUntil: 'networkidle0' }),
            page.click('button[type="submit"]')
        ]);
    }

    try {
        // ==========================================
        // CT-25 — Correções da auditoria final
        // ==========================================
        console.log('\n--- CT-25 (Fig 66 a 68) ---');
        // 1. Como admin, dar CAD_USUARIOS ao OPERADOR_PROD
        await login('admin');
        await page.goto(`${BASE_URL}/admin_profiles/matrix/2?aba=funcionalidades`, { waitUntil: 'networkidle0' });
        await page.evaluate(() => {
            const cb = document.querySelector('input[value="CAD_USUARIOS"]') || Array.from(document.querySelectorAll('input[type="checkbox"]')).find(i => i.name && i.name.includes('CAD_USUARIOS'));
            if (cb && !cb.checked) cb.click();
        });
        const btnSalvarMat = await page.$('form[action*="/admin_profiles/matriz_salvar"] button[type="submit"]');
        if (btnSalvarMat) {
            await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), btnSalvarMat.click()]);
        }

        // 2. Login como op.prod e tentar redefinir senha do admin (id 1)
        await login('op.prod');
        await page.goto(`${BASE_URL}/admin_users/form/1`, { waitUntil: 'networkidle0' });
        
        // Preencher senha e confirmacao
        await page.evaluate(() => {
            const s = document.querySelector('input[name="password"]');
            const c = document.querySelector('input[name="confirmation"]');
            if (s) s.value = 'NovaSenha123!';
            if (c) c.value = 'NovaSenha123!';
        });

        // Submeter redefinicao
        const formRedef = await page.$('form[action*="/admin_users/reset_password"]');
        if (formRedef) {
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle0' }),
                formRedef.evaluate(f => f.submit())
            ]);
        }
        await snap(66, false);

        // 3. Fig 67: SHA-256 informado no cadastro do script
        await login('admin');
        await page.goto(`${BASE_URL}/admin_scripts/form/1`, { waitUntil: 'networkidle0' });
        const dummySha = 'ab'.repeat(32);
        await page.evaluate((val) => {
            const el = document.querySelector('#field-sha256_informado');
            if (el) el.value = val;
        }, dummySha);
        const formSalvarScr = await page.$('form[action*="/admin_scripts/save"]');
        if (formSalvarScr) {
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle0' }),
                formSalvarScr.evaluate(f => f.submit())
            ]);
        }
        await snap(67, false);

        // 4. Fig 68: Solicitante mascarado para o perfil consulta
        await login('consulta');
        await page.goto(`${BASE_URL}/tickets/detail/17`, { waitUntil: 'networkidle0' });
        await snap(68, false);

        console.log('\n=============================================');
        console.log('FIGURAS 66, 67 E 68 CAPTURADAS COM SUCESSO!');
        console.log('=============================================\n');

    } catch (err) {
        console.error('Erro durante a execucao:', err);
    } finally {
        await browser.close();
    }
})();
