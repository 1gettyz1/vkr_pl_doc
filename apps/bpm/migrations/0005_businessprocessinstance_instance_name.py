from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bpm", "0004_dictionary_selection_column"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessprocessinstance",
            name="instance_name",
            field=models.CharField(
                blank=True,
                help_text="Название экземпляра БП, которое задаёт оператор при запуске.",
                max_length=255,
            ),
        ),
    ]

