/* SSS - componentes reutilizados pelos partials de views/components/ e por mais de uma tela.
 * Carregado com defer depois do dom.js (CR-021). O 'confirmation' do Alpine, ao fim do arquivo, atende
 * so as telas em que o modal usa o estado de outro componente Alpine (matriz de permissoes,
 * homologacao do script e disparo) e sai com elas no CR-021b.
 */
(function () {
  'use strict';

  var SSS = window.SSS;
  var dom = SSS.dom;
  var COPY_FEEDBACK_MS = 2000;
  var COPY_LABEL = 'Copiar';
  var COPIED_LABEL = 'Copiado!';

  function copyFallback(text) {
    var area = document.createElement('textarea');
    var ok = false;
    area.value = text;
    area.setAttribute('readonly', '');
    area.className = 'sss-copy-area';
    document.body.appendChild(area);
    area.select();
    try {
      ok = document.execCommand('copy');
    } catch (error) {
      ok = false;
    }
    document.body.removeChild(area);
    return ok;
  }

  function normalize(text) {
    return String(text || '').toLowerCase().replace(/^\s+|\s+$/g, '');
  }

  function isEscape(evt) {
    return evt.key === 'Escape' || evt.key === 'Esc';
  }

  // Busca por grupo de [data-search] (Rodar um script e nova regra de agendamento, CR-017c).
  SSS.component('scriptSearch', function (root) {
    var term = dom.ref(root, 'searchTerm');
    var noResult = dom.ref(root, 'noResult');

    dom.on(root, 'input', 'filter', function () {
      var value = normalize(term.value);
      var groups = root.querySelectorAll('[data-group]');
      var visibleTotal = 0;
      var g;
      var items;
      var i;
      var visible;
      var show;
      for (g = 0; g < groups.length; g++) {
        items = groups[g].querySelectorAll('[data-search]');
        visible = 0;
        for (i = 0; i < items.length; i++) {
          show = value === '' || items[i].getAttribute('data-search').indexOf(value) !== -1;
          items[i].hidden = !show;
          if (show) {
            visible++;
          }
        }
        groups[g].hidden = visible === 0;
        visibleTotal += visible;
      }
      dom.show(noResult, visibleTotal === 0);
    });
  });

  /* Modal do Bootstrap aberto e fechado so por classe, sem o JS do Bootstrap. O componente dono passa
   * os elementos dele (data-ref modal, backdrop, cancel) e o elemento que recebe o foco ao fechar.
   * Fecha por Esc e por clique no fundo; os botoes de fechar o componente liga em close().
   */
  SSS.modal = function (options) {
    var modal = options.modal;
    var backdrop = options.backdrop;
    var isOpen = false;

    function open() {
      isOpen = true;
      modal.classList.add('show', 'd-block');
      backdrop.classList.add('modal-backdrop', 'fade', 'show');
      document.body.classList.add('modal-open');
      options.initialFocus.focus();
    }

    // restoreFocus = false quando o fechamento segue de um envio (a pagina vai mudar).
    function close(restoreFocus) {
      if (!isOpen) {
        return;
      }
      isOpen = false;
      modal.classList.remove('show', 'd-block');
      backdrop.classList.remove('modal-backdrop', 'fade', 'show');
      document.body.classList.remove('modal-open');
      if (restoreFocus !== false) {
        options.returnFocus.focus();
      }
    }

    // Clique no fundo escuro: o alvo e o proprio .modal, fora do .modal-dialog.
    modal.addEventListener('click', function (evt) {
      if (evt.target === modal) {
        close();
      }
    });
    document.addEventListener('keydown', function (evt) {
      if (isOpen && isEscape(evt)) {
        close();
      }
    });
    return { open: open, close: close };
  };

  // Modal de confirmacao com POST real (components/confirm_modal.html e Redefinir senha).
  SSS.component('confirmation', function (root) {
    var modal = SSS.modal({
      modal: dom.ref(root, 'modal'),
      backdrop: dom.ref(root, 'backdrop'),
      initialFocus: dom.ref(root, 'cancel'),
      returnFocus: dom.ref(root, 'trigger')
    });
    dom.on(root, 'click', 'open', modal.open);
    dom.on(root, 'click', 'close', function () { modal.close(); });
  });

  SSS.component('filters', function (root) {
    // Limpa os campos visiveis e submete; hidden (tamanho etc.) e preservado.
    dom.on(root, 'click', 'clear', function (evt) {
      var fields = root.querySelectorAll('input:not([type="hidden"]), select');
      var i;
      evt.preventDefault();
      for (i = 0; i < fields.length; i++) {
        if (fields[i].tagName === 'SELECT') {
          fields[i].selectedIndex = 0;
        } else if (fields[i].type === 'checkbox') {
          fields[i].checked = false;
        } else {
          fields[i].value = '';
        }
      }
      if (root.requestSubmit) {
        root.requestSubmit();
      } else {
        root.submit();
      }
    });
  });

  SSS.component('copy', function (root) {
    var label = dom.ref(root, 'label');

    dom.on(root, 'click', 'copy', function (evt, el) {
      var text = el.getAttribute('data-text') || '';
      function success() {
        dom.setText(label, COPIED_LABEL);
        SSS.toast('success', 'Texto copiado para a área de transferência.');
        window.setTimeout(function () { dom.setText(label, COPY_LABEL); }, COPY_FEEDBACK_MS);
      }
      function failure() {
        SSS.toast('error', 'Não foi possível copiar. Selecione o texto e copie manualmente.');
      }
      // navigator.clipboard so existe em contexto seguro (HTTPS ou localhost).
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(success, function () {
          if (copyFallback(text)) { success(); } else { failure(); }
        });
      } else if (copyFallback(text)) {
        success();
      } else {
        failure();
      }
    });
  });

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('confirmation', function () {
      return {
        isOpen: false,
        get modalClass() {
          return this.isOpen ? 'show d-block' : '';
        },
        get backdropClass() {
          return this.isOpen ? 'modal-backdrop fade show' : '';
        },
        open: function () {
          var self = this;
          this.isOpen = true;
          document.body.classList.add('modal-open');
          this.$nextTick(function () { self.$refs.cancel.focus(); });
        },
        close: function () {
          if (!this.isOpen) {
            return;
          }
          this.isOpen = false;
          document.body.classList.remove('modal-open');
          this.$refs.trigger.focus();
        }
      };
    });
  });
}());
