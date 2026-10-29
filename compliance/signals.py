"""Re-evaluate compliance when documents are uploaded/validated or rules change."""
import threading
from contextlib import contextmanager

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from documents.models import Document
from faculty.models import Faculty
from requirements.models import PacucoaSubArea, Requirement

_state = threading.local()


@contextmanager
def suspended():
    """Temporarily disable automatic re-evaluation (bulk imports, the seeder)."""
    previous = getattr(_state, "suspended", False)
    _state.suspended = True
    try:
        yield
    finally:
        _state.suspended = previous


def _active():
    return not getattr(_state, "suspended", False)


def _evaluate_faculty_id(faculty_id):
    from .engine import evaluate_faculty

    faculty = Faculty.objects.filter(pk=faculty_id).first()
    if faculty:
        evaluate_faculty(faculty)


def _evaluate_all():
    from .engine import evaluate_all

    evaluate_all()


@receiver(post_save, sender=Document)
def document_saved(sender, instance, raw=False, **kwargs):
    if raw or not _active():
        return
    _evaluate_faculty_id(instance.faculty_id)


@receiver(post_delete, sender=Document)
def document_deleted(sender, instance, **kwargs):
    # Deferred: during a cascade delete of the faculty the row must not be re-created.
    if _active():
        faculty_id = instance.faculty_id
        transaction.on_commit(lambda: _evaluate_faculty_id(faculty_id))


@receiver(post_save, sender=Faculty)
def faculty_saved(sender, instance, raw=False, **kwargs):
    """Applicability depends on faculty attributes (graduate, licensure, study leave...)."""
    if raw or not _active():
        return
    _evaluate_faculty_id(instance.pk)


@receiver(post_save, sender=Requirement)
@receiver(post_save, sender=PacucoaSubArea)
def rule_saved(sender, raw=False, **kwargs):
    if raw or not _active():
        return
    _evaluate_all()


@receiver(post_delete, sender=Requirement)
def rule_deleted(sender, **kwargs):
    if _active():
        transaction.on_commit(_evaluate_all)
