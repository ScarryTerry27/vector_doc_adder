import streamlit as st
import requests
from config import API_BASE_URL, headers
from werkzeug.security import check_password_hash


def get_user_from_db(email: str):
    url = f"{API_BASE_URL}/get_user"
    data = {"email": email.lower().strip()}

    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 200:
        return response.json().get("user_data")
    elif response.status_code == 404:
        return None
    else:
        raise ValueError("Произошла ошибка")


def login():
    """Функция входа в систему с проверкой роли"""
    st.subheader("🔑 Вход в систему")

    email = st.text_input("Email")
    password = st.text_input("Пароль", type="password", key="password_input")
    login_button = st.button("Войти")
    if login_button:
        user = get_user_from_db(email)
        if not user:
            st.error("Неверный логин или пароль.")
            return

        if not check_password_hash(user["hashed_password"], password):
            st.error("Неверный логин или пароль.")
            return

        # Проверяем, является ли пользователь админом или менеджером
        if user["role"] not in ("ROLE_ADMIN", "ROLE_MANAGER"):
            st.error("У вас нет доступа к системе.")
            return

        # Если всё ок – даём доступ
        st.session_state["authenticated"] = True
        st.session_state["user_role"] = user["role"]
        st.session_state["user_email"] = email
        st.success(f"Добро пожаловать, {email}!")

        # Перезапускаем страницу
        st.rerun()


def check_auth():
    """Проверяет, авторизован ли пользователь"""
    if "authenticated" not in st.session_state or not st.session_state["authenticated"]:
        login()
        st.stop()

    if st.session_state["user_role"] not in ["ROLE_ADMIN", "ROLE_MANAGER"]:
        st.error("У вас нет доступа к этой странице!")
        st.stop()


def logout():
    st.session_state.clear()
    st.rerun()
