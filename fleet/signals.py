"""Removes photo files from disk when a photo (or the car it belongs to) is deleted."""
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import CarPhoto


@receiver(post_delete, sender=CarPhoto)
def delete_photo_files(sender, instance, **kwargs):
    files = [(f.storage, f.name) for f in (instance.image, instance.thumbnail) if f and f.name]

    def remove():
        for storage, name in files:
            storage.delete(name)

    # Only once the database change is saved, so a rolled-back delete keeps its files.
    transaction.on_commit(remove)
