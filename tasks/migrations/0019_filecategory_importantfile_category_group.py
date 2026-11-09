from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ('tasks', '0018_tasktag_task_tags'),
    ]

    operations = [
        migrations.CreateModel(
            name='FileCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='Название категории')),
                ('slug', models.SlugField(blank=True, unique=True, verbose_name='Слаг (для URL)')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активна')),
            ],
            options={
                'verbose_name': 'Категория важных файлов',
                'verbose_name_plural': 'Категории важных файлов',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='importantfile',
            name='category_group',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='important_files', to='tasks.filecategory', verbose_name='Группа категории'),
        ),
    ]