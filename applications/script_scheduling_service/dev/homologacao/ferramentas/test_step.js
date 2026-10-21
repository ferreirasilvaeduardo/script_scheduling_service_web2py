const puppeteer = require('puppeteer');
// Senha do admin do DEV: so pela variavel SSS_HOMOLOG_SENHA, nunca no codigo.
if (!process.env.SSS_HOMOLOG_SENHA) { console.error('Defina SSS_HOMOLOG_SENHA.'); process.exit(2); }

(async () => {
    const browser = await puppeteer.launch({
        executablePath: '/home/eduardof/.cache/puppeteer/chrome/linux-131.0.6778.204/chrome-linux64/chrome',
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    const page = await browser.newPage();
    
    // Login admin
    await page.goto('http://127.0.0.1:8000/script_scheduling_service/default/login', { waitUntil: 'networkidle0' });
    await page.type('#campo-login', 'admin');
    await page.type('#campo-senha', process.env.SSS_HOMOLOG_SENHA);
    await Promise.all([
        page.waitForNavigation({ waitUntil: 'networkidle0' }),
        page.click('button[type="submit"]')
    ]);
    console.log('1. Logged in, url:', page.url());

    // Ir para admin_ambientes/form
    await page.goto('http://127.0.0.1:8000/script_scheduling_service/admin_ambientes/form', { waitUntil: 'networkidle0' });
    console.log('2. In form, url:', page.url());

    // Digitar espacos
    await page.type('#campo-nome', '  QA_01  ');
    await page.type('#campo-descricao', 'Ambiente de teste');
    await Promise.all([
        page.waitForNavigation({ waitUntil: 'networkidle0' }),
        page.click('button[type="submit"]')
    ]);
    console.log('3. After submit, url:', page.url());
    const errText = await page.evaluate(() => {
        const el = document.querySelector('.is-invalid, .invalid-feedback, .alert');
        return el ? el.textContent.trim() : 'NENHUM ERRO ENCONTRADO';
    });
    console.log('3. Error shown:', errText);

    // Ir para admin_ambientes/form/2
    await page.goto('http://127.0.0.1:8000/script_scheduling_service/admin_ambientes/form/2', { waitUntil: 'networkidle0' });
    console.log('4. Next form/2 url:', page.url());

    // Ir para admin_perfis/lista
    await page.goto('http://127.0.0.1:8000/script_scheduling_service/admin_perfis/lista', { waitUntil: 'networkidle0' });
    console.log('5. Perfis lista url:', page.url());

    await browser.close();
})();
