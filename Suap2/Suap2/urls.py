"""
URL configuration for Suap2 project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from Suap2APP import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('entrar/', auth_views.LoginView.as_view(template_name='Suap2APP/login.html'), name='login'),
    path('sair/', auth_views.LogoutView.as_view(), name='logout'),
    path('painel/', views.PainelView.as_view(), name='painel'),
    path('', views.TarefaListView.as_view(), name='tarefa_list'),
    path('tarefas/nova/', views.TarefaCreateView.as_view(), name='tarefa_create'),
    path('tarefas/<int:pk>/editar/', views.TarefaUpdateView.as_view(), name='tarefa_update'),
    path('tarefas/<int:pk>/excluir/', views.TarefaDeleteView.as_view(), name='tarefa_delete'),
    path('tarefas/<int:pk>/concluir/', views.tarefa_toggle, name='tarefa_toggle'),
    path('responsaveis/', views.ResponsavelListView.as_view(), name='responsavel_list'),
    path('responsaveis/novo/', views.ResponsavelCreateView.as_view(), name='responsavel_create'),
    path('responsaveis/<int:pk>/', views.ResponsavelDetailView.as_view(), name='responsavel_detail'),
    path('responsaveis/<int:pk>/editar/', views.ResponsavelUpdateView.as_view(), name='responsavel_update'),
    path('responsaveis/<int:pk>/excluir/', views.ResponsavelDeleteView.as_view(), name='responsavel_delete'),
]
