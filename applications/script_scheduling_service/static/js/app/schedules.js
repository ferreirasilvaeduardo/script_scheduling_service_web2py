/* SSS - formulario de regra de agendamento (schedules/form).
 * Carregado com defer ANTES do alpine.min.js. Nenhuma regra decisoria fica aqui: os campos
 * condicionais so ajudam o preenchimento e a previa e calculada pelo servidor (recurrence.py).
 */
(function () {
  'use strict';

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

  function list(items) {
    var listItems = [];
    var i;
    for (i = 0; i < items.length; i++) {
      listItems.push({ id: i, text: String(items[i]) });
    }
    return listItems;
  }

  function mapValues(map) {
    var listItems = [];
    var key;
    for (key in map) {
      if (Object.prototype.hasOwnProperty.call(map, key)) {
        listItems.push(map[key]);
      }
    }
    return listItems;
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('scheduleRule', function () {
      return {
        type: '',
        loading: false,
        description: '',
        dates: [],
        errors: [],
        timer: null,
        sequence: 0,
        init: function () {
          this.type = this.$refs.type.value;
          this.load();
        },
        get isOnce() { return this.type === 'ONCE'; },
        get notOnce() { return this.type !== 'ONCE'; },
        get hasHour() { return this.type === 'DAILY' || this.type === 'WEEKLY' || this.type === 'MONTHLY'; },
        get isWeekly() { return this.type === 'WEEKLY'; },
        get isMonthly() { return this.type === 'MONTHLY'; },
        get isCron() { return this.type === 'CRON'; },
        get hasDescription() { return this.description !== ''; },
        get hasDates() { return this.dates.length > 0; },
        get hasErrors() { return this.errors.length > 0; },
        changeType: function () {
          this.type = this.$refs.type.value;
          if (this.type === 'ONCE') {
            // data_fim nao se aplica a UNICA (README §7.2): o campo escondido e limpo.
            var end = this.$root.querySelector('#field-end_date');
            if (end) {
              end.value = '';
            }
          }
        },
        schedulePreview: function () {
          var self = this;
          if (this.timer) {
            window.clearTimeout(this.timer);
          }
          this.timer = window.setTimeout(function () {
            self.timer = null;
            self.load();
          }, DEBOUNCE_MS);
        },
        load: function () {
          var self = this;
          var form = this.$root;
          var body = { week_days: weekDays(form) };
          var i;
          // Respostas fora de ordem sao descartadas: so a ultima requisicao atualiza a tela.
          var number = ++this.sequence;
          for (i = 0; i < FIELDS.length; i++) {
            body[FIELDS[i]] = value(form, FIELDS[i]);
          }
          this.loading = true;
          window.sssFetch(form.getAttribute('data-url-preview'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(body)
          }).then(function (response) {
            if (response.status === 403) {
              return null;
            }
            return response.json();
          }).then(function (data) {
            if (!data || number !== self.sequence) {
              return;
            }
            self.description = data.description || '';
            self.dates = list(data.dates || []);
            self.errors = list(mapValues(data.errors || {}));
          }).catch(function () {
            if (number === self.sequence) {
              window.SSS.toast('error', 'Não foi possível calcular a prévia. Tente novamente.');
            }
          }).then(function () {
            if (number === self.sequence) {
              self.loading = false;
            }
          });
        }
      };
    });
  });
}());
