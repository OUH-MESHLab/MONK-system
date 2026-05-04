from django.conf import settings

from monksystem import __version__


def idle_logout(request):
    return {"IDLE_LOGOUT_SECONDS": getattr(settings, "IDLE_LOGOUT_SECONDS", 900)}


def version(request):
    return {"MONK_VERSION": __version__}
