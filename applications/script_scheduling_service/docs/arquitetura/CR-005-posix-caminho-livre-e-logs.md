# CR-005: Somente POSIX, caminho livre do script e pastas de log por minuto

| Campo | Valor |
|---|---|
| Status | **Aprovado** em 2026-10-16 pelo responsável pelo produto: D1 a D7 e o plano R0 a R5 + UF, "seguir em sequência". Revisão no R2 (mesma data): D8 substitui a R-f e a CK de `plataforma` ganha texto único (R-h). **Implementado** em 2026-10-16 (R0 a R5), com as correções da auditoria pós-R5 (R0b, R4b, R4c, R5b), e fechamento UF concluído no mesmo dia: 718 testes OK em Python 3.6.0, 3.6.8 e 3.13.2, 24 telas sem rolagem horizontal nas cinco larguras, manual de homologação v2.1 e pacote `fe5884c` ensaiado para o 3067 (`docs/IMPLANTACAO.md` §22.6) |
| Origem | Pedido do responsável pelo produto após o fechamento do CR-004: arquitetura só POSIX, script cadastrado em qualquer lugar do servidor e padrão fixo de pastas para os logs |
| Restrições | Sem dependência nova. Nenhuma mudança na pilha (Python 3.6+, web2py, Oracle 11gR2, Alpine CSP) |
| Afeta | README §2.3, §2.6, §3.1, §3.2, §4.1, §5.4, §5.6, §6.4, §6.5, §8.0, §8.1, §8.2, §8.4, §8.5, §8.6, §8.10, §8.11, §8.12, §10 (tabelas `tbsss_scripts` e `tbsss_agentes`), §11.3, §12.1, §12.2, §13 e §14. `AGENTS.md`. `docs/IMPLANTACAO.md`, `docs/AMBIENTE_DEV.md`. Prompts F7 a F9. Manual de homologação |
| Revoga | **CR-001**, na parte Windows: plataforma Windows, interpretador `POWERSHELL`, SIDs, ACL, Job Object, launchers `.ps1`. **CR-003, D16** (várias pastas base): saem `pasta_base`, `base_script_dirs` e o snapshot v3 |
| Contrato | `tbsss_scripts`: sai `pasta_base`; `path_file` passa a ser absoluto (`VARCHAR2(500 CHAR)`). `tbsss_agentes`: sai `pastas_base`; `plataforma` só `LINUX` ou `UNIX`. Snapshot v4. `[agent] base_script_dirs` e `script_owner_sids` saem; `[logging] app_log_backups` vira `app_log_retention_days` |
| Depende de | CR-003 e CR-004 concluídos. O F7 (Oracle) e o F8 (agente) ainda não foram executados, então não há dado de produção a migrar |

---

## 1. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Somente POSIX | Nó web e agente só em Linux (nível 1) e demais Unix (nível 2). A camada `modules/plataforma/` continua, só com a implementação POSIX, para isolar as primitivas de sistema operacional e permitir os testes |
| D2 | Caminho absoluto em qualquer lugar | O cadastro grava `path_file` absoluto (ex.: `/opt/automacoes/scripts/carga.py`). Sem pastas base. Snapshot v4 com o caminho absoluto |
| D3 | Checagens do caminho | Dono do arquivo em `script_owner_uids`; o arquivo e **cada diretório até `/`** sem escrita para grupo, outros ou o UID do agente (diretórios ancestrais podem pertencer ao root ou a um UID de `script_owner_uids`). Recusa as pastas do sistema: `/bin`, `/sbin`, `/usr`, `/lib`, `/lib32`, `/lib64`, `/libx32`, `/etc`, `/boot`, `/proc`, `/sys`, `/dev` e `/root`. Recusa também caminho dentro de `log_dir` ou `work_dir` |
| D4 | Existência no nó web | Se o arquivo existe no servidor web, as checagens da D3 rodam na hora e bloqueiam. Se não existe ali, o cadastro e o disparo seguem com aviso, e o agente confere no claim |
| D5 | Log de cada execução | `log_dir/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log`, com a data e a hora do início da execução (`started_at`, relógio do banco) e o PID do processo do script |
| D6 | Logs da aplicação | `log_dir/app/AAAA/MM/DD/HH/MI/<nome_log>_<PID>.log`. O arquivo nasce na pasta do minuto em que o processo sobe. Ao atingir `app_log_max_bytes`, abre um arquivo novo na pasta do minuto atual. A retenção é por dias (`app_log_retention_days`) |
| D7 | Nome reservado | Nenhum script pode ter a pasta de log `app`, para não colidir com os logs da aplicação |
| D8 | Caminho visível a todos | O caminho completo do script (`path_file`) aparece para todos que já veem o script ou o ticket: cadastro, prévia do comando, disparo e detalhe do ticket. Substitui a R-f |

## 2. Regras derivadas (detalhe técnico das decisões)

| # | Regra | Motivo |
|---|---|---|
| R-a | **Pasta do script no log:** a forma segura do nome do script: sem acento (NFKD → ASCII), minúsculo, cada sequência de caracteres fora de `[a-z0-9._-]` vira um `_`, sem `.` ou `_` nas pontas; vazio vira `script_<id>`. Ex.: "Carga Diária" → `carga_diaria`. A função fica em `modules/pastas_log.py` e é a mesma no web e no agente | O nome do script é texto livre (CR-003) e pode ter espaço, acento ou `/` |
| R-b | **PID no nome do log:** o agente abre o log antes do spawn como `ticket_<id>.log.parcial` (`O_EXCL`, `0600`) e, logo depois do `Popen`, renomeia para `ticket_<id>_<PID>.log` no mesmo diretório (renome atômico no POSIX; o descritor continua válido). Se o spawn falhar (`SPAWN_ERROR`), o arquivo vira `ticket_<id>_0.log` | O PID só existe depois do spawn, mas a saída precisa de um arquivo aberto antes |
| R-c | **Rotação do log da aplicação:** se o arquivo novo cair no mesmo minuto e no mesmo PID de um já existente, ganha o sufixo `_<n>` (`sss_web_4321_2.log`) | Evitar sobrescrever na troca por tamanho dentro do mesmo minuto |
| R-d | **Retenção do log da aplicação:** o próprio processo apaga as pastas `app/AAAA/MM/DD` mais antigas que `app_log_retention_days`, na subida e a cada troca de arquivo. O `purge.py` cuida dos logs de execução (`local_log_retention_days`) e nunca toca em `app/` | O nó web sem agente não roda o `purge.py` |
| R-e | **Relógio das pastas:** log de execução usa `started_at` (relógio do banco, devolvido pelo claim); log da aplicação usa o relógio local do processo, com o `TZ` do launcher | O log de execução casa com o ticket; o da aplicação existe antes de haver banco |
| R-f | ~~Caminho do servidor só para admin~~ **Revogada pela D8.** O caminho completo aparece para todos | O próprio campo `path_file` do cadastro já é o caminho completo, e quem tem `CAD_SCRIPTS` sem ser admin precisa vê-lo para editar |
| R-g | **Formato de `path_file`:** absoluto, normalizado (`os.path.normpath(p) == p`), sem `..`, `\`, `//`, barra final ou caractere de controle, até 500 caracteres. CK `ck_tbsss_scr_path`: `SUBSTR(path_file, 1, 1) = '/' AND INSTR(path_file, '..') = 0 AND INSTR(path_file, '//') = 0 AND INSTR(path_file, '\') = 0` | Defesa em profundidade, como no CR-003 |
| R-h | **CK de `plataforma`:** `ck_tbsss_agt_plat (plataforma IS NULL OR plataforma IN ('LINUX','UNIX'))`, com o mesmo texto no README e no `sql_ident`. A coluna aceita nulo, e o `IS NULL` explícito segue o padrão das demais CKs de coluna opcional | README e código tinham textos diferentes (mesmo efeito no Oracle) |

## 3. Riscos

| Risco | Mitigação |
|---|---|
| Com o caminho livre, a barreira passa a ser dono e permissão. Se `script_owner_uids` incluir o root (0), qualquer arquivo de software de terceiros que pertença ao root, fora das pastas do sistema, vira candidato a script | Pastas do sistema bloqueadas (D3); interpretador obrigatório da allowlist; cadastro só com `CAD_SCRIPTS` e auditado. Recomendação de implantação: um UID dono dedicado aos scripts em `script_owner_uids`, sem o 0 |
| Muitas pastas por minuto em `log_dir` | Uma pasta por minuto só quando há execução ou subida; retenção por dias nos dois tipos de log |

## 4. Plano de execução

Cada passo segue o fluxo do projeto: implementação, testes (3.6.0, 3.6.8 e 3.13.2), validação no navegador quando houver tela, relatório AGENTS §9, commit e push.

| Passo | Escopo | Testes principais |
|---|---|---|
| R0 | Este documento; README, AGENTS, IMPLANTACAO e AMBIENTE_DEV com as decisões | Suíte completa (sem código novo) |
| R1 | D1: `POWERSHELL` sai da allowlist, das CKs e dos rótulos; plataforma só `LINUX`/`UNIX`; sai `plataforma_local` | `test_path_guard.py`, `test_params_compiler.py`, `test_admin_scripts_service.py`, `test_db_schema.py` |
| R2 | D2, D3, D4, D7, D8, R-g, R-h: `path_guard` (caminho absoluto, cadeia até `/`, pastas do sistema), `sss_config` sem `base_script_dirs`, `sql_ident` (colunas e CKs), snapshot v4, cadastro e detalhe, seed, contratos e FAKE | `test_path_guard.py`, `test_admin_scripts_service.py`, `test_params_compiler.py`, `test_ticket_service.py`, `test_repo_contract.py`, `test_seed_fake.py`, `test_sss_config.py` |
| R3 | D5, R-a, R-b: `modules/pastas_log.py` (pasta do script e caminho do log de execução), usado pelo cadastro (D7) e pelo agente no F8 | Novo `test_pastas_log.py` |
| R4 | D6, R-c, R-d, R-e: `sss_logging` com o padrão `app/AAAA/MM/DD/HH/MI/<nome_log>_<PID>.log`, troca por tamanho e retenção; `[logging] app_log_retention_days` | `test_sss_logging.py`, `test_sss_config.py` |
| R5 | Prompts F7 a F9, índice e manual de homologação (Gestão de Scripts, detalhe do ticket e figuras) | Suíte completa e capturas |
| UF | Fechamento: bateria completa, telas nas cinco larguras, documentação de homologação e git | Suíte completa e roteiro manual |
