from django import forms
from .models import Tarefa, Responsavel


class TarefaForm(forms.ModelForm):
    class Meta:
        model = Tarefa
        fields = ['title', 'deadline', 'pessoa_responsavel']
        labels = {
            'title': 'Título',
            'deadline': 'Prazo',
            'pessoa_responsavel': 'Responsável',
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

    def clean_cpf(self):
        digitos = ''.join(c for c in self.cleaned_data['cpf'] if c.isdigit())
        if len(digitos) != 11 or digitos == digitos[0] * 11:
            raise forms.ValidationError('CPF inválido.')
        for tamanho in (9, 10):
            soma = sum(int(d) * peso for d, peso in zip(digitos, range(tamanho + 1, 1, -1)))
            if (soma * 10 % 11) % 10 != int(digitos[tamanho]):
                raise forms.ValidationError('CPF inválido.')
        # Guarda sempre no mesmo formato para que o unique=True pegue duplicatas
        return f'{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}'
