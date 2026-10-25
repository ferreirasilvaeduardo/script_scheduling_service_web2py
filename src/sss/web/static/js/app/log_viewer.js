/* SSS - visor de log do ticket com polling por offset (README §8.10).
 * O log so chega a tela por textContent: nunca innerHTML.
 */
(function () {
  'use strict';

  var SSS = window.SSS;
  var dom = SSS.dom;
  var SCREEN_LIMIT = 5000000;
  // Ao estourar o limite, mantem uma folga para nao recortar a cada nova leitura.
  var SCREEN_KEEP = 4000000;
  var BACKOFF_FACTOR = 3;
  var END_MARGIN_PX = 8;
  var DEFAULT_INTERVAL_S = 3;
  var DEFAULT_MAX_CHARS = 65536;
  var TERMINAL_STATUSES = { SUCCESS: 1, FAILED: 1, CANCELLED: 1 };

  function HttpError(status) {
    this.status = status;
  }

  function positiveInt(value, fallback) {
    var n = parseInt(value, 10);
    return n > 0 ? n : fallback;
  }

  SSS.component('logViewer', function (root) {
    var el = {
      area: dom.ref(root, 'area'),
      badge: dom.ref(root, 'badge'),
      badgeLabel: dom.ref(root, 'badgeLabel'),
      follow: dom.ref(root, 'follow'),
      pause: dom.ref(root, 'pause'),
      pauseLabel: dom.ref(root, 'pauseLabel'),
      statusText: dom.ref(root, 'statusText'),
      truncated: dom.ref(root, 'truncated'),
      discarded: dom.ref(root, 'discarded')
    };
    var url = root.getAttribute('data-url-chunk');
    var intervalMs = positiveInt(root.getAttribute('data-interval-s'), DEFAULT_INTERVAL_S) * 1000;
    var maxChars = positiveInt(root.getAttribute('data-max-chars'), DEFAULT_MAX_CHARS);
    var initialStatus = root.getAttribute('data-status') || '';
    var statusInfo = {};
    var state = {
      text: '',
      offset: 0,
      status: initialStatus,
      truncated: root.getAttribute('data-truncated') === 'Y',
      discarded: false,
      follow: true,
      paused: false,
      finished: false,
      loading: false
    };
    var badgeClass = '';
    var timer = null;
    // Incrementada ao pausar: respostas de requisicoes antigas sao descartadas.
    var generation = 0;

    try {
      statusInfo = JSON.parse(root.getAttribute('data-status-info') || '{}');
    } catch (error) {
      statusInfo = {};
    }

    function renderStatus() {
      var info = statusInfo[state.status];
      var next = info ? info.css_class : '';
      if (badgeClass !== next) {
        if (badgeClass) {
          el.badge.classList.remove(badgeClass);
        }
        if (next) {
          el.badge.classList.add(next);
        }
        badgeClass = next;
      }
      dom.setText(el.badgeLabel, info ? info.label : state.status);
      dom.show(el.truncated, state.truncated);
      dom.show(el.discarded, state.discarded);
      el.pause.disabled = state.finished;
      dom.setText(el.pauseLabel, state.paused ? 'Retomar' : 'Pausar');
      el.follow.checked = state.follow;
    }

    function setStatusText(message) {
      dom.setText(el.statusText, message);
    }

    function scrollToEnd() {
      el.area.scrollTop = el.area.scrollHeight;
    }

    function cancelSchedule() {
      if (timer !== null) {
        window.clearTimeout(timer);
        timer = null;
      }
    }

    function schedule(ms) {
      cancelSchedule();
      timer = window.setTimeout(function () {
        timer = null;
        search();
      }, ms);
    }

    function finish(message) {
      state.finished = true;
      cancelSchedule();
      setStatusText(message);
      renderStatus();
    }

    function append(block) {
      var text;
      if (!block) {
        return;
      }
      text = state.text + block;
      if (text.length > SCREEN_LIMIT) {
        text = text.slice(text.length - SCREEN_KEEP);
        state.discarded = true;
      }
      state.text = text;
      dom.setText(el.area, text);
      if (state.follow) {
        scrollToEnd();
      }
    }

    function search() {
      var current = generation;
      var chunkUrl;
      if (state.paused || state.finished || state.loading) {
        return;
      }
      state.loading = true;
      chunkUrl = url + (url.indexOf('?') === -1 ? '?' : '&') + 'offset=' + encodeURIComponent(state.offset);
      SSS.fetch(chunkUrl).then(function (response) {
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
        if (current !== generation) {
          return;
        }
        state.loading = false;
        if (typeof data.text !== 'string' || typeof data.next_offset !== 'number') {
          throw new HttpError(0);
        }
        append(data.text);
        state.offset = data.next_offset;
        // README §5.7: a frase e a barra de etapas acompanham a mudanca de situacao.
        if (initialStatus && data.status && data.status !== initialStatus) {
          state.status = data.status;
          finish('A situação mudou; atualizando a página…');
          window.setTimeout(function () { window.location.reload(); }, 1500);
          return;
        }
        state.status = data.status;
        state.truncated = data.truncated === true;
        full = data.text.length >= maxChars;
        if ((data.terminal === true || TERMINAL_STATUSES[data.status]) && !full) {
          // Situacao terminal desde a abertura (se mudasse, a pagina ja teria recarregado acima).
          finish('Log completo.');
          return;
        }
        renderStatus();
        setStatusText(full ? 'Carregando o log…' : 'Acompanhando a execução.');
        // Bloco cheio: ainda ha log acumulado, le o proximo sem esperar o intervalo.
        schedule(full ? 0 : intervalMs);
      }).catch(function (error) {
        var status = error instanceof HttpError ? error.status : -1;
        if (current !== generation) {
          return;
        }
        state.loading = false;
        if (status === 401) {
          finish('Sessão encerrada. Recarregue a página para continuar acompanhando o log.');
        } else if (status === 400 || status === 403 || status === 404) {
          finish('Não foi possível acompanhar o log deste ticket. Recarregue a página.');
        } else {
          setStatusText('Falha de comunicação; nova tentativa em ' +
            Math.round(intervalMs * BACKOFF_FACTOR / 1000) + ' s.');
          schedule(intervalMs * BACKOFF_FACTOR);
        }
      });
    }

    dom.on(root, 'click', 'togglePause', function () {
      if (state.finished) {
        return;
      }
      if (state.paused) {
        state.paused = false;
        setStatusText('Atualização retomada.');
        renderStatus();
        search();
        return;
      }
      state.paused = true;
      generation++;
      state.loading = false;
      cancelSchedule();
      setStatusText('Atualização pausada.');
      renderStatus();
    });
    dom.on(root, 'change', 'toggleFollow', function (evt) {
      state.follow = evt.target.checked;
      if (state.follow) {
        scrollToEnd();
      }
    });
    el.area.addEventListener('scroll', function () {
      state.follow = el.area.scrollHeight - el.area.scrollTop - el.area.clientHeight <= END_MARGIN_PX;
      el.follow.checked = state.follow;
    });

    renderStatus();
    setStatusText('Carregando o log…');
    search();
  });
}());
