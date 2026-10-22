/* SSS - formulario do dicionario de parametros (README §6.2).
 * Carregado com defer ANTES do alpine.min.js. Campos condicionais por tipo, editor de pares
 * valor/rotulo (o JSON e montado so por conveniencia: o servidor faz json.loads e valida tudo) e
 * "Testar valor" contra a configuracao em edicao. A regex digitada nunca roda no navegador.
 */
(function () {
  'use strict';

  // O servidor entrega as opcoes como lista de pares [valor, rotulo]: JSON.parse de um objeto
  // reordenaria chaves numericas ("2" antes de "1" viraria "1", "2").
  function opcoesIniciais(campo) {
    var pares;
    var bruto = campo.getAttribute('data-pares');
    if (!bruto) {
      return { linhas: [], valido: !campo.getAttribute('value') };
    }
    try {
      pares = JSON.parse(bruto);
    } catch (erro) {
      return { linhas: [], valido: false };
    }
    if (!Array.isArray(pares)) {
      return { linhas: [], valido: false };
    }
    return {
      linhas: pares.map(function (par) {
        return { valor: String(par[0]), rotulo: typeof par[1] === 'string' ? par[1] : '' };
      }),
      valido: true
    };
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('parametroForm', function () {
      return {
        tipo: 'TEXT',
        sensivel: false,
        linhas: [],
        editado: false,
        opcoesBrutas: '',
        testando: false,
        resultadoTeste: '',
        testeOk: null,

        init: function () {
          var inicial;
          this.tipo = this.$refs.tipo.value;
          this.sensivel = this.$refs.sensivel.checked;
          this.opcoesBrutas = this.$refs.opcoes.getAttribute('value') || '';
          inicial = opcoesIniciais(this.$refs.opcoes);
          this.linhas = inicial.linhas;
          // JSON reapresentado invalido (apos erro) segue intacto ate o usuario editar a lista.
          this.editado = inicial.valido;
          if (this.tipo === 'SELECT' && !this.linhas.length) {
            this.linhas.push({ valor: '', rotulo: '' });
          }
          this.ajustarRegex();
        },

        get ehSelect() {
          return this.tipo === 'SELECT';
        },
        get ehTexto() {
          return this.tipo === 'TEXT';
        },
        get tipoPadrao() {
          return this.sensivel ? 'password' : 'text';
        },
        get classeTeste() {
          if (this.testeOk === null) {
            return '';
          }
          return this.testeOk ? 'sss-teste-ok' : 'sss-teste-erro';
        },
        get opcoesJson() {
          var partes = [];
          if (!this.ehSelect) {
            return '';
          }
          if (!this.editado) {
            return this.opcoesBrutas;
          }
          // Montagem manual: objetos JS reordenam chaves numericas, e a ordem do usuario importa.
          this.linhas.forEach(function (linha) {
            var valor = String(linha.valor || '');
            var rotulo = String(linha.rotulo || '');
            if (valor.trim() || rotulo.trim()) {
              partes.push(JSON.stringify(valor) + ':' + JSON.stringify(rotulo));
            }
          });
          return partes.length ? '{' + partes.join(',') + '}' : '';
        },

        trocarTipo: function (evt) {
          this.tipo = evt.target.value;
          if (this.ehSelect && !this.linhas.length) {
            this.linhas.push({ valor: '', rotulo: '' });
          }
          this.limparTeste();
          this.ajustarRegex();
        },
        ajustarRegex: function () {
          // Campo oculto pelo tipo nao e enviado: o servidor rejeitaria regex fora de Texto.
          var campo = this.$root.querySelector('#campo-regex_validacao');
          if (campo) {
            campo.disabled = !this.ehTexto;
          }
        },
        trocarSensivel: function (evt) {
          this.sensivel = evt.target.checked;
        },
        editarLinha: function (evt) {
          var i = parseInt(evt.target.getAttribute('data-i'), 10);
          var campo = evt.target.getAttribute('data-campo');
          if (this.linhas[i] && (campo === 'valor' || campo === 'rotulo')) {
            this.linhas[i][campo] = evt.target.value;
            this.editado = true;
          }
        },
        adicionarLinha: function () {
          this.linhas.push({ valor: '', rotulo: '' });
          this.editado = true;
        },
        removerLinha: function (evt) {
          var i = parseInt(evt.target.getAttribute('data-i'), 10);
          this.linhas.splice(i, 1);
          this.editado = true;
        },
        limparTeste: function () {
          this.resultadoTeste = '';
          this.testeOk = null;
        },

        testar: function () {
          var self = this;
          var form = this.$root;
          var corpo = new URLSearchParams();
          var dados = new FormData(form);
          dados.forEach(function (valor, chave) {
            if (chave !== 'default_value') {
              corpo.append(chave, valor);
            }
          });
          corpo.set('options_json', this.opcoesJson);
          corpo.set('test_value', this.$refs.valorTeste.value);
          this.testando = true;
          this.limparTeste();
          window.SSS.fetch(form.getAttribute('data-url-testar'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: corpo.toString()
          }).then(function (resposta) {
            return resposta.json();
          }).then(function (r) {
            self.testeOk = r.ok === true;
            self.resultadoTeste = r.ok === true ? 'Válido. Valor normalizado: ' + r.valor : (r.erro || 'Valor inválido.');
          }).catch(function () {
            self.testeOk = false;
            self.resultadoTeste = 'Não foi possível testar agora. Tente novamente.';
          }).then(function () {
            self.testando = false;
          });
        }
      };
    });
  });
}());
