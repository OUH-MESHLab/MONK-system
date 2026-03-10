;;; guix/monk/services.scm — Guix System service for the MONK platform.
;;;
;;; Provides monk-service-type, which:
;;;   • creates a dedicated system user/group
;;;   • writes /etc/monk/monk_settings.py from the configuration record
;;;   • runs Django migrations on every activation
;;;   • runs the app under gunicorn via a Shepherd daemon

(define-module (monk services)
  #:use-module (gnu services)
  #:use-module (gnu services shepherd)
  #:use-module (gnu system shadow)          ; user-account, user-group
  #:use-module (gnu packages admin)         ; shadow (nologin shell)
  #:use-module (guix gexp)
  #:use-module (guix records)
  #:use-module (monk packages)
  #:export (monk-configuration
            monk-configuration?
            monk-configuration-package
            monk-configuration-host
            monk-configuration-port
            monk-configuration-workers
            monk-configuration-secret-key
            monk-configuration-allowed-hosts
            monk-configuration-data-directory
            monk-configuration-file-import-base-dir
            monk-configuration-user
            monk-configuration-group
            monk-service-type))


;;;
;;; Configuration record
;;;

(define-record-type* <monk-configuration>
  monk-configuration make-monk-configuration
  monk-configuration?
  ;; Package to deploy.
  (package         monk-configuration-package         (default monk))
  ;; Network interface and port gunicorn binds to.
  (host            monk-configuration-host             (default "127.0.0.1"))
  (port            monk-configuration-port             (default 8000))
  ;; Number of gunicorn worker processes.
  (workers         monk-configuration-workers          (default 4))
  ;; Django SECRET_KEY — must be set; no default to avoid accidental insecurity.
  (secret-key      monk-configuration-secret-key       (default #f))
  ;; Django ALLOWED_HOSTS list.
  (allowed-hosts   monk-configuration-allowed-hosts    (default '("localhost" "127.0.0.1")))
  ;; Directory for the SQLite database and uploaded media files.
  (data-directory  monk-configuration-data-directory   (default "/var/lib/monk"))
  ;; Directory from which clinicians can import .mwf files directly via the
  ;; web UI, bypassing the browser file dialog.  Typically the Samba incoming
  ;; share.  Empty string disables the feature.
  (file-import-base-dir monk-configuration-file-import-base-dir (default ""))
  ;; System user and group the daemon runs as.
  (user            monk-configuration-user             (default "monk"))
  (group           monk-configuration-group            (default "monk")))


;;;
;;; Shepherd start script
;;;
;;; A program-file stored in /gnu/store is used so that the gunicorn command
;;; and its arguments are fixed at configuration-build time, and so that
;;; shepherd tracks the actual gunicorn master PID (execv replaces the
;;; Guile process with gunicorn).
;;;

(define (monk-start-script config)
  (let* ((pkg     (monk-configuration-package config))
         (gunicorn-bin (file-append pkg "/bin/monk-gunicorn"))
         (host    (monk-configuration-host config))
         (port    (number->string (monk-configuration-port config)))
         (workers (number->string (monk-configuration-workers config)))
         (bind    (string-append host ":" port)))
    (program-file "monk-start"
      #~(begin
          ;; Override DJANGO_SETTINGS_MODULE so the gunicorn entry-point
          ;; uses the deployment settings instead of the dev defaults.
          (setenv "DJANGO_SETTINGS_MODULE" "monk_settings")
          ;; Prepend /etc/monk to PYTHONPATH so monk_settings.py is
          ;; importable.  The monk-gunicorn Guix wrapper will further
          ;; prepend /share/monk and all Python input site-packages.
          (let ((existing (getenv "PYTHONPATH")))
            (setenv "PYTHONPATH"
                    (if existing
                        (string-append "/etc/monk:" existing)
                        "/etc/monk")))
          ;; exec replaces this Guile process with gunicorn so that
          ;; shepherd's PID tracking points to the gunicorn master.
          ;; Guile exposes execl (variadic), not execv; use apply.
          (apply execl #$gunicorn-bin
                 (list "monk-gunicorn"
                       "monksystem.wsgi:application"
                       "--bind" #$bind
                       "--workers" #$workers))))))


;;;
;;; Shepherd service
;;;

(define (monk-shepherd-service config)
  (let* ((start (monk-start-script config))
         (user  (monk-configuration-user config))
         (group (monk-configuration-group config)))
    (list
     (shepherd-service
      (documentation "MONK Nihon-Kohden waveform management platform (gunicorn)")
      (provision '(monk))
      (requirement '(user-processes networking))
      (start #~(make-forkexec-constructor
                (list #$start)
                #:user #$user
                #:group #$group
                #:log-file "/var/log/monk/gunicorn.log"))
      (stop  #~(make-kill-destructor))
      (respawn? #t)))))


;;;
;;; System accounts
;;;

(define (monk-accounts config)
  (list
   (user-group
    (name    (monk-configuration-group config))
    (system? #t))
   (user-account
    (name            (monk-configuration-user config))
    (group           (monk-configuration-group config))
    (system?         #t)
    (comment         "MONK web application daemon")
    (home-directory  (monk-configuration-data-directory config))
    (shell           (file-append shadow "/sbin/nologin")))))


;;;
;;; Activation
;;;

(define (monk-activation config)
  (let* ((pkg        (monk-configuration-package config))
         (manage     (file-append pkg "/bin/monk-manage"))
         (data-dir   (monk-configuration-data-directory config))
         (user       (monk-configuration-user config))
         (secret     (monk-configuration-secret-key config))
         (hosts      (monk-configuration-allowed-hosts config))
         (import-dir (monk-configuration-file-import-base-dir config)))
    (with-imported-modules '((guix build utils))
      #~(begin
        (use-modules (guix build utils)
                     (ice-9 format))

        ;; Abort early if the operator forgot to set a secret key.
        (unless #$secret
          (error "monk-service: secret-key must be set in monk-configuration"))

        ;; ── Data directories ────────────────────────────────────────────
        (for-each (lambda (dir)
                    (unless (file-exists? dir)
                      (mkdir-p dir)))
                  (list #$data-dir
                        (string-append #$data-dir "/media")
                        (string-append #$data-dir "/static")
                        "/var/log/monk"))

        ;; ── Deployment settings ─────────────────────────────────────────
        ;; Write /etc/monk/monk_settings.py, which is imported by the
        ;; DJANGO_SETTINGS_MODULE=monk_settings env var set in the start
        ;; script.  It imports the base settings and overrides only what
        ;; must change for production.
        (mkdir-p "/etc/monk")
        (call-with-output-file "/etc/monk/monk_settings.py"
          (lambda (port)
            (let* ((h    '#$hosts)
                   (py-list
                    (lambda (items prefix)
                      (string-append
                       "["
                       (string-join
                        (map (lambda (s)
                               (string-append "\"" prefix s "\""))
                             items)
                        ", ")
                       "]"))))
              (format port "# Auto-generated by Guix System — do not edit manually.\n")
              (format port "from monksystem.settings import *  # noqa\n\n")
              (format port "SECRET_KEY = ~s\n" #$secret)
              (format port "DEBUG = False\n")
              (format port "ALLOWED_HOSTS = ~a\n" (py-list h ""))
              ;; Required by Django 4+ when DEBUG=False and a reverse proxy
              ;; terminates TLS.  Adjust the scheme prefix to match your setup.
              (format port "CSRF_TRUSTED_ORIGINS = ~a\n" (py-list h "https://"))
              (format port "\nDATABASES = {\n")
              (format port "    'default': {\n")
              (format port "        'ENGINE': 'django.db.backends.sqlite3',\n")
              (format port "        'NAME': ~s,\n"
                      (string-append #$data-dir "/db.sqlite3"))
              (format port "    }\n}\n\n")
              (format port "MEDIA_ROOT  = ~s\n"
                      (string-append #$data-dir "/media/"))
              (format port "MEDIA_URL   = '/media/'\n")
              (format port "STATIC_ROOT = ~s\n"
                      (string-append #$data-dir "/static/"))
              ;; Server-side directory import (bypasses browser file dialog).
              ;; Empty string leaves the feature disabled.
              (format port "FILE_IMPORT_BASE_DIR = ~s\n" #$import-dir))))

        ;; ── Database migrations + static files ──────────────────────────
        ;; Run every activation so new deployments and upgrades are
        ;; handled automatically.
        (setenv "DJANGO_SETTINGS_MODULE" "monk_settings")
        (setenv "PYTHONPATH"
                (let ((existing (getenv "PYTHONPATH")))
                  (if existing
                      (string-append "/etc/monk:" existing)
                      "/etc/monk")))
        (let ((status (system* #$manage "migrate" "--no-input")))
          (unless (zero? (status:exit-val status))
            (error "monk: database migration failed")))
        ;; Collect static assets into STATIC_ROOT so whitenoise can serve
        ;; them without a CDN or nginx — required for airgapped deployments.
        (let ((status (system* #$manage "collectstatic" "--no-input" "--clear")))
          (unless (zero? (status:exit-val status))
            (error "monk: collectstatic failed")))

        ;; ── Ownership ───────────────────────────────────────────────────
        ;; Give the monk daemon user ownership over all data directories.
        (let* ((pw  (getpwnam #$user))
               (uid (passwd:uid pw))
               (gid (passwd:gid pw)))
          (for-each
           (lambda (path)
             (when (file-exists? path)
               (chown path uid gid)))
           (list #$data-dir
                 (string-append #$data-dir "/db.sqlite3")
                 (string-append #$data-dir "/media")
                 (string-append #$data-dir "/static")
                 "/var/log/monk")))))))


;;;
;;; Service type
;;;

(define monk-service-type
  (service-type
   (name 'monk)
   (extensions
    (list
     (service-extension shepherd-root-service-type  monk-shepherd-service)
     (service-extension account-service-type        monk-accounts)
     (service-extension activation-service-type     monk-activation)))
   (description
    "Run the MONK Nihon-Kohden MFER waveform management platform under
gunicorn.  On every system activation the database is migrated
automatically.  Configure a reverse proxy (e.g. nginx) to forward
requests to the configured host:port and to serve /media/ and /static/
from the data-directory.")))
