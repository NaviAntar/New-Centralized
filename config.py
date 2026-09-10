"""
Konfigurasi global HR Recruitment Portal — PT Darma Henwa.

Semua angka SLA, sumber data, dan pemetaan nama recruiter hidup di sini.
Tidak ada satu pun konstanta di bawah yang boleh diduplikasi di modul lain:
kalau ada dua tempat menyimpan angka yang sama, cepat atau lambat keduanya
tidak sinkron — itu persis penyebab temuan T-01b (dua standar SLA berbeda).
"""
from __future__ import annotations

# ===========================================================================
# 1. SUMBER DATA
# ===========================================================================
# All Database Centralize — sumber utama kandidat.
DB_SPREADSHEET_ID = "1eysrca2wIWsx2LZeP3z2qlRawLzdRBYxsDf6JizcaZc"
DB_SHEET_FIX = "fix_centralized"     # tabel wide, 1 baris per kandidat
DB_SHEET_STAGING = "staging"         # tabel long, 1 baris per kandidat per tahap

# gid dipakai sebagai fallback kalau pengambilan berbasis nama tab gagal.
#
# Kenapa gid penting: endpoint `export?format=csv&sheet=<nama>` MENGABAIKAN
# parameter `sheet` dan selalu mengembalikan tab pertama (temuan T-07). Versi
# lama dashboard kebetulan benar karena fix_centralized memang tab pertama —
# begitu urutan tab digeser, data yang tampil diam-diam berubah.
DB_GID_FIX = "1210250666"
DB_GID_STAGING = ""                  # TODO: isi dari URL tab staging

# Monitoring 2026 — MPP, PRF, SLA master, kalender libur.
MONITORING_SPREADSHEET_ID = "1WxPctId12ETTmELrkC6NGUJxKMW45R8llENqTtRt1hU"
MONITORING_GID_DEFAULT = "593032148"
MONITORING_SHEET_BACKEND = "Backend"

# PRF Management — pengajuan posisi sebelum masuk proses rekrutmen.
PRF_SPREADSHEET_ID = "14BT6eNFBlaKouhlQWfR1N72v-wr4bD3qntcsZiDv7gk"
PRF_GID_TRACKING = "0"
PRF_SHEET_TRACKING = "PRF Tracking"

# Level yang dihitung Staff. Sisanya — apa pun isinya — masuk Non Staff, jadi
# level baru tidak diam-diam hilang dari filter "Jenis Level".
PRF_STAFF_LEVELS = [
    "Junior Staff", "Supervisor", "Superintendent",
    "Manager", "General Manager", "Boards", "Commisioner",
]

# Nilai yang boleh muncul di filter, ditulis lengkap walau datanya belum punya
# semuanya. CLOSE dan CANCEL belum ada satu baris pun per 1 Sep 2026; kalau
# daftarnya diambil dari data, filternya menyusut sendiri begitu keadaan berubah
# dan orang mengira fiturnya hilang.
PRF_TRACKING_VALUES = ["APPROVED", "ROUTING PRF"]
PRF_STATUS_VALUES = ["CLOSE", "OPEN", "HOLD", "CANCEL"]

# MPP Reforecast — rencana headcount per posisi. Sumber angka MPP di halaman
# Summary by Division.
MPP_SPREADSHEET_ID = "1BdzArgjMunh7IDMnnidNi3-qgKliaSQxMKyW0hc0FGY"
MPP_GID_REFORECAST = "1401190451"
MPP_SHEET_REFORECAST = "MPP Reforecast"

# Level di sheet ditulis sebagai ANGKA. Peta ini menerjemahkannya ke sebutan yang
# dipakai tim (arahan Navi, 7 Sep 2026). Urutannya dari paling bawah ke paling
# atas — itu urutan yang dipakai menampilkan drill-down per level.
LEVEL_CODE_NAMES = {
    11: "Non Staff",
    10: "Jr. Staff / Foreman",
    9: "Supervisor",
    8: "Superintendent",
    7: "Manager",
    6: "Manager",
    5: "General Manager",
    4: "Deputy Director",
    3: "Director",
    2: "President Director",
    1: "Commissioner",
    0: "Commissioner",
}

# Urutan tampil: dari level paling bawah ke paling atas.
LEVEL_ORDER = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0]

# Peserta FTAP diberi sebutan level sendiri supaya tidak tercampur dengan
# karyawan tetap di level yang sama (arahan Navi, 11 Sep 2026). Mereka tetap
# berada di divisi tujuannya, hanya barisnya terpisah saat divisi dibuka.
FTAP_LEVEL_STAFF = "FTAP Staff"
FTAP_LEVEL_NON_STAFF = "FTAP Non Staff"

# Urutan tampil nama level, dari paling bawah ke paling atas. Dua level FTAP
# ditaruh tepat di atas padanan tetapnya: FTAP Non Staff setelah Non Staff,
# FTAP Staff setelah Jr. Staff / Foreman.
LEVEL_NAME_ORDER = [
    "Non Staff", FTAP_LEVEL_NON_STAFF, "Jr. Staff / Foreman", FTAP_LEVEL_STAFF,
    "Supervisor", "Superintendent", "Manager", "General Manager",
    "Deputy Director", "Director", "President Director", "Commissioner",
]


def level_name(code, ftap: bool = False) -> str:
    """Kode level angka -> sebutan tim. 'LS' dan nilai tak dikenal apa adanya.

    `ftap` True mengembalikan sebutan FTAP: peserta program dipisah barisnya
    supaya "Non Staff" di sebuah divisi tidak mencampur operator tetap dengan
    anak FTAP yang masih dalam program.
    """
    try:
        nama = LEVEL_CODE_NAMES[int(float(code))]
    except (TypeError, ValueError, KeyError):
        teks = str(code or "").strip()
        return teks if teks and teks.lower() != "nan" else "No level"
    if ftap:
        return FTAP_LEVEL_NON_STAFF if nama == "Non Staff" else FTAP_LEVEL_STAFF
    return nama


# Nama lokasi panjang -> kode site, dipakai menyamakan sheet MPP/karyawan dengan
# database kandidat yang memakai kode singkat.
LOCATION_TO_SITE = {
    "Bengalon Coal Project": "BCP",
    "Kintap Coal Project": "KCP",
    "Asam-Asam Coal Project": "ACP",
    "Sebuku Sejaka Coal Project": "SSCP",
    "Jakarta": "JKT",
    "Balikpapan": "BPN",
}

# Report Recruitment — Summary, New Hire, ONP.
REPORT_SPREADSHEET_ID = "1_MAK4sNAKQpQA7fV3HPvsRN3BI-EIowyRYEM5D3Av4w"
REPORT_GID_DEFAULT = "1072355758"
REPORT_SHEET_SUMMARY = "Summary"
REPORT_SHEET_NEWHIRE = "New Hire"
REPORT_SHEET_ONP = "ONP"
REPORT_SHEET_MPP = "Update MPP"      # daftar karyawan — sumber panel resign

# Sheet "Backend Monitoring" (gid 0) di spreadsheet Report. Isinya kandidat yang
# sama dengan fix_centralized, tapi kolom POSITION NAME / LEVEL / DEPARTMENT /
# LOC-nya sudah terisi untuk baris baru — di fix_centralized kolom itu lookup
# yang belum ditarik ke bawah. Dipakai menambal identitas kandidat saja.
REPORT_GID_BACKEND = "0"
REPORT_SHEET_BACKEND = "Backend Monitoring"

# gid tiap tab di spreadsheet Report. Dipakai LEBIH DULU, bukan sebagai cadangan:
# endpoint gviz berbasis nama tab kadang diam-diam mengembalikan tab lain (untuk
# "Update MPP" ia mengembalikan tab Summary) atau memotong isinya. Nama tab hanya
# jadi cadangan kalau gid-nya berubah.
REPORT_GIDS = {
    "Summary": "1072355758",
    "New Hire": "976877691",
    "ONP": "190296503",
    "Karyawan Resign": "836878659",
    "Backend Monitoring": "0",
    "Update MPP": "504172347",
    "Summary by Division": "856663966",
    "Code Divisi": "482521119",
    "Copy of Summary by Division": "68955289",
}

# ── Sumber Summary by Division (arahan Navi, 8 Sep 2026) ───────────────────
# Rumus di tab "Copy of Summary by Division" adalah acuan resminya:
#
#   MPP    = SUMIFS(MPP2!Reforecast; MPP2!Divisi; MPP2!Loc; MPP2!Status)
#   Actual = COUNTIFS('Existing Employee'!Division; Level "<11" (Staff) atau
#            "=11" (Non Staff); Loc)
#   ADP    = COUNTIFS(ADP!Division; ADP!Lokasi; ADP!Status)
#   Need to Hire = ADP + Gap − FTAP
#
# Tiga tab ini ada di spreadsheet Report yang sama. gid-nya belum diketahui,
# jadi diambil lewat nama tab — aman karena _try_sources() menolak tab yang
# kolom wajibnya tidak cocok. Kalau nanti gid-nya diisi, ia dipakai lebih dulu.
REPORT_SHEET_MPP2 = "MPP2"                     # rencana headcount per posisi
REPORT_SHEET_EMPLOYEE = "Existing Employee"    # karyawan aktif, sudah tersaring
REPORT_SHEET_ADP = "ADP"                       # karyawan yang sedang acting
REPORT_GID_MPP2 = ""                           # TODO: isi kalau gid diketahui
REPORT_GID_EMPLOYEE = ""
REPORT_GID_ADP = ""

# Karyawan Future Talent Acceleration Program. Di daftar karyawan mereka tercatat
# di divisi Human Capital Management, dan Position Name mereka selalu diawali
# "FTAP".
#
# Mereka TETAP dihitung di HCM dan tampil sebagai KOLOM tersendiri — sama persis
# dengan sheet "Copy of Summary by Division". Sempat (8 Sep 2026) dipisah jadi
# divisi sendiri supaya HCM tidak terlihat kelebihan orang, tapi itulah
# satu-satunya penyebab Actual dan MPP portal meleset dari rumus Excel milik tim.
# Dikembalikan 10 Sep 2026: satu sumber, satu cara hitung, satu hasil.
#
# Bedanya dengan sheet: di sana angka FTAP diketik manual (BCP 15, KCP 9, ACP 4),
# di sini diturunkan dari Position Name sehingga ikut bertambah sendiri saat
# program menerima orang baru (BCP 41, KCP 33, ACP 15 per 10 Sep 2026).
FTAP_POSITION_PREFIX = "FTAP"

# Pemisah kunci "divisi ▸ level" untuk tabel proses. Dijadikan konstanta supaya
# pembuat kunci dan pembacanya tidak mungkin memakai pemisah yang berbeda.
LEVEL_SEP = " ▸ "

# ── Sumber kolom proses di Summary by Division ─────────────────────────────
# Tab monitoring kandidat di spreadsheet Monitoring 2026 — tab yang SAMA dengan
# yang dibaca rumus "Copy of Summary by Division" lewat Backend Monitoring di
# spreadsheet Report (isinya cermin satu sama lain: 3.951 baris, STATUS-nya
# cocok persis). Dipakai KHUSUS untuk kolom proses di halaman Summary by
# Division; halaman lain tetap membaca fix_centralized (arahan Navi, 11 Sep
# 2026: "kalau sumbernya sudah sama, dengan rumus yang sama hasilnya sama").
MONITORING_GID_PROCESS = "593032148"
MONITORING_SHEET_PROCESS = "DATABASE EXISTING PROJECT 2026"

# Sebutan level di tab monitoring tidak sama persis dengan nama level portal.
MONITORING_LEVEL_ALIAS = {
    "JUNIOR STAFF": "Jr. Staff / Foreman",
    "JR STAFF": "Jr. Staff / Foreman",
    "JR. STAFF": "Jr. Staff / Foreman",
    "FOREMAN": "Jr. Staff / Foreman",
    "SUPERVISOR": "Supervisor",
    "SUPERINTENDENT": "Superintendent",
    "SPERINTENDENT": "Superintendent",     # salah ketik di sumber
    "MANAGER": "Manager",
    "GENERAL MANAGER": "General Manager",
    "NON STAFF": "Non Staff",
    "NON-STAFF": "Non Staff",
    "MEKANIK": "Non Staff",
    "OPERATOR": "Non Staff",
}


def monitoring_level(nilai) -> str:
    """Sebutan level di tab monitoring -> nama level yang dipakai portal."""
    teks = str(nilai or "").strip()
    if not teks or teks.lower() == "nan":
        return "No level"
    return MONITORING_LEVEL_ALIAS.get(teks.upper(), teks)

# Nama posisi FTAP menyebut departemen tujuannya di belakang tanda hubung, dan
# ke situlah budget, reforecast, dan orangnya dihitung (arahan Navi, 11 Sep
# 2026). Sebelumnya semuanya menumpuk di Human Capital Management karena itu
# yang tertulis di kolom Divisi.
FTAP_DIVISION_MAP = {
    "ENGINEERING": "Engineering",
    "OPERATOR": "Operation",
    "OPERATION": "Operation",
    "HEALTH, SAFETY, & ENVIRONMENT": "Health, Safety & Environment",
    "HEALTH, SAFETY & ENVIRONMENT": "Health, Safety & Environment",
    "COST CONTROL": "Project Control",
    "MECHANIC": "Plant & Maintenance",
    "PLANT & MAINTENANCE": "Plant & Maintenance",
    "WAREHOUSE": "Warehouse",
    "HUMAN CAPITAL MANAGEMENT": "Human Capital Management",
}


def ftap_division(position_name, fallback: str | None = None) -> str | None:
    """Divisi tujuan sebuah posisi FTAP, dibaca dari nama posisinya.

    "FTAP - Cost Control" -> "Project Control". Nama yang tidak dikenal tetap
    di `fallback` (biasanya Human Capital Management) daripada hilang.
    """
    teks = str(position_name or "").strip()
    if not teks.upper().startswith(FTAP_POSITION_PREFIX):
        return fallback
    ekor = teks.split("-", 1)[1].strip().upper() if "-" in teks else ""
    return FTAP_DIVISION_MAP.get(ekor, fallback)


# Divisi yang digabung — baik MPP maupun Actual (arahan Navi, 11 Sep 2026).
# Warehouse memang bagian dari rantai pasok, dan Digital Transformation tidak
# pernah cukup besar untuk berdiri sendiri di samping Information Technology.
DIVISION_MERGE = {
    "Warehouse": "Supply Chain Management",
    "Digital Transformation": "Digital Transformation & Information Technology",
    "Information Technology": "Digital Transformation & Information Technology",
}


def merge_division(nama) -> str:
    """Nama divisi setelah penggabungan. Yang tidak digabung kembali apa adanya."""
    teks = str(nama or "").strip()
    return DIVISION_MERGE.get(teks, teks)
REPORT_GID_MPP = REPORT_GIDS["Update MPP"]

# Tab "Backend" di Monitoring 2026 — matriks SLA per level + kalender libur.
MONITORING_GID_BACKEND = "0"

CACHE_TTL_SECONDS = 60


def gsheet_csv_url(sheet_name: str, spreadsheet_id: str) -> str:
    """URL CSV publik lewat endpoint gviz (menghormati parameter `sheet`).

    Parameter `_cb` (cache buster) WAJIB ada. Endpoint gviz dilayani lewat CDN
    dan bisa mengembalikan salinan lama beberapa menit setelah spreadsheet
    diubah, karena URL-nya persis sama. Nilai yang selalu berganti membuat tiap
    pengambilan jadi URL unik sehingga selalu menembus ke sumber.

    Ini tidak membuat aplikasi sering menembak Google: URL hanya dibangun saat
    cache Streamlit meleset (lihat CACHE_TTL_SECONDS), bukan tiap rerun.
    """
    import time
    from urllib.parse import quote
    return (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        f"/gviz/tq?tqx=out:csv&sheet={quote(sheet_name)}"
        f"&_cb={int(time.time())}"
    )


def gsheet_gid_url(gid: str, spreadsheet_id: str) -> str:
    """URL CSV berbasis gid — fallback kalau pengambilan by-name gagal."""
    import time
    return (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        f"/export?format=csv&gid={gid}&_cb={int(time.time())}"
    )


# ===========================================================================
# 2. AKSES
# ===========================================================================
# Password dibaca dari st.secrets kalau ada; nilai di bawah hanya fallback
# supaya aplikasi tetap jalan saat dikembangkan lokal. Untuk produksi, isi
# .streamlit/secrets.toml dan JANGAN commit file itu:
#
#   [auth]
#   recruitment = "..."
#   user = "..."
ROLE_RECRUITMENT = "recruitment"
ROLE_USER = "user"

DEFAULT_PASSWORDS = {
    ROLE_RECRUITMENT: "RecruitmentPTDH",
    ROLE_USER: "UserPTDH",
}

ROLE_LABEL = {
    ROLE_RECRUITMENT: "Recruitment",
    ROLE_USER: "User",
}

# Halaman yang boleh dibuka tiap peran. Router membaca peta ini — halaman yang
# tidak terdaftar tidak akan muncul di nav DAN ditolak kalau diakses langsung.
PAGE_ACCESS = {
    "overview": {ROLE_RECRUITMENT, ROLE_USER},
    "weekly": {ROLE_RECRUITMENT, ROLE_USER},
    "tracking_candidate": {ROLE_RECRUITMENT, ROLE_USER},
    "tracking_position": {ROLE_RECRUITMENT, ROLE_USER},
    "prf": {ROLE_RECRUITMENT, ROLE_USER},
    "division": {ROLE_RECRUITMENT, ROLE_USER},
    "rec_room": {ROLE_RECRUITMENT},
}

# Aksi yang hanya boleh dilakukan peran Recruitment.
ACTION_ACCESS = {
    "export": {ROLE_RECRUITMENT},
    "clear_cache": {ROLE_RECRUITMENT},
    "edit_recruiter": {ROLE_RECRUITMENT},
}

# Nama kandidat ditampilkan penuh di kedua peran (keputusan Navi, 25 Agt 2026).
MASK_CANDIDATE_NAME_FOR_USER = False


# ===========================================================================
# 3. SITE
# ===========================================================================
# `loc_values` = nilai kolom `loc` di database yang termasuk site itu.
SITES = {
    "HO": {
        "label": "HO & BPN",
        "icon": "🏢",
        "loc_values": ["JKT", "BPN", "HO"],
        "active": True,
    },
    "BCP": {"label": "Bengalon (BCP)", "icon": "🔩", "loc_values": ["BCP"], "active": True},
    "KCP": {"label": "Kintap (KCP)", "icon": "⛏️", "loc_values": ["KCP"], "active": True},
    "ACP": {"label": "Asam-Asam (ACP)", "icon": "🏭", "loc_values": ["ACP"], "active": True},
    "SSCP": {"label": "SSCP", "icon": "🔧", "loc_values": ["SSCP"], "active": False},
}

# Nama lokasi di sheet "Update MPP" ditulis panjang, sementara database kandidat
# memakai kode singkat. Peta ini menyatukan keduanya supaya filter site di Weekly
# Report berlaku sama untuk panel kandidat maupun panel karyawan resign.
SITE_LOCATION_NAMES = {
    "HO": ["Jakarta", "Balikpapan"],
    "BCP": ["Bengalon Coal Project"],
    "KCP": ["Kintap Coal Project"],
    "ACP": ["Asam-Asam Coal Project"],
    "SSCP": ["Sebuku Sejaka Coal Project"],
}


def location_names_for(site_keys) -> list[str]:
    """Nama lokasi panjang untuk sekumpulan kode site."""
    out = []
    for k in site_keys or []:
        out.extend(SITE_LOCATION_NAMES.get(k, []))
    return out


def loc_values_for(site_keys) -> list[str]:
    """Nilai kolom `loc` di database kandidat untuk sekumpulan kode site."""
    out = []
    for k in site_keys or []:
        out.extend(v.upper() for v in SITES.get(k, {}).get("loc_values", []))
    return out


# Tiap site punya deployment Apps Script sendiri.
#
# HO memakai form baru (Staff). Empat site lain sementara memakai form Centralized
# yang sudah berjalan selama ini — bukan dikosongkan, supaya tim tetap punya
# tempat input sambil menunggu form Non Staff per site selesai dibuat.
#
# Mengganti form sebuah site: tempel URL deployment barunya di baris yang sesuai.
# Tidak ada tempat lain yang perlu diubah.
FORM_URLS = {
    "HO": ("https://script.google.com/macros/s/"
           "AKfycbyOxlEMzjJQ1cwICJFdCbaTiP-5N_UsQiP4gwqRRPBhiGcZCA3dKJItqh5nW07PwIGU/exec"),
    "BCP": ("https://script.google.com/macros/s/"
            "AKfycbwYNMV7x1qjFr6CcVE2QF30iqeg-RjJb2uUIkD8oh69fmN5ZEvkyrnU41Td-sMp4ZqTyQ/exec"),
    "KCP": ("https://script.google.com/macros/s/"
            "AKfycbx2-5kNGHHj-qqAKmV0kHbXiN1VQ0KUu9Gw5nqXnYTXuRho3BSeWrgWodNWzVne4mC7MA/exec"),
    "ACP": ("https://script.google.com/macros/s/"
            "AKfycbwyF4rVWA016TGZgKm2GE3NLjLqPFsdpm8tVISeKLbjrL0qZdFXXRiowwpjfeeW6sC6UA/exec"),
    "SSCP": "",
}

# Spreadsheet tempat tiap form menulis. Dipakai Recruitment Room supaya orang
# bisa langsung membuka sheet-nya tanpa mencari-cari link.
SHEET_URLS = {
    "HO": ("https://docs.google.com/spreadsheets/d/"
           "1WxPctId12ETTmELrkC6NGUJxKMW45R8llENqTtRt1hU/edit?gid=593032148"),
    "BCP": ("https://docs.google.com/spreadsheets/d/"
            "1Zqcs7d497_8kvoCDcFMSSRrfdxw5XBgD3pshIQhZWhg/edit?gid=29237685"),
    "KCP": ("https://docs.google.com/spreadsheets/d/"
            "1TZ91xddvt5718knaxDqAIlFadGSUvFjd67KDAx33VKA/edit?gid=0"),
    "ACP": ("https://docs.google.com/spreadsheets/d/"
            "1ijLgBLvNJVG4VrSBwEaWLw7GfyYb7ck3tmuctE3I8Oo/edit?gid=0"),
    "SSCP": "",
}

# Keterangan singkat tiap site, tampil di bawah judul kartu.
FORM_NOTES = {
    "HO": "Form baru · Staff",
    "BCP": "Centralized form · Non Staff to follow",
    "KCP": "Centralized form · Non Staff to follow",
    "ACP": "Centralized form · Non Staff to follow",
    "SSCP": "Not active yet",
}

# CATATAN — form Apps Script tidak akan tampil di dalam iframe sampai doGet()
# di Code.gs memanggil .setXFrameOptionsMode(ALLOWALL). Contoh kodenya ada di
# README.md bagian "Form Apps Script belum mau di-embed".
FORM_EMBED_HEIGHT = 900

# Dashboard Looker tetap disematkan di Overview atas keputusan Navi, berdampingan
# dengan KPI yang dihitung portal sendiri.
LOOKER_EMBED_URL = ("https://lookerstudio.google.com/embed/reporting/"
                    "a425625f-0af4-4b5c-8826-218a929b1333/page/YwLxF")
LOOKER_EMBED_HEIGHT = 700


def form_url_for(site_key: str) -> str:
    """URL form site tersebut. String kosong berarti formnya belum ada."""
    return FORM_URLS.get(site_key, "")


def sheet_url_for(site_key: str) -> str:
    """URL spreadsheet tujuan form site tersebut."""
    return SHEET_URLS.get(site_key, "")


# ===========================================================================
# 4. SLA — MATRIKS RESMI PER LEVEL
# ===========================================================================
# Sumber: Monitoring 2026 > sheet "Backend", kolom C..N.
#
# Ini menggantikan kolom `budget_lt1` di database, yang berisi 76/77/79/86 —
# selalu 16 hari lebih longgar dari standar resmi dan membuat 99,4% kandidat
# tampil "Onbudget" padahal 45,7% hire sebenarnya lewat target (temuan T-01b).
#
# Angka = jumlah hari yang dialokasikan untuk tahap itu.
SLA_BUDGET = {
    "General Manager": {
        "PRF Approval": 1, "Screening CV": 7, "Interview HR": 2, "Interview User": 5,
        "Psychotest": 5, "Offering": 5, "MCU": 5, "Review MCU": 2, "FU MCU": 7,
        "One Month Notice": 30, "Onboarding": 1,
    },
    "Manager": {
        "PRF Approval": 1, "Screening CV": 7, "Interview HR": 2, "Interview User": 5,
        "Psychotest": 5, "Offering": 5, "MCU": 5, "Review MCU": 2, "FU MCU": 7,
        "One Month Notice": 30, "Onboarding": 1,
    },
    "Superintendent": {
        "PRF Approval": 1, "Screening CV": 6, "Interview HR": 2, "Interview User": 3,
        "Psychotest": 1, "Offering": 5, "MCU": 5, "Review MCU": 2, "FU MCU": 7,
        "One Month Notice": 30, "Onboarding": 1,
    },
    "Supervisor": {
        "PRF Approval": 1, "Screening CV": 5, "Interview HR": 2, "Interview User": 2,
        "Psychotest": 1, "Offering": 5, "MCU": 5, "Review MCU": 2, "FU MCU": 7,
        "One Month Notice": 30, "Onboarding": 1,
    },
    "Junior Staff": {
        "PRF Approval": 1, "Screening CV": 4, "Interview HR": 2, "Interview User": 2,
        "Psychotest": 1, "Offering": 5, "MCU": 5, "Review MCU": 2, "FU MCU": 7,
        "One Month Notice": 30, "Onboarding": 1,
    },
}

# Non Staff tidak punya baris di sheet Backend padahal jumlahnya 239 kandidat
# (17% dari total). Keputusan Navi: samakan dengan Junior Staff, ditambah
# Technical Test.
#
# Technical Test hanya berlaku di level Non Staff — dikonfirmasi data: 235 dari
# 239 kandidat Non Staff punya tanggal Technical Test, dan NOL di level lain.
# Alokasi 1 hari diambil dari kolom b_lt_tech yang sudah terisi di database.
TECHNICAL_TEST_BUDGET = 1

SLA_BUDGET["Non Staff"] = dict(
    SLA_BUDGET["Junior Staff"], **{"Technical Test": TECHNICAL_TEST_BUDGET}
)

# Level yang memakai Technical Test. Tahap ini dilewati (status "tidak berlaku",
# bukan "pending") untuk level lain — inilah yang memperbaiki progress bar yang
# tidak pernah mencapai 100% (temuan T-04).
TECHNICAL_TEST_LEVELS = {"Non Staff"}

LEVEL_FALLBACK = "Junior Staff"


# ===========================================================================
# 4b. HARI KERJA & KALENDER LIBUR
# ===========================================================================
# Lead time dihitung dalam HARI KERJA, bukan hari kalender — Sabtu, Minggu,
# dan libur nasional tidak dihitung. Ini bukan asumsi: rumus dicocokkan ulang
# terhadap kolom LT yang sudah ada di spreadsheet dan cocok 100% di seluruh
# tahap (PRF, Screening, Interview HR, Interview User, Psikotes, Technical
# Test, Offering, MCU, Review MCU, FU MCU, One Month Notice).
#
# Konvensinya inklusif: mulai dan selesai di hari kerja yang sama = 1 hari.
#
# Sumber daftar: Monitoring 2026 > sheet "Backend", kolom A. Daftar di bawah
# adalah salinan cadangan yang dipakai kalau sheet tidak bisa diambil —
# data_loader menimpanya dengan isi sheet saat aplikasi berjalan.
HOLIDAYS_FALLBACK = [
    "2025-12-25", "2025-12-26",
    "2026-01-01", "2026-01-16",
    "2026-02-16", "2026-02-17",
    "2026-03-18", "2026-03-19", "2026-03-20", "2026-03-21",
    "2026-03-22", "2026-03-23", "2026-03-24",
    "2026-04-03", "2026-04-05",
    "2026-05-01", "2026-05-14", "2026-05-15",
    "2026-05-27", "2026-05-28", "2026-05-31",
    "2026-06-01", "2026-06-16",
    "2026-08-17",
    "2026-12-25",
]


def stage_budget(level: str, stage: str) -> int | None:
    """Budget hari satu tahap untuk satu level. None = tahap tidak berlaku."""
    table = SLA_BUDGET.get(str(level).strip(), SLA_BUDGET[LEVEL_FALLBACK])
    return table.get(stage)


def total_budget(level: str) -> int:
    """Total budget end-to-end untuk satu level, termasuk One Month Notice."""
    table = SLA_BUDGET.get(str(level).strip(), SLA_BUDGET[LEVEL_FALLBACK])
    return sum(table.values())


def applicable_stages(level: str) -> list[str]:
    """Tahap yang benar-benar berlaku untuk satu level, sesuai urutan proses."""
    from theme import STAGE_ORDER
    table = SLA_BUDGET.get(str(level).strip(), SLA_BUDGET[LEVEL_FALLBACK])
    return [s for s in STAGE_ORDER if s in table]


# ===========================================================================
# 5. RECRUITER — PEMETAAN INISIAL KE NAMA LENGKAP
# ===========================================================================
# Database lama memakai inisial di kolom *_by; tim sekarang memakai nama
# lengkap. Peta ini menyatukan keduanya supaya satu orang tidak terhitung dua
# kali. Kunci = inisial di database (huruf besar), nilai = nama lengkap.
#
# Menambah orang baru: cukup tambahkan satu baris di sini, atau lewat panel
# "Kelola recruiter" di halaman Weekly Report — panel itu menulis ke
# st.session_state dan langsung terpakai tanpa restart.
RECRUITER_NAMES = {
    "PURI": "Puranti Nurparida",
    "PUR": "Puranti Nurparida",                   # varian lama di sebagian baris
    "AWL": "Awaluddin",
    "DIV": "Alfina Diva Ramadhanty",
    "FLI": "Muhammad Rafli",
    "UMY": "Shaumy Fadhila",
    "SHA": "Shaumy Fadhila",                      # varian lama
    # Di database tertulis FAQ, bukan FAW — itu sebabnya barisnya kosong.
    "FAQ": "Muhammad Faiq Kenzie Widodo",
}


def _kunci_nama(value) -> str:
    """Nama jadi bentuk banding: huruf kecil, tanpa tanda baca, satu spasi."""
    import re as _re
    return _re.sub(r"[^a-z ]+", "", str(value or "").lower()).strip()


def resolve_recruiter(value, extra: dict | None = None) -> str | None:
    """Isi kolom PIC -> nama di roster. None kalau bukan orang roster.

    Kolom PIC pernah berisi inisial dan sekarang berisi nama lengkap, karena form
    Apps Script menulis nama. Ejaannya pun tidak selalu sama — di database ada
    "SHAUMY FADHILA" dan "SHAUMY FADILAH", "ALFINA DIVA RAMADHANTY" dan
    "ALFINA DIVA". Mendaftar tiap ejaan satu per satu tidak akan pernah selesai,
    jadi urutannya:

      1. Cocokkan ke nama roster apa adanya (abaikan besar-kecil & tanda baca).
      2. Cocokkan ke peta inisial di atas.
      3. Cocokkan lewat NAMA DEPAN, tapi hanya kalau nama depan itu cuma dimiliki
         satu orang di roster. "Shaumy" hanya satu orang, jadi "SHAUMY FADILAH"
         aman dipulangkan ke Shaumy Fadhila. "Muhammad" dimiliki dua orang, jadi
         nama depan saja sengaja TIDAK cukup — lebih baik masuk "Recruiter lain"
         daripada dikreditkan ke orang yang salah.
    """
    if not is_valid_initial(value):
        return None

    peta_nama = {_kunci_nama(n): n for n in RECRUITER_ROSTER}
    peta_inisial = {k.strip().upper(): v for k, v in RECRUITER_NAMES.items()}
    if extra:
        for k, v in extra.items():
            if not k or not v:
                continue
            peta_inisial[str(k).strip().upper()] = v
            peta_nama[_kunci_nama(v)] = v

    kunci = _kunci_nama(value)
    if kunci in peta_nama:
        return peta_nama[kunci]

    tepat = peta_inisial.get(str(value).strip().upper())
    if tepat:
        return tepat

    depan = kunci.split(" ")[0] if kunci else ""
    if len(depan) >= 4:
        cocok = {n for k, n in peta_nama.items() if k.split(" ")[0] == depan}
        if len(cocok) == 1:
            return cocok.pop()
    return None


def is_valid_initial(value) -> bool:
    """False untuk nilai yang jelas bukan inisial recruiter.

    Kolom PIC di database sempat kemasukan angka serial tanggal Excel
    (46205, 46216, …) dari salah tempel. Tanpa saringan ini, angka-angka itu
    muncul sebagai "recruiter" baru di tabel Performance.
    """
    s = str(value or "").strip()
    if not s or s.lower() in ("nan", "none", "-"):
        return False
    return not s.replace(".", "").replace(",", "").isdigit()

# Tallita Ayu Salsabila belum punya inisial apa pun di database — barisnya nol
# karena datanya memang belum ada, bukan karena salah pemetaan.
#
# Inisial yang masih menganggur (hitungan data live 27 Agt):
#   AIC (548 aktivitas) · BEL (109) · JAZ (42) · ALD (19) · MEI (5) · SOM (1)
# Inisial besar yang sudah diketahui BUKAN milik roster:
#   RAF = Rafi'ud A · MRB = M. Ribi H · NAV / NAVI ANTAR = Navi A · IRV = Irviyani
UNMAPPED_INITIALS_HINT = ["AIC", "BEL", "JAZ", "ALD", "MEI", "SOM"]

# Master posisi -> departemen, dipakai memperbaiki kolom `departement` di
# database kandidat yang sebagian terisi NAMA POSISI, bukan departemen.
MONITORING_SHEET_MPP = "MPP 2026"

# Endpoint gviz (by nama tab) memotong sheet ini di baris ke-4 — kemungkinan
# karena filter view / baris beku. Endpoint export by gid mengembalikan 771
# baris utuh, jadi gid dipakai lebih dulu dan gviz hanya cadangan.
MONITORING_GID_MPP = "354501614"

# Di sheet MPP 2026 judul kolom "Position" dan "PositionID" tertukar dengan
# isinya: kolom berjudul "Position" berisi KODE posisi, yang berjudul
# "PositionID" berisi NAMA posisi. Ditukar balik saat dibaca.
MPP_HEADER_SWAPPED = True

# Label untuk baris yang departemennya tidak bisa dipastikan dari master mana
# pun. Sengaja satu baris gabungan — lebih jujur daripada membiarkan nama posisi
# menyamar jadi departemen.
DEPT_UNMAPPED_LABEL = "Not filled in at source"

# Satu departemen, beberapa ejaan. Tanpa ini New Hire menampilkan dua baris HSE
# yang sebenarnya departemen yang sama — ejaannya beda antar sheet:
# fix_centralized & MPP 2026 menulis "Environent", Backend Monitoring menulis
# "Environment", sheet Report menulis "Environtment". Daftar ini sengaja pendek
# dan eksplisit supaya Navi bisa melihat persis apa yang digabung; tambahkan
# baris baru kalau ketemu ejaan lain.
DEPT_ALIASES = {
    "Health, Safety, & Environent": "Health, Safety & Environment",
    "Health Safety & Environtment": "Health, Safety & Environment",
    "Finance Controller & Treasury": "Financial Controller & Treasury",
    "Bussiness Improvement": "Business Improvement",
    "IT": "Information Technology & Digital Transformation",
    "Information Technology": "Information Technology & Digital Transformation",
    "Digital Transformation & Information Technology":
        "Information Technology & Digital Transformation",
}

# ===========================================================================
# TALENT POOL
# ===========================================================================
# Kandidat yang lolos seleksi tapi belum ditempatkan: bagus, hanya saja
# posisinya sudah terisi orang lain atau kebutuhannya belum ada. Ditandai lewat
# kolom Result di tahap mana pun oleh form Apps Script.
#
# Dampaknya ke arti CLOSE: sebuah proses sekarang bisa berakhir dengan DUA cara
# yang sama-sama "selesai" tapi sangat berbeda maknanya —
#   · Close Onboarding  orangnya masuk kerja
#   · Close Talent Pool orangnya disimpan untuk kebutuhan berikutnya
# Menjumlahkan keduanya jadi satu angka "hire" membuat pencapaian rekrutmen
# terlihat lebih besar dari kenyataan, jadi di portal keduanya dipisah.
TALENT_POOL_RESULT = "TALENT POOL"

# Di layar orang-orangnya disebut "backup candidate" (arahan Navi, 7 Sep 2026).
# Nilai yang dicari di kolom Result TETAP "TALENT POOL" karena itu yang ditulis
# form Apps Script — yang berganti hanya sebutannya, bukan datanya.
BACKUP_LABEL = "Backup candidate"

# Pilihan filter status proses. Label yang dilihat pengguna berbahasa Inggris;
# nilai di sheet TETAP apa adanya, jadi peta ini yang menjembatani.
#
# "In process" adalah OPEN — prosesnya masih berjalan. Ditulis begitu, bukan
# "Open", karena di halaman ini "open" mudah terbaca sebagai "posisi yang
# dibuka" padahal yang dimaksud keadaan prosesnya (arahan Navi, 10 Sep 2026).
# Urutannya sengaja menaruh In process paling depan: itu nilai bawaan filter,
# dan itu pula yang dipatok rumus sheet untuk kolom On progress dan Passed.
#
# "TALENT POOL" tampil sebagai "Backup candidate" — sebutan yang dipakai tim
# sejak 6 Sep 2026, sementara rumus di spreadsheet masih menulis TALENT POOL.
STATUS_OPTIONS = {
    "In process": "OPEN",
    "On hold": "HOLD",
    "Closed": "CLOSE",
    "Failed": "FAILED",
    BACKUP_LABEL: TALENT_POOL_RESULT,
}
STATUS_DEFAULT = ["In process"]

# Achievement recruiter dipotong di sini. Tanpa batas, orang yang kebetulan
# memegang satu kandidat cepat bisa tampil 2.000% dan membuat kolomnya tidak
# bisa dibandingkan antar orang — yang tinggi terbaca sebagai anomali, bukan
# sebagai prestasi (arahan Navi, 7 Sep 2026).
ACHIEVEMENT_MAX = 120.0

# Nama yang tampil sebagai baris tersendiri di tabel Performance, sesuai urutan
# yang Navi berikan. Nama tanpa inisial tetap muncul (nilai nol) supaya terlihat
# bahwa orangnya ada tapi datanya belum masuk.
RECRUITER_ROSTER = [
    "Puranti Nurparida",
    "Awaluddin",
    "Alfina Diva Ramadhanty",
    "Muhammad Rafli",
    "Muhammad Faiq Kenzie Widodo",
    "Shaumy Fadhila",
    "Tallita Ayu Salsabila",
]

# Inisial di luar roster digabung jadi satu baris dengan label ini (keputusan
# Navi). Tanpa ini, 84% aktivitas di database hilang dari report.
OTHER_RECRUITER_LABEL = "Other recruiters"

# Kandidat yang kolom PIC Screening CV-nya KOSONG. Dulu baris seperti ini hilang
# sama sekali dari tabel Performance — bukan masuk "Recruiter lain", tapi
# benar-benar tidak dihitung — sehingga jumlah kolom Onboarding tidak pernah
# cocok dengan Ringkasan per site. Sekarang dikelompokkan per site, karena di
# lapangan memang site yang menanganinya (rekrutan massal Non Staff seperti
# Driver Travel dan Pit Controller).
def site_pic_label(loc) -> str | None:
    """Nama baris pengganti untuk kandidat tanpa PIC. None kalau site-nya juga
    kosong — barisnya tidak punya site untuk dituju, jadi lebih jujur masuk
    "Recruiter lain" daripada jadi baris "PIC Site (tanpa site)" yang tidak
    memberi tahu apa pun (keputusan Navi, 6 Sep 2026).
    """
    loc = str(loc or "").strip().upper()
    if not loc or loc in ("NAN", "NONE", "-"):
        return None
    return f"PIC Site {loc}"

# Kolom PIC per tahap. Tahap yang tidak terdaftar tidak punya PIC di database,
# jadi tidak ikut dihitung ke siapa pun.
STAGE_PIC_COLUMN = {
    "Screening CV": "screening_by",
    "Interview HR": "interview_hr_by",
    "Interview User": "interview_user_by",
    "Psychotest": "psychotest_by",
    "Offering": "offering_by",
    "MCU": "mcu_by",
    "Technical Test": "technical_test_by",
}

# Satu onboarding dihitung ke SEMUA PIC yang menangani kandidat itu (keputusan
# Navi). Konsekuensinya kolom Total Onboarding TIDAK bisa dijumlahkan ke bawah —
# tabel harus mencantumkan catatan itu supaya pembaca tidak salah menyimpulkan.
ONBOARDING_CREDIT = "all_pic"
