# Guia do código — Suap2

Este documento explica **como o projeto funciona por dentro**. Para instalar e rodar,
veja o [README.md](README.md).

---

## 0. Antes de tudo: entrar no sistema

O banco (`Suap2/db.sqlite3`) **vem junto com o repositório**, já migrado e com os dados
de exemplo dentro. Ele traz um superusuário chamado `ronaldo`, mas **a senha dele não
está em lugar nenhum** — o Django guarda só um hash. Então, ao clonar, você tem duas
opções:

```powershell
cd Suap2
python manage.py changepassword ronaldo   # escolher uma senha para o usuário que já existe
# ou
python manage.py createsuperuser          # criar o seu próprio usuário
python manage.py runserver
```

Se o banco não existir (você apagou, ou está montando um do zero), rode
`python manage.py migrate` antes — é ele que cria as tabelas.

O mesmo usuário serve para o site (`http://127.0.0.1:8000/`) e para o `/admin`.

O Django **nunca guarda a senha em texto**, só um hash. Ou seja: não existe jeito de
"descobrir" uma senha esquecida, só de trocá-la:

```powershell
python manage.py changepassword <usuario>
```

### Dados de exemplo

O `db.sqlite3` é versionado (não está no `.gitignore`), então os dados de exemplo já estão
lá quando você clona. Eles também existem como *fixture*: um arquivo JSON em
`Suap2APP/fixtures/exemplos.json` com 3 departamentos, 5 responsáveis, 3 projetos, 4
categorias, 4 etiquetas, 5 tarefas e os itens delas (subtarefas, comentários e horas
apontadas). Para recarregá-los em um banco vazio:

```powershell
python manage.py loaddata exemplos
```

As tarefas de exemplo cobrem os três estados (pendente, atrasada e concluída) e um dos
responsáveis está sem e-mail de propósito, para você ver como o comando de lembretes
ignora esse caso. Os prazos são datas fixas de setembro/outubro de 2026 — com o tempo
todas vão aparecer como atrasadas; é só editar o JSON quando isso incomodar.

A fixture **não traz anexos**: eles dependeriam de arquivos de verdade em `MEDIA_ROOT`, que
não têm por que ir para o Git. Para ver a tela de anexos funcionando, envie um arquivo
qualquer na página de uma tarefa.

---

## 1. Mapa do projeto

A pasta `Suap2/` de fora é o projeto Django (onde fica o `manage.py`). Dentro dela há
duas pastas com nomes parecidos, e vale não confundir:

| Caminho | O que é |
|---|---|
| `Suap2/manage.py` | Porta de entrada de todo comando (`runserver`, `migrate`, `test`…) |
| `Suap2/Suap2/settings.py` | Configuração: banco, idioma, fuso, e-mail, login |
| `Suap2/Suap2/urls.py` | Todas as rotas do site (não há `urls.py` dentro do app) |
| `Suap2/Suap2APP/models.py` | As dez tabelas (veja a seção 2) |
| `Suap2/Suap2APP/views.py` | A lógica de cada tela |
| `Suap2/Suap2APP/forms.py` | Formulários de cadastro e o formulário de filtros |
| `Suap2/Suap2APP/admin.py` | Como as tabelas aparecem no `/admin` |
| `Suap2/Suap2APP/templates/Suap2APP/` | O HTML |
| `Suap2/Suap2APP/static/Suap2APP/style.css` | Todo o CSS (arquivo único, sem framework) |
| `Suap2/Suap2APP/fixtures/exemplos.json` | Dados de exemplo (`loaddata exemplos`) |
| `Suap2/media/` | Os anexos enviados; fora do Git |
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

## 2. Os dez modelos (`Suap2APP/models.py`)

`Tarefa` é o centro de tudo. Os outros nove existem em três papéis diferentes, e **essa
distinção explica o desenho de quase todo o resto do projeto**:

| Papel | Modelos | Como se ligam à tarefa | Tela própria? |
|---|---|---|---|
| Quem faz | `Departamento`, `Responsavel` | `Tarefa.pessoa_responsavel` (PROTECT) | sim, menu "Responsáveis" e "Cadastros" |
| Como classificar | `Projeto`, `Categoria`, `Etiqueta` | FK ou M2M, todos opcionais | sim, menu "Projetos" e "Cadastros" |
| O que vive dentro | `Subtarefa`, `Comentario`, `Anexo`, `RegistroTempo` | FK obrigatória para `Tarefa`, com CASCADE | não: aparecem na tela da tarefa |

Os quatro "de dentro" não têm menu nem CRUD separado de propósito — uma página listando
todos os comentários do sistema não serviria para nada. Eles nascem e morrem na tela da
tarefa (`TarefaDetailView`, seção 3).

Um resumo dos relacionamentos:

```
Departamento ──< Responsavel ──< Tarefa >── Projeto ──> Departamento
                      │            │  │
                      │            │  └── Categoria
                      │            │  └──< Etiqueta (muitos para muitos)
                      │            │
                      │            ├──< Subtarefa
                      │            ├──< Comentario >── Responsavel (autor, opcional)
                      │            ├──< Anexo
                      └────────────┴──< RegistroTempo
```

### `Departamento`

Campos: `nome` (único), `sigla`. Agrupa responsáveis e projetos. O `__str__` junta os dois
(`Coordenação de Informática (CINF)`), e omite o parêntese quando não há sigla.

### `Responsavel`

Campos: `nome`, `cpf`, `email`, `telefone`, `departamento`.

O `cpf` é `unique=True` — não pode haver dois responsáveis com o mesmo CPF. Isso só
funciona de verdade porque o formulário normaliza o CPF antes de salvar (veja a seção 4);
sem isso, `52998224725` e `529.982.247-25` entrariam como duas pessoas diferentes.

`Meta.ordering = ['nome']` faz a lista de responsáveis já sair em ordem alfabética sem
nenhum `order_by()` nas views.

`departamento` é `null=True, blank=True` com `on_delete=SET_NULL`: excluir um departamento
**não** apaga ninguém, só deixa os cadastros sem departamento.

### `Projeto`

Campos: `nome` (único), `descricao`, `departamento`, `inicio`, `fim`.

As datas são opcionais, mas se as duas existirem o fim não pode ser antes do início. Essa
regra está escrita **duas vezes**, de propósito:

```python
constraints = [
    models.CheckConstraint(
        condition=(Q(inicio__isnull=True) | Q(fim__isnull=True) | Q(fim__gte=F('inicio'))),
        name='projeto_fim_depois_do_inicio',
    ),
]
```

A `CheckConstraint` é a garantia final, no banco: vale até para quem cria projeto pelo
shell ou pelo `/admin`. O `ProjetoForm.clean` (seção 4) repete a checagem só para virar uma
mensagem de erro bonita no formulário, em vez de um `IntegrityError` na tela. Há um teste
para cada um dos dois caminhos.

`encerrado` é uma `@property`, não um campo: `fim` no passado. Não faz sentido guardar no
banco algo que muda de valor sozinho com o passar do tempo.

### `Categoria` e `Etiqueta`

São os dois jeitos de classificar uma tarefa, e a diferença é intencional:

- **`Categoria`** é FK: cada tarefa tem *no máximo uma*. Tem `nome` e `cor` (com
  `choices`), e a cor vira a classe CSS `cor-azul`, `cor-verde`… no template.
- **`Etiqueta`** é M2M: cada tarefa pode ter *várias*. Só tem `nome`.

Excluir uma categoria ou etiqueta nunca apaga tarefa: a FK é `SET_NULL` e o M2M só perde a
linha de ligação.

### `Tarefa`

Campos: `titulo`, `criada_em`, `prazo`, `concluida_em`, `lembrete_enviado_em`,
`pessoa_responsavel`, `projeto`, `categoria`, `etiquetas`.

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

#### `TarefaQuerySet.com_relacionados()`

`Tarefa.objects` não é o manager padrão: vem de um `QuerySet` próprio com um método só.

```python
def com_relacionados(self):
    return self.select_related('pessoa_responsavel', 'projeto', 'categoria').prefetch_related(
        'etiquetas', 'subtarefas',
    )
```

É exatamente o que `_tarefa_item.html` precisa para desenhar um card. Como o mesmo parcial
aparece em quatro telas (lista, painel, responsável e projeto), o método evita repetir a
lista de relacionamentos — e evita esquecer um deles em uma tela e fazer uma consulta por
tarefa. Como está no manager, também funciona nas relações inversas:
`responsavel.tarefa_set.com_relacionados()`.

#### `progresso` e `horas_registradas`

As duas são `@property` e **percorrem `self.subtarefas.all()` / `self.registros_tempo.all()`
em Python**, em vez de chamar `.count()` ou `.aggregate()`. É de propósito: `all()`
aproveita o `prefetch_related` que a view já fez, enquanto `count()` daria uma consulta
nova para cada tarefa da lista. `progresso` devolve `None` quando não há subtarefa — que é
diferente de `0`, ou seja "tem checklist e nada foi feito".

### `Subtarefa`, `Comentario`, `Anexo` e `RegistroTempo`

Os quatro têm uma FK obrigatória para `Tarefa` com `on_delete=CASCADE`: excluir a tarefa
leva tudo embora junto (a tela de confirmação avisa quantos itens vão). E os quatro têm
`Meta.ordering`, então nenhuma view precisa ordená-los.

- **`Subtarefa`** — `descricao`, `concluida`, `ordem`. O `save()` dá a `ordem` seguinte
  para um item novo (`Max('ordem') + 1`), então a lista respeita a ordem de criação sem
  ninguém digitar número nenhum.
- **`Comentario`** — `autor` (opcional), `texto`, `criado_em`. O autor é `SET_NULL`: se o
  responsável for excluído um dia, o comentário fica como "Anônimo" em vez de desaparecer.
- **`Anexo`** — `arquivo` (`FileField`), `descricao`, `enviado_em`. Veja o cuidado com o
  arquivo em disco logo abaixo.
- **`RegistroTempo`** — `responsavel`, `horas`, `data`, `observacao`. As horas são
  `DecimalField` (dinheiro e hora não se guardam em `float`) com mínimo de 0,25 h. O
  `responsavel` aqui é **PROTECT**, igual ao da tarefa: quem já apontou hora não pode ser
  excluído. `data` usa `default=timezone.localdate` — a *função*, sem parênteses, senão
  todos os registros nasceriam com a data em que o servidor subiu.

#### O sinal que apaga o arquivo do anexo

Quando você apaga um `Anexo`, o Django tira a linha do banco e **deixa o arquivo em
`MEDIA_ROOT`** — lixo acumulando para sempre. Daí o `post_delete`:

```python
@receiver(post_delete, sender=Anexo)
def apagar_arquivo_do_anexo(sender, instance, **kwargs):
    if instance.arquivo:
        instance.arquivo.delete(save=False)
```

Um sinal, e não um `delete()` sobrescrito, porque `Model.delete()` **não é chamado** na
exclusão em cascata nem em `queryset.delete()`. Com o sinal, apagar a tarefa inteira também
limpa os arquivos dela. Há um teste para os dois caminhos.

---

## 3. As views (`Suap2APP/views.py`)

Quase tudo usa as *generic views* do Django (`ListView`, `CreateView`, …), então cada
classe é curta: ela só declara *qual modelo*, *qual formulário* e *para onde vai depois*.

### A hierarquia de mixins

```
FormularioMixin                    login + mensagem de sucesso + template form.html
├── TarefaFormularioMixin          modelo Tarefa, TarefaForm, volta pra lista
│   ├── TarefaCreateView           só muda titulo_pagina e success_message
│   └── TarefaUpdateView
├── ResponsavelFormularioMixin     modelo Responsavel, ResponsavelForm
│   ├── ResponsavelCreateView
│   └── ResponsavelUpdateView
├── DepartamentoFormularioMixin    ┐
├── ProjetoFormularioMixin         │ mesma receita para os quatro
├── CategoriaFormularioMixin       │ cadastros auxiliares
└── EtiquetaFormularioMixin        ┘

ExclusaoMixin                      login + mensagem + template confirm_delete.html
├── DepartamentoDeleteView         cada uma só diz o título, a mensagem e o aviso
├── ProjetoDeleteView
├── CategoriaDeleteView
└── EtiquetaDeleteView
```

Criar e editar usam **o mesmo template** (`form.html`); a diferença é só o título da
página e a mensagem exibida no fim. Todo formulário é renderizado em um laço genérico
`{% for field in form %}`, então **um campo novo no form aparece sozinho na tela**.

`ExclusaoMixin` é o irmão do `FormularioMixin` para as telas de excluir dos quatro
cadastros auxiliares. Cada subclasse preenche três atributos e, se quiser, o método
`contar_relacionados()`; o mixin transforma o número em um aviso do tipo "esta categoria
está em 3 tarefa(s). Nenhuma será apagada". `Tarefa` e `Responsavel` **não** usam esse
mixin: as duas têm template próprio, porque o texto delas é mais específico (a de
responsável precisa esconder o botão quando o PROTECT vai barrar a exclusão).

### `TarefaListView`

- `get_queryset()` guarda `self.agora` e `self.filtro` em atributos, para reaproveitá-los
  em `get_context_data()` sem recalcular.
- `com_relacionados()` (seção 2) traz responsável, projeto e categoria na mesma consulta e
  faz o *prefetch* de etiquetas e subtarefas. Sem isso, uma lista de 10 tarefas faria
  dezenas de consultas extras. Existe um teste que crava o número: se ele quebrar com
  "esperava 11 queries", provavelmente algum relacionamento se perdeu no caminho.
- `now` vai para o template para marcar as tarefas atrasadas; `filtrando` diz se algum
  filtro está ativo (muda a mensagem de lista vazia e mostra o botão "Limpar").
- **Os contadores do topo** (total, pendentes, atrasadas, concluídas) respeitam a busca e
  os outros filtros, mas **ignoram a situação**. Por isso a view chama
  `filtro.filtrar(..., com_status=False)`: se o filtro de situação entrasse na conta,
  escolher "Concluídas" zeraria os outros contadores. Assim cada contador funciona como uma
  aba: o link troca só o `status` (com `{% querystring status='...' page=None %}`, que mantém
  os outros filtros e volta para a página 1), e `status_atual` destaca a aba ativa.
  `total` é `pendentes + concluidas`, porque toda tarefa está em uma das duas (as atrasadas
  são pendentes).

### `TarefaDetailView` — a tela com quatro formulários

É a view mais incomum do projeto, porque uma única página cria quatro tipos de item
diferentes. A saída foi um dicionário no alto da classe:

```python
FORMULARIOS = {
    'subtarefa': (SubtarefaForm, 'Subtarefa adicionada.'),
    'comentario': (ComentarioForm, 'Comentário adicionado.'),
    'anexo': (AnexoForm, 'Anexo enviado.'),
    'registro': (RegistroTempoForm, 'Tempo registrado.'),
}
```

- **No GET**, `get_context_data` põe os quatro formulários vazios no contexto, com os nomes
  `form_subtarefa`, `form_comentario`… O `setdefault` é a parte importante: se alguém já
  colocou um formulário ali (o caso do POST inválido, abaixo), ele não é substituído.
- **No POST**, o campo escondido `acao` diz qual dos quatro foi enviado. O formulário certo
  é montado, o `tarefa` é preenchido pela view (por isso nenhum dos quatro tem esse campo)
  e, se valer, salva e redireciona.
- **Se o formulário for inválido**, a view **re-renderiza a própria página** com aquele
  formulário preenchido no contexto. É o motivo de os quatro morarem na mesma URL: assim o
  erro aparece embaixo do campo errado, e não como uma mensagem solta no topo.
- Um `acao` que não está no dicionário devolve 404 — ninguém chega nesse caminho pela tela.

### `item_delete` e `subtarefa_toggle`

Excluir um dos quatro itens é sempre a mesma coisa: achar pelo `pk`, apagar e voltar para a
tarefa. Em vez de quatro views iguais, existe uma, e o tipo vem na URL
(`/itens/comentario/3/excluir/`):

```python
TIPOS_DE_ITEM = {
    'subtarefa': (Subtarefa, 'Subtarefa excluída.'),
    ...
}
```

Tipo fora do dicionário é 404, então a URL aberta não dá acesso a nenhum outro modelo do
projeto. As duas views são `@require_POST`, pela mesma razão do `tarefa_toggle`: mudam
dados. E as duas redirecionam para a tarefa, não para a lista.

### `ProjetoDetailView`

É a gêmea da `ResponsavelDetailView`: mesmos três contadores de `contar_por_situacao`, mesma
lista de tarefas com o parcial. A diferença é o total de horas, que não sai das tarefas mas
de `RegistroTempo.objects.filter(tarefa__projeto=...)` — atravessa duas tabelas em uma
consulta.

### `contar_por_situacao` (`views.py:116`)

Os contadores saem de **uma única** consulta, usando `Count('pk', filter=Q(...))` dentro de
um `aggregate`, em vez de três `count()` separados. A função recebe qualquer queryset de
tarefas, então serve para todas as telas com esses três contadores: a lista principal e as
páginas do responsável e do projeto. O painel tem a própria consulta, porque conta também
o que vence e o que foi concluído na semana.

### `tarefa_toggle` (`views.py:234`)

É a única view escrita como função, porque é uma ação e não uma tela. Dois cuidados:

- `@require_POST` — concluir uma tarefa muda dados, então não pode acontecer por GET
  (um GET devolve 405). É também por isso que o botão "Concluir" no template é um
  `<form method="post">` e não um link.
- O campo escondido `next` guarda a página de onde você veio, com os filtros, para voltar
  exatamente para lá. Antes de redirecionar, `url_has_allowed_host_and_scheme` confere se
  o endereço é deste site — sem essa checagem, alguém poderia forjar um link que joga o
  usuário em um site externo (*open redirect*).

### `ResponsavelDetailView`

Os três contadores (pendentes, atrasadas, concluídas) vêm de `contar_por_situacao`,
aplicada só às tarefas da pessoa. Cada um é um link para a lista principal já filtrada.

### `ResponsavelDeleteView`

- `get_context_data` conta as tarefas da pessoa; o template usa esse número para mostrar
  "Não é possível excluir…" e esconder o botão.
- `form_valid` envolve a exclusão em `try/except ProtectedError` — se alguém tentar
  excluir mesmo assim (via POST direto), a página é re-renderizada com o aviso em vez de
  estourar um erro 500.

---

## 4. Os formulários (`Suap2APP/forms.py`)

### `DataInput` e `DataHoraInput`

Os dois widgets no topo do arquivo são os seletores nativos do navegador
(`type="date"` e `type="datetime-local"`). Eles só falam **ISO** (`2030-01-01`,
`2030-01-01T10:00`), enquanto o projeto está em pt-br e formata datas como `01/01/2030`.
São necessárias duas peças em lugares diferentes:

| Peça | Onde fica | Para quê |
|---|---|---|
| `format` | no widget | **Escrever** o valor no HTML. Sem ele o campo aparece vazio no navegador, porque `01/01/2030` não é uma data válida para um `<input type="date">`. |
| `input_formats` | no campo do form | **Ler** o que o navegador mandou. Sem ele o Django recusa uma data válida. |

E há uma pegadinha que custou um bug: **não basta declarar `format` como atributo de
classe**, porque `DateTimeBaseInput.__init__` sobrescreve `self.format` com `format or
None`. Daí o formato ser passado como valor padrão do `__init__`:

```python
class DataInput(forms.DateInput):
    input_type = 'date'

    def __init__(self, attrs=None, format='%Y-%m-%d'):
        super().__init__(attrs, format)
```

`WidgetsDeDataTests`, em `tests.py`, confere que os três campos de data do projeto saem em
ISO no HTML — é o teste que pega esse erro de volta.

### `TarefaForm`

Os campos `projeto` e `categoria` são opcionais e recebem um `empty_label` em português
("Sem projeto", "Sem categoria"). `etiquetas` usa `CheckboxSelectMultiple`: com poucas
etiquetas, caixinhas são mais claras que um `<select multiple>`, onde é preciso saber que
se seleciona vários com Ctrl.

O `save()` é sobrescrito por um motivo só:

```python
if 'prazo' in self.changed_data:
    self.instance.lembrete_enviado_em = None
```

Prazo novo merece lembrete novo. Mudar só o título mantém o lembrete já enviado.

### `TarefaFiltroForm`

Não é um `ModelForm` — é um formulário comum, com seis campos opcionais (`q`, `status`,
`responsavel`, `projeto`, `categoria`, `etiqueta`), que existe para duas coisas ao mesmo
tempo: **desenhar a barra de filtros** e **filtrar o queryset**, no método
`filtrar(tarefas, agora)`. O parâmetro opcional
`com_status=False` aplica todos os filtros menos a situação — é o que os contadores da lista
usam.

Se o formulário for inválido (alguém digitou `?status=xyz` na URL), ele devolve a lista
inteira em vez de dar erro — decisão deliberada, com teste.

O `tarefa_list.html` desenha a barra em um laço `{% for campo in filtro %}` (com o `q`
fora, porque ele ocupa a linha inteira). Ou seja: **um filtro novo só precisa do campo e do
`if` dentro de `filtrar()`** — ele aparece na tela sozinho.

### Os quatro formulários dos itens da tarefa

`SubtarefaForm`, `ComentarioForm`, `AnexoForm` e `RegistroTempoForm` não têm o campo
`tarefa`: quem preenche é a `TarefaDetailView` (seção 3). O `AnexoForm` também tem um
`clean_arquivo` que recusa arquivo acima de 10 MB — sem ele, qualquer upload entraria.

### `ProjetoForm.clean`

Repete no formulário a regra que a `CheckConstraint` já garante no banco (seção 2). Sem
esse `clean`, salvar um projeto com o fim antes do início daria um `IntegrityError` — uma
página de erro 500 em vez de uma mensagem em vermelho no formulário.

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
| `/painel/` | `PainelView` | `painel` |
| `/tarefas/nova/` | `TarefaCreateView` | `tarefa_create` |
| `/tarefas/<pk>/` | `TarefaDetailView` | `tarefa_detail` |
| `/tarefas/<pk>/editar/` | `TarefaUpdateView` | `tarefa_update` |
| `/tarefas/<pk>/excluir/` | `TarefaDeleteView` | `tarefa_delete` |
| `/tarefas/<pk>/concluir/` | `tarefa_toggle` (só POST) | `tarefa_toggle` |
| `/subtarefas/<pk>/concluir/` | `subtarefa_toggle` (só POST) | `subtarefa_toggle` |
| `/itens/<tipo>/<pk>/excluir/` | `item_delete` (só POST) | `item_delete` |
| `/responsaveis/…` | as cinco views de `Responsavel` | `responsavel_list`, `_create`, `_detail`, `_update`, `_delete` |
| `/projetos/…` | as cinco views de `Projeto` | `projeto_list`, `_create`, `_detail`, `_update`, `_delete` |
| `/departamentos/…` | as quatro views de `Departamento` | `departamento_list`, `_create`, `_update`, `_delete` |
| `/categorias/…` | as quatro views de `Categoria` | `categoria_list`, `_create`, `_update`, `_delete` |
| `/etiquetas/…` | as quatro views de `Etiqueta` | `etiqueta_list`, `_create`, `_update`, `_delete` |
| `/media/…` | os anexos, **só com `DEBUG=1`** | — |
| `/entrar/` e `/sair/` | views prontas do Django | `login` e `logout` |
| `/admin/` | admin do Django | — |

Sempre use o **nome** da rota, nunca o endereço escrito à mão: assim, mudar a URL não
quebra nada.

`Departamento`, `Categoria` e `Etiqueta` não têm rota de detalhe: a lista já mostra tudo o
que existe para mostrar, e o número de tarefas em cada uma é um link para a lista de
tarefas já filtrada.

A última linha do arquivo serve os anexos no `runserver`. Em produção (`DEBUG=0`) quem faz
isso é o servidor web; o Django nem registra a rota.

### Templates

- `base.html` — o esqueleto: menu (só para quem está logado) e as mensagens de sucesso.
  Todos os outros templates fazem `{% extends %}` dele.
- `_tarefa_item.html` — um card de tarefa. O underline no nome indica que é um *parcial*,
  incluído por outros templates. Aparece em quatro telas, e as flags do `{% include %}`
  dizem o que esconder: `mostrar_responsavel=True` na lista e no painel,
  `esconder_projeto=True` na página do projeto (onde repetir o nome do projeto em cada card
  seria ruído) e nenhuma flag na página do responsável.
- `_form_item.html` — um dos quatro formulários de adicionar item na tela da tarefa. Recebe
  `form`, `acao` (o valor do campo escondido lido pela view), `rotulo` do botão e
  `arquivo=True` quando precisa de `enctype="multipart/form-data"` — sem esse `enctype` o
  upload chega vazio.
- `_item_excluir.html` — o botãozinho de excluir um item; recebe `tipo` e `pk`.
- `form.html` — serve para criar **e** editar, nos seis cadastros.
- `confirm_delete.html` — a tela de excluir dos quatro cadastros auxiliares, usada pelo
  `ExclusaoMixin`. `Tarefa` e `Responsavel` têm as suas próprias.
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
explica exatamente isso, e há um teste cobrindo o caso (`tests.py:324`).

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
| Novo filtro na lista | `TarefaFiltroForm`: cria o campo **e** o `if` correspondente em `filtrar()`. A barra de filtros se desenha sozinha |
| Novo cadastro auxiliar (como Categoria) | modelo → migração → form → `FormularioMixin` + `ExclusaoMixin` em `views.py` → 4 rotas → um `_list.html` → link em `base.html` → `admin.py` |
| Novo tipo de item dentro da tarefa | modelo com FK CASCADE → form sem o campo `tarefa` → uma linha em `TarefaDetailView.FORMULARIOS` e outra em `TIPOS_DE_ITEM` → um bloco em `tarefa_detail.html` |
| Nova cor de categoria | `Categoria.CORES` **e** a classe `.cor-<nome>` no `style.css` |
| Mudar o limite de tamanho do anexo | `TAMANHO_MAXIMO_ANEXO` em `forms.py` |
| Mudar onde os anexos são guardados | `MEDIA_ROOT` em `settings.py`, ou o `upload_to` do `Anexo` |
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
| `DepartamentoTests` | Cadastro, contagem na lista, e que excluir só desliga os ligados |
| `ProjetoTests` | Cadastro, fim antes do início barrado nos **dois** níveis, contadores, horas, `encerrado` |
| `CategoriaTests` / `EtiquetaTests` | Cadastro, contagem, e que excluir não apaga tarefa |
| `TarefaComRelacionamentosTests` | Criar tarefa com projeto, categoria e etiquetas; aparecem na lista |
| `FiltroPorRelacionamentoTests` | Os três filtros novos, inclusive combinados com a situação |
| `SubtarefaTests` | `ordem` automática, `progresso`, marcar/desmarcar, exigir POST |
| `TarefaDetalheTests` | Os quatro formulários, erro que reaparece no campo, excluir item, CASCADE, número de consultas |
| `AnexoTests` | Upload, limite de tamanho, e o arquivo saindo do disco nos dois caminhos |
| `RegistroTempoProtegidoTests` | PROTECT nas horas apontadas e a soma na página do responsável |
| `PainelDosNovosModelosTests` | Agrupamento por projeto e por categoria no painel |
| `WidgetsDeDataTests` | Os campos de data saem em ISO no HTML (veja a seção 4) |
| `FixtureDeExemploTests` | O `loaddata exemplos` funciona e cobre os modelos |
| `TodasAsPaginasAbremTests` | Passeia por **todas** as telas com os dados de exemplo e cobra HTTP 200 |

`BaseTestCase` no topo do arquivo cria um usuário e um responsável e já faz o login — é
dele que a maioria das classes herda, junto com o atalho `criar_tarefa()`.

Vale entender dois tipos de teste que se repetem:

- **Os que cravam o número de consultas** (`assertNumQueries`) rodam a mesma página duas
  vezes, com poucos e com muitos registros, e exigem o mesmo número. Eles não protegem um
  número bonito: protegem o *formato* do código. Se alguém tirar um `select_related`, o
  teste falha mesmo que a tela continue funcionando.
- **`TodasAsPaginasAbremTests`** não confere conteúdo nenhum, só que cada tela responde
  200 com os dados de exemplo. É uma rede de segurança barata: pega `{% url %}` com nome
  errado, template que não existe e variável que faltou no contexto.
