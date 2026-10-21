/* SSS - visor de log do ticket com polling por offset (README §8.10).
 * Carregado com defer ANTES do alpine.min.js. O log so chega a tela via x-text: nunca innerHTML.
 */
(function () {
  'use strict';

  var LIMITE_TELA = 5000000;
  // Ao estourar o limite, mantem uma folga para nao recortar a cada nova leitura.
  var MANTER_TELA = 4000000;
  var FATOR_BACKOFF = 3;
  var MARGEM_FINAL_PX = 8;
  var STATUS_TERMINAIS = { SUCCESS: 1, FAILED: 1, CANCELLED: 1 };

  function ErroHttp(status) {
    this.status = status;
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('logViewer', function () {
      return {
        texto: '',
        offset: 0,
        status: '',
        statusInicial: '',
        truncado: false,
        descartado: false,
        seguir: true,
        pausado: false,
        encerrado: false,
        carregando: false,
        situacao: '',
        temporizador: null,
        // Incrementada ao pausar: respostas de requisicoes antigas sao descartadas.
        geracao: 0,
        intervaloMs: 3000,
        maxChars: 65536,
        url: '',
        statusInfo: {},

        init: function () {
          var raiz = this.$root;
          var segundos = parseInt(raiz.getAttribute('data-intervalo-s'), 10);
          var max = parseInt(raiz.getAttribute('data-max-chars'), 10);
          this.url = raiz.getAttribute('data-url-chunk');
          this.intervaloMs = (segundos > 0 ? segundos : 3) * 1000;
          this.maxChars = max > 0 ? max : 65536;
          this.status = raiz.getAttribute('data-status') || '';
          this.statusInicial = this.status;
          this.truncado = raiz.getAttribute('data-truncado') === 'Y';
          try {
            this.statusInfo = JSON.parse(raiz.getAttribute('data-status-info') || '{}');
          } catch (erro) {
            this.statusInfo = {};
          }
          this.situacao = 'Carregando o log…';
          this.buscar();
        },
        destroy: function () {
          this.cancelarAgendamento();
          this.geracao++;
        },

        get rotuloStatus() {
          var info = this.statusInfo[this.status];
          return info ? info.rotulo : this.status;
        },
        get classeStatus() {
          var info = this.statusInfo[this.status];
          return info ? info.classe : '';
        },
        get rotuloPausa() {
          return this.pausado ? 'Retomar' : 'Pausar';
        },

        cancelarAgendamento: function () {
          if (this.temporizador !== null) {
            window.clearTimeout(this.temporizador);
            this.temporizador = null;
          }
        },
        agendar: function (ms) {
          var self = this;
          this.cancelarAgendamento();
          this.temporizador = window.setTimeout(function () {
            self.temporizador = null;
            self.buscar();
          }, ms);
        },
        alternarPausa: function () {
          if (this.encerrado) {
            return;
          }
          if (this.pausado) {
            this.pausado = false;
            this.situacao = 'Atualização retomada.';
            this.buscar();
            return;
          }
          this.pausado = true;
          this.geracao++;
          this.carregando = false;
          this.cancelarAgendamento();
          this.situacao = 'Atualização pausada.';
        },
        alternarSeguir: function (evt) {
          this.seguir = evt.target.checked;
          if (this.seguir) {
            this.rolarParaFinal();
          }
        },
        aoRolar: function () {
          var area = this.$refs.area;
          this.seguir = area.scrollHeight - area.scrollTop - area.clientHeight <= MARGEM_FINAL_PX;
        },
        rolarParaFinal: function () {
          var self = this;
          this.$nextTick(function () {
            var area = self.$refs.area;
            area.scrollTop = area.scrollHeight;
          });
        },
        encerrar: function (mensagem) {
          this.encerrado = true;
          this.cancelarAgendamento();
          this.situacao = mensagem;
        },

        anexar: function (bloco) {
          if (!bloco) {
            return;
          }
          var novo = this.texto + bloco;
          if (novo.length > LIMITE_TELA) {
            novo = novo.slice(novo.length - MANTER_TELA);
            this.descartado = true;
          }
          this.texto = novo;
          if (this.seguir) {
            this.rolarParaFinal();
          }
        },

        buscar: function () {
          var self = this;
          var geracao = this.geracao;
          var url;
          if (this.pausado || this.encerrado || this.carregando) {
            return;
          }
          this.carregando = true;
          url = this.url + (this.url.indexOf('?') === -1 ? '?' : '&') + 'offset=' + encodeURIComponent(this.offset);
          window.SSS.fetch(url).then(function (resposta) {
            var tipo = resposta.headers.get('Content-Type') || '';
            if (!resposta.ok) {
              throw new ErroHttp(resposta.status);
            }
            // Sessao expirada redireciona ao login (HTML 200): nao ha como continuar.
            if (tipo.indexOf('application/json') === -1) {
              throw new ErroHttp(401);
            }
            return resposta.json();
          }).then(function (dados) {
            var cheio;
            if (geracao !== self.geracao) {
              return;
            }
            self.carregando = false;
            if (typeof dados.texto !== 'string' || typeof dados.proximo_offset !== 'number') {
              throw new ErroHttp(0);
            }
            self.anexar(dados.texto);
            self.offset = dados.proximo_offset;
            // README §5.7: a frase e a barra de etapas acompanham a mudanca de situacao.
            if (self.statusInicial && dados.status && dados.status !== self.statusInicial) {
              self.status = dados.status;
              self.encerrar('A situação mudou; atualizando a página…');
              window.setTimeout(function () { window.location.reload(); }, 1500);
              return;
            }
            self.status = dados.status;
            self.truncado = dados.truncado === true;
            cheio = dados.texto.length >= self.maxChars;
            if ((dados.terminal === true || STATUS_TERMINAIS[dados.status]) && !cheio) {
              self.encerrar('Execução finalizada; log lido até o fim. Recarregue a página para atualizar o resumo.');
              return;
            }
            self.situacao = cheio ? 'Carregando o log…' : 'Acompanhando a execução.';
            // Bloco cheio: ainda ha log acumulado, le o proximo sem esperar o intervalo.
            self.agendar(cheio ? 0 : self.intervaloMs);
          }).catch(function (erro) {
            var status = erro instanceof ErroHttp ? erro.status : -1;
            if (geracao !== self.geracao) {
              return;
            }
            self.carregando = false;
            if (status === 401) {
              self.encerrar('Sessão encerrada. Recarregue a página para continuar acompanhando o log.');
            } else if (status === 400 || status === 403 || status === 404) {
              self.encerrar('Não foi possível acompanhar o log deste ticket. Recarregue a página.');
            } else {
              self.situacao = 'Falha de comunicação; nova tentativa em ' +
                Math.round(self.intervaloMs * FATOR_BACKOFF / 1000) + ' s.';
              self.agendar(self.intervaloMs * FATOR_BACKOFF);
            }
          });
        }
      };
    });
  });
}());
