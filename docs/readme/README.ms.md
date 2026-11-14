# EPUB Browser

> **Ubah buku kepada laman web. Bina perpustakaan milik anda sendiri.**
>
> Terbitkan buku EPUB dan PDF sebagai laman web statik, atau jalankan perpustakaan peribadi
> yang dihoskan sendiri dengan akaun, kemajuan yang disegerakkan, anotasi dan bacaan dengan AI bersepadu sebagai pilihan.

[Terokai perpustakaan statik](https://epub-browser-test.yuhan.tech/) · [Cuba perpustakaan peribadi](#demo-langsung)

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/dfface/epub-browser/main/epub_browser/assets/logo-lockup-color.png" alt="Logo EPUB Browser" width="520">
</p>

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![PDF yang dipaparkan dalam pembaca bersama EPUB Browser, dengan halaman asal, navigasi, tema dan alat bacaan.](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser bukan sekadar penukar buku. Ia ialah platform bacaan lengkap yang boleh
anda terbitkan di mana-mana atau hoskan sendiri. EPUB dan PDF berkongsi Perpustakaan,
halaman buku, isi kandungan, mod bacaan, tema, penjejakan kemajuan dan aliran anotasi yang
sama. Setiap halaman PDF menjadi bab pembaca, yang dipaparkan secara setempat oleh PDF.js
dalam pengalaman bacaan yang sama—tanpa viewer berasingan dan tanpa CDN semasa runtime.

## Isi kandungan

- [Gambaran keseluruhan projek](#gambaran-keseluruhan-projek)
  - [Mengapa EPUB Browser](#mengapa-epub-browser)
  - [Tindanan teknologi](#tindanan-teknologi)
  - [Pilih SSG atau Server](#pilih-ssg-atau-server)
  - [Demo langsung](#demo-langsung)
  - [Bacaan dengan AI bersepadu](#bacaan-dengan-ai-bersepadu-server-sahaja)
  - [Mod minimum Kindle](#mod-minimum-kindle)
- [Bermula](#bermula)
  - [Pilih pemasangan](#pilih-pemasangan)
  - [Mula pantas](#mula-pantas)
- [Format dan bacaan](#format-dan-bacaan)
  - [Sumber dan identiti buku yang stabil](#sumber-dan-identiti-buku-yang-stabil)
  - [PDF: satu halaman, satu bab](#pdf-satu-halaman-satu-bab)
- [Deployment](#deployment)
  - [SSG](#ssg)
  - [Server](#server)
  - [Docker](#docker)
- [Rujukan dan operasi](#rujukan-dan-operasi)
  - [Rujukan perintah](#rujukan-perintah)
  - [Data bacaan dan penempatan ciri](#data-bacaan-dan-penempatan-ciri)
  - [Server API dan WebHooks](#server-api-dan-webhooks)
  - [Keselamatan data dan penyelesaian masalah](#keselamatan-data-dan-migrasi)
- [Pembangunan dan lesen](#pembangunan-dan-lesen)
- [Hab dokumentasi](../README.md)

## Gambaran keseluruhan projek

### Mengapa EPUB Browser

- **Terbitkan di mana-mana. Kekal mengawal.** Bina laman statik lengkap untuk Pages,
  storan objek atau Nginx dengan satu perintah, atau jalankan Server berterusan dengan
  akaun, kebenaran buku dan OIDC. Aset aplikasi, fon, PDF.js dan pemapar disediakan secara
  setempat, jadi bacaan tidak pernah bergantung pada CDN.
- **EPUB dan PDF, satu pembaca untuk kedua-duanya.** Kedua-dua format berkongsi Perpustakaan,
  halaman buku, isi kandungan, susun atur responsif, tiga mod bacaan, tema, skrin penuh dan
  kemajuan. Setiap halaman PDF kekal dalam ruang bacaan, dengan zum, pemilihan teks pada lapisan
  teks dan anotasi, bukannya dalam pratonton berasingan.
- **Cari buku—dan petikan yang diperlukan.** Carian Perpustakaan merangkumi metadata, tag
  dan pinyin, dengan pengisihan serta penomboran halaman. Carian seluruh buku EPUB di bahagian
  Server mengembalikan hasil lengkap yang dikumpulkan mengikut bab dan melompat ke petikan
  yang diserlahkan. ID buku yang stabil memastikan titik sambung bacaan, anotasi dan sejarah
  kekal terikat pada buku yang sama.
- **Fahami kandungan, bukan sekadar menatal.** Dalam mod Server, panduan bab EPUB,
  penerangan yang dipautkan kepada bukti, peta minda dan Ask AI peribadi kekal di sisi teks
  sumber. Serlahan, nota, Kamus dan Ensiklopedia berfungsi pada EPUB serta PDF yang mempunyai
  lapisan teks; senarai kosa kata Server merekodkan sumber dan tahap penguasaan setiap perkataan.
- **Jadikan bacaan sebagai sejarah yang berbaloi disimpan.** Rak bertingkat, penarafan,
  ulasan, eksport anotasi, kalendar aktiviti, trend, statistik setiap buku dan kedudukan masa
  membaca membentuk rekod yang saling berkaitan. Server memastikan data bacaan setiap akaun
  kekal peribadi dan disegerakkan merentas peranti.
- **Jalankan perkhidmatan bacaan, bukan sekadar viewer.** Dalam mod Server, tambah buku melalui
  muat naik web pentadbir atau folder yang dipantau, hadkan penggunaan cakera dengan penyingkiran
  entri cache LRU yang boleh dikonfigurasi, urus kebenaran ahli dan AI, serta buat integrasi melalui
  OpenAPI, PAT dan WebHooks. Bacaan minimum Kindle menyokong peranti terhad; Server turut
  menyediakan papan pemuka screen saver Kindle peribadi dengan jam, kalendar, agenda, memo
  dan pemasa Pomodoro.

![Panduan bab yang dibenamkan di sisi teks EPUB asal, dengan laci Ask AI peribadi.](assets/ai-native-reading.png)

*Panduan dengan AI bersepadu dan soalan peribadi kekal terikat pada buku asal.*

![Paparan cerapan bacaan peribadi dengan kalendar aktiviti dan trend masa membaca.](assets/reading-insights.png)

*Cerapan bacaan menukar bacaan aktif kepada sejarah peribadi yang boleh anda fahami.*

### Tindanan teknologi

EPUB Browser sengaja menggunakan tindanan web kecil yang dijana di pelayan. Aplikasi
yang dipasang tidak mempunyai rangka kerja SPA dan tidak memerlukan runtime Node.js:

| Lapisan | Teknologi | Peranan |
| --- | --- | --- |
| Frontend | HTML semantik, CSS, VanillaJS dengan modul ES dan API pelayar | Satu UI responsif bersama untuk SSG dan Server |
| CLI dan Server | Python 3.9+, Starlette, Uvicorn | Perintah penukaran, halaman berpengesahan, API dan kerja latar belakang |
| Data | SQLite serta cache kandungan JSON yang boleh dibina semula | State pengguna kekal berasingan daripada kandungan terbitan EPUB/PDF |
| Format buku | lxml, pypdf, pypdfium2, PDF.js | Penghuraian dan pembersihan EPUB bersepadu yang mengutamakan mod ketat, metadata/kulit PDF dan pemaparan setempat dalam pelayar |
| Luar talian dan aset | Service Worker, aset immutable dengan hash, dependensi vendor yang dikunci | Penyampaian serba lengkap tanpa CDN semasa runtime |
| Pengedaran | PyPI, Docker, pengehosan statik biasa | Pangkalan kod yang sama tersedia sebagai SSG atau Server berterusan |
| AI pilihan | API serasi OpenAI dengan Markdown, KaTeX dan Mermaid yang dipaparkan secara setempat | Lapisan pembelajaran EPUB dalam mod Server sahaja |

Node.js hanya digunakan oleh penyelenggara untuk ujian bahagian pelayar; ia bukan sebahagian
daripada runtime produksi pembaca.

### Pilih SSG atau Server

Pemprosesan sumber dan templat halaman yang sama menggerakkan dua mod deployment yang
jelas. Pilih berdasarkan tempat data bacaan disimpan, bukan berdasarkan format buku:

| Keupayaan | `ssg` | `server` |
| --- | --- | --- |
| EPUB dan PDF | Ya | Ya |
| Penyampaian | HTML/aset statik atomik untuk Pages, storan objek atau Nginx | Halaman dinamis dengan pengesahan yang disokong oleh cache kandungan boleh ganti |
| Akaun dan kawalan akses | Tiada | Akaun pentadbir/ahli, pemberian akses buku terhad, sesi dan perlindungan CSRF |
| Daftar masuk tunggal OIDC | Tidak disertakan | Provider generik, pemautan akaun sedia ada dan penyediaan ahli pilihan |
| Kemajuan, anotasi, rak buku | Disimpan dalam pelayar semasa | Disegerakkan bagi setiap akaun yang disahkan dalam SQLite |
| Penarafan, ulasan, sesi bacaan | Tidak disertakan dalam output | Rekod peribadi setiap akaun dan cerapan bacaan |
| Kemas kini sumber | Jalankan `ssg` sekali lagi | Mulakan semula, imbas semula atau gunakan `--watch` |
| Pentadbiran, tag, OpenAPI, WebHooks | Tidak disertakan | Disertakan |
| Bacaan AI dan Ask AI | Tidak disertakan | Tersedia untuk EPUB apabila dikonfigurasi dan diberi kebenaran secara eksplisit; disembunyikan untuk PDF |
| Pangkalan data runtime | Tiada | Diperlukan untuk mod berterusan |
| Paling sesuai untuk | Pengehosan awam/statik, bundel luar talian, penerbitan peribadi ringkas | Perpustakaan peribadi, beberapa peranti atau pembaca, automasi dan akses terurus |

Gunakan `ssg` apabila hasilnya mesti berupa fail statik biasa. Gunakan `server` apabila pembaca memerlukan akaun, data merentas peranti, kawalan akses atau penyelarasan sumber automatik.

### Demo langsung

- **Mod SSG**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Mod Server**: [epub.yuhan.tech](https://epub.yuhan.tech/) — log masuk dengan nama pengguna `demo` dan kata laluan `demo`.

### Bacaan dengan AI bersepadu (Server sahaja)

Bagi buku EPUB, mod Server boleh menambah panduan bab, penerangan yang dipautkan kepada
bukti, peta minda, soalan reflektif dan laci Ask AI peribadi tanpa membawa pembaca keluar
daripada teks asal. Hasilnya kekal tertakluk pada kebenaran buku; setiap ahli mesti diberi
kebenaran secara jelas, manakala SSG tidak mengandungi sebarang kawalan AI, tugas, data
akaun atau konfigurasi pembekal. PDF sengaja menyembunyikan bacaan AI dan Ask AI.

Rujuk [panduan bacaan dengan AI bersepadu](../ai-native-reading.md) untuk model interaksi lengkap
dan [nota pemapar teks kaya setempat](../third-party-ai-renderers.md) untuk sempadan
pemaparan serta keselamatan rangkaian.

### Mod minimum Kindle

Kindle e-Ink lama (dan mana-mana pelayar terhad) mendapat antara muka bacaan minimum
tanpa dependensi. Aktifkannya dengan `--kindle`:

- SSG: `epub-browser ssg --kindle -o output/ SOURCE...`
- Server: `epub-browser server --kindle --server-dir data SOURCE...`

Setiap buku EPUB (buku PDF tidak disertakan) memperoleh tiga halaman tambahan:

- rak minimum `/kindle-library.html`
- halaman buku `/book/<id>/kindle.html`
- halaman bab `/book/<id>/kindle_chapter_N.html`

Halaman ini diselaraskan untuk e-Ink: markup minimum, tema menggunakan CSS sahaja, skrip
serasi ES5, tiada Service Worker dan tiada rangka kerja. Anda boleh membaca tanpa sebarang
JavaScript; penukaran tema (Cerah / Sepia / Gelap), saiz fon (A- / A+) dan pelokalan antara
muka menggunakan skrip inline ringan yang dilapiskan pada HTML biasa.

Setiap halaman menawarkan kawalan tema dan fon (di pengepala, serta sekali lagi di pengaki
halaman bab), navigasi kandungan, bab sebelumnya/seterusnya dan pautan "Sambung membaca"
yang menyambung semula daripada kemajuan tersimpan.

Kemajuan bacaan berbeza mengikut mod:

- **SSG:** kemajuan disimpan dalam kuki pelayar semasa—setempat, tanpa akaun.
- **Server:** kemajuan dan heartbeat bacaan disegerakkan ke dalam SQLite bagi setiap akaun
  yang telah log masuk. Antara muka Kindle hanya membaca/melapor: ia merekodkan bab semasa dan
  melaporkan heartbeat, memaparkan rak buku baca sahaja, serta tidak pernah memaparkan cerapan
  atau pengurusan kandungan.

Kawalan akses dikuatkuasakan pada setiap antara muka Kindle. Buku dengan keterlihatan
terhad mengembalikan 403 kepada pengguna yang tidak dibenarkan pada rak minimum
(diketepikan), halaman buku dan bab, serta API kemajuan.

Pelayar yang disokong (UA yang mengandungi `Kindle/`, `Arora/` dan sebagainya) dialihkan
secara automatik daripada pembaca penuh ke halaman minimum; URL di atas juga berfungsi
secara langsung. Ini menjadikan mod minimum sebagai fallback yang berfungsi dengan baik
untuk peranti berkuasa rendah atau peranti dengan JavaScript terhad.

## Bermula

### Pilih pemasangan

EPUB Browser menyokong dua laluan pemasangan. Kedua-duanya menerima satu atau lebih fail
`.epub` atau `.pdf`, direktori bersarang atau direktori perpustakaan gaya Calibre.

| Pemasangan | Gunakan untuk | Keperluan hos |
| --- | --- | --- |
| PyPI | Mod SSG atau Server | Python 3.9 atau lebih baharu |
| Docker | Mod Server berterusan | Docker Engine; Python disertakan dalam imej |

#### PyPI (SSG atau Server)

Pasang aplikasi baris perintah:

```bash
pip install epub-browser
```

Paparkan rujukan perintah khusus mod:

```bash
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

#### Docker (Server)

Imej [`dfface/epub-browser`](https://hub.docker.com/r/dfface/epub-browser) yang
diterbitkan menjalankan mod Server dan tidak memerlukan Python pada hos:

```bash
docker pull dfface/epub-browser:latest
```

Gunakan `latest` untuk mencuba keluaran semasa; kunci tag keluaran bernombor bagi deployment
production yang boleh diulang. Rujuk [Docker](#docker) untuk lekapan buku dan state yang
diperlukan, panduan mula pantas Compose, persediaan kali pertama dan panduan rangkaian.

### Mula pantas

#### Jana laman statik

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

Sediakan `dist/` melalui HTTP. Membuka halaman yang dijana secara langsung melalui `file://` tidak disokong kerana storan pelayar, modul, manifest dan Service Worker memerlukan origin HTTP.

Bagi laman yang dihoskan di bawah awalan URL, tetapkan laluan awam secara berasingan daripada destinasi sistem fail:

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist \
  --base-path /my-repository/
```

`--base-path` mengubah URL yang dijana, bukan tempat fail ditulis. Dengan `/my-repository/`, pautan, ikon, manifest, metadata buku dan entri Service Worker semuanya menggunakan awalan tersebut, manakala fail kekal terus di dalam `dist/`.

#### Jalankan perpustakaan Server berterusan

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

Buka `http://127.0.0.1:8000/`. Pada akses pertama, EPUB Browser akan meminta anda mencipta pentadbir awal. Perpustakaan tidak diimbas atau didedahkan sehingga persediaan sekali sahaja ini selesai.

Jika anda memilih Docker, langkau perintah Python di atas dan teruskan dengan
[panduan mula pantas Docker Compose](#docker-compose).

## Format dan bacaan

### Sumber dan identiti buku yang stabil

Setiap argumen `SOURCE` boleh berupa fail EPUB, fail PDF atau direktori.
Direktori diimbas secara rekursif. Beberapa sumber boleh diberikan kepada satu perintah:

```bash
epub-browser server book.epub /srv/library /srv/periodicals \
  --server-dir /srv/epub-browser \
  --watch
```

Setiap buku menerima `book_id` yang stabil, turut didedahkan sebagai `book_hash` dalam URL yang dijana dan data pelayar. Lalai CLI umum ialah:

```bash
--book-id-storage sidecar
```

Mod sidecar menulis fail identiti yang kelihatan di sebelah sumber, seperti `BOOK.epub.epub-browser.json` atau `BOOK.pdf.epub-browser.json`, dan tidak mengubah bait sumber. Sidecar itu mengandungi ID stabil dan cap jari SHA-256 sumber yang telah disahkan.

Untuk meletakkan ID dalam metadata OPF EPUB atau kamus maklumat dokumen PDF, pilih storan embedded bagi keseluruhan pemanggilan:

```bash
--book-id-storage embedded
```

Mod embedded boleh membina semula ZIP EPUB atau menambahkan kemas kini metadata PDF sebelum penukaran. Jika PDF tidak dapat dikemas kini dan sumbernya tidak berubah, EPUB Browser menyimpan ID yang sama dalam sidecar bersebelahan. Ini termasuk PDF yang ditandatangani, disulitkan dan baca sahaja. EPUB Browser berhenti apabila ID tidak sepadan, beberapa sumber aktif menggunakan ID yang sama, media penyimpanan ID tidak sah atau media penyimpanan yang diperlukan tidak dapat ditulis.

Semasa berhijrah antara mod storan, EPUB Browser menyalin ID sedia ada kepada media penyimpanan yang dipilih dan mengekalkan media lain yang sah. ID embedded sedia ada daripada v2.0.4 disalin ke sidecar lalai tanpa menulis semula EPUB. Kedua-dua SSG dan Server menyediakan salinan sumber PDF bait demi bait selepas sebarang kemas kini metadata.

### PDF: satu halaman, satu bab

PDF disokong oleh kedua-dua mod deployment. Pembaca menganggap setiap halaman PDF sebagai
bab EPUB Browser biasa, jadi halaman Buku, navigasi bab, isi kandungan, penomboran halaman,
bacaan berterusan, kemajuan, sesi bacaan, anotasi, Kamus dan Ensiklopedia sedia ada kekal
menggunakan satu UI dan model data bersama:

| Konsep PDF | SSG | Server |
| --- | --- | --- |
| URL halaman 1 | `chapter_0.html` | `/book/<book-id>/chapter_0.html` |
| URL halaman N | `chapter_{N-1}.html` | `/book/<book-id>/chapter_{N-1}.html` |
| Label halaman dan isi kandungan | Dijana secara setempat; setiap halaman disenaraikan | Dipaparkan daripada cache metadata PDF; setiap halaman disenaraikan |
| Outline embedded | Penanda pada entri isi kandungan halaman destinasi | Penanda yang sama, tanpa mengeluarkan atau menyusun semula entri halaman |
| Penatalan dan penomboran/pembalikan halaman | Shell bab statik dan PDF.js setempat | Shell bab bersama yang dinamis dan PDF.js setempat |
| Serlahan, nota, Kamus, Ensiklopedia | Komponen bersama setempat dalam pelayar apabila lapisan teks wujud | Komponen bersama untuk pengguna yang disahkan apabila lapisan teks wujud |
| Bait PDF mentah | Satu `document.pdf` dalam output buku statik | Route khusus Session yang menyokong Range untuk dokumen dalam cache |

Nombor halaman bermula daripada satu pada label yang kelihatan dan PDF.js; indeks bab
bermula daripada sifar dalam URL, state, API dan SQLite. Oleh itu, halaman PDF 1 sentiasa
menjadi `chapter_0.html`. Isi kandungan yang dinormalkan mengekalkan satu entri `Page N` bagi
setiap halaman; tajuk outline PDF embedded dilampirkan sebagai penanda outline pada entri
destinasinya, termasuk beberapa penanda pada satu halaman.

SSG menulis satu `document.pdf` dan satu shell `chapter_<index>.html` bagi setiap
halaman. Output SSG tidak mengandungi skrip Session, panggilan `/api/*`, data anotasi
yang disegerakkan atau dependensi Server. Server menyimpan sumber lengkap yang identik
bait demi bait sebagai `book/<book-id>/pdf/document.pdf` dan tidak pernah memecahkan atau
menulis semula dokumen itu. Server memaparkan shell bab yang sama secara dinamis daripada
metadata PDF; sumber yang berubah akan membatalkan kesahihan cache PDF dan menyegarkan
keseluruhannya (dokumen, metadata dan kulit yang dijana), bukannya mencampurkan halaman lama
dengan baharu.

Endpoint dokumen mentah Server ialah khusus Session:
`GET`/`HEAD /api/books/<book-id>/document`. Ia menyemak pengesahan, keterlihatan buku,
format PDF serta cap jari sumber/cache, kemudian menyokong respons single-range terhad
dengan `ETag`, `Accept-Ranges`, caching peribadi, `nosniff` dan disposition PDF inline.
Ia tidak mendedahkan laluan mutlak, tidak tersedia untuk pengesahan PAT dan tidak
disenaraikan dalam API PAT/OpenAPI. SSG hanya mempunyai `document.pdf` setempat
dan tiada API dokumen mentah.

PDF dengan lapisan teks PDF.js yang boleh digunakan menggunakan semula popup pemilihan
dan komponen anotasi sedia ada yang sama untuk Serlahan dan Nota, serta Kamus dan Ensiklopedia.
Storan, pemilikan, eksport, penyenaraian dan deep link anotasi kekal dikongsi; tiada jadual
anotasi atau UI tetapan khusus PDF. PDF imbasan atau PDF yang hanya mengandungi imej masih
boleh dibaca, tetapi Serlahan, Nota, Kamus, Ensiklopedia dan carian dokumen berasaskan
pemilihan secara jelas tidak tersedia apabila tiada lapisan teks yang boleh digunakan.
Pemilihan yang merentasi halaman masih boleh disalin, manakala tindakan anotasi dan carian
kata memaparkan mesej tidak disokong yang telah dilokalkan; pemilihan dalam satu halaman
terus berfungsi.

PDF.js bukan shell viewer kedua. Sebelum membina atau menerbitkan, sediakan dan sahkan
aset pihak ketiga yang dikunci:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
```

Aplikasi kemudiannya menyediakan aset modul dan worker PDF.js setempat dengan hash semasa
runtime; aset itu tidak pernah diambil daripada CDN. Lightbox imej menggunakan dependensi
GLightbox yang dikunci; Fancyapps/Fancybox bukan dependensi runtime atau dependensi yang
diedarkan semula. Rujuk [third_party/README.md](../../third_party/README.md) untuk aliran
kerja untuk aset berkunci dan keluaran.

## Deployment

### SSG

SSG membina snapshot lengkap dalam direktori staging yang bersebelahan, mengesahkannya, kemudian menggantikan destinasi. Jika mana-mana penukaran gagal, destinasi sebelumnya kekal tidak berubah. Output yang dijana tidak mengandungi pangkalan data Server, state migrasi, halaman akaun atau metadata cache runtime.

Tingkah laku SSG sengaja bersifat setempat dan tanpa akaun:

- Kemajuan bacaan dan anotasi menggunakan storan pelayar pada origin semasa.
- Rak buku menyokong Import dan Eksport JSON setempat; ia tidak mempunyai tindakan Sync awan.
- Log masuk, tetapan akaun, Server API dan kawalan yang bergantung pada pengguna tidak disertakan.
- Destinasi storan ditetapkan kepada storan pelayar setempat dan tidak dipaparkan sebagai tetapan.
- Output statik menyertakan Service Worker yang diperlukan supaya aset boleh digunakan di luar talian.

Semua JavaScript, CSS, fon dan ikon aplikasi yang diperlukan disertakan dalam output. Rujuk [Aset serba lengkap dan tingkah laku rangkaian](#aset-serba-lengkap-dan-tingkah-laku-rangkaian) untuk satu-satunya permintaan rangkaian pilihan.

### Server

#### Persediaan awal, akaun dan kebenaran

Pada direktori state berterusan baharu, halaman biasa dialihkan ke `/setup`. API, event stream, aset yang dijana dan buku mengembalikan respons bahawa persediaan diperlukan sehingga pentadbir awal dicipta. Selesaikan persediaan melalui loopback atau laluan peribadi dipercayai yang lain sebelum mendedahkan port: penghantaran persediaan pertama yang berjaya akan menuntut akaun pentadbir.

Selepas persediaan:

- Pendaftaran awam ditutup. Pentadbir mencipta dan mengurus pengguna.
- Akaun mempunyai peranan `administrator` atau `member`.
- Buku biasa kelihatan kepada setiap akaun yang disahkan.
- Buku terhad hanya kelihatan kepada pentadbir dan pengguna yang dipilih secara jelas.
- Setiap pengguna memiliki rak buku, kemajuan, anotasi dan sesi aktifnya sendiri.
- Pengguna boleh menukar kata laluan dan membatalkan sesi mereka.
- Pentadbir boleh mengurus pengguna, peranan, kata laluan, sesi dan pemberian akses buku.
- Sesi menggunakan kuki HttpOnly, perlindungan CSRF dan tempoh hayat bergerak 30 hari.

#### Daftar masuk tunggal OIDC dan pemautan akaun

Mod Server boleh menggunakan satu Provider OpenID Connect (OIDC) generik, termasuk
Authelia, Keycloak, Authentik dan perkhidmatan yang serasi. Dalam **Pentadbiran →
Log masuk OIDC**, masukkan nama Provider yang dipaparkan kepada pembaca, URL issuer,
client ID, client secret, redirect URI yang tepat, scope dan claim nama pengguna.
EPUB Browser menggunakan discovery bersama aliran Authorization Code dengan S256 PKCE,
mengesahkan ID token yang ditandatangani dan mengenal pasti akaun luaran hanya melalui
`(issuer, sub)`; claim e-mel dan nama pengguna hanyalah petunjuk paparan/penyediaan,
dan tidak pernah menjadi kunci identiti.

Daftarkan callback yang tepat ini pada Provider, termasuk skema dan hos:

```text
https://reader.example.com/auth/oidc/callback
```

Pengguna sedia ada boleh log masuk secara setempat dan menyambungkan Provider daripada
tetapan Akaun. Identiti luaran yang tidak dikenali akan diminta sekali sahaja memasukkan
nama pengguna dan kata laluan setempat sedia ada. Penyediaan automatik pilihan mencipta
ahli tanpa kata laluan; ia tidak pernah mengimport peranan pentadbir. Benarkan pengguna
sedia ada memautkan akaun dahulu: mengaktifkan penyediaan automatik terlalu awal boleh
mencipta **akaun setempat pendua**. Log masuk kata laluan **pentadbir setempat** sentiasa
kekal tersedia walaupun log masuk kata laluan ahli setempat dinyahaktifkan. Pastikan
kelayakan pemulihan itu telah diuji dan dilindungi. Log keluar Provider tidak dilakukan,
dan token akses/refresh Provider tidak disimpan.

Bagi Authelia, konfigurasikan confidential client dalam bahagian OIDC Provider. Petikan
berikut menggunakan nilai palsu yang disengajakan dan menganggap kunci serta dasar
provider yang diperlukan Authelia telah dikonfigurasi. Simpan hash bagi client secret
rawak yang kukuh dalam Authelia, kemudian masukkan secret mentah yang sepadan sekali
sahaja dalam EPUB Browser:

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

Dalam EPUB Browser, gunakan issuer `https://auth.example.com`, client ID
`epub-browser`, scope `openid profile email` dan claim nama pengguna
`preferred_username`. Apabila anda menyimpan, EPUB Browser menjalankan discovery secara
langsung dan mengesahkan keupayaan; jika gagal, konfigurasi sebelumnya kekal aktif.

#### Konfigurasikan dan urus bacaan AI

Pentadbir mengkonfigurasi bacaan AI dalam **Pentadbiran**, sejurus selepas
pengurusan pengguna dan sebelum pengurusan buku. Halaman ini menyimpan Base URL
serasi OpenAI, API key, model, timeout, belanjawan konteks, had keserempakan dan
had harian lalai panggilan pembekal dalam pangkalan data SQLite Server. AI bermula
dalam keadaan dinyahaktifkan untuk ahli; pentadbir mesti memberikan akses kepada setiap
ahli dan boleh menetapkan had harian individu (`0` bermakna tanpa had).

Lapisan pembelajaran bab dan ulasan peringkat buku dikongsi bagi setiap bahasa yang
layak, manakala perbualan susulan kekal peribadi untuk setiap akaun. Hasil, state tugas,
tag tersuai, klasifikasi bacaan buku dan susulan peribadi disimpan dalam SQLite. Hasil
lama kekal tersedia selepas konfigurasi model berubah sehingga pentadbir memilih untuk
menjana semula hasil tersebut.

Apabila pembaca meminta panduan AI atau mengemukakan soalan, teks EPUB yang dipilih dan
konteks perbualan yang dimampatkan dihantar kepada pembekal luaran yang dikonfigurasi.
Jangan aktifkan ciri ini melainkan pembaca dibenarkan menghantar kandungan tersebut kepada
pembekal. API key tidak pernah dikembalikan kepada pelayar atau didedahkan melalui API;
lindungi direktori state Server dengan sewajarnya.

Untuk permulaan pertama tanpa interaksi, sediakan nama pengguna dan fail kata laluan:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --admin-username admin \
  --admin-password-file /run/secrets/epub-browser-admin-password \
  --no-browser
```

Fail kata laluan seharusnya menggunakan mod `0600`. EPUB Browser membuang satu newline di hujung, menyimpan hash Argon2id dan tidak pernah mencetak secret. Konfigurasi tidak lengkap, fail kosong atau fail yang tidak dapat dibaca akan menghentikan permulaan. Selepas persediaan selesai, permulaan berikutnya tidak membaca secret bootstrap.

Padanan environment ialah `EPUB_BROWSER_ADMIN_USERNAME` dan `EPUB_BROWSER_ADMIN_PASSWORD_FILE`. `EPUB_BROWSER_ADMIN_PASSWORD` hanya menjadi fallback plaintext apabila tiada fail kata laluan dikonfigurasi. Laluan fail kata laluan CLI mendapat keutamaan berbanding sumber kata laluan environment.

#### Pelancaran pelayar dan pengelogan

Secara lalai, Server cuba membuka pelayar lalai sistem operasi selepas listener HTTP dimulakan. `--no-browser` menghalang pelancaran setempat itu. Ia **tidak menyahaktifkan antara muka web atau akses pelayar**; ia hanya menyekat panggilan `webbrowser.open(...)` setempat. Gunakannya untuk Docker, systemd, sesi SSH, mesin headless dan skrip.

Secara lalai (`--log-level error`), CLI hanya mengeluarkan ralat supaya paparan kemajuan terminal tidak diganggu oleh mesej atau amaran rutin. Terminal interaktif mencetak URL yang di-bind sekali; proses Docker dan perkhidmatan tidak interaktif pula kekal senyap. Gunakan `--log-level warning` untuk menyertakan amaran, `--log-level info` untuk log operasi dan akses HTTP, atau `--log-level debug` untuk perincian paling lengkap. `--log` kekal sebagai alias keserasian untuk `--log-level info`.

Imbasan awal dan imbasan watch dipaparkan dalam antara muka web dan bukannya `tqdm` terminal. Ringkasan yang berjaya ditutup secara automatik; kegagalan kekal kelihatan sehingga diketepikan. Dengan `--watch`, membaiki atau menggantikan sumber akan memulakan imbasan lain tanpa tindakan cuba semula manual.

#### State berterusan dan sementara

Mod Server berterusan memerlukan `--server-dir`. Untuk proses sekali pakai, gunakan `--ephemeral`:

```bash
epub-browser server book.epub --ephemeral
```

State sementara dipadam semasa penutupan. Oleh sebab pangkalan datanya baharu pada setiap proses, persediaan turut diulang melainkan kelayakan bootstrap untuk permulaan automatik disediakan.

Susun atur berterusan:

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

Hanya `data/` menjadi sumber data utama. `cache/` boleh dipadam dan akan dibina semula. Kekalkan `data/` merentas peningkatan versi dan penggantian kontena. Kunci sistem operasi mengawal akses eksklusif; `.server.lock` mungkin kekal selepas penutupan normal sebagai metadata diagnostik.

Simpan `data/epub-browser.db` berterusan pada sistem fail setempat. Sistem fail kongsi atau rangkaian tidak disokong untuk keserempakan WAL. Sandaran yang disahkan kekal di bawah `data/backups/` dan merangkumi semua data WAL yang telah di-commit.

#### LAN dan proksi songsang

Secara lalai, Server melakukan bind pada `127.0.0.1:8000`. Untuk LAN yang dipercayai:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --port 8080 \
  --no-browser
```

Jangan dedahkan pelayan HTTP terbina dalam terus kepada Internet awam. Tamatkan TLS pada proksi songsang, gunakan kawalan rangkaian dan aktifkan kuki selamat.

Untuk merekodkan IP klien sebenar dalam sesi aktif dan had kadar log masuk di belakang proksi songsang, konfigurasikan **rangkaian soket langsungnya** (bukan julat klien awam):

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

Ulang `--trusted-proxy-cidr` sekali bagi setiap alamat atau rangkaian proksi langsung. Hanya permintaan yang peer langsungnya tergolong dalam salah satu CIDR ini boleh memberikan `X-Forwarded-For`; semua peer lain hanya merekodkan alamat langsungnya. Pemprosesan alamat yang diteruskan oleh Uvicorn dinyahaktifkan, jadi `Forwarded` dan `FORWARDED_ALLOW_IPS` tidak boleh meluaskan sempadan kepercayaan ini. Gunakan `--cookie-secure` hanya apabila pelayar mengakses perkhidmatan melalui HTTPS.

### Docker

Imej menjalankan mod Server berterusan dengan lalai berikut:

- `/app/Library` sebagai sumber
- `/app/EpubBrowserFiles` sebagai state berterusan
- `--watch`
- `--no-browser`
- `--host 0.0.0.0 --port 80`
- `--book-id-storage embedded`
- `--kindle`

Oleh sebab identiti embedded boleh mengemas kini fail EPUB atau PDF, lekapkan perpustakaan sebagai baca-tulis. Lekapkan state Server sebagai baca-tulis dan kekalkannya semasa menggantikan kontena:

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  dfface/epub-browser:latest
```

Lawati `http://127.0.0.1:8080/setup` sebelum mengubah pengikatan port atau peraturan proksi.

#### Docker Compose

Repositori menyertakan [docker-compose.yml](../../docker-compose.yml) untuk pengguna yang memilih Compose. Daripada checkout, cipta `Library/`, letakkan buku EPUB atau PDF di situ, kemudian jalankan:

```bash
docker compose up -d --build
```

Konfigurasi ini hanya menerbitkan `127.0.0.1:8080`, menyimpan buku sumber EPUB/PDF dalam `./Library` dan mengekalkan state Server dalam `./EpubBrowserFiles`. `command` Server lengkap sengaja dipaparkan dalam fail supaya bendera khusus deployment boleh ditambah tanpa menggantikan lalai imej implisit. Selesaikan persediaan sekali sahaja di `http://127.0.0.1:8080/setup`. Untuk akses jauh, kekalkan pengikatan loopback ini dan letakkan proksi songsang TLS berpengesahan di hadapannya.

Untuk persediaan tanpa interaksi:

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

Selepas permulaan pertama berjaya, lekapan secret sekali sahaja boleh dikeluarkan. Perpustakaan baca sahaja hanya berfungsi apabila setiap EPUB telah mengandungi ID embedded sah yang sepadan. Sidecar sedia ada dikekalkan apabila ID-nya dibenamkan.

Lekapkan `/app/SyncData:ro` hanya semasa mengimport JSON rak buku legasi:

```bash
-v /path/to/legacy-sync:/app/SyncData:ro
```

Port terbitan loopback dalam contoh memastikan kontena berada di belakang sempadan hos. Untuk akses jauh, gunakan proksi songsang TLS, konfigurasikan CIDR rangkaian kontena sebenar dan tambah `--cookie-secure`.

## Rujukan dan operasi

### Rujukan perintah

#### `epub-browser ssg SOURCE [SOURCE ...]`

| Pilihan | Maksud |
| --- | --- |
| `--output-dir DIR`, `-o DIR` | Destinasi wajib untuk snapshot statik atomik. |
| `--base-path PATH` | Awalan URL awam; lalai `/`. Ia mesti bermula dan berakhir dengan `/`. |
| `--book-id-storage sidecar\|embedded` | Media penyimpanan identiti stabil bagi setiap sumber yang dipilih; lalai `sidecar`. |
| `--kindle` | Jana halaman minimum tanpa dependensi untuk Kindle e-Ink lama dan alihkan pelayar Kindle WebKit ke halaman tersebut; tidak aktif secara lalai. |
| `--log` | Alias keserasian untuk `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Tahap perincian log operasi; lalai `error`, yang memastikan output penukaran rutin dan amaran tidak dipaparkan. |

#### `epub-browser server SOURCE [SOURCE ...]`

Hanya satu daripada `--server-dir` dan `--ephemeral` mesti dinyatakan.

| Pilihan | Maksud |
| --- | --- |
| `--server-dir DIR` | Akar bagi data utama berterusan dan cache yang boleh diganti. |
| `--ephemeral` | Gunakan state sekali pakai; saling eksklusif dengan `--server-dir`. |
| `--watch`, `-w` | Pantau sumber dan selaraskan penambahan, kemas kini, pemindahan serta pemadaman. |
| `--host ADDRESS` | Alamat bind; lalai `127.0.0.1`. |
| `--port PORT`, `-p PORT` | Port bind; lalai `8000`. |
| `--no-browser` | Jangan lancarkan pelayar lalai setempat. UI web kekal tersedia. |
| `--log` | Alias keserasian untuk `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Tahap perincian log operasi; lalai `error`. Log akses HTTP diaktifkan pada `info` dan `debug`. |
| `--legacy-sync-dir DIR` | Baca JSON rak buku legasi semasa migrasi permulaan. |
| `--book-id-storage sidecar\|embedded` | Media penyimpanan identiti stabil bagi setiap sumber yang dipilih; lalai `sidecar`. |
| `--admin-username NAME` | Pentadbir awal untuk persediaan tanpa interaksi; fallback `EPUB_BROWSER_ADMIN_USERNAME`. |
| `--admin-password-file FILE` | Fail secret awal pilihan; fallback `EPUB_BROWSER_ADMIN_PASSWORD_FILE`, kemudian `EPUB_BROWSER_ADMIN_PASSWORD` apabila tiada fail ditetapkan. |
| `--trusted-proxy-cidr CIDR` | Sempadan kepercayaan rangkaian proksi langsung yang boleh diulang untuk penghuraian IP klien `X-Forwarded-For` yang selamat. |
| `--cookie-secure` | Hantar kuki sesi hanya melalui HTTPS yang diakses pelayar. |
| `--kindle` | Sediakan halaman minimum tanpa dependensi untuk Kindle e-Ink lama dan alihkan pelayar Kindle WebKit ke halaman tersebut; tidak aktif secara lalai. |

#### Sintaks v1 legasi

Sintaks legasi disokong sepanjang lini utama v2:

| Perintah v1 | Pemetaan v2 |
| --- | --- |
| `epub-browser BOOKS` | `epub-browser server BOOKS --ephemeral` |
| `epub-browser BOOKS --output-dir STATE` | `epub-browser server BOOKS --server-dir STATE` |
| `epub-browser BOOKS --no-server --output-dir DIST` | `epub-browser ssg BOOKS --output-dir DIST` |
| `--sync-dir DIR` | `server --legacy-sync-dir DIR` |

`--keep-files` khusus legasi mengekalkan direktori Server sementara. Direktori Server berterusan sememangnya kekal. Dengan `--log`, penyesuai keserasian mencetak perintah v2 yang setara; jika tidak, ia kekal senyap.

### Data bacaan dan penempatan ciri

- Pengesanan rekursif EPUB/PDF dan perpustakaan Calibre, tag metadata, carian dan carian pinyin
- Antara muka Perpustakaan, perincian buku dan bacaan bab yang responsif
- Penatalan, pembalikan halaman, bacaan berterusan, lebar kandungan boleh laras, fon, CSS tersuai, tema dan mod bacaan tanpa gangguan
- Serlahan, nota, pelayaran anotasi, kumpulan rak buku bertingkat, tag serta Import/Eksport JSON
- Sokongan pelokalan antara muka untuk bahasa Inggeris, Cina Ringkas, Cina Tradisional, Korea,
  Jepun, Sepanyol, Jerman, Perancis, Rusia, Itali, Portugis Brazil, Arab, Indonesia, Hindi,
  Vietnam, Thai dan Melayu
- Tingkah laku mesra e-reader untuk pelayar Kindle/Silk; ciri yang banyak bergantung pada pelayar mungkin dikurangkan

| Data | SSG | Server |
| --- | --- | --- |
| Kemajuan bacaan | Setempat dalam pelayar | Rekod SQLite pengguna yang disahkan |
| Serlahan dan nota | Setempat dalam pelayar | Rekod SQLite pengguna yang disahkan |
| Penarafan peribadi, ulasan dan sejarah sesi bacaan | Tidak tersedia | Rekod SQLite pengguna yang disahkan |
| Rak buku | Setempat dalam pelayar; Import/Eksport | Dokumen awan berversi milik pengguna yang disahkan; simpanan automatik |
| Akaun dan sesi | Tidak tersedia | SQLite di bawah `<server-dir>/data` |
| Pemberian akses buku | Tidak tersedia | SQLite di bawah `<server-dir>/data` |

Server tidak menawarkan pemilih storan setempat/awan: data bacaan pengguna yang disahkan sentiasa disimpan pada Server. Sejarah sesi bacaan peribadi yang terperinci tidak pernah dikeluarkan oleh SSG. SSG tidak pernah mencuba mengakses Server API dan sentiasa menggunakan storan setempat bagi origin pelayar semasa.

### Aset serba lengkap dan tingkah laku rangkaian

Aplikasi ini serba lengkap untuk bacaan: JavaScript, CSS, fon, ikon, manifest dan sumber EPUB yang ditukar disediakan secara setempat. Tiada dependensi CDN semasa runtime. Menyekat akses Internet keluar tidak menghalang persediaan, log masuk, pelayaran, bacaan, anotasi, kemajuan, penggunaan rak buku, pentadbiran atau penukaran sumber.

Pengaki mungkin membuat permintaan pilihan kepada GitHub Releases API untuk menemui versi EPUB Browser yang lebih baharu. Kegagalan, sekatan atau penggunaan luar talian hanya menyembunyikan petua kemas kini itu.

SSG menerbitkan Service Worker statik. Server sengaja menyahaktifkan dan menyingkirkan Service Worker seluruh origin supaya satu akaun tidak dapat menerima kandungan terlindung akaun lain daripada cache.

### Server API dan WebHooks

Akaun Server boleh mencipta personal access token berskop dalam tetapan Akaun. Klien luaran menggunakan `Authorization: Bearer <PAT>` dengan API `/api/v1/*` berversi; kuki pelayar tidak mengesahkan route ini. API merangkumi buku dan kandungan bab yang kelihatan, rak buku pemilik token, kemajuan, anotasi dan ulasan, serta data merentas pengguna baca sahaja untuk PAT pentadbir dengan `admin:data:read`.

Dokumen OpenAPI 3.1 tersedia di `/openapi.json`; pengguna yang telah log masuk boleh melayari rujukan setempat di `/api-docs`. Contohnya: `curl -H 'Authorization: Bearer …' https://reader.example/api/v1/books`. Perincian bab mengembalikan HTML yang telah dibersihkan secara lalai dan teks biasa dengan `?format=text`.

Endpoint senarai mengembalikan `items` dan `next_cursor`. `limit` lalai ialah 24 dan maksimum ialah 100. Hantar `next_cursor` sebagai `cursor` dengan penapis yang sama untuk mendapatkan halaman seterusnya. Cursor null menandakan halaman terakhir. Sebagai contoh, gunakan `/api/v1/me/annotations?book_id=BOOK_ID&chapter_index=0&fields=id,text,note` untuk mendapatkan medan anotasi terpilih daripada satu bab EPUB atau halaman PDF. Penapis pertanyaan dan medan yang disokong disenaraikan dalam dokumen OpenAPI.

Kosa kata menggunakan format senarai yang sama secara lalai. Klien yang menggunakan respons `words` lama boleh menghantar `page=1` atau `page_size` untuk memilih format penomboran halaman legasi.

Pentadbir mengurus endpoint WebHook dalam Pentadbiran. Secret hanya dipaparkan semasa dicipta atau diganti. Penghantaran ditandatangani dan disimpan secara persisten, kemudian dicuba semula bagi respons bukan 2xx. Event ulasan buku mengandungi ID serta cap masa tindakan, tetapi tidak pernah mengandungi penarafan atau teks ulasan.

### Keselamatan data dan migrasi

Sebelum menaik taraf pemasangan Server berterusan, sandarkan buku sumber EPUB/PDF dan `<server-dir>/data`. Kekalkan volum state berterusan yang sama semasa menggantikan kontena.

Migrasi permulaan berjalan secara automatik dan selamat dijalankan semula pada setiap permulaan semula. Ia mengesahkan pangkalan data legasi, mencipta sandaran, menaik taraf salinan, mengimport data rak buku/kemajuan/anotasi legasi yang layak ke dalam akaun pentadbir awal yang belum selesai disediakan, dan hanya menyingkirkan artefak awam legasi yang boleh diganti selepas checkpoint berjaya. Permintaan biasa tidak pernah mengimbas direktori sync legasi. Pangkalan data rosak, hash kata laluan tidak sah, pangkalan data legasi yang samar dan ID bercanggah akan menyebabkan proses gagal secara selamat; sistem tidak akan meneka atau menulis ganti data tersebut.

`epub-browser.db` atau `annotations.db` yang telah dimigrasikan pada akar dikekalkan sebagai salinan pemulihan yang mengandungi data sensitif dan bukan sumber data utama; `data/epub-browser.db` ialah sumber data utama dan permintaan Server tidak menggunakan fail akar yang dikekalkan. Hadkan akses kepada salinan pemulihan itu. Padamkannya secara manual hanya semasa Server dihentikan, selepas mengesahkan pangkalan data utama dan sandaran yang direkodkan, serta hanya apabila rollback ke v1 tidak lagi diperlukan. EPUB Browser tidak pernah memadamkannya secara automatik.

Jika kedua-dua `epub-browser.db` dan `annotations.db` wujud pada akar legasi, permulaan berhenti dan membiarkan kedua-duanya tanpa diubah. Rujuk [Migrasi ke v2](../migration-v2.md) untuk sandaran, rollback, pembinaan semula cache dan pemulihan konflik.

### Penyelesaian masalah

#### Perintah telah dimulakan, tetapi tiada pelayar dibuka

Buang `--no-browser` apabila menjalankan pada mesin setempat bergrafik, atau buka URL yang dicetak/di-bind secara manual. Dalam Docker, systemd, SSH dan sesi tidak interaktif, anda memang perlu membuka URL itu sendiri.

#### CLI kelihatan senyap

Operasi senyap memang disengajakan tanpa `--log`, terutamanya dalam persekitaran tidak interaktif. Tambah `--log` untuk perincian operasi dan akses. Kemajuan imbasan Server dipaparkan dalam antara muka web.

#### Docker tidak dapat menulis ID stabil

Imej menggunakan identiti embedded secara lalai. Lekapkan `/app/Library` sebagai baca-tulis atau benamkan dahulu ID sah yang sepadan. Gunakan perintah tersuai dengan `--book-id-storage sidecar` hanya jika media penyimpanan sidecar yang boleh ditulis lebih sesuai.

#### Laman SSG yang dijana mempunyai pautan rosak di bawah sublaluan

Jana semula laman dengan `--base-path` yang dinormalkan, seperti `/reader/`, dan konfigurasikan hos statik untuk menyediakan output pada awalan yang sama.

#### Server enggan dimulakan selepas peningkatan versi

Baca ralat migrasi atau pengesahan pertama yang dilogkan, kekalkan data dan fail sumber, kemudian rujuk [docs/migration-v2.md](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/migration-v2.md). Jangan padam direktori `data/` yang menjadi sumber data utama untuk mengatasi ralat.

## Pembangunan dan lesen

### Sumbangan

Issues dan pull requests dialu-alukan di [dfface/epub-browser](https://github.com/dfface/epub-browser). Laporan yang berguna menyertakan perintah yang tepat, pelayar/peranti, langkah pengulangan, log berkaitan serta EPUB atau PDF jika boleh dikongsi secara sah.

#### Kontrak seni bina untuk penyelenggara

Baca [AGENTS.md](../../AGENTS.md) sebelum mengubah pemprosesan kandungan, templat halaman,
cache, kebenaran, aset atau tingkah laku deployment. Dokumen itu menetapkan sempadan format
EPUB/PDF, pemilikan SSG/Server, semakan cache bebas, keperluan i18n runtime, pemeriksaan
keselamatan dan pengesahan yang diwajibkan. Istilah produk yang dikongsi seperti *bab pembaca*,
*tetingkap bacaan*, *ruang bacaan* dan *cache kandungan* ditakrifkan dalam
[CONTEXT.md](../../CONTEXT.md).

Ringkasnya: kekalkan satu UI pembaca, jangan masukkan data khusus Server ke dalam SSG,
asingkan cache terbitan EPUB dan PDF daripada data pengguna SQLite, dan jangan sekali-kali
menambah dependensi CDN semasa runtime. Perubahan yang menyentuh bahagian yang dikongsi mesti
diuji dengan kedua-dua format dan kedua-dua mod deployment jika berkenaan.

#### Pembangunan daripada checkout repositori

Fail pihak ketiga untuk pelayar ialah input binaan yang dijana, bukan sumber projek,
jadi `epub_browser/assets/vendor/` sengaja tidak disertakan dalam Git. Sediakan versi
berkunci yang tepat secara eksplisit sebelum membangun atau membina, kemudian sahkan secara
luar talian:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
python3 -m unittest tests.test_vendor_assets -v
python3 -m build
```

`fetch` ialah satu-satunya perintah di atas yang memuat turun aset vendor pelayar. Lock
merekodkan tarball npm immutable, digest fail, allowlist dan lesen; `verify`, ujian, binaan
daripada checkout yang aset vendornya telah disediakan dan pembaca yang dipasang tidak memuat
turun aset pelayar. Perintah standard `python3 -m build`, yang membina dalam persekitaran
terpencil, masih boleh merujuk indeks pakej Python untuk keperluan binaan. Untuk binaan yang
sepenuhnya tanpa rangkaian, sediakan pohon vendor dan prapasang `build`, `setuptools` serta
`wheel` sebelum memutuskan sambungan,
kemudian jalankan `PIP_NO_INDEX=1 python3 -m build --no-isolation`. Wheel, source distribution,
imej Docker dan laman SSG yang dijana mengandungi fail yang telah disahkan dan tidak mempunyai
dependensi CDN semasa runtime. Rujuk [third_party/README.md](../../third_party/README.md)
untuk aliran kerja kemas kini, keluaran dan amalan menjaga repositori kekal kemas.

### Lesen

[MIT](../../License.txt)
