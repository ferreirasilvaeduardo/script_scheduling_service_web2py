# UI Freeze: Registro Parcial de Evidências

**Data:** 2026-10-18

**Ambiente:** DEV, backend FAKE, web2py em `127.0.0.1:8000`
**Resultado geral:** PARCIAL; não aprovado para freeze.

Este registro complementa o manual v2.5. O manual DOCX e seu arquivo `.bak` não foram alterados por esta execução. As evidências abaixo foram coletadas diretamente no Chromium; não foram salvas capturas de tela como arquivos.

## Pré-condições

| Verificação | Resultado | Evidência |
|---|---|---|
| Suíte `unittest` | OK | 821 testes executados; 23 ignorados. |
| `scripts/check_env.py` | OK | Python 3.6.0, web2py, Bootstrap e Alpine CSP detectados. |
| `instance/config.ini` | OK para a preparação DEV descrita no manual | Sem `base_script_dirs`/`app_log_backups`; `app_log_retention_days` presente. |
| Relatórios F0.1–F6.1 | PENDENTE | Não localizados no workspace durante a homologação. |
| Aceite final | PENDENTE | Os checklists e campos de aceite de `UI_FREEZE.md` permanecem em branco. |

## Evidências no Chromium

- Login no painel DEV: HTTP 200. Sessões seed de `admin`, `op.prod` e `consulta` foram utilizadas; nenhuma senha foi registrada neste documento.
- Smoke test de 16 rotas GET do mapa: todas responderam HTTP 200, incluindo painel, permissões, catálogo/histórico, disparo, lista/detalhe de tickets, cadastros, regras/agenda e auditoria/agentes.
- Nas rotas verificadas: nenhuma requisição externa e nenhuma violação CSP observada.
- Cabeçalhos da página de login: CSP `default-src 'self'`, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin` e `Cache-Control: no-store`.
- POST sem CSRF: HTTP 403. Formulário de origem opaca (`Origin: null`) com token inválido: HTTP 403.
- GET direto em `/default/logout`: HTTP 405; sessão continuou ativa.
- Detalhe do ticket inexistente: HTTP 404 com mensagem acionável.
- Nas 16 rotas smoke, a página não teve rolagem horizontal nas larguras 360, 414, 768, 1024 e 1440 px (`scrollWidth <= clientWidth`).
- CT-20, painel de agentes: exibidos “Fila sem atendente”, “Rodando sem PID” (pedido #16) e “Configuração divergente”.
- CT-22, tema escuro: detalhe e histórico renderizados com `prefers-color-scheme: dark`; fundo `rgb(15, 17, 21)`, texto `rgb(229, 231, 235)`. O histórico exibiu gráfico SVG, legenda e tabela acessível, sem rolagem horizontal.
- CT-23, quadro Registro: admin viu o solicitante `op.prod` e o ator do agente no ticket #17; `consulta` viu “outra pessoa”, sem o login de terceiros; `op.prod` viu “você”.
- CT-24, regex: `(a|a)*b` e `^(\w|\d)+$` foram recusadas; `^\d+(\.\d{1,2})?$` foi aceita. A regex larga `\w{0,100}\w{0,100}\w{0,100}x` do CT-25 também foi recusada.
- CT-24, sigilo e validação: tentativa de retirar o sigilo de `documento_cliente` foi recusada; recarga confirmou o parâmetro ainda sigiloso. O valor curto `abc` e agendamento para `2028-01-01T12:00` foram recusados; nenhum ticket foi criado.
- CT-24, concorrência/retomada: a segunda pausa de `Execucao Avulsa Carga` retornou “A regra já está pausada.”; regra de responsável inativo mostrou “Será pausada: Responsável inativo.” e a retomada foi recusada com a orientação prevista.
- CT-24, caminho: cadastro de script pelo symlink temporário retornou `CAMINHO_COM_LINK`; o symlink e seu diretório temporário foram removidos.
- CT-25, E1: temporariamente concedido `CAD_USUARIOS` a `OPERADOR_PROD`; o seletor de perfil não ofereceu `ADMINISTRADOR`. Redefinição de senha e desativação de `admin` foram recusadas com a mensagem “Só um administrador…”. A permissão temporária foi removida.
- CT-25, E4: hash `xyz` foi recusado; hash hexadecimal de 64 caracteres foi aceito no cadastro de `carga_diaria` (o valor coincidia com o hash já exibido antes do teste).
- CT-25, E2: em contexto Chromium isolado autenticado como `op.prod`, logout em outra sessão retornou 303; no próximo pedido a sessão isolada voltou ao login com “Seu acesso mudou e a sessão foi encerrada.”

## Pendências

- CT-01 a CT-19 e CT-21 não foram executados integralmente. O smoke test de rotas não substitui os passos funcionais de cada CT. Também não foram completados todos os passos de criação/edição, filtros, exportação, download, teclado e validação de todos os perfis.
- A verificação de origem forjada com `https://exemplo.invalido` e os testes de sigilo em URL, fonte HTML, logs e auditoria ainda precisam ser registrados. O teste de origem opaca acima não substitui aquele caso exato.
- A lista de relatórios F0.1–F6.1 não foi localizada; o aceite final permanece bloqueado até que esses relatórios sejam apresentados ou a lacuna seja resolvida.

## Limpeza e estado do DEV

- Reativado `op.hml`; removido `CAD_USUARIOS` de `OPERADOR_PROD`; retomadas as regras `Execucao Avulsa Carga` e `Fechamento Mensal Dia 1`.
- O parâmetro de teste `ct24_valor` foi desativado, pois a UI não oferece exclusão física. Os registros de auditoria gerados pelos testes permanecem.
- Nenhum ticket foi criado pelos submits inválidos. O ticket #41 já existia antes destes testes e foi preservado; por isso o servidor não foi reiniciado para não descartar estado preexistente do backend FAKE.
- O servidor web2py existente foi mantido em execução. As pontes locais de credencial de uso único foram encerradas.

**Decisão:** continuar homologação manual CT-01–CT-25 e checklist transversal antes de marcar o UI Freeze como aprovado.
