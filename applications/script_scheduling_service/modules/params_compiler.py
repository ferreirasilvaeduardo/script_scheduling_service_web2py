# -*- coding: utf-8 -*-
"""Validacao de parametros, montagem do argv e snapshot imutavel (README §6, §8.4 passo 1).

Modulo puro: nao importa gluon (AGENTS §7.1). Toda ordem e explicita (OrderedDict ou
sort por 'ordem'); nunca depende da ordem de dict comum (AGENTS §2.1).
"""
import collections
import datetime
import json
import re

import path_guard

VERSAO_SNAPSHOT = 4
TAMANHO_MAXIMO = 500
MASCARA = '****'
CHAVE_GERAL = '_geral'

TIPOS_PARAM = ('NAMED', 'POSITIONAL', 'NONE')
TIPOS_COMPONENTE = ('TEXT', 'NUMBER', 'DATE', 'SELECT', 'CHECKBOX')

_RE_CONTROLE = re.compile(r'[\x00-\x1f\x7f]')
_RE_NUMBER = re.compile(r'^-?\d{1,18}(\.\d{1,6})?$')
_RE_QUANT_CHAVE = re.compile(r'\{(\d*)(,?)(\d*)\}')
TAMANHO_REGEX = 150
SENSIVEL_MINIMO = 4
MAX_ILIMITADOS = 2
MAX_ESCOLHAS = 6
# CR-008, R-06: {m,n} com n - m acima de AMPLITUDE_LARGA conta como ilimitado; com algum ilimitado,
# no maximo MAX_ESCOLHAS_COM_ILIMITADO quantificadores de escolha (pior caso medido < 0,2 s em 500 caracteres).
AMPLITUDE_LARGA = 10
MAX_ESCOLHAS_COM_ILIMITADO = 4
_CHECKBOX = {'true': True, '1': True, 'false': False, '0': False}
_RE_FLAG = re.compile(r'-{1,2}[A-Za-z0-9][A-Za-z0-9_-]{0,27}')
TAMANHO_OPCOES = 500
TAMANHO_CHAVE_OPCAO = 100
TAMANHO_ROTULO_OPCAO = 100

# Snapshot v4 (README §6.5, CR-005): path_file absoluto; sem pasta base nem executavel do no que compilou.
_CHAVES_SNAPSHOT = ('version', 'script_id', 'script_nome', 'interpreter', 'path_file', 'param_type',
                    'args', 'respostas', 'sensiveis', 'compilado_em')


class ParamErro(Exception):
    """Erro de validacao de um parametro; a mensagem e voltada ao usuario e nunca ecoa o valor."""

    def __init__(self, codigo_param, mensagem):
        Exception.__init__(self, mensagem)
        self.codigo_param = codigo_param
        self.mensagem = mensagem


class SnapshotErro(Exception):
    """Falha na pre-validacao do snapshot (PRECHECK_FAILED)."""

    def __init__(self, motivo):
        Exception.__init__(self, motivo)
        self.motivo = motivo


def _sensivel(parametro):
    return parametro.get('sensitive') == 'Y'


def _rotulo(parametro):
    return parametro.get('label') or parametro.get('code') or 'Parâmetro'


def _opcoes_select(parametro):
    try:
        opcoes = json.loads(parametro.get('options_json') or '')
    except ValueError:
        opcoes = None
    if not isinstance(opcoes, dict) or not opcoes:
        raise ParamErro(parametro.get('code'),
                        'O parâmetro "%s" está com as opções mal configuradas. Contate o administrador.'
                        % _rotulo(parametro))
    return opcoes


def validar_valor(parametro, valor_bruto):
    """Valida e normaliza um valor conforme tipo_componente (README §6.2); lanca ParamErro.

    CHECKBOX devolve bool; os demais tipos devolvem str normalizada.
    """
    codigo = parametro.get('code')
    rotulo = _rotulo(parametro)
    tipo = parametro.get('component_type')

    if tipo == 'CHECKBOX' and isinstance(valor_bruto, bool):
        return valor_bruto
    if not isinstance(valor_bruto, str):
        raise ParamErro(codigo, 'Valor inválido para "%s".' % rotulo)
    # Ordem do README §6.2: strip primeiro; controle so nas pontas ja foi removido.
    valor = valor_bruto.strip()
    if len(valor) > TAMANHO_MAXIMO:
        raise ParamErro(codigo, 'O campo "%s" excede o limite de %d caracteres.' % (rotulo, TAMANHO_MAXIMO))
    if _RE_CONTROLE.search(valor):
        raise ParamErro(codigo, 'O campo "%s" contém caracteres de controle não permitidos.' % rotulo)
    # Valor sigiloso curto nao pode ser mascarado com seguranca (README §4.1 e §6.2, CR-007 R-25).
    if _sensivel(parametro) and tipo != 'CHECKBOX' and 0 < len(valor) < SENSIVEL_MINIMO:
        raise ParamErro(codigo, 'O valor sigiloso precisa ter pelo menos %d caracteres.' % SENSIVEL_MINIMO)

    if tipo == 'TEXT':
        padrao = parametro.get('validation_regex')
        if padrao:
            try:
                casou = re.fullmatch(padrao, valor) is not None
            except re.error:
                raise ParamErro(codigo, 'O parâmetro "%s" está com a validação mal configurada. '
                                        'Contate o administrador.' % rotulo)
            if not casou:
                raise ParamErro(codigo, 'O campo "%s" não está no formato esperado.' % rotulo)
        return valor
    if tipo == 'NUMBER':
        if not _RE_NUMBER.match(valor):
            raise ParamErro(codigo, 'O campo "%s" deve ser um número (até 18 dígitos e 6 decimais).' % rotulo)
        return valor
    if tipo == 'DATE':
        try:
            data = datetime.datetime.strptime(valor, '%Y-%m-%d')
        except ValueError:
            raise ParamErro(codigo, 'O campo "%s" deve ser uma data válida no formato AAAA-MM-DD.' % rotulo)
        return data.strftime('%Y-%m-%d')
    if tipo == 'SELECT':
        if valor not in _opcoes_select(parametro):
            raise ParamErro(codigo, 'Selecione uma opção válida para "%s".' % rotulo)
        return valor
    if tipo == 'CHECKBOX':
        chave = valor.lower()
        if chave not in _CHECKBOX:
            raise ParamErro(codigo, 'O campo "%s" aceita apenas verdadeiro ou falso.' % rotulo)
        return _CHECKBOX[chave]
    raise ParamErro(codigo, 'O parâmetro "%s" tem um tipo de componente desconhecido.' % rotulo)


def _recusar_regex(motivo):
    raise ParamErro('validation_regex', 'A expressão regular foi recusada: %s (README §6.2).' % motivo)


def _fim_da_classe(padrao, i):
    """Indice logo depois do ']' que fecha a classe aberta em padrao[i] == '['."""
    j = i + 1
    if j < len(padrao) and padrao[j] == '^':
        j += 1
    if j < len(padrao) and padrao[j] == ']':
        j += 1
    while j < len(padrao):
        if padrao[j] == '\\':
            j += 2
            continue
        if padrao[j] == ']':
            return j + 1
        j += 1
    return len(padrao)


def validar_regex_cadastro(padrao):
    """Compila regex_validacao e exige o subconjunto seguro do README §6.2 (CR-007, D5); lanca ParamErro.

    Recusa grupo repetido por quantificador (exceto '?'), quantificador sobre quantificador, referencia a
    grupo, lookaround, grupo condicional, mais de MAX_ILIMITADOS quantificadores ilimitados (*, +, {n,} e
    {m,n} com n - m > AMPLITUDE_LARGA), mais de MAX_ESCOLHAS quantificadores que criam escolha (so
    MAX_ESCOLHAS_COM_ILIMITADO se houver ilimitado) e mais de TAMANHO_REGEX caracteres. Assim o fullmatch
    fica no maximo polinomial de grau 2 no tamanho do valor (CR-008, R-06).
    """
    try:
        re.compile(padrao)
    except Exception:  # noqa: B902 - re.error, TypeError e erros internos do sre (ex.: grupo condicional invalido)
        raise ParamErro('validation_regex', 'A expressão regular é inválida.')
    if len(padrao) > TAMANHO_REGEX:
        _recusar_regex('tem mais de %d caracteres' % TAMANHO_REGEX)
    ilimitados = 0
    escolhas = 0
    atomo = None          # 'simples' (caractere, escape, classe, '.'), 'grupo' ou None
    apos_quant = False    # o ultimo token foi um quantificador
    preguicoso = False    # e ele ja recebeu o modificador '?'
    i = 0
    n = len(padrao)
    while i < n:
        c = padrao[i]
        if c == '\\':
            prox = padrao[i + 1:i + 2]
            if prox.isdigit() and prox != '0':
                _recusar_regex('referência a grupo (\\%s) não é permitida' % prox)
            atomo, apos_quant, i = 'simples', False, i + 2
            continue
        if c == '[':
            atomo, apos_quant, i = 'simples', False, _fim_da_classe(padrao, i)
            continue
        if c == '(':
            resto = padrao[i + 1:i + 5]
            if resto.startswith(('?=', '?!', '?<=', '?<!')):
                _recusar_regex('lookahead e lookbehind não são permitidos')
            if resto.startswith('?('):
                _recusar_regex('grupo condicional não é permitido')
            if resto.startswith('?P='):
                _recusar_regex('referência a grupo não é permitida')
            atomo, apos_quant, i = None, False, i + 1
            continue
        if c == ')':
            atomo, apos_quant, i = 'script_group', False, i + 1
            continue
        if c == '|':
            atomo, apos_quant, i = None, False, i + 1
            continue
        quant = None
        if c in '*+?':
            quant, fim = c, i + 1
        elif c == '{':
            m = _RE_QUANT_CHAVE.match(padrao, i)
            if m and (m.group(1) or m.group(3)):
                quant, fim = m.group(0), m.end()
        if quant is None:
            # '{' literal, '^', '$', '.' e demais caracteres.
            atomo = None if c in '^$' else 'simples'
            apos_quant, i = False, i + 1
            continue
        if apos_quant:
            if quant == '?' and not preguicoso:
                preguicoso, i = True, fim
                continue
            _recusar_regex('quantificador aplicado a outro quantificador')
        if atomo == 'script_group' and quant not in ('?', '{0,1}'):
            _recusar_regex('grupo entre parênteses repetido por quantificador (use só ? depois de parênteses)')
        limites = quant[1:-1].split(',') if quant.startswith('{') else None
        largo = (limites is not None and len(limites) == 2 and limites[1] != ''
                 and int(limites[1]) - int(limites[0] or 0) > AMPLITUDE_LARGA)
        if quant in ('*', '+') or (quant.startswith('{') and quant.endswith(',}')) or largo:
            ilimitados += 1
            if ilimitados > MAX_ILIMITADOS:
                _recusar_regex('mais de %d quantificadores ilimitados (*, +, {n,} ou {m,n} com mais de %d de '
                               'diferença)' % (MAX_ILIMITADOS, AMPLITUDE_LARGA))
        if limites is None or len(limites) == 2 and limites[0] != limites[1]:
            # ?, *, + e {m,n} com m != n criam escolha; muitas escolhas seguidas explodem o tempo.
            escolhas += 1
            teto = MAX_ESCOLHAS_COM_ILIMITADO if ilimitados else MAX_ESCOLHAS
            if escolhas > teto:
                _recusar_regex('mais de %d quantificadores que criam escolha (?, *, + ou {m,n})%s'
                               % (teto, ' quando há quantificador ilimitado' if ilimitados else ''))
        apos_quant, preguicoso, i = True, False, fim


def validar_flag(flag):
    """Valida param_nomeado pela CK ck_tbsss_prm_flag (README §10 tabela 10); lanca ParamErro."""
    if not isinstance(flag, str) or not _RE_FLAG.fullmatch(flag):
        raise ParamErro('param_flag', 'Use uma flag como --data-ref ou -n (até 30 caracteres, '
                                         'letras, dígitos, _ e -).')


def _pares_sem_duplicata(pares):
    vistos = collections.OrderedDict()
    for chave, valor in pares:
        if chave in vistos:
            raise ValueError('chave duplicada')
        vistos[chave] = valor
    return vistos


def validar_opcoes_cadastro(texto):
    """Valida options_json de SELECT e devolve o JSON canonico (sort_order do usuario preservada).

    Exige objeto {"valor": "Rotulo"} nao vazio, sem chave duplicada, com chaves e rotulos str nao vazios
    (apos strip), sem caracteres de controle, e serializacao com ate TAMANHO_OPCOES caracteres.
    """
    if not isinstance(texto, str) or not texto.strip():
        raise ParamErro('options_json', 'Informe as opções da lista (pelo menos uma).')
    try:
        opcoes = json.loads(texto, object_pairs_hook=_pares_sem_duplicata)
    except ValueError:
        raise ParamErro('options_json', 'As opções não formam um JSON válido sem chaves repetidas.')
    if not isinstance(opcoes, dict) or not opcoes:
        raise ParamErro('options_json', 'As opções devem ser um objeto {"valor": "Rótulo"} com pelo menos um item.')
    limpas = collections.OrderedDict()
    for chave, rotulo in opcoes.items():
        if not isinstance(rotulo, str):
            raise ParamErro('options_json', 'Todo rótulo de opção deve ser texto.')
        chave, rotulo = chave.strip(), rotulo.strip()
        if not chave or not rotulo:
            raise ParamErro('options_json', 'Valores e rótulos das opções não podem ser vazios.')
        if _RE_CONTROLE.search(chave) or _RE_CONTROLE.search(rotulo):
            raise ParamErro('options_json', 'As opções contêm caracteres de controle não permitidos.')
        if len(chave) > TAMANHO_CHAVE_OPCAO or len(rotulo) > TAMANHO_ROTULO_OPCAO:
            raise ParamErro('options_json', 'Cada valor e rótulo de opção aceita até %d caracteres.'
                                           % TAMANHO_CHAVE_OPCAO)
        if chave in limpas:
            raise ParamErro('options_json', 'O valor "%s" aparece mais de uma vez.' % chave)
        limpas[chave] = rotulo
    canonico = json.dumps(limpas, ensure_ascii=False, separators=(',', ':'))
    if len(canonico) > TAMANHO_OPCOES:
        raise ParamErro('options_json', 'As opções excedem %d caracteres; reduza a lista ou os rótulos.'
                                       % TAMANHO_OPCOES)
    return canonico


def _ordenados(vinculos):
    return sorted(vinculos, key=lambda v: int(v['sort_order']))


def _vazio(valor):
    return valor is None or (isinstance(valor, str) and valor.strip() == '')


def _resolver(vinculos, respostas):
    """Aplica a precedencia (README §6.1) acumulando os erros por campo."""
    respostas = respostas or {}
    resolvidos = collections.OrderedDict()
    erros = collections.OrderedDict()
    for v in _ordenados(vinculos):
        codigo = v['code']
        valor = None
        try:
            for fonte in (respostas.get(codigo), v.get('default_value_override'), v.get('default_value')):
                if not _vazio(fonte):
                    valor = validar_valor(v, fonte)
                    break
            if valor is None and v.get('required') == 'Y':
                raise ParamErro(codigo, 'O campo "%s" é obrigatório.' % _rotulo(v))
        except ParamErro as e:
            erros[codigo] = e.mensagem
            valor = None
        resolvidos[codigo] = valor
    return resolvidos, erros


def resolver_respostas(vinculos, respostas):
    """Resolve o valor final de cada vinculo (OrderedDict codigo -> valor | None); lanca ParamErro."""
    resolvidos, erros = _resolver(vinculos, respostas)
    for codigo, mensagem in erros.items():
        raise ParamErro(codigo, mensagem)
    return resolvidos


def _args_nomeado(v, valor):
    codigo = v['code']
    flag = v.get('param_flag')
    if not flag:
        raise ParamErro(codigo, 'O parâmetro "%s" não tem flag configurada para script NOMEADO.' % _rotulo(v))
    if v.get('component_type') == 'CHECKBOX':
        return [flag] if valor is True else []
    if valor is None:
        return []
    if flag[:2] == '--':
        if valor[:1] == '-':
            return [flag + '=' + valor]
        return [flag, valor]
    if valor[:1] == '-':
        raise ParamErro(codigo, 'O campo "%s" não pode começar com "-".' % _rotulo(v))
    return [flag, valor]


def _arg_sequencial(v, valor):
    if valor is None:
        return ''
    if v.get('component_type') == 'CHECKBOX':
        return '1' if valor else '0'
    if valor[:1] == '-' and v.get('component_type') != 'NUMBER':
        raise ParamErro(v['code'], 'O campo "%s" não pode começar com "-".' % _rotulo(v))
    return valor


def _montar(tipo_param, vinculos, resolvidos, erros):
    """Monta args acumulando erros; erros estruturais vao em CHAVE_GERAL."""
    args = []
    if tipo_param == 'NONE':
        if vinculos:
            erros[CHAVE_GERAL] = 'Scripts sem parâmetros (NENHUM) não podem ter parâmetros vinculados.'
        return args
    if tipo_param not in ('NAMED', 'POSITIONAL'):
        erros[CHAVE_GERAL] = 'Estratégia de parâmetros do script é desconhecida.'
        return args
    for v in _ordenados(vinculos):
        codigo = v['code']
        if codigo in erros:
            continue
        valor = resolvidos.get(codigo)
        try:
            if tipo_param == 'NAMED':
                args.extend(_args_nomeado(v, valor))
            else:
                args.append(_arg_sequencial(v, valor))
        except ParamErro as e:
            erros[codigo] = e.mensagem
    return args


def montar_args(tipo_param, vinculos, resolvidos):
    """Monta a lista de argumentos conforme a estrategia (README §6.3); lanca ParamErro."""
    erros = collections.OrderedDict()
    args = _montar(tipo_param, vinculos, resolvidos, erros)
    for codigo, mensagem in erros.items():
        raise ParamErro(None if codigo == CHAVE_GERAL else codigo, mensagem)
    return args


def montar_argv_agente(interpretador, executavel, script_real, args):
    """argv real montado no agente (README §6.4): executavel local + argumentos fixos + script + args.

    Lanca PathGuardErro se o interpretador logico estiver fora da allowlist.
    """
    path_guard.validar_interpretador(interpretador)
    return [executavel] + list(path_guard.ARGS_FIXOS[interpretador]) + [script_real] + list(args)


def compilar_snapshot(script, vinculos, respostas, agora):
    """Compila o snapshot v4 (README §6.5) -> (json_str | None, resolvidos, erros_por_campo).

    Guarda o interpretador logico, o path_file absoluto e apenas os argumentos: o argv real e montado
    pelo agente com o proprio executavel. Erros sao acumulados.
    """
    resolvidos, erros = _resolver(vinculos, respostas)
    args = _montar(script['param_type'], vinculos, resolvidos, erros)
    try:
        path_guard.validar_interpretador(script['interpreter'])
    except path_guard.PathGuardErro:
        erros[CHAVE_GERAL] = 'O interpretador do script não é permitido.'
    if erros:
        return None, resolvidos, erros

    obj = {
        'version': VERSAO_SNAPSHOT,
        'script_id': script['id'],
        'script_nome': script['name'],
        'interpreter': script['interpreter'],
        'path_file': script['path_file'],
        'param_type': script['param_type'],
        'args': args,
        'respostas': dict(resolvidos),
        'sensiveis': sorted(v['code'] for v in vinculos if _sensivel(v)),
        'compilado_em': agora.strftime('%Y-%m-%d %H:%M:%S'),
    }
    return json.dumps(obj, ensure_ascii=False, sort_keys=True), resolvidos, erros


def validar_snapshot(json_str, cfg):
    """Pre-valida o snapshot no claim (README §8.4 passo 1) e devolve (snap, argv_real, script_real);
    lanca SnapshotErro. script_real (o path_file resolvido) alimenta o SSS_SCRIPT_DIR do env_builder.

    cfg expoe interpretadores (dict logico -> executavel do agente) e, opcional, dirs_sss (log_dir, work_dir e
    exec_work_dir, onde nenhum script pode ficar).
    Status e homologacao do script ficam a cargo do chamador.
    """
    try:
        snap = json.loads(json_str)
    except (TypeError, ValueError):
        raise SnapshotErro('JSON_INVALIDO')
    if not isinstance(snap, dict) or any(k not in snap for k in _CHAVES_SNAPSHOT):
        raise SnapshotErro('ESTRUTURA_INVALIDA')
    if snap['version'] != VERSAO_SNAPSHOT:
        raise SnapshotErro('VERSAO_NAO_SUPORTADA')
    interpretador = snap['interpreter']
    if interpretador not in path_guard.ALLOWLIST:
        raise SnapshotErro('INTERPRETADOR_NAO_PERMITIDO')
    executavel = (cfg.interpreters or {}).get(interpretador)
    if not executavel:
        raise SnapshotErro('INTERPRETADOR_NAO_DISPONIVEL')
    args = snap['args']
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise SnapshotErro('ARGS_INVALIDOS')
    # Defesa em profundidade (CR-007, R-32): o snapshot vem do banco; NUL ou controle nunca chegam ao argv.
    if any(_RE_CONTROLE.search(a) for a in args):
        raise SnapshotErro('ARGS_INVALIDOS')

    try:
        real = path_guard.resolver(snap['path_file'], dirs_sss=getattr(cfg, 'dirs_sss', None) or ())
    except path_guard.PathGuardErro as e:
        raise SnapshotErro('PATH_GUARD_' + e.codigo)
    return snap, montar_argv_agente(interpretador, executavel, real, args), real


def _segredos(snapshot):
    respostas = snapshot.get('respostas') or {}
    segredos = set()
    for codigo in snapshot.get('sensiveis') or []:
        valor = respostas.get(codigo)
        if isinstance(valor, str) and valor != '':
            segredos.add(valor)
    return segredos


def _mascarar_args(args, segredos):
    exibidos = []
    for token in args:
        if token in segredos:
            token = MASCARA
        elif token[:2] == '--' and '=' in token:
            flag, valor = token.split('=', 1)
            if valor in segredos:
                token = flag + '=' + MASCARA
        exibidos.append(token)
    return exibidos


def argv_para_exibicao(snapshot):
    """argv logico para a UI: interpretador, argumentos fixos, script e args com sensiveis em '****'.

    O caminho do script vai completo para todos (README §6.4, CR-005 D8).
    Conservador: qualquer argumento igual a um valor sensivel e mascarado.
    """
    interpretador = snapshot['interpreter']
    return ([interpretador] + list(path_guard.ARGS_FIXOS.get(interpretador, ())) + [snapshot['path_file']]
            + _mascarar_args(list(snapshot['args']), _segredos(snapshot)))
