;;; guix/monk/packages.scm — Guix package definitions for the MONK platform.
;;;
;;; Two packages are defined:
;;;   python-monklib  — the C++/pybind11 MFER waveform parsing library
;;;   monk            — the MONK Django web application

(define-module (monk packages)
  #:use-module (guix packages)
  #:use-module (guix utils)
  #:use-module (guix git-download)
  #:use-module (guix gexp)
  #:use-module (guix build-system cmake)
  #:use-module (guix build-system python)
  #:use-module ((guix licenses) #:prefix license:)
  ;; Python infrastructure
  #:use-module (gnu packages python)
  #:use-module (gnu packages python-xyz)    ; pybind11, python-numpy, python-wheel
  #:use-module (gnu packages python-science) ; python-pandas, python-plotly
  #:use-module (gnu packages python-web)    ; python-asgiref, gunicorn, python-whitenoise
  #:use-module (gnu packages django)        ; python-django
  #:use-module (gnu packages databases)     ; python-sqlparse
  #:use-module (gnu packages time))         ; python-pytz, python-dateutil, python-tzdata

;;;
;;; python-monklib
;;;

(define-public python-monklib
  (package
    (name "python-monklib")
    (version "0.2.4")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
             (url "https://github.com/OUH-MESHLab/MONK-library.git")
             (commit "e4885c10f4e34c9c5575123cf48afe2882357eed")))
       (file-name (git-file-name name version))
       (sha256
        (base32 "1hl26clc845jyzalffhahwzchw5x5ai817i65pshv11pjdm50168"))))
    (build-system cmake-build-system)
    (arguments
     (list
      #:tests? #f
      #:configure-flags
      #~(list "-DMONK_PYTHON_BINDINGS=ON"
              "-DMONK_BUILD_TOOLS=OFF"
              "-DBUILD_TESTING=OFF"
              ;; Override Python3_SITEARCH so the module installs under $out,
              ;; not into the Python store path.
              (string-append "-DPython3_SITEARCH="
                             #$output
                             "/lib/python"
                             #$(version-major+minor (package-version python))
                             "/site-packages"))))
    (inputs (list python))
    (native-inputs (list pybind11))
    (synopsis "MFER medical waveform parsing library (C++/pybind11)")
    (description
     "monklib is a C++ library with Python bindings (via pybind11) for reading
Nihon-Kohden MFER (.mwf) waveform files.  It provides header extraction,
waveform data access, and CSV conversion used by the MONK platform.")
    (home-page "https://github.com/OUH-MESHLab/MONK-library")
    (license license:expat)))


;;;
;;; monk
;;;

(define-public monk
  (package
    (name "monk")
    (version "0.1.0")
    (source
     ;; "../.." is resolved relative to this file (guix/monk/packages.scm),
     ;; giving the repo root.  local-file uses (current-source-directory)
     ;; internally so this works even when the module is pre-compiled to .go.
     ;; Channel checkouts are clean git clones, so no .venv/ or db.sqlite3
     ;; is present — no git-predicate filter needed.
     (local-file "../.." "monk-checkout" #:recursive? #t))
    (build-system python-build-system)
    (arguments
     (list
      #:tests? #f
      #:phases
      #~(modify-phases %standard-phases
          (delete 'build)
          (replace 'install
            (lambda* (#:key outputs #:allow-other-keys)
              (let* ((out   (assoc-ref outputs "out"))
                     (share (string-append out "/share/monk"))
                     (bin   (string-append out "/bin")))
                (mkdir-p share)
                (mkdir-p bin)
                ;; Copy the Django project tree (monksystem/).
                (copy-recursively "monksystem" share)

                ;; monk-manage: Python entry point so Guix's wrap phase
                ;; automatically sets PYTHONPATH to all runtime inputs.
                ;; DJANGO_SETTINGS_MODULE uses setdefault so the service
                ;; can override it by setting the variable before calling this.
                (call-with-output-file (string-append bin "/monk-manage")
                  (lambda (port)
                    (format port "\
#!/usr/bin/env python3
import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'monksystem.settings')
from django.core.management import execute_from_command_line
execute_from_command_line(sys.argv)
")))
                (chmod (string-append bin "/monk-manage") #o755)

                ;; monk-gunicorn: Python entry point for production WSGI serving.
                ;; Shepherd invokes this with the application and bind args.
                (call-with-output-file (string-append bin "/monk-gunicorn")
                  (lambda (port)
                    (format port "\
#!/usr/bin/env python3
import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'monksystem.settings')
from gunicorn.app.wsgiapp import run
run()
")))
                (chmod (string-append bin "/monk-gunicorn") #o755))))

          ;; Prepend $out/share/monk to PYTHONPATH before the standard wrap
          ;; phase runs.  Both calls are additive: the final wrapper will
          ;; have share/monk first, then all Python input site-packages.
          ;; Running before 'wrap avoids the double-.real rename conflict.
          (add-before 'wrap 'add-app-to-pythonpath
            (lambda* (#:key outputs #:allow-other-keys)
              (let* ((out   (assoc-ref outputs "out"))
                     (share (string-append out "/share/monk")))
                (for-each
                 (lambda (prog)
                   (wrap-program prog
                     `("PYTHONPATH" ":" prefix (,share))))
                 (find-files (string-append out "/bin")
                             "^monk-"))))))))
    (inputs
     (list python-monklib
           gunicorn
           python-django
           python-whitenoise
           python-numpy
           python-pandas
           python-plotly
           python-pytz
           python-dateutil
           python-tzdata
           python-sqlparse
           python-asgiref))
    (synopsis "MONK — Nihon-Kohden MFER medical waveform management platform")
    (description
     "MONK is a Django web application for managing and accessing Nihon-Kohden
MFER (.mwf) medical waveform data.  It provides role-based access control,
patient data anonymization, waveform visualization (Plotly), and CSV export.

After installation, initialise the database and start the server with:
@example
monk-manage migrate
monk-manage createsuperuser
monk-manage runserver
@end example")
    (home-page "https://github.com/OUH-MESHLab/MONK-library")
    (license license:expat)))
