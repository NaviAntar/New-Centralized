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
    ("weekly", "Weekly Report"),
    ("tracking_candidate", "Tracking Kandidat"),
    ("tracking_position", "Tracking Posisi"),
    ("prf", "PRF Tracking"),
    ("rec_room", "Recruitment Room"),
]


# ===========================================================================
# Data — cache di lapisan ini, loader tetap bisa dipanggil tanpa Streamlit
# ===========================================================================
@st.cache_data(ttl=C.CACHE_TTL_SECONDS, show_spinner="Mengambil data kandidat…")
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


@st.cache_data(ttl=C.CACHE_TTL_SECONDS, show_spinner="Mengambil data MPP…")
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
    if not site_key or site_key == "Semua site":
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
        if st.button("Keluar", width="stretch", key="btn_logout"):
            auth.logout()
            st.rerun()


def data_or_stop():
    try:
        return get_data()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Data tidak bisa diambil.\n\n{exc}")
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
                              placeholder=s.get("placeholder", "Semua"))
    if jenis == "text":
        return st.text_input(s["label"], key=s["key"], help=s.get("help"),
                             placeholder=s.get("placeholder", ""))
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


@st.cache_data(show_spinner="Menyiapkan gambar…", max_entries=32)
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
            help="Isi tabel apa adanya, mengikuti filter yang sedang aktif")
    with k_png, st.container(key=f"unduh_{key}_png"):
        siap = f"siap_png_{key}"
        if len(rows) <= PNG_LANGSUNG_MAKS or st.session_state.get(siap):
            st.download_button(
                "Gambar", _png(judul, sub, beku_h, beku_r, beku_t, align),
                file_name=XP.nama_berkas(judul, "png"), mime="image/png",
                key=f"dl_{key}_png", width="stretch",
                help="PNG tabel ini — seluruh baris ikut, tanpa perlu digulir")
        elif st.button("Gambar", key=f"prep_{key}_png", width="stretch",
                       help=f"Tabel ini {len(rows)} baris. Klik sekali untuk "
                            "menyiapkan gambarnya."):
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
        {"label": "Site", "key": "ov_site", "options": ["Semua site"] + list(C.SITES)},
    ])

    if site != "Semua site":
        keys = set(_site_filter(df, site)["cand_key"])
        df, lt = df[df["cand_key"].isin(keys)], lt[lt["cand_key"].isin(keys)]

    if not len(df):
        st.markdown(theme.empty_state("Tidak ada kandidat", "Belum ada data untuk site ini."),
                    unsafe_allow_html=True)
        return

    h = M.headline(df, lt)

    st.markdown(theme.section_heading(1, "Ringkasan", "kondisi pipeline saat ini"),
                unsafe_allow_html=True)
    def persen(x):
        return f'{x / h["candidates"] * 100:.1f}% dari total' if h["candidates"] else "—"

    # Satu baris lima kartu. Talent pool tidak ikut di sini — daftarnya hidup di
    # Recruitment Room, tempat orang benar-benar menindaklanjutinya, dan kartu
    # keenam di sini hanya membuat barisnya pecah jadi dua tanpa menambah
    # keputusan apa pun.
    k = st.columns(5, gap="small")
    with k[0]:
        st.markdown(theme.kpi_card("Total kandidat", n(h["candidates"]),
                                   f'{n(h["open"])} masih berjalan', emoji="👥",
                                   accent=theme.BRAND["navy"], value_size=28),
                    unsafe_allow_html=True)
    with k[1]:
        st.markdown(theme.kpi_card(
            "Close — Onboarding", n(h["hired"]), persen(h["hired"]), emoji="✅",
            accent=theme.STATUS["good"], value_size=28), unsafe_allow_html=True)
    with k[2]:
        st.markdown(theme.kpi_card(
            "Talent pool", n(h["talent_pool"]), "lolos, belum ditempatkan",
            emoji="🗂️", accent=theme.BRAND["orange"], value_size=28),
            unsafe_allow_html=True)
    with k[3]:
        med = n(h["median_lt"]) if h["median_lt"] else "—"
        st.markdown(theme.kpi_card("Median time-to-hire", med,
                                   f'hari kerja · P90 {n(h["p90_lt"])}',
                                   emoji="⏱️", value_size=28), unsafe_allow_html=True)
    with k[4]:
        st.markdown(theme.kpi_card("Gagal", n(h["failed"]), persen(h["failed"]),
                                   emoji="✕", accent=theme.STATUS["bad"], value_size=28),
                    unsafe_allow_html=True)

    st.markdown(theme.inline_note(
        "<b>Close</b> punya dua arti dan sengaja dipisah: <b>Close — Onboarding</b> "
        "berarti orangnya masuk kerja, <b>Talent pool</b> berarti orangnya lolos "
        "seleksi tapi disimpan untuk kebutuhan berikutnya. Daftar lengkap talent "
        "pool beserta nomor HP-nya ada di <b>Recruitment Room</b>.",
        block=True), unsafe_allow_html=True)

    st.markdown(theme.section_heading(2, "Dashboard Looker", "Recruitment Dashboard"),
                unsafe_allow_html=True)
    with theme.card("ov_looker", "Looker Studio", "visualisasi lengkap"):
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
        st.markdown(theme.empty_state("Belum ada kandidat", "—"), unsafe_allow_html=True)
        return

    with st.container(key="filterbar_tc"):
        label = st.selectbox(
            "Cari kandidat — ketik namanya",
            list(pilihan), key="tc_pick", filter_mode="contains",
            help="Ketik namanya; saran yang muncul sudah menyebut posisi dan "
                 "site, jadi dua orang bernama mirip langsung terbedakan.")
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
            "Nama ini muncul lebih dari sekali — biasanya karena melamar lebih dari satu "
            f'posisi. Yang ditampilkan: <b>{theme.esc(row.get("position_name"))}</b>.',
            warn=True, block=True), unsafe_allow_html=True)

    st.markdown(theme.info_grid([
        ("Posisi", theme.esc(row.get("position_name")), theme.esc(row.get("position_id"))),
        ("Departemen", theme.esc(row.get("departement")), theme.esc(row.get("divisi"))),
        ("Level", theme.esc(row["level"]), f'budget {C.total_budget(row["level"])} hari kerja'),
        ("Lokasi", theme.esc(row.get("loc")), ""),
        ("Sumber CV", theme.esc(row.get("source_cv")), ""),
        ("Tahap terakhir", theme.esc(row.get("last_progress")), ""),
    ]), unsafe_allow_html=True)

    berlaku = stages[stages["applicable"]]
    selesai = int(berlaku["end"].notna().sum())
    st.markdown(theme.progress_bar(selesai, len(berlaku), failed=(hstat == "FAILED")),
                unsafe_allow_html=True)

    m = st.columns(3, gap="small")
    telat = int(ltrow["stages_late"])
    kartu = [
        ("SLA", n(ltrow["lt_elapsed"]), "hari kerja berjalan", "⏱️", theme.BRAND["orange"]),
        ("Budget SLA", n(ltrow["budget_total"]), f'target level {theme.esc(row["level"])}',
         "🎯", theme.BRAND["navy"]),
        ("Tahap terlambat", n(telat), f'dari {selesai} tahap selesai', "⚠️",
         theme.STATUS["bad"] if telat else theme.STATUS["good"]),
    ]
    for col, (lab, val, sub, emo, warna) in zip(m, kartu):
        with col:
            st.markdown(theme.kpi_card(lab, val, sub, emoji=emo, accent=warna, value_size=24),
                        unsafe_allow_html=True)

    with theme.card("tc_stages", "Tahap seleksi",
                    "lead time dalam hari kerja, dibandingkan budget level ini"):
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
            "tc_stages", f'Tahap seleksi — {row["candidate_id"]}',
            f'{row.get("position_name") or "—"} · {row.get("loc") or "—"}',
            ["Tahap", "Status", "Mulai", "Selesai", "LT", "Budget", "SLA"],
            [[r["name"],
              {"done": "Selesai", "active": "Berjalan", "idle": "Belum mulai",
               "failed": "Gagal", "na": "Tidak berlaku"}[r["status"]],
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
        ("berjalan", r["ongoing"], theme.STATUS["warn"]),
        ("onboarding", r["hired"], theme.STATUS["good"]),
        ("talent pool", r["pool"], theme.BRAND["orange"]),
        ("gagal", r["gagal"], theme.STATUS["bad"]),
    ]
    sisa = r["kandidat"] - sum(v for _l, v, _c in utama)
    if sisa > 0:
        utama.append(("hold / lainnya", sisa, theme.NEUTRAL["text_soft"]))
    return utama


def _kartu_ringkas(r: dict):
    """Lima kartu KPI dengan definisi yang sama di mana pun dipakai."""
    isi = [
        ("Kandidat", r["kandidat"], "👥", theme.BRAND["navy"]),
        ("Masih berjalan", r["ongoing"], "⏳", theme.STATUS["warn"]),
        ("Onboarding", r["hired"], "✅", theme.STATUS["good"]),
        ("Talent pool", r["pool"], "🗂️", theme.BRAND["orange"]),
        ("Gagal", r["gagal"], "✕", theme.STATUS["bad"]),
    ]
    for col, (lab, val, emo, warna) in zip(st.columns(len(isi), gap="small"), isi):
        with col:
            st.markdown(theme.kpi_card(lab, n(val), "", emoji=emo, accent=warna,
                                       value_size=24), unsafe_allow_html=True)


def _filter_posisi(df, sf):
    """Satu panel filter untuk kedua mode: bulan (screening CV) dan site."""
    bulan_ada = M.month_options(df, sf)
    bulan_p, site_p = filterbar("tp_f", [
        {"label": "Bulan (tanggal Screening CV)", "key": "tp_bulan", "kind": "multi",
         "options": bulan_ada, "default": [], "width": 2,
         "placeholder": "Semua bulan — pilih beberapa untuk mempersempit"},
        {"label": "Site", "key": "tp_site_f", "kind": "multi",
         "options": list(C.SITES), "default": [], "placeholder": "Semua site"},
    ])
    d = M.filter_month(df, sf, bulan_p)
    if site_p:
        d = d[d["loc"].isin(C.loc_values_for(site_p))]
    label = " · ".join(x for x in [", ".join(bulan_p), ", ".join(site_p)] if x)
    return d, (label or "semua bulan · semua site")


def _mode_posisi(df, sf, lt):
    """Cari satu posisi, lihat detail prosesnya."""
    d, label = _filter_posisi(df, sf)
    if d.empty:
        st.markdown(theme.empty_state("Tidak ada kandidat", "Longgarkan filternya."),
                    unsafe_allow_html=True)
        return

    pilihan = M.position_options(d)
    with st.container(key="filterbar_tp_cari"):
        judul = st.selectbox(
            "Cari posisi — ketik nama posisinya", list(pilihan), key="tp_pick",
            filter_mode="contains",
            help="Saran yang muncul sudah menyebut site dan departemen.")
    posisi, loc = pilihan[judul]

    kand = M.position_candidates(d, lt, posisi, loc)
    if kand.empty:
        st.markdown(theme.empty_state("Tidak ada kandidat", "—"), unsafe_allow_html=True)
        return

    sub = d[(d["position_name"] == posisi) & (d["loc"] == loc)]
    ring = M._ringkas(sub)
    baris0 = kand.iloc[0]

    st.markdown(theme.section_heading(
        1, theme.esc(posisi),
        f'{theme.esc(loc)} · {theme.esc(baris0.get("departement"))} · {label}',
        tag=theme.esc(baris0.get("position_id"))), unsafe_allow_html=True)
    _kartu_ringkas(ring)

    with theme.card("tp_kand", "Kandidat posisi ini", f"{len(kand)} orang · {label}"):
        st.markdown(theme.split_bar(_segmen(ring), ring["kandidat"]),
                    unsafe_allow_html=True)
        jalan = M.last_progress_breakdown(sub)
        if jalan:
            st.markdown('<div class="dh-secnote">Yang masih berjalan, berhenti di:</div>'
                        + theme.chip_row(jalan), unsafe_allow_html=True)
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        tabel("tp_kand", f"Kandidat {posisi}", f"{loc or '—'} · {label}",
              ["Kandidat", "Level", "Site", "Last progress", "Total LT", "Status"],
              [[theme.esc(r.candidate_id), theme.esc(r.level), theme.esc(r.loc),
                theme.esc(r.last_progress),
                n(r.total_lt) if pd.notna(r.total_lt) else "—",
                theme.result_pill(r.status1)]
               for r in kand.itertuples()], align="llllrl")


def _mode_departemen(df, sf, lt):
    """Pilih departemen, lalu buka posisinya satu per satu."""
    d, label = _filter_posisi(df, sf)
    if d.empty:
        st.markdown(theme.empty_state("Tidak ada kandidat", "Longgarkan filternya."),
                    unsafe_allow_html=True)
        return

    dep_ring = M.department_summary(d)
    daftar = dep_ring["departement"].tolist()
    if not daftar:
        st.markdown(theme.empty_state("Belum ada departemen", "—"),
                    unsafe_allow_html=True)
        return

    with st.container(key="filterbar_tp_dep"):
        dep = st.selectbox(
            "Pilih departemen", daftar, key="tp_dep_pick", filter_mode="contains",
            format_func=lambda x: x,
            help="Diurutkan dari yang paling banyak kandidatnya masih berjalan.")

    sub = d[d["departement"] == dep]
    ring = M._ringkas(sub)
    pos = M.position_summary(d, dep)

    st.markdown(theme.section_heading(
        1, theme.esc(dep), f'{len(pos)} posisi · {label}'), unsafe_allow_html=True)
    _kartu_ringkas(ring)

    with theme.card("tp_depbar", "Sebaran departemen ini", label):
        st.markdown(theme.split_bar(_segmen(ring), ring["kandidat"]),
                    unsafe_allow_html=True)
        jalan = M.last_progress_breakdown(sub)
        if jalan:
            st.markdown('<div class="dh-secnote">Yang masih berjalan, berhenti di:</div>'
                        + theme.chip_row(jalan), unsafe_allow_html=True)

    # Yang ditampilkan lebih dulu hanya posisi yang MASIH ADA ORANGNYA jalan —
    # itu arti "posisi yang dibuka". Plant & Maintenance punya 79 posisi tercatat
    # dan hanya 35 yang masih berjalan; menampilkan 79 kotak sekaligus membuat
    # yang penting tenggelam, dan halamannya berat.
    jalan_saja = pos[pos["ongoing"] > 0]
    semua = st.toggle(
        f"Tampilkan juga posisi yang sudah selesai ({len(pos) - len(jalan_saja)})",
        key="tp_dep_semua", value=False,
        help="Posisi yang sudah tidak punya kandidat berjalan — sudah terisi, "
             "gagal semua, atau prosesnya berhenti.")
    tampil = pos if semua else jalan_saja

    st.markdown(theme.section_heading(
        2, "Posisi yang dibuka",
        f"{len(tampil)} posisi · klik satu untuk melihat kandidatnya"),
        unsafe_allow_html=True)

    if tampil.empty:
        st.markdown(theme.empty_state(
            "Tidak ada posisi yang masih berjalan",
            "Nyalakan tombol di atas untuk melihat posisi yang sudah selesai."),
            unsafe_allow_html=True)
        return

    for i, r in enumerate(tampil.itertuples()):
        judul = (f"{r.position_name}  ·  {r.loc}  ·  {r.kandidat} kandidat, "
                 f"{r.ongoing} masih berjalan")
        with st.expander(judul, expanded=(i == 0 and len(pos) <= 3)):
            r_ring = {"kandidat": r.kandidat, "ongoing": r.ongoing, "hired": r.hired,
                      "pool": r.pool, "gagal": r.gagal}
            st.markdown(theme.stat_inline([
                ("Level", str(r.level)),
                ("Kandidat", n(r.kandidat)),
                ("Berjalan", n(r.ongoing)),
                ("Onboarding", n(r.hired)),
                ("Gagal", n(r.gagal)),
            ]), unsafe_allow_html=True)
            st.markdown(theme.split_bar(_segmen(r_ring), r.kandidat),
                        unsafe_allow_html=True)

            posisi_sub = sub[(sub["position_name"] == r.position_name)
                             & (sub["loc"] == r.loc)]
            pecah = M.last_progress_breakdown(posisi_sub)
            if pecah:
                st.markdown(
                    '<div class="dh-secnote">Yang masih berjalan, berhenti di:</div>'
                    + theme.chip_row(pecah), unsafe_allow_html=True)

            jalan = M.ongoing_candidates(sub, lt, dep, position_name=r.position_name)
            jalan = jalan[jalan["loc"] == r.loc]
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            if jalan.empty:
                st.markdown(theme.inline_note(
                    "Tidak ada kandidat yang prosesnya masih berjalan di posisi ini.",
                    block=True), unsafe_allow_html=True)
            else:
                tabel(f"tpd_{i}", f"Sedang diproses — {r.position_name}",
                      f"{r.loc} · {label}",
                      ["Kandidat", "Level", "Tahap terakhir", "SLA"],
                      [[theme.esc(x.candidate_id), theme.esc(x.level),
                        theme.esc(x.last_progress),
                        n(x.lt_elapsed) if pd.notna(x.lt_elapsed) else "—"]
                       for x in jalan.itertuples()], align="lllr")


MODE_POSISI = {
    "Per Posisi": _mode_posisi,
    "Per Departemen": _mode_departemen,
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
            "Mode", list(MODE_POSISI), default="Per Posisi", key="tp_mode",
            label_visibility="collapsed")
    MODE_POSISI[mode or "Per Posisi"](df, sf, lt)


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
        {"label": "Tahun", "key": "wk_year", "kind": "multi",
         "options": [str(y) for y in tahun_ada], "default": thn_default, "width": 1,
         "placeholder": "Pilih tahun"},
        {"label": "Bulan", "key": "wk_month", "kind": "multi",
         "options": list(M.BULAN_NAMA.values()), "default": [], "width": 2,
         "placeholder": "Semua bulan — pilih beberapa untuk membandingkan"},
        {"label": "Site", "key": "wk_site", "kind": "multi",
         "options": list(C.SITES), "default": [], "width": 1,
         "placeholder": "Semua site"},
    ])

    periods = periode_terpilih(tahun_pilih, bulan_pilih)
    if tahun_pilih and not bulan_pilih:
        # Tidak memilih bulan berarti seluruh bulan pada tahun yang dipilih.
        periods = [(int(t), b) for t in tahun_pilih for b in range(1, 13)]

    if periods:
        dari = min(pd.Timestamp(t, b, 1) for t, b in periods)
        sampai = max(pd.Timestamp(t, b, 1) + pd.offsets.MonthEnd(1) for t, b in periods)
        label_periode = f"{dari.date()} s/d {sampai.date()}"
    else:
        dari = sampai = None
        label_periode = "sepanjang waktu"
    label_site = ", ".join(site_pilih) if site_pilih else "semua site"

    # ── Performance ────────────────────────────────────────────────────────
    st.markdown(theme.section_heading(
        1, "Performance recruiter",
        "rata-rata tiap tahap dijumlahkan, seluruh tahap proses ikut dihitung"),
        unsafe_allow_html=True)

    perf = M.recruiter_performance(sf, dari, sampai, sites=site_pilih)
    with theme.card("wk_perf", "Performance",
                    f"periode screening CV · {label_periode} · {label_site}"):
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
        tabel("wk_perf", "Performance recruiter",
              f"{label_periode} · {label_site}",
              ["Nama", "SLA Actual", "SLA Budget", "Achievement", "Kandidat",
               "Onboarding"], baris, align="lrrrrr", max_rows=None)
        st.markdown(theme.inline_note(
            "Tiap tahap dirata-ratakan dulu di antara kandidat yang orang itu tangani, lalu "
            "rata-rata antar tahap dijumlahkan — <b>seluruh tahap proses ikut</b>, termasuk "
            "One Month Notice yang budget-nya 30 hari. Karena itu SLA Budget di sini sejalan "
            "dengan target 60+ hari di matriks Backend. <b>Achievement</b> = Budget ÷ Actual; "
            "di atas 100% berarti lebih cepat dari target. <b>Kandidat</b> dan <b>Onboarding</b> "
            "dihitung dari PIC Screening CV saja, jadi satu kandidat hanya masuk ke satu nama "
            "dan kolomnya boleh dijumlahkan ke bawah.",
            block=True), unsafe_allow_html=True)

    # ── New Hire ───────────────────────────────────────────────────────────
    st.markdown(theme.section_heading(2, "New Hire", "onboarding per departemen"),
                unsafe_allow_html=True)
    with theme.card("wk_nh", "New Hire", f"{label_periode} · {label_site}"):
        nh = M.new_hire_matrix(df, periods, sites=site_pilih)
        if nh.empty:
            st.markdown(theme.empty_state(
                "Belum ada onboarding di periode ini",
                "Ubah pilihan tahun, bulan, atau site di filter atas."), unsafe_allow_html=True)
        else:
            kolom = list(nh.columns)
            isi = [[theme.esc(r[0])] + [n(v) for v in r[1:]] for r in nh.values.tolist()]
            tabel("wk_nh", "New Hire", f"{label_periode} · {label_site}",
                  kolom, isi[:-1], total_row=isi[-1],
                  align="l" + "r" * (len(kolom) - 1))

    # ── Ringkasan per site ─────────────────────────────────────────────────
    st.markdown(theme.section_heading(3, "Ringkasan per site", "onboarding per site"),
                unsafe_allow_html=True)
    with theme.card("wk_sum", "Summary", f"{label_periode} · {label_site}"):
        sm = M.summary_matrix(df, periods, sites=site_pilih)
        if sm.empty:
            st.markdown(theme.empty_state(
                "Belum ada onboarding di periode ini",
                "Ubah pilihan tahun, bulan, atau site di filter atas."), unsafe_allow_html=True)
        else:
            kolom = list(sm.columns)
            isi = [[theme.esc(r[0])] + [n(v) for v in r[1:]] for r in sm.values.tolist()]
            tabel("wk_sum", "Ringkasan per site", f"{label_periode} · {label_site}",
                  kolom, isi[:-1], total_row=isi[-1],
                  align="l" + "r" * (len(kolom) - 1))

    # ── On Progress ────────────────────────────────────────────────────────
    st.markdown(theme.section_heading(
        4, "On Progress", "mengikuti rumus sheet ONP, mengikuti filter di atas"),
        unsafe_allow_html=True)
    panels = M.on_progress(df, periods=periods, sites=site_pilih)
    cols = st.columns(3, gap="small")
    for col, (nama, sel) in zip(cols, panels.items()):
        with col, theme.card(f"wk_onp_{nama}", nama, f"{len(sel)} kandidat"):
            if sel.empty:
                st.markdown(theme.empty_state("Kosong", "Tidak ada di tahap ini.", emoji="—"),
                            unsafe_allow_html=True)
            else:
                tabel(f"wk_onp_{nama}", f"On Progress {nama}",
                      f"{label_periode} · {label_site}",
                      ["Kandidat", "Posisi", "Site", "Tanggal"],
                      [[theme.esc(r.candidate_id), theme.esc(r.position_name),
                        theme.esc(r.loc),
                        theme.esc(r.tanggal.date() if pd.notna(r.tanggal) else None)]
                       for r in sel.itertuples()], align="llll")

    # ── Karyawan resign ────────────────────────────────────────────────────
    st.markdown(theme.section_heading(
        5, "Karyawan resign", "tanggal resign dan site mengikuti filter di atas"),
        unsafe_allow_html=True)
    with theme.card("wk_resign", "Resign",
                    f"{label_periode} · {label_site} · level di bawah 11"):
        mpp = get_mpp()
        if mpp is None:
            st.markdown(theme.empty_state(
                "Data MPP belum bisa diambil",
                "Sheet <b>Update MPP</b> di spreadsheet Report belum terbaca. Pastikan "
                "spreadsheet-nya di-share 'Anyone with the link — Viewer'.", emoji="🔌"),
                unsafe_allow_html=True)
        else:
            res = M.resign(mpp, periods=periods, sites=site_pilih)
            if res.empty:
                st.markdown(theme.empty_state("Tidak ada yang resign di periode ini", "—"),
                            unsafe_allow_html=True)
            else:
                tabel("wk_resign", "Karyawan resign",
                      f"{label_periode} · {label_site}",
                      ["Karyawan", "Posisi", "Site", "Tanggal resign",
                       "Akhir kontrak", "Level"],
                      [[theme.esc(r[1]), theme.esc(r[2]), theme.esc(r[3]),
                        theme.esc(r[4].date() if pd.notna(r[4]) else None),
                        theme.esc(r[5].date() if pd.notna(r[5]) else None),
                        n(r[6])] for r in res.itertuples()], align="lllllr")


# ===========================================================================
# ⑤ PRF TRACKING
# ===========================================================================
@st.cache_data(ttl=C.CACHE_TTL_SECONDS, show_spinner="Mengambil data PRF…")
def get_prf():
    return M.prepare_prf(DL.load_prf())


def page_prf():
    try:
        prf = get_prf()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Data PRF tidak bisa diambil.\n\n{exc}")
        st.stop()

    # Pilihan filter diambil dari data untuk site/level/divisi, tapi Tracking dan
    # Status memakai daftar tetap di config: CLOSE dan CANCEL belum pernah ada
    # satu baris pun, dan filter yang menyusut sendiri terbaca seperti fitur yang
    # hilang, bukan seperti keadaan yang memang belum terjadi.
    site_opt = sorted(prf["site"].unique())
    level_opt = sorted(prf["level"].unique())

    site_p, level_p, jenis_p, track_p, status_p = filterbar("prf", [
        {"label": "Site", "key": "prf_site", "kind": "multi",
         "options": site_opt, "default": [], "placeholder": "Semua site"},
        {"label": "Level", "key": "prf_level", "kind": "multi",
         "options": level_opt, "default": [], "placeholder": "Semua level"},
        {"label": "Jenis Level", "key": "prf_jenis", "kind": "multi",
         "options": ["Staff", "Non Staff"], "default": [],
         "placeholder": "Staff & Non Staff"},
        {"label": "Tracking PRF", "key": "prf_track", "kind": "multi",
         "options": C.PRF_TRACKING_VALUES, "default": [], "placeholder": "Semua"},
        {"label": "Status PRF", "key": "prf_status", "kind": "multi",
         "options": C.PRF_STATUS_VALUES, "default": [], "placeholder": "Semua"},
    ])

    d = M.filter_prf(prf, sites=site_p, levels=level_p, level_types=jenis_p,
                     trackings=track_p, statuses=status_p)
    s = M.prf_summary(d)

    dipilih = [", ".join(x) for x in (site_p, level_p, jenis_p, track_p, status_p) if x]
    label_filter = " · ".join(dipilih) if dipilih else "semua PRF"

    # ── Kartu ──────────────────────────────────────────────────────────────
    st.markdown(theme.section_heading(1, "Ringkasan PRF", label_filter),
                unsafe_allow_html=True)
    k = st.columns(4, gap="small")
    with k[0]:
        st.markdown(theme.kpi_card(
            "Jumlah PRF", n(s["total"]), f'{n(s["qty"])} orang diminta',
            emoji="📄", accent=theme.BRAND["navy"], value_size=28),
            unsafe_allow_html=True)
    with k[1]:
        st.markdown(theme.kpi_card(
            "Approved", n(s["approved"]), f'{n(s["approved_pct"], 1)}% dari total PRF',
            emoji="✅", accent=theme.STATUS["good"], value_size=28),
            unsafe_allow_html=True)
    with k[2]:
        st.markdown(theme.kpi_card(
            "Not Approved", n(s["not_approved"]),
            f'{n(s["not_approved_pct"], 1)}% dari total PRF',
            emoji="⏳", accent=theme.STATUS["warn"], value_size=28),
            unsafe_allow_html=True)
    with k[3]:
        st.markdown(theme.kpi_card(
            "Status Close", n(s["close"]), f'{n(s["close_pct"], 1)}% dari total PRF',
            emoji="🔒", accent=theme.BRAND["orange"], value_size=28),
            unsafe_allow_html=True)

    st.markdown(theme.inline_note(
        "<b>Approved</b> dan <b>Not Approved</b> dibaca dari kolom Tracking PRF — "
        "pengajuannya sudah disetujui atau masih berjalan. <b>Status Close</b> dibaca "
        "dari kolom Status dan persentasenya dihitung terhadap <b>total PRF</b>, bukan "
        "terhadap yang approved saja. Semua angka menghitung <b>baris PRF</b>, bukan qty "
        "orang — satu PRF bisa meminta beberapa orang sekaligus, dan qty-nya tetap "
        "terlihat di tiap baris tabel.",
        block=True), unsafe_allow_html=True)

    # ── Tabel ──────────────────────────────────────────────────────────────
    st.markdown(theme.section_heading(2, "Daftar PRF", "satu baris satu pengajuan"),
                unsafe_allow_html=True)
    with theme.card("prf_tabel", "PRF", f"{n(len(d))} baris · {label_filter}"):
        if d.empty:
            st.markdown(theme.empty_state(
                "Tidak ada PRF", "Tidak ada baris yang cocok dengan filter di atas."),
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
               "Divisi", "Level", "Tracking PRF", "Status PRF"],
              baris, align="llrllllll")
        st.markdown(theme.inline_note(
            "Kolom <b>Request Number</b> memakai ID PRF kalau nomor requestnya belum "
            "terbit — satu kolom identitas, bukan dua kolom yang separuhnya kosong.",
            block=True), unsafe_allow_html=True)


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
        [{"label": "Bulan (tanggal Screening CV)", "key": "rr_bulan_f", "kind": "multi",
          "options": bulan_ada, "default": [], "width": 2,
          "placeholder": "Semua bulan"},
         {"label": "Site", "key": "rr_site_f", "kind": "multi",
          "options": list(C.SITES), "default": [], "placeholder": "Semua site"},
         {"label": "PIC (Screening CV)", "key": "rr_pic_f", "kind": "multi",
          "options": pic_ada, "default": [], "placeholder": "Semua PIC"}],
        [{"label": "Departemen", "key": "rr_dep_f", "kind": "multi",
          "options": dep_ada, "default": [], "placeholder": "Semua departemen",
          "width": 2},
         {"label": "Status", "key": "rr_status_f", "kind": "multi",
          "options": status_ada, "default": [], "placeholder": "Semua status"},
         {"label": "Level", "key": "rr_level_f", "kind": "multi",
          "options": lvl_ada, "default": [], "placeholder": "Semua level"},
         {"label": "Jenis level", "key": "rr_jenis_f", "kind": "multi",
          "options": ["Staff", "Non Staff"], "default": [],
          "placeholder": "Staff & Non Staff"}],
        [{"label": "Tambah kolom tahap", "key": "rr_tahap_f", "kind": "multi",
          "options": TAHAP_MONITORING, "default": [],
          "placeholder": "Kolom inti saja — pilih tahap untuk menambah LT dan SLA-nya",
          "help": "Tiap tahap menambah dua kolom: lead time dan hasil SLA-nya. "
                  "Kolom variance dan LT contribution sengaja tidak dibawa — "
                  "keduanya turunan dari angka yang sudah tampil."}],
    ])

    d = M.filter_monitoring(
        M.monitoring_table(M.filter_month(df, sf, bulan_p), sf, lt, stages=tahap_p),
        sites=site_p, pics=pic_p, departemen=dep_p, statuses=status_p,
        levels=lvl_p, level_types=jenis_p)

    dipilih = [", ".join(x) for x in
               (bulan_p, site_p, pic_p, dep_p, status_p, lvl_p, jenis_p) if x]
    label = " · ".join(dipilih) if dipilih else "semua kandidat"

    st.markdown(theme.section_heading(
        1, "Monitoring kandidat", label), unsafe_allow_html=True)

    if len(d):
        _kartu_ringkas(M._ringkas(d))

    with theme.card("rr_mon", "Monitoring", f"{n(len(d))} kandidat · {label}"):
        if d.empty:
            st.markdown(theme.empty_state(
                "Tidak ada kandidat", "Tidak ada baris yang cocok dengan filter di atas."),
                unsafe_allow_html=True)
            return d

        inti = ["Kandidat", "Posisi", "Site", "Departemen", "Level", "PIC",
                "Tahap terakhir", "Status", "SLA"]
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

        tabel("rr_mon", "Monitoring kandidat", label, headers, baris, align=align)
        st.markdown(theme.inline_note(
            "Tiap tahap yang ditambahkan lewat filter membawa <b>LT</b> dan <b>SLA</b> "
            "saja. <b>PIC</b> diambil dari PIC Screening CV — dasar yang sama dengan "
            "tabel Performance, jadi angkanya bisa dibandingkan langsung.",
            block=True), unsafe_allow_html=True)
    return d


def _panel_talent_pool(df, d):
    """Talent pool, mengikuti filter monitoring di atasnya.

    Ditaruh di sini, bukan di Overview: di Overview orang cuma melihat angkanya,
    di sini orang benar-benar menindaklanjutinya — dan nomor HP-nya jadi berguna
    justru saat filter site/PIC sudah dipersempit.
    """
    kunci = set(d[d["talent_pool"]]["cand_key"])
    tp = M.talent_pool(df)
    tp = tp[tp["cand_key"].isin(kunci)]

    st.markdown(theme.section_heading(
        2, "Talent pool", "lolos seleksi, belum ditempatkan"), unsafe_allow_html=True)
    with theme.card("rr_tp", "Talent pool", f"{len(tp)} orang · mengikuti filter di atas"):
        if tp.empty:
            st.markdown(theme.empty_state(
                "Tidak ada yang masuk talent pool",
                "Kandidat masuk daftar ini begitu salah satu tahapnya diberi hasil "
                "<b>TALENT POOL</b> di form. Longgarkan filter di atas kalau "
                "daftarnya kosong padahal seharusnya ada."), unsafe_allow_html=True)
            return
        tabel("rr_tp", "Talent pool", f"{len(tp)} orang",
              ["Kandidat", "No HP", "Posisi dilamar", "Departemen", "Site",
               "Level", "Masuk pool di tahap"],
              [[theme.esc(r.candidate_id), theme.esc(r.phone or "—"),
                theme.esc(r.position_name), theme.esc(r.departement),
                theme.esc(r.loc), theme.esc(r.level), theme.esc(r.stage)]
               for r in tp.itertuples()], align="lllllll")
        st.markdown(theme.inline_note(
            "Site, level, dan tahap ikut ditampilkan karena itu yang menentukan siapa "
            "yang menghubungi, posisi apa yang pantas ditawarkan, dan berapa banyak "
            "seleksi yang tidak perlu diulang. Nomor HP diambil dari sheet Backend "
            "Monitoring — fix_centralized tidak punya kolomnya.",
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
                    "Belum ada link untuk site ini. Tempel URL-nya di "
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
    with theme.card("todo", title, "belum dibangun"):
        st.markdown(theme.empty_state(
            "Halaman ini belum ada isinya",
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
        "overview": ("Overview", "Ringkasan pipeline dan dashboard Looker"),
        "weekly": ("Weekly Report", "Performance recruiter, New Hire, ringkasan site, On Progress, resign"),
        "tracking_candidate": ("Tracking Kandidat", "Proses seleksi per kandidat, tahap demi tahap"),
        "tracking_position": ("Tracking Posisi",
                              "Per posisi, atau telusuri per departemen"),
        "prf": ("PRF Tracking", "Pengajuan posisi: approval, status, dan sebarannya"),
        "rec_room": ("Recruitment Room",
                     "Monitoring kandidat, plus link form & spreadsheet per site"),
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


main()
