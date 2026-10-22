/* SSS - tela de disparo de script (tickets/new).
 * Carregado com defer ANTES do alpine.min.js. Nenhuma regra decisoria fica aqui: o servidor
 * revalida tudo; o cliente apenas filtra a lista e exibe a previa devolvida pelo servidor.
 */
(function () {
  'use strict';

  var PARAM_PREFIX = 'p_';
  var RE_SIMPLE_TOKEN = /^[A-Za-z0-9_@%+=:,.\/-]+$/;

  function normalize(text) {
    return String(text || '').toLowerCase().replace(/^\s+|\s+$/g, '');
  }

  // Apenas para exibicao: o argv real e uma lista e nunca passa por shell.
  function displayToken(token) {
    if (RE_SIMPLE_TOKEN.test(token)) {
      return token;
    }
    return "'" + String(token).replace(/'/g, "'\\''") + "'";
  }

  // Ordem do DOM: o hidden "false" vem antes do checkbox, que so sobrescreve quando marcado.
  function collectAnswers(form) {
    var answers = {};
    var fields = form.elements;
    var i;
    var field;
    var code;
    for (i = 0; i < fields.length; i++) {
      field = fields[i];
      if (!field.name || field.name.indexOf(PARAM_PREFIX) !== 0 || field.disabled) {
        continue;
      }
      code = field.name.substring(PARAM_PREFIX.length);
      if (field.type === 'checkbox') {
        if (field.checked) {
          answers[code] = field.value;
        }
      } else {
        answers[code] = field.value;
      }
    }
    return answers;
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('scriptSearch', function () {
      return {
        noResult: false,
        filter: function () {
          var term = normalize(this.$refs.searchTerm.value);
          var groups = this.$root.querySelectorAll('[data-group]');
          var visibleTotal = 0;
          var g;
          var items;
          var i;
          var visible;
          var show;
          for (g = 0; g < groups.length; g++) {
            items = groups[g].querySelectorAll('[data-search]');
            visible = 0;
            for (i = 0; i < items.length; i++) {
              show = term === '' || items[i].getAttribute('data-search').indexOf(term) !== -1;
              items[i].hidden = !show;
              if (show) {
                visible++;
              }
            }
            groups[g].hidden = visible === 0;
            visibleTotal += visible;
          }
          this.noResult = visibleTotal === 0;
        }
      };
    });

    // Resumo em frase do modal de confirmacao (README §5.4): montado pelo servidor ao abrir o modal.
    window.Alpine.data('triggerSummary', function () {
      return {
        loading: false,
        script: '',
        environment: '',
        when: '',
        priority: '',
        command: '',
        answers: [],
        errors: [],
        get hasSummary() { return this.script !== ''; },
        get hasAnswers() { return this.answers.length > 0; },
        get hasErrors() { return this.errors.length > 0; },
        init: function () {
          var self = this;
          var form = this.$root.closest('form');
          var trigger = form.querySelector('[data-summary-trigger]');
          if (trigger) {
            trigger.addEventListener('click', function () { self.load(); });
          }
        },
        load: function () {
          var self = this;
          var form = this.$root.closest('form');
          var body = {
            script_id: form.elements.script_id.value,
            environment: form.elements.environment.value,
            priority: form.elements.priority ? form.elements.priority.value : '',
            scheduled_at: form.elements.scheduled_at ? form.elements.scheduled_at.value : '',
            answers: collectAnswers(form)
          };
          this.loading = true;
          this.script = '';
          this.errors = [];
          window.sssFetch(this.$root.getAttribute('data-url'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(body)
          }).then(function (response) {
            return response.json();
          }).then(function (data) {
            var key;
            if (data && data.summary) {
              self.script = data.summary.script;
              self.environment = data.summary.environment;
              self.when = data.summary.when;
              self.priority = String(data.summary.priority);
              self.answers = data.summary.answers.map(function (r, i) {
                return { id: i, label: r.label, value: String(r.value) };
              });
              self.command = (data.argv || []).map(displayToken).join(' ');
            } else {
              for (key in (data && data.errors) || {}) {
                if (Object.prototype.hasOwnProperty.call(data.errors, key)) {
                  self.errors.push({ id: self.errors.length, text: String(data.errors[key]) });
                }
              }
              if (!self.errors.length) {
                self.errors.push({ id: 0, text: (data && data.error) || 'Não foi possível montar o resumo.' });
              }
            }
          }).catch(function () {
            self.errors = [{ id: 0, text: 'Não foi possível montar o resumo. Tente novamente.' }];
          }).then(function () {
            self.loading = false;
          });
        }
      };
    });

    window.Alpine.data('preview', function () {
      return {
        loading: false,
        command: '',
        errors: [],
        get hasCommand() {
          return this.command !== '';
        },
        get hasErrors() {
          return this.errors.length > 0;
        },
        showErrors: function (map) {
          var listItems = [];
          var key;
          for (key in map) {
            if (Object.prototype.hasOwnProperty.call(map, key)) {
              listItems.push({ id: listItems.length, text: String(map[key]) });
            }
          }
          this.errors = listItems;
        },
        load: function () {
          var self = this;
          var form = this.$root.closest('form');
          var body = {
            script_id: form.elements.script_id.value,
            environment: form.elements.environment.value,
            answers: collectAnswers(form)
          };
          this.loading = true;
          this.command = '';
          this.errors = [];
          window.sssFetch(this.$root.getAttribute('data-url'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(body)
          }).then(function (response) {
            if (response.status === 403) {
              return null;
            }
            return response.json();
          }).then(function (data) {
            if (!data) {
              return;
            }
            if (data.argv) {
              self.command = data.argv.map(displayToken).join(' ');
            } else {
              self.showErrors(data.errors || {});
            }
          }).catch(function () {
            window.SSS.toast('error', 'Não foi possível gerar a prévia. Tente novamente.');
          }).then(function () {
            self.loading = false;
          });
        }
      };
    });
  });
}());
