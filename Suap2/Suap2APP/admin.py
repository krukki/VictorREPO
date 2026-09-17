from django.contrib import admin
from .models import Tarefa, Responsavel


@admin.register(Tarefa)
class TarefaAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'pessoa_responsavel', 'prazo', 'concluida_em', 'criada_em']
    list_filter = ['pessoa_responsavel', 'prazo', 'concluida_em']
    search_fields = ['titulo', 'pessoa_responsavel__nome']
    list_select_related = ['pessoa_responsavel']
    date_hierarchy = 'prazo'


@admin.register(Responsavel)
class ResponsavelAdmin(admin.ModelAdmin):
    list_display = ['nome', 'cpf', 'email', 'telefone']
    search_fields = ['nome', 'cpf', 'email']
