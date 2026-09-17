from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import ResponsavelForm
from .models import Responsavel, Tarefa

CPF_VALIDO = '529.982.247-25'


class BaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user('ana', password='senha-forte-123')
        cls.responsavel = Responsavel.objects.create(nome='Ana', cpf=CPF_VALIDO)

    def setUp(self):
        self.client.force_login(self.usuario)

    def criar_tarefa(self, titulo='Tarefa', dias=1, **kwargs):
        return Tarefa.objects.create(
            titulo=titulo,
            prazo=timezone.now() + timedelta(days=dias),
            pessoa_responsavel=self.responsavel,
            **kwargs,
        )


class AutenticacaoTests(TestCase):
    def test_paginas_exigem_login(self):
        urls = [
            reverse('tarefa_list'),
            reverse('tarefa_create'),
            reverse('responsavel_list'),
            reverse('responsavel_create'),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_login(self):
        User.objects.create_user('ana', password='senha-forte-123')
        response = self.client.post(reverse('login'), {'username': 'ana', 'password': 'senha-forte-123'})
        self.assertRedirects(response, reverse('tarefa_list'))


class TarefaTests(BaseTestCase):
    def test_lista_ordena_pendentes_por_prazo_e_concluidas_por_ultimo(self):
        self.criar_tarefa('concluida', dias=-5, concluida_em=timezone.now())
        self.criar_tarefa('depois', dias=5)
        self.criar_tarefa('antes', dias=1)

        response = self.client.get(reverse('tarefa_list'))

        titulos = [t.titulo for t in response.context['tarefas']]
        self.assertEqual(titulos, ['antes', 'depois', 'concluida'])

    def test_lista_nao_faz_uma_consulta_por_tarefa(self):
        for i in range(5):
            self.criar_tarefa(f'Tarefa {i}')
        # sessão, usuário, contagem da paginação, tarefas com responsável e opções do filtro
        with self.assertNumQueries(5):
            self.client.get(reverse('tarefa_list'))
        for i in range(5, 10):
            self.criar_tarefa(f'Tarefa {i}')
        with self.assertNumQueries(5):
            self.client.get(reverse('tarefa_list'))

    def test_lista_marca_tarefa_atrasada(self):
        self.criar_tarefa('Atrasada', dias=-1)
        response = self.client.get(reverse('tarefa_list'))
        self.assertContains(response, 'Atrasada — prazo era')

    def test_criar(self):
        response = self.client.post(reverse('tarefa_create'), {
            'titulo': 'Nova',
            'prazo': '2030-01-01T10:00',
            'pessoa_responsavel': self.responsavel.pk,
        }, follow=True)

        self.assertRedirects(response, reverse('tarefa_list'))
        self.assertContains(response, 'Tarefa &quot;Nova&quot; criada.')
        self.assertTrue(Tarefa.objects.filter(titulo='Nova').exists())

    def test_formulario_avisa_quando_nao_ha_responsaveis(self):
        Responsavel.objects.all().delete()
        response = self.client.get(reverse('tarefa_create'))
        self.assertContains(response, 'Cadastre um responsável')

    def test_editar(self):
        tarefa = self.criar_tarefa()
        self.client.post(reverse('tarefa_update', args=[tarefa.pk]), {
            'titulo': 'Editada',
            'prazo': '2030-01-01T10:00',
            'pessoa_responsavel': self.responsavel.pk,
        })
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.titulo, 'Editada')

    def test_excluir(self):
        tarefa = self.criar_tarefa()
        response = self.client.post(reverse('tarefa_delete', args=[tarefa.pk]))
        self.assertRedirects(response, reverse('tarefa_list'))
        self.assertFalse(Tarefa.objects.filter(pk=tarefa.pk).exists())

    def test_concluir_e_reabrir(self):
        tarefa = self.criar_tarefa()
        url = reverse('tarefa_toggle', args=[tarefa.pk])

        self.client.post(url)
        tarefa.refresh_from_db()
        self.assertIsNotNone(tarefa.concluida_em)

        self.client.post(url)
        tarefa.refresh_from_db()
        self.assertIsNone(tarefa.concluida_em)

    def test_concluir_exige_post(self):
        tarefa = self.criar_tarefa()
        response = self.client.get(reverse('tarefa_toggle', args=[tarefa.pk]))
        self.assertEqual(response.status_code, 405)


class ResponsavelTests(BaseTestCase):
    def test_criar(self):
        response = self.client.post(reverse('responsavel_create'), {
            'nome': 'Bia',
            'cpf': '11144477735',
        })
        self.assertRedirects(response, reverse('responsavel_list'))
        self.assertEqual(Responsavel.objects.get(nome='Bia').cpf, '111.444.777-35')

    def test_nao_excluir_com_tarefas(self):
        self.criar_tarefa()
        url = reverse('responsavel_delete', args=[self.responsavel.pk])

        self.assertContains(self.client.get(url), 'Não é possível excluir')
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Responsavel.objects.filter(pk=self.responsavel.pk).exists())

    def test_excluir_sem_tarefas(self):
        response = self.client.post(reverse('responsavel_delete', args=[self.responsavel.pk]))
        self.assertRedirects(response, reverse('responsavel_list'))
        self.assertFalse(Responsavel.objects.exists())


class ResponsavelFormTests(TestCase):
    def test_cpf_invalido(self):
        for cpf in ['123.456.789-00', '111.111.111-11', '1234', 'abc']:
            with self.subTest(cpf=cpf):
                form = ResponsavelForm(data={'nome': 'X', 'cpf': cpf})
                self.assertIn('cpf', form.errors)

    def test_cpf_duplicado_em_outro_formato(self):
        Responsavel.objects.create(nome='Ana', cpf=CPF_VALIDO)
        form = ResponsavelForm(data={'nome': 'Outra', 'cpf': '52998224725'})
        self.assertIn('cpf', form.errors)


class FiltroTarefaTests(BaseTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.outro = Responsavel.objects.create(nome='Bia', cpf='111.444.777-35')

    def setUp(self):
        super().setUp()
        self.pendente = self.criar_tarefa('Comprar pão', dias=2)
        self.atrasada = self.criar_tarefa('Pagar conta', dias=-2)
        self.concluida = self.criar_tarefa('Lavar carro', dias=-1, concluida_em=timezone.now())
        self.da_bia = Tarefa.objects.create(
            titulo='Estudar', prazo=timezone.now() + timedelta(days=3), pessoa_responsavel=self.outro,
        )

    def titulos(self, **params):
        response = self.client.get(reverse('tarefa_list'), params)
        return {t.titulo for t in response.context['tarefas']}

    def test_status(self):
        self.assertEqual(self.titulos(status='pendentes'), {'Comprar pão', 'Pagar conta', 'Estudar'})
        self.assertEqual(self.titulos(status='atrasadas'), {'Pagar conta'})
        self.assertEqual(self.titulos(status='concluidas'), {'Lavar carro'})
        self.assertEqual(len(self.titulos()), 4)

    def test_responsavel(self):
        self.assertEqual(self.titulos(responsavel=self.outro.pk), {'Estudar'})

    def test_busca_ignora_maiusculas(self):
        self.assertEqual(self.titulos(q='PAGAR'), {'Pagar conta'})

    def test_filtros_combinados(self):
        self.assertEqual(
            self.titulos(q='a', status='pendentes', responsavel=self.responsavel.pk),
            {'Comprar pão', 'Pagar conta'},
        )

    def test_filtro_invalido_mostra_tudo(self):
        self.assertEqual(len(self.titulos(status='xyz')), 4)

    def test_sem_resultados(self):
        response = self.client.get(reverse('tarefa_list'), {'q': 'nada disso'})
        self.assertContains(response, 'Nenhuma tarefa encontrada com esses filtros.')

    def test_paginacao_mantem_filtros(self):
        for i in range(12):
            self.criar_tarefa(f'Extra {i}', dias=10 + i)
        response = self.client.get(reverse('tarefa_list'), {'status': 'pendentes'})

        self.assertEqual(len(response.context['tarefas']), 10)
        self.assertContains(response, '?status=pendentes&amp;page=2')

        response = self.client.get(reverse('tarefa_list'), {'status': 'pendentes', 'page': 2})
        self.assertEqual(len(response.context['tarefas']), 5)

    def test_concluir_volta_para_a_pagina_filtrada(self):
        destino = reverse('tarefa_list') + '?status=pendentes'
        response = self.client.post(reverse('tarefa_toggle', args=[self.pendente.pk]), {'next': destino})
        self.assertRedirects(response, destino)

    def test_concluir_ignora_next_externo(self):
        response = self.client.post(
            reverse('tarefa_toggle', args=[self.pendente.pk]), {'next': 'https://exemplo.com/'},
        )
        self.assertRedirects(response, reverse('tarefa_list'))


class ResponsavelDetailTests(BaseTestCase):
    def test_mostra_tarefas_e_contadores(self):
        self.criar_tarefa('Pendente', dias=2)
        self.criar_tarefa('Atrasada 1', dias=-1)
        self.criar_tarefa('Atrasada 2', dias=-2)
        self.criar_tarefa('Feita', dias=-3, concluida_em=timezone.now())

        response = self.client.get(reverse('responsavel_detail', args=[self.responsavel.pk]))

        self.assertEqual(response.context['pendentes'], 3)
        self.assertEqual(response.context['atrasadas'], 2)
        self.assertEqual(response.context['concluidas'], 1)
        self.assertEqual(len(response.context['tarefas']), 4)
        self.assertContains(response, 'Atrasada 2')

    def test_nao_mostra_tarefas_de_outros(self):
        outro = Responsavel.objects.create(nome='Bia', cpf='111.444.777-35')
        Tarefa.objects.create(titulo='Da Bia', prazo=timezone.now(), pessoa_responsavel=outro)
        response = self.client.get(reverse('responsavel_detail', args=[self.responsavel.pk]))
        self.assertNotContains(response, 'Da Bia')
        self.assertContains(response, 'Nenhuma tarefa atribuída')

    def test_inexistente(self):
        response = self.client.get(reverse('responsavel_detail', args=[999]))
        self.assertEqual(response.status_code, 404)


class EnviarLembretesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = Responsavel.objects.create(nome='Ana', cpf=CPF_VALIDO, email='ana@exemplo.com')

    def criar(self, titulo, horas, responsavel=None, **kwargs):
        return Tarefa.objects.create(
            titulo=titulo,
            prazo=timezone.now() + timedelta(hours=horas),
            pessoa_responsavel=responsavel or self.ana,
            **kwargs,
        )

    def rodar(self, *args):
        saida = StringIO()
        call_command('enviar_lembretes', *args, stdout=saida, stderr=StringIO())
        return saida.getvalue()

    def test_agrupa_tarefas_por_responsavel_em_um_email(self):
        t1 = self.criar('Relatório', horas=3)
        t2 = self.criar('Reunião', horas=20)

        self.rodar()

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['ana@exemplo.com'])
        self.assertIn('2 tarefas', email.subject)
        self.assertIn('Relatório', email.body)
        self.assertIn('Reunião', email.body)
        for tarefa in (t1, t2):
            tarefa.refresh_from_db()
            self.assertIsNotNone(tarefa.lembrete_enviado_em)

    def test_um_email_por_responsavel_mesmo_com_nomes_iguais(self):
        outra_ana = Responsavel.objects.create(nome='Ana', cpf='111.444.777-35', email='outra@exemplo.com')
        self.criar('A', horas=1)
        self.criar('B', horas=2, responsavel=outra_ana)
        self.criar('C', horas=3)

        self.rodar()

        self.assertEqual(sorted(e.to[0] for e in mail.outbox), ['ana@exemplo.com', 'outra@exemplo.com'])

    def test_ignora_tarefas_que_nao_devem_ser_lembradas(self):
        sem_email = Responsavel.objects.create(nome='Bia', cpf='111.444.777-35')
        self.criar('Longe', horas=48)
        self.criar('Vencida', horas=-1)
        self.criar('Feita', horas=2, concluida_em=timezone.now())
        self.criar('Já avisada', horas=2, lembrete_enviado_em=timezone.now())
        self.criar('Sem e-mail', horas=2, responsavel=sem_email)

        self.rodar()

        self.assertEqual(mail.outbox, [])

    def test_nao_envia_duas_vezes(self):
        self.criar('Relatório', horas=3)
        self.rodar()
        self.rodar()
        self.assertEqual(len(mail.outbox), 1)

    def test_opcao_horas(self):
        self.criar('Semana que vem', horas=100)
        self.rodar('--horas', '24')
        self.assertEqual(mail.outbox, [])
        self.rodar('--horas', '168')
        self.assertEqual(len(mail.outbox), 1)

    def test_dry_run_nao_envia_nem_marca(self):
        tarefa = self.criar('Relatório', horas=3)

        saida = self.rodar('--dry-run')

        self.assertIn('ana@exemplo.com: 1 tarefa(s)', saida)
        self.assertEqual(mail.outbox, [])
        tarefa.refresh_from_db()
        self.assertIsNone(tarefa.lembrete_enviado_em)

    def test_mudar_prazo_permite_novo_lembrete(self):
        usuario = User.objects.create_user('ana', password='senha-forte-123')
        self.client.force_login(usuario)
        tarefa = self.criar('Relatório', horas=3, lembrete_enviado_em=timezone.now())
        url = reverse('tarefa_update', args=[tarefa.pk])
        prazo_atual = timezone.localtime(tarefa.prazo).strftime('%Y-%m-%dT%H:%M')

        # Mudar só o título mantém o lembrete já enviado
        tarefa.prazo = tarefa.prazo.replace(second=0, microsecond=0)
        tarefa.save()
        self.client.post(url, {'titulo': 'Relatório final', 'prazo': prazo_atual, 'pessoa_responsavel': self.ana.pk})
        tarefa.refresh_from_db()
        self.assertIsNotNone(tarefa.lembrete_enviado_em)

        self.client.post(url, {'titulo': 'Relatório final', 'prazo': '2030-01-01T10:00', 'pessoa_responsavel': self.ana.pk})
        tarefa.refresh_from_db()
        self.assertIsNone(tarefa.lembrete_enviado_em)
