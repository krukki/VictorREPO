from .views import e_visitante


def acesso(request):
    """`visitante`: está no modo visitante. `pode_editar`: pode ver os botões de alterar."""
    return {
        'visitante': e_visitante(request),
        'pode_editar': request.user.is_authenticated,
    }
