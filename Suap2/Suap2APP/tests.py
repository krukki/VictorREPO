from datetime import timedelta

from django.contrib.auth.models import User
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
        # sessão, usuário e a lista de tarefas com o responsável
        with self.assertNumQueries(3):
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
