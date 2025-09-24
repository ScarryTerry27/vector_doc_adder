import re
import os
import requests
import json
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Tuple
from openai import OpenAI
from collections import defaultdict
import asyncio
from llama_parse import LlamaParse
from llama_parse.base import ResultType
from llama_index.core import Document
from pathlib import Path
from datetime import datetime
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OpenAI_LLM:
    def __init__(self, api_key: Optional[str] = None):
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"

    def invoke(
            self,
            prompt: str,
            system_message: str = "Ты являешься электронным помощником врача.",
    ) -> Dict:
        class AnswerStruct(BaseModel):
            icd: str = Field("", description="Код МКБ-10")
            title: str = Field("", description="Наименование документа")
            published: str = Field("", description="Дата публикации документа")
            review: str = Field("", description="Дата пересмотра документа")
            type: str = Field("", description="Тип документа")
            summary: str = Field("", description="Краткая аннотация документа")
            language: str = Field("", description="Язык документа (ru или eng)")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0
            )
            content = response.choices[0].message.content
            if content:
                try:
                    json_data = json.loads(content)
                    validated_data = AnswerStruct(**json_data)
                    return validated_data.model_dump()
                except (json.JSONDecodeError, ValueError) as e:
                    return {"error": f"Failed to parse response: {str(e)}"}
            return {"error": "Empty response from API"}

        except Exception as e:
            return {"error": str(e)}


class Meta_parser(OpenAI_LLM):
    def __init__(self, progress_callback=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.progress_callback = progress_callback

    def __call__(self, path: str = "/mnt/ramdisk/temp_processing/") -> tuple:
        if self.progress_callback:
            self.progress_callback(10, "Загрузка документов...")
        documents = asyncio.run(parse_documents_parallel(path))
        if self.progress_callback:
            self.progress_callback(30, "Извлечение текста из документов...")
        first_pages_text = self.extract_first_pages_text(documents)
        if self.progress_callback:
            self.progress_callback(50, "Анализ метаданных...")
        meta = self.get_meta(first_pages_text)
        total_docs = len(documents)
        for i, doc in enumerate(documents):
            file_name = doc.metadata["file_name"]
            doc.metadata.update(meta[file_name])
            if self.progress_callback:
                progress = 50 + int((i + 1) / total_docs * 50)
                self.progress_callback(
                    progress,
                    f"Обработка документов: {i + 1}/{total_docs}"
                )
        return meta, documents

    def extract_first_pages_text(self, documents: List, num_pages: int = 3) -> Dict:
        pages_by_file = defaultdict(list)
        for doc in documents:
            file_name = doc.metadata["file_name"]
            pages_by_file[file_name].append(doc)
        first_pages_text = {}
        for file_name, pages in pages_by_file.items():
            first_pages = pages[:num_pages]
            text = [doc.text for doc in first_pages]
            first_pages_text[file_name] = '\n'.join(text)
        return first_pages_text

    @staticmethod
    def make_meta_prompt(text: str) -> str:
        return f"""/no_think
Представлен фрагмент текста из медицинского документа:
{text}
Проанализируй представленный текст и определи:
- код или коды МКБ-10 заболеваний к которым относится данный документ. \
Для сплошных диапазонов МКБ кодов используй сокращенное обозначение \
в виде начального и конечного МКБ кода, например C50-C55.
- название медицинского документа.
- дату публикации медицинского документа и дату его пересмотра \
(при их наличии). Формат даты СТРОГО дд.мм.гггг (01.02.2003). При отсутствии \
даты в ответе выведи пустую строку "".
- тип документа (статья, учебник, инструкция и т.п.). В случае отсутствии \
информации о типе документа ставь метку "?".
- краткую аннотацию документа.
- язык документа (ru или eng). Если документ на английском, \
Ответ в формате json. 
{{
    "icd": "I10, E21",
    "title": "Some words about desease",
    "published": "01.03.2022",
    "review": "01.03.2028",
    "type": "монография",
    "summary": "В данной статье рассматривается лечение..."
    "language": "ru"
}}
Никаких дополнительных комментариев не нужно."""

    def get_meta(self, first_pages_text: Dict) -> Dict:
        meta = defaultdict(dict)
        for file_name, text in first_pages_text.items():
            prompt = self.make_meta_prompt(text)
            response = self.invoke(prompt)
            if isinstance(response, dict):
                response["icd"] = self.normalize_icd_codes(response.get("icd", ""))
                meta[file_name] = response
        return meta

    @staticmethod
    def normalize_icd_codes(icd_string: str) -> str:
        if not icd_string:
            return ""
        icd_string = icd_string.upper().replace(" ", "")
        parts = re.split(r",|\+|\n|;", icd_string)
        result_codes = []
        for part in parts:
            if not part:
                continue
            if "-" in part:
                start, end = part.split("-", 1)
                start_letter = re.match(r"^[A-Z]+", start).group()
                start_num = re.sub(r"^[A-Z]+", "", start)
                end_letter = re.match(r"^[A-Z]+", end).group()
                end_num = re.sub(r"^[A-Z]+", "", end)
                if start_letter != end_letter:
                    result_codes.append(part)
                    continue
                try:
                    start_int = int(start_num.split(".")[0])
                    end_int = int(end_num.split(".")[0])
                    for num in range(start_int, end_int + 1):
                        if "." in start:
                            decimal_part = "." + start.split(".")[1]
                            code = f"{start_letter}{num}{decimal_part}"
                        else:
                            code = f"{start_letter}{num}"
                        result_codes.append(code)
                except ValueError:
                    result_codes.append(part)
            else:
                result_codes.append(part)
        unique_codes = sorted(set(result_codes), key=lambda x: (re.match(r"^[A-Z]+", x).group(),
                                                                int(re.sub(r"^[A-Z]+", "", x).split(".")[0])))
        return ", ".join(unique_codes)


class DS_LLM:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("Хде ключ?")
        self.base_url = "https://api.deepseek.com/chat/completions"
        self.default_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def invoke(
            self,
            prompt: str,
            system_message: str = "Ты являешься электронным помощником врача.",
            max_tokens: int = 4000,
            temperature: float = 0,
            response_format: str = "json_object"
    ) -> Dict:
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {"type": response_format}
        }
        try:
            response = requests.post(
                self.base_url,
                headers=self.default_headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            content = result['choices'][0]['message']['content']
            if isinstance(content, str):
                try:
                    cleaned = content.strip().strip('"').replace('\\"', '"')
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    return {"raw_response": content}
            return content
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"API request failed: {str(e)}")
        except (KeyError, IndexError) as e:
            raise ValueError(f"Invalid API response format: {str(e)}")


class AsyncDocumentParser:
    def __init__(
            self,
            api_key: Optional[str] = os.getenv("LLAMA_CLOUD_API_KEY"),
            max_concurrent: int = 3,
            max_workers: int = 4
    ):
        self.api_key = api_key
        self.max_concurrent = max_concurrent
        self.max_workers = max_workers
        self.supported_extensions = {'.pdf', '.doc', '.docx', '.ppt', '.pptx'}

    async def parse_single_file(self, file_path: Path) -> List[Document]:
        """
        Асинхронно парсит один файл и возвращает список документов
        """
        try:
            logger.info(f"Начало парсинга файла: {file_path.name}")
            parser = LlamaParse(
                api_key=os.getenv("LLAMA_CLOUD_API_KEY"),
                result_type=ResultType.MD,
                language="ru",
                verbose=False
            )
            file_stats = file_path.stat()
            loop = asyncio.get_event_loop()
            parsed_result = await loop.run_in_executor(
                None,
                parser.load_data,
                str(file_path)
            )
            file_documents = []
            for page_num, parsed_doc in enumerate(parsed_result, 1):
                metadata = {
                    'page_label': str(page_num),
                    'file_name': file_path.name,
                    'file_type': self._get_file_type(file_path),
                    'creation_date': datetime.fromtimestamp(file_stats.st_ctime).strftime('%Y-%m-%d'),
                }
                doc = Document(
                    text=parsed_doc.text,
                    metadata=metadata
                )
                file_documents.append(doc)
            logger.info(f"Успешно обработан: {file_path.name} ({len(file_documents)} страниц)")
            return file_documents
        except Exception as e:
            logger.error(f"Ошибка при обработке файла {file_path.name}: {e}")
            return []

    async def parse_directory_batch(
            self,
            directory_path: str,
            file_filter: str = "*.*"  # Можно указать "*.pdf" или "*.*" для всех поддерживаемых
    ) -> List[Document]:
        """
        Асинхронно парсит все файлы в директории с ограничением на количество одновременных операций
        """
        directory = Path(directory_path)
        if not directory.exists():
            raise FileNotFoundError(f"Директория не найдена: {directory_path}")
        if file_filter == "*.*":
            files_to_parse = [
                f for f in directory.iterdir()
                if f.is_file() and f.suffix.lower() in self.supported_extensions
            ]
        else:
            files_to_parse = list(directory.glob(file_filter))
        logger.info(f"Найдено файлов для парсинга: {len(files_to_parse)}")
        if not files_to_parse:
            return []
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def parse_with_semaphore(file_path: Path) -> List[Document]:
            """Парсит файл с ограничением по semaphore"""
            async with semaphore:
                return await self.parse_single_file(file_path)

        tasks = [parse_with_semaphore(file_path) for file_path in files_to_parse]
        results = []
        completed = 0
        total = len(tasks)
        for i in range(0, len(tasks), self.max_concurrent):
            batch = tasks[i:i + self.max_concurrent]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            for result in batch_results:
                completed += 1
                logger.info(f"Прогресс: {completed}/{total} файлов обработано")
                if isinstance(result, list):
                    results.extend(result)
                elif isinstance(result, Exception):
                    logger.error(f"Ошибка в задаче: {result}")
        logger.info(f"Обработка завершена. Всего документов: {len(results)}")
        return results

    async def parse_directory_with_progress(
            self,
            directory_path: str,
            progress_callback=None
    ) -> Tuple[List[Document], dict]:
        """
        Парсит директорию с отслеживанием прогресса
        """
        directory = Path(directory_path)
        files_to_parse = [
            f for f in directory.iterdir()
            if f.is_file() and f.suffix.lower() in self.supported_extensions
        ]
        total_files = len(files_to_parse)
        processed_files = 0
        successful_files = 0
        failed_files = 0
        total_documents = 0
        all_documents = []
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def process_file_with_tracking(file_path: Path):
            nonlocal processed_files, successful_files, failed_files, total_documents
            async with semaphore:
                try:
                    documents = await self.parse_single_file(file_path)
                    if documents:
                        successful_files += 1
                        total_documents += len(documents)
                        return documents
                    else:
                        failed_files += 1
                        return []
                except Exception as e:
                    failed_files += 1
                    logger.error(f"Ошибка при обработке {file_path.name}: {e}")
                    return []
                finally:
                    processed_files += 1
                    if progress_callback:
                        await progress_callback(
                            processed_files,
                            total_files,
                            successful_files,
                            failed_files
                        )

        tasks = [process_file_with_tracking(file_path) for file_path in files_to_parse]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                all_documents.extend(result)
        stats = {
            'total_files': total_files,
            'processed_files': processed_files,
            'successful_files': successful_files,
            'failed_files': failed_files,
            'total_documents': total_documents
        }
        return all_documents, stats

    def _get_file_type(self, file_path: Path) -> str:
        """
        Определяет MIME-тип файла
        """
        extension = file_path.suffix.lower()
        mime_types = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        }
        return mime_types.get(extension, 'application/octet-stream')


async def parse_documents_parallel(
        directory_path: str,
        api_key: Optional[str] = None,
        max_concurrent: int = 4
) -> List[Document]:
    """
    Упрощенная функция для параллельного парсинга документов
    """
    parser = AsyncDocumentParser(api_key=os.getenv("LLAMA_CLOUD_API_KEY"), max_concurrent=max_concurrent)
    return await parser.parse_directory_batch(directory_path)


async def parse_documents_with_stats(
        directory_path: str,
        api_key: Optional[str] = None,
        max_concurrent: int = 3
) -> Tuple[List[Document], dict]:
    """
    Парсит документы и возвращает статистику
    """
    parser = AsyncDocumentParser(api_key=os.getenv("LLAMA_CLOUD_API_KEY"), max_concurrent=max_concurrent)

    async def progress_callback(processed, total, successful, failed):
        logger.info(f"Прогресс: {processed}/{total} ({successful} успешно, {failed} ошибок)")

    return await parser.parse_directory_with_progress(
        directory_path,
        progress_callback=progress_callback
    )
