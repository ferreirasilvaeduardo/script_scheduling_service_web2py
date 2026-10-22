/* SSS - tela de disparo de script (tickets/new).
 * Carregado com defer ANTES do alpine.min.js. Nenhuma regra decisoria fica aqui: o servidor
 * revalida tudo; o cliente apenas filtra a lista e exibe a previa devolvida pelo servidor.
 */
(function () {
  'use strict';

  var PREFIXO_PARAM = 'p_';
  var RE_TOKEN_SIMPLES = /^[A-Za-z0-9_@%+=:,.\/-]+$/;

  function normalizar(texto) {
    return String(texto || '').toLowerCase().replace(/^\s+|\s+$/g, '');
  }

  // Apenas para exibicao: o argv real e uma lista e nunca passa por shell.
  function tokenExibicao(token) {
    if (RE_TOKEN_SIMPLES.test(token)) {
      return token;
    }
    return "'" + String(token).replace(/'/g, "'\\''") + "'";
  }

  // Ordem do DOM: o hidden "false" vem antes do checkbox, que so sobrescreve quando marcado.
  function coletarRespostas(form) {
    var respostas = {};
    var campos = form.elements;
    var i;
    var campo;
    var codigo;
    for (i = 0; i < campos.length; i++) {
      campo = campos[i];
      if (!campo.name || campo.name.indexOf(PREFIXO_PARAM) !== 0 || campo.disabled) {
        continue;
      }
      codigo = campo.name.substring(PREFIXO_PARAM.length);
      if (campo.type === 'checkbox') {
        if (campo.checked) {
          respostas[codigo] = campo.value;
        }
      } else {
        respostas[codigo] = campo.value;
      }
    }
    return respostas;
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('buscaScript', function () {
      return {
        semResultado: false,
        filtrar: function () {
          var termo = normalizar(this.$refs.busca.value);
          var grupos = this.$root.querySelectorAll('[data-grupo]');
          var visiveisTotal = 0;
          var g;
          var itens;
          var i;
          var visiveis;
          var mostra;
          for (g = 0; g < grupos.length; g++) {
            itens = grupos[g].querySelectorAll('[data-busca]');
            visiveis = 0;
            for (i = 0; i < itens.length; i++) {
              mostra = termo === '' || itens[i].getAttribute('data-busca').indexOf(termo) !== -1;
              itens[i].hidden = !mostra;
              if (mostra) {
                visiveis++;
              }
            }
            grupos[g].hidden = visiveis === 0;
            visiveisTotal += visiveis;
          }
          this.semResultado = visiveisTotal === 0;
        }
      };
    });

    // Resumo em frase do modal de confirmacao (README §5.4): montado pelo servidor ao abrir o modal.
    window.Alpine.data('resumoDisparo', function () {
      return {
        carregando: false,
        script: '',
        ambiente: '',
        quando: '',
        prioridade: '',
        comando: '',
        respostas: [],
        erros: [],
        get temResumo() { return this.script !== ''; },
        get temRespostas() { return this.respostas.length > 0; },
        get temErros() { return this.erros.length > 0; },
        init: function () {
          var self = this;
          var form = this.$root.closest('form');
          var gatilho = form.querySelector('[data-resumo-gatilho]');
          if (gatilho) {
            gatilho.addEventListener('click', function () { self.carregar(); });
          }
        },
        carregar: function () {
          var self = this;
          var form = this.$root.closest('form');
          var corpo = {
            script_id: form.elements.script_id.value,
            ambiente: form.elements.ambiente.value,
            prioridade: form.elements.prioridade ? form.elements.prioridade.value : '',
            scheduled_at: form.elements.scheduled_at ? form.elements.scheduled_at.value : '',
            respostas: coletarRespostas(form)
          };
          this.carregando = true;
          this.script = '';
          this.erros = [];
          window.sssFetch(this.$root.getAttribute('data-url'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(corpo)
          }).then(function (resposta) {
            return resposta.json();
          }).then(function (dados) {
            var chave;
            if (dados && dados.resumo) {
              self.script = dados.resumo.script;
              self.ambiente = dados.resumo.ambiente;
              self.quando = dados.resumo.quando;
              self.prioridade = String(dados.resumo.prioridade);
              self.respostas = dados.resumo.respostas.map(function (r, i) {
                return { id: i, rotulo: r.rotulo, valor: String(r.valor) };
              });
              self.comando = (dados.argv || []).map(tokenExibicao).join(' ');
            } else {
              for (chave in (dados && dados.erros) || {}) {
                if (Object.prototype.hasOwnProperty.call(dados.erros, chave)) {
                  self.erros.push({ id: self.erros.length, texto: String(dados.erros[chave]) });
                }
              }
              if (!self.erros.length) {
                self.erros.push({ id: 0, texto: (dados && dados.erro) || 'Não foi possível montar o resumo.' });
              }
            }
          }).catch(function () {
            self.erros = [{ id: 0, texto: 'Não foi possível montar o resumo. Tente novamente.' }];
          }).then(function () {
            self.carregando = false;
          });
        }
      };
    });

    window.Alpine.data('previa', function () {
      return {
        carregando: false,
        comando: '',
        erros: [],
        get temComando() {
          return this.comando !== '';
        },
        get temErros() {
          return this.erros.length > 0;
        },
        mostrarErros: function (mapa) {
          var lista = [];
          var chave;
          for (chave in mapa) {
            if (Object.prototype.hasOwnProperty.call(mapa, chave)) {
              lista.push({ id: lista.length, texto: String(mapa[chave]) });
            }
          }
          this.erros = lista;
        },
        carregar: function () {
          var self = this;
          var form = this.$root.closest('form');
          var corpo = {
            script_id: form.elements.script_id.value,
            ambiente: form.elements.ambiente.value,
            respostas: coletarRespostas(form)
          };
          this.carregando = true;
          this.comando = '';
          this.erros = [];
          window.sssFetch(this.$root.getAttribute('data-url'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(corpo)
          }).then(function (resposta) {
            if (resposta.status === 403) {
              return null;
            }
            return resposta.json();
          }).then(function (dados) {
            if (!dados) {
              return;
            }
            if (dados.argv) {
              self.comando = dados.argv.map(tokenExibicao).join(' ');
            } else {
              self.mostrarErros(dados.erros || {});
            }
          }).catch(function () {
            window.SSS.toast('erro', 'Não foi possível gerar a prévia. Tente novamente.');
          }).then(function () {
            self.carregando = false;
          });
        }
      };
    });
  });
}());
