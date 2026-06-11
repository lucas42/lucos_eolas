"""
Case-transform helpers that preserve all-uppercase words (acronyms).

Python's built-in str.lower() and str.title() treat every word identically,
which destroys acronym information: "TV Programme" → "tv programme" → "Tv Programme".

These helpers apply the same word-by-word logic everywhere names and plurals
are normalised, so an all-uppercase word entered by the user survives the
round-trip unchanged.
"""


def smart_lower(text):
    """Lowercase each word, but leave all-uppercase words (acronyms) untouched.

    Examples:
        "TV Programme"  → "TV programme"
        "BBC documentary" → "BBC documentary"
        "road"          → "road"
        "tv programme"  → "tv programme"  (already lowercase — no info to recover)
    """
    return ' '.join(word if word.isupper() else word.lower() for word in text.split())


def smart_title(text):
    """Title-case each word, but leave all-uppercase words (acronyms) untouched.

    Examples:
        "TV programme"    → "TV Programme"
        "BBC documentary" → "BBC Documentary"
        "road"            → "Road"
        "tv programme"    → "Tv Programme"  (same as .title() — stored lowercase has no acronym info)
    """
    return ' '.join(word if word.isupper() else word.capitalize() for word in text.split())
