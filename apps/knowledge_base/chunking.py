"""Heading-aware and procedure-aware deterministic chunking."""

import hashlib
import re
from dataclasses import dataclass, field

from .extraction import ExtractedBlock, ExtractionResult, ProcessingWarning

TOKEN_PATTERN = re.compile(r"\w+(?:[-/.]\w+)*|[^\w\s]", re.UNICODE)


@dataclass(frozen=True)
class ChunkingConfig:
    target_tokens: int = 600
    overlap_tokens: int = 75
    minimum_tokens: int = 100
    maximum_tokens: int = 900

    def validate(self) -> None:
        if not 400 <= self.target_tokens <= 800:
            raise ValueError("Target chunk size must be between 400 and 800 tokens.")
        if not 50 <= self.overlap_tokens <= 100:
            raise ValueError("Chunk overlap must be between 50 and 100 tokens.")
        if self.minimum_tokens <= 0:
            raise ValueError("Minimum chunk size must be positive.")
        if self.maximum_tokens < self.target_tokens:
            raise ValueError("Maximum chunk size cannot be below the target.")
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("Chunk overlap must be smaller than the target.")


@dataclass
class ChunkDraft:
    sequence: int
    text: str
    chapter: str
    section: str
    page_start: int | None
    page_end: int | None
    token_count: int
    contains_warning: bool
    contains_caution: bool
    warnings: list[ProcessingWarning] = field(default_factory=list)
    content_hash: str = ""
    chunk_id: str = ""
    duplicate_sequence: int | None = None


def approximate_token_count(text: str) -> int:
    return len(TOKEN_PATTERN.findall(text))


class DocumentChunker:
    def __init__(self, config: ChunkingConfig) -> None:
        config.validate()
        self.config = config

    def chunk(
        self,
        extraction: ExtractionResult,
        *,
        version_id: str,
    ) -> list[ChunkDraft]:
        sections = self._group_by_section(extraction.blocks)
        drafts: list[ChunkDraft] = []
        previous_tail = ""

        for blocks in sections:
            for text, source_blocks in self._pack_section(blocks):
                if previous_tail and source_blocks[0].section == (
                    drafts[-1].section if drafts else ""
                ):
                    text = f"{previous_tail}\n\n{text}"
                draft = self._build_draft(len(drafts) + 1, text, source_blocks)
                drafts.append(draft)
                previous_tail = self._tail(text)

        for draft in drafts:
            draft.content_hash = hashlib.sha256(
                normalize_chunk_text(draft.text).encode("utf-8")
            ).hexdigest()
            stable_material = (
                f"{version_id}|{draft.sequence}|{draft.content_hash}".encode()
            )
            draft.chunk_id = "CHK-" + hashlib.sha256(stable_material).hexdigest()[:32]

        self._mark_duplicates(drafts)
        return drafts

    @staticmethod
    def _group_by_section(
        blocks: list[ExtractedBlock],
    ) -> list[list[ExtractedBlock]]:
        groups: list[list[ExtractedBlock]] = []
        current: list[ExtractedBlock] = []
        current_key: tuple[str, str] | None = None
        for block in blocks:
            key = (block.chapter, block.section)
            if current and key != current_key and block.kind == "heading":
                if any(item.kind != "heading" for item in current):
                    groups.append(current)
                    current = []
            current.append(block)
            current_key = key
        if current:
            groups.append(current)
        return groups

    def _pack_section(
        self,
        blocks: list[ExtractedBlock],
    ) -> list[tuple[str, list[ExtractedBlock]]]:
        units = self._semantic_units(blocks)
        packed: list[tuple[str, list[ExtractedBlock]]] = []
        current: list[ExtractedBlock] = []
        current_tokens = 0

        for unit in units:
            unit_tokens = sum(approximate_token_count(block.text) for block in unit)
            if unit_tokens > self.config.maximum_tokens:
                if current:
                    packed.append((render_blocks(current), current))
                    current = []
                    current_tokens = 0
                packed.extend(self._split_oversized_unit(unit))
                continue

            if (
                current
                and current_tokens + unit_tokens > self.config.target_tokens
                and current_tokens >= self.config.minimum_tokens
            ):
                packed.append((render_blocks(current), current))
                current = []
                current_tokens = 0
            current.extend(unit)
            current_tokens += unit_tokens

        if current:
            packed.append((render_blocks(current), current))
        return packed

    @staticmethod
    def _semantic_units(
        blocks: list[ExtractedBlock],
    ) -> list[list[ExtractedBlock]]:
        units: list[list[ExtractedBlock]] = []
        current: list[ExtractedBlock] = []

        for block in blocks:
            if block.kind in {"warning", "caution"}:
                if current:
                    units.append(current)
                current = [block]
                continue

            if block.kind == "heading":
                if current:
                    units.append(current)
                current = [block]
                continue

            if block.kind == "procedure":
                if current and all(
                    item.kind
                    in {
                        "heading",
                        "procedure",
                        "warning",
                        "caution",
                        "paragraph",
                    }
                    for item in current
                ):
                    current.append(block)
                else:
                    if current:
                        units.append(current)
                    current = [block]
                continue

            if current and current[0].kind in {"warning", "caution"}:
                current.append(block)
                continue
            if current:
                units.append(current)
            current = [block]

        if current:
            units.append(current)
        return units

    def _split_oversized_unit(
        self,
        unit: list[ExtractedBlock],
    ) -> list[tuple[str, list[ExtractedBlock]]]:
        prefix = [
            block for block in unit if block.kind in {"heading", "warning", "caution"}
        ]
        body = [block for block in unit if block not in prefix]
        pieces: list[tuple[str, list[ExtractedBlock]]] = []
        current = list(prefix)
        current_tokens = sum(approximate_token_count(item.text) for item in current)

        for block in body:
            block_tokens = approximate_token_count(block.text)
            if block_tokens > self.config.maximum_tokens:
                sentences = re.split(r"(?<=[.!?])\s+", block.text)
                for sentence in sentences:
                    candidate = ExtractedBlock(
                        block.kind,
                        sentence,
                        block.page_number,
                        block.chapter,
                        block.section,
                    )
                    candidate_tokens = approximate_token_count(sentence)
                    if (
                        len(current) > len(prefix)
                        and current_tokens + candidate_tokens
                        > self.config.maximum_tokens
                    ):
                        pieces.append((render_blocks(current), list(current)))
                        current = list(prefix)
                        current_tokens = sum(
                            approximate_token_count(item.text) for item in current
                        )
                    current.append(candidate)
                    current_tokens += candidate_tokens
                continue

            if (
                len(current) > len(prefix)
                and current_tokens + block_tokens > self.config.maximum_tokens
            ):
                pieces.append((render_blocks(current), list(current)))
                current = list(prefix)
                current_tokens = sum(
                    approximate_token_count(item.text) for item in current
                )
            current.append(block)
            current_tokens += block_tokens

        if current:
            pieces.append((render_blocks(current), current))
        return pieces

    def _tail(self, text: str) -> str:
        tokens = TOKEN_PATTERN.findall(text)
        return " ".join(tokens[-self.config.overlap_tokens :])

    def _build_draft(
        self,
        sequence: int,
        text: str,
        blocks: list[ExtractedBlock],
    ) -> ChunkDraft:
        pages = [block.page_number for block in blocks if block.page_number is not None]
        count = approximate_token_count(text)
        warnings: list[ProcessingWarning] = []
        if count < self.config.minimum_tokens:
            warnings.append(
                ProcessingWarning(
                    "unusually_short_chunk",
                    f"Chunk has only {count} approximate tokens.",
                    min(pages) if pages else None,
                )
            )
        if count > self.config.maximum_tokens:
            warnings.append(
                ProcessingWarning(
                    "unusually_long_chunk",
                    f"Chunk has {count} approximate tokens.",
                    min(pages) if pages else None,
                )
            )
        chapter = next((block.chapter for block in blocks if block.chapter), "")
        section = next((block.section for block in blocks if block.section), "")
        if not chapter and not section:
            warnings.append(
                ProcessingWarning(
                    "missing_heading",
                    "Chunk has no chapter or section reference.",
                    min(pages) if pages else None,
                )
            )
        if not pages:
            warnings.append(
                ProcessingWarning(
                    "missing_page_reference",
                    "Chunk has no page reference.",
                )
            )
        return ChunkDraft(
            sequence=sequence,
            text=text,
            chapter=chapter,
            section=section,
            page_start=min(pages) if pages else None,
            page_end=max(pages) if pages else None,
            token_count=count,
            contains_warning=any(block.kind == "warning" for block in blocks),
            contains_caution=any(block.kind == "caution" for block in blocks),
            warnings=warnings,
        )

    @staticmethod
    def _mark_duplicates(drafts: list[ChunkDraft]) -> None:
        exact: dict[str, int] = {}
        fingerprints: list[tuple[set[str], int]] = []
        for draft in drafts:
            if draft.content_hash in exact:
                draft.duplicate_sequence = exact[draft.content_hash]
                continue
            words = set(normalize_chunk_text(draft.text).split())
            for prior_words, prior_sequence in fingerprints:
                union = words | prior_words
                similarity = len(words & prior_words) / len(union) if union else 1
                if similarity >= 0.92:
                    draft.duplicate_sequence = prior_sequence
                    break
            exact[draft.content_hash] = draft.sequence
            fingerprints.append((words, draft.sequence))


def render_blocks(blocks: list[ExtractedBlock]) -> str:
    parts: list[str] = []
    for block in blocks:
        if block.kind == "warning":
            parts.append(f"WARNING:\n{block.text.removeprefix('WARNING').lstrip(': ')}")
        elif block.kind == "caution":
            parts.append(f"CAUTION:\n{block.text.removeprefix('CAUTION').lstrip(': ')}")
        else:
            parts.append(block.text)
    return "\n\n".join(part for part in parts if part.strip()).strip()


def normalize_chunk_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()
