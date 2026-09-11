from django import forms
from .models import Tarefa, Responsavel


class TarefaForm(forms.ModelForm):
    class Meta:
        model = Tarefa
        fields = ['title', 'deadline']
        labels = {
            'title': 'Título',
            'deadline': 'Prazo',
        }
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'O que precisa ser feito?'}),
            'deadline': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deadline'].input_formats = ['%Y-%m-%dT%H:%M']


class ResponsavelForm(forms.ModelForm):
    class Meta:
        model = Responsavel
        fields = ['nome', 'cpf', 'email', 'telefone']
        labels = {
            'nome': 'Nome',
            'cpf': 'CPF',
            'email': 'E-mail',
            'telefone': 'Telefone',
        }
        widgets = {
            'nome': forms.TextInput(attrs={'placeholder': 'Nome completo'}),
            'cpf': forms.TextInput(attrs={'placeholder': '000.000.000-00'}),
            'email': forms.EmailInput(attrs={'placeholder': 'nome@exemplo.com'}),
            'telefone': forms.TextInput(attrs={'placeholder': '(00) 00000-0000'}),
        }
