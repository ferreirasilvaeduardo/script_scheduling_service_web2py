# CR-036: Alertas no lugar de bloqueios extremos

| Campo | Valor |
|---|---|
| Status | **Encerrado** em 2026-10-29 |
| Origem | Pedido do responsável pelo produto: para deixar o sistema mais simples e objetivo, os controles extremos devem só gerar alerta, sem bloquear, sem perder a função principal; decisões passo a passo |
| Esquema | Sem mudança: `LOG_LIMIT`, `EXCEEDED` e `DEADLINE` continuam válidos nas CKs para os registros antigos |

## 1. Decisões

| # | Controle | Antes | Decisão | Depois |
|---|---|---|---|---|
| D1 | Log local do ticket acima de `max_local_log_size_bytes` (50 MB) | Matava o script: `FAILED/LOG_LIMIT/-5` | A | Alerta uma vez por ticket (`[SSS] log local acima de <n> MB (alerta; o script continua)` e WARNING); o script vai até o fim |
| D2 | Limite de arquivos abertos dos scripts (`RLIMIT_NOFILE` fixo em 1024) | Script com mais de 1024 arquivos abertos falhava | A | Herda o limite da conta; fica só o *core dump* desligado |
| D3 | Saída acima de `output_max_bytes` (20 MiB) ou `output_max_files` (1000) | Zip não ia ao banco (`EXCEEDED`); pasta no disco | **B** (o responsável escolheu, contra a recomendação de manter) | Sem limite: o agente passa 0 ao `pack` e todo zip vai ao BLOB; zip64 para arquivo de mais de 1 GiB; as duas chaves só geram aviso. Risco registrado no README §14: acompanhar o tablespace (DEPLOYMENT §5.5) |
| D4 | Prazo de 120 s do empacotamento da saída | Matava o `pack`: `FAILED/DEADLINE` | A | Alerta aos 120 s e espera o zip; a parada do agente continua abandonando o empacotamento |
| D5 | Agente com ambiente atendido sem `[environment:<NOME>]` no `secrets.cfg` | Recusa a subida | **B** | Mantido (CR-032, D11) |
| D6 | Chaves retiradas antes do CR-032 (`data_backend`, `script_owner_uids`, `ambientes_exigem_hash`) | Recusavam a subida | A | Só aviso, como as demais; as renomeadas (CR-015a) continuam recusadas, para o valor não se perder |
| D7 | Prazo de 120 s da entrega de um arquivo da tela Entrada (`put-input`) | Matava a gravação: entrega `FAILED/ERROR` | **B** (o responsável escolheu, contra a recomendação de manter) | Alerta aos 120 s e a gravação termina; como o agente faz uma entrega por vez, uma gravação travada segura as seguintes até a parada do agente (o WARNING é o sinal) |

| D8 | Linha do alerta do log grande (D1) com o log do banco já truncado (5 MB vence antes dos 50 MB) | A linha ficava só no arquivo local e no WARNING; não chegava à tela | A | `log_pump.add_note`: a linha vai ao banco depois do marcador de truncado, por fora do teto; se a coleta normal já a levou, não duplica |

Mantidos sem decisão de mudança, por não bloquearem ou por protegerem o servidor: `max_parallel_jobs` e `max_parallel_env` (só seguram na fila), `log_dir_min_free_mb` (segura os tickets novos na fila, com WARNING `DISCO_LOG`), `input_upload_max_bytes` (o envio passa inteiro pela memória do web), timeout do script, bloqueio de login, permissões dos scripts, `path_guard`, versão do esquema e `critical_config`.

## 2. Mudanças

* `src/sss/scheduler/scheduler_loop.py`: `_warn_log_limit` no lugar do `_stop(LOG_LIMIT)`; `_Item.log_limit_warned`.
* `src/sss/platform/os_platform/posix.py`: `DEFAULT_RLIMITS` só com `RLIMIT_CORE`.
* `src/sss/config/sss_config.py`: `output_max_bytes` e `output_max_files` fixos em 0 (sem limite) e ignorados com aviso, também pelos nomes antigos; `REMOVED_KEYS` virou parte de `IGNORED_KEYS`.
* `src/sss/platform/os_platform/ticket_files.py`: `pack` aceita 0 (sem limite) e força zip64 para arquivo de 1 GiB ou mais.
* `src/sss/scheduler/output_phase.py` e `input_phase.py`: prazo só alerta (`slow`), sem sinal; o caminho `DEADLINE` do empacotamento saiu.
* Testes: `test_scheduler_claim.py` (log acima do limite com o script terminando em `SUCCESS`), `test_platform.py` (limite herdado), `test_ticket_files.py` (0 = sem limite), `test_output_phase.py` e `test_input_phase.py` (prazo só alerta), `test_config.py` (chaves antigas e de limite da saída só com aviso).
* Documentação (varredura de todos os documentos vivos, a pedido do responsável):
  * README §2.5 (`data_backend`), §5.2 e §5.3 (`LOG_LIMIT` só em tickets antigos), §8.0 (`setrlimit` só do *core dump*), §8.4 (códigos 7 e 8 do `pack`), §8.7 (finalização sem `LOG_LIMIT`), §8.10 (log local com limite de alerta), §8.13 (saída sem limite, prazo só alerta, `EXCEEDED`/`DEADLINE` só em saídas antigas), §8.14 (entrega com prazo só alerta), §12.1 (tabela de chaves e "chave que saiu nunca impede a subida") e §14 (risco do zip sem teto no banco);
  * AGENTS §3.2 (saída), §5 (`data_backend`) e §7 (linhas dos testes);
  * DEPLOYMENT §5.5 (sem teto por ticket), §15 (código 11 e `LOG_LIMIT`) e §18.2 (notas da versão);
  * DEV_ENVIRONMENT (chaves do CR-011 só com aviso).
  * Sem mudança: `ADMIN_CRUD_PATTERN.md`, `UTILITY_SCRIPTS.md` e `docs/explain/` (não citam os limites alterados; os limites de tamanho dos campos ficam).

## 3. Comparação do código com a documentação (pedido do responsável)

Revisão só de leitura dos seis documentos vivos contra o código, depois da implementação: 24 achados, conferidos no código. Corrigidos no texto: sobras do comportamento antigo (`LOG_LIMIT` na finalização, risco do §14, chaves do CR-011 "recusadas" no AGENTS, `saida_max_*` no `RENAMED_KEYS`), referências cruzadas (§8.2, sem "cota da conta"), vaga ocupada durante o zip e riscos novos no §14, `DBMS_LOB.APPEND` da saída, `pack` com 0 = sem limite, linhas `[SSS]` de alerta no DEPLOYMENT §14.3, checklist §19 (chaves só com aviso e alerta de tablespace), retorno do §18.2, `UTILITY_SCRIPTS` (categoria `ARQUIVOS` do seed e coluna "Orientação") e `ADMIN_CRUD_PATTERN` (`request.post_vars`, `expected=`, sem `gluon`); comentários de código. No código: a mensagem do alerta em KB abaixo de 1 MB, e a decisão D8.

## 4. Validação

* Teste manual do zip sem limite: arquivo de 1,1 GiB empacotado pelo `ticket_files.py pack ... 0 0` em 23 s, zip válido (`testzip` sem erro).
* Suíte completa em 3.6.0, 3.6.15 e 3.13.2: 1502 testes OK (61 pulados, os do Oracle real); `var/` do DEV intacto.
* `make check-all` (flake8 e mypy no 3.11): zero achados.
* Homologação real no DEV com o código do CR-036 (antes do D8 e do ajuste de KB, que só tocam o caminho do log grande, coberto pelos testes): `SSS_EVIDENCE_DATE=20261029 SSS_EVIDENCE_ROUND=2`, **332 de 332 verificações OK**, 34 casos, 102 figuras (`dev/others/homologation/evidence_20261029_r2/results.json`). O DEV ficou parado no fim.
* O PROD não foi atualizado neste CR: continua parado no `e0030e7` (CR-035). A atualização segue o DEPLOYMENT §18.1, com as notas do §18.2.
