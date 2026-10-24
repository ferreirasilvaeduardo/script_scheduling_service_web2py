/* SSS - formulario do dicionario de parametros (README §6.2).
 * Campos condicionais por tipo, editor de pares valor/rotulo (o JSON e montado so por conveniencia: o
 * servidor faz json.loads e valida tudo) e "Testar valor" contra a configuracao em edicao. A regex
 * digitada nunca roda no navegador.
 */
(function () {
  'use strict';

  var SSS = window.SSS;
  var dom = SSS.dom;
  var TEST_CLASSES = { ok: 'sss-test-ok', error: 'sss-test-error' };

  // O servidor entrega as opcoes como lista de pares [valor, rotulo]: JSON.parse de um objeto
  // reordenaria chaves numericas ("2" antes de "1" viraria "1", "2").
  function initialOptions(field) {
    var pairs;
    var raw = field.getAttribute('data-pairs');
    if (!raw) {
      return { rows: [], valid: !field.getAttribute('value') };
    }
    try {
      pairs = JSON.parse(raw);
    } catch (error) {
      return { rows: [], valid: false };
    }
    if (!Array.isArray(pairs)) {
      return { rows: [], valid: false };
    }
    return {
      rows: pairs.map(function (pair) {
        return { value: String(pair[0]), label: typeof pair[1] === 'string' ? pair[1] : '' };
      }),
      valid: true
    };
  }

  SSS.component('parameterForm', function (root) {
    var el = {
      type: dom.ref(root, 'type'),
      sensitive: dom.ref(root, 'sensitive'),
      options: dom.ref(root, 'options'),
      optionsBox: dom.ref(root, 'optionsBox'),
      optionRows: dom.ref(root, 'optionRows'),
      optionRow: dom.ref(root, 'optionRow'),
      addOption: dom.ref(root, 'addOption'),
      regexBox: dom.ref(root, 'regexBox'),
      regex: root.querySelector('#field-validation_regex'),
      sensitiveWarning: dom.ref(root, 'sensitiveWarning'),
      defaultValue: dom.ref(root, 'defaultValue'),
      testValue: dom.ref(root, 'testValue'),
      testButton: dom.ref(root, 'testButton'),
      testResult: dom.ref(root, 'testResult')
    };
    // Lido antes da primeira sincronizacao: em input hidden, mudar .value tambem muda o atributo.
    var rawOptions = el.options.getAttribute('value') || '';
    var initial = initialOptions(el.options);
    var rows = initial.rows;
    // JSON reapresentado invalido (apos erro) segue intacto ate o usuario editar a lista.
    var edited = initial.valid;

    function isSelect() {
      return el.type.value === 'SELECT';
    }

    function optionsJson() {
      var parts = [];
      if (!isSelect()) {
        return '';
      }
      if (!edited) {
        return rawOptions;
      }
      // Montagem manual: objetos JS reordenam chaves numericas, e a ordem do usuario importa.
      rows.forEach(function (row) {
        var value = String(row.value || '');
        var label = String(row.label || '');
        if (value.trim() || label.trim()) {
          parts.push(JSON.stringify(value) + ':' + JSON.stringify(label));
        }
      });
      return parts.length ? '{' + parts.join(',') + '}' : '';
    }

    function syncOptions() {
      el.options.value = optionsJson();
    }

    function renderRows() {
      var fragment = document.createDocumentFragment();
      rows.forEach(function (row, index) {
        var item = dom.clone(el.optionRow);
        var value = item.querySelector('[data-field="value"]');
        var label = item.querySelector('[data-field="label"]');
        value.value = row.value;
        label.value = row.label;
        value.setAttribute('data-i', index);
        label.setAttribute('data-i', index);
        item.querySelector('[data-action="removeRow"]').setAttribute('data-i', index);
        fragment.appendChild(item);
      });
      el.optionRows.replaceChildren(fragment);
      syncOptions();
    }

    function renderType() {
      var text = el.type.value === 'TEXT';
      dom.show(el.optionsBox, isSelect());
      dom.show(el.regexBox, text);
      // Campo oculto pelo tipo nao e enviado: o servidor rejeitaria regex fora de Texto.
      if (el.regex) {
        el.regex.disabled = !text;
      }
      syncOptions();
    }

    function renderSensitive() {
      dom.show(el.sensitiveWarning, el.sensitive.checked);
      el.defaultValue.type = el.sensitive.checked ? 'password' : 'text';
    }

    function showTest(ok, message) {
      el.testResult.classList.remove(TEST_CLASSES.ok, TEST_CLASSES.error);
      if (ok !== null) {
        el.testResult.classList.add(ok ? TEST_CLASSES.ok : TEST_CLASSES.error);
      }
      dom.setText(el.testResult, message);
    }

    function ensureOneRow() {
      if (isSelect() && !rows.length) {
        rows.push({ value: '', label: '' });
        renderRows();
      }
    }

    function index(target) {
      return parseInt(target.getAttribute('data-i'), 10);
    }

    dom.on(root, 'change', 'switchType', function () {
      ensureOneRow();
      showTest(null, '');
      renderType();
    });
    dom.on(root, 'change', 'switchSensitive', renderSensitive);
    // Digitar so atualiza o estado: redesenhar a lista tiraria o foco do campo.
    dom.on(root, 'input', 'editRow', function (evt, target) {
      var i = index(target);
      var field = target.getAttribute('data-field');
      if (rows[i] && (field === 'value' || field === 'label')) {
        rows[i][field] = target.value;
        edited = true;
        syncOptions();
      }
    });
    dom.on(root, 'click', 'addRow', function () {
      rows.push({ value: '', label: '' });
      edited = true;
      renderRows();
    });
    dom.on(root, 'click', 'removeRow', function (evt, target) {
      var i = index(target);
      var next;
      rows.splice(i, 1);
      edited = true;
      renderRows();
      // O botao clicado saiu da pagina: o foco vai para o Remover que ocupou o lugar, ou para Adicionar.
      next = el.optionRows.querySelector('[data-action="removeRow"][data-i="' + Math.min(i, rows.length - 1) + '"]');
      (next || el.addOption).focus();
    });
    dom.on(root, 'click', 'test', function () {
      var body = new URLSearchParams();
      new FormData(root).forEach(function (value, key) {
        if (key !== 'default_value') {
          body.append(key, value);
        }
      });
      body.set('options_json', optionsJson());
      body.set('test_value', el.testValue.value);
      el.testButton.disabled = true;
      showTest(null, '');
      SSS.fetch(root.getAttribute('data-url-test'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body.toString()
      }).then(function (response) {
        return response.json();
      }).then(function (r) {
        showTest(r.ok === true, r.ok === true ? 'Válido. Valor normalizado: ' + r.value : (r.error || 'Valor inválido.'));
      }).catch(function () {
        showTest(false, 'Não foi possível testar agora. Tente novamente.');
      }).then(function () {
        el.testButton.disabled = false;
      });
    });

    renderRows();
    ensureOneRow();
    renderType();
    renderSensitive();
  });
}());
