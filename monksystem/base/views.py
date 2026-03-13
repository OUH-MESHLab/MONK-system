import os
from pathlib import Path

from django.conf import settings
from django.core.files import File as DjangoFile
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.contrib.auth import authenticate, login, logout

from monklib import get_header

from .models import Subject, UserProfile, Project, File, FileImport
from .forms import FileForm, UserRegistrationForm, FileFieldForm, EditProfileForm
from .utils import (
    process_and_create_subject,
    download_format_csv,
    download_mfer_header,
    download_mwf,
    plot_graph,
    list_export_dirs,
)


@login_required
@require_GET
def home_page(request):
    return render(request, "base/home.html")


@login_required
@require_GET
def subject(request, pk):
    subj = get_object_or_404(Subject, subject_id=pk)
    context = {"subject": subj}
    return render(request, "base/subject.html", context)


@login_required
@require_GET
def user(request, pk):
    usr = get_object_or_404(UserProfile, id=pk)
    try:
        viewer_profile = request.user.userprofile
        shared_projects = Project.objects.filter(users=usr).filter(users=viewer_profile)
    except UserProfile.DoesNotExist:
        shared_projects = Project.objects.none()
    context = {"user": usr, "shared_projects": shared_projects}
    return render(request, "base/user.html", context)


@login_required
def edit_profile(request):
    try:
        user_profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profile not found.")
        return redirect("home")

    if request.method == "POST":
        form = EditProfileForm(request.POST, instance=user_profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("user", pk=user_profile.id)
    else:
        form = EditProfileForm(instance=user_profile)

    return render(request, "base/edit_profile.html", {"form": form})


@login_required
@require_GET
def project(request, pk):
    proj = get_object_or_404(Project, id=pk)
    context = {"project": proj}
    return render(request, "base/project.html", context)


@login_required
def file(request, file_id):
    file = get_object_or_404(File, id=file_id)
    user_profile = request.user.userprofile
    subjects = Subject.objects.filter(file=file)
    projects = Project.objects.filter(subjects__in=subjects)
    user_in_project = projects.filter(users=user_profile).exists()
    user_has_imported = FileImport.objects.filter(file=file, user=user_profile).exists()

    if not (user_in_project or user_has_imported):
        return HttpResponseForbidden("You do not have permission to view this file.")

    is_MFER_file = file.file.name.lower().endswith(".mwf")
    is_text_file = file.file.name.lower().endswith(".txt")
    content = None

    if is_MFER_file:
        try:
            content = get_header(file.file.path)
        except Exception as e:
            content = f"Error reading file: {e}"
    elif is_text_file:
        try:
            with open(file.file.path, "r") as f:
                content = f.read()
        except Exception as e:
            content = f"Error reading file: {e}"

    context = {
        "file": file,
        "content": content,
        "is_text_file": is_text_file,
        "is_MFER_file": is_MFER_file,
    }
    return render(request, "base/file.html", context)


def login_page(request):
    page = "login"
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        username = request.POST.get("username").lower()
        password = request.POST.get("password")
        try:
            User.objects.get(username=username)
        except User.DoesNotExist:
            messages.error(request, "User does not exist")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Logged in successfully as {user.username}.")
            return redirect("home")
        else:
            messages.error(request, "Username or password does not exist")

    context = {"page": page}
    return render(request, "base/login_register.html", context)


def logout_user(request):
    logout(request)
    return redirect("home")


def register_page(request):
    form = UserRegistrationForm()

    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.username = user.username.lower()
            user.save()
            UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    "name": form.cleaned_data.get("name"),
                    "email": form.cleaned_data.get("email", ""),
                },
            )
            login(request, user)
            return redirect("home")
        else:
            messages.error(request, "An error occurred during registration")

    context = {"form": form}
    return render(request, "base/login_register.html", context)


@login_required
@require_GET
def view_subjects(request):
    try:
        user_profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        subjects = Subject.objects.none()
    else:
        subjects = Subject.objects.filter(
            Q(projects__users=user_profile) | Q(file__fileimport__user=user_profile)
        ).distinct()
    context = {"subjects": subjects}
    return render(request, "base/view_subjects.html", context)


@login_required
@require_GET
def view_projects(request):
    try:
        user_profile = request.user.userprofile
        projects = Project.objects.filter(users=user_profile)
    except UserProfile.DoesNotExist:
        projects = Project.objects.none()
    context = {"projects": projects}
    return render(request, "base/view_projects.html", context)


@login_required
@require_GET
def view_files(request):
    try:
        user_profile = request.user.userprofile
        files = File.objects.filter(
            fileimport__user=user_profile, subjects__isnull=False
        ).distinct()
    except UserProfile.DoesNotExist:
        files = File.objects.none()
    context = {"files": files}
    return render(request, "base/view_files.html", context)


@login_required
def add_project(request):
    if request.method == "POST":
        rekNummer = request.POST.get("rekNummer")
        description = request.POST.get("description")
        user_ids = request.POST.getlist("users")
        subject_ids = request.POST.getlist("subjects")

        project = Project.objects.create(rekNummer=rekNummer, description=description)
        project.users.set(UserProfile.objects.filter(id__in=user_ids))

        valid_subjects = Subject.objects.filter(
            id__in=subject_ids, file__fileimport__user__id__in=user_ids
        )
        project.subjects.set(valid_subjects)

        messages.success(request, "Project added successfully.")
        return redirect("view_projects")
    else:
        users = UserProfile.objects.all()
        try:
            user_profile = request.user.userprofile
            subjects = Subject.objects.filter(file__fileimport__user=user_profile)
        except UserProfile.DoesNotExist:
            subjects = Subject.objects.none()
        return render(
            request, "base/add_project.html", {"users": users, "subjects": subjects}
        )


@login_required
def edit_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    try:
        user_profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        messages.error(request, "You are not registered as a regular user.")
        return redirect("view_projects")

    if request.method == "POST":
        user_ids = request.POST.getlist("users")
        new_subject_ids = set(map(int, request.POST.getlist("subjects")))

        existing_subject_ids = set(project.subjects.values_list("id", flat=True))

        allowed_subject_ids = set(
            Subject.objects.filter(file__fileimport__user=user_profile).values_list(
                "id", flat=True
            )
        )

        valid_new_subject_ids = new_subject_ids.intersection(allowed_subject_ids)
        updated_subject_ids = existing_subject_ids.union(valid_new_subject_ids)

        subjects_to_remove = allowed_subject_ids.intersection(
            existing_subject_ids.difference(new_subject_ids)
        )
        final_subject_ids = updated_subject_ids.difference(subjects_to_remove)

        project.users.set(UserProfile.objects.filter(id__in=user_ids))
        project.subjects.set(Subject.objects.filter(id__in=final_subject_ids))

        project.save()
        messages.success(request, "Project updated successfully.")
        return redirect("view_projects")
    else:
        users = UserProfile.objects.all()
        subjects = Subject.objects.filter(
            id__in=project.subjects.values_list("id", flat=True)
            | Subject.objects.filter(file__fileimport__user=user_profile).values_list(
                "id", flat=True
            )
        )
        context = {"project": project, "users": users, "subjects": subjects}
        return render(request, "base/edit_project.html", context)


@login_required
def leave_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    try:
        user_profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        messages.error(request, "You are not registered as a regular user.")
        return redirect("view_projects")

    if user_profile in project.users.all():
        project.users.remove(user_profile)
        project.save()
        messages.success(request, "You have successfully left the project.")
    else:
        messages.error(request, "You are not a member of this project.")
    return redirect("view_projects")


@login_required
def import_file(request):
    form = FileForm()
    if request.method == "POST" and "submitted" in request.POST:
        form = FileForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                user_profile = request.user.userprofile
            except UserProfile.DoesNotExist:
                messages.error(request, "You are not registered as a regular user.")
                return redirect("view_files")

            new_file = form.save()
            FileImport.objects.create(user=user_profile, file=new_file)
            process_and_create_subject(new_file, request)

            messages.success(request, "File imported and processed successfully.")
            return redirect("view_files")
        else:
            messages.error(request, "Please choose title and upload .MWF files only")
    server_import = bool(getattr(settings, "FILE_IMPORT_BASE_DIR", ""))
    return render(request, "base/import_file.html", {"form": form, "server_import": server_import})


@login_required
def import_multiple_files(request):
    form = FileFieldForm()
    if request.method == "POST":
        form = FileFieldForm(request.POST, request.FILES)
        if form.is_valid():
            files = request.FILES.getlist("file_field")
            valid_files = [f for f in files if f.name.lower().endswith(".mwf")]
            for name in [f.name for f in files if not f.name.lower().endswith(".mwf")]:
                messages.error(
                    request, f"Only .MWF files are allowed. Invalid file: {name}"
                )

            if valid_files:
                try:
                    user_profile = request.user.userprofile
                except UserProfile.DoesNotExist:
                    messages.error(request, "You are not registered as a regular user.")
                    return redirect("view_files")

                for f in valid_files:
                    base_title = os.path.splitext(f.name)[0]
                    new_file = File.objects.create(file=f, title=base_title)
                    FileImport.objects.create(user=user_profile, file=new_file)
                    process_and_create_subject(new_file, request)

                messages.success(
                    request, "All valid .MWF files imported and processed successfully."
                )
            else:
                messages.error(request, "No valid .MWF files provided.")
            return redirect("view_files")
        else:
            messages.error(request, "Only .MWF files allowed.")
    return render(request, "base/import_file.html", {"form": form})


def _safe_import_path(base_dir: str, name: str) -> Path:
    """Return the resolved path for *name* inside *base_dir*.

    Raises ValueError if the resolved path escapes *base_dir*, blocking any
    directory-traversal attempt (e.g. '../../../etc/passwd').
    """
    base = Path(base_dir).resolve()
    candidate = (base / name).resolve()
    candidate.relative_to(base)  # raises ValueError if outside base
    return candidate


@login_required
def import_from_directory(request):
    """List .mwf files from FILE_IMPORT_BASE_DIR and import selected ones.

    No browser file dialog is involved: files are read directly from the
    server-side incoming directory (typically the Samba share).
    """
    base_dir = getattr(settings, "FILE_IMPORT_BASE_DIR", "")
    if not base_dir:
        messages.error(request, "Directory import is not configured on this server.")
        return redirect("view_files")

    if request.method == "POST":
        filenames = request.POST.getlist("filenames")
        if not filenames:
            messages.error(request, "No files selected.")
            return redirect("import_from_directory")

        try:
            user_profile = request.user.userprofile
        except UserProfile.DoesNotExist:
            messages.error(request, "You are not registered as a regular user.")
            return redirect("view_files")

        imported = 0
        for name in filenames:
            if not name.lower().endswith(".mwf"):
                messages.error(request, f"Skipped non-.mwf file: {name}")
                continue
            try:
                safe_path = _safe_import_path(base_dir, name)
            except ValueError:
                messages.error(request, f"Invalid filename rejected: {name}")
                continue
            if not safe_path.is_file():
                messages.error(request, f"File no longer available: {name}")
                continue
            with open(safe_path, "rb") as fh:
                django_file = DjangoFile(fh, name=safe_path.name)
                title = safe_path.stem
                new_file = File.objects.create(file=django_file, title=title)
                FileImport.objects.create(user=user_profile, file=new_file)
                process_and_create_subject(new_file, request)
            safe_path.unlink(missing_ok=True)
            imported += 1

        if imported:
            messages.success(request, f"{imported} file(s) imported successfully.")
        return redirect("view_files")

    # GET: list available .mwf files
    try:
        base_path = Path(base_dir).resolve()
        available = sorted(
            f.name for f in base_path.iterdir()
            if f.is_file() and f.suffix.lower() == ".mwf"
        )
    except OSError as exc:
        messages.error(request, f"Cannot read import directory: {exc}")
        available = []

    return render(request, "base/import_from_directory.html", {
        "available_files": available,
        "base_dir": base_dir,
    })


@login_required
@require_GET
def list_export_dirs_view(request):
    """Return JSON list of available export directories under /run/media/rafael."""
    dirs = [{"name": name, "path": path} for name, path in list_export_dirs()]
    return JsonResponse({"dirs": dirs})
