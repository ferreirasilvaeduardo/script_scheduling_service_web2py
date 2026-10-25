/* SSS - lista de tickets: atualizacao automatica opcional da tabela.
 * O fragmento (tickets/index.load) e renderizado e escapado pelo servidor, que reaplica os mesmos
 * guardas da pagina; aqui so se troca o no (SSS.dom.replaceFragment).
 */
(function () {
  'use strict';

  var SSS = window.SSS;
  var dom = SSS.dom;
  var INTERVAL_MS = 10000;
  var FRAGMENT_SELECTOR = '[data-sss-fragment="tickets"]';

  SSS.component('ticketsRefresh', function (root) {
    var toggle = dom.ref(root, 'toggle');
    var status = dom.ref(root, 'status');
    var active = false;
    var loading = false;
    var last = '';
    var timer = null;
    // Incrementada ao desligar: respostas de requisicoes antigas sao descartadas.
    var generation = 0;

    function render() {
      toggle.checked = active;
      if (!active) {
        dom.setText(status, 'Atualização automática desligada.');
      } else {
        dom.setText(status, last ? 'Atualizada às ' + last + '.' : 'Atualização a cada 10 segundos.');
      }
    }

    function start() {
      active = true;
      timer = window.setInterval(reload, INTERVAL_MS);
      render();
    }

    function stop() {
      active = false;
      generation++;
      if (timer !== null) {
        window.clearInterval(timer);
        timer = null;
      }
      render();
    }

    function reload() {
      var current = generation;
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
        if (current !== generation) {
          return;
        }
        dom.replaceFragment(root, FRAGMENT_SELECTOR, html);
        last = dom.clockTime();
        render();
      }).catch(function () {
        if (current === generation) {
          stop();
          SSS.toast('error', 'Não foi possível atualizar a lista. A atualização automática foi desligada; recarregue a página.');
        }
      }).then(function () {
        loading = false;
      });
    }

    dom.on(root, 'change', 'toggle', function () {
      if (active) {
        stop();
      } else {
        start();
      }
    });
    render();
  });
}());
