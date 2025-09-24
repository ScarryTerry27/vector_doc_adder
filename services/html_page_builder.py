from collections import defaultdict


class HTMLPageBuilder:
    def __init__(self):
        pass

    def build_grouped_by_file(self, documents: list) -> list[dict]:
        """
        Возвращает список:
        [
          {"file_name": "<исходное>.html", "html": "<...>"},
          ...
        ]
        """
        if not documents:
            return []

        grouped_docs = defaultdict(list)
        for doc in documents:
            file_name = doc.metadata.get("file_name", "unknown.pdf")
            grouped_docs[file_name].append(doc)

        html_pages = []
        for file_name, docs in grouped_docs.items():
            html = self._build_single_html(file_name, docs)
            html_pages.append({
                "file_name": file_name.replace(".pdf", ".html"),
                "html": html
            })
        return html_pages

    def _build_single_html(self, file_name: str, docs: list) -> str:
        title = file_name.replace(".pdf", "")
        body_blocks = []

        for doc in docs:
            # если у документа текст лежит в doc.text, а не в text_resource:
            text = getattr(getattr(doc, "text_resource", None), "text", None) or getattr(doc, "text", None)
            if not text:
                continue
            page = doc.metadata.get("chunk_number", "unknown")
            block = (
                f'<div id="page-{page}" class="page-block">\n'
                f'  <a href="#page-{page}" style="text-decoration:none;color:#666;float:right">#</a>\n'
                f'  <pre>{self.escape_html(text)}</pre>\n'
                f'</div>'
            )
            body_blocks.append(block)

        if not body_blocks:
            return f"<html><body><p>No content for file {file_name}</p></body></html>"

        return self.wrap_html("\n".join(body_blocks), title)

    def wrap_html(self, body: str, title: str) -> str:
        return f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>{title}</title>
        <style>
            html {{
                scroll-behavior: smooth;
            }}
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                background-color: #f9f9f9;
            }}
            .page-block {{
                padding: 20px;
                margin-bottom: 10px;
                background-color: #fff;
                border: 1px solid #ddd;
                border-radius: 5px;
                scroll-margin-top: 16px;
                transition: box-shadow .2s, border-color .2s, background-color .2s;
            }}
            .page-block pre {{
                white-space: pre-wrap;
                word-wrap: break-word;
            }}
            .page-block:target {{
                border-color: #007bff;
                box-shadow: 0 0 10px rgba(0,123,255,.5);
                animation: highlight-fade 1.8s ease-out;
                background-color: #e7f1ff;
            }}
            @keyframes highlight-fade {{
                0%   {{ background-color: #e7f1ff; }}
                100% {{ background-color: #fff; }}
            }}
        </style>
    </head>
    <body>
    {body}
    </body>
    </html>"""

    def escape_html(self, text: str) -> str:
        return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#039;"))
