from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


@dataclass(frozen=True)
class BookMetadata:
    title: str
    authors: Tuple[str, ...]
    tags: Tuple[str, ...]
    cover: Optional[str]
    language: str
    epub_identifier: Optional[str]


@dataclass(frozen=True)
class ConvertedBook:
    book_id: str
    source_path: Path
    output_dir: Path
    metadata: BookMetadata
    chapter_count: int
