from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
from pathlib import Path
import urllib.parse
import fitz
import tempfile
import re
from typing import Dict, Tuple

"""
На что следует обратить внимание: сейчас к серверу прикручена статическая папка,
в которой должны находится те документы, на которые можно будет сослаться. Их
наименования (example.pdf) должны фигурировать в базовой части ссылки в ответе
модели. Из этих файлов динамически создаются новые файлы с подсвеченными желтым
хайлайтом текстовыми блоками, в которых находятся цитаты. Эти файлы сервером
записываются во временную папку, но время жизни их нигде здесь не контролируется
и возложено на ОС, поэтому гипотетически они могут заполнить свободное дисковое
пространство, над этим надо подумать. Нечеткий поиск пока реализован как наилучшее
пересечение множеств слов текстовых блоков документа и поисковой строки, это так
себе решение, лучше будет потом приделать поиск по эмбеддингам или что-то подобное
для точности.
"""


app = FastAPI(title="Показыватель цытат")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


PDF_DIR = "./examples" # <==== !!! Это папка где должны лежать документы
Path(PDF_DIR).mkdir(exist_ok=True)
app.mount("/static/pdf", StaticFiles(directory=PDF_DIR), name="static_pdf")


class PDFBlockSearch:
    @staticmethod
    def find_best_matching_block(filename: str, search_text: str) -> Dict:
        """
        Поиск текстового блока с наилучшим совпадением с поисковой строкой
        """
        file_path = os.path.join(PDF_DIR, filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="PDF file not found")
        search_words = set(re.split(r'\s+', search_text.lower()))
        best_block = None
        best_score = 0
        best_page = -1
        best_block_rect = None
        try:
            with fitz.open(file_path) as doc:
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    text_blocks = page.get_text_blocks()
                    for block in text_blocks:
                        block_text = block[4].lower()
                        block_words = set(re.split(r'\s+', block_text))
                        common_words = search_words & block_words
                        score = len(common_words)
                        if score > best_score:
                            best_score = score
                            best_block = block_text
                            best_page = page_num + 1
                            best_block_rect = block[:4]  # координаты блока
                        if score == len(search_words):
                            break
                results = {
                    "found": best_score > 0,
                    "best_block": best_block,
                    "page_number": best_page,
                    "match_score": best_score,
                    "search_text": search_text,
                    "block_rect": best_block_rect
                }
                return results
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")


def highlight_best_block(doc, page_num: int, block_rect: Tuple[float, float, float, float]):
    """
    Подсвечивает найденный текстовый блок
    """
    if block_rect is None:
        return
    page = doc.load_page(page_num - 1)  # fitz использует 0-based индексацию
    highlight = page.add_highlight_annot(block_rect)
    highlight.set_colors(stroke=(1, 1, 0))  # желтый цвет
    highlight.set_opacity(0.3)  # полупрозрачный
    highlight.update()


def create_highlighted_pdf(filename: str, search_text: str) -> str:
    """
    Создает временный PDF файл с подсветкой найденного блока
    """
    file_path = os.path.join(PDF_DIR, filename)
    temp_dir = tempfile.gettempdir()            # <==== Отредаченный пдфник сохраняется во временную папку!
                                                # нужно будет подумать либо про регулярную частую чистку,
                                                # либо про сохранение в оперативную память, чтобы не засралось!
    temp_filename = f"highlighted_{hash(filename + search_text)}.pdf"
    temp_path = os.path.join(temp_dir, temp_filename)
    search_results = PDFBlockSearch.find_best_matching_block(filename, search_text)
    if not search_results["found"]:
        return None
    with fitz.open(file_path) as doc:
        highlight_best_block(doc, search_results["page_number"], search_results["block_rect"])
        doc.save(temp_path)
    return temp_path


@app.get("/search/{filename}/{search_text}")
async def search_and_view_pdf(filename: str, search_text: str):
    """
    Ищет текст в PDF и открывает на странице с найденным блоком
    """
    file_path = os.path.join(PDF_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="PDF file not found")
    search_text_decoded = urllib.parse.unquote(search_text)
    search_results = PDFBlockSearch.find_best_matching_block(filename, search_text_decoded)
    if not search_results["found"]:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Текст не найден - {filename}</title>
            <style>
                body {{ font-family: Arial; padding: 50px; text-align: center; }}
                .message {{ color: #d32f2f; font-size: 18px; margin: 20px 0; }}
                .back-link {{ color: #1976d2; text-decoration: none; }}
            </style>
        </head>
        <body>
            <h1>Текст не найден</h1>
            <div class="message">Текст "{search_text_decoded}" не найден в документе "{filename}"</div>
            <a href="/" class="back-link">← Вернуться к списку файлов</a>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    temp_pdf_path = create_highlighted_pdf(filename, search_text_decoded)
    html_content = generate_pdf_viewer_html(
        filename, 
        search_results["page_number"], 
        search_text_decoded,
        search_results,
        temp_pdf_path
    )
    return HTMLResponse(content=html_content)


@app.get("/api/pdf/highlighted/{filename}/{search_text}")
async def get_highlighted_pdf(filename: str, search_text: str):
    """
    Отдает PDF файл с подсветкой найденного блока
    """
    search_text_decoded = urllib.parse.unquote(search_text)
    temp_pdf_path = create_highlighted_pdf(filename, search_text_decoded)
    if not temp_pdf_path or not os.path.exists(temp_pdf_path):
        raise HTTPException(status_code=404, detail="Highlighted PDF not found")
    response = FileResponse(
        temp_pdf_path,
        media_type="application/pdf",
        filename=f"highlighted_{filename}"
    )
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


def generate_pdf_viewer_html(filename: str, page_number: int, search_text: str, 
                           search_results: Dict, temp_pdf_path: str) -> str:
    """
    Генерация HTML страницы с PDF viewer и подсветкой найденного блока
    """
    return f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Поиск: "{search_text}" - {filename}</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.min.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
            background-color: #f0f0f0;
        }}
        .controls {{
            background: white;
            padding: 10px;
            border-bottom: 1px solid #ddd;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
            position: sticky;
            top: 0;
            z-index: 100;
        }}
        button {{
            padding: 8px 16px;
            background: #007bff;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }}
        button:hover {{
            background: #0056b3;
        }}
        button:disabled {{
            background: #6c757d;
            cursor: not-allowed;
        }}
        .page-info {{
            font-weight: bold;
            color: #333;
            font-size: 14px;
        }}
        #pdf-canvas {{
            margin: 20px auto;
            display: block;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .loading {{
            text-align: center;
            padding: 100px;
            font-size: 18px;
            color: #666;
        }}
        .pdf-container {{
            padding: 20px;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="controls">
        <button onclick="prevPage()" id="prev-btn">← Назад</button>
        <span class="page-info">Страница: <span id="page-num">{page_number}</span> из <span id="page-count">-</span></span>
        <button onclick="nextPage()" id="next-btn">Вперед →</button>
        <button onclick="goToFoundPage()" id="found-btn">К найденному</button>
    </div>

    <div class="pdf-container">
        <div id="loading" class="loading">Загрузка PDF с подсветкой...</div>
        <canvas id="pdf-canvas" style="display: none;"></canvas>
    </div>

    <script>
        // Конфигурация PDF.js
        pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';

        let pdfDoc = null;
        let currentPage = {page_number};
        let foundPage = {page_number};
        let pageRendering = false;
        let pageNumPending = null;
        const scale = 1.8;
        
        // URL для PDF с подсветкой
        const searchTextEncoded = encodeURIComponent("{search_text}");
        const pdfUrl = `/api/pdf/highlighted/{filename}/${{searchTextEncoded}}`;

        // Загрузка PDF документа
        pdfjsLib.getDocument(pdfUrl).promise.then(function(pdf) {{
            pdfDoc = pdf;
            document.getElementById('page-count').textContent = pdf.numPages;
            document.getElementById('loading').style.display = 'none';
            document.getElementById('pdf-canvas').style.display = 'block';
            
            renderPage(currentPage);
            updatePagination();
        }}).catch(function(error) {{
            console.error('PDF loading error:', error);
            document.getElementById('loading').innerHTML = 'Ошибка загрузка PDF: ' + error.message;
        }});

        function renderPage(num) {{
            pageRendering = true;
            pdfDoc.getPage(num).then(function(page) {{
                const viewport = page.getViewport({{scale: scale}});
                const canvas = document.getElementById('pdf-canvas');
                const ctx = canvas.getContext('2d');
                
                canvas.height = viewport.height;
                canvas.width = viewport.width;

                const renderContext = {{
                    canvasContext: ctx,
                    viewport: viewport
                }};
                
                const renderTask = page.render(renderContext);
                renderTask.promise.then(function() {{
                    pageRendering = false;
                    if (pageNumPending !== null) {{
                        renderPage(pageNumPending);
                        pageNumPending = null;
                    }}
                }});
            }});
            
            document.getElementById('page-num').textContent = num;
            currentPage = num;
            updatePagination();
        }}

        function queueRenderPage(num) {{
            if (pageRendering) {{
                pageNumPending = num;
            }} else {{
                renderPage(num);
            }}
        }}

        function prevPage() {{
            if (currentPage <= 1) return;
            currentPage--;
            queueRenderPage(currentPage);
        }}

        function nextPage() {{
            if (currentPage >= pdfDoc.numPages) return;
            currentPage++;
            queueRenderPage(currentPage);
        }}

        function goToFoundPage() {{
            currentPage = foundPage;
            queueRenderPage(currentPage);
        }}

        function updatePagination() {{
            if (pdfDoc) {{
                document.getElementById('prev-btn').disabled = (currentPage <= 1);
                document.getElementById('next-btn').disabled = (currentPage >= pdfDoc.numPages);
            }}
        }}

        // Навигация с помощью клавиатуры
        document.addEventListener('keydown', function(event) {{
            if (event.key === 'ArrowLeft') prevPage();
            if (event.key === 'ArrowRight') nextPage();
            if (event.key === 'Home') goToFoundPage();
        }});
    </script>
</body>
</html>
"""

@app.get("/")
async def root():
    """
    Главная страница со списком PDF файлов
    """
    pdf_files = []
    if os.path.exists(PDF_DIR):
        pdf_files = [f for f in os.listdir(PDF_DIR) if f.lower().endswith('.pdf')]
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>PDF Block Search - Поиск по текстовым блокам</title>
        <style>
            body { font-family: Arial; padding: 20px; background-color: #f8f9fa; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #2c3e50; margin-bottom: 20px; }
            .search-box { 
                margin: 30px 0; 
                padding: 20px;
                background: #f8f9fa;
                border-radius: 8px;
                border: 1px solid #e9ecef;
            }
            input[type="text"] { 
                padding: 12px; 
                width: 300px; 
                border: 1px solid #ddd;
                border-radius: 4px;
                margin-right: 10px;
                font-size: 14px;
            }
            button { 
                padding: 12px 24px;
                background: #007bff;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
            }
            button:hover { 
                background: #0056b3;
            }
            .file-list { list-style: none; padding: 0; }
            .file-list li { margin: 15px 0; }
            .file-list a { 
                text-decoration: none; 
                color: #007bff; 
                font-size: 16px;
                padding: 12px 16px;
                border: 1px solid #e9ecef;
                border-radius: 6px;
                display: block;
                background: white;
                transition: all 0.2s;
            }
            .file-list a:hover { 
                background-color: #f8f9fa;
                border-color: #007bff;
                transform: translateY(-2px);
            }
            .instructions {
                background: #e7f3ff;
                padding: 15px;
                border-radius: 6px;
                border-left: 4px solid #007bff;
                margin: 20px 0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔍 Поиск по текстовым блокам в PDF</h1>
            
            <div class="instructions">
                <strong>Как работает:</strong> Система ищет текстовый блок с наибольшим количеством совпадающих слов 
                и подсвечивает весь блок целиком.
            </div>
            
            <div class="search-box">
                <h3>Быстрый поиск:</h3>
                <input type="text" id="searchText" placeholder="Введите текст для поиска...">
                <button onclick="quickSearch()">Найти в первом файле</button>
            </div>
            
            <h2>📄 Доступные файлы:</h2>
            <ul class="file-list" id="fileList">
    """
    for pdf_file in pdf_files:
        html_content += f'<li><a href="/search/{pdf_file}/пример" onclick="return promptSearch(this)">{pdf_file}</a></li>'
    html_content += """
            </ul>
        </div>

        <script>
            function promptSearch(link) {
                const searchText = prompt('Введите текст для поиска:');
                if (searchText && searchText.trim() !== '') {
                    const href = link.href.replace('/пример', '/' + encodeURIComponent(searchText.trim()));
                    window.location.href = href;
                    return false;
                }
                return false;
            }
            
            function quickSearch() {
                const searchText = document.getElementById('searchText').value.trim();
                if (searchText === '') {
                    alert('Введите текст для поиска');
                    return;
                }
                
                const files = document.getElementById('fileList').getElementsByTagName('a');
                if (files.length > 0) {
                    const firstFile = files[0].href.replace('/пример', '/' + encodeURIComponent(searchText));
                    window.location.href = firstFile;
                }
            }
            
            // Поиск по Enter
            document.getElementById('searchText').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    quickSearch();
                }
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)