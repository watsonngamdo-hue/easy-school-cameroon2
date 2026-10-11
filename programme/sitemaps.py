"""Plan du site : uniquement des pages publiques (les leçons payantes ne sont pas indexées)."""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = "weekly"

    def items(self):
        return ["programme:programme", "programme:about", "programme:level", "programme:contact",
                "profs:catalogue", "profs:devenir", "depot:accueil"]

    def location(self, item):
        return reverse(item)


class ProfesseurSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        from profs.models import ProfilProfesseur
        return ProfilProfesseur.objects.filter(statut=ProfilProfesseur.Statut.VERIFIE).order_by("pk")

    def location(self, obj):
        return reverse("profs:chaine", args=[obj.slug])


class CoursProfSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        from profs.models import CoursProf, ProfilProfesseur
        return CoursProf.objects.filter(publie=True, bloque_par_admin=False,
                                        professeur__statut=ProfilProfesseur.Statut.VERIFIE).order_by("pk")

    def location(self, obj):
        return reverse("profs:cours", args=[obj.slug])

    def lastmod(self, obj):
        return obj.date_maj
