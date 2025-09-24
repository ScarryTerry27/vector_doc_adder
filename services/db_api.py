import os
import datetime
from typing import Dict, List, Optional, Sequence
import asyncio
from pymongo import MongoClient
from pinecone import Pinecone, ServerlessSpec
from llama_index.core.schema import BaseNode, TextNode
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding


class Mongo_api:
    def __init__(
            self,
            client: MongoClient = MongoClient("mongodb://localhost:27017/"),
            db_name: str = "vdb_docs",
            collection_name: str = "test_2"
    ) -> None:
        db = client[db_name]
        self.collection = db[collection_name]

    def add_doc(self, filename: str, metadata: Dict) -> Dict:
        try:
            existing_doc = self.collection.find_one(
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
            }
            result = self.collection.insert_one(document)
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
                "status": 1
            }
            return list(self.collection.find({}, projection).limit(limit))
        except Exception as e:
            print(f"Ошибка при получении документов: {e}")
            return []

    def get_document_details(self, filename: str) -> Optional[Dict]:
        try:
            document = self.collection.find_one(
                {"filename": filename},
                {"_id": 0}
            )
            return document
        except Exception as e:
            print(f"Ошибка при получении документа {filename}: {e}")
            return None

    def search_documents(self, search_query: str) -> List[Dict]:
        try:
            query = {
                "$or": [
                    {"filename": {"$regex": search_query, "$options": "i"}},
                    {"title": {"$regex": search_query, "$options": "i"}},
                    {"summary": {"$regex": search_query, "$options": "i"}}
                ]
            }
            return list(self.collection.find(query, {"_id": 0}).limit(50))
        except Exception as e:
            print(f"Ошибка поиска: {e}")
            return []

    def del_by_filename(self, filenames: List[str]) -> Dict:
        try:
            result = self.collection.delete_many(
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
        try:
            result = self.collection.delete_one({"filename": filename})
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
    PROJECT_SECRETS = {
        "ONCO": os.getenv("PINECONE_API_KEY_ONCO"),
        "CARDIO": os.getenv("PINECONE_API_KEY_CARDIO")
    }
    OPENAI_SECRETS = {
        "ONCO": os.getenv("OPENAI_API_KEY_ONCO"),
        "CARDIO": os.getenv("OPENAI_API_KEY_CARDIO")
    }

    def __init__(
            self,
            app: str = "ONCO",
            embedding_model: str = "text-embedding-3-small",
            splitter: str = "semantic"
    ) -> None:
        self.api_key = self.PROJECT_SECRETS.get(app)
        self.openai_key = self.OPENAI_SECRETS.get(app)
        if not self.api_key or not self.openai_key:
            raise ValueError("API keys for Pinecone or OpenAI not found in environment variables")
        self.pc = Pinecone(api_key=self.api_key)
        self.embed_model = OpenAIEmbedding(
            model=embedding_model,
            api_key=self.openai_key
        )
        if splitter == "simple":
            from llama_index.core.node_parser import SimpleNodeParser
            self.node_splitter = SimpleNodeParser.from_defaults(
                chunk_size=512,
                chunk_overlap=20,
                separator="\n\n"
            )
        elif splitter == "semantic":
            from llama_index.core.node_parser.text.semantic_splitter import SemanticSplitterNodeParser
            self.node_splitter = SemanticSplitterNodeParser(
                buffer_size=2,
                embed_model=self.embed_model,
                breakpoint_percentile_threshold=90,
                include_metadata=True,
                include_prev_next_rel=True
            )
        else:
            raise ValueError("Поддерживаются только 'simple' и 'semantic' парсеры")

    def __call__(self, doc_pages: List, index_name: str = "test") -> bool:
        try:
            nodes = self.nodes_splitter(doc_pages)
            if not nodes:
                print("Не удалось разбить документы на nodes")
                return False
            return self._sync_upsert_nodes(index_name, nodes)
        except Exception as call_error:
            print(f"Ошибка при обработке документов: {str(call_error)}")
            return False

    def _sync_upsert_nodes(self, index_name: str, nodes: Sequence[TextNode]) -> bool:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._async_upsert_nodes(index_name, nodes))
        except Exception as sync_error:
            print(f"Ошибка в синхронном выполнении: {str(sync_error)}")
            return False

    async def _async_upsert_nodes(self, index_name: str, nodes: Sequence[TextNode]) -> bool:
        try:
            base_nodes = []
            for node in nodes:
                if isinstance(node, TextNode):
                    if not node.embedding:
                        node.embedding = await self.embed_model.aget_text_embedding(node.text)
                    base_nodes.append(node)
            if not base_nodes:
                print("Нет подходящих nodes для загрузки")
                return False
            await self._upsert_to_pinecone(index_name, base_nodes)
            print(f"Успешно загружено {len(base_nodes)} nodes в индекс {index_name}")
            return True
        except Exception as async_error:
            print(f"Ошибка при загрузке в Pinecone: {str(async_error)}")
            return False

    async def _ensure_index(self, index_name: str, dimension: int = 1536) -> str:
        try:
            existing_indexes = [index.name for index in self.pc.list_indexes()]
            if index_name not in existing_indexes:
                self.pc.create_index(
                    name=index_name,
                    dimension=dimension,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1")
                )
            return index_name
        except Exception as index_error:
            error_msg = str(index_error)
            if "400" in error_msg:
                raise ValueError(f"Некорректное имя индекса: {index_name}."
                                 "Допустимы только строчные латинские буквы, цифры и дефисы")
            raise

    async def _upsert_to_pinecone(self, index_name: str, nodes: List[BaseNode]):
        try:
            await self._ensure_index(index_name)
            vector_store = PineconeVectorStore(
                pinecone_index=self.pc.Index(index_name),
                embed_model=self.embed_model
            )
            await vector_store.async_add(nodes)
        except Exception as upsert_error:
            error_msg = str(upsert_error)
            if "400" in error_msg:
                raise ValueError(f"Некорректный запрос к Pinecone: {error_msg}")
            elif "401" in error_msg:
                raise PermissionError("Ошибка аутентификации Pinecone. Проверьте API-ключ")
            else:
                raise

    def nodes_splitter(self, doc_pages: List) -> List:
        try:
            for doc in doc_pages:
                doc.metadata = {
                    "file_name": doc.metadata.get("file_name"),
                    "doc_title": doc.metadata.get("title")
                }
            nodes = self.node_splitter.get_nodes_from_documents(doc_pages)
            return nodes
        except Exception as e:
            print("Ошибка при разбиении документа на чанки:", str(e))
            return []