from django import forms
from .models import Tarefa


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
