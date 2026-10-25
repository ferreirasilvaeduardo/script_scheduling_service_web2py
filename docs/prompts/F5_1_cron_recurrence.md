# SSS — Prompt F5.1: Parser CRON e cálculo de recorrência

## Leitura obrigatória antes de planejar
- `AGENTS.md` §2.1 (sem `zoneinfo`), §6 (tempo), §7
- `README.md` §7.1–7.4 (inteiros), §10 (tabela 12, CKs de `tbsss_agendamentos`), §12.1 (`misfire_*`, `cron_horizon_days`)

## Objetivo
Implementar, em Python puro e sem bibliotecas, o cálculo exato das próximas execuções e da política de *misfire*. O F5.2 e o daemon (F8.4) vão consumir esses módulos.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/cron_parser.py`:**
  - `parse(expr) -> CronExpr`, que lança `CronErro(mensagem_pt)`. Sintaxe do README §7.3: 5 campos; `*`, número, lista, intervalo e passo; `dia_semana` 0–7 com 0/7 = domingo. São **rejeitados**: nomes, `L`, `W`, `#`, `?`, campos a mais ou a menos, valores fora da faixa e passo 0.
  - `CronExpr.proxima(apos, horizonte_dias) -> datetime | None`:
    - a primeira ocorrência **estritamente maior** que `apos`, com segundos = 0;
    - cálculo **campo a campo** (mês → dia → hora → minuto, com *carry*), nunca minuto a minuto;
    - semântica **OU** quando dia do mês e dia da semana forem ambos restritos (Vixie);
    - retorna `None` se não houver ocorrência até `apos + horizonte_dias`.
  - `CronExpr.descrever() -> str`: descrição curta em português para a UI (por exemplo, "às 02:30, de segunda a sexta").
- **`applications/script_scheduling_service/modules/recurrence.py`** (puro, com datas *naive* sem microssegundos):
  - `validar_regra(regra) -> erros_por_campo`: espelha as CKs de `tbsss_agendamentos` (`ck_tbsss_agd_campos`, `_hora`, `_dsem`, `_dia`, `_fim`) e valida a expressão CRON.
  - `proxima_execucao(regra, apos) -> datetime | None`, conforme a tabela do README §7.2:
    - `UNICA` → `data_inicio` se maior que `apos`, senão `None`;
    - `DIARIA` e `SEMANAL` (ISO 1–7, 1 = segunda);
    - `MENSAL` com o **último dia do mês** quando o dia não existir (31 em abril vira o dia 30; 29–31 em fevereiro vira o dia 28 ou 29);
    - `CRON`;
    - sempre respeitando o piso `data_inicio` e o teto `data_fim`.
  - `proximas(regra, apos, n) -> lista` (para a prévia da UI).
  - `avaliar_disparo(regra, agora, misfire_policy, misfire_tolerance_s) -> Decisao(gerar_ticket:bool, nova_data:datetime|None, perdidas:int, concluir:bool)`, implementando o README §7.4 e os passos 3–4 do §7.5:
    - `nova_data` é **sempre** a primeira ocorrência maior que `agora`;
    - `perdidas` conta as ocorrências entre `proxima_execucao` e `agora`, limitada a 10.000 para o log;
    - `concluir` vale para `UNICA` depois do disparo ou quando não houver próxima antes de `data_fim`.
  - `truncar_segundos(dt)` e `sem_microssegundos(dt)`, usados em toda saída.
- **`applications/script_scheduling_service/scripts/test_cron_parser.py` e `applications/script_scheduling_service/scripts/test_recurrence.py`**, cobrindo todos os casos do AGENTS §7.4, mais:
  - `*/15`;
  - `0 0 29 2 *`, que só ocorre em ano bissexto;
  - `0 0 31 * *`, que pula os meses curtos (é CRON, diferente de `MENSAL`);
  - `0 12 * * 0` e `0 12 * * 7`, que dão o mesmo resultado;
  - a semântica OU com `0 0 1 * 1`;
  - expressão sem ocorrência no horizonte (`0 0 30 2 *`), que retorna `None`;
  - `MENSAL` dia 31 em abril, fevereiro e dezembro;
  - `SEMANAL` `1,3,5`;
  - *misfire* `RUN_ONCE` após 3 dias de downtime, gerando 1 ticket e a nova data no futuro;
  - *misfire* `SKIP`;
  - `data_fim` atingido;
  - `UNICA` no passado;
  - nenhuma saída com microssegundos.

**OUT**
- Sem UI e sem persistência.

## Requisitos
1. Proibido `datetime.now()` dentro dos módulos. O "agora" sempre chega por parâmetro (AGENTS §6).
2. **Horário de verão:** nenhum tratamento de fuso no código. A semântica é de horário de parede (README §7.1). Documente isso na docstring do módulo.
3. Desempenho: `proxima()` deve responder em menos de 10 ms para qualquer expressão válida. Inclua um teste com `timeit` e limite folgado de 50 ms.

## Critérios de aceite
- [ ] Os dois arquivos de teste passam, incluindo os de desempenho.
- [ ] `descrever()` gera textos em português corretos para 5 expressões comuns, testadas.

## Verificação
`python -m unittest discover -s scripts -p "test_cron_parser.py" -v` e `... -p "test_recurrence.py" -v`

## Regras de parada
Se surgir uma ambiguidade de semântica não coberta pelo README §7 (por exemplo, `data_inicio` com horário diferente de `hora_execucao`), **pare** e liste-a.

## Saída
Relatório AGENTS.md §9.
