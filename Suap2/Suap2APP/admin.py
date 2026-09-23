from django.contrib import admin

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


# Os quatro itens que só existem dentro de uma tarefa aparecem na página dela

class SubtarefaInline(admin.TabularInline):
    model = Subtarefa
    extra = 1


class ComentarioInline(admin.TabularInline):
    model = Comentario
    extra = 0
    autocomplete_fields = ['autor']
    readonly_fields = ['criado_em']


class AnexoInline(admin.TabularInline):
    model = Anexo
    extra = 0
    readonly_fields = ['enviado_em']


class RegistroTempoInline(admin.TabularInline):
    model = RegistroTempo
    extra = 0
    autocomplete_fields = ['responsavel']


@admin.register(Tarefa)
class TarefaAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'pessoa_responsavel', 'projeto', 'categoria', 'prazo', 'concluida_em', 'criada_em']
    list_filter = ['pessoa_responsavel', 'projeto', 'categoria', 'etiquetas', 'prazo', 'concluida_em']
    search_fields = ['titulo', 'pessoa_responsavel__nome']
    list_select_related = ['pessoa_responsavel', 'projeto', 'categoria']
    autocomplete_fields = ['pessoa_responsavel', 'projeto', 'categoria']
    filter_horizontal = ['etiquetas']
    date_hierarchy = 'prazo'
    inlines = [SubtarefaInline, ComentarioInline, AnexoInline, RegistroTempoInline]


@admin.register(Responsavel)
class ResponsavelAdmin(admin.ModelAdmin):
    list_display = ['nome', 'cpf', 'email', 'telefone', 'departamento']
    list_filter = ['departamento']
    search_fields = ['nome', 'cpf', 'email']
    list_select_related = ['departamento']


@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'sigla']
    search_fields = ['nome', 'sigla']


@admin.register(Projeto)
class ProjetoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'departamento', 'inicio', 'fim']
    list_filter = ['departamento']
    search_fields = ['nome', 'descricao']
    list_select_related = ['departamento']


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'cor']
    list_filter = ['cor']
    search_fields = ['nome']


@admin.register(Etiqueta)
class EtiquetaAdmin(admin.ModelAdmin):
    list_display = ['nome']
    search_fields = ['nome']


@admin.register(Subtarefa)
class SubtarefaAdmin(admin.ModelAdmin):
    list_display = ['descricao', 'tarefa', 'concluida', 'ordem']
    list_filter = ['concluida']
    search_fields = ['descricao', 'tarefa__titulo']
    list_select_related = ['tarefa']
    autocomplete_fields = ['tarefa']


@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    list_display = ['tarefa', 'autor', 'criado_em']
    list_filter = ['autor', 'criado_em']
    search_fields = ['texto', 'tarefa__titulo']
    list_select_related = ['tarefa', 'autor']
    autocomplete_fields = ['tarefa', 'autor']
    date_hierarchy = 'criado_em'


@admin.register(Anexo)
class AnexoAdmin(admin.ModelAdmin):
    list_display = ['nome_arquivo', 'tarefa', 'descricao', 'enviado_em']
    search_fields = ['descricao', 'tarefa__titulo']
    list_select_related = ['tarefa']
    autocomplete_fields = ['tarefa']


@admin.register(RegistroTempo)
class RegistroTempoAdmin(admin.ModelAdmin):
    list_display = ['tarefa', 'responsavel', 'horas', 'data']
    list_filter = ['responsavel', 'data']
    search_fields = ['observacao', 'tarefa__titulo', 'responsavel__nome']
    list_select_related = ['tarefa', 'responsavel']
    autocomplete_fields = ['tarefa', 'responsavel']
    date_hierarchy = 'data'
