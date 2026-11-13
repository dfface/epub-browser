"""Validation shared by the browser and versioned vocabulary APIs."""

from .dictionary_formats import normalize_lookup

MASTERY_STATES = ("new", "learning", "mastered")
PAGE_SIZE = 24
MAX_PAGE_SIZE = 100
MAX_QUERY_LENGTH = 2048


def vocabulary_page_options(params):
    page = int(params.get("page", "1"))
    page_size = int(params.get("page_size", str(PAGE_SIZE)))
    query = params.get("q", "")
    mastery = params.get("mastery")
    if (
        not 1 <= page <= 2**31 - 1 or not 1 <= page_size <= MAX_PAGE_SIZE
        or len(query) > MAX_QUERY_LENGTH
        or (mastery is not None and mastery not in MASTERY_STATES)
    ):
        raise ValueError("Invalid vocabulary query")
    return {
        "page": page, "page_size": page_size,
        "query": normalize_lookup(query) if query.strip() else "",
        "mastery": mastery,
    }
