import os
from decimal import Decimal

from django.conf import settings
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

    # As três situações. "Pendente" (usada nos contadores e filtros) é a_fazer + em_andamento.

    def a_fazer(self):
        return self.filter(concluida_em__isnull=True, iniciada_em__isnull=True)

    def em_andamento(self):
        return self.filter(concluida_em__isnull=True, iniciada_em__isnull=False)

    def concluidas(self):
        return self.filter(concluida_em__isnull=False)

    def com_peso_da_prioridade(self):
        """Anota `peso_prioridade` (0 = alta, 2 = baixa) para ordenar pela prioridade."""
        return self.annotate(peso_prioridade=models.Case(
            *(models.When(prioridade=valor, then=peso) for peso, (valor, _) in enumerate(Tarefa.PRIORIDADES)),
            default=1,
            output_field=models.IntegerField(),
        ))


class Tarefa(models.Model):
    # Da mais para a menos urgente: a ordem define o peso usado para ordenar
    PRIORIDADES = [
        ('alta', 'Alta'),
        ('media', 'Média'),
        ('baixa', 'Baixa'),
    ]
    SITUACOES = [
        ('a_fazer', 'A fazer'),
        ('em_andamento', 'Em andamento'),
        ('concluida', 'Concluída'),
    ]

    titulo = models.CharField(max_length=100)
    criada_em = models.DateTimeField(auto_now_add=True)
    prazo = models.DateTimeField()
    prioridade = models.CharField(max_length=5, choices=PRIORIDADES, default='media')
    iniciada_em = models.DateTimeField(null=True, blank=True)
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
    def situacao(self):
        if self.concluida_em:
            return 'concluida'
        return 'em_andamento' if self.iniciada_em else 'a_fazer'

    def get_situacao_display(self):
        return dict(self.SITUACOES)[self.situacao]

    def mudar_situacao(self, nova):
        """Leva a tarefa para `nova` e devolve a ação para o histórico, ou None se nada mudou.

        Não salva: quem chama faz save(update_fields=['iniciada_em', 'concluida_em']).
        """
        if nova not in dict(self.SITUACOES):
            raise ValueError(f'Situação desconhecida: {nova}')
        antiga = self.situacao
        if nova == antiga:
            return None
        agora = timezone.now()
        if nova == 'concluida':
            self.concluida_em = agora
            return 'concluiu'
        self.concluida_em = None
        if nova == 'em_andamento':
            # Quem reabre uma tarefa que já tinha sido iniciada mantém a data de início
            self.iniciada_em = self.iniciada_em or agora
            return 'reabriu' if antiga == 'concluida' else 'iniciou'
        self.iniciada_em = None
        return 'reabriu' if antiga == 'concluida' else 'voltou'

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


class Atividade(models.Model):
    """Linha do histórico de uma tarefa: quem fez o quê e quando."""
    ACOES = [
        ('criou', 'Criou a tarefa'),
        ('editou', 'Editou'),
        ('iniciou', 'Começou a trabalhar na tarefa'),
        ('concluiu', 'Concluiu a tarefa'),
        ('reabriu', 'Reabriu a tarefa'),
        ('voltou', 'Voltou a tarefa para "A fazer"'),
        ('adicionou', 'Adicionou'),
        ('removeu', 'Removeu'),
        ('marcou', 'Marcou'),
        ('desmarcou', 'Desmarcou'),
    ]

    tarefa = models.ForeignKey(Tarefa, on_delete=models.CASCADE, related_name='atividades')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    acao = models.CharField(max_length=10, choices=ACOES)
    detalhe = models.CharField(max_length=200, blank=True)
    criada_em = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Atividade'
        verbose_name_plural = 'Atividades'
        ordering = ['-criada_em', '-pk']

    def __str__(self):
        return f'{self.tarefa}: {self.texto}'

    @property
    def texto(self):
        """Frase pronta para a tela, ex.: "Editou: título, prazo" ou "Adicionou a subtarefa “X”"."""
        rotulo = self.get_acao_display()
        if not self.detalhe:
            return rotulo
        separador = ': ' if self.acao == 'editou' else ' '
        return f'{rotulo}{separador}{self.detalhe}'


def registrar_atividade(tarefa, usuario, acao, detalhe=''):
    """Grava uma linha no histórico. `usuario` pode ser anônimo (vira None)."""
    if usuario is not None and not usuario.is_authenticated:
        usuario = None
    return Atividade.objects.create(tarefa=tarefa, usuario=usuario, acao=acao, detalhe=detalhe[:200])
