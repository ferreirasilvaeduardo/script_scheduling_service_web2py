/* SSS - cadastro de scripts: homologacao por ambiente e vinculo ordenado de parametros (README §6.3).
 * Listas montadas aqui sao conveniencia: o servidor revalida tudo (IDs, ativos, duplicidade, flags,
 * valores padrao) e renumera a ordem.
 */
(function () {
  'use strict';

  var SSS = window.SSS;
  var dom = SSS.dom;
  var MAX_RESULTS = 15;

  function readJson(el, attribute, defaultValue) {
    try {
      return JSON.parse(el.getAttribute(attribute) || '');
    } catch (error) {
      return defaultValue;
    }
  }

  function boxes(root, selector) {
    return Array.prototype.slice.call(root.querySelectorAll(selector));
  }

  function linkRow(data) {
    return {
      id: data.id, code: data.code, label: data.label, flag: data.flag, sensitive: data.sensitive === true,
      active: data.active !== false, required: data.required === true, sub: data.sub || '',
      hasSub: data.hasSub === true
    };
  }

  // Valor sigiloso gravado: em branco mantem; "Remover valor" apaga sem remover o vinculo (README §6.5).
  function canClear(row) {
    return row.sensitive && row.hasSub;
  }

  // Homologacao: resumo +/- e aviso de agendamentos afetados pelos ambientes removidos.
  SSS.component('scriptHomologation', function (root) {
    var el = {
      noChanges: dom.ref(root, 'noChanges'),
      summary: dom.ref(root, 'summary'),
      affected: dom.ref(root, 'affected'),
      affectedText: dom.ref(root, 'affectedText'),
      save: dom.ref(root, 'save')
    };
    var modal = SSS.modal({
      modal: dom.ref(root, 'modal'),
      backdrop: dom.ref(root, 'backdrop'),
      initialFocus: dom.ref(root, 'cancel'),
      returnFocus: dom.ref(root, 'trigger')
    });

    function refresh() {
      var more = [];
      var less = [];
      var affected = 0;
      var rows;
      boxes(root, 'input[type="checkbox"][name="environments"]').forEach(function (cx) {
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
      rows = more.concat(less);
      dom.show(el.noChanges, rows.length === 0);
      dom.show(el.summary, rows.length > 0);
      dom.fillList(el.summary, rows);
      dom.show(el.affected, affected > 0);
      dom.setText(el.affectedText, affected + ' agendamento(s) ativo(s) nos ambientes removidos serão pausados no próximo ciclo.');
      el.save.disabled = rows.length === 0;
    }

    dom.on(root, 'change', 'refresh', refresh);
    dom.on(root, 'click', 'open', function () {
      refresh();
      modal.open();
    });
    dom.on(root, 'click', 'close', function () { modal.close(); });
    refresh();
  });

  // Vinculos: lista ordenavel (subir/descer, sem arrastar), busca no dicionario e previa do argv.
  SSS.component('scriptLinks', function (root) {
    var el = {
      linksJson: dom.ref(root, 'linksJson'),
      noLinks: dom.ref(root, 'noLinks'),
      rows: dom.ref(root, 'rows'),
      rowTemplate: dom.ref(root, 'rowTemplate'),
      search: dom.ref(root, 'search'),
      noResults: dom.ref(root, 'noResults'),
      results: dom.ref(root, 'results'),
      resultTemplate: dom.ref(root, 'resultTemplate'),
      previewButton: dom.ref(root, 'previewButton'),
      previewText: dom.ref(root, 'previewText'),
      previewErrors: dom.ref(root, 'previewErrors'),
      previewWarning: dom.ref(root, 'previewWarning'),
      submit: root.querySelector('button[type="submit"]')
    };
    var available = readJson(root, 'data-available', []);
    var rows = readJson(root, 'data-links', []).map(function (v) {
      return linkRow({ id: v.id, code: v.code, label: v.label, flag: v.param_flag, sensitive: v.sensitive,
                       active: v.active, required: v.required, sub: v.default_value_override,
                       hasSub: v.has_override });
    });

    function linksJson() {
      return JSON.stringify(rows.map(function (l) {
        return {
          parameter_id: l.id, required: l.required, default_value_override: l.sub,
          keep_secret: l.sensitive && l.hasSub && !l.sub
        };
      }));
    }

    function sync() {
      el.linksJson.value = linksJson();
    }

    function part(item, name) {
      return item.querySelector('[data-part="' + name + '"]');
    }

    function renderRows() {
      var fragment = document.createDocumentFragment();
      rows.forEach(function (row, i) {
        var item = dom.clone(el.rowTemplate);
        var required = part(item, 'required');
        var sub = part(item, 'sub');
        var clear = part(item, 'clear');
        dom.setText(part(item, 'code'), row.code);
        dom.setText(part(item, 'label'), row.label);
        dom.setText(part(item, 'flag'), row.flag);
        dom.show(part(item, 'flag'), !!row.flag);
        dom.show(part(item, 'sensitive'), row.sensitive);
        required.id = 'req-' + row.id;
        required.checked = row.required;
        part(item, 'requiredLabel').setAttribute('for', required.id);
        sub.type = row.sensitive ? 'password' : 'text';
        sub.value = row.sub;
        sub.placeholder = canClear(row) ? 'Valor sigiloso gravado (em branco mantém)' : 'Valor padrão específico (opcional)';
        dom.show(clear, canClear(row));
        part(item, 'up').setAttribute('aria-label', 'Subir ' + row.code);
        part(item, 'down').setAttribute('aria-label', 'Descer ' + row.code);
        part(item, 'remove').setAttribute('aria-label', 'Remover ' + row.code);
        boxes(item, '[data-action]').forEach(function (target) { target.setAttribute('data-i', i); });
        fragment.appendChild(item);
      });
      el.rows.replaceChildren(fragment);
      dom.show(el.noLinks, rows.length === 0);
      sync();
      renderResults();
    }

    function results() {
      var term = el.search ? el.search.value.trim().toLowerCase() : '';
      var used = {};
      rows.forEach(function (l) { used[l.id] = true; });
      return available.filter(function (p) {
        return !used[p.id] && (!term || (p.code + ' ' + p.label).toLowerCase().indexOf(term) !== -1);
      }).slice(0, MAX_RESULTS);
    }

    function renderResults() {
      var fragment = document.createDocumentFragment();
      var found;
      // Script sem argumentos (NONE) nao tem a busca.
      if (!el.results) {
        return;
      }
      found = results();
      found.forEach(function (p) {
        var item = dom.clone(el.resultTemplate);
        dom.setText(part(item, 'code'), p.code);
        dom.setText(part(item, 'label'), p.label);
        part(item, 'add').setAttribute('data-id', p.id);
        fragment.appendChild(item);
      });
      el.results.replaceChildren(fragment);
      dom.show(el.noResults, found.length === 0);
    }

    function index(target) {
      return parseInt(target.getAttribute('data-i'), 10);
    }

    function focusRow(i, action) {
      var target = el.rows.querySelector('[data-action="' + action + '"][data-i="' + i + '"]');
      (target || el.search || el.submit).focus();
    }

    // Digitar e marcar so atualizam o estado: redesenhar a lista tiraria o foco do campo.
    dom.on(root, 'change', 'toggleRequired', function (evt, target) {
      rows[index(target)].required = target.checked;
      sync();
    });
    dom.on(root, 'input', 'editSub', function (evt, target) {
      rows[index(target)].sub = target.value;
      sync();
    });
    dom.on(root, 'click', 'clearSecret', function (evt, target) {
      var i = index(target);
      rows[i].hasSub = false;
      rows[i].sub = '';
      renderRows();
      focusRow(i, 'editSub');
    });
    dom.on(root, 'click', 'move', function (evt, target) {
      var i = index(target);
      var to = i + parseInt(target.getAttribute('data-delta'), 10);
      var direction = target.getAttribute('data-delta');
      if (to < 0 || to >= rows.length) {
        return;
      }
      rows.splice(to, 0, rows.splice(i, 1)[0]);
      renderRows();
      el.rows.querySelector('[data-action="move"][data-delta="' + direction + '"][data-i="' + to + '"]').focus();
    });
    dom.on(root, 'click', 'remove', function (evt, target) {
      var i = index(target);
      rows.splice(i, 1);
      renderRows();
      focusRow(Math.min(i, rows.length - 1), 'remove');
    });
    dom.on(root, 'input', 'search', renderResults);
    dom.on(root, 'click', 'add', function (evt, target) {
      var id = parseInt(target.getAttribute('data-id'), 10);
      var p = available.filter(function (d) { return d.id === id; })[0];
      if (p) {
        rows.push(linkRow({ id: p.id, code: p.code, label: p.label, flag: p.param_flag,
                            sensitive: p.sensitive, active: true, required: false }));
        renderRows();
        el.search.focus();
      }
    });
    dom.on(root, 'click', 'preview', function () {
      var body = new URLSearchParams();
      var errors = [];
      body.set('_csrf', root.querySelector('input[name="_csrf"]').value);
      body.set('id', root.querySelector('input[name="id"]').value);
      body.set('links_json', linksJson());
      el.previewButton.disabled = true;
      dom.setText(el.previewText, '');
      dom.show(el.previewText, false);
      dom.fillList(el.previewErrors, []);
      dom.show(el.previewErrors, false);
      dom.setText(el.previewWarning, '');
      dom.show(el.previewWarning, false);
      SSS.fetch(root.getAttribute('data-url-preview'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body.toString()
      }).then(function (response) {
        return response.json();
      }).then(function (r) {
        var key;
        if (r.argv) {
          dom.setText(el.previewText, r.argv.join(' '));
          dom.show(el.previewText, true);
        }
        for (key in (r.errors || {})) {
          if (Object.prototype.hasOwnProperty.call(r.errors, key)) {
            errors.push(r.errors[key]);
          }
        }
        if (r.warning) {
          dom.setText(el.previewWarning, r.warning);
          dom.show(el.previewWarning, true);
        }
      }).catch(function () {
        errors = ['Não foi possível gerar a prévia agora. Tente novamente.'];
      }).then(function () {
        dom.fillList(el.previewErrors, errors);
        dom.show(el.previewErrors, errors.length > 0);
        el.previewButton.disabled = false;
      });
    });

    renderRows();
  });
}());
