import logging
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = (
    f"mongodb://{os.getenv('MONGO_INITDB_ROOT_USERNAME')}:"
    f"{os.getenv('MONGO_INITDB_ROOT_PASSWORD')}@"
    f"{os.getenv('MONGO_CONTAINER_NAME')}:27017"
)

API_BASE_URL = os.getenv("API_BASE_URL")
headers = {os.getenv("API_BASE_NAME"): os.getenv("API_BASE_KEY")}

TEMP_FOLDER = "/tmp/temp_processing/"