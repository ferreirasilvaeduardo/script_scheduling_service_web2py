/* SSS - namespace e componentes Alpine.
 * Carregado com defer ANTES do alpine.min.js: o listener de alpine:init precisa existir
 * quando o Alpine iniciar. Expressoes nas views sao apenas nomes de propriedade/metodo,
 * unico formato aceito pelo build CSP (sem eval/new Function).
 */
(function () {
  'use strict';

  var SSS = window.SSS = window.SSS || {};
  var TOAST_TYPES = { success: 1, error: 1, alert: 1, info: 1 };
  var TOAST_DURATION_MS = 6000;
  var nextId = 1;

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

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('toast', function () {
      return {
        items: [],
        init: function () {
          var self = this;
          window.addEventListener('sss:toast', function (evt) {
            self.add(evt.detail.type, evt.detail.message);
          });
        },
        add: function (type, message) {
          var id = nextId++;
          var self = this;
          if (!TOAST_TYPES[type]) {
            type = 'info';
          }
          this.items.push({ id: id, message: message, classValue: 'sss-toast-' + type });
          window.setTimeout(function () { self.remove(id); }, TOAST_DURATION_MS);
        },
        remove: function (id) {
          this.items = this.items.filter(function (t) { return t.id !== id; });
        },
        // Chamado dentro do x-for: o escopo mesclado expoe o item corrente como this.t.
        close: function () {
          this.remove(this.t.id);
        }
      };
    });

    window.Alpine.data('toastDemo', function () {
      return {
        trigger: function (evt) {
          var button = evt.currentTarget;
          SSS.toast(button.getAttribute('data-type'), button.getAttribute('data-message'));
        }
      };
    });
  });
}());
