import streamlit as st

from config import MONGO_URI
from services.db_api_weaviate import Mongo_api


def show_document_viewer():
    st.header("Просмотр документов в базе данных")
    mongo = Mongo_api(MONGO_URI)
    search_query = st.text_input(
        "Введите текст для поиска",
        placeholder="Поиск по названию или содержимому",
        label_visibility="visible"
    )
    if search_query:
        documents = mongo.search_documents(search_query)
        st.success(f"Найдено документов: {len(documents)}")
    else:
        documents = mongo.get_all_documents()
        st.info(f"Всего документов в базе: {len(documents)}")
    if documents:
        for i, doc in enumerate(documents):
            with st.container(border=True):
                col1, col2 = st.columns(2)
                st.markdown("**Добавил в базу данных:**")
                st.write(doc.get("user_email", "Не указано"))
                with col1:
                    st.markdown("**Название документа:**")
                    st.write(doc.get("title", "Не указано"))
                    st.markdown("**Тип документа:**")
                    st.write(doc.get("document_type", "Не указано"))
                with col2:
                    st.markdown("**Дата публикации:**")
                    st.write(doc.get("publication_date", "Не указана"))
                    st.markdown("**Дата пересмотра:**")
                    st.write(doc.get("review_date", "Не указана"))
                st.markdown("**Коды МКБ:**")
                st.code(doc.get("icd_codes", "Не указаны"), language="text")

                st.markdown("**Аннотация:**")
                st.text_area(
                    " ",
                    value=doc.get("summary", "Нет аннотации"),
                    height=100,
                    disabled=True,
                    label_visibility="collapsed",
                    key=f"summary_{i}"
                )


def view_documents_page():
    show_document_viewer()
