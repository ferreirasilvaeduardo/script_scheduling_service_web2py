/* SSS - componentes Alpine reutilizados pelos partials de views/components/.
 * Carregado com defer ANTES do alpine.min.js (mesmo motivo de sss.js).
 * Build CSP: as views so referenciam nomes de propriedade/metodo; classes condicionais
 * saem de getters porque objetos literais em :class nao sao avaliados.
 */
(function () {
  'use strict';

  var FEEDBACK_COPIA_MS = 2000;

  function copiarFallback(texto) {
    var area = document.createElement('textarea');
    var ok = false;
    area.value = texto;
    area.setAttribute('readonly', '');
    area.className = 'sss-copiar-area';
    document.body.appendChild(area);
    area.select();
    try {
      ok = document.execCommand('copy');
    } catch (erro) {
      ok = false;
    }
    document.body.removeChild(area);
    return ok;
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('confirmacao', function () {
      return {
        aberto: false,
        get classeModal() {
          return this.aberto ? 'show d-block' : '';
        },
        get classeFundo() {
          return this.aberto ? 'modal-backdrop fade show' : '';
        },
        abrir: function () {
          var self = this;
          this.aberto = true;
          document.body.classList.add('modal-open');
          this.$nextTick(function () { self.$refs.cancelar.focus(); });
        },
        fechar: function () {
          if (!this.aberto) {
            return;
          }
          this.aberto = false;
          document.body.classList.remove('modal-open');
          this.$refs.gatilho.focus();
        }
      };
    });

    window.Alpine.data('filtros', function () {
      return {
        // Limpa os campos visiveis e submete; hidden (tamanho etc.) e preservado.
        limpar: function (evt) {
          var form = this.$root;
          var campos = form.querySelectorAll('input:not([type="hidden"]), select');
          var i;
          evt.preventDefault();
          for (i = 0; i < campos.length; i++) {
            if (campos[i].tagName === 'SELECT') {
              campos[i].selectedIndex = 0;
            } else if (campos[i].type === 'checkbox') {
              campos[i].checked = false;
            } else {
              campos[i].value = '';
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

    window.Alpine.data('copiar', function () {
      return {
        copiado: false,
        get rotulo() {
          return this.copiado ? 'Copiado!' : 'Copiar';
        },
        copiar: function (evt) {
          var self = this;
          var texto = evt.currentTarget.getAttribute('data-texto') || '';
          function sucesso() {
            self.copiado = true;
            window.SSS.toast('success', 'Texto copiado para a área de transferência.');
            window.setTimeout(function () { self.copiado = false; }, FEEDBACK_COPIA_MS);
          }
          function falha() {
            window.SSS.toast('error', 'Não foi possível copiar. Selecione o texto e copie manualmente.');
          }
          // navigator.clipboard so existe em contexto seguro (HTTPS ou localhost).
          if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(texto).then(sucesso, function () {
              if (copiarFallback(texto)) { sucesso(); } else { falha(); }
            });
          } else if (copiarFallback(texto)) {
            sucesso();
          } else {
            falha();
          }
        }
      };
    });
  });
}());
