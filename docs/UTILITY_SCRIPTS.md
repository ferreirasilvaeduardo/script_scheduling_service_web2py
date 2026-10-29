# Script Scheduling Service (SSS) — Catálogo de Scripts Utilitários

Documento de especificação, governança e catálogo operacional dos **14 scripts utilitários de manipulação de arquivos** homologados e cadastrados por padrão no SSS.

---

## 1. Visão Geral

Para atender aos cenários operacionais frequentes de manipulação de arquivos corporativos (compactação, descompactação, divisão, consolidação, conversão de encoding, deduplicação, higienização, filtros e cálculo de integridade criptográfica), foram homologados **14 scripts utilitários**, desenvolvidos em conformidade com as diretrizes do projeto:

- **Runtime:** Compatíveis com Python 3.6.0+ (sem recursos de versões posteriores) e Shell POSIX (`/bin/bash` e `/bin/sh`).
- **Segurança e Isolamento:**
  - Validação estrita de caminhos (`path_guard`), rejeição de *path traversal* / *zip slip*;
  - Leitura em *streaming* / blocos (*chunks*) para arquivos de grande porte, com baixo uso de memória;
  - Parâmetros sanitizados sem injeção de comandos.
- **Localização dos Fontes:**
  - **Repositório (DEV):** `dev/scripts/utilitarios/`; o agente do DEV usa `[agent] script_base_dir = <RAIZ>/dev/scripts`.
  - **Instalação pelo pacote (PROD):** `<RAIZ>/scripts_ambiente/utilitarios/`, na pasta base padrão do agente (`scripts_ambiente/`, sem `script_base_dir` no `config.ini`; CR-028 e CR-032). O pacote não leva `dev/`: os scripts são copiados à parte (§6.1).
- **Cadastro no catálogo (CR-023):** o seed cadastra os 14 scripts com caminho relativo à pasta base do agente (`utilitarios/<arquivo>`). O mesmo cadastro vale no DEV e no PROD; só a pasta base muda.

---

## 2. Matriz dos 14 Scripts Utilitários

| # | Nome da Rotina | Interpretador | Tipo Param | Grupo / Categoria / Etapa | Timeout (s) | Max Paralelo | Arquivo Físico |
|:---:|:---|:---:|:---:|:---|:---:|:---:|:---|
| 1 | `zipar_arquivos` | `python3` | `NAMED` | `UTILITARIOS` / `ARQUIVOS` / `COMPACTACAO` | 1800 | 2 | `zipar_arquivos.py` |
| 2 | `descompactar_zip` | `python3` | `NAMED` | `UTILITARIOS` / `ARQUIVOS` / `DESCOMPACTACAO` | 1800 | 2 | `descompactar_zip.py` |
| 3 | `quebrar_arquivo` | `python3` | `NAMED` | `UTILITARIOS` / `ARQUIVOS` / `DIVISAO` | 1800 | 2 | `quebrar_arquivo.py` |
| 4 | `juntar_arquivos` | `python3` | `NAMED` | `UTILITARIOS` / `ARQUIVOS` / `CONCATENACAO` | 1800 | 2 | `juntar_arquivos.py` |
| 5 | `converter_encoding` | `python3` | `NAMED` | `UTILITARIOS` / `ARQUIVOS` / `CONVERSAO` | 1800 | 2 | `converter_encoding.py` |
| 6 | `substituir_texto` | `python3` | `NAMED` | `UTILITARIOS` / `ARQUIVOS` / `TRANSFORMACAO` | 1800 | 2 | `substituir_texto.py` |
| 7 | `remover_duplicadas` | `python3` | `NAMED` | `UTILITARIOS` / `ARQUIVOS` / `HIGIENIZACAO` | 1800 | 2 | `remover_duplicadas.py` |
| 8 | `gerar_hash_arquivo` | `python3` | `NAMED` | `UTILITARIOS` / `ARQUIVOS` / `AUDITORIA` | 1800 | 2 | `gerar_hash_arquivo.py` |
| 9 | `compactar_targz` | `bash` | `NAMED` | `UTILITARIOS` / `ARQUIVOS` / `COMPACTACAO` | 1800 | 2 | `compactar_targz.sh` |
| 10 | `descompactar_targz` | `bash` | `NAMED` | `UTILITARIOS` / `ARQUIVOS` / `DESCOMPACTACAO` | 1800 | 2 | `descompactar_targz.sh` |
| 11 | `contar_linhas_arquivo` | `sh` | `POSITIONAL` | `UTILITARIOS` / `ARQUIVOS` / `ANALISE` | 600 | 2 | `contar_linhas_arquivo.sh` |
| 12 | `filtrar_linhas` | `bash` | `NAMED` | `UTILITARIOS` / `ARQUIVOS` / `FILTRAGEM` | 1800 | 2 | `filtrar_linhas.sh` |
| 13 | `ordenar_arquivo` | `sh` | `NAMED` | `UTILITARIOS` / `ARQUIVOS` / `ORGANIZACAO` | 1800 | 2 | `ordenar_arquivo.sh` |
| 14 | `limpar_linhas_vazias` | `bash` | `NAMED` | `UTILITARIOS` / `ARQUIVOS` / `HIGIENIZACAO` | 1800 | 2 | `limpar_linhas_vazias.sh` |

---

## 3. Dicionário de Parâmetros Homologados (`tbsss_parameters`)

Os parâmetros abaixo são componentes reutilizáveis cadastrados no banco de dados e vinculados a cada rotina conforme as necessidades de entrada:

Na coluna "Orientação", o que se espera do valor: o seed não grava regex nem faixa, e quem valida o conteúdo é o próprio script (o SSS confere o tipo, as opções de `SELECT` e o tamanho, README §6).

| Código | Flag Nomeada | Rótulo (Label) | Tipo | Orientação | Valor Padrão |
|:---|:---:|:---|:---:|:---|:---:|
| `arq_origem` | `--origem` | Arquivo ou Pasta de Origem | `TEXT` | Caminho absoluto normalizado | — |
| `arq_destino` | `--destino` | Arquivo ou Pasta de Destino | `TEXT` | Caminho absoluto normalizado | — |
| `arq_zip` | `--arquivo-zip` | Arquivo ZIP | `TEXT` | Caminho do pacote `.zip` | — |
| `arq_tar` | `--arquivo-tar` | Arquivo TAR.GZ | `TEXT` | Caminho do pacote `.tar.gz` | — |
| `nivel_compressao` | `--nivel` | Nível de Compressão (1-9) | `NUMBER` | Faixa de 1 a 9 | `6` |
| `linhas_por_parte` | `--linhas-por-parte` | Linhas por Parte | `NUMBER` | Quantidade inteira positiva | `1000` |
| `prefixo_saida` | `--prefixo-saida` | Prefixo dos Arquivos Gerados | `TEXT` | Prefixo de caminho e nome | `/tmp/parte_` |
| `padrao_origem` | `--padrao-origem` | Padrão de Origem (Glob) | `TEXT` | Máscara de busca (ex: `/tmp/parte_*`) | `/tmp/parte_*` |
| `enc_origem` | `--enc-origem` | Codificação de Origem | `SELECT` | `ISO-8859-1`, `UTF-8`, `CP1252`, `ASCII` | `ISO-8859-1` |
| `enc_destino` | `--enc-destino` | Codificação de Destino | `SELECT` | `UTF-8`, `ISO-8859-1`, `CP1252` | `UTF-8` |
| `termo_busca` | `--busca` | Texto a Localizar | `TEXT` | String de busca | — |
| `termo_substituicao` | `--substituicao` | Texto Substituto | `TEXT` | Nova string | — |
| `flag_ordenar` | `--ordenar` | Ordenar Resultado | `SELECT` | `Y` (Sim), `N` (Não) | `Y` |
| `tipo_hash` | `--algoritmo` | Algoritmo de Hash | `SELECT` | `sha256`, `md5`, `sha1` | `sha256` |
| `termo_filtro` | `--padrao` | Padrão de Filtragem | `TEXT` | Termo para filtragem | — |
| `flag_inverter` | `--inverter` | Inverter Seleção | `SELECT` | `N` (Manter), `Y` (Excluir) | `N` |
| `flag_numerico` | `--numerico` | Ordenação Numérica | `SELECT` | `N` (Alfanumérica), `Y` (Numérica) | `N` |
| `flag_reverso` | `--reverso` | Ordem Reversa (Decrescente) | `SELECT` | `N` (Crescente), `Y` (Decrescente) | `N` |
| `caminho_arquivo` | *(posicional)* | Caminho do Arquivo | `TEXT` | Argumento posicional 1 | — |

---

## 4. Detalhamento Operacional dos Scripts

### 4.1 `zipar_arquivos` (Python 3)
- **Finalidade:** Compacta um arquivo individual ou uma árvore completa de diretórios em formato `.zip`.
- **Parâmetros:**
  1. `arq_origem` (`--origem`, obrigatório)
  2. `arq_destino` (`--destino`, obrigatório)
  3. `nivel_compressao` (`--nivel`, opcional, padrão `6`)
- **Exemplo de Execução CLI:**
  ```bash
  python3 scripts_ambiente/utilitarios/zipar_arquivos.py --origem /dados/relatorios --destino /backup/relatorios.zip --nivel 9
  ```

### 4.2 `descompactar_zip` (Python 3)
- **Finalidade:** Extrai o conteúdo de um pacote `.zip` para um diretório de destino, incluindo proteção ativa contra *zip slip* (*path traversal*).
- **Parâmetros:**
  1. `arq_zip` (`--arquivo-zip`, obrigatório)
  2. `arq_destino` (`--destino`, obrigatório)
- **Exemplo de Execução CLI:**
  ```bash
  python3 scripts_ambiente/utilitarios/descompactar_zip.py --arquivo-zip /backup/relatorios.zip --destino /dados/relatorios_extracao
  ```

### 4.3 `quebrar_arquivo` (Python 3)
- **Finalidade:** Divide arquivos texto extensos em partes menores contendo no máximo $N$ linhas por bloco.
- **Parâmetros:**
  1. `arq_origem` (`--origem`, obrigatório)
  2. `linhas_por_parte` (`--linhas-por-parte`, opcional, padrão `1000`)
  3. `prefixo_saida` (`--prefixo-saida`, opcional, padrão `/tmp/parte_`)
- **Exemplo de Execução CLI:**
  ```bash
  python3 scripts_ambiente/utilitarios/quebrar_arquivo.py --origem /dados/extrato_anual.csv --linhas-por-parte 5000 --prefixo-saida /dados/partes/extrato_
  ```

### 4.4 `juntar_arquivos` (Python 3)
- **Finalidade:** Concatena em streaming blocos de arquivos particionados (ordenados alfanumericamente) gerando um arquivo consolidado final.
- **Parâmetros:**
  1. `padrao_origem` (`--padrao-origem`, obrigatório, padrão `/tmp/parte_*`)
  2. `arq_destino` (`--destino`, obrigatório)
- **Exemplo de Execução CLI:**
  ```bash
  python3 scripts_ambiente/utilitarios/juntar_arquivos.py --padrao-origem "/dados/partes/extrato_*" --destino /dados/extrato_consolidado.csv
  ```

### 4.5 `converter_encoding` (Python 3)
- **Finalidade:** Converte a codificação de caracteres de arquivos texto (ex.: migração de bases legadas ISO-8859-1/Latin1 ou CP1252 para UTF-8).
- **Parâmetros:**
  1. `arq_origem` (`--origem`, obrigatório)
  2. `arq_destino` (`--destino`, obrigatório)
  3. `enc_origem` (`--enc-origem`, opcional, padrão `ISO-8859-1`)
  4. `enc_destino` (`--enc-destino`, opcional, padrão `UTF-8`)
- **Exemplo de Execução CLI:**
  ```bash
  python3 scripts_ambiente/utilitarios/converter_encoding.py --origem /dados/legado.txt --destino /dados/moderno_utf8.txt --enc-origem ISO-8859-1 --enc-destino UTF-8
  ```

### 4.6 `substituir_texto` (Python 3)
- **Finalidade:** Localiza e substitui ocorrências de strings em arquivos texto com geração de relatório de linhas afetadas.
- **Parâmetros:**
  1. `arq_origem` (`--origem`, obrigatório)
  2. `arq_destino` (`--destino`, obrigatório)
  3. `termo_busca` (`--busca`, obrigatório)
  4. `termo_substituicao` (`--substituicao`, obrigatório)
- **Exemplo de Execução CLI:**
  ```bash
  python3 scripts_ambiente/utilitarios/substituir_texto.py --origem /dados/config.ini --destino /dados/config_novo.ini --busca "10.0.0.1" --substituicao "10.0.0.2"
  ```

### 4.7 `remover_duplicadas` (Python 3)
- **Finalidade:** Remove linhas duplicadas de arquivos texto, com opção de manter a ordem original de inserção ou ordenar alfabeticamente.
- **Parâmetros:**
  1. `arq_origem` (`--origem`, obrigatório)
  2. `arq_destino` (`--destino`, obrigatório)
  3. `flag_ordenar` (`--ordenar`, opcional, padrão `Y`)
- **Exemplo de Execução CLI:**
  ```bash
  python3 scripts_ambiente/utilitarios/remover_duplicadas.py --origem /dados/lista_emails.txt --destino /dados/lista_emails_unicos.txt --ordenar S
  ```

### 4.8 `gerar_hash_arquivo` (Python 3)
- **Finalidade:** Calcula a assinatura de integridade criptográfica (SHA-256, MD5 ou SHA-1) através de leitura em blocos (*streaming*), suportando arquivos de múltiplos gigabytes com baixo consumo de memória.
- **Parâmetros:**
  1. `arq_origem` (`--origem`, obrigatório)
  2. `tipo_hash` (`--algoritmo`, opcional, padrão `sha256`)
- **Exemplo de Execução CLI:**
  ```bash
  python3 scripts_ambiente/utilitarios/gerar_hash_arquivo.py --origem /dados/remessa.txt --algoritmo sha256
  ```

### 4.9 `compactar_targz` (Bash)
- **Finalidade:** Empacota e compacta arquivo ou pasta em formato `.tar.gz`.
- **Parâmetros:**
  1. `arq_origem` (`--origem`, obrigatório)
  2. `arq_destino` (`--destino`, obrigatório)
- **Exemplo de Execução CLI:**
  ```bash
  scripts_ambiente/utilitarios/compactar_targz.sh --origem /dados/arquivos --destino /backup/arquivos.tar.gz
  ```

### 4.10 `descompactar_targz` (Bash)
- **Finalidade:** Valida a integridade do arquivo `.tar.gz` e extrai o conteúdo no diretório de destino.
- **Parâmetros:**
  1. `arq_tar` (`--arquivo-tar`, obrigatório)
  2. `arq_destino` (`--destino`, obrigatório)
- **Exemplo de Execução CLI:**
  ```bash
  scripts_ambiente/utilitarios/descompactar_targz.sh --arquivo-tar /backup/arquivos.tar.gz --destino /dados/arquivos_extraidos
  ```

### 4.11 `contar_linhas_arquivo` (POSIX Sh)
- **Finalidade:** Executa análise volumétrica completa de arquivo texto (linhas totais, linhas preenchidas, linhas vazias, palavras e tamanho em bytes) usando modo posicional/sequencial.
- **Parâmetros:**
  1. `caminho_arquivo` (*posicional $1*, obrigatório)
- **Exemplo de Execução CLI:**
  ```bash
  scripts_ambiente/utilitarios/contar_linhas_arquivo.sh /dados/carga.csv
  ```

### 4.12 `filtrar_linhas` (Bash)
- **Finalidade:** Filtra linhas de arquivo baseado em padrão de texto, com suporte a inversão de seleção (`grep -v`).
- **Parâmetros:**
  1. `arq_origem` (`--origem`, obrigatório)
  2. `arq_destino` (`--destino`, obrigatório)
  3. `termo_filtro` (`--padrao`, obrigatório)
  4. `flag_inverter` (`--inverter`, opcional, padrão `N`)
- **Exemplo de Execução CLI:**
  ```bash
  scripts_ambiente/utilitarios/filtrar_linhas.sh --origem /dados/log.txt --destino /dados/erros.txt --padrao "ERROR" --inverter N
  ```

### 4.13 `ordenar_arquivo` (POSIX Sh)
- **Finalidade:** Ordena linhas de arquivo texto com opções para ordenação alfanumérica, numérica (`sort -n`) e reversa (`sort -r`).
- **Parâmetros:**
  1. `arq_origem` (`--origem`, obrigatório)
  2. `arq_destino` (`--destino`, obrigatório)
  3. `flag_numerico` (`--numerico`, opcional, padrão `N`)
  4. `flag_reverso` (`--reverso`, opcional, padrão `N`)
- **Exemplo de Execução CLI:**
  ```bash
  scripts_ambiente/utilitarios/ordenar_arquivo.sh --origem /dados/valores.txt --destino /dados/valores_ordenados.txt --numerico S --reverso N
  ```

### 4.14 `limpar_linhas_vazias` (Bash)
- **Finalidade:** Higieniza arquivos texto eliminando espaços em branco nas bordas e descartando linhas em branco ou contendo apenas espaços.
- **Parâmetros:**
  1. `arq_origem` (`--origem`, obrigatório)
  2. `arq_destino` (`--destino`, obrigatório)
- **Exemplo de Execução CLI:**
  ```bash
  scripts_ambiente/utilitarios/limpar_linhas_vazias.sh --origem /dados/bruto.txt --destino /dados/limpo.txt
  ```

---

## 5. Homologação, Perfis e Usuários Cadastrados no Oracle

Na implantação do banco de dados (via `scripts/init_db.py` ou script SQL `docs/sql/01_deploy_sss_openrisow_tbsss.sql`):

### 5.1 Homologação Técnica nos Ambientes (`tbsss_script_env`)
Todos os 14 scripts são automaticamente homologados para execução nos **5 ambientes padrão**:
- `CLONE2` (`10.238.55.146/gfprod`)
- `CLONE1` (`10.238.55.145/gfprod`)
- `CLONE6` (`10.238.45.230/svc_gfprodc6`)
- `CLONE7` (`10.238.45.230/svc_gfprodc7`)
- `GFPREPROD` (`10.129.177.188/GFPR`)
*Totalizando 70 registros de homologação técnica (14 scripts × 5 ambientes).*

### 5.2 Perfis de Acesso e Matriz de Autorização (`tbsss_profiles`, `tbsss_profile_feature`, `tbsss_profile_env`)
Foram configurados **4 perfis de acesso** com escopos operacionais e administrativos bem delineados:

| Perfil | Tipo | Funcionalidades Autorizadas (`tbsss_profile_feature`) | Ambientes Autorizados (`tbsss_profile_env`) |
|:---|:---:|:---|:---|
| `ADMINISTRATOR` | Super Administrador (`is_admin = 'Y'`) | Todas as 14 funcionalidades (`EXEC_SCRIPT`, `VIEW_LOGS`, `CANCEL_TICKET`, `DOWNLOAD_OUTPUT`, `UPLOAD_INPUT`, `FILES_UPLOAD`, `FILES_DOWNLOAD`, `MANAGE_USERS`, `MANAGE_PROFILES`, `MANAGE_ENVIRONMENTS`, `MANAGE_SCRIPTS`, `MANAGE_PARAMETERS`, `MANAGE_SCHEDULES`, `VIEW_AUDIT`) | Todos os 5 ambientes (`CLONE2`, `CLONE1`, `CLONE6`, `CLONE7`, `GFPREPROD`) |
| `OPERATOR_PROD` | Operacional Produção (`is_admin = 'N'`) | `EXEC_SCRIPT`, `VIEW_LOGS`, `CANCEL_TICKET`, `DOWNLOAD_OUTPUT`, `UPLOAD_INPUT`, `FILES_UPLOAD`, `FILES_DOWNLOAD` | Todos os 5 ambientes (`CLONE2`, `CLONE1`, `CLONE6`, `CLONE7`, `GFPREPROD`) |
| `OPERATOR_HML` | Operacional Homologação (`is_admin = 'N'`) | `EXEC_SCRIPT`, `VIEW_LOGS`, `CANCEL_TICKET`, `DOWNLOAD_OUTPUT`, `UPLOAD_INPUT`, `FILES_UPLOAD`, `FILES_DOWNLOAD` | Subconjunto `CLONE6`, `CLONE7` e `GFPREPROD` (no seed, todos os ambientes estão marcados como produção) |
| `READ_ONLY` | Auditoria / Leitura (`is_admin = 'N'`) | Apenas leitura de logs e tickets (`VIEW_LOGS`) | Todos os 5 ambientes (`CLONE2`, `CLONE1`, `CLONE6`, `CLONE7`, `GFPREPROD`) |

### 5.3 Liberação de Scripts por Perfil (`tbsss_profile_script`)
Todos os 14 scripts utilitários foram liberados para os 4 perfis operacionais cadastrados, totalizando **56 registros de permissão** (4 perfis × 14 scripts).

### 5.4 Usuários Padrão Cadastrados para Homologação e Demonstração (`tbsss_users`)
Para viabilizar a demonstração operacional e os testes de interface (conforme matriz utilizada na homologação das telas / UI Freeze), foram cadastrados **4 usuários padrão**:

| Login | Nome Completo | Perfil Atribuído | Privilégio Administrativo | Finalidade de Teste / Demonstração |
|:---|:---|:---|:---:|:---|
| `admin` | Super Administrador | `ADMINISTRATOR` | Sim (`is_admin = 'Y'`) | Acesso total a painéis administrativos, cadastros, agendamentos, trilha de auditoria e disparo de rotinas |
| `op.prod` | Operador Producao | `OPERATOR_PROD` | Não (`is_admin = 'N'`) | Disparo e acompanhamento de rotinas em ambientes de produção e clones |
| `op.hml` | Operador Homologacao | `OPERATOR_HML` | Não (`is_admin = 'N'`) | Validação de restrição de escopo de ambientes (apenas Clones 6/7 e Preprod) |
| `consulta` | Auditor e Consulta | `READ_ONLY` | Não (`is_admin = 'N'`) | Validação de acesso somente leitura, sem permissão para disparar scripts ou alterar cadastros |

> [!IMPORTANT]
> **Credenciais Padrão de Homologação / Demonstração:**
> - **Senha Inicial:** `Sss@Homolog2026!` (atende à política corporativa com 16 caracteres, maiúsculas, minúsculas, números e caracteres especiais).
> - **Hash no Banco:** Criptografado com PBKDF2-SHA256 (200.000 iterações): `pbkdf2_sha256$200000$f9fb31dc39b754d083af236a880dfa6e$2229f3f8a694a9c45be82d9c3bd38110f8b474d2a0aa0ee7f691d405738a4cd8`.
> - **Idempotência:** A rotina de seed em SQL e Python utiliza `MERGE INTO`, atualizando nome, perfil e reativando o usuário, mas **preserva o hash da senha existente** caso o operador já tenha trocado sua senha.

### 5.5 Vínculos no Dicionário de Parâmetros (`tbsss_script_param`)
Foram criados **38 vínculos de parâmetros**, estabelecendo ordem de exibição no formulário, obrigatoriedade e valores de substituição padrão para cada uma das 14 rotinas.

---

## 6. Procedimento de Instalação e Execução em Produção

### 6.1 Instalação dos Arquivos Físicos no Servidor Linux

Com a conta do SSS, sem root (DEPLOYMENT §4.0: um usuário de SO só), a partir de uma cópia do repositório (o pacote não leva `dev/`):

```bash
# na <RAIZ>; a pasta scripts_ambiente/ e criada pelo agente na subida, se faltar (CR-032, D12)
mkdir -p scripts_ambiente/utilitarios
cp <copia do repositorio>/dev/scripts/utilitarios/* scripts_ambiente/utilitarios/

# o agente recusa script gravavel por grupo ou por outros (README §8.5; AGENTS §3.2)
chmod 0755 scripts_ambiente/utilitarios scripts_ambiente/utilitarios/*.sh scripts_ambiente/utilitarios/*.py
```

Nada a configurar no `config.ini` do agente: sem `[agent] script_base_dir`, a pasta base é `scripts_ambiente/` (CR-023, CR-028; DEPLOYMENT §9). Ensaiado no PROD (CR-033 e CR-035).

### 6.2 Execução do Script SQL via SQL*Plus

Para criar o esquema com o catálogo num banco vazio:

```bash
sqlplus usuario_owner/senha@//host:porta/servico @docs/sql/01_deploy_sss_openrisow_tbsss.sql
```

O `01_deploy_sss_<owner>_<prefixo>.sql` não roda sobre um esquema existente (para do primeiro erro; reaplicar exige o `02_rollback_sss_<owner>_<prefixo>.sql` antes, apagando os dados). Num banco já instalado, o catálogo é atualizado pelo `scripts/init_db.py`, que pula os objetos existentes e reaplica o seed por `MERGE INTO`, atualizando descrições, parâmetros e caminhos sem duplicidade (DEPLOYMENT §18).
