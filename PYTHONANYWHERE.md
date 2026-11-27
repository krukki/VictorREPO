# Publicar no PythonAnywhere (plano grátis)

Passo a passo para colocar o Suap2 no ar em `https://SEUUSUARIO.pythonanywhere.com`.
Em todo este arquivo, troque **`SEUUSUARIO`** pelo seu nome de usuário no PythonAnywhere.

O plano grátis ("Beginner") permite um site, sem domínio próprio. A cada 3 meses é preciso
entrar na aba **Web** e clicar em **"Run until 3 months from today"**, senão o site é
desligado (os dados não se perdem).

## 1. Criar a conta

Cadastre-se em https://www.pythonanywhere.com/ e escolha o plano **Beginner** (grátis).

## 2. Criar um token do GitHub

O repositório é privado, então o PythonAnywhere precisa de uma senha para baixá-lo.

1. No GitHub: **Settings → Developer settings → Personal access tokens → Fine-grained tokens
   → Generate new token**.
2. Em **Repository access**, escolha **Only select repositories** → `krukki/VictorREPO`.
3. Em **Permissions → Repository permissions → Contents**, escolha **Read-only**.
4. Gere e copie o token (começa com `github_pat_`). Ele só aparece uma vez.

## 3. Baixar o código e instalar

No PythonAnywhere, abra **Consoles → Bash** e rode (cole o token quando pedir a senha;
o usuário é `krukki`):

```bash
git clone https://github.com/krukki/VictorREPO.git
cd VictorREPO
python3.13 -m venv ~/.venvs/suap2
source ~/.venvs/suap2/bin/activate
pip install -r requirements.txt
```

O Django 6.1 exige Python 3.12 ou mais novo. Se `python3.13` não existir, use a versão mais
nova que aparecer em `ls /usr/bin/python3.*` (e escolha a mesma no passo 5).

## 4. Banco de dados e arquivos estáticos

Ainda no console, gere uma chave secreta e guarde-a para o passo 6:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

Depois crie o banco **fora** do repositório (assim um `git pull` nunca apaga seus dados):

```bash
mkdir -p ~/suap2-dados
export DJANGO_DB_PATH=~/suap2-dados/db.sqlite3
cd ~/VictorREPO/Suap2
python manage.py migrate
python manage.py loaddata exemplos     # opcional: dados de exemplo
python manage.py createsuperuser       # seu usuário para entrar no site
python manage.py collectstatic --noinput
```

## 5. Criar o site

Na aba **Web**:

1. **Add a new web app → Next → Manual configuration** (não escolha "Django") →
   a mesma versão de Python do passo 3.
2. Em **Virtualenv**, coloque `/home/SEUUSUARIO/.venvs/suap2`.
3. Em **Code**, coloque `/home/SEUUSUARIO/VictorREPO/Suap2` em **Source code** e
   **Working directory**.
4. Em **Static files**, adicione duas linhas:

   | URL       | Directory                                       |
   |-----------|-------------------------------------------------|
   | `/static/` | `/home/SEUUSUARIO/VictorREPO/Suap2/staticfiles` |
   | `/media/`  | `/home/SEUUSUARIO/VictorREPO/Suap2/media`       |

5. Em **Security**, ative **Force HTTPS**.

## 6. Arquivo WSGI

Ainda na aba **Web**, em **Code**, clique no link do **WSGI configuration file**, apague
tudo o que estiver lá e cole o texto abaixo. Troque `SEUUSUARIO` e cole a chave do passo 4.
Este arquivo fica só no PythonAnywhere, então a chave não vai para o GitHub.

```python
import os
import sys

USUARIO = 'SEUUSUARIO'

sys.path.insert(0, f'/home/{USUARIO}/VictorREPO/Suap2')

os.environ['DJANGO_SETTINGS_MODULE'] = 'Suap2.settings'
os.environ['DJANGO_DEBUG'] = '0'
os.environ['DJANGO_SECRET_KEY'] = 'COLE-A-CHAVE-AQUI'
os.environ['DJANGO_ALLOWED_HOSTS'] = f'{USUARIO}.pythonanywhere.com'
os.environ['DJANGO_CSRF_TRUSTED_ORIGINS'] = f'https://{USUARIO}.pythonanywhere.com'
os.environ['DJANGO_DB_PATH'] = f'/home/{USUARIO}/suap2-dados/db.sqlite3'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Salve, volte à aba **Web** e clique em **Reload**. Abra
`https://SEUUSUARIO.pythonanywhere.com` e entre com o usuário criado no passo 4.

Se aparecer erro, veja o **Error log** na aba **Web** (link na seção **Log files**).

## Atualizar o site depois de mudar o código

```bash
source ~/.venvs/suap2/bin/activate
export DJANGO_DB_PATH=~/suap2-dados/db.sqlite3
cd ~/VictorREPO && git pull
pip install -r requirements.txt
cd Suap2
python manage.py migrate
python manage.py collectstatic --noinput
```

Depois clique em **Reload** na aba **Web**.

## Lembretes por e-mail (opcional)

O plano grátis permite **uma tarefa agendada por dia** e só deixa enviar e-mail pelo Gmail.
Para usar:

1. Acrescente ao arquivo WSGI as variáveis de e-mail do Gmail listadas no README
   (`DJANGO_EMAIL_BACKEND`, `DJANGO_EMAIL_HOST` etc.).
2. Na aba **Tasks**, crie uma tarefa diária com o comando abaixo, colocando as mesmas
   variáveis de e-mail antes de `python`:

```bash
cd ~/VictorREPO/Suap2 && DJANGO_DB_PATH=~/suap2-dados/db.sqlite3 ~/.venvs/suap2/bin/python manage.py enviar_lembretes --horas 24
```
