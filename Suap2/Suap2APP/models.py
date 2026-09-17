from django.db import models

# Create your models here.
class Responsavel(models.Model):
    nome = models.CharField(max_length=150, null=False, blank=False)
    cpf = models.CharField(max_length=14, unique=True, null=False, blank=False)
    email = models.EmailField(null=True, blank=True)
    telefone = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        verbose_name = 'Responsável'
        verbose_name_plural = 'Responsáveis'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Tarefa(models.Model):
    title = models.CharField(max_length=100, null=False, blank=False)
    created_at = models.DateTimeField(auto_now_add=True, null=False, blank=False)
    deadline = models.DateTimeField(null=False, blank=False)
    finished_at = models.DateTimeField(null=True, blank=True)
    pessoa_responsavel = models.ForeignKey(Responsavel, on_delete=models.PROTECT)

    class Meta:
        verbose_name = 'Tarefa'
        verbose_name_plural = 'Tarefas'
        ordering = [models.F('finished_at').asc(nulls_first=True), 'deadline']

    def __str__(self):
        return self.title



