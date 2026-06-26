"""
Template context processors for lucosauth.
"""

import os


def aithne_origin(request):
    """Inject AITHNE_ORIGIN into all template contexts.

    Used by templates/admin/base.html to set the aithne-origin attribute on
    <lucos-navbar>, enabling the keepalive to call the right aithne instance.
    """
    return {
        "AITHNE_ORIGIN": os.environ.get("AITHNE_ORIGIN", "https://aithne.l42.eu"),
    }
