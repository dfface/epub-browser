BOOK_ID_STORAGE_SIDECAR = "sidecar"
BOOK_ID_STORAGE_EMBEDDED = "embedded"
BOOK_ID_STORAGE_CHOICES = (
    BOOK_ID_STORAGE_SIDECAR,
    BOOK_ID_STORAGE_EMBEDDED,
)


def validate_book_id_storage(value: str) -> str:
    if value not in BOOK_ID_STORAGE_CHOICES:
        choices = ", ".join(BOOK_ID_STORAGE_CHOICES)
        raise ValueError(f"Book ID storage must be one of: {choices}")
    return value
