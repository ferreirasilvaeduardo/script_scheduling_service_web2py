# -*- coding: utf-8 -*-
"""Validacao de parametros, montagem do argv e snapshot imutavel (README §6, §8.4 passo 1).

Modulo puro: nao importa gluon (AGENTS §7.1). Toda ordem e explicita (OrderedDict ou
sort por 'ordem'); nunca depende da ordem de dict comum (AGENTS §2.1).
"""
import collections
import datetime
import json
import os
import re

from sss.platform import path_guard

# CR-025: v6 acrescenta interpreter_override (o interpretador digitado no disparo, ou None). CR-026: v7 guarda
# em interpreter o nome do cadastro (python, python3, sh, bash); v5 e v6, com a chave logica anterior, ainda
# sao aceitas (path_guard.LEGACY). Agente anterior recusa a v7 (UNSUPPORTED_VERSION).
SNAPSHOT_VERSION = 7
ACCEPTED_VERSIONS = (5, 6, 7)
MAX_LENGTH = 500
MASK = '****'
GENERAL_KEY = '_geral'

PARAM_TYPES = ('NAMED', 'POSITIONAL', 'NONE')
COMPONENT_TYPES = ('TEXT', 'NUMBER', 'DATE', 'SELECT', 'CHECKBOX')

_RE_CONTROL = re.compile(r'[\x00-\x1f\x7f]')
_RE_NUMBER = re.compile(r'^-?\d{1,18}(\.\d{1,6})?$')
_RE_BRACE_QUANT = re.compile(r'\{(\d*)(,?)(\d*)\}')
REGEX_MAX_LENGTH = 150
SENSITIVE_MIN_LENGTH = 4
MAX_UNBOUNDED = 2
MAX_CHOICES = 6
# CR-008, R-06: {m,n} com n - m acima de WIDE_RANGE conta como ilimitado; com algum ilimitado,
# no maximo MAX_CHOICES_WITH_UNBOUNDED quantificadores de escolha (pior caso medido < 0,2 s em 500 caracteres).
WIDE_RANGE = 10
MAX_CHOICES_WITH_UNBOUNDED = 4
_CHECKBOX = {'true': True, '1': True, 'false': False, '0': False}
_RE_FLAG = re.compile(r'-{1,2}[A-Za-z0-9][A-Za-z0-9_-]{0,27}')
OPTIONS_MAX_LENGTH = 500
OPTION_KEY_MAX_LENGTH = 100
OPTION_LABEL_MAX_LENGTH = 100

# Chaves obrigatorias das versoes 5 e 6 do snapshot (README §6.5, CR-005; chaves em ingles no CR-016c2, D20; a v6
# acrescenta interpreter_override, CR-025): path_file como foi cadastrado (absoluto ou,
# desde o CR-023, relativo a pasta base de cada agente); sem executavel do no que compilou.
_SNAPSHOT_KEYS = ('version', 'script_id', 'script_name', 'interpreter', 'path_file', 'param_type',
                    'args', 'answers', 'sensitive', 'compiled_at')


# CR-025: campo do interpretador digitado no disparo e a mensagem do formato invalido.
INTERPRETER_KEY = 'interpreter'
INTERPRETER_MESSAGE = (u'Informe o caminho completo do interpretador (ex.: /opt/py311/bin/python3) ou só o '
                       u'nome sem espaços (ex.: python3.13).')


class ParamError(Exception):
    """Erro de validacao de um parametro; a mensagem e voltada ao usuario e nunca ecoa o valor."""

    def __init__(self, param_code, message):
        Exception.__init__(self, message)
        self.param_code = param_code
        self.message = message


class SnapshotError(Exception):
    """Falha na pre-validacao do snapshot (PRECHECK_FAILED)."""

    def __init__(self, reason):
        Exception.__init__(self, reason)
        self.reason = reason


def _sensitive(parameter):
    return parameter.get('sensitive') == 'Y'


def _label(parameter):
    return parameter.get('label') or parameter.get('code') or 'Parâmetro'


def _select_options(parameter):
    try:
        options = json.loads(parameter.get('options_json') or '')
    except ValueError:
        options = None
    if not isinstance(options, dict) or not options:
        raise ParamError(parameter.get('code'),
                        'O parâmetro "%s" está com as opções mal configuradas. Contate o administrador.'
                        % _label(parameter))
    return options


def validate_value(parameter, raw_value):
    """Valida e normaliza um valor conforme component_type (README §6.2); lanca ParamError.

    CHECKBOX devolve bool; os demais tipos devolvem str normalizada.
    """
    code = parameter.get('code')
    label = _label(parameter)
    kind = parameter.get('component_type')

    if kind == 'CHECKBOX' and isinstance(raw_value, bool):
        return raw_value
    if not isinstance(raw_value, str):
        raise ParamError(code, 'Valor inválido para "%s".' % label)
    # Ordem do README §6.2: strip primeiro; controle so nas pontas ja foi removido.
    value = raw_value.strip()
    if len(value) > MAX_LENGTH:
        raise ParamError(code, 'O campo "%s" excede o limite de %d caracteres.' % (label, MAX_LENGTH))
    if _RE_CONTROL.search(value):
        raise ParamError(code, 'O campo "%s" contém caracteres de controle não permitidos.' % label)
    # Valor sigiloso curto nao pode ser mascarado com seguranca (README §4.1 e §6.2, CR-007 R-25).
    if _sensitive(parameter) and kind != 'CHECKBOX' and 0 < len(value) < SENSITIVE_MIN_LENGTH:
        raise ParamError(code, 'O valor sigiloso precisa ter pelo menos %d caracteres.' % SENSITIVE_MIN_LENGTH)

    if kind == 'TEXT':
        default = parameter.get('validation_regex')
        if default:
            try:
                matched = re.fullmatch(default, value) is not None
            except re.error:
                raise ParamError(code, 'O parâmetro "%s" está com a validação mal configurada. '
                                        'Contate o administrador.' % label)
            if not matched:
                raise ParamError(code, 'O campo "%s" não está no formato esperado.' % label)
        return value
    if kind == 'NUMBER':
        if not _RE_NUMBER.match(value):
            raise ParamError(code, 'O campo "%s" deve ser um número (até 18 dígitos e 6 decimais).' % label)
        return value
    if kind == 'DATE':
        try:
            date = datetime.datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            raise ParamError(code, 'O campo "%s" deve ser uma data válida no formato AAAA-MM-DD.' % label)
        return date.strftime('%Y-%m-%d')
    if kind == 'SELECT':
        if value not in _select_options(parameter):
            raise ParamError(code, 'Selecione uma opção válida para "%s".' % label)
        return value
    if kind == 'CHECKBOX':
        key = value.lower()
        if key not in _CHECKBOX:
            raise ParamError(code, 'O campo "%s" aceita apenas verdadeiro ou falso.' % label)
        return _CHECKBOX[key]
    raise ParamError(code, 'O parâmetro "%s" tem um tipo de componente desconhecido.' % label)


def _reject_regex(reason):
    raise ParamError('validation_regex', 'A expressão regular foi recusada: %s (README §6.2).' % reason)


def _class_end(default_value, i):
    """Indice logo depois do ']' que fecha a classe aberta em padrao[i] == '['."""
    j = i + 1
    if j < len(default_value) and default_value[j] == '^':
        j += 1
    if j < len(default_value) and default_value[j] == ']':
        j += 1
    while j < len(default_value):
        if default_value[j] == '\\':
            j += 2
            continue
        if default_value[j] == ']':
            return j + 1
        j += 1
    return len(default_value)


def validate_registry_regex(default_value):
    """Compila validation_regex e exige o subconjunto seguro do README §6.2 (CR-007, D5); lanca ParamError.

    Recusa grupo repetido por quantificador (exceto '?'), quantificador sobre quantificador, referencia a
    grupo, lookaround, grupo condicional, mais de MAX_UNBOUNDED quantificadores ilimitados (*, +, {n,} e
    {m,n} com n - m > WIDE_RANGE), mais de MAX_CHOICES quantificadores que criam escolha (so
    MAX_CHOICES_WITH_UNBOUNDED se houver ilimitado) e mais de REGEX_MAX_LENGTH caracteres. Assim o fullmatch
    fica no maximo polinomial de grau 2 no tamanho do valor (CR-008, R-06).
    """
    try:
        re.compile(default_value)
    except Exception:  # noqa: B902 - re.error, TypeError e erros internos do sre (ex.: grupo condicional invalido)
        raise ParamError('validation_regex', 'A expressão regular é inválida.')
    if len(default_value) > REGEX_MAX_LENGTH:
        _reject_regex('tem mais de %d caracteres' % REGEX_MAX_LENGTH)
    unbounded = 0
    choices = 0
    atom = None          # 'simples' (caractere, escape, classe, '.'), 'grupo' ou None
    after_quant = False    # o ultimo token foi um quantificador
    lazy = False    # e ele ja recebeu o modificador '?'
    i = 0
    n = len(default_value)
    while i < n:
        c = default_value[i]
        if c == '\\':
            next_value = default_value[i + 1:i + 2]
            if next_value.isdigit() and next_value != '0':
                _reject_regex('referência a grupo (\\%s) não é permitida' % next_value)
            atom, after_quant, i = 'simples', False, i + 2
            continue
        if c == '[':
            atom, after_quant, i = 'simples', False, _class_end(default_value, i)
            continue
        if c == '(':
            rest = default_value[i + 1:i + 5]
            if rest.startswith(('?=', '?!', '?<=', '?<!')):
                _reject_regex('lookahead e lookbehind não são permitidos')
            if rest.startswith('?('):
                _reject_regex('grupo condicional não é permitido')
            if rest.startswith('?P='):
                _reject_regex('referência a grupo não é permitida')
            atom, after_quant, i = None, False, i + 1
            continue
        if c == ')':
            atom, after_quant, i = 'script_group', False, i + 1
            continue
        if c == '|':
            atom, after_quant, i = None, False, i + 1
            continue
        quant = None
        if c in '*+?':
            quant, end = c, i + 1
        elif c == '{':
            m = _RE_BRACE_QUANT.match(default_value, i)
            if m and (m.group(1) or m.group(3)):
                quant, end = m.group(0), m.end()
        if quant is None:
            # '{' literal, '^', '$', '.' e demais caracteres.
            atom = None if c in '^$' else 'simples'
            after_quant, i = False, i + 1
            continue
        if after_quant:
            if quant == '?' and not lazy:
                lazy, i = True, end
                continue
            _reject_regex('quantificador aplicado a outro quantificador')
        if atom == 'script_group' and quant not in ('?', '{0,1}'):
            _reject_regex('grupo entre parênteses repetido por quantificador (use só ? depois de parênteses)')
        limits = quant[1:-1].split(',') if quant.startswith('{') else None
        wide = (limits is not None and len(limits) == 2 and limits[1] != ''
                 and int(limits[1]) - int(limits[0] or 0) > WIDE_RANGE)
        if quant in ('*', '+') or (quant.startswith('{') and quant.endswith(',}')) or wide:
            unbounded += 1
            if unbounded > MAX_UNBOUNDED:
                _reject_regex('mais de %d quantificadores ilimitados (*, +, {n,} ou {m,n} com mais de %d de '
                               'diferença)' % (MAX_UNBOUNDED, WIDE_RANGE))
        if limits is None or len(limits) == 2 and limits[0] != limits[1]:
            # ?, *, + e {m,n} com m != n criam escolha; muitas escolhas seguidas explodem o tempo.
            choices += 1
            cap = MAX_CHOICES_WITH_UNBOUNDED if unbounded else MAX_CHOICES
            if choices > cap:
                _reject_regex('mais de %d quantificadores que criam escolha (?, *, + ou {m,n})%s'
                               % (cap, ' quando há quantificador ilimitado' if unbounded else ''))
        after_quant, lazy, i = True, False, end


def validate_flag(flag):
    """Valida param_nomeado pela CK ck_tbsss_prm_flag (README §10 tabela 10); lanca ParamError."""
    if not isinstance(flag, str) or not _RE_FLAG.fullmatch(flag):
        raise ParamError('param_flag', 'Use uma flag como --data-ref ou -n (até 30 caracteres, '
                                         'letras, dígitos, _ e -).')


def _unique_pairs(pairs):
    seen = collections.OrderedDict()
    for key, value in pairs:
        if key in seen:
            raise ValueError('chave duplicada')
        seen[key] = value
    return seen


def validate_registry_options(text):
    """Valida options_json de SELECT e devolve o JSON canonico (sort_order do usuario preservada).

    Exige objeto {"valor": "Rotulo"} nao vazio, sem chave duplicada, com chaves e rotulos str nao vazios
    (apos strip), sem caracteres de controle, e serializacao com ate OPTIONS_MAX_LENGTH caracteres.
    """
    if not isinstance(text, str) or not text.strip():
        raise ParamError('options_json', 'Informe as opções da lista (pelo menos uma).')
    try:
        options = json.loads(text, object_pairs_hook=_unique_pairs)
    except ValueError:
        raise ParamError('options_json', 'As opções não formam um JSON válido sem chaves repetidas.')
    if not isinstance(options, dict) or not options:
        raise ParamError('options_json', 'As opções devem ser um objeto {"valor": "Rótulo"} com pelo menos um item.')
    cleaned = collections.OrderedDict()
    for key, label in options.items():
        if not isinstance(label, str):
            raise ParamError('options_json', 'Todo rótulo de opção deve ser texto.')
        key, label = key.strip(), label.strip()
        if not key or not label:
            raise ParamError('options_json', 'Valores e rótulos das opções não podem ser vazios.')
        if _RE_CONTROL.search(key) or _RE_CONTROL.search(label):
            raise ParamError('options_json', 'As opções contêm caracteres de controle não permitidos.')
        if len(key) > OPTION_KEY_MAX_LENGTH or len(label) > OPTION_LABEL_MAX_LENGTH:
            raise ParamError('options_json', 'Cada valor e rótulo de opção aceita até %d caracteres.'
                                           % OPTION_KEY_MAX_LENGTH)
        if key in cleaned:
            raise ParamError('options_json', 'O valor "%s" aparece mais de uma vez.' % key)
        cleaned[key] = label
    canonical = json.dumps(cleaned, ensure_ascii=False, separators=(',', ':'))
    if len(canonical) > OPTIONS_MAX_LENGTH:
        raise ParamError('options_json', 'As opções excedem %d caracteres; reduza a lista ou os rótulos.'
                                       % OPTIONS_MAX_LENGTH)
    return canonical


def _sorted_links(links):
    return sorted(links, key=lambda v: int(v['sort_order']))


def _empty(value):
    return value is None or (isinstance(value, str) and value.strip() == '')


def _resolve(links, answers):
    """Aplica a precedencia (README §6.1) acumulando os erros por campo."""
    answers = answers or {}
    resolved = collections.OrderedDict()
    errors = collections.OrderedDict()
    for v in _sorted_links(links):
        code = v['code']
        value = None
        try:
            for source in (answers.get(code), v.get('default_value_override'), v.get('default_value')):
                if not _empty(source):
                    value = validate_value(v, source)
                    break
            if value is None and v.get('required') == 'Y':
                raise ParamError(code, 'O campo "%s" é obrigatório.' % _label(v))
        except ParamError as e:
            errors[code] = e.message
            value = None
        resolved[code] = value
    return resolved, errors


def resolve_answers(links, answers):
    """Resolve o valor final de cada vinculo (OrderedDict codigo -> valor | None); lanca ParamError."""
    resolved, errors = _resolve(links, answers)
    for code, message in errors.items():
        raise ParamError(code, message)
    return resolved


def _named_args(v, value):
    code = v['code']
    flag = v.get('param_flag')
    if not flag:
        raise ParamError(code, 'O parâmetro "%s" não tem flag configurada para script NOMEADO.' % _label(v))
    if v.get('component_type') == 'CHECKBOX':
        return [flag] if value is True else []
    if value is None:
        return []
    if flag[:2] == '--':
        if value[:1] == '-':
            return [flag + '=' + value]
        return [flag, value]
    if value[:1] == '-':
        raise ParamError(code, 'O campo "%s" não pode começar com "-".' % _label(v))
    return [flag, value]


def _sequential_arg(v, value):
    if value is None:
        return ''
    if v.get('component_type') == 'CHECKBOX':
        return '1' if value else '0'
    if value[:1] == '-' and v.get('component_type') != 'NUMBER':
        raise ParamError(v['code'], 'O campo "%s" não pode começar com "-".' % _label(v))
    return value


def _build(param_type, links, resolved, errors):
    """Monta args acumulando erros; erros estruturais vao em GENERAL_KEY."""
    args = []
    if param_type == 'NONE':
        if links:
            errors[GENERAL_KEY] = 'Scripts sem parâmetros (NENHUM) não podem ter parâmetros vinculados.'
        return args
    if param_type not in ('NAMED', 'POSITIONAL'):
        errors[GENERAL_KEY] = 'Estratégia de parâmetros do script é desconhecida.'
        return args
    for v in _sorted_links(links):
        code = v['code']
        if code in errors:
            continue
        value = resolved.get(code)
        try:
            if param_type == 'NAMED':
                args.extend(_named_args(v, value))
            else:
                args.append(_sequential_arg(v, value))
        except ParamError as e:
            errors[code] = e.message
    return args


def build_args(param_type, links, resolved):
    """Monta a lista de argumentos conforme a estrategia (README §6.3); lanca ParamError."""
    errors = collections.OrderedDict()
    args = _build(param_type, links, resolved, errors)
    for code, message in errors.items():
        raise ParamError(None if code == GENERAL_KEY else code, message)
    return args


def compile_snapshot(script, links, answers, now, interpreter_override=None):
    """Compila o snapshot v7 (README §6.5) -> (json_str | None, resolvidos, erros por campo).

    Guarda o interpretador do cadastro, o path_file cadastrado e apenas os argumentos: o argv real e montado
    pelo agente (#!, digitado ou cadastro, CR-026). Erros sao acumulados.
    """
    resolved, errors = _resolve(links, answers)
    args = _build(script['param_type'], links, resolved, errors)
    try:
        path_guard.validate_interpreter(script['interpreter'])
    except path_guard.PathGuardError:
        errors[GENERAL_KEY] = 'O interpretador do script não é permitido.'
    override = (interpreter_override or '').strip() or None
    if override is not None:
        try:
            path_guard.validate_override(override)
        except path_guard.PathGuardError:
            errors[INTERPRETER_KEY] = INTERPRETER_MESSAGE
    if errors:
        return None, resolved, errors

    obj = {
        'version': SNAPSHOT_VERSION,
        'script_id': script['id'],
        'script_name': script['name'],
        'interpreter': script['interpreter'],
        'path_file': script['path_file'],
        'param_type': script['param_type'],
        'args': args,
        'answers': dict(resolved),
        'sensitive': sorted(v['code'] for v in links if _sensitive(v)),
        'compiled_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        # CR-025: interpretador digitado no disparo (caminho ou nome), ou None (como cadastrado)
        'interpreter_override': override,
    }
    return json.dumps(obj, ensure_ascii=False, sort_keys=True), resolved, errors


def interpreter_name(value):
    """Nome do cadastro guardado no snapshot (CR-026); a chave anterior (v5, v6) vira o nome equivalente."""
    return path_guard.registered_name(value) or value


def validate_snapshot(json_str, cfg, notes=None):
    """Pre-valida o snapshot no claim (README §8.4 passo 1) e devolve (snap, argv, script_real);
    lanca SnapshotError. script_real (o path_file resolvido) alimenta o SSS_SCRIPT_DIR do env_builder.

    cfg expoe, opcionais, sss_dirs (log_dir, work_dir e exec_work_dir, onde nenhum script pode ficar),
    script_base_dir (base do caminho relativo, CR-023), dev (script em dev/ da aplicacao aceito, CR-023 D8)
    e search_path (PATH do agente, onde os nomes sao procurados). notes, se dado, recebe as linhas para o log
    do ticket (ex.: #! ignorado, CR-026).
    Status e homologacao do script ficam a cargo do chamador.
    """
    try:
        snap = json.loads(json_str)
    except (TypeError, ValueError):
        raise SnapshotError('INVALID_JSON')
    if not isinstance(snap, dict) or any(k not in snap for k in _SNAPSHOT_KEYS):
        raise SnapshotError('INVALID_STRUCTURE')
    if snap['version'] not in ACCEPTED_VERSIONS:
        raise SnapshotError('UNSUPPORTED_VERSION')
    registered = path_guard.registered_name(snap['interpreter'])
    if registered is None:
        raise SnapshotError('INTERPRETER_NOT_ALLOWED')
    override = snap.get('interpreter_override')
    if override is not None and not isinstance(override, str):
        raise SnapshotError('INVALID_STRUCTURE')
    args = snap['args']
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise SnapshotError('INVALID_ARGS')
    # Defesa em profundidade (CR-007, R-32): o snapshot vem do banco; NUL ou controle nunca chegam ao argv.
    if any(_RE_CONTROL.search(a) for a in args):
        raise SnapshotError('INVALID_ARGS')

    try:
        # CR-023: caminho relativo junto da pasta base do agente; script na pasta da aplicacao so em dev/ no DEV.
        real = path_guard.resolve(snap['path_file'], sss_dirs=getattr(cfg, 'sss_dirs', None) or (),
                                  base_dir=getattr(cfg, 'script_base_dir', None),
                                  dev=bool(getattr(cfg, 'dev', False)))
    except path_guard.PathGuardError as e:
        raise SnapshotError('PATH_GUARD_' + e.code)
    try:
        argv, note = _agent_argv(registered, override, real, args, getattr(cfg, 'search_path', None))
    except path_guard.PathGuardError as e:
        raise SnapshotError('PATH_GUARD_' + e.code)
    if note and notes is not None:
        notes.append(note)
    return snap, argv, real


def _shebang_argv(script_real, search_path):
    """(cabeca do argv pelo #!, ou None, nota). #! ausente: None sem nota; #! cujo executavel nao existe
    (ou invalido): None com a nota para o log do ticket (CR-026, D5)."""
    try:
        path, extra = path_guard.read_shebang(script_real)
    except path_guard.PathGuardError:
        return None, None
    try:
        executable = path_guard.find_executable(path, search_path)
    except path_guard.PathGuardError:
        return None, u'#! ignorado: %s nao encontrado ou nao executavel neste servidor' % path
    # #!/usr/bin/env python3: o Python e o argumento do env; -E -s vem depois dele (o env nao aceita -E).
    tokens = (extra or '').split()
    python = path_guard.is_python(executable) or (os.path.basename(executable) == 'env'
                                                  and any(path_guard.is_python(t) for t in tokens))
    head = [executable] + ([extra] if extra else [])
    return head + (list(path_guard.PYTHON_PORTABLE_ARGS) if python else []), None


def _agent_argv(registered, override, script_real, args, search_path):
    """(argv do agente, nota) na ordem do CR-026 (D5): o #! do script, se o executavel existir; senao o
    digitado no disparo; senao o nome do cadastro, procurado no PATH do agente. O python3 do cadastro roda
    com -I; os demais Python com -E -s (D7). Nenhum existe: INTERPRETER_NOT_FOUND."""
    head, note = _shebang_argv(script_real, search_path)
    if head is None:
        if override:
            executable = path_guard.find_executable(override, search_path)
            fixed = path_guard.PYTHON_PORTABLE_ARGS if path_guard.is_python(override) else ()
        else:
            executable = path_guard.find_executable(registered, search_path)
            if registered == 'python3':
                fixed = path_guard.PYTHON3_ARGS
            else:
                fixed = path_guard.PYTHON_PORTABLE_ARGS if path_guard.is_python(registered) else ()
        head = [executable] + list(fixed)
    return head + [script_real] + list(args), note


def _secrets(snapshot):
    answers = snapshot.get('answers') or {}
    secrets_value = set()
    for code in snapshot.get('sensitive') or []:
        value = answers.get(code)
        if isinstance(value, str) and value != '':
            secrets_value.add(value)
    return secrets_value


def _mask_args(args, secrets):
    displayed = []
    for token in args:
        if token in secrets:
            token = MASK
        elif token[:2] == '--' and '=' in token:
            flag, value = token.split('=', 1)
            if value in secrets:
                token = flag + '=' + MASK
        displayed.append(token)
    return displayed


def display_argv(snapshot):
    """argv logico para a UI: interpretador, argumentos fixos, script e args com sensiveis em '****'.

    O caminho do script vai completo para todos (README §6.4, CR-005 D8).
    Conservador: qualquer argumento igual a um valor sensivel e mascarado.
    """
    registered = path_guard.registered_name(snapshot['interpreter']) or snapshot['interpreter']
    override = snapshot.get('interpreter_override')
    # CR-026: o comando mostrado e o do disparo (digitado) ou do cadastro; o #! so o agente le, no servidor.
    shown = override or registered
    if not override and registered == 'python3':
        head = [shown] + list(path_guard.PYTHON3_ARGS)
    else:
        head = [shown] + (list(path_guard.PYTHON_PORTABLE_ARGS) if path_guard.is_python(shown) else [])
    return head + [snapshot['path_file']] + _mask_args(list(snapshot['args']), _secrets(snapshot))
