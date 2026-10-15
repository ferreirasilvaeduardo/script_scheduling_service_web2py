/* SSS - cadastro de scripts: homologacao por ambiente e vinculo ordenado de parametros (README §6.3).
 * Carregado com defer ANTES do alpine.min.js. Listas montadas aqui sao conveniencia: o servidor
 * revalida tudo (IDs, ativos, duplicidade, flags, valores padrao) e renumera a ordem.
 */
(function () {
  'use strict';

  function lerJson(el, atributo, padrao) {
    try {
      return JSON.parse(el.getAttribute(atributo) || '');
    } catch (erro) {
      return padrao;
    }
  }

  // O build CSP do Alpine nao avalia concatenacao nem ternario no HTML: derivados ficam na propria linha.
  function linhaVinculo(dados) {
    var l = {
      id: dados.id, codigo: dados.codigo, label: dados.label, flag: dados.flag, sensivel: dados.sensivel === true,
      ativo: dados.ativo !== false, obrigatorio: dados.obrigatorio === true, sub: dados.sub || '',
      temSub: dados.temSub === true
    };
    l.idObrig = 'obrig-' + l.id;
    l.tipoSub = l.sensivel ? 'password' : 'text';
    l.dicaSub = l.sensivel && l.temSub ? 'Valor sigiloso gravado (em branco mantém)' : 'Valor padrão específico (opcional)';
    l.rotuloSubir = 'Subir ' + l.codigo;
    l.rotuloDescer = 'Descer ' + l.codigo;
    l.rotuloRemover = 'Remover ' + l.codigo;
    return l;
  }

  function caixas(raiz, seletor) {
    return Array.prototype.slice.call(raiz.querySelectorAll(seletor));
  }

  document.addEventListener('alpine:init', function () {
    // Homologacao: resumo +/- e aviso de agendamentos afetados pelos ambientes removidos.
    window.Alpine.data('homologacaoScript', function () {
      return {
        resumo: [],
        afetados: 0,
        get semAlteracoes() {
          return this.resumo.length === 0;
        },
        get temAlteracoes() {
          return this.resumo.length > 0;
        },
        get temAfetados() {
          return this.afetados > 0;
        },
        get avisoAfetados() {
          return this.afetados + ' agendamento(s) ativo(s) nos ambientes removidos serão pausados no próximo ciclo.';
        },
        init: function () {
          this.atualizar();
        },
        atualizar: function () {
          var mais = [];
          var menos = [];
          var afetados = 0;
          caixas(this.$root, 'input[type="checkbox"][name="ambientes"]').forEach(function (cx) {
            var inicial = cx.getAttribute('data-inicial') === 'S';
            if (cx.disabled || cx.checked === inicial) {
              return;
            }
            if (cx.checked) {
              mais.push('+' + cx.getAttribute('data-nome'));
            } else {
              menos.push('-' + cx.getAttribute('data-nome'));
              afetados += parseInt(cx.getAttribute('data-agendamentos'), 10) || 0;
            }
          });
          mais.sort();
          menos.sort();
          this.resumo = mais.concat(menos);
          this.afetados = afetados;
        }
      };
    });

    // Vinculos: lista ordenavel (subir/descer, sem arrastar), busca no dicionario e previa do argv.
    window.Alpine.data('vinculosScript', function () {
      return {
        linhas: [],
        disponiveis: [],
        termo: '',
        previaTexto: '',
        previaErros: [],
        previaAviso: '',
        carregando: false,

        init: function () {
          var raiz = this.$root;
          this.disponiveis = lerJson(raiz, 'data-disponiveis', []);
          this.linhas = lerJson(raiz, 'data-vinculos', []).map(function (v) {
            return linhaVinculo({ id: v.id, codigo: v.codigo, label: v.label, flag: v.param_nomeado,
                                  sensivel: v.sensivel, ativo: v.ativo, obrigatorio: v.obrigatorio,
                                  sub: v.valor_padrao_sub, temSub: v.tem_sub });
          });
        },

        get vinculosJson() {
          return JSON.stringify(this.linhas.map(function (l) {
            return {
              parametro_id: l.id, obrigatorio: l.obrigatorio, valor_padrao_sub: l.sub,
              manter_sigiloso: l.sensivel && l.temSub && !l.sub
            };
          }));
        },
        get resultados() {
          var termo = this.termo.trim().toLowerCase();
          var usados = {};
          this.linhas.forEach(function (l) { usados[l.id] = true; });
          return this.disponiveis.filter(function (p) {
            if (usados[p.id]) {
              return false;
            }
            return !termo || (p.codigo + ' ' + p.label).toLowerCase().indexOf(termo) !== -1;
          }).slice(0, 15);
        },
        get semVinculos() {
          return this.linhas.length === 0;
        },
        get semResultados() {
          return this.resultados.length === 0;
        },
        get temPrevia() {
          return this.previaTexto !== '';
        },
        get temErrosPrevia() {
          return this.previaErros.length > 0;
        },
        get temAvisoPrevia() {
          return this.previaAviso !== '';
        },

        indice: function (evt) {
          return parseInt(evt.currentTarget.getAttribute('data-i'), 10);
        },
        buscar: function (evt) {
          this.termo = evt.target.value;
        },
        adicionar: function (evt) {
          var id = parseInt(evt.currentTarget.getAttribute('data-id'), 10);
          var p = this.disponiveis.filter(function (d) { return d.id === id; })[0];
          if (p) {
            this.linhas.push(linhaVinculo({ id: p.id, codigo: p.codigo, label: p.label, flag: p.param_nomeado,
                                            sensivel: p.sensivel, ativo: true, obrigatorio: false }));
          }
        },
        mover: function (evt) {
          var i = this.indice(evt);
          var destino = i + parseInt(evt.currentTarget.getAttribute('data-delta'), 10);
          var linha;
          if (destino < 0 || destino >= this.linhas.length) {
            return;
          }
          linha = this.linhas.splice(i, 1)[0];
          this.linhas.splice(destino, 0, linha);
        },
        remover: function (evt) {
          this.linhas.splice(this.indice(evt), 1);
        },
        alternarObrigatorio: function (evt) {
          this.linhas[this.indice(evt)].obrigatorio = evt.currentTarget.checked;
        },
        editarSub: function (evt) {
          this.linhas[this.indice(evt)].sub = evt.currentTarget.value;
        },

        previa: function () {
          var self = this;
          var form = this.$root;
          var corpo = new URLSearchParams();
          corpo.set('_csrf', form.querySelector('input[name="_csrf"]').value);
          corpo.set('id', form.querySelector('input[name="id"]').value);
          corpo.set('vinculos_json', this.vinculosJson);
          this.carregando = true;
          this.previaTexto = '';
          this.previaErros = [];
          this.previaAviso = '';
          window.SSS.fetch(form.getAttribute('data-url-previa'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: corpo.toString()
          }).then(function (resposta) {
            return resposta.json();
          }).then(function (r) {
            var chave;
            if (r.argv) {
              self.previaTexto = r.argv.join(' ');
            }
            for (chave in (r.erros || {})) {
              if (Object.prototype.hasOwnProperty.call(r.erros, chave)) {
                self.previaErros.push(r.erros[chave]);
              }
            }
            self.previaAviso = r.aviso || '';
          }).catch(function () {
            self.previaErros = ['Não foi possível gerar a prévia agora. Tente novamente.'];
          }).then(function () {
            self.carregando = false;
          });
        }
      };
    });
  });
}());
