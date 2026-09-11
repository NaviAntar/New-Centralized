"""
HR Recruitment Portal — PT Darma Henwa
Entrypoint Streamlit. Jalankan: streamlit run app.py

Struktur mengikuti pola repo FTE Calculator:
  - theme.inject_css() sekali di module level, satu blok CSS besar
  - router manual lewat st.session_state["page"], bukan folder pages/
  - tombol nav di-style lewat prefiks key (st.container(key="nav_..."))
  - cache ada di sini, data_loader & metrics tetap murni pandas

Bedanya dari FTE: halaman ini berisi data orang, jadi ada gerbang login di
paling depan dan seluruh teks dari data di-escape sebelum masuk HTML.
"""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="PTDH HR Recruitment Portal",
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

import auth  # noqa: E402
import charts  # noqa: E402
import config as C  # noqa: E402
import data_loader as DL  # noqa: E402
import exporters as XP  # noqa: E402
import metrics as M  # noqa: E402
import theme  # noqa: E402

theme.inject_css()
theme.inject_portal_css()

NAV = [
    ("overview", "Overview"),
    ("division", "Summary by Division"),
    ("weekly", "Weekly Report"),
    ("tracking_candidate", "Candidate Tracking"),
    ("tracking_position", "Position Tracking"),
    ("prf", "PRF Tracking"),
    ("rec_room", "Recruitment Room"),
]


# ===========================================================================
# Data — cache di lapisan ini, loader tetap bisa dipanggil tanpa Streamlit
# ===========================================================================
@st.cache_data(ttl=C.CACHE_TTL_SECONDS, show_spinner="Loading candidates…")
def get_data():
    """Kembalikan (kandidat, tabel tahap, lead time). Kalender libur dipasang dulu.

    Urutannya penting: set_holidays() harus jalan SEBELUM stage_frame(), karena
    seluruh lead time dihitung dalam hari kerja terhadap kalender itu.
    """
    M.set_holidays(DL.load_holidays())
    # Master posisi dipasang sebelum prepare(): kolom departemen di database
    # sebagian terisi nama posisi dan diperbaiki lewat master ini.
    M.set_position_master(DL.load_position_master())
    # Penambal identitas: kolom lookup di fix_centralized belum ditarik ke bawah
    # untuk baris baru, sheet Backend Monitoring sudah lengkap.
    M.set_row_master(DL.load_backend_monitoring())
    df = M.prepare(DL.load_candidates())
    sf = M.stage_frame(df)
    return df, sf, M.lead_time(df, sf)


@st.cache_data(ttl=C.CACHE_TTL_SECONDS, show_spinner="Loading MPP data…")
def get_mpp():
    """Sheet 'Update MPP' dari spreadsheet Report — sumber daftar karyawan resign.

    Mengembalikan None kalau tidak terbaca, supaya halaman bisa menjelaskan
    keadaannya alih-alih gagal seluruhnya. Bagian lain Weekly Report tidak
    bergantung pada data ini.
    """
    try:
        return DL.load_mpp()
    except Exception:
        return None


def _site_of(loc: str) -> str | None:
    loc = str(loc or "").strip().upper()
    for key, cfg in C.SITES.items():
        if loc in [v.upper() for v in cfg["loc_values"]]:
            return key
    return None


def _site_filter(df: pd.DataFrame, site_key: str | None) -> pd.DataFrame:
    if not site_key or site_key == "All sites":
        return df
    vals = [v.upper() for v in C.SITES[site_key]["loc_values"]]
    return df[df["loc"].isin(vals)]


def n(x, dec: int = 0) -> str:
    return charts.num(x, dec)


# ===========================================================================
# Kerangka halaman
# ===========================================================================
def shell(title: str, subtitle: str, chips: list[str] | None = None):
    base = [auth.role_badge(), pd.Timestamp.today().strftime("%d %b %Y")]
    st.markdown(theme.header_band(title, subtitle, chips=(chips or []) + base),
                unsafe_allow_html=True)


def navbar():
    pages = [(k, label) for k, label in NAV if auth.can_view(k)]
    cols = st.columns(len(pages) + 1, gap="small")
    for col, (key, label) in zip(cols, pages):
        with col, st.container(key=f"nav_{key}"):
            if st.button(label, width="stretch", key=f"btn_{key}",
                         type="primary" if st.session_state.page == key else "secondary"):
                st.session_state.page = key
                st.rerun()
    with cols[-1], st.container(key="nav_logout"):
        if st.button("Sign out", width="stretch", key="btn_logout"):
            auth.logout()
            st.rerun()


def data_or_stop():
    try:
        return get_data()
    except Exception as exc:  # noqa: BLE001
        st.error(f"The data could not be loaded.\n\n{exc}")
        st.stop()


# ===========================================================================
# Pembantu bersama
# ===========================================================================
def _kontrol(s: dict):
    jenis = s.get("kind", "select")
    if jenis == "multi":
        return st.multiselect(s["label"], s["options"], key=s["key"],
                              default=s.get("default", []),
                              help=s.get("help"),
                              placeholder=s.get("placeholder", "All"))
    if jenis == "text":
        return st.text_input(s["label"], key=s["key"], help=s.get("help"),
                             placeholder=s.get("placeholder", ""))
    if jenis == "date":
        return st.date_input(s["label"], key=s["key"], help=s.get("help"),
                             value=s.get("value"), format="DD/MM/YYYY")
    return st.selectbox(s["label"], s["options"], key=s["key"],
                        index=s.get("index", 0), help=s.get("help"),
                        **({"filter_mode": s["filter_mode"]} if s.get("filter_mode") else {}))


def filterbar(key: str, specs: list[dict] | list[list[dict]]):
    """Filter dalam SATU panel putih, boleh beberapa baris.

    `specs` boleh berupa daftar kontrol (satu baris) atau daftar baris. Enam
    filter yang dipecah jadi tiga panel putih terpisah terbaca sebagai tiga
    kelompok yang tidak berhubungan, padahal semuanya menyaring tabel yang sama —
    jadi banyaknya baris tidak boleh menambah banyaknya kotak.

    Dibungkus st.container(key="filterbar_…") supaya CSS bisa menyasarnya. Tanpa
    itu kontrol Streamlit melayang di atas latar abu dan hampir tidak terlihat
    sebagai sesuatu yang bisa diklik.
    """
    baris = specs if specs and isinstance(specs[0], list) else [specs]
    hasil = []
    with st.container(key=f"filterbar_{key}"):
        for row in baris:
            cols = st.columns([s.get("width", 1) for s in row], gap="medium")
            for col, s in zip(cols, row):
                with col:
                    hasil.append(_kontrol(s))
    return hasil


# Di atas jumlah baris ini, gambar tidak dibuat otomatis. Menggambar 257 baris
# perlu ~2 detik dan menghasilkan berkas 3 MB — biaya yang tidak pantas dibayar
# setiap kali filter digeser, apalagi untuk gambar yang jarang dipakai sepanjang
# itu. Tabel sepanjang itu tetap bisa diunduh, tapi disiapkan saat diminta.
PNG_LANGSUNG_MAKS = 60


@st.cache_data(show_spinner=False, max_entries=64)
def _xlsx(judul: str, catatan: str, headers: tuple, rows: tuple,
          total_row: tuple | None) -> bytes:
    df = XP.frame_dari_baris(list(headers), [list(r) for r in rows],
                             list(total_row) if total_row else None)
    return XP.to_excel(df, judul, catatan)


@st.cache_data(show_spinner="Rendering image…", max_entries=32)
def _png(judul: str, sub: str, headers: tuple, rows: tuple,
         total_row: tuple | None, align: str | None) -> bytes:
    df = XP.frame_dari_baris(list(headers), [list(r) for r in rows],
                             list(total_row) if total_row else None)
    return XP.to_png(df, judul, sub, align=align, baris_total=bool(total_row))


def unduh_saja(key: str, judul: str, sub: str, headers: list[str],
               rows: list[list], align: str | None = None,
               total_row: list | None = None):
    """Baris tombol Excel + Gambar, rata kanan di atas tabel.

    Dipisah dari tabel() karena Tahap seleksi memakai penampil sendiri tapi tetap
    perlu bisa diunduh.

    Hanya peran Recruitment yang melihatnya — peran User memang tidak diberi
    export sejak awal. Kalau nanti mau dibuka untuk semua, ubah `export` di
    config.ACTION_ACCESS.
    """
    if not auth.can_do("export") or not rows:
        return
    beku_h = tuple(str(h) for h in headers)
    beku_r = tuple(tuple(str(v) for v in r) for r in rows)
    beku_t = tuple(str(v) for v in total_row) if total_row else None
    catatan = f"{judul} — {sub} · diunduh {pd.Timestamp.today():%d %b %Y}"

    _, k_xls, k_png = st.columns([1, 0.085, 0.085], gap="small")
    with k_xls, st.container(key=f"unduh_{key}_xls"):
        st.download_button(
            "Excel", _xlsx(judul, catatan, beku_h, beku_r, beku_t),
            file_name=XP.nama_berkas(judul, "xlsx"),
            mime=("application/vnd.openxmlformats-officedocument"
                  ".spreadsheetml.sheet"),
            key=f"dl_{key}_xls", width="stretch",
            help="The table exactly as shown, following the active filters")
    with k_png, st.container(key=f"unduh_{key}_png"):
        siap = f"siap_png_{key}"
        if len(rows) <= PNG_LANGSUNG_MAKS or st.session_state.get(siap):
            st.download_button(
                "Image", _png(judul, sub, beku_h, beku_r, beku_t, align),
                file_name=XP.nama_berkas(judul, "png"), mime="image/png",
                key=f"dl_{key}_png", width="stretch",
                help="PNG of this table — every row included, no scrolling needed")
        elif st.button("Image", key=f"prep_{key}_png", width="stretch",
                       help=f"This table has {len(rows)} rows. Click once to "
                            "prepare the image."):
            st.session_state[siap] = True
            st.rerun()


def tabel(key: str, judul: str, sub: str, headers: list[str], rows: list[list],
          align: str | None = None, total_row: list | None = None,
          max_rows: int | None = 10):
    """Tabel portal + tombol unduh di ujung kanan atasnya.

    Semua tabel lewat sini, bukan langsung ke theme.data_table(), supaya berkas
    unduhan dijamin memakai baris yang sama persis dengan yang tampil di layar —
    termasuk filter yang sedang aktif. Kalau tiap halaman menyusun ulang datanya
    sendiri untuk diunduh, cepat atau lambat isi berkas dan isi layar berbeda,
    dan itu baru ketahuan setelah berkasnya beredar.
    """
    unduh_saja(key, judul, sub, headers, rows, align=align, total_row=total_row)
    st.markdown(theme.data_table(headers, rows, align=align,
                                total_row=total_row, max_rows=max_rows),
                unsafe_allow_html=True)


def periode_terpilih(tahun_pilih, bulan_pilih) -> list[tuple[int, int]]:
    """Gabungkan pilihan tahun x bulan jadi daftar (tahun, bulan)."""
    if not tahun_pilih or not bulan_pilih:
        return []
    return [(int(t), M.BULAN_NAMA_BALIK[b]) for t in tahun_pilih for b in bulan_pilih]


# ===========================================================================
# ① OVERVIEW — hanya dua bagian: ringkasan dan Looker
# ===========================================================================
def page_overview():
    df, sf, lt = data_or_stop()

    (site,) = filterbar("ov", [
        {"label": "Site", "key": "ov_site", "options": ["All sites"] + list(C.SITES)},
    ])

    if site != "All sites":
        keys = set(_site_filter(df, site)["cand_key"])
        df, lt = df[df["cand_key"].isin(keys)], lt[lt["cand_key"].isin(keys)]
        sf = sf[sf["cand_key"].isin(keys)]

    if not len(df):
        st.markdown(theme.empty_state("No candidates", "No data for this site yet."),
                    unsafe_allow_html=True)
        return

    h = M.headline(df, lt)

    st.markdown(theme.section_heading(1, "Summary", "pipeline as it stands today"),
                unsafe_allow_html=True)
    def persen(x):
        return f'{x / h["candidates"] * 100:.1f}% of total' if h["candidates"] else "—"

    # Satu baris lima kartu. Daftar backup candidate tidak ikut di sini — daftarnya hidup di
    # Recruitment Room, tempat orang benar-benar menindaklanjutinya, dan kartu
    # keenam di sini hanya membuat barisnya pecah jadi dua tanpa menambah
    # keputusan apa pun.
    k = st.columns(5, gap="small")
    with k[0]:
        st.markdown(theme.kpi_card("Total candidates", n(h["candidates"]),
                                   f'{n(h["open"])} still in process', emoji="👥",
                                   accent=theme.BRAND["navy"], value_size=28),
                    unsafe_allow_html=True)
    with k[1]:
        st.markdown(theme.kpi_card(
            "Close — Onboarding", n(h["hired"]), persen(h["hired"]), emoji="✅",
            accent=theme.STATUS["good"], value_size=28), unsafe_allow_html=True)
    with k[2]:
        st.markdown(theme.kpi_card(
            "Backup candidate", n(h["talent_pool"]), "passed, not yet placed",
            emoji="🗂️", accent=theme.BRAND["orange"], value_size=28),
            unsafe_allow_html=True)
    with k[3]:
        rata = M.average_to_hire(sf)
        nilai = n(rata["total"], 1) if rata["total"] else "—"
        st.markdown(theme.kpi_card(
            "Average to hire", nilai,
            f'working days · {rata["n_stage"]} stages summed',
            emoji="⏱️", value_size=28), unsafe_allow_html=True)
    with k[4]:
        st.markdown(theme.kpi_card("Failed", n(h["failed"]), persen(h["failed"]),
                                   emoji="✕", accent=theme.STATUS["bad"], value_size=28),
                    unsafe_allow_html=True)

    if rata["per_stage"]:
        rinci = " · ".join(f'<b>{theme.esc(s)}</b> {n(v, 1)}'
                           for s, v, _c in rata["per_stage"])
        st.markdown(theme.inline_note(
            f'<b>Average to hire</b> {n(rata["total"], 1)} working days = the sum of '
            "the average of EVERY stage, from PRF Approval to One Month Notice. "
            "Each stage is averaged first and only then added up, so stages with "
            "little data are not drowned out by stages with a lot. Breakdown: "
            f'{rinci}.', block=True), unsafe_allow_html=True)

    st.markdown(theme.inline_note(
        "<b>Close</b> means two different things and is deliberately split: "
        "<b>Close — Onboarding</b> means the person actually started work, "
        "<b>Backup candidate</b> means they passed but are being held for the next "
        "opening. The full list with phone numbers lives in "
        "<b>Recruitment Room</b>.",
        block=True), unsafe_allow_html=True)

    st.markdown(theme.section_heading(2, "Looker dashboard", "Recruitment Dashboard"),
                unsafe_allow_html=True)
    with theme.card("ov_looker", "Looker Studio", "full visualisation"):
        # Filter site di atas TIDAK mengubah isi Looker — Looker punya filternya
        # sendiri di dalam frame.
        if hasattr(st, "iframe"):
            st.iframe(C.LOOKER_EMBED_URL, height=C.LOOKER_EMBED_HEIGHT)
        else:
            st.components.v1.iframe(C.LOOKER_EMBED_URL, height=C.LOOKER_EMBED_HEIGHT,
                                    scrolling=True)


# ===========================================================================
# ② TRACKING KANDIDAT
# ===========================================================================
def page_tracking_candidate():
    df, sf, lt = data_or_stop()

    # Satu kotak saja. st.selectbox punya pencarian bawaan: ketik "tika clara"
    # dan pilihannya langsung menyusut di bawah kotak, lengkap dengan posisi,
    # departemen, dan site. Versi sebelumnya memisah kotak cari dan daftar
    # pilihan, jadi orang harus mengetik lalu membuka dropdown lagi.
    pilihan = M.candidate_options(df)
    if not pilihan:
        st.markdown(theme.empty_state("No candidates yet", "—"), unsafe_allow_html=True)
        return

    with st.container(key="filterbar_tc"):
        label = st.selectbox(
            "Find a candidate — type the name",
            list(pilihan), key="tc_pick", filter_mode="contains",
            help="Type a name; each suggestion names the position and site, "
                 "so two people with similar names are easy to tell apart.")
    pilih = pilihan[label]

    row = df[df["cand_key"] == pilih].iloc[0]
    stages = sf[sf["cand_key"] == pilih].sort_values("stage_no")
    ltrow = lt[lt["cand_key"] == pilih].iloc[0]
    hstat = str(row["status1"] or "").upper()

    st.markdown(theme.section_heading(
        1, theme.esc(row["candidate_id"]), theme.esc(row.get("position_name")),
        tag=theme.RESULT_LABEL.get(hstat, hstat)), unsafe_allow_html=True)

    if row["is_duplicate_name"]:
        st.markdown(theme.inline_note(
            "This name appears more than once — usually because the person applied "
            "for more than one position. Showing: "
            f'<b>{theme.esc(row.get("position_name"))}</b>.',
            warn=True, block=True), unsafe_allow_html=True)

    st.markdown(theme.info_grid([
        ("Position", theme.esc(row.get("position_name")), theme.esc(row.get("position_id"))),
        ("Department", theme.esc(row.get("departement")), theme.esc(row.get("divisi"))),
        ("Level", theme.esc(row["level"]), f'budget {C.total_budget(row["level"])} working days'),
        ("Site", theme.esc(row.get("loc")), ""),
        ("CV source", theme.esc(row.get("source_cv")), ""),
        ("Last stage", theme.esc(row.get("last_progress")), ""),
    ]), unsafe_allow_html=True)

    berlaku = stages[stages["applicable"]]
    selesai = int(berlaku["end"].notna().sum())
    st.markdown(theme.progress_bar(selesai, len(berlaku), failed=(hstat == "FAILED")),
                unsafe_allow_html=True)

    telat = int(ltrow["stages_late"])

    # SLA dijumlahkan dari tiap tahap, bukan dari selisih tanggal ujung ke ujung.
    # Kandidat OPEN dan FAILED belum punya tanggal onboarding, jadi cara lama
    # membuat kolomnya kosong padahal prosesnya jelas sudah memakan waktu.
    sla_kandidat = M.sla_per_candidate(sf).get(pilih)

    kartu = [
        ("SLA", n(sla_kandidat) if pd.notna(sla_kandidat) else "—",
         f"working days, {selesai} stages counted", "⏱️", theme.BRAND["orange"]),
        ("SLA budget", n(ltrow["budget_total"]), f'target for level {theme.esc(row["level"])}',
         "🎯", theme.BRAND["navy"]),
        ("Stages late", n(telat), f'of {selesai} completed stages', "⚠️",
         theme.STATUS["bad"] if telat else theme.STATUS["good"]),
    ]

    # Kartu keempat hanya untuk kandidat yang prosesnya masih berjalan: kalau
    # sudah CLOSE atau FAILED, "estimasi onboarding" tidak menjawab apa pun.
    est = None
    if hstat == "OPEN":
        est = M.estimate_onboarding(sf, pilih, M.stage_averages(sf))
        if est["total"] is not None:
            # Tanggal jadi nilai utama, bukan jumlah harinya: yang ditanya orang
            # adalah "kapan", bukan "berapa". Sisa harinya tetap ditulis di
            # bawahnya untuk yang perlu tahu jaraknya.
            import math
            kartu.append(("Estimate Onboarding", f'{est["tanggal"]:%d %b %Y}',
                          f'{math.ceil(est["total"])} working days to go',
                          "📅", theme.STATUS["warn"]))

    for col, (lab, val, sub, emo, warna) in zip(
            st.columns(len(kartu), gap="small"), kartu):
        with col:
            st.markdown(theme.kpi_card(lab, val, sub, emoji=emo, accent=warna, value_size=24),
                        unsafe_allow_html=True)

    # Jadwalnya ditampilkan utuh, bukan cuma angka akhirnya. Perkiraan tanggal
    # yang tidak bisa ditelusuri selalu berakhir sebagai angka yang tidak
    # dipercaya siapa pun; dengan langkahnya terbaca, orang bisa menunjuk tahap
    # mana yang menurutnya tidak masuk akal.
    if est and est["rincian"]:
        with theme.card("tc_jadwal", "Projected schedule",
                        "each stage takes its overall recruitment average"):
            tabel("tc_jadwal", f'Projected schedule — {row["candidate_id"]}',
                  f'{est["total"]:.1f} working days to {est["tanggal"]:%d %b %Y}',
                  ["Stage", "Average", "Cumulative", "Expected by", "Basis"],
                  [[theme.esc(x["tahap"]), n(x["hari"], 1), n(x["kumulatif"], 1),
                    f'{x["tanggal"]:%d %b %Y}', theme.esc(x["dasar"])]
                   for x in est["rincian"]], align="lrrll", max_rows=None)
            st.markdown(theme.inline_note(
                "Read it forward like a calendar: the stage running now finishes "
                f'after what is left of its average ({n(est["sisa_tahap_ini"], 1)} '
                "days), then every stage still ahead adds its own average "
                f'({n(est["tahap_berikutnya"], 1)} days in total), until '
                "onboarding. The averages are how long each stage <b>actually</b> "
                "takes across all recruitment — not the SLA budget, and not this "
                "recruiter alone, so two candidates at the same stage get the same "
                "date. Weekends and public holidays are excluded and the total is "
                "rounded up.", block=True), unsafe_allow_html=True)

    with theme.card("tc_stages", "Selection stages",
                    "lead time in working days against this level\u2019s budget"):
        rows = []
        for s in stages.itertuples():
            if not s.applicable:
                kode = "na"
            elif pd.notna(s.end):
                kode = "done"
            elif pd.notna(s.start):
                kode = "active"
            else:
                kode = "idle"
            rows.append({
                "name": s.stage, "status": kode,
                "start": s.start.date() if pd.notna(s.start) else None,
                "end": s.end.date() if pd.notna(s.end) else None,
                "lt": int(s.lt) if pd.notna(s.lt) else None,
                "budget": int(s.budget) if pd.notna(s.budget) else None,
                "sla": s.sla,
            })
        if hstat == "FAILED":
            ada = [i for i, r in enumerate(rows) if r["start"] or r["end"]]
            if ada:
                rows[ada[-1]]["status"] = "failed"

        # Tabel tahap punya penampil sendiri (theme.stage_table) karena tiap
        # barisnya berisi lencana status. Untuk diunduh, isinya sama tapi
        # lencananya jadi teks: di Excel dan di gambar, warna saja tidak cukup
        # untuk menyampaikan "Late".
        unduh_saja(
            "tc_stages", f'Selection stages — {row["candidate_id"]}',
            f'{row.get("position_name") or "—"} · {row.get("loc") or "—"}',
            ["Stage", "Status", "Start", "End", "LT", "Budget", "SLA"],
            [[r["name"],
              {"done": "Done", "active": "Running", "idle": "Not started",
               "failed": "Failed", "na": "N/A"}[r["status"]],
              str(r["start"] or "—"), str(r["end"] or "—"),
              "—" if r["lt"] is None else str(r["lt"]),
              "—" if r["budget"] is None else str(r["budget"]),
              r["sla"] or "—"] for r in rows],
            align="lllrrrl")
        st.markdown(theme.stage_table(rows), unsafe_allow_html=True)


# ===========================================================================
# ③ TRACKING POSISI
# ===========================================================================
SEGMEN_WARNA = None  # diisi saat pertama dipakai, lihat _segmen()


def _segmen(r: dict) -> list[tuple[str, int, str]]:
    """Potongan batang bertumpuk dengan warna yang sama di seluruh portal.

    Sisa yang tidak masuk empat kategori — hampir semuanya HOLD — ikut digambar
    sebagai "lainnya". Tanpa itu batangnya menyisakan celah abu yang tidak
    dijelaskan apa pun, dan celah yang tidak dijelaskan selalu dibaca sebagai bug.
    """
    utama = [
        ("in process", r["ongoing"], theme.STATUS["warn"]),
        ("onboarding", r["hired"], theme.STATUS["good"]),
        ("backup candidate", r["pool"], theme.BRAND["orange"]),
        ("failed", r["gagal"], theme.STATUS["bad"]),
    ]
    sisa = r["kandidat"] - sum(v for _l, v, _c in utama)
    if sisa > 0:
        utama.append(("hold / other", sisa, theme.NEUTRAL["text_soft"]))
    return utama


def _kartu_ringkas(r: dict):
    """Lima kartu KPI dengan definisi yang sama di mana pun dipakai."""
    isi = [
        ("Candidates", r["kandidat"], "👥", theme.BRAND["navy"]),
        ("In process", r["ongoing"], "⏳", theme.STATUS["warn"]),
        ("Onboarded", r["hired"], "✅", theme.STATUS["good"]),
        ("Backup", r["pool"], "🗂️", theme.BRAND["orange"]),
        ("Failed", r["gagal"], "✕", theme.STATUS["bad"]),
    ]
    for col, (lab, val, emo, warna) in zip(st.columns(len(isi), gap="small"), isi):
        with col:
            st.markdown(theme.kpi_card(lab, n(val), "", emoji=emo, accent=warna,
                                       value_size=24), unsafe_allow_html=True)


@st.cache_data(show_spinner=False, ttl=C.CACHE_TTL_SECONDS)
def _estimasi_semua(_sf, _df):
    """Perkiraan sisa hari untuk seluruh kandidat OPEN — dihitung sekali.

    Memakai rata-rata seluruh rekrutmen per tahap, bukan rata-rata per PIC:
    satu acuan yang sama untuk semua orang (arahan Navi, 10 Sep 2026).
    """
    return M.estimate_all(_sf, _df)


def _sel_sla(nilai, budget=None):
    """Isi sel "SLA / target": hari terpakai / budget SLA level itu.

    Tidak pernah kosong — kandidat yang masih berjalan atau gagal pun punya
    angka kiri, karena SLA-nya dijumlahkan dari tiap tahap yang sudah punya
    durasi (arahan Navi, 7 Sep 2026).

    Perkiraan onboarding TIDAK lagi ikut di sel ini: sejak 7 Sep 2026 dia punya
    kolom sendiri, "Estimate Onboarding", dan isinya tanggal — lihat _sel_est().
    """
    kiri = n(nilai) if pd.notna(nilai) else "—"
    kanan = (f'<span style="color:{theme.NEUTRAL["text_soft"]}">/ {n(budget)}</span>'
             if pd.notna(budget) else "")
    return f"{kiri} {kanan}".strip()


def _sel_est(estimasi, status=None):
    """Isi kolom "Estimate Onboarding" — TANGGAL, bukan jumlah hari.

    "11 hari lagi" memaksa pembacanya menghitung sendiri, dan hitungannya salah
    kalau ada libur di tengah. Tanggal langsung menjawab "kapan". Pembulatannya
    ke atas dan kalender liburnya sama dengan seluruh lead time portal ini.

    Yang sudah selesai (CLOSE/FAILED) tidak diberi perkiraan: perkiraan untuk
    proses yang sudah berhenti bukan informasi, cuma angka yang menempel.
    """
    if status is not None and status != "OPEN":
        return f'<span style="color:{theme.NEUTRAL["text_soft"]}">closed</span>'
    tanggal = M.estimate_date(estimasi) if pd.notna(estimasi) else None
    if tanggal is None:
        return f'<span style="color:{theme.NEUTRAL["text_soft"]}">—</span>'
    return (f'<span style="color:{theme.STATUS["warn"]};font-weight:600">'
            f"{tanggal:%d %b %Y}</span>")


def _filter_posisi(df, sf):
    """Satu panel filter untuk kedua mode: bulan (screening CV) dan site."""
    bulan_ada = M.month_options(df, sf)
    bulan_p, site_p = filterbar("tp_f", [
        {"label": "Month (CV Screening date)", "key": "tp_bulan", "kind": "multi",
         "options": bulan_ada, "default": [], "width": 2,
         "placeholder": "All months — pick some to narrow it down"},
        {"label": "Site", "key": "tp_site_f", "kind": "multi",
         "options": list(C.SITES), "default": [], "placeholder": "All sites"},
    ])
    d = M.filter_month(df, sf, bulan_p)
    if site_p:
        d = d[d["loc"].isin(C.loc_values_for(site_p))]
    label = " · ".join(x for x in [", ".join(bulan_p), ", ".join(site_p)] if x)
    return d, (label or "all months · all sites")


def _mode_posisi(df, sf, lt):
    """Cari satu posisi, lihat detail prosesnya."""
    d, label = _filter_posisi(df, sf)
    if d.empty:
        st.markdown(theme.empty_state("No candidates", "Loosen the filters."),
                    unsafe_allow_html=True)
        return

    pilihan = M.position_options(d)
    with st.container(key="filterbar_tp_cari"):
        judul = st.selectbox(
            "Find a position — type the position name", list(pilihan), key="tp_pick",
            filter_mode="contains",
            help="Each suggestion names the site and the department.")
    posisi, loc = pilihan[judul]

    est_semua = _estimasi_semua(sf, df)
    kand = M.position_candidates(d, lt, posisi, loc, sf=sf, estimasi=est_semua)
    if kand.empty:
        st.markdown(theme.empty_state("No candidates", "—"), unsafe_allow_html=True)
        return

    sub = d[(d["position_name"] == posisi) & (d["loc"] == loc)]
    ring = M._ringkas(sub)
    baris0 = kand.iloc[0]

    st.markdown(theme.section_heading(
        1, theme.esc(posisi),
        f'{theme.esc(loc)} · {theme.esc(baris0.get("departement"))} · {label}',
        tag=theme.esc(baris0.get("position_id"))), unsafe_allow_html=True)
    _kartu_ringkas(ring)

    with theme.card("tp_kand", "Candidates for this position", f"{len(kand)} people · {label}"):
        st.markdown(theme.split_bar(_segmen(ring), ring["kandidat"]),
                    unsafe_allow_html=True)
        jalan = M.last_progress_breakdown(sub)
        if jalan:
            st.markdown('<div class="dh-secnote">Still in process, stopped at:</div>'
                        + theme.chip_row(jalan), unsafe_allow_html=True)
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        tabel("tp_kand", f"Candidates — {posisi}", f"{loc or '—'} · {label}",
              ["Candidate", "Level", "Site", "Last progress",
               "SLA / target", "Estimate Onboarding", "Status"],
              [[theme.esc(r.candidate_id), theme.esc(r.level), theme.esc(r.loc),
                theme.esc(r.last_progress),
                _sel_sla(r.total_lt, r.budget_total),
                _sel_est(r.estimasi, r.status1),
                theme.result_pill(r.status1)]
               for r in kand.itertuples()], align="llllrrl")
        st.markdown(theme.inline_note(
            "<b>SLA / target</b>: the left number is working days used, summed stage "
            "by stage — so candidates still running or already failed have a "
            "number too; the grey number on the right is the SLA budget for that "
            "level. <b>Estimate Onboarding</b> is the projected "
            f'<span style="color:{theme.STATUS["warn"]}">start date</span> for '
            "anyone still OPEN — working days, public holidays excluded, rounded up.",
            block=True), unsafe_allow_html=True)


# Kolom tabel departemen. Baris posisi dan baris kandidat berbagi kolom yang
# sama — itu yang membuat grouping terbaca: kolom yang tidak berlaku dibiarkan
# kosong, bukan diisi tanda hubung yang menambah kebisingan.
KOLOM_DEP = [
    {"label": "Position / Candidate", "align": "l"},
    {"label": "Level", "align": "l"},
    {"label": "Site", "align": "l"},
    {"label": "Last stage", "align": "l", "sep": True},
    {"label": "Candidates", "align": "r", "sep": True},
    {"label": "In process", "align": "r"},
    {"label": "Onboarded", "align": "r"},
    {"label": "Backup", "align": "r"},
    {"label": "Failed", "align": "r"},
    {"label": "SLA / target", "align": "r", "sep": True},
    {"label": "Estimate Onboarding", "align": "r"},
    {"label": "Status", "align": "l"},
]
HEAD_DEP = [k["label"] for k in KOLOM_DEP]
ALIGN_DEP = "".join(k["align"] for k in KOLOM_DEP)


def _mode_departemen(df, sf, lt):
    """Satu departemen, satu tabel: posisinya di baris utama, kandidatnya di
    dalam.

    Bentuknya sengaja disamakan dengan Summary by Division (arahan Navi, 8 Sep
    2026): klik [+] di depan nama posisi dan kandidatnya muncul tepat di
    bawahnya. Sebelumnya tiap posisi adalah satu expander Streamlit — Plant &
    Maintenance punya 79 posisi, dan 79 kotak yang harus dibuka satu-satu bukan
    tracking, cuma daftar panjang. Dalam satu tabel, posisi bisa dibandingkan
    menurun dan kandidatnya tetap sejangkauan satu klik.
    """
    d, label = _filter_posisi(df, sf)
    if d.empty:
        st.markdown(theme.empty_state("No candidates", "Loosen the filters."),
                    unsafe_allow_html=True)
        return

    est_semua = _estimasi_semua(sf, df)
    dep_ring = M.department_summary(d)
    daftar = dep_ring["departement"].tolist()
    if not daftar:
        st.markdown(theme.empty_state("No departments yet", "—"),
                    unsafe_allow_html=True)
        return

    with st.container(key="filterbar_tp_dep"):
        dep = st.selectbox(
            "Department", daftar, key="tp_dep_pick", filter_mode="contains",
            help="Sorted by how many candidates are still in process.")

    sub = d[d["departement"] == dep]
    ring = M._ringkas(sub)
    pos = M.position_summary(d, dep)

    st.markdown(theme.section_heading(
        1, theme.esc(dep), f'{len(pos)} positions · {label}'), unsafe_allow_html=True)
    _kartu_ringkas(ring)

    with theme.card("tp_depbar", "Department breakdown", label):
        st.markdown(theme.split_bar(_segmen(ring), ring["kandidat"]),
                    unsafe_allow_html=True)
        jalan = M.last_progress_breakdown(sub)
        if jalan:
            st.markdown('<div class="dh-secnote">Still in process, stopped at:</div>'
                        + theme.chip_row(jalan), unsafe_allow_html=True)

    # Yang ditampilkan lebih dulu hanya posisi yang MASIH ADA ORANGNYA jalan —
    # itu arti "posisi yang dibuka". Posisi yang sudah selesai tetap bisa
    # dimunculkan lewat tombol, tapi tidak menenggelamkan yang sedang berjalan.
    jalan_saja = pos[pos["ongoing"] > 0]
    semua = st.toggle(
        f"Also show closed positions ({len(pos) - len(jalan_saja)})",
        key="tp_dep_semua", value=False,
        help="Positions with no candidate still in process — filled, all failed, "
             "or on hold.")
    tampil = pos if semua else jalan_saja

    st.markdown(theme.section_heading(
        2, "Open positions",
        f"{len(tampil)} positions · click [+] to see the candidates"),
        unsafe_allow_html=True)

    if tampil.empty:
        st.markdown(theme.empty_state(
            "No position still in process",
            "Turn on the switch above to see the closed ones."),
            unsafe_allow_html=True)
        return

    kosong = ""
    baris, unduh = [], []
    for r in tampil.itertuples():
        sel = [f"<b>{theme.esc(r.position_name)}</b>", theme.esc(str(r.level)),
               theme.esc(r.loc), kosong,
               n(r.kandidat), n(r.ongoing), n(r.hired), n(r.pool), n(r.gagal),
               kosong, kosong, kosong]
        unduh.append(_baris_polos([r.position_name] + sel[1:]))

        kand = M.position_candidates(sub, lt, r.position_name, r.loc, sf=sf,
                                     estimasi=est_semua)
        detail = []
        for x in kand.itertuples():
            dsel = [theme.esc(x.candidate_id), theme.esc(x.level), theme.esc(x.loc),
                    theme.esc(x.last_progress),
                    kosong, kosong, kosong, kosong, kosong,
                    _sel_sla(x.total_lt, x.budget_total),
                    _sel_est(x.estimasi, x.status1),
                    theme.result_pill(x.status1)]
            detail.append(dsel)
            unduh.append(_baris_polos([f"   {x.candidate_id}"] + dsel[1:]))
        baris.append({"cells": sel, "detail": detail})

    total_sel = ["TOTAL", "", "", "", n(ring["kandidat"]), n(ring["ongoing"]),
                 n(ring["hired"]), n(ring["pool"]), n(ring["gagal"]), "", "", ""]

    unduh_saja("tp_dep", f"{dep} — positions & candidates", label,
               HEAD_DEP, unduh, align=ALIGN_DEP,
               total_row=_baris_polos(total_sel))
    st.markdown(theme.group_table(
        "tpd", KOLOM_DEP, baris, tinggi=560,
        petunjuk=f"{len(tampil)} positions · [+] opens the candidates",
        total=total_sel), unsafe_allow_html=True)

    st.markdown(theme.inline_note(
        "Count columns belong to the <b>position</b> rows; SLA, Estimate "
        "Onboarding and Status belong to the <b>candidate</b> rows underneath. "
        "<b>SLA / target</b> is working days used, summed stage by stage, against "
        "the SLA budget for that level — so candidates still running or already "
        "failed have a number too. <b>Estimate Onboarding</b> is the projected "
        "start date for anyone still OPEN.", block=True), unsafe_allow_html=True)


MODE_POSISI = {
    "By Position": _mode_posisi,
    "By Department": _mode_departemen,
}


def page_tracking_position():
    """Dua cara masuk ke data yang sama.

    Per Posisi menjawab "posisi X isinya siapa" dan jadi default karena itu
    pertanyaan yang paling sering. Per Departemen menjawab "departemen saya sudah
    sampai mana" — dijawab bertingkat: pilih departemen, lalu buka posisinya satu
    per satu, karena melihat semua posisi sekaligus sebagai tabel bukan tracking,
    cuma daftar.

    Keduanya memakai definisi yang sama (metrics._ringkas) dan filter yang sama,
    jadi angkanya bisa dibandingkan langsung.
    """
    df, sf, lt = data_or_stop()

    with st.container(key="modebar_tp"):
        mode = st.segmented_control(
            "Mode", list(MODE_POSISI), default="By Position", key="tp_mode",
            label_visibility="collapsed")
    MODE_POSISI[mode or "By Position"](df, sf, lt)


# ===========================================================================
# ④ WEEKLY REPORT
# ===========================================================================
def page_weekly():
    df, sf, lt = data_or_stop()

    tahun_ada = sorted(sf["screening_date"].dropna().dt.year.unique().tolist(), reverse=True)
    thn_default = [str(tahun_ada[0])] if tahun_ada else []

    # Satu baris filter untuk SELURUH halaman. Semua bagian di bawah — Performance,
    # New Hire, Ringkasan per site, On Progress, dan Karyawan resign — membaca
    # pilihan yang sama.
    tahun_pilih, bulan_pilih, site_pilih = filterbar("wk", [
        {"label": "Year", "key": "wk_year", "kind": "multi",
         "options": [str(y) for y in tahun_ada], "default": thn_default, "width": 1,
         "placeholder": "Year"},
        {"label": "Month", "key": "wk_month", "kind": "multi",
         "options": list(M.BULAN_NAMA.values()), "default": [], "width": 2,
         "placeholder": "All months — pick several to compare"},
        {"label": "Site", "key": "wk_site", "kind": "multi",
         "options": list(C.SITES), "default": [], "width": 1,
         "placeholder": "All sites"},
    ])

    periods = periode_terpilih(tahun_pilih, bulan_pilih)
    if tahun_pilih and not bulan_pilih:
        # Tidak memilih bulan berarti seluruh bulan pada tahun yang dipilih.
        periods = [(int(t), b) for t in tahun_pilih for b in range(1, 13)]

    if periods:
        dari = min(pd.Timestamp(t, b, 1) for t, b in periods)
        sampai = max(pd.Timestamp(t, b, 1) + pd.offsets.MonthEnd(1) for t, b in periods)
        label_periode = f"{dari.date()} to {sampai.date()}"
    else:
        dari = sampai = None
        label_periode = "sepanjang waktu"
    label_site = ", ".join(site_pilih) if site_pilih else "all sites"

    # ── Performance ────────────────────────────────────────────────────────
    st.markdown(theme.section_heading(
        1, "Recruiter performance",
        "the average of each stage, summed across every process stage"),
        unsafe_allow_html=True)

    perf = M.recruiter_performance(sf, dari, sampai, sites=site_pilih)
    with theme.card("wk_perf", "Performance",
                    f"CV screening period · {label_periode} · {label_site}"):
        baris = []
        for r in perf.itertuples():
            ach = r.achievement
            warna = (theme.STATUS["good"] if pd.notna(ach) and ach >= 100
                     else theme.STATUS["bad"] if pd.notna(ach) else theme.NEUTRAL["text_soft"])
            baris.append([
                theme.esc(r.name),
                n(r.sla_actual, 1) if pd.notna(r.sla_actual) else "—",
                n(r.sla_budget, 1) if pd.notna(r.sla_budget) else "—",
                (f'<span style="color:{warna};font-weight:800">{n(ach, 1)}%</span>'
                 if pd.notna(ach) else "—"),
                n(r.candidates), n(r.onboarding),
            ])
        tabel("wk_perf", "Recruiter performance",
              f"{label_periode} · {label_site}",
              ["Recruiter", "SLA actual", "SLA budget", "Achievement", "Candidates",
               "Onboarded"], baris, align="lrrrrr", max_rows=None)
        st.markdown(theme.inline_note(
            "<b>Candidates</b> uses the <b>CV Screening</b> date — how many CVs that "
            "person processed in this period. <b>Onboarded</b> uses the "
            "<b>onboarding</b> date — how many actually started work in this period. "
            "Two different date bases, and that is deliberate: it is what makes the "
            "Onboarded column add up to exactly the same total as <b>Summary per "
            "site</b> below. Candidates with an empty PIC land in the <b>PIC Site …</b> "
            "row rather than disappearing. <b>SLA</b> sums the average of every "
            "process stage, One Month Notice included; <b>Achievement</b> = "
            "Budget ÷ Actual.",
            block=True), unsafe_allow_html=True)

    # ── New Hire ───────────────────────────────────────────────────────────
    st.markdown(theme.section_heading(2, "New Hire", "onboarding per department"),
                unsafe_allow_html=True)
    with theme.card("wk_nh", "New Hire", f"{label_periode} · {label_site}"):
        nh = M.new_hire_matrix(df, periods, sites=site_pilih)
        if nh.empty:
            st.markdown(theme.empty_state(
                "No onboarding in this period",
                "Change the year, month or site above."), unsafe_allow_html=True)
        else:
            kolom = list(nh.columns)
            isi = [[theme.esc(r[0])] + [n(v) for v in r[1:]] for r in nh.values.tolist()]
            tabel("wk_nh", "New Hire", f"{label_periode} · {label_site}",
                  kolom, isi[:-1], total_row=isi[-1],
                  align="l" + "r" * (len(kolom) - 1))

    # ── Ringkasan per site ─────────────────────────────────────────────────
    st.markdown(theme.section_heading(3, "Summary per site", "onboarding per site"),
                unsafe_allow_html=True)
    with theme.card("wk_sum", "Summary", f"{label_periode} · {label_site}"):
        sm = M.summary_matrix(df, periods, sites=site_pilih)
        if sm.empty:
            st.markdown(theme.empty_state(
                "No onboarding in this period",
                "Change the year, month or site above."), unsafe_allow_html=True)
        else:
            kolom = list(sm.columns)
            isi = [[theme.esc(r[0])] + [n(v) for v in r[1:]] for r in sm.values.tolist()]
            tabel("wk_sum", "Summary per site", f"{label_periode} · {label_site}",
                  kolom, isi[:-1], total_row=isi[-1],
                  align="l" + "r" * (len(kolom) - 1))

    # ── On Progress ────────────────────────────────────────────────────────
    st.markdown(theme.section_heading(
        4, "On Progress", "mengikuti rumus sheet ONP, mengikuti filter di atas"),
        unsafe_allow_html=True)
    panels = M.on_progress(df, periods=periods, sites=site_pilih)
    cols = st.columns(3, gap="small")
    for col, (nama, sel) in zip(cols, panels.items()):
        with col, theme.card(f"wk_onp_{nama}", nama, f"{len(sel)} candidates"):
            if sel.empty:
                st.markdown(theme.empty_state("Empty", "Nobody at this stage.", emoji="—"),
                            unsafe_allow_html=True)
            else:
                tabel(f"wk_onp_{nama}", f"On Progress {nama}",
                      f"{label_periode} · {label_site}",
                      ["Candidate", "Position", "Site", "Date"],
                      [[theme.esc(r.candidate_id), theme.esc(r.position_name),
                        theme.esc(r.loc),
                        theme.esc(r.tanggal.date() if pd.notna(r.tanggal) else None)]
                       for r in sel.itertuples()], align="llll")

    # ── Karyawan resign ────────────────────────────────────────────────────
    st.markdown(theme.section_heading(
        5, "Resignations", "resignation date and site follow the filters above"),
        unsafe_allow_html=True)
    with theme.card("wk_resign", "Resign",
                    f"{label_periode} · {label_site} · levels below 11"):
        mpp = get_mpp()
        if mpp is None:
            st.markdown(theme.empty_state(
                "MPP data could not be loaded",
                "The <b>Update MPP</b> tab in the Report spreadsheet could not be read. "
                "Make sure the spreadsheet is shared as 'Anyone with the link — "
                "Viewer'.", emoji="🔌"),
                unsafe_allow_html=True)
        else:
            res = M.resign(mpp, periods=periods, sites=site_pilih)
            if res.empty:
                st.markdown(theme.empty_state("No resignations in this period", "—"),
                            unsafe_allow_html=True)
            else:
                tabel("wk_resign", "Resignations",
                      f"{label_periode} · {label_site}",
                      ["Employee", "Position", "Site", "Resignation date",
                       "Contract end", "Level"],
                      [[theme.esc(r[1]), theme.esc(r[2]), theme.esc(r[3]),
                        theme.esc(r[4].date() if pd.notna(r[4]) else None),
                        theme.esc(r[5].date() if pd.notna(r[5]) else None),
                        n(r[6])] for r in res.itertuples()], align="lllllr")


# ===========================================================================
# ⑤ PRF TRACKING
# ===========================================================================
@st.cache_data(ttl=C.CACHE_TTL_SECONDS, show_spinner="Loading PRF data…")
def get_prf():
    return M.prepare_prf(DL.load_prf())


def page_prf():
    try:
        prf = get_prf()
    except Exception as exc:  # noqa: BLE001
        st.error(f"The PRF data could not be loaded.\n\n{exc}")
        st.stop()

    # Pilihan filter diambil dari data untuk site/level/divisi, tapi Tracking dan
    # Status memakai daftar tetap di config: CLOSE dan CANCEL belum pernah ada
    # satu baris pun, dan filter yang menyusut sendiri terbaca seperti fitur yang
    # hilang, bukan seperti keadaan yang memang belum terjadi.
    site_opt = sorted(prf["site"].unique())
    level_opt = sorted(prf["level"].unique())

    site_p, level_p, jenis_p, track_p, status_p = filterbar("prf", [
        {"label": "Site", "key": "prf_site", "kind": "multi",
         "options": site_opt, "default": [], "placeholder": "All sites"},
        {"label": "Level", "key": "prf_level", "kind": "multi",
         "options": level_opt, "default": [], "placeholder": "All levels"},
        {"label": "Level type", "key": "prf_jenis", "kind": "multi",
         "options": ["Staff", "Non Staff"], "default": [],
         "placeholder": "Staff & Non Staff"},
        {"label": "Tracking PRF", "key": "prf_track", "kind": "multi",
         "options": C.PRF_TRACKING_VALUES, "default": [], "placeholder": "All"},
        {"label": "Status PRF", "key": "prf_status", "kind": "multi",
         "options": C.PRF_STATUS_VALUES, "default": [], "placeholder": "All"},
    ])

    d = M.filter_prf(prf, sites=site_p, levels=level_p, level_types=jenis_p,
                     trackings=track_p, statuses=status_p)
    s = M.prf_summary(d)

    dipilih = [", ".join(x) for x in (site_p, level_p, jenis_p, track_p, status_p) if x]
    label_filter = " · ".join(dipilih) if dipilih else "all PRFs"

    # ── Kartu ──────────────────────────────────────────────────────────────
    st.markdown(theme.section_heading(1, "PRF summary", label_filter),
                unsafe_allow_html=True)
    k = st.columns(4, gap="small")
    with k[0]:
        st.markdown(theme.kpi_card(
            "PRF count", n(s["total"]), f'{n(s["qty"])} people requested',
            emoji="📄", accent=theme.BRAND["navy"], value_size=28),
            unsafe_allow_html=True)
    with k[1]:
        st.markdown(theme.kpi_card(
            "Approved", n(s["approved"]), f'{n(s["approved_pct"], 1)}% of all PRFs',
            emoji="✅", accent=theme.STATUS["good"], value_size=28),
            unsafe_allow_html=True)
    with k[2]:
        st.markdown(theme.kpi_card(
            "Not Approved", n(s["not_approved"]),
            f'{n(s["not_approved_pct"], 1)}% of all PRFs',
            emoji="⏳", accent=theme.STATUS["warn"], value_size=28),
            unsafe_allow_html=True)
    with k[3]:
        st.markdown(theme.kpi_card(
            "Status Close", n(s["close"]), f'{n(s["close_pct"], 1)}% of all PRFs',
            emoji="🔒", accent=theme.BRAND["orange"], value_size=28),
            unsafe_allow_html=True)

    st.markdown(theme.inline_note(
        "<b>Approved</b> and <b>Not Approved</b> come from the PRF Tracking column — "
        "the request is either approved or still moving. <b>Status Close</b> comes "
        "from the Status column and its percentage is measured against <b>all "
        "PRFs</b>, not only the approved ones. Every figure counts <b>PRF rows</b>, "
        "not headcount — one PRF can ask for several people at once, and that qty "
        "is shown on every row of the table.",
        block=True), unsafe_allow_html=True)

    # ── Tabel ──────────────────────────────────────────────────────────────
    st.markdown(theme.section_heading(2, "PRF list", "one row per request"),
                unsafe_allow_html=True)
    with theme.card("prf_tabel", "PRF", f"{n(len(d))} rows · {label_filter}"):
        if d.empty:
            st.markdown(theme.empty_state(
                "No PRF", "No row matches the filters above."),
                unsafe_allow_html=True)
            return

        baris = []
        for r in d.sort_values(["site", "level", "position_name"]).itertuples():
            baris.append([
                theme.esc(r.prf_id), theme.esc(r.prf_class), n(r.qty),
                theme.esc(r.position_name), theme.esc(r.site), theme.esc(r.divisi),
                f"{theme.esc(r.level)} <span style='color:{theme.NEUTRAL['text_soft']}'>"
                f"· {theme.esc(r.level_type)}</span>",
                theme.esc(r.tracking), theme.esc(r.status),
            ])
        tabel("prf_tabel", "PRF Tracking", label_filter,
              ["Request Number", "PRF Class", "Qty", "Position Name", "Site",
               "Division", "Level", "Tracking PRF", "Status PRF"],
              baris, align="llrllllll")
        st.markdown(theme.inline_note(
            "<b>Request Number</b> falls back to the PRF ID when the request number "
            "has not been issued yet — one identity column instead of two "
            "half-empty ones.",
            block=True), unsafe_allow_html=True)


# ===========================================================================
# ⑥ SUMMARY BY DIVISION
# ===========================================================================
@st.cache_data(ttl=C.CACHE_TTL_SECONDS, show_spinner="Loading MPP & headcount…")
def get_mpp_actual():
    """(reforecast, headcount aktif, ADP) — tiga tab di spreadsheet Report.

    Sejak 8 Sep 2026 ketiganya diambil dari tab yang persis sama dengan yang
    dipakai rumus di sheet "Copy of Summary by Division": MPP2, Existing
    Employee, dan ADP. Sebelumnya MPP diambil dari spreadsheet lain dan divisi
    karyawan ditebak dari huruf pertama Position Code — dua sumber berbeda untuk
    satu angka yang sama adalah cara paling pasti membuat portal dan sheet
    berselisih.

    Kalau salah satu gagal diambil, halaman menjelaskan keadaannya alih-alih
    menampilkan Gap yang dihitung dari angka setengah.
    """
    ref = M.prepare_reforecast(DL.load_mpp2())
    hc = M.prepare_headcount(DL.load_existing_employee())
    try:
        adp = M.prepare_adp(DL.load_adp())
    except Exception:  # noqa: BLE001
        # ADP hanya menambah satu kolom; kalau tabnya bermasalah, halaman tetap
        # berguna tanpa kolom itu.
        adp = None
    try:
        bm = DL.load_process_monitoring()
    except Exception:  # noqa: BLE001
        bm = None
    return ref, hc, adp, bm


def _cand_divisi(df):
    """Kandidat disandingkan dengan MPP: pakai nama kolom yang sama.

    Penggabungan divisi ikut diterapkan di sini — kalau tidak, kandidat
    Warehouse akan berdiri di barisnya sendiri sementara MPP dan Actual-nya
    sudah pindah ke Supply Chain Management.
    """
    c = df.copy()
    c["divisi"] = c["departement"].map(C.merge_division)
    c["site"] = c["loc"]
    c["level_code"] = M.candidate_level_code(c)
    return c


def _baris_angka(r, kolom_mpp=True):
    """Angka ringkas satu baris divisi/level."""
    isi = []
    if kolom_mpp:
        isi += [("MPP", n(r["mpp"])), ("Actual", n(r["actual"]))]
        # stat_inline meng-escape isinya, jadi angkanya ditulis polos. Warnanya
        # sudah disampaikan batang sebaran dan tabel level di bawah.
        isi += [("Gap", f'{int(r["gap"]):+d}')]
    isi += [("Diproses", n(r["ongoing"])), ("Onboarded", n(r["hired"]))]
    return theme.stat_inline(isi)


def _detail_level(kunci, dfc, lt, sf, est, divisi, nama_level, site):
    """Isi paling dalam: posisi apa saja dan siapa yang sedang diproses.

    Disaring lewat NAMA level, bukan kodenya, karena satu nama bisa mewakili dua
    kode (level 7 dan 6 sama-sama "Manager").
    """
    c = dfc[(dfc["divisi"] == divisi)
            & (dfc["level_code"].map(C.level_name) == nama_level)]
    if site:
        c = c[c["site"] == site]
    if c.empty:
        st.markdown(theme.inline_note(
            "No candidate recorded at this level — the MPP and Actual columns above "
            "come from the MPP sheet and the employee list, not from the "
            "recruitment pipeline.", block=True), unsafe_allow_html=True)
        return

    pos = (c.groupby(["position_name", "loc"], dropna=False)
             .apply(lambda g: pd.Series(M._ringkas(g)), include_groups=False)
             .reset_index().sort_values(["ongoing", "kandidat"], ascending=False))
    tabel(f"{kunci}_pos", f"Positions — {divisi}", nama_level,
          ["Position", "Site", "Candidates", "In process", "Onboarded",
           "Backup", "Failed"],
          [[theme.esc(r.position_name), theme.esc(r.loc), n(r.kandidat),
            n(r.ongoing), n(r.hired), n(r.pool), n(r.gagal)]
           for r in pos.itertuples()], align="llrrrrr")

    jalan = c[c["status1"] == "OPEN"]
    if jalan.empty:
        return
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    jalan = jalan.merge(lt[["cand_key", "budget_total"]], on="cand_key", how="left")
    jalan["sla"] = jalan["cand_key"].map(M.sla_per_candidate(sf))
    jalan["est"] = jalan["cand_key"].map(est)
    tabel(f"{kunci}_kand", f"In process — {divisi}", nama_level,
          ["Candidate", "Position", "Site", "Last stage", "SLA / target",
           "Estimate Onboarding"],
          [[theme.esc(r.candidate_id), theme.esc(r.position_name), theme.esc(r.loc),
            theme.esc(r.last_progress),
            _sel_sla(r.sla, r.budget_total),
            _sel_est(r.est, "OPEN")]
           for r in jalan.itertuples()], align="llllrr")


# Susunan kolom tabel Summary by Division. Dipisah jadi konstanta supaya tabel
# ringkas (divisi) dan tabel detail (level) dijamin memakai kolom yang sama —
# itu inti dari grouping ala Excel: barisnya bertingkat, kolomnya satu.
KOLOM_DIVISI = [
    {"label": "Division / Level", "align": "l"},
    {"label": "MPP", "align": "r"},
    {"label": "Actual", "align": "r"},
    {"label": "Gap", "align": "r"},
    {"label": "ADP", "align": "r"},
    {"label": "FTAP", "align": "r"},
    {"label": "Need to hire", "align": "r"},
    {"label": "Candidates", "align": "r", "sep": True},
    {"label": "Onboarded", "align": "r"},
    {"label": "Failed", "align": "r"},
    {"label": "Interview User", "align": "r", "sep": True,
     "sub": ["On prog", "Passed", "Failed"]},
    {"label": "Psychotest", "align": "r", "sep": True,
     "sub": ["On prog", "Passed", "Failed"]},
    {"label": "Offering", "align": "r", "sep": True,
     "sub": ["On prog", "Passed", "Failed"]},
    {"label": "MCU", "align": "r", "sep": True,
     "sub": ["On prog", "Passed", "Failed"]},
    {"label": "Ready to onboard", "align": "r", "sep": True},
]
# Judul datar untuk unduhan Excel/PNG: header dua tingkat tidak punya padanan
# di file, jadi nama grupnya ditempelkan ke tiap anaknya.
# Judul untuk file unduhan. Divisi dan Level dipisah jadi DUA kolom, tidak
# ditumpuk seperti di layar: di layar barisnya bertingkat dan jelas mana induk
# mana anak, tapi di dalam file keduanya berdiri sejajar. Sempat ditandai lekukan
# spasi, dan Excel membuang lekukannya — siapa pun yang menjumlahkan satu kolom
# lalu menghitung baris divisi DAN baris levelnya sekaligus, hasilnya dua kali
# lipat (temuan Navi, 11 Sep 2026). Dengan dua kolom, "baris divisi" = baris yang
# kolom Level-nya kosong, dan penjumlahannya tidak mungkin salah.
HEAD_DIVISI = ["Division", "Level", "MPP", "Actual", "Gap", "ADP", "FTAP",
               "Need to hire", "Candidates", "Onboarded", "Failed"] + [
    f"{t} — {k}" for t in ("Interview User", "Psychotest", "Offering", "MCU")
    for k in ("On prog", "Passed", "Failed")] + ["Ready to onboard"]
ALIGN_DIVISI = "ll" + "r" * (len(HEAD_DIVISI) - 2)


def _gap_sel(v):
    """Gap diwarnai: kurang orang merah, cukup/lebih hijau. Selalu bertanda."""
    v = int(v)
    warna = theme.STATUS["bad"] if v < 0 else theme.STATUS["good"]
    return f'<span style="color:{warna};font-weight:700">{v:+d}</span>'


def _nol_abu(v):
    """Angka nol ditulis abu supaya mata langsung lompat ke yang ada isinya."""
    v = int(v)
    if not v:
        return f'<span style="color:{theme.NEUTRAL["text_soft"]}">0</span>'
    return n(v)


def _proc_sel(pb, kunci, slug, jenis):
    """Satu sel proses, diwarnai menurut artinya."""
    v = 0
    if pb is not None and kunci in pb.index:
        v = int(pb.loc[kunci, f"{slug}_{jenis}"])
    if not v:
        return f'<span style="color:{theme.NEUTRAL["text_soft"]}">0</span>'
    warna = {"progress": theme.STATUS["warn"], "passed": theme.STATUS["good"],
             "failed": theme.STATUS["bad"]}[jenis]
    return f'<span style="color:{warna};font-weight:700">{v}</span>'


def _angka0(v):
    """Nilai angka yang aman: kosong / NaN dibaca nol.

    Baris level yang ditambahkan supaya kolom proses tetap menjumlah bisa datang
    tanpa angka MPP/Actual sama sekali — dan itu memang benar, mereka nol.
    """
    try:
        if v is None or pd.isna(v):
            return 0
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _baris_divisi(nama, r, pb, kunci):
    """Satu baris tabel — dipakai baris divisi maupun baris level di bawahnya."""
    mpp, aktual = _angka0(r.get("mpp")), _angka0(r.get("actual"))
    perlu = _angka0(r.get("need", max(mpp - aktual, 0)))
    sel = [nama, n(mpp), n(aktual), _gap_sel(_angka0(r.get("gap"))),
           _nol_abu(_angka0(r.get("adp"))), _nol_abu(_angka0(r.get("ftap"))),
           _nol_abu(perlu),
           n(_angka0(r.get("kandidat"))), n(_angka0(r.get("hired"))),
           n(_angka0(r.get("gagal")))]
    for tahap, slug in M.PROCESS_SLUG.items():
        for jenis in M.PROCESS_KINDS:
            sel.append(_proc_sel(pb, kunci, slug, jenis))
    siap = _angka0(r.get("ready"))
    sel.append(f'<span style="color:{theme.STATUS["good"]};font-weight:700">{siap}</span>'
               if siap else _nol_abu(0))
    return sel


def _baris_polos(sel):
    """Versi teks dari satu baris, untuk file unduhan (tanpa tag HTML)."""
    return [re.sub(r"<[^>]+>", "", str(v)) for v in sel]


def _awal_bulan():
    """Tanggal 1 bulan berjalan — nilai awal filter Summary by Division."""
    return pd.Timestamp.today().normalize().replace(day=1).date()


@st.cache_data(show_spinner=False, ttl=C.CACHE_TTL_SECONDS)
def _rekap_divisi(_ref, _hc, _adp, _bm, _dfc, site, mulai, akhir,
                  status=(), jenis=()):
    """Semua yang dibutuhkan tabel: ringkasan divisi, level tiap divisi, dan
    sebaran prosesnya. Dihitung sekali, bukan per baris.

    `mulai`/`akhir` hanya menyaring KANDIDAT. MPP, Actual, ADP, dan FTAP adalah
    potret keadaan hari ini, bukan kejadian dalam rentang waktu — menyaringnya
    dengan tanggal akan menghasilkan angka yang tidak berarti apa-apa.

    **Kolom proses punya sumber dan aturan waktunya sendiri.** Ia dibaca dari
    tab monitoring (`_bm`) — tab yang sama dengan yang dibaca rumus sheet — dan
    tidak ikut filter tanggal halaman: yang ditanya kolom itu adalah "sekarang
    orangnya ada di mana", dan itu tidak punya periode. Jendela waktunya sudah
    dipatok di dalam rumusnya sendiri: dua bulan terakhir, khusus kolom Failed.
    """
    # Filter Staff / Non Staff berlaku untuk SELURUH tabel, bukan kolom kandidat
    # saja: Need to hire untuk "Staff" harus memakai MPP Staff dan Actual Staff,
    # kalau tidak angkanya membandingkan dua populasi yang berbeda. Struktur
    # sheet tim juga begitu — tiap bloknya Staff atau Non Staff.
    if jenis:
        pilih = set(jenis)
        _ref = _ref[_ref["status"].isin(pilih)]
        _hc = _hc[_hc["status"].isin(pilih)]
        if _adp is not None and len(_adp):
            _adp = _adp[_adp["status"].isin(pilih)]
        if _bm is not None and len(_bm) and "jenis" in _bm.columns:
            _bm = _bm[_bm["jenis"].isin(pilih)]

    div = M.division_summary(_ref, _hc, _dfc, site=site, adp=_adp)

    stat = [C.STATUS_OPTIONS.get(x, str(x).upper()) for x in (status or ())]

    # Kolom proses dibaca dari tab MONITORING — sumber yang sama dengan rumus
    # sheet, bukan fix_centralized (arahan Navi, 11 Sep 2026). Sumber sama +
    # rumus sama = hasil sama; dan memang begitu hasilnya: rantai antar tahap
    # menutup persis di setiap divisi.
    #
    # Dihitung di butiran PALING HALUS (divisi ▸ level), lalu angka divisinya
    # DITURUNKAN dengan menjumlahkan barisnya. Batas rantai diterapkan per
    # baris, jadi kalau divisi dihitung terpisah, batasnya bisa berbeda dari
    # batas per level dan baris levelnya tidak menjumlah ke barisnya.
    pb_lvl = M.process_from_monitoring(_bm, site=site, statuses=stat)
    # Kolom kandidat (Candidates / Onboarded / Ready to onboard / Failed) dibaca
    # dari tab yang sama — satu sumber untuk seluruh blok kanan tabel.
    kand_lvl = M.candidate_counts_monitoring(_bm, site=site, statuses=stat)
    if len(kand_lvl):
        pb_lvl = (pb_lvl.join(kand_lvl, how="outer").fillna(0).astype(int)
                  if len(pb_lvl) else kand_lvl)
    pb_lvl = pb_lvl if len(pb_lvl) else None

    if pb_lvl is not None and len(pb_lvl):
        _d = pb_lvl.copy()
        _d["_div"] = [str(i).split(C.LEVEL_SEP)[0] for i in _d.index]
        pb_div = _d.groupby("_div").sum(numeric_only=True)
        pb_div.index.name = "_grup"
    else:
        pb_div = None

    # Divisi yang punya kandidat di kolom proses tapi belum punya baris — divisi
    # yang tidak dikenal MPP maupun daftar karyawan, misalnya kandidat yang
    # departemennya kosong di sumber. Tanpa baris ini, angkanya tetap ikut di
    # baris TOTAL sementara tidak ada baris yang memuatnya, dan kolom Passed
    # Interview User tidak akan pernah menjumlah ke totalnya (temuan Navi,
    # 11 Sep 2026: TOTAL 88 sementara barisnya hanya berjumlah 73).
    if pb_div is not None:
        belum = [g for g in pb_div.index if g not in set(div["divisi"])]
        if belum:
            tambah = pd.DataFrame({"divisi": belum})
            for k in ("mpp", "actual", "gap", "adp", "ftap", "need",
                      "kandidat", "ongoing", "hired", "pool", "gagal"):
                tambah[k] = 0
            div = pd.concat([div, tambah[div.columns]], ignore_index=True)
        # Angka kandidat diambil alih dari monitoring, menggantikan hitungan
        # lama dari fix_centralized — satu sumber, satu definisi.
        for k in ("kandidat", "hired", "gagal", "ready"):
            if k in pb_div.columns:
                div[k] = (pb_div[k].reindex(div["divisi"]).fillna(0)
                          .astype(int).values)

    level = {}
    for r in div.itertuples():
        lvl = M.level_summary(_ref, _hc, _dfc, r.divisi, site=site, adp=_adp)
        # Level yang punya kandidat di kolom proses tapi belum punya baris —
        # perlakuan yang sama dengan divisi di atas, supaya baris level selalu
        # menjumlah ke baris divisinya.
        if pb_lvl is not None:
            awalan = f"{r.divisi}{C.LEVEL_SEP}"
            punya = set(lvl["level"]) if len(lvl) else set()
            kurang = [str(i)[len(awalan):] for i in pb_lvl.index
                      if str(i).startswith(awalan)
                      and str(i)[len(awalan):] not in punya]
            if kurang:
                kolom0 = list(lvl.columns) if len(lvl.columns) else []
                kolom = kolom0 or [
                    "level", "mpp", "actual", "gap", "adp", "ftap", "need",
                    "kandidat", "ongoing", "hired", "pool", "gagal", "level_code"]
                t = pd.DataFrame(0, index=range(len(kurang)), columns=kolom)
                t["level"] = kurang
                if "level_code" in kolom:
                    t["level_code"] = None
                lvl = pd.concat([lvl, t], ignore_index=True)
                for k in ("mpp", "actual", "gap", "adp", "ftap", "need",
                          "kandidat", "ongoing", "hired", "pool", "gagal"):
                    if k in lvl.columns:
                        lvl[k] = pd.to_numeric(lvl[k], errors="coerce").fillna(0).astype(int)
            # Angka kandidat per level juga diambil alih dari monitoring, sama
            # seperti barisan divisinya — kalau tidak, baris level dan baris
            # divisi menghitung dari dua sumber yang berbeda.
            if len(lvl):
                kunci_l = [f"{r.divisi}{C.LEVEL_SEP}{x}" for x in lvl["level"]]
                for k in ("kandidat", "hired", "gagal", "ready"):
                    if k in pb_lvl.columns:
                        lvl[k] = (pb_lvl[k].reindex(kunci_l).fillna(0)
                                  .astype(int).values)
        level[r.divisi] = lvl
    return div, level, pb_div, pb_lvl


def page_division():
    """MPP vs isi organisasi vs pipeline, dalam SATU tabel yang bisa dibuka.

    Bentuknya sengaja meniru grouping Excel yang sudah dipakai tim: klik [+] di
    depan nama divisi, baris levelnya muncul tepat di bawahnya, dalam kolom yang
    sama persis. Buka-tutupnya murni CSS: tidak ada rerun, dan semua divisi
    berdiri di kolom yang sama sehingga bisa dibaca menurun.

    Kolom prosesnya (Interview User, Psychotest, Offering, MCU — masing-masing
    On progress / Passed / Failed) sengaja ditaruh di sebelah kanan: yang paling
    sering dicari adalah MPP-Actual-Gap, dan itu tetap terlihat karena kolom
    pertama dibekukan saat tabelnya digeser.
    """
    df, sf, lt = data_or_stop()
    try:
        ref, hc, adp, bm = get_mpp_actual()
    except Exception as exc:  # noqa: BLE001
        st.error(f"MPP or the employee list could not be loaded.\n\n{exc}")
        st.stop()

    situs = ["All"] + [s for s in ["BCP", "KCP", "ACP", "SSCP", "JKT", "BPN"]
                       if (ref["site"] == s).any() or (hc["site"] == s).any()]
    with st.container(key="modebar_sd"):
        pilih = st.segmented_control("Site", situs, default="All", key="sd_site",
                                     label_visibility="collapsed")
    site = None if (pilih or "All") == "All" else pilih

    hari_ini = pd.Timestamp.today().normalize().date()
    mulai, akhir, jenis_p, status_p = filterbar("sd_f", [
        {"label": "Active from", "key": "sd_dari",
         "kind": "date", "value": _awal_bulan(),
         "help": "A candidate counts as active in the period when their own "
                 "activity window overlaps it — first stage date to last stage "
                 "date, or to today while still running. Filters the candidate "
                 "columns only: MPP, Actual and ADP are today's snapshot."},
        {"label": "Active to", "key": "sd_sampai", "kind": "date",
         "value": hari_ini},
        {"label": "Level type", "key": "sd_jenis", "kind": "multi",
         "options": ["Staff", "Non Staff"], "default": [],
         "placeholder": "Staff & Non Staff",
         "help": "Narrows the whole table — MPP, Actual, ADP and the candidate "
                 "columns together, the way each block of the team's sheet is "
                 "either Staff or Non Staff."},
        {"label": "Process status", "key": "sd_status", "kind": "multi",
         "options": list(C.STATUS_OPTIONS), "default": list(C.STATUS_DEFAULT),
         "placeholder": "All statuses",
         "help": "Which processes count as live. <In process> is the default "
                 "and matches the team's sheet: On progress and Passed only "
                 "count candidates still moving. Failed always ignores this "
                 "filter — a failed candidate is never in process. MPP, Actual, "
                 "ADP and FTAP never move."},
    ])
    if isinstance(mulai, (list, tuple)):
        mulai = mulai[0] if mulai else None
    if isinstance(akhir, (list, tuple)):
        akhir = akhir[0] if akhir else None
    if mulai and akhir and mulai > akhir:
        mulai, akhir = akhir, mulai

    # Rentang tanggal menyaring SIAPA yang dihitung; status menyaring APA yang
    # dianggap "masih berjalan" di kolom proses. Dua hal berbeda, jadi status
    # sengaja tidak ikut memotong daftar kandidatnya — kalau ikut, kolom Failed
    # akan selalu nol saat filternya "In process".
    dsaring = M.filter_date_range(df, sf, mulai, akhir)
    dfc = _cand_divisi(dsaring)
    est = _estimasi_semua(sf, df)
    periode = (f"{pd.Timestamp(mulai):%d %b %Y} – {pd.Timestamp(akhir):%d %b %Y}"
               if mulai and akhir else "all periods")
    if jenis_p:
        periode += " · " + ", ".join(jenis_p)
    if status_p:
        periode += " · " + ", ".join(status_p)

    div, level, pb_div, pb_lvl = _rekap_divisi(
        ref, hc, adp, bm, dfc, site, mulai, akhir, tuple(status_p),
        tuple(jenis_p))
    if div.empty:
        st.markdown(theme.empty_state("No data yet", "—"), unsafe_allow_html=True)
        return

    judul = "All sites" if site is None else site
    st.markdown(theme.section_heading(
        1, judul, f"{len(div)} divisions · MPP vs. headcount today · "
                  f"candidates active {periode}"), unsafe_allow_html=True)

    for k in ("kandidat", "hired", "gagal", "ready"):
        if k not in div.columns:
            div[k] = 0
    total = {k: int(div[k].sum()) for k in
             ("mpp", "actual", "gap", "adp", "ftap", "need", "kandidat",
              "hired", "gagal", "ready")}
    k = st.columns(5, gap="small")
    kartu = [
        ("MPP", total["mpp"], "planned headcount", "📋", theme.BRAND["navy"]),
        ("Actual", total["actual"], "active employees", "👥", theme.BRAND["orange"]),
        ("Gap", f'{total["gap"]:+d}', "actual − MPP", "⚖️",
         theme.STATUS["bad"] if total["gap"] < 0 else theme.STATUS["good"]),
        ("Need to hire", total["need"],
         f'shortfalls only, {n(total["adp"])} ADP deducted', "🎯",
         theme.STATUS["warn"]),
        ("Candidates", total["kandidat"], "still in process", "⏳",
         theme.STATUS["warn"]),
    ]
    for col, (lab, val, sub, emo, warna) in zip(k, kartu):
        with col:
            st.markdown(theme.kpi_card(lab, n(val) if not isinstance(val, str) else val,
                                       sub, emoji=emo, accent=warna, value_size=26),
                        unsafe_allow_html=True)

    st.markdown(theme.section_heading(
        2, "Division table", "click [+] to open the levels — like grouping in Excel"),
        unsafe_allow_html=True)

    baris, unduh = [], []
    for r in div.itertuples():
        d = r._asdict()
        sel = _baris_divisi(f"<b>{theme.esc(r.divisi)}</b>", d, pb_div, r.divisi)
        unduh.append(_baris_polos([r.divisi, ""] + sel[1:]))

        lvl = level.get(r.divisi)
        detail = []
        if lvl is not None and len(lvl):
            for x in lvl.itertuples():
                kunci = f"{r.divisi}{C.LEVEL_SEP}{x.level}"
                dsel = _baris_divisi(theme.esc(x.level), x._asdict(), pb_lvl, kunci)
                detail.append(dsel)
                unduh.append(_baris_polos([r.divisi, x.level] + dsel[1:]))
        baris.append({"cells": sel, "detail": detail})

    # Baris TOTAL memakai penjumlahan kolom apa adanya. Angka proses dijumlahkan
    # dari tabel divisi, bukan dihitung ulang dari nol, supaya total dan isinya
    # tidak mungkin berbeda.
    def jum(slug, jenis):
        """Total kolom proses — HANYA dari divisi yang benar-benar punya baris.

        Menjumlahkan seluruh isi pb_div akan memuat grup yang tidak tampil
        sebagai baris, dan baris TOTAL jadi lebih besar dari jumlah kolomnya.
        """
        if pb_div is None:
            return 0
        return int(pb_div.reindex(div["divisi"])[f"{slug}_{jenis}"]
                   .fillna(0).sum())

    total_sel = ["TOTAL", n(total["mpp"]), n(total["actual"]),
                 f'{total["gap"]:+d}', n(total["adp"]), n(total["ftap"]),
                 n(total["need"]),
                 n(total["kandidat"]), n(total["hired"]), n(total["gagal"])] + [
        n(jum(sl, jn)) for sl in M.PROCESS_SLUG.values()
        for jn in M.PROCESS_KINDS] + [n(total["ready"])]

    unduh_saja("sd_tabel", f"Summary by Division — {judul}",
               f"{len(div)} divisions · {periode}",
               HEAD_DIVISI, unduh, align=ALIGN_DIVISI,
               total_row=_baris_polos(["TOTAL", ""] + total_sel[1:]))
    st.markdown(theme.group_table(
        "sd", KOLOM_DIVISI, baris, tinggi=560,
        petunjuk=f"{len(div)} divisions · [+] opens the level breakdown",
        total=total_sel), unsafe_allow_html=True)

    # ── Tingkat ketiga: posisi dan orangnya. Tidak dijadikan baris tabel karena
    # isinya bukan angka melainkan daftar nama, dan daftar nama di dalam kolom
    # angka tidak terbaca. Dipilih lewat dua dropdown supaya tetap dua klik.
    st.markdown(theme.section_heading(
        3, "Drill down to people", "pick a division, then a level"),
        unsafe_allow_html=True)

    punya = [r.divisi for r in div.itertuples() if r.kandidat]
    if not punya:
        st.markdown(theme.inline_note(
            "No candidates active in this site and period, so there is nothing to open.",
            block=True), unsafe_allow_html=True)
        return

    with st.container(key="filterbar_sd_drill"):
        c1, c2 = st.columns(2, gap="small")
        with c1:
            dpil = st.selectbox("Division", punya, key="sd_dv",
                                filter_mode="contains")
        lvl = level.get(dpil)
        opsi = [f"{x.level} ({x.kandidat} candidates)"
                for x in lvl.itertuples() if x.kandidat] if lvl is not None else []
        with c2:
            lpil = st.selectbox("Level", ["—"] + opsi, key="sd_lv")

    if lpil and lpil != "—":
        nama_level = lpil.rsplit(" (", 1)[0]
        _detail_level("sd_drill", dfc, lt, sf, est, dpil, nama_level, site)

    _panel_kandidat_divisi(bm, site, jenis_p, status_p, periode)


def _panel_kandidat_divisi(bm, site, jenis_p, status_p, periode):
    """Bagian 4: siapa saja yang sedang diproses, bukan hanya berapa banyak.

    Tabel di atas menjawab "berapa"; bagian ini menjawab "siapa". Keduanya dari
    tab monitoring yang sama, jadi jumlah barisnya di sini persis sama dengan
    angka di kolom Candidates — daftar dan angkanya tidak mungkin berselisih.
    """
    b = bm
    if b is not None and len(b) and jenis_p and "jenis" in b.columns:
        b = b[b["jenis"].isin(set(jenis_p))]
    stat = [C.STATUS_OPTIONS.get(x, str(x).upper()) for x in status_p]
    orang = M.candidates_in_process(b, site=site, statuses=stat)

    st.markdown(theme.section_heading(
        4, "Candidates", "everyone currently in process, with their last stage"),
        unsafe_allow_html=True)

    if orang.empty:
        st.markdown(theme.empty_state(
            "No candidate in process", "Loosen the filters above."),
            unsafe_allow_html=True)
        return

    with theme.card("sd_kandidat", "In process", f"{len(orang)} people · {periode}"):
        tabel("sd_kandidat", "Candidates in process", periode,
              ["Candidate", "Position", "Division", "Level", "Site",
               "Last progress", "Status"],
              [[theme.esc(r.candidate), theme.esc(r.position),
                theme.esc(r.divisi), theme.esc(r.level), theme.esc(r.site),
                theme.esc(r.last_progress), theme.result_pill(r.status)]
               for r in orang.itertuples()], align="llllllr", max_rows=18)


# ===========================================================================
# ⑥ RECRUITMENT ROOM
# ===========================================================================
# Tahap yang boleh ditambahkan sebagai kolom di tabel monitoring. Urutannya
# mengikuti urutan proses, bukan abjad — orang membacanya sebagai perjalanan.
TAHAP_MONITORING = [t for t in M.STAGE_COLUMNS if t != "Onboarding"]


def _panel_monitoring(df, sf, lt):
    """Tabel monitoring pengganti membaca spreadsheet mentah."""
    dasar = M.monitoring_table(df, sf, lt)

    pic_ada = sorted(x for x in dasar["pic"].unique() if x and x != "—")
    dep_ada = sorted(x for x in dasar["departement"].dropna().unique())
    lvl_ada = sorted(x for x in dasar["level"].dropna().unique())
    status_ada = ["OPEN", "CLOSE", "TALENT POOL", "HOLD", "FAILED"]

    bulan_ada = M.month_options(df, sf)
    (bulan_p, site_p, pic_p, dep_p,
     status_p, lvl_p, jenis_p, tahap_p) = filterbar("rr", [
        [{"label": "Month (CV Screening date)", "key": "rr_bulan_f", "kind": "multi",
          "options": bulan_ada, "default": [], "width": 2,
          "placeholder": "All months"},
         {"label": "Site", "key": "rr_site_f", "kind": "multi",
          "options": list(C.SITES), "default": [], "placeholder": "All sites"},
         {"label": "PIC (Screening CV)", "key": "rr_pic_f", "kind": "multi",
          "options": pic_ada, "default": [], "placeholder": "All recruiters"}],
        [{"label": "Department", "key": "rr_dep_f", "kind": "multi",
          "options": dep_ada, "default": [], "placeholder": "All departments",
          "width": 2},
         {"label": "Status", "key": "rr_status_f", "kind": "multi",
          "options": status_ada, "default": [], "placeholder": "All statuses"},
         {"label": "Level", "key": "rr_level_f", "kind": "multi",
          "options": lvl_ada, "default": [], "placeholder": "All levels"},
         {"label": "Level type", "key": "rr_jenis_f", "kind": "multi",
          "options": ["Staff", "Non Staff"], "default": [],
          "placeholder": "Staff & Non Staff"}],
        [{"label": "Add stage columns", "key": "rr_tahap_f", "kind": "multi",
          "options": TAHAP_MONITORING, "default": [],
          "placeholder": "Core columns only — pick a stage to add its LT and SLA",
          "help": "Each stage adds two columns: its lead time and its SLA result. "
                  "Variance and LT contribution are deliberately left out — both "
                  "are derived from figures already on screen."}],
    ])

    d = M.filter_monitoring(
        M.monitoring_table(M.filter_month(df, sf, bulan_p), sf, lt, stages=tahap_p),
        sites=site_p, pics=pic_p, departemen=dep_p, statuses=status_p,
        levels=lvl_p, level_types=jenis_p)

    dipilih = [", ".join(x) for x in
               (bulan_p, site_p, pic_p, dep_p, status_p, lvl_p, jenis_p) if x]
    label = " · ".join(dipilih) if dipilih else "all candidates"

    st.markdown(theme.section_heading(
        1, "Candidate monitoring", label), unsafe_allow_html=True)

    if len(d):
        _kartu_ringkas(M._ringkas(d))

    with theme.card("rr_mon", "Monitoring", f"{n(len(d))} candidates · {label}"):
        if d.empty:
            st.markdown(theme.empty_state(
                "No candidates", "No row matches the filters above."),
                unsafe_allow_html=True)
            return d

        inti = ["Candidate", "Position", "Site", "Department", "Level", "PIC",
                "Last stage", "Status", "SLA"]
        kol_tahap = []
        for t in tahap_p:
            kol_tahap += [f"{t} · LT", f"{t} · SLA"]
        headers = inti + kol_tahap
        align = "llllllll" + "r" + "rl" * len(tahap_p)

        # Dibaca sebagai dict, bukan itertuples: nama kolom tahap mengandung spasi
        # dan titik tengah, dan itertuples diam-diam menggantinya jadi _1, _2.
        baris = []
        for r in d.sort_values(["loc", "departement", "candidate_id"]).to_dict("records"):
            inti_baris = [
                theme.esc(r["candidate_id"]), theme.esc(r["position_name"]),
                theme.esc(r["loc"]), theme.esc(r["departement"]),
                theme.esc(r["level"]), theme.esc(r["pic"]),
                theme.esc(r["last_progress"]), theme.result_pill(r["status"]),
                n(r["lt_elapsed"]) if pd.notna(r["lt_elapsed"]) else "—",
            ]
            for t in tahap_p:
                v, sla = r.get(f"{t} · LT"), r.get(f"{t} · SLA")
                inti_baris += [
                    n(v) if pd.notna(v) else "—",
                    theme.sla_pill(sla) if sla and sla != "—" else "—",
                ]
            baris.append(inti_baris)

        tabel("rr_mon", "Candidate monitoring", label, headers, baris, align=align)
        st.markdown(theme.inline_note(
            "Each stage added through the filter brings only its <b>LT</b> and "
            "<b>SLA</b>. <b>PIC</b> comes from the CV Screening PIC — the same basis "
            "as "
            "the Recruiter performance table, so the two can be compared directly.",
            block=True), unsafe_allow_html=True)
    return d


def _panel_talent_pool(df, d):
    """Backup candidate, mengikuti filter monitoring di atasnya.

    Ditaruh di sini, bukan di Overview: di Overview orang cuma melihat angkanya,
    di sini orang benar-benar menindaklanjutinya — dan nomor HP-nya jadi berguna
    justru saat filter site/PIC sudah dipersempit.
    """
    kunci = set(d[d["talent_pool"]]["cand_key"])
    tp = M.talent_pool(df)
    tp = tp[tp["cand_key"].isin(kunci)]

    st.markdown(theme.section_heading(
        2, "Backup candidate", "passed selection, not yet placed"), unsafe_allow_html=True)
    with theme.card("rr_tp", "Backup candidate",
                    f"{len(tp)} people · follows the filters above"):
        if tp.empty:
            st.markdown(theme.empty_state(
                "No backup candidate",
                "A candidate joins this list as soon as any stage is marked "
                "<b>TALENT POOL</b> on the form. Loosen the filters above if "
                "the list is empty when it should not be."), unsafe_allow_html=True)
            return
        tabel("rr_tp", "Backup candidate", f"{len(tp)} people",
              ["Candidate", "Phone", "Position applied for", "Department", "Site",
               "Level", "Moved to backup at"],
              [[theme.esc(r.candidate_id), theme.esc(r.phone or "—"),
                theme.esc(r.position_name), theme.esc(r.departement),
                theme.esc(r.loc), theme.esc(r.level), theme.esc(r.stage)]
               for r in tp.itertuples()], align="lllllll")
        st.markdown(theme.inline_note(
            "Site, level and stage are shown because they decide who makes the call, "
            "what role is worth offering, and how much of the selection does not "
            "have to be repeated. Phone numbers come from the Backend Monitoring "
            "sheet — fix_centralized does not carry that column.",
            block=True), unsafe_allow_html=True)


def _panel_link():
    """Daftar link form dan spreadsheet per site — tanpa embed."""
    st.markdown(theme.section_heading(
        3, "Link form & spreadsheet", "salin atau buka di tab baru"),
        unsafe_allow_html=True)

    for site, cfg in C.SITES.items():
        url = C.form_url_for(site)
        sheet = C.sheet_url_for(site)
        note = C.FORM_NOTES.get(site, "")
        with theme.card(f"rr_link_{site}", f'{cfg["icon"]}  {cfg["label"]}', note):
            if not url and not sheet:
                st.markdown(theme.inline_note(
                    "No link for this site yet. Paste the URL into "
                    "<code>FORM_URLS</code> dan <code>SHEET_URLS</code> pada "
                    "<code>config.py</code>.", block=True), unsafe_allow_html=True)
                continue
            for label, tautan, kunci in (("Form", url, "form"),
                                         ("Spreadsheet", sheet, "sheet")):
                if not tautan:
                    continue
                kiri, kanan = st.columns([1, 0.16], gap="small")
                with kiri:
                    st.markdown(f'<div class="dh-linklabel">{label}</div>',
                                unsafe_allow_html=True)
                    st.code(tautan, language=None)
                with kanan, st.container(key=f"rr_open_{site}_{kunci}"):
                    st.markdown("<div style='height:26px'></div>",
                                unsafe_allow_html=True)
                    st.link_button("Buka", tautan, width="stretch")


def page_rec_room():
    """Monitoring di atas, link di bawah — embed Apps Script sudah dihapus.

    Alasannya bukan teknis: form Apps Script memang untuk MENGISI, dan mengisi
    lebih enak di tab sendiri yang lebar. Yang tidak bisa dilakukan form adalah
    MELIHAT — dan itu yang selama ini memaksa tim kembali ke spreadsheet mentah.
    Halaman ini mengambil alih bagian melihatnya.
    """
    df, sf, lt = data_or_stop()
    d = _panel_monitoring(df, sf, lt)
    _panel_talent_pool(df, d)
    _panel_link()


# ===========================================================================
# Halaman yang belum dibangun — jujur soal apa yang belum ada
# ===========================================================================
def page_todo(title: str, isi: list[str], fase: str):
    st.markdown(theme.section_heading(1, title, f"dijadwalkan {fase}"), unsafe_allow_html=True)
    with theme.card("todo", title, "not built yet"):
        st.markdown(theme.empty_state(
            "This page has no content yet",
            "Yang akan masuk ke sini:<br>• " + "<br>• ".join(theme.esc(i) for i in isi),
            emoji="🚧",
        ), unsafe_allow_html=True)


# ===========================================================================
# Router
# ===========================================================================
def main():
    role = auth.require_login()
    st.session_state.setdefault("page", "overview")

    # Peran User tidak boleh mendarat di halaman yang tidak diizinkan, termasuk
    # kalau nilainya tertinggal dari sesi sebelumnya.
    if not auth.can_view(st.session_state.page):
        st.session_state.page = "overview"

    titles = {
        "overview": ("Overview", "Pipeline summary and the Looker dashboard"),
        "weekly": ("Weekly Report", "Recruiter performance, new hires, site summary, in progress, resignations"),
        "tracking_candidate": ("Candidate Tracking", "One candidate at a time, stage by stage"),
        "tracking_position": ("Position Tracking",
                              "By position, or drill down by department"),
        "prf": ("PRF Tracking", "Position requests: approval, status and how they spread"),
        "division": ("Summary by Division",
                     "MPP vs. headcount vs. pipeline — drill down to the people"),
        "rec_room": ("Recruitment Room",
                     "Candidate monitoring, plus the form and spreadsheet link per site"),
    }
    title, subtitle = titles[st.session_state.page]
    shell(title, subtitle)
    navbar()
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    page = st.session_state.page
    if page == "overview":
        page_overview()
    elif page == "rec_room":
        page_rec_room()
    elif page == "weekly":
        page_weekly()
    elif page == "tracking_candidate":
        page_tracking_candidate()
    elif page == "tracking_position":
        page_tracking_position()
    elif page == "prf":
        page_prf()
    elif page == "division":
        page_division()


main()
