"""
URL configuration for Suap2 project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path
from Suap2APP import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.tarefa_list, name='tarefa_list'),
    path('tarefas/nova/', views.tarefa_create, name='tarefa_create'),
    path('tarefas/<int:pk>/editar/', views.tarefa_update, name='tarefa_update'),
    path('tarefas/<int:pk>/excluir/', views.tarefa_delete, name='tarefa_delete'),
    path('tarefas/<int:pk>/concluir/', views.tarefa_toggle, name='tarefa_toggle'),
    path('responsaveis/', views.responsavel_list, name='responsavel_list'),
    path('responsaveis/novo/', views.responsavel_create, name='responsavel_create'),
    path('responsaveis/<int:pk>/editar/', views.responsavel_update, name='responsavel_update'),
    path('responsaveis/<int:pk>/excluir/', views.responsavel_delete, name='responsavel_delete'),
]
