from typing import List, Dict, Literal
import httpx
import os
from typing import Optional


class StorageClient:
    def __init__(self):
        self.url = os.getenv("STORAGE_URL", "http://localhost:9000")
        self.headers = {
            os.getenv("API_KEY_NAME", "x-api-key"): os.getenv("API_KEY", "secret")
        }
        self.client = httpx.Client(timeout=90.0)

    def close(self):
        self.client.close()

    def upload_fileobj(self, file_bytes: bytes, filename: str, folder: Literal["sources", "cr", "others"] = "sources"):
        url = f"{self.url}/upload/{folder}"
        files = {
            "file": (filename, file_bytes, "text/html" if filename.endswith(".html") else "application/octet-stream")
        }
        r = self.client.post(url, headers=self.headers, files=files)  # без params
        try:
            r.raise_for_status()
        except Exception:
            # логируем для дебага
            raise
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text

    def download_fileobj(self, file_name: str, folder: Literal["cr", "sources"] = "sources"):
        url = f"{self.url}/download/{file_name}"
        r = self.client.get(url, headers=self.headers, params={"type_doc": folder})
        r.raise_for_status()
        return r.content

    def delete_fileobj(self, file_name: str) -> bool:
        url = f"{self.url}/delete/{file_name}"
        r = self.client.delete(url, headers=self.headers, params={"type_doc": "cr"})
        r.raise_for_status()
        return r.status_code == 204


# object_storage.py (sync)
class ObjectStorageService:
    def __init__(self, storage_client: StorageClient | None = None):
        self.storage_client = storage_client or StorageClient()

    def close(self):
        self.storage_client.close()

    def upload_file(self, file_bytes: bytes, filename: str, folder: str = "sources"):
        return self.storage_client.upload_fileobj(file_bytes, filename, folder)

    def download_file(self, file_name: str) -> bytes:
        return self.storage_client.download_fileobj(file_name)

    def delete_file(self, file_name: str) -> bool:
        return self.storage_client.delete_fileobj(file_name)

    def upload_html_documents(self, html_documents: List[Dict[str, str]], folder: str = "html/") -> List:
        """
        html_documents: [{"file_name": "a.html", "html": "<html>...</html>"}, ...]
        """
        uploaded = []
        for doc in html_documents:
            filename = doc["file_name"]
            file_bytes = doc["html"].encode("utf-8")
            res = self.storage_client.upload_fileobj(file_bytes, filename, folder)
            uploaded.append(res)
        return uploaded
