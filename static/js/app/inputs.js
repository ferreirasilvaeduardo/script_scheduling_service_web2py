/* SSS - tela de Entrada (CR-020d): confirmacao antes de enviar com "Substituir se ja existir".
 * Sem JavaScript o formulario e enviado direto: a caixa de substituir ja e a escolha explicita do usuario.
 */
(function () {
  'use strict';

  var SSS = window.SSS;
  var dom = SSS.dom;

  SSS.component('inputUpload', function (root) {
    var form = dom.ref(root, 'form');
    var replace = dom.ref(root, 'replace');
    var modal = SSS.modal({
      modal: dom.ref(root, 'modal'),
      backdrop: dom.ref(root, 'backdrop'),
      initialFocus: dom.ref(root, 'cancel'),
      returnFocus: dom.ref(root, 'submit')
    });
    var confirmed = false;

    form.addEventListener('submit', function (evt) {
      if (replace.checked && !confirmed) {
        evt.preventDefault();
        modal.open();
      }
    });
    dom.on(root, 'click', 'confirm', function () {
      confirmed = true;
      modal.close(false);
      // form.submit() nao dispara o evento submit: o envio confirmado nao reabre o modal.
      form.submit();
    });
    dom.on(root, 'click', 'close', function () { modal.close(); });
  });
}());
