# Guia do código — Suap2

Este documento explica **como o projeto funciona por dentro**. Para instalar e rodar,
veja o [README.md](README.md).

---

## 0. Antes de tudo: criar seu usuário

O banco (`Suap2/db.sqlite3`) começa vazio e **não existe nenhuma senha de admin
pré-definida** — você cria a sua:

```powershell
cd Suap2
python manage.py migrate            # cria as tabelas
python manage.py createsuperuser    # aqui você escolhe usuário e senha
python manage.py runserver
```

O mesmo usuário serve para o site (`http://127.0.0.1:8000/`) e para o `/admin`.

O Django **nunca guarda a senha em texto**, só um hash. Ou seja: não existe jeito de
"descobrir" uma senha esquecida, só de trocá-la:

```powershell
python manage.py changepassword <usuario>
```

### Dados de exemplo

O banco em si (`db.sqlite3`) **não vai para o Git** — está no `.gitignore`, porque banco de
dados não se versiona. O que está versionado é uma *fixture*: um arquivo JSON com 5
responsáveis e 5 tarefas de exemplo, em `Suap2APP/fixtures/exemplos.json`. Para encher um
banco vazio com eles:

```powershell
python manage.py loaddata exemplos
```

As tarefas de exemplo cobrem os três estados (pendente, atrasada e concluída) e um dos
responsáveis está sem e-mail de propósito, para você ver como o comando de lembretes
ignora esse caso. Os prazos são datas fixas de setembro/outubro de 2026 — com o tempo
todas vão aparecer como atrasadas; é só editar o JSON quando isso incomodar.

---

## 1. Mapa do projeto

A pasta `Suap2/` de fora é o projeto Django (onde fica o `manage.py`). Dentro dela há
duas pastas com nomes parecidos, e vale não confundir:

| Caminho | O que é |
|---|---|
| `Suap2/manage.py` | Porta de entrada de todo comando (`runserver`, `migrate`, `test`…) |
| `Suap2/Suap2/settings.py` | Configuração: banco, idioma, fuso, e-mail, login |
| `Suap2/Suap2/urls.py` | Todas as rotas do site (não há `urls.py` dentro do app) |
| `Suap2/Suap2APP/models.py` | As duas tabelas: `Responsavel` e `Tarefa` |
| `Suap2/Suap2APP/views.py` | A lógica de cada tela |
| `Suap2/Suap2APP/forms.py` | Formulários de cadastro e o formulário de filtros |
| `Suap2/Suap2APP/admin.py` | Como as tabelas aparecem no `/admin` |
| `Suap2/Suap2APP/templates/Suap2APP/` | O HTML |
| `Suap2/Suap2APP/static/Suap2APP/style.css` | Todo o CSS (arquivo único, sem framework) |
| `Suap2/Suap2APP/management/commands/enviar_lembretes.py` | Comando de e-mail |
| `Suap2/Suap2APP/migrations/` | Histórico de mudanças no banco |
| `Suap2/Suap2APP/tests.py` | Os testes automatizados |

Configurações que merecem atenção em `settings.py`:

- `LANGUAGE_CODE = 'pt-br'` e `TIME_ZONE = 'America/Cuiaba'` com `USE_TZ = True` — o banco
  guarda tudo em UTC e o Django converte para o fuso de Cuiabá na hora de exibir. Por isso
  o código usa `timezone.now()` (com fuso) e nunca `datetime.now()`.
- Tudo o que é sensível vem de variável de ambiente com um padrão de desenvolvimento
  (`DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, e as `DJANGO_EMAIL_*`).
- `LOGIN_URL = 'login'` é o que faz o visitante sem login cair na tela de entrar.

---

## 2. Os dois modelos (`Suap2APP/models.py`)

### `Responsavel`

Campos: `nome`, `cpf`, `email`, `telefone`.

O `cpf` é `unique=True` — não pode haver dois responsáveis com o mesmo CPF. Isso só
funciona de verdade porque o formulário normaliza o CPF antes de salvar (veja a seção 4);
sem isso, `52998224725` e `529.982.247-25` entrariam como duas pessoas diferentes.

`Meta.ordering = ['nome']` faz a lista de responsáveis já sair em ordem alfabética sem
nenhum `order_by()` nas views.

### `Tarefa`

Campos: `titulo`, `criada_em`, `prazo`, `concluida_em`, `lembrete_enviado_em`,
`pessoa_responsavel`.

Três decisões importantes:

**1. Não existe um campo booleano "concluída".** O estado sai de `concluida_em` ser `None`
ou não — o mesmo campo guarda *se* foi concluída e *quando*. Por isso todo filtro do
projeto usa `concluida_em__isnull=True` (pendente) ou `isnull=False` (concluída), e nunca
algo como `concluida=True`.

**2. A ordenação padrão já resolve a tela principal** (`models.py:30`):

```python
ordering = [models.F('concluida_em').asc(nulls_first=True), 'prazo']
```

`nulls_first` põe as pendentes (`concluida_em = None`) antes das concluídas, e dentro de
cada grupo ordena pelo prazo. É por isso que `TarefaListView` não chama `order_by()`.

**3. `on_delete=models.PROTECT`** em `pessoa_responsavel`: o banco se recusa a apagar um
responsável que ainda tem tarefas. Esse erro é tratado na view (seção 3).

`lembrete_enviado_em` é `editable=False`: nunca aparece em formulário. Quem mexe nele é só
o comando de e-mail (marca a data ao enviar) e o `TarefaForm.save` (zera quando o prazo
muda).

---

## 3. As views (`Suap2APP/views.py`)

Quase tudo usa as *generic views* do Django (`ListView`, `CreateView`, …), então cada
classe é curta: ela só declara *qual modelo*, *qual formulário* e *para onde vai depois*.

### A hierarquia de mixins

```
FormularioMixin              (views.py:17)  login + mensagem de sucesso + template form.html
├── TarefaFormularioMixin                   modelo Tarefa, TarefaForm, volta pra lista
│   ├── TarefaCreateView                    só muda titulo_pagina e success_message
│   └── TarefaUpdateView
└── ResponsavelFormularioMixin              modelo Responsavel, ResponsavelForm
    ├── ResponsavelCreateView
    └── ResponsavelUpdateView
```

Criar e editar usam **o mesmo template** (`form.html`); a diferença é só o título da
página e a mensagem exibida no fim. Todo formulário é renderizado em um laço genérico
`{% for field in form %}`, então **um campo novo no form aparece sozinho na tela**.

### `TarefaListView`

- `get_queryset()` guarda `self.agora` e `self.filtro` em atributos, para reaproveitá-los
  em `get_context_data()` sem recalcular.
- `select_related('pessoa_responsavel')` traz o responsável na mesma consulta. Sem isso,
  uma lista de 10 tarefas faria 10 consultas extras. Existe um teste que crava esse número
  (`tests.py:65`): se ele quebrar com "esperava 5 queries", provavelmente algum
  `select_related` se perdeu.
- `now` vai para o template para marcar as tarefas atrasadas; `filtrando` diz se algum
  filtro está ativo (muda a mensagem de lista vazia e mostra o botão "Limpar").

### `tarefa_toggle` (`views.py:78`)

É a única view escrita como função, porque é uma ação e não uma tela. Dois cuidados:

- `@require_POST` — concluir uma tarefa muda dados, então não pode acontecer por GET
  (um GET devolve 405). É também por isso que o botão "Concluir" no template é um
  `<form method="post">` e não um link.
- O campo escondido `next` guarda a página de onde você veio, com os filtros, para voltar
  exatamente para lá. Antes de redirecionar, `url_has_allowed_host_and_scheme` confere se
  o endereço é deste site — sem essa checagem, alguém poderia forjar um link que joga o
  usuário em um site externo (*open redirect*).

### `ResponsavelDetailView`

Os três contadores (pendentes, atrasadas, concluídas) saem de **uma única** consulta,
usando `Count('pk', filter=Q(...))` dentro de um `aggregate`, em vez de três `count()`
separados.

### `ResponsavelDeleteView`

- `get_context_data` conta as tarefas da pessoa; o template usa esse número para mostrar
  "Não é possível excluir…" e esconder o botão.
- `form_valid` envolve a exclusão em `try/except ProtectedError` — se alguém tentar
  excluir mesmo assim (via POST direto), a página é re-renderizada com o aviso em vez de
  estourar um erro 500.

---

## 4. Os formulários (`Suap2APP/forms.py`)

### `TarefaForm`

O widget do prazo é `type="datetime-local"`, o seletor de data nativo do navegador. Ele
envia a data no formato `2030-01-01T10:00`, que o Django não aceita por padrão — daí as
duas linhas de `format` e `input_formats`. Se você tirar uma delas, o campo passa a
recusar datas válidas.

O `save()` é sobrescrito por um motivo só:

```python
if 'prazo' in self.changed_data:
    self.instance.lembrete_enviado_em = None
```

Prazo novo merece lembrete novo. Mudar só o título mantém o lembrete já enviado.

### `TarefaFiltroForm`

Não é um `ModelForm` — é um formulário comum, com três campos opcionais (`q`, `status`,
`responsavel`), que existe para duas coisas ao mesmo tempo: **desenhar a barra de filtros**
e **filtrar o queryset**, no método `filtrar(tarefas, agora)`.

Se o formulário for inválido (alguém digitou `?status=xyz` na URL), ele devolve a lista
inteira em vez de dar erro — decisão deliberada, com teste em `tests.py:206`.

### `ResponsavelForm.clean_cpf`

Faz duas coisas:

1. **Valida** os dois dígitos verificadores do CPF pelo algoritmo oficial, e rejeita
   sequências repetidas como `111.111.111-11`.
2. **Normaliza**: devolve sempre no formato `000.000.000-00`. É isso que faz o
   `unique=True` do modelo pegar o mesmo CPF digitado de jeitos diferentes.

---

## 5. URLs e templates

### Rotas (`Suap2/Suap2/urls.py`)

| URL | View | Nome (usado em `{% url %}` e `reverse()`) |
|---|---|---|
| `/` | `TarefaListView` | `tarefa_list` |
| `/tarefas/nova/` | `TarefaCreateView` | `tarefa_create` |
| `/tarefas/<pk>/editar/` | `TarefaUpdateView` | `tarefa_update` |
| `/tarefas/<pk>/excluir/` | `TarefaDeleteView` | `tarefa_delete` |
| `/tarefas/<pk>/concluir/` | `tarefa_toggle` (só POST) | `tarefa_toggle` |
| `/responsaveis/` | `ResponsavelListView` | `responsavel_list` |
| `/responsaveis/novo/` | `ResponsavelCreateView` | `responsavel_create` |
| `/responsaveis/<pk>/` | `ResponsavelDetailView` | `responsavel_detail` |
| `/responsaveis/<pk>/editar/` | `ResponsavelUpdateView` | `responsavel_update` |
| `/responsaveis/<pk>/excluir/` | `ResponsavelDeleteView` | `responsavel_delete` |
| `/entrar/` e `/sair/` | views prontas do Django | `login` e `logout` |
| `/admin/` | admin do Django | — |

Sempre use o **nome** da rota, nunca o endereço escrito à mão: assim, mudar a URL não
quebra nada.

### Templates

- `base.html` — o esqueleto: menu (só para quem está logado) e as mensagens de sucesso.
  Todos os outros templates fazem `{% extends %}` dele.
- `_tarefa_item.html` — um card de tarefa. O underline no nome indica que é um *parcial*,
  incluído por outros templates. É usado na lista de tarefas (com
  `{% include ... with mostrar_responsavel=True %}`) e na página do responsável (sem a
  flag, porque ali o responsável já é óbvio).
- `form.html` — serve para criar **e** editar, tarefa **e** responsável.
- Na paginação (`tarefa_list.html:42`), a tag `{% querystring page=... %}` reaproveita os
  parâmetros da URL atual e só troca a página — é o que impede os filtros de sumirem ao
  clicar em "Próxima".

Os nomes dos templates das generic views não são escolhidos à toa: `ListView` procura
`<app>/<modelo>_list.html` e `DeleteView` procura `<modelo>_confirm_delete.html`
automaticamente. Por isso `tarefa_list.html` e `responsavel_confirm_delete.html` não
aparecem declarados em lugar nenhum do `views.py`.

---

## 6. Lembretes por e-mail

`Suap2APP/management/commands/enviar_lembretes.py` cria o comando
`python manage.py enviar_lembretes`. Ele roda "por fora" do site (pelo Agendador de
Tarefas do Windows ou pelo cron), não quando alguém abre uma página.

**Quais tarefas entram no e-mail** — as cinco condições do filtro:

1. `concluida_em__isnull=True` — ainda não foi feita;
2. `lembrete_enviado_em__isnull=True` — ninguém já foi avisado dessa tarefa;
3. `prazo__gt=agora` — o prazo ainda não passou (tarefa vencida não gera lembrete);
4. `prazo__lte=agora + horas` — vence dentro da janela (padrão: 24h);
5. `.exclude(pessoa_responsavel__email='')` — a pessoa tem e-mail cadastrado.

**Um e-mail por pessoa, não por tarefa.** As tarefas são ordenadas por
`pessoa_responsavel_id` e agrupadas com `itertools.groupby`. O agrupamento é pelo **id**,
e não pelo objeto: o `Meta.ordering` do `Responsavel` ordena por nome, e duas pessoas
chamadas "Ana" ficariam grudadas no mesmo grupo — o comentário na linha 39 do arquivo
explica exatamente isso, e há um teste cobrindo o caso (`tests.py:297`).

**A marcação vem depois do envio.** `lembrete_enviado_em` só é gravado se o `send_mail`
não levantar exceção; se o servidor de e-mail estiver fora do ar, aquela pessoa é pulada
com um aviso no stderr e as tarefas dela continuam elegíveis na próxima execução.

Opções: `--horas N` muda a janela, `--dry-run` mostra quem receberia sem enviar nem
marcar nada.

Sem configuração, `EMAIL_BACKEND` é o `console`: os e-mails aparecem impressos no
terminal. Para enviar de verdade, veja a tabela de variáveis no README.

---

## 7. "Quero mudar X — onde mexo?"

| O que você quer | Onde mexer |
|---|---|
| Adicionar um campo na tarefa | `models.py` → `python manage.py makemigrations` → `fields` do `TarefaForm` → `_tarefa_item.html` → `admin.py` |
| Novo filtro na lista | `TarefaFiltroForm`: cria o campo **e** o `if` correspondente em `filtrar()` → mostra o campo em `tarefa_list.html` |
| Mudar a ordem da lista | `Meta.ordering` em `models.py` |
| Mudar quantas tarefas por página | `paginate_by` em `TarefaListView` |
| Mudar texto/assunto do e-mail | método `enviar()` do comando `enviar_lembretes` |
| Mudar o prazo do lembrete | `--horas` na hora de rodar, ou o `default=24` em `add_arguments` |
| Mudar cores, fontes, espaçamento | `static/Suap2APP/style.css` |
| Mudar o menu | `templates/Suap2APP/base.html` |
| Nova página | view em `views.py` → rota em `Suap2/Suap2/urls.py` → template |
| Mudar colunas/filtros do `/admin` | `admin.py` |

Depois de mexer em `models.py`, **sempre**:

```powershell
cd Suap2
python manage.py makemigrations
python manage.py migrate
```

---

## 8. Os testes

```powershell
cd Suap2
python manage.py test Suap2APP
```

Os testes rodam em um banco temporário, separado do seu `db.sqlite3` — pode rodar à
vontade que nada dos seus dados é tocado. Eles funcionam como um índice do comportamento
esperado do sistema:

| Classe em `tests.py` | O que garante |
|---|---|
| `AutenticacaoTests` | Toda página redireciona para o login; o login funciona |
| `TarefaTests` | Ordenação da lista, número de consultas, criar/editar/excluir, concluir e reabrir |
| `ResponsavelTests` | Cadastro, e que não dá para excluir alguém com tarefas |
| `ResponsavelFormTests` | CPF inválido é recusado; CPF duplicado em outro formato é detectado |
| `FiltroTarefaTests` | Busca, situação, responsável, filtros combinados, paginação e o retorno do "Concluir" |
| `ResponsavelDetailTests` | Contadores corretos e sem vazar tarefa de outra pessoa |
| `EnviarLembretesTests` | Agrupamento por pessoa, o que é ignorado, não enviar duas vezes, `--horas` e `--dry-run` |

`BaseTestCase` no topo do arquivo cria um usuário e um responsável e já faz o login — é
dele que a maioria das classes herda, junto com o atalho `criar_tarefa()`.
