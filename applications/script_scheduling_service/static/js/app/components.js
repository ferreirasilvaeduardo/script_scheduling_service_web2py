/* SSS - componentes Alpine reutilizados pelos partials de views/components/.
 * Carregado com defer ANTES do alpine.min.js (mesmo motivo de sss.js).
 * Build CSP: as views so referenciam nomes de propriedade/metodo; classes condicionais
 * saem de getters porque objetos literais em :class nao sao avaliados.
 */
(function () {
  'use strict';

  var COPY_FEEDBACK_MS = 2000;

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

    window.Alpine.data('filters', function () {
      return {
        // Limpa os campos visiveis e submete; hidden (tamanho etc.) e preservado.
        clear: function (evt) {
          var form = this.$root;
          var fields = form.querySelectorAll('input:not([type="hidden"]), select');
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
          if (form.requestSubmit) {
            form.requestSubmit();
          } else {
            form.submit();
          }
        }
      };
    });

    window.Alpine.data('copy', function () {
      return {
        copied: false,
        get label() {
          return this.copied ? 'Copiado!' : 'Copiar';
        },
        copy: function (evt) {
          var self = this;
          var text = evt.currentTarget.getAttribute('data-text') || '';
          function success() {
            self.copied = true;
            window.SSS.toast('success', 'Texto copiado para a área de transferência.');
            window.setTimeout(function () { self.copied = false; }, COPY_FEEDBACK_MS);
          }
          function failure() {
            window.SSS.toast('error', 'Não foi possível copiar. Selecione o texto e copie manualmente.');
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
        }
      };
    });
  });
}());
