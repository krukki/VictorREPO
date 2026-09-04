from django.db import models

# Create your models here.

class tarefa(models.Model):
    titulo = models.CharField(max_length=200)
    descricao = models.TextField()
    concluida = models.BooleanField(default=False)
    data_criacao = models.DateTimeField(auto_now_add=True)