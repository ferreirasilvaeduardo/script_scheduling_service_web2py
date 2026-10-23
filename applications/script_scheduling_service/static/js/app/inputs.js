/* SSS - tela de Entrada (CR-020d): confirmacao antes de enviar com "Substituir se ja existir".
 * Carregado com defer ANTES do alpine.min.js. Sem JavaScript o formulario e enviado direto: a caixa
 * de substituir ja e a escolha explicita do usuario.
 */
(function () {
  'use strict';

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('inputUpload', function () {
      return {
        isOpen: false,
        confirmed: false,
        get modalClass() {
          return this.isOpen ? 'show d-block' : '';
        },
        get backdropClass() {
          return this.isOpen ? 'modal-backdrop fade show' : '';
        },
        submit: function (evt) {
          if (this.$refs.replace.checked && !this.confirmed) {
            evt.preventDefault();
            var self = this;
            this.isOpen = true;
            document.body.classList.add('modal-open');
            this.$nextTick(function () { self.$refs.cancel.focus(); });
          }
        },
        confirm: function () {
          this.confirmed = true;
          this.isOpen = false;
          document.body.classList.remove('modal-open');
          this.$refs.form.submit();
        },
        close: function () {
          if (!this.isOpen) {
            return;
          }
          this.isOpen = false;
          document.body.classList.remove('modal-open');
          this.$refs.submit.focus();
        }
      };
    });
  });
}());
