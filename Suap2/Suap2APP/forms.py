from django import forms

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

TAMANHO_MAXIMO_ANEXO = 10 * 1024 * 1024


# Os dois widgets abaixo passam o formato pelo __init__ porque DateTimeBaseInput
# sobrescreve self.format na construção: só o atributo de classe não pega, e o valor
# sairia no formato brasileiro, que <input type="date"> não aceita.

class DataInput(forms.DateInput):
    """<input type="date">, que só entende e só devolve o formato ISO."""
    input_type = 'date'

    def __init__(self, attrs=None, format='%Y-%m-%d'):
        super().__init__(attrs, format)


class DataHoraInput(forms.DateTimeInput):
    """<input type="datetime-local">, idem."""
    input_type = 'datetime-local'

    def __init__(self, attrs=None, format='%Y-%m-%dT%H:%M'):
        super().__init__(attrs, format)


class TarefaForm(forms.ModelForm):
    class Meta:
        model = Tarefa
        fields = ['titulo', 'prazo', 'pessoa_responsavel', 'projeto', 'categoria', 'etiquetas']
        labels = {
            'titulo': 'Título',
            'prazo': 'Prazo',
            'pessoa_responsavel': 'Responsável',
            'projeto': 'Projeto',
            'categoria': 'Categoria',
            'etiquetas': 'Etiquetas',
        }
        widgets = {
            'titulo': forms.TextInput(attrs={'placeholder': 'O que precisa ser feito?'}),
            'prazo': DataHoraInput,
            'etiquetas': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['prazo'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['projeto'].empty_label = 'Sem projeto'
        self.fields['categoria'].empty_label = 'Sem categoria'

    def save(self, commit=True):
        # Prazo novo merece um lembrete novo
        if 'prazo' in self.changed_data:
            self.instance.lembrete_enviado_em = None
        return super().save(commit)


class TarefaFiltroForm(forms.Form):
    STATUS_CHOICES = [
        ('', 'Todas'),
        ('pendentes', 'Pendentes'),
        ('atrasadas', 'Atrasadas'),
        ('concluidas', 'Concluídas'),
    ]

    q = forms.CharField(
        label='Buscar',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Buscar pelo título', 'type': 'search'}),
    )
    status = forms.ChoiceField(label='Situação', choices=STATUS_CHOICES, required=False)
    responsavel = forms.ModelChoiceField(
        label='Responsável',
        queryset=Responsavel.objects.all(),
        required=False,
        empty_label='Todos',
    )
    projeto = forms.ModelChoiceField(
        label='Projeto',
        queryset=Projeto.objects.all(),
        required=False,
        empty_label='Todos',
    )
    categoria = forms.ModelChoiceField(
        label='Categoria',
        queryset=Categoria.objects.all(),
        required=False,
        empty_label='Todas',
    )
    etiqueta = forms.ModelChoiceField(
        label='Etiqueta',
        queryset=Etiqueta.objects.all(),
        required=False,
        empty_label='Todas',
    )

    def filtrar(self, tarefas, agora):
        if not self.is_valid():
            return tarefas
        dados = self.cleaned_data
        if dados['q']:
            tarefas = tarefas.filter(titulo__icontains=dados['q'])
        if dados['responsavel']:
            tarefas = tarefas.filter(pessoa_responsavel=dados['responsavel'])
        if dados['projeto']:
            tarefas = tarefas.filter(projeto=dados['projeto'])
        if dados['categoria']:
            tarefas = tarefas.filter(categoria=dados['categoria'])
        if dados['etiqueta']:
            tarefas = tarefas.filter(etiquetas=dados['etiqueta'])
        if dados['status'] == 'pendentes':
            tarefas = tarefas.filter(concluida_em__isnull=True)
        elif dados['status'] == 'atrasadas':
            tarefas = tarefas.filter(concluida_em__isnull=True, prazo__lt=agora)
        elif dados['status'] == 'concluidas':
            tarefas = tarefas.filter(concluida_em__isnull=False)
        return tarefas


class ResponsavelForm(forms.ModelForm):
    class Meta:
        model = Responsavel
        fields = ['nome', 'cpf', 'email', 'telefone', 'departamento']
        labels = {
            'nome': 'Nome',
            'cpf': 'CPF',
            'email': 'E-mail',
            'telefone': 'Telefone',
            'departamento': 'Departamento',
        }
        widgets = {
            'nome': forms.TextInput(attrs={'placeholder': 'Nome completo'}),
            'cpf': forms.TextInput(attrs={'placeholder': '000.000.000-00'}),
            'email': forms.EmailInput(attrs={'placeholder': 'nome@exemplo.com'}),
            'telefone': forms.TextInput(attrs={'placeholder': '(00) 00000-0000'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['departamento'].empty_label = 'Sem departamento'

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


class DepartamentoForm(forms.ModelForm):
    class Meta:
        model = Departamento
        fields = ['nome', 'sigla']
        labels = {'nome': 'Nome', 'sigla': 'Sigla'}
        widgets = {
            'nome': forms.TextInput(attrs={'placeholder': 'Coordenação de Informática'}),
            'sigla': forms.TextInput(attrs={'placeholder': 'CINF'}),
        }


class ProjetoForm(forms.ModelForm):
    class Meta:
        model = Projeto
        fields = ['nome', 'descricao', 'departamento', 'inicio', 'fim']
        labels = {
            'nome': 'Nome',
            'descricao': 'Descrição',
            'departamento': 'Departamento',
            'inicio': 'Início',
            'fim': 'Fim',
        }
        widgets = {
            'nome': forms.TextInput(attrs={'placeholder': 'Nome do projeto'}),
            'descricao': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Para que serve este projeto?'}),
            'inicio': DataInput,
            'fim': DataInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['departamento'].empty_label = 'Sem departamento'
        for campo in ('inicio', 'fim'):
            self.fields[campo].input_formats = ['%Y-%m-%d']

    def clean(self):
        dados = super().clean()
        inicio, fim = dados.get('inicio'), dados.get('fim')
        # Mesma regra da CheckConstraint do modelo, para virar erro de formulário
        if inicio and fim and fim < inicio:
            raise forms.ValidationError('O fim não pode ser antes do início.')
        return dados


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ['nome', 'cor']
        labels = {'nome': 'Nome', 'cor': 'Cor'}
        widgets = {'nome': forms.TextInput(attrs={'placeholder': 'Ensino, Manutenção, Compras…'})}


class EtiquetaForm(forms.ModelForm):
    class Meta:
        model = Etiqueta
        fields = ['nome']
        labels = {'nome': 'Nome'}
        widgets = {'nome': forms.TextInput(attrs={'placeholder': 'urgente'})}


# Formulários dos itens que vivem dentro de uma tarefa: a tela de detalhe preenche
# o campo `tarefa`, por isso ele não aparece em nenhum deles.

class SubtarefaForm(forms.ModelForm):
    class Meta:
        model = Subtarefa
        fields = ['descricao']
        labels = {'descricao': 'Nova subtarefa'}
        widgets = {'descricao': forms.TextInput(attrs={'placeholder': 'Mais um passo desta tarefa'})}


class ComentarioForm(forms.ModelForm):
    class Meta:
        model = Comentario
        fields = ['autor', 'texto']
        labels = {'autor': 'Autor', 'texto': 'Comentário'}
        widgets = {'texto': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Escreva um comentário'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['autor'].empty_label = 'Anônimo'


class AnexoForm(forms.ModelForm):
    class Meta:
        model = Anexo
        fields = ['arquivo', 'descricao']
        labels = {'arquivo': 'Arquivo', 'descricao': 'Descrição'}
        widgets = {'descricao': forms.TextInput(attrs={'placeholder': 'Do que se trata o arquivo?'})}

    def clean_arquivo(self):
        arquivo = self.cleaned_data['arquivo']
        if arquivo.size > TAMANHO_MAXIMO_ANEXO:
            limite = TAMANHO_MAXIMO_ANEXO // (1024 * 1024)
            raise forms.ValidationError(f'O arquivo passa de {limite} MB.')
        return arquivo


class RegistroTempoForm(forms.ModelForm):
    class Meta:
        model = RegistroTempo
        fields = ['responsavel', 'horas', 'data', 'observacao']
        labels = {
            'responsavel': 'Quem trabalhou',
            'horas': 'Horas',
            'data': 'Data',
            'observacao': 'Observação',
        }
        widgets = {
            'horas': forms.NumberInput(attrs={'step': '0.25', 'min': '0.25'}),
            'data': DataInput,
            'observacao': forms.TextInput(attrs={'placeholder': 'O que foi feito nesse tempo?'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data'].input_formats = ['%Y-%m-%d']
        self.fields['responsavel'].empty_label = 'Escolha quem trabalhou'
