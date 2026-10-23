# CR-019: Pasta de trabalho do script

| Campo | Valor |
|---|---|
| Status | **Em andamento.** Aprovado pelo responsável pelo produto em 2026-10-23. 019a e 019b concluídos |
| Origem | Pedido do responsável pelo produto (2026-10-23): repassar ao script uma pasta "work" com a mesma estrutura da pasta de saída |
| Restrições | Sem dependência nova. Python 3.6. Sem mudança de esquema nem de tela |
| Afeta | README §8.0, §8.4, §8.5, §8.6, §8.12, §8.15 (nova), §11.3, §12.1. `AGENTS.md` §3.4, §7 e §8. `DEPLOYMENT.md`. Código: `sss_config`, `log_paths`, `env_builder`, `executor`, `os_platform`, `scheduler_loop`, `bin/sss-helper`, `scripts/purge.py` |

---

## 1. Problema

O script não recebe nenhuma variável com uma pasta de trabalho organizada. O `HOME` e o `cwd` ficam numa pasta por ticket que é apagada no fim da execução, e o `work_dir` do agente não pode ser entregue ao script: ele guarda o estado local de cada ticket (`.sss_spawn`, `.sss_proc`, `.sss_result`, log parcial, `output.zip`), e um script com escrita ali poderia adulterar o resultado do próprio ticket.

## 2. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Base própria | `[agent] script_work_dir`, separada do `work_dir`; vazia desliga. Sem sobreposição com `log_dir`, `work_dir`, `exec_work_dir`, `output_dir` e `input_dir` |
| D2 | Estrutura da saída | `script_work_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>/` (`log_paths.script_work_dir`) |
| D3 | Só a variável | `SSS_WORK_DIR`. `HOME`, `cwd` e `TMPDIR` continuam na pasta descartável (§8.4, passo 2); a limpeza do fim do ticket e o startup check não mudam |
| D4 | Fica no disco | Nada no fim do ticket; o `purge.py` remove as pastas de minuto depois de `[logging] script_work_retention_days` (1 a 365, padrão 7), pelo `purge-output` do helper |
| D5 | Criação | Fora de DEV, pelo helper `run` (campo `work`), como o usuário de execução, `0700` nível a nível, sem seguir link; em DEV sem usuário de execução, pelo agente (`os_platform.create_script_work_dir`). Falha impede a execução, como na saída |
| D6 | Fora do escopo | Trava de espaço livre (a saída tem `DISCO_SAIDA`) e qualquer mudança de tela |

## 3. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 019a | D1, D2, D3, D5: config, caminho, variável, criação (helper e DEV), conferência na subida, `SSS_DIR`, README, AGENTS, DEPLOYMENT e testes | Concluído |
| 019b | D4: alvo `script_work` do `purge.py` (mesmo `purge-output` do helper), README §8.0, §8.15, §11.3 e §14, AGENTS, DEPLOYMENT (alvo do purge e helper novo na atualização, §18) | Concluído |
| 019c | Ensaio real no DEV: chave ligada, ticket real gravando em `SSS_WORK_DIR`, `purge.py --dry-run`, bateria completa | Pendente |
