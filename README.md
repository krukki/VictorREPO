# Suap2

Gerenciador de tarefas em Django. Cada tarefa tem responsável, prazo, projeto, categoria e
etiquetas, e na página dela ficam o checklist, os comentários, os anexos e as horas
trabalhadas. São onze modelos: `Departamento`, `Responsavel`, `Projeto`, `Categoria`,
`Etiqueta`, `Tarefa`, `Subtarefa`, `Comentario`, `Anexo`, `RegistroTempo` e `Atividade`.

Além da lista, as tarefas aparecem num **quadro** (arraste entre A fazer, Em andamento e
Concluída) e num **calendário** mensal. Cada tarefa tem prioridade e um histórico do que
aconteceu com ela. O visual tem tema claro e escuro, e a tecla **N** abre a adição rápida:
escreva `Revisar o relatório amanhã 14h @ana #mensal !alta` e a tarefa sai pronta.
Atalhos: `N` nova tarefa, `/` busca, `G` + `P`/`T`/`Q`/`C` para Painel, Tarefas, Quadro e
Calendário, `?` lista os atalhos. Detalhes na seção 9 do [GUIA.md](GUIA.md).

Este arquivo explica **como rodar**. Para entender **como o código funciona por dentro**,
veja o [GUIA.md](GUIA.md). Para **publicar na internet** de graça, veja o
[PYTHONANYWHERE.md](PYTHONANYWHERE.md).

## Como rodar

```bash
python -m venv venv
venv\Scripts\activate        # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
cd Suap2
python manage.py migrate
python manage.py createsuperuser   # usuário para entrar no sistema e no /admin
python manage.py runserver
```

Acesse http://127.0.0.1:8000/ e entre com o usuário criado. Todas as páginas exigem login.

Para começar com dados de exemplo (departamentos, projetos, categorias, etiquetas, tarefas
e os itens delas):

```bash
python manage.py loaddata exemplos
```

## Anexos

Os arquivos enviados nas tarefas ficam em `Suap2/media/`, fora do Git. No `runserver` o
próprio Django os serve; em produção (`DJANGO_DEBUG=0`) isso é trabalho do servidor web.
Mude o lugar com `MEDIA_ROOT` em `settings.py` e o limite de tamanho em
`TAMANHO_MAXIMO_ANEXO` (`Suap2APP/forms.py`, 10 MB por padrão).

## Testes

```bash
cd Suap2
python manage.py test Suap2APP
```

## Configuração por variáveis de ambiente

| Variável               | Padrão (desenvolvimento)     | Em produção                          |
|------------------------|------------------------------|--------------------------------------|
| `DJANGO_SECRET_KEY`    | chave insegura fixa          | uma chave longa e aleatória          |
| `DJANGO_DEBUG`         | `1`                          | `0`                                  |
| `DJANGO_ALLOWED_HOSTS` | vazio                        | domínios separados por vírgula       |

Gere uma chave com:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

## Lembretes por e-mail

O comando `enviar_lembretes` manda um e-mail para cada responsável (que tenha e-mail
cadastrado) listando as tarefas pendentes que vencem nas próximas 24 horas. Cada tarefa
recebe no máximo um lembrete; se o prazo for alterado, ela pode receber outro.

```bash
python manage.py enviar_lembretes              # prazo nas próximas 24h
python manage.py enviar_lembretes --horas 48   # outra janela
python manage.py enviar_lembretes --dry-run    # só mostra quem receberia
```

Sem configuração, os e-mails aparecem apenas no terminal. Para enviar de verdade,
defina as variáveis (exemplo com Gmail, que exige uma "senha de app"):

| Variável                     | Exemplo                                        |
|------------------------------|------------------------------------------------|
| `DJANGO_EMAIL_BACKEND`       | `django.core.mail.backends.smtp.EmailBackend`  |
| `DJANGO_EMAIL_HOST`          | `smtp.gmail.com`                               |
| `DJANGO_EMAIL_PORT`          | `587`                                          |
| `DJANGO_EMAIL_HOST_USER`     | `voce@gmail.com`                               |
| `DJANGO_EMAIL_HOST_PASSWORD` | senha de app                                   |
| `DJANGO_DEFAULT_FROM_EMAIL`  | `Suap2 <voce@gmail.com>`                       |

Para rodar automaticamente a cada hora no Windows (Agendador de Tarefas):

```powershell
schtasks /Create /SC HOURLY /TN "Suap2 lembretes" /TR "py -3.14 C:\caminho\para\VictorREPO\Suap2\manage.py enviar_lembretes"
```

No Linux, use o cron: `0 * * * * cd /caminho/Suap2 && python manage.py enviar_lembretes`.

## Atualizando um banco antigo

Depois de puxar esta versão, rode `python manage.py migrate`: a migração `0006` cria a
prioridade (todas as tarefas existentes ficam como Média), a data de início e o histórico.
Nada do que já estava no banco é apagado.

## Atenção: migrações foram unificadas

As migrações antigas (0001–0005) foram juntadas em uma única `0001_initial`.
Se você já tinha um `db.sqlite3` criado com as migrações antigas, apague o
arquivo e rode `python manage.py migrate` de novo.
