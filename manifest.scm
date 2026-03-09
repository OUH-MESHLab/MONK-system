;;; Guix development environment for MONK-system.
;;; direnv loads this automatically via .envrc (use guix).
;;; The .envrc handles building monklib (a C++/CMake extension not in Guix).

(specifications->manifest
 '("gunicorn"
   ;; Python runtime
   "python"

   ;; Django and web
   "python-django"
   "python-asgiref"
   "python-sqlparse"

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
   "python-attrs"

   ;; Build tools for compiling monklib (C++/CMake/pybind11 extension)
   "cmake"
   "ninja"
   "gcc-toolchain"
   "python-pip"

   ;; For cloning monklib with submodules
   "git"))
