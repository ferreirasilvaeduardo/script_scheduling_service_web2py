/* SSS - lista de tickets: atualizacao automatica opcional da tabela.
 * Carregado com defer ANTES do alpine.min.js. O fragmento (tickets/index.load) e renderizado
 * e escapado pelo servidor, que reaplica os mesmos guardas da pagina; aqui so se troca o no.
 */
(function () {
  'use strict';

  var INTERVALO_MS = 10000;
  var SELETOR_FRAGMENTO = '[data-sss-fragmento="tickets"]';

  function horaAtual() {
    var d = new Date();
    function dois(n) { return (n < 10 ? '0' : '') + n; }
    return dois(d.getHours()) + ':' + dois(d.getMinutes()) + ':' + dois(d.getSeconds());
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('atualizacaoTickets', function () {
      return {
        ativo: false,
        carregando: false,
        ultima: '',
        temporizador: null,
        // Incrementada ao desligar: respostas de requisicoes antigas sao descartadas.
        geracao: 0,
        get situacao() {
          if (!this.ativo) {
            return 'Atualização automática desligada.';
          }
          return this.ultima ? 'Atualizada às ' + this.ultima + '.' : 'Atualização a cada 10 segundos.';
        },
        alternar: function () {
          if (this.ativo) {
            this.parar();
          } else {
            this.iniciar();
          }
        },
        iniciar: function () {
          var self = this;
          this.ativo = true;
          this.temporizador = window.setInterval(function () { self.recarregar(); }, INTERVALO_MS);
        },
        parar: function () {
          this.ativo = false;
          this.geracao++;
          if (this.temporizador !== null) {
            window.clearInterval(this.temporizador);
            this.temporizador = null;
          }
        },
        destroy: function () {
          this.parar();
        },
        recarregar: function () {
          var self = this;
          var geracao = this.geracao;
          if (!this.ativo || this.carregando || document.hidden) {
            return;
          }
          this.carregando = true;
          window.SSS.fetch(this.$root.getAttribute('data-url')).then(function (resposta) {
            if (!resposta.ok) {
              throw new Error('HTTP ' + resposta.status);
            }
            return resposta.text();
          }).then(function (html) {
            var novo;
            var atual;
            if (geracao !== self.geracao) {
              return;
            }
            novo = new DOMParser().parseFromString(html, 'text/html').querySelector(SELETOR_FRAGMENTO);
            atual = self.$root.querySelector(SELETOR_FRAGMENTO);
            // Sem o marcador (ex.: sessao expirada redirecionou ao login), nao ha o que trocar.
            if (!novo || !atual) {
              throw new Error('fragmento ausente');
            }
            atual.replaceWith(document.importNode(novo, true));
            self.ultima = horaAtual();
          }).catch(function () {
            if (geracao === self.geracao) {
              self.parar();
              window.SSS.toast('erro', 'Não foi possível atualizar a lista. A atualização automática foi desligada; recarregue a página.');
            }
          }).then(function () {
            self.carregando = false;
          });
        }
      };
    });
  });
}());
