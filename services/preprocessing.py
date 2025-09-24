import re
from services.html_page_builder import HTMLPageBuilder
from services.object_storage import ObjectStorageService


class PreprocessingService:
    """
    Service for preprocessing text data.
    """

    def __init__(self):
        self.html_builder = HTMLPageBuilder()
        self.oss = ObjectStorageService()

    def generate_html_and_upload_to_storage(self, doc_pages):
        for index, doc in enumerate(doc_pages, 1):
            doc.metadata["chunk_number"] = index

        html_pages = self.html_builder.build_grouped_by_file(doc_pages)
        res = self.oss.upload_html_documents(html_pages)
        file_id = res[0].get("file_id", None) if res else None
        for index, doc in enumerate(doc_pages, 1):
            doc.metadata["file_id"] = file_id
        return doc_pages

    def upload_file_to_storage(self, file_bytes: bytes, filename: str, doc_pages: list, folder: str = "sources"):
        res = self.oss.upload_file(file_bytes, filename, folder)
        file_id = res.get("file_id", None).split(".md")[0] if res else None
        for index, doc in enumerate(doc_pages, 1):
            doc.metadata["file_id"] = file_id
        return doc_pages


class MDProcessor:
    @staticmethod
    def add_labels(markdown_text: str, prefix="p") -> str:
        """
        Расставляет метки вида <!-- p_1 --> перед каждым логическим абзацем.
        Абзац = блок, отделённый одной или более пустыми строками.
        Заголовки, списки, таблицы — каждый считается отдельным абзацем.
        Исключение: не добавляет якоря перед заголовками (#, ##, ### ... ######)
        """
        blocks = re.split(r'\n\s*\n', markdown_text.strip())
        anchored_blocks = []
        paragraph_counter = 1
        for block in blocks:
            stripped_block = block.lstrip()
            is_header = stripped_block.startswith('#')
            if is_header:
                anchored_blocks.append(block)
            else:
                anchor_id = f"{prefix}_{paragraph_counter}"
                anchor_tag = f"<!-- {anchor_id} -->"
                anchored_block = f"{anchor_tag}\n{block}"
                anchored_blocks.append(anchored_block)
                paragraph_counter += 1
        return "\n".join(anchored_blocks)

    @staticmethod
    def add_anchors(markdown_text: str) -> str:
        """
        """
        pattern = r'<!--\s*p_(\d+)\s*-->'
        lines = markdown_text.split('\n')
        result_lines = []
        for line in lines:
            match = re.search(pattern, line)
            if match:
                p_id = match.group(1)
                result_lines.append(line)
                result_lines.append(f'<div id="p_{p_id}"></div>')
            else:
                result_lines.append(line)
        return '\n'.join(result_lines)
