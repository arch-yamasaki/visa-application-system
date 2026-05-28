"""Document inputs prepared for extraction."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LoadedDocument:
    document_id: str
    file_name: str
    document_role: str
    content: bytes


@dataclass
class PreparedDocuments:
    pdf_contents: list[tuple[str, bytes]] = field(default_factory=list)
    text_contents: list[tuple[str, str]] = field(default_factory=list)
    image_entries: list[tuple[str, str, bytes]] = field(default_factory=list)
    pdf_bytes_map: dict[str, bytes] = field(default_factory=dict)

    @property
    def total_inline_bytes(self) -> int:
        pdf_bytes = sum(len(content) for _, content in self.pdf_contents)
        image_bytes = sum(
            len(content)
            for _, file_name, content in self.image_entries
            if not file_name.lower().endswith(".pdf")
        )
        return pdf_bytes + image_bytes
