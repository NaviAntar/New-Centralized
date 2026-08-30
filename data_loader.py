"""
data_loader.py — pengambilan data dari Google Sheets.

Modul ini murni pandas; cache ada di app.py. Dengan begitu loader bisa dipanggil
dari skrip biasa dan dari test tanpa Streamlit.

Rantai sumber untuk tiap tabel:
    1. path/URL yang dioper langsung (dipakai test & mode offline)
    2. environment variable
    3. endpoint gviz berbasis NAMA tab
    4. endpoint export berbasis GID

Langkah 3 dan 4 sengaja dipisah. Endpoint `export?format=csv&sheet=<nama>`
MENGABAIKAN parameter `sheet` dan selalu mengembalikan tab pertama — versi lama
dashboard memakai bentuk itu dan kebetulan benar karena fix_centralized memang
tab pertama (temuan T-07). gviz menghormati nama tab; gid dipakai kalau nama tab
diubah orang.
"""
from __future__ import annotations

import os

import pandas as pd

import config as C


class SheetError(Exception):
    """Kegagalan mengambil sheet, dengan pesan yang bisa langsung ditindaklanjuti."""


def _looks_like_html(raw: str) -> bool:
    head = raw[:400].lstrip().lower()
    return head.startswith("<!doctype html") or head.startswith("<html") or "<title>" in head


def _read_csv(url_or_path: str, **kw) -> pd.DataFrame:
    df = pd.read_csv(url_or_path, **kw)
    if df.empty:
        raise SheetError("Sheet terbaca tapi kosong.")
    return df


def _try_sources(sources: list[tuple[str, str]], **kw) -> tuple[pd.DataFrame, str]:
    """Coba tiap sumber berurutan. Mengembalikan (frame, label sumber yang berhasil)."""
    errors = []
    for label, src in sources:
        if not src:
            continue
        try:
            return _read_csv(src, **kw), label
        except Exception as exc:  # noqa: BLE001 — semua kegagalan dikumpulkan
            msg = str(exc)
            if _looks_like_html(msg) or "html" in msg.lower():
                msg = "Google mengembalikan halaman HTML, bukan CSV."
            errors.append(f"  · {label}: {msg[:160]}")

    raise SheetError(
        "Tidak ada sumber yang bisa dibaca.\n"
        + "\n".join(errors)
        + "\n\nYang biasanya jadi penyebab:\n"
        "  1. Spreadsheet belum di-share 'Anyone with the link — Viewer'.\n"
        "  2. Nama tab berubah. Cocokkan dengan nilai di config.py.\n"
        "  3. gid salah. Buka tab-nya di browser dan salin angka setelah 'gid=' di URL."
    )


# ---------------------------------------------------------------------------
# Tabel kandidat
# ---------------------------------------------------------------------------
def load_candidates(source: str | pd.DataFrame | None = None) -> pd.DataFrame:
    """Ambil tab fix_centralized dari All Database Centralize."""
    if isinstance(source, pd.DataFrame):
        return source.copy()

    df, _ = _try_sources([
        ("argumen langsung", source or ""),
        ("env CENTRALIZED_CSV", os.environ.get("CENTRALIZED_CSV", "")),
        ("gviz by nama tab", C.gsheet_csv_url(C.DB_SHEET_FIX, C.DB_SPREADSHEET_ID)),
        ("export by gid", C.gsheet_gid_url(C.DB_GID_FIX, C.DB_SPREADSHEET_ID)),
    ])

    if "candidate_id" not in [str(c).strip().lower() for c in df.columns]:
        raise SheetError(
            f"Tab yang terambil tidak punya kolom 'candidate_id'. Kolom yang ada: "
            f"{list(df.columns)[:8]}...\n"
            f"Kemungkinan besar yang terbaca bukan '{C.DB_SHEET_FIX}'. "
            f"Periksa DB_GID_FIX di config.py."
        )
    return df


# ---------------------------------------------------------------------------
# Kalender libur
# ---------------------------------------------------------------------------
def load_holidays(source: str | pd.DataFrame | None = None) -> list[pd.Timestamp]:
    """Ambil daftar hari libur dari Monitoring 2026 > Backend, kolom A.

    Kalau gagal, kembalikan daftar cadangan dari config — lebih baik memakai
    kalender yang mungkin agak basi daripada menghitung lead time tanpa libur
    sama sekali, yang membuat setiap tahap terlihat lebih lambat dari kenyataan.
    """
    try:
        if isinstance(source, pd.DataFrame):
            df = source
        else:
            df, _ = _try_sources([
                ("argumen langsung", source or ""),
                ("env MONITORING_BACKEND_CSV", os.environ.get("MONITORING_BACKEND_CSV", "")),
                ("gviz by nama tab", C.gsheet_csv_url(
                    C.MONITORING_SHEET_BACKEND, C.MONITORING_SPREADSHEET_ID)),
            ], header=None)

        col = pd.to_datetime(df.iloc[:, 0], errors="coerce", format="mixed").dropna()
        if len(col) >= 5:
            return sorted(col.dt.normalize().unique().tolist())
    except Exception:
        pass

    return sorted(pd.to_datetime(pd.Series(C.HOLIDAYS_FALLBACK)).tolist())


# ---------------------------------------------------------------------------
# Report mingguan
# ---------------------------------------------------------------------------
def load_report_sheet(sheet_name: str) -> pd.DataFrame:
    """Ambil satu tab dari Report Recruitment sebagai grid mentah.

    Dibaca `header=None` karena tab-tab report punya header bertingkat dan blok
    per-site yang berulang; parsing dilakukan dengan mencari teks judul, bukan
    dengan menebak nomor baris — supaya tidak rusak saat ada baris disisipkan.
    """
    df, _ = _try_sources([
        ("gviz by nama tab", C.gsheet_csv_url(sheet_name, C.REPORT_SPREADSHEET_ID)),
        ("export by gid", C.gsheet_gid_url(C.REPORT_GID_DEFAULT, C.REPORT_SPREADSHEET_ID)),
    ], header=None)
    return df


def load_mpp(source: str | pd.DataFrame | None = None) -> pd.DataFrame:
    """Sheet 'Update MPP' dari spreadsheet Report — daftar karyawan aktif & resign.

    Dipakai panel "Karyawan resign" di Weekly Report, mengikuti rumus yang sudah
    dipakai tim di sheet "Karyawan Resign".
    """
    if isinstance(source, pd.DataFrame):
        return source.copy()
    df, _ = _try_sources([
        ("argumen langsung", source or ""),
        ("env MPP_CSV", os.environ.get("MPP_CSV", "")),
        ("gviz by nama tab", C.gsheet_csv_url(C.REPORT_SHEET_MPP, C.REPORT_SPREADSHEET_ID)),
    ])
    return df


def load_position_master(source: str | pd.DataFrame | None = None) -> dict[str, dict]:
    """Master posisi dari Monitoring 2026 > "MPP 2026".

    Dipakai memperbaiki kolom `departement` di database kandidat: sebagian baris
    terisi NAMA POSISI ("Foreman - DMS Operation") alih-alih departemen.

    Mengembalikan dua peta: berdasarkan Position ID dan berdasarkan nama posisi.
    Kalau sheet tidak terbaca, kembalikan peta kosong — perbaikan dilewati, bukan
    membuat aplikasi gagal.
    """
    kosong = {"by_id": {}, "by_name": {}, "valid": set()}
    try:
        if isinstance(source, pd.DataFrame):
            df = source
        else:
            # gid lebih dulu: endpoint gviz memotong sheet ini di baris ke-4.
            df, _ = _try_sources([
                ("argumen langsung", source or ""),
                ("env MPP2026_CSV", os.environ.get("MPP2026_CSV", "")),
                ("export by gid", C.gsheet_gid_url(
                    C.MONITORING_GID_MPP, C.MONITORING_SPREADSHEET_ID)),
                ("gviz by nama tab", C.gsheet_csv_url(
                    C.MONITORING_SHEET_MPP, C.MONITORING_SPREADSHEET_ID)),
            ])
        df.columns = [str(c).strip() for c in df.columns]
        if not {"Position", "PositionID", "Departement"} <= set(df.columns):
            return kosong

        if getattr(C, "MPP_HEADER_SWAPPED", False):
            # Judul tertukar dengan isinya: kolom "Position" berisi kode,
            # kolom "PositionID" berisi nama posisi.
            kode, nama = df["Position"], df["PositionID"]
        else:
            kode, nama = df["PositionID"], df["Position"]
        kode = kode.astype(str).str.strip()
        nama = nama.astype(str).str.strip()
        dept = df["Departement"].astype(str).str.strip()

        ok = dept.notna() & ~dept.isin(["", "nan", "None", "-"])
        if ok.sum() < 20:
            # Ambilan terpotong / sheet sedang dirapikan — lebih baik tidak
            # dipakai sama sekali daripada dipercaya setengah-setengah.
            return kosong
        return {
            "by_id": dict(zip(kode[ok], dept[ok])),
            "by_name": dict(zip(nama[ok], dept[ok])),
            "valid": set(dept[ok]),
        }
    except Exception:
        return kosong
