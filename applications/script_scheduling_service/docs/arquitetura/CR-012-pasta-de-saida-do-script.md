# CR-012: Pasta de saída do script, com zip para download

| Campo | Valor |
|---|---|
| Status | **Aprovado** em 2026-10-20 pelo responsável pelo produto, com as recomendações (a) a (d) e a regra de excesso (D6) |
| Origem | Pedido do responsável pelo produto: uma pasta de saída parametrizada, com a mesma estrutura do log e uma pasta final por execução, passada ao script por variável de ambiente; um canal alternativo para o script expurgar ou adicionar informações. O agente confere se há dados, gera um zip e deixa o arquivo para download na tela do usuário |
| Restrições | Sem dependência nova (`zipfile` da biblioteca padrão). Python 3.6. Esquema v1 ainda aberto: a tabela nova entra no DDL, sem migração; GFPR recriado pelo ciclo 02→01→99 |
| Afeta | README §2.4.3, §5.7, §8.0, §8.4, §8.6, §8.7, §8.12, §9.2, §10 (18 tabelas), §11.3, §12.1, §13 e §14. `AGENTS.md` (helper, testes). `docs/IMPLANTACAO.md`. Prompts F8.3 (parte d), F8.4, F9.1 e F9.2. Código: `sss_config`, `sql_ident`/`ddl_builder`, `pastas_log`, `env_builder`, helper, `plataforma`, `scheduler_loop`, `repo_oracle/scheduler_fila`, repositórios de tickets, `ticket_service`, controller e view do ticket |
| Revoga | Nada |
| Depende de | CR-009 (estrutura de pastas do log), CR-010 (variáveis `SSS_*`), CR-011, F8.3c (laço do agente) |

---

## 1. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Pasta por ticket | `saida_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>/`, com as mesmas partes do caminho do log (§8.4, passo 3; CR-009) e o mesmo minuto. Usa o número do ticket, e não o PID: o PID só existe depois do spawn e, fora de DEV, é o do `sudo` |
| D2 | Opcional por agente | `[agent] saida_dir` vazio desliga o recurso naquele agente: sem `SSS_SAIDA_DIR`, sem zip. Cada servidor tem o seu `saida_dir`; ele não precisa ser igual entre os agentes, porque o zip vai para o banco |
| D3 | Dono da pasta | Fora de DEV, a pasta do ambiente `saida_dir/<ambiente>/` é criada na implantação pelo root, com dono o usuário de execução do ambiente e modo `0700`. O helper, como o usuário de execução, cria o resto do caminho (`0700`) antes de executar o script. O agente nunca lê o conteúdo. Em DEV sem usuário de execução, o próprio agente cria tudo |
| D4 | Zip no banco | Tabela nova `tbsss_ticket_saida`, uma linha por ticket, com o zip num BLOB. Web e agentes podem estar em servidores diferentes, e o download sai do banco. Removida em cascata com o ticket (retenção atual) |
| D5 | Empacotamento em todo fim | Depois da finalização do ticket (sucesso, erro, timeout, cancelamento, `LOG_LIMIT`), com o grupo de processos já encerrado. Pasta vazia ou inexistente: nada é gravado e a pasta é removida |
| D6 | Limite | `saida_max_bytes` (padrão 20 MiB, teto 200 MiB) e `saida_max_arquivos` (padrão 1.000, teto 10.000). Ao passar de qualquer um, o empacotamento **para na hora**, sem zip parcial. O resultado do ticket não muda. Fica a linha `[SSS]` no log, uma linha `EXCEDEU` sem conteúdo no banco e a pasta no disco do agente que executou, até `saida_retention_days` |
| D7 | Pasta apagada depois do zip | Com o zip gravado (`DISPONIVEL`), a pasta é removida pelo helper. Em `EXCEDEU` ou `FALHOU`, fica no disco para recuperação manual |
| D8 | Sem mascaramento | O conteúdo da saída não passa pelo mascarador. Um segredo gravado pelo script vai para o zip (risco aceito no §14) |
| D9 | Download | GET no detalhe do ticket, com a mesma permissão de ler o log do ticket (§4.3.C: `VER_LOGS` no ambiente, ou o solicitante com `EXEC_SCRIPT` nos próprios tickets). Anexo (`Content-Disposition: attachment`), `application/zip`, `nosniff`, `no-store`. Sem auditoria (tela de consulta) |

## 2. Configuração

| Seção | Chave | Padrão | Regra |
|---|---|---|---|
| `[agent]` | `saida_dir` | vazio | Absoluto e normalizado; fora das pastas do sistema e sem se sobrepor a `log_dir`, `work_dir` e `exec_work_dir` (nenhuma dentro da outra) |
| `[agent]` | `saida_max_bytes` | 20.971.520 | 1.048.576 a 209.715.200 |
| `[agent]` | `saida_max_arquivos` | 1000 | 1 a 10.000 |
| `[logging]` | `saida_retention_days` | 7 | 1 a 365; pastas que ficaram no disco (D6, D7) |

## 3. Variável do script

`SSS_SAIDA_DIR`: caminho absoluto da pasta do ticket. Só existe quando o agente tem `saida_dir` (regra R-a do CR-010).

## 4. Helper

* **`run`:** a especificação ganha `saida` = `{"base": "<saida_dir>/<ambiente>", "relativo": "<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>"}`. O helper confere que `base` é absoluta, normalizada, sem link e do próprio usuário, e que `relativo` tem exatamente esse formato. Cria cada nível com `os.mkdir(..., 0o700)`, recusando link ou item que não seja diretório do próprio usuário. Falha aqui é `SPAWN_ERROR`.
* **`empacotar <base> <relativo> <max_bytes> <max_arquivos>`** (novo): percorre a pasta sem seguir links. Só entram arquivos regulares, com nomes relativos à pasta do ticket; links e itens especiais são ignorados. Conta os arquivos antes de compactar e grava o zip (`ZIP_DEFLATED`) na saída padrão, interrompendo ao passar de `max_bytes`. Códigos novos: **6** pasta vazia ou inexistente; **7** limite excedido, com `ARQUIVOS` ou `BYTES` no stderr.
* **`limpar-saida <base> <relativo>`** (novo): remove a pasta do ticket sem seguir links.
* **`purgar-saida <base> <dias>`** (novo, usado pelo `purge.py`): remove as pastas de minuto mais antigas que `<dias>`, com a data tirada do caminho, e depois as pastas vazias acima delas.

Em DEV sem usuário de execução, as mesmas funções rodam no agente, por `plataforma`.

## 5. Agente

1. **Spawn (§8.4):** com `saida_dir`, monta `base` e `relativo` com as partes do caminho do log e passa à especificação e ao `SSS_SAIDA_DIR`.
2. **Fase de saída**, nova, depois do passo 5 da finalização (§8.7) e antes da limpeza. É uma máquina de estados do laço, sem espera:
   1. inicia o `empacotar` (helper ou plataforma) com a saída padrão num arquivo `work_dir/ticket_<id>/saida.zip`, e acompanha com `poll()`. O prazo é fixo, de 120 s; ao vencer, o processo é encerrado e a saída fica `FALHOU`;
   2. código 6: remove a pasta e não grava nada;
   3. código 7: grava a linha `EXCEDEU` (motivo `ARQUIVOS` ou `BYTES`) e anexa ao log a linha `[SSS] saída não empacotada: excede o limite de <n> arquivos (ou de <n> MiB) (agente <agent_id>)`;
   4. código 0: grava a linha `GRAVANDO` com `EMPTY_BLOB()` e envia o zip por partes de 1 MiB (`DBMS_LOB.WRITEAPPEND`, até 4 partes por volta do laço). No fim, grava `DISPONIVEL`, com tamanho e quantidade de arquivos, e remove a pasta;
   5. todo `INSERT` ou `UPDATE` exige que o ticket ainda seja deste agente (`agente_id = :agente_id`). `rowcount = 0` abandona a fase (`OWNERSHIP_LOST`) e deixa a pasta no disco;
   6. erro de banco: a fase é tentada de novo a cada `cancel_poll_interval_s`, como a finalização pendente. No `SHUTDOWN`, a fase é abandonada: a linha fica `GRAVANDO` e a pasta fica no disco.
3. **Startup check (§8.12):** linhas `GRAVANDO` de tickets deste agente viram `FALHOU`.
4. **Subida fora de DEV:** para cada ambiente atendido, `saida_dir/<ambiente>/` existe, é diretório, pertence ao usuário de execução e não tem escrita de grupo nem de outros (saída 13).
5. **Espaço:** `log_dir_min_livre_mb` também é conferido em `saida_dir` antes do claim.

## 6. Banco: `tbsss_ticket_saida` (abreviação `tsai`)

* PK `pk_tbsss_ticket_saida` · UK `uk_tbsss_tsai_tck (ticket_id)`
* FK `fk_tbsss_tsai_tck → tbsss_tickets(id) ON DELETE CASCADE` (coberta pela UK)
* CK `ck_tbsss_tsai_sit (situacao IN ('GRAVANDO','DISPONIVEL','EXCEDEU','FALHOU'))`, `ck_tbsss_tsai_mot (motivo IS NULL OR motivo IN ('ARQUIVOS','BYTES','PRAZO','ERRO'))` e `ck_tbsss_tsai_upd` (colunas de registro)
* **Colunas:**
  * `id`, `ticket_id NUMBER(10) NOT NULL`
  * `situacao VARCHAR2(10 CHAR) NOT NULL`, `motivo VARCHAR2(10 CHAR)`
  * `agente_id VARCHAR2(30 CHAR) NOT NULL` (onde a pasta ficou)
  * `qtd_arquivos NUMBER(10)`, `tamanho_bytes NUMBER(12)`
  * `conteudo BLOB` (SECUREFILE, ou BASICFILE no fallback)
  * colunas de registro (CR-006), com o ator `SYSTEM:<agent_id>`
* **Privilégios:** agente com `SELECT`, `INSERT` e `UPDATE`; web com `SELECT`; purge sem privilégio novo (cascata).

## 7. Tela

O quadro "Saída" do detalhe do ticket (§5.7):

| Situação | Mostra |
|---|---|
| sem linha | nada (o script não gravou saída, ou o agente não tem `saida_dir`) |
| `GRAVANDO` | "Saída em preparação." Depois de 1 hora: "A saída não foi concluída. Os arquivos ficaram no servidor do agente `<agente>`." |
| `DISPONIVEL` | "Saída: N arquivos, X KB" e o botão **Baixar** (`ticket_<id>_saida.zip`) |
| `EXCEDEU` | "Saída não disponível: passou do limite de <n> arquivos (ou de <n> MiB). Os arquivos ficaram no servidor do agente `<agente>` por <dias> dias." |
| `FALHOU` | "A saída não foi gravada. Os arquivos ficaram no servidor do agente `<agente>` por <dias> dias." |

## 8. Riscos aceitos

* Conteúdo da saída sem mascaramento (D8).
* Um zip de até `saida_max_bytes` por ticket ocupa o banco até a retenção dos tickets. Dimensionar o tablespace dos LOBs (`IMPLANTACAO.md`).
* Excesso ou falha deixam arquivos no disco do agente até `saida_retention_days`.

## 9. Passos

| Passo | Conteúdo |
|---|---|
| P0 | Este documento; README, AGENTS, IMPLANTACAO e prompts |
| R1 | Configuração, registro `sql_ident` (18 tabelas), DDL e SQL regenerados, repositório da saída (Oracle e FAKE) |
| R2 | Helper (`run` com `saida`, `empacotar`, `limpar-saida`, `purgar-saida`), `plataforma` e `env_builder` (`SSS_SAIDA_DIR`) |
| R3 | Agente: fase de saída, startup check e conferências da subida |
| R4 | Web: quadro "Saída" e download |
| UF | Suíte nas 3 versões, ciclo 02→01→99 no GFPR (com confirmação), bateria Oracle, relatório §9, commit e push |
