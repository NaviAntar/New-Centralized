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

# Report Recruitment — Summary, New Hire, ONP.
REPORT_SPREADSHEET_ID = "1_MAK4sNAKQpQA7fV3HPvsRN3BI-EIowyRYEM5D3Av4w"
REPORT_GID_DEFAULT = "1072355758"
REPORT_SHEET_SUMMARY = "Summary"
REPORT_SHEET_NEWHIRE = "New Hire"
REPORT_SHEET_ONP = "ONP"

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

# Tiap site punya deployment Apps Script sendiri.
#
# Form yang sudah ada melayani rekrutmen di HO, yang levelnya Staff. Site tambang
# memakai form terpisah untuk Non Staff — Navi sedang membuatnya. Selama URL-nya
# masih kosong, Recruitment Room menampilkan keadaan itu apa adanya, bukan
# mengarahkan orang ke form yang salah.
#
# Menambahkan form baru: tempel URL deployment-nya di baris site yang sesuai.
# Tidak ada tempat lain yang perlu diubah.
FORM_URLS = {
    "HO": ("https://script.google.com/macros/s/"
           "AKfycbyOxlEMzjJQ1cwICJFdCbaTiP-5N_UsQiP4gwqRRPBhiGcZCA3dKJItqh5nW07PwIGU/exec"),
    "BCP": "",
    "KCP": "",
    "ACP": "",
    "SSCP": "",
}

# Keterangan singkat tiap form, tampil di bawah judul kartu.
FORM_NOTES = {
    "HO": "Staff · rekrutmen HO",
    "BCP": "Non Staff · menyusul",
    "KCP": "Non Staff · menyusul",
    "ACP": "Non Staff · menyusul",
    "SSCP": "Non Staff · menyusul",
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
    "AWL": "Awaluddin",
    "DIV": "Alfina Diva Ramadhanty",
    "PLI": "Muhammad Rafli",
    "SHA": "Shaumy Fadhila",
}

# Tiga orang di roster belum punya inisial: Muhammad Faiq Kenzie Widodo,
# Tallita Ayu Salsabila, dan Fachry. Selama belum dipetakan, mereka tampil di
# tabel dengan nilai nol — BUKAN mengambil data orang lain.
#
# Inisial yang masih menganggur di database dan menunggu dipetakan:
#   AIC (550 aktivitas) · FLI (175) · BEL (112) · SOM (62) · JAZ (42)
#   MEI (5) · ADR (1)
# Inisial dengan volume besar yang sudah diketahui BUKAN milik roster:
#   RAF = Rafi'ud A · MRB = M. Ribi H · NAV = Navi A · IRV = Irviyani
UNMAPPED_INITIALS_HINT = ["AIC", "FLI", "BEL", "SOM", "JAZ", "MEI", "ADR"]

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
    "Fachry",
]

# Inisial di luar roster digabung jadi satu baris dengan label ini (keputusan
# Navi). Tanpa ini, 84% aktivitas di database hilang dari report.
OTHER_RECRUITER_LABEL = "Recruiter lain"

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
