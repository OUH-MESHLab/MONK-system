class NoCacheMiddleware:
    """Set Cache-Control: no-store on every response.

    Prevents the browser from caching any page, which is important for
    a medical-data kiosk where multiple users may share one session.
    Whitenoise handles its own static-file responses before this middleware
    runs, so static assets are unaffected.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Cache-Control"] = "no-store"
        return response
