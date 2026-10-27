# CR-030: Sem purge, um usuário só e manutenção pelo cron

| Campo | Valor |
|---|---|
| Status | **Encerrado** em 2026-10-27 |
| Origem | Ambiente super restrito do responsável pelo produto: um usuário de banco e um usuário do sistema operacional para tudo, sem root; só DEV e PROD (sem HOM). Pedido: retirar todo o processo de purge, de banco e de arquivo, e documentar a limpeza no README |
| Restrições | Python 3.6.0 a 3.13; sem dependência nova; esquema continua na versão 1 (AGENTS §4.16) |
| Afeta | `sss_config`, `sss_logging`, `log_paths`, `db_conn`, `ddl_builder`, `sql_ident`, `health.py`, `generate_sql`, `init_db`, `posix`/`os_platform`, `bin/sss-helper`, `bin/sss-update.sh`, `bin/sss-keepalive.sh` (novo), `tools/package.py`, testes, README, DEPLOYMENT, DEV_ENVIRONMENT, AGENTS |

## 1. Decisões

| # | Decisão |
|---|---|
| 1 | Opção B: as colunas `purge_owner` e `purge_lease_until` saem de `tbsss_control` (DDL; `ALTER TABLE ... DROP` para bancos instalados, DEPLOYMENT §18.3; aplicado no DEV). A auditoria antiga com `PURGE` fica, com o rótulo só para exibição |
| 2 | Opção B: sai também a retenção automática do log da aplicação (`app_log_retention_days`). O SSS não apaga nada por idade |
| 3 | Opção A: linhas antigas (`[retention]`, retenções de `[logging]`, `[purge]` dos segredos) ignoradas com aviso; os arquivos atuais (DEV, modelos, exemplos dos testes) limpos |
| P1 | Opção A: com `sss_env = DEV` e sem `[monitor]`, o `health.py` usa a conta do `[oracle]` |
| P2 | `bin/sss-keepalive.sh` para o cron da conta (`@reboot` e a cada 5 minutos), com `--pause`/`--resume`, e a subida manual documentada |
| P3 | Roteiro "instalação com um usuário só" no DEPLOYMENT §4.0 |
| T1 | `[agent] script_timeout_s` com padrão de 168 h (604.800 s) e máximo de 9.999.999 s, o mesmo do `timeout_s` do cadastro (pedido de 2026-10-27). A limpeza manual dos arquivos usa um prazo maior que esse tempo |
| P4 | Sem mudança: os scripts conectam em outros bancos, com usuários próprios (`[environment:<NOME>]`) |

## 2. O que mudou

* Saíram: `scripts/purge.py`, `src/sss/cli/purge.py`, `src/sss/persistence/oracle/purge.py`, o subcomando `purge-output` do helper e `os_platform.purge_output`, o papel `purge` (GRANTs, `db_conn`, segredos), a checagem "nenhum PURGE auditado" e `--purge-days` do `health.py`, e a limpeza das pastas do log da aplicação.
* A limpeza é manual: README §11.3 (SQL em lotes para tickets terminais, auditoria e envios da tela de Entrada; `find` para as pastas de minuto de logs, saídas e pastas de trabalho), com exemplo de cron no DEPLOYMENT §4.0.
* `bin/sss-keepalive.sh <nome>[:<porta>]...` sobe, pelos launchers, o processo que não estiver rodando; log em `var/<nome>/logs/keepalive.log`.
* Documentação sem HOM: `<TIPO>` = `DEV` ou `PROD`.
