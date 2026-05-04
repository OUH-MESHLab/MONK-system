# Changelog

All notable changes to MONK-system will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-04

First tagged release. Targeted at airgapped hospital kiosk deployment.

### Added
- Django web app for ingesting Nihon-Kohden MFER (`.mwf`) waveform files,
  with header parsing via `python-monklib`.
- Single-file and recursive multi-file import flows; case-insensitive
  `.mwf` matching; best-effort cleanup of empty source directories after
  import.
- Per-file detail page with MFER header download, raw `.mwf` download,
  CSV export (with absolute datetime column), and interactive Plotly
  visualisation with per-subplot time axes.
- Project- and subject-based access control: users see files they
  imported plus files belonging to subjects in their projects.
- Admin-approval user registration and in-app user management for staff.
- Kiosk-mode UX: inline USB-drive browser replaces browser download
  dialogs for CSV export; idle-logout after 15 minutes; no-cache
  middleware to avoid stale waveform pages.
- Reproducible bootstrap via `manifest.scm` + direnv (`use guix`);
  `python-monklib` packaged as a local Guix module.

### Security
- Session expires on browser close and after 15 minutes of inactivity.
- Django request errors logged to stderr (captured by gunicorn) — no
  filesystem permission dependency.
