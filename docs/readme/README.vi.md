# EPUB Browser

> **Biến sách thành website. Sở hữu thư viện của riêng bạn.**
>
> Xuất bản sách EPUB và PDF thành website tĩnh, hoặc vận hành một thư viện riêng tư, tự lưu trữ
> với tài khoản, đồng bộ tiến độ, chú thích và tính năng đọc tích hợp AI tùy chọn.

[Khám phá thư viện tĩnh](https://epub-browser-test.yuhan.tech/) · [Dùng thử thư viện riêng tư](#bản-dùng-thử-trực-tuyến)

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/dfface/epub-browser/main/epub_browser/assets/logo-lockup-color.png" alt="Logo EPUB Browser" width="520">
</p>

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![Một tệp PDF được hiển thị trong trình đọc dùng chung của EPUB Browser, với trang gốc, điều hướng, chủ đề và công cụ đọc.](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser không chỉ là công cụ chuyển đổi sách. Đây là một nền tảng đọc hoàn chỉnh mà bạn
có thể xuất bản ở bất cứ đâu hoặc tự lưu trữ. EPUB và PDF dùng chung Thư viện, trang sách,
mục lục, chế độ đọc, chủ đề, theo dõi tiến độ và quy trình chú thích. Mỗi trang PDF trở thành
một chương trong trình đọc, được PDF.js kết xuất cục bộ ngay trong cùng trải nghiệm đọc—không
cần trình xem riêng, không phụ thuộc CDN khi chạy.

## Mục lục

- [Tổng quan dự án](#tổng-quan-dự-án)
  - [Vì sao chọn EPUB Browser](#vì-sao-chọn-epub-browser)
  - [Công nghệ sử dụng](#công-nghệ-sử-dụng)
  - [Chọn SSG hay Server](#chọn-ssg-hay-server)
  - [Bản dùng thử trực tuyến](#bản-dùng-thử-trực-tuyến)
  - [Đọc sách tích hợp AI (chỉ Server)](#đọc-sách-tích-hợp-ai-chỉ-server)
  - [Chế độ Kindle tối giản](#chế-độ-kindle-tối-giản)
- [Bắt đầu](#bắt-đầu)
  - [Chọn cách cài đặt](#chọn-cách-cài-đặt)
  - [Bắt đầu nhanh](#bắt-đầu-nhanh)
- [Định dạng và trải nghiệm đọc](#định-dạng-và-trải-nghiệm-đọc)
  - [Nguồn sách và danh tính sách ổn định](#nguồn-sách-và-danh-tính-sách-ổn-định)
  - [PDF: mỗi trang là một chương](#pdf-mỗi-trang-là-một-chương)
- [Triển khai](#triển-khai)
  - [SSG](#ssg)
  - [Server](#server)
  - [Docker](#docker)
- [Tham chiếu và vận hành](#tham-chiếu-và-vận-hành)
  - [Tham chiếu lệnh](#tham-chiếu-lệnh)
  - [Dữ liệu đọc và vị trí tính năng](#dữ-liệu-đọc-và-vị-trí-tính-năng)
  - [Server API và WebHooks](#server-api-và-webhooks)
  - [An toàn dữ liệu và khắc phục sự cố](#an-toàn-dữ-liệu-và-di-chuyển)
- [Phát triển và giấy phép](#phát-triển-và-giấy-phép)
- [Trung tâm tài liệu](../README.md)

## Tổng quan dự án

### Vì sao chọn EPUB Browser

- **Xuất bản ở bất cứ đâu, vẫn giữ quyền kiểm soát.** Chỉ với một lệnh, bạn có thể tạo website
  tĩnh hoàn chỉnh cho Pages, object storage hoặc Nginx; hoặc vận hành Server lâu dài với tài
  khoản, quyền truy cập sách và OIDC. Tài nguyên ứng dụng, phông chữ, PDF.js và các trình kết
  xuất đều được phục vụ cục bộ, nên việc đọc không bao giờ phụ thuộc vào CDN.
- **EPUB và PDF dùng chung một trình đọc thực thụ.** Cả hai định dạng có chung Thư viện, trang
  sách, mục lục, bố cục responsive, ba chế độ đọc, chủ đề, toàn màn hình và tiến độ. Mỗi trang
  PDF vẫn nằm trong khu vực đọc, hỗ trợ thu phóng, chọn văn bản trên text layer và chú thích,
  thay vì mở một trình xem trước riêng.
- **Tìm được cả cuốn sách lẫn đoạn cần đọc.** Tìm kiếm trong Thư viện bao gồm metadata, thẻ và
  bính âm, đồng thời hỗ trợ sắp xếp và phân trang. Tìm kiếm toàn sách EPUB phía Server trả về
  kết quả đầy đủ được nhóm theo chương và chuyển thẳng đến đoạn được đánh dấu. ID sách ổn định
  giúp vị trí đọc tiếp, chú thích và lịch sử luôn gắn với đúng cuốn sách.
- **Hiểu nội dung, không chỉ cuộn trang.** Ở chế độ Server, hướng dẫn chương EPUB, lời giải thích
  có liên kết tới bằng chứng, sơ đồ tư duy và Ask AI riêng tư luôn nằm cạnh văn bản gốc. Đánh dấu,
  ghi chú, Dictionary và Encyclopedia hoạt động trên cả EPUB lẫn PDF có text layer; danh sách từ
  vựng trên Server ghi lại nguồn và trạng thái thành thạo của từng từ.
- **Biến việc đọc thành lịch sử đáng lưu giữ.** Giá sách lồng nhau, đánh giá, nhận xét, xuất chú
  thích, lịch hoạt động, xu hướng, thống kê theo sách và bảng xếp hạng thời gian đọc tạo thành
  một hồ sơ liên kết với nhau. Server giữ dữ liệu đọc ở chế độ riêng tư cho từng tài khoản và
  đồng bộ giữa các thiết bị.
- **Vận hành một dịch vụ đọc, không chỉ một trình xem.** Ở chế độ Server, quản trị viên có thể
  tải sách lên qua web hoặc thêm từ thư mục được theo dõi, giới hạn dung lượng đĩa bằng cơ chế
  loại bỏ cache LRU có thể cấu hình, quản lý quyền của thành viên và AI, đồng thời tích hợp qua
  OpenAPI, PAT và WebHooks. Chế độ đọc Kindle tối giản hỗ trợ thiết bị bị giới hạn; Server còn
  cung cấp bảng điều khiển màn hình chờ Kindle cá nhân với đồng hồ, lịch, lịch trình, ghi nhớ
  và đồng hồ Pomodoro.

![Hướng dẫn chương được đặt cạnh văn bản EPUB gốc, cùng ngăn kéo Ask AI riêng tư.](assets/ai-native-reading.png)

*Hướng dẫn tích hợp AI và các câu hỏi riêng tư luôn gắn với nguyên bản.*

![Chế độ xem thông tin chi tiết về việc đọc riêng tư, với lịch hoạt động và xu hướng thời gian đọc.](assets/reading-insights.png)

*Thông tin chi tiết về việc đọc biến hoạt động đọc chủ động thành một lịch sử riêng tư mà bạn có thể hiểu được.*

### Công nghệ sử dụng

EPUB Browser cố ý sử dụng một web stack gọn nhẹ, kết xuất phía server. Ứng dụng sau khi cài đặt
không có SPA framework và không yêu cầu Node.js runtime:

| Tầng | Công nghệ | Vai trò |
| --- | --- | --- |
| Frontend | Semantic HTML, CSS, VanillaJS với ES modules và browser API | Một giao diện responsive dùng chung cho SSG và Server |
| CLI và Server | Python 3.9+, Starlette, Uvicorn | Lệnh chuyển đổi, trang có xác thực, API và tác vụ nền |
| Dữ liệu | SQLite cùng cache nội dung JSON có thể dựng lại | Trạng thái người dùng được tách khỏi nội dung EPUB/PDF phái sinh |
| Định dạng sách | lxml, pypdf, pypdfium2, PDF.js | Phân tích/làm sạch EPUB thống nhất, ưu tiên chế độ nghiêm ngặt; metadata và bìa PDF; kết xuất cục bộ trong trình duyệt |
| Ngoại tuyến và tài nguyên | Service Worker, tài nguyên bất biến có hash, dependency vendor được khóa phiên bản | Phân phối độc lập, không cần CDN khi chạy |
| Phân phối | PyPI, Docker, static hosting thông thường | Cùng một codebase có thể tạo SSG hoặc chạy Server lâu dài |
| AI tùy chọn | API tương thích OpenAI với Markdown, KaTeX và Mermaid được kết xuất cục bộ | Các lớp học tập EPUB chỉ trong chế độ Server |

Node.js chỉ được maintainer dùng cho các bài kiểm thử phía trình duyệt; đây không phải một phần
của production runtime dành cho người đọc.

### Chọn SSG hay Server

Cùng quy trình xử lý nguồn và page template cung cấp hai chế độ triển khai riêng biệt. Hãy chọn
dựa trên nơi lưu dữ liệu đọc, không phải dựa trên định dạng sách:

| Khả năng | `ssg` | `server` |
| --- | --- | --- |
| EPUB và PDF | Có | Có |
| Phân phối | HTML/tài nguyên tĩnh được tạo theo cơ chế nguyên tử cho Pages, object storage hoặc Nginx | Trang động có xác thực, dựa trên cache nội dung có thể thay thế |
| Tài khoản và kiểm soát truy cập | Không có | Tài khoản administrator/member, cấp quyền sách bị hạn chế, session và bảo vệ CSRF |
| Đăng nhập một lần OIDC | Không bao gồm | Provider chung, liên kết tài khoản hiện có và tùy chọn tự động tạo thành viên |
| Tiến độ, chú thích, giá sách | Lưu trong trình duyệt hiện tại | Đồng bộ theo từng tài khoản đã xác thực trong SQLite |
| Đánh giá, nhận xét, phiên đọc | Không tạo | Bản ghi riêng tư theo tài khoản và thông tin chi tiết về việc đọc |
| Cập nhật nguồn | Chạy lại `ssg` | Khởi động lại, quét lại hoặc dùng `--watch` |
| Quản trị, thẻ, OpenAPI, WebHooks | Không bao gồm | Có |
| Đọc bằng AI và Ask AI | Không bao gồm | Khả dụng cho EPUB khi đã cấu hình và được cấp quyền rõ ràng; ẩn với PDF |
| Cơ sở dữ liệu khi chạy | Không có | Bắt buộc với chế độ lâu dài |
| Phù hợp nhất | Public/static hosting, gói ngoại tuyến, xuất bản cá nhân đơn giản | Thư viện riêng tư, nhiều thiết bị hoặc người đọc, tự động hóa và kiểm soát truy cập |

Dùng `ssg` khi kết quả cần là các tệp tĩnh thông thường. Dùng `server` khi người đọc cần tài khoản,
dữ liệu xuyên thiết bị, kiểm soát truy cập hoặc tự động đồng bộ thay đổi từ nguồn.

### Bản dùng thử trực tuyến

- **Chế độ SSG**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Chế độ Server**: [epub.yuhan.tech](https://epub.yuhan.tech/) — đăng nhập bằng tên người dùng `demo` và mật khẩu `demo`.

### Đọc sách tích hợp AI (chỉ Server)

Với sách EPUB, chế độ Server có thể thêm hướng dẫn chương, lời giải thích liên kết tới bằng chứng,
sơ đồ tư duy, câu hỏi gợi suy ngẫm và ngăn kéo Ask AI riêng tư mà không khiến người đọc rời khỏi
văn bản gốc. Kết quả vẫn tuân theo quyền truy cập sách; thành viên phải được cấp quyền rõ ràng,
còn SSG không chứa bất kỳ điều khiển AI, tác vụ, dữ liệu tài khoản hay cấu hình provider nào.
PDF cố ý ẩn tính năng đọc bằng AI và Ask AI.

Xem [hướng dẫn đọc sách tích hợp AI](../ai-native-reading.md) để biết đầy đủ mô hình tương tác và
[ghi chú về trình kết xuất rich text cục bộ](../third-party-ai-renderers.md) để hiểu ranh giới an toàn
về kết xuất và mạng.

### Chế độ Kindle tối giản

Máy Kindle e-Ink đời cũ (và mọi trình duyệt bị giới hạn) có một giao diện đọc tối giản, không phụ
thuộc bên ngoài. Bật chế độ này bằng `--kindle`:

- SSG: `epub-browser ssg --kindle -o output/ SOURCE...`
- Server: `epub-browser server --kindle --server-dir data SOURCE...`

Mỗi cuốn EPUB (không bao gồm PDF) có thêm ba trang:

- giá sách tối giản `/kindle-library.html`
- trang sách `/book/<id>/kindle.html`
- trang chương `/book/<id>/kindle_chapter_N.html`

Các trang này được tối ưu cho e-Ink: markup tối giản, đổi chủ đề chỉ bằng CSS, script tương thích
ES5, không Service Worker và không framework. Bạn có thể đọc mà hoàn toàn không cần JavaScript;
chuyển chủ đề (Light / Sepia / Dark), cỡ chữ (A- / A+) và bản địa hóa giao diện dùng các inline
script nhẹ, bổ sung cho HTML thuần.

Mọi trang đều có điều khiển chủ đề và phông chữ (ở header và lặp lại ở footer chương), điều hướng
mục lục, chương trước/sau và liên kết "Continue reading" để tiếp tục từ tiến độ đã lưu.

Cách lưu tiến độ đọc khác nhau theo chế độ:

- **SSG:** tiến độ được lưu trong cookie của trình duyệt hiện tại—cục bộ, không cần tài khoản.
- **Server:** tiến độ và heartbeat đọc được đồng bộ theo từng tài khoản đã đăng nhập trong SQLite.
  Giao diện Kindle chỉ đọc/báo cáo: ghi lại chương hiện tại và gửi heartbeat, hiển thị giá sách
  chỉ đọc, đồng thời không bao giờ để lộ thông tin chi tiết về việc đọc hay chức năng quản lý nội dung.

Kiểm soát truy cập được áp dụng trên mọi giao diện Kindle. Với sách bị hạn chế hiển thị, người dùng
không được phép sẽ nhận 403 trên giá sách tối giản (sách bị ẩn), trang sách, trang chương và API tiến độ.

Các trình duyệt được hỗ trợ (UA chứa `Kindle/`, `Arora/`, v.v.) sẽ tự động được chuyển hướng từ
trình đọc đầy đủ sang trang tối giản; các URL ở trên cũng có thể truy cập trực tiếp. Nhờ đó, chế độ
tối giản là phương án dự phòng phù hợp cho thiết bị cấu hình thấp hoặc bị giới hạn JavaScript.

## Bắt đầu

### Chọn cách cài đặt

EPUB Browser hỗ trợ hai cách cài đặt. Cả hai đều chấp nhận một hoặc nhiều tệp `.epub` hoặc `.pdf`,
thư mục lồng nhau, hoặc thư mục thư viện theo cấu trúc Calibre.

| Cách cài đặt | Dùng cho | Yêu cầu máy chủ |
| --- | --- | --- |
| PyPI | Chế độ SSG hoặc Server | Python 3.9 trở lên |
| Docker | Chế độ Server lâu dài | Docker Engine; Python đã có trong image |

#### PyPI (SSG hoặc Server)

Cài đặt ứng dụng dòng lệnh:

```bash
pip install epub-browser
```

Hiển thị tham chiếu lệnh theo từng chế độ:

```bash
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

#### Docker (Server)

Image [`dfface/epub-browser`](https://hub.docker.com/r/dfface/epub-browser) đã phát hành chạy
chế độ Server và không yêu cầu Python trên máy chủ:

```bash
docker pull dfface/epub-browser:latest
```

Dùng `latest` để đánh giá bản phát hành hiện tại; hãy ghim một tag phiên bản cụ thể để triển khai
production có thể lặp lại. Xem [Docker](#docker) để biết các mount bắt buộc cho sách và trạng thái,
hướng dẫn nhanh Compose, thiết lập lần đầu và hướng dẫn mạng.

### Bắt đầu nhanh

#### Tạo website tĩnh

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

Phục vụ `dist/` qua HTTP. Không hỗ trợ mở trực tiếp các trang đã tạo bằng `file://`, vì browser
storage, module, manifest và Service Worker đều yêu cầu một HTTP origin.

Với website được lưu trữ dưới một URL prefix, hãy đặt public path tách biệt với đích đến trên filesystem:

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist \
  --base-path /my-repository/
```

`--base-path` thay đổi URL được tạo, không thay đổi nơi ghi tệp. Với `/my-repository/`, liên kết,
biểu tượng, manifest, metadata sách và mục Service Worker đều dùng prefix này, trong khi các tệp
vẫn nằm trực tiếp bên trong `dist/`.

#### Chạy thư viện Server lâu dài

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

Mở `http://127.0.0.1:8000/`. Ở lần truy cập đầu tiên, EPUB Browser sẽ yêu cầu bạn tạo administrator
ban đầu. Thư viện không được quét hoặc công khai cho đến khi hoàn tất thiết lập một lần này.

Nếu bạn chọn Docker, hãy bỏ qua lệnh Python ở trên và tiếp tục với
[hướng dẫn nhanh Docker Compose](#docker-compose).

## Định dạng và trải nghiệm đọc

### Nguồn sách và danh tính sách ổn định

Mỗi `SOURCE` theo vị trí có thể là một tệp EPUB, tệp PDF hoặc thư mục. Thư mục được tìm kiếm
đệ quy. Một lệnh có thể nhận nhiều nguồn:

```bash
epub-browser server book.epub /srv/library /srv/periodicals \
  --server-dir /srv/epub-browser \
  --watch
```

Mỗi cuốn sách nhận một `book_id` ổn định, cũng được thể hiện dưới dạng `book_hash` trong URL và dữ
liệu trình duyệt được tạo. Mặc định chung của CLI là:

```bash
--book-id-storage sidecar
```

Chế độ sidecar ghi một tệp danh tính hiển thị cạnh nguồn, chẳng hạn `BOOK.epub.epub-browser.json`
hoặc `BOOK.pdf.epub-browser.json`, và giữ nguyên byte của nguồn. Sidecar chứa ID ổn định cùng
dấu vân tay SHA-256 đã xác minh của nguồn.

Để đặt ID trong metadata OPF của EPUB hoặc document information dictionary của PDF, hãy chọn
embedded storage cho toàn bộ lần gọi lệnh:

```bash
--book-id-storage embedded
```

Chế độ embedded có thể dựng lại EPUB ZIP hoặc nối thêm bản cập nhật metadata PDF trước khi chuyển
đổi. Nếu không thể cập nhật PDF và nguồn không thay đổi, EPUB Browser lưu cùng ID đó vào sidecar
liền kề. Điều này áp dụng cả PDF đã ký, được mã hóa và chỉ đọc. EPUB Browser dừng lại khi các ID
không khớp, nhiều nguồn đang hoạt động trùng một ID, carrier không hợp lệ hoặc không thể ghi carrier bắt buộc.

Khi di chuyển giữa các chế độ lưu trữ, EPUB Browser sao chép ID hiện có sang carrier đã chọn và giữ
lại carrier hợp lệ còn lại. ID embedded có sẵn từ v2.0.4 được sao chép sang sidecar mặc định mà
không viết lại EPUB. Cả SSG và Server đều phân phối bản sao byte-for-byte của nguồn PDF sau mọi
cập nhật metadata.

### PDF: mỗi trang là một chương

Cả hai chế độ triển khai đều hỗ trợ PDF. Trình đọc xem mỗi trang PDF như một chương EPUB Browser
thông thường, nhờ đó trang Book, điều hướng chương, mục lục, phân trang, đọc liên tục, tiến độ,
phiên đọc, chú thích, Dictionary và Encyclopedia hiện có vẫn dùng chung một UI và mô hình dữ liệu:

| Khái niệm PDF | SSG | Server |
| --- | --- | --- |
| URL trang 1 | `chapter_0.html` | `/book/<book-id>/chapter_0.html` |
| URL trang N | `chapter_{N-1}.html` | `/book/<book-id>/chapter_{N-1}.html` |
| Nhãn trang và mục lục | Tạo cục bộ; liệt kê mọi trang | Kết xuất từ cache metadata PDF; liệt kê mọi trang |
| Outline nhúng | Một marker trên mục mục lục của trang đích | Cùng marker, không xóa hoặc sắp xếp lại các mục trang |
| Cuộn và phân trang/lật trang | Chapter shell tĩnh và PDF.js cục bộ | Chapter shell dùng chung, động và PDF.js cục bộ |
| Đánh dấu, ghi chú, Dictionary, Encyclopedia | Component dùng chung, lưu cục bộ trong trình duyệt khi có text layer | Component dùng chung có xác thực khi có text layer |
| Byte PDF thô | Một `document.pdf` trong đầu ra sách tĩnh | Route chỉ dành cho Session, hỗ trợ range cho tài liệu được cache |

Số trang hiển thị và trong PDF.js bắt đầu từ 1; chỉ mục chương trong URL, trạng thái, API và SQLite
bắt đầu từ 0. Do đó trang 1 của PDF luôn là `chapter_0.html`. Mục lục chuẩn hóa giữ một mục `Page N`
cho mỗi trang; tiêu đề outline nhúng của PDF được gắn dưới dạng outline marker vào mục đích, kể cả
nhiều marker trên cùng một trang.

SSG ghi một `document.pdf` duy nhất và một chapter shell `chapter_<index>.html` cho mỗi trang. Đầu
ra SSG không chứa script Session, lời gọi `/api/*`, dữ liệu chú thích đồng bộ hay dependency Server.
Server lưu toàn bộ nguồn giống từng byte tại `book/<book-id>/pdf/document.pdf`, không bao giờ tách
hoặc viết lại. Server kết xuất động cùng các chapter shell từ metadata PDF; khi nguồn thay đổi, cache
PDF bị vô hiệu và được làm mới hoàn toàn (tài liệu, metadata và bìa phái sinh), thay vì trộn trang cũ với trang mới.

Endpoint tài liệu thô trên Server chỉ dành cho Session:
`GET`/`HEAD /api/books/<book-id>/document`. Endpoint kiểm tra xác thực, khả năng hiển thị sách,
định dạng PDF và dấu vân tay nguồn/cache, sau đó hỗ trợ phản hồi single-range có giới hạn với `ETag`,
`Accept-Ranges`, private caching, `nosniff` và inline PDF disposition. Endpoint không để lộ đường dẫn
tuyệt đối, không khả dụng với xác thực PAT và không nằm trong bề mặt PAT/OpenAPI. SSG chỉ có
`document.pdf` cục bộ và không có API tài liệu thô.

PDF có text layer mà PDF.js sử dụng được sẽ tái sử dụng chính popup chọn văn bản và component chú
thích hiện có cho Highlight và Note, cùng Dictionary và Encyclopedia. Lưu trữ, quyền sở hữu, xuất,
liệt kê và deep link của chú thích vẫn dùng chung; không có bảng chú thích hay UI cài đặt riêng cho PDF.
PDF quét hoặc chỉ có hình ảnh vẫn đọc được, nhưng Highlight, Note, Dictionary, Encyclopedia dựa trên
vùng chọn và tìm kiếm tài liệu được thông báo rõ là không khả dụng khi không có text layer sử dụng được.
Vùng chọn trải nhiều trang vẫn có thể sao chép, còn thao tác chú thích và tra cứu hiển thị thông báo
không hỗ trợ đã bản địa hóa; vùng chọn trong một trang vẫn hoạt động.

PDF.js không phải một viewer shell thứ hai. Trước khi build hoặc xuất bản, hãy nạp và xác minh các
tài nguyên bên thứ ba đã khóa phiên bản:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
```

Sau đó ứng dụng phục vụ module và worker PDF.js cục bộ có hash khi chạy; tuyệt đối không tải chúng
từ CDN. Image lightbox dùng dependency GLightbox đã khóa; Fancyapps/Fancybox không phải dependency
khi chạy hay được phân phối lại. Xem [third_party/README.md](../../third_party/README.md) để biết quy
trình tài nguyên khóa phiên bản và phát hành.

## Triển khai

### SSG

SSG dựng một snapshot hoàn chỉnh trong thư mục staging cùng cấp, xác thực rồi thay thế đích đến.
Nếu bất kỳ lần chuyển đổi nào thất bại, đích đến trước đó vẫn giữ nguyên. Đầu ra được tạo không chứa
cơ sở dữ liệu Server, trạng thái migration, trang tài khoản hay metadata runtime cache.

Hoạt động của SSG cố ý hoàn toàn cục bộ và không có tài khoản:

- Tiến độ đọc và chú thích dùng browser storage trên origin hiện tại.
- Giá sách hỗ trợ Import và Export JSON cục bộ; không có thao tác Sync lên cloud.
- Không có đăng nhập, cài đặt tài khoản, Server API và các điều khiển phụ thuộc người dùng.
- Đích lưu trữ cố định là local browser storage và không được hiển thị như một cài đặt.
- Đầu ra tĩnh bao gồm Service Worker cần thiết cho tài nguyên có thể dùng ngoại tuyến.

Mọi JavaScript, CSS, phông chữ và biểu tượng ứng dụng cần thiết đều có trong đầu ra. Xem
[Tự đủ tài nguyên và hoạt động mạng](#tự-đủ-tài-nguyên-và-hoạt-động-mạng) để biết yêu cầu mạng tùy chọn duy nhất.

### Server

#### Thiết lập ban đầu, tài khoản và quyền

Với thư mục trạng thái lâu dài hoàn toàn mới, các trang thông thường chuyển hướng tới `/setup`. API,
event stream, tài nguyên được tạo và sách trả về phản hồi yêu cầu thiết lập cho đến khi administrator
ban đầu được tạo. Hãy hoàn tất thiết lập qua loopback hoặc một đường truyền riêng tư đáng tin cậy khác
trước khi mở port: lần gửi thiết lập thành công đầu tiên sẽ chiếm tài khoản administrator.

Sau khi thiết lập:

- Đăng ký công khai bị đóng. Administrator tạo và quản lý người dùng.
- Tài khoản có vai trò `administrator` hoặc `member`.
- Sách thông thường hiển thị với mọi tài khoản đã xác thực.
- Sách bị hạn chế chỉ hiển thị với administrator và những người dùng được chọn rõ ràng.
- Mỗi người dùng sở hữu giá sách, tiến độ, chú thích và session đang hoạt động của mình.
- Người dùng có thể đổi mật khẩu và thu hồi session của mình.
- Administrator có thể quản lý người dùng, vai trò, mật khẩu, session và quyền truy cập sách.
- Session dùng cookie HttpOnly, bảo vệ CSRF và thời hạn trượt 30 ngày.

#### Đăng nhập một lần OIDC và liên kết tài khoản

Chế độ Server có thể dùng một OpenID Connect (OIDC) Provider chung, bao gồm Authelia, Keycloak,
Authentik và các dịch vụ tương thích. Trong **Administration → OIDC login**, nhập tên Provider hiển thị
với người đọc, issuer URL, client ID, client secret, redirect URI chính xác, scope và username claim.
EPUB Browser dùng discovery cùng Authorization Code flow với S256 PKCE, xác thực ID token có chữ ký
và chỉ nhận diện tài khoản bên ngoài bằng `(issuer, sub)`; email và username claim chỉ là gợi ý hiển
thị/provisioning, không bao giờ là khóa danh tính.

Đăng ký chính xác callback sau tại Provider, bao gồm scheme và host:

```text
https://reader.example.com/auth/oidc/callback
```

Người dùng hiện có có thể đăng nhập cục bộ rồi kết nối Provider từ Account settings. Nếu danh tính bên
ngoài chưa được biết, hệ thống sẽ hỏi một lần tên người dùng và mật khẩu cục bộ hiện có. Tính năng
automatic provisioning tùy chọn tạo thành viên không có mật khẩu; tính năng này không bao giờ nhập
vai trò administrator. Hãy để người dùng hiện có liên kết trước: bật automatic provisioning quá sớm
có thể tạo **tài khoản cục bộ trùng lặp**. Đăng nhập bằng mật khẩu của **administrator cục bộ** luôn
khả dụng ngay cả khi đăng nhập bằng mật khẩu của member cục bộ bị tắt. Hãy kiểm thử và bảo vệ thông tin
đăng nhập khôi phục này. Hệ thống không thực hiện Provider logout và không lưu Provider access/refresh token.

Với Authelia, hãy cấu hình confidential client trong phần OIDC Provider. Đoạn trích sau cố ý dùng giá
trị giả và giả định các provider key và policy bắt buộc của Authelia đã được cấu hình. Lưu hash của
một client secret ngẫu nhiên mạnh trong Authelia, sau đó nhập raw secret tương ứng một lần vào EPUB Browser:

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

Trong EPUB Browser, dùng issuer `https://auth.example.com`, client ID
`epub-browser`, scope `openid profile email` và username claim
`preferred_username`. Thao tác Save thực hiện live discovery và xác thực khả năng;
nếu thất bại, cấu hình trước đó vẫn có hiệu lực.

#### Cấu hình và quản trị tính năng đọc bằng AI

Administrator cấu hình tính năng đọc bằng AI trong **Administration**, ngay sau phần quản lý người dùng
và trước phần quản lý sách. Trang này lưu Base URL tương thích OpenAI, API key, model, timeout, ngân
sách context, giới hạn concurrency và giới hạn lượt gọi provider mặc định mỗi ngày trong cơ sở dữ liệu
Server SQLite. AI ban đầu bị tắt với member; administrator phải cấp quyền cho từng member và có thể
đặt giới hạn hằng ngày riêng (`0` nghĩa là không giới hạn).

Các lớp học tập theo chương và bài đánh giá cấp sách được chia sẻ theo từng ngôn ngữ đủ điều kiện,
trong khi hội thoại tiếp nối vẫn riêng tư với từng tài khoản. Kết quả, trạng thái tác vụ, thẻ tùy chỉnh,
phân loại đọc sách và nội dung tiếp nối riêng tư được lưu trong SQLite. Kết quả cũ vẫn khả dụng sau
khi thay đổi cấu hình model cho đến khi administrator chủ động tạo lại.

Khi người đọc yêu cầu hướng dẫn AI hoặc đặt câu hỏi, phần văn bản EPUB được chọn và context hội thoại
đã nén sẽ được gửi tới provider bên ngoài đã cấu hình. Không bật tính năng này trừ khi người đọc được
phép gửi nội dung đó tới provider. API key không bao giờ được trả về trình duyệt hoặc để lộ qua API;
hãy bảo vệ thư mục trạng thái Server tương ứng.

Để khởi động lần đầu không cần tương tác, hãy cung cấp tệp tên người dùng và mật khẩu:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --admin-username admin \
  --admin-password-file /run/secrets/epub-browser-admin-password \
  --no-browser
```

Tệp mật khẩu nên có mode `0600`. EPUB Browser xóa một newline ở cuối, lưu hash Argon2id và không bao
giờ in secret. Cấu hình thiếu, tệp rỗng hoặc tệp không đọc được sẽ làm dừng khởi động. Sau khi thiết
lập hoàn tất, các lần khởi động sau không đọc bootstrap secret.

Biến môi trường tương đương là `EPUB_BROWSER_ADMIN_USERNAME` và `EPUB_BROWSER_ADMIN_PASSWORD_FILE`.
`EPUB_BROWSER_ADMIN_PASSWORD` chỉ là phương án plaintext dự phòng khi không cấu hình tệp mật khẩu.
Đường dẫn tệp mật khẩu trong CLI được ưu tiên hơn các nguồn mật khẩu từ môi trường.

#### Khởi chạy trình duyệt và logging

Theo mặc định, Server cố mở trình duyệt mặc định của hệ điều hành sau khi HTTP listener đã khởi động.
`--no-browser` ngăn lần khởi chạy cục bộ này. Tùy chọn **không tắt giao diện web hoặc quyền truy cập bằng
trình duyệt**; nó chỉ chặn lời gọi `webbrowser.open(...)` cục bộ. Hãy dùng cho Docker, systemd, phiên SSH,
máy headless và script.

Theo mặc định (`--log-level error`), CLI chỉ xuất lỗi để hiển thị tiến độ trên terminal không bị thông
điệp hoặc cảnh báo thường lệ làm gián đoạn. Terminal tương tác in URL đã bind một lần; các lần chạy
Docker và service không tương tác nói chung vẫn yên lặng. Dùng `--log-level warning` để thêm cảnh báo,
`--log-level info` cho log vận hành và truy cập HTTP, hoặc `--log-level debug` để có chi tiết nhất.
`--log` vẫn là alias tương thích cho `--log-level info`.

Lần quét ban đầu và quét watch xuất hiện trong giao diện web thay vì `tqdm` trên terminal. Tóm tắt
thành công tự động đóng; lỗi vẫn hiển thị cho đến khi được bỏ qua. Với `--watch`, sửa hoặc thay thế
một nguồn sẽ bắt đầu lần quét khác mà không cần thao tác thử lại thủ công.

#### Trạng thái lâu dài và tạm thời

Chế độ Server lâu dài yêu cầu `--server-dir`. Với lần chạy dùng một lần, hãy dùng `--ephemeral`:

```bash
epub-browser server book.epub --ephemeral
```

Trạng thái ephemeral bị xóa khi tắt. Vì cơ sở dữ liệu luôn mới sau mỗi lần chạy, thiết lập cũng lặp lại
trừ khi cung cấp thông tin đăng nhập bootstrap không cần tương tác.

Bố cục lâu dài:

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

Chỉ `data/` là nguồn dữ liệu có thẩm quyền. Có thể xóa `cache/` và hệ thống sẽ dựng lại. Hãy giữ `data/`
khi nâng cấp và thay container. Lock của hệ điều hành kiểm soát tính độc quyền; `.server.lock` có thể
còn lại sau khi tắt bình thường dưới dạng metadata chẩn đoán.

Lưu `data/epub-browser.db` lâu dài trên filesystem cục bộ. Không hỗ trợ shared hoặc network filesystem
cho WAL concurrency. Các bản sao lưu đã xác minh nằm trong `data/backups/` và bao gồm toàn bộ dữ liệu WAL đã commit.

#### LAN và reverse proxy

Server mặc định bind tới `127.0.0.1:8000`. Với LAN đáng tin cậy:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --port 8080 \
  --no-browser
```

Không đưa HTTP server tích hợp trực tiếp ra public internet. Hãy chấm dứt TLS tại reverse proxy,
áp dụng kiểm soát mạng và bật secure cookie.

Để ghi lại client IP thực trong active session và login-rate limit phía sau reverse proxy, hãy cấu hình
**direct socket network** của proxy (không phải public client range):

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

Lặp `--trusted-proxy-cidr` một lần cho mỗi địa chỉ hoặc mạng proxy trực tiếp. Chỉ request có direct peer
thuộc một trong các CIDR này mới được cung cấp `X-Forwarded-For`; mọi peer khác chỉ ghi địa chỉ trực tiếp.
Xử lý forwarded address của Uvicorn bị tắt, nên `Forwarded` và `FORWARDED_ALLOW_IPS` không thể mở rộng
ranh giới tin cậy này. Chỉ dùng `--cookie-secure` khi trình duyệt truy cập dịch vụ qua HTTPS.

### Docker

Image chạy chế độ Server lâu dài với các mặc định sau:

- `/app/Library` làm nguồn
- `/app/EpubBrowserFiles` làm trạng thái lâu dài
- `--watch`
- `--no-browser`
- `--host 0.0.0.0 --port 80`
- `--book-id-storage embedded`

Vì embedded identity có thể cập nhật tệp EPUB hoặc PDF, hãy mount thư viện ở chế độ đọc-ghi. Mount
trạng thái Server ở chế độ đọc-ghi và giữ lại khi thay container:

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  dfface/epub-browser:latest
```

Truy cập `http://127.0.0.1:8080/setup` trước khi thay đổi port binding hoặc quy tắc proxy.

#### Docker Compose

Repository có [docker-compose.yml](../../docker-compose.yml) cho người dùng thích Compose. Từ một
checkout, tạo `Library/`, đặt sách EPUB hoặc PDF vào đó rồi chạy:

```bash
docker compose up -d --build
```

Cấu hình này chỉ publish `127.0.0.1:8080`, giữ sách EPUB/PDF nguồn trong `./Library` và lưu trạng thái
Server lâu dài trong `./EpubBrowserFiles`. Toàn bộ `command` của Server được cố ý hiển thị trong tệp,
để có thể thêm flag theo từng triển khai mà không thay thế mặc định ẩn của image. Hoàn tất thiết lập
một lần tại `http://127.0.0.1:8080/setup`. Với truy cập từ xa, giữ loopback binding này và đặt một
reverse proxy TLS có xác thực phía trước.

Để thiết lập không cần tương tác:

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

Sau lần khởi động thành công đầu tiên, có thể bỏ mount secret dùng một lần. Thư viện chỉ đọc chỉ hoạt
động khi mọi EPUB đã chứa embedded ID hợp lệ và khớp. Sidecar hiện có được giữ lại khi ID của chúng được embed.

Chỉ mount `/app/SyncData:ro` khi nhập bookshelf JSON cũ:

```bash
-v /path/to/legacy-sync:/app/SyncData:ro
```

Loopback published port trong các ví dụ giữ container phía sau ranh giới máy chủ. Với truy cập từ xa,
hãy dùng reverse proxy TLS, cấu hình CIDR container-network thực tế của proxy và thêm `--cookie-secure`.

## Tham chiếu và vận hành

### Tham chiếu lệnh

#### `epub-browser ssg SOURCE [SOURCE ...]`

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--output-dir DIR`, `-o DIR` | Đích bắt buộc cho snapshot tĩnh được thay thế theo cơ chế nguyên tử. |
| `--base-path PATH` | Public URL prefix; mặc định `/`. Phải bắt đầu và kết thúc bằng `/`. |
| `--book-id-storage sidecar\|embedded` | Carrier danh tính ổn định cho mọi nguồn đã chọn; mặc định `sidecar`. |
| `--kindle` | Tạo trang tối giản không dependency cho Kindle e-Ink đời cũ và chuyển hướng trình duyệt Kindle WebKit tới đó; mặc định tắt. |
| `--log` | Alias tương thích cho `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Mức chi tiết log vận hành; mặc định `error`, giữ đầu ra chuyển đổi và cảnh báo thường lệ ở chế độ yên lặng. |

#### `epub-browser server SOURCE [SOURCE ...]`

Phải chỉ định đúng một trong hai tùy chọn `--server-dir` và `--ephemeral`.

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--server-dir DIR` | Thư mục gốc cho dữ liệu lâu dài có thẩm quyền và cache có thể thay thế. |
| `--ephemeral` | Dùng trạng thái tạm; loại trừ lẫn nhau với `--server-dir`. |
| `--watch`, `-w` | Theo dõi nguồn và đồng bộ thêm, cập nhật, di chuyển và xóa. |
| `--host ADDRESS` | Địa chỉ bind; mặc định `127.0.0.1`. |
| `--port PORT`, `-p PORT` | Port bind; mặc định `8000`. |
| `--no-browser` | Không khởi chạy trình duyệt mặc định cục bộ. Web UI vẫn khả dụng. |
| `--log` | Alias tương thích cho `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Mức chi tiết log vận hành; mặc định `error`. HTTP access log được bật ở `info` và `debug`. |
| `--legacy-sync-dir DIR` | Đọc bookshelf JSON cũ trong quá trình migration khi khởi động. |
| `--book-id-storage sidecar\|embedded` | Carrier danh tính ổn định cho mọi nguồn đã chọn; mặc định `sidecar`. |
| `--admin-username NAME` | Administrator ban đầu khi chạy không tương tác; fallback `EPUB_BROWSER_ADMIN_USERNAME`. |
| `--admin-password-file FILE` | Tệp secret ban đầu được ưu tiên; fallback `EPUB_BROWSER_ADMIN_PASSWORD_FILE`, rồi `EPUB_BROWSER_ADMIN_PASSWORD` khi không đặt tệp. |
| `--trusted-proxy-cidr CIDR` | Ranh giới tin cậy mạng proxy trực tiếp có thể lặp lại để phân tích client IP từ `X-Forwarded-For` an toàn. |
| `--cookie-secure` | Chỉ gửi session cookie qua HTTPS phía trình duyệt. |
| `--kindle` | Phục vụ trang tối giản không dependency cho Kindle e-Ink đời cũ và chuyển hướng trình duyệt Kindle WebKit tới đó; mặc định tắt. |

#### Cú pháp v1 cũ

Cú pháp cũ được hỗ trợ trong toàn bộ dòng major v2:

| Lệnh v1 | Ánh xạ v2 |
| --- | --- |
| `epub-browser BOOKS` | `epub-browser server BOOKS --ephemeral` |
| `epub-browser BOOKS --output-dir STATE` | `epub-browser server BOOKS --server-dir STATE` |
| `epub-browser BOOKS --no-server --output-dir DIST` | `epub-browser ssg BOOKS --output-dir DIST` |
| `--sync-dir DIR` | `server --legacy-sync-dir DIR` |

`--keep-files` chỉ có ở phiên bản cũ giữ lại thư mục Server tạm thời. Thư mục Server lâu dài vốn đã
được giữ vĩnh viễn. Với `--log`, adapter tương thích in lệnh v2 tương đương; nếu không sẽ giữ yên lặng.

### Dữ liệu đọc và vị trí tính năng

- Khám phá đệ quy EPUB/PDF và thư viện Calibre, metadata tag, tìm kiếm và tìm kiếm bính âm
- Giao diện Thư viện, chi tiết sách và đọc chương responsive
- Cuộn, lật trang, đọc liên tục, điều chỉnh độ rộng nội dung, phông chữ, CSS tùy chỉnh, chủ đề và chế độ đọc thuần
- Đánh dấu, ghi chú, duyệt chú thích, nhóm giá sách lồng nhau, thẻ và Import/Export JSON
- Giao diện hỗ trợ tiếng Anh, tiếng Trung giản thể, tiếng Trung phồn thể, tiếng Hàn, tiếng Nhật,
  tiếng Tây Ban Nha, tiếng Đức, tiếng Pháp, tiếng Nga, tiếng Ý, tiếng Bồ Đào Nha (Brasil),
  tiếng Ả Rập, tiếng Indonesia, tiếng Hindi, tiếng Việt, tiếng Thái và tiếng Mã Lai
- Hoạt động phù hợp với e-reader trên trình duyệt Kindle/Silk; một số tính năng nặng về trình duyệt có thể được giảm bớt

| Dữ liệu | SSG | Server |
| --- | --- | --- |
| Tiến độ đọc | Cục bộ trong trình duyệt | Bản ghi SQLite của người dùng đã xác thực |
| Đánh dấu và ghi chú | Cục bộ trong trình duyệt | Bản ghi SQLite của người dùng đã xác thực |
| Đánh giá, nhận xét riêng tư và lịch sử phiên đọc | Không có | Bản ghi SQLite của người dùng đã xác thực |
| Giá sách | Cục bộ trong trình duyệt; Import/Export | Tài liệu cloud có phiên bản của người dùng đã xác thực; tự động lưu |
| Tài khoản và session | Không có | SQLite trong `<server-dir>/data` |
| Quyền truy cập sách | Không có | SQLite trong `<server-dir>/data` |

Server không cung cấp bộ chọn lưu trữ local/cloud: dữ liệu đọc đã xác thực luôn được lưu trên Server.
Lịch sử phiên đọc riêng tư chi tiết không bao giờ được SSG tạo ra. SSG không bao giờ thăm dò Server API
và luôn dùng local storage của browser origin hiện tại.

### Tự đủ tài nguyên và hoạt động mạng

Ứng dụng độc lập cho việc đọc: JavaScript, CSS, phông chữ, biểu tượng, manifest và tài nguyên EPUB
đã chuyển đổi cần thiết đều được phục vụ cục bộ. Không có CDN dependency khi chạy. Chặn truy cập
internet ra ngoài không ngăn thiết lập, đăng nhập, duyệt, đọc, chú thích, tiến độ, dùng giá sách,
quản trị hoặc chuyển đổi nguồn.

Footer có thể gửi một request tùy chọn tới GitHub Releases API để phát hiện phiên bản EPUB Browser
mới hơn. Nếu thất bại, bị chặn hoặc dùng ngoại tuyến, chỉ gợi ý cập nhật đó bị ẩn.

SSG xuất bản Service Worker tĩnh. Server cố ý tắt và loại bỏ Service Worker trên toàn origin để tài
khoản này không thể nhận nội dung được bảo vệ đã cache của tài khoản khác.

### Server API và WebHooks

Tài khoản Server có thể tạo personal access token có scope trong Account settings. Client bên ngoài dùng
`Authorization: Bearer <PAT>` với API `/api/v1/*` có phiên bản; browser cookie không xác thực các route
này. API bao gồm sách và nội dung chương hiển thị, giá sách của chủ token, tiến độ, chú thích và nhận xét,
cùng dữ liệu chỉ đọc xuyên người dùng cho administrator PAT có `admin:data:read`.

Tài liệu OpenAPI 3.1 có tại `/openapi.json`; người dùng đã đăng nhập có thể duyệt tài liệu tham chiếu cục
bộ tại `/api-docs`. Ví dụ: `curl -H 'Authorization: Bearer …' https://reader.example/api/v1/books`.
Chi tiết chương mặc định trả về HTML đã làm sạch và trả về plain text với `?format=text`.

List endpoint trả về `items` và `next_cursor`. `limit` mặc định là 24, tối đa 100. Truyền `next_cursor`
làm `cursor` cùng các bộ lọc giữ nguyên để lấy trang tiếp theo. Cursor null đánh dấu trang cuối. Ví dụ,
dùng `/api/v1/me/annotations?book_id=BOOK_ID&chapter_index=0&fields=id,text,note` để lấy các trường chú
thích đã chọn từ một chương EPUB hoặc trang PDF. Query filter và trường được hỗ trợ nằm trong tài liệu OpenAPI.

Vocabulary mặc định dùng cùng định dạng list. Client dùng phản hồi `words` cũ có thể gửi `page=1` hoặc
`page_size` để chọn định dạng phân trang cũ.

Administrator quản lý WebHook endpoint trong Administration. Secret chỉ hiển thị khi tạo hoặc xoay vòng.
Delivery được ký, bền bỉ, thử lại với phản hồi non-2xx; sự kiện book-review chứa ID và timestamp hành
động nhưng không bao giờ chứa điểm đánh giá hoặc nội dung nhận xét.

### An toàn dữ liệu và di chuyển

Trước khi nâng cấp bản cài Server lâu dài, hãy sao lưu sách EPUB/PDF nguồn và `<server-dir>/data`.
Giữ nguyên volume trạng thái lâu dài khi thay container.

Migration khi khởi động diễn ra tự động và an toàn khi khởi động lại. Quá trình này xác minh cơ sở dữ
liệu cũ, tạo bản sao lưu, nâng cấp một bản sao, nhập dữ liệu bookshelf/tiến độ/chú thích cũ đủ điều kiện
vào administrator ban đầu đang chờ, và chỉ loại bỏ artifact public cũ có thể thay thế sau các checkpoint
thành công. Request thông thường không bao giờ quét thư mục legacy sync. Cơ sở dữ liệu hỏng, password
hash không hợp lệ, cơ sở dữ liệu cũ mơ hồ và ID xung đột đều fail closed thay vì bị đoán hoặc ghi đè.

`epub-browser.db` hoặc `annotations.db` đã di chuyển ở thư mục gốc được giữ lại như bản sao khôi phục
nhạy cảm, không có thẩm quyền; `data/epub-browser.db` mới là nguồn có thẩm quyền và Server request
không dùng tệp gốc được giữ lại. Hãy giữ bản sao khôi phục ở chế độ riêng tư. Chỉ xóa thủ công khi
Server đã dừng, sau khi xác minh cơ sở dữ liệu có thẩm quyền và bản sao lưu đã ghi, đồng thời chỉ khi
không còn cần rollback về v1. EPUB Browser không bao giờ tự động xóa tệp này.

Nếu cả `epub-browser.db` và `annotations.db` cùng tồn tại ở legacy root, quá trình khởi động dừng và
giữ nguyên cả hai. Xem [Di chuyển lên v2](../migration-v2.md) để biết cách sao lưu, rollback, dựng lại
cache và khôi phục xung đột.

### Khắc phục sự cố

#### Lệnh đã khởi động nhưng trình duyệt không mở

Bỏ `--no-browser` khi chạy trên máy cục bộ có giao diện đồ họa, hoặc tự mở URL được in/đã bind. Trong
Docker, systemd, SSH và phiên không tương tác, bạn được kỳ vọng tự mở URL.

#### CLI có vẻ yên lặng

Hoạt động yên lặng là cố ý khi không có `--log`, đặc biệt trong môi trường không tương tác. Thêm `--log`
để xem chi tiết vận hành và truy cập. Tiến độ quét của Server hiển thị trong giao diện web.

#### Docker không thể ghi ID ổn định

Image mặc định dùng embedded identity. Mount `/app/Library` ở chế độ đọc-ghi hoặc nhúng trước các ID
hợp lệ, khớp nhau. Chỉ dùng custom command với `--book-id-storage sidecar` nếu bạn thích carrier sidecar có thể ghi.

#### Website SSG được tạo có liên kết hỏng dưới subpath

Tạo lại với `--base-path` đã chuẩn hóa, chẳng hạn `/reader/`, và cấu hình static host phục vụ đầu ra tại cùng prefix.

#### Server từ chối khởi động sau khi nâng cấp

Đọc lỗi migration hoặc validation đầu tiên được ghi log, giữ nguyên dữ liệu và tệp nguồn, rồi tham khảo
[docs/migration-v2.md](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/migration-v2.md).
Không xóa thư mục `data/` có thẩm quyền để vượt qua lỗi.

## Phát triển và giấy phép

### Đóng góp

Hoan nghênh Issues và pull requests tại [dfface/epub-browser](https://github.com/dfface/epub-browser).
Một báo cáo hữu ích bao gồm lệnh chính xác, trình duyệt/thiết bị, bước tái hiện, log liên quan và tệp
EPUB hoặc PDF nếu được phép chia sẻ hợp pháp.

#### Hợp đồng kiến trúc dành cho maintainer

Đọc [AGENTS.md](../../AGENTS.md) trước khi thay đổi xử lý nội dung, page template, cache, quyền, tài
nguyên hoặc hành vi triển khai. Tệp này xác định ranh giới định dạng EPUB/PDF, quyền sở hữu giữa
SSG/Server, cache revision độc lập, yêu cầu i18n khi chạy, kiểm tra bảo mật và xác minh bắt buộc.
Các thuật ngữ sản phẩm dùng chung như *reader chapter*, *reading window*, *reading stage* và *content
cache* được định nghĩa trong [CONTEXT.md](../../CONTEXT.md).

Tóm lại: giữ một UI trình đọc, không đưa dữ liệu chỉ dành cho Server vào SSG, giữ cache phái sinh EPUB
và PDF tách khỏi dữ liệu người dùng SQLite, và không bao giờ thêm CDN dependency khi chạy. Thay đổi ảnh
hưởng tới bề mặt dùng chung phải được kiểm thử với cả hai định dạng và cả hai chế độ triển khai khi áp dụng.

#### Phát triển từ source checkout

Các tệp trình duyệt bên thứ ba là build input được tạo, không phải project source, nên
`epub_browser/assets/vendor/` cố ý không có trong Git. Hãy nạp rõ ràng đúng phiên bản đã khóa trước khi
phát triển hoặc build, sau đó xác minh ngoại tuyến:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
python3 -m unittest tests.test_vendor_assets -v
python3 -m build
```

`fetch` là lệnh duy nhất ở trên tải browser vendor asset. Lock ghi lại npm tarball bất biến, file digest,
allowlist và giấy phép; `verify`, kiểm thử, build từ checkout đã nạp và trình đọc đã cài đặt không tải
browser asset. Lệnh `python3 -m build` isolated tiêu chuẩn vẫn có thể truy cập Python package index để
lấy build requirement. Để build hoàn toàn không dùng mạng, hãy nạp vendor tree và cài trước `build`,
`setuptools` và `wheel` trước khi ngắt kết nối, rồi chạy
`PIP_NO_INDEX=1 python3 -m build --no-isolation`. Wheel, source distribution, Docker image và website
SSG được tạo chứa các tệp đã xác minh và không có CDN dependency khi chạy. Xem
[third_party/README.md](../../third_party/README.md) để biết quy trình cập nhật, phát hành và giữ repository sạch.

### Giấy phép

[MIT](../../License.txt)
