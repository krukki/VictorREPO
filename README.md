# Suap2

Gerenciador de tarefas em Django: cadastro de tarefas e de responsáveis.

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

## Atenção: migrações foram unificadas

As migrações antigas (0001–0005) foram juntadas em uma única `0001_initial`.
Se você já tinha um `db.sqlite3` criado com as migrações antigas, apague o
arquivo e rode `python manage.py migrate` de novo.
