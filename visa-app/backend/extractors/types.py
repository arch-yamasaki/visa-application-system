from dataclasses import dataclass, field


@dataclass
class BoundingBox:
    x: float
    y: float
    width: float
    height: float


@dataclass
class WordResult:
    text: str
    bbox: BoundingBox | None
    confidence: float


@dataclass
class PageResult:
    page_number: int
    text: str
    words: list[WordResult] = field(default_factory=list)


@dataclass
class OcrResult:
    document_id: str
    pages: list[PageResult] = field(default_factory=list)


@dataclass
class ExtractionResult:
    case_data: dict
    review: dict
    field_metadata: dict
