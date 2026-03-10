from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0022_alter_userprofile_mobile'),
    ]

    operations = [
        migrations.RenameField(
            model_name='userprofile',
            old_name='mobile',
            new_name='email',
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='email',
            field=models.EmailField(blank=True, max_length=254),
        ),
    ]
