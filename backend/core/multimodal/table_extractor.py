"""
Table Extractor
Extracts and processes tables from PDF documents
"""
import structlog
from typing import Optional
from dataclasses import dataclass

logger = structlog.get_logger()


@dataclass
class ExtractedTable:
    """Represents an extracted table"""
    table_id: str
    headers: list[str]
    rows: list[list[str]]
    page: int
    bbox: Optional[tuple] = None
    markdown: str = ""


class TableExtractor:
    """
    Extracts tables from PDF documents.

    Supports multiple extraction strategies:
    - pdfplumber (best for structured tables)
    - Camelot (alternative with different strengths)
    - PyMuPDF (fallback)
    """

    def __init__(self):
        self.logger = logger

    async def extract_tables(
        self,
        file_path: str,
        pages: Optional[list[int]] = None,
    ) -> list[ExtractedTable]:
        """
        Extract tables from PDF file.

        Args:
            file_path: Path to PDF file
            pages: Specific pages to extract from (None = all)

        Returns:
            List of extracted tables
        """
        self.logger.info("extracting_tables", file=file_path)

        tables = []

        try:
            tables = await self._extract_with_pdfplumber(file_path, pages)
        except Exception as e:
            self.logger.warning("pdfplumber_failed", error=str(e))
            try:
                tables = await self._extract_with_pymupdf(file_path, pages)
            except Exception as e2:
                self.logger.error("pymupdf_failed", error=str(e2))

        self.logger.info("tables_extracted", count=len(tables))
        return tables

    async def _extract_with_pdfplumber(
        self,
        file_path: str,
        pages: Optional[list[int]],
    ) -> list[ExtractedTable]:
        """Extract tables using pdfplumber"""
        import pdfplumber

        tables = []

        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            target_pages = pages if pages else range(page_count)

            for page_num in target_pages:
                if page_num >= page_count:
                    break

                page = pdf.pages[page_num]

                extracted_tables = page.extract_tables()

                for i, table_data in enumerate(extracted_tables):
                    if not table_data:
                        continue

                    headers = []
                    rows = []

                    if table_data and len(table_data) > 0:
                        first_row = table_data[0]
                        if self._looks_like_header(first_row):
                            headers = [str(cell) if cell else "" for cell in first_row]
                            rows = [
                                [str(cell) if cell else "" for cell in row]
                                for row in table_data[1:]
                            ]
                        else:
                            headers = [f"Col{i}" for i in range(len(first_row))]
                            rows = [
                                [str(cell) if cell else "" for cell in row]
                                for row in table_data
                            ]

                    table = ExtractedTable(
                        table_id=f"{page_num}_{i}",
                        headers=headers,
                        rows=rows,
                        page=page_num + 1,
                    )
                    table.markdown = self._to_markdown(table)

                    tables.append(table)

        return tables

    async def _extract_with_pymupdf(
        self,
        file_path: str,
        pages: Optional[list[int]],
    ) -> list[ExtractedTable]:
        """Extract tables using PyMuPDF"""
        import fitz

        tables = []
        doc = fitz.open(file_path)

        page_count = len(doc)
        target_pages = pages if pages else range(page_count)

        for page_num in target_pages:
            if page_num >= page_count:
                break

            page = doc[page_num]

            try:
                tabs = page.find_tables()
                if tabs and tabs.tables:
                    for i, tab in enumerate(tabs.tables):
                        headers = []
                        rows = []

                        if tab.extract.header_names:
                            headers = tab.extract.header_names
                        else:
                            headers = [f"Col{j}" for j in range(tab.ncols)]

                        extracted_rows = tab.extract()
                        if extracted_rows:
                            rows = [[str(cell) if cell else "" for cell in row] for row in extracted_rows]

                        table = ExtractedTable(
                            table_id=f"{page_num}_{i}",
                            headers=headers,
                            rows=rows,
                            page=page_num + 1,
                        )
                        table.markdown = self._to_markdown(table)
                        tables.append(table)

            except Exception as e:
                self.logger.warning(f"table_extract_failed_page_{page_num}", error=str(e))

        doc.close()
        return tables

    def _looks_like_header(self, row: list) -> bool:
        """Heuristic to determine if first row is a header"""
        if not row:
            return False

        header_count = sum(
            1 for cell in row
            if cell and isinstance(cell, str) and any(
                c.isupper() for c in cell[:5]
            )
        )

        return header_count >= len(row) * 0.5

    def _to_markdown(self, table: ExtractedTable) -> str:
        """Convert table to markdown format"""
        lines = []

        header_line = "| " + " | ".join(table.headers) + " |"
        separator = "| " + " | ".join(["---"] * len(table.headers)) + " |"

        lines.append(header_line)
        lines.append(separator)

        for row in table.rows:
            row_line = "| " + " | ".join(row) + " |"
            lines.append(row_line)

        return "\n".join(lines)

    async def table_to_text(self, table: ExtractedTable) -> str:
        """Convert table to plain text representation"""
        lines = []

        if table.headers:
            lines.append(" | ".join(table.headers))

        for row in table.rows:
            lines.append(" | ".join(row))

        return "\n".join(lines)

    async def query_table(
        self,
        table: ExtractedTable,
        query: str,
    ) -> str:
        """
        Answer questions about a table.

        Args:
            table: Extracted table
            query: Question about the table

        Returns:
            Answer text
        """
        table_text = await self.table_to_text(table)

        prompt = f"""根据以下表格内容回答问题。

【表格】
{table_text}

【问题】
{query}

请直接根据表格内容回答，不要添加表格中没有的信息。
"""

        from backend.core.generation.generator import Generator

        try:
            generator = Generator()
            answer = await generator.generate(prompt)
            return answer
        except Exception as e:
            self.logger.error("table_query_failed", error=str(e))
            return "无法回答此问题"
