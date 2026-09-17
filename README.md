# Suap2

Gerenciador de tarefas em Django: cadastro de tarefas e de responsáveis.

## Como rodar

```bash
python -m venv venv
venv\Scripts\activate        # Linux/macOS: source venv/bin/activate
pip install "Django>=6.1,<6.2"
cd Suap2
python manage.py migrate
python manage.py createsuperuser   # opcional, para acessar /admin
python manage.py runserver
```

Acesse http://127.0.0.1:8000/.

## Atenção: migrações foram unificadas

As migrações antigas (0001–0005) foram juntadas em uma única `0001_initial`.
Se você já tinha um `db.sqlite3` criado com as migrações antigas, apague o
arquivo e rode `python manage.py migrate` de novo.
