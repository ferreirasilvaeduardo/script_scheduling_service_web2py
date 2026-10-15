/* SSS - matriz de permissoes do perfil (README §4.3).
 * Carregado com defer ANTES do alpine.min.js. Abas, contadores, "marcar todos", busca de scripts e o
 * resumo do modal. O resumo segue o formato do diff auditado (PERM_ALTERAR); o servidor revalida tudo.
 */
(function () {
  'use strict';

  var DIMENSOES = ['funcs', 'ambs', 'scrs'];

  function caixas(raiz, seletor) {
    return Array.prototype.slice.call(raiz.querySelectorAll(seletor));
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('matrizPermissoes', function () {
      return {
        resumo: [],
        aba: 'funcs',

        get semAlteracoes() {
          return this.resumo.length === 0;
        },
        get temAlteracoes() {
          return this.resumo.length > 0;
        },
        get situacao() {
          if (!this.resumo.length) {
            return 'Nenhuma alteração pendente.';
          }
          return this.resumo.length === 1 ? '1 alteração pendente.' : this.resumo.length + ' alterações pendentes.';
        },

        init: function () {
          this.mostrarAba('funcs');
          this.atualizar();
        },

        mostrarAba: function (dim) {
          var raiz = this.$root;
          this.aba = dim;
          caixas(raiz, '[data-aba]').forEach(function (botao) {
            var ativo = botao.getAttribute('data-aba') === dim;
            botao.classList.toggle('active', ativo);
            botao.setAttribute('aria-selected', ativo ? 'true' : 'false');
            botao.setAttribute('tabindex', ativo ? '0' : '-1');
          });
          caixas(raiz, '[data-painel]').forEach(function (painel) {
            painel.hidden = painel.getAttribute('data-painel') !== dim;
          });
        },
        abrirAba: function (evt) {
          this.mostrarAba(evt.currentTarget.getAttribute('data-aba'));
        },

        atualizar: function () {
          var raiz = this.$root;
          var linhas = [];
          DIMENSOES.forEach(function (dim) {
            var mudancas = [];
            var marcados = 0;
            caixas(raiz, 'input[type="checkbox"][data-dim="' + dim + '"]').forEach(function (cx) {
              var inicial = cx.getAttribute('data-inicial') === 'S';
              var rotulo = cx.getAttribute('data-diff');
              if (cx.checked) {
                marcados++;
              }
              if (cx.disabled || cx.checked === inicial) {
                return;
              }
              mudancas.push({ rotulo: rotulo, sinal: cx.checked ? '+' : '-' });
            });
            // Mesma ordem do servidor: por rotulo e depois sinal ('+' antes de '-').
            mudancas.sort(function (a, b) {
              if (a.rotulo !== b.rotulo) {
                return a.rotulo < b.rotulo ? -1 : 1;
              }
              return a.sinal < b.sinal ? -1 : (a.sinal > b.sinal ? 1 : 0);
            });
            mudancas.forEach(function (m) { linhas.push(m.sinal + m.rotulo); });
            caixas(raiz, '[data-contador="' + dim + '"]').forEach(function (el) {
              el.textContent = String(marcados);
            });
          });
          this.resumo = linhas;
        },

        marcarGrupo: function (evt) {
          var grupo = evt.currentTarget.getAttribute('data-grupo');
          var conjunto = this.$root.querySelector('fieldset[data-grupo="' + grupo + '"]');
          var editaveis = caixas(conjunto, 'input[type="checkbox"]').filter(function (cx) {
            return !cx.disabled && !cx.closest('[hidden]');
          });
          var todos = editaveis.length > 0 && editaveis.every(function (cx) { return cx.checked; });
          editaveis.forEach(function (cx) { cx.checked = !todos; });
          this.atualizar();
        },

        filtrarScripts: function (evt) {
          var termo = String(evt.target.value || '').trim().toLowerCase();
          var painel = this.$root.querySelector('[data-painel="scrs"]');
          var algum = false;
          caixas(painel, 'fieldset[data-grupo]').forEach(function (conjunto) {
            var visiveis = 0;
            caixas(conjunto, '[data-busca]').forEach(function (item) {
              var ok = !termo || item.getAttribute('data-busca').indexOf(termo) !== -1;
              item.hidden = !ok;
              if (ok) {
                visiveis++;
              }
            });
            conjunto.hidden = visiveis === 0;
            if (visiveis) {
              algum = true;
            }
          });
          painel.querySelector('[data-sem-resultado]').hidden = algum;
        }
      };
    });
  });
}());
