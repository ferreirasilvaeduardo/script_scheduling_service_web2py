# SSS — Prompt F3.1: Compilador de parâmetros e path_guard

## Leitura obrigatória antes de planejar
- `AGENTS.md` §2.1 (ordem de dict), §3.2, §7
- `README.md` §6 (inteiro), §8.4 (passo 1), §8.5 (inteiro)

## Objetivo
Implementar a lógica pura que valida o questionário e compila o snapshot imutável, além da validação de interpretador e caminho. As telas F3.2, F4.4, F4.5 e F5.2 vão consumir esses módulos.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/path_guard.py`** (puro, sem `gluon`):
  - `ALLOWLIST = ('/usr/bin/python3', '/bin/bash', '/bin/sh')`.
  - `resolver(base_script_dir, path_file, owner_uids, uid_agente=None) -> script_real`. Lança `PathGuardErro(codigo)`, com o código num enum (`FORA_DA_BASE`, `NAO_E_ARQUIVO`, `IGUAL_A_BASE`, `CAMINHO_ABSOLUTO`, `CONTEM_PONTOS`, `DONO_INVALIDO`, `GRAVAVEL_GRUPO_OUTROS`, `GRAVAVEL_PELO_AGENTE`).
  - O algoritmo é o do README §8.5, **literal**: `realpath` na base e no script, `commonpath` com `ValueError` tratado, `real != base`, `isfile`.
  - Ownership e modo valem para o arquivo, para **cada diretório** de `real` até `base`, e para a própria base.
  - `validar_interpretador(comando_real)`.
  - `validar_cadastro(path_file)`: checagens textuais equivalentes às CKs `ck_tbsss_scr_path`, para uso na UI.
- **`applications/script_scheduling_service/modules/params_compiler.py`** (puro):
  - `validar_valor(parametro, valor_bruto) -> valor_normalizado`, que lança `ParamErro(codigo_param, mensagem_pt)`. Aplica as regras do README §6.2: NUL e caracteres de controle, tamanho 500, `strip`, `NUMBER`, `DATE`, `SELECT` contra `opcoes_json` parseado e `CHECKBOX`, e `re.fullmatch` para `TEXT` com regex.
  - `validar_regex_cadastro(padrao)`: compila o padrão e aplica a heurística anti-ReDoS do README §6.2.
  - `resolver_respostas(vinculos, respostas) -> OrderedDict[codigo -> valor | None]` com a precedência do README §6.1. Os padrões também passam por `validar_valor`, e um obrigatório sem valor gera erro.
  - `montar_args(tipo_param, vinculos, resolvidos) -> lista`, com as regras do README §6.3 **literalmente**:
    - flag longa com valor iniciado em `-` vira `--x=valor`;
    - flag curta com valor iniciado em `-` é rejeitada;
    - `SEQUENCIAL` com opcional vazio emite `""`, e `CHECKBOX` emite `"1"`/`"0"`;
    - `NUMBER` negativo é permitido;
    - `NENHUM` com vínculos é um erro.
  - `montar_argv(comando_real, script_real, args)`, com `-I` para python (README §6.4).
  - `compilar_snapshot(script, vinculos, respostas, script_real, agora) -> (json_str, resolvidos, erros_por_campo)`:
    - estrutura do README §6.5;
    - `json.dumps(..., ensure_ascii=False, sort_keys=True)`;
    - `sensiveis` listados.

    A função **acumula** os erros de todos os campos para a UI exibir de uma vez, em vez de parar no primeiro.
  - `validar_snapshot(json_str, cfg) -> snapshot`: a pré-validação do README §8.4, passo 1. Ela cobre a versão suportada, `argv[0] == comando_real`, a allowlist e `script_real` revalidado por `path_guard`. O status do script e a homologação ficam com o chamador.
  - `argv_para_exibicao(snapshot) -> lista`, com os valores sensíveis trocados por `****`.
- **`applications/script_scheduling_service/dev/scripts/`:** uma árvore de exemplo **sem** lógica perigosa, coerente com os `path_file` do seed F0.4:
  - `faturamento/carga_faturas.py`: imprime os args e sai com 0;
  - `faturamento/conciliacao.sh`: gera N linhas de saída;
  - `infra/limpeza.sh`: aceita `--falhar` e sai com 3;
  - `infra/longo.py`: dorme em ciclos e imprime progresso, para os testes de timeout e cancelamento;
  - `relatorios/exporta.sh` (posicional).

  Documente em `docs/DEV_ENVIRONMENT.md` que, em DEV, `script_owner_uids` deve conter o seu UID e os arquivos precisam de modo `0644` (scripts) e `0755` (diretórios).
- **Testes:**
  - `applications/script_scheduling_service/scripts/test_path_guard.py`: todos os casos do AGENTS §7.4, com árvore temporária (`tempfile`) e symlinks reais. O caso de dono inválido é testado passando `owner_uids` sem o UID atual.
  - `applications/script_scheduling_service/scripts/test_params_compiler.py`: todos os casos do AGENTS §7.4, mais `SELECT` com `opcoes_json` inválido, regex ReDoS rejeitada no cadastro, determinismo (duas compilações iguais produzem a mesma string) e `argv_para_exibicao`.

**OUT**
- Sem UI e sem persistência.

## Requisitos
1. Ordem do argv **determinística** (AGENTS §2.1): nunca dependa da ordem de `dict` comum.
2. As mensagens de `ParamErro` ficam em português, voltadas ao usuário, e **nunca** ecoam o valor de parâmetro sensível.
3. É proibido usar `str.startswith` para validar caminho (AGENTS §3.2).

## Critérios de aceite
- [ ] Os dois arquivos de teste passam, com cobertura de todos os ramos de erro de `path_guard` e de `montar_args`.
- [ ] `compilar_snapshot` com o seed do FAKE gera um JSON idêntico ao formato do README §6.5.

## Verificação
`python -m unittest discover -s scripts -p "test_p*.py" -v`

## Regras de parada
Se uma combinação de `tipo_param` × `tipo_componente` não estiver coberta pelo README §6.3, **pare** e liste-a.

## Saída
Relatório AGENTS.md §9.
