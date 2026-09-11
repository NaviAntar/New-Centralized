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


def _try_sources(sources: list[tuple[str, str]], require: list[str] | None = None,
                 **kw) -> tuple[pd.DataFrame, str]:
    """Coba tiap sumber berurutan. Mengembalikan (frame, label sumber yang berhasil).

    `require` adalah kolom yang WAJIB ada. Sumber yang terbaca tapi kolomnya tidak
    cocok dianggap gagal dan sumber berikutnya dicoba. Ini penting karena Google
    tidak selalu menolak permintaan tab yang salah — ia mengembalikan tab lain
    dengan tenang, dan tanpa pemeriksaan ini yang terbaca dipakai apa adanya lalu
    meledak jauh di dalam perhitungan sebagai KeyError yang membingungkan.
    """
    errors = []
    for label, src in sources:
        if not src:
            continue
        try:
            df = _read_csv(src, **kw)
            if require:
                ada = {str(c).strip() for c in df.columns}
                kurang = [c for c in require if c not in ada]
                if kurang:
                    raise SheetError(
                        f"tab yang terambil bukan yang diminta — kolom {kurang} "
                        f"tidak ada (yang ada: {sorted(ada)[:6]})"
                    )
            return df, label
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
        ("export by gid", C.gsheet_gid_url(C.DB_GID_FIX, C.DB_SPREADSHEET_ID)),
        ("gviz by nama tab", C.gsheet_csv_url(C.DB_SHEET_FIX, C.DB_SPREADSHEET_ID)),
    ], require=["candidate_id"])

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
                ("export by gid", C.gsheet_gid_url(
                    C.MONITORING_GID_BACKEND, C.MONITORING_SPREADSHEET_ID)),
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
    gid = C.REPORT_GIDS.get(sheet_name, C.REPORT_GID_DEFAULT)
    df, _ = _try_sources([
        ("export by gid", C.gsheet_gid_url(gid, C.REPORT_SPREADSHEET_ID)),
        ("gviz by nama tab", C.gsheet_csv_url(sheet_name, C.REPORT_SPREADSHEET_ID)),
    ], header=None)
    return df


def load_mpp(source: str | pd.DataFrame | None = None) -> pd.DataFrame:
    """Sheet 'Update MPP' dari spreadsheet Report — daftar karyawan aktif & resign.

    Dipakai panel "Karyawan resign" di Weekly Report, mengikuti rumus yang sudah
    dipakai tim di sheet "Karyawan Resign".
    """
    if isinstance(source, pd.DataFrame):
        return source.copy()
    # gid lebih dulu: endpoint gviz untuk "Update MPP" diam-diam mengembalikan
    # tab Summary (69 baris, header nama site) — bukan error, jadi dulu terpakai
    # begitu saja lalu meledak sebagai KeyError di metrics.resign().
    df, _ = _try_sources([
        ("argumen langsung", source or ""),
        ("env MPP_CSV", os.environ.get("MPP_CSV", "")),
        ("export by gid", C.gsheet_gid_url(C.REPORT_GID_MPP, C.REPORT_SPREADSHEET_ID)),
        ("gviz by nama tab", C.gsheet_csv_url(C.REPORT_SHEET_MPP, C.REPORT_SPREADSHEET_ID)),
    ], require=["Employee Name", "Position Name", "Location Name",
                "End Date", "Contract End Date", "Level"])
    return df


def load_backend_monitoring(source: str | pd.DataFrame | None = None) -> pd.DataFrame:
    """Sheet 'Backend Monitoring' di spreadsheet Report — identitas kandidat.

    Kenapa perlu, padahal database utamanya fix_centralized: di fix_centralized
    kolom POSITION NAME, LEVEL, DEPARTMENT dan LOC adalah kolom lookup yang
    BELUM ditarik ke bawah untuk baris-baris baru (per 30 Agu 2026: 566 baris,
    hampir semuanya SSCP). Baris yang sama di Backend Monitoring sudah terisi
    lengkap — sheet inilah yang dilihat tim di dashboard monitoring.

    fix_centralized tetap jadi sumber utama karena punya kolom Technical Test
    dan seluruh peta tahap portal; sheet ini hanya menambal identitasnya.

    Kembalikan frame kosong kalau tidak terbaca — penambalan dilewati, bukan
    membuat aplikasi gagal.
    """
    kolom = {
        "CANDIDATE NAME": "candidate_id",
        "No Telpon": "phone",
        "Position ID": "position_id",
        "POSITION NAME": "position_name",
        "DEPARTMENT": "departement",
        "DEPT (for Looker)": "dept_looker",
        "LEVEL": "level",
        "LOC": "loc",
    }
    try:
        if isinstance(source, pd.DataFrame):
            df = source
        else:
            df, _ = _try_sources([
                ("argumen langsung", source or ""),
                ("env BACKEND_MONITORING_CSV",
                 os.environ.get("BACKEND_MONITORING_CSV", "")),
                ("export by gid", C.gsheet_gid_url(
                    C.REPORT_GID_BACKEND, C.REPORT_SPREADSHEET_ID)),
            ])
        df.columns = [str(c).strip() for c in df.columns]
        if "CANDIDATE NAME" not in df.columns:
            return pd.DataFrame(columns=list(kolom.values()))
        ada = {a: b for a, b in kolom.items() if a in df.columns}
        out = df[list(ada)].rename(columns=ada)
        for c in out.columns:
            out[c] = out[c].astype(str).str.strip().replace(
                {"nan": None, "": None, "None": None, "-": None})
        return out[out["candidate_id"].notna()]
    except Exception:
        return pd.DataFrame(columns=list(kolom.values()))


def load_prf(source: str | pd.DataFrame | None = None) -> pd.DataFrame:
    """Tab "PRF Tracking" dari spreadsheet PRF Management.

    Satu baris = satu pengajuan posisi. Sumbernya terpisah dari database
    kandidat: PRF terjadi SEBELUM ada kandidat, jadi tidak bisa diturunkan dari
    fix_centralized.
    """
    if isinstance(source, pd.DataFrame):
        return source.copy()
    df, _ = _try_sources([
        ("argumen langsung", source or ""),
        ("env PRF_CSV", os.environ.get("PRF_CSV", "")),
        ("export by gid", C.gsheet_gid_url(C.PRF_GID_TRACKING, C.PRF_SPREADSHEET_ID)),
        ("gviz by nama tab", C.gsheet_csv_url(
            C.PRF_SHEET_TRACKING, C.PRF_SPREADSHEET_ID)),
    ], require=["request_number", "Site", "position_name", "Tracking PRF", "Status"])
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


def load_mpp_reforecast(source: str | pd.DataFrame | None = None) -> pd.DataFrame:
    """Sheet "MPP Reforecast" — rencana headcount per posisi.

    Satu baris = satu posisi di satu site, dengan Budget dan Reforecast. Kolom
    Actual di sheet ini kosong; angka aktual dihitung sendiri dari daftar
    karyawan (lihat metrics.division_summary).
    """
    if isinstance(source, pd.DataFrame):
        return source.copy()
    df, _ = _try_sources([
        ("argumen langsung", source or ""),
        ("env MPP_REFORECAST_CSV", os.environ.get("MPP_REFORECAST_CSV", "")),
        ("export by gid", C.gsheet_gid_url(C.MPP_GID_REFORECAST, C.MPP_SPREADSHEET_ID)),
        ("gviz by nama tab", C.gsheet_csv_url(
            C.MPP_SHEET_REFORECAST, C.MPP_SPREADSHEET_ID)),
    ], require=["Loc", "Level Code", "Status", "Divisi", "Reforecast"])
    return df


def load_mpp2(source: str | pd.DataFrame | None = None) -> pd.DataFrame:
    """Tab "MPP2" di spreadsheet Report — rencana headcount per posisi.

    Menggantikan tab "MPP Reforecast" di spreadsheet lain: sejak 8 Sep 2026
    inilah yang dipakai sheet "Copy of Summary by Division" milik tim, jadi
    portal memakai sumber yang sama persis supaya angkanya tidak pernah
    berbeda. Bentuk kolomnya sama, sehingga metrics.prepare_reforecast() tidak
    perlu diubah.
    """
    if isinstance(source, pd.DataFrame):
        return source.copy()
    kandidat = [("argumen langsung", source or ""),
                ("env MPP2_CSV", os.environ.get("MPP2_CSV", ""))]
    if C.REPORT_GID_MPP2:
        kandidat.append(("export by gid", C.gsheet_gid_url(
            C.REPORT_GID_MPP2, C.REPORT_SPREADSHEET_ID)))
    kandidat.append(("gviz by nama tab", C.gsheet_csv_url(
        C.REPORT_SHEET_MPP2, C.REPORT_SPREADSHEET_ID)))
    df, _ = _try_sources(
        kandidat, require=["Loc", "Level Code", "Status", "Divisi", "Reforecast"])
    return df


def load_existing_employee(source: str | pd.DataFrame | None = None) -> pd.DataFrame:
    """Tab "Existing Employee" — karyawan aktif, satu baris satu orang.

    Kelebihannya dibanding "Update MPP" yang dipakai sebelumnya: tab ini sudah
    punya kolom **Division**, **Loc**, dan **Level** yang sudah dibereskan, jadi
    divisi tidak perlu ditebak lagi dari huruf pertama Position Code. Isinya juga
    sudah tersaring — tidak ada baris dengan End Date terisi.
    """
    if isinstance(source, pd.DataFrame):
        return source.copy()
    kandidat = [("argumen langsung", source or ""),
                ("env EMPLOYEE_CSV", os.environ.get("EMPLOYEE_CSV", ""))]
    if C.REPORT_GID_EMPLOYEE:
        kandidat.append(("export by gid", C.gsheet_gid_url(
            C.REPORT_GID_EMPLOYEE, C.REPORT_SPREADSHEET_ID)))
    kandidat.append(("gviz by nama tab", C.gsheet_csv_url(
        C.REPORT_SHEET_EMPLOYEE, C.REPORT_SPREADSHEET_ID)))
    df, _ = _try_sources(
        kandidat, require=["Employee ID", "Position Name", "Division", "Loc", "Level"])
    return df


def load_adp(source: str | pd.DataFrame | None = None) -> pd.DataFrame:
    """Tab "ADP" — karyawan yang sedang acting ke posisi di atasnya.

    Dipakai kolom ADP di Summary by Division: orang yang sudah menempati posisi
    itu sebagai acting mengurangi kebutuhan rekrut dari luar. Dua kolom kunci
    (divisi dan Staff/Non Staff) TIDAK punya judul di sheet, jadi di sini diberi
    nama sendiri berdasarkan posisinya: tepat setelah "Progress Status" dan
    tepat setelah "Existing Posid".
    """
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    else:
        kandidat = [("argumen langsung", source or ""),
                    ("env ADP_CSV", os.environ.get("ADP_CSV", ""))]
        if C.REPORT_GID_ADP:
            kandidat.append(("export by gid", C.gsheet_gid_url(
                C.REPORT_GID_ADP, C.REPORT_SPREADSHEET_ID)))
        kandidat.append(("gviz by nama tab", C.gsheet_csv_url(
            C.REPORT_SHEET_ADP, C.REPORT_SPREADSHEET_ID)))
        df, _ = _try_sources(kandidat, require=["Kategori", "Lokasi", "Existing Posid"])

    kol = [str(c).strip() for c in df.columns]
    df.columns = kol

    def setelah(nama):
        """Judul kolom tepat setelah `nama` — kolom tanpa judul di sheet."""
        if nama in kol:
            i = kol.index(nama) + 1
            if i < len(kol):
                return kol[i]
        return None

    d_div = setelah("Progress Status (Updated)") or setelah("Progress Status")
    d_stat = setelah("Existing Posid")
    out = pd.DataFrame({
        "divisi": (df[d_div].astype(str).str.strip() if d_div else ""),
        "site": df["Lokasi"].astype(str).str.strip().str.upper(),
        "status": (df[d_stat].astype(str).str.strip() if d_stat else ""),
        # Level yang sedang dia duduki sebagai acting — itu level posisi yang
        # kebutuhannya berkurang, bukan level asalnya. Dipakai menempatkan angka
        # ADP di baris level yang benar saat divisi dibuka.
        "level": (df["Level Acting"].astype(str).str.strip()
                  if "Level Acting" in kol else ""),
    })
    return out[out["divisi"].notna() & ~out["divisi"].isin(["", "nan", "None"])]


# Tahap proses -> (kolom Result, kolom tanggal mulai) di tab monitoring.
_PROSES_KOLOM = {
    "Interview User": ("RESULT INTERVIEW USER", "START INTERVIEW USER"),
    "Psychotest": ("RESULT PSYCHOTEST", "START PSYCHOTEST"),
    "Offering": ("RESULT OFFERING", "START REQ OFFERING"),
    "MCU": ("RESULT MCU", "MCU DATE"),
}


def load_process_monitoring(source: str | pd.DataFrame | None = None) -> pd.DataFrame:
    """Tab monitoring kandidat — sumber kolom proses di Summary by Division.

    Tab yang SAMA dengan yang dibaca rumus sheet "Copy of Summary by Division"
    (di spreadsheet Report ia muncul sebagai "Backend Monitoring"; isinya cermin
    satu sama lain). Dipakai khusus untuk empat kolom proses supaya sumber dan
    rumusnya sama-sama identik dengan sheet — kalau sumbernya sama dan rumusnya
    sama, hasilnya tidak mungkin berbeda.

    Kembalikan frame rapi: candidate, site, divisi, level, status, lalu untuk
    tiap tahap `res_<tahap>` dan `start_<tahap>`. Baris tanpa STATUS dibuang —
    itu baris kosong sisa template, bukan kandidat.
    """
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    else:
        kandidat = [("argumen langsung", source or ""),
                    ("env PROCESS_MONITORING_CSV",
                     os.environ.get("PROCESS_MONITORING_CSV", "")),
                    ("export by gid", C.gsheet_gid_url(
                        C.MONITORING_GID_PROCESS, C.MONITORING_SPREADSHEET_ID)),
                    ("gviz by nama tab", C.gsheet_csv_url(
                        C.MONITORING_SHEET_PROCESS, C.MONITORING_SPREADSHEET_ID))]
        df, _ = _try_sources(
            kandidat,
            require=["STATUS", "LOC", "DEPARTMENT", "LEVEL",
                     "RESULT INTERVIEW USER", "RESULT PSYCHOTEST",
                     "RESULT OFFERING", "RESULT MCU"])

    df.columns = [str(c).strip() for c in df.columns]
    # fillna("") WAJIB: kolomnya bertipe string nullable, jadi sel kosong tetap
    # NA setelah astype(str) — dan NA di dalam masker boolean lolos sebagai True.
    # Tanpa ini, 1.935 baris kosong sisa template ikut terbaca sebagai kandidat.
    status = (df["STATUS"].astype("string").str.strip().str.upper()
              .fillna("").replace("NAN", ""))
    df = df[status.ne("")]
    if df.empty:
        return pd.DataFrame(columns=["candidate", "site", "divisi", "level", "status"])

    nama = df.get("Nama", df.get("CANDIDATE NAME"))
    posisi = df.get("POSITION NAME")
    progres = df.get("LAST PROGRESS", df.get("LAST PROGRESS 1"))
    onboard = df.get("DATE OF ONBOARDING")
    out = pd.DataFrame({
        "candidate": (nama.astype("string").str.strip().fillna("")
                      if nama is not None else ""),
        "site": df["LOC"].astype("string").str.strip().str.upper().fillna(""),
        "divisi": (df["DEPARTMENT"].astype("string").str.strip().fillna("")
                   .replace({"": C.DEPT_UNMAPPED_LABEL,
                             "nan": C.DEPT_UNMAPPED_LABEL})
                   .map(C.merge_division)),
        "level": df["LEVEL"].map(C.monitoring_level),
        "status": df["STATUS"].astype(str).str.strip().str.upper(),
        # Staff / Non Staff diturunkan dari sebutan level, bukan kolom sendiri —
        # tab ini tidak punya kolom Status level seperti MPP2.
        "jenis": df["LEVEL"].map(C.monitoring_level_type),
        "position": (posisi.astype("string").str.strip().fillna("")
                     if posisi is not None else ""),
        "last_progress": (progres.astype("string").str.strip().fillna("")
                          if progres is not None else ""),
        "onboard_date": (pd.to_datetime(onboard, errors="coerce", dayfirst=True)
                         if onboard is not None else pd.NaT),
    }, index=df.index)

    for tahap, (kol_res, kol_tgl) in _PROSES_KOLOM.items():
        out[f"res_{tahap}"] = (
            df[kol_res].astype("string").str.strip().str.upper()
            .fillna("").replace("NAN", "")
            if kol_res in df.columns else "")
        out[f"start_{tahap}"] = (pd.to_datetime(df[kol_tgl], errors="coerce",
                                                dayfirst=True)
                                 if kol_tgl in df.columns else pd.NaT)
    return out.reset_index(drop=True)


def load_division_code(source: str | pd.DataFrame | None = None) -> dict[str, str]:
    """Huruf kode divisi -> nama divisi, dari sheet "Code Divisi".

    Dipakai menentukan divisi seorang karyawan: huruf PERTAMA Position Code
    adalah kode divisinya. Itu aturan yang sama dengan yang dipakai sheet
    Summary by Division, dan sudah dicocokkan — hasilnya sama persis untuk
    seluruh divisi BCP kecuali dua yang selisih satu orang karena snapshot-nya
    beda hari.
    """
    try:
        if isinstance(source, pd.DataFrame):
            df = source
        else:
            df, _ = _try_sources([
                ("argumen langsung", source or ""),
                ("export by gid", C.gsheet_gid_url(
                    C.REPORT_GIDS["Code Divisi"], C.REPORT_SPREADSHEET_ID)),
            ], require=["Division", "Code"])
        return dict(zip(df["Code"].astype(str).str.strip(),
                        df["Division"].astype(str).str.strip()))
    except Exception:
        return {}
