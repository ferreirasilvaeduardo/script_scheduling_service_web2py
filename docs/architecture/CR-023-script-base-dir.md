# CR-023: Caminho base do script (`[agent] script_base_dir`)

| Campo | Valor |
|---|---|
| Status | **Em andamento**. Proposta do responsável pelo produto em 2026-10-25; plano e decisões aprovados em 2026-10-25 |
| Origem | Cadastrar o script com caminho relativo (ex.: `relatorios/run_executor_scripts.py`) e deixar cada agente juntá-lo a uma pasta base própria |
| Restrições | Sem dependência nova (AGENTS §2.2). Python 3.6.0 a 3.13. Esquema na versão 1, ainda aberta (AGENTS §4.16): muda sem migração; para banco já instalado, `ALTER` documentado no DEPLOYMENT §18 |
| Afeta | README §6.4, §8.5, §10, §12; AGENTS §3.2, §4, §7; DEPLOYMENT §7, §18; `path_guard`, `sss_config`, `params_compiler`, `env_builder`, `scheduler_loop`, repositórios, cadastro de scripts, detalhe do ticket, painel de agentes, seed e homologação |

---

## 1. Situação de partida

Desde o CR-005 (D2), `path_file` é sempre o **caminho absoluto** do script no servidor do agente, conferido pelo `path_guard` (README §8.5); a CK `ck_tbsss_scr_path` exige a `/` inicial. O caminho real executado é calculado na hora pelo agente e não fica gravado.

## 2. Decisões

| # | Decisão |
|---|---|
| D1 | Pasta base em `[agent] script_base_dir`, no `config.ini` de cada agente (como `interpreters`, `input_dir`, `output_dir`). Opcional: vazia ou ausente desliga o caminho relativo |
| D2 | `path_file` aceita o caminho absoluto (como hoje, inclusive com link simbólico) ou um **relativo** à pasta base. O relativo é recusado com `..`, `//`, `\`, caractere de controle ou `./` no início; com `/` no início ele é absoluto |
| D3 | No agente, o relativo vira `script_base_dir/<relativo>`; daí em diante valem as mesmas conferências do absoluto (README §8.5), no caminho juntado e no real. O caminho real **pode ficar fora da pasta base** (link simbólico); pastas do sistema e do SSS continuam proibidas |
| D4 | Relativo sem `script_base_dir` no agente: `PRECHECK_FAILED` com o motivo `NO_BASE_DIR`. Arquivo ausente ou sem acesso: como hoje (`NOT_FOUND`, `NO_ACCESS`) |
| D5 | `script_base_dir` inexistente na subida: só aviso no log (a subida segue); os tickets com caminho relativo terminam em `NOT_FOUND`. Formato inválido (não absoluto, pasta do sistema, dentro de uma pasta do SSS ou da aplicação) aborta a subida como as demais chaves |
| D6 | Caminho final usado gravado na coluna nova `tbsss_tickets.script_path` junto com o PID; o detalhe do ticket o mostra ao lado do cadastrado |
| D7 | `tbsss_agents.script_base_dir`: cada agente publica a sua pasta base no registro, e o painel de agentes a mostra. Regra de configuração: todo agente de um ambiente que usa caminho relativo precisa da pasta base (sem desvio na fila) |
| D8 | O `path_guard` passa a proibir script (e pasta base) dentro da pasta da aplicação (`/opt/sss/app`), que a atualização troca inteira (DEPLOYMENT §18); em `sss_env = DEV`, a subpasta `dev/` da aplicação é a exceção |
| D9 | O snapshot do ticket não muda de versão: `path_file` continua o texto cadastrado. Um agente da versão anterior recusa o relativo com `PRECHECK_FAILED` (`RELATIVE_PATH`), nunca executa outro arquivo |
| D10 | Seed (Oracle e FAKE) e scripts de diagnóstico da homologação passam a caminho relativo; o DEV usa `script_base_dir = /opt/automacoes/scripts` |
| D11 | Fase final só de validação da documentação contra o código (pedido do responsável) |

## 3. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 023a | Agente, regras e banco: `path_guard` (relativo, base, pasta da aplicação), `sss_config` (`script_base_dir`), `params_compiler`, `env_builder` (`SSS_SCRIPT_LINK`), `scheduler_loop` (aviso na subida, `script_path` no PID, base publicada), `sql_ident` (CK de `path_file`, `tbsss_tickets.script_path`, `tbsss_agents.script_base_dir`), repositórios Oracle e FAKE, testes (`script_path` com 1000 caracteres: caminho maior guarda o final, com `...`). Tabelas do DEV recriadas a pedido do responsável (rollback do SSS + `init_db`), esquema 100% compatível com o registro. Testes novos: relativo no formato e no agente, sem base, link para fora da base, pasta da aplicação, `script_base_dir` na configuração, `SSS_SCRIPT_LINK` com o relativo, agente de ponta a ponta (relativo executa e grava `script_path`; sem base, `PRECHECK_FAILED`), Oracle (`script_path` truncado, base publicada) | Concluído |
| 023b | Telas: cadastro de scripts (relativo com aviso, pasta da aplicação), disparo, detalhe do ticket (caminho final), painel de agentes (pasta base), mensagens | Pendente |
| 023c | Seed e DEV com caminho relativo, roteiro de homologação (CT-31), DEPLOYMENT (§7 e §18 com os `ALTER`), homologação real | Pendente |
| 023d | Validação da documentação contra o código (revisão independente) e encerramento | Pendente |
