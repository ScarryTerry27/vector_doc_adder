import os
import datetime
from contextlib import contextmanager
from typing import Dict, List, Optional, Generator
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
import weaviate
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.vector_stores.weaviate import WeaviateVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding


class Mongo_api:
    def __init__(
            self,
            connection_string: str = "mongodb://localhost:27017/",
            db_name: str = "vdb_docs",
            collection_name: str = "test_2"
    ) -> None:
        self.connection_string = connection_string
        self.db_name = db_name
        self.collection_name = collection_name

    @contextmanager
    def _get_collection(self) -> Generator[Collection, None, None]:
        client = None
        try:
            client = MongoClient(self.connection_string)
            db: Database = client[self.db_name]
            collection: Collection = db[self.collection_name]
            yield collection
        finally:
            if client is not None:
                client.close()

    def add_doc(self, filename: str, metadata: Dict, username) -> Dict:
        with self._get_collection() as collection:
            try:
                existing_doc = collection.find_one(
                    {"title": metadata.get("title", "")},
                    {"_id": 1}
                )
                if existing_doc:
                    return {
                        "success": False,
                        "inserted_id": None,
                        "filename": filename,
                        "error": f"Документ с названием '{metadata.get('title')}' уже существует (ID: {existing_doc['_id']})"
                    }

                document = {
                    "filename": filename,
                    "title": metadata.get("title", ""),
                    "document_type": metadata.get("type", ""),
                    "icd_codes": metadata.get("icd", ""),
                    "publication_date": metadata.get("published", ""),
                    "review_date": metadata.get("review", ""),
                    "summary": metadata.get("summary", ""),
                    "created_at": datetime.datetime.now(),
                    "status": "active",
                    "user_email": username,
                    "language": metadata.get("language", "")
                }
                result = collection.insert_one(document)
                return {
                    "success": True,
                    "inserted_id": str(result.inserted_id),
                    "filename": filename,
                    "error": None
                }
            except Exception as e:
                return {
                    "success": False,
                    "inserted_id": None,
                    "filename": filename,
                    "error": f"Ошибка при добавлении документа: {str(e)}"
                }

    def get_all_documents(self, limit: int = 100) -> List[Dict]:
        with self._get_collection() as collection:
            try:
                projection = {
                    "_id": 0,
                    "filename": 1,
                    "title": 1,
                    "document_type": 1,
                    "publication_date": 1,
                    "review_date": 1,
                    "icd_codes": 1,
                    "summary": 1,
                    "status": 1,
                    "user_email": 1
                }
                return list(collection.find({}, projection).limit(limit))
            except Exception as e:
                print(f"Ошибка при получении документов: {e}")
                return []

    def get_document_details(self, filename: str) -> Optional[Dict]:
        with self._get_collection() as collection:
            try:
                document = collection.find_one(
                    {"filename": filename},
                    {"_id": 0}
                )
                return document
            except Exception as e:
                print(f"Ошибка при получении документа {filename}: {e}")
                return None

    def search_documents(self, search_query: str) -> List[Dict]:
        with self._get_collection() as collection:
            try:
                query = {
                    "$or": [
                        {"filename": {"$regex": search_query, "$options": "i"}},
                        {"title": {"$regex": search_query, "$options": "i"}},
                        {"summary": {"$regex": search_query, "$options": "i"}}
                    ]
                }
                return list(collection.find(query, {"_id": 0}).limit(50))
            except Exception as e:
                print(f"Ошибка поиска: {e}")
                return []

    def del_by_filename(self, filenames: List[str]) -> Dict:
        with self._get_collection() as collection:
            try:
                result = collection.delete_many(
                    {"filename": {"$in": filenames}}
                )
                return {
                    "success": True,
                    "deleted_count": result.deleted_count,
                    "message": f"Удалено документов: {result.deleted_count}"
                }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Ошибка при удалении: {str(e)}"
                }

    def del_by_title(self, filename: str) -> Dict:
        with self._get_collection() as collection:
            try:
                result = collection.delete_one({"filename": filename})
                if result.deleted_count == 1:
                    return {
                        "success": True,
                        "message": f"Документ {filename} успешно удален"
                    }
                return {
                    "success": False,
                    "message": f"Документ {filename} не найден"
                }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Ошибка при удалении: {str(e)}"
                }


class VDB_api:
    OPENAI_SECRETS = {
        "ONCO": os.getenv("OPENAI_API_KEY_ONCO"),
        "CARDIO": os.getenv("OPENAI_API_KEY_CARDIO")
    }

    def __init__(
            self,
            app: str = "ONCO",
            embedding_model: str = "text-embedding-3-small",
            splitter: str = "markdown",
            host: str = "localhost",
            port: int = 8080,
            grpc_port: int = 50051,
            index_dim: int = 1536,  # для text-embedding-3-small
            index_name_default: str = "Test",
            readiness_timeout_s: int = 30,
    ) -> None:
        self.index_name_default = index_name_default
        self.readiness_timeout_s = readiness_timeout_s

        self.openai_key = self.OPENAI_SECRETS.get(app) or os.getenv("OPENAI_API_KEY")
        if not self.openai_key:
            raise ValueError("OpenAI API key не найден. Установите OPENAI_API_KEY или *_ONCO/*_CARDIO.")

        self.embed_model = OpenAIEmbedding(model=embedding_model, api_key=self.openai_key)

        if splitter == "simple":
            from llama_index.core.node_parser import SimpleNodeParser
            self.node_splitter = SimpleNodeParser.from_defaults(
                chunk_size=512, chunk_overlap=20, separator="\n\n"
            )
        elif splitter == "semantic":
            from llama_index.core.node_parser.text.semantic_splitter import SemanticSplitterNodeParser
            self.node_splitter = SemanticSplitterNodeParser(
                buffer_size=2,
                embed_model=self.embed_model,
                breakpoint_percentile_threshold=90,
                include_metadata=True,
                include_prev_next_rel=True,
            )
        elif splitter == "markdown": 
            from llama_index.core.node_parser import MarkdownNodeParser
            self.node_splitter = MarkdownNodeParser()
        else:
            raise ValueError("Поддерживаются только 'simple', 'semantic' и 'markdown' парсеры")

        self.connection_params = {
            "host": host,
            "port": port,
            "grpc_port": grpc_port,
            # включим init checks — они полезны в деве
            "skip_init_checks": False,
            "auth_credentials": weaviate.auth.AuthApiKey(os.getenv("WEAVIATE_API_KEY", "")),
        }
        self.index_dim = index_dim

    @contextmanager
    def _db_connection(self) -> Generator[weaviate.WeaviateClient, None, None]:
        client = None
        try:
            client = weaviate.connect_to_local(**self.connection_params)
            # ждём готовность ноды (weaviate v4 API)
            import time
            start = time.time()
            while True:
                try:
                    if client.is_ready():
                        break
                except Exception:
                    pass
                if time.time() - start > self.readiness_timeout_s:
                    raise RuntimeError("Weaviate не готов (timeout)")
                time.sleep(1)

            yield client
        finally:
            if client is not None:
                client.close()

    def _ensure_collection(self, client: weaviate.WeaviateClient, index_name: str):
        # Попробуем через LlamaIndex-обёртку: она умеет создавать схему при отсутствии
        # (в актуальных версиях create_schema_if_missing=True по умолчанию, но укажем явно)
        return WeaviateVectorStore(
            weaviate_client=client,
            index_name=index_name,
            text_key="text",  # поле с текстом
            create_schema_if_missing=True,
        )

    def __call__(self, doc_pages: List, index_name: str | None = None) -> bool:
        idx = index_name or self.index_name_default
        try:
            # я убрал фильтрацию метаданных, пусть вся мета заходит в чанки
            nodes = self.node_splitter.get_nodes_from_documents(doc_pages)
            if not nodes:
                print("Не удалось создать узлы из документов")
                return False
            with self._db_connection() as client:
                vector_store = self._ensure_collection(client, idx)
                storage_context = StorageContext.from_defaults(vector_store=vector_store)
                VectorStoreIndex(
                    nodes,
                    storage_context=storage_context,
                    embed_model=self.embed_model,
                    show_progress=True,
                )
                print(f"Успешно добавлены узлы в индекс '{idx}'")
                return True
        except Exception as e:
            print(f"Ошибка при индексации: {str(e)}")
            return False