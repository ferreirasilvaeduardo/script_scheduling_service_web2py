/* SSS - tela de disparo de script (tickets/new).
 * Nenhuma regra decisoria fica aqui: o servidor revalida tudo; o cliente apenas exibe, no modal de
 * confirmacao, o resumo que o servidor monta ao abrir o modal (README §5.4).
 */
(function () {
  'use strict';

  var SSS = window.SSS;
  var dom = SSS.dom;
  var PARAM_PREFIX = 'p_';
  var RE_SIMPLE_TOKEN = /^[A-Za-z0-9_@%+=:,.\/-]+$/;

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

  function errorTexts(data) {
    var texts = [];
    var key;
    for (key in (data && data.errors) || {}) {
      if (Object.prototype.hasOwnProperty.call(data.errors, key)) {
        texts.push(String(data.errors[key]));
      }
    }
    if (!texts.length) {
      texts.push((data && data.error) || 'Não foi possível montar o resumo.');
    }
    return texts;
  }

  SSS.component('ticketTrigger', function (form) {
    var el = {
      loading: dom.ref(form, 'loading'),
      summary: dom.ref(form, 'summary'),
      script: dom.ref(form, 'script'),
      environment: dom.ref(form, 'environment'),
      when: dom.ref(form, 'when'),
      priority: dom.ref(form, 'priority'),
      interpreter: dom.ref(form, 'interpreter'),
      answers: dom.ref(form, 'answers'),
      answerTemplate: dom.ref(form, 'answerTemplate'),
      command: dom.ref(form, 'command'),
      errors: dom.ref(form, 'errors')
    };
    var modal = SSS.modal({
      modal: dom.ref(form, 'modal'),
      backdrop: dom.ref(form, 'backdrop'),
      initialFocus: dom.ref(form, 'cancel'),
      returnFocus: dom.ref(form, 'trigger')
    });

    function renderAnswers(answers) {
      var fragment = document.createDocumentFragment();
      answers.forEach(function (r) {
        var item = dom.clone(el.answerTemplate);
        dom.setText(item.querySelector('[data-part="label"]'), r.label);
        dom.setText(item.querySelector('[data-part="value"]'), r.value);
        fragment.appendChild(item);
      });
      el.answers.replaceChildren(fragment);
      dom.show(el.answers, answers.length > 0);
    }

    function showErrors(texts) {
      dom.fillList(el.errors, texts);
      dom.show(el.errors, texts.length > 0);
    }

    function load() {
      var body = {
        script_id: form.elements.script_id.value,
        environment: form.elements.environment.value,
        priority: form.elements.priority ? form.elements.priority.value : '',
        scheduled_at: form.elements.scheduled_at ? form.elements.scheduled_at.value : '',
        interpreter: form.elements.interpreter ? form.elements.interpreter.value : '',
        answers: collectAnswers(form)
      };
      dom.show(el.loading, true);
      dom.show(el.summary, false);
      showErrors([]);
      SSS.fetch(form.getAttribute('data-url-preview'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(body)
      }).then(function (response) {
        return response.json();
      }).then(function (data) {
        var summary = data && data.summary;
        if (!summary) {
          showErrors(errorTexts(data));
          return;
        }
        dom.setText(el.script, summary.script);
        dom.setText(el.environment, summary.environment);
        dom.setText(el.when, summary.when);
        dom.setText(el.priority, summary.priority);
        dom.setText(el.interpreter, summary.interpreter);
        renderAnswers(summary.answers.map(function (r) { return { label: r.label, value: String(r.value) }; }));
        dom.setText(el.command, (data.argv || []).map(displayToken).join(' '));
        dom.show(el.summary, true);
      }).catch(function () {
        showErrors(['Não foi possível montar o resumo. Tente novamente.']);
      }).then(function () {
        dom.show(el.loading, false);
      });
    }

    dom.on(form, 'click', 'open', function () {
      modal.open();
      load();
    });
    dom.on(form, 'click', 'close', function () { modal.close(); });
  });
}());
