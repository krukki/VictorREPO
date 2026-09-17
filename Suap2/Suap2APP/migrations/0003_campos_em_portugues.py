from django.db import migrations, models


def nulos_para_vazio(apps, schema_editor):
    Responsavel = apps.get_model('Suap2APP', 'Responsavel')
    Responsavel.objects.filter(email__isnull=True).update(email='')
    Responsavel.objects.filter(telefone__isnull=True).update(telefone='')


class Migration(migrations.Migration):

    dependencies = [
        ('Suap2APP', '0002_ordering_protect_responsavel'),
    ]

    operations = [
        migrations.RenameField(model_name='tarefa', old_name='title', new_name='titulo'),
        migrations.RenameField(model_name='tarefa', old_name='created_at', new_name='criada_em'),
        migrations.RenameField(model_name='tarefa', old_name='deadline', new_name='prazo'),
        migrations.RenameField(model_name='tarefa', old_name='finished_at', new_name='concluida_em'),
        migrations.AlterModelOptions(
            name='tarefa',
            options={
                'ordering': [models.OrderBy(models.F('concluida_em'), nulls_first=True), 'prazo'],
                'verbose_name': 'Tarefa',
                'verbose_name_plural': 'Tarefas',
            },
        ),
        migrations.RunPython(nulos_para_vazio, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='responsavel',
            name='email',
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AlterField(
            model_name='responsavel',
            name='telefone',
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
