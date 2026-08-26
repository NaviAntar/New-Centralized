"""
metrics.py — satu-satunya tempat angka rekrutmen dihitung.

Setiap halaman memanggil modul ini; tidak ada halaman yang boleh menghitung
lead time atau status SLA sendiri. Itu yang membuat versi lama menampilkan dua
angka berbeda untuk orang yang sama (`tot_lt` di halaman posisi vs `total_lt`
di halaman kandidat — temuan T-05).

Modul ini murni pandas: tidak mengimpor streamlit, jadi bisa dites dari skrip
biasa. Cache ada di lapisan aplikasi.

--- Cara lead time dihitung ---------------------------------------------------
Durasi diukur dalam HARI KERJA dan bersifat inklusif: mulai dan selesai di hari
kerja yang sama = 1 hari. Sabtu, Minggu, dan libur nasional tidak dihitung.

Ini bukan definisi baru — rumusnya dicocokkan ulang terhadap kolom LT yang
sudah ada di spreadsheet dan cocok 100% di sebelas tahap. Portal memakai
konvensi yang sama supaya angkanya bisa langsung dicocokkan dengan angka yang
biasa dilihat tim.

Modul menyediakan DUA ukuran yang sengaja dipisah:

  lt_stage_sum  jumlah durasi tahap. Ini definisi yang dipakai tim untuk
                menilai kinerja PIC — orang hanya bertanggung jawab atas tahap
                yang ia pegang.

  lt_elapsed    selisih tanggal ujung ke ujung. Ini yang dirasakan user dan
                manajemen, dan selalu lebih besar karena mencakup waktu tunggu
                ANTAR tahap.

Selisih keduanya (`lt_idle`) adalah waktu proses menganggur. Versi lama hanya
punya angka pertama dan menyebutnya "total lead time", sehingga keterlambatan
nyata tidak pernah terlihat (temuan T-01).
"""
from __future__ import annotations

import pandas as pd

import config as C
from theme import MAIN_FUNNEL, STAGE_ORDER

# ---------------------------------------------------------------------------
# Peta kolom: satu tahap -> kolom-kolom yang mewakilinya di fix_centralized.
# Ini SATU-SATUNYA tempat nama kolom database disebut. Kalau spreadsheet
# berubah, cukup ubah di sini.
# ---------------------------------------------------------------------------
# Pasangan tanggal di bawah BUKAN tebakan. Tiap pasangan diuji terhadap kolom
# LT yang sudah ada di spreadsheet memakai rumus hari kerja + kalender libur,
# dan hanya pasangan yang cocok 100% yang dipakai. Dua di antaranya berbeda dari
# dugaan awal:
#   MCU              -> berakhir di mcu_issue_date, bukan mcu_date
#   One Month Notice -> date_fit sampai date_onboarding (inilah masa notice
#                       30 hari; versi lama salah melabelinya "Onboarding")
STAGE_COLUMNS = {
    #                    start                    end                        lt sheet        sla sheet  result
    "PRF Approval":     ("start_prf_routing",     "complete_prf_routing",    "lt_prf",         "sla1",  None),
    "Screening CV":     ("start_screening_cv",    "complete_screening_cv",   "lt_screening",   "sla2",  "result_screening_cv"),
    "Interview HR":     ("start_interview_hr",    "complete_interview_hr",   "lt_hr_interview", "sla3", "result_interview_hr"),
    "Interview User":   ("start_interview_user",  "complete_interview_user", "lt_user_interview", "sla4", "result_interview_user"),
    "Technical Test":   ("start_technical_test",  "complete_technical_test", "lt_tech_test",   "sla11", "result_technical_test"),
    "Psychotest":       ("start_psychotest",      "complete_psychotest",     "lt_psikotest",   "sla5",  "result_psychotest"),
    "Offering":         ("start_offering",        "complete_offering",       "lt_offering",    "sla6",  "result_offering"),
    "MCU":              ("start_mcu",             "mcu_issue_date",          "lt_mcu",         "sla7",  None),
    "Review MCU":       ("start_review_mcu",      "review_mcu",              "lt_review_mcu",  "sla8",  None),
    "FU MCU":           ("start_fu_mcu",          "complete_fu_mcu",         "lt_fu_mcu",      "sla9",  "result_fu_mcu"),
    "One Month Notice": ("date_fit",              "date_onboarding",         "lt_omn",         "sla10", None),
    "Onboarding":       ("date_onboarding",       "date_onboarding",         None,             None,    None),
}

# Tanggal paling awal dan paling akhir dari seluruh proses, dipakai menghitung
# lt_elapsed. PRF sengaja TIDAK jadi titik awal: kolomnya hanya terisi di 422
# dari 1.396 baris, jadi memakainya akan membuat mayoritas kandidat kosong.
ELAPSED_START = "start_screening_cv"
ELAPSED_END = "date_onboarding"

_ID_COLS = ["candidate_id", "position_id", "position_name", "departement",
            "divisi", "level", "loc", "status1", "last_progress", "source_cv"]


# ===========================================================================
# Normalisasi
# ===========================================================================
def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Bersihkan frame mentah fix_centralized jadi tabel kandidat yang layak pakai.

    Yang dikerjakan:
      - buang baris kosong (sheet punya ~560 baris tanpa kandidat sama sekali)
      - normalisasi nama kolom & nilai teks
      - parse semua kolom tanggal
      - bangun kunci unik `cand_key` dan tandai duplikat (temuan T-03)
    """
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    if "candidate_id" not in df.columns:
        raise ValueError(
            "Kolom 'candidate_id' tidak ada. Kemungkinan besar yang terambil "
            "bukan tab fix_centralized — periksa gid/nama tab di config.py."
        )

    df = df[df["candidate_id"].notna() & (df["candidate_id"].astype(str).str.strip() != "")]
    df = df.reset_index(drop=True)

    for col in _ID_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace({"nan": None, "": None})

    if "loc" in df.columns:
        df["loc"] = df["loc"].str.upper()
    if "status1" in df.columns:
        df["status1"] = df["status1"].str.upper()

    tanggal = {c for s, (a, b, *_r) in STAGE_COLUMNS.items() for c in (a, b)}
    # Dipakai panel On Progress tapi tidak masuk peta tahap, jadi harus
    # disebut terpisah — kalau tidak, perbandingan tanggalnya diam-diam gagal.
    tanggal |= {"ol_sent_to_candidate", "mcu_issue_date", "date_fit", "sent_mcu_to_doctor"}
    for col in tanggal:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Kunci unik. Nama saja tidak cukup: 31 nama muncul dua kali karena orang
    # yang sama melamar lebih dari satu posisi. Versi lama memakai nama sebagai
    # kunci lalu mengambil baris pertama, jadi 31 orang melihat proses yang
    # bukan miliknya.
    pos = df["position_id"].fillna("—") if "position_id" in df.columns else "—"
    df["cand_key"] = df["candidate_id"].astype(str) + " · " + pos.astype(str)
    df["is_duplicate_name"] = df["candidate_id"].duplicated(keep=False)

    # Kalau kunci gabungan pun masih kembar, bedakan dengan nomor urut supaya
    # tidak ada dua baris yang tidak bisa dipilih terpisah di dropdown.
    dup_key = df["cand_key"].duplicated(keep=False)
    if dup_key.any():
        seq = df.groupby("cand_key").cumcount() + 1
        df.loc[dup_key, "cand_key"] = (
            df.loc[dup_key, "cand_key"] + " #" + seq[dup_key].astype(str)
        )

    df["level"] = df.get("level").fillna(C.LEVEL_FALLBACK) if "level" in df.columns else C.LEVEL_FALLBACK
    return df


_HOLIDAYS: "np.ndarray | None" = None


def set_holidays(dates) -> None:
    """Pasang kalender libur (dari sheet Backend). Panggil sekali saat startup."""
    global _HOLIDAYS
    import numpy as np
    parsed = pd.to_datetime(pd.Series(list(dates)), errors="coerce").dropna()
    _HOLIDAYS = parsed.dt.normalize().values.astype("datetime64[D]")


def _holidays():
    global _HOLIDAYS
    if _HOLIDAYS is None:
        set_holidays(C.HOLIDAYS_FALLBACK)
    return _HOLIDAYS


def working_days(start: pd.Series, end: pd.Series) -> pd.Series:
    """Durasi dalam HARI KERJA, inklusif — mulai & selesai di hari sama = 1.

    Sabtu, Minggu, dan libur nasional tidak dihitung. Rumus ini diverifikasi
    terhadap kolom LT yang sudah ada di spreadsheet: cocok 100% di sebelas
    tahap. Jadi angka portal bisa dicocokkan langsung dengan angka yang biasa
    dilihat tim — bukan definisi baru yang bersaing.

    Tanggal terbalik (selesai mendahului mulai) menghasilkan nilai negatif dan
    sengaja TIDAK dipaksa jadi nol, supaya kesalahan input tetap terlihat.
    """
    import numpy as np
    out = pd.Series(np.nan, index=start.index, dtype="float64")
    mask = start.notna() & end.notna()
    if not mask.any():
        return out
    s = start[mask].dt.normalize().values.astype("datetime64[D]")
    e = (end[mask].dt.normalize() + pd.Timedelta(days=1)).values.astype("datetime64[D]")
    fwd = e >= s
    days = np.empty(len(s), dtype="float64")
    days[fwd] = np.busday_count(s[fwd], e[fwd], holidays=_holidays())
    # Untuk tanggal terbalik, hitung mundur lalu beri tanda negatif.
    if (~fwd).any():
        back = np.busday_count(
            (end[mask][~fwd].dt.normalize()).values.astype("datetime64[D]"),
            (start[mask][~fwd].dt.normalize() + pd.Timedelta(days=1)).values.astype("datetime64[D]"),
            holidays=_holidays(),
        )
        days[~fwd] = -back
    out[mask] = days
    return out


# ===========================================================================
# Tabel panjang: 1 baris per kandidat per tahap
# ===========================================================================
def stage_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Ubah tabel wide jadi long — bentuk yang dipakai hampir semua metrik.

    Kolom hasil: cand_key, candidate_id, position_name, departement, level, loc,
    status1, stage, stage_no, start, end, lt (inklusif, dihitung dari tanggal),
    lt_sheet, budget, applicable, sla, pic_initial, pic_name, result.
    """
    rows = []
    for stage in STAGE_ORDER:
        s_col, e_col, lt_col, sla_col, res_col = STAGE_COLUMNS[stage]
        if s_col not in df.columns:
            continue

        start = df[s_col]
        end = df[e_col] if e_col in df.columns else pd.Series(pd.NaT, index=df.index)

        block = pd.DataFrame({
            "cand_key": df["cand_key"],
            "candidate_id": df["candidate_id"],
            "position_id": df.get("position_id"),
            "position_name": df.get("position_name"),
            "departement": df.get("departement"),
            "level": df["level"],
            "loc": df.get("loc"),
            "status1": df.get("status1"),
            "stage": stage,
            "stage_no": STAGE_ORDER.index(stage) + 1,
            "start": start,
            "end": end,
            "screening_date": df.get(ELAPSED_START),
        })

        block["lt"] = working_days(start, end)
        block["lt_sheet"] = (pd.to_numeric(df[lt_col], errors="coerce")
                             if lt_col and lt_col in df.columns else pd.NA)
        block["budget"] = df["level"].map(lambda lv, st=stage: C.stage_budget(lv, st))
        block["applicable"] = block["budget"].notna()
        block["result"] = (df[res_col].astype(str).str.strip().str.upper()
                           if res_col and res_col in df.columns else None)

        pic_col = C.STAGE_PIC_COLUMN.get(stage)
        if pic_col and pic_col in df.columns:
            block["pic_initial"] = df[pic_col].astype(str).str.strip().str.upper().replace({"NAN": None, "": None})
        else:
            block["pic_initial"] = None

        rows.append(block)

    out = pd.concat(rows, ignore_index=True)
    out["sla"] = _sla_state(out)
    out["over_days"] = (out["lt"] - out["budget"]).where(out["lt"].notna() & out["budget"].notna())
    return out


def _sla_state(sf: pd.DataFrame) -> pd.Series:
    """Status SLA dihitung ulang dari tanggal + budget resmi per level.

    Sengaja TIDAK memakai kolom sla1..sla11 dari sheet: kolom itu dibandingkan
    terhadap budget yang salah (temuan T-01b), jadi hampir semuanya "Ontime".
    """
    state = pd.Series("", index=sf.index, dtype="object")
    has_budget = sf["budget"].notna()
    done = sf["lt"].notna() & has_budget
    state[done & (sf["lt"] <= sf["budget"])] = "Ontime"
    state[done & (sf["lt"] > sf["budget"])] = "Late"
    running = sf["start"].notna() & sf["end"].isna() & has_budget
    state[running] = "Running"
    return state


# ===========================================================================
# Lead time per kandidat
# ===========================================================================
def lead_time(df: pd.DataFrame, sf: pd.DataFrame | None = None) -> pd.DataFrame:
    """Tiga ukuran lead time per kandidat + status terhadap budget resmi."""
    sf = stage_frame(df) if sf is None else sf

    stage_sum = sf.groupby("cand_key")["lt"].sum(min_count=1)
    stages_done = sf[sf["end"].notna()].groupby("cand_key").size()
    stages_late = sf[sf["sla"] == "Late"].groupby("cand_key").size()

    out = pd.DataFrame({"cand_key": df["cand_key"]}).set_index("cand_key")
    out["level"] = df.set_index("cand_key")["level"]
    out["status1"] = df.set_index("cand_key")["status1"]
    out["lt_stage_sum"] = stage_sum
    idx = df.set_index("cand_key")
    out["lt_elapsed"] = (working_days(idx[ELAPSED_START], idx[ELAPSED_END])
                         if ELAPSED_END in df.columns else pd.NA)
    out["lt_idle"] = out["lt_elapsed"] - out["lt_stage_sum"]
    out["budget_total"] = out["level"].map(C.total_budget)
    out["stages_done"] = stages_done.reindex(out.index).fillna(0).astype(int)
    out["stages_late"] = stages_late.reindex(out.index).fillna(0).astype(int)

    over = out["lt_elapsed"] > out["budget_total"]
    out["lt_status"] = pd.Series("", index=out.index, dtype="object")
    out.loc[out["lt_elapsed"].notna() & ~over, "lt_status"] = "Onbudget"
    out.loc[out["lt_elapsed"].notna() & over, "lt_status"] = "Overbudget"

    # Tanggal terbalik. Ada 13 baris seperti ini di data (terendah -113 hari);
    # ditandai supaya bisa ditampilkan sebagai daftar perbaikan, bukan diam-diam
    # ikut merusak rata-rata.
    out["date_error"] = (out["lt_elapsed"] < 0) | (sf.groupby("cand_key")["lt"].min() < 0)
    return out.reset_index()


# ===========================================================================
# Ringkasan untuk Overview
# ===========================================================================
def sla_summary(sf: pd.DataFrame) -> pd.DataFrame:
    """Tingkat keterlambatan per tahap, diurutkan dari yang paling parah."""
    done = sf[sf["sla"].isin(["Ontime", "Late"])]
    g = done.groupby("stage").agg(
        n=("sla", "size"),
        late=("sla", lambda s: (s == "Late").sum()),
        median_lt=("lt", "median"),
        budget=("budget", "median"),
    )
    g["late_pct"] = (g["late"] / g["n"] * 100).round(1)
    g["stage_no"] = [STAGE_ORDER.index(s) + 1 for s in g.index]
    return g.reset_index().sort_values("late_pct", ascending=False)


def funnel(sf: pd.DataFrame) -> pd.DataFrame:
    """Jumlah kandidat yang menyentuh tiap tahap, mengikuti urutan proses.

    Hanya menghitung tahap yang BERLAKU untuk kandidat itu, sehingga konversi
    tidak lagi melompat di atas 100% seperti pada versi lama (Technical Test
    hanya untuk Non Staff, tapi dulu ikut jadi pembagi untuk semua orang).
    """
    touched = sf[sf["applicable"] & sf["start"].notna()]
    if touched.empty:
        return pd.DataFrame(columns=["stage", "stage_no", "n", "conv_pct",
                                     "of_base_pct", "drop"])

    # Dihitung sebagai "kandidat yang MINIMAL sampai tahap ini", memakai tahap
    # terjauh yang pernah ia sentuh. Menghitung sentuhan mentah per tahap tidak
    # bisa dipakai: banyak kandidat melewati Psikotes dan sebagian besar tidak
    # punya tanggal PRF, sehingga angkanya naik-turun dan konversi melompat di
    # atas 100% — persis yang terjadi di versi lama.
    #
    # PRF Approval dikeluarkan dari funnel: itu persetujuan permintaan, bukan
    # tahap seleksi kandidat, dan kolomnya cuma terisi di 422 dari 1.396 baris.
    furthest = touched.groupby("cand_key")["stage_no"].max()
    rows = []
    base = None
    prev = None
    for stage in MAIN_FUNNEL:
        i = STAGE_ORDER.index(stage) + 1
        n = int((furthest >= i).sum())
        if base is None:
            base = n
        rows.append({
            "stage": stage,
            "stage_no": i,
            "n": n,
            "conv_pct": round(n / prev * 100, 1) if prev else None,
            "of_base_pct": round(n / base * 100, 1) if base else None,
            "drop": (prev - n) if prev is not None else None,
        })
        prev = n
    return pd.DataFrame(rows)


def failure_by_stage(df: pd.DataFrame) -> pd.DataFrame:
    """Di tahap mana kandidat gugur."""
    failed = df[df["status1"] == "FAILED"]
    g = failed["last_progress"].value_counts().rename_axis("stage").reset_index(name="n")
    total = g["n"].sum()
    g["pct"] = (g["n"] / total * 100).round(1) if total else 0
    return g


def source_effectiveness(df: pd.DataFrame) -> pd.DataFrame:
    """Hire rate per sumber CV."""
    if "source_cv" not in df.columns:
        return pd.DataFrame(columns=["source_cv", "n", "hired", "rate"])
    g = df.assign(_h=df["status1"] == "CLOSE").groupby("source_cv").agg(
        n=("cand_key", "size"), hired=("_h", "sum"))
    g["rate"] = (g["hired"] / g["n"] * 100).round(1)
    return g.reset_index().sort_values("rate", ascending=False)


# ===========================================================================
# Performance recruiter — tabel di halaman Weekly Report
# ===========================================================================
def recruiter_name(initial: str, extra_map: dict | None = None) -> str | None:
    """Inisial di database -> nama lengkap. None kalau tidak ada di roster."""
    if not initial:
        return None
    mapping = dict(C.RECRUITER_NAMES)
    if extra_map:
        mapping.update({k.strip().upper(): v for k, v in extra_map.items() if k and v})
    return mapping.get(str(initial).strip().upper())


def recruiter_owned(sf: pd.DataFrame, extra_map: dict | None = None) -> pd.DataFrame:
    """Peta kandidat -> recruiter yang menanganinya.

    Seseorang dianggap menangani sebuah kandidat kalau namanya muncul sebagai PIC
    di tahap mana pun. Satu kandidat bisa dimiliki lebih dari satu orang; itu
    disengaja, karena proses rekrutmen memang dikerjakan bergantian.
    """
    pic = sf[sf["pic_initial"].notna()][["cand_key", "pic_initial", "loc", "screening_date"]].copy()
    pic["name"] = pic["pic_initial"].map(lambda i: recruiter_name(i, extra_map))
    pic["name"] = pic["name"].fillna(C.OTHER_RECRUITER_LABEL)
    return pic.drop_duplicates(["cand_key", "name"])


def recruiter_performance(sf: pd.DataFrame, date_from=None, date_to=None,
                          extra_map: dict | None = None, sites=None) -> pd.DataFrame:
    """Tabel performance per recruiter.

    Cara hitungnya, sesuai arahan Navi:

      1. Kumpulkan kandidat yang ditangani orang itu.
      2. Untuk SETIAP tahap proses — dari PRF Approval sampai Onboarding —
         hitung rata-rata lead time dan rata-rata budget di antara kandidat tadi.
      3. Jumlahkan rata-rata itu lintas tahap. Tidak dibagi lagi.

    Yang penting di langkah 2: SELURUH tahap ikut, bukan hanya tahap yang punya
    kolom PIC di database. Versi sebelumnya hanya menghitung tujuh tahap ber-PIC,
    sehingga One Month Notice yang budget-nya saja 30 hari ikut terbuang dan
    total budget keluar cuma ~20 hari — jelas tidak masuk akal untuk proses yang
    targetnya 60+ hari. Sekarang budget totalnya sejalan dengan matriks SLA di
    Monitoring 2026 > Backend.

    Filter tanggal merujuk ke TANGGAL SCREENING CV kandidat, jadi satu kandidat
    selalu utuh dalam satu periode.

    PENTING: kolom Onboarding tidak bisa dijumlahkan ke bawah — satu kandidat
    dikreditkan ke semua PIC yang menanganinya (keputusan Navi).
    """
    milik = recruiter_owned(sf, extra_map)

    if date_from is not None:
        milik = milik[milik["screening_date"] >= pd.Timestamp(date_from)]
    if date_to is not None:
        milik = milik[milik["screening_date"] <= pd.Timestamp(date_to)]
    if sites:
        milik = milik[milik["loc"].isin(C.loc_values_for(sites))]

    kolom = ["name", "sla_actual", "sla_budget", "stages", "candidates",
             "onboarding", "achievement"]
    if milik.empty:
        g = pd.DataFrame(columns=kolom[1:], index=pd.Index([], name="name"))
    else:
        # Seluruh tahap kandidat yang ditangani orang itu — bukan hanya tahap
        # yang ia pegang sendiri.
        semua = sf.merge(milik[["cand_key", "name"]], on="cand_key", how="inner")
        terpakai = semua[semua["applicable"] & semua["budget"].notna()]

        per_stage = terpakai.groupby(["name", "stage"]).agg(
            lt=("lt", "mean"),
            budget=("budget", "mean"),
        ).reset_index()

        g = per_stage.groupby("name").agg(
            sla_actual=("lt", "sum"),
            sla_budget=("budget", "sum"),
            stages=("stage", "nunique"),
        )
        g["candidates"] = milik.groupby("name")["cand_key"].nunique()
        hire = semua[semua["status1"] == "CLOSE"]
        g["onboarding"] = hire.groupby("name")["cand_key"].nunique()
        g["achievement"] = (g["sla_budget"] / g["sla_actual"] * 100).where(g["sla_actual"] > 0)

    # Roster selalu tampil lengkap, termasuk orang yang belum punya data —
    # baris nol lebih jujur daripada nama yang hilang begitu saja.
    g = g.reindex(g.index.union(C.RECRUITER_ROSTER, sort=False))
    for c in ("candidates", "stages", "onboarding"):
        g[c] = g[c].fillna(0).astype(int)

    order = {n: i for i, n in enumerate(C.RECRUITER_ROSTER)}
    g["_sort"] = [order.get(n, 90 if n == C.OTHER_RECRUITER_LABEL else 50) for n in g.index]
    g = g.sort_values(["_sort"]).drop(columns="_sort")

    return g.reset_index().rename(columns={"index": "name"}).round(
        {"sla_actual": 1, "sla_budget": 1, "achievement": 1})[kolom]


def unmapped_initials(sf: pd.DataFrame, extra_map: dict | None = None) -> pd.DataFrame:
    """Inisial yang belum punya nama lengkap, diurutkan dari yang tersibuk.

    Dipakai panel "Kelola recruiter" supaya Navi bisa langsung melihat inisial
    mana yang paling berdampak kalau dipetakan.
    """
    work = sf[sf["pic_initial"].notna()]
    known = work["pic_initial"].map(lambda i: recruiter_name(i, extra_map)).notna()
    g = work[~known].groupby("pic_initial").agg(
        aktivitas=("stage", "size"),
        kandidat=("cand_key", "nunique"),
        onboarding=("status1", lambda s: (s == "CLOSE").sum()),
    )
    return g.sort_values("aktivitas", ascending=False).reset_index()


def hire_trend(df: pd.DataFrame, lt: pd.DataFrame, exclude_levels=("Non Staff",)) -> pd.DataFrame:
    """Median time-to-hire per bulan onboarding.

    Non Staff dikecualikan secara default: 163 dari 164 hire Non Staff punya
    tanggal screening, interview, dan onboarding yang persis sama (input borongan
    di KCP), jadi lead time-nya nol dan akan menarik median ke bawah secara palsu.
    """
    onboard = df.set_index("cand_key")[ELAPSED_END]
    j = lt.set_index("cand_key").join(onboard.rename("onboard_date"))
    j = j[(j["status1"] == "CLOSE") & j["lt_elapsed"].notna() & (j["lt_elapsed"] > 0)]
    if exclude_levels:
        j = j[~j["level"].isin(exclude_levels)]
    if j.empty:
        return pd.DataFrame(columns=["period", "n", "median_lt"])

    j["period"] = j["onboard_date"].dt.to_period("M")
    g = j.groupby("period").agg(n=("lt_elapsed", "size"), median_lt=("lt_elapsed", "median"))
    return g.reset_index().sort_values("period")


def headline(df: pd.DataFrame, lt: pd.DataFrame) -> dict:
    """Angka-angka untuk baris KPI di Overview."""
    staff = lt[(lt["status1"] == "CLOSE") & (lt["level"] != "Non Staff")
               & lt["lt_elapsed"].notna() & (lt["lt_elapsed"] > 0)]
    scored = staff[staff["lt_status"].isin(["Onbudget", "Overbudget"])]
    counts = df["status1"].value_counts()
    return {
        "candidates": len(df),
        "hired": int(counts.get("CLOSE", 0)),
        "open": int(counts.get("OPEN", 0)),
        "failed": int(counts.get("FAILED", 0)),
        "median_lt": float(staff["lt_elapsed"].median()) if len(staff) else None,
        "p90_lt": float(staff["lt_elapsed"].quantile(0.9)) if len(staff) else None,
        "lt_n": len(staff),
        "over_pct": (float((scored["lt_status"] == "Overbudget").mean() * 100)
                     if len(scored) else None),
        "over_n": int((scored["lt_status"] == "Overbudget").sum()),
        "scored_n": len(scored),
        "date_errors": int(lt["date_error"].sum()),
        "dup_names": int(df["is_duplicate_name"].sum()),
    }


# ===========================================================================
# Weekly Report
# ===========================================================================
BULAN_NAMA = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
              7: "Jul", 8: "Agu", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des"}


BULAN_NAMA_BALIK = {v: k for k, v in BULAN_NAMA.items()}


def periode_label(tahun: int, bulan: int, banyak_tahun: bool = False) -> str:
    """Label kolom untuk satu periode. Tahun ikut ditulis kalau lebih dari satu."""
    return f"{BULAN_NAMA[bulan]} {str(tahun)[-2:]}" if banyak_tahun else BULAN_NAMA[bulan]


def _periode_kolom(periods: list[tuple[int, int]]) -> list[tuple[tuple[int, int], str]]:
    banyak = len({t for t, _ in periods}) > 1
    return [(p, periode_label(p[0], p[1], banyak)) for p in sorted(periods)]


def new_hire_matrix(df: pd.DataFrame, periods: list[tuple[int, int]],
                    sites=None) -> pd.DataFrame:
    """Onboarding per departemen untuk periode yang dipilih.

    `periods` = daftar (tahun, bulan). Tiap periode jadi satu kolom, ditutup
    kolom Total. Baris terakhir adalah total per kolom.

    Berbeda dengan sheet aslinya, angka Total di sini SELALU sama dengan jumlah
    isinya karena dihitung, bukan diketik (temuan T-06).
    """
    if not periods:
        return pd.DataFrame()

    h = df[(df["status1"] == "CLOSE") & df["date_onboarding"].notna()].copy()
    if sites:
        h = h[h["loc"].isin(C.loc_values_for(sites))]
    if h.empty:
        return pd.DataFrame()

    h["_dept"] = h["departement"].fillna("(tanpa departemen)")
    kolom = _periode_kolom(periods)

    hasil = {}
    for (thn, bln), label in kolom:
        sel = h[(h["date_onboarding"].dt.year == thn) & (h["date_onboarding"].dt.month == bln)]
        hasil[label] = sel.groupby("_dept").size()

    tabel = pd.DataFrame(hasil).fillna(0).astype(int)
    if tabel.empty:
        return pd.DataFrame()
    tabel["Total"] = tabel.sum(axis=1)
    tabel = tabel[tabel["Total"] > 0].sort_values("Total", ascending=False)
    tabel.loc["TOTAL"] = tabel.sum()
    return tabel.reset_index().rename(columns={"_dept": "Departemen", "index": "Departemen"})


def summary_matrix(df: pd.DataFrame, periods: list[tuple[int, int]],
                   sites=None) -> pd.DataFrame:
    """Onboarding per SITE untuk periode yang dipilih — bentuknya sama dengan New Hire.

    Periodenya memakai tanggal onboarding, jadi angkanya bisa disandingkan
    langsung dengan tabel New Hire di atasnya.
    """
    if not periods:
        return pd.DataFrame()

    h = df[(df["status1"] == "CLOSE") & df["date_onboarding"].notna()].copy()
    if sites:
        h = h[h["loc"].isin(C.loc_values_for(sites))]
    if h.empty:
        return pd.DataFrame()

    h["_site"] = h["loc"].fillna("(tanpa site)")
    kolom = _periode_kolom(periods)

    hasil = {}
    for (thn, bln), label in kolom:
        sel = h[(h["date_onboarding"].dt.year == thn) & (h["date_onboarding"].dt.month == bln)]
        hasil[label] = sel.groupby("_site").size()

    tabel = pd.DataFrame(hasil).fillna(0).astype(int)
    if tabel.empty:
        return pd.DataFrame()
    tabel["Total"] = tabel.sum(axis=1)
    tabel = tabel[tabel["Total"] > 0].sort_values("Total", ascending=False)
    tabel.loc["TOTAL"] = tabel.sum()
    return tabel.reset_index().rename(columns={"_site": "Site", "index": "Site"})


# ===========================================================================
# Tracking Posisi
# ===========================================================================
def candidate_options(df: pd.DataFrame) -> dict[str, str]:
    """Label pencarian -> cand_key, untuk selectbox Tracking Kandidat.

    Labelnya memuat nama, posisi, departemen, dan site sekaligus. Karena
    st.selectbox mencocokkan ketikan ke seluruh isi label, mengetik "tika",
    "supervisor", atau "BCP" sama-sama menyaring daftarnya.
    """
    d = df.sort_values("candidate_id")
    label = (d["candidate_id"].astype(str) + "  ·  "
             + d["position_name"].fillna("(tanpa posisi)").astype(str) + "  ·  "
             + d["departement"].fillna("—").astype(str) + "  ·  "
             + d["loc"].fillna("—").astype(str))
    return dict(zip(label, d["cand_key"]))


def position_options(df: pd.DataFrame) -> dict[str, tuple[str, str]]:
    """Label pencarian -> (nama posisi, site), untuk selectbox Tracking Posisi.

    Satu posisi bisa ada di beberapa site, jadi site ikut jadi bagian kunci —
    bukan navigasi terpisah. Mengetik "supervisor" langsung memunculkan semua
    Supervisor beserta site masing-masing dalam satu daftar.
    """
    d = df[df["position_name"].notna()].copy()
    if d.empty:
        return {}
    g = (d.groupby(["position_name", "loc"])
           .agg(departement=("departement", "first"), kandidat=("cand_key", "nunique"))
           .reset_index()
           .sort_values(["position_name", "loc"]))
    label = (g["position_name"].astype(str) + "  ·  " + g["loc"].fillna("—").astype(str)
             + "  ·  " + g["departement"].fillna("—").astype(str)
             + "  ·  " + g["kandidat"].astype(str) + " kandidat")
    return dict(zip(label, zip(g["position_name"], g["loc"])))


def position_candidates(df: pd.DataFrame, lt: pd.DataFrame, position_name: str,
                        loc: str | None = None) -> pd.DataFrame:
    """Kandidat untuk satu posisi di satu site, lengkap dengan total lead time.

    Kolomnya sengaja dibatasi pada yang dipakai saat menilai pemenuhan posisi:
    nama, posisi, departemen, level, lokasi, tahap terakhir, total LT, status.
    """
    d = df[df["position_name"] == position_name]
    if loc:
        d = d[d["loc"] == loc]
    if d.empty:
        return pd.DataFrame(columns=["candidate_id", "position_name", "position_id",
                                     "departement", "level", "loc", "last_progress",
                                     "total_lt", "status1"])

    # Sheet sumber sudah punya kolom bernama total_lt, tapi isinya jumlah durasi
    # tahap — bukan lead time end-to-end (temuan T-01). Kolom itu dibuang lebih
    # dulu supaya tidak ada dua kolom bernama sama dengan arti berbeda.
    d = d.drop(columns=[c for c in ("total_lt", "tot_lt") if c in d.columns])
    d = d.merge(lt[["cand_key", "lt_elapsed"]], on="cand_key", how="left")
    d = d.rename(columns={"lt_elapsed": "total_lt"})
    kol = ["candidate_id", "position_name", "position_id", "departement", "level",
           "loc", "last_progress", "total_lt", "status1"]
    kol = [c for c in kol if c in d.columns]
    urut = {"OPEN": 0, "CLOSE": 1, "FAILED": 2}
    d["_u"] = d["status1"].map(urut).fillna(3)
    return d.sort_values(["_u", "candidate_id"])[kol]




# ===========================================================================
# On Progress & Karyawan resign — replikasi rumus sheet Report
# ===========================================================================
# Ketiga panel ONP dan panel resign MEREPLIKASI rumus QUERY milik tim, bukan
# tafsiran sendiri. Rumus aslinya membaca sheet "Backend Monitoring"; kolom yang
# dipakai dipetakan ke fix_centralized seperti ini:
#
#   Backend Monitoring        fix_centralized
#   K  STATUS                 status1
#   M  LAST PROGRESS          last_progress
#   BG START REQ OFFERING     start_offering
#   BH OL SENT TO CANDIDATE   ol_sent_to_candidate
#   CL RESULT MCU             result_fu_mcu
#   CN DATE OF ONBOARDING     date_onboarding
#
# Backend Monitoring memakai satu label "Offering", sementara fix_centralized
# memecahnya jadi "Req Offering" dan "Offering Negotiation" — keduanya diterima.
ONP_OFFERING_PROGRESS = {"OFFERING", "REQ OFFERING", "OFFERING NEGOTIATION"}
ONP_MCU_PROGRESS = {"MCU", "REVIEW MCU", "FU MCU"}


def _month_bounds(ref=None):
    """Awal bulan berjalan dan awal bulan berikutnya — persis EOMONTH di rumus."""
    ref = pd.Timestamp(ref) if ref is not None else pd.Timestamp.today()
    awal = ref.normalize().replace(day=1)
    return awal, awal + pd.offsets.MonthBegin(1)


def _periode_mask(seri: pd.Series, periods) -> pd.Series:
    """True untuk baris yang tanggalnya jatuh di salah satu (tahun, bulan) terpilih."""
    if not periods:
        return pd.Series(True, index=seri.index)
    ok = pd.Series(False, index=seri.index)
    for thn, bln in periods:
        ok |= (seri.dt.year == thn) & (seri.dt.month == bln)
    return ok & seri.notna()


def on_progress(df: pd.DataFrame, periods=None, sites=None) -> dict[str, pd.DataFrame]:
    """Tiga panel On Progress, mengikuti rumus sheet ONP.

    Offering    status OPEN, tahap Offering, START REQ OFFERING di periode terpilih
    MCU         status OPEN, tahap MCU/Review MCU/FU MCU, OL SENT di periode terpilih
    Onboarding  hasil MCU FIT TO WORK, tanggal onboarding di periode terpilih

    Rumus aslinya mematok bulan berjalan lewat EOMONTH(TODAY()). Di portal, "bulan
    berjalan" itu diganti periode yang dipilih di filter; kalau filternya kosong,
    hasilnya sama persis dengan rumus aslinya.
    """
    d = df
    if sites:
        d = d[d["loc"].isin(C.loc_values_for(sites))]

    prog = d["last_progress"].astype(str).str.strip().str.upper()
    buka = d["status1"] == "OPEN"
    kol = ["candidate_id", "position_name", "departement", "loc", "last_progress", "level"]

    def _ambil(mask, tgl_col):
        sel = d[mask].copy()
        sel["tanggal"] = sel[tgl_col]
        return sel[kol + ["tanggal"]].sort_values(["loc", "candidate_id"])

    offering = _ambil(
        buka & prog.isin(ONP_OFFERING_PROGRESS)
        & _periode_mask(d["start_offering"], periods), "start_offering")

    mcu = _ambil(
        buka & prog.isin(ONP_MCU_PROGRESS)
        & _periode_mask(d["ol_sent_to_candidate"], periods), "ol_sent_to_candidate")

    fit = d["result_fu_mcu"].astype(str).str.strip().str.upper() == "FIT TO WORK"
    if periods:
        onboard = _ambil(fit & _periode_mask(d["date_onboarding"], periods), "date_onboarding")
    else:
        # Tanpa filter, ikuti rumus aslinya: yang akan datang, bukan riwayat.
        hari_ini = pd.Timestamp.today().normalize()
        onboard = _ambil(fit & (d["date_onboarding"] > hari_ini), "date_onboarding")

    return {"Offering": offering, "MCU": mcu, "Onboarding": onboard}


def resign(mpp: pd.DataFrame, periods=None, sites=None) -> pd.DataFrame:
    """Karyawan resign — replikasi rumus sheet "Karyawan Resign".

    Rumus aslinya menggabungkan dua QUERY atas sheet "Update MPP":
      End Date terisi · Level < 11 · Position Name bukan 'Internship'
      · End Date di bulan berjalan
      · DAN (End Date < Contract End Date  ATAU  Contract End Date kosong)

    Di portal "bulan berjalan" diganti periode yang dipilih di filter, dan filter
    site memakai peta nama lokasi panjang (ACP = Asam-Asam Coal Project). Tanpa
    filter, hasilnya sama persis dengan rumus aslinya.

    Diverifikasi: 18 dari 18 nama cocok dengan sheet untuk Agustus 2026.
    """
    kosong = pd.DataFrame(columns=["Karyawan", "Position Name", "Site",
                                   "Resign Date", "End Contract", "Level"])
    if mpp is None or getattr(mpp, "empty", True):
        return kosong

    d = mpp.copy()
    d.columns = [str(c).strip() for c in d.columns]
    for c in ("End Date", "Contract End Date"):
        d[c] = pd.to_datetime(d.get(c), errors="coerce")
    d["Level"] = pd.to_numeric(d.get("Level"), errors="coerce")

    if periods:
        periode_ok = _periode_mask(d["End Date"], periods)
    else:
        awal, berikut = _month_bounds()
        periode_ok = d["End Date"].between(awal, berikut, inclusive="left")

    # Level >= 11 itu non-staff operator, tidak masuk laporan ini.
    mask = (
        d["End Date"].notna()
        & (d["Level"] < 11)
        & (d.get("Position Name") != "Internship")
        & periode_ok
        & ((d["End Date"] < d["Contract End Date"]) | d["Contract End Date"].isna())
    )
    if sites:
        mask &= d["Location Name"].isin(C.location_names_for(sites))

    out = d[mask][["Employee Name", "Position Name", "Location Name",
                   "End Date", "Contract End Date", "Level"]]
    if out.empty:
        return kosong
    out.columns = ["Karyawan", "Position Name", "Site", "Resign Date",
                   "End Contract", "Level"]
    return out.sort_values(["Site", "Resign Date"])
