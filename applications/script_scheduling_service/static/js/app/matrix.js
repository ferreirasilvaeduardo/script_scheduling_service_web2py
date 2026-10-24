/* SSS - matriz de permissoes do perfil (README §4.3).
 * Abas, contadores, "marcar todos", busca de scripts e o resumo do modal. O resumo segue o formato do
 * diff auditado (PERM_UPDATE); o servidor revalida tudo.
 */
(function () {
  'use strict';

  var SSS = window.SSS;
  var dom = SSS.dom;
  var DIMENSIONS = ['funcs', 'ambs', 'scrs'];

  function boxes(root, selector) {
    return Array.prototype.slice.call(root.querySelectorAll(selector));
  }

  SSS.component('permissionMatrix', function (root) {
    var el = {
      statusText: dom.ref(root, 'statusText'),
      noChanges: dom.ref(root, 'noChanges'),
      changes: dom.ref(root, 'changes'),
      summary: dom.ref(root, 'summary'),
      save: dom.ref(root, 'save')
    };
    var modal = SSS.modal({
      modal: dom.ref(root, 'modal'),
      backdrop: dom.ref(root, 'backdrop'),
      initialFocus: dom.ref(root, 'cancel'),
      returnFocus: dom.ref(root, 'trigger')
    });

    function showTab(dim) {
      boxes(root, '[data-tab]').forEach(function (button) {
        var active = button.getAttribute('data-tab') === dim;
        button.classList.toggle('active', active);
        button.setAttribute('aria-selected', active ? 'true' : 'false');
        button.setAttribute('tabindex', active ? '0' : '-1');
      });
      boxes(root, '[data-panel]').forEach(function (panel) {
        panel.hidden = panel.getAttribute('data-panel') !== dim;
      });
    }

    function summary() {
      var rows = [];
      DIMENSIONS.forEach(function (dim) {
        var changes = [];
        var checked = 0;
        boxes(root, 'input[type="checkbox"][data-dim="' + dim + '"]').forEach(function (cx) {
          var initial = cx.getAttribute('data-initial') === 'Y';
          if (cx.checked) {
            checked++;
          }
          if (cx.disabled || cx.checked === initial) {
            return;
          }
          changes.push({ label: cx.getAttribute('data-diff'), sign: cx.checked ? '+' : '-' });
        });
        // Mesma ordem do servidor: por rotulo e depois sinal ('+' antes de '-').
        changes.sort(function (a, b) {
          if (a.label !== b.label) {
            return a.label < b.label ? -1 : 1;
          }
          return a.sign < b.sign ? -1 : (a.sign > b.sign ? 1 : 0);
        });
        changes.forEach(function (m) { rows.push(m.sign + m.label); });
        boxes(root, '[data-counter="' + dim + '"]').forEach(function (counter) {
          dom.setText(counter, checked);
        });
      });
      return rows;
    }

    function refresh() {
      var rows = summary();
      var count = rows.length;
      dom.setText(el.statusText, count === 0 ? 'Nenhuma alteração pendente.'
        : (count === 1 ? '1 alteração pendente.' : count + ' alterações pendentes.'));
      dom.show(el.noChanges, count === 0);
      dom.show(el.changes, count > 0);
      dom.fillList(el.summary, rows);
      el.save.disabled = count === 0;
    }

    dom.on(root, 'click', 'openTab', function (evt, button) {
      showTab(button.getAttribute('data-tab'));
    });
    dom.on(root, 'change', 'refresh', refresh);
    dom.on(root, 'click', 'markGroup', function (evt, button) {
      var set = root.querySelector('fieldset[data-group="' + button.getAttribute('data-group') + '"]');
      var editable = boxes(set, 'input[type="checkbox"]').filter(function (cx) {
        return !cx.disabled && !cx.closest('[hidden]');
      });
      var all = editable.length > 0 && editable.every(function (cx) { return cx.checked; });
      editable.forEach(function (cx) { cx.checked = !all; });
      refresh();
    });
    dom.on(root, 'input', 'filterScripts', function (evt, input) {
      var term = String(input.value || '').trim().toLowerCase();
      var panel = root.querySelector('[data-panel="scrs"]');
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
    });
    dom.on(root, 'click', 'open', function () {
      refresh();
      modal.open();
    });
    dom.on(root, 'click', 'close', function () { modal.close(); });

    showTab('funcs');
    refresh();
  });
}());
