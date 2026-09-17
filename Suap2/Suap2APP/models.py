from django.db import models


class Responsavel(models.Model):
    nome = models.CharField(max_length=150)
    cpf = models.CharField(max_length=14, unique=True)
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = 'Responsável'
        verbose_name_plural = 'Responsáveis'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Tarefa(models.Model):
    titulo = models.CharField(max_length=100)
    criada_em = models.DateTimeField(auto_now_add=True)
    prazo = models.DateTimeField()
    concluida_em = models.DateTimeField(null=True, blank=True)
    lembrete_enviado_em = models.DateTimeField(null=True, blank=True, editable=False)
    pessoa_responsavel = models.ForeignKey(Responsavel, on_delete=models.PROTECT)

    class Meta:
        verbose_name = 'Tarefa'
        verbose_name_plural = 'Tarefas'
        ordering = [models.F('concluida_em').asc(nulls_first=True), 'prazo']

    def __str__(self):
        return self.titulo
