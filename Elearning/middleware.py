"""En-têtes HTTP de sécurité complémentaires à ceux de Django."""


class SecurityHeadersMiddleware:
    # Politique compatible avec les scripts inline existants : elle bloque
    # l'intégration du site dans une iframe étrangère, les plugins (<object>),
    # la modification de <base> et l'envoi de formulaires vers un autre domaine.
    CSP = (
        "frame-ancestors 'none'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    PERMISSIONS = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault("Permissions-Policy", self.PERMISSIONS)
        return response
