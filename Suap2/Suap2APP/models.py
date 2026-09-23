import os
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone


class Departamento(models.Model):
    """Setor da instituição; agrupa responsáveis e projetos."""
    nome = models.CharField(max_length=100, unique=True)
    sigla = models.CharField(max_length=10, blank=True)

    class Meta:
        verbose_name = 'Departamento'
        verbose_name_plural = 'Departamentos'
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome} ({self.sigla})' if self.sigla else self.nome


class Responsavel(models.Model):
    nome = models.CharField(max_length=150)
    cpf = models.CharField(max_length=14, unique=True)
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    departamento = models.ForeignKey(
        Departamento, on_delete=models.SET_NULL, null=True, blank=True, related_name='responsaveis',
    )

    class Meta:
        verbose_name = 'Responsável'
        verbose_name_plural = 'Responsáveis'
        ordering = ['nome']

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return reverse('responsavel_detail', args=[self.pk])


class Projeto(models.Model):
    """Conjunto de tarefas com um objetivo comum."""
    nome = models.CharField(max_length=120, unique=True)
    descricao = models.TextField(blank=True)
    departamento = models.ForeignKey(
        Departamento, on_delete=models.SET_NULL, null=True, blank=True, related_name='projetos',
    )
    inicio = models.DateField(null=True, blank=True)
    fim = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Projeto'
        verbose_name_plural = 'Projetos'
        ordering = ['nome']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(inicio__isnull=True)
                    | models.Q(fim__isnull=True)
                    | models.Q(fim__gte=models.F('inicio'))
                ),
                name='projeto_fim_depois_do_inicio',
            ),
        ]

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return reverse('projeto_detail', args=[self.pk])

    @property
    def encerrado(self):
        return self.fim is not None and self.fim < timezone.localdate()


class Categoria(models.Model):
    """Assunto da tarefa. Cada tarefa tem no máximo uma."""
    CORES = [
        ('azul', 'Azul'),
        ('verde', 'Verde'),
        ('amarelo', 'Amarelo'),
        ('vermelho', 'Vermelho'),
        ('cinza', 'Cinza'),
    ]

    nome = models.CharField(max_length=60, unique=True)
    cor = models.CharField(max_length=10, choices=CORES, default='cinza')

    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Etiqueta(models.Model):
    """Marcador livre; uma tarefa pode ter várias."""
    nome = models.CharField(max_length=40, unique=True)

    class Meta:
        verbose_name = 'Etiqueta'
        verbose_name_plural = 'Etiquetas'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class TarefaQuerySet(models.QuerySet):
    def com_relacionados(self):
        """Tudo o que `_tarefa_item.html` mostra, sem uma consulta por tarefa."""
        return self.select_related('pessoa_responsavel', 'projeto', 'categoria').prefetch_related(
            'etiquetas', 'subtarefas',
        )


class Tarefa(models.Model):
    titulo = models.CharField(max_length=100)
    criada_em = models.DateTimeField(auto_now_add=True)
    prazo = models.DateTimeField()
    concluida_em = models.DateTimeField(null=True, blank=True)
    lembrete_enviado_em = models.DateTimeField(null=True, blank=True, editable=False)
    pessoa_responsavel = models.ForeignKey(Responsavel, on_delete=models.PROTECT)
    projeto = models.ForeignKey(Projeto, on_delete=models.SET_NULL, null=True, blank=True, related_name='tarefas')
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True, related_name='tarefas')
    etiquetas = models.ManyToManyField(Etiqueta, blank=True, related_name='tarefas')

    objects = TarefaQuerySet.as_manager()

    class Meta:
        verbose_name = 'Tarefa'
        verbose_name_plural = 'Tarefas'
        ordering = [models.F('concluida_em').asc(nulls_first=True), 'prazo']

    def __str__(self):
        return self.titulo

    def get_absolute_url(self):
        return reverse('tarefa_detail', args=[self.pk])

    @property
    def atrasada(self):
        return self.concluida_em is None and self.prazo < timezone.now()

    @property
    def progresso(self):
        """Percentual de subtarefas concluídas, ou None quando não há subtarefas."""
        # all() em vez de filter()/count() para aproveitar o prefetch_related das telas
        subtarefas = list(self.subtarefas.all())
        if not subtarefas:
            return None
        return round(100 * sum(1 for s in subtarefas if s.concluida) / len(subtarefas))

    @property
    def horas_registradas(self):
        return sum((r.horas for r in self.registros_tempo.all()), Decimal('0'))


class Subtarefa(models.Model):
    """Item de checklist dentro de uma tarefa."""
    tarefa = models.ForeignKey(Tarefa, on_delete=models.CASCADE, related_name='subtarefas')
    descricao = models.CharField(max_length=150)
    concluida = models.BooleanField(default=False)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Subtarefa'
        verbose_name_plural = 'Subtarefas'
        ordering = ['ordem', 'pk']

    def __str__(self):
        return self.descricao

    def save(self, *args, **kwargs):
        # Item novo sem ordem definida vai para o fim da lista
        if self._state.adding and not self.ordem:
            ultima = Subtarefa.objects.filter(tarefa=self.tarefa_id).aggregate(models.Max('ordem'))
            self.ordem = (ultima['ordem__max'] or 0) + 1
        return super().save(*args, **kwargs)


class Comentario(models.Model):
    """Recado registrado em uma tarefa."""
    tarefa = models.ForeignKey(Tarefa, on_delete=models.CASCADE, related_name='comentarios')
    autor = models.ForeignKey(
        Responsavel, on_delete=models.SET_NULL, null=True, blank=True, related_name='comentarios',
    )
    texto = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Comentário'
        verbose_name_plural = 'Comentários'
        ordering = ['-criado_em', '-pk']

    def __str__(self):
        return f'{self.autor or "Anônimo"}: {self.texto[:40]}'


class Anexo(models.Model):
    """Arquivo enviado em uma tarefa."""
    tarefa = models.ForeignKey(Tarefa, on_delete=models.CASCADE, related_name='anexos')
    arquivo = models.FileField(upload_to='anexos/%Y/%m')
    descricao = models.CharField(max_length=150, blank=True)
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Anexo'
        verbose_name_plural = 'Anexos'
        ordering = ['-enviado_em', '-pk']

    def __str__(self):
        return self.descricao or self.nome_arquivo

    @property
    def nome_arquivo(self):
        return os.path.basename(self.arquivo.name)


# O Django apaga a linha do banco, mas nunca o arquivo em MEDIA_ROOT. O sinal cobre tanto
# a exclusão de um anexo quanto o cascade de quando a tarefa inteira é excluída.
@receiver(post_delete, sender=Anexo)
def apagar_arquivo_do_anexo(sender, instance, **kwargs):
    if instance.arquivo:
        instance.arquivo.delete(save=False)


class RegistroTempo(models.Model):
    """Apontamento de horas trabalhadas em uma tarefa."""
    tarefa = models.ForeignKey(Tarefa, on_delete=models.CASCADE, related_name='registros_tempo')
    responsavel = models.ForeignKey(Responsavel, on_delete=models.PROTECT, related_name='registros_tempo')
    horas = models.DecimalField(
        max_digits=5, decimal_places=2, validators=[MinValueValidator(Decimal('0.25'))],
    )
    data = models.DateField(default=timezone.localdate)
    observacao = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = 'Registro de tempo'
        verbose_name_plural = 'Registros de tempo'
        ordering = ['-data', '-pk']

    def __str__(self):
        return f'{self.horas}h por {self.responsavel} em {self.data:%d/%m/%Y}'
