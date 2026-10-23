from pathlib import Path

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import ImportantFile, ImportantFileRevision
from .permissions import is_manager


ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".odt", ".ods", ".txt", ".csv", ".jpg", ".jpeg", ".png"}
MAX_FILE_SIZE = 20 * 1024 * 1024


class ImportantFileForm(forms.ModelForm):
    upload = forms.FileField(label="Файл", required=False, widget=forms.ClearableFileInput(attrs={"accept": ",".join(sorted(ALLOWED_EXTENSIONS))}))

    class Meta:
        model = ImportantFile
        fields = ["title", "category", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, require_file=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["upload"].required = require_file

    def clean_upload(self):
        upload = self.cleaned_data.get("upload")
        if upload:
            if Path(upload.name).suffix.lower() not in ALLOWED_EXTENSIONS:
                raise forms.ValidationError("Допустимы PDF, Word, Excel, ODT/ODS, текст и изображения JPG/PNG.")
            if not 0 < upload.size <= MAX_FILE_SIZE:
                raise forms.ValidationError("Размер файла должен быть от 1 байта до 20 МБ.")
        return upload


@login_required
def index(request):
    files = ImportantFile.objects.prefetch_related(Prefetch(
        "versions", queryset=ImportantFileRevision.objects.select_related("uploaded_by"), to_attr="saved_versions"
    ))
    query = request.GET.get("q", "").strip()[:100]
    category = request.GET.get("category", "")
    if query:
        files = files.filter(Q(title__icontains=query) | Q(description__icontains=query))
    if category in ImportantFile.Category.values:
        files = files.filter(category=category)
    return render(request, "tasks/important_files.html", {
        "files": files, "query": query, "category": category,
        "categories": ImportantFile.Category.choices,
    })


@login_required
@require_http_methods(["GET", "POST"])
def create(request):
    if not is_manager(request.user):
        return HttpResponseForbidden("Добавлять документы может только руководитель.")
    form = ImportantFileForm(request.POST or None, request.FILES or None, require_file=True)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            document = form.save(commit=False)
            document.created_by = document.updated_by = request.user
            document.save()
            upload = form.cleaned_data["upload"]
            ImportantFileRevision.objects.create(
                document=document, file=upload, original_name=Path(upload.name.replace("\\", "/")).name[:255],
                size_bytes=upload.size, uploaded_by=request.user,
            )
        messages.success(request, "Файл добавлен.")
        return redirect("important_file_detail", pk=document.pk)
    return render(request, "tasks/important_file_form.html", {"form": form, "document": None})


@login_required
def detail(request, pk):
    document = get_object_or_404(ImportantFile, pk=pk)
    versions = list(document.versions.select_related("uploaded_by"))
    return render(request, "tasks/important_file_detail.html", {"document": document, "versions": versions})


@login_required
@require_http_methods(["GET", "POST"])
def edit(request, pk):
    if not is_manager(request.user):
        return HttpResponseForbidden("Обновлять документы может только руководитель.")
    document = get_object_or_404(ImportantFile, pk=pk)
    form = ImportantFileForm(request.POST or None, request.FILES or None, instance=document)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            document = form.save(commit=False)
            document.updated_by = request.user
            document.save()
            upload = form.cleaned_data.get("upload")
            if upload:
                ImportantFileRevision.objects.create(
                    document=document, file=upload, original_name=Path(upload.name.replace("\\", "/")).name[:255],
                    size_bytes=upload.size, uploaded_by=request.user,
                )
        messages.success(request, "Файл обновлён. Предыдущая версия сохранена.")
        return redirect("important_file_detail", pk=document.pk)
    return render(request, "tasks/important_file_form.html", {"form": form, "document": document})


@login_required
def download(request, pk, revision_pk):
    revision = get_object_or_404(ImportantFileRevision, pk=revision_pk, document_id=pk)
    try:
        stream = revision.file.open("rb")
    except OSError as exc:
        raise Http404("Файл не найден в хранилище.") from exc
    response = FileResponse(stream, as_attachment=True, filename=revision.original_name, content_type="application/octet-stream")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
