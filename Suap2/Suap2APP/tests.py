import os
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse, reverse_lazy
from django.utils import timezone

from .forms import ProjetoForm, RegistroTempoForm, ResponsavelForm, TarefaForm, TarefaRapidaForm
from .models import (
    Anexo,
    Atividade,
    Categoria,
    Comentario,
    Departamento,
    Etiqueta,
    Projeto,
    RegistroTempo,
    Responsavel,
    Subtarefa,
    Tarefa,
    registrar_atividade,
)

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
            reverse('painel'),
            reverse('tarefa_list'),
            reverse('tarefa_create'),
            reverse('responsavel_list'),
            reverse('responsavel_create'),
            reverse('departamento_list'),
            reverse('departamento_create'),
            reverse('projeto_list'),
            reverse('projeto_create'),
            reverse('categoria_list'),
            reverse('categoria_create'),
            reverse('etiqueta_list'),
            reverse('etiqueta_create'),
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
        # sessão, usuário, contagem da paginação, os contadores, as 4 opções dos filtros, as
        # tarefas com responsável/projeto/categoria e os prefetch de etiquetas e subtarefas
        with self.assertNumQueries(11):
            self.client.get(reverse('tarefa_list'))
        for i in range(5, 10):
            self.criar_tarefa(f'Tarefa {i}')
        with self.assertNumQueries(11):
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


class PainelTests(BaseTestCase):
    def test_contadores(self):
        self.criar_tarefa('Pendente', dias=3)
        self.criar_tarefa('Pendente longe', dias=30)
        self.criar_tarefa('Atrasada', dias=-1)
        self.criar_tarefa('Concluída', dias=-2, concluida_em=timezone.now())
        self.criar_tarefa('Concluída antiga', dias=-20, concluida_em=timezone.now() - timedelta(days=10))
        response = self.client.get(reverse('painel'))
        self.assertEqual(response.context['pendentes'], 3)
        self.assertEqual(response.context['atrasadas'], 1)
        self.assertEqual(response.context['concluidas'], 2)
        self.assertEqual(response.context['vencem_na_semana'], 1)
        self.assertEqual(response.context['concluidas_na_semana'], 1)

    def test_proximas_sao_pendentes_por_prazo(self):
        for dias in [5, 1, 3, 2, 4, 6]:
            self.criar_tarefa(f'Em {dias} dias', dias=dias)
        self.criar_tarefa('Concluída', dias=0, concluida_em=timezone.now())
        response = self.client.get(reverse('painel'))
        titulos = [t.titulo for t in response.context['proximas']]
        self.assertEqual(titulos, ['Em 1 dias', 'Em 2 dias', 'Em 3 dias', 'Em 4 dias', 'Em 5 dias'])

    def test_responsaveis_sem_pendencias_nao_aparecem(self):
        outro = Responsavel.objects.create(nome='Bruno', cpf='111.444.777-35')
        Tarefa.objects.create(
            titulo='Feita', prazo=timezone.now(), pessoa_responsavel=outro, concluida_em=timezone.now(),
        )
        self.criar_tarefa('Atrasada', dias=-1)
        response = self.client.get(reverse('painel'))
        responsaveis = list(response.context['responsaveis'])
        self.assertEqual(responsaveis, [self.responsavel])
        self.assertEqual(responsaveis[0].atrasadas, 1)

    def test_consultas_nao_crescem_com_tarefas(self):
        self.criar_tarefa()
        with self.assertNumQueries(9) as consultas:
            self.client.get(reverse('painel'))
        for dias in range(10):
            self.criar_tarefa(dias=dias)
        with self.assertNumQueries(len(consultas)):
            self.client.get(reverse('painel'))


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

    def contadores(self, **params):
        context = self.client.get(reverse('tarefa_list'), params).context
        return {chave: context[chave] for chave in ('total', 'pendentes', 'atrasadas', 'concluidas')}

    def test_contadores(self):
        esperado = {'total': 4, 'pendentes': 3, 'atrasadas': 1, 'concluidas': 1}
        self.assertEqual(self.contadores(), esperado)

    def test_contadores_ignoram_situacao(self):
        esperado = {'total': 4, 'pendentes': 3, 'atrasadas': 1, 'concluidas': 1}
        self.assertEqual(self.contadores(status='concluidas'), esperado)

    def test_contadores_respeitam_responsavel_e_busca(self):
        self.assertEqual(
            self.contadores(responsavel=self.outro.pk),
            {'total': 1, 'pendentes': 1, 'atrasadas': 0, 'concluidas': 0},
        )
        self.assertEqual(
            self.contadores(q='conta'),
            {'total': 1, 'pendentes': 1, 'atrasadas': 1, 'concluidas': 0},
        )

    def test_contador_mantem_busca_e_volta_para_primeira_pagina(self):
        response = self.client.get(reverse('tarefa_list'), {'q': 'a', 'status': 'pendentes', 'page': 1})
        self.assertContains(response, 'href="?q=a&amp;status=atrasadas"')
        self.assertContains(response, 'class="contador contador-ativo" href="?q=a&amp;status=pendentes"')

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

    def test_pagina_404_personalizada(self):
        response = self.client.get(reverse('responsavel_detail', args=[999]))
        self.assertTemplateUsed(response, '404.html')
        self.assertContains(response, 'Página não encontrada', status_code=404)


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


class DepartamentoTests(BaseTestCase):
    def test_criar(self):
        response = self.client.post(reverse('departamento_create'), {
            'nome': 'Coordenação de Informática',
            'sigla': 'CINF',
        })
        self.assertRedirects(response, reverse('departamento_list'))
        self.assertEqual(str(Departamento.objects.get(sigla='CINF')), 'Coordenação de Informática (CINF)')

    def test_lista_conta_responsaveis_e_projetos(self):
        departamento = Departamento.objects.create(nome='Ensino', sigla='DE')
        self.responsavel.departamento = departamento
        self.responsavel.save(update_fields=['departamento'])
        Projeto.objects.create(nome='Semana Acadêmica', departamento=departamento)

        response = self.client.get(reverse('departamento_list'))

        registro = response.context['departamentos'][0]
        self.assertEqual(registro.total_responsaveis, 1)
        self.assertEqual(registro.total_projetos, 1)

    def test_excluir_apenas_desliga_os_ligados(self):
        departamento = Departamento.objects.create(nome='Ensino')
        self.responsavel.departamento = departamento
        self.responsavel.save(update_fields=['departamento'])
        url = reverse('departamento_delete', args=[departamento.pk])

        self.assertContains(self.client.get(url), 'ligado a 1 cadastro(s)')
        response = self.client.post(url)

        self.assertRedirects(response, reverse('departamento_list'))
        self.responsavel.refresh_from_db()
        self.assertIsNone(self.responsavel.departamento)
        self.assertTrue(Responsavel.objects.filter(pk=self.responsavel.pk).exists())


class ProjetoTests(BaseTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.projeto = Projeto.objects.create(nome='Reforma do laboratório')

    def test_criar(self):
        response = self.client.post(reverse('projeto_create'), {
            'nome': 'Semana Acadêmica',
            'descricao': 'Organizar a semana',
            'inicio': '2030-01-01',
            'fim': '2030-01-05',
        })
        self.assertRedirects(response, reverse('projeto_list'))
        self.assertEqual(Projeto.objects.get(nome='Semana Acadêmica').fim, date(2030, 1, 5))

    def test_formulario_recusa_fim_antes_do_inicio(self):
        form = ProjetoForm(data={'nome': 'X', 'inicio': '2030-01-10', 'fim': '2030-01-01'})
        self.assertFalse(form.is_valid())
        self.assertIn('O fim não pode ser antes do início.', form.non_field_errors())

    def test_banco_tambem_recusa_fim_antes_do_inicio(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Projeto.objects.create(nome='Y', inicio=date(2030, 1, 10), fim=date(2030, 1, 1))

    def test_detalhe_conta_e_lista_tarefas(self):
        self.criar_tarefa('Comprar bancadas', dias=2, projeto=self.projeto)
        self.criar_tarefa('Pintar', dias=-1, projeto=self.projeto)
        self.criar_tarefa('Fora do projeto', dias=3)

        response = self.client.get(reverse('projeto_detail', args=[self.projeto.pk]))

        self.assertEqual(response.context['pendentes'], 2)
        self.assertEqual(response.context['atrasadas'], 1)
        self.assertContains(response, 'Comprar bancadas')
        self.assertNotContains(response, 'Fora do projeto')

    def test_detalhe_soma_horas_do_projeto(self):
        tarefa = self.criar_tarefa('Comprar bancadas', projeto=self.projeto)
        RegistroTempo.objects.create(tarefa=tarefa, responsavel=self.responsavel, horas=Decimal('2.50'))
        RegistroTempo.objects.create(tarefa=tarefa, responsavel=self.responsavel, horas=Decimal('1.25'))

        response = self.client.get(reverse('projeto_detail', args=[self.projeto.pk]))

        self.assertEqual(response.context['horas'], Decimal('3.75'))

    def test_excluir_deixa_as_tarefas_sem_projeto(self):
        tarefa = self.criar_tarefa('Pintar', projeto=self.projeto)
        url = reverse('projeto_delete', args=[self.projeto.pk])

        self.assertContains(self.client.get(url), 'tem 1 tarefa(s)')
        response = self.client.post(url)

        self.assertRedirects(response, reverse('projeto_list'))
        tarefa.refresh_from_db()
        self.assertIsNone(tarefa.projeto)

    def test_encerrado(self):
        self.assertFalse(self.projeto.encerrado)
        self.projeto.fim = timezone.localdate() - timedelta(days=1)
        self.assertTrue(self.projeto.encerrado)


class CategoriaTests(BaseTestCase):
    def test_criar(self):
        response = self.client.post(reverse('categoria_create'), {'nome': 'Manutenção', 'cor': 'verde'})
        self.assertRedirects(response, reverse('categoria_list'))
        self.assertEqual(Categoria.objects.get(nome='Manutenção').cor, 'verde')

    def test_lista_conta_tarefas(self):
        categoria = Categoria.objects.create(nome='Ensino')
        self.criar_tarefa('Corrigir provas', categoria=categoria)
        response = self.client.get(reverse('categoria_list'))
        self.assertEqual(response.context['categorias'][0].total, 1)

    def test_excluir_deixa_as_tarefas_sem_categoria(self):
        categoria = Categoria.objects.create(nome='Ensino')
        tarefa = self.criar_tarefa('Corrigir provas', categoria=categoria)

        response = self.client.post(reverse('categoria_delete', args=[categoria.pk]))

        self.assertRedirects(response, reverse('categoria_list'))
        tarefa.refresh_from_db()
        self.assertIsNone(tarefa.categoria)


class EtiquetaTests(BaseTestCase):
    def test_criar(self):
        response = self.client.post(reverse('etiqueta_create'), {'nome': 'urgente'})
        self.assertRedirects(response, reverse('etiqueta_list'))
        self.assertTrue(Etiqueta.objects.filter(nome='urgente').exists())

    def test_tarefa_pode_ter_varias(self):
        urgente = Etiqueta.objects.create(nome='urgente')
        externo = Etiqueta.objects.create(nome='externo')
        tarefa = self.criar_tarefa()
        tarefa.etiquetas.set([urgente, externo])
        self.assertEqual(list(tarefa.etiquetas.all()), [externo, urgente])

    def test_excluir_so_tira_a_etiqueta_da_tarefa(self):
        etiqueta = Etiqueta.objects.create(nome='urgente')
        tarefa = self.criar_tarefa()
        tarefa.etiquetas.add(etiqueta)
        url = reverse('etiqueta_delete', args=[etiqueta.pk])

        self.assertContains(self.client.get(url), 'está em 1 tarefa(s)')
        self.client.post(url)

        self.assertTrue(Tarefa.objects.filter(pk=tarefa.pk).exists())
        self.assertEqual(tarefa.etiquetas.count(), 0)


class TarefaComRelacionamentosTests(BaseTestCase):
    def test_criar_com_projeto_categoria_e_etiquetas(self):
        projeto = Projeto.objects.create(nome='Reforma')
        categoria = Categoria.objects.create(nome='Manutenção')
        etiqueta = Etiqueta.objects.create(nome='urgente')

        self.client.post(reverse('tarefa_create'), {
            'titulo': 'Trocar lâmpadas',
            'prazo': '2030-01-01T10:00',
            'pessoa_responsavel': self.responsavel.pk,
            'projeto': projeto.pk,
            'categoria': categoria.pk,
            'etiquetas': [etiqueta.pk],
        })

        tarefa = Tarefa.objects.get(titulo='Trocar lâmpadas')
        self.assertEqual(tarefa.projeto, projeto)
        self.assertEqual(tarefa.categoria, categoria)
        self.assertEqual(list(tarefa.etiquetas.all()), [etiqueta])

    def test_lista_mostra_categoria_e_etiqueta(self):
        tarefa = self.criar_tarefa(categoria=Categoria.objects.create(nome='Manutenção'))
        tarefa.etiquetas.add(Etiqueta.objects.create(nome='urgente'))

        response = self.client.get(reverse('tarefa_list'))

        self.assertContains(response, 'Manutenção')
        self.assertContains(response, 'urgente')


class FiltroPorRelacionamentoTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.projeto = Projeto.objects.create(nome='Reforma')
        self.categoria = Categoria.objects.create(nome='Manutenção')
        self.etiqueta = Etiqueta.objects.create(nome='urgente')
        self.do_projeto = self.criar_tarefa('Trocar lâmpadas', projeto=self.projeto)
        self.da_categoria = self.criar_tarefa('Pintar parede', categoria=self.categoria)
        self.da_etiqueta = self.criar_tarefa('Consertar porta')
        self.da_etiqueta.etiquetas.add(self.etiqueta)
        self.criar_tarefa('Sem nada')

    def titulos(self, **params):
        response = self.client.get(reverse('tarefa_list'), params)
        return {t.titulo for t in response.context['tarefas']}

    def test_projeto(self):
        self.assertEqual(self.titulos(projeto=self.projeto.pk), {'Trocar lâmpadas'})

    def test_categoria(self):
        self.assertEqual(self.titulos(categoria=self.categoria.pk), {'Pintar parede'})

    def test_etiqueta(self):
        self.assertEqual(self.titulos(etiqueta=self.etiqueta.pk), {'Consertar porta'})

    def test_combinado_com_status(self):
        self.assertEqual(self.titulos(projeto=self.projeto.pk, status='concluidas'), set())


class SubtarefaTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.tarefa = self.criar_tarefa()

    def test_ordem_segue_a_ordem_de_criacao(self):
        primeira = Subtarefa.objects.create(tarefa=self.tarefa, descricao='Primeira')
        segunda = Subtarefa.objects.create(tarefa=self.tarefa, descricao='Segunda')
        self.assertEqual([primeira.ordem, segunda.ordem], [1, 2])
        self.assertEqual(list(self.tarefa.subtarefas.all()), [primeira, segunda])

    def test_progresso(self):
        self.assertIsNone(self.tarefa.progresso)
        Subtarefa.objects.create(tarefa=self.tarefa, descricao='A', concluida=True)
        Subtarefa.objects.create(tarefa=self.tarefa, descricao='B')
        Subtarefa.objects.create(tarefa=self.tarefa, descricao='C')
        self.assertEqual(Tarefa.objects.get(pk=self.tarefa.pk).progresso, 33)

    def test_marcar_e_desmarcar(self):
        subtarefa = Subtarefa.objects.create(tarefa=self.tarefa, descricao='A')
        url = reverse('subtarefa_toggle', args=[subtarefa.pk])

        response = self.client.post(url)

        self.assertRedirects(response, reverse('tarefa_detail', args=[self.tarefa.pk]))
        subtarefa.refresh_from_db()
        self.assertTrue(subtarefa.concluida)

        self.client.post(url)
        subtarefa.refresh_from_db()
        self.assertFalse(subtarefa.concluida)

    def test_marcar_exige_post(self):
        subtarefa = Subtarefa.objects.create(tarefa=self.tarefa, descricao='A')
        response = self.client.get(reverse('subtarefa_toggle', args=[subtarefa.pk]))
        self.assertEqual(response.status_code, 405)


class TarefaDetalheTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.tarefa = self.criar_tarefa('Trocar lâmpadas')
        self.url = reverse('tarefa_detail', args=[self.tarefa.pk])

    def test_mostra_os_itens_da_tarefa(self):
        Subtarefa.objects.create(tarefa=self.tarefa, descricao='Comprar lâmpada')
        Comentario.objects.create(tarefa=self.tarefa, autor=self.responsavel, texto='Já pedi a nota')
        RegistroTempo.objects.create(tarefa=self.tarefa, responsavel=self.responsavel, horas=Decimal('1.50'))

        response = self.client.get(self.url)

        self.assertContains(response, 'Comprar lâmpada')
        self.assertContains(response, 'Já pedi a nota')
        self.assertContains(response, '1,50 h')

    def test_adicionar_subtarefa(self):
        response = self.client.post(self.url, {'acao': 'subtarefa', 'descricao': 'Comprar lâmpada'}, follow=True)

        self.assertRedirects(response, self.url)
        self.assertContains(response, 'Subtarefa adicionada.')
        self.assertEqual(self.tarefa.subtarefas.get().descricao, 'Comprar lâmpada')

    def test_adicionar_comentario(self):
        self.client.post(self.url, {
            'acao': 'comentario', 'autor': self.responsavel.pk, 'texto': 'Já pedi a nota',
        })
        comentario = self.tarefa.comentarios.get()
        self.assertEqual(comentario.autor, self.responsavel)
        self.assertEqual(comentario.texto, 'Já pedi a nota')

    def test_comentario_sem_autor_fica_anonimo(self):
        self.client.post(self.url, {'acao': 'comentario', 'texto': 'Recado sem assinatura'})
        self.assertIsNone(self.tarefa.comentarios.get().autor)

    def test_adicionar_registro_de_tempo(self):
        self.client.post(self.url, {
            'acao': 'registro',
            'responsavel': self.responsavel.pk,
            'horas': '2.5',
            'data': '2026-09-20',
            'observacao': 'Troca feita',
        })
        registro = self.tarefa.registros_tempo.get()
        self.assertEqual(registro.horas, Decimal('2.50'))
        self.assertEqual(registro.data, date(2026, 9, 20))
        self.assertEqual(self.tarefa.horas_registradas, Decimal('2.50'))

    def test_registro_recusa_horas_pequenas(self):
        response = self.client.post(self.url, {
            'acao': 'registro', 'responsavel': self.responsavel.pk, 'horas': '0.1', 'data': '2026-09-20',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.tarefa.registros_tempo.exists())
        self.assertTrue(response.context['form_registro'].errors)

    def test_formulario_invalido_reaparece_com_o_erro(self):
        response = self.client.post(self.url, {'acao': 'subtarefa', 'descricao': ''})
        self.assertEqual(response.status_code, 200)
        self.assertIn('descricao', response.context['form_subtarefa'].errors)
        self.assertFalse(self.tarefa.subtarefas.exists())

    def test_acao_desconhecida(self):
        response = self.client.post(self.url, {'acao': 'nada-disso'})
        self.assertEqual(response.status_code, 404)

    def test_excluir_item(self):
        comentario = Comentario.objects.create(tarefa=self.tarefa, texto='Apagar isto')

        response = self.client.post(reverse('item_delete', args=['comentario', comentario.pk]))

        self.assertRedirects(response, self.url)
        self.assertFalse(Comentario.objects.exists())

    def test_excluir_item_de_tipo_desconhecido(self):
        response = self.client.post(reverse('item_delete', args=['inventado', 1]))
        self.assertEqual(response.status_code, 404)

    def test_excluir_item_exige_post(self):
        comentario = Comentario.objects.create(tarefa=self.tarefa, texto='Apagar isto')
        response = self.client.get(reverse('item_delete', args=['comentario', comentario.pk]))
        self.assertEqual(response.status_code, 405)

    def test_excluir_a_tarefa_leva_os_itens(self):
        Subtarefa.objects.create(tarefa=self.tarefa, descricao='A')
        Comentario.objects.create(tarefa=self.tarefa, texto='B')
        RegistroTempo.objects.create(tarefa=self.tarefa, responsavel=self.responsavel, horas=Decimal('1'))

        self.client.post(reverse('tarefa_delete', args=[self.tarefa.pk]))

        self.assertFalse(Subtarefa.objects.exists())
        self.assertFalse(Comentario.objects.exists())
        self.assertFalse(RegistroTempo.objects.exists())

    def test_confirmacao_avisa_o_que_vai_junto(self):
        Subtarefa.objects.create(tarefa=self.tarefa, descricao='A')
        response = self.client.get(reverse('tarefa_delete', args=[self.tarefa.pk]))
        self.assertContains(response, '1 subtarefa(s)')

    def test_detalhe_nao_faz_uma_consulta_por_item(self):
        for i in range(3):
            Subtarefa.objects.create(tarefa=self.tarefa, descricao=f'Passo {i}')
            Comentario.objects.create(tarefa=self.tarefa, autor=self.responsavel, texto=f'Nota {i}')
            RegistroTempo.objects.create(tarefa=self.tarefa, responsavel=self.responsavel, horas=Decimal('1'))
            registrar_atividade(self.tarefa, self.usuario, 'editou', 'título')

        # 12 de antes + 1 para o histórico (com o usuário de cada linha no mesmo SELECT)
        with self.assertNumQueries(13) as consultas:
            self.client.get(self.url)

        for i in range(3, 9):
            Subtarefa.objects.create(tarefa=self.tarefa, descricao=f'Passo {i}')
            Comentario.objects.create(tarefa=self.tarefa, autor=self.responsavel, texto=f'Nota {i}')
            RegistroTempo.objects.create(tarefa=self.tarefa, responsavel=self.responsavel, horas=Decimal('1'))
            registrar_atividade(self.tarefa, self.usuario, 'editou', 'título')

        with self.assertNumQueries(len(consultas)):
            self.client.get(self.url)


class AnexoTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.tarefa = self.criar_tarefa()
        self.url = reverse('tarefa_detail', args=[self.tarefa.pk])
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        media = override_settings(MEDIA_ROOT=pasta.name)
        media.enable()
        self.addCleanup(media.disable)

    def enviar(self, nome='nota.txt', conteudo=b'conteudo', descricao='Nota fiscal'):
        return self.client.post(self.url, {
            'acao': 'anexo',
            'arquivo': SimpleUploadedFile(nome, conteudo),
            'descricao': descricao,
        })

    def test_enviar(self):
        self.enviar()

        anexo = self.tarefa.anexos.get()
        self.assertEqual(anexo.nome_arquivo, 'nota.txt')
        self.assertEqual(anexo.descricao, 'Nota fiscal')
        self.assertTrue(os.path.exists(anexo.arquivo.path))

    def test_recusa_arquivo_grande(self):
        response = self.enviar(conteudo=b'x' * (10 * 1024 * 1024 + 1))
        self.assertEqual(response.status_code, 200)
        self.assertIn('arquivo', response.context['form_anexo'].errors)
        self.assertFalse(Anexo.objects.exists())

    def test_excluir_apaga_o_arquivo_do_disco(self):
        self.enviar()
        anexo = self.tarefa.anexos.get()
        caminho = anexo.arquivo.path

        self.client.post(reverse('item_delete', args=['anexo', anexo.pk]))

        self.assertFalse(Anexo.objects.exists())
        self.assertFalse(os.path.exists(caminho))

    def test_excluir_a_tarefa_tambem_apaga_o_arquivo(self):
        self.enviar()
        caminho = self.tarefa.anexos.get().arquivo.path

        self.client.post(reverse('tarefa_delete', args=[self.tarefa.pk]))

        self.assertFalse(os.path.exists(caminho))


class RegistroTempoProtegidoTests(BaseTestCase):
    def test_nao_excluir_responsavel_com_horas_registradas(self):
        outro = Responsavel.objects.create(nome='Bia', cpf='111.444.777-35')
        tarefa = self.criar_tarefa()
        RegistroTempo.objects.create(tarefa=tarefa, responsavel=outro, horas=Decimal('1'))
        url = reverse('responsavel_delete', args=[outro.pk])

        self.assertContains(self.client.get(url), 'Não é possível excluir')
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Responsavel.objects.filter(pk=outro.pk).exists())

    def test_detalhe_do_responsavel_soma_as_horas(self):
        tarefa = self.criar_tarefa()
        RegistroTempo.objects.create(tarefa=tarefa, responsavel=self.responsavel, horas=Decimal('1.25'))
        RegistroTempo.objects.create(tarefa=tarefa, responsavel=self.responsavel, horas=Decimal('0.75'))

        response = self.client.get(reverse('responsavel_detail', args=[self.responsavel.pk]))

        self.assertEqual(response.context['horas'], Decimal('2.00'))


class PainelDosNovosModelosTests(BaseTestCase):
    def test_agrupa_pendentes_por_projeto_e_categoria(self):
        projeto = Projeto.objects.create(nome='Reforma')
        categoria = Categoria.objects.create(nome='Manutenção')
        self.criar_tarefa('Atrasada', dias=-1, projeto=projeto, categoria=categoria)
        self.criar_tarefa('Pendente', dias=2, projeto=projeto)
        self.criar_tarefa('Feita', dias=-3, projeto=projeto, concluida_em=timezone.now())

        response = self.client.get(reverse('painel'))

        projetos = list(response.context['projetos'])
        self.assertEqual(projetos, [projeto])
        self.assertEqual((projetos[0].pendentes, projetos[0].atrasadas), (2, 1))
        categorias = list(response.context['categorias'])
        self.assertEqual(categorias, [categoria])
        self.assertEqual(categorias[0].pendentes, 1)

    def test_projeto_e_categoria_sem_pendencias_nao_aparecem(self):
        projeto = Projeto.objects.create(nome='Reforma')
        categoria = Categoria.objects.create(nome='Manutenção')
        self.criar_tarefa('Feita', dias=-3, projeto=projeto, categoria=categoria, concluida_em=timezone.now())

        response = self.client.get(reverse('painel'))

        self.assertEqual(list(response.context['projetos']), [])
        self.assertEqual(list(response.context['categorias']), [])


class FixtureDeExemploTests(TestCase):
    def test_loaddata_funciona_e_cobre_os_modelos(self):
        call_command('loaddata', 'exemplos', verbosity=0)

        for modelo in (
            Departamento, Responsavel, Projeto, Categoria, Etiqueta,
            Tarefa, Subtarefa, Comentario, RegistroTempo, Atividade,
        ):
            with self.subTest(modelo=modelo.__name__):
                self.assertTrue(modelo.objects.exists())
        # Anexo fica fora da fixture: dependeria de arquivos de verdade em MEDIA_ROOT
        self.assertFalse(Anexo.objects.exists())


class WidgetsDeDataTests(TestCase):
    # O <input type="date"> e o <input type="datetime-local"> só aceitam o formato
    # ISO; se o valor sair como 23/09/2026 o campo aparece vazio no navegador.
    def test_prazo_sai_em_iso_no_formulario_de_editar(self):
        responsavel = Responsavel.objects.create(nome='Ana', cpf=CPF_VALIDO)
        tarefa = Tarefa.objects.create(
            titulo='Trocar lâmpadas',
            prazo=timezone.make_aware(datetime(2026, 9, 24, 13, 45)),
            pessoa_responsavel=responsavel,
        )
        html = TarefaForm(instance=tarefa).as_p()
        self.assertIn('value="2026-09-24T13:45"', html)

    def test_data_do_registro_sai_em_iso(self):
        html = RegistroTempoForm(initial={'data': date(2026, 9, 24)}).as_p()
        self.assertIn('value="2026-09-24"', html)

    def test_datas_do_projeto_saem_em_iso(self):
        projeto = Projeto.objects.create(nome='Reforma', inicio=date(2026, 9, 1), fim=date(2026, 12, 20))
        html = ProjetoForm(instance=projeto).as_p()
        self.assertIn('value="2026-09-01"', html)
        self.assertIn('value="2026-12-20"', html)


class TodasAsPaginasAbremTests(TestCase):
    # Passeia por todas as telas com os dados de exemplo carregados. Não confere
    # conteúdo: serve para pegar template quebrado, url errada e erro de contexto.
    fixtures = ['exemplos']

    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user('ana', password='senha-forte-123')

    def setUp(self):
        self.client.force_login(self.usuario)

    def test_abre_todas(self):
        tarefa = Tarefa.objects.first()
        subtarefa = Subtarefa.objects.first()
        urls = [
            reverse('painel'),
            reverse('tarefa_list'),
            reverse('tarefa_create'),
            reverse('tarefa_detail', args=[tarefa.pk]),
            reverse('tarefa_update', args=[tarefa.pk]),
            reverse('tarefa_delete', args=[tarefa.pk]),
            reverse('responsavel_list'),
            reverse('responsavel_create'),
            reverse('responsavel_detail', args=[Responsavel.objects.first().pk]),
            reverse('responsavel_update', args=[Responsavel.objects.first().pk]),
            reverse('responsavel_delete', args=[Responsavel.objects.first().pk]),
            reverse('departamento_list'),
            reverse('departamento_create'),
            reverse('departamento_update', args=[Departamento.objects.first().pk]),
            reverse('departamento_delete', args=[Departamento.objects.first().pk]),
            reverse('projeto_list'),
            reverse('projeto_create'),
            reverse('projeto_detail', args=[Projeto.objects.first().pk]),
            reverse('projeto_update', args=[Projeto.objects.first().pk]),
            reverse('projeto_delete', args=[Projeto.objects.first().pk]),
            reverse('categoria_list'),
            reverse('categoria_create'),
            reverse('categoria_update', args=[Categoria.objects.first().pk]),
            reverse('categoria_delete', args=[Categoria.objects.first().pk]),
            reverse('etiqueta_list'),
            reverse('etiqueta_create'),
            reverse('etiqueta_update', args=[Etiqueta.objects.first().pk]),
            reverse('etiqueta_delete', args=[Etiqueta.objects.first().pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        # A lista com cada filtro preenchido
        for parametro, valor in [
            ('q', 'relatório'),
            ('status', 'atrasadas'),
            ('responsavel', Responsavel.objects.first().pk),
            ('projeto', Projeto.objects.first().pk),
            ('categoria', Categoria.objects.first().pk),
            ('etiqueta', Etiqueta.objects.first().pk),
        ]:
            with self.subTest(filtro=parametro):
                response = self.client.get(reverse('tarefa_list'), {parametro: valor})
                self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(subtarefa)


# Prioridade, situação "em andamento", quadro, calendário, histórico e adição rápida

class PrioridadeTests(BaseTestCase):
    def test_tarefa_nova_comeca_com_prioridade_media(self):
        self.assertEqual(self.criar_tarefa().prioridade, 'media')

    def test_criar_com_prioridade(self):
        self.client.post(reverse('tarefa_create'), {
            'titulo': 'Urgente',
            'prazo': '2030-01-01T10:00',
            'prioridade': 'alta',
            'pessoa_responsavel': self.responsavel.pk,
        })
        self.assertEqual(Tarefa.objects.get(titulo='Urgente').prioridade, 'alta')

    def test_editar_sem_mandar_prioridade_mantem_a_atual(self):
        tarefa = self.criar_tarefa(prioridade='baixa')
        self.client.post(reverse('tarefa_update', args=[tarefa.pk]), {
            'titulo': 'Editada',
            'prazo': '2030-01-01T10:00',
            'pessoa_responsavel': self.responsavel.pk,
        })
        tarefa.refresh_from_db()
        self.assertEqual((tarefa.titulo, tarefa.prioridade), ('Editada', 'baixa'))

    def titulos(self, **params):
        response = self.client.get(reverse('tarefa_list'), params)
        return [t.titulo for t in response.context['tarefas']]

    def test_filtro_por_prioridade(self):
        self.criar_tarefa('Alta', prioridade='alta')
        self.criar_tarefa('Baixa', prioridade='baixa')
        self.assertEqual(self.titulos(prioridade='alta'), ['Alta'])

    def test_ordenar_por_prioridade_mantem_concluidas_no_fim(self):
        self.criar_tarefa('media cedo', dias=1)
        self.criar_tarefa('baixa', dias=2, prioridade='baixa')
        self.criar_tarefa('alta tarde', dias=9, prioridade='alta')
        self.criar_tarefa('alta feita', dias=-1, prioridade='alta', concluida_em=timezone.now())

        self.assertEqual(self.titulos(ordenar='prioridade'), ['alta tarde', 'media cedo', 'baixa', 'alta feita'])
        self.assertEqual(self.titulos(), ['media cedo', 'baixa', 'alta tarde', 'alta feita'])

    def test_lista_mostra_a_prioridade(self):
        self.criar_tarefa(prioridade='alta')
        response = self.client.get(reverse('tarefa_list'))
        self.assertContains(response, 'prioridade-texto-alta')


class SituacaoTests(BaseTestCase):
    def test_situacao_e_helpers_do_queryset(self):
        a_fazer = self.criar_tarefa('a fazer')
        andamento = self.criar_tarefa('andamento', iniciada_em=timezone.now())
        feita = self.criar_tarefa('feita', iniciada_em=timezone.now(), concluida_em=timezone.now())

        self.assertEqual(
            [a_fazer.situacao, andamento.situacao, feita.situacao], ['a_fazer', 'em_andamento', 'concluida'],
        )
        self.assertEqual(list(Tarefa.objects.a_fazer()), [a_fazer])
        self.assertEqual(list(Tarefa.objects.em_andamento()), [andamento])
        self.assertEqual(list(Tarefa.objects.concluidas()), [feita])

    def test_mudar_situacao(self):
        tarefa = self.criar_tarefa()
        self.assertEqual(tarefa.mudar_situacao('em_andamento'), 'iniciou')
        inicio = tarefa.iniciada_em
        self.assertIsNotNone(inicio)
        self.assertIsNone(tarefa.mudar_situacao('em_andamento'))
        self.assertEqual(tarefa.mudar_situacao('concluida'), 'concluiu')
        self.assertEqual(tarefa.mudar_situacao('em_andamento'), 'reabriu')
        self.assertEqual(tarefa.iniciada_em, inicio)  # reabrir não reinicia a contagem
        self.assertEqual(tarefa.mudar_situacao('a_fazer'), 'voltou')
        self.assertIsNone(tarefa.iniciada_em)
        tarefa.mudar_situacao('concluida')
        self.assertEqual(tarefa.mudar_situacao('a_fazer'), 'reabriu')

    def test_situacao_desconhecida(self):
        with self.assertRaises(ValueError):
            self.criar_tarefa().mudar_situacao('arquivada')

    def test_filtros_de_situacao(self):
        self.criar_tarefa('a fazer')
        self.criar_tarefa('andamento', iniciada_em=timezone.now())
        response = self.client.get(reverse('tarefa_list'), {'status': 'em_andamento'})
        self.assertEqual([t.titulo for t in response.context['tarefas']], ['andamento'])
        response = self.client.get(reverse('tarefa_list'), {'status': 'a_fazer'})
        self.assertEqual([t.titulo for t in response.context['tarefas']], ['a fazer'])
        self.assertEqual(response.context['em_andamento'], 1)

    def test_reabrir_volta_para_em_andamento_se_ja_tinha_comecado(self):
        tarefa = self.criar_tarefa(iniciada_em=timezone.now(), concluida_em=timezone.now())
        self.client.post(reverse('tarefa_toggle', args=[tarefa.pk]))
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.situacao, 'em_andamento')


class MoverTarefaTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.tarefa = self.criar_tarefa()
        self.url = reverse('tarefa_mover', args=[self.tarefa.pk])

    def test_exige_post_e_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.logout()
        response = self.client.post(self.url, {'situacao': 'concluida'})
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False)

    def test_pedido_do_quadro_recebe_json(self):
        response = self.client.post(
            self.url, {'situacao': 'em_andamento'}, headers={'Accept': 'application/json'},
        )
        self.assertEqual(response.json(), {'ok': True, 'situacao': 'em_andamento', 'rotulo': 'Em andamento'})
        self.tarefa.refresh_from_db()
        self.assertEqual(self.tarefa.situacao, 'em_andamento')
        atividade = self.tarefa.atividades.get()
        self.assertEqual((atividade.acao, atividade.usuario), ('iniciou', self.usuario))

    def test_formulario_sem_javascript_volta_para_a_pagina(self):
        response = self.client.post(self.url, {'situacao': 'concluida'})
        self.assertRedirects(response, reverse('quadro'))
        destino = reverse('quadro') + '?prioridade=alta'
        response = self.client.post(self.url, {'situacao': 'a_fazer', 'next': destino})
        self.assertRedirects(response, destino)
        response = self.client.post(self.url, {'situacao': 'a_fazer', 'next': 'https://exemplo.com/'})
        self.assertRedirects(response, reverse('quadro'))

    def test_situacao_invalida(self):
        self.assertEqual(self.client.post(self.url, {'situacao': 'xyz'}).status_code, 400)

    def test_mesma_situacao_nao_vai_para_o_historico(self):
        self.client.post(self.url, {'situacao': 'a_fazer'})
        self.assertFalse(self.tarefa.atividades.exists())


class HistoricoTests(BaseTestCase):
    def acoes(self, tarefa):
        return [(a.acao, a.detalhe) for a in tarefa.atividades.order_by('pk')]

    def test_criar_e_editar(self):
        self.client.post(reverse('tarefa_create'), {
            'titulo': 'Nova', 'prazo': '2030-01-01T10:00', 'pessoa_responsavel': self.responsavel.pk,
        })
        tarefa = Tarefa.objects.get(titulo='Nova')
        dados = {'titulo': 'Outra', 'prazo': '2030-01-01T10:00', 'pessoa_responsavel': self.responsavel.pk}
        self.client.post(reverse('tarefa_update', args=[tarefa.pk]), dados)
        # Salvar sem mudar nada não suja o histórico
        self.client.post(reverse('tarefa_update', args=[tarefa.pk]), dados)

        self.assertEqual(self.acoes(tarefa), [('criou', ''), ('editou', 'título')])
        self.assertEqual(tarefa.atividades.first().usuario, self.usuario)

    def test_concluir_e_reabrir(self):
        tarefa = self.criar_tarefa()
        url = reverse('tarefa_toggle', args=[tarefa.pk])
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(self.acoes(tarefa), [('concluiu', ''), ('reabriu', '')])

    def test_itens_da_tarefa(self):
        tarefa = self.criar_tarefa()
        url = reverse('tarefa_detail', args=[tarefa.pk])
        self.client.post(url, {'acao': 'subtarefa', 'descricao': 'Ligar'})
        subtarefa = tarefa.subtarefas.get()
        self.client.post(reverse('subtarefa_toggle', args=[subtarefa.pk]))
        self.client.post(url, {
            'acao': 'registro', 'responsavel': self.responsavel.pk, 'horas': '1.5', 'data': '2030-01-01',
        })
        self.client.post(reverse('item_delete', args=['subtarefa', subtarefa.pk]))

        self.assertEqual(self.acoes(tarefa), [
            ('adicionou', 'a subtarefa “Ligar”'),
            ('marcou', '“Ligar” no checklist'),
            ('adicionou', '1,50 h de trabalho de Ana'),
            ('removeu', 'a subtarefa “Ligar”'),
        ])

    def test_aparece_na_tela_da_tarefa(self):
        tarefa = self.criar_tarefa()
        registrar_atividade(tarefa, self.usuario, 'editou', 'título, prazo')
        response = self.client.get(reverse('tarefa_detail', args=[tarefa.pk]))
        self.assertContains(response, 'Editou: título, prazo')
        self.assertContains(response, 'ana ·')

    def test_usuario_excluido_vira_alguem(self):
        tarefa = self.criar_tarefa()
        outro = User.objects.create_user('beto')
        registrar_atividade(tarefa, outro, 'concluiu')
        outro.delete()
        atividade = Atividade.objects.get()
        self.assertIsNone(atividade.usuario)
        self.assertContains(self.client.get(reverse('tarefa_detail', args=[tarefa.pk])), 'Alguém ·')


class QuadroTests(BaseTestCase):
    def colunas(self, **params):
        response = self.client.get(reverse('quadro'), params)
        return {c['situacao']: [t.titulo for t in c['tarefas']] for c in response.context['colunas']}

    def test_separa_por_situacao_e_ordena_por_prioridade(self):
        agora = timezone.now()
        self.criar_tarefa('media', dias=1)
        self.criar_tarefa('alta', dias=5, prioridade='alta')
        self.criar_tarefa('andamento', iniciada_em=agora)
        self.criar_tarefa('feita ontem', concluida_em=agora - timedelta(days=1))
        self.criar_tarefa('feita hoje', concluida_em=agora)
        self.criar_tarefa('feita faz tempo', concluida_em=agora - timedelta(days=40))

        self.assertEqual(self.colunas(), {
            'a_fazer': ['alta', 'media'],
            'em_andamento': ['andamento'],
            'concluida': ['feita hoje', 'feita ontem'],
        })

    def test_filtros(self):
        outro = Responsavel.objects.create(nome='Bia', cpf='111.444.777-35')
        self.criar_tarefa('da Ana')
        Tarefa.objects.create(titulo='da Bia', prazo=timezone.now(), pessoa_responsavel=outro)
        self.assertEqual(self.colunas(responsavel=outro.pk)['a_fazer'], ['da Bia'])

    def test_setas_apontam_para_as_colunas_vizinhas(self):
        response = self.client.get(reverse('quadro'))
        vizinhas = [(c['anterior'], c['proxima']) for c in response.context['colunas']]
        self.assertEqual(vizinhas, [('', 'em_andamento'), ('a_fazer', 'concluida'), ('em_andamento', '')])

    def test_consultas_nao_crescem_com_tarefas(self):
        self.criar_tarefa()
        # sessão, usuário, as 3 opções de filtro usadas na tela e as tarefas com os prefetch de etiquetas e subtarefas
        with self.assertNumQueries(8) as consultas:
            self.client.get(reverse('quadro'))
        for dias in range(8):
            self.criar_tarefa(dias=dias, iniciada_em=timezone.now() if dias % 2 else None)
        with self.assertNumQueries(len(consultas)):
            self.client.get(reverse('quadro'))


class CalendarioTests(BaseTestCase):
    def tarefa_em(self, titulo, ano, mes, dia, hora=10):
        return Tarefa.objects.create(
            titulo=titulo,
            prazo=timezone.make_aware(datetime(ano, mes, dia, hora)),
            pessoa_responsavel=self.responsavel,
        )

    def test_tarefa_aparece_no_dia_do_prazo(self):
        self.tarefa_em('Reunião', 2030, 3, 15)
        response = self.client.get(reverse('calendario'), {'mes': '2030-03'})

        dias = {dia['data']: dia for semana in response.context['semanas'] for dia in semana}
        self.assertEqual([t.titulo for t in dias[date(2030, 3, 15)]['tarefas']], ['Reunião'])
        self.assertEqual([d['data'] for d in response.context['agenda']], [date(2030, 3, 15)])
        self.assertContains(response, 'Março de 2030')

    def test_hora_local_decide_o_dia(self):
        # 23h30 em Cuiabá já é o dia seguinte em UTC; o calendário segue a hora local
        self.tarefa_em('Tarde da noite', 2030, 3, 15, hora=23)
        response = self.client.get(reverse('calendario'), {'mes': '2030-03'})
        self.assertEqual(response.context['agenda'][0]['data'], date(2030, 3, 15))

    def test_semanas_completas_comecando_no_domingo(self):
        response = self.client.get(reverse('calendario'), {'mes': '2030-03'})
        semanas = response.context['semanas']
        self.assertEqual(semanas[0][0]['data'].weekday(), 6)
        self.assertTrue(all(len(semana) == 7 for semana in semanas))
        self.assertTrue(semanas[0][0]['fora'])  # 24/02, do mês anterior

    def test_navegacao_entre_meses(self):
        response = self.client.get(reverse('calendario'), {'mes': '2030-01'})
        self.assertEqual((response.context['mes_anterior'], response.context['mes_proximo']), ('2029-12', '2030-02'))

    def test_mes_invalido_mostra_o_mes_atual(self):
        for valor in ('2030-13', 'abc', ''):
            with self.subTest(mes=valor):
                response = self.client.get(reverse('calendario'), {'mes': valor})
                self.assertEqual(response.context['mes'], timezone.localdate().replace(day=1))

    def test_consultas_nao_crescem_com_tarefas(self):
        self.tarefa_em('Uma', 2030, 3, 1)
        # sessão, usuário, as 3 opções de filtro usadas na tela e as tarefas do mês
        with self.assertNumQueries(6) as consultas:
            self.client.get(reverse('calendario'), {'mes': '2030-03'})
        for dia in range(2, 20):
            self.tarefa_em(f'Tarefa {dia}', 2030, 3, dia)
        with self.assertNumQueries(len(consultas)):
            self.client.get(reverse('calendario'), {'mes': '2030-03'})


class TarefaRapidaFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = Responsavel.objects.create(nome='Ana Souza', cpf=CPF_VALIDO)
        cls.joao = Responsavel.objects.create(nome='João Pedro', cpf='111.444.777-35')
        cls.joana = Responsavel.objects.create(nome='Joana Lima', cpf='390.533.447-05')
        cls.urgente = Etiqueta.objects.create(nome='urgente')

    def form(self, texto, **dados):
        return TarefaRapidaForm({'texto': texto, **dados})

    def test_so_o_titulo_usa_o_responsavel_da_lista_e_amanha_as_17h(self):
        form = self.form('Comprar toner', pessoa_responsavel=self.ana.pk)
        self.assertTrue(form.is_valid(), form.errors)
        tarefa = form.save()
        prazo = timezone.localtime(tarefa.prazo)
        self.assertEqual(tarefa.titulo, 'Comprar toner')
        self.assertEqual(tarefa.pessoa_responsavel, self.ana)
        self.assertEqual(tarefa.prioridade, 'media')
        self.assertEqual((prazo.date(), prazo.hour, prazo.minute), (timezone.localdate() + timedelta(days=1), 17, 0))

    def test_pedacos_especiais_saem_do_titulo(self):
        form = self.form('Ligar para o fornecedor @ana #Urgente !alta amanhã 14h30')
        self.assertTrue(form.is_valid(), form.errors)
        tarefa = form.save()
        prazo = timezone.localtime(tarefa.prazo)
        self.assertEqual(tarefa.titulo, 'Ligar para o fornecedor')
        self.assertEqual(tarefa.pessoa_responsavel, self.ana)
        self.assertEqual(tarefa.prioridade, 'alta')
        self.assertEqual(list(tarefa.etiquetas.all()), [self.urgente])
        self.assertEqual((prazo.date(), prazo.hour, prazo.minute), (timezone.localdate() + timedelta(days=1), 14, 30))

    def test_nome_sem_acento_e_por_sobrenome(self):
        for texto, esperado in (('Teste @joao', self.joao), ('Teste @lima', self.joana)):
            with self.subTest(texto=texto):
                form = self.form(texto)
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data['responsavel'], esperado)

    def test_data_com_e_sem_ano(self):
        form = self.form('Prova @ana 10/12/2031 8:00')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(timezone.localtime(form.cleaned_data['prazo']).replace(tzinfo=None), datetime(2031, 12, 10, 8, 0))

        ontem = timezone.localdate() - timedelta(days=1)
        form = self.form(f'Prova @ana {ontem:%d/%m}')
        self.assertTrue(form.is_valid(), form.errors)
        if ontem.year == timezone.localdate().year:
            # Sem ano, um dia que já passou é o do ano que vem
            self.assertEqual(timezone.localtime(form.cleaned_data['prazo']).year, ontem.year + 1)

    def test_prazo_do_campo_quando_o_texto_nao_tem_dia(self):
        form = self.form('Prova @ana', prazo='2031-05-04T09:15')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(timezone.localtime(form.cleaned_data['prazo']).replace(tzinfo=None), datetime(2031, 5, 4, 9, 15))

    def assertErro(self, texto, trecho, **dados):
        form = self.form(texto, **dados)
        self.assertFalse(form.is_valid())
        self.assertIn(trecho, ' '.join(e for erros in form.errors.values() for e in erros))

    def test_erros(self):
        self.assertErro('Teste @jo', 'Mais de um responsável combina com @jo')
        self.assertErro('Teste @zé', 'Nenhum responsável combina com @zé')
        self.assertErro('Teste @ana #inexistente', 'A etiqueta #inexistente não existe')
        self.assertErro('Teste', 'Escolha o responsável')
        self.assertErro('@ana amanhã', 'Escreva o que precisa ser feito')
        self.assertErro('Teste @ana 31/02', 'Data inválida')
        self.assertErro('Teste @ana 25h', 'Hora inválida')
        self.assertErro('x' * 101 + ' @ana', 'passa de 100 caracteres')


class TarefaRapidaViewTests(BaseTestCase):
    url = reverse_lazy('tarefa_rapida')

    def test_get_devolve_o_formulario(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-form-rapida')
        self.assertNotContains(response, '<html')

    def test_cria_e_responde_json(self):
        response = self.client.post(
            self.url, {'texto': 'Comprar toner @ana !alta'}, headers={'Accept': 'application/json'},
        )
        dados = response.json()
        tarefa = Tarefa.objects.get(titulo='Comprar toner')
        self.assertTrue(dados['ok'])
        self.assertEqual(dados['url'], tarefa.get_absolute_url())
        self.assertEqual(tarefa.prioridade, 'alta')
        atividade = tarefa.atividades.get()
        self.assertEqual((atividade.acao, atividade.detalhe, atividade.usuario), ('criou', 'pela adição rápida', self.usuario))

    def test_erro_em_json(self):
        response = self.client.post(self.url, {'texto': 'Sem dono'}, headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'ok': False, 'erros': ['Escolha o responsável ou escreva @nome no texto.']})
        self.assertFalse(Tarefa.objects.exists())

    def test_sem_javascript_volta_para_a_pagina_com_mensagem(self):
        destino = reverse('quadro')
        response = self.client.post(self.url, {'texto': 'Comprar toner @ana', 'next': destino}, follow=True)
        self.assertRedirects(response, destino)
        self.assertContains(response, 'Tarefa &quot;Comprar toner&quot; criada para Ana')

    def test_exige_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False)


class TelasNovasTests(TestCase):
    fixtures = ['exemplos']

    def test_exigem_login(self):
        for nome in ('quadro', 'calendario', 'tarefa_rapida'):
            with self.subTest(url=nome):
                url = reverse(nome)
                self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_abrem_com_os_dados_de_exemplo(self):
        self.client.force_login(User.objects.create_user('ana', password='senha-forte-123'))
        for url in (reverse('quadro'), reverse('calendario'), reverse('calendario') + '?mes=2026-09',
                    reverse('tarefa_rapida'), reverse('tarefa_list') + '?ordenar=prioridade&status=em_andamento'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
