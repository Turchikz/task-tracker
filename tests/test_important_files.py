from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

import pytest

from tasks.models import ImportantFile, ImportantFileRevision


def upload(name, content=b"first version", content_type="application/pdf"):
    return SimpleUploadedFile(name, content, content_type=content_type)


@pytest.mark.django_db
def test_manager_adds_and_replaces_file_and_employee_reads_both_versions(client, manager, employee, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    create_url = reverse("important_file_create")
    assert client.get(reverse("important_files")).status_code == 302
    client.force_login(employee)
    assert client.get(reverse("important_files")).status_code == 200
    assert "Важные файлы" in client.get(reverse("my_today")).content.decode()
    assert client.post(create_url, {"title": "Инструкция", "upload": upload("old.pdf")}).status_code == 403

    client.force_login(manager)
    result = client.post(create_url, {"title": "Инструкция", "category": "guides", "description": "Для отдела", "upload": upload("old.pdf")})
    assert result.status_code == 302
    doc = ImportantFile.objects.get(title="Инструкция")
    first = doc.versions.get()
    assert first.file.name.startswith(f"important_files/{doc.pk}/")
    assert "Обновлено" in client.get(reverse("important_files")).content.decode()
    result = client.post(reverse("important_file_edit", args=[doc.pk]), {
        "title": "Инструкция обновлена", "category": "guides", "description": "Новая редакция",
        "upload": upload("new.pdf", b"second version"),
    })
    assert result.status_code == 302
    doc.refresh_from_db()
    assert doc.versions.count() == 2
    assert doc.updated_by == manager
    assert doc.versions.first().original_name == "new.pdf"

    client.force_login(employee)
    listing = client.get(reverse("important_files"), {"q": "обновлена", "category": "guides"})
    assert "new.pdf" in listing.content.decode()
    assert "old.pdf" in client.get(reverse("important_file_detail", args=[doc.pk])).content.decode()
    for version, expected in [(first, b"first version"), (doc.versions.first(), b"second version")]:
        response = client.get(reverse("important_file_download", args=[doc.pk, version.pk]))
        assert response.status_code == 200
        assert response["Content-Disposition"].startswith("attachment;")
        assert b"".join(response.streaming_content) == expected
    assert client.get(reverse("important_file_edit", args=[doc.pk])).status_code == 403


@pytest.mark.django_db
def test_file_validation_and_scoped_download(client, manager, employee, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client.force_login(manager)
    url = reverse("important_file_create")
    assert client.post(url, {"title": "Недопустимый", "category": "other", "upload": upload("run.html", b"<script></script>")}).status_code == 200
    assert client.post(url, {"title": "Пустой", "category": "other", "upload": upload("empty.pdf", b"")}).status_code == 200
    assert not ImportantFile.objects.exists()
    client.post(url, {"title": "Допустимый", "category": "other", "upload": upload("good.pdf")})
    doc = ImportantFile.objects.get()
    revision = ImportantFileRevision.objects.get(document=doc)
    another = ImportantFile.objects.create(title="Чужая карточка", category="other", created_by=manager, updated_by=manager)
    wrong_url = reverse("important_file_download", args=[another.pk, revision.pk])
    assert client.get(wrong_url).status_code == 404
    client.logout()
    assert client.get(reverse("important_file_download", args=[doc.pk, revision.pk])).status_code == 302
