/* SSS - formulario de regra de agendamento (agendamentos/form).
 * Carregado com defer ANTES do alpine.min.js. Nenhuma regra decisoria fica aqui: os campos
 * condicionais so ajudam o preenchimento e a previa e calculada pelo servidor (recurrence.py).
 */
(function () {
  'use strict';

  var DEBOUNCE_MS = 500;
  var CAMPOS = ['tipo_recorrencia', 'data_inicio', 'data_fim', 'hora_execucao', 'dia_mes', 'expressao_cron'];

  function valor(form, nome) {
    var campo = form.elements[nome];
    return campo && typeof campo.value === 'string' ? campo.value : '';
  }

  // Checkboxes seg-dom -> '1,3,5' (ISO 1-7, README §7.2).
  function diasSemana(form) {
    var marcados = form.querySelectorAll('input[name="dias_semana"]:checked');
    var dias = [];
    var i;
    for (i = 0; i < marcados.length; i++) {
      dias.push(marcados[i].value);
    }
    return dias.join(',');
  }

  function listar(itens) {
    var lista = [];
    var i;
    for (i = 0; i < itens.length; i++) {
      lista.push({ id: i, texto: String(itens[i]) });
    }
    return lista;
  }

  function valoresDoMapa(mapa) {
    var lista = [];
    var chave;
    for (chave in mapa) {
      if (Object.prototype.hasOwnProperty.call(mapa, chave)) {
        lista.push(mapa[chave]);
      }
    }
    return lista;
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('regraAgendamento', function () {
      return {
        tipo: '',
        carregando: false,
        descricao: '',
        datas: [],
        erros: [],
        temporizador: null,
        sequencia: 0,
        init: function () {
          this.tipo = this.$refs.tipo.value;
          this.carregar();
        },
        get ehUnica() { return this.tipo === 'UNICA'; },
        get naoUnica() { return this.tipo !== 'UNICA'; },
        get temHora() { return this.tipo === 'DIARIA' || this.tipo === 'SEMANAL' || this.tipo === 'MENSAL'; },
        get ehSemanal() { return this.tipo === 'SEMANAL'; },
        get ehMensal() { return this.tipo === 'MENSAL'; },
        get ehCron() { return this.tipo === 'CRON'; },
        get temDescricao() { return this.descricao !== ''; },
        get temDatas() { return this.datas.length > 0; },
        get temErros() { return this.erros.length > 0; },
        alterarTipo: function () {
          this.tipo = this.$refs.tipo.value;
          if (this.tipo === 'UNICA') {
            // data_fim nao se aplica a UNICA (README §7.2): o campo escondido e limpo.
            var fim = this.$root.querySelector('#campo-data_fim');
            if (fim) {
              fim.value = '';
            }
          }
        },
        agendarPrevia: function () {
          var self = this;
          if (this.temporizador) {
            window.clearTimeout(this.temporizador);
          }
          this.temporizador = window.setTimeout(function () {
            self.temporizador = null;
            self.carregar();
          }, DEBOUNCE_MS);
        },
        carregar: function () {
          var self = this;
          var form = this.$root;
          var corpo = { dias_semana: diasSemana(form) };
          var i;
          // Respostas fora de ordem sao descartadas: so a ultima requisicao atualiza a tela.
          var numero = ++this.sequencia;
          for (i = 0; i < CAMPOS.length; i++) {
            corpo[CAMPOS[i]] = valor(form, CAMPOS[i]);
          }
          this.carregando = true;
          window.sssFetch(form.getAttribute('data-url-previa'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(corpo)
          }).then(function (resposta) {
            if (resposta.status === 403) {
              return null;
            }
            return resposta.json();
          }).then(function (dados) {
            if (!dados || numero !== self.sequencia) {
              return;
            }
            self.descricao = dados.descricao || '';
            self.datas = listar(dados.datas || []);
            self.erros = listar(valoresDoMapa(dados.erros || {}));
          }).catch(function () {
            if (numero === self.sequencia) {
              window.SSS.toast('erro', 'Não foi possível calcular a prévia. Tente novamente.');
            }
          }).then(function () {
            if (numero === self.sequencia) {
              self.carregando = false;
            }
          });
        }
      };
    });
  });
}());
