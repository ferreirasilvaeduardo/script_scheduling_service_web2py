# SSS — Prompt F0.2: Configuração tipada, logging e launchers

## Leitura obrigatória antes de planejar
- `AGENTS.md` (inteiro, com atenção a §3.3 e §6)
- `README.md` §2.3, §2.5, §4.1, §8.9 (invariantes), §8.12 (passo 2), §12 (inteiro), §13

## Objetivo
Carregar e validar o `config.ini` e o `secrets.cfg` de forma tipada e fail-fast, configurar o logging padronizado e criar os launchers.

## Escopo
**IN**
- `applications/script_scheduling_service/modules/sss_config.py`:
  - **Esquema declarativo** de todas as seções e chaves do README §12.1, incluindo `[app]`. Cada chave declara tipo (`str`, `int`, `bool`, `enum`, `list_csv`, `path`), obrigatoriedade, faixa mínima/máxima e enum permitido.
  - `carregar(caminho_ini) -> Config`, um objeto imutável (namedtuple aninhado ou classe com `__slots__`; **sem dataclasses**).
  - Rejeição de chave desconhecida, ausente, com tipo inválido ou fora da faixa. A exceção é `ConfigErro`, com seção, chave e motivo.
  - **Invariantes:**
    - `max_parallel_jobs <= max_parallel_hard_limit`;
    - `fence_timeout_s * 2 <= node_offline_timeout_s`;
    - `heartbeat_interval_s * 3 <= fence_timeout_s`;
    - `data_backend == FAKE` exige `sss_env == DEV`.
  - **Regex:** `owner` com `^[A-Za-z][A-Za-z0-9_]{0,29}$`, `table_prefix` com `^[a-zA-Z0-9_]{1,8}$` (histórico; vigente: `^[a-z][a-z0-9_]{0,7}$`, só minúsculas, CR-007 R-31 e CR-008 R-28, README §12.1) e `agent_id` com `^[A-Za-z0-9._-]{1,30}$`.
  - `env_passthrough` contendo variável bloqueada (README §8.6) gera `ConfigErro`.
  - `carregar_segredos(caminho) -> Segredos`:
    - valida arquivo regular, dono igual a `os.geteuid()` e `mode & 0o077 == 0`;
    - retorna o acesso a `[oracle] password`, `[web] cookie_key` e `[ambiente:<NOME>]`;
    - `repr()` e `str()` do objeto **nunca** exibem valores.
  - Em `sss_env = DEV` e `data_backend = FAKE`, o `secrets.cfg` é opcional **somente** para `[oracle]`. O `cookie_key` continua obrigatório.
- `applications/script_scheduling_service/modules/sss_logging.py`: `configurar(nome_log, cfg)` cria um `RotatingFileHandler` em `log_dir` com o formato do README §13 (campos `agente`, `ticket` e `acao` via `logging.LoggerAdapter` ou `Filter`, com default `-`), aplica o nível do config e cria `log_dir` se não existir (com permissão `0o750`).
- `applications/script_scheduling_service/instance/config.ini.example` (cópia fiel do README §12.1) e `applications/script_scheduling_service/instance/secrets.cfg.example` com valores **placeholder** (`CHANGE_ME`), nunca reais.
- `bin/sss-web.sh` e `bin/sss-scheduler.sh` (bash, `set -euo pipefail`):
  - recusam root (`[ "$(id -u)" -eq 0 ]`);
  - aplicam `umask 077`;
  - exportam `LD_LIBRARY_PATH` a partir de `SSS_IC_DIR` quando definido, e `TZ` se `SSS_TZ` estiver definido;
  - fazem `exec` do comando web2py (README §3.1).
- `applications/script_scheduling_service/scripts/test_config.py` (unittest).

**OUT**
- Não abrir conexão com banco.
- Não criar `models/` (isso é o F1.1).

## Requisitos
1. Nenhum segredo em código, testes ou fixtures. Os testes criam `secrets.cfg` temporário com valores aleatórios (`secrets.token_hex`) em `tempfile.mkdtemp()`.
2. As mensagens de `ConfigErro` nunca incluem valor de segredo.
3. Python 3.6 estrito, apenas `configparser` da stdlib, com `interpolation=None`.

## Critérios de aceite
- [ ] `test_config.py` cobre:
  - config válido;
  - chave ausente;
  - chave desconhecida;
  - tipo inválido;
  - fora da faixa;
  - cada invariante;
  - FAKE com HML;
  - prefixo de 9 caracteres;
  - `env_passthrough` com `LD_PRELOAD`;
  - `secrets.cfg` com modo `0644`;
  - `repr(segredos)` sem valores.
- [ ] Os launchers passam em `bash -n`.
- [ ] Uma linha de log gerada no teste segue o formato do README §13.

## Verificação
- `python -m unittest discover -s scripts -p "test_config.py"`
- `bash -n ../../bin/sss-web.sh && bash -n ../../bin/sss-scheduler.sh`

## Regras de parada
Se alguma chave do README §12.1 tiver tipo ou faixa ambíguos, **pare** e liste a chave.

## Saída
Relatório AGENTS.md §9.
