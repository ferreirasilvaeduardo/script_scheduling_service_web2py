# CR-037: Pasta de Arquivos, só em disco

| Campo | Valor |
|---|---|
| Status | **Encerrado** em 2026-10-29 |
| Origem | Pedido do responsável pelo produto: novas funcionalidades de entrada e saída que **não gravam no banco**, só no diretório servido pelo web, ao lado da Entrada e das Saídas atuais (que continuam pelo banco) |
| Esquema | Sem mudança de estrutura; o catálogo de funcionalidades ganha duas linhas (seed por `MERGE`) |
| Passos | 037a `fc5faac` (catálogo, seed e agente), 037b `a485163` (tela), 037c (documentação, homologação e fechamento) |

## 1. Decisões

| # | Decisão |
|---|---|
| D1 A | Pasta por ambiente e script, independente de ticket, com nomes em inglês no plural: `files/<ambiente>/<script>/inputs` (as pessoas enviam, o script lê) e `outputs` (o script grava, as pessoas baixam) |
| D2 B | Uma pasta por agente: `var/<agente>/files/...`. Com um agente no ambiente, a tela o usa; com mais de um, pede a escolha |
| D3 B | Funcionalidades novas `FILES_UPLOAD` ("Enviar para Pasta de Arquivos") e `FILES_DOWNLOAD` ("Baixar da Pasta de Arquivos"), no grupo Operação, nos ambientes e scripts do perfil |
| D4 A | No seed, `OPERATOR_PROD` e `OPERATOR_HML` com as duas; `READ_ONLY` sem; `ADMINISTRATOR` por `is_admin` |
| D5 A | Variáveis `SSS_FILES_INPUTS_DIR` e `SSS_FILES_OUTPUTS_DIR` em todo ticket; o agente cria as pastas antes do script e nunca apaga nem empacota nada nelas |
| D6 A | `[web] files_upload_max_bytes` (1 GiB por padrão, até 10 GiB), só na rota `files/upload`; o envio vai em blocos para `var/<web>/tmp/` e para a pasta, sem passar inteiro pela memória do web |
| D7 A | A tela não apaga: `inputs` lista, envia e substitui com confirmação; `outputs` navega, baixa um arquivo ou a pasta em zip montado em fluxo; tudo auditado |
| D8 B | Sem procedimento de limpeza: a pasta cresce até alguém apagar à mão (risco no README §14) |

Durante o CR, o responsável trocou o DEV para `table_prefix = ssdev_` (o PROD continua `tbsss_`, no mesmo owner); decisão A: o esquema `ssdev_` foi criado depois do 037a pelo `init_db --real-schema`, já com as 14 funcionalidades. Com tabelas separadas, DEV e PROD podem ficar no ar ao mesmo tempo (substitui o CR-033, D1).

## 2. Implementação

* **037a:** `ddl_builder` (catálogo e perfis), FAKE, `audit_service` (ações `FILES_UPLOAD` e `FILES_DOWNLOAD`), `docs/sql` (`tbsss_`) com os `MERGE`; `sss_config` (`files_dir` derivado do nome, sem chave); `log_paths.files_dirs`; `os_platform.create_files_dirs`; `executor`, `env_builder` e `scheduler_loop` (pasta criada na subida, em `SSS_DIR`, e por ticket).
* **037b:** `platform/files_area.py` (caminhos sem link, listagem, gravação com temporário e link/rename, abertura com `O_NOFOLLOW`, árvore para o zip), `services/files_service.py`, `web/controllers/files.py`, `templates/files/index.html`, item de menu e ícone; `framework` (`Limits.spool_dir`, `Settings.upload_dir`); `security.body_limit` (limite grande só em `files/upload`) e `upload_dir`. Tipos nas assinaturas chamadas pelo código novo (`rbac`, `admin_crud`, `ui_helpers`, `app_context`, `repo_factory`, `sss_logging`, `input_browse_service`, `log_paths`), sem mudança de comportamento.
* **037c:** README (§2.4.3, §4.3, §5.11, §8.6, §8.16, §12.1, §14), AGENTS §7, DEPLOYMENT (§1.3, §8, §12, §18.2, §19, Apêndice A), DEV_ENVIRONMENT; caso CT-33 no roteiro de homologação e o script `dev/scripts/diagnostico/pasta_arquivos.sh`.

## 3. Validação

* Suíte completa e portões: ver o relatório da entrega.
* Teste real no DEV (037b), com o servidor web e o banco `ssdev_`: envio, download de arquivo e do zip, `../../instance/secrets.cfg` e ambiente fora do perfil com 404, `consulta` com 403, linhas `FILES_UPLOAD`/`FILES_DOWNLOAD` em `ssdev_audit`.
* Homologação real no DEV com o CT-33: ver §4.

## 4. Comparação do código com a documentação

Revisão só de leitura dos documentos vivos contra o código, depois da homologação: 19 achados, conferidos no código.

* **Código:** a tela caminha a partir de `var/<agente>/files`, sem seguir link também em `<ambiente>` e `<script>` (antes só o último nível era conferido); o limite grande do corpo só com sessão logada (sem login, o corpo grande chegaria ao temporário); "substituído" só quando havia arquivo; entidade `files` no filtro da auditoria; envio cuja auditoria falha (decisão B): o arquivo fica, a tela avisa e o log recebe um ERROR com o detalhe. Testes novos em `test_files_service.py` e `test_webapp.py`.
* **Documentação:** a nota do §18.2 do DEPLOYMENT mandava rodar o `init_db` num banco em uso, o que devolveria ao padrão o seed inteiro; passou a indicar só os blocos `MERGE` das duas funcionalidades e dos perfis. Também: listas de pastas (`files_dir` em `SSS_DIR`, código 13, chaves derivadas), ações e entidade da auditoria (§4.4 e §10), exceções da "mesma transação", 403 por rota, `var/<web>/tmp` como temporário de todo envio, árvores do código e do `var/`, limpeza dos `.sss_files_*` (§11.3), bloco de regras e exceção de `platform/files_area.py` no AGENTS, `pasta_arquivos.sh` no DEV_ENVIRONMENT e os ambientes do `OPERATOR_HML` sem chamá-los de não produtivos.

## 5. Homologação

Rodada `SSS_EVIDENCE_DATE=20261029 SSS_EVIDENCE_ROUND=3` no DEV (prefixo `ssdev_`, admin começando na senha do seed): **352 de 352 verificações OK**, 35 casos (com o CT-33 novo), 110 figuras. Documento: `docs/homologation/SSS_Homologation_Evidence_2026-10-29_r3.docx` e `.md`.

A rodada completa teve 351/352. A falha mostrou um defeito de usabilidade: a lista da auditoria mostra só os 80 primeiros caracteres do detalhe, e o sha256 empurrava "substituído" para o "ver mais". Corrigido em `files_service` ("substituído:" no início, sha256 no fim); o web foi reiniciado e o CT-33 repetido (19/19).
