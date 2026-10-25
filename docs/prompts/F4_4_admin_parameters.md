# SSS — Prompt F4.4: Dicionário de parâmetros

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.4
- `README.md` §6.1–6.3, §6.5 (sensíveis e a proibição de parâmetro de senha), §10 (tabela 10 `tbsss_parametros`, política de exclusão e de desativação com dependência)
- `docs/ADMIN_CRUD_PATTERN.md`, `modules/params_compiler.py`

## Objetivo
Gerenciar o catálogo de perguntas e flags reutilizáveis com validação de cadastro forte e governança de regex.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/admin_parametros_service.py`:**
  - `codigo`: CK `ck_tbsss_prm_codigo` e único.
  - `param_nomeado`: CK `ck_tbsss_prm_flag`, opcional, mas obrigatório se o parâmetro estiver vinculado a script `NOMEADO`. A alteração é bloqueada nesse caso.
  - `label` e `descricao`.
  - `tipo_componente`: alterá-lo com vínculos existentes é **bloqueado**, com a lista dos scripts afetados.
  - `opcoes_json`: obrigatório para `SELECT` e proibido nos demais tipos. Deve ser um objeto JSON `{"valor": "Rótulo"}` com chaves e rótulos não vazios. O tamanho serializado não pode passar de 500 caracteres.
  - `valor_padrao`: validado com `params_compiler.validar_valor` contra o próprio parâmetro.
  - `regex_validacao`: só para `TEXT`, validado por `params_compiler.validar_regex_cadastro`. Somente admin pode alterar (README §6.2).
  - `sensivel`: alerta fixo na UI: "Não use parâmetros para senhas ou credenciais. Elas ficam visíveis no processo do servidor." (README §6.5).
  - **Desativação com dependência** (README §10): bloqueada se houver vínculo com script ativo. A mensagem lista os scripts.
- **"Testar valor":** o formulário tem um campo de teste (POST + CSRF, JSON) que roda `validar_valor` com a configuração em edição, antes de salvar, e exibe o valor normalizado ou o erro.
- **`applications/script_scheduling_service/controllers/admin_parametros.py`:** `lista` (filtros código/label/tipo/status, com a coluna "Usado por N scripts"), `form`, `salvar`, `alternar_ativo` e `testar`, todos com `_exigir_func('CAD_PARAMETROS')`. O `testar` com regex exige perfil admin.
- **Views:** o formulário mostra os campos condicionais por tipo (Alpine): `opcoes_json` com um editor simples de pares valor/rótulo (adicionar/remover linhas, que serializa num campo oculto) e regex apenas para `TEXT`.
- **`applications/script_scheduling_service/scripts/test_params_compiler.py` (ampliar)** e **`applications/script_scheduling_service/scripts/test_admin_parametros_service.py`:**
  - código inválido ou duplicado;
  - flag inválida;
  - `SELECT` sem opções;
  - opções em não `SELECT`;
  - JSON inválido;
  - padrão inválido para o tipo;
  - regex ReDoS;
  - regex por não admin;
  - troca de tipo com vínculo;
  - desativação com vínculo ativo.

**OUT**
- O vínculo de parâmetro com script é feito no F4.5.

## Requisitos
1. O editor de opções gera o JSON no cliente **apenas como conveniência**. O servidor faz `json.loads` e valida tudo.
2. A regex digitada nunca é executada no cliente.

## Critérios de aceite
- [ ] O padrão `(a+)+$` é rejeitado com a mensagem de risco de desempenho.
- [ ] Desativar um parâmetro usado por um script ativo é negado, e a mensagem lista os scripts.
- [ ] "Testar valor" reflete a configuração em edição, ainda não salva.
- [ ] Os testes passam.

## Verificação
- **Browser:** cadastrar um parâmetro de cada `tipo_componente`; testar valores; tentar as operações bloqueadas.
- Testes: `python -m unittest discover -s scripts -p "test_*param*.py"`

## Saída
Relatório AGENTS.md §9.
