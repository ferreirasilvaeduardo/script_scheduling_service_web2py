/* SSS - painel de agentes: atualizacao automatica dos cartoes (F6.1).
 * Carregado com defer ANTES do alpine.min.js. O fragmento (auditoria/agentes.load) e renderizado
 * e escapado pelo servidor, que reaplica os mesmos guardas da pagina; aqui so se troca o no,
 * preservando quais listas de tickets estavam abertas.
 */
(function () {
  'use strict';

  var SELETOR_FRAGMENTO = '[data-sss-fragmento="agentes"]';

  function horaAtual() {
    var d = new Date();
    function dois(n) { return (n < 10 ? '0' : '') + n; }
    return dois(d.getHours()) + ':' + dois(d.getMinutes()) + ':' + dois(d.getSeconds());
  }

  function abertos(raiz) {
    var codigos = {};
    Array.prototype.forEach.call(raiz.querySelectorAll('details[data-agente]'), function (el) {
      if (el.open) {
        codigos[el.getAttribute('data-agente')] = true;
      }
    });
    return codigos;
  }

  function reabrir(raiz, codigos) {
    Array.prototype.forEach.call(raiz.querySelectorAll('details[data-agente]'), function (el) {
      if (codigos[el.getAttribute('data-agente')]) {
        el.open = true;
      }
    });
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('atualizacaoAgentes', function () {
      return {
        ativo: false,
        carregando: false,
        ultima: '',
        intervaloS: 15,
        temporizador: null,
        get situacao() {
          if (!this.ativo) {
            return 'Atualização automática interrompida. Recarregue a página.';
          }
          return (this.ultima ? 'Atualizado às ' + this.ultima + '. ' : '') +
            'Atualização automática a cada ' + this.intervaloS + ' segundos.';
        },
        init: function () {
          var self = this;
          var intervalo = parseInt(this.$root.getAttribute('data-intervalo'), 10);
          if (intervalo > 0) {
            this.intervaloS = intervalo;
          }
          this.ativo = true;
          this.ultima = horaAtual();
          this.temporizador = window.setInterval(function () { self.recarregar(); }, this.intervaloS * 1000);
        },
        parar: function () {
          this.ativo = false;
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
            var novo = new DOMParser().parseFromString(html, 'text/html').querySelector(SELETOR_FRAGMENTO);
            var atual = self.$root.querySelector(SELETOR_FRAGMENTO);
            var estado;
            // Sem o marcador (ex.: sessao expirada redirecionou ao login), nao ha o que trocar.
            if (!novo || !atual) {
              throw new Error('fragmento ausente');
            }
            estado = abertos(atual);
            novo = document.importNode(novo, true);
            reabrir(novo, estado);
            atual.replaceWith(novo);
            self.ultima = horaAtual();
          }).catch(function () {
            self.parar();
            window.SSS.toast('erro', 'Não foi possível atualizar o painel de agentes. Recarregue a página.');
          }).then(function () {
            self.carregando = false;
          });
        }
      };
    });
  });
}());
