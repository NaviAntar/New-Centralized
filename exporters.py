"""
exporters.py — mengubah tabel yang tampil di layar menjadi berkas yang bisa
diunduh: Excel untuk diolah lagi, PNG untuk ditempel ke deck atau dikirim di
WhatsApp.

Modul ini murni pandas/matplotlib — tidak mengimpor streamlit — supaya bisa
dites dari skrip biasa, sama seperti metrics.py dan data_loader.py.

Yang diunduh adalah tabel yang SEDANG TAMPIL, sudah kena filter halaman. Kalau
yang diunduh selalu data mentah, orang mengirimkan berkas yang isinya berbeda
dari yang baru saja mereka lihat di layar, dan itu jenis kesalahan yang baru
ketahuan setelah berkasnya terlanjur beredar.
"""
from __future__ import annotations

import io
import re

import pandas as pd

import theme

# Warna diambil dari theme supaya PNG-nya satu bahasa dengan tampilan di layar.
# Tidak ada hex yang ditulis ulang di sini.
_NAVY = theme.BRAND["navy"]
_ORANGE = theme.BRAND["orange"]
_TEXT = theme.NEUTRAL["text"]
_MUTED = theme.NEUTRAL["text_muted"]
_BORDER = theme.NEUTRAL["border"]
_WASH = theme.NEUTRAL["wash"]
_CARD = theme.NEUTRAL["card"]

_TAG = re.compile(r"<[^>]+>")


def bersihkan(nilai) -> str:
    """Teks sel apa adanya, tanpa penanda HTML.

    Sel di layar boleh mengandung <span> untuk mewarnai Achievement atau
    menandai Staff/Non Staff. Penanda itu berguna di layar dan jadi sampah di
    Excel, jadi dibuang di sini — satu tempat, bukan di tiap halaman.
    """
    s = "" if nilai is None else str(nilai)
    s = _TAG.sub("", s)
    return (s.replace("&nbsp;", " ").replace("&amp;", "&")
             .replace("&lt;", "<").replace("&gt;", ">")
             .replace("&#39;", "'").replace("&quot;", '"').strip())


def frame_dari_baris(headers: list[str], rows: list[list],
                     total_row: list | None = None) -> pd.DataFrame:
    """Bangun DataFrame dari bahan yang sama dengan yang dikirim ke data_table().

    Dipakai supaya berkas unduhan dijamin sama dengan tabel di layar: satu
    sumber baris, dua cara menampilkannya. Kalau halaman menyusun ulang datanya
    sendiri untuk diunduh, cepat atau lambat keduanya berbeda.
    """
    isi = [[bersihkan(v) for v in r] for r in rows]
    if total_row:
        isi.append([bersihkan(v) for v in total_row])
    return pd.DataFrame(isi, columns=[bersihkan(h) for h in headers])


# Angka bergaya Indonesia: titik ribuan, koma desimal, boleh diakhiri persen.
# Polanya sengaja ketat dan harus cocok seluruh teks, supaya kode seperti
# "H15P1" atau nomor PRF "013/OFC/PRF/ACP/12/2025" tidak ikut dianggap angka.
_ANGKA_ID = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?%?$|^-?\d+(,\d+)?%?$")


def _angka(teks: str) -> tuple[float | None, bool]:
    """(nilai, apakah persen). (None, False) kalau teksnya memang bukan angka."""
    s = teks.strip()
    if not s or not _ANGKA_ID.match(s):
        return None, False
    # Nol di depan berarti ini kode, bukan angka — "013" harus tetap "013".
    utuh = s.lstrip("-").rstrip("%").split(",")[0]
    if len(utuh) > 1 and utuh.startswith("0"):
        return None, False

    persen = s.endswith("%")
    s = s.rstrip("%").replace(".", "").replace(",", ".")
    try:
        return float(s), persen
    except ValueError:
        return None, False


def _nama_sheet(nama: str) -> str:
    """Nama tab Excel: maksimal 31 karakter dan tanpa : \\ / ? * [ ]."""
    bersih = re.sub(r"[:\\/?*\[\]]", " ", nama).strip() or "Data"
    return bersih[:31]


def to_excel(df: pd.DataFrame, nama: str = "Data", catatan: str = "") -> bytes:
    """Berkas .xlsx dengan header bergaya portal dan lebar kolom yang masuk akal.

    Excel, bukan CSV: separator desimal di Excel Indonesia membuat CSV sering
    terbaca berantakan, dan berkas ini memang untuk dibuka di Excel.
    """
    import xlsxwriter

    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    ws = wb.add_worksheet(_nama_sheet(nama))
    awal = 2 if catatan else 0

    if catatan:
        ws.write(0, 0, catatan, wb.add_format(
            {"italic": True, "font_color": _MUTED, "font_size": 9}))

    gaya_header = wb.add_format({
        "bold": True, "font_color": "#FFFFFF", "bg_color": _NAVY,
        "border": 1, "border_color": _NAVY, "align": "left",
        "valign": "vcenter", "text_wrap": True,
    })
    gaya_angka = wb.add_format({"num_format": "#,##0.#"})
    gaya_persen = wb.add_format({"num_format": '#,##0.0"%"'})

    kolom = [str(c) for c in df.columns]
    for i, k in enumerate(kolom):
        ws.write(awal, i, k, gaya_header)
        isi = df[k].astype(str)
        # Lebar mengikuti isi terpanjang, dibatasi supaya satu kolom panjang
        # tidak mendorong kolom lain keluar layar.
        lebar = max(len(k), int(isi.str.len().max() or 0)) + 2
        ws.set_column(i, i, min(max(lebar, 10), 45))

    # Ditulis sel per sel, bukan lewat df.to_excel: angka yang di layar sudah
    # diformat gaya Indonesia ("1.150", "40,4", "166,2%") harus kembali jadi
    # ANGKA di Excel. Kalau dibiarkan sebagai teks, kolomnya tidak bisa
    # dijumlahkan atau diurutkan — padahal itu alasan orang mengunduh ke Excel.
    for j, baris in enumerate(df.astype(str).values.tolist()):
        for i, sel in enumerate(baris):
            angka, persen = _angka(sel)
            if angka is None:
                ws.write_string(awal + 1 + j, i, sel)
            else:
                ws.write_number(awal + 1 + j, i, angka,
                                gaya_persen if persen else gaya_angka)

    ws.freeze_panes(awal + 1, 0)
    ws.autofilter(awal, 0, awal + len(df), max(len(kolom) - 1, 0))
    wb.close()
    return buf.getvalue()


def to_png(df: pd.DataFrame, judul: str, subjudul: str = "",
           align: str | None = None, baris_total: bool = False) -> bytes:
    """Gambar tabel, digambar ulang dengan gaya yang sama dengan di layar.

    Bukan tangkapan layar: Streamlit tidak bisa memotret dirinya sendiri, jadi
    tabelnya digambar ulang. Untungnya hasilnya justru lebih rapi — tidak ada
    scrollbar, tidak terpotong, dan seluruh baris ikut walau di layar harus
    digulir.

    Seluruh baris digambar, tanpa batas. Tabel yang panjang menghasilkan gambar
    yang tinggi, dan itu memang konsekuensi yang jujur: memotongnya diam-diam
    lebih buruk daripada gambar yang besar.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    kolom = [str(c) for c in df.columns]
    data = df.astype(str).values.tolist()
    align = (align or "l" * len(kolom))
    align = (align + "l" * len(kolom))[:len(kolom)]

    # Lebar kolom proporsional terhadap isi terpanjang. Angka 7,4 px per karakter
    # adalah lebar rata-rata DejaVu Sans di 13 px — cukup akurat untuk tata letak,
    # dan jauh lebih murah daripada mengukur tiap string.
    PX_CHAR, PAD = 7.4, 26
    lebar = []
    for i, k in enumerate(kolom):
        terpanjang = max([len(k)] + [len(r[i]) for r in data]) if data else len(k)
        lebar.append(min(max(terpanjang * PX_CHAR + PAD, 90), 420))

    W = sum(lebar)
    TINGGI_BARIS, TINGGI_HEADER, TINGGI_JUDUL = 34, 40, 64
    H = TINGGI_JUDUL + TINGGI_HEADER + TINGGI_BARIS * len(data) + 18

    dpi = 160
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")
    fig.patch.set_facecolor(_CARD)

    def kotak(x, y, w, h, warna, tepi=None):
        ax.add_patch(Rectangle((x, y), w, h, facecolor=warna,
                               edgecolor=tepi or warna, linewidth=0.8))

    # Judul + strip oranye, meniru kepala kartu di layar.
    atas = H - TINGGI_JUDUL
    kotak(0, atas + 16, 4, 26, _ORANGE)
    ax.text(14, atas + 30, judul, fontsize=13, fontweight="bold",
            color=_TEXT, va="center")
    if subjudul:
        ax.text(W - 12, atas + 30, subjudul, fontsize=9, color=_MUTED,
                va="center", ha="right")

    def tulis(teks, i, x, y, warna, tebal=False, ukuran=9.5):
        if align[i] == "r":
            ax.text(x + lebar[i] - 12, y, teks, fontsize=ukuran, color=warna,
                    va="center", ha="right",
                    fontweight="bold" if tebal else "normal")
        else:
            ax.text(x + 12, y, teks, fontsize=ukuran, color=warna,
                    va="center", ha="left",
                    fontweight="bold" if tebal else "normal")

    # Header
    y = atas - TINGGI_HEADER
    kotak(0, y, W, TINGGI_HEADER, _NAVY)
    x = 0
    for i, k in enumerate(kolom):
        tulis(k.upper(), i, x, y + TINGGI_HEADER / 2, "#FFFFFF", tebal=True,
              ukuran=8.5)
        x += lebar[i]

    # Isi
    for j, baris in enumerate(data):
        y -= TINGGI_BARIS
        terakhir = baris_total and j == len(data) - 1
        latar = _NAVY if terakhir else (_CARD if j % 2 == 0 else _WASH)
        kotak(0, y, W, TINGGI_BARIS, latar, tepi=_BORDER)
        x = 0
        for i, sel in enumerate(baris):
            # Teks yang lebih panjang dari kolomnya dipotong dengan elipsis,
            # bukan ditumpuk ke kolom sebelah.
            muat = int((lebar[i] - PAD) / PX_CHAR)
            teks = sel if len(sel) <= muat else sel[:max(muat - 1, 1)] + "…"
            tulis(teks, i, x, y + TINGGI_BARIS / 2,
                  "#FFFFFF" if terakhir else _TEXT, tebal=terakhir)
            x += lebar[i]

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=_CARD)
    plt.close(fig)
    return buf.getvalue()


def nama_berkas(judul: str, ext: str) -> str:
    """Nama berkas yang aman dan bisa diurutkan: judul-tanggal.ext."""
    dasar = re.sub(r"[^A-Za-z0-9]+", "-", judul).strip("-").lower() or "tabel"
    return f"{dasar}-{pd.Timestamp.today():%Y%m%d}.{ext}"
