# CR-014: Pasta de entrada do script

| Campo | Valor |
|---|---|
| Status | **Concluído** em 2026-10-21. Aprovado pelo responsável pelo produto, com a estrutura por ambiente, acesso de leitura e gravação e criação sob demanda pelo agente |
| Renomeado | Pelo CR-015a (2026-10-21): `entrada_dir` → `input_dir` e `SSS_ENTRADA_DIR` → `SSS_INPUT_DIR`. O texto abaixo mantém os nomes da época |
| Origem | Pedido do responsável pelo produto: uma pasta de entrada parametrizada, com a estrutura só pelo nome do script (minúsculo e sem espaço), passada ao script por variável de ambiente |
| Restrições | Sem dependência nova. Python 3.6. Sem mudança de esquema |
| Afeta | README §8.0 (helper `run`), §8.4 (passo 3), §8.5 (`PASTA_DO_SSS`), §8.6 (variáveis), §8.12 (passo 4), §8.14 (nova) e §12.1. `AGENTS.md` (regras e testes). `docs/IMPLANTACAO.md`. Código: `sss_config`, `pastas_log`, `env_builder`, `executor`, `plataforma`, `bin/sss-helper` e `scheduler_loop` |
| Revoga | Nada |
| Depende de | CR-009 (pasta do ambiente no topo), CR-012 (pasta de saída, modelo de criação pelo helper) |

---

## 1. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Pasta por ambiente e script | `entrada_dir/<ambiente>/<pasta do script>/`, sem data nem ticket. O nome do script segue a regra das pastas de log (`pastas_log.pasta_script`: minúsculo, sem acento, espaço e especiais viram `_`), com o nome do snapshot. **Por ambiente** (decisão do responsável pelo produto): fora de DEV, cada ambiente roda com um usuário de execução próprio, e a pasta só por script deixaria `PRODUCAO` e `HOMOLOGACAO` vendo os mesmos arquivos |
| D2 | Opcional por agente | `[agent] entrada_dir` vazio desliga o recurso: sem `SSS_ENTRADA_DIR` |
| D3 | Variável | `SSS_ENTRADA_DIR`, com o caminho absoluto da pasta do script |
| D4 | Leitura e gravação | O script lê, grava e apaga na pasta. Ela pertence ao usuário de execução do ambiente (`0700`) |
| D5 | Criação sob demanda | Antes de cada execução, se a pasta do script não existir, ela é criada com `0700`, sem seguir link: pelo helper `run` fora de DEV (campo `entrada` da especificação) e pelo agente em DEV sem usuário de execução. A existente fica como está (modo e conteúdo) |
| D6 | Permanente | O SSS não lê, não limpa, não compacta e não purga nada na pasta de entrada |
| D7 | Implantação | Fora de DEV, o root cria `entrada_dir/<ambiente>/` de cada ambiente atendido, com dono o usuário de execução e `0700`; o agente confere na subida e recusa subir (código 13) se faltar |
| D8 | Pastas do SSS | `entrada_dir` e `saida_dir` passam a contar como pastas do SSS (`PASTA_DO_SSS`) para scripts e interpretadores, porque o usuário de execução grava nelas. **Muda a saída também:** um script já cadastrado dentro do `saida_dir` passa a ser recusado na pré-validação |
| D9 | Concorrência | Dois tickets do mesmo script no mesmo ambiente usam a mesma pasta ao mesmo tempo; a coordenação é do script |

## 2. Configuração

| Seção | Chave | Padrão | Regra |
|---|---|---|---|
| `[agent]` | `entrada_dir` | vazio (desligado) | Absoluto e normalizado; fora das pastas do sistema (conferido na subida); sem sobreposição com `log_dir`, `work_dir`, `exec_work_dir` e `saida_dir` |

## 3. Validação

* Suítes em 3.6.0, 3.6.8 e 3.13.2 e bateria Oracle (3.6.15, GFPR).
* Testes novos em `test_config`, `test_pastas_log`, `test_env_builder`, `test_executor`, `test_plataforma`, `test_sss_helper`, `test_scheduler_claim` e `test_scheduler_init` (ver AGENTS §7).
* DEV: `entrada_dir` e `saida_dir` ligados no `instance/config.ini`.
