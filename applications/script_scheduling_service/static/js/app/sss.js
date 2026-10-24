/* SSS - namespace, tema, fetch com CSRF e notificacoes (toast).
 * Carregado com defer depois do dom.js, que monta os componentes registrados aqui (CR-021).
 */
(function () {
  'use strict';

  var SSS = window.SSS = window.SSS || {};
  // Os mesmos modificadores de .sss-toast-* em sss.css.
  var TOAST_TYPES = { success: 1, error: 1, warning: 1, info: 1 };
  var TOAST_DURATION_MS = 6000;

  // Bootstrap 5.3 nao segue prefers-color-scheme sozinho; o tema vem do sistema.
  var darkScheme = window.matchMedia('(prefers-color-scheme: dark)');
  function applyTheme() {
    document.documentElement.setAttribute('data-bs-theme', darkScheme.matches ? 'dark' : 'light');
  }
  applyTheme();
  if (darkScheme.addEventListener) {
    darkScheme.addEventListener('change', applyTheme);
  } else {
    darkScheme.addListener(applyTheme);
  }

  SSS.toast = function (type, message) {
    window.dispatchEvent(new CustomEvent('sss:toast', {
      detail: { type: type, message: String(message) }
    }));
  };

  var SAFE_METHODS = { GET: 1, HEAD: 1 };

  function tokenCsrf() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  // fetch com cookies de mesma origem e X-CSRF-Token em metodos que alteram estado (README §4.2).
  SSS.fetch = window.sssFetch = function (url, options) {
    var opts = {};
    var key;
    options = options || {};
    for (key in options) {
      if (Object.prototype.hasOwnProperty.call(options, key)) {
        opts[key] = options[key];
      }
    }
    var method = String(opts.method || 'GET').toUpperCase();
    var headers = new Headers(opts.headers || {});
    if (!SAFE_METHODS[method]) {
      headers.set('X-CSRF-Token', tokenCsrf());
    }
    opts.method = method;
    opts.headers = headers;
    opts.credentials = 'same-origin';
    return window.fetch(url, opts).then(function (response) {
      if (response.status === 403) {
        SSS.toast('error', 'Requisição recusada. Recarregue a página e tente novamente.');
      }
      return response;
    });
  };

  SSS.component('toast', function (root) {
    var template = SSS.dom.ref(root, 'item');

    function add(type, message) {
      var item = SSS.dom.clone(template);
      if (!TOAST_TYPES[type]) {
        type = 'info';
      }
      item.classList.add('sss-toast-' + type);
      SSS.dom.setText(item.querySelector('[data-ref="message"]'), message);
      root.appendChild(item);
      window.setTimeout(function () { remove(item); }, TOAST_DURATION_MS);
    }

    function remove(item) {
      if (item.parentNode === root) {
        root.removeChild(item);
      }
    }

    window.addEventListener('sss:toast', function (evt) {
      add(evt.detail.type, evt.detail.message);
    });
    SSS.dom.on(root, 'click', 'close', function (evt, el) {
      remove(el.closest('.sss-toast'));
    });
  });

  SSS.component('toastDemo', function (root) {
    SSS.dom.on(root, 'click', 'trigger', function (evt, el) {
      SSS.toast(el.getAttribute('data-type'), el.getAttribute('data-message'));
    });
  });
}());
