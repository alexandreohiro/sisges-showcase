from pathlib import Path
import pdfplumber


class PDFExtractionResult:
    def __init__(self, text: str, pages: int) -> None:
        self.text = text
        self.pages = pages


def extract_text_from_pdf(pdf_path: str | Path) -> PDFExtractionResult:
    pdf_path = Path(pdf_path)

    texts: list[str] = []
    total_pages = 0

    with pdfplumber.open(str(pdf_path)) as pdf:
        total_pages = len(pdf.pages)

        for page_index, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            texts.append(f"[[PAGE:{page_index}]]")
            texts.append(page_text)

    final_text = "\n\n".join(texts).strip()
    return PDFExtractionResult(text=final_text, pages=total_pages)