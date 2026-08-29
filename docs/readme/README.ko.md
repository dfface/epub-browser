# EPUB Browser

> EPUB과 PDF를 개인 읽기 라이브러리 또는 독립 실행형 정적 사이트에서 제공합니다.

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

**인터페이스 언어(17개):** 영어, 중국어 간체, 중국어 번체, 일본어, 한국어, 스페인어, 독일어, 프랑스어, 러시아어, 이탈리아어, 브라질 포르투갈어, 아랍어, 인도네시아어, 힌디어, 베트남어, 태국어, 말레이어.

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![EPUB Browser 공용 리더에서 표시한 PDF 페이지.](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser는 `.epub`과 `.pdf`를 역할이 분명히 구분된 두 가지 모드로 처리합니다.

| | `ssg` | `server` |
| --- | --- | --- |
| EPUB 및 PDF | 지원 | 지원 |
| 배포 | 정적 호스팅, Pages, 오브젝트 스토리지, Nginx | 영속적인 개인 읽기 서비스 |
| 계정 | 없음 | 로컬 계정 |
| 진도, 주석, 책장 | 현재 브라우저에만 저장 | SQLite의 로그인 계정 데이터 |
| 원본 갱신 | `ssg`를 다시 실행 | 서비스를 재시작하거나 `--watch` 사용 |
| 런타임 데이터베이스 | 없음 | 필요 |

PDF는 일급 도서 형식입니다. PDF의 첫 페이지는 `chapter_0.html`이 되고 모든 페이지가 목차에 표시되며, 로컬 PDF.js가 동일한 라이브러리, 도서 페이지, 읽기 화면, 검색, 주석 흐름에서 렌더링합니다. PDF에서 지원하지 않는 AI 읽기 같은 기능은 명시적으로 숨기며 읽는 동안 CDN에 접속하지 않습니다.

일반 정적 파일을 배포하려면 `ssg`를, 계정·기기 간 데이터·도서 접근 제어·원본 자동 감시가 필요하면 `server`를 사용하세요.

## 개요

### EPUB Browser를 선택하는 이유

- **원문에 근거한 AI 네이티브 읽기(Server·EPUB 전용):** Server 모드에서는 장별 가이드, 근거 구절과 연결된 설명, 마인드맵, 성찰 질문, 비공개 Ask AI 대화가 원본 EPUB 본문 옆에 머뭅니다. 책과 분리된 일반적인 요약으로 제공하지 않습니다.
- **비공개 읽기 인사이트(Server 전용):** 실제 읽기 시간, 활동 캘린더, 추세, 세션, 가장 많이 읽은 책을 확인할 수 있습니다. 모든 인사이트는 현재 로그인한 계정에만 표시됩니다.

![원본 EPUB 본문 옆에 표시된 장별 가이드와 비공개 Ask AI 패널.](assets/ai-native-reading.png)

*AI 가이드와 비공개 질문은 원문에 연결된 채로 유지됩니다.*

![활동 캘린더와 읽기 시간 추세를 보여 주는 비공개 읽기 인사이트 화면.](assets/reading-insights.png)

*읽기 인사이트는 실제 읽기 시간을 나만의 이해하기 쉬운 기록으로 바꿉니다.*

### 기술 스택

프런트엔드는 시맨틱 HTML, CSS, Vanilla JavaScript로 구성하며 SPA 프레임워크를 사용하지 않습니다. CLI와 Server는 Python 3.9+, Starlette, Uvicorn, SQLite를 사용하고 PDF는 pypdf, pypdfium2, PDF.js로 로컬 처리하므로 런타임 CDN이 필요하지 않습니다.

### 데모

- **SSG 모드**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Server 모드**: [epub.yuhan.tech](https://epub.yuhan.tech/) — 데모 계정과 비밀번호는 모두 `demo`입니다.

### AI 네이티브 읽기(Server 전용)

AI 읽기는 책 옆에 일반적인 요약을 붙이는 기능이 아닙니다. 원문 위에 함께 검토할 수 있는 학습 레이어를 만듭니다. 장을 읽기 전의 안내, 필요할 때 여는 장 개요, 인용문에 연결된 설명과 문단 메모, 어휘 및 낯선 글자 설명, 장 끝의 파인만식 쉬운 설명, 더 생각해 볼 질문이 읽기 흐름 안에 남습니다.

결과는 SQLite에 저장되는 백그라운드 작업으로 생성되며, 해당 도서 접근 권한이 있는 독자는 결과를 공유합니다. 후속 대화는 각 계정에만 비공개로 보관됩니다. 관리자는 OpenAI 호환 공급자를 설정하고 구성원별로 사용 권한을 부여해야 합니다. 선택된 EPUB 텍스트는 설정한 외부 공급자에게 전송되므로, 독자가 이에 동의한 경우에만 활성화하세요. SSG 출력에는 AI 제어, 계정, 작업, 공급자 설정이 포함되지 않습니다.

## 시작하기

### 요구 사항 및 설치

- Python 3.9 이상
- 하나 이상의 `.epub` 또는 `.pdf` 파일, 도서가 있는 중첩 디렉터리 또는 Calibre 형식의 라이브러리 디렉터리

PyPI 설치는 SSG와 Server 모드를 모두 지원합니다:

```bash
pip install epub-browser

# 모드별 전체 명령 도움말
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

Docker에서 영속적인 Server를 실행하려면 공개 이미지를 사용하세요. 호스트에 Python을 설치할 필요가 없습니다:

```bash
docker pull dfface/epub-browser:latest
```

### 빠른 시작

#### 정적 사이트 만들기

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

`dist/`는 HTTP로 제공해야 합니다. 생성된 페이지를 `file://`로 직접 열면 안 됩니다. 하위 경로에 배포할 경우 `--base-path /my-repository/`를 추가하세요. 이 옵션은 출력 경로가 아니라 생성된 URL을 변경합니다.

#### 영속적인 Server 라이브러리 실행

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

`http://127.0.0.1:8000/`을 여세요. 첫 접속 시 최초 관리자를 만듭니다. 이 일회성 설정이 끝나기 전에는 라이브러리가 검색되거나 공개되지 않습니다. `--no-browser`는 서버가 로컬 기본 브라우저를 자동으로 여는 것만 막으며, 웹 UI를 끄지는 않습니다.

## 데이터 및 운영

### 데이터, 계정, 접근 경계

모든 도서에는 안정적인 `book_id`가 있으며 URL과 브라우저 데이터에서는 `book_hash`로도 표시됩니다. 기본값인 `--book-id-storage sidecar`는 원본 옆에 식별 파일을 만들고 원본 바이트를 변경하지 않습니다. EPUB의 `--book-id-storage embedded`는 OPF 메타데이터에 저장하지만, PDF에서는 항상 인접한 sidecar로 대체됩니다.

Server의 `--server-dir`은 SQLite, 캐시, 마이그레이션 백업을 포함하는 권한 있는 상태 디렉터리입니다. 계정, 책장, 읽기 진도, 주석, AI 결과와 작업도 이곳에 저장됩니다. 관리자는 사용자·역할·세션·제한 도서 권한을 관리하며, 일반 구성원은 권한이 있는 도서와 자신의 비공개 데이터만 이용할 수 있습니다. 이 디렉터리와 백업의 파일 권한을 보호하세요.

일회성 테스트에는 다음을 사용할 수 있습니다.

```bash
epub-browser server book.epub --ephemeral
```

임시 상태는 종료 시 삭제되므로 다음 시작 시 다시 설정해야 합니다. 운영 환경에서는 항상 `--server-dir`을 사용하세요.

### Docker 및 리버스 프록시

컨테이너에서는 도서 디렉터리를 읽기 전용으로 마운트하고 `--server-dir`은 영속 볼륨에 마운트하세요. 리버스 프록시 헤더는 신뢰할 수 있는 프록시에서 온 경우에만 허용해야 합니다. 공개 배포에서는 HTTPS를 사용하고 배포 문서에 따라 신뢰 프록시와 호스트 이름을 설정하세요.

전체 Docker Compose 예시, CLI 인수, 데이터 이전, LAN/리버스 프록시, 문제 해결은 [영문 전체 README](../../README.md) 또는 [간체 중국어 전체 README](README.zh-CN.md)를 참고하세요. 명령줄 옵션과 두 모드의 동작은 모든 언어에서 동일합니다.

## 개발 및 라이선스

### 기여 및 라이선스

Issue와 Pull Request를 환영합니다. 라이선스는 [License.txt](../../License.txt)를 참고하세요.
