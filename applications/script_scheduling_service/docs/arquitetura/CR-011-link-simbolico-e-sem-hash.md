# CR-011: Script por link simbólico, sem hash e validação enxuta

| Campo | Valor |
|---|---|
| Status | **Aprovado** em 2026-10-20 pelo responsável pelo produto. Parte 1 em `b99c66c`; parte 2 (S1, S2, S3 e remoção completa do hash) neste CR |
| Origem | Pedido do responsável pelo produto: cadastrar o script por link simbólico, sem cálculo de hash, e simplificar o processo. "O ambiente fica responsável por controlar versionamento e o conteúdo do script; o scheduler tem que se preocupar em agendar e funcionar, simples e objetivo, sem abrir mão do essencial" |
| Restrições | Sem dependência nova. Python 3.6. Esquema v1 ainda aberto: colunas saem do DDL, sem migração; GFPR recriado pelo ciclo 02→01→99 |
| Afeta | README §6.5, §8.0, §8.4, §8.5, §8.6, §8.12, §10, §12.1 e §14. `AGENTS.md` (validação de caminho, testes). `docs/IMPLANTACAO.md`, `docs/AMBIENTE_DEV.md`. Prompts F8.3 (parte d), F9.1, F9.2 e `UI_FREEZE.md` |
| Revoga | CR-007 R-14 (caminho sem link, `CAMINHO_COM_LINK`), R-15 (dono e cadeia de pastas, `script_owner_uids`) e R-24 (hash no claim, `ARQUIVO_ALTERADO`); CR-008 E4 (hash homologado informado, `ambientes_exigem_hash`, `SEM_HASH`); CR-005 D4 (aviso de arquivo ausente no nó web) |
| Depende de | F8.3c (laço do agente) |

---

## 1. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Link simbólico aceito | `path_file` pode ser link ou ter link em qualquer pasta do caminho. O agente resolve o `realpath` e executa o arquivo real; o script recebe `SSS_SCRIPT_ARQUIVO` (real) e `SSS_SCRIPT_LINK` (cadastrado, só quando difere) |
| D2 | Sem hash | O agente não calcula nem confere hash. Saem as colunas `scripts.sha256_homologado` e `tickets.arquivo_sha256`, as CKs `ck_tbsss_scr_sha` e `ck_tbsss_tck_sha`, o campo do cadastro e a chave `[agent] ambientes_exigem_hash` |
| S1 | Web só confere formato | No nó web (cadastro, prévia e disparo): formato do caminho, allowlist do interpretador e pastas do sistema. O web não lê o arquivo e não emite aviso |
| S2 | Agente confere só o arquivo real | Existe, é acessível, é arquivo regular, não é gravável por grupo nem por outros e fica fora das pastas do sistema e do SSS (no caminho cadastrado e no real). Sem dono e sem cadeia de pastas: sai `[agent] script_owner_uids` e os códigos `DONO_INVALIDO`, `GRAVAVEL_PELO_AGENTE` e `GRAVAVEL_PELO_EXECUTOR` |
| S3 | Interpretador só precisa existir | O executável de `[agent] interpretadores`: absoluto e normalizado, existe, é arquivo executável e fica fora das pastas do SSS. Pode ser link e ficar nas pastas do sistema |
| D3 | Chave removida | O `config.ini` com uma chave removida aborta a subida com "Chave removida: ...; apague a linha", e não com "Chave desconhecida" (`sss_config.CHAVES_REMOVIDAS`) |
| D4 | Vários agentes | Continuam possíveis (vários servidores); o fencing do F8.4 fica como está |

## 2. Códigos do `path_guard` após o CR-011

`CAMINHO_RELATIVO`, `CAMINHO_NAO_NORMALIZADO`, `CONTEM_PONTOS`, `SEPARADOR_INVALIDO`, `CARACTERE_INVALIDO`, `PASTA_DO_SISTEMA`, `PASTA_DO_SSS`, `NAO_ENCONTRADO` (inclusive ciclo de links), `SEM_ACESSO`, `NAO_E_ARQUIVO`, `GRAVAVEL_GRUPO_OUTROS`, `INTERPRETADOR_NAO_PERMITIDO` e `INTERPRETADOR_INSEGURO`.

## 3. Risco aceito

Um arquivo alterado no disco, ou um link trocado por quem grava na pasta dele, executa o novo conteúdo sem aviso. Mitigação: arquivo real sem escrita de grupo e outros, fora das pastas do sistema e do SSS; execução com o usuário de execução do ambiente (CR-007, D1); gestão de versões e permissões dos scripts sob responsabilidade do ambiente (README §14).

## 4. Implantação

* Esquema v1 aberto: `docs/sql/01_implantar_sss.sql` regenerado sem as colunas; bancos de DEV recriados pelo ciclo 02→01→99.
* `config.ini` existente: apagar as linhas `script_owner_uids` e `ambientes_exigem_hash` (`docs/IMPLANTACAO.md` §16).
