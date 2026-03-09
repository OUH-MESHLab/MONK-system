import os
import tempfile
from datetime import datetime

from django.db import IntegrityError
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.http import (
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseBadRequest,
    JsonResponse,
)
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from monklib import get_header, convert_to_csv, Data

from .models import Subject, File, FileImport, UserProfile, Project
from django.views.decorators.http import require_POST


def _has_file_access(request, file_obj):
    """Return True if the authenticated user has access to file_obj."""
    try:
        user_profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        return False
    subjects = Subject.objects.filter(file=file_obj)
    user_in_project = Project.objects.filter(
        subjects__in=subjects, users=user_profile
    ).exists()
    user_has_imported = FileImport.objects.filter(
        file=file_obj, user=user_profile
    ).exists()
    return user_in_project or user_has_imported


def process_and_create_subject(file, request):
    if file.file.name.lower().endswith(".mwf"):
        try:
            header = get_header(file.file.path)
            subject_id = getattr(header, "patientID", None)
            time_stamp = getattr(header, "measurementTimeISO", None)
            subject_name = getattr(header, "patientName", "Unknown")
            subject_sex = getattr(header, "patientSex", "Unknown")
            birth_date_str = getattr(header, "birthDateISO", None)
            birth_date = None
            if birth_date_str and birth_date_str != "N/A":
                try:
                    birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
                except ValueError:
                    pass

            ts = time_stamp or "no-timestamp"
            pid = subject_id or "no-patient-id"
            Subject.objects.create(
                subject_id=f"{ts} {pid}",
                name=subject_name,
                gender=subject_sex,
                birth_date=birth_date,
                file=file,
            )
            messages.success(request, f"Subject created for file {file.title}")
        except IntegrityError:
            messages.info(
                request,
                f"This subject already exists. No duplicate created for file {file.title}.",
            )
        except Exception as e:
            messages.error(
                request,
                f"Failed to process file {file.title} for subject creation: {str(e)}",
            )
    else:
        messages.info(
            request,
            f"File {file.title} imported but no subject created due to file type.",
        )


@login_required
@require_POST
def download_format_csv(request, file_id):
    selected_channels = request.POST.getlist("channels")
    start_time_str = request.POST.get("start_time")
    end_time_str = request.POST.get("end_time")
    start_seconds = float(start_time_str) if start_time_str else 0.0
    end_seconds = float(end_time_str) if end_time_str else 0.0

    file = get_object_or_404(File, id=file_id)
    if not _has_file_access(request, file):
        return HttpResponseForbidden("You do not have permission to access this file.")

    header = get_header(file.file.path)
    data = Data(file.file.path)

    for index, channel in enumerate(header.channels):
        data.setChannelSelection(index, channel.attribute in selected_channels)

    if start_time_str or end_time_str:
        data.setIntervalSelection(start_seconds, end_seconds)

    fd, tmp_path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        data.writeToCsv(tmp_path)
        with open(tmp_path, "rb") as f:
            response = HttpResponse(f.read(), content_type="text/csv")
        csv_name = os.path.splitext(os.path.basename(file.file.path))[0] + ".csv"
        response["Content-Disposition"] = f'attachment; filename="{csv_name}"'
        return response
    finally:
        os.unlink(tmp_path)


@login_required
def download_mfer_header(request, file_id):
    file_instance = get_object_or_404(File, id=file_id)
    if not _has_file_access(request, file_instance):
        return HttpResponseForbidden("You do not have permission to access this file.")

    file_path = file_instance.file.path
    try:
        if "anonymize" in request.POST and request.POST["anonymize"] == "true":
            anon_path = anonymize_data(file_path)
            try:
                header_info = get_header(anon_path)
            finally:
                os.unlink(anon_path)
        else:
            header_info = get_header(file_path)

        response = HttpResponse(header_info, content_type="text/plain")
        response["Content-Disposition"] = (
            f'attachment; filename="{file_instance.title}_header.txt"'
        )
        return response
    except Exception as e:
        return HttpResponse(
            f"An error occurred while retrieving the header: {str(e)}", status=500
        )


@login_required
def download_mwf(request, file_id):
    file_instance = get_object_or_404(File, id=file_id)
    if not _has_file_access(request, file_instance):
        return HttpResponseForbidden("You do not have permission to access this file.")

    if not file_instance.file.name.lower().endswith(".mwf"):
        return HttpResponseBadRequest("Unsupported file format.")

    try:
        file_path = file_instance.file.path
        if request.GET.get("anonymize") == "true":
            anon_path = anonymize_data(file_path)
            try:
                with open(anon_path, "rb") as f:
                    content = f.read()
            finally:
                os.unlink(anon_path)
        else:
            with open(file_path, "rb") as f:
                content = f.read()

        response = HttpResponse(content, content_type="application/octet-stream")
        response["Content-Disposition"] = (
            f'attachment; filename="{file_instance.title}.mwf"'
        )
        return response
    except Exception as e:
        return HttpResponse(
            f"An error occurred while reading the file: {str(e)}", status=500
        )


def anonymize_data(file_path):
    try:
        data = Data(file_path)
        data.anonymize()
        fd, anon_path = tempfile.mkstemp(suffix="_anonymized.mwf")
        os.close(fd)
        data.writeToBinary(anon_path)
        return anon_path
    except Exception as e:
        raise Exception(f"Failed to anonymize and save the file: {str(e)}")


@login_required
def plot_graph(request, file_id):
    combined = request.GET.get("combined", "false").lower() == "true"
    rows = int(request.GET.get("rows", 10000))
    file_instance = get_object_or_404(File, id=file_id)

    if not _has_file_access(request, file_instance):
        return JsonResponse(
            {"error": "You do not have permission to access this file."}, status=403
        )

    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            convert_to_csv(file_instance.file.path, tmp_path)
            df = pd.read_csv(tmp_path, nrows=rows)
        finally:
            os.unlink(tmp_path)

        df = df.apply(pd.to_numeric, errors="coerce").interpolate().dropna()

        if combined:
            fig = go.Figure()
            for column in df.columns:
                fig.add_trace(
                    go.Scatter(x=df.index, y=df[column], mode="lines", name=column)
                )
            fig.update_layout(
                title="Combined Graph", xaxis_title="Index", yaxis_title="Values"
            )
        else:
            fig = make_subplots(rows=len(df.columns), cols=1, shared_xaxes=True)
            for i, column in enumerate(df.columns):
                fig.add_trace(
                    go.Scatter(x=df.index, y=df[column], mode="lines", name=column),
                    row=i + 1,
                    col=1,
                )
            fig.update_layout(title="Multiple Subplots Graph")

        graph_html = fig.to_html(full_html=False, include_plotlyjs=True)
        return JsonResponse({"graph_html": graph_html})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
