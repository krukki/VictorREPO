from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import Tarefa, Responsavel
from .forms import TarefaForm, ResponsavelForm


def tarefa_list(request):
    tarefas = Tarefa.objects.all()
    return render(request, 'Suap2APP/tarefa_list.html', {
        'tarefas': tarefas,
        'now': timezone.now(),
    })


def tarefa_create(request):
    if request.method == 'POST':
        form = TarefaForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('tarefa_list')
    else:
        form = TarefaForm()
    return render(request, 'Suap2APP/tarefa_form.html', {
        'form': form,
        'titulo_pagina': 'Nova tarefa',
    })


def tarefa_update(request, pk):
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if request.method == 'POST':
        form = TarefaForm(request.POST, instance=tarefa)
        if form.is_valid():
            form.save()
            return redirect('tarefa_list')
    else:
        form = TarefaForm(instance=tarefa)
    return render(request, 'Suap2APP/tarefa_form.html', {
        'form': form,
        'titulo_pagina': 'Editar tarefa',
    })


def tarefa_delete(request, pk):
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if request.method == 'POST':
        tarefa.delete()
        return redirect('tarefa_list')
    return render(request, 'Suap2APP/tarefa_confirm_delete.html', {'tarefa': tarefa})


def tarefa_toggle(request, pk):
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if request.method == 'POST':
        tarefa.finished_at = None if tarefa.finished_at else timezone.now()
        tarefa.save()
    return redirect('tarefa_list')


def responsavel_list(request):
    responsaveis = Responsavel.objects.order_by('nome')
    return render(request, 'Suap2APP/responsavel_list.html', {'responsaveis': responsaveis})


def responsavel_create(request):
    if request.method == 'POST':
        form = ResponsavelForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('responsavel_list')
    else:
        form = ResponsavelForm()
    return render(request, 'Suap2APP/responsavel_form.html', {
        'form': form,
        'titulo_pagina': 'Novo responsável',
    })


def responsavel_update(request, pk):
    responsavel = get_object_or_404(Responsavel, pk=pk)
    if request.method == 'POST':
        form = ResponsavelForm(request.POST, instance=responsavel)
        if form.is_valid():
            form.save()
            return redirect('responsavel_list')
    else:
        form = ResponsavelForm(instance=responsavel)
    return render(request, 'Suap2APP/responsavel_form.html', {
        'form': form,
        'titulo_pagina': 'Editar responsável',
    })


def responsavel_delete(request, pk):
    responsavel = get_object_or_404(Responsavel, pk=pk)
    if request.method == 'POST':
        responsavel.delete()
        return redirect('responsavel_list')
    return render(request, 'Suap2APP/responsavel_confirm_delete.html', {'responsavel': responsavel})
