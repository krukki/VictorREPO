"""
URL configuration for Suap2 project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from Suap2APP import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('entrar/', auth_views.LoginView.as_view(template_name='Suap2APP/login.html'), name='login'),
    path('sair/', auth_views.LogoutView.as_view(), name='logout'),
    path('cadastrar/', views.CadastroView.as_view(), name='cadastro'),
    path('visitante/', views.entrar_como_visitante, name='visitante'),
    path('painel/', views.PainelView.as_view(), name='painel'),
    path('', views.TarefaListView.as_view(), name='tarefa_list'),
    path('tarefas/nova/', views.TarefaCreateView.as_view(), name='tarefa_create'),
    path('tarefas/<int:pk>/', views.TarefaDetailView.as_view(), name='tarefa_detail'),
    path('tarefas/<int:pk>/editar/', views.TarefaUpdateView.as_view(), name='tarefa_update'),
    path('tarefas/<int:pk>/excluir/', views.TarefaDeleteView.as_view(), name='tarefa_delete'),
    path('tarefas/<int:pk>/concluir/', views.tarefa_toggle, name='tarefa_toggle'),
    path('tarefas/<int:pk>/mover/', views.tarefa_mover, name='tarefa_mover'),
    path('tarefas/rapida/', views.tarefa_rapida, name='tarefa_rapida'),
    path('quadro/', views.QuadroView.as_view(), name='quadro'),
    path('calendario/', views.CalendarioView.as_view(), name='calendario'),
    # Itens de dentro da tarefa (subtarefa, comentário, anexo, registro de tempo)
    path('subtarefas/<int:pk>/concluir/', views.subtarefa_toggle, name='subtarefa_toggle'),
    path('itens/<str:tipo>/<int:pk>/excluir/', views.item_delete, name='item_delete'),
    path('responsaveis/', views.ResponsavelListView.as_view(), name='responsavel_list'),
    path('responsaveis/novo/', views.ResponsavelCreateView.as_view(), name='responsavel_create'),
    path('responsaveis/<int:pk>/', views.ResponsavelDetailView.as_view(), name='responsavel_detail'),
    path('responsaveis/<int:pk>/editar/', views.ResponsavelUpdateView.as_view(), name='responsavel_update'),
    path('responsaveis/<int:pk>/excluir/', views.ResponsavelDeleteView.as_view(), name='responsavel_delete'),
    path('departamentos/', views.DepartamentoListView.as_view(), name='departamento_list'),
    path('departamentos/novo/', views.DepartamentoCreateView.as_view(), name='departamento_create'),
    path('departamentos/<int:pk>/editar/', views.DepartamentoUpdateView.as_view(), name='departamento_update'),
    path('departamentos/<int:pk>/excluir/', views.DepartamentoDeleteView.as_view(), name='departamento_delete'),
    path('projetos/', views.ProjetoListView.as_view(), name='projeto_list'),
    path('projetos/novo/', views.ProjetoCreateView.as_view(), name='projeto_create'),
    path('projetos/<int:pk>/', views.ProjetoDetailView.as_view(), name='projeto_detail'),
    path('projetos/<int:pk>/editar/', views.ProjetoUpdateView.as_view(), name='projeto_update'),
    path('projetos/<int:pk>/excluir/', views.ProjetoDeleteView.as_view(), name='projeto_delete'),
    path('categorias/', views.CategoriaListView.as_view(), name='categoria_list'),
    path('categorias/nova/', views.CategoriaCreateView.as_view(), name='categoria_create'),
    path('categorias/<int:pk>/editar/', views.CategoriaUpdateView.as_view(), name='categoria_update'),
    path('categorias/<int:pk>/excluir/', views.CategoriaDeleteView.as_view(), name='categoria_delete'),
    path('etiquetas/', views.EtiquetaListView.as_view(), name='etiqueta_list'),
    path('etiquetas/nova/', views.EtiquetaCreateView.as_view(), name='etiqueta_create'),
    path('etiquetas/<int:pk>/editar/', views.EtiquetaUpdateView.as_view(), name='etiqueta_update'),
    path('etiquetas/<int:pk>/excluir/', views.EtiquetaDeleteView.as_view(), name='etiqueta_delete'),
]

# Em produção os anexos são servidos pelo servidor web, não pelo Django.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
