/* SSS - painel de agentes: atualizacao automatica dos cartoes (F6.1).
 * O fragmento (audit/agents.load) e renderizado e escapado pelo servidor, que reaplica os mesmos
 * guardas da pagina; aqui so se troca o no, preservando quais listas de tickets estavam abertas.
 */
(function () {
  'use strict';

  var SSS = window.SSS;
  var dom = SSS.dom;
  var DEFAULT_INTERVAL_S = 15;
  var FRAGMENT_SELECTOR = '[data-sss-fragment="agentes"]';

  function openItems(fragment) {
    var codes = {};
    Array.prototype.forEach.call(fragment.querySelectorAll('details[data-agent]'), function (el) {
      if (el.open) {
        codes[el.getAttribute('data-agent')] = true;
      }
    });
    return codes;
  }

  function reopen(fragment, codes) {
    Array.prototype.forEach.call(fragment.querySelectorAll('details[data-agent]'), function (el) {
      if (codes[el.getAttribute('data-agent')]) {
        el.open = true;
      }
    });
  }

  SSS.component('agentsRefresh', function (root) {
    var status = dom.ref(root, 'status');
    var interval = parseInt(root.getAttribute('data-interval'), 10);
    var intervalS = interval > 0 ? interval : DEFAULT_INTERVAL_S;
    var active = true;
    var loading = false;
    var last = dom.clockTime();
    var timer = null;

    function render() {
      if (!active) {
        dom.setText(status, 'Atualização automática interrompida. Recarregue a página.');
        return;
      }
      dom.setText(status, (last ? 'Atualizado às ' + last + '. ' : '') +
        'Atualização automática a cada ' + intervalS + ' segundos.');
    }

    function stop() {
      active = false;
      if (timer !== null) {
        window.clearInterval(timer);
        timer = null;
      }
      render();
    }

    function reload() {
      if (!active || loading || document.hidden) {
        return;
      }
      loading = true;
      SSS.fetch(root.getAttribute('data-url')).then(function (response) {
        if (!response.ok) {
          throw new Error('HTTP ' + response.status);
        }
        return response.text();
      }).then(function (html) {
        dom.replaceFragment(root, FRAGMENT_SELECTOR, html, function (fresh, current) {
          reopen(fresh, openItems(current));
        });
        last = dom.clockTime();
        render();
      }).catch(function () {
        stop();
        SSS.toast('error', 'Não foi possível atualizar o painel de agentes. Recarregue a página.');
      }).then(function () {
        loading = false;
      });
    }

    timer = window.setInterval(reload, intervalS * 1000);
    render();
  });
}());
