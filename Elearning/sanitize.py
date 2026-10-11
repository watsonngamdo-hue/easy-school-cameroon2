"""Nettoyage du HTML saisi par les utilisateurs (protection XSS)."""
import nh3

ALLOWED_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "s", "a", "ul", "ol", "li",
    "blockquote", "code", "pre", "h2", "h3", "h4", "span", "sub", "sup",
    "table", "thead", "tbody", "tr", "th", "td", "img", "hr",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}


def clean_html(value):
    """Retourne une version sûre du HTML : scripts, gestionnaires d'événements
    (onclick…), liens javascript: et styles sont supprimés."""
    if not value:
        return ""
    return nh3.clean(
        str(value),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer nofollow",
    )
