# EPUB Browser

> **Ubah buku menjadi situs web. Bangun perpustakaan yang benar-benar milik Anda.**
>
> Publikasikan buku EPUB dan PDF sebagai situs web statis, atau jalankan perpustakaan pribadi
> yang dihosting sendiri dengan akun, kemajuan yang disinkronkan, anotasi, dan pembacaan AI-native opsional.

[Jelajahi perpustakaan statis](https://epub-browser-test.yuhan.tech/) · [Coba perpustakaan pribadi](#demo-langsung)

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/dfface/epub-browser/main/epub_browser/assets/logo-lockup-color.png" alt="Logo EPUB Browser" width="520">
</p>

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![PDF yang ditampilkan dalam pembaca bersama EPUB Browser, dengan halaman asli, navigasi, tema, dan alat baca.](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser lebih dari sekadar konverter buku. Ini adalah platform membaca lengkap yang
dapat dipublikasikan di mana saja atau dihosting sendiri. EPUB dan PDF menggunakan
Perpustakaan, halaman buku, daftar isi, mode membaca, tema, pelacakan kemajuan, dan alur
anotasi yang sama. Setiap halaman PDF menjadi bab pembaca, yang dirender secara lokal oleh
PDF.js dalam pengalaman membaca yang sama—tanpa viewer terpisah dan tanpa CDN saat runtime.

## Daftar isi

- [Ringkasan proyek](#ringkasan-proyek)
  - [Mengapa EPUB Browser](#mengapa-epub-browser)
  - [Tumpukan teknologi](#tumpukan-teknologi)
  - [Pilih SSG atau Server](#pilih-ssg-atau-server)
  - [Demo langsung](#demo-langsung)
  - [Pembacaan AI-native](#pembacaan-ai-native-khusus-server)
  - [Mode minimal Kindle](#mode-minimal-kindle)
- [Memulai](#memulai)
  - [Pilih pemasangan](#pilih-pemasangan)
  - [Mulai cepat](#mulai-cepat)
- [Format dan pembacaan](#format-dan-pembacaan)
  - [Sumber dan identitas buku yang stabil](#sumber-dan-identitas-buku-yang-stabil)
  - [PDF: satu halaman, satu bab](#pdf-satu-halaman-satu-bab)
- [Deployment](#deployment)
  - [SSG](#ssg)
  - [Server](#server)
  - [Docker](#docker)
- [Referensi dan operasi](#referensi-dan-operasi)
  - [Referensi perintah](#referensi-perintah)
  - [Data membaca dan penempatan fitur](#data-membaca-dan-penempatan-fitur)
  - [Server API dan WebHooks](#server-api-dan-webhooks)
  - [Keamanan data dan pemecahan masalah](#keamanan-data-dan-migrasi)
- [Pengembangan dan lisensi](#pengembangan-dan-lisensi)
- [Pusat dokumentasi](../README.md)

## Ringkasan proyek

### Mengapa EPUB Browser

- **Publikasikan di mana saja. Tetap pegang kendali.** Buat situs statis lengkap untuk Pages,
  penyimpanan objek, atau Nginx dengan satu perintah, atau jalankan Server persisten dengan
  akun, izin buku, dan OIDC. Aset aplikasi, font, PDF.js, dan perender disajikan secara lokal,
  sehingga membaca tidak pernah bergantung pada CDN.
- **EPUB dan PDF, satu pembaca yang sesungguhnya.** Kedua format menggunakan Perpustakaan,
  halaman buku, daftar isi, tata letak responsif, tiga mode membaca, tema, layar penuh, dan
  pelacakan kemajuan yang sama. Setiap halaman PDF tetap berada di area membaca, dengan zoom,
  pemilihan lapisan teks, dan anotasi, bukan dalam pratinjau terpisah.
- **Temukan buku—dan kutipannya.** Pencarian Perpustakaan mencakup metadata, tag, dan pinyin,
  dengan pengurutan dan paginasi. Pencarian seluruh buku EPUB di sisi Server menampilkan hasil
  lengkap yang dikelompokkan per bab dan dapat melompat ke kutipan yang disorot. ID buku yang
  stabil menjaga titik lanjut membaca, anotasi, dan riwayat tetap terkait dengan buku yang sama.
- **Pahami, bukan hanya menggulir.** Dalam mode Server, panduan bab EPUB, penjelasan yang
  terhubung ke bukti, peta pikiran, dan Ask AI privat tetap berada di samping teks sumber.
  Sorotan, catatan, Kamus, dan Ensiklopedia berfungsi pada EPUB serta PDF yang memiliki lapisan
  teks; daftar kosakata Server mencatat sumber dan tingkat penguasaan setiap kata.
- **Jadikan kegiatan membaca sebagai riwayat yang layak disimpan.** Rak bertingkat, rating,
  ulasan, ekspor anotasi, kalender aktivitas, tren, statistik per buku, dan peringkat waktu
  membaca membentuk catatan yang saling terhubung. Server menjaga data membaca tetap privat
  untuk setiap akun dan menyinkronkannya antarperangkat.
- **Jalankan layanan membaca, bukan sekadar viewer.** Dalam mode Server, tambahkan buku melalui
  unggahan web administrator atau folder yang dipantau, batasi penggunaan disk dengan pengosongan
  cache LRU yang dapat dikonfigurasi, kelola izin anggota dan AI, serta lakukan integrasi melalui
  OpenAPI, PAT, dan WebHooks. Pembacaan minimal Kindle mendukung perangkat dengan kemampuan
  terbatas; Server juga menyediakan dasbor screen saver Kindle pribadi dengan jam, kalender,
  agenda, memo, dan timer Pomodoro.

![Panduan bab yang disematkan di samping teks EPUB asli, dengan panel Ask AI privat.](assets/ai-native-reading.png)

*Panduan AI-native dan pertanyaan privat tetap terhubung dengan buku aslinya.*

![Tampilan wawasan membaca privat dengan kalender aktivitas dan tren waktu membaca.](assets/reading-insights.png)

*Wawasan membaca mengubah kegiatan membaca aktif menjadi riwayat pribadi yang dapat Anda pahami.*

### Tumpukan teknologi

EPUB Browser sengaja menggunakan tumpukan web kecil yang dirender di server. Aplikasi yang
terpasang tidak memiliki framework SPA dan tidak memerlukan runtime Node.js:

| Lapisan | Teknologi | Peran |
| --- | --- | --- |
| Frontend | HTML semantik, CSS, VanillaJS dengan modul ES dan API peramban | Satu UI responsif bersama untuk SSG dan Server |
| CLI dan Server | Python 3.9+, Starlette, Uvicorn | Perintah konversi, halaman dengan autentikasi, API, dan pekerjaan latar belakang |
| Data | SQLite serta cache konten JSON yang dapat dibangun ulang | Status pengguna tetap terpisah dari konten turunan EPUB/PDF |
| Format buku | lxml, pypdf, pypdfium2, PDF.js | Parsing dan sanitasi EPUB terpadu yang mengutamakan mode ketat, metadata/sampul PDF, rendering lokal di peramban |
| Offline dan aset | Service Worker, aset immutable dengan hash, dependensi vendor yang versinya dikunci | Penyajian mandiri tanpa CDN saat runtime |
| Distribusi | PyPI, Docker, hosting statis biasa | Basis kode yang sama tersedia sebagai SSG atau Server persisten |
| AI opsional | API yang kompatibel dengan OpenAI dengan Markdown, KaTeX, dan Mermaid yang dirender secara lokal | Lapisan pembelajaran EPUB hanya dalam mode Server |

Node.js hanya digunakan oleh maintainer untuk pengujian sisi peramban; Node.js bukan bagian
dari runtime produksi pembaca.

### Pilih SSG atau Server

Pemrosesan sumber dan templat halaman yang sama menjalankan dua mode deployment yang
jelas. Pilih berdasarkan tempat penyimpanan data membaca, bukan berdasarkan format buku:

| Kemampuan | `ssg` | `server` |
| --- | --- | --- |
| EPUB dan PDF | Ya | Ya |
| Penyajian | HTML/aset statis atomik untuk Pages, penyimpanan objek, atau Nginx | Halaman dinamis dengan autentikasi yang didukung cache konten yang dapat diganti |
| Akun dan kontrol akses | Tidak ada | Akun administrator/anggota, pemberian akses buku terbatas, sesi, dan perlindungan CSRF |
| Login tunggal OIDC | Tidak disertakan | Provider generik, penautan akun yang sudah ada, dan penyediaan anggota opsional |
| Kemajuan, anotasi, rak buku | Disimpan di peramban saat ini | Disinkronkan untuk setiap akun yang diautentikasi dalam SQLite |
| Rating, ulasan, sesi membaca | Tidak dihasilkan | Catatan privat per akun dan wawasan membaca |
| Pembaruan sumber | Jalankan `ssg` lagi | Mulai ulang, pindai ulang, atau gunakan `--watch` |
| Administrasi, tag, OpenAPI, WebHooks | Tidak disertakan | Disertakan |
| Pembacaan AI dan Ask AI | Tidak disertakan | Tersedia untuk EPUB bila dikonfigurasi dan diizinkan secara eksplisit; disembunyikan untuk PDF |
| Basis data runtime | Tidak ada | Diperlukan untuk mode persisten |
| Paling sesuai untuk | Hosting publik/statik, bundel offline, penerbitan pribadi sederhana | Perpustakaan pribadi, beberapa perangkat atau pembaca, otomatisasi, dan akses yang dikelola |

Gunakan `ssg` jika hasilnya harus berupa berkas statis biasa. Gunakan `server` jika pembaca memerlukan akun, data lintas perangkat, kontrol akses, atau rekonsiliasi sumber otomatis.

### Demo langsung

- **Mode SSG**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Mode Server**: [epub.yuhan.tech](https://epub.yuhan.tech/) — masuk dengan nama pengguna `demo` dan kata sandi `demo`.

### Pembacaan AI-native (khusus Server)

Untuk buku EPUB, mode Server dapat menambahkan panduan bab, penjelasan yang terhubung
ke bukti, peta pikiran, pertanyaan reflektif, dan panel Ask AI privat tanpa mengalihkan
pembaca dari teks aslinya. Hasil tetap tunduk pada izin buku; setiap anggota harus diberi
izin secara eksplisit, sedangkan SSG tidak memuat kontrol AI, tugas, data akun, atau
konfigurasi provider apa pun. PDF sengaja menyembunyikan pembacaan AI dan Ask AI.

Lihat [panduan pembacaan AI-native](../ai-native-reading.md) untuk model interaksi
lengkap dan [catatan perender rich text lokal](../third-party-ai-renderers.md) untuk
batas rendering dan keamanan jaringan.

### Mode minimal Kindle

Kindle e-Ink lama (dan peramban lain dengan kemampuan terbatas) mendapatkan antarmuka
membaca minimal tanpa dependensi. Aktifkan dengan `--kindle`:

- SSG: `epub-browser ssg --kindle -o output/ SOURCE...`
- Server: `epub-browser server --kindle --server-dir data SOURCE...`

Setiap buku EPUB (buku PDF tidak disertakan) memperoleh tiga halaman tambahan:

- rak minimal `/kindle-library.html`
- halaman buku `/book/<id>/kindle.html`
- halaman bab `/book/<id>/kindle_chapter_N.html`

Halaman ini disesuaikan untuk e-Ink: markup minimal, tema hanya dengan CSS, skrip yang
kompatibel dengan ES5, tanpa Service Worker, dan tanpa framework. Anda dapat membaca tanpa
JavaScript sama sekali; pergantian tema (Terang / Sepia / Gelap), pengaturan ukuran font
(A- / A+), dan pelokalan antarmuka menggunakan skrip inline ringan yang ditambahkan di atas
HTML biasa.

Setiap halaman menyediakan kontrol tema dan font (di header, serta sekali lagi di footer
halaman bab), navigasi daftar isi, bab sebelumnya/berikutnya, dan tautan "Lanjutkan
membaca" yang kembali ke kemajuan tersimpan.

Penyimpanan kemajuan membaca berbeda menurut mode:

- **SSG:** kemajuan disimpan dalam cookie peramban saat ini—lokal, tanpa akun.
- **Server:** kemajuan dan heartbeat membaca disinkronkan untuk setiap akun yang sedang
  masuk ke SQLite. Antarmuka Kindle hanya membaca/melaporkan: mencatat bab saat ini dan
  melaporkan heartbeat, menampilkan rak hanya-baca, serta tidak pernah membuka wawasan
  atau pengelolaan konten.

Kontrol akses diterapkan pada setiap antarmuka Kindle. Buku dengan visibilitas terbatas
mengembalikan 403 kepada pengguna yang tidak berwenang pada rak minimal (buku dihilangkan),
halaman buku dan bab, serta API kemajuan.

Peramban yang didukung (UA berisi `Kindle/`, `Arora/`, dan sebagainya) otomatis dialihkan
dari pembaca lengkap ke halaman minimal; URL di atas juga dapat diakses langsung.
Dengan demikian, mode minimal menjadi fallback yang tetap berfungsi baik pada perangkat
berdaya rendah atau perangkat dengan dukungan JavaScript terbatas.

## Memulai

### Pilih pemasangan

EPUB Browser mendukung dua jalur pemasangan. Keduanya menerima satu atau beberapa berkas
`.epub` atau `.pdf`, direktori bertingkat, atau direktori perpustakaan bergaya Calibre.

| Pemasangan | Gunakan untuk | Persyaratan host |
| --- | --- | --- |
| PyPI | Mode SSG atau Server | Python 3.9 atau lebih baru |
| Docker | Mode Server persisten | Docker Engine; Python sudah termasuk dalam image |

#### PyPI (SSG atau Server)

Pasang aplikasi baris perintah:

```bash
pip install epub-browser
```

Tampilkan referensi perintah untuk setiap mode:

```bash
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

#### Docker (Server)

Image [`dfface/epub-browser`](https://hub.docker.com/r/dfface/epub-browser) yang
diterbitkan menjalankan mode Server dan tidak memerlukan Python di host:

```bash
docker pull dfface/epub-browser:latest
```

Gunakan `latest` untuk mencoba rilis saat ini; kunci tag rilis bernomor untuk deployment
produksi yang dapat diulang. Lihat [Docker](#docker) untuk mount buku dan state yang
wajib, panduan mulai cepat Compose, penyiapan pertama, serta panduan jaringan.

### Mulai cepat

#### Buat situs statis

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

Sajikan `dist/` melalui HTTP. Membuka halaman hasil langsung melalui `file://` tidak didukung karena penyimpanan peramban, modul, manifest, dan Service Worker memerlukan origin HTTP.

Untuk situs yang dihosting di bawah prefiks URL, tetapkan jalur publik secara terpisah dari tujuan filesystem:

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist \
  --base-path /my-repository/
```

`--base-path` mengubah URL yang dihasilkan, bukan lokasi penulisan berkas. Dengan `/my-repository/`, tautan, ikon, manifest, metadata buku, dan entri Service Worker semuanya menggunakan prefiks tersebut, sedangkan berkas tetap berada langsung di dalam `dist/`.

#### Jalankan perpustakaan Server persisten

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

Buka `http://127.0.0.1:8000/`. Pada akses pertama, EPUB Browser meminta Anda membuat administrator awal. Perpustakaan tidak dipindai atau diekspos sebelum penyiapan satu kali ini selesai.

Jika Anda memilih Docker, lewati perintah Python di atas dan lanjutkan dengan
[panduan mulai cepat Docker Compose](#docker-compose).

## Format dan pembacaan

### Sumber dan identitas buku yang stabil

Setiap `SOURCE` posisional dapat berupa berkas EPUB, berkas PDF, atau direktori.
Direktori dicari secara rekursif. Beberapa sumber dapat diberikan dalam satu perintah:

```bash
epub-browser server book.epub /srv/library /srv/periodicals \
  --server-dir /srv/epub-browser \
  --watch
```

Setiap buku memperoleh `book_id` stabil, yang juga ditampilkan sebagai `book_hash` dalam URL yang dihasilkan dan data peramban. Default CLI umum adalah:

```bash
--book-id-storage sidecar
```

Mode sidecar menulis berkas identitas yang terlihat di samping sumber, seperti `BOOK.epub.epub-browser.json` atau `BOOK.pdf.epub-browser.json`, tanpa mengubah byte sumber. Sidecar berisi ID stabil dan sidik jari SHA-256 sumber yang telah diverifikasi.

Untuk menempatkan ID dalam metadata OPF EPUB atau kamus informasi dokumen PDF, pilih penyimpanan embedded untuk seluruh pemanggilan:

```bash
--book-id-storage embedded
```

Mode embedded dapat membangun ulang ZIP EPUB atau menambahkan pembaruan metadata PDF sebelum konversi. Jika PDF tidak dapat diperbarui dan sumbernya tidak berubah, EPUB Browser menyimpan ID yang sama dalam sidecar yang berdekatan. Ini mencakup PDF yang ditandatangani, dienkripsi, dan hanya-baca. EPUB Browser berhenti ketika ID tidak cocok, beberapa sumber aktif menduplikasi suatu ID, pembawa identitas tidak valid, atau pembawa yang diperlukan tidak dapat ditulis.

Saat bermigrasi antarmode penyimpanan, EPUB Browser menyalin ID yang ada ke pembawa yang dipilih dan mempertahankan pembawa lain yang masih valid. ID embedded yang sudah ada dari v2.0.4 disalin ke sidecar default tanpa menulis ulang EPUB. Baik SSG maupun Server menyajikan salinan byte demi byte dari sumber PDF setelah pembaruan metadata apa pun.

### PDF: satu halaman, satu bab

PDF didukung oleh kedua mode deployment. Pembaca memperlakukan setiap halaman PDF sebagai
bab EPUB Browser biasa, sehingga halaman Buku, navigasi bab, daftar isi, paginasi, pembacaan
kontinu, kemajuan, sesi membaca, anotasi, Kamus, dan Ensiklopedia yang sudah ada tetap
menggunakan satu UI dan model data bersama:

| Konsep PDF | SSG | Server |
| --- | --- | --- |
| URL halaman 1 | `chapter_0.html` | `/book/<book-id>/chapter_0.html` |
| URL halaman N | `chapter_{N-1}.html` | `/book/<book-id>/chapter_{N-1}.html` |
| Label halaman dan daftar isi | Dihasilkan secara lokal; setiap halaman dicantumkan | Dirender dari cache metadata PDF; setiap halaman dicantumkan |
| Outline embedded | Penanda pada entri daftar isi halaman tujuannya | Penanda yang sama, tanpa menghapus atau mengubah urutan entri halaman |
| Pengguliran dan paginasi/pembalikan halaman | Shell bab statis dan PDF.js lokal | Shell bab bersama yang dinamis dan PDF.js lokal |
| Sorotan, catatan, Kamus, Ensiklopedia | Komponen bersama yang tersimpan lokal di peramban bila ada lapisan teks | Komponen bersama dengan autentikasi bila ada lapisan teks |
| Byte PDF mentah | Satu `document.pdf` dalam output buku statis | Route dengan dukungan range khusus sesi untuk dokumen dalam cache |

Nomor halaman dimulai dari satu pada label yang terlihat dan PDF.js; indeks bab dimulai
dari nol dalam URL, state, API, dan SQLite. Jadi, halaman PDF 1 selalu menjadi
`chapter_0.html`. Daftar isi yang dinormalisasi menyimpan satu entri `Page N` untuk setiap
halaman; judul outline PDF embedded dilampirkan sebagai penanda outline pada entri
tujuannya, termasuk beberapa penanda pada satu halaman.

SSG menulis satu `document.pdf` dan satu shell `chapter_<index>.html` per halaman.
Output SSG tidak memuat skrip Session, panggilan `/api/*`, data anotasi tersinkronisasi,
atau dependensi Server. Server menyimpan sumber lengkap yang identik byte demi byte sebagai
`book/<book-id>/pdf/document.pdf` dan tidak pernah memecah atau menulis ulang dokumen itu.
Server merender shell bab yang sama secara dinamis dari metadata PDF; sumber yang berubah
membuat cache PDF tidak valid dan menyegarkan seluruh cache (dokumen, metadata, dan sampul
turunan), bukan mencampur halaman lama dan baru.

Endpoint dokumen mentah Server hanya tersedia melalui Session:
`GET`/`HEAD /api/books/<book-id>/document`. Endpoint memeriksa autentikasi, visibilitas
buku, format PDF, serta sidik jari sumber/cache, lalu mendukung respons single-range
terbatas dengan `ETag`, `Accept-Ranges`, caching privat, `nosniff`, dan disposition PDF
inline. Endpoint tidak mengekspos path absolut, tidak tersedia untuk autentikasi PAT, dan
tidak dicantumkan dalam permukaan PAT/OpenAPI. SSG hanya memiliki `document.pdf` lokal dan
tidak memiliki API dokumen mentah.

PDF dengan lapisan teks PDF.js yang dapat digunakan memakai kembali popup pemilihan dan
komponen anotasi yang sama persis untuk Sorotan dan Catatan, serta Kamus dan Ensiklopedia.
Penyimpanan, kepemilikan, ekspor, pencantuman, dan deep link anotasi tetap digunakan bersama;
tidak ada tabel anotasi atau UI pengaturan khusus PDF. PDF hasil pindaian atau yang hanya
berisi gambar tetap dapat dibaca, tetapi Sorotan, Catatan, Kamus, Ensiklopedia, dan pencarian
dokumen berbasis pemilihan secara eksplisit tidak tersedia jika tidak ada lapisan teks yang
dapat digunakan. Pemilihan yang melintasi halaman masih dapat disalin, sedangkan tindakan
anotasi dan pencarian kata menampilkan pesan tidak didukung yang telah dilokalkan; pemilihan
dalam satu halaman tetap berfungsi.

PDF.js bukan shell viewer kedua. Sebelum membangun atau menerbitkan, lengkapi dan verifikasi
aset pihak ketiga yang versinya dikunci:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
```

Aplikasi kemudian menyajikan aset modul dan worker PDF.js lokal dengan hash saat runtime;
aset tersebut tidak pernah diambil dari CDN. Lightbox gambar menggunakan dependensi
GLightbox yang dikunci; Fancyapps/Fancybox bukan dependensi runtime maupun dependensi yang
didistribusikan ulang. Lihat [third_party/README.md](../../third_party/README.md) untuk
alur kerja aset terkunci dan rilis.

## Deployment

### SSG

SSG membangun snapshot lengkap dalam direktori staging yang bersebelahan, memvalidasinya, lalu mengganti tujuan. Jika ada konversi yang gagal, tujuan sebelumnya tetap tidak berubah. Output yang dihasilkan tidak memuat basis data Server, status migrasi, halaman akun, atau metadata cache runtime.

Perilaku SSG sengaja bersifat lokal dan tanpa akun:

- Kemajuan membaca dan anotasi menggunakan penyimpanan peramban pada origin saat ini.
- Rak buku mendukung Impor dan Ekspor JSON lokal; tidak ada tindakan Sinkronisasi cloud.
- Login, pengaturan akun, Server API, dan kontrol yang bergantung pada pengguna tidak disertakan.
- Tujuan penyimpanan ditetapkan ke penyimpanan peramban lokal dan tidak ditampilkan sebagai pengaturan.
- Output statis menyertakan Service Worker yang diperlukan untuk aset yang dapat digunakan offline.

Semua JavaScript, CSS, font, dan ikon aplikasi yang diperlukan disertakan dalam output. Lihat [Kemandirian dan perilaku jaringan](#kemandirian-dan-perilaku-jaringan) untuk satu-satunya permintaan jaringan opsional.

### Server

#### Penyiapan awal, akun, dan izin

Pada direktori state persisten baru, halaman biasa dialihkan ke `/setup`. API, event stream, aset yang dihasilkan, dan buku mengembalikan respons bahwa penyiapan diperlukan sampai administrator awal dibuat. Selesaikan penyiapan melalui loopback atau jalur privat tepercaya lain sebelum mengekspos port: pengiriman penyiapan pertama yang berhasil akan mengklaim akun administrator.

Setelah penyiapan:

- Pendaftaran publik ditutup. Administrator membuat dan mengelola pengguna.
- Akun memiliki peran `administrator` atau `member`.
- Buku biasa terlihat oleh semua akun yang telah diautentikasi.
- Buku terbatas hanya terlihat oleh administrator dan pengguna yang dipilih secara eksplisit.
- Setiap pengguna memiliki rak buku, kemajuan, anotasi, dan sesi aktifnya sendiri.
- Pengguna dapat mengubah kata sandi dan mencabut sesi mereka.
- Administrator dapat mengelola pengguna, peran, kata sandi, sesi, dan pemberian akses buku.
- Sesi menggunakan cookie HttpOnly, perlindungan CSRF, dan masa berlaku bergerak 30 hari.

#### Login tunggal OIDC dan penautan akun

Mode Server dapat menggunakan satu Provider OpenID Connect (OIDC) generik, termasuk
Authelia, Keycloak, Authentik, dan layanan yang kompatibel. Di **Administrasi →
Login OIDC**, masukkan nama Provider yang ditampilkan kepada pembaca, URL issuer,
client ID, client secret, redirect URI yang persis sama, scope, dan claim nama pengguna.
EPUB Browser menggunakan discovery serta alur Authorization Code dengan S256 PKCE,
memvalidasi ID token yang ditandatangani, dan mengidentifikasi akun eksternal hanya melalui
`(issuer, sub)`; claim email dan nama pengguna hanya menjadi petunjuk tampilan/penyediaan,
tidak pernah menjadi kunci identitas.

Daftarkan callback berikut di Provider persis seperti tertulis, termasuk skema dan host:

```text
https://reader.example.com/auth/oidc/callback
```

Pengguna yang sudah ada dapat masuk secara lokal dan menghubungkan Provider dari
pengaturan Akun. Identitas eksternal yang belum dikenal akan diminta satu kali memasukkan
nama pengguna dan kata sandi lokal yang sudah ada. Penyediaan otomatis opsional membuat
anggota tanpa kata sandi; penyediaan ini tidak pernah mengimpor peran administrator. Biarkan
pengguna yang sudah ada menautkan akun terlebih dahulu: mengaktifkan penyediaan otomatis
terlalu awal dapat membuat **akun lokal duplikat**. Login kata sandi **administrator lokal**
selalu tetap tersedia meskipun login kata sandi anggota lokal dinonaktifkan. Pastikan
kredensial pemulihan tersebut telah diuji dan dilindungi. Logout Provider tidak dilakukan,
dan token akses/refresh Provider tidak disimpan.

Untuk Authelia, konfigurasikan confidential client di bagian OIDC Provider. Kutipan
berikut menggunakan nilai palsu yang disengaja dan mengasumsikan kunci serta kebijakan
provider yang diwajibkan Authelia sudah dikonfigurasi. Simpan hash dari client secret acak
yang kuat di Authelia, lalu masukkan secret mentah yang sesuai satu kali di EPUB Browser:

```yaml
identity_providers:
  oidc:
    clients:
      - client_id: 'epub-browser'
        client_name: 'EPUB Browser'
        client_secret: '<AUTHELIA_HASH_OF_A_RANDOM_SECRET>'
        public: false
        authorization_policy: 'two_factor'
        require_pkce: true
        pkce_challenge_method: 'S256'
        redirect_uris:
          - 'https://reader.example.com/auth/oidc/callback'
        scopes: ['openid', 'profile', 'email']
        response_types: ['code']
        grant_types: ['authorization_code']
        token_endpoint_auth_method: 'client_secret_basic'
```

Di EPUB Browser, gunakan issuer `https://auth.example.com`, client ID
`epub-browser`, scope `openid profile email`, dan claim nama pengguna
`preferred_username`. Penyimpanan menjalankan discovery langsung dan validasi kemampuan;
jika gagal, konfigurasi sebelumnya tetap aktif.

#### Konfigurasikan dan kelola pembacaan AI

Administrator mengonfigurasi pembacaan AI di **Administrasi**, tepat setelah
pengelolaan pengguna dan sebelum pengelolaan buku. Halaman tersebut menyimpan
Base URL yang kompatibel dengan OpenAI, API key, model, timeout, anggaran konteks,
batas konkurensi, dan batas harian default panggilan provider dalam basis data SQLite
Server. AI awalnya dinonaktifkan untuk anggota; administrator harus memberikan akses kepada
setiap anggota dan dapat menetapkan batas harian individual (`0` berarti tanpa batas).

Lapisan pembelajaran bab dan ulasan tingkat buku digunakan bersama untuk setiap bahasa yang
memenuhi syarat, sedangkan percakapan lanjutan tetap privat untuk setiap akun. Hasil, status
tugas, tag kustom, klasifikasi bacaan buku, dan percakapan lanjutan privat disimpan dalam
SQLite. Hasil lama tetap tersedia setelah konfigurasi model diubah sampai administrator
secara eksplisit membuatnya ulang.

Ketika pembaca meminta panduan AI atau mengajukan pertanyaan, teks EPUB yang dipilih dan
konteks percakapan yang telah dipadatkan dikirim ke provider eksternal yang dikonfigurasi.
Jangan aktifkan fitur ini kecuali pembaca diizinkan mengirim konten tersebut ke provider.
API key tidak pernah dikembalikan ke peramban atau diekspos melalui API; lindungi direktori
state Server dengan semestinya.

Untuk memulai pertama tanpa pengawasan, sediakan berkas nama pengguna dan kata sandi:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --admin-username admin \
  --admin-password-file /run/secrets/epub-browser-admin-password \
  --no-browser
```

Berkas kata sandi sebaiknya memiliki mode `0600`. EPUB Browser menghapus satu newline di akhir, menyimpan hash Argon2id, dan tidak pernah mencetak secret. Konfigurasi yang tidak lengkap, berkas kosong, atau berkas yang tidak dapat dibaca akan menghentikan startup. Setelah penyiapan selesai, startup berikutnya tidak membaca secret bootstrap.

Padanan environment adalah `EPUB_BROWSER_ADMIN_USERNAME` dan `EPUB_BROWSER_ADMIN_PASSWORD_FILE`. `EPUB_BROWSER_ADMIN_PASSWORD` hanya menjadi fallback plaintext jika tidak ada berkas kata sandi yang dikonfigurasi. Path berkas kata sandi dari CLI memiliki prioritas di atas sumber kata sandi environment.

#### Peluncuran peramban dan logging

Secara default, Server mencoba membuka peramban default sistem operasi setelah listener HTTP dimulai. `--no-browser` mencegah peluncuran lokal tersebut. Opsi ini **tidak menonaktifkan antarmuka web atau akses peramban**; opsi ini hanya menekan panggilan `webbrowser.open(...)` lokal. Gunakan untuk Docker, systemd, sesi SSH, mesin headless, dan skrip.

Secara default (`--log-level error`), CLI hanya mengeluarkan error agar tampilan kemajuan terminal tidak terganggu oleh pesan atau peringatan rutin. Terminal interaktif mencetak URL yang di-bind satu kali; proses Docker dan layanan noninteraktif lainnya tetap tidak mengeluarkan pesan. Gunakan `--log-level warning` untuk menyertakan peringatan, `--log-level info` untuk logging operasional dan akses HTTP, atau `--log-level debug` untuk detail paling lengkap. `--log` tetap menjadi alias kompatibilitas untuk `--log-level info`.

Pemindaian awal dan pemindaian watch muncul di antarmuka web, bukan sebagai `tqdm` di terminal. Ringkasan yang berhasil tertutup otomatis; kegagalan tetap terlihat sampai ditutup. Dengan `--watch`, memperbaiki atau mengganti sumber akan memulai pemindaian lain tanpa tindakan coba lagi manual.

#### State persisten dan sementara

Mode Server persisten memerlukan `--server-dir`. Untuk menjalankan instance sekali pakai, gunakan `--ephemeral`:

```bash
epub-browser server book.epub --ephemeral
```

State sementara dihapus saat shutdown. Karena basis datanya baru pada setiap proses, penyiapan juga diulang kecuali kredensial bootstrap tanpa pengawasan disediakan.

Tata letak persisten:

```text
<server-dir>/
├── .server.lock                 # reusable process-lock metadata
├── data/
│   ├── epub-browser.db          # authoritative accounts, books, grants, reading data
│   ├── migration-state.json     # restart-safe migration state
│   └── backups/                 # verified pre-migration database copies
└── cache/
    ├── catalog.json             # generated-cache status
    ├── public/                  # served application and converted books
    └── staging/                 # replaceable conversion work
```

Hanya `data/` yang bersifat otoritatif. `cache/` dapat dihapus dan akan dibangun ulang. Pertahankan `data/` saat upgrade dan penggantian container. Lock sistem operasi mengatur eksklusivitas; `.server.lock` dapat tetap ada setelah shutdown normal sebagai metadata diagnostik.

Simpan `data/epub-browser.db` persisten pada filesystem lokal. Filesystem bersama atau jaringan tidak didukung untuk konkurensi WAL. Cadangan terverifikasi tetap berada di bawah `data/backups/` dan mencakup semua data WAL yang telah di-commit.

#### LAN dan reverse proxy

Secara default, Server melakukan bind ke `127.0.0.1:8000`. Untuk LAN tepercaya:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --port 8080 \
  --no-browser
```

Jangan ekspos HTTP server bawaan langsung ke internet publik. Terminasi TLS di reverse proxy, terapkan kontrol jaringan, dan aktifkan secure cookie.

Untuk mencatat IP klien sebenarnya dalam sesi aktif dan pembatasan laju login di belakang reverse proxy, konfigurasikan **jaringan socket langsungnya** (bukan rentang klien publik):

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --trusted-proxy-cidr 172.32.11.1/32 \
  --trusted-proxy-cidr 10.42.0.0/16 \
  --cookie-secure \
  --no-browser
```

Ulangi `--trusted-proxy-cidr` satu kali untuk setiap alamat atau jaringan proxy langsung. Hanya permintaan yang peer langsungnya termasuk dalam salah satu CIDR ini yang dapat memberikan `X-Forwarded-For`; semua peer lain hanya mencatat alamat langsungnya. Pemrosesan alamat yang diteruskan oleh Uvicorn dinonaktifkan, sehingga `Forwarded` dan `FORWARDED_ALLOW_IPS` tidak dapat memperluas batas kepercayaan ini. Gunakan `--cookie-secure` hanya jika peramban mengakses layanan melalui HTTPS.

### Docker

Image menjalankan mode Server persisten dengan default berikut:

- `/app/Library` sebagai sumber
- `/app/EpubBrowserFiles` sebagai state persisten
- `--watch`
- `--no-browser`
- `--host 0.0.0.0 --port 80`
- `--book-id-storage embedded`

Karena identitas embedded dapat memperbarui berkas EPUB atau PDF, mount perpustakaan sebagai baca-tulis. Mount state Server sebagai baca-tulis dan pertahankan saat mengganti container:

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  dfface/epub-browser:latest
```

Buka `http://127.0.0.1:8080/setup` sebelum mengubah binding port atau aturan proxy.

#### Docker Compose

Repositori menyertakan [docker-compose.yml](../../docker-compose.yml) bagi pengguna yang lebih memilih Compose. Dari checkout, buat `Library/`, letakkan buku EPUB atau PDF di sana, lalu jalankan:

```bash
docker compose up -d --build
```

Konfigurasi ini hanya menerbitkan `127.0.0.1:8080`, menyimpan buku sumber EPUB/PDF di `./Library`, dan mempertahankan state Server di `./EpubBrowserFiles`. `command` Server lengkap sengaja ditampilkan dalam berkas agar flag khusus deployment dapat ditambahkan tanpa mengganti default image implisit. Selesaikan penyiapan satu kali di `http://127.0.0.1:8080/setup`. Untuk akses jarak jauh, pertahankan binding loopback ini dan tempatkan reverse proxy TLS dengan autentikasi di depannya.

Untuk penyiapan tanpa pengawasan:

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  -e EPUB_BROWSER_ADMIN_USERNAME=admin \
  -e EPUB_BROWSER_ADMIN_PASSWORD_FILE=/run/secrets/epub-browser-admin-password \
  --mount type=bind,src=/path/to/admin-password,dst=/run/secrets/epub-browser-admin-password,readonly \
  dfface/epub-browser:latest
```

Setelah startup pertama berhasil, mount secret satu kali dapat dilepas. Perpustakaan hanya-baca hanya berfungsi jika setiap EPUB sudah memiliki ID embedded valid yang cocok. Sidecar yang sudah ada dipertahankan ketika ID-nya di-embed.

Mount `/app/SyncData:ro` hanya saat mengimpor JSON rak buku lama:

```bash
-v /path/to/legacy-sync:/app/SyncData:ro
```

Port terbitan loopback dalam contoh menjaga container berada di belakang batas host. Untuk akses jarak jauh, gunakan reverse proxy TLS, konfigurasikan CIDR jaringan container yang sebenarnya, dan tambahkan `--cookie-secure`.

## Referensi dan operasi

### Referensi perintah

#### `epub-browser ssg SOURCE [SOURCE ...]`

| Opsi | Arti |
| --- | --- |
| `--output-dir DIR`, `-o DIR` | Tujuan wajib untuk snapshot statis atomik. |
| `--base-path PATH` | Prefiks URL publik; default `/`. Harus diawali dan diakhiri dengan `/`. |
| `--book-id-storage sidecar\|embedded` | Pembawa identitas stabil untuk setiap sumber yang dipilih; default `sidecar`. |
| `--kindle` | Hasilkan halaman minimal tanpa dependensi untuk Kindle e-Ink lama dan alihkan peramban Kindle WebKit ke halaman tersebut; nonaktif secara default. |
| `--log` | Alias kompatibilitas untuk `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Tingkat detail log operasional; default `error`, yang membuat output konversi rutin dan peringatan tidak ditampilkan. |

#### `epub-browser server SOURCE [SOURCE ...]`

Tepat satu dari `--server-dir` dan `--ephemeral` wajib digunakan.

| Opsi | Arti |
| --- | --- |
| `--server-dir DIR` | Root data otoritatif persisten dan cache yang dapat diganti. |
| `--ephemeral` | Gunakan state sekali pakai; saling eksklusif dengan `--server-dir`. |
| `--watch`, `-w` | Pantau sumber dan rekonsiliasi penambahan, pembaruan, pemindahan, serta penghapusan. |
| `--host ADDRESS` | Alamat bind; default `127.0.0.1`. |
| `--port PORT`, `-p PORT` | Port bind; default `8000`. |
| `--no-browser` | Jangan luncurkan peramban default lokal. UI web tetap tersedia. |
| `--log` | Alias kompatibilitas untuk `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Tingkat detail log operasional; default `error`. Log akses HTTP diaktifkan pada `info` dan `debug`. |
| `--legacy-sync-dir DIR` | Baca JSON rak buku lama selama migrasi startup. |
| `--book-id-storage sidecar\|embedded` | Pembawa identitas stabil untuk setiap sumber yang dipilih; default `sidecar`. |
| `--admin-username NAME` | Administrator awal tanpa pengawasan; fallback `EPUB_BROWSER_ADMIN_USERNAME`. |
| `--admin-password-file FILE` | Berkas secret awal yang disarankan; fallback `EPUB_BROWSER_ADMIN_PASSWORD_FILE`, lalu `EPUB_BROWSER_ADMIN_PASSWORD` jika tidak ada berkas yang ditetapkan. |
| `--trusted-proxy-cidr CIDR` | Batas kepercayaan jaringan proxy langsung yang dapat diulang untuk parsing IP klien `X-Forwarded-For` yang aman. |
| `--cookie-secure` | Kirim cookie sesi hanya melalui HTTPS yang diakses peramban. |
| `--kindle` | Sajikan halaman minimal tanpa dependensi untuk Kindle e-Ink lama dan alihkan peramban Kindle WebKit ke halaman tersebut; nonaktif secara default. |

#### Sintaks v1 lama

Sintaks lama didukung di seluruh lini utama v2:

| Perintah v1 | Pemetaan v2 |
| --- | --- |
| `epub-browser BOOKS` | `epub-browser server BOOKS --ephemeral` |
| `epub-browser BOOKS --output-dir STATE` | `epub-browser server BOOKS --server-dir STATE` |
| `epub-browser BOOKS --no-server --output-dir DIST` | `epub-browser ssg BOOKS --output-dir DIST` |
| `--sync-dir DIR` | `server --legacy-sync-dir DIR` |

`--keep-files` khusus versi lama mempertahankan direktori Server sementara. Direktori Server persisten memang sudah permanen. Dengan `--log`, adaptor kompatibilitas mencetak perintah v2 yang setara; tanpa opsi itu, adaptor tidak mengeluarkan pesan.

### Data membaca dan penempatan fitur

- Penemuan rekursif EPUB/PDF dan perpustakaan Calibre, tag metadata, pencarian, serta pencarian pinyin
- Antarmuka Perpustakaan, detail buku, dan pembacaan bab yang responsif
- Pengguliran, pembalikan halaman, pembacaan kontinu, lebar konten yang dapat disesuaikan, font, CSS kustom, tema, dan mode membaca murni
- Sorotan, catatan, penelusuran anotasi, grup rak buku bertingkat, tag, serta Impor/Ekspor JSON
- Dukungan pelokalan antarmuka untuk bahasa Inggris, Tionghoa Sederhana, Tionghoa Tradisional,
  Korea, Jepang, Spanyol, Jerman, Prancis, Rusia, Italia, Portugis Brasil, Arab, Indonesia,
  Hindi, Vietnam, Thai, dan Melayu
- Perilaku yang ramah e-reader untuk peramban Kindle/Silk; fitur yang banyak bergantung pada peramban mungkin dikurangi

| Data | SSG | Server |
| --- | --- | --- |
| Kemajuan membaca | Lokal di peramban | Catatan SQLite pengguna yang diautentikasi |
| Sorotan dan catatan | Lokal di peramban | Catatan SQLite pengguna yang diautentikasi |
| Rating privat, ulasan, dan riwayat sesi membaca | Tidak tersedia | Catatan SQLite pengguna yang diautentikasi |
| Rak buku | Lokal di peramban; Impor/Ekspor | Dokumen cloud berversi milik pengguna yang diautentikasi; penyimpanan otomatis |
| Akun dan sesi | Tidak tersedia | SQLite di bawah `<server-dir>/data` |
| Pemberian akses buku | Tidak tersedia | SQLite di bawah `<server-dir>/data` |

Server tidak menawarkan pemilih penyimpanan lokal/cloud: data membaca pengguna yang diautentikasi selalu disimpan di Server. Riwayat sesi membaca privat yang terperinci tidak pernah dihasilkan oleh SSG. SSG tidak pernah memeriksa Server API dan selalu menggunakan penyimpanan lokal pada origin peramban saat ini.

### Kemandirian dan perilaku jaringan

Aplikasi ini mandiri untuk membaca: JavaScript, CSS, font, ikon, manifest, dan resource EPUB hasil konversi yang diperlukan disajikan secara lokal. Tidak ada dependensi CDN saat runtime. Memblokir akses internet keluar tidak menghalangi penyiapan, login, penelusuran, membaca, anotasi, kemajuan, penggunaan rak buku, administrasi, atau konversi sumber.

Footer dapat membuat permintaan opsional ke GitHub Releases API untuk menemukan versi EPUB Browser yang lebih baru. Kegagalan, pemblokiran, atau penggunaan offline hanya menyembunyikan petunjuk pembaruan tersebut.

SSG menerbitkan Service Worker statis. Server sengaja menonaktifkan dan mempensiunkan Service Worker lingkup origin agar satu akun tidak dapat menerima konten terproteksi milik akun lain dari cache.

### Server API dan WebHooks

Akun Server dapat membuat personal access token dengan cakupan tertentu di pengaturan Akun. Klien eksternal menggunakan `Authorization: Bearer <PAT>` dengan API `/api/v1/*` berversi; cookie peramban tidak mengautentikasi route ini. API mencakup buku dan konten bab yang terlihat, rak buku pemilik token, kemajuan, anotasi dan ulasan, serta data lintas pengguna hanya-baca untuk PAT administrator dengan `admin:data:read`.

Dokumen OpenAPI 3.1 tersedia di `/openapi.json`; pengguna yang sudah masuk dapat membuka referensi lokal di `/api-docs`. Contoh: `curl -H 'Authorization: Bearer …' https://reader.example/api/v1/books`. Detail bab mengembalikan HTML yang telah disanitasi secara default dan teks biasa dengan `?format=text`.

Endpoint daftar mengembalikan `items` dan `next_cursor`. `limit` default adalah 24 dan maksimum 100. Berikan `next_cursor` sebagai `cursor` dengan filter yang sama untuk mengambil halaman berikutnya. Cursor null menandai halaman terakhir. Misalnya, gunakan `/api/v1/me/annotations?book_id=BOOK_ID&chapter_index=0&fields=id,text,note` untuk mengambil field anotasi tertentu dari satu bab EPUB atau halaman PDF. Filter kueri dan field yang didukung tercantum dalam dokumen OpenAPI.

Kosakata menggunakan format daftar yang sama secara default. Klien yang menggunakan respons `words` lama dapat mengirim `page=1` atau `page_size` untuk memilih format paginasi lama.

Administrator mengelola endpoint WebHook di Administrasi. Secret hanya ditampilkan saat dibuat atau dirotasi. Pengiriman ditandatangani, bersifat durable, dicoba ulang untuk respons non-2xx, dan event ulasan buku berisi ID serta timestamp tindakan tetapi tidak pernah menyertakan rating atau teks ulasan.

### Keamanan data dan migrasi

Sebelum mengupgrade instalasi Server persisten, cadangkan buku sumber EPUB/PDF dan `<server-dir>/data`. Pertahankan volume state persisten yang sama saat mengganti container.

Migrasi startup berjalan otomatis dan aman diulang setelah restart. Migrasi memverifikasi basis data lama, membuat cadangan, mengupgrade salinan, mengimpor data rak buku/kemajuan/anotasi lama yang memenuhi syarat ke administrator awal yang masih tertunda, dan mempensiunkan hanya artefak publik lama yang dapat diganti setelah checkpoint berhasil. Permintaan biasa tidak pernah memindai direktori sinkronisasi lama. Basis data rusak, hash kata sandi tidak valid, basis data lama yang ambigu, dan ID yang bertentangan membuat proses berhenti demi keamanan, bukan ditebak atau ditimpa.

`epub-browser.db` atau `annotations.db` hasil migrasi di root dipertahankan sebagai salinan pemulihan sensitif yang tidak otoritatif; `data/epub-browser.db` bersifat otoritatif dan permintaan Server tidak menggunakan berkas root yang dipertahankan. Jaga kerahasiaan salinan pemulihan. Hapus secara manual hanya ketika Server berhenti, setelah memverifikasi basis data otoritatif dan cadangan yang tercatat, serta hanya jika rollback ke v1 tidak lagi diperlukan. EPUB Browser tidak pernah menghapusnya secara otomatis.

Jika `epub-browser.db` dan `annotations.db` sama-sama ada di root lama, startup berhenti dan membiarkan keduanya tidak tersentuh. Lihat [Migrasi ke v2](../migration-v2.md) untuk pencadangan, rollback, pembangunan ulang cache, dan pemulihan konflik.

### Pemecahan masalah

#### Perintah dimulai, tetapi tidak ada peramban yang terbuka

Hapus `--no-browser` saat menjalankan pada mesin lokal dengan antarmuka grafis, atau buka URL yang dicetak/di-bind secara manual. Di Docker, systemd, SSH, dan sesi noninteraktif, Anda memang diharapkan membuka URL sendiri.

#### CLI tampak tidak mengeluarkan pesan

Perilaku tanpa pesan memang disengaja jika tidak menggunakan `--log`, terutama di lingkungan noninteraktif. Tambahkan `--log` untuk detail operasional dan akses. Kemajuan pemindaian Server ditampilkan di antarmuka web.

#### Docker tidak dapat menulis ID stabil

Image menggunakan identitas embedded secara default. Mount `/app/Library` sebagai baca-tulis atau tanamkan terlebih dahulu ID valid yang cocok. Gunakan perintah kustom dengan `--book-id-storage sidecar` hanya jika pembawa sidecar yang dapat ditulis lebih sesuai.

#### Situs SSG yang dihasilkan memiliki tautan rusak di bawah subpath

Hasilkan ulang dengan `--base-path` yang dinormalisasi, seperti `/reader/`, dan konfigurasikan host statis untuk menyajikan output pada prefiks yang sama.

#### Server menolak memulai setelah upgrade

Baca error migrasi atau validasi pertama yang dicatat, pertahankan data dan berkas sumber, lalu baca [docs/migration-v2.md](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/migration-v2.md). Jangan hapus direktori `data/` otoritatif untuk mengatasi error.

## Pengembangan dan lisensi

### Kontribusi

Issues dan pull requests diterima di [dfface/epub-browser](https://github.com/dfface/epub-browser). Laporan yang berguna mencantumkan perintah persisnya, peramban/perangkat, langkah reproduksi, log terkait, serta EPUB atau PDF jika dapat dibagikan secara sah.

#### Kontrak arsitektur maintainer

Baca [AGENTS.md](../../AGENTS.md) sebelum mengubah pemrosesan konten, templat halaman,
cache, izin, aset, atau perilaku deployment. Dokumen tersebut menetapkan batas format
EPUB/PDF, kepemilikan SSG/Server, revisi cache independen, persyaratan i18n runtime,
pemeriksaan keamanan, dan verifikasi yang diwajibkan. Istilah produk bersama seperti
*bab pembaca*, *jendela membaca*, *area membaca*, dan *cache konten* didefinisikan dalam
[CONTEXT.md](../../CONTEXT.md).

Ringkasnya: pertahankan satu UI pembaca, jangan masukkan data khusus Server ke SSG,
pisahkan cache turunan EPUB dan PDF dari data pengguna SQLite, dan jangan pernah
menambahkan dependensi CDN saat runtime. Perubahan yang memengaruhi antarmuka bersama
harus diuji dengan kedua format dan kedua mode deployment jika berlaku.

#### Pengembangan dari checkout sumber

Berkas pihak ketiga untuk peramban merupakan input build yang dihasilkan, bukan sumber
proyek, sehingga `epub_browser/assets/vendor/` sengaja tidak disertakan dalam Git. Lengkapi
versi terkunci yang tepat secara eksplisit sebelum mengembangkan atau membangun, lalu
verifikasi secara offline:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
python3 -m unittest tests.test_vendor_assets -v
python3 -m build
```

`fetch` adalah satu-satunya perintah di atas yang mengunduh aset vendor peramban. Lock
mencatat tarball npm immutable, digest berkas, allowlist, dan lisensi; `verify`, pengujian,
build dari checkout yang telah dilengkapi, dan pembaca yang terpasang tidak mengunduh aset
peramban. Perintah `python3 -m build` terisolasi standar masih dapat menghubungi indeks
paket Python untuk kebutuhan build. Untuk build yang sepenuhnya tanpa jaringan, lengkapi
pohon vendor dan pasang `build`, `setuptools`, serta `wheel` terlebih dahulu sebelum
memutus koneksi, lalu jalankan `PIP_NO_INDEX=1 python3 -m build --no-isolation`. Wheel,
source distribution, image Docker, dan situs SSG yang dihasilkan memuat berkas terverifikasi
serta tidak memiliki dependensi CDN saat runtime. Lihat
[third_party/README.md](../../third_party/README.md) untuk alur kerja pembaruan, rilis,
dan kebersihan repositori.

### Lisensi

[MIT](../../License.txt)
