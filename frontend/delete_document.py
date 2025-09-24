import streamlit as st

from config import MONGO_URI
from services.db_api_weaviate import Mongo_api


def show_delete_interface():
    st.header("Удаление документов из базы данных")
    mongo = Mongo_api(MONGO_URI)
    search_query = st.text_input(
        "Поиск документов для удаления",
        placeholder="Введите имя файла или название документа",
        key="delete_search"
    )
    if search_query:
        documents = mongo.search_documents(search_query)
        st.info(f"Найдено документов: {len(documents)}")
    else:
        documents = mongo.get_all_documents()
        st.info(f"Всего документов в базе: {len(documents)}")
    if documents:
        st.markdown("### Выберите документы для удаления")
        if 'documents_to_delete' not in st.session_state:
            st.session_state.documents_to_delete = {}
        cols = st.columns([1, 2, 3, 2])
        with cols[0]:
            st.markdown("**Выбрать**")
        with cols[1]:
            st.markdown("**Имя файла**")
        with cols[2]:
            st.markdown("**Название**")
        with cols[3]:
            st.markdown("**Тип**")
        for doc in documents:
            cols = st.columns([1, 2, 3, 2])
            with cols[0]:
                checked = st.session_state.documents_to_delete.get(doc['filename'], False)
                if st.checkbox(
                        "Выбрать",
                        value=checked,
                        key=f"check_{doc['filename']}",
                        label_visibility="collapsed"
                ):
                    st.session_state.documents_to_delete[doc['filename']] = True
                else:
                    st.session_state.documents_to_delete[doc['filename']] = False
            with cols[1]:
                st.write(doc.get("filename", "-"))
            with cols[2]:
                st.write(doc.get("title", "-"))
            with cols[3]:
                st.write(doc.get("document_type", "-"))
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Удалить выбранные", type="primary"):
            if hasattr(st.session_state, 'documents_to_delete'):
                selected = [f for f, checked in st.session_state.documents_to_delete.items() if checked]
                if selected:
                    result = mongo.del_by_filename(selected)
                    if result['success']:
                        st.success(result['message'])
                        st.session_state.documents_to_delete = {
                            k: False for k in st.session_state.documents_to_delete.keys()
                        }
                        st.rerun()
                    else:
                        st.error(result['message'])
                else:
                    st.warning("Не выбрано ни одного документа")
    with col2:
        if st.button("Очистить выбор"):
            if hasattr(st.session_state, 'documents_to_delete'):
                st.session_state.documents_to_delete = {
                    k: False for k in st.session_state.documents_to_delete.keys()
                }
            st.rerun()


def delete_document_page():
    show_delete_interface()
