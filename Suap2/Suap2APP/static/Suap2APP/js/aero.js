// Melhorias opcionais: o site funciona igual sem este arquivo.
(function () {
    'use strict';

    // Botão de fechar nas mensagens. Ele é criado aqui, e não no HTML, para não
    // aparecer um botão que não faz nada quando o JavaScript está desligado.
    document.querySelectorAll('.mensagem').forEach(function (mensagem) {
        var botao = document.createElement('button');
        botao.type = 'button';
        botao.className = 'mensagem-fechar';
        botao.setAttribute('aria-label', 'Fechar mensagem');
        botao.innerHTML = '<span aria-hidden="true">&times;</span>';

        botao.addEventListener('click', function () {
            var lista = mensagem.parentNode;
            mensagem.classList.add('saindo');
            window.setTimeout(function () {
                mensagem.remove();
                if (lista && !lista.children.length) {
                    lista.remove();
                }
            }, 230);
        });

        mensagem.appendChild(botao);
    });
})();
