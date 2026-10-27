# CR-029: `instance/` só com os processos

| Campo | Valor |
|---|---|
| Status | **Encerrado** em 2026-10-27 |
| Origem | Pedido do responsável pelo produto, depois do CR-028: os arquivos do formato único em `instance/` (`config.ini`, `config.ini.example`, `secrets.cfg`, `secrets.cfg.example`, `web.env`, `.gitkeep`) continuam? |
| Restrições | Python 3.6.0 a 3.13; sem dependência nova; sem mudança de banco; o formato único continua aceito por `--config` |
| Afeta | `sss_config` (`config_path`, `get_config`, `processes`, `app.config_path`), comandos de `src/sss/cli/`, `db_conn` (sondagem), `bin/sss-stop.sh`, `bin/sss-update.sh`, `bin/start_local.sh`, `Makefile` (`package-local`), suporte dos testes Oracle, README, DEPLOYMENT, DEV_ENVIRONMENT, AGENTS |

## 1. Decisões

| # | Decisão |
|---|---|
| D1 | Opção A: sem `--name` nem `--config`, todo comando sai com código 2 e lista os processos de `instance/` (sem os modelos de `exemplos/`). Não há config padrão |
| D2 | Opção C: a bateria Oracle lê config e segredos de `instance/agente0001/`; no DEV, o `secrets.cfg` dele recebe `[web] cookie_key` (o mesmo do web0001) para conectar também como web. Recusadas: A (pasta `instance/testes/` só para os testes) e B (juntar os segredos num arquivo temporário a cada execução). A subida do agente no DEV avisa que `[web]` não é do papel dele |

## 2. O que mudou

* `instance/` fica com `exemplos/` (no git e no pacote) e um `<nome>/` por processo (fora do git). Saíram `config.ini`, `secrets.cfg` (apagados do DEV, com cópia de segurança), `config.ini.example` e `secrets.cfg.example` (movidos para `tests/support/`, só para os testes) e `.gitkeep`. O `web.env` do DEV foi para `instance/web0001/web.env`.
* `init_db`, `generate_sql` e `check_env` ganharam `--name`. O `generate_sql` continua rodando só com `--owner` e `--prefix`.
* A sondagem do driver recebe o config do próprio processo (`app.config_path`). Antes ela procurava um atributo que não existia e lia sempre o `instance/config.ini`, o que só funcionava porque o `[oracle]` dos três arquivos do DEV era igual.
* A bateria Oracle lê `instance/agente0001/` (config e segredos, D2).
* `make package-local` copia de `instance/` só `exemplos/`: os `instance/<nome>/secrets.cfg` reais nunca são copiados.
* `sss-update.sh` troca só `instance/exemplos/`.
