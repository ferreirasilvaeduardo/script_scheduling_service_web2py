/* SSS - painel de agentes: atualizacao automatica dos cartoes (F6.1).
 * Carregado com defer ANTES do alpine.min.js. O fragmento (audit/agents.load) e renderizado
 * e escapado pelo servidor, que reaplica os mesmos guardas da pagina; aqui so se troca o no,
 * preservando quais listas de tickets estavam abertas.
 */
(function () {
  'use strict';

  var FRAGMENT_SELECTOR = '[data-sss-fragment="agentes"]';

  function currentTime() {
    var d = new Date();
    function two(n) { return (n < 10 ? '0' : '') + n; }
    return two(d.getHours()) + ':' + two(d.getMinutes()) + ':' + two(d.getSeconds());
  }

  function openItems(root) {
    var codes = {};
    Array.prototype.forEach.call(root.querySelectorAll('details[data-agent]'), function (el) {
      if (el.open) {
        codes[el.getAttribute('data-agent')] = true;
      }
    });
    return codes;
  }

  function reopen(root, codes) {
    Array.prototype.forEach.call(root.querySelectorAll('details[data-agent]'), function (el) {
      if (codes[el.getAttribute('data-agent')]) {
        el.open = true;
      }
    });
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('agentsRefresh', function () {
      return {
        active: false,
        loading: false,
        last: '',
        intervalS: 15,
        timer: null,
        get statusText() {
          if (!this.active) {
            return 'Atualização automática interrompida. Recarregue a página.';
          }
          return (this.last ? 'Atualizado às ' + this.last + '. ' : '') +
            'Atualização automática a cada ' + this.intervalS + ' segundos.';
        },
        init: function () {
          var self = this;
          var interval = parseInt(this.$root.getAttribute('data-interval'), 10);
          if (interval > 0) {
            this.intervalS = interval;
          }
          this.active = true;
          this.last = currentTime();
          this.timer = window.setInterval(function () { self.reload(); }, this.intervalS * 1000);
        },
        stop: function () {
          this.active = false;
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
            var newValue = new DOMParser().parseFromString(html, 'text/html').querySelector(FRAGMENT_SELECTOR);
            var current = self.$root.querySelector(FRAGMENT_SELECTOR);
            var state;
            // Sem o marcador (ex.: sessao expirada redirecionou ao login), nao ha o que trocar.
            if (!newValue || !current) {
              throw new Error('fragmento ausente');
            }
            state = openItems(current);
            newValue = document.importNode(newValue, true);
            reopen(newValue, state);
            current.replaceWith(newValue);
            self.last = currentTime();
          }).catch(function () {
            self.stop();
            window.SSS.toast('error', 'Não foi possível atualizar o painel de agentes. Recarregue a página.');
          }).then(function () {
            self.loading = false;
          });
        }
      };
    });
  });
}());
