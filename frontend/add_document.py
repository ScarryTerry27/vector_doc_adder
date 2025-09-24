import os
import time
import shutil
from pathlib import Path
import streamlit as st
from llama_index.core.schema import Document

from config import MONGO_URI
from services.meta_parser_ds import Meta_parser
from services.db_api_weaviate import Mongo_api, VDB_api
from services.preprocessing import PreprocessingService, MDProcessor


def save_uploaded_files(uploaded_files, temp_folder):
    try:
        shutil.rmtree(temp_folder)
        Path(temp_folder).mkdir()
        for uploaded_file in uploaded_files:
            with open(os.path.join(temp_folder, uploaded_file.name), "wb") as f:
                f.write(uploaded_file.getbuffer())
        return True, f"Обработано {len(uploaded_files)} файлов"
    except Exception as e:
        return False, f"Ошибка: {str(e)}"


def step_upload_files(temp_folder):
    st.header("Загрузка документов")
    uploaded_files = st.file_uploader(
        "Выберите файлы для обработки",
        accept_multiple_files=True,
        type="pdf",
        help="Выберите один или несколько PDF-файлов"
    )
    if uploaded_files:
        st.subheader("Выбранные файлы:")
        for file in uploaded_files:
            st.write(f"- {file.name}")
    if uploaded_files and st.button("Загрузить файлы", type="primary"):
        success, message = save_uploaded_files(uploaded_files, temp_folder)
        if success:
            st.session_state["uploaded_files"] = uploaded_files
            st.session_state["step"] = 1
            st.rerun()
        else:
            st.error(message)


def step_process_files(temp_folder):
    st.header("Обработка документов")
    if not st.session_state.get("uploaded_files"):
        st.warning("Нет загруженных файлов для обработки")
        st.button("Вернуться к загрузке", on_click=lambda: st.session_state.update({"step": 0}))
        return
    progress_container = st.empty()
    if st.button("Начать обработку", type="primary"):
        with progress_container.container():
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_progress(percent, message):
                progress_bar.progress(percent)
                status_text.info(message)
                time.sleep(0.05)

            try:
                meta_prsr = Meta_parser(progress_callback=update_progress)
                meta, documents = meta_prsr(temp_folder)
                st.session_state["meta"] = meta
                st.session_state["documents"] = documents
                st.session_state["step"] = 2
                status_text.success("Обработка завершена успешно!")
                time.sleep(0.1)
                st.rerun()
            except Exception as e:
                status_text.error(f"Ошибка обработки: {str(e)}")
    st.write("Загруженные файлы готовы к обработке")
    st.button("Вернуться к загрузке", on_click=lambda: st.session_state.update({"step": 0}))


def step_edit_meta():
    st.header("Проверка результатов обработки")
    if "file_selections" not in st.session_state:
        st.session_state.file_selections = {filename: False for filename in st.session_state["meta"].keys()}
    if "editable_meta" not in st.session_state:
        st.session_state.editable_meta = st.session_state["meta"].copy()
    st.subheader("Выберите файлы для обработки")
    selected_files = []

    def validate_icd(icd_str: str) -> tuple[bool, str]:
        if not icd_str or icd_str == "Не указано":
            return True, icd_str
        normalized = ", ".join([code.strip() for code in icd_str.split(",") if code.strip()])
        codes = [code.strip() for code in normalized.split(",")]
        for code in codes:
            if not code:
                continue
            if len(code) < 2:
                return False, "Код должен содержать минимум 2 символа"
            first_char = code[0]
            if not (first_char.isalpha() and first_char.isupper() and ord(first_char) < 128):
                return False, "Первый символ должен быть заглавной латинской буквой (A-Z)"
            if not code[1:].replace(".", "").isdigit():
                return False, "После буквы должны быть цифры (возможно с точкой)"
        return True, normalized

    for filename, data in st.session_state["meta"].items():
        with st.container(border=True):
            col1, col2 = st.columns([1, 20])
            with col1:
                is_selected = st.checkbox(
                    f"Выбрать {filename}",
                    key=f"select_{filename}",
                    value=st.session_state.file_selections[filename],
                    label_visibility="collapsed",
                    on_change=lambda f=filename: st.session_state.file_selections.update(
                        {f: not st.session_state.file_selections[f]}
                    )
                )
            with col2:
                with st.expander(f"📄 {filename}", expanded=True):
                    st.markdown("**Наименование:**")
                    new_title = st.text_input(
                        "Наименование",
                        value=data.get("title", "Не указано"),
                        key=f"title_{filename}",
                        label_visibility="collapsed"
                    )
                    st.session_state.editable_meta[filename]["title"] = new_title
                    st.markdown("**МКБ-коды:**")
                    new_icd = st.text_input(
                        "МКБ-коды (например: C34.90, D12.6)",
                        value=data.get("icd", "Не указано"),
                        key=f"icd_{filename}",
                        label_visibility="collapsed"
                    )
                    st.markdown("**Язык документа:**")
                    new_lang = st.text_input(
                        "Язык документа",
                        value=data.get("language", "Не указано"),
                        key=f"language_{filename}",
                        label_visibility="collapsed"
                    )

                    if is_selected:
                        is_valid, normalized_icd = validate_icd(new_icd)

                        if not is_valid:
                            st.error("Некорректный формат МКБ-кода. Пример: C34.90, D12.6")
                        else:
                            st.session_state.editable_meta[filename]["icd"] = normalized_icd
                    else:
                        st.session_state.editable_meta[filename]["icd"] = new_icd
                    st.markdown("**Дата публикации:**")
                    new_published = st.text_input(
                        "Дата публикации",
                        value=data.get("published", "Не указано"),
                        key=f"published_{filename}",
                        label_visibility="collapsed"
                    )
                    st.session_state.editable_meta[filename]["language"] = new_lang
                    st.session_state.editable_meta[filename]["published"] = new_published
                    st.markdown("**Дата пересмотра:**")
                    new_review = st.text_input(
                        "Дата пересмотра",
                        value=data.get("review", "Не указано"),
                        key=f"review_{filename}",
                        label_visibility="collapsed"
                    )
                    st.session_state.editable_meta[filename]["review"] = new_review
                    st.markdown("**Тип документа:**")
                    new_type = st.text_input(
                        "Тип документа",
                        value=data.get("type", "Не указано"),
                        key=f"type_{filename}",
                        label_visibility="collapsed"
                    )
                    st.session_state.editable_meta[filename]["type"] = new_type
                    st.markdown("**Краткая аннотация:**")
                    new_summary = st.text_area(
                        "Краткая аннотация",
                        value=data.get("summary", "Не указано"),
                        key=f"summary_{filename}",
                        label_visibility="collapsed",
                        height=180
                    )
                    st.session_state.editable_meta[filename]["summary"] = new_summary
            if st.session_state.file_selections[filename]:
                selected_files.append(filename)
    if selected_files:
        all_valid = True
        for filename in selected_files:
            icd_value = st.session_state.editable_meta[filename].get("icd", "")
            is_valid, _ = validate_icd(icd_value)
            if not is_valid:
                all_valid = False
                break
        if st.button("Записать в ВБД", type="primary", use_container_width=True, disabled=not all_valid):
            if not all_valid:
                st.error("Некоторые выбранные файлы содержат некорректные МКБ-коды")
            else:
                documents = st.session_state.get("documents", [])
                for doc in documents:
                    file_name = doc.metadata["file_name"]
                    if file_name in st.session_state.editable_meta:
                        doc.metadata["doc_title"] = st.session_state.editable_meta[file_name].get("title", "")
                st.session_state["meta"] = st.session_state.editable_meta.copy()
                st.session_state["documents"] = documents
                st.session_state.selected_files = selected_files
                st.session_state["step"] = 3
                st.rerun()
    else:
        st.warning("Выберите хотя бы один файл для продолжения")


def step_add_db():
    if "meta" not in st.session_state or not st.session_state.meta:
        st.warning("Нет данных для сохранения")
        return

    mongo = Mongo_api(connection_string=MONGO_URI)
    vdb = VDB_api(app="ONCO", host=os.getenv("WEAVIATE_CONTAINER_NAME"))
    documents = st.session_state.documents
    meta_data = st.session_state.meta
    total_files = len(meta_data)
    total_steps = 3

    progress_bar = st.progress(5)
    status_text = st.empty()
    results = []

    for i, (filename, metadata) in enumerate(meta_data.items(), 1):
        doc_pages = [p for p in documents if p.metadata.get("file_name") == filename]
        processed_texts = []
        processed_doc_pages = []
        for page in doc_pages:
            new_text = MDProcessor.add_labels(page.text)
            new_page = Document(text=new_text, metadata=page.metadata.copy())
            processed_doc_pages.append(new_page)
            processed_texts.append(MDProcessor.add_anchors(new_text))
        md_text = ''.join(processed_texts)
        preproc = PreprocessingService()
        file_path = os.path.join(st.session_state["temp_folder"], filename)
        if not os.path.exists(file_path):
            results.append({"success": False, "filename": filename, "error": f"Файл не найден: {file_path}"})
            progress = int(((i - 1) * total_steps + 1) / (total_files * total_steps) * 100)
            progress_bar.progress(max(5, progress))
            continue
        md_filename = f"{filename}.md"
        processed_doc_pages = preproc.upload_file_to_storage(md_text, md_filename, processed_doc_pages, folder="sources")    # Здесь правильно указана папка "sources"?
        # doc_pages = preproc.upload_file_to_storage(f, filename, doc_pages, folder="sources")
        status_text.text(f"Файл {i}/{total_files}: {filename} (Векторная БД)")
        time.sleep(0.1)
        try:
            success = vdb(processed_doc_pages, "Test")
            if not success:
                results.append({"success": False, "filename": filename, "error": "Ошибка векторной БД"})
                progress = int(((i - 1) * total_steps + 1) / (total_files * total_steps) * 100)
                progress_bar.progress(max(5, progress))
                continue
        except Exception as e:
            st.error(e)
            time.sleep(3)
            results.append({"success": False, "filename": filename, "error": f"Ошибка векторной БД: {str(e)}"})
            progress = int(((i - 1) * total_steps + 1) / (total_files * total_steps) * 100)
            progress_bar.progress(max(5, progress))
            continue

        progress = int(((i - 1) * total_steps + 2) / (total_files * total_steps) * 100)
        progress_bar.progress(max(5, progress))
        status_text.text(f"Файл {i}/{total_files}: {filename} (MongoDB)")

        try:
            result = mongo.add_doc(filename, metadata, st.session_state.get("user_email", "default"))
            results.append(result)
        except Exception as e:
            st.error(e)
            time.sleep(3)
            results.append({"success": False, "filename": filename, "error": f"Ошибка MongoDB: {str(e)}"})

        progress = int((i * total_steps) / (total_files * total_steps) * 100)
        progress_bar.progress(progress)
        progress_bar.empty()
        status_text.empty()

    success_count = sum(1 for r in results if r.get("success", False))
    error_count = len(results) - success_count
    if success_count > 0:
        st.success(f"Успешно сохранено {success_count}/{total_files} документов")
    if error_count > 0:
        print(f"Ошибки при сохранении {error_count} документов:")
        st.error(f"Ошибки при сохранении {error_count} документов:")
        for result in filter(lambda r: not r.get("success", True), results):
            st.write(f"• {result['filename']}: {result.get('error', 'Неизвестная ошибка')}")
    time.sleep(3)
    st.info("Нажмите в любом месте для продолжения...")
    st.session_state["waiting_for_click"] = True
    if st.session_state.get("waiting_for_click", False):
        reset_application_state()
        st.session_state["step"] = 0
        st.session_state.pop("waiting_for_click", None)
        st.rerun()


def cleanup_temp_folder():
    try:
        temp_folder = st.session_state.get("temp_folder")
        if temp_folder and Path(temp_folder).exists():
            shutil.rmtree(temp_folder)
            print(f"Очищена временная папка: {temp_folder}")
    except Exception as e:
        print(f"Ошибка при очистке временной папки: {e}")
    finally:
        if "temp_folder" in st.session_state:
            del st.session_state["temp_folder"]


def reset_application_state():
    cleanup_temp_folder()
    for key in ["meta", "uploaded_files", "processed", "file_selections", "editable_meta", "select_complete"]:
        if key in st.session_state:
            del st.session_state[key]


def add_document_page(temp_folder):
    if "step" not in st.session_state:
        st.session_state["step"] = 0
        st.session_state.processed = False
        st.session_state.uploaded_files = []
        st.session_state["temp_folder"] = temp_folder

    if st.session_state["step"] == 0:
        step_upload_files(temp_folder)
    elif st.session_state["step"] == 1:
        step_process_files(temp_folder)
    elif st.session_state["step"] == 2:
        step_edit_meta()
    elif st.session_state["step"] == 3:
        step_add_db()
