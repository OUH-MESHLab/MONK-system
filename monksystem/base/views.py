import os

from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.contrib.auth import authenticate, login, logout

from monklib import get_header

from .models import Subject, UserProfile, Project, File, FileImport
from .forms import FileForm, UserRegistrationForm, FileFieldForm
from .utils import (
    process_and_create_subject,
    download_format_csv,
    download_mfer_header,
    download_mwf,
    plot_graph,
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
    context = {"user": usr}
    return render(request, "base/user.html", context)


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
            UserProfile.objects.create(
                user=user,
                name=form.cleaned_data.get("name"),
                mobile=form.cleaned_data.get("mobile"),
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
    return render(request, "base/import_file.html", {"form": form})


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
