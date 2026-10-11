from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from django.urls import include, path, re_path
from django.views.static import serve

from programme.sitemaps import CoursProfSitemap, ProfesseurSitemap, StaticViewSitemap

sitemaps = {
    "static": StaticViewSitemap,
    "professeurs": ProfesseurSitemap,
    "cours": CoursProfSitemap,
}


def serve_media(request, path):
    """Sert un média public dans un « bac à sable » : même si un fichier HTML/SVG
    malveillant était déposé, le navigateur n'y exécuterait aucun script."""
    response = serve(request, path, document_root=settings.MEDIA_ROOT)
    response["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def robots(request):
    lignes = [
        "User-agent: *",
        "Disallow: /accounts/",
        "Disallow: /ai/",
        "Disallow: /document/",
        "Disallow: /lire/",
        "Disallow: /depot/fichier/",
        "Disallow: /profs/studio/",
        "Disallow: /profs/lecon/",
        "Allow: /",
        f"Sitemap: {request.scheme}://{request.get_host()}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lignes) + "\n", content_type="text/plain")


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("healthz", healthz),
    path("robots.txt", robots),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("programme.urls")),
    path("accounts/", include("allauth.urls")),
    path("", include("chatapp.urls")),
    path("ai/", include("aiapp.urls")),
    path("", include("authapp.urls")),
    path("quiz/", include("quizapp.urls")),
    path("depot/", include("depot.urls")),
    path("profs/", include("profs.urls")),
]

if settings.SERVE_MEDIA and not settings.USE_S3:
    # Hébergement simple (Render gratuit, démo) : Django sert lui-même les médias publics.
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve_media),
    ]

handler404 = "programme.views.handels_error404"
handler500 = "programme.views.handels_error500"
handler403 = "programme.views.handels_error403"
