/* SSS - lista de tickets: atualizacao automatica opcional da tabela.
 * Carregado com defer ANTES do alpine.min.js. O fragmento (tickets/index.load) e renderizado
 * e escapado pelo servidor, que reaplica os mesmos guardas da pagina; aqui so se troca o no.
 */
(function () {
  'use strict';

  var INTERVAL_MS = 10000;
  var FRAGMENT_SELECTOR = '[data-sss-fragment="tickets"]';

  function currentTime() {
    var d = new Date();
    function two(n) { return (n < 10 ? '0' : '') + n; }
    return two(d.getHours()) + ':' + two(d.getMinutes()) + ':' + two(d.getSeconds());
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('ticketsRefresh', function () {
      return {
        active: false,
        loading: false,
        last: '',
        timer: null,
        // Incrementada ao desligar: respostas de requisicoes antigas sao descartadas.
        generation: 0,
        get statusText() {
          if (!this.active) {
            return 'Atualização automática desligada.';
          }
          return this.last ? 'Atualizada às ' + this.last + '.' : 'Atualização a cada 10 segundos.';
        },
        toggle: function () {
          if (this.active) {
            this.stop();
          } else {
            this.start();
          }
        },
        start: function () {
          var self = this;
          this.active = true;
          this.timer = window.setInterval(function () { self.reload(); }, INTERVAL_MS);
        },
        stop: function () {
          this.active = false;
          this.generation++;
          if (this.timer !== null) {
            window.clearInterval(this.timer);
            this.timer = null;
          }
        },
        destroy: function () {
          this.stop();
        },
        reload: function () {
          var self = this;
          var generation = this.generation;
          if (!this.active || this.loading || document.hidden) {
            return;
          }
          this.loading = true;
          window.SSS.fetch(this.$root.getAttribute('data-url')).then(function (response) {
            if (!response.ok) {
              throw new Error('HTTP ' + response.status);
            }
            return response.text();
          }).then(function (html) {
            var newValue;
            var current;
            if (generation !== self.generation) {
              return;
            }
            newValue = new DOMParser().parseFromString(html, 'text/html').querySelector(FRAGMENT_SELECTOR);
            current = self.$root.querySelector(FRAGMENT_SELECTOR);
            // Sem o marcador (ex.: sessao expirada redirecionou ao login), nao ha o que trocar.
            if (!newValue || !current) {
              throw new Error('fragmento ausente');
            }
            current.replaceWith(document.importNode(newValue, true));
            self.last = currentTime();
          }).catch(function () {
            if (generation === self.generation) {
              self.stop();
              window.SSS.toast('error', 'Não foi possível atualizar a lista. A atualização automática foi desligada; recarregue a página.');
            }
          }).then(function () {
            self.loading = false;
          });
        }
      };
    });
  });
}());
