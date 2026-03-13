;;; Guix development environment for MONK-system.
;;; direnv loads this automatically via .envrc (use guix).
;;;
;;; python-monklib is loaded from guix/monk/packages.scm (the local channel
;;; module), so no extra `guix pull` or global channel configuration is needed.

(add-to-load-path (string-append (dirname (current-filename)) "/guix"))
(use-modules (monk packages))

(manifest
 (append
  (manifest-entries (packages->manifest (list python-monklib)))
  (manifest-entries
   (specifications->manifest
    '("gunicorn"
      ;; Python runtime
      "python"

      ;; Django and web
      "python-django"
      "python-asgiref"
      "python-sqlparse"
      "python-whitenoise"

      ;; Testing
      "python-pytest"
      "python-pytest-django"
      "python-pytest-cov"
      "python-coverage"
      "python-selenium"

      ;; Data processing
      "python-numpy"
      "python-pandas"
      "python-plotly"
      "python-pytz"
      "python-dateutil"
      "python-tzdata"

      ;; Code quality
      "python-black"
      "python-pylint"
      "python-isort"

      ;; Utilities
      "python-click"
      "python-six"
      "python-packaging"
      "python-tomlkit"
      "python-attrs")))))
