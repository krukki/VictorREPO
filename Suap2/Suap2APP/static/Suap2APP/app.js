// Suap2 — comportamentos da página. Tudo aqui é um extra: sem JavaScript o site
// continua funcionando (o quadro usa as setas, e "Nova tarefa" abre o formulário completo).
(function () {
    'use strict';

    var CHAVE_TEMA = 'suap2-tema';
    var CHAVE_RESPONSAVEL = 'suap2-ultimo-responsavel';

    // localStorage pode não existir (janela anônima, bloqueio de cookies): nunca deixa quebrar
    function ler(chave) {
        try { return localStorage.getItem(chave); } catch (e) { return null; }
    }
    function gravar(chave, valor) {
        try { localStorage.setItem(chave, valor); } catch (e) { /* sem onde guardar */ }
    }

    function csrf() {
        var campo = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return campo ? campo.value : '';
    }

    function postar(url, dados) {
        return fetch(url, {
            method: 'POST',
            body: dados,
            headers: { 'X-CSRFToken': csrf(), 'Accept': 'application/json' },
            credentials: 'same-origin'
        });
    }

    // Tema claro/escuro -------------------------------------------------------

    function temaAtual() {
        var escolhido = document.documentElement.dataset.theme;
        if (escolhido) return escolhido;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    document.querySelectorAll('[data-alternar-tema]').forEach(function (botao) {
        botao.addEventListener('click', function () {
            var novo = temaAtual() === 'dark' ? 'light' : 'dark';
            document.documentElement.dataset.theme = novo;
            gravar(CHAVE_TEMA, novo === 'dark' ? 'escuro' : 'claro');
        });
    });

    // Menus suspensos: fecham ao clicar fora ou apertar Esc --------------------

    document.addEventListener('click', function (evento) {
        document.querySelectorAll('details.suspenso[open]').forEach(function (menu) {
            if (!menu.contains(evento.target)) menu.removeAttribute('open');
        });
    });

    // Filtros começam fechados em telas pequenas, a não ser que algum esteja em uso
    if (window.matchMedia('(max-width: 1080px)').matches) {
        document.querySelectorAll('[data-filtros]:not([data-filtrando])').forEach(function (caixa) {
            caixa.removeAttribute('open');
        });
    }

    // Janelas (<dialog>) ------------------------------------------------------

    document.querySelectorAll('dialog [data-fechar]').forEach(function (botao) {
        botao.addEventListener('click', function () { botao.closest('dialog').close(); });
    });
    document.querySelectorAll('dialog').forEach(function (janela) {
        // Clique no fundo escuro fecha a janela
        janela.addEventListener('click', function (evento) {
            if (evento.target === janela) janela.close();
        });
    });

    // Adição rápida -----------------------------------------------------------

    var janelaRapida = document.getElementById('janela-rapida');
    var botaoRapida = document.querySelector('[data-abrir-rapida]');

    function abrirRapida() {
        if (!janelaRapida || !botaoRapida) return;
        var corpo = janelaRapida.querySelector('[data-conteudo-rapida]');
        janelaRapida.showModal();
        fetch(botaoRapida.dataset.url, { credentials: 'same-origin' })
            .then(function (resposta) {
                if (!resposta.ok) throw new Error(resposta.status);
                return resposta.text();
            })
            .then(function (html) {
                corpo.innerHTML = html;
                prepararFormRapida(corpo.querySelector('[data-form-rapida]'));
            })
            .catch(function () {
                corpo.innerHTML = '<p class="erro">Não foi possível abrir a adição rápida. ' +
                    'Use o botão "Nova tarefa".</p>';
            });
    }

    function prepararFormRapida(form) {
        if (!form) return;
        var texto = form.querySelector('input[name="texto"]');
        var responsavel = form.querySelector('select[name="pessoa_responsavel"]');
        var caixaErros = form.querySelector('[data-erros-rapida]');
        var ultimo = ler(CHAVE_RESPONSAVEL);
        if (responsavel && ultimo && responsavel.querySelector('option[value="' + ultimo + '"]')) {
            responsavel.value = ultimo;
        }
        if (texto) texto.focus();

        form.addEventListener('submit', function (evento) {
            evento.preventDefault();
            var botao = form.querySelector('button[type="submit"]');
            botao.disabled = true;
            postar(form.action, new FormData(form))
                .then(function (resposta) { return resposta.json(); })
                .then(function (dados) {
                    if (dados.ok) {
                        if (responsavel && responsavel.value) gravar(CHAVE_RESPONSAVEL, responsavel.value);
                        // Recarrega para a tarefa nova aparecer, com a mensagem de sucesso
                        window.location.reload();
                        return;
                    }
                    caixaErros.textContent = dados.erros.join(' ');
                    caixaErros.hidden = false;
                    botao.disabled = false;
                    if (texto) texto.focus();
                })
                .catch(function () {
                    caixaErros.textContent = 'Não foi possível salvar. Verifique a conexão e tente de novo.';
                    caixaErros.hidden = false;
                    botao.disabled = false;
                });
        });
    }

    if (botaoRapida) botaoRapida.addEventListener('click', abrirRapida);

    // Atalhos do teclado ------------------------------------------------------

    var janelaAtalhos = document.getElementById('janela-atalhos');
    document.querySelectorAll('[data-abrir-atalhos]').forEach(function (botao) {
        botao.addEventListener('click', function () {
            botao.closest('details').removeAttribute('open');
            janelaAtalhos.showModal();
        });
    });

    var urls = document.querySelector('[data-urls]');
    var esperandoG = false;
    var tempoG = null;

    function digitando(alvo) {
        var tag = alvo.tagName;
        return alvo.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
    }

    document.addEventListener('keydown', function (evento) {
        if (evento.key === 'Escape') {
            document.querySelectorAll('details.suspenso[open]').forEach(function (m) { m.removeAttribute('open'); });
        }
        if (!urls || evento.ctrlKey || evento.metaKey || evento.altKey) return;
        if (digitando(evento.target) || document.querySelector('dialog[open]')) return;

        var tecla = evento.key.toLowerCase();
        if (esperandoG) {
            esperandoG = false;
            clearTimeout(tempoG);
            var destino = { p: 'painel', t: 'tarefas', q: 'quadro', c: 'calendario' }[tecla];
            if (destino) {
                evento.preventDefault();
                window.location.href = urls.dataset[destino];
            }
            return;
        }
        if (tecla === 'g') {
            esperandoG = true;
            tempoG = setTimeout(function () { esperandoG = false; }, 1200);
        } else if (tecla === 'n') {
            evento.preventDefault();
            abrirRapida();
        } else if (tecla === '/') {
            var busca = document.querySelector('input[name="q"]');
            if (busca) {
                evento.preventDefault();
                busca.focus();
                busca.select();
            }
        } else if (evento.key === '?') {
            evento.preventDefault();
            janelaAtalhos.showModal();
        }
    });

    // Quadro (kanban) ---------------------------------------------------------

    var quadro = document.querySelector('[data-quadro]');
    if (!quadro) return;

    var arrastado = null;

    function atualizarTotais() {
        quadro.querySelectorAll('[data-coluna]').forEach(function (coluna) {
            coluna.querySelector('[data-total]').textContent =
                coluna.querySelectorAll('[data-cartao]').length;
        });
    }

    // As setas de cada cartão apontam para as colunas vizinhas da coluna onde ele está
    function atualizarSetas(cartao) {
        var coluna = cartao.closest('[data-coluna]');
        ['anterior', 'proxima'].forEach(function (lado) {
            var botao = cartao.querySelector('[data-mover="' + lado + '"]');
            var destino = coluna.dataset[lado];
            botao.value = destino;
            botao.hidden = !destino;
        });
    }

    function mover(cartao, colunaDestino) {
        var colunaOrigem = cartao.closest('[data-coluna]');
        if (colunaOrigem === colunaDestino) return;
        // Muda na tela na hora; se o servidor recusar, desfaz
        colunaDestino.querySelector('[data-cartoes]').prepend(cartao);
        atualizarSetas(cartao);
        atualizarTotais();

        var dados = new FormData();
        dados.append('situacao', colunaDestino.dataset.coluna);
        postar(cartao.dataset.url, dados)
            .then(function (resposta) {
                if (!resposta.ok) throw new Error(resposta.status);
            })
            .catch(function () {
                colunaOrigem.querySelector('[data-cartoes]').prepend(cartao);
                atualizarSetas(cartao);
                atualizarTotais();
                alert('Não foi possível mover a tarefa. Tente de novo.');
            });
    }

    quadro.addEventListener('dragstart', function (evento) {
        var cartao = evento.target.closest && evento.target.closest('[data-cartao]');
        if (!cartao) return;
        arrastado = cartao;
        cartao.classList.add('arrastando');
        evento.dataTransfer.effectAllowed = 'move';
        evento.dataTransfer.setData('text/plain', cartao.dataset.url);
    });

    quadro.addEventListener('dragend', function () {
        if (arrastado) arrastado.classList.remove('arrastando');
        arrastado = null;
        quadro.querySelectorAll('.alvo').forEach(function (c) { c.classList.remove('alvo'); });
    });

    quadro.querySelectorAll('[data-coluna]').forEach(function (coluna) {
        coluna.addEventListener('dragover', function (evento) {
            if (!arrastado) return;
            evento.preventDefault();
            evento.dataTransfer.dropEffect = 'move';
            coluna.classList.add('alvo');
        });
        coluna.addEventListener('dragleave', function (evento) {
            if (!coluna.contains(evento.relatedTarget)) coluna.classList.remove('alvo');
        });
        coluna.addEventListener('drop', function (evento) {
            evento.preventDefault();
            coluna.classList.remove('alvo');
            if (arrastado) mover(arrastado, coluna);
        });
    });

    // As setas também movem sem recarregar a página
    quadro.addEventListener('click', function (evento) {
        var botao = evento.target.closest('[data-mover]');
        if (!botao) return;
        evento.preventDefault();
        var destino = quadro.querySelector('[data-coluna="' + botao.value + '"]');
        if (destino) mover(botao.closest('[data-cartao]'), destino);
    });
})();
