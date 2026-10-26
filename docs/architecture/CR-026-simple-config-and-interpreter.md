# CR-026: Config simplificado e interpretador só no cadastro

| Campo | Valor |
|---|---|
| Status | **Em andamento**. Proposta e decisões do responsável pelo produto em 2026-10-26 ("quero simplificar config") |
| Origem | O `[agent] interpreters` era obrigatório em todo agente, quase sempre igual, e um caminho errado (mesmo de um tipo que ninguém usa) impedia a subida; mais de 30 chaves de ajuste fino do `config.ini` eram obrigatórias sem precisar |
| Restrições | Sem dependência nova (AGENTS §2.2). Python 3.6.0 a 3.13. Esquema na versão 1, ainda aberta (AGENTS §4.16): muda sem migração; tabelas do DEV recriadas a pedido do responsável; `ALTER` documentado no DEPLOYMENT §18 |
| Afeta | README §5, §6.4, §6.5, §8.4, §8.5, §8.6, §8.12, §10, §12, §13; AGENTS §3.2, §7; DEPLOYMENT §7, §9, §15, §18, §19; `sss_config`, `path_guard`, `params_compiler`, `scheduler_loop`, `executor`, repositórios, cadastro de scripts, disparo, detalhe do ticket, painel de agentes |

---

## 1. Decisões

| # | Decisão |
|---|---|
| D1 | A linha `[agent] interpreters` sai do `config.ini`. Uma linha antiga gera aviso no log e é ignorada (a subida segue) |
| D2 | Sai a coluna `tbsss_agents.interpreters`; o agente pega os tickets só pelo ambiente (qualquer interpretador) |
| D3 | `tbsss_scripts.interpreter` obrigatório, `VARCHAR2(100 CHAR)`, só `python`, `python3`, `sh` ou `bash` (CK `ck_tbsss_scr_int`); saem as seis opções do CR-025 |
| D4 | O interpretador digitado no disparo é gravado em `tbsss_tickets.interpreter_path` (e continua no snapshot e na auditoria do disparo) |
| D5 | Na execução, nesta ordem: o `#!` da primeira linha do script, se o executável existir no servidor; senão o informado no disparo; senão o do cadastro, procurado no `PATH` do agente. Nenhum existe: `PRECHECK_FAILED` com `INTERPRETER_NOT_FOUND`. `#!` que aponta para executável inexistente é ignorado, com a linha `[SSS] #! ignorado: ...` no log do ticket (inverte o CR-025, em que o digitado vencia o `#!`) |
| D6 | Coluna nova `tbsss_tickets.interpreter_used` (`VARCHAR2(1000 CHAR)`): o caminho executado, gravado pelo agente junto com o PID; o log do ticket abre com `[SSS] interpretador usado: ...` |
| D7 | O `python3` do cadastro roda com `-I`; os demais Python (o `python` do cadastro, o do `#!` e o digitado, reconhecidos pelo nome `python`, `python3`, `python3.13`...) com `-E -s`, depois do argumento do `#!`; shell sem opções extras |
| D8 | Cerca de 35 chaves de ajuste fino passam a ser opcionais, com o valor do `config.ini.example` como padrão |
| D9 | Sem a linha `secrets_file` (ou sem a seção `[secrets]`), vale o `secrets.cfg` da pasta do `config.ini` |
| D10 | Tabelas do DEV recriadas (rollback do SSS + `init_db`): os dados de teste são apagados e o admin volta à senha do seed |
| D12 | `scripts/prepare_dirs.py` (pedido do responsável em 2026-10-26): lê o `config.ini` e **aplica direto** (como root) as pastas com o dono e o modo da implantação, inclusive `script_base_dir`; usuário do serviço `sss` por padrão (`--service-user`); `--dry-run` só mostra. A pasta existente tem dono e modo ajustados; nada é apagado; usuário inexistente para antes de criar qualquer pasta |
| D11 | Snapshot versão 7 (o `interpreter` guarda o nome do cadastro). O agente aceita v5 e v6 pendentes, traduzindo a chave anterior (`PYTHON3` → `python3`, `PYTHON` → `python`, `BASH` → `bash`, `SH` → `sh`, `PYTHON_SCRIPT` → `python3`, `SHELL_SCRIPT` → `sh`); um agente anterior recusa a v7 (`UNSUPPORTED_VERSION`) |

## 2. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 026a | Config (D1, D8, D9), agente e banco (D2 a D7, D11), telas (cadastro com os quatro nomes, ajuda do disparo, detalhe com cadastrado, informado e usado, painel de agentes sem interpretadores), `docs/sql` regenerados, tabelas do DEV recriadas (D10). Os passos 026a a 026c do plano foram juntados a pedido do responsável. Validação: suíte de 1518 testes em 3.6.0, 3.6.8 e 3.13.2; bateria Oracle (1516, com o banco recriado: esquema 100% compatível); `make lint` e `make type-check` com zero achados; subida real do agente no DEV sem `interpreters`. As telas e a execução real ficam para a homologação do 026d. Achados no caminho: a variável `SSS_INTERPRETER` do script passa a trazer o nome do cadastro (`python3`), e o README §4.1 chama de "cifrado" o cookie de sessão, que é só assinado (a corrigir no 026d) | Concluído |
| 026d | Documentação: README §12.1 com o config mínimo, a tabela de todas as chaves (obrigatória, padrão e faixa; conferida contra o `SCHEMA` por teste) e a regra das pastas que o SSS não cria; README §5, §6.4, §6.5, §8.4, §8.5, §8.6, §8.12, §10, §13, §14 e o cookie de sessão (assinado, não cifrado); `config.ini.example` enxuto, com os opcionais comentados e o padrão ao lado; DEPLOYMENT §7.1, §9, §15, §18 (os `ALTER` e o retorno) e §19; DEV_ENVIRONMENT; AGENTS. Seed do FAKE: o `agt-host01` atende só `PRODUCAO`, para o quadro da fila sem atendente continuar demonstrável. Homologação real r4 329/329 (`docs/homologation/SSS_Homologation_Evidence_2026-10-26_r4.docx`), com o CT-32 refeito; a r3 ficou incompleta porque a massa de teste da raiz não existia mais e o `config.ini` do DEV tinha outro `agent_id` e pastas em `dev/`: o roteiro passou a ler o config e a massa passou a ser gerada por `tools/gerar_massa.py` | Concluído |
| 026e | `scripts/prepare_dirs.py` (D12): plano a partir do `config.ini`, `--dry-run`, aplicação como root (fora de DEV, exigido), usuário inexistente sem criar nada, pasta existente com dono e modo ajustados, arquivo ou link no lugar da pasta recusados; testes em `test_prepare_dirs.py`; README §12.1 e DEPLOYMENT §8 | Concluído |
| 026f | Validação da documentação contra o código (revisão independente, inclusive do `prepare_dirs.py`) e encerramento | Pendente |

## 3. Riscos

* Os do CR-025 continuam (README §8.5 e §14): quem dispara escolhe o executável; versão errada; `#!` sob controle de quem edita o script.
* **Servidor sem o interpretador:** o agente não filtra mais pelo interpretador; um ticket de `bash` num servidor sem `bash` termina em `PRECHECK_FAILED` (`INTERPRETER_NOT_FOUND`) em vez de esperar outro agente.
* **O operador não troca um `#!` válido:** com `#!` existente, o digitado no disparo é ignorado (D5).
