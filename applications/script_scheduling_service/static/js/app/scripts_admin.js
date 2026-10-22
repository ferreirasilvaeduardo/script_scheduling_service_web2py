/* SSS - cadastro de scripts: homologacao por ambiente e vinculo ordenado de parametros (README §6.3).
 * Carregado com defer ANTES do alpine.min.js. Listas montadas aqui sao conveniencia: o servidor
 * revalida tudo (IDs, ativos, duplicidade, flags, valores padrao) e renumera a ordem.
 */
(function () {
  'use strict';

  function readJson(el, attribute, defaultValue) {
    try {
      return JSON.parse(el.getAttribute(attribute) || '');
    } catch (error) {
      return defaultValue;
    }
  }

  // O build CSP do Alpine nao avalia concatenacao nem ternario no HTML: derivados ficam na propria linha.
  function linkRow(data) {
    var l = {
      id: data.id, code: data.code, label: data.label, flag: data.flag, sensitive: data.sensitive === true,
      active: data.active !== false, required: data.required === true, sub: data.sub || '',
      hasSub: data.hasSub === true
    };
    l.idReq = 'req-' + l.id;
    l.typeSub = l.sensitive ? 'password' : 'text';
    refreshSecret(l);
    l.upLabel = 'Subir ' + l.code;
    l.downLabel = 'Descer ' + l.code;
    l.removeLabel = 'Remover ' + l.code;
    return l;
  }

  // Valor sigiloso gravado: em branco mantem; "Remover valor" apaga sem remover o vinculo (README §6.5).
  function refreshSecret(l) {
    l.canClear = l.sensitive && l.hasSub;
    l.hintSub = l.canClear ? 'Valor sigiloso gravado (em branco mantém)' : 'Valor padrão específico (opcional)';
  }

  function boxes(root, selector) {
    return Array.prototype.slice.call(root.querySelectorAll(selector));
  }

  document.addEventListener('alpine:init', function () {
    // Homologacao: resumo +/- e aviso de agendamentos afetados pelos ambientes removidos.
    window.Alpine.data('scriptHomologation', function () {
      return {
        summary: [],
        affected: 0,
        get noChanges() {
          return this.summary.length === 0;
        },
        get hasChanges() {
          return this.summary.length > 0;
        },
        get hasAffected() {
          return this.affected > 0;
        },
        get affectedWarning() {
          return this.affected + ' agendamento(s) ativo(s) nos ambientes removidos serão pausados no próximo ciclo.';
        },
        init: function () {
          this.refresh();
        },
        refresh: function () {
          var more = [];
          var less = [];
          var affected = 0;
          boxes(this.$root, 'input[type="checkbox"][name="environments"]').forEach(function (cx) {
            var initial = cx.getAttribute('data-initial') === 'Y';
            if (cx.disabled || cx.checked === initial) {
              return;
            }
            if (cx.checked) {
              more.push('+' + cx.getAttribute('data-name'));
            } else {
              less.push('-' + cx.getAttribute('data-name'));
              affected += parseInt(cx.getAttribute('data-schedules'), 10) || 0;
            }
          });
          more.sort();
          less.sort();
          this.summary = more.concat(less);
          this.affected = affected;
        }
      };
    });

    // Vinculos: lista ordenavel (subir/descer, sem arrastar), busca no dicionario e previa do argv.
    window.Alpine.data('scriptLinks', function () {
      return {
        rows: [],
        available: [],
        term: '',
        previewText: '',
        previewErrors: [],
        previewWarning: '',
        loading: false,

        init: function () {
          var root = this.$root;
          this.available = readJson(root, 'data-available', []);
          this.rows = readJson(root, 'data-links', []).map(function (v) {
            return linkRow({ id: v.id, code: v.code, label: v.label, flag: v.param_flag,
                                  sensitive: v.sensitive, active: v.active, required: v.required,
                                  sub: v.default_value_override, hasSub: v.has_override });
          });
        },

        get linksJson() {
          return JSON.stringify(this.rows.map(function (l) {
            return {
              parameter_id: l.id, required: l.required, default_value_override: l.sub,
              keep_secret: l.sensitive && l.hasSub && !l.sub
            };
          }));
        },
        get results() {
          var term = this.term.trim().toLowerCase();
          var used = {};
          this.rows.forEach(function (l) { used[l.id] = true; });
          return this.available.filter(function (p) {
            if (used[p.id]) {
              return false;
            }
            return !term || (p.code + ' ' + p.label).toLowerCase().indexOf(term) !== -1;
          }).slice(0, 15);
        },
        get noLinks() {
          return this.rows.length === 0;
        },
        get noResults() {
          return this.results.length === 0;
        },
        get hasPreview() {
          return this.previewText !== '';
        },
        get hasErrorsPreview() {
          return this.previewErrors.length > 0;
        },
        get hasWarningPreview() {
          return this.previewWarning !== '';
        },

        index: function (evt) {
          return parseInt(evt.currentTarget.getAttribute('data-i'), 10);
        },
        search: function (evt) {
          this.term = evt.target.value;
        },
        add: function (evt) {
          var id = parseInt(evt.currentTarget.getAttribute('data-id'), 10);
          var p = this.available.filter(function (d) { return d.id === id; })[0];
          if (p) {
            this.rows.push(linkRow({ id: p.id, code: p.code, label: p.label, flag: p.param_flag,
                                            sensitive: p.sensitive, active: true, required: false }));
          }
        },
        move: function (evt) {
          var i = this.index(evt);
          var target = i + parseInt(evt.currentTarget.getAttribute('data-delta'), 10);
          var row;
          if (target < 0 || target >= this.rows.length) {
            return;
          }
          row = this.rows.splice(i, 1)[0];
          this.rows.splice(target, 0, row);
        },
        remove: function (evt) {
          this.rows.splice(this.index(evt), 1);
        },
        clearSecret: function (evt) {
          var l = this.rows[this.index(evt)];
          l.hasSub = false;
          l.sub = '';
          refreshSecret(l);
        },
        toggleRequired: function (evt) {
          this.rows[this.index(evt)].required = evt.currentTarget.checked;
        },
        editSub: function (evt) {
          this.rows[this.index(evt)].sub = evt.currentTarget.value;
        },

        preview: function () {
          var self = this;
          var form = this.$root;
          var body = new URLSearchParams();
          body.set('_csrf', form.querySelector('input[name="_csrf"]').value);
          body.set('id', form.querySelector('input[name="id"]').value);
          body.set('links_json', this.linksJson);
          this.loading = true;
          this.previewText = '';
          this.previewErrors = [];
          this.previewWarning = '';
          window.SSS.fetch(form.getAttribute('data-url-preview'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: body.toString()
          }).then(function (response) {
            return response.json();
          }).then(function (r) {
            var key;
            if (r.argv) {
              self.previewText = r.argv.join(' ');
            }
            for (key in (r.errors || {})) {
              if (Object.prototype.hasOwnProperty.call(r.errors, key)) {
                self.previewErrors.push(r.errors[key]);
              }
            }
            self.previewWarning = r.warning || '';
          }).catch(function () {
            self.previewErrors = ['Não foi possível gerar a prévia agora. Tente novamente.'];
          }).then(function () {
            self.loading = false;
          });
        }
      };
    });
  });
}());
