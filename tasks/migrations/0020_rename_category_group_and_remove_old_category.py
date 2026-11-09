from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ('tasks', '0019_filecategory_importantfile_category_group'),
    ]

    operations = [
        # Удаляем старое поле category (CharField)
        migrations.RemoveField(
            model_name='importantfile',
            name='category',
        ),
        # Переименовываем category_group в category
        migrations.RenameField(
            model_name='importantfile',
            old_name='category_group',
            new_name='category',
        ),
        # Меняем on_delete с SET_NULL на PROTECT (опционально)
        migrations.AlterField(
            model_name='importantfile',
            name='category',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='important_files',
                to='tasks.filecategory',
                verbose_name='Категория'
            ),
        ),
    ]