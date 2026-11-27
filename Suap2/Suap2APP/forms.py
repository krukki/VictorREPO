import re
import unicodedata
from datetime import datetime, time, timedelta

from django import forms
from django.utils import timezone

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
        fields = ['titulo', 'prazo', 'prioridade', 'pessoa_responsavel', 'projeto', 'categoria', 'etiquetas']
        labels = {
            'titulo': 'Título',
            'prazo': 'Prazo',
            'prioridade': 'Prioridade',
            'pessoa_responsavel': 'Responsável',
            'projeto': 'Projeto',
            'categoria': 'Categoria',
            'etiquetas': 'Etiquetas',
        }
        widgets = {
            'titulo': forms.TextInput(attrs={'placeholder': 'O que precisa ser feito?'}),
            'prazo': DataHoraInput,
            'prioridade': forms.RadioSelect,
            'etiquetas': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['prazo'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['pessoa_responsavel'].empty_label = 'Escolha o responsável'
        self.fields['projeto'].empty_label = 'Sem projeto'
        self.fields['categoria'].empty_label = 'Sem categoria'
        # Sem prioridade no envio, fica a que a tarefa já tinha (ou Média, numa tarefa nova).
        # Preencher os dados, em vez de só tratar no clean, também evita que o campo conte
        # como alterado em changed_data (que vai para o histórico).
        if self.is_bound and not self.data.get('prioridade'):
            self.data = self.data.copy()
            self.data['prioridade'] = self.instance.prioridade

    def save(self, commit=True):
        # Prazo novo merece um lembrete novo
        if 'prazo' in self.changed_data:
            self.instance.lembrete_enviado_em = None
        return super().save(commit)


class TarefaFiltroForm(forms.Form):
    STATUS_CHOICES = [
        ('', 'Todas'),
        ('pendentes', 'Pendentes'),
        ('a_fazer', 'A fazer'),
        ('em_andamento', 'Em andamento'),
        ('atrasadas', 'Atrasadas'),
        ('concluidas', 'Concluídas'),
    ]
    ORDENAR_CHOICES = [
        ('', 'Prazo'),
        ('prioridade', 'Prioridade'),
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
    prioridade = forms.ChoiceField(
        label='Prioridade', choices=[('', 'Todas')] + Tarefa.PRIORIDADES, required=False,
    )
    ordenar = forms.ChoiceField(label='Ordenar por', choices=ORDENAR_CHOICES, required=False)

    def filtrar(self, tarefas, agora, com_status=True):
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
        if dados['prioridade']:
            tarefas = tarefas.filter(prioridade=dados['prioridade'])
        if not com_status:
            return tarefas
        if dados['status'] == 'pendentes':
            tarefas = tarefas.filter(concluida_em__isnull=True)
        elif dados['status'] == 'atrasadas':
            tarefas = tarefas.filter(concluida_em__isnull=True, prazo__lt=agora)
        elif dados['status'] == 'concluidas':
            tarefas = tarefas.filter(concluida_em__isnull=False)
        elif dados['status'] == 'a_fazer':
            tarefas = tarefas.a_fazer()
        elif dados['status'] == 'em_andamento':
            tarefas = tarefas.em_andamento()
        return tarefas

    def aplicar_ordem(self, tarefas):
        """Pendentes antes das concluídas sempre; dentro disso, prazo ou prioridade."""
        if self.is_valid() and self.cleaned_data['ordenar'] == 'prioridade':
            return tarefas.com_peso_da_prioridade().order_by(
                *Tarefa._meta.ordering[:1], 'peso_prioridade', 'prazo',
            )
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


# Adição rápida

def normalizar(texto):
    """Minúsculas e sem acento, para comparar "Amanhã" com "amanha" e "@Joao" com "João"."""
    sem_acento = unicodedata.normalize('NFKD', texto)
    return ''.join(c for c in sem_acento if not unicodedata.combining(c)).casefold()


DATA_CURTA = re.compile(r'(\d{1,2})/(\d{1,2})(?:/(\d{4}|\d{2}))?')
HORA = re.compile(r'(\d{1,2})(?:h(\d{2})?|:(\d{2}))', re.IGNORECASE)
HORA_PADRAO = time(17, 0)


class TarefaRapidaForm(forms.Form):
    """Cria uma tarefa a partir de uma linha de texto.

    Pedaços especiais do texto preenchem os campos e saem do título:
    `@nome` (responsável), `#etiqueta`, `!alta`/`!media`/`!baixa`,
    `hoje`/`amanhã`/`25/12` (dia do prazo) e `14h`/`14h30`/`14:30` (hora; sem hora, 17h).
    Sem `@nome`, vale o responsável escolhido na lista; sem dia nem hora, vale o prazo do campo
    e, se ele também estiver vazio, amanhã às 17h.
    """
    texto = forms.CharField(
        label='O que precisa ser feito?',
        max_length=300,
        widget=forms.TextInput(attrs={
            'placeholder': 'Ex.: Revisar o relatório amanhã 14h @ana #mensal !alta',
            'autocomplete': 'off',
            'class': 'rapida-texto',
        }),
    )
    pessoa_responsavel = forms.ModelChoiceField(
        label='Responsável',
        queryset=Responsavel.objects.all(),
        required=False,
        empty_label='Escolha ou use @nome',
    )
    prazo = forms.DateTimeField(label='Prazo', required=False, widget=DataHoraInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['prazo'].input_formats = ['%Y-%m-%dT%H:%M']

    def clean(self):
        dados = super().clean()
        texto = dados.get('texto')
        if not texto:
            return dados

        nomes, etiquetas, palavras = [], [], []
        prioridade, dia, hora = 'media', None, None
        hoje = timezone.localdate()
        for pedaco in texto.split():
            simples = normalizar(pedaco)
            if pedaco[0] in '@#' and len(pedaco) > 1:
                limpo = pedaco[1:].rstrip('.,;:!?')
                (nomes if pedaco[0] == '@' else etiquetas).append(limpo)
            elif simples[0] == '!' and simples[1:] in dict(Tarefa.PRIORIDADES):
                prioridade = simples[1:]
            elif simples in ('hoje', 'amanha'):
                dia = hoje if simples == 'hoje' else hoje + timedelta(days=1)
            elif m := DATA_CURTA.fullmatch(pedaco):
                dia = self._dia(m, hoje)
            elif m := HORA.fullmatch(pedaco):
                hora = self._hora(m)
            else:
                palavras.append(pedaco)

        titulo = ' '.join(palavras)
        if not titulo:
            self.add_error('texto', 'Escreva o que precisa ser feito.')
        elif len(titulo) > Tarefa._meta.get_field('titulo').max_length:
            self.add_error('texto', 'O título passa de 100 caracteres.')

        responsavel = self._responsavel(nomes) if nomes else dados.get('pessoa_responsavel')
        if responsavel is None and not self.has_error('pessoa_responsavel') and not nomes:
            self.add_error('pessoa_responsavel', 'Escolha o responsável ou escreva @nome no texto.')

        if dia or hora:
            if dia is None:
                dia = hoje + timedelta(days=1)
            prazo = timezone.make_aware(datetime.combine(dia, hora or HORA_PADRAO))
        elif dados.get('prazo'):
            prazo = dados['prazo']
        else:
            prazo = timezone.make_aware(datetime.combine(hoje + timedelta(days=1), HORA_PADRAO))

        dados.update(
            titulo=titulo,
            responsavel=responsavel,
            prazo=prazo,
            prioridade=prioridade,
            etiquetas=[e for e in (self._etiqueta(nome) for nome in etiquetas) if e],
        )
        return dados

    def _dia(self, m, hoje):
        dia, mes, ano = int(m[1]), int(m[2]), m[3]
        if ano:
            ano = int(ano) + (2000 if len(ano) == 2 else 0)
        try:
            data = hoje.replace(year=ano or hoje.year, month=mes, day=dia)
        except ValueError:
            self.add_error('texto', f'Data inválida: {m[0]}.')
            return None
        # Sem ano, um dia que já passou quer dizer o do ano que vem
        if not ano and data < hoje:
            data = data.replace(year=data.year + 1)
        return data

    def _hora(self, m):
        horas, minutos = int(m[1]), int(m[2] or m[3] or 0)
        if horas > 23 or minutos > 59:
            self.add_error('texto', f'Hora inválida: {m[0]}.')
            return None
        return time(horas, minutos)

    def _responsavel(self, nomes):
        procurado = normalizar(nomes[-1])
        responsaveis = list(Responsavel.objects.all())
        # Primeiro pelo começo do primeiro nome; se ninguém bater, pelo começo de qualquer nome
        achados = [r for r in responsaveis if normalizar(r.nome).startswith(procurado)]
        if not achados:
            achados = [r for r in responsaveis if any(p.startswith(procurado) for p in normalizar(r.nome).split())]
        if len(achados) == 1:
            return achados[0]
        if achados:
            nomes_achados = ', '.join(r.nome for r in achados[:3])
            self.add_error('texto', f'Mais de um responsável combina com @{nomes[-1]}: {nomes_achados}.')
        else:
            self.add_error('texto', f'Nenhum responsável combina com @{nomes[-1]}.')
        return None

    def _etiqueta(self, nome):
        procurado = normalizar(nome)
        for etiqueta in Etiqueta.objects.all():
            if normalizar(etiqueta.nome) == procurado:
                return etiqueta
        self.add_error('texto', f'A etiqueta #{nome} não existe.')
        return None

    def save(self):
        dados = self.cleaned_data
        tarefa = Tarefa.objects.create(
            titulo=dados['titulo'],
            prazo=dados['prazo'],
            prioridade=dados['prioridade'],
            pessoa_responsavel=dados['responsavel'],
        )
        tarefa.etiquetas.set(dados['etiquetas'])
        return tarefa
