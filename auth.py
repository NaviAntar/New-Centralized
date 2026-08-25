"""
auth.py — gerbang dua tingkat untuk HR Recruitment Portal.

Kenapa ada: versi lama tidak punya login sama sekali, sementara datanya berisi
nama asli, hasil psikotes, hasil MCU, dan alasan kegagalan 1.365 orang. Siapa
pun yang punya URL bisa membacanya (temuan T-02).

Dua peran:
  Recruitment  seluruh fungsi, termasuk Recruitment Room dan export
  User         Overview, Tracking Kandidat, Tracking Posisi, Weekly Report

Ini gerbang password, bukan sistem identitas: ia menahan orang yang tidak
berkepentingan, tapi tidak bisa membedakan siapa yang login memakai password
yang sama. Kalau nanti perlu jejak audit per orang, ini harus diganti SSO.
"""
from __future__ import annotations

import hmac

import streamlit as st

import config as C
import theme

_SESSION_KEY = "auth_role"


def _password_for(role: str) -> str:
    """Password satu peran. st.secrets menang atas nilai default di config."""
    try:
        return str(st.secrets["auth"][role])
    except Exception:
        return C.DEFAULT_PASSWORDS[role]


def _match(entered: str) -> str | None:
    """Cocokkan password ke peran. compare_digest supaya waktu bandingnya tetap."""
    for role in (C.ROLE_RECRUITMENT, C.ROLE_USER):
        if hmac.compare_digest(entered.strip(), _password_for(role)):
            return role
    return None


def current_role() -> str | None:
    return st.session_state.get(_SESSION_KEY)


def can_view(page: str) -> bool:
    return current_role() in C.PAGE_ACCESS.get(page, set())


def can_do(action: str) -> bool:
    return current_role() in C.ACTION_ACCESS.get(action, set())


def allowed_pages() -> set[str]:
    role = current_role()
    return {p for p, roles in C.PAGE_ACCESS.items() if role in roles}


def logout() -> None:
    st.session_state.pop(_SESSION_KEY, None)
    st.session_state.pop("page", None)


def require_login() -> str:
    """Tampilkan layar login sampai password benar. Mengembalikan peran aktif.

    Dipanggil paling awal di app.py. Selama belum login, tidak ada satu pun
    pemanggilan data yang terjadi — jadi spreadsheet tidak pernah tersentuh
    oleh pengunjung yang tidak berhak.
    """
    role = current_role()
    if role:
        return role

    st.markdown(
        theme.header_band(
            "HR Recruitment Portal",
            "PT Darma Henwa — Human Capital Management",
        ),
        unsafe_allow_html=True,
    )

    left, mid, right = st.columns([1, 1.15, 1])
    with mid:
        with theme.card("login", "Masuk", "Portal ini berisi data kandidat. Masukkan password tim."):
            entered = st.text_input(
                "Password", type="password", key="auth_input",
                placeholder="Password Recruitment atau User",
                label_visibility="collapsed",
            )
            submit = st.button("Masuk", type="primary", width="stretch", key="auth_submit")

            if submit:
                matched = _match(entered) if entered else None
                if matched:
                    st.session_state[_SESSION_KEY] = matched
                    st.rerun()
                else:
                    # Sengaja tidak memberi tahu password mana yang hampir benar.
                    st.error("Password tidak cocok. Hubungi tim Recruitment kalau lupa.")

            st.markdown(
                theme.inline_note(
                    "<b>Recruitment</b> membuka seluruh fungsi. "
                    "<b>User</b> membuka Overview, Tracking, dan Weekly Report."
                ),
                unsafe_allow_html=True,
            )

    st.stop()


def role_badge() -> str:
    """Chip peran untuk ditaruh di header band."""
    role = current_role()
    return f"Masuk sebagai <b>{C.ROLE_LABEL.get(role, '—')}</b>"
