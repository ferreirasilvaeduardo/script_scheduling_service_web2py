# SSS — Prompt F4.5: Gestão de scripts, homologação e vínculo de parâmetros

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.2
- `README.md` §4.3.A (homologação), §6.3 (`NENHUM` sem vínculos, `NOMEADO` exige flag), §8.5, §10 (tabelas 6, 8 e 11, política de exclusão)
- `docs/ADMIN_CRUD_PATTERN.md`, `modules/path_guard.py`, `modules/params_compiler.py`

## Objetivo
Cadastrar rotinas no catálogo com validação de segurança do executável, a homologação por ambiente e o vínculo ordenado de parâmetros.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/admin_scripts_service.py`:**
  - Campos: `nome` (único), `descricao`, `grupo`, `categoria`, `etapa`, `comando_real` (select fixo com a `ALLOWLIST`), `path_file`, `tipo_param`, `max_qtd_parallel_env` (1–999) e `timeout_seg` (opcional, > 0).
  - **Validação de `path_file` no cadastro:**
    1. `path_guard.validar_cadastro` (relativo, sem `..`);
    2. `path_guard.resolver(base_script_dir, ...)` contra o servidor local.

    Se a etapa 2 falhar, a UI mostra o código traduzido ("Arquivo fora do diretório base", "Arquivo gravável por outros usuários" etc.).

    **Observação na UI:** "A validação definitiva ocorre também no agente executor no momento da execução." (README §8.4). Em `sss_env = DEV`, o cadastro pode ser salvo com um aviso quando apenas a etapa 2 falhar e o arquivo não existir localmente. Em HML/PROD, a etapa 2 é bloqueante.
  - **Homologação:** `homologacao_salvar(script_id, ambiente_ids)`, com auditoria. Só ambientes ativos aparecem para marcar. Remover uma homologação mostra o aviso sobre os agendamentos afetados.
  - **Vínculo de parâmetros:** `script_params_salvar(script_id, vinculos)`, onde cada vínculo é `{parametro_id, ordem, obrigatorio, valor_padrao_sub}`.
    - `ordem` sequencial a partir de 1, renumerada no servidor;
    - parâmetro ativo e sem duplicidade;
    - `valor_padrao_sub` validado por `validar_valor`;
    - `NOMEADO` exige que todo parâmetro vinculado tenha `param_nomeado`;
    - `NENHUM` rejeita qualquer vínculo;
    - trocar `tipo_param` revalida os vínculos existentes.
  - **Prévia do argv:** ação que usa `params_compiler.compilar_snapshot` com os valores padrão e mostra o argv mascarado, ou os erros.
  - **Desativação** com aviso sobre os agendamentos pausados (README §10).
- **`applications/script_scheduling_service/controllers/admin_scripts.py`:** `lista` (filtros nome/grupo/categoria/interpretador/status, com as colunas "Ambientes homologados" e "Parâmetros"), `form`, `salvar`, `alternar_ativo`, `homologacao`, `salvar_homologacao`, `parametros`, `salvar_parametros` e `previa`, todos com `_exigir_func('CAD_SCRIPTS')`.
- **`views/admin_scripts/parametros.html`:**
  - lista ordenável com botões "subir/descer" (sem arrastar, para manter a acessibilidade);
  - adicionar parâmetro via busca no dicionário;
  - "obrigatório" e "valor padrão específico" por linha;
  - o POST envia a lista completa.
- **`applications/script_scheduling_service/scripts/test_admin_scripts_service.py`:**
  - interpretador fora da allowlist;
  - `path_file` absoluto, com `..`, fora da base e gravável por outros;
  - o comportamento DEV vs. HML do aviso;
  - homologação com ambiente inativo;
  - vínculo duplicado;
  - `NOMEADO` com parâmetro sem flag;
  - `NENHUM` com vínculo;
  - renumeração da ordem;
  - prévia gerando o argv esperado para um script do seed.

**OUT**
- Sem upload nem edição de arquivo de script pela UI (proibido: a árvore não é gravável pelo sistema, README §8.5).

## Requisitos
1. O `comando_real` enviado fora da allowlist é rejeitado no servidor, mesmo que o HTML tenha sido adulterado.
2. Nenhum caminho absoluto do servidor aparece para usuários sem perfil admin.

## Critérios de aceite
- [ ] Um script cadastrado, homologado e com parâmetros aparece no F3.2 para o perfil autorizado e gera o ticket corretamente.
- [ ] `../../etc/passwd` e `/bin/ls` são rejeitados com mensagens claras.
- [ ] Os testes passam.

## Verificação
- **Browser:** cadastrar um script novo de `dev/scripts`, homologar, vincular 3 parâmetros, reordenar, pré-visualizar e disparar pelo F3.2.
- Testes: `python -m unittest discover -s scripts -p "test_admin_scripts_service.py"` e `... -p "test_path_guard.py"`

## Saída
Relatório AGENTS.md §9.
