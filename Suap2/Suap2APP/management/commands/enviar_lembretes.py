from datetime import timedelta
from itertools import groupby

from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from Suap2APP.models import Tarefa


class Command(BaseCommand):
    help = (
        'Envia um e-mail para cada responsável com as tarefas pendentes cujo prazo '
        'vence nas próximas horas. Cada tarefa recebe no máximo um lembrete por prazo.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--horas', type=int, default=24,
            help='Avisar sobre tarefas que vencem dentro deste número de horas (padrão: 24).',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Só mostra o que seria enviado, sem enviar nem marcar as tarefas.',
        )

    def handle(self, *args, horas, dry_run, **options):
        agora = timezone.now()
        tarefas = (
            Tarefa.objects
            .select_related('pessoa_responsavel')
            .filter(
                concluida_em__isnull=True,
                lembrete_enviado_em__isnull=True,
                prazo__gt=agora,
                prazo__lte=agora + timedelta(hours=horas),
            )
            .exclude(pessoa_responsavel__email='')
            # pelo id, não 'pessoa_responsavel' (que ordenaria por nome e misturaria homônimos)
            .order_by('pessoa_responsavel_id', 'prazo')
        )

        enviados = 0
        for responsavel, grupo in groupby(tarefas, key=lambda t: t.pessoa_responsavel):
            grupo = list(grupo)
            if dry_run:
                self.stdout.write(f'{responsavel.email}: {len(grupo)} tarefa(s)')
                continue
            try:
                self.enviar(responsavel, grupo)
            except Exception as erro:
                self.stderr.write(f'Falha ao enviar para {responsavel.email}: {erro}')
                continue
            Tarefa.objects.filter(pk__in=[t.pk for t in grupo]).update(lembrete_enviado_em=agora)
            enviados += 1

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f'{enviados} lembrete(s) enviado(s).'))

    def enviar(self, responsavel, tarefas):
        linhas = [
            f'- {t.titulo} (prazo: {timezone.localtime(t.prazo):%d/%m/%Y %H:%M})'
            for t in tarefas
        ]
        assunto = (
            f'Lembrete: {len(tarefas)} tarefas vencem em breve'
            if len(tarefas) > 1 else
            f'Lembrete: "{tarefas[0].titulo}" vence em breve'
        )
        corpo = '\n'.join([
            f'Olá, {responsavel.nome}!',
            '',
            'As seguintes tarefas estão com o prazo próximo:',
            '',
            *linhas,
            '',
            'Suap2',
        ])
        send_mail(assunto, corpo, None, [responsavel.email])
