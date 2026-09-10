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

Tambahkan ke `RECRUITER_NAMES` di `config.py` kalau inisialnya sudah diketahui.

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
| Weekly Report | Performance recruiter, New Hire, ringkasan site, On Progress, karyawan resign — semuanya mengikuti satu baris filter |
| Tracking Kandidat | Satu kotak pencarian, tabel tahap, progress bar, kartu SLA |
| Tracking Posisi | Satu kotak pencarian, langsung ke detail posisi dan kandidatnya |
| Recruitment Room | Pilih site → link form & spreadsheet → form tersemat |

Halaman yang belum dibangun tetap bisa dibuka dan menampilkan daftar isi yang
akan masuk ke sana, supaya tidak ada tombol yang mati tanpa penjelasan.

### Catatan tiap halaman

**Overview.** Dashboard Looker tetap disematkan di bagian bawah. Filter site di
halaman ini hanya berlaku untuk kartu dan chart portal — Looker punya filternya
sendiri dan menghitung terpisah.

**Weekly Report.** Satu baris filter di atas — Tahun, Bulan, Site — mengatur
SELURUH bagian di bawahnya: Performance, New Hire, Ringkasan per site,
On Progress, dan Karyawan resign.

Tabel Performance dihitung dua langkah:

1. Kumpulkan kandidat yang ditangani orang itu.
2. Untuk **setiap tahap proses** — PRF Approval sampai Onboarding — hitung
   rata-rata lead time dan rata-rata budget di antara kandidat tadi.
3. Jumlahkan rata-rata itu lintas tahap. Tidak dibagi lagi.

Yang penting di langkah 2: seluruh tahap ikut, bukan hanya tahap yang punya
kolom PIC di database. Versi sebelumnya hanya menghitung tujuh tahap ber-PIC,
sehingga One Month Notice yang budget-nya saja 30 hari ikut terbuang dan total
budget keluar cuma ~20 hari — mustahil untuk proses bertarget 60+ hari. Sekarang
SLA Budget sejalan dengan matriks di `Monitoring 2026 › Backend`.

Filter bulan bisa memilih lebih dari satu. Memilih dua bulan membuat New Hire
dan Ringkasan per site menampilkan satu kolom untuk tiap bulan plus kolom Total.
Periodenya merujuk ke tanggal **screening CV** untuk Performance, tanggal
**onboarding** untuk New Hire dan Ringkasan per site, tanggal tahap
masing-masing untuk On Progress, dan tanggal **resign** untuk Karyawan resign.

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

Kolom **Kandidat** dan **Onboarding** dihitung dari **PIC Screening CV saja**,
sesuai permintaan Navi: satu kandidat hanya dikreditkan ke satu orang, jadi kedua
kolom itu boleh dijumlahkan ke bawah tanpa dobel. SLA-nya tetap dihitung dari
seluruh tahap yang orang itu tangani — dua ukuran yang beda dasar, dan memang
sengaja.

Sheet **Summary** belum punya kolom Need. Angka kebutuhan berasal dari weekly
report dan portal belum menyambungnya; menampilkan kolom kosong bernama Need
akan lebih menyesatkan daripada tidak menampilkannya.

**Tracking Kandidat & Tracking Posisi.** Keduanya memakai satu kotak saja, dan
daftarnya menyusut **sambil diketik** — tidak perlu menekan tombol apa pun.

Yang dicocokkan hanya **nama** (di Tracking Kandidat) atau **nama posisi** (di
Tracking Posisi). Keterangan lain — posisi, departemen, level, site — muncul di
bawah setelah dipilih, bukan ikut jadi bahan pencarian. Kalau labelnya memuat
semua keterangan itu, mengetik "tika" ikut memunculkan orang yang cuma kebetulan
departemennya mengandung "tika".

Nama yang kembar diberi pembeda seperlunya: nama posisi dulu, dan site hanya
kalau posisinya pun sama.

Tracking Posisi langsung menampilkan detail posisi yang dipilih; tabel hasil
pencarian sudah dihapus. Kolom kandidatnya: nama, posisi, departemen, level,
loc, last progress, total LT, dan status.

**Panjang tabel.** New Hire, Ringkasan per site, On Progress, Karyawan resign,
dan daftar kandidat per posisi dibatasi **10 baris terlihat**; sisanya digulir
di dalam kotak tabel dengan header yang tetap menempel. Tanpa batas ini satu
panel On Progress berisi 200 baris mendorong seluruh bagian lain jauh ke bawah.

**Site kosong.** Kandidat yang kolom `loc`-nya tidak terisi dimasukkan ke
**BPN**, bukan ditampilkan sebagai baris "(tanpa site)".


**Departemen yang terisi nama posisi.** Sebagian baris database mengisi kolom
`departement` dengan nama posisi ("Foreman - DMS Operation"), sehingga New Hire
dulu memunculkan nama posisi seolah-olah departemen. Portal memperbaikinya lewat
master `Monitoring 2026 › MPP 2026` (660 Position ID, 685 nama posisi, 56
departemen sah), dengan urutan: nilai yang memang departemen dipakai apa adanya →
cari lewat Position ID → cari lewat nama posisi → contek baris lain dengan posisi
sama → sisanya dikumpulkan ke satu baris "Belum diisi di sumber".

Dua jebakan yang sudah ditutup:

* Endpoint **gviz by nama tab** memotong sheet MPP 2026 di **baris ke-4**. Portal
  memakai `export?format=csv&gid=354501614` lebih dulu dan gviz hanya cadangan.
  Kalau master terbaca kurang dari 20 departemen, master itu **tidak dipakai sama
  sekali** — lebih baik jatuh ke acuan cadangan daripada menganggap semua
  departemen asli tidak sah dan meruntuhkan laporan jadi satu baris.
* Di sheet MPP 2026 judul kolom **"Position" dan "PositionID" tertukar dengan
  isinya** (yang berjudul Position berisi kode, yang berjudul PositionID berisi
  nama). Portal menukarnya balik saat membaca; kalau nanti sheetnya diperbaiki,
  ubah `MPP_HEADER_SWAPPED = False` di `config.py`.

Sisanya, **711 baris** memang belum bisa dipetakan, dan itu perkara data bukan
kode: 566 baris kolom departemennya kosong di sumber, sisanya memakai posisi yang
belum ada di MPP 2026 (rata-rata posisi baru berkode 11 digit seperti
`E26E0200002`, `P26P0470002` — SSCP). Di New Hire hanya 50 dari 414 yang jatuh ke
"Belum diisi di sumber".

**Tanggal di sheet Update MPP** ditulis hari-dulu (`03/01/2026` = 3 Januari).
Dibaca dengan format eksplisit `%d/%m/%Y`, bukan tebakan pandas — kalau tidak,
tanggal 1–12 berisiko terbalik jadi bulan dan daftar resign salah periode.


## fix_centralized vs Backend Monitoring — kolom lookup yang belum ditarik

Per 30 Agu 2026, **566 baris** di `fix_centralized` punya Position ID tapi kolom
POSITION NAME, LEVEL, DEPARTMENT dan LOC-nya **kosong** — kolom lookup yang belum
ditarik ke bawah untuk baris baru (hampir semuanya SSCP). Akibatnya di portal
kandidat SSCP tercatat tanpa site, lalu ikut terhitung sebagai BPN, dan tanpa
departemen.

Baris yang sama di `Report › Backend Monitoring` (gid 0) **sudah terisi lengkap**
— itulah sheet yang dilihat tim di dashboard monitoring. Portal memakai sheet itu
sebagai penambal identitas: `data_loader.load_backend_monitoring()` +
`metrics.set_row_master()`, dicocokkan dengan kunci **nama + Position ID** supaya
orang yang melamar dua posisi tidak tertukar.

Penambalan ini **hanya mengisi lubang**, tidak menimpa nilai yang sudah ada.
`fix_centralized` tetap sumber utama karena punya kolom Technical Test dan
seluruh peta tahap portal.

Hasilnya (Agustus 2026): Ringkasan per site berubah dari *BPN 29* menjadi
**SSCP 30 · BCP 10 · JKT 2 · BPN 1 · KCP 1**, dan New Hire yang jatuh ke
"Belum diisi di sumber" turun dari **30 menjadi 1**. Sepanjang 2026, dari 414
hire hanya **3** yang belum berdepartemen dan **2** yang benar-benar tanpa site.

Sisa 37 baris tanpa site memang tidak punya Position ID di kedua sheet — ini
perkara input, bukan lookup.

## Satu departemen, beberapa ejaan

Tiga sheet menulis HSE dengan tiga ejaan berbeda: `fix_centralized` dan MPP 2026
menulis "Environent", Backend Monitoring "Environment", sheet Report
"Environtment". Tanpa penyatuan, New Hire menampilkan dua baris untuk departemen
yang sama. `config.DEPT_ALIASES` menyatukannya — daftarnya sengaja pendek dan
eksplisit supaya terlihat persis apa yang digabung.


## Halaman PRF Tracking

Sumbernya spreadsheet **PRF Management › tab "PRF Tracking"** (`config.PRF_*`),
terpisah dari database kandidat: PRF terjadi SEBELUM ada kandidat, jadi tidak
bisa diturunkan dari fix_centralized.

**Kartu.** Jumlah PRF · Approved · Not Approved · Status Close. Approved dan Not
Approved dibaca dari kolom **Tracking PRF**; Status Close dari kolom **Status**,
dan persentasenya terhadap **total PRF** (bukan terhadap yang approved saja),
sesuai permintaan Navi.

Semua angka menghitung **baris PRF**, bukan qty orang. Satu PRF bisa meminta 14
orang sekaligus; menjumlahkan qty menjawab pertanyaan yang berbeda dari "berapa
PRF yang sudah approved". Qty tetap tampil per baris di tabel, dan total qty
disebut sebagai keterangan kecil di kartu Jumlah PRF.

**Filter.** Site · Level · Jenis Level · Tracking PRF · Status PRF. Site, Level,
dan Jenis Level diambil dari data. Tracking PRF dan Status PRF memakai daftar
tetap di `config.PRF_TRACKING_VALUES` dan `config.PRF_STATUS_VALUES` — CLOSE dan
CANCEL belum pernah ada satu baris pun, dan filter yang menyusut sendiri terbaca
seperti fitur yang hilang, bukan seperti keadaan yang memang belum terjadi.

**Jenis Level.** Staff = Junior Staff, Supervisor, Superintendent, Manager,
General Manager, Boards, Commisioner (`config.PRF_STAFF_LEVELS`). Sisanya —
apa pun isinya — masuk Non Staff, jadi level baru tidak diam-diam hilang dari
filter. Baris yang levelnya kosong ditandai "—", bukan Non Staff: itu klaim yang
tidak ada dasarnya. Per 2 Sep 2026 seluruh 144 baris berlevel Staff.

**Kolom identitas.** Tabel memakai satu kolom **Request Number** saja: kalau
`request_number` kosong, dipakai `ID PRF`. Dua kolom untuk satu identitas, yang
masing-masing separuhnya kosong, hanya menyulitkan pembacaan — per 2 Sep 2026 ada
3 baris yang baru punya ID PRF (`H15P1`, `H12P1`, `H12P2`).


## Unduh tabel: Excel dan Gambar

Tiap tabel punya dua tombol kecil di ujung kanan atasnya. Yang diunduh adalah
**tabel yang sedang tampil**, sudah kena filter halaman — bukan data mentah.
Kalau yang keluar selalu data mentah, orang mengirimkan berkas yang isinya
berbeda dari yang baru saja mereka lihat di layar, dan itu jenis kesalahan yang
baru ketahuan setelah berkasnya beredar.

Karena itu semua tabel lewat satu pintu, `app.tabel()`, bukan langsung ke
`theme.data_table()`: satu sumber baris, dua cara menampilkannya.

**Excel (.xlsx).** Header bergaya portal, freeze pane, autofilter, dan satu baris
catatan berisi judul + filter aktif + tanggal unduh. Angka yang di layar diformat
gaya Indonesia (`1.150`, `40,4`, `166,2%`) dikembalikan jadi **angka betulan** di
Excel — kalau dibiarkan teks, kolomnya tidak bisa dijumlahkan atau diurutkan,
padahal itu alasan orang mengunduh ke Excel. Teks yang kebetulan berbentuk angka
tidak ikut dikonversi: pola pencocokannya harus cocok seluruh teks, dan nilai
berawalan nol (`013`) tetap teks karena itu kode, bukan angka.

**Gambar (.png).** Tabelnya digambar ulang dengan matplotlib memakai warna yang
sama dengan di layar — Streamlit tidak bisa memotret dirinya sendiri. Hasilnya
justru lebih rapi: tidak ada scrollbar, tidak terpotong, dan **seluruh baris
ikut** walau di layar harus digulir. Dipakai untuk ditempel ke deck atau dikirim
di WhatsApp.

Tabel di atas **60 baris** tidak digambar otomatis — menggambar 257 baris perlu
~2 detik dan menghasilkan berkas 3 MB, biaya yang tidak pantas dibayar setiap
kali filter digeser. Tombolnya jadi "siapkan dulu": klik sekali untuk menyiapkan,
lalu tombolnya berubah jadi unduhan. Hasilnya di-cache, jadi filter yang sama
tidak digambar dua kali.

**Siapa yang bisa mengunduh.** Hanya peran Recruitment — peran User memang tidak
diberi export sejak awal. Kalau mau dibuka untuk semua, ubah `export` di
`config.ACTION_ACCESS`.

Tabel Tahap seleksi memakai penampil sendiri (`theme.stage_table`) karena tiap
barisnya berisi lencana status, tapi tetap bisa diunduh lewat `app.unduh_saja()`.
Di berkasnya lencana jadi teks — di Excel dan di gambar, warna saja tidak cukup
untuk menyampaikan "Late".

## Talent pool

Kandidat yang lolos seleksi tapi belum ditempatkan — posisinya sudah terisi orang
lain, atau kebutuhannya belum ada. Ditandai lewat kolom **Result** di tahap mana
pun oleh form Apps Script, bukan lewat satu kolom khusus: keputusan itu diambil
di tahap yang berbeda-beda per orang.

**Dampaknya ke arti CLOSE.** Sebuah proses sekarang bisa berakhir dengan dua cara
yang sama-sama "selesai" tapi sangat berbeda maknanya:

| | Artinya |
|---|---|
| Close — Onboarding | orangnya masuk kerja |
| Talent pool | orangnya disimpan untuk kebutuhan berikutnya |

Menjumlahkan keduanya jadi satu angka "hire" membuat pencapaian rekrutmen
terlihat lebih besar dari kenyataan, jadi di Overview keduanya berdiri sendiri.
Kartu Talent pool menghitung **semua** orang di pool apa pun `status1`-nya —
sebagian baris masih tertulis OPEN di sheet padahal keputusannya sudah diambil di
kolom Result.

**Tabelnya hidup di Recruitment Room**, bukan di Overview: di Overview orang cuma
melihat angkanya, di Recruitment Room orang menindaklanjutinya — dan nomor HP-nya
justru berguna saat filter site/PIC sudah dipersempit. Daftarnya ikut seluruh
filter halaman itu.

Isinya nama, nomor HP, posisi yang dilamar, dan departemen sesuai permintaan, ditambah tiga kolom yang membuatnya bisa langsung dipakai menelepon
orang: **Site** (siapa yang menghubungi), **Level** (posisi apa yang pantas
ditawarkan), dan **Tahap** tempat dia masuk pool (semakin jauh tahapnya, semakin
sedikit seleksi yang perlu diulang).

Nomor HP diambil dari kolom `No Telpon` di `Report › Backend Monitoring` —
`fix_centralized` tidak punya kolomnya sama sekali.

## Tracking Posisi — dua mode

| Mode | Menjawab |
|---|---|
| **Per Posisi** (default) | "posisi X isinya siapa?" |
| Per Departemen | "departemen saya sudah sampai mana?" |

Mode Site dihapus: pertanyaannya sudah terjawab oleh filter Site yang berlaku di
kedua mode, dan mode ketiga hanya menambah pilihan tanpa menambah jawaban.

Pemilih modenya `st.segmented_control`, bukan radio bertitik — dua pilihan yang
saling meniadakan lebih terbaca sebagai dua tombol berdampingan.

**Filter bersama kedua mode:** bulan (multi-pilih, patokannya tanggal
**Screening CV**) dan site. Screening CV dipakai sebagai patokan periode di
seluruh portal karena itu tanggal kandidat masuk proses, jadi satu kandidat
selalu utuh dalam satu bulan. Kalau patokannya tanggal tahap terakhir, orang yang
sama pindah-pindah bulan setiap prosesnya maju, dan angka bulan lalu berubah
sendiri.

**Mode Per Departemen bertingkat, bukan tabel.** Pilih departemen di dropdown →
ringkasannya muncul (kartu + batang sebaran + chip "yang masih berjalan berhenti
di mana") → di bawahnya posisi yang dibuka, satu per satu bisa dibuka untuk
melihat sebaran dan siapa yang sedang diproses. Melihat semua posisi sekaligus
sebagai tabel bukan tracking, cuma daftar.

Yang tampil lebih dulu hanya posisi yang **masih ada orangnya jalan** — itu arti
"posisi yang dibuka". Plant & Maintenance punya 79 posisi tercatat dan hanya 35
yang masih berjalan; ada tombol untuk memunculkan sisanya.

**Komponen visual baru** menggantikan deretan kolom angka:

* `theme.split_bar()` — batang bertumpuk + legenda angkanya. Proporsi jauh lebih
  cepat dibaca sebagai panjang daripada sebagai lima kolom angka. Sisa yang tidak
  masuk empat kategori (hampir semuanya HOLD) ikut digambar sebagai "lainnya" —
  celah abu yang tidak dijelaskan selalu dibaca sebagai bug.
* `theme.chip_row()` — sebaran last progress sebagai chip. Sebagai tabel, sepuluh
  baris dipakai untuk memberi tahu bahwa kebanyakan bernilai nol; sebagai chip,
  yang nol tidak ditulis sama sekali.
* `theme.stat_inline()` — angka ringkas sebaris untuk ruang sempit di dalam
  expander.

## Recruitment Room — monitoring, bukan embed

Embed form Apps Script sudah dihapus. Alasannya bukan teknis: form itu memang
untuk **mengisi**, dan mengisi lebih enak di tab sendiri yang lebar. Yang tidak
bisa dilakukan form adalah **melihat** — dan itu yang selama ini memaksa tim
kembali ke spreadsheet mentah. Halaman ini mengambil alih bagian melihatnya.

**Atas: tabel monitoring.** Enam filter (Site · PIC · Departemen · Status · Level
· Jenis level), semuanya default "semua". Kolom inti yang selalu tampil: kandidat,
posisi, site, departemen, level, PIC, tahap terakhir, status, SLA.

Sheet aslinya punya **delapan kolom per tahap** — start, done, LT, budget, LT
contribution, variance, reason, result — dan itu yang membuatnya berhenti
terbaca. Di portal, tahap ditambahkan sendiri lewat "Tambah kolom tahap", dan
tiap tahap hanya membawa **LT** dan **SLA**. Variance dan LT contribution tidak
dibawa karena keduanya turunan dari LT dan budget yang sudah tampil.

**PIC** diambil dari PIC Screening CV, dasar yang sama dengan tabel Performance,
jadi angka di dua halaman itu bisa dibandingkan langsung.

**Bawah: daftar link** form dan spreadsheet per site, masing-masing bisa disalin
atau dibuka di tab baru.

## PIC: nama lengkap, bukan lagi inisial

Kolom `*_by` dulu berisi inisial tiga huruf; form Apps Script sekarang menulis
**nama lengkap**, dan ejaannya tidak seragam — di database ada "SHAUMY FADHILA"
dan "SHAUMY FADILAH", "ALFINA DIVA RAMADHANTY" dan "ALFINA DIVA". Karena peta
lama hanya berisi inisial, empat recruiter tercatat nol padahal datanya ada.

`config.resolve_recruiter()` menggantikan peta itu, dengan urutan:

1. cocokkan ke nama roster apa adanya (abaikan besar-kecil dan tanda baca);
2. cocokkan ke peta inisial;
3. cocokkan lewat **nama depan**, tapi hanya kalau nama depan itu cuma dimiliki
   satu orang di roster. "Shaumy" unik, jadi "SHAUMY FADILAH" aman dipulangkan.
   "Muhammad" dimiliki dua orang, jadi nama depan saja sengaja tidak cukup —
   lebih baik masuk "Recruiter lain" daripada dikreditkan ke orang yang salah.

Diverifikasi terhadap hitungan langsung dari sheet: kedelapan baris tabel
Performance cocok persis, selisih nol.


## Kolom Onboarding sekarang cocok dengan Ringkasan per site

Sebelumnya kolom Onboarding di tabel Performance tidak pernah bisa dicocokkan
dengan Ringkasan per site walau sumbernya sama. Untuk Jun–Sep 2026: **75 vs 126**.
Selisih 51 itu punya dua sebab yang berbeda, dan keduanya sudah diperbaiki.

**Sebab 1 — kandidat tanpa PIC hilang tanpa jejak (21 orang).** Baris yang kolom
PIC Screening CV-nya kosong disaring keluar sejak awal: bukan masuk "Recruiter
lain", tapi benar-benar tidak dihitung. Dari 127 orang yang onboarding Jun–Sep
2026, **21 tidak punya PIC screening** — 18 di antaranya SSCP, sisanya JKT, KCP,
ACP. Kebanyakan rekrutan massal Non Staff seperti Driver Travel dan Pit
Controller.

Sekarang mereka dikelompokkan per site jadi baris **"PIC Site SSCP"**, **"PIC Site
ACP"**, dan seterusnya — di lapangan memang site yang menanganinya. Barisnya
diurutkan setelah nama orang tapi sebelum "Recruiter lain": bukan orang, tapi juga
bukan sisa-sisa.

**Sebab 2 — Onboarding memakai basis tanggal yang salah (34 orang).** Kolom itu
dulu menghitung "kandidat yang di-screening dalam periode DAN statusnya CLOSE",
jadi orang yang di-screening Mei tapi onboarding Juli tidak terhitung di periode
Jun–Sep. Sekarang basisnya **tanggal onboarding**, sama dengan Ringkasan per site
dan New Hire.

Dua kolom, dua basis tanggal, dan itu disengaja:

| Kolom | Basis | Menjawab |
|---|---|---|
| Kandidat | tanggal **Screening CV** | berapa CV yang saya proses periode ini |
| Onboarding | tanggal **onboarding** | berapa yang benar-benar mulai kerja periode ini |

Syarat `status1 = CLOSE` ikut dipakai persis seperti di `summary_matrix()`: ada 4
orang di 2026 yang tanggal onboarding-nya terisi tapi statusnya FAILED — batal di
detik terakhir.

**Hasil verifikasi** — kolom Onboarding dijumlahkan ke bawah vs total Ringkasan
per site:

| Periode | Performance | Ringkasan per site | Selisih |
|---|---|---|---|
| Jan–Mar 2026 | 175 | 175 | 0 |
| Jun–Sep 2026 | 126 | 126 | 0 |
| Agustus 2026 | 44 | 44 | 0 |
| 2026 penuh | 435 | 435 | 0 |

Cocok juga saat difilter per site (BCP 42, SSCP 53, KCP 8).

## Satu baris, satu populasi

Ikut diperbaiki sekalian: SLA di tabel Performance dulu memakai populasi yang
BERBEDA dari Kandidat dan Onboarding. SLA memakai "semua kandidat yang tahap mana
pun pernah ia pegang", sementara dua kolom lain memakai "kandidat yang ia
screening". Satu baris berisi angka dari dua kelompok orang yang berbeda — dan
itu sebabnya baris "PIC Site SSCP" sempat tampil punya 83 kandidat tapi SLA
kosong: SLA kandidat itu tercatat di baris orang lain.

Sekarang seluruh kolom memakai satu populasi: **kandidat yang PIC Screening
CV-nya orang itu**. SLA-nya tetap menjumlahkan rata-rata dari SELURUH tahap
proses kandidat tersebut, bukan hanya tahap yang ia pegang sendiri.

## Summary by Division

Meniru sheet **Summary by Division** milik tim, tapi bisa ditelusuri: sheet
aslinya berhenti di Staff/Non Staff, dan level baru terlihat kalau pivot-nya
dibongkar sendiri.

Sejak 8 Sep 2026 halaman ini ada di urutan **kedua**, tepat setelah Overview,
dan bentuknya **satu tabel yang bisa di-grup seperti Excel** — bukan lagi dua
puluh enam expander yang berdiri sendiri-sendiri.

**Cara bacanya:** klik `[+]` di depan nama divisi, baris levelnya muncul tepat di
bawahnya **dalam kolom yang sama persis**. Buka-tutupnya murni CSS (checkbox
tersembunyi + selector `~`), jadi tidak ada rerun Streamlit sama sekali —
sebelumnya tiap klik expander memaksa halaman menghitung ulang MPP, daftar
karyawan, dan seluruh pipeline.

**Kolom pertama dibekukan** (freeze pane) dan tabelnya bisa digeser ke kanan
sampai kolom proses: **Interview User · Psychotest · Offering · MCU**, masing-
masing dipecah **On progress / Passed / Failed**. Baris TOTAL menempel di dasar
tabel. Petunjuk gesernya ditulis di kanan atas tabel.

Empat tahap itu yang dipilih karena di situlah kandidat paling sering tertahan —
Screening CV terlalu di depan (hampir semua orang lewat), Onboarding terlalu di
belakang (sudah jadi angka Onboarding). Keadaan tiap tahap dibaca dari kolom
Result kalau ada; MCU tidak punya kolom Result sama sekali, jadi keadaannya
disimpulkan dari tanggal: sudah mulai belum selesai = berjalan, sudah selesai dan
kandidat lanjut ke tahap berikutnya = lulus, sudah selesai tapi berhenti di sini
dan kandidatnya FAILED = gagal di sini. Tahap yang belum pernah disentuh tidak
dihitung sama sekali — "belum sampai ke sini" bukan "gagal di sini".

Tingkat ketiga (**posisi & orangnya**) ada di bawah tabel, dipilih lewat dua
dropdown: Divisi lalu Level. Isinya daftar nama, dan daftar nama di dalam kolom
angka tidak terbaca — jadi sengaja tidak dijadikan baris tabel.

**Empat sumber, empat peran yang berbeda** — semuanya tab di spreadsheet
Report yang sama, persis yang dipakai rumus di sheet *Copy of Summary by
Division* milik tim (diselaraskan 8 Sep 2026):

| Tab | Perannya | Rumus aslinya |
|---|---|---|
| `MPP2` | berapa yang **direncanakan** | `SUMIFS(MPP2!Reforecast; Divisi; Loc; Status)` |
| `Existing Employee` | berapa yang **ada** sekarang | `COUNTIFS(Division; Level "<11"/"=11"; Loc)` |
| `ADP` | berapa yang sudah **diisi acting** | `COUNTIFS(ADP!Division; Lokasi; Status)` |
| Database kandidat | berapa yang **sedang diproses** | — |

Sebelumnya MPP diambil dari spreadsheet lain dan divisi karyawan ditebak dari
huruf pertama Position Code. Dua sumber berbeda untuk satu angka yang sama
adalah cara paling pasti membuat portal dan sheet berselisih, jadi sekarang
keduanya membaca tab yang sama. Tab `Existing Employee` juga sudah punya kolom
**Division**, **Loc**, dan **Level** yang dibereskan tim — tidak ada lagi
tebakan dari kode posisi, dan isinya sudah tersaring (tidak ada End Date).

**ADP** = orang yang sudah menempati posisi itu sebagai *acting*. Kolomnya
ditempatkan di level yang sedang dia duduki (kolom `Level Acting`), bukan level
asalnya — yang berkurang kebutuhannya adalah posisi yang sedang dia isi.

**Need to hire** = `MPP − Actual − ADP`, minimal nol. Sheet menulisnya
bertanda terbalik (`ADP + Gap`, negatif berarti kurang); di portal tandanya
dibalik supaya kolom bernama "Need to hire" berisi angka yang benar-benar
berarti "rekrut sekian orang lagi". ADP mengurangi karena orangnya sudah
menempati posisi itu sebagai acting.

**FTAP tidak ikut dalam rumus ini** (sejak 11 Sep 2026). Sheet mengurangkannya,
dan portal sempat menambahkannya kembali, karena dulu peserta FTAP terhitung di
Actual sebuah divisi tanpa punya posisi yang dianggarkan. Sejak budget FTAP
masuk ke MPP2, tiap peserta sudah punya anggarannya sendiri di divisi tujuannya
— MPP dan Actual-nya saling menutup, dan menambahkan FTAP sekali lagi akan
menghitung orang yang sama dua kali. Kolom FTAP sekarang murni keterangan:
berapa dari Actual itu peserta program.

### Kolom proses: sumber & rumus sama dengan sheet

Sejak 11 Sep 2026 empat kolom proses di halaman ini dibaca dari **tab monitoring
kandidat** (`MONITORING_GID_PROCESS = 593032148` di spreadsheet Monitoring
2026) — tab yang sama dengan yang dibaca rumus sheet, yang di spreadsheet Report
muncul sebagai *Backend Monitoring*. Keduanya cermin satu sama lain: 3.951
baris, 2.016 di antaranya punya STATUS, dan hitungan STATUS-nya cocok persis.

Arahan Navi: *"kalau sourcenya sudah sama maka dengan rumus yang sama hasilnya
sama kan? samakan rumusnya."* Dan memang begitu hasilnya.

Halaman lain **tetap** membaca `fix_centralized` — di situlah peta tahap portal
lengkap (Technical Test, seluruh tanggal per tahap, lead time). Yang dipindah
hanya empat kolom proses di Summary by Division.

Keuntungan lain: tab ini punya kolom **RESULT MCU** langsung, jadi tidak perlu
lagi menumpang hasil FU MCU.

**Rumusnya:**

1. **On Progress** dan **Passed** dari kolom Result, disaring status (bawaan
   `OPEN` = In process).
2. **Failed** dari kolom Result, jendela **dua bulan terakhir** pada tanggal
   MULAI tahap, status diabaikan. Kolom proses tidak ikut filter tanggal
   halaman — "sekarang orangnya ada di mana" tidak punya periode.
3. **Batas rantai**, per baris: isi sebuah tahap (on progress + passed + failed)
   tidak boleh melebihi yang lulus di tahap sebelumnya. Failed mengisi tepat
   sisanya:

   ```
   Failed(B) = min( gagal dalam dua bulan terakhir ,
                    Passed(A) − (B.on progress + B.passed) )
   ```

Dihitung di butiran `divisi ▸ level`, lalu angka divisinya diturunkan dengan
menjumlahkan baris levelnya — hierarkinya dijamin konsisten.

**Hasil 11 Sep 2026 — rantainya menutup persis:**

| Passed at | People | Should appear at | Recorded | Gap |
|---|---:|---|---:|---:|
| Interview User | 82 | Psychotest on progress + passed | 82 | **0** |
| Psychotest | 50 | Offering on progress + passed | 50 | **0** |
| Offering | 32 | MCU on progress + passed | 32 | **0** |

Per divisi juga menutup: Operation 21→21 · Engineering 16→16 · Plant &
Maintenance 16→16 · HCM 7→7 · HSE 7→7 · Supply Chain 5→5.

Total: Interview User 17 / 82 / 83 · Psychotest 32 / 50 / 0 · Offering
18 / 32 / 0 · MCU 26 / 6 / 0.

**Mode status lain** — begitu Closed / Failed / On hold / Backup ikut dipilih,
batas rantai tidak berlaku lagi dan ketiga kolom memakai kosakata hasil apa
adanya: `DECLINE` dan `WITHDRAWN` di Offering, `UNFIT` di MCU.

**Satu jebakan yang memakan waktu:** kolom sheet bertipe *string nullable*, jadi
sel kosong tetap `NA` setelah `astype(str)` — dan `NA` di dalam masker boolean
lolos sebagai True. Tanpa `.fillna("")`, 1.935 baris kosong sisa template ikut
terbaca sebagai kandidat.

### Baris harus menjumlah ke TOTAL

Diperbaiki 11 Sep 2026 setelah Navi menjumlahkan sendiri kolom *Interview User
— Passed* di file unduhan dan mendapat **73**, sementara baris TOTAL menulis
**88**. Tiga sebab terpisah, semuanya nyata:

1. **Grup proses tanpa baris.** Kandidat yang departemennya tidak dikenal MPP
   maupun daftar karyawan (label `Not filled in at source`, 15 orang lulus
   Interview User) ikut terhitung di TOTAL tapi tidak punya baris di tabel.
   Sekarang grup seperti itu **ditambahkan sebagai baris** dengan MPP dan Actual
   nol. Perlakuan yang sama berlaku untuk level di dalam divisi.
2. **TOTAL menjumlah lebih banyak daripada yang tampil.** Baris TOTAL kini
   dihitung dengan `pb_div.reindex(div["divisi"])` — hanya divisi yang benar-
   benar punya baris.
3. **Batas rantai dihitung dua kali di butiran berbeda.** Kolom proses sekarang
   dihitung di butiran paling halus (`divisi ▸ level`) lebih dulu, lalu angka
   divisinya **diturunkan dengan menjumlahkan baris levelnya**. Sebelumnya
   keduanya dihitung terpisah, dan batas rantai per divisi bisa berbeda dari
   batas per level — membuat baris level tidak menjumlah ke barisnya. Batas
   rantainya tetap terpenuhi: penjumlahan pertidaksamaan tetap pertidaksamaan.

**Dan file unduhannya memisahkan Divisi dan Level jadi dua kolom.** Di layar
barisnya bertingkat jadi jelas mana induk mana anak; di dalam file keduanya
berdiri sejajar. Sempat ditandai lekukan spasi, dan Excel membuang lekukannya —
siapa pun yang menjumlahkan satu kolom lalu ikut menghitung baris level, hasilnya
dua kali lipat. Dengan dua kolom, "baris divisi" = baris yang kolom **Level**-nya
kosong.

Diverifikasi dengan mengunduh file dari aplikasi yang berjalan lalu menjumlahkan
ulang tiap kolom: 26 baris divisi, 118 baris level, **23 dari 23 kolom cocok**
dengan baris TOTAL, dan baris level menjumlah tepat ke baris divisinya.

### Rekonsiliasi terhadap sheet (10 Sep 2026)

Diuji terhadap `Report Recruitment 4.xlsx` — portal dijalankan atas tab yang
sama persis dengan yang dibaca rumus sheet, jadi selisih yang muncul murni
selisih logika, bukan selisih tanggal snapshot.

| Site | MPP sheet/portal | Actual sheet/portal | ADP sheet/portal |
|---|---|---|---|
| BCP | 3.039 / 3.039 | 2.555 / 2.555 | 38 / 38 |
| KCP | 1.312 / 1.312 | 1.344 / 1.344 | 9 / 9 |
| ACP | 637 / 637 | 608 / 608 | 8 / 8 |
| SSCP | 1.009 / 1.009 | 338 / 338 | 0 / 0 |
| JKT | 257 / 257 | 213 / **216** | 6 / 6 |
| BPN | 24 / 24 | 21 / 21 | 0 / 0 |

Satu-satunya selisih yang tersisa: **Hospitality JKT, 3 orang**. Mereka ada di
tab Existing Employee tapi blok JKT di sheet tidak punya baris Hospitality, jadi
sheet tidak menghitungnya. Portal sengaja tidak ikut menghilangkan orang —
kalau baris departemennya ditambahkan di sheet, angkanya akan sama.

Empat baris MPP di blok JKT (Internal Audit, HSE, Finance Controller & Treasury,
Plant & Maintenance) juga selisih 1–2 karena nilai di sel-nya sudah basi: di
MPP2 ada posisi Manager/Superintendent yang tertulis `Non Staff`, jadi
`SUMIFS(...;"Staff")` sekarang menghasilkan angka yang berbeda dari yang
tersimpan di sheet. Itu perlu dibereskan di MPP2, bukan di portal.

**Filter status proses.** Multiselect Open / Close / Failed / Hold / Backup
candidate, kosong berarti semua. Sama seperti filter tanggal, yang disaring
hanya kolom kandidat — MPP, Actual, dan ADP tidak ikut bergerak. Label
"Backup candidate" dipetakan ke nilai `TALENT POOL` di sheet, dan kolom
`talent_pool` ikut diperiksa karena sebagian baris pool masih tertulis OPEN di
`status1`.

**Filter rentang tanggal.** Dua kotak tanggal, default **tanggal 1 bulan
berjalan sampai hari ini**. Yang disaring hanya kolom kandidat — MPP, Actual,
dan ADP adalah potret hari ini, bukan kejadian dalam rentang waktu.

Kandidat ikut kalau **rentang aktifnya bersinggungan** dengan rentang yang
dipilih: dari tanggal tahap paling awal sampai tahap paling akhir, atau sampai
hari ini kalau prosesnya masih berjalan. Bukan "yang masuk dalam rentang ini" —
kalau yang dipakai tanggal Screening CV saja, memilih "bulan ini" akan membuang
semua orang yang masuk bulan Juni dan sampai sekarang masih di tahap MCU,
padahal justru merekalah isi kolom *In process* hari ini.

**Level** ditulis sebagai angka di sheet dan diterjemahkan lewat
`config.LEVEL_CODE_NAMES`: 11 Non Staff · 10 Jr. Staff/Foreman · 9 Supervisor ·
8 Superintendent · 7–6 Manager · 5 GM · 4 Deputy Director · 3 Director ·
2 President Director · 1–0 Commissioner. Level 7 dan 6 digabung jadi satu baris
"Manager" — dua baris Manager yang berbeda hanya membingungkan pembaca yang tidak
tahu kode di baliknya.

## SLA per kandidat & estimasi onboarding

**SLA** sekarang dijumlahkan dari lead time TIAP TAHAP, bukan dari selisih
tanggal ujung ke ujung. Kandidat OPEN dan FAILED belum punya tanggal onboarding,
jadi cara lama membuat kolomnya kosong padahal prosesnya jelas sudah memakan
waktu. Hasilnya: terisi untuk **2.205 kandidat**, dari sebelumnya 451.

**Estimate Onboarding** adalah **tanggal**, bukan jumlah hari (arahan Navi,
8 Sep 2026): "11 hari lagi" memaksa pembacanya menghitung sendiri dan hitungannya
salah kalau ada libur di tengah. Sisa harinya **dibulatkan ke atas** — setengah
hari kerja tetap butuh satu hari kerja — lalu dijadikan tanggal memakai kalender
libur yang sama dengan seluruh lead time portal ini, jadi tanggalnya tidak pernah
jatuh di Sabtu, Minggu, atau libur nasional.

Tampil di dua tempat: sebagai **kartu keempat** di Tracking Kandidat (tanggalnya
jadi angka besar, sisa harinya di bawahnya) dan sebagai **kolom tersendiri**
bernama "Estimate Onboarding" di Tracking Posisi (Per Posisi & Per Departemen)
serta di tabel detail Summary by Division. Kolom itu dipisah dari "SLA / target"
supaya keduanya bisa dibaca berdampingan; yang sudah CLOSE atau FAILED ditulis
"selesai", karena perkiraan untuk proses yang sudah berhenti bukan informasi.

Cara hitungnya **dijalani maju tahap demi tahap seperti membaca kalender**
(arahan Navi, 10 Sep 2026):

> Si A sedang di Interview User. Rata-rata Interview User 1 hari, jadi besok
> dia mestinya masuk Psychotest. Rata-rata Psychotest 2 hari, jadi 3 hari dari
> sekarang dia mestinya masuk Offering. Begitu terus sampai Onboarding.

1. tahap yang sedang berjalan menyumbang **rata-ratanya dikurangi hari yang
   sudah terpakai**, minimal nol;
2. tiap tahap berikutnya menambah **rata-ratanya sendiri**, satu per satu,
   sampai One Month Notice selesai.

Yang dipakai adalah **rata-rata seluruh rekrutmen** per tahap — bukan budget
SLA, dan bukan rata-rata PIC kandidat itu. Budget hanya menambal tahap yang
belum pernah ada riwayatnya sama sekali.

Kenapa bukan budget: budget adalah janji, rata-rata adalah kenyataan. Tahap
yang budgetnya 5 hari tapi kenyataannya selalu 12 hari akan terus menghasilkan
perkiraan yang meleset.

Kenapa bukan rata-rata per PIC: perkiraan yang ikut berubah tergantung siapa
PIC-nya membuat dua kandidat di tahap yang sama punya tanggal berbeda tanpa
alasan yang bisa dijelaskan ke pengguna.

Tahap **Onboarding** tidak ikut dihitung: tanggal mulai dan selesainya sama,
dan One Month Notice sudah BERAKHIR di tanggal onboarding — memasukkannya
menambah satu hari palsu di ujung jadwal.

Rata-rata per tahap hari ini: PRF Approval 3,5 · Screening CV 0,6 ·
Interview HR 0,9 · Interview User 1,8 · Technical Test 0,6 · Psychotest 1,7 ·
Offering 5,8 · MCU 3,0 · Review MCU 2,3 · FU MCU 5,7 · One Month Notice 14,2.
Perkiraan rata-rata 33,3 hari kerja untuk 465 kandidat OPEN.

Di Tracking Kandidat, jadwalnya ditampilkan **utuh** sebagai tabel: tiap tahap,
rata-ratanya, hari kumulatif, dan tanggal perkiraannya. Perkiraan tanggal yang
tidak bisa ditelusuri selalu berakhir sebagai angka yang tidak dipercaya siapa
pun; dengan langkahnya terbaca, orang bisa menunjuk tahap mana yang menurutnya
tidak masuk akal.

Rata-ratanya dihitung **per tahap dulu baru dijumlahkan** — bukan semua durasi
dikumpulkan lalu dirata-rata sekali, karena tahap yang datanya banyak akan
menenggelamkan tahap yang datanya sedikit. Yang dipakai adalah kecepatan PIC
kandidat itu sendiri; rata-rata semua orang hanya menambal tahap yang PIC-nya
belum pernah kerjakan.

Tahap yang nomornya lebih kecil dari tahap terjauh yang sudah dijalani tidak
dihitung sebagai sisa — itu tahap yang dilewati atau tanggalnya tidak pernah
diisi (PRF Approval paling sering), dan menghitungnya membuat perkiraannya
kepanjangan.

Di tabel, kolom **SLA / target** selalu terisi: angka kiri hari kerja yang sudah
terpakai (dijumlahkan dari tiap tahap, jadi yang OPEN dan FAILED pun punya
angka), angka kanan abu adalah budget SLA level itu.

## Bahasa antarmuka

Seluruh teks yang dilihat pengguna berbahasa **Inggris** sejak 8 Sep 2026 —
nav, judul section, label kartu, header kolom, filter, catatan penjelas, dan
halaman login. Komentar kode dan docstring tetap bahasa Indonesia: itu catatan
kerja untuk yang merawat portalnya, bukan antarmuka.

Yang TIDAK diterjemahkan dan memang tidak boleh: kunci `session_state`, nama
kolom data (`kandidat`, `ongoing`, `hired`, `pool`, `gagal`), dan nilai yang
datang dari sheet (`TALENT POOL`, nama level, nama departemen). Mengubahnya
memutus data, bukan memperjelas bahasa.

## Tracking Posisi — By Department

Bentuknya disamakan dengan Summary by Division (arahan Navi, 8 Sep 2026): satu
tabel, baris posisi di tingkat atas, klik `[+]` dan **kandidatnya muncul tepat
di bawahnya** dalam kolom yang sama.

Sebelumnya tiap posisi adalah satu expander Streamlit. Plant & Maintenance
punya 79 posisi, dan 79 kotak yang harus dibuka satu-satu bukan tracking, cuma
daftar panjang. Dalam satu tabel, posisi bisa dibandingkan menurun dan
kandidatnya tetap sejangkauan satu klik — tanpa rerun, karena buka-tutupnya
murni CSS.

Kolom hitung (Candidates, In process, Onboarded, Backup, Failed) milik baris
**posisi**; SLA / target, Estimate Onboarding, dan Status milik baris
**kandidat** di bawahnya. Kolom yang tidak berlaku dibiarkan kosong, bukan
diisi tanda hubung yang menambah kebisingan.

## Average to hire

Kartu keempat di Overview. Menggantikan "Median time-to-hire" atas arahan Navi
(8 Sep 2026), dan cara hitungnya memang berbeda, bukan sekadar ganti nama:

> rata-rata SLA screening + rata-rata SLA interview + rata-rata SLA masing-masing
> stage, termasuk routing PRF

Jadi **tiap tahap dirata-rata dulu, baru dijumlahkan** — bukan seluruh durasi
kandidat dikumpulkan lalu dirata-rata sekali. Bedanya nyata: tahap yang datanya
sedikit (Psychotest, Technical Test) akan tenggelam kalau semuanya dicampur,
padahal tahap itu yang paling sering jadi penyebab molor. Dengan cara ini tiap
tahap punya bobot yang sama besar.

Sebelas tahap ikut, dari PRF Approval sampai One Month Notice; Onboarding tidak
dihitung karena tanggal mulai dan selesainya sama. Angka hari ini: **43,3 hari
kerja**. Rinciannya ditulis lengkap di catatan bawah kartu, jadi kalau angkanya
naik, tahap mana yang naik langsung kelihatan.

## Backup candidate

"Talent pool" diganti jadi **backup candidate** di seluruh tampilan. Nilai yang
dicari di kolom Result tetap `TALENT POOL` karena itu yang ditulis form Apps
Script — yang berganti hanya sebutannya (arahan Navi, 7 Sep 2026).

## Achievement dipotong di 120%

Tanpa batas, orang yang kebetulan memegang satu kandidat cepat bisa tampil
2.000% dan membuat kolomnya tidak bisa dibandingkan antar orang — yang tinggi
terbaca sebagai anomali, bukan sebagai prestasi. Batasnya di
`config.ACHIEVEMENT_MAX`.
