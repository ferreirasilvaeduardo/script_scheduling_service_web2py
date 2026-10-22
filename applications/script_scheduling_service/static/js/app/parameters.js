/* SSS - formulario do dicionario de parametros (README §6.2).
 * Carregado com defer ANTES do alpine.min.js. Campos condicionais por tipo, editor de pares
 * valor/rotulo (o JSON e montado so por conveniencia: o servidor faz json.loads e valida tudo) e
 * "Testar valor" contra a configuracao em edicao. A regex digitada nunca roda no navegador.
 */
(function () {
  'use strict';

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

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('parameterForm', function () {
      return {
        type: 'TEXT',
        sensitive: false,
        rows: [],
        edited: false,
        rawOptions: '',
        testing: false,
        testResult: '',
        testOk: null,

        init: function () {
          var initial;
          this.type = this.$refs.type.value;
          this.sensitive = this.$refs.sensitive.checked;
          this.rawOptions = this.$refs.options.getAttribute('value') || '';
          initial = initialOptions(this.$refs.options);
          this.rows = initial.rows;
          // JSON reapresentado invalido (apos erro) segue intacto ate o usuario editar a lista.
          this.edited = initial.valid;
          if (this.type === 'SELECT' && !this.rows.length) {
            this.rows.push({ value: '', label: '' });
          }
          this.adjustRegex();
        },

        get isSelect() {
          return this.type === 'SELECT';
        },
        get isText() {
          return this.type === 'TEXT';
        },
        get defaultType() {
          return this.sensitive ? 'password' : 'text';
        },
        get testClass() {
          if (this.testOk === null) {
            return '';
          }
          return this.testOk ? 'sss-test-ok' : 'sss-test-error';
        },
        get optionsJson() {
          var parts = [];
          if (!this.isSelect) {
            return '';
          }
          if (!this.edited) {
            return this.rawOptions;
          }
          // Montagem manual: objetos JS reordenam chaves numericas, e a ordem do usuario importa.
          this.rows.forEach(function (row) {
            var value = String(row.value || '');
            var label = String(row.label || '');
            if (value.trim() || label.trim()) {
              parts.push(JSON.stringify(value) + ':' + JSON.stringify(label));
            }
          });
          return parts.length ? '{' + parts.join(',') + '}' : '';
        },

        switchType: function (evt) {
          this.type = evt.target.value;
          if (this.isSelect && !this.rows.length) {
            this.rows.push({ value: '', label: '' });
          }
          this.clearTest();
          this.adjustRegex();
        },
        adjustRegex: function () {
          // Campo oculto pelo tipo nao e enviado: o servidor rejeitaria regex fora de Texto.
          var field = this.$root.querySelector('#field-validation_regex');
          if (field) {
            field.disabled = !this.isText;
          }
        },
        switchSensitive: function (evt) {
          this.sensitive = evt.target.checked;
        },
        editRow: function (evt) {
          var i = parseInt(evt.target.getAttribute('data-i'), 10);
          var field = evt.target.getAttribute('data-field');
          if (this.rows[i] && (field === 'value' || field === 'label')) {
            this.rows[i][field] = evt.target.value;
            this.edited = true;
          }
        },
        addRow: function () {
          this.rows.push({ value: '', label: '' });
          this.edited = true;
        },
        removeRow: function (evt) {
          var i = parseInt(evt.target.getAttribute('data-i'), 10);
          this.rows.splice(i, 1);
          this.edited = true;
        },
        clearTest: function () {
          this.testResult = '';
          this.testOk = null;
        },

        test: function () {
          var self = this;
          var form = this.$root;
          var body = new URLSearchParams();
          var data = new FormData(form);
          data.forEach(function (value, key) {
            if (key !== 'default_value') {
              body.append(key, value);
            }
          });
          body.set('options_json', this.optionsJson);
          body.set('test_value', this.$refs.testValue.value);
          this.testing = true;
          this.clearTest();
          window.SSS.fetch(form.getAttribute('data-url-test'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: body.toString()
          }).then(function (response) {
            return response.json();
          }).then(function (r) {
            self.testOk = r.ok === true;
            self.testResult = r.ok === true ? 'Válido. Valor normalizado: ' + r.value : (r.error || 'Valor inválido.');
          }).catch(function () {
            self.testOk = false;
            self.testResult = 'Não foi possível testar agora. Tente novamente.';
          }).then(function () {
            self.testing = false;
          });
        }
      };
    });
  });
}());
