from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Suap2APP', '0001_initial'),
    ]

    operations = [
        migrations.RenameModel(old_name='Todo', new_name='Tarefa'),
        migrations.AlterModelOptions(
            name='tarefa',
            options={'verbose_name': 'Tarefa', 'verbose_name_plural': 'Tarefas'},
        ),
        migrations.AlterField(
            model_name='tarefa',
            name='finished_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
