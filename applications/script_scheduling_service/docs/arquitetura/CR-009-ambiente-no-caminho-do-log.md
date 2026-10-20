# CR-009: Pasta do ambiente no topo do caminho do log

| Campo | Valor |
|---|---|
| Status | **Aprovado** em 2026-10-20 pelo responsável pelo produto, ao fim do F8.2. Decisões D1 a D3 com as opções recomendadas |
| Origem | Pedido do responsável pelo produto: separar os logs por ambiente já na primeira pasta de `log_dir`, para que a operação de cada ambiente (produção, homologação…) encontre, guarde e apague os próprios logs sem misturar com os de outro |
| Restrições | Sem dependência nova. Sem mudança de esquema (o GFPR não precisa ser reimplantado) |
| Afeta | README §8.4 (passo 3), §10 (tabela 1, nome reservado), §11.3, §12.1 e §13. `AGENTS.md` §6 e §7. `docs/IMPLANTACAO.md`, `docs/AMBIENTE_DEV.md`. Prompts F8.3, F9.1 e F9.2. Código: `pastas_log`, `executor.abrir_log`, `admin_ambientes_service` |
| Revoga | Os caminhos `log_dir/app/...` e `log_dir/<pasta do script>/...` do CR-005 (D5 e D6) |
| Depende de | CR-005, F8.1 (`executor.abrir_log`) e F8.2 |

---

## 1. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Pasta do ambiente no topo | Todo log fica sob uma pasta de ambiente em `log_dir`. Logs de execução dos scripts: `log_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log`, com o ambiente do ticket **obrigatório**. Logs sem ambiente (os da aplicação: `sss_web`, `sss_scheduler`, `purge`, `init_db`): `log_dir/interno/app/AAAA/MM/DD/HH/MI/<nome_log>_<PID>.log` |
| D2 | `INTERNO` reservado só na aplicação | O cadastro de ambientes recusa o nome `INTERNO` ("O nome INTERNO é reservado aos logs da aplicação. Escolha outro nome."). Sem constraint no banco, para não exigir o ciclo 02→01→99 do GFPR |
| D3 | `interno/app/` | A pasta `app` continua dentro de `interno`, como no CR-005; a regra de nome reservado `app` para scripts fica mantida |

## 2. Regras derivadas

| # | Regra |
|---|---|
| R-a | **Forma da pasta do ambiente** (`pastas_log.pasta_ambiente`): a mesma regra da pasta do script (sem acento, minúsculo, cada sequência fora de `[a-z0-9._-]` vira `_`, sem `.` ou `_` nas pontas). Como o nome do ambiente já é `^[A-Z0-9_]{1,30}$`, na prática é o nome em minúsculo (`PRODUCAO` → `producao`) |
| R-b | **Obrigatório nos scripts:** ambiente vazio, sem caractere aproveitável ou que gere `interno` lança `ValueError` em `pastas_log.diretorio_log_execucao` (e em `executor.abrir_log`); nenhuma pasta é criada e o spawn não acontece (`SPAWN_ERROR` no F8.3) |
| R-c | **Retenção da aplicação** (`limpar_retencao_app`) só olha `log_dir/interno/app/`. O `purge.py` (F9.1) só olha `log_dir/<ambiente>/<pasta>/AAAA/MM/DD/HH/MI` e nunca entra em `log_dir/interno/` |
| R-d | **Migração:** nada é movido. A pasta antiga `log_dir/app/` não é mais limpa pela retenção e deve ser apagada à mão depois da atualização (`docs/IMPLANTACAO.md` §16). Ainda não há logs de execução em produção (o agente nasce no F8.3) |
