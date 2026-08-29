# EPUB Browser

> EPUB dan PDF dalam perpustakaan bacaan peribadi atau sebagai laman statik serba lengkap.

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

**Bahasa antara muka (17):** Inggeris, Cina Ringkas, Cina Tradisional, Jepun, Korea, Sepanyol, Jerman, Perancis, Rusia, Itali, Portugis Brazil, Arab, Indonesia, Hindi, Vietnam, Thai dan Melayu.

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![Halaman PDF dalam pembaca bersama EPUB Browser.](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser memproses `.epub` dan `.pdf` dalam dua mod dengan tanggungjawab yang dipisahkan dengan jelas:

| | `ssg` | `server` |
| --- | --- | --- |
| EPUB dan PDF | Ya | Ya |
| Penggunaan | Pengehosan statik, Pages, storan objek, Nginx | Perkhidmatan membaca peribadi yang berterusan |
| Akaun | Tiada | Akaun setempat |
| Kemajuan, anotasi, rak buku | Dalam pelayar ini sahaja | Data akaun yang dilog masuk dalam SQLite |
| Kemas kini sumber | Jalankan `ssg` sekali lagi | Mulakan semula perkhidmatan atau gunakan `--watch` |
| Pangkalan data masa jalan | Tiada | Diperlukan |

PDF ialah format buku kelas pertama: halaman 1 menjadi `chapter_0.html`, setiap halaman disenaraikan dalam kandungan dan PDF.js setempat memaparkannya dalam perpustakaan, halaman buku, antara muka bacaan, carian serta aliran anotasi yang sama. Ciri PDF yang tidak disokong seperti bacaan AI disembunyikan dengan jelas dan tiada CDN diperlukan semasa membaca.

Gunakan `ssg` untuk menerbitkan fail statik biasa. Gunakan `server` apabila anda memerlukan akaun, data merentas peranti, kawalan akses buku atau pemantauan sumber secara automatik.

## Gambaran keseluruhan

### Tindanan teknologi

Antara muka menggunakan HTML semantik, CSS dan Vanilla JavaScript tanpa rangka kerja SPA. CLI dan Server menggunakan Python 3.9+, Starlette, Uvicorn dan SQLite; pypdf, pypdfium2 serta PDF.js memproses PDF secara setempat tanpa CDN semasa runtime.

### Demo

- **Mod SSG**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Mod Server**: [epub.yuhan.tech](https://epub.yuhan.tech/) — nama pengguna dan kata laluan: `demo`.

### Membaca natif dengan AI (Server sahaja)

Pembacaan AI membina lapisan pembelajaran bersama yang boleh disemak terus pada teks asal, bukan meletakkan ringkasan umum di sebelah buku. Ia merangkumi laluan sebelum membaca, gambaran keseluruhan bab apabila diperlukan, penerangan yang dipautkan kepada petikan, nota tentang peranan perenggan, penjelasan kosa kata, penerangan ringkas di penghujung dan soalan untuk pemikiran lanjut.

Hasil dijana sebagai tugas latar belakang, disimpan dalam SQLite dan dikongsi oleh pembaca yang boleh mengakses buku tersebut. Perbualan susulan kekal peribadi bagi setiap akaun. Pentadbir perlu mengkonfigurasi penyedia yang serasi dengan OpenAI dan memberi kebenaran kepada setiap ahli. Teks EPUB yang dipilih dihantar kepada penyedia itu, jadi aktifkan ciri ini hanya dengan persetujuan pembaca. Output SSG tidak pernah mengandungi akaun, kawalan AI, tugas atau konfigurasi penyedia.

## Bermula

### Keperluan dan pemasangan

- Python 3.9 atau lebih baharu
- Satu atau lebih fail `.epub` atau `.pdf`, direktori buku bersarang atau perpustakaan gaya Calibre

Pemasangan daripada PyPI menyokong mod SSG dan Server:

```bash
pip install epub-browser

# Bantuan penuh bagi setiap mod
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

Untuk Server berterusan dengan Docker, gunakan imej yang diterbitkan; hos tidak memerlukan Python:

```bash
docker pull dfface/epub-browser:latest
```

### Mula pantas

#### Jana laman statik

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

Sediakan `dist/` melalui HTTP; jangan buka halaman yang dijana secara terus menggunakan `file://`. Untuk penggunaan di bawah sublaluan, tambah `--base-path /repositori-saya/`; pilihan ini mengubah URL yang dijana, bukan direktori output.

#### Jalankan perpustakaan Server berterusan

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

Buka `http://127.0.0.1:8000/`. Pada lawatan pertama, cipta pentadbir awal; perpustakaan tidak akan diimbas atau diterbitkan sebelum persediaan selesai. `--no-browser` hanya menghalang perkhidmatan daripada membuka pelayar setempat secara automatik.

## Data dan operasi

### Data, akaun dan sempadan akses

Setiap buku mempunyai `book_id` yang stabil. Secara lalai, `--book-id-storage sidecar` menyimpan identiti di sebelah fail sumber tanpa mengubah baitnya. Untuk EPUB, `--book-id-storage embedded` menulisnya ke metadata OPF; untuk PDF tetapan ini sentiasa kembali kepada sidecar bersebelahan.

Dalam mod Server, `--server-dir` ialah lokasi berwibawa bagi SQLite, cache dan sandaran migrasi. Akaun, rak buku, kemajuan membaca, anotasi, hasil AI dan tugas juga disimpan di situ. Pentadbir mengurus pengguna, peranan, sesi dan kebenaran buku; ahli hanya menggunakan buku yang dibenarkan dan data peribadi mereka sendiri. Lindungi kebenaran direktori ini serta sandarannya.

### Docker, proksi songsang dan dokumentasi penuh

Dalam kontena, lekapkan buku sebagai baca sahaja dan `--server-dir` pada volum berterusan. Terima pengepala proksi hanya daripada proksi yang dipercayai dan gunakan HTTPS bagi penggunaan awam.

Untuk Docker Compose, semua pilihan CLI, migrasi, LAN, proksi songsang dan penyelesaian masalah, lihat [README penuh dalam bahasa Inggeris](../../README.md) atau [README penuh dalam bahasa Cina Ringkas](README.zh-CN.md). Tingkah laku kedua-dua mod adalah sama dalam semua bahasa.

## Pembangunan dan lesen

### Sumbangan dan lesen

Issues dan Pull Requests dialu-alukan. Lihat [License.txt](../../License.txt) untuk lesen.
