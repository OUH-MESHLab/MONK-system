import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

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


EXPORT_BASE_DIR = "/run/media/monk"


def list_export_dirs():
    """Return a list of (name, path) tuples for each subdir of EXPORT_BASE_DIR."""
    base = Path(EXPORT_BASE_DIR)
    if not base.is_dir():
        return []
    return sorted(
        (entry.name, str(entry))
        for entry in base.iterdir()
        if entry.is_dir()
    )


MONK_USB_SCAN_LIMIT = 5000


def browse_usb_dir(path: str) -> dict:
    """List immediate children of path (dirs and .mwf files), validated under EXPORT_BASE_DIR."""
    base = Path(EXPORT_BASE_DIR).resolve()
    target = Path(path).resolve()
    target.relative_to(base)  # raises ValueError if outside base
    dirs, files = [], []
    for child in sorted(target.iterdir()):
        if child.name.startswith("."):
            continue
        if child.is_dir():
            dirs.append({"name": child.name, "path": str(child)})
        elif child.is_file() and child.suffix.lower() == ".mwf":
            files.append({"name": child.name, "path": str(child)})
    parent = str(target.parent) if target != base else None
    return {"path": str(target), "parent": parent, "dirs": dirs, "files": files}


def scan_usb_mwf_files(path: str) -> dict:
    """Recursively find .mwf files under path, validated under EXPORT_BASE_DIR.

    Stops after MONK_USB_SCAN_LIMIT files to avoid worker timeouts.
    Returns {"files": [...], "count": n, "truncated": bool}.
    """
    base = Path(EXPORT_BASE_DIR).resolve()
    target = Path(path).resolve()
    target.relative_to(base)  # raises ValueError if outside base
    files = []
    truncated = False
    for f in sorted(target.rglob("*")):
        if f.is_file() and f.suffix.lower() == ".mwf":
            files.append({"name": f.name, "path": str(f)})
            if len(files) >= MONK_USB_SCAN_LIMIT:
                truncated = True
                break
    return {"files": files, "count": len(files), "truncated": truncated}


def _safe_usb_file_path(abs_path: str) -> Path:
    """Validate abs_path is under EXPORT_BASE_DIR and return the resolved Path."""
    base = Path(EXPORT_BASE_DIR).resolve()
    candidate = Path(abs_path).resolve()
    candidate.relative_to(base)  # raises ValueError if outside base
    return candidate


def _safe_export_path(target_dir: str, filename: str) -> Path:
    """Return resolved destination path; raises ValueError if outside EXPORT_BASE_DIR."""
    base = Path(EXPORT_BASE_DIR).resolve()
    dest_dir = Path(target_dir).resolve()
    dest_dir.relative_to(base)  # raises ValueError if outside base
    dest = dest_dir / filename
    dest.relative_to(base)      # guard against filename tricks
    return dest


@login_required
@require_POST
def download_format_csv(request, file_id):
    selected_channels = request.POST.getlist("channels")
    start_time_str = request.POST.get("start_time")
    end_time_str = request.POST.get("end_time")
    export_dir = request.POST.get("export_dir", "").strip()
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

    csv_name = os.path.splitext(os.path.basename(file.file.path))[0] + ".csv"

    if export_dir:
        # Write directly to the chosen directory on external media
        try:
            dest_path = _safe_export_path(export_dir, csv_name)
        except ValueError:
            return JsonResponse({"error": "Invalid export directory."}, status=400)

        fd, tmp_path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            data.writeToCsv(tmp_path)
            shutil.move(tmp_path, str(dest_path))
        except Exception as e:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return JsonResponse({"error": f"Export failed: {e}"}, status=500)

        return JsonResponse({"status": "ok", "path": str(dest_path)})

    # Fallback: stream as browser download
    fd, tmp_path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        data.writeToCsv(tmp_path)
        with open(tmp_path, "rb") as f:
            response = HttpResponse(f.read(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{csv_name}"'
        return response
    finally:
        os.unlink(tmp_path)


@login_required
def download_mfer_header(request, file_id):
    file_instance = get_object_or_404(File, id=file_id)
    if not _has_file_access(request, file_instance):
        return HttpResponseForbidden("You do not have permission to access this file.")

    anonymize = (
        request.POST.get("anonymize") == "true"
        or request.GET.get("anonymize") == "true"
    )
    export_dir = request.POST.get("export_dir", "").strip()
    file_path = file_instance.file.path
    header_name = f"{file_instance.title}_header.txt"

    try:
        if anonymize:
            anon_path = anonymize_data(file_path)
            try:
                header_info = get_header(anon_path)
            finally:
                os.unlink(anon_path)
        else:
            header_info = get_header(file_path)
    except Exception as e:
        if export_dir:
            return JsonResponse(
                {"error": f"Failed to read header: {e}"}, status=500
            )
        return HttpResponse(
            f"An error occurred while retrieving the header: {str(e)}", status=500
        )

    if export_dir:
        try:
            dest_path = _safe_export_path(export_dir, header_name)
        except ValueError:
            return JsonResponse({"error": "Invalid export directory."}, status=400)
        try:
            with open(dest_path, "w") as f:
                f.write(str(header_info))
        except Exception as e:
            return JsonResponse({"error": f"Export failed: {e}"}, status=500)
        return JsonResponse({"status": "ok", "path": str(dest_path)})

    # Fallback: stream as browser download (used by tests; hidden from kiosk UI).
    response = HttpResponse(header_info, content_type="text/plain")
    response["Content-Disposition"] = f'attachment; filename="{header_name}"'
    return response


@login_required
def download_mwf(request, file_id):
    file_instance = get_object_or_404(File, id=file_id)
    if not _has_file_access(request, file_instance):
        return HttpResponseForbidden("You do not have permission to access this file.")

    if not file_instance.file.name.lower().endswith(".mwf"):
        return HttpResponseBadRequest("Unsupported file format.")

    anonymize = (
        request.POST.get("anonymize") == "true"
        or request.GET.get("anonymize") == "true"
    )
    export_dir = request.POST.get("export_dir", "").strip()
    file_path = file_instance.file.path
    mwf_name = f"{file_instance.title}.mwf"

    try:
        if anonymize:
            source_path = anonymize_data(file_path)
            cleanup_source = True
        else:
            source_path = file_path
            cleanup_source = False
    except Exception as e:
        if export_dir:
            return JsonResponse({"error": f"Anonymize failed: {e}"}, status=500)
        return HttpResponse(
            f"An error occurred while reading the file: {str(e)}", status=500
        )

    try:
        if export_dir:
            try:
                dest_path = _safe_export_path(export_dir, mwf_name)
            except ValueError:
                return JsonResponse(
                    {"error": "Invalid export directory."}, status=400
                )
            try:
                shutil.copyfile(source_path, str(dest_path))
            except Exception as e:
                return JsonResponse({"error": f"Export failed: {e}"}, status=500)
            return JsonResponse({"status": "ok", "path": str(dest_path)})

        # Fallback: stream as browser download (used by tests; hidden from kiosk UI).
        with open(source_path, "rb") as f:
            content = f.read()
        response = HttpResponse(content, content_type="application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="{mwf_name}"'
        return response
    finally:
        if cleanup_source:
            try:
                os.unlink(source_path)
            except OSError:
                pass


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
            # Count total rows to determine stride for even sampling across the
            # full recording (avoids dropping channels that only appear later).
            with open(tmp_path) as _f:
                total_rows = sum(1 for _ in _f) - 1  # subtract header
            stride = max(1, total_rows // rows)
            if stride > 1:
                df = pd.read_csv(
                    tmp_path,
                    skiprows=lambda i: i > 0 and (i - 1) % stride != 0,
                )
            else:
                df = pd.read_csv(tmp_path)
        finally:
            os.unlink(tmp_path)

        df = df.apply(pd.to_numeric, errors="coerce")
        df = df.dropna(axis=1, how="all")  # drop channels with no data at all
        df = df.ffill().bfill()            # fill gaps from multi-rate channels

        # Use the time column as x-axis if present, otherwise fall back to row index
        time_col = next((c for c in df.columns if c.strip().lower().startswith("time")), None)
        x = df[time_col] if time_col is not None else df.index
        x_label = "Time (s)" if time_col is not None else "Index"
        signal_cols = [c for c in df.columns if c != time_col]

        # Parse "NAME: MANTISSAx10^EXP (UNIT)" column headers to scale to physical units
        _col_re = re.compile(r"^\s*(.+?):\s*([\d.]+)x10\^(-?\d+)\s*\((.+?)\)\s*$")

        def _parse_col(col):
            m = _col_re.match(col)
            if m:
                name, mantissa, exp, unit = m.group(1), float(m.group(2)), int(m.group(3)), m.group(4)
                return name.strip(), mantissa * 10 ** exp, unit.strip()
            return col.strip(), 1.0, ""

        _SI = [(1e12,"T"),(1e9,"G"),(1e6,"M"),(1e3,"k"),(1,""),(1e-3,"m"),(1e-6,"μ"),(1e-9,"n"),(1e-12,"p")]

        def _human_scale(series, unit):
            """Rescale series to a human-readable SI range; return (scaled_series, new_unit)."""
            max_abs = series.abs().max()
            if max_abs == 0 or pd.isna(max_abs):
                return series, unit
            for factor, prefix in _SI:
                if max_abs >= factor * 0.5:
                    return series / factor, f"{prefix}{unit}"
            return series, unit

        if combined:
            fig = go.Figure()
            for column in signal_cols:
                name, mult, unit = _parse_col(column)
                y, scaled_unit = _human_scale(df[column] * mult, unit)
                label = f"{name} ({scaled_unit})" if scaled_unit else name
                fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=label))
            fig.update_layout(
                title="Combined Graph", xaxis_title=x_label, yaxis_title="Values"
            )
        else:
            fig = make_subplots(
                rows=len(signal_cols), cols=1, shared_xaxes=True,
                subplot_titles=[_parse_col(c)[0] for c in signal_cols],
            )
            for i, column in enumerate(signal_cols):
                name, mult, unit = _parse_col(column)
                y, scaled_unit = _human_scale(df[column] * mult, unit)
                label = f"{name} ({scaled_unit})" if scaled_unit else name
                fig.add_trace(
                    go.Scatter(x=x, y=y, mode="lines", name=label),
                    row=i + 1, col=1,
                )
                fig.update_yaxes(title_text=scaled_unit, row=i + 1, col=1)
            fig.update_layout(title="Waveform", height=300 * len(signal_cols))

        # Apply to ALL axes — for_each_* guarantees every subplot axis is reached
        fig.for_each_yaxis(lambda ax: ax.update(exponentformat="none", tickformat=".6~g"))
        fig.for_each_xaxis(lambda ax: ax.update(exponentformat="none", tickformat=".6~g"))

        graph_html = fig.to_html(
            full_html=True,
            include_plotlyjs=True,
            div_id="graph",
        )
        inject = (
            '<div id="_monk_loading" style="'
            'position:fixed;inset:0;background:#fff;z-index:9999;'
            'display:flex;align-items:center;justify-content:center;'
            'flex-direction:column;gap:1rem;font-family:sans-serif;">'
            '<div style="width:48px;height:48px;border:5px solid #e2e8f0;'
            'border-top-color:#2563eb;border-radius:50%;'
            'animation:_spin 0.8s linear infinite;"></div>'
            '<span style="color:#64748b;">Loading plot\u2026</span>'
            '</div>'
            '<style>@keyframes _spin{to{transform:rotate(360deg)}}</style>'
            '<div style="padding:8px">'
            '<button onclick="window.close()" '
            'style="font-size:1rem;padding:6px 16px;cursor:pointer">&#x2715; Close</button>'
            '</div>'
            '<script>'
            'window.addEventListener("load",function(){'
            'var el=document.getElementById("_monk_loading");'
            'if(el)el.style.display="none";'
            '});'
            '</script>'
        )
        html = graph_html.replace("<body>", f"<body>{inject}", 1)
        return HttpResponse(html, content_type="text/html")
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
