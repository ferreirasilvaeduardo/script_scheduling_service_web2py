# CR-016b: Configuração e operação em inglês

| Campo | Valor |
|---|---|
| Status | **Concluído** em 2026-10-21. Aprovado pelo responsável pelo produto, com o plano de de-para apresentado antes da implementação |
| Origem | Padronização em inglês dos nomes técnicos (CR-016), fase de configuração e operação, depois do CR-016a (banco) |
| Restrições | Sem dependência nova. Python 3.6. Sem mudança de esquema |
| Afeta | `sss_config` (chaves, seções, papel `agent`, recusa com o nome novo), `db_conn`, `ddl_builder` (papéis de GRANT), scripts de operação, `bin/sss-helper` e `plataforma`, `executor`, testes, README (§2.8 nova, §4.1, §8.0, §11.3, §12, §13), `AGENTS.md`, `docs/IMPLANTACAO.md`, `instance/config.ini.example`, ferramentas de `dev/homologacao` |
| Fases seguintes | CR-016c (código: módulos, arquivos e pastas, funções, chaves lógicas), CR-016d (web: controllers, views, URLs, atributos de sessão), CR-016e (pasta de trabalho) |

---

## 1. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Troca direta | Chave ou seção antiga é recusada na subida com o nome novo (`CHAVES_RENOMEADAS`, `SECOES_RENOMEADAS`); nada é aceito com o nome antigo |
| D2 | Papel `agent` | O papel de segredos e de GRANT `agente` passa a `agent` (`--grants-to web=…,agent=…`). A chave de log `agente` e o formato `[agente=…]` ficam para o CR-016c |
| D3 | Scripts de operação | Arquivos renomeados; atributos internos do `argparse` (`dest`) mantidos até o CR-016c |
| D4 | Pastas do DEV | `input/` e `output/` (antes `entrada/` e `saida/`), no singular, como `work/` |
| D5 | Regra geral | README §2.8 e AGENTS §1: nome técnico em inglês; conteúdo, comentários e dados em português |

## 2. `config.ini` e `secrets.cfg`

| Seção | Antes | Depois |
|---|---|---|
| `[oracle]` | `modo_driver` | `driver_mode` |
| `[agent]` | `ambientes_atendidos` | `environments` |
| `[agent]` | `usuarios_execucao` | `exec_users` |
| `[agent]` | `interpretadores` | `interpreters` |
| `[agent]` | `fila_envelhecimento_min` | `queue_aging_min` |
| `[agent]` | `log_dir_min_livre_mb` | `log_dir_min_free_mb` |
| `[web]` | `sessao_max_horas` | `session_max_hours` |
| `[web]` | `login_max_tentativas` | `login_max_attempts` |
| `[web]` | `login_bloqueio_s` | `login_lockout_s` |
| — | `[retencao]` | `[retention]` |
| `secrets.cfg` | `[ambiente:<NOME>]` | `[environment:<NOME>]` |

## 3. Scripts e opções

| Antes | Depois |
|---|---|
| `scripts/saude.py` | `scripts/health.py` |
| `scripts/empacotar.py` | `scripts/package.py` (`--origem` → `--source`, `--saida` → `--out-dir`) |
| `scripts/sondar_driver.py` | `scripts/probe_driver.py` (`--usuario` → `--user`) |
| `scripts/gerar_scripts_sql.py` | `scripts/generate_sql.py` (`--prefixo` → `--prefix`, `--grants-para` → `--grants-to`, `--admin-nome` → `--admin-name`, `--admin-senha-hash` → `--admin-password-hash`, `--stdout implantar/validar` → `deploy/validate`) |
| `purge.py --alvo tickets/auditoria/logs_locais/saida/todos` | `--target tickets/audit/local_logs/output/all` |
| `purge.py --exportar-auditoria` | `--export-audit` |
| `health.py --sem-pid-min`, `--fila-warn`, `--fila-crit`, `--espera-warn-min`, `--espera-crit-min`, `--purge-dias` | `--no-pid-min`, `--queue-warn`, `--queue-crit`, `--wait-warn-min`, `--wait-crit-min`, `--purge-days` |
| perfdata `agentes_saudaveis`, `fila_vencida`, `espera_max_min` | `healthy_agents`, `overdue_queue`, `max_wait_min` |
| `init_db.py --usuario-dono`, `--admin-nome`, `--grants-para`, `--schema-real`, `--gerar-sql` | `--owner-user`, `--admin-name`, `--grants-to`, `--real-schema`, `--generate-sql` |

## 4. Helper (`bin/sss-helper`)

| Antes | Depois |
|---|---|
| `limpar` | `clean` |
| `encerrar-ticket` | `stop-ticket` |
| `empacotar` | `pack` |
| `limpar-saida` | `clean-output` |
| `purgar-saida … [contar]` | `purge-output … [count]` |
| campos do `run`: `pasta_base`, `saida`, `entrada` | `base_dir`, `output`, `input` |

O `sudoers` não muda (a regra libera o helper inteiro). O helper e a aplicação são trocados juntos.

## 5. Outros

* `SSS_HOMOLOG_SENHA` → `SSS_HOMOLOG_PASSWORD` (ferramentas do manual de homologação, `dev/`).
* DEV: `instance/config.ini` e `instance/secrets.cfg` atualizados (só os cabeçalhos das seções de ambiente); pastas `input/` e `output/`.

## 6. Validação

* Suítes em 3.6.0, 3.6.8 e 3.13.2 e bateria Oracle (3.6.15, GFPR).
* Testes novos em `test_config`: chaves e seções renomeadas recusadas com o nome novo, inclusive `[ambiente:X]` no `secrets.cfg`, sem expor o valor.
* Ensaio real: agente com `config.ini` antigo recusado; `health.py` e `purge.py --dry-run --target output` no GFPR; `package.py` gerando o pacote.
