# EPUB Browser

> EPUB và PDF trong thư viện đọc riêng tư hoặc dưới dạng trang tĩnh độc lập.

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

**Ngôn ngữ giao diện (17):** tiếng Anh, tiếng Trung giản thể, tiếng Trung phồn thể, tiếng Nhật, tiếng Hàn, tiếng Tây Ban Nha, tiếng Đức, tiếng Pháp, tiếng Nga, tiếng Ý, tiếng Bồ Đào Nha (Brasil), tiếng Ả Rập, tiếng Indonesia, tiếng Hindi, tiếng Việt, tiếng Thái và tiếng Mã Lai.

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![Một trang PDF trong trình đọc dùng chung của EPUB Browser.](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser xử lý `.epub` và `.pdf` trong hai chế độ với trách nhiệm được phân tách rõ ràng:

| | `ssg` | `server` |
| --- | --- | --- |
| EPUB và PDF | Có | Có |
| Triển khai | Lưu trữ tĩnh, Pages, lưu trữ đối tượng, Nginx | Dịch vụ đọc riêng tư và lâu dài |
| Tài khoản | Không có | Tài khoản cục bộ |
| Đăng nhập một lần OIDC | Không bao gồm | Provider chung, liên kết tài khoản hiện có và tùy chọn tự tạo thành viên |
| Tiến độ, chú thích, giá sách | Chỉ trong trình duyệt này | Dữ liệu tài khoản đã đăng nhập trong SQLite |
| Cập nhật nguồn | Chạy lại `ssg` | Khởi động lại dịch vụ hoặc dùng `--watch` |
| Cơ sở dữ liệu khi chạy | Không có | Bắt buộc |

PDF là định dạng sách hạng nhất: trang 1 trở thành `chapter_0.html`, mọi trang đều xuất hiện trong mục lục và PDF.js cục bộ hiển thị chúng trong cùng thư viện, trang sách, giao diện đọc, tìm kiếm và quy trình chú thích. Các tính năng PDF chưa hỗ trợ như đọc bằng AI được ẩn rõ ràng và không cần CDN trong khi đọc.

Dùng `ssg` khi cần xuất bản các tệp tĩnh thông thường. Dùng `server` khi cần tài khoản, dữ liệu xuyên thiết bị, kiểm soát quyền truy cập sách hoặc tự động theo dõi nguồn.

## Tổng quan

### Vì sao chọn EPUB Browser

- **Trải nghiệm đọc AI-native bám sát nguyên văn:** trong chế độ Server và chỉ
  dành cho EPUB, hướng dẫn chương, lời giải thích dựa trên bằng chứng, sơ đồ tư
  duy, gợi ý suy ngẫm và các cuộc trò chuyện Ask AI riêng tư luôn nằm bên cạnh
  văn bản gốc, thay vì biến cuốn sách thành một bản tóm tắt chung chung tách rời.
- **Phân tích đọc sách riêng tư:** trong chế độ Server,
  bạn có thể xem thời gian đọc chủ động, lịch hoạt động, xu hướng, các phiên đọc
  và những cuốn sách được đọc nhiều nhất; chỉ tài khoản hiện tại nhìn thấy dữ liệu này.

![Hướng dẫn chương bằng AI bên cạnh văn bản EPUB gốc và cuộc trò chuyện Ask AI riêng tư.](assets/ai-native-reading.png)

*Hướng dẫn bằng AI và câu hỏi riêng tư luôn gắn với cuốn sách gốc.*

![Phân tích đọc sách riêng tư với lịch hoạt động và xu hướng thời gian đọc.](assets/reading-insights.png)

*Phân tích biến thời gian đọc chủ động thành lịch sử dễ hiểu và chỉ tài khoản hiện tại nhìn thấy.*

### Công nghệ sử dụng

Giao diện dùng HTML ngữ nghĩa, CSS và Vanilla JavaScript, không dùng framework SPA. CLI và Server dựa trên Python 3.9+, Starlette, Uvicorn và SQLite; pypdf, pypdfium2 cùng PDF.js xử lý PDF cục bộ, không cần CDN khi chạy.

### Bản dùng thử

- **Chế độ SSG**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Chế độ Server**: [epub.yuhan.tech](https://epub.yuhan.tech/) — tên đăng nhập và mật khẩu: `demo`.

### Đọc sách tích hợp AI (chỉ Server)

Tính năng đọc với AI xây dựng một lớp học tập dùng chung và có thể kiểm chứng ngay trên văn bản gốc, thay vì đặt một bản tóm tắt chung chung bên cạnh cuốn sách. Lớp này gồm lộ trình trước khi đọc, tổng quan chương theo yêu cầu, giải thích gắn với trích dẫn, ghi chú về vai trò của đoạn văn, giải nghĩa từ vựng, phần diễn giải đơn giản ở cuối và các câu hỏi để suy nghĩ tiếp.

Kết quả được tạo bằng tác vụ nền, lưu trong SQLite và chia sẻ cho những người đọc có quyền truy cập cuốn sách. Các cuộc trò chuyện tiếp theo vẫn riêng tư cho từng tài khoản. Quản trị viên phải cấu hình nhà cung cấp tương thích OpenAI và cấp quyền riêng cho từng thành viên. Văn bản EPUB được chọn sẽ gửi đến nhà cung cấp đó, vì vậy chỉ bật tính năng khi người đọc đồng ý. Đầu ra SSG không bao giờ chứa tài khoản, điều khiển AI, tác vụ hay cấu hình nhà cung cấp.

## Bắt đầu

### Yêu cầu và cài đặt

- Python 3.9 trở lên
- Một hoặc nhiều tệp `.epub` hoặc `.pdf`, thư mục lồng nhau chứa sách hoặc thư viện theo cấu trúc Calibre

Cài đặt từ PyPI hỗ trợ cả chế độ SSG và Server:

```bash
pip install epub-browser

# Trợ giúp đầy đủ cho từng chế độ
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

Để chạy Server lâu dài bằng Docker, hãy dùng image đã phát hành; máy chủ không cần cài Python:

```bash
docker pull dfface/epub-browser:latest
```

### Bắt đầu nhanh

#### Tạo trang tĩnh

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

Phục vụ `dist/` qua HTTP; không mở trực tiếp các trang đã tạo bằng `file://`. Để triển khai dưới một đường dẫn con, thêm `--base-path /my-repository/`; tùy chọn này thay đổi URL được tạo chứ không thay đổi thư mục đầu ra.

#### Chạy thư viện Server lâu dài

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

Mở `http://127.0.0.1:8000/`. Trong lần truy cập đầu tiên, hãy tạo quản trị viên ban đầu; thư viện sẽ không được quét hoặc công bố trước khi hoàn tất bước này. `--no-browser` chỉ ngăn dịch vụ tự động mở trình duyệt cục bộ.

## Dữ liệu và vận hành

### Dữ liệu, tài khoản và ranh giới truy cập

Mỗi cuốn sách có một `book_id` ổn định. Theo mặc định, `--book-id-storage sidecar` lưu danh tính cạnh tệp nguồn mà không thay đổi byte của tệp. Với EPUB, `--book-id-storage embedded` ghi vào siêu dữ liệu OPF; với PDF, thiết lập này luôn dùng sidecar liền kề.

Trong chế độ Server, `--server-dir` là nơi dữ liệu có thẩm quyền của SQLite, bộ nhớ đệm và bản sao lưu di chuyển. Tài khoản, giá sách, tiến độ đọc, chú thích, kết quả AI và tác vụ cũng được lưu tại đây. Quản trị viên quản lý người dùng, vai trò, phiên và quyền sách; thành viên chỉ sử dụng sách được phép và dữ liệu riêng của mình. Hãy bảo vệ quyền truy cập của thư mục này cùng các bản sao lưu.

### Docker, proxy ngược và tài liệu đầy đủ

Trong container, gắn sách ở chế độ chỉ đọc và gắn `--server-dir` vào ổ đĩa lâu dài. Chỉ chấp nhận tiêu đề proxy từ proxy đáng tin cậy và dùng HTTPS cho triển khai công khai.

Để xem Docker Compose, toàn bộ tùy chọn CLI, di chuyển dữ liệu, LAN, proxy ngược và khắc phục sự cố, hãy đọc [README tiếng Anh đầy đủ](../../README.md) hoặc [README tiếng Trung giản thể đầy đủ](README.zh-CN.md). Hai chế độ hoạt động giống nhau trong mọi ngôn ngữ.

## Phát triển và giấy phép

### Đóng góp và giấy phép

Chúng tôi hoan nghênh Issues và Pull Requests. Xem [License.txt](../../License.txt) để biết giấy phép.
