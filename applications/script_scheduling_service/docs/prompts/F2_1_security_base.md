# SSS — Prompt F2.1: Hash de senha, CSRF, Origin, sessão, cabeçalhos e mascaramento

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.3, §3.4, §5.2, §6
- `README.md` §4.1, §4.2 (inteiro, incluindo a nota sobre SameSite no Python 3.6), §8.10 (mascaramento), §13

## Objetivo
Implementar as primitivas de segurança que todas as telas vão usar, antes de existir qualquer tela funcional.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/security.py`** (puro, sem `gluon`):
  - `hash_senha(senha) -> str` no formato `pbkdf2_sha256$200000$<salt_hex>$<hash_hex>`, com salt de 16 bytes via `secrets.token_bytes`.
  - `verificar_senha(senha, armazenado) -> bool`:
    - usa `hmac.compare_digest`;
    - formato inválido ou `'!'` retorna `False` sem exceção.
  - `precisa_rehash(armazenado) -> bool`.
  - `hash_ficticio()`: hash pré-computado em memória na carga do módulo, para equalizar o tempo de resposta de login inexistente.
  - `validar_politica_senha(senha) -> lista_de_erros`, com mínimo de 12 caracteres.
  - `gerar_token_csrf()` (32 bytes, `secrets.token_urlsafe`) e `validar_token_csrf(esperado, recebido)`.
  - `origem_permitida(origin, referer, allowed_origins) -> bool`, comparando esquema + host + porta exatos e extraindo a origem do `Referer` com `urllib.parse`.
- **`applications/script_scheduling_service/modules/masking.py`** (puro):
  - `Mascarador` com `registrar(valor)` (ignora valores com menos de 4 caracteres e registra os candidatos em ordem decrescente de tamanho) e `mascarar(texto) -> texto`, substituindo por `****`.
  - `MascaradorFluxo(mascarador)` para fluxo em blocos:
    - `alimentar(bloco) -> texto_seguro` retém internamente uma cauda de `max_len_segredo - 1` caracteres, para não vazar segredo cortado entre blocos;
    - `finalizar() -> texto_restante`.
  - Mascaramento de padrão de connect string `usuario/senha@dsn`, que vira `usuario/****@dsn`.
  - `filtro_logging(mascarador)`: um `logging.Filter` que mascara `record.msg` e `record.args`.
- **`applications/script_scheduling_service/models/10_security.py`:**
  - **Sessão:**
    - `session.connect(request, response, cookie_key=<segredos.cookie_key>)`, com cookie `HttpOnly` e `Secure` (o `Secure` só pode ser omitido em `sss_env = DEV` sobre HTTP local);
    - timeout por inatividade (`session_idle_timeout_s`): sessão expirada é limpa e redireciona para o login com aviso.
  - **CSRF:** token por sessão; helper `csrf_campo()` para formulários (campo oculto `_csrf`) e `<meta name="csrf-token">` no layout para o `fetch`.
  - **Validação central de todo `POST`** em models, antes do controller: CSRF (campo `_csrf` ou cabeçalho `X-CSRF-Token`) **e** Origin/Referer contra `allowed_origins`. Em DEV, inclui a origem local do servidor. Falha retorna `HTTP(403)` com página genérica e log WARN sem o token.
  - **Cabeçalhos do README §4.2 em toda resposta**, incluindo as páginas de erro do web2py, e `Cache-Control: no-store` quando houver sessão autenticada.
  - **Mascarador global:** registro dos segredos carregados e instalação do filtro em todos os handlers de log.
- **Ajustes:** `views/layout.html` (meta CSRF), `components/modal_confirmacao.html` e o formulário de exemplo de `dev/componentes` passam a enviar `_csrf`.
- **`applications/script_scheduling_service/static/js/app/sss.js`:** helper `sssFetch(url, opcoes)` que injeta `X-CSRF-Token` em métodos que não sejam GET e trata 403 com toast.
- **Testes:**
  - `applications/script_scheduling_service/scripts/test_security.py`: formato do hash, verificação certa/errada, `'!'`, formato inválido, `precisa_rehash`, política de senha, CSRF, `origem_permitida` (origem igual, porta diferente, esquema diferente, só `Referer`, nenhum dos dois).
  - `applications/script_scheduling_service/scripts/test_masking.py`: segredo inteiro; segredo cortado entre 2 e 3 blocos; vários segredos com prefixo comum; connect string; filtro de logging.

**OUT**
- Sem tela de login (isso é o F2.2). Use o formulário de `dev/componentes` para testar o CSRF.

## Requisitos
1. **`SameSite`:** não tente setar via `Morsel` (o 3.6 lança `CookieError`). Use a dupla CSRF + Origin (README §4.2).
2. Nunca registrar token, cookie ou segredo em log, nem em mensagem de exceção.
3. Funções de `security.py` e `masking.py` não importam `gluon` (AGENTS §7.1).

## Critérios de aceite
- [ ] `POST` sem `_csrf`, com `_csrf` errado, ou com Origin de outro host retorna 403. Com tudo correto, retorna 200.
- [ ] Os cabeçalhos aparecem na aba Network inclusive numa URL inexistente (404).
- [ ] Os testes `test_security.py` e `test_masking.py` passam.

## Verificação
- **Browser:** submeter o formulário de `dev/componentes`; repetir removendo o campo `_csrf` pelo DevTools; inspecionar os cabeçalhos.
- Testes: `python -m unittest discover -s scripts -p "test_s*.py"` e `... -p "test_masking.py"`

## Regras de parada
Se a versão do web2py não permitir aplicar cabeçalhos às páginas de erro, **pare** e descreva a limitação.

## Saída
Relatório AGENTS.md §9.
