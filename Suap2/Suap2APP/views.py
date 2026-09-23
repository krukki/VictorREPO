from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView

from .models import Tarefa, Responsavel
from .forms import TarefaForm, TarefaFiltroForm, ResponsavelForm


class FormularioMixin(LoginRequiredMixin, SuccessMessageMixin):
    """Configuração comum das telas de criar/editar, que usam o mesmo template."""
    template_name = 'Suap2APP/form.html'
    titulo_pagina = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo_pagina'] = self.titulo_pagina
        context['cancelar_url'] = self.success_url
        return context


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
        context['proximas'] = (
            Tarefa.objects.filter(concluida_em__isnull=True)
            .select_related('pessoa_responsavel')
            .order_by('prazo')[:5]
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
        return self.filtro.filtrar(Tarefa.objects.select_related('pessoa_responsavel'), self.agora)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['now'] = self.agora
        context['filtro'] = self.filtro
        context['filtrando'] = any(self.request.GET.get(campo) for campo in self.filtro.fields)
        return context


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


# Responsáveis

class ResponsavelListView(LoginRequiredMixin, ListView):
    model = Responsavel
    context_object_name = 'responsaveis'


class ResponsavelDetailView(LoginRequiredMixin, DetailView):
    model = Responsavel

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        agora = timezone.now()
        tarefas = self.object.tarefa_set.select_related('pessoa_responsavel')
        pendente = Q(concluida_em__isnull=True)
        context.update(tarefas.aggregate(
            pendentes=Count('pk', filter=pendente),
            atrasadas=Count('pk', filter=pendente & Q(prazo__lt=agora)),
            concluidas=Count('pk', filter=Q(concluida_em__isnull=False)),
        ))
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
        return context

    def get_success_message(self, cleaned_data):
        return f'Responsável "{self.object.nome}" excluído.'

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ProtectedError:
            return self.render_to_response(self.get_context_data(form=form))
