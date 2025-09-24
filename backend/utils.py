from pathlib import Path
import re
import streamlit as st

from config import TEMP_FOLDER


def safe_name(s: str, fallback: str = "anon") -> str:
    if not s:
        return fallback
    # только буквы, цифры, точка, дефис, подчеркивание и @; остальное -> _
    s = re.sub(r"[^a-zA-Z0-9._@-]", "_", s)
    # на всякий: убираем возможные разделители пути
    s = s.replace("/", "_").replace("\\", "_")
    return s or fallback


def get_user_temp_folder(user_key) -> Path:
    # если нет вообще ничего — уникальный токен на сессию
    if not user_key or user_key == "anon":
        if "tmp_user_key" not in st.session_state:
            import secrets
            st.session_state.tmp_user_key = f"session_{secrets.token_hex(6)}"
        user_key = st.session_state.tmp_user_key

    folder = Path(f"{TEMP_FOLDER}/{user_key}")
    folder.mkdir(parents=True, exist_ok=True)
    return folder
