/* SSS - matriz de permissoes do perfil (README §4.3).
 * Carregado com defer ANTES do alpine.min.js. Abas, contadores, "marcar todos", busca de scripts e o
 * resumo do modal. O resumo segue o formato do diff auditado (PERM_UPDATE); o servidor revalida tudo.
 */
(function () {
  'use strict';

  var DIMENSIONS = ['funcs', 'ambs', 'scrs'];

  function boxes(root, selector) {
    return Array.prototype.slice.call(root.querySelectorAll(selector));
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('permissionMatrix', function () {
      return {
        summary: [],
        tab: 'funcs',

        get noChanges() {
          return this.summary.length === 0;
        },
        get hasChanges() {
          return this.summary.length > 0;
        },
        get statusText() {
          if (!this.summary.length) {
            return 'Nenhuma alteração pendente.';
          }
          return this.summary.length === 1 ? '1 alteração pendente.' : this.summary.length + ' alterações pendentes.';
        },

        init: function () {
          this.showTab('funcs');
          this.refresh();
        },

        showTab: function (dim) {
          var root = this.$root;
          this.tab = dim;
          boxes(root, '[data-tab]').forEach(function (button) {
            var active = button.getAttribute('data-tab') === dim;
            button.classList.toggle('active', active);
            button.setAttribute('aria-selected', active ? 'true' : 'false');
            button.setAttribute('tabindex', active ? '0' : '-1');
          });
          boxes(root, '[data-panel]').forEach(function (panel) {
            panel.hidden = panel.getAttribute('data-panel') !== dim;
          });
        },
        openTab: function (evt) {
          this.showTab(evt.currentTarget.getAttribute('data-tab'));
        },

        refresh: function () {
          var root = this.$root;
          var rows = [];
          DIMENSIONS.forEach(function (dim) {
            var changes = [];
            var checked = 0;
            boxes(root, 'input[type="checkbox"][data-dim="' + dim + '"]').forEach(function (cx) {
              var initial = cx.getAttribute('data-initial') === 'Y';
              var label = cx.getAttribute('data-diff');
              if (cx.checked) {
                checked++;
              }
              if (cx.disabled || cx.checked === initial) {
                return;
              }
              changes.push({ label: label, sign: cx.checked ? '+' : '-' });
            });
            // Mesma ordem do servidor: por rotulo e depois sinal ('+' antes de '-').
            changes.sort(function (a, b) {
              if (a.label !== b.label) {
                return a.label < b.label ? -1 : 1;
              }
              return a.sign < b.sign ? -1 : (a.sign > b.sign ? 1 : 0);
            });
            changes.forEach(function (m) { rows.push(m.sign + m.label); });
            boxes(root, '[data-counter="' + dim + '"]').forEach(function (el) {
              el.textContent = String(checked);
            });
          });
          this.summary = rows;
        },

        markGroup: function (evt) {
          var group = evt.currentTarget.getAttribute('data-group');
          var set = this.$root.querySelector('fieldset[data-group="' + group + '"]');
          var editable = boxes(set, 'input[type="checkbox"]').filter(function (cx) {
            return !cx.disabled && !cx.closest('[hidden]');
          });
          var all = editable.length > 0 && editable.every(function (cx) { return cx.checked; });
          editable.forEach(function (cx) { cx.checked = !all; });
          this.refresh();
        },

        filterScripts: function (evt) {
          var term = String(evt.target.value || '').trim().toLowerCase();
          var panel = this.$root.querySelector('[data-panel="scrs"]');
          var any = false;
          boxes(panel, 'fieldset[data-group]').forEach(function (set) {
            var visible = 0;
            boxes(set, '[data-search]').forEach(function (item) {
              var ok = !term || item.getAttribute('data-search').indexOf(term) !== -1;
              item.hidden = !ok;
              if (ok) {
                visible++;
              }
            });
            set.hidden = visible === 0;
            if (visible) {
              any = true;
            }
          });
          panel.querySelector('[data-no-result]').hidden = any;
        }
      };
    });
  });
}());
