import uuid
from datetime import datetime

import factory
from django.utils.timezone import make_aware
from files.models import File


class FileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = File
        # Exclude trait names from being passed to the model constructor
        exclude = ("deleted", "multiple_refs")

    # Traits defined as class attributes again
    deleted = factory.Trait(
        is_deleted=True,
        ref_count=0,  # Typically deleted files have ref_count decremented to 0 or 1 before marking deleted
    )
    multiple_refs = factory.Trait(
        ref_count=factory.LazyFunction(lambda: 3)  # Example with 3 refs
    )

    id = factory.LazyFunction(uuid.uuid4)
    file = factory.django.FileField(
        filename="test_file.txt", data=b"file content"
    )  # Simple default
    file_path = factory.LazyAttribute(lambda o: o.file.name if o.file else None)
    file_hash = factory.Sequence(lambda n: f"testhash_{n:03d}")
    size = factory.LazyAttribute(lambda o: o.file.size if o.file else 100)
    uploaded_at = factory.LazyFunction(lambda: make_aware(datetime.now()))
    ref_count = 1
    original_filename = factory.LazyAttribute(
        lambda o: o.file.name if o.file else "default_name.txt"
    )
    file_type = factory.LazyAttribute(
        lambda o: (
            o.original_filename.split(".")[-1] if "." in o.original_filename else "txt"
        )
    )
    is_deleted = False
    version = 0
