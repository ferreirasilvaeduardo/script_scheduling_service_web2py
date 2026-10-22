/* SSS - visor de log do ticket com polling por offset (README §8.10).
 * Carregado com defer ANTES do alpine.min.js. O log so chega a tela via x-text: nunca innerHTML.
 */
(function () {
  'use strict';

  var SCREEN_LIMIT = 5000000;
  // Ao estourar o limite, mantem uma folga para nao recortar a cada nova leitura.
  var SCREEN_KEEP = 4000000;
  var BACKOFF_FACTOR = 3;
  var END_MARGIN_PX = 8;
  var TERMINAL_STATUSES = { SUCCESS: 1, FAILED: 1, CANCELLED: 1 };

  function HttpError(status) {
    this.status = status;
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('logViewer', function () {
      return {
        text: '',
        offset: 0,
        status: '',
        initialStatus: '',
        truncated: false,
        discarded: false,
        follow: true,
        paused: false,
        finished: false,
        loading: false,
        statusText: '',
        timer: null,
        // Incrementada ao pausar: respostas de requisicoes antigas sao descartadas.
        generation: 0,
        intervalMs: 3000,
        maxChars: 65536,
        url: '',
        statusInfo: {},

        init: function () {
          var root = this.$root;
          var seconds = parseInt(root.getAttribute('data-interval-s'), 10);
          var max = parseInt(root.getAttribute('data-max-chars'), 10);
          this.url = root.getAttribute('data-url-chunk');
          this.intervalMs = (seconds > 0 ? seconds : 3) * 1000;
          this.maxChars = max > 0 ? max : 65536;
          this.status = root.getAttribute('data-status') || '';
          this.initialStatus = this.status;
          this.truncated = root.getAttribute('data-truncated') === 'Y';
          try {
            this.statusInfo = JSON.parse(root.getAttribute('data-status-info') || '{}');
          } catch (error) {
            this.statusInfo = {};
          }
          this.statusText = 'Carregando o log…';
          this.search();
        },
        destroy: function () {
          this.cancelSchedule();
          this.generation++;
        },

        get statusLabel() {
          var info = this.statusInfo[this.status];
          return info ? info.label : this.status;
        },
        get statusClass() {
          var info = this.statusInfo[this.status];
          return info ? info.css_class : '';
        },
        get pauseLabel() {
          return this.paused ? 'Retomar' : 'Pausar';
        },

        cancelSchedule: function () {
          if (this.timer !== null) {
            window.clearTimeout(this.timer);
            this.timer = null;
          }
        },
        schedule: function (ms) {
          var self = this;
          this.cancelSchedule();
          this.timer = window.setTimeout(function () {
            self.timer = null;
            self.search();
          }, ms);
        },
        togglePause: function () {
          if (this.finished) {
            return;
          }
          if (this.paused) {
            this.paused = false;
            this.statusText = 'Atualização retomada.';
            this.search();
            return;
          }
          this.paused = true;
          this.generation++;
          this.loading = false;
          this.cancelSchedule();
          this.statusText = 'Atualização pausada.';
        },
        toggleFollow: function (evt) {
          this.follow = evt.target.checked;
          if (this.follow) {
            this.scrollToEnd();
          }
        },
        onScroll: function () {
          var area = this.$refs.area;
          this.follow = area.scrollHeight - area.scrollTop - area.clientHeight <= END_MARGIN_PX;
        },
        scrollToEnd: function () {
          var self = this;
          this.$nextTick(function () {
            var area = self.$refs.area;
            area.scrollTop = area.scrollHeight;
          });
        },
        finish: function (message) {
          this.finished = true;
          this.cancelSchedule();
          this.statusText = message;
        },

        append: function (block) {
          if (!block) {
            return;
          }
          var newValue = this.text + block;
          if (newValue.length > SCREEN_LIMIT) {
            newValue = newValue.slice(newValue.length - SCREEN_KEEP);
            this.discarded = true;
          }
          this.text = newValue;
          if (this.follow) {
            this.scrollToEnd();
          }
        },

        search: function () {
          var self = this;
          var generation = this.generation;
          var url;
          if (this.paused || this.finished || this.loading) {
            return;
          }
          this.loading = true;
          url = this.url + (this.url.indexOf('?') === -1 ? '?' : '&') + 'offset=' + encodeURIComponent(this.offset);
          window.SSS.fetch(url).then(function (response) {
            var type = response.headers.get('Content-Type') || '';
            if (!response.ok) {
              throw new HttpError(response.status);
            }
            // Sessao expirada redireciona ao login (HTML 200): nao ha como continuar.
            if (type.indexOf('application/json') === -1) {
              throw new HttpError(401);
            }
            return response.json();
          }).then(function (data) {
            var full;
            if (generation !== self.generation) {
              return;
            }
            self.loading = false;
            if (typeof data.text !== 'string' || typeof data.next_offset !== 'number') {
              throw new HttpError(0);
            }
            self.append(data.text);
            self.offset = data.next_offset;
            // README §5.7: a frase e a barra de etapas acompanham a mudanca de situacao.
            if (self.initialStatus && data.status && data.status !== self.initialStatus) {
              self.status = data.status;
              self.finish('A situação mudou; atualizando a página…');
              window.setTimeout(function () { window.location.reload(); }, 1500);
              return;
            }
            self.status = data.status;
            self.truncated = data.truncated === true;
            full = data.text.length >= self.maxChars;
            if ((data.terminal === true || TERMINAL_STATUSES[data.status]) && !full) {
              self.finish('Execução finalizada; log lido até o fim. Recarregue a página para atualizar o resumo.');
              return;
            }
            self.statusText = full ? 'Carregando o log…' : 'Acompanhando a execução.';
            // Bloco cheio: ainda ha log acumulado, le o proximo sem esperar o intervalo.
            self.schedule(full ? 0 : self.intervalMs);
          }).catch(function (error) {
            var status = error instanceof HttpError ? error.status : -1;
            if (generation !== self.generation) {
              return;
            }
            self.loading = false;
            if (status === 401) {
              self.finish('Sessão encerrada. Recarregue a página para continuar acompanhando o log.');
            } else if (status === 400 || status === 403 || status === 404) {
              self.finish('Não foi possível acompanhar o log deste ticket. Recarregue a página.');
            } else {
              self.statusText = 'Falha de comunicação; nova tentativa em ' +
                Math.round(self.intervalMs * BACKOFF_FACTOR / 1000) + ' s.';
              self.schedule(self.intervalMs * BACKOFF_FACTOR);
            }
          });
        }
      };
    });
  });
}());
