import streamlit as st
import os
import config
from backend.utils import get_user_temp_folder, safe_name
from frontend.add_document import add_document_page
from frontend.auth import check_auth
from frontend.delete_document import delete_document_page
from frontend.view_documents import view_documents_page

st.set_page_config(
    page_title="Документный добавлятель",
    page_icon="📂",
    layout="wide"
)

st.markdown("""
<style>
    .sidebar .stButton>button {
        width: 100%;
        justify-content: start;
        padding: 10px 15px;
        margin: 2px 0;
        text-align: left;
        border-radius: 5px;
        transition: all 0.3s;
    }
    .sidebar .stButton>button:hover {
        background-color: #f0f2f6;
    }
    .sidebar .stButton>button:focus {
        background-color: #e6f7ff;
    }
</style>
""", unsafe_allow_html=True)


def main():
    st.sidebar.title("Меню")
    if st.sidebar.button("📥 Добавить документ", key="add_btn"):
        st.session_state.current_page = "add"

    if st.sidebar.button("🗑️ Удалить документ", key="delete_btn"):
        st.session_state.current_page = "delete"

    if st.sidebar.button("👁️ Просмотреть документы", key="view_btn"):
        st.session_state.current_page = "view"

    st.sidebar.markdown("---")

    if "current_page" not in st.session_state:
        st.session_state.current_page = "add"

    st.title("📂 Система управления документами ВБД")
    user_email = st.session_state.get("user_email", "default")
    folder = get_user_temp_folder(user_key=safe_name(user_email))
    st.session_state["temp_folder"] = folder
    if st.session_state.current_page == "add":
        add_document_page(folder)
    elif st.session_state.current_page == "delete":
        delete_document_page()
    elif st.session_state.current_page == "view":
        view_documents_page()

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Временная папка: `{os.path.abspath(folder)}`")
    if os.path.exists(folder):
        st.sidebar.caption(f"Файлов в папке: {len(os.listdir(folder))}")


if __name__ == "__main__":
    check_auth()
    if "authenticated" not in st.session_state or not st.session_state["authenticated"]:
        st.warning("Пожалуйста, войдите в систему!")
        st.stop()  # Останавливаем выполнение кода
    main()
