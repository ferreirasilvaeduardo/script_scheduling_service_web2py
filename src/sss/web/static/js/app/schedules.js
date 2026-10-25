/* SSS - formulario de regra de agendamento (schedules/form).
 * Nenhuma regra decisoria fica aqui: os campos condicionais so ajudam o preenchimento e a previa e
 * calculada pelo servidor (recurrence.py). Cada bloco condicional declara em data-types os tipos de
 * recorrencia em que aparece.
 */
(function () {
  'use strict';

  var SSS = window.SSS;
  var dom = SSS.dom;
  var DEBOUNCE_MS = 500;
  var FIELDS = ['recurrence_type', 'start_date', 'end_date', 'run_time', 'month_day', 'cron_expression'];

  function value(form, name) {
    var field = form.elements[name];
    return field && typeof field.value === 'string' ? field.value : '';
  }

  // Checkboxes seg-dom -> '1,3,5' (ISO 1-7, README §7.2).
  function weekDays(form) {
    var checked = form.querySelectorAll('input[name="week_days"]:checked');
    var days = [];
    var i;
    for (i = 0; i < checked.length; i++) {
      days.push(checked[i].value);
    }
    return days.join(',');
  }

  function mapValues(map) {
    var values = [];
    var key;
    for (key in map) {
      if (Object.prototype.hasOwnProperty.call(map, key)) {
        values.push(String(map[key]));
      }
    }
    return values;
  }

  SSS.component('scheduleRule', function (root) {
    var el = {
      type: dom.ref(root, 'type'),
      fields: dom.ref(root, 'fields'),
      loading: dom.ref(root, 'loading'),
      description: dom.ref(root, 'description'),
      descriptionText: dom.ref(root, 'descriptionText'),
      dates: dom.ref(root, 'dates'),
      errors: dom.ref(root, 'errors')
    };
    var conditional = Array.prototype.slice.call(root.querySelectorAll('[data-types]'));
    var timer = null;
    var sequence = 0;

    function renderType() {
      var type = el.type.value;
      conditional.forEach(function (block) {
        dom.show(block, block.getAttribute('data-types').split(' ').indexOf(type) !== -1);
      });
    }

    function renderPreview(description, dates, errors) {
      dom.setText(el.descriptionText, description);
      dom.show(el.description, description !== '');
      dom.fillList(el.dates, dates);
      dom.show(el.dates, dates.length > 0);
      dom.fillList(el.errors, errors);
      dom.show(el.errors, errors.length > 0);
    }

    function load() {
      var body = { week_days: weekDays(root) };
      var i;
      // Respostas fora de ordem sao descartadas: so a ultima requisicao atualiza a tela.
      var number = ++sequence;
      for (i = 0; i < FIELDS.length; i++) {
        body[FIELDS[i]] = value(root, FIELDS[i]);
      }
      dom.show(el.loading, true);
      SSS.fetch(root.getAttribute('data-url-preview'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(body)
      }).then(function (response) {
        if (response.status === 403) {
          return null;
        }
        return response.json();
      }).then(function (data) {
        if (!data || number !== sequence) {
          return;
        }
        renderPreview(data.description || '', (data.dates || []).map(String), mapValues(data.errors || {}));
      }).catch(function () {
        if (number === sequence) {
          SSS.toast('error', 'Não foi possível calcular a prévia. Tente novamente.');
        }
      }).then(function () {
        if (number === sequence) {
          dom.show(el.loading, false);
        }
      });
    }

    function schedulePreview() {
      if (timer) {
        window.clearTimeout(timer);
      }
      timer = window.setTimeout(function () {
        timer = null;
        load();
      }, DEBOUNCE_MS);
    }

    dom.on(root, 'change', 'changeType', function () {
      var end;
      renderType();
      if (el.type.value === 'ONCE') {
        // data_fim nao se aplica a UNICA (README §7.2): o campo escondido e limpo.
        end = root.querySelector('#field-end_date');
        if (end) {
          end.value = '';
        }
      }
    });
    el.fields.addEventListener('input', schedulePreview);
    el.fields.addEventListener('change', schedulePreview);

    renderType();
    load();
  });
}());
