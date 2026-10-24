/* SSS - base dos componentes em JavaScript puro (CR-021, D7).
 * Componente e um elemento com data-component="<nome>", montado uma unica vez no DOMContentLoaded pela
 * fabrica registrada em SSS.component(nome, fabrica). Eventos chegam por delegacao (data-action),
 * elementos por data-ref e texto so por textContent: nada de expressao no HTML nem de innerHTML.
 * Carregado com defer ANTES dos demais arquivos de static/js/app/, que registram os componentes
 * (todos tambem com defer, para rodarem antes do DOMContentLoaded).
 */
(function () {
  'use strict';

  var SSS = window.SSS = window.SSS || {};
  var factories = {};
  var MOUNTED_ATTR = 'data-component-mounted';

  // Um elemento pertence ao componente mais proximo: refs e acoes de um componente aninhado nao vazam.
  function owner(el) {
    return el.closest('[data-component]');
  }

  function refs(root, name) {
    var found = root.querySelectorAll('[data-ref="' + name + '"]');
    var result = [];
    var i;
    for (i = 0; i < found.length; i++) {
      if (owner(found[i]) === root) {
        result.push(found[i]);
      }
    }
    return result;
  }

  function ref(root, name) {
    var found = refs(root, name);
    return found.length ? found[0] : null;
  }

  // handler(evt, el) recebe o elemento com o data-action, mesmo quando o alvo e um filho dele.
  function on(root, type, action, handler) {
    root.addEventListener(type, function (evt) {
      var el = evt.target.closest ? evt.target.closest('[data-action]') : null;
      if (!el || !root.contains(el) || owner(el) !== root) {
        return;
      }
      if (el.getAttribute('data-action') === action) {
        handler(evt, el);
      }
    });
  }

  function show(el, visible) {
    el.hidden = !visible;
  }

  function setText(el, value) {
    el.textContent = value === null || value === undefined ? '' : String(value);
  }

  // Copia o primeiro elemento de um <template>; o conteudo vem do servidor, os dados entram por setText.
  function clone(template) {
    return template.content.firstElementChild.cloneNode(true);
  }

  SSS.dom = {
    ref: ref,
    refs: refs,
    on: on,
    show: show,
    setText: setText,
    clone: clone
  };

  SSS.component = function (name, factory) {
    if (factories[name]) {
      throw new Error('SSS: componente registrado duas vezes: ' + name);
    }
    factories[name] = factory;
  };

  function mountAll() {
    var roots = document.querySelectorAll('[data-component]');
    var i;
    var name;
    for (i = 0; i < roots.length; i++) {
      name = roots[i].getAttribute('data-component');
      if (roots[i].hasAttribute(MOUNTED_ATTR)) {
        continue;
      }
      if (!factories[name]) {
        window.console.error('SSS: componente sem registro: ' + name);
        continue;
      }
      roots[i].setAttribute(MOUNTED_ATTR, '');
      factories[name](roots[i]);
    }
  }

  // Scripts com defer rodam com readyState 'interactive', antes do DOMContentLoaded: montar ja aqui
  // perderia os registros dos arquivos carregados depois deste.
  document.addEventListener('DOMContentLoaded', mountAll);
}());
