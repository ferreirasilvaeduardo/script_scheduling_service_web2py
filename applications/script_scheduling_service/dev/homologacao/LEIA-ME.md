# Ferramentas do manual de homologação (somente DEV)

Geram e conferem as figuras do `docs/homologacao/SSS_Manual_Homologacao_UI_Freeze.docx` (UI Freeze, 2026-10-18). Ficam em `dev/`, fora do pacote de implantação (README §12.2).

| Arquivo | Uso |
|---|---|
| `ferramentas/capture_all_screens.js` | Executa os 25 casos de teste (CT-01 a CT-25) no navegador (Puppeteer) e grava as 68 telas em `telas/` |
| `ferramentas/capture_remaining.js`, `ferramentas/capture_ct25.js` | Recapturam só as figuras que faltaram ou só as do CT-25 |
| `ferramentas/test_step.js`, `ferramentas/test_step2.js` | Depuração de um passo isolado (login e formulário de ambientes) |
| `ferramentas/update_docx_images.py` | Troca as figuras do `.docx` pelas de `telas/` (cria um `.bak` antes) |
| `ferramentas/verify_docx_images.py` | Lista as figuras do `.docx` com as dimensões |
| `all_cts_steps.txt`, `all_figures.txt` | Texto dos casos de teste e mapa figura → imagem, extraídos do manual |
| `telas/` | As 68 capturas (`image<n>.png`); não versionadas, porque já estão dentro do `.docx` |

Uso, com o servidor de DEV em `http://127.0.0.1:8000`:

```bash
cd dev/homologacao/ferramentas
read -s -p "Senha do admin do DEV: " SSS_HOMOLOG_PASSWORD && export SSS_HOMOLOG_PASSWORD && echo
node capture_all_screens.js
python3 update_docx_images.py && python3 verify_docx_images.py
```

A senha nunca fica no código: sem `SSS_HOMOLOG_PASSWORD`, os scripts param com código 2. O caminho do Chrome do Puppeteer está fixo nos `.js` (`executablePath`); ajuste-o na sua máquina.
