from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, ProtectedError, Q, Sum
from django.http import Http404
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView

from .models import (
    Anexo,
    Categoria,
    Comentario,
    Departamento,
    Etiqueta,
    Projeto,
    RegistroTempo,
    Responsavel,
    Subtarefa,
    Tarefa,
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
)


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


class PainelView(LoginRequiredMixin, TemplateView):
    """Resumo das tarefas; as condições seguem as de TarefaFiltroForm.filtrar."""
    template_name = 'Suap2APP/painel.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        agora = timezone.now()
        semana = timedelta(days=7)
        pendente = Q(concluida_em__isnull=True)
        context.update(Tarefa.objects.aggregate(
            pendentes=Count('pk', filter=pendente),
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


class TarefaListView(LoginRequiredMixin, ListView):
    model = Tarefa
    context_object_name = 'tarefas'
    paginate_by = 10

    def get_queryset(self):
        self.agora = timezone.now()
        self.filtro = TarefaFiltroForm(self.request.GET)
        return self.filtro.filtrar(Tarefa.objects.com_relacionados(), self.agora)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['now'] = self.agora
        context['filtro'] = self.filtro
        context['filtrando'] = any(self.request.GET.get(campo) for campo in self.filtro.fields)
        return context


class TarefaDetailView(LoginRequiredMixin, DetailView):
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
        messages.success(request, sucesso)
        return redirect(self.object)


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


class TarefaUpdateView(TarefaFormularioMixin, UpdateView):
    titulo_pagina = 'Editar tarefa'
    success_message = 'Tarefa "%(titulo)s" atualizada.'


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
    tarefa.concluida_em = None if tarefa.concluida_em else timezone.now()
    tarefa.save(update_fields=['concluida_em'])
    estado = 'concluída' if tarefa.concluida_em else 'reaberta'
    messages.success(request, f'Tarefa "{tarefa.titulo}" {estado}.')
    # Volta para a página de onde veio (com filtros), se for um endereço deste site
    proxima = request.POST.get('next')
    if proxima and url_has_allowed_host_and_scheme(proxima, allowed_hosts={request.get_host()}):
        return redirect(proxima)
    return redirect('tarefa_list')


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
    item = get_object_or_404(modelo, pk=pk)
    tarefa_pk = item.tarefa_id
    item.delete()
    messages.success(request, mensagem)
    return redirect('tarefa_detail', pk=tarefa_pk)


@login_required
@require_POST
def subtarefa_toggle(request, pk):
    subtarefa = get_object_or_404(Subtarefa, pk=pk)
    subtarefa.concluida = not subtarefa.concluida
    subtarefa.save(update_fields=['concluida'])
    return redirect('tarefa_detail', pk=subtarefa.tarefa_id)


# Responsáveis

class ResponsavelListView(LoginRequiredMixin, ListView):
    model = Responsavel
    context_object_name = 'responsaveis'

    def get_queryset(self):
        return Responsavel.objects.select_related('departamento')


class ResponsavelDetailView(LoginRequiredMixin, DetailView):
    model = Responsavel

    def get_queryset(self):
        return Responsavel.objects.select_related('departamento')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        agora = timezone.now()
        tarefas = self.object.tarefa_set.com_relacionados()
        pendente = Q(concluida_em__isnull=True)
        context.update(tarefas.aggregate(
            pendentes=Count('pk', filter=pendente),
            atrasadas=Count('pk', filter=pendente & Q(prazo__lt=agora)),
            concluidas=Count('pk', filter=Q(concluida_em__isnull=False)),
        ))
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

class DepartamentoListView(LoginRequiredMixin, ListView):
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

class ProjetoListView(LoginRequiredMixin, ListView):
    model = Projeto
    context_object_name = 'projetos'

    def get_queryset(self):
        pendente = Q(tarefas__concluida_em__isnull=True)
        return Projeto.objects.select_related('departamento').annotate(
            total=Count('tarefas', distinct=True),
            pendentes=Count('tarefas', filter=pendente, distinct=True),
        )


class ProjetoDetailView(LoginRequiredMixin, DetailView):
    model = Projeto

    def get_queryset(self):
        return Projeto.objects.select_related('departamento')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        agora = timezone.now()
        tarefas = self.object.tarefas.com_relacionados()
        pendente = Q(concluida_em__isnull=True)
        context.update(tarefas.aggregate(
            pendentes=Count('pk', filter=pendente),
            atrasadas=Count('pk', filter=pendente & Q(prazo__lt=agora)),
            concluidas=Count('pk', filter=Q(concluida_em__isnull=False)),
        ))
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

class CategoriaListView(LoginRequiredMixin, ListView):
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

class EtiquetaListView(LoginRequiredMixin, ListView):
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
