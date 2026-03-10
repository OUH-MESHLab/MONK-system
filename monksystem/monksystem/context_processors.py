from django.conf import settings


def idle_logout(request):
    return {"IDLE_LOGOUT_SECONDS": getattr(settings, "IDLE_LOGOUT_SECONDS", 900)}
