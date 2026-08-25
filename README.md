# HR Recruitment Portal — PT Darma Henwa

Aplikasi Streamlit pengganti dashboard Centralized. Mengikuti sistem desain
FTE Calculator: band oranye, kartu putih di atas abu terang, aksen navy,
Archivo + Public Sans.

---

## Deploy ke Streamlit Cloud

1. Push seluruh isi folder ini ke GitHub (repo boleh privat).
2. Di [share.streamlit.io](https://share.streamlit.io): **New app** → pilih repo →
   **Main file path** diisi `app.py`.
3. Buka **Advanced settings → Secrets**, tempel:

   ```toml
   [auth]
   recruitment = "RecruitmentPTDH"
   user = "UserPTDH"
   ```

4. Deploy.

`.streamlit/secrets.toml` sudah masuk `.gitignore` supaya password tidak ikut
ter-commit. Kalau file itu tidak ada, aplikasi jatuh ke nilai default di
`config.py` — cukup untuk uji coba, tapi ganti sebelum dipakai produksi.

**Syarat data:** ketiga spreadsheet harus di-share minimal
*Anyone with the link — Viewer*, kalau tidak Google mengembalikan halaman login
dan aplikasi menampilkan pesan error yang menyebutkan hal ini.

## Jalankan lokal

```bash
pip install -r requirements.txt
streamlit run app.py
```

Untuk bekerja tanpa menyentuh Google Sheets (mis. saat mengembangkan tampilan):

```bash
CENTRALIZED_CSV=/path/ke/fix_centralized.csv streamlit run app.py
```

---

## Peran & akses

| Halaman | Recruitment | User |
|---|:--:|:--:|
| Overview | ✓ | ✓ |
| Weekly Report | ✓ | ✓ |
| Tracking Kandidat | ✓ | ✓ |
| Tracking Posisi | ✓ | ✓ |
| Recruitment Room | ✓ | — |
| Export, hapus cache | ✓ | — |

Peran User yang mencoba membuka Recruitment Room lewat session state dialihkan
ke Overview. Nama kandidat tampil penuh di kedua peran.

## Struktur file

| File | Isi |
|---|---|
| `app.py` | Entrypoint: router, nav, dan empat halaman yang sudah jadi |
| `theme.py` | Sistem desain — token warna, satu blok CSS, komponen yang mengembalikan HTML |
| `charts.py` | Chart Plotly. Warna diambil dari token `theme.py`, tidak ada hex di sini |
| `config.py` | SLA per level, kalender libur, ID spreadsheet, password, roster recruiter |
| `metrics.py` | Semua perhitungan. Murni pandas, bisa dites tanpa Streamlit |
| `data_loader.py` | Pengambilan dari Google Sheets + rantai fallback |
| `auth.py` | Gerbang login dua tingkat |

Aturan yang menjaga aplikasi ini tetap konsisten:

- **Tidak ada halaman yang menghitung sendiri.** Semua angka lewat `metrics.py`.
  Versi lama menampilkan dua lead time berbeda untuk orang yang sama karena
  perhitungan tersebar di dua halaman.
- **Tidak ada hex di luar `theme.py`.** Ganti satu token, seluruh chart dan
  badge ikut berubah.
- **Semua teks dari data di-escape** sebelum masuk HTML (`theme.esc`). Portal ini
  menampilkan nama orang dan alasan keterlambatan yang diketik manusia.

---

## Cara lead time dihitung

**Hari kerja, inklusif.** Mulai dan selesai di hari kerja yang sama = 1 hari.
Sabtu, Minggu, dan libur nasional tidak dihitung.

Ini bukan definisi baru. Rumusnya dicocokkan terhadap kolom LT yang sudah ada di
spreadsheet dan **cocok 100% di 6.478 baris, sebelas tahap** — jadi angka portal
bisa langsung disandingkan dengan angka yang biasa dilihat tim.

Kalender libur dibaca dari `Monitoring 2026 › Backend` kolom A. Kalau sheet itu
tidak bisa diambil, dipakai salinan cadangan di `config.HOLIDAYS_FALLBACK`.

Portal menyediakan dua ukuran yang sengaja dipisah:

- `lt_stage_sum` — jumlah durasi tahap. Dipakai menilai kinerja PIC, karena orang
  hanya bertanggung jawab atas tahap yang ia pegang.
- `lt_elapsed` — selisih tanggal ujung ke ujung. Ini yang dirasakan user dan
  manajemen. Selisih keduanya (`lt_idle`) adalah waktu proses menganggur.

## SLA per level

Sumber: `Monitoring 2026 › Backend`. Ini menggantikan kolom `budget_lt1` di
database, yang berisi angka 16 hari lebih longgar dan membuat 99,4% kandidat
tampil "Onbudget".

| Level | Total | Catatan |
|---|--:|---|
| General Manager | 70 | |
| Manager | 70 | |
| Superintendent | 63 | |
| Supervisor | 61 | |
| Junior Staff | 60 | |
| Non Staff | 61 | Junior Staff + Technical Test 1 hari |

Technical Test hanya berlaku Non Staff — dikonfirmasi data: 235 dari 239 kandidat
Non Staff punya tanggalnya, nol di seluruh level lain. Untuk level lain, tahap ini
ditandai "tidak berlaku", bukan "pending", sehingga progress bar bisa mencapai 100%.

## Pemetaan kolom tanggal

Tiap pasangan diuji terhadap kolom LT yang sudah ada; hanya yang cocok 100%
dipakai. Dua di antaranya berbeda dari label lamanya:

- **MCU** berakhir di `mcu_issue_date`, bukan `mcu_date`.
- **One Month Notice** = `date_fit` → `date_onboarding`, budget 30 hari. Versi
  lama melabelinya "Onboarding"; Onboarding sendiri hanya milestone 1 hari.

---

## Yang masih perlu dilengkapi

### 1. Form Apps Script harus mengizinkan penyematan

Iframe di Recruitment Room akan kosong sampai `doGet()` di `Code.gs`
mengembalikan output dengan mode X-Frame `ALLOWALL`.

**Sebelum** — bentuk yang biasa dipakai:

```js
function doGet(e) {
  return HtmlService.createTemplateFromFile('Form').evaluate()
    .setTitle('Form Monitoring Recruitment');
}
```

**Sesudah** — tambahkan satu baris `.setXFrameOptionsMode(...)`:

```js
function doGet(e) {
  return HtmlService.createTemplateFromFile('Form').evaluate()
    .setTitle('Form Monitoring Recruitment')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
```

Kalau `doGet` memakai `createHtmlOutputFromFile` (bukan template), polanya sama:

```js
function doGet(e) {
  return HtmlService.createHtmlOutputFromFile('Form')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
```

Setelah diubah: **Deploy → Manage deployments → ikon pensil → Version: New
version → Deploy.** Menyimpan file saja tidak cukup; URL web app baru memakai
kode terbaru setelah versi baru di-deploy.

`addMetaTag('viewport', ...)` bukan keharusan, tapi membuat form ikut menyesuaikan
lebar iframe alih-alih tampil kecil di pojok.

Kalau form perlu tahu sedang dibuka untuk site mana, `e.parameter` bisa dibaca:

```js
function doGet(e) {
  var site = (e && e.parameter && e.parameter.site) || 'HO';
  var t = HtmlService.createTemplateFromFile('Form');
  t.site = site;   // dipakai di Form.html lewat <?= site ?>
  return t.evaluate()
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
```

### 2. Form dan spreadsheet per site

`config.FORM_URLS` dan `config.SHEET_URLS` menyimpan satu URL per site. HO
memakai form baru (Staff); BCP, KCP, dan ACP sementara memakai form Centralized
yang sudah berjalan selama ini. Mengganti form sebuah site cukup satu baris:

```python
FORM_URLS = {
    "HO":  "https://script.google.com/macros/s/AKfycby.../exec",
    "BCP": "https://script.google.com/macros/s/PASTE_URL_BARU/exec",
}
```

SSCP belum punya keduanya, jadi halamannya menyatakan itu apa adanya.

### 3. Inisial recruiter yang belum dipetakan

Tiga orang di roster belum punya inisial di `config.RECRUITER_NAMES`:
Muhammad Faiq Kenzie Widodo, Tallita Ayu Salsabila, Fachry. Sesuai arahan Navi
ini dibiarkan — mereka tampil dengan nilai nol, bukan mengambil data orang lain.

Kalau nanti inisialnya ketemu, ada dua cara memasukkannya:

- **Sementara** — panel *Kelola recruiter* di halaman Weekly Report. Berlaku
  untuk sesi itu saja, berguna untuk mencoba-coba.
- **Permanen** — tambahkan ke `RECRUITER_NAMES` di `config.py`.

Inisial yang masih menganggur, diurutkan dari yang tersibuk: `AIC` (550
aktivitas) · `FLI` (175) · `BEL` (112) · `SOM` (62) · `JAZ` (42) · `MEI` (5) ·
`ADR` (1). Sudah diketahui bukan milik roster: `RAF` = Rafi'ud A ·
`MRB` = M. Ribi H · `NAV` = Navi A · `IRV` = Irviyani.

### 4. Lead time Non Staff belum bisa diukur

163 dari 164 hire Non Staff punya tanggal screening, interview, dan onboarding
yang persis sama — input borongan di KCP tanggal 5 dan 7 Januari 2026. SLA
Non Staff yang sudah dipasang baru bermakna setelah site mengisi tanggal per
tahap. Sampai itu terjadi, semua metrik lead time mengecualikan Non Staff dan
hal itu dinyatakan terbuka di layar.

---

## Status halaman

| Halaman | Status |
|---|---|
| Overview | Ringkasan (5 kartu) + embed Looker — dua bagian saja |
| Weekly Report | Performance recruiter, New Hire, ringkasan site, On Progress, karyawan resign |
| Tracking Kandidat | Satu kotak cari + daftar kandidat, tabel tahap, progress bar |
| Tracking Posisi | Cari posisi langsung, site tertera di tiap baris, kandidat per posisi |
| Recruitment Room | Pilih site → link form & spreadsheet → form tersemat |

Halaman yang belum dibangun tetap bisa dibuka dan menampilkan daftar isi yang
akan masuk ke sana, supaya tidak ada tombol yang mati tanpa penjelasan.

### Catatan tiap halaman

**Overview.** Dashboard Looker tetap disematkan di bagian bawah. Filter site di
halaman ini hanya berlaku untuk kartu dan chart portal — Looker punya filternya
sendiri dan menghitung terpisah.

**Weekly Report.** Tabel Performance dihitung dua langkah: tiap tahap yang
seseorang pegang dirata-ratakan dulu (Screening rata-rata 1 hari, Interview HR
rata-rata 2 hari, dan seterusnya), lalu rata-rata antar tahap itu dijumlahkan.
SLA Budget mengikuti tahap yang sama, jadi keduanya selalu sebanding. Expander
*Rincian per tahap* memperlihatkan asal tiap angkanya.

Filter bulan/tahun bisa memilih lebih dari satu. Memilih dua bulan membuat
New Hire dan Ringkasan per site menampilkan satu kolom untuk tiap bulan plus
kolom Total. Periodenya merujuk ke tanggal **screening CV** untuk Performance,
dan tanggal **onboarding** untuk New Hire dan Ringkasan per site.

**On Progress dan Karyawan resign** mereplikasi rumus QUERY yang sudah dipakai
tim di sheet ONP dan Karyawan Resign, bukan tafsiran sendiri:

| Panel | Aturan |
|---|---|
| Offering | status OPEN, tahap Offering, START REQ OFFERING di bulan berjalan |
| MCU | status OPEN, tahap MCU/Review MCU/FU MCU, OL SENT di bulan berjalan |
| Onboarding | hasil MCU FIT TO WORK dan tanggal onboarding masih di depan |
| Resign | dari sheet `Update MPP`: level < 11, posisi bukan Internship, berhenti di bulan berjalan, dan berhenti sebelum kontrak habis atau tidak punya tanggal akhir kontrak |

Panel resign diverifikasi terhadap sheet: **18 dari 18 nama cocok persis** untuk
Agustus 2026.

Kolom **Onboarding** tidak bisa dijumlahkan ke bawah: satu kandidat ditangani
beberapa PIC dan masing-masing mendapat kreditnya (keputusan Navi), jadi
jumlahnya lebih besar dari hire sebenarnya. Kolom **Kandidat** disertakan supaya
Achievement bisa dibaca adil — orang yang hanya memegang screening wajar punya
angka jauh lebih tinggi daripada yang memegang offering sampai MCU.

Sheet **Summary** belum punya kolom Need. Angka kebutuhan berasal dari weekly
report dan portal belum menyambungnya; menampilkan kolom kosong bernama Need
akan lebih menyesatkan daripada tidak menampilkannya.

**Tracking Kandidat.** Kotak cari hanya menyaring; daftar di bawahnya yang
memilih. Tiap barisnya bertuliskan *nama · posisi · site* — memakai nama posisi,
bukan Position ID, karena kode seperti `R22R030012` tidak berarti apa-apa saat
dibaca sekilas. Progress bar dihitung terhadap tahap yang berlaku untuk level
itu, jadi kandidat yang sudah onboarding benar-benar mencapai 100%.

**Tracking Posisi.** Mengetik kata kunci langsung memunculkan posisi yang cocok,
dengan site tertera sebagai chip berwarna di tiap baris — tidak perlu memilih
site lebih dulu. Jadi mengetik "supervisor" langsung memperlihatkan semua
Supervisor di semua site sekaligus dan bisa dibandingkan.
