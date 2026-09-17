from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import ProtectedError
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from .models import Tarefa, Responsavel
from .forms import TarefaForm, ResponsavelForm


class FormularioMixin(LoginRequiredMixin, SuccessMessageMixin):
    """Configuração comum das telas de criar/editar, que usam o mesmo template."""
    template_name = 'Suap2APP/form.html'
    titulo_pagina = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo_pagina'] = self.titulo_pagina
        context['cancelar_url'] = self.success_url
        return context


# Tarefas

class TarefaListView(LoginRequiredMixin, ListView):
    model = Tarefa
    context_object_name = 'tarefas'

    def get_queryset(self):
        return Tarefa.objects.select_related('pessoa_responsavel')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['now'] = timezone.now()
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
    return redirect('tarefa_list')


# Responsáveis

class ResponsavelListView(LoginRequiredMixin, ListView):
    model = Responsavel
    context_object_name = 'responsaveis'


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
