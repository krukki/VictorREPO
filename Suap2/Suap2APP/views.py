import calendar
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, Prefetch, ProtectedError, Q, Sum
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, get_object_or_404, render
from django.template.defaultfilters import floatformat
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView

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
from .forms import (
    AnexoForm,
    CategoriaForm,
    ComentarioForm,
    DepartamentoForm,
    EtiquetaForm,
    ProjetoForm,
    RegistroTempoForm,
    ResponsavelForm,
    SubtarefaForm,
    TarefaFiltroForm,
    TarefaForm,
    TarefaRapidaForm,
)


# Modo visitante: uma marca na sessão, sem usuário nem tabela nova. O visitante pode abrir
# as telas de consulta (as que usam LeituraMixin), só com GET. Qualquer alteração continua
# exigindo login, e quem tenta cai na tela de entrar, que explica o motivo.

SESSAO_VISITANTE = 'modo_visitante'


def e_visitante(request):
    return not request.user.is_authenticated and request.session.get(SESSAO_VISITANTE, False)


class LeituraMixin(LoginRequiredMixin):
    """Exige login, menos para o visitante que só está olhando (GET/HEAD)."""

    def dispatch(self, request, *args, **kwargs):
        if request.method in ('GET', 'HEAD') and e_visitante(request):
            # Pula a checagem do LoginRequiredMixin e segue direto para a view
            return super(LoginRequiredMixin, self).dispatch(request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)


@require_POST
def entrar_como_visitante(request):
    if request.user.is_authenticated:
        return redirect('painel')
    request.session[SESSAO_VISITANTE] = True
    messages.info(request, 'Você entrou como visitante: pode ver tudo, mas não alterar nada.')
    return redirect('painel')


class CadastroView(CreateView):
    """Criar conta. Usa o User do próprio Django: nenhum modelo do sistema muda."""
    form_class = UserCreationForm
    template_name = 'Suap2APP/cadastro.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('painel')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        usuario = form.save()
        self.request.session.pop(SESSAO_VISITANTE, None)
        login(self.request, usuario)
        messages.success(self.request, f'Conta criada. Boas-vindas, {usuario.get_username()}!')
        return redirect(settings.LOGIN_REDIRECT_URL)


class FormularioMixin(LoginRequiredMixin, SuccessMessageMixin):
    """Configuração comum das telas de criar/editar, que usam o mesmo template."""
    template_name = 'Suap2APP/form.html'
    titulo_pagina = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo_pagina'] = self.titulo_pagina
        context['cancelar_url'] = self.success_url
        return context


class ExclusaoMixin(LoginRequiredMixin, SuccessMessageMixin):
    """Telas de excluir dos cadastros auxiliares, que usam o mesmo template."""
    template_name = 'Suap2APP/confirm_delete.html'
    titulo_pagina = ''
    mensagem_exclusao = '"%s" excluído.'
    aviso_relacionados = ''

    def contar_relacionados(self):
        """Quantos registros perdem a referência (todos são SET_NULL, nada é apagado)."""
        return 0

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo_pagina'] = self.titulo_pagina
        context['cancelar_url'] = self.success_url
        total = self.contar_relacionados()
        if total and self.aviso_relacionados:
            context['aviso'] = self.aviso_relacionados.format(n=total)
        return context

    def get_success_message(self, cleaned_data):
        return self.mensagem_exclusao % self.object


class PainelView(LeituraMixin, TemplateView):
    """Resumo das tarefas; as condições seguem as de TarefaFiltroForm.filtrar."""
    template_name = 'Suap2APP/painel.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        agora = timezone.now()
        semana = timedelta(days=7)
        pendente = Q(concluida_em__isnull=True)
        context.update(Tarefa.objects.aggregate(
            pendentes=Count('pk', filter=pendente),
            em_andamento=Count('pk', filter=pendente & Q(iniciada_em__isnull=False)),
            atrasadas=Count('pk', filter=pendente & Q(prazo__lt=agora)),
            concluidas=Count('pk', filter=Q(concluida_em__isnull=False)),
            vencem_na_semana=Count('pk', filter=pendente & Q(prazo__gte=agora, prazo__lt=agora + semana)),
            concluidas_na_semana=Count('pk', filter=Q(concluida_em__gte=agora - semana)),
        ))
        pendente_do_responsavel = Q(tarefa__concluida_em__isnull=True)
        context['responsaveis'] = Responsavel.objects.annotate(
            pendentes=Count('tarefa', filter=pendente_do_responsavel),
            atrasadas=Count('tarefa', filter=pendente_do_responsavel & Q(tarefa__prazo__lt=agora)),
        ).filter(pendentes__gt=0).order_by('-atrasadas', '-pendentes', 'nome')
        # Categorias e projetos usam o related_name 'tarefas'
        pendente_da_tarefa = Q(tarefas__concluida_em__isnull=True)
        context['categorias'] = Categoria.objects.annotate(
            pendentes=Count('tarefas', filter=pendente_da_tarefa),
        ).filter(pendentes__gt=0).order_by('-pendentes', 'nome')
        context['projetos'] = Projeto.objects.annotate(
            pendentes=Count('tarefas', filter=pendente_da_tarefa),
            atrasadas=Count('tarefas', filter=pendente_da_tarefa & Q(tarefas__prazo__lt=agora)),
        ).filter(pendentes__gt=0).order_by('-atrasadas', '-pendentes', 'nome')
        context['proximas'] = (
            Tarefa.objects.filter(concluida_em__isnull=True).com_relacionados().order_by('prazo')[:5]
        )
        context['now'] = agora
        return context


def contar_por_situacao(tarefas, agora):
    pendente = Q(concluida_em__isnull=True)
    return tarefas.aggregate(
        pendentes=Count('pk', filter=pendente),
        em_andamento=Count('pk', filter=pendente & Q(iniciada_em__isnull=False)),
        atrasadas=Count('pk', filter=pendente & Q(prazo__lt=agora)),
        concluidas=Count('pk', filter=Q(concluida_em__isnull=False)),
    )


# Tarefas

class TarefaListView(LeituraMixin, ListView):
    model = Tarefa
    context_object_name = 'tarefas'
    paginate_by = 10

    def get_queryset(self):
        self.agora = timezone.now()
        self.filtro = TarefaFiltroForm(self.request.GET)
        tarefas = self.filtro.filtrar(Tarefa.objects.com_relacionados(), self.agora)
        return self.filtro.aplicar_ordem(tarefas)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['now'] = self.agora
        context['filtro'] = self.filtro
        context['filtrando'] = any(self.request.GET.get(campo) for campo in self.filtro.fields)
        # Os contadores respeitam busca e responsável, mas não a situação: cada um vira uma aba
        sem_status = self.filtro.filtrar(Tarefa.objects.all(), self.agora, com_status=False)
        context.update(contar_por_situacao(sem_status, self.agora))
        context['total'] = context['pendentes'] + context['concluidas']
        context['status_atual'] = self.filtro.cleaned_data.get('status', '')
        return context


class TarefaDetailView(LeituraMixin, DetailView):
    """Tarefa com seus itens: subtarefas, comentários, anexos e horas.

    Os quatro formulários de adicionar moram nesta mesma página e são postados aqui,
    escolhidos pelo campo escondido `acao`, para que os erros apareçam junto do campo.
    """
    model = Tarefa
    FORMULARIOS = {
        'subtarefa': (SubtarefaForm, 'Subtarefa adicionada.'),
        'comentario': (ComentarioForm, 'Comentário adicionado.'),
        'anexo': (AnexoForm, 'Anexo enviado.'),
        'registro': (RegistroTempoForm, 'Tempo registrado.'),
    }

    def get_queryset(self):
        return Tarefa.objects.com_relacionados().prefetch_related(
            'comentarios__autor', 'anexos', 'registros_tempo__responsavel',
            Prefetch('atividades', queryset=Atividade.objects.select_related('usuario')),
        )

    def get_context_data(self, **kwargs):
        for acao, (form_class, _) in self.FORMULARIOS.items():
            kwargs.setdefault(f'form_{acao}', form_class())
        context = super().get_context_data(**kwargs)
        context['now'] = timezone.now()
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        acao = request.POST.get('acao')
        if acao not in self.FORMULARIOS:
            raise Http404('Ação desconhecida.')
        form_class, sucesso = self.FORMULARIOS[acao]
        form = form_class(request.POST, request.FILES)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(**{f'form_{acao}': form}))
        item = form.save(commit=False)
        item.tarefa = self.object
        item.save()
        registrar_atividade(self.object, request.user, 'adicionou', descrever_item(acao, item))
        messages.success(request, sucesso)
        return redirect(self.object)


def descrever_item(tipo, item):
    """Como um item de dentro da tarefa aparece no histórico."""
    if tipo == 'subtarefa':
        return f'a subtarefa “{item.descricao}”'
    if tipo == 'comentario':
        return f'um comentário de {item.autor}' if item.autor else 'um comentário'
    if tipo == 'anexo':
        return f'o anexo “{item.nome_arquivo}”'
    return f'{floatformat(item.horas, -2)} h de trabalho de {item.responsavel.nome}'


class TarefaFormularioMixin(FormularioMixin):
    model = Tarefa
    form_class = TarefaForm
    success_url = reverse_lazy('tarefa_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sem_responsaveis'] = not Responsavel.objects.exists()
        return context


class TarefaCreateView(TarefaFormularioMixin, CreateView):
    titulo_pagina = 'Nova tarefa'
    success_message = 'Tarefa "%(titulo)s" criada.'

    def form_valid(self, form):
        resposta = super().form_valid(form)
        registrar_atividade(self.object, self.request.user, 'criou')
        return resposta


class TarefaUpdateView(TarefaFormularioMixin, UpdateView):
    titulo_pagina = 'Editar tarefa'
    success_message = 'Tarefa "%(titulo)s" atualizada.'

    def form_valid(self, form):
        resposta = super().form_valid(form)
        if form.changed_data:
            campos = ', '.join(form.fields[nome].label.lower() for nome in form.changed_data)
            registrar_atividade(self.object, self.request.user, 'editou', campos)
        return resposta


class TarefaDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Tarefa
    success_url = reverse_lazy('tarefa_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Tudo o que vai embora junto com a tarefa (CASCADE)
        context.update(Tarefa.objects.filter(pk=self.object.pk).aggregate(
            total_subtarefas=Count('subtarefas', distinct=True),
            total_comentarios=Count('comentarios', distinct=True),
            total_anexos=Count('anexos', distinct=True),
            total_registros=Count('registros_tempo', distinct=True),
        ))
        return context

    def get_success_message(self, cleaned_data):
        return f'Tarefa "{self.object.titulo}" excluída.'


@login_required
@require_POST
def tarefa_toggle(request, pk):
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if tarefa.concluida_em:
        # Reabrir devolve a tarefa para onde ela estava antes de ser concluída
        nova = 'em_andamento' if tarefa.iniciada_em else 'a_fazer'
    else:
        nova = 'concluida'
    acao = tarefa.mudar_situacao(nova)
    tarefa.save(update_fields=['iniciada_em', 'concluida_em'])
    registrar_atividade(tarefa, request.user, acao)
    estado = 'concluída' if tarefa.concluida_em else 'reaberta'
    messages.success(request, f'Tarefa "{tarefa.titulo}" {estado}.')
    return voltar(request, 'tarefa_list')


def voltar(request, padrao):
    """Volta para a página de onde veio (com filtros), se `next` for um endereço deste site."""
    proxima = request.POST.get('next')
    if proxima and url_has_allowed_host_and_scheme(
        proxima, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return redirect(proxima)
    return redirect(padrao)


def quer_json(request):
    """Pedidos feitos pelo app.js (quadro, adição rápida) pedem a resposta em JSON."""
    return 'application/json' in request.headers.get('Accept', '')


@login_required
@require_POST
def tarefa_mover(request, pk):
    """Muda a situação da tarefa: é o que o quadro chama ao arrastar um cartão."""
    tarefa = get_object_or_404(Tarefa, pk=pk)
    nova = request.POST.get('situacao')
    if nova not in dict(Tarefa.SITUACOES):
        return HttpResponseBadRequest('Situação desconhecida.')
    acao = tarefa.mudar_situacao(nova)
    if acao:
        tarefa.save(update_fields=['iniciada_em', 'concluida_em'])
        registrar_atividade(tarefa, request.user, acao)
    rotulo = tarefa.get_situacao_display()
    if quer_json(request):
        return JsonResponse({'ok': True, 'situacao': nova, 'rotulo': rotulo})
    messages.success(request, f'Tarefa "{tarefa.titulo}" agora está em "{rotulo}".')
    return voltar(request, 'quadro')


# Itens de dentro da tarefa

# Os quatro são filhos de Tarefa e só aparecem na tela de detalhe dela, então uma
# única rota de exclusão atende todos, escolhendo o modelo pelo tipo na URL.
TIPOS_DE_ITEM = {
    'subtarefa': (Subtarefa, 'Subtarefa excluída.'),
    'comentario': (Comentario, 'Comentário excluído.'),
    'anexo': (Anexo, 'Anexo excluído.'),
    'registro': (RegistroTempo, 'Registro de tempo excluído.'),
}


@login_required
@require_POST
def item_delete(request, tipo, pk):
    if tipo not in TIPOS_DE_ITEM:
        raise Http404('Tipo de item desconhecido.')
    modelo, mensagem = TIPOS_DE_ITEM[tipo]
    item = get_object_or_404(modelo.objects.select_related('tarefa'), pk=pk)
    tarefa = item.tarefa
    descricao = descrever_item(tipo, item)
    item.delete()
    registrar_atividade(tarefa, request.user, 'removeu', descricao)
    messages.success(request, mensagem)
    return redirect(tarefa)


@login_required
@require_POST
def subtarefa_toggle(request, pk):
    subtarefa = get_object_or_404(Subtarefa.objects.select_related('tarefa'), pk=pk)
    subtarefa.concluida = not subtarefa.concluida
    subtarefa.save(update_fields=['concluida'])
    acao = 'marcou' if subtarefa.concluida else 'desmarcou'
    registrar_atividade(subtarefa.tarefa, request.user, acao, f'“{subtarefa.descricao}” no checklist')
    return redirect('tarefa_detail', pk=subtarefa.tarefa_id)


# Responsáveis

class ResponsavelListView(LeituraMixin, ListView):
    model = Responsavel
    context_object_name = 'responsaveis'

    def get_queryset(self):
        return Responsavel.objects.select_related('departamento')


class ResponsavelDetailView(LeituraMixin, DetailView):
    model = Responsavel

    def get_queryset(self):
        return Responsavel.objects.select_related('departamento')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        agora = timezone.now()
        tarefas = self.object.tarefa_set.com_relacionados()
        context.update(contar_por_situacao(tarefas, agora))
        context['horas'] = self.object.registros_tempo.aggregate(total=Sum('horas'))['total']
        context['tarefas'] = tarefas
        context['now'] = agora
        return context


class ResponsavelFormularioMixin(FormularioMixin):
    model = Responsavel
    form_class = ResponsavelForm
    success_url = reverse_lazy('responsavel_list')


class ResponsavelCreateView(ResponsavelFormularioMixin, CreateView):
    titulo_pagina = 'Novo responsável'
    success_message = 'Responsável "%(nome)s" cadastrado.'


class ResponsavelUpdateView(ResponsavelFormularioMixin, UpdateView):
    titulo_pagina = 'Editar responsável'
    success_message = 'Responsável "%(nome)s" atualizado.'


class ResponsavelDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Responsavel
    success_url = reverse_lazy('responsavel_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_tarefas'] = self.object.tarefa_set.count()
        context['total_registros'] = self.object.registros_tempo.count()
        return context

    def get_success_message(self, cleaned_data):
        return f'Responsável "{self.object.nome}" excluído.'

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ProtectedError:
            return self.render_to_response(self.get_context_data(form=form))


# Departamentos

class DepartamentoListView(LeituraMixin, ListView):
    model = Departamento
    context_object_name = 'departamentos'

    def get_queryset(self):
        return Departamento.objects.annotate(
            total_responsaveis=Count('responsaveis', distinct=True),
            total_projetos=Count('projetos', distinct=True),
        )


class DepartamentoFormularioMixin(FormularioMixin):
    model = Departamento
    form_class = DepartamentoForm
    success_url = reverse_lazy('departamento_list')


class DepartamentoCreateView(DepartamentoFormularioMixin, CreateView):
    titulo_pagina = 'Novo departamento'
    success_message = 'Departamento "%(nome)s" cadastrado.'


class DepartamentoUpdateView(DepartamentoFormularioMixin, UpdateView):
    titulo_pagina = 'Editar departamento'
    success_message = 'Departamento "%(nome)s" atualizado.'


class DepartamentoDeleteView(ExclusaoMixin, DeleteView):
    model = Departamento
    success_url = reverse_lazy('departamento_list')
    titulo_pagina = 'Excluir departamento'
    mensagem_exclusao = 'Departamento "%s" excluído.'
    aviso_relacionados = (
        'Este departamento está ligado a {n} cadastro(s). Nada será apagado: '
        'eles apenas ficam sem departamento.'
    )

    def contar_relacionados(self):
        return self.object.responsaveis.count() + self.object.projetos.count()


# Projetos

class ProjetoListView(LeituraMixin, ListView):
    model = Projeto
    context_object_name = 'projetos'

    def get_queryset(self):
        pendente = Q(tarefas__concluida_em__isnull=True)
        return Projeto.objects.select_related('departamento').annotate(
            total=Count('tarefas', distinct=True),
            pendentes=Count('tarefas', filter=pendente, distinct=True),
        )


class ProjetoDetailView(LeituraMixin, DetailView):
    model = Projeto

    def get_queryset(self):
        return Projeto.objects.select_related('departamento')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        agora = timezone.now()
        tarefas = self.object.tarefas.com_relacionados()
        context.update(contar_por_situacao(tarefas, agora))
        context['horas'] = RegistroTempo.objects.filter(
            tarefa__projeto=self.object,
        ).aggregate(total=Sum('horas'))['total']
        context['tarefas'] = tarefas
        context['now'] = agora
        return context


class ProjetoFormularioMixin(FormularioMixin):
    model = Projeto
    form_class = ProjetoForm
    success_url = reverse_lazy('projeto_list')


class ProjetoCreateView(ProjetoFormularioMixin, CreateView):
    titulo_pagina = 'Novo projeto'
    success_message = 'Projeto "%(nome)s" cadastrado.'


class ProjetoUpdateView(ProjetoFormularioMixin, UpdateView):
    titulo_pagina = 'Editar projeto'
    success_message = 'Projeto "%(nome)s" atualizado.'


class ProjetoDeleteView(ExclusaoMixin, DeleteView):
    model = Projeto
    success_url = reverse_lazy('projeto_list')
    titulo_pagina = 'Excluir projeto'
    mensagem_exclusao = 'Projeto "%s" excluído.'
    aviso_relacionados = (
        'Este projeto tem {n} tarefa(s). Nenhuma será apagada: elas apenas ficam sem projeto.'
    )

    def contar_relacionados(self):
        return self.object.tarefas.count()


# Categorias

class CategoriaListView(LeituraMixin, ListView):
    model = Categoria
    context_object_name = 'categorias'

    def get_queryset(self):
        return Categoria.objects.annotate(total=Count('tarefas'))


class CategoriaFormularioMixin(FormularioMixin):
    model = Categoria
    form_class = CategoriaForm
    success_url = reverse_lazy('categoria_list')


class CategoriaCreateView(CategoriaFormularioMixin, CreateView):
    titulo_pagina = 'Nova categoria'
    success_message = 'Categoria "%(nome)s" cadastrada.'


class CategoriaUpdateView(CategoriaFormularioMixin, UpdateView):
    titulo_pagina = 'Editar categoria'
    success_message = 'Categoria "%(nome)s" atualizada.'


class CategoriaDeleteView(ExclusaoMixin, DeleteView):
    model = Categoria
    success_url = reverse_lazy('categoria_list')
    titulo_pagina = 'Excluir categoria'
    mensagem_exclusao = 'Categoria "%s" excluída.'
    aviso_relacionados = (
        'Esta categoria está em {n} tarefa(s). Nenhuma será apagada: elas apenas ficam sem categoria.'
    )

    def contar_relacionados(self):
        return self.object.tarefas.count()


# Etiquetas

class EtiquetaListView(LeituraMixin, ListView):
    model = Etiqueta
    context_object_name = 'etiquetas'

    def get_queryset(self):
        return Etiqueta.objects.annotate(total=Count('tarefas'))


class EtiquetaFormularioMixin(FormularioMixin):
    model = Etiqueta
    form_class = EtiquetaForm
    success_url = reverse_lazy('etiqueta_list')


class EtiquetaCreateView(EtiquetaFormularioMixin, CreateView):
    titulo_pagina = 'Nova etiqueta'
    success_message = 'Etiqueta "%(nome)s" cadastrada.'


class EtiquetaUpdateView(EtiquetaFormularioMixin, UpdateView):
    titulo_pagina = 'Editar etiqueta'
    success_message = 'Etiqueta "%(nome)s" atualizada.'


class EtiquetaDeleteView(ExclusaoMixin, DeleteView):
    model = Etiqueta
    success_url = reverse_lazy('etiqueta_list')
    titulo_pagina = 'Excluir etiqueta'
    mensagem_exclusao = 'Etiqueta "%s" excluída.'
    aviso_relacionados = (
        'Esta etiqueta está em {n} tarefa(s). Nenhuma será apagada: elas apenas perdem a etiqueta.'
    )

    def contar_relacionados(self):
        return self.object.tarefas.count()


# Quadro (kanban)

class QuadroView(LeituraMixin, TemplateView):
    """As tarefas em três colunas, uma por situação. Arrastar um cartão chama tarefa_mover."""
    template_name = 'Suap2APP/quadro.html'
    DIAS_DE_CONCLUIDAS = 30

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        agora = timezone.now()
        filtro = TarefaFiltroForm(self.request.GET)
        limite = agora - timedelta(days=self.DIAS_DE_CONCLUIDAS)
        # Uma consulta só para as três colunas; a separação acontece aqui em Python
        tarefas = filtro.filtrar(
            Tarefa.objects.com_relacionados().com_peso_da_prioridade(), agora, com_status=False,
        ).filter(Q(concluida_em__isnull=True) | Q(concluida_em__gte=limite)).order_by('peso_prioridade', 'prazo')
        por_situacao = defaultdict(list)
        for tarefa in tarefas:
            por_situacao[tarefa.situacao].append(tarefa)
        por_situacao['concluida'].sort(key=lambda t: t.concluida_em, reverse=True)

        ordem = [valor for valor, _ in Tarefa.SITUACOES]
        context['colunas'] = [
            {
                'situacao': valor,
                'titulo': rotulo,
                'tarefas': por_situacao[valor],
                'anterior': ordem[i - 1] if i > 0 else '',
                'proxima': ordem[i + 1] if i + 1 < len(ordem) else '',
            }
            for i, (valor, rotulo) in enumerate(Tarefa.SITUACOES)
        ]
        context['filtro'] = filtro
        context['filtrando'] = any(self.request.GET.get(campo) for campo in filtro.fields)
        context['dias_de_concluidas'] = self.DIAS_DE_CONCLUIDAS
        context['now'] = agora
        return context


# Calendário

MES = re.compile(r'(\d{4})-(\d{1,2})')
DIAS_DA_SEMANA = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb']


class CalendarioView(LeituraMixin, TemplateView):
    """Um mês por vez, com cada tarefa no dia do prazo. O mês vem de ?mes=AAAA-MM."""
    template_name = 'Suap2APP/calendario.html'

    def mes_pedido(self):
        hoje = timezone.localdate()
        m = MES.fullmatch(self.request.GET.get('mes', ''))
        if m:
            try:
                return date(int(m[1]), int(m[2]), 1)
            except ValueError:
                pass
        return hoje.replace(day=1)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        agora = timezone.now()
        hoje = timezone.localdate()
        primeiro = self.mes_pedido()
        # Semanas completas, de domingo a sábado, incluindo os dias dos meses vizinhos
        semanas = calendar.Calendar(firstweekday=6).monthdatescalendar(primeiro.year, primeiro.month)
        inicio = timezone.make_aware(datetime.combine(semanas[0][0], time.min))
        fim = timezone.make_aware(datetime.combine(semanas[-1][-1] + timedelta(days=1), time.min))

        filtro = TarefaFiltroForm(self.request.GET)
        tarefas = filtro.filtrar(
            Tarefa.objects.select_related('categoria', 'pessoa_responsavel'), agora, com_status=False,
        ).filter(prazo__gte=inicio, prazo__lt=fim).order_by('prazo')
        por_dia = defaultdict(list)
        for tarefa in tarefas:
            por_dia[timezone.localdate(tarefa.prazo)].append(tarefa)

        context['semanas'] = [
            [
                {'data': dia, 'tarefas': por_dia[dia], 'fora': dia.month != primeiro.month, 'hoje': dia == hoje}
                for dia in semana
            ]
            for semana in semanas
        ]
        context['agenda'] = [
            dia for semana in context['semanas'] for dia in semana if dia['tarefas'] and not dia['fora']
        ]
        anterior = (primeiro - timedelta(days=1)).replace(day=1)
        proximo = (primeiro + timedelta(days=32)).replace(day=1)
        context.update(
            mes=primeiro,
            mes_anterior=f'{anterior:%Y-%m}',
            mes_proximo=f'{proximo:%Y-%m}',
            e_mes_atual=primeiro == hoje.replace(day=1),
            dias_da_semana=DIAS_DA_SEMANA,
            filtro=filtro,
            filtrando=any(self.request.GET.get(campo) for campo in filtro.fields),
            now=agora,
        )
        return context


# Adição rápida

@login_required
def tarefa_rapida(request):
    """GET devolve o formulário da janela de adição rápida; POST cria a tarefa."""
    if request.method != 'POST':
        return render(request, 'Suap2APP/_tarefa_rapida.html', {'form': TarefaRapidaForm()})

    form = TarefaRapidaForm(request.POST)
    if not form.is_valid():
        erros = [erro for lista in form.errors.values() for erro in lista]
        if quer_json(request):
            return JsonResponse({'ok': False, 'erros': erros}, status=400)
        messages.error(request, ' '.join(erros))
        return voltar(request, 'tarefa_list')

    tarefa = form.save()
    registrar_atividade(tarefa, request.user, 'criou', 'pela adição rápida')
    prazo = timezone.localtime(tarefa.prazo)
    mensagem = (
        f'Tarefa "{tarefa.titulo}" criada para {tarefa.pessoa_responsavel.nome}, '
        f'prazo {prazo:%d/%m às %H:%M}.'
    )
    # A mensagem aparece na próxima página, inclusive quando o app.js recarrega a atual
    messages.success(request, mensagem)
    if quer_json(request):
        return JsonResponse({'ok': True, 'url': tarefa.get_absolute_url(), 'mensagem': mensagem})
    return voltar(request, 'tarefa_list')
