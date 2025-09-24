import io

from services.object_storage import ObjectStorageService


async def upload_and_verify_file():
    service = ObjectStorageService()

    file_name = "example.txt"
    file_content = b"Hello, this is test data!"
    file_data = io.BytesIO(file_content)
    file_data.name = file_name

    # 1. Upload
    upload_result = await service.upload_file(file_data)
    if upload_result is None:
        print("Upload failed.")
        return

    try:
        file_id = upload_result.json().get("file_id", None)
        if not file_id:
            print("Upload succeeded, but response missing 'file_id'")
            return
    except Exception as e:
        print(f"Error decoding upload response JSON: {e}")
        return

    # 2. Download
    downloaded = await service.download_file(file_id)
    if downloaded is None:
        print("Download failed.")
        return

    if downloaded != file_content:
        print("Downloaded content does not match uploaded content!")
        return

    print("Download: verified successfully.")

    # 3. Delete
    deleted = await service.delete_file(file_id)
    if deleted:
        print("Delete: successful.")
    else:
        print("Delete: failed.")

#
# if __name__ == "__main__":
#     load_dotenv()
#     asyncio.run(upload_and_verify_file())

import requests
resp = requests.get("http://localhost:8080/v1/meta", timeout=3)
print(resp.status_code, resp.json())