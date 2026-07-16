from django.db import migrations
from django.db.models import Q


def backfill_broken_slugs(apps, schema_editor):
    """
    Repair App rows whose slug cannot be reversed by the <slug:...> URL
    converter, which requires at least one character.

    App.save() used to set slug = slugify(name), and slugify() strips
    non-ASCII characters. An app named entirely in e.g. Korean therefore got
    slug='' (and subsequent ones got counter-only slugs like '-1'), crashing
    /dashboard/ with NoReverseMatch for every app of that user.
    """
    App = apps.get_model('analytics', 'App')
    broken = App.objects.filter(Q(slug='') | Q(slug__startswith='-'))
    for app in broken:
        base_slug = f"app-{str(app.id)[:8]}"
        slug = base_slug
        counter = 1
        while App.objects.filter(slug=slug).exclude(id=app.id).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        app.slug = slug
        app.save(update_fields=['slug'])


class Migration(migrations.Migration):

    dependencies = [
        ('analytics', '0013_add_deletion_log_model'),
    ]

    operations = [
        migrations.RunPython(backfill_broken_slugs, migrations.RunPython.noop),
    ]
