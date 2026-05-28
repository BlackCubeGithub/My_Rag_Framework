"""
Layout Analyzer
Analyzes document layout and structure
"""
import structlog
from typing import Optional
from dataclasses import dataclass
from enum import Enum

logger = structlog.get_logger()


class LayoutElementType(str, Enum):
    """Types of layout elements"""
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    HEADER = "header"
    FOOTER = "footer"
    PAGE_NUMBER = "page_number"
    MARGIN = "margin"
    UNKNOWN = "unknown"


@dataclass
class LayoutElement:
    """Represents a layout element"""
    element_id: str
    type: LayoutElementType
    bbox: tuple[float, float, float, float]
    content: str
    page: int
    confidence: float = 1.0


@dataclass
class LayoutAnalysis:
    """Result of layout analysis"""
    page_count: int
    elements: list[LayoutElement]
    reading_order: list[str]
    text_regions: list[LayoutElement]
    image_regions: list[LayoutElement]
    table_regions: list[LayoutElement]


class LayoutAnalyzer:
    """
    Analyzes document layout and structure.

    Identifies:
    - Text regions and reading order
    - Image locations
    - Table locations
    - Headers and footers
    - Page boundaries
    """

    def __init__(self):
        self.logger = logger

    async def analyze(
        self,
        file_path: str,
        extract_images: bool = False,
    ) -> LayoutAnalysis:
        """
        Analyze document layout.

        Args:
            file_path: Path to document
            extract_images: Whether to extract image data

        Returns:
            LayoutAnalysis with identified elements
        """
        self.logger.info("analyzing_layout", file=file_path)

        try:
            import fitz

            doc = fitz.open(file_path)
            page_count = len(doc)

            elements = []
            text_regions = []
            image_regions = []
            table_regions = []

            for page_num in range(page_count):
                page = doc[page_num]

                page_elements = await self._analyze_page(page, page_num)
                elements.extend(page_elements)

                text_regions.extend(
                    [e for e in page_elements if e.type == LayoutElementType.TEXT]
                )
                image_regions.extend(
                    [e for e in page_elements if e.type == LayoutElementType.IMAGE]
                )
                table_regions.extend(
                    [e for e in page_elements if e.type == LayoutElementType.TABLE]
                )

            reading_order = self._compute_reading_order(elements)

            doc.close()

            self.logger.info(
                "layout_analysis_completed",
                pages=page_count,
                elements=len(elements),
            )

            return LayoutAnalysis(
                page_count=page_count,
                elements=elements,
                reading_order=reading_order,
                text_regions=text_regions,
                image_regions=image_regions,
                table_regions=table_regions,
            )

        except ImportError:
            self.logger.error("PyMuPDF not available for layout analysis")
            return LayoutAnalysis(
                page_count=0,
                elements=[],
                reading_order=[],
                text_regions=[],
                image_regions=[],
                table_regions=[],
            )
        except Exception as e:
            self.logger.error("layout_analysis_failed", error=str(e))
            return LayoutAnalysis(
                page_count=0,
                elements=[],
                reading_order=[],
                text_regions=[],
                image_regions=[],
                table_regions=[],
            )

    async def _analyze_page(self, page, page_num: int) -> list[LayoutElement]:
        """Analyze a single page layout"""
        elements = []

        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if block.get("type") == 0:
                element = self._process_text_block(block, page_num)
                if element:
                    elements.append(element)

            elif block.get("type") == 1:
                element = self._process_image_block(block, page_num)
                if element:
                    elements.append(element)

        headers, footers = self._extract_headers_footers(page, page_num)
        elements.extend(headers)
        elements.extend(footers)

        return elements

    def _process_text_block(
        self,
        block: dict,
        page_num: int,
    ) -> Optional[LayoutElement]:
        """Process a text block"""
        lines = block.get("lines", [])
        if not lines:
            return None

        text_parts = []
        bbox = block.get("bbox", (0, 0, 0, 0))

        for line in lines:
            for span in line.get("spans", []):
                text_parts.append(span.get("text", ""))

        text = "".join(text_parts)

        if not text.strip():
            return None

        return LayoutElement(
            element_id=f"text_{page_num}_{block.get('number', 0)}",
            type=LayoutElementType.TEXT,
            bbox=bbox,
            content=text,
            page=page_num + 1,
        )

    def _process_image_block(
        self,
        block: dict,
        page_num: int,
    ) -> Optional[LayoutElement]:
        """Process an image block"""
        bbox = block.get("bbox", (0, 0, 0, 0))

        return LayoutElement(
            element_id=f"image_{page_num}_{block.get('number', 0)}",
            type=LayoutElementType.IMAGE,
            bbox=bbox,
            content=f"[Image at {bbox}]",
            page=page_num + 1,
        )

    def _extract_headers_footers(
        self,
        page,
        page_num: int,
    ) -> tuple[list[LayoutElement], list[LayoutElement]]:
        """Extract header and footer elements"""
        headers = []
        footers = []

        page_height = page.rect.height
        margin_threshold = 50

        text = page.get_text()

        lines = text.split("\n")
        if lines:
            header_text = lines[0]
            if header_text.strip():
                headers.append(LayoutElement(
                    element_id=f"header_{page_num}",
                    type=LayoutElementType.HEADER,
                    bbox=(0, 0, page.rect.width, margin_threshold),
                    content=header_text.strip(),
                    page=page_num + 1,
                ))

            footer_text = lines[-1]
            if footer_text.strip():
                footers.append(LayoutElement(
                    element_id=f"footer_{page_num}",
                    type=LayoutElementType.FOOTER,
                    bbox=(0, page_height - margin_threshold, page.rect.width, page_height),
                    content=footer_text.strip(),
                    page=page_num + 1,
                ))

        return headers, footers

    def _compute_reading_order(self, elements: list[LayoutElement]) -> list[str]:
        """Compute reading order of elements (top-to-bottom, left-to-right)"""
        sorted_elements = sorted(
            elements,
            key=lambda e: (e.page, e.bbox[1], e.bbox[0]),
        )

        return [e.element_id for e in sorted_elements]
