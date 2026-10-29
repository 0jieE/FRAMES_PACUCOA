"""Copy encrypted documents from PRIVATE_MEDIA_ROOT into the StoredFile table.

The bytes are copied exactly as stored (still encrypted) - nothing is decrypted.
Run once when switching PRIVATE_STORAGE from "filesystem" to "database".
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from documents.models import Document, StoredFile


class Command(BaseCommand):
    help = "Copy encrypted document files from private_media/ into the database (StoredFile)."

    def handle(self, *args, **options):
        root = Path(settings.PRIVATE_MEDIA_ROOT)
        existing = set(StoredFile.objects.values_list("name", flat=True))
        names = [n for n in Document.objects.exclude(file="").values_list("file", flat=True).distinct() if n not in existing]
        copied, missing, batch = 0, [], []
        for name in names:
            path = root / name
            if not path.is_file():
                missing.append(name)
                continue
            token = path.read_bytes()
            batch.append(StoredFile(name=name, data=token, size=len(token)))
            if len(batch) >= 200:
                StoredFile.objects.bulk_create(batch)
                copied += len(batch)
                batch = []
        if batch:
            StoredFile.objects.bulk_create(batch)
            copied += len(batch)
        self.stdout.write(f"Already in database: {len(existing)}")
        self.stdout.write(self.style.SUCCESS(f"Copied: {copied}"))
        if missing:
            self.stdout.write(self.style.WARNING(f"Missing on disk ({len(missing)}): " + ", ".join(missing[:10])))
