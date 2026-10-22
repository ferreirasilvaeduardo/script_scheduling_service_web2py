/* SSS - namespace e componentes Alpine.
 * Carregado com defer ANTES do alpine.min.js: o listener de alpine:init precisa existir
 * quando o Alpine iniciar. Expressoes nas views sao apenas nomes de propriedade/metodo,
 * unico formato aceito pelo build CSP (sem eval/new Function).
 */
(function () {
  'use strict';

  var SSS = window.SSS = window.SSS || {};
  var TIPOS_TOAST = { sucesso: 1, erro: 1, alerta: 1, info: 1 };
  var DURACAO_TOAST_MS = 6000;
  var proximoId = 1;

  // Bootstrap 5.3 nao segue prefers-color-scheme sozinho; o tema vem do sistema.
  var esquemaEscuro = window.matchMedia('(prefers-color-scheme: dark)');
  function aplicarTema() {
    document.documentElement.setAttribute('data-bs-theme', esquemaEscuro.matches ? 'dark' : 'light');
  }
  aplicarTema();
  if (esquemaEscuro.addEventListener) {
    esquemaEscuro.addEventListener('change', aplicarTema);
  } else {
    esquemaEscuro.addListener(aplicarTema);
  }

  SSS.toast = function (tipo, mensagem) {
    window.dispatchEvent(new CustomEvent('sss:toast', {
      detail: { tipo: tipo, mensagem: String(mensagem) }
    }));
  };

  var METODOS_SEGUROS = { GET: 1, HEAD: 1 };

  function tokenCsrf() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  // fetch com cookies de mesma origem e X-CSRF-Token em metodos que alteram estado (README §4.2).
  SSS.fetch = window.sssFetch = function (url, opcoes) {
    var opts = {};
    var chave;
    opcoes = opcoes || {};
    for (chave in opcoes) {
      if (Object.prototype.hasOwnProperty.call(opcoes, chave)) {
        opts[chave] = opcoes[chave];
      }
    }
    var metodo = String(opts.method || 'GET').toUpperCase();
    var cabecalhos = new Headers(opts.headers || {});
    if (!METODOS_SEGUROS[metodo]) {
      cabecalhos.set('X-CSRF-Token', tokenCsrf());
    }
    opts.method = metodo;
    opts.headers = cabecalhos;
    opts.credentials = 'same-origin';
    return window.fetch(url, opts).then(function (resposta) {
      if (resposta.status === 403) {
        SSS.toast('error', 'Requisição recusada. Recarregue a página e tente novamente.');
      }
      return resposta;
    });
  };

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('toast', function () {
      return {
        itens: [],
        init: function () {
          var self = this;
          window.addEventListener('sss:toast', function (evt) {
            self.adicionar(evt.detail.tipo, evt.detail.mensagem);
          });
        },
        adicionar: function (tipo, mensagem) {
          var id = proximoId++;
          var self = this;
          if (!TIPOS_TOAST[tipo]) {
            tipo = 'info';
          }
          this.itens.push({ id: id, mensagem: mensagem, classe: 'sss-toast-' + tipo });
          window.setTimeout(function () { self.remover(id); }, DURACAO_TOAST_MS);
        },
        remover: function (id) {
          this.itens = this.itens.filter(function (t) { return t.id !== id; });
        },
        // Chamado dentro do x-for: o escopo mesclado expoe o item corrente como this.t.
        fechar: function () {
          this.remover(this.t.id);
        }
      };
    });

    window.Alpine.data('toastDemo', function () {
      return {
        disparar: function (evt) {
          var botao = evt.currentTarget;
          SSS.toast(botao.getAttribute('data-tipo'), botao.getAttribute('data-mensagem'));
        }
      };
    });
  });
}());
