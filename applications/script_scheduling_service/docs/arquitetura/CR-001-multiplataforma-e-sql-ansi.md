# CR-001: Agente multiplataforma (Windows, Linux, Unix) e SQL ANSI com camada de dialeto

| Campo | Valor |
|---|---|
| Status | **Aprovado** em 2026-10-15 (D1 a D10). Aplicado ao README e ao AGENTS. **D7 e a parte de dialeto da D8 revogadas, D10 substituída pelo CR-002** (Oracle único e driver adaptativo) |
| Origem | Decisões do responsável pelo produto em 2026-10-15: **A** (Python ≥ 3.6.0, já aplicada em `1955fcf`), **B** (agente em Windows, Linux e Unix) e **C** (SQL ANSI sempre que possível, com dialeto isolado) |
| Afeta | README §2.2, §2.3, §3, §4.1, §5.6, §7.5, §8, §9, §10, §11, §12 e §14. AGENTS §2.2, §3.1, §3.2, §4, §5.5, §6, §7 e §8. Prompts F4.5 (ajuste), F7.x e F8.x (reescrita) |
| Não afeta | Regras de negócio (§1, §5.1 a §5.5, §6, §7.1 a §7.4), RBAC, UI (exceto o select de interpretador do F4.5) e backend FAKE |

Este documento **não altera nada sozinho**. Depois de aprovado, o README e o AGENTS são atualizados num único commit, e os prompts afetados são revisados antes do F7.

---

## 1. Contexto

Hoje o README define:
- o **agente** exclusivamente para Linux/POSIX: `start_new_session`, `os.killpg`, `preexec_fn` com `resource.setrlimit`, `/proc/<pid>/stat`, `fcntl.flock`, ownership por UID e modo `0o022`, e interpretadores `/usr/bin/python3`, `/bin/bash` e `/bin/sh`;
- o **banco** com SQL específico do Oracle 11g: `ROWNUM`, `FOR UPDATE WAIT n`, `DBMS_LOB.WRITEAPPEND`, `SYSDATE`, `NEXTVAL FROM DUAL`, `DECODE`, `EMPTY_CLOB()`, índices baseados em função e triggers de PK.

O contrato de repositório (`repo_*.py`) já isola a persistência, e o backend FAKE prova isso com 493 testes. O motor de execução (F8) e o acesso ao banco real (F7) **ainda não foram implementados**, então este é o momento de menor custo para a mudança.

---

## 2. Parte B: agente multiplataforma

### 2.1 Princípio

Toda primitiva dependente do sistema operacional passa para uma **camada de plataforma** (`modules/plataforma/`), com uma interface única e implementações `posix.py` (Linux, macOS, BSD, AIX, Solaris, HP-UX) e `windows.py`. O restante do daemon (claim, heartbeat, log pump, fencing e desdobro) não conhece o sistema operacional. **Não entra nenhuma dependência nova** (AGENTS §2.2): no Windows, as APIs nativas são acessadas por `ctypes` da biblioteca padrão. `pywin32` e `psutil` continuam proibidos.

### 2.2 Mapeamento das primitivas

| Necessidade (README) | POSIX (hoje) | Windows (proposta) |
|---|---|---|
| Isolar o grupo de processos do filho (§8.4) | `start_new_session=True` | `CREATE_NEW_PROCESS_GROUP` + **Job Object** atribuído ao filho, com `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` |
| Encerrar com escalada (§5.6, §8.7, §8.9, §8.11) | `killpg(SIGTERM)` → `kill_grace_s` → `killpg(SIGKILL)` | `CTRL_BREAK_EVENT` ao grupo → `kill_grace_s` → `TerminateJobObject`. O Job encerra também netos e double-fork, o que **elimina o risco residual "setsid escapa do killpg"** do §14 |
| Limites do filho (`_child_limits`) | `umask(0o077)` + `setrlimit` | Limites do Job (`JOB_OBJECT_LIMIT_PROCESS_MEMORY`, `ACTIVE_PROCESS`). O diretório de trabalho é criado com ACL restrita ao usuário do agente |
| Identidade do processo contra reciclagem de PID (§8.4 passo 5, §8.12 passo 9) | Linux: `starttime` de `/proc/<pid>/stat`. Outros Unix: `/proc/<pid>/psinfo` (AIX, Solaris) ou `sysctl KERN_PROC` (macOS/BSD) via `ctypes` | `GetProcessTimes` (`CreationTime`) via `ctypes` |
| Instância única por host (§8.12 passo 5) | `fcntl.flock` | `msvcrt.locking` no lock file |
| Usuário não privilegiado (§8.12 passo 1) | `geteuid() != 0` | Recusar token elevado (membro de Administradores ou SYSTEM), consultado por `ctypes` |
| Segredos (§4.1) | Arquivo regular, dono = euid, `mode & 0o077 == 0` | Arquivo regular, dono = SID do agente e DACL apenas com o dono e SYSTEM, sem herança de Users, Authenticated Users ou Everyone |
| `path_guard` (§8.5) | `realpath` + `commonpath` + UID em `script_owner_uids` + `st_mode & 0o022 == 0` + sem escrita do agente | Caminho final resolvido por `GetFinalPathNameByHandleW` (ver 2.3), `commonpath` com `normcase`, dono em `script_owner_sids` e **direitos efetivos** sem escrita para o agente nem para grupos amplos (`GetEffectiveRightsFromAclW`) |
| Graceful shutdown (§8.11) | SIGTERM/SIGINT acionam uma flag | `SIGBREAK`/`SIGINT` acionam a flag; **arquivo de parada** `work_dir/sss-<agent_id>.stop`, verificado a cada ciclo, para operação como serviço |
| Launchers (§12.2) | `bin/sss-*.sh` | `bin/sss-*.ps1` com as mesmas regras: recusa elevação e define `TZ` e `PATH` do Instant Client |
| Ambiente do filho (§8.6) | `PATH=/usr/bin:/bin` etc. | `PATH` mínimo com `%SystemRoot%\System32`, mais `SystemRoot`, `TEMP` e `TMP` no diretório do ticket, `PYTHONIOENCODING=utf-8`. Lista de bloqueio própria (`PATHEXT` fixo, `COMSPEC` fixo e as variáveis `PYTHON*`) |

### 2.3 Riscos de segurança novos e como tratá-los

1. **`os.path.realpath` no Windows, antes do Python 3.8, não resolve links simbólicos nem junctions.** Ele apenas normaliza o caminho, o que permitiria escapar do diretório base. **Mitigação:** no Windows, o `path_guard` usa sempre `GetFinalPathNameByHandleW` (via `ctypes`), em qualquer versão do Python, e rejeita *reparse points* intermediários que não sejam resolvidos.
2. **`os.access(W_OK)` no Windows só olha o atributo "somente leitura"** e ignora a ACL. **Mitigação:** os direitos efetivos são calculados pela ACL (tabela acima).
3. **`cmd.exe` e arquivos `.bat`/`.cmd` reinterpretam argumentos** (classe de falhas "BatBadBut", 2024): não existe *quoting* seguro e universal para eles. **Mitigação:** `.bat`/`.cmd` e `cmd.exe` ficam **proibidos** na allowlist do Windows (decisão D2).
4. **Saída do filho em code page do console (cp1252/OEM).** Isso não é risco de segurança, mas afeta a legibilidade do log. **Mitigação:** `PYTHONIOENCODING=utf-8` para Python; para PowerShell, `-OutputFormat Text` com `[Console]::OutputEncoding` UTF-8 injetado pelo wrapper de execução. O `log_pump` mantém `errors='replace'`.

### 2.4 Interpretadores lógicos (muda o modelo de dados)

Hoje `tbsss_scripts.comando_real` guarda um **caminho absoluto Linux** (CK `ck_tbsss_scr_cmd`). Com agentes em vários sistemas, o catálogo passa a guardar um **interpretador lógico**, e cada agente o mapeia para o executável local:

| Interpretador lógico | Linux/Unix (padrão, configurável) | Windows (padrão, configurável) | Argumentos fixos |
|---|---|---|---|
| `PYTHON3` | `/usr/bin/python3` | `C:\Python36\python.exe` (via config) | `-I` |
| `BASH` | `/bin/bash` | não disponível | — |
| `SH` | `/bin/sh` | não disponível | — |
| `POWERSHELL` | não disponível | `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe` | `-NoProfile -NonInteractive -ExecutionPolicy Bypass -File` |

* A CK passa a ser `comando_real IN ('PYTHON3','BASH','SH','POWERSHELL')` (coluna renomeada para `interpretador`).
* `[agent] interpretadores` no `config.ini` mapeia cada chave para o caminho absoluto. O agente valida na inicialização que cada caminho existe e é executável, e registra em `tbsss_agentes.interpretadores` quais chaves suporta, junto com `plataforma` (`LINUX`, `WINDOWS`, `UNIX`).
* **Claim filtrado por capacidade:** a seleção de candidatos (§8.2) só pega tickets de scripts cujo interpretador o agente suporta (`s.interpretador IN (:int0..:intN)`, com binds gerados pelo código). Assim, um ambiente pode ter agentes Linux e Windows sem que um pegue o script do outro.
* O **snapshot** (§6.5) passa a guardar o interpretador lógico. O `argv` real é montado **no agente**, no claim, a partir do mapeamento local. A UI mostra o `argv` lógico (por exemplo, `PYTHON3 -I <base>/carga.py --data ...`).
* No F4.5, o select de interpretador passa a listar as chaves lógicas. É um ajuste pequeno, feito antes do UI Freeze.

### 2.5 Níveis de suporte

| Nível | Plataformas | Garantia |
|---|---|---|
| **1** | Linux x86_64 e Windows Server 2016 ou mais novo (x86_64) | Testes automatizados e roteiro E2E (F9.2) em cada uma |
| **2** | Outros Unix (AIX, Solaris, HP-UX, macOS, BSD) | Mesma camada POSIX. A identidade de processo depende do provedor da plataforma; a homologação é feita pela equipe de infraestrutura com o mesmo roteiro, sob demanda |

> **Limite deste ambiente de desenvolvimento:** o código Windows pode ser **escrito e testado com dublês (mocks)** aqui. Para validar de verdade é preciso uma **VM ou runner Windows**. Sem isso, o veredito das partes Windows é `NÃO TESTADO` (AGENTS §7).

---

## 3. Parte C: SQL ANSI com camada de dialeto

### 3.1 Princípio

* O SQL da aplicação é escrito em **ANSI (SQL:2003)** sempre que o Oracle 11g aceitar.
* O que não for portável fica num **dialeto** (`modules/sql_dialeto/`): `oracle11g.py` primeiro e, no futuro, `ansi2008.py` (PostgreSQL, SQL Server 2012+, Oracle 12c+ etc.).
* Os repositórios SQL (`modules/repo_sql/`, que substitui o nome `repo_oracle/`) pedem fragmentos ao dialeto e nunca escrevem sintaxe proprietária diretamente.
* **Trocar de banco = novo dialeto + driver homologado + a mesma suíte `test_repo_contract.py`.**

### 3.2 Pontos não portáveis e onde ficam

| Necessidade | ANSI no Oracle 11g? | Solução |
|---|---|---|
| Paginação (§4.4, listas) | **Não** (`OFFSET/FETCH` só a partir do 12c) | `dialeto.paginar(sql, inicio, fim)`: `ROWNUM` no 11g e `OFFSET ... FETCH NEXT` no ANSI 2008 |
| Top-N em lote (§7.5, §8.2, purge) | Não | `dialeto.limitar(sql, n)` |
| Próximo ID (§7.5 passo 6) | Não (`NEXT VALUE FOR` é SQL:2003, mas o 11g não aceita) | `dialeto.proximo_id(seq)`. A aplicação **sempre informa o `id`**. A trigger condicional continua no Oracle apenas como defesa |
| Relógio do banco (§7.1, §8) | Parcial | `dialeto.agora()`: `SYSDATE` no 11g e `CURRENT_TIMESTAMP` truncado no ANSI. Mantém a regra "relógio do banco" |
| Aritmética de tempo (§8.8) | **Sim**: `SYSDATE - :n * INTERVAL '1' SECOND` funciona no 11g | Escrita em ANSI direto (sai o `:n/86400`) |
| Lock com espera (§8.3, §4.3.B) | Não (`WAIT n` é proprietário) | `dialeto.para_atualizar(espera_s)`: `FOR UPDATE WAIT n` no 11g; nos outros, `FOR UPDATE` com timeout de lock por sessão, configurado pelo `db_conn` |
| Comparação que trata nulos (concorrência otimista, §10) | Sim com `(c = :v OR (c IS NULL AND :v IS NULL))` | Escrita em ANSI direto (sai o `DECODE`) |
| Upsert (§8.12, seed) | **Sim** (`MERGE` é SQL:2003) | `MERGE` ANSI |
| Anexar texto a CLOB (§8.10) | Não | `dialeto.lob_anexar()`: PL/SQL com `DBMS_LOB.WRITEAPPEND` no 11g; `UPDATE ... SET c = c \|\| :chunk` nos outros |
| Ler CLOB por offset (§8.10, UI) | Não | `dialeto.lob_ler()`: locator no 11g; `SUBSTRING(c FROM :i FOR :n)` nos outros |
| CLOB vazio no claim (§8.3) | Não | `dialeto.lob_vazio()` |
| `FROM DUAL` | Não | `dialeto.sem_tabela()` |
| Índices parciais da fila (`ix_tbsss_tck_fila`/`_run`) | Não | DDL por dialeto (função `CASE` no 11g, índice parcial `WHERE status = ...` nos outros). As consultas com `CASE` continuam sendo ANSI válido |
| Tipos de coluna | Não | DDL gerada por dialeto a partir do registro `sql_ident`: `VARCHAR2(n CHAR)`/`NUMBER`/`DATE` no 11g; `VARCHAR(n)`/`NUMERIC`/`TIMESTAMP(0)` nos outros |
| Imutabilidade de `nome`/`login` (triggers `_bu`) | Não (PL/SQL) | Trigger por dialeto **e** checagem no repositório (que já existe no FAKE) |
| `executemany` com contagem por linha (§8.7) | Não (`arraydmlrowcounts` é do driver Oracle) | `db_conn` com *fallback* linha a linha |
| Estilo de bind | — | Os repositórios escrevem `:nome`; o `db_conn` converte para o `paramstyle` do driver |
| Códigos de erro (ORA-) | — | O `db_conn` mapeia os erros de cada driver para `RepoConflito`, `RepoViolacao` etc. |

### 3.3 O que **não** muda

* **O Oracle 11gR2 continua sendo o alvo inicial e o piso de compatibilidade**, assim como o limite de 30 caracteres por identificador, o charset e o Instant Client 19.
* **SQL 100% ANSI é impossível enquanto o 11g for o alvo.** A regra passa a ser "ANSI por padrão; sintaxe proprietária só no dialeto, com teste".
* A inclusão de outro banco exige aprovar o driver dele (AGENTS §2.2). Este CR **não** homologa nenhum driver novo.

---

## 3.4 Matriz de compatibilidade resultante

| Dimensão | Suporte | Observações |
|---|---|---|
| Python | **3.6.0 a 3.13**, inclusive | A sintaxe e a biblioteca padrão são as da 3.6.0. O que está acima da 3.13 só passa a valer depois de validado |
| Sistema operacional (web e agente) | Nível 1: Linux e Windows Server 2016 ou mais novo. Nível 2: demais Unix | Seção 2.5 |
| Oracle Database | **11gR2 ou superior** (12c, 18c, 19c, 21c, 23ai) | O dialeto `oracle11g` usa só sintaxe que as versões novas aceitam. Um dialeto "12c+" (`OFFSET/FETCH`) é opcional e não obrigatório |
| Cliente Oracle | Instant Client 19.x | O IC 19 conecta do 11.2.0.4 ao 23ai. O IC 21c/23ai **não** conecta ao 11g |
| **Driver × versão do Python** | 3.6: `python-oracledb 1.x` (Thick) ou `cx_Oracle 8.3`. 3.7 a 3.13: `python-oracledb 2.x` (Thick) | **Consequência:** nenhuma versão do driver cobre de 3.6 a 3.13 ao mesmo tempo. O `db_conn` já abstrai os dois. Hoje o AGENTS §2.3 restringe a `oracledb < 2.0`, e precisa passar a permitir a 2.x quando o Python for 3.7 ou mais novo. O modo **Thin** continua proibido, porque não conecta ao 11g |

> **Estado atual (antes da implementação):** o que está validado hoje é o servidor web + UI + backend FAKE em Linux, de 3.6.0 a 3.13. Oracle real (F7) e agente (F8) ainda não foram implementados; a matriz acima vale **depois** deles, com Windows validado numa VM ou runner Windows.

---

## 4. Decisões para aprovar

| # | Decisão | Recomendação |
|---|---|---|
| D1 | Interpretador lógico (`PYTHON3`, `BASH`, `SH`, `POWERSHELL`) mapeado por agente no lugar do caminho absoluto no catálogo | **Sim** |
| D2 | Windows: apenas `PYTHON3` e `POWERSHELL`; `cmd.exe`/`.bat`/`.cmd` proibidos (risco de injeção de argumentos) | **Sim** |
| D3 | Claim filtrado pelos interpretadores do agente; `tbsss_agentes` ganha `plataforma` e `interpretadores` | **Sim** |
| D4 | No Windows, o daemon roda como processo de console, iniciado por um serviço ou pelo Agendador de Tarefas da infraestrutura. Parada por arquivo `.stop` e `CTRL_BREAK`. Sem `pywin32` | **Sim** |
| D5 | Níveis de suporte: nível 1 para Linux e Windows; nível 2 para os demais Unix | **Sim** |
| D6 | `path_guard` no Windows com `GetFinalPathNameByHandleW` e direitos efetivos por ACL, em qualquer versão do Python | **Sim** (obrigatório para segurança) |
| D7 | Repositório SQL genérico (`repo_sql/`) + dialeto (`oracle11g` primeiro); a aplicação sempre informa o `id`; sem `DECODE`; `MERGE` ANSI; intervalos ANSI | **Sim** |
| D8 | DDL gerada por dialeto a partir do registro de identificadores; limite de 30 caracteres mantido | **Sim** |
| D9 | Validação Windows real depende de uma VM ou runner Windows (fornecida pela infraestrutura); sem ela, as partes Windows saem como `NÃO TESTADO` | Ciência |
| D10 | Driver por versão do Python: `oracledb 1.x`/`cx_Oracle 8.3` na 3.6 e `oracledb 2.x` (Thick) da 3.7 à 3.13, ambos atrás do `db_conn`. Atualizar o AGENTS §2.3 | **Sim** |

---

## 5. Impacto no plano de execução

| Item | Mudança |
|---|---|
| **F4.5** (feito) | Ajuste: select de interpretador lógico, CK nova no FAKE e na regra do `path_guard`. É um subitem pequeno, feito antes do UI Freeze |
| **F7.0** (novo) | `sql_dialeto` (interface + `oracle11g`) e `db_conn` (substitui `oracle_conn`: shim de driver, binds, mapa de erros), com testes do dialeto sem banco |
| **F7.1–F7.3** | `init_db.py` gera DDL pelo dialeto; `repo_sql/` no lugar de `repo_oracle/`; a suíte de contrato não muda |
| **F8.0** (novo) | `modules/plataforma/` (interface, `posix.py` e `windows.py`), com testes reais em POSIX e dublês para Windows |
| **F8.1–F8.4** | Executor, log pump e daemon passam a usar a camada de plataforma e o dialeto; launchers `.ps1` |
| **F9.2** | Roteiro E2E com um nó Linux **e** um nó Windows no mesmo ambiente |
| **UI Freeze** | Antecipar o ajuste do F4.5 (interpretador lógico) |

**Estimativa relativa:** F7 cresce cerca de 30% (dialeto e DDL por dialeto). F8 cresce cerca de 70% (camada de plataforma e Windows). Os prompts F7.x e F8.x são reescritos antes de serem executados.

---

## 6. Próximos passos depois da aprovação

1. Commit único com o README e o AGENTS atualizados conforme as seções 2 a 4, com o novo §2.6 "Plataformas suportadas" e o §2.7 "Portabilidade de SQL".
2. Ajuste do F4.5 (interpretador lógico), com testes e verificação no navegador.
3. Revisão dos prompts F7.x e F8.x e criação do F7.0 e do F8.0 em `docs/prompts/`.
4. Retomar a sequência pelo F5.1 (parser CRON), que não é afetado.
