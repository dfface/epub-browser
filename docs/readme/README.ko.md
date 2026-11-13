# EPUB Browser

> **책을 웹사이트로 만들고, 나만의 라이브러리를 구축하세요.**
>
> EPUB 및 PDF 도서를 정적 웹사이트로 게시하거나, 계정, 진도 동기화, 주석,
> 선택적 AI 네이티브 읽기를 갖춘 비공개 셀프 호스팅 라이브러리를 운영할 수 있습니다.

[정적 라이브러리 살펴 보기](https://epub-browser-test.yuhan.tech/) · [비공개 라이브러리 사용해 보기](#라이브-데모)

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/dfface/epub-browser/main/epub_browser/assets/logo-lockup-color.png" alt="EPUB Browser 로고" width="520">
</p>

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![공용 EPUB Browser 리더에서 렌더링한 PDF. 원본 페이지, 탐색, 테마, 읽기 도구를 함께 사용할 수 있다.](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser는 단순한 도서 변환기가 아닙니다. 어디에나 게시하거나 직접 호스팅할 수 있는
완전한 읽기 플랫폼입니다. EPUB과 PDF는 동일한 라이브러리, 도서 페이지, 목차, 읽기 모드,
테마, 진도 추적, 주석 워크플로를 공유합니다. PDF의 모든 페이지는 리더의 장이 되어
동일한 읽기 환경 안에서 PDF.js로 로컬 렌더링됩니다. 별도의 뷰어도, 런타임 CDN도 필요하지 않습니다.

## 목차

- [프로젝트 개요](#프로젝트-개요)
  - [EPUB Browser를 선택해야 하는 이유](#epub-browser를-선택해야-하는-이유)
  - [기술 스택](#기술-스택)
  - [SSG와 Server 선택](#ssg와-server-선택)
  - [라이브 데모](#라이브-데모)
  - [AI 네이티브 읽기(Server 전용)](#ai-네이티브-읽기server-전용)
  - [Kindle 미니멀 모드](#kindle-미니멀-모드)
- [시작하기](#시작하기)
  - [설치 방법 선택](#설치-방법-선택)
  - [빠른 시작](#빠른-시작)
- [형식과 읽기](#형식과-읽기)
  - [소스와 안정적인 도서 ID](#소스와-안정적인-도서-id)
  - [PDF: 한 페이지를 한 장으로](#pdf-한-페이지를-한-장으로)
- [배포](#배포)
  - [SSG](#ssg)
  - [Server](#server)
  - [Docker](#docker)
- [참조 및 운영](#참조-및-운영)
  - [명령 참조](#명령-참조)
  - [읽기 데이터와 기능 배치](#읽기-데이터와-기능-배치)
  - [Server API 및 WebHooks](#server-api-및-webhooks)
  - [데이터 안전 및 문제 해결](#데이터-안전-및-마이그레이션)
- [개발 및 라이선스](#개발-및-라이선스)
- [문서 허브](../README.md)

## 프로젝트 개요

### EPUB Browser를 선택해야 하는 이유

- **어디에나 게시하고 통제권도 유지합니다.** 명령 하나로 Pages, 오브젝트 스토리지,
  Nginx에 배포할 완전한 정적 사이트를 빌드하거나, 계정, 도서 권한, OIDC를 갖춘
  영속적인 Server를 운영할 수 있습니다. 애플리케이션 자산, 글꼴, PDF.js, 렌더러를
  모두 로컬에서 제공하므로 읽기가 CDN에 의존하지 않습니다.
- **EPUB과 PDF에 하나의 통합 리더를 제공합니다.** 두 형식은 라이브러리, 도서 페이지,
  목차, 반응형 레이아웃, 세 가지 읽기 모드, 테마, 전체 화면, 진도를 공유합니다.
  PDF의 모든 페이지는 읽기 화면 안에 표시되며, 별도의 미리 보기로 전환하지 않고 확대/축소,
  텍스트 레이어 선택, 주석을 사용할 수 있습니다.
- **도서는 물론 필요한 구절까지 찾습니다.** 라이브러리 검색은 메타데이터, 태그,
  병음을 지원하며 정렬과 페이지 매김도 제공합니다. Server 측 EPUB 전체 도서 검색은
  모든 검색 결과를 장별로 묶어 반환하고 강조 표시된 구절로 이동할 수 있습니다.
  안정적인 도서 ID 덕분에 다시 읽을 위치, 주석, 기록이 항상 같은 도서에 연결됩니다.
- **넘기는 데 그치지 않고 이해할 수 있습니다.** Server 모드에서는 EPUB 장별 가이드,
  근거 구절과 연결된 설명, 마인드맵, 비공개 Ask AI가 원문 옆에 함께 표시됩니다.
  하이라이트, 노트, 사전, 백과사전은 EPUB과 텍스트 레이어가 있는 PDF에서 모두 작동하며,
  Server의 어휘 목록에는 각 단어의 출처와 숙련도가 기록됩니다.
- **읽기를 보관할 가치가 있는 기록으로 만듭니다.** 중첩 책장, 평점, 리뷰, 주석 내보내기,
  활동 캘린더, 추세, 도서별 통계, 읽기 시간 순위가 서로 연결된 기록을 형성합니다.
  Server는 읽기 데이터를 계정별로 비공개로 보관하고 여러 기기 간에 동기화합니다.
- **뷰어가 아닌 읽기 서비스를 운영할 수 있습니다.** Server 모드에서는 관리자 웹 업로드나
  감시 폴더로 도서를 추가하고, 설정 가능한 LRU 방식의 캐시 삭제로 디스크 사용량을 제한하고,
  멤버 및 AI 권한을 관리하며, OpenAPI, PAT, WebHooks로 연동할 수 있습니다.
  Kindle 미니멀 모드는 기능이 제한된 기기도 지원합니다. Server는 시계, 캘린더, 일정, 메모,
  포모도로 타이머를 갖춘 개인용 Kindle 화면 보호기 대시보드도 제공합니다.

![원본 EPUB 본문 옆에 포함된 장별 가이드와 비공개 Ask AI 드로어.](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/readme/assets/ai-native-reading.png)

*AI 네이티브 안내와 비공개 질문은 원문에 연결된 상태로 유지됩니다.*

![활동 캘린더와 읽기 시간 추세를 보여 주는 비공개 읽기 인사이트 화면.](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/readme/assets/reading-insights.png)

*읽기 인사이트는 능동적인 읽기를 이해하기 쉬운 개인 기록으로 바꿔 줍니다.*

### 기술 스택

EPUB Browser는 의도적으로 작은 서버 렌더링 웹 스택을 사용합니다. 설치된 애플리케이션에는
SPA 프레임워크가 없으며 Node.js 런타임도 필요하지 않습니다.

| 계층 | 기술 | 역할 |
| --- | --- | --- |
| 프런트엔드 | 시맨틱 HTML, CSS, ES 모듈과 브라우저 API를 사용하는 VanillaJS | SSG와 Server가 공유하는 하나의 반응형 UI |
| CLI 및 Server | Python 3.9+, Starlette, Uvicorn | 변환 명령, 인증된 페이지, API, 백그라운드 작업 |
| 데이터 | SQLite와 재구축 가능한 JSON 콘텐츠 캐시 | 사용자 상태와 EPUB/PDF 파생 콘텐츠를 분리 |
| 도서 형식 | lxml, pypdf, pypdfium2, PDF.js | 엄격한 파싱을 우선하는 통합 EPUB 파싱/새니타이징, PDF 메타데이터/표지, 로컬 브라우저 렌더링 |
| 오프라인 및 자산 | Service Worker, 해시된 불변 자산, 버전을 고정한 타사 종속성 | 런타임 CDN 없이 자체 완결형으로 제공 |
| 배포 | PyPI, Docker, 일반 정적 호스팅 | 동일한 코드베이스를 SSG 또는 영속적인 Server로 제공 |
| 선택적 AI | OpenAI 호환 API, 로컬에서 렌더링되는 Markdown, KaTeX, Mermaid | Server 모드에서만 제공하는 EPUB 학습 레이어 |

Node.js는 유지 관리자가 브라우저 측 테스트를 실행할 때만 사용하며,
리더의 프로덕션 런타임에는 포함되지 않습니다.

### SSG와 Server 선택

동일한 소스 처리와 페이지 템플릿이 명확히 구분된 두 배포 모드를 지원합니다.
도서 형식이 아니라 읽기 데이터를 어디에 둘지를 기준으로 선택하세요.

| 기능 | `ssg` | `server` |
| --- | --- | --- |
| EPUB 및 PDF | 지원 | 지원 |
| 제공 방식 | Pages, 오브젝트 스토리지, Nginx용 정적 HTML/자산을 원자적으로 생성 | 교체 가능한 콘텐츠 캐시를 기반으로 하는 동적 인증 페이지 |
| 계정 및 액세스 제어 | 없음 | 관리자/멤버 계정, 제한 도서 권한 부여, 세션, CSRF 보호 |
| OIDC 통합 로그인 | 포함 안 됨 | 범용 Provider, 기존 계정 연결, 선택적 멤버 프로비저닝 |
| 진도, 주석, 책장 | 현재 브라우저에 저장 | 인증된 계정별로 SQLite에 동기화 |
| 평점, 리뷰, 읽기 세션 | 생성하지 않음 | 계정별 비공개 기록 및 읽기 인사이트 |
| 소스 업데이트 | `ssg` 다시 실행 | 재시작, 재스캔 또는 `--watch` 사용 |
| 관리, 태그, OpenAPI, WebHooks | 포함 안 됨 | 포함 |
| AI 읽기 및 Ask AI | 포함 안 됨 | 구성하고 명시적으로 허용한 경우 EPUB에서 사용 가능. PDF에서는 숨김 |
| 런타임 데이터베이스 | 없음 | 영속 모드에서 필수 |
| 적합한 용도 | 공개/정적 호스팅, 오프라인 번들, 간단한 개인 게시 | 비공개 라이브러리, 여러 기기 또는 독자, 자동화, 관리형 액세스 |

일반 정적 파일이 결과로 필요하면 `ssg`를 사용하세요. 독자에게 계정, 기기 간 데이터,
액세스 제어 또는 소스 변경 사항의 자동 반영이 필요하면 `server`를 사용하세요.

### 라이브 데모

- **SSG 모드**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Server 모드**: [epub.yuhan.tech](https://epub.yuhan.tech/) — 사용자 이름 `demo`와 비밀번호 `demo`로 로그인하세요.

### AI 네이티브 읽기(Server 전용)

Server 모드에서는 EPUB 도서에 장별 가이드, 근거 구절과 연결된 설명, 마인드맵, 성찰 질문,
비공개 Ask AI 드로어를 추가하며, 독자는 원문을 떠나지 않고도 이를 이용할 수 있습니다.
생성 결과에도 도서 권한이 적용되며 멤버에게는 명시적인 권한 부여가 필요합니다. SSG에는 AI 컨트롤, 작업, 계정 데이터,
프로바이더 구성이 전혀 포함되지 않습니다. PDF에서는 AI 읽기와 Ask AI를 의도적으로 숨깁니다.

상호작용 모델에 대한 자세한 내용은 [AI 네이티브 읽기 가이드](../ai-native-reading.md)를,
렌더링 및 네트워크 안전 경계는 [로컬 리치 텍스트 렌더러 노트](../third-party-ai-renderers.md)를 참고하세요.

### Kindle 미니멀 모드

구형 e-Ink Kindle과 기능이 제한된 다른 브라우저에서는 종속성이 없는 미니멀 읽기 화면을 사용할 수 있습니다.
`--kindle`로 활성화하세요.

- SSG: `epub-browser ssg --kindle -o output/ SOURCE...`
- Server: `epub-browser server --kindle --server-dir data SOURCE...`

각 EPUB 도서(PDF 도서는 제외)에는 다음 세 페이지가 추가됩니다.

- 미니멀 책장 `/kindle-library.html`
- 도서 페이지 `/book/<id>/kindle.html`
- 장 페이지 `/book/<id>/kindle_chapter_N.html`

이 페이지들은 e-Ink에 맞게 최소한의 마크업, CSS 전용 테마, ES5 호환 스크립트를 사용하며
Service Worker와 프레임워크는 사용하지 않습니다. JavaScript 없이도 읽을 수 있습니다.
테마 전환(Light / Sepia / Dark), 글꼴 크기(A- / A+), 인터페이스 현지화는
기본 HTML 위에 가벼운 인라인 스크립트를 얹어 구현합니다.

모든 페이지에는 테마와 글꼴 컨트롤(헤더와 장 푸터에 각각 제공), 목차 탐색, 이전/다음 장,
저장된 진도에서 다시 읽기를 시작하는 “이어 읽기” 링크가 있습니다.

읽기 진도는 모드에 따라 다릅니다.

- **SSG:** 진도는 현재 브라우저의 쿠키에 저장됩니다. 로컬에만 저장되며 계정은 없습니다.
- **Server:** 진도와 읽기 하트비트는 로그인한 계정별로 SQLite에 동기화됩니다.
  Kindle 화면은 읽기/보고 전용입니다. 현재 장을 기록하고 하트비트를 보고하며 읽기 전용 책장을 표시하지만,
  인사이트나 콘텐츠 관리는 제공하지 않습니다.

모든 Kindle 화면에서 액세스 제어가 적용됩니다. 공개가 제한된 도서는 권한이 없는 사용자의
미니멀 책장에서 생략되며, 도서 및 장 페이지와 진도 API에서는 403을 반환합니다.

지원되는 브라우저(UA에 `Kindle/`, `Arora/` 등이 포함된 브라우저)는 일반 리더에서 미니멀 페이지로
자동 리디렉션됩니다. 위 URL로 직접 접속할 수도 있습니다. 따라서 저사양 기기나 JavaScript가 제한된 기기에서도
미니멀 모드를 대체 화면으로 사용할 수 있습니다.

## 시작하기

### 설치 방법 선택

EPUB Browser는 두 가지 설치 경로를 지원합니다. 두 방법 모두 하나 이상의 `.epub` 또는 `.pdf` 파일,
중첩 디렉터리, Calibre 스타일 라이브러리 디렉터리를 입력으로 받을 수 있습니다.

| 설치 | 용도 | 호스트 요구 사항 |
| --- | --- | --- |
| PyPI | SSG 또는 Server 모드 | Python 3.9 이상 |
| Docker | 영속적인 Server 모드 | Docker Engine. Python은 이미지에 포함됨 |

#### PyPI(SSG 또는 Server)

명령줄 애플리케이션을 설치합니다.

```bash
pip install epub-browser
```

모드별 명령 참조를 표시합니다.

```bash
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

#### Docker(Server)

게시된 [`dfface/epub-browser`](https://hub.docker.com/r/dfface/epub-browser)
이미지는 Server 모드로 실행되며 호스트에 Python이 필요하지 않습니다.

```bash
docker pull dfface/epub-browser:latest
```

현재 릴리스를 평가할 때는 `latest`를 사용하고, 반복 가능한 프로덕션 배포에는 번호가 지정된 릴리스 태그를 고정하세요.
필수 도서 및 상태 마운트, Compose 빠른 시작, 최초 실행 설정, 네트워크 안내는 [Docker](#docker)를 참고하세요.

### 빠른 시작

#### 정적 사이트 생성

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

`dist/`는 HTTP로 제공해야 합니다. 브라우저 스토리지, 모듈, 매니페스트, Service Worker에는 HTTP 오리진이 필요하므로
생성된 페이지를 `file://`로 직접 여는 방식은 지원되지 않습니다.

URL 접두사 아래에 사이트를 호스팅하려면 파일 시스템의 출력 위치와 별도로 공개 경로를 설정하세요.

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist \
  --base-path /my-repository/
```

`--base-path`는 파일이 기록되는 위치가 아니라 생성되는 URL을 변경합니다. `/my-repository/`를 지정하면
링크, 아이콘, 매니페스트, 도서 메타데이터, Service Worker 항목에 모두 해당 접두사가 사용되지만,
파일은 계속 `dist/` 바로 아래에 위치합니다.

#### 영속적인 Server 라이브러리 실행

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

`http://127.0.0.1:8000/`을 여세요. 처음 접속하면 EPUB Browser가 초기 관리자 생성을 안내합니다.
이 초기 설정이 끝나기 전까지는 라이브러리를 스캔하거나 공개하지 않습니다.

Docker를 선택했다면 위 Python 명령은 건너뛰고
[Docker Compose 빠른 시작](#docker-compose)으로 이동하세요.

## 형식과 읽기

### 소스와 안정적인 도서 ID

각 위치 인수 `SOURCE`는 EPUB 파일, PDF 파일 또는 디렉터리일 수 있습니다.
디렉터리는 재귀적으로 검색합니다. 하나의 명령에 여러 소스를 전달할 수도 있습니다.

```bash
epub-browser server book.epub /srv/library /srv/periodicals \
  --server-dir /srv/epub-browser \
  --watch
```

각 도서에는 안정적인 `book_id`가 할당되며, 생성된 URL과 브라우저 데이터에서는 `book_hash`로도 노출됩니다.
일반 CLI 기본값은 다음과 같습니다.

```bash
--book-id-storage sidecar
```

sidecar 모드는 소스 옆에 `BOOK.epub.epub-browser.json` 또는 `BOOK.pdf.epub-browser.json`과 같은 식별 파일을
생성하며, 소스 파일의 바이트는 변경하지 않습니다. sidecar에는 안정적인 ID와 검증된 SHA-256 소스 지문이 들어 있습니다.

ID를 EPUB OPF 메타데이터 또는 PDF 문서 정보 사전에 저장하려면 해당 명령에서 처리하는 모든 소스에 embedded 저장 방식을 사용하세요.

```bash
--book-id-storage embedded
```

embedded 모드는 변환 전에 EPUB ZIP을 다시 빌드하거나 PDF 메타데이터 업데이트를 추가할 수 있습니다.
PDF를 업데이트할 수 없고 소스가 변경되지 않았다면 EPUB Browser는 동일한 ID를 인접한 sidecar에 저장합니다.
여기에는 서명되거나 암호화된 PDF와 읽기 전용 PDF도 포함됩니다. ID가 서로 다르거나, 활성 소스가 ID를 중복 사용하거나,
ID 저장 위치가 유효하지 않거나, 필요한 저장 위치에 쓸 수 없으면 EPUB Browser는 중단됩니다.

ID 저장 방식을 마이그레이션할 때 EPUB Browser는 기존 ID를 선택한 저장 위치로 복사하고 다른 유효한 저장 위치도 그대로 유지합니다.
v2.0.4의 기존 embedded ID는 EPUB을 다시 쓰지 않고 기본 sidecar로 복사됩니다.
SSG와 Server 모두 메타데이터 업데이트 후에도 PDF 소스를 바이트 단위로 동일하게 복사해 제공합니다.

### PDF: 한 페이지를 한 장으로

PDF는 두 배포 모드에서 모두 지원됩니다. 리더는 PDF의 각 페이지를 일반적인 EPUB Browser 장으로 취급하므로,
기존 도서 페이지, 장 탐색, 목차, 페이지 매김, 연속 읽기, 진도, 읽기 세션, 주석,
사전, 백과사전이 하나의 공유 UI와 데이터 모델로 유지됩니다.

| PDF 개념 | SSG | Server |
| --- | --- | --- |
| 1페이지 URL | `chapter_0.html` | `/book/<book-id>/chapter_0.html` |
| N페이지 URL | `chapter_{N-1}.html` | `/book/<book-id>/chapter_{N-1}.html` |
| 페이지 레이블 및 목차 | 로컬에서 생성하며 모든 페이지를 나열 | PDF 메타데이터 캐시에서 렌더링하며 모든 페이지를 나열 |
| 내장 아웃라인 | 대상 페이지의 목차 항목에 마커 표시 | 동일한 마커를 표시하며 페이지 항목을 제거하거나 순서를 바꾸지 않음 |
| 스크롤 및 페이지 매김/넘김 | 정적 장 페이지 골격과 로컬 PDF.js | 동적 공유 장 페이지 골격과 로컬 PDF.js |
| 하이라이트, 노트, 사전, 백과사전 | 텍스트 레이어가 있으면 공유 브라우저 로컬 컴포넌트 사용 | 텍스트 레이어가 있으면 공유 인증 컴포넌트 사용 |
| 원본 PDF 바이트 | 정적 도서 출력에 `document.pdf` 하나 | 캐시된 문서를 제공하는 Session 전용 Range 지원 경로 |

표시되는 레이블과 PDF.js의 페이지 번호는 1부터 시작하고, URL, 상태, API, SQLite의 장 인덱스는 0부터 시작합니다.
따라서 PDF의 1페이지는 항상 `chapter_0.html`입니다. 정규화된 목차는 모든 페이지에 `Page N` 항목을 하나씩 유지합니다.
PDF에 포함된 아웃라인 제목은 대상 항목에 아웃라인 마커로 첨부되며, 한 페이지에 여러 마커가 붙을 수도 있습니다.

SSG는 `document.pdf` 하나와 페이지마다 `chapter_<index>.html` 장 페이지 골격을 하나씩 생성합니다.
SSG 출력에는 Session 스크립트, `/api/*` 호출, 동기화된 주석 데이터, Server 종속성이 없습니다.
Server는 원본 소스 전체를 바이트 단위로 동일하게 `book/<book-id>/pdf/document.pdf`에 저장하며 분할하거나 다시 쓰지 않습니다.
Server는 PDF 메타데이터를 바탕으로 동일한 장 페이지 골격을 동적으로 렌더링합니다. 소스가 변경되면 PDF 캐시
(문서, 메타데이터, 파생 표지)를 무효화하고 완전히 새로 고치므로 이전 페이지와 새 페이지가 섞이지 않습니다.

Server 원본 문서 엔드포인트는 Session 전용인 `GET`/`HEAD /api/books/<book-id>/document`입니다.
인증, 도서 공개 범위, PDF 형식, 소스/캐시 지문을 확인한 후 `ETag`, `Accept-Ranges`, 비공개 캐싱,
`nosniff`, 인라인 PDF disposition을 갖춘 범위가 제한된 단일 Range 응답을 지원합니다.
절대 경로를 노출하지 않으며 PAT 인증으로는 사용할 수 없고 PAT/OpenAPI 인터페이스에도 포함되지 않습니다.
SSG에는 로컬 `document.pdf`만 있고 원본 문서 API는 없습니다.

PDF.js에서 텍스트 레이어를 사용할 수 있는 PDF는 기존 선택 팝업과 주석 컴포넌트를 그대로 재사용해
하이라이트, 노트, 사전, 백과사전을 제공합니다. 주석 저장, 소유권, 내보내기, 목록, 딥 링크도 공유되며
PDF 전용 주석 테이블이나 설정 UI는 없습니다. 스캔한 PDF나 이미지만 있는 PDF도 읽을 수는 있지만,
사용 가능한 텍스트 레이어가 없으면 선택 기반 하이라이트, 노트, 사전, 백과사전, 문서 검색을
명시적으로 사용할 수 없습니다. 여러 페이지에 걸친 선택 영역은 복사할 수 있지만 주석과 조회 동작에는
현지화된 미지원 메시지가 표시됩니다. 한 페이지 안에서의 선택은 계속 작동합니다.

PDF.js를 사용한다고 별도의 뷰어 화면이 생기는 것은 아닙니다. 빌드하거나 게시하기 전에 버전이 고정된 타사 자산을 가져오고 검증하세요.

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
```

이후 애플리케이션은 런타임에 로컬 해시 PDF.js 모듈과 워커 자산을 제공하며 CDN에서 가져오지 않습니다.
이미지 라이트박스에는 버전이 고정된 GLightbox를 사용합니다. Fancyapps/Fancybox는 런타임 종속성이나
재배포 종속성이 아닙니다. 자산 버전 고정 및 릴리스 워크플로는 [third_party/README.md](../../third_party/README.md)를 참고하세요.

## 배포

### SSG

SSG는 대상의 형제 스테이징 디렉터리에 완전한 스냅숏을 빌드하고 검증한 다음 대상을 교체합니다.
변환이 하나라도 실패하면 이전 대상은 변경되지 않습니다. 생성된 출력에는 Server 데이터베이스,
마이그레이션 상태, 계정 페이지, 런타임 캐시 메타데이터가 포함되지 않습니다.

SSG는 의도적으로 로컬에서 계정 없이 동작합니다.

- 읽기 진도와 주석은 현재 오리진의 브라우저 스토리지를 사용합니다.
- 책장은 로컬 JSON 가져오기와 내보내기를 지원하며 클라우드 동기화 동작은 없습니다.
- 로그인, 계정 설정, Server API, 사용자 종속 컨트롤은 제공하지 않습니다.
- 저장 위치는 로컬 브라우저 스토리지로 고정되며 설정 항목으로 표시하지 않습니다.
- 정적 출력에는 오프라인 자산 사용에 필요한 Service Worker가 포함됩니다.

필요한 애플리케이션 JavaScript, CSS, 글꼴, 아이콘은 모두 출력에 포함됩니다.
유일한 선택적 네트워크 요청은 [자체 완결형 구성과 네트워크 동작](#자체-완결형-구성과-네트워크-동작)을 참고하세요.

### Server

#### 초기 설정, 계정, 권한

새 영속 상태 디렉터리에서는 일반 페이지가 `/setup`으로 리디렉션됩니다. 초기 관리자가 생성되기 전까지
API, 이벤트 스트림, 생성된 자산, 도서는 설정 필요 응답을 반환합니다. 포트를 외부에 노출하기 전에
루프백이나 신뢰할 수 있는 다른 비공개 경로에서 설정을 완료하세요. 최초로 성공한 설정 제출이 관리자 계정을 확정합니다.

설정 후에는 다음과 같이 동작합니다.

- 공개 가입은 닫히며 관리자가 사용자를 생성하고 관리합니다.
- 계정에는 `administrator` 또는 `member` 역할이 있습니다.
- 일반 도서는 인증된 모든 계정에 표시됩니다.
- 제한 도서는 관리자와 명시적으로 선택한 사용자에게만 표시됩니다.
- 각 사용자는 자신의 책장, 진도, 주석, 활성 세션을 소유합니다.
- 사용자는 비밀번호를 변경하고 세션을 해지할 수 있습니다.
- 관리자는 사용자, 역할, 비밀번호, 세션, 도서 권한 부여를 관리할 수 있습니다.
- 세션은 HttpOnly 쿠키, CSRF 보호, 30일 슬라이딩 유효 기간을 사용합니다.

#### OIDC 통합 로그인 및 계정 연결

Server 모드는 Authelia, Keycloak, Authentik 및 호환 서비스를 포함한 범용 OpenID Connect(OIDC) Provider 하나를 사용할 수 있습니다.
**Administration → OIDC login**에서 독자에게 표시할 Provider 이름, 발급자 URL, 클라이언트 ID,
클라이언트 시크릿, 정확한 리다이렉트 URI, 스코프, 사용자 이름 클레임을 입력합니다.
EPUB Browser는 Discovery와 S256 PKCE를 사용하는 Authorization Code 흐름을 사용하고 서명된 ID 토큰을 검증하며,
외부 계정은 `(issuer, sub)`로만 식별합니다. 이메일과 사용자 이름 클레임은 화면 표시와 프로비저닝에만 참고하며,
계정을 식별하는 데는 사용하지 않습니다.

Provider에는 스킴과 호스트를 포함한 다음 콜백을 정확히 등록하세요.

```text
https://reader.example.com/auth/oidc/callback
```

기존 사용자는 로컬로 로그인한 후 Account settings에서 Provider를 연결할 수 있습니다.
아직 로컬 계정과 연결되지 않은 외부 계정으로 로그인하면 기존 로컬 사용자 이름과 비밀번호를 한 번 묻습니다.
선택적 자동 프로비저닝은 비밀번호 없는 멤버를 생성하며 관리자 역할은 절대 가져오지 않습니다.
기존 사용자가 먼저 연결하도록 하세요. 자동 프로비저닝을 너무 일찍 활성화하면 **중복 로컬 계정**이 생길 수 있습니다.
로컬 멤버 비밀번호 로그인을 비활성화하더라도 **로컬 관리자** 비밀번호 로그인은 항상 유지됩니다.
이 복구용 자격 증명이 정상적으로 동작하는지 확인하고 안전하게 보관하세요. Provider 로그아웃은 수행하지 않으며
Provider 액세스/리프레시 토큰도 저장하지 않습니다.

Authelia에서는 OIDC Provider 섹션에 confidential client를 구성하세요. 다음 발췌는 의도적으로 가짜 값을 사용하며,
Authelia에 필요한 Provider 키와 정책이 이미 구성되어 있다고 가정합니다. 강력한 무작위 클라이언트 시크릿의 해시를
Authelia에 저장한 다음, 대응하는 원문 시크릿을 EPUB Browser에 한 번 입력하세요.

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

EPUB Browser에는 발급자 `https://auth.example.com`, 클라이언트 ID `epub-browser`, 스코프 `openid profile email`,
사용자 이름 클레임 `preferred_username`을 사용합니다. 저장하면 실시간 Discovery와 기능 검증이 실행되며,
실패하면 이전 구성이 계속 활성 상태로 유지됩니다.

#### AI 읽기 구성과 관리

관리자는 **Administration**에서 AI 읽기를 구성합니다. 이 페이지는 사용자 관리 바로 다음, 도서 관리 바로 앞에 있습니다.
OpenAI 호환 Base URL, API 키, 모델, 제한 시간, 컨텍스트 예산, 동시 실행 상한,
기본 일일 프로바이더 호출 한도를 Server SQLite 데이터베이스에 저장합니다. AI는 멤버에게 기본적으로 비활성화되어 있으며,
관리자가 멤버별로 액세스 권한을 부여해야 합니다. 개별 일일 한도도 설정할 수 있으며 `0`은 무제한을 뜻합니다.

장 학습 레이어와 도서 전체 리뷰는 대상 언어별로 공유되지만 후속 대화는 계정별로 비공개로 유지됩니다.
결과, 작업 상태, 사용자 지정 태그, 도서 읽기 분류, 비공개 후속 대화는 SQLite에 저장됩니다.
모델 구성을 변경한 후에도 관리자가 명시적으로 다시 생성하기 전까지는 기존 결과를 계속 사용할 수 있습니다.

독자가 AI 가이드를 요청하거나 질문하면 선택한 EPUB 텍스트와 압축된 대화 컨텍스트가 구성된 외부 프로바이더로 전송됩니다.
독자가 해당 콘텐츠를 프로바이더에 보낼 수 있도록 허용된 경우가 아니라면 이 기능을 활성화하지 마세요.
API 키는 브라우저에 반환되거나 API를 통해 노출되지 않으므로, Server 상태 디렉터리도 적절히 보호하세요.

사용자 개입 없이 처음 시작하려면 사용자 이름과 비밀번호 파일을 제공하세요.

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --admin-username admin \
  --admin-password-file /run/secrets/epub-browser-admin-password \
  --no-browser
```

비밀번호 파일 권한은 `0600`이어야 합니다. EPUB Browser는 마지막 줄 바꿈 하나를 제거하고 Argon2id 해시를 저장하며
시크릿을 출력하지 않습니다. 구성이 불완전하거나 파일이 비어 있거나 읽을 수 없으면 시작이 중단됩니다.
설정이 완료된 후에는 다음 시작부터 부트스트랩 시크릿을 읽지 않습니다.

동등한 환경 변수는 `EPUB_BROWSER_ADMIN_USERNAME`과 `EPUB_BROWSER_ADMIN_PASSWORD_FILE`입니다.
`EPUB_BROWSER_ADMIN_PASSWORD`는 비밀번호 파일이 구성되지 않은 경우에만 사용하는 평문 대체 수단입니다.
CLI 비밀번호 파일 경로는 환경 변수의 비밀번호 소스보다 우선합니다.

#### 브라우저 실행과 로깅

기본적으로 Server는 HTTP 리스너가 시작된 후 운영 체제의 기본 브라우저를 열려고 시도합니다.
`--no-browser`는 이 로컬 실행을 막습니다. **웹 인터페이스나 브라우저 액세스를 비활성화하지는 않으며**,
로컬 `webbrowser.open(...)` 호출만 억제합니다. Docker, systemd, SSH 세션, 헤드리스 머신, 스크립트에서 사용하세요.

기본값(`--log-level error`)에서는 CLI가 오류만 출력하므로 일상적인 메시지나 경고가 터미널 진행 표시를 방해하지 않습니다.
대화형 터미널에는 바인딩된 URL을 한 번 출력하며, 비대화형 Docker 및 서비스 실행에서는 그 외의 메시지를 출력하지 않습니다.
경고까지 보려면 `--log-level warning`, 운영 및 HTTP 액세스 로깅에는 `--log-level info`,
가장 자세한 정보에는 `--log-level debug`를 사용하세요. `--log`는 `--log-level info`의 호환성 별칭으로 유지됩니다.

초기 스캔과 감시 스캔은 터미널 `tqdm` 대신 웹 인터페이스에 표시됩니다. 성공 요약은 자동으로 닫히고
실패는 닫을 때까지 표시됩니다. `--watch`를 사용할 때 소스를 수정하거나 교체하면 수동 재시도 없이 새 스캔이 시작됩니다.

#### 영속 상태와 임시 상태

영속적인 Server 모드에는 `--server-dir`이 필요합니다. 일회성 실행에는 대신 `--ephemeral`을 사용하세요.

```bash
epub-browser server book.epub --ephemeral
```

임시 상태는 종료 시 삭제됩니다. 실행할 때마다 데이터베이스가 새로 생성되므로 무인 부트스트랩 자격 증명을 제공하지 않으면
설정도 매번 반복됩니다.

영속 레이아웃:

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

`data/`만 기준 데이터입니다. `cache/`는 삭제할 수 있으며 다시 빌드됩니다.
업그레이드와 컨테이너 교체 시 `data/`를 보존하세요. 운영 체제 잠금이 배타성을 제어하며,
`.server.lock`은 정상 종료 후에도 진단 메타데이터로 남을 수 있습니다.

영속적인 `data/epub-browser.db`는 로컬 파일 시스템에 저장하세요. WAL 동시성에는 공유 또는 네트워크 파일 시스템이 지원되지 않습니다.
검증된 백업은 `data/backups/`에 남으며 커밋된 모든 WAL 데이터를 포함합니다.

#### LAN 및 리버스 프록시

Server는 기본적으로 `127.0.0.1:8000`에 바인딩됩니다. 신뢰할 수 있는 LAN에서 사용하려면:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --port 8080 \
  --no-browser
```

기본 제공 HTTP 서버를 공용 인터넷에 직접 노출하지 마세요. 리버스 프록시에서 TLS를 종료하고
네트워크 제어를 적용하며 보안 쿠키를 활성화하세요.

리버스 프록시 뒤에서 활성 세션과 로그인 속도 제한에 실제 클라이언트 IP를 기록하려면
공개 클라이언트 대역이 아니라 **Server에 직접 연결되는 프록시의 네트워크**를 지정하세요.

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

직접 연결되는 각 프록시 주소나 네트워크마다 `--trusted-proxy-cidr`을 한 번씩 반복하세요.
Server는 직접 연결된 피어가 이 CIDR 중 하나에 속하는 요청의 `X-Forwarded-For`만 신뢰하며,
그 외 피어는 직접 연결된 주소만 기록합니다. Uvicorn forwarded-address 처리는 비활성화되어 있으므로
`Forwarded`와 `FORWARDED_ALLOW_IPS`가 이 신뢰 경계를 넓힐 수 없습니다.
브라우저가 HTTPS를 통해 서비스에 접근하는 경우에만 `--cookie-secure`를 사용하세요.

### Docker

이미지는 다음 기본값으로 영속적인 Server 모드를 실행합니다.

- 소스는 `/app/Library`
- 영속 상태는 `/app/EpubBrowserFiles`
- `--watch`
- `--no-browser`
- `--host 0.0.0.0 --port 80`
- `--book-id-storage embedded`

embedded ID 저장 방식은 EPUB 또는 PDF 파일을 업데이트할 수 있으므로 라이브러리를 읽기/쓰기 가능으로 마운트하세요.
Server 상태도 읽기/쓰기 가능으로 마운트하고 컨테이너를 교체한 후에도 유지하세요.

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  dfface/epub-browser:latest
```

포트 바인딩이나 프록시 규칙을 변경하기 전에 `http://127.0.0.1:8080/setup`을 방문하세요.

#### Docker Compose

Compose를 선호하는 사용자를 위해 리포지토리에는 [docker-compose.yml](../../docker-compose.yml)이 포함되어 있습니다.
체크아웃에서 `Library/`를 만들고 EPUB 또는 PDF 도서를 넣은 다음 실행하세요.

```bash
docker compose up -d --build
```

`127.0.0.1:8080`만 게시하고, 원본 EPUB/PDF 도서는 `./Library`에 보관하며, Server 상태는 `./EpubBrowserFiles`에 영속화합니다.
이미지의 암묵적인 기본값을 대체하지 않고 배포별 플래그를 추가할 수 있도록, 전체 Server `command`를 파일에 명시해 두었습니다.
`http://127.0.0.1:8080/setup`에서 일회성 설정을 완료하세요. 원격 액세스의 경우 이 루프백 바인딩을 유지하고
앞단에 인증된 TLS 리버스 프록시를 배치하세요.

무인 설정:

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

첫 시작에 성공한 후에는 일회성 시크릿 마운트를 제거할 수 있습니다. 읽기 전용 라이브러리는 모든 EPUB에
일치하는 유효한 embedded ID가 이미 들어 있는 경우에만 작동합니다. ID를 embedded 모드로 저장할 때도 기존 sidecar는 유지됩니다.

레거시 책장 JSON을 가져오는 동안에만 `/app/SyncData:ro`를 마운트하세요.

```bash
-v /path/to/legacy-sync:/app/SyncData:ro
```

예시처럼 루프백 주소에 포트를 게시하면 호스트에서만 컨테이너에 접근할 수 있습니다. 원격 액세스에는 TLS 리버스 프록시를 사용하고,
실제 컨테이너 네트워크 CIDR을 구성한 후 `--cookie-secure`를 추가하세요.

## 참조 및 운영

### 명령 참조

#### `epub-browser ssg SOURCE [SOURCE ...]`

| 옵션 | 의미 |
| --- | --- |
| `--output-dir DIR`, `-o DIR` | 원자적 정적 스냅숏의 필수 출력 대상. |
| `--base-path PATH` | 공개 URL 접두사. 기본값은 `/`이며 `/`로 시작하고 끝나야 함. |
| `--book-id-storage sidecar\|embedded` | 선택한 모든 소스의 안정적인 ID를 저장할 위치. 기본값은 `sidecar`. |
| `--kindle` | 구형 e-Ink Kindle용 종속성 없는 미니멀 페이지를 생성하고 Kindle WebKit 브라우저를 해당 페이지로 리디렉션. 기본값은 꺼짐. |
| `--log` | `--log-level info`의 호환성 별칭. |
| `--log-level debug\|info\|warning\|error` | 운영 로그 상세 수준. 기본값은 `error`이며 일상적인 변환 출력과 경고를 표시하지 않음. |

#### `epub-browser server SOURCE [SOURCE ...]`

`--server-dir`과 `--ephemeral` 중 정확히 하나를 지정해야 합니다.

| 옵션 | 의미 |
| --- | --- |
| `--server-dir DIR` | 영속적으로 보관할 기준 데이터와 교체 가능한 캐시의 루트. |
| `--ephemeral` | 일회성 상태를 사용하며 `--server-dir`과 상호 배타적. |
| `--watch`, `-w` | 소스를 감시하고 추가, 업데이트, 이동, 삭제를 반영. |
| `--host ADDRESS` | 바인딩 주소. 기본값은 `127.0.0.1`. |
| `--port PORT`, `-p PORT` | 바인딩 포트. 기본값은 `8000`. |
| `--no-browser` | 로컬 기본 브라우저를 실행하지 않음. 웹 UI는 계속 사용할 수 있음. |
| `--log` | `--log-level info`의 호환성 별칭. |
| `--log-level debug\|info\|warning\|error` | 운영 로그 상세 수준. 기본값은 `error`. HTTP 액세스 로그는 `info`와 `debug`에서 활성화됨. |
| `--legacy-sync-dir DIR` | 시작 마이그레이션 중 레거시 책장 JSON을 읽음. |
| `--book-id-storage sidecar\|embedded` | 선택한 모든 소스의 안정적인 ID를 저장할 위치. 기본값은 `sidecar`. |
| `--admin-username NAME` | 무인 설정에 사용할 초기 관리자 이름. 지정하지 않으면 `EPUB_BROWSER_ADMIN_USERNAME` 사용. |
| `--admin-password-file FILE` | 초기 설정에 권장하는 시크릿 파일. 파일을 지정하지 않으면 `EPUB_BROWSER_ADMIN_PASSWORD_FILE`, 그다음 `EPUB_BROWSER_ADMIN_PASSWORD`를 대체 사용. |
| `--trusted-proxy-cidr CIDR` | `X-Forwarded-For`에서 클라이언트 IP를 안전하게 읽기 위해 신뢰할 직접 연결 프록시 네트워크. 여러 번 지정할 수 있음. |
| `--cookie-secure` | 브라우저 측 HTTPS를 통해서만 세션 쿠키를 전송. |
| `--kindle` | 구형 e-Ink Kindle용 종속성 없는 미니멀 페이지를 제공하고 Kindle WebKit 브라우저를 해당 페이지로 리디렉션. 기본값은 꺼짐. |

#### 레거시 v1 구문

레거시 구문은 v2 메이저 버전 전반에서 지원됩니다.

| v1 명령 | v2 매핑 |
| --- | --- |
| `epub-browser BOOKS` | `epub-browser server BOOKS --ephemeral` |
| `epub-browser BOOKS --output-dir STATE` | `epub-browser server BOOKS --server-dir STATE` |
| `epub-browser BOOKS --no-server --output-dir DIST` | `epub-browser ssg BOOKS --output-dir DIST` |
| `--sync-dir DIR` | `server --legacy-sync-dir DIR` |

레거시 전용 `--keep-files`는 임시 Server 디렉터리를 유지합니다. 영속적인 Server 디렉터리는 이미 영구적입니다.
`--log`를 사용하면 호환성 어댑터가 동등한 v2 명령을 출력하며, 지정하지 않으면 출력하지 않습니다.

### 읽기 데이터와 기능 배치

- EPUB/PDF 및 Calibre 라이브러리 재귀 검색, 메타데이터 태그, 검색, 병음 검색
- 반응형 라이브러리, 도서 상세, 장 읽기 인터페이스
- 스크롤, 페이지 넘김, 연속 읽기, 콘텐츠 너비 조정, 글꼴, 사용자 지정 CSS, 테마, 집중 읽기 모드
- 하이라이트, 노트, 주석 탐색, 중첩 책장 그룹, 태그, JSON 가져오기/내보내기
- 영어, 중국어 간체, 중국어 번체, 한국어, 일본어, 스페인어, 독일어, 프랑스어, 러시아어,
  이탈리아어, 브라질 포르투갈어, 아랍어, 인도네시아어, 힌디어, 베트남어, 태국어, 말레이어 인터페이스 로케일 지원
- Kindle/Silk 브라우저에 적합한 전자책 리더 동작. 브라우저의 고급 기능을 많이 사용하는 기능은 축소될 수 있음

| 데이터 | SSG | Server |
| --- | --- | --- |
| 읽기 진도 | 브라우저 로컬 | 인증된 사용자의 SQLite 레코드 |
| 하이라이트와 노트 | 브라우저 로컬 | 인증된 사용자의 SQLite 레코드 |
| 비공개 평점, 리뷰, 읽기 세션 기록 | 없음 | 인증된 사용자의 SQLite 레코드 |
| 책장 | 브라우저 로컬, 가져오기/내보내기 | 인증된 사용자의 버전 관리 클라우드 문서, 자동 저장 |
| 계정 및 세션 | 없음 | `<server-dir>/data` 아래의 SQLite |
| 도서 권한 부여 | 없음 | `<server-dir>/data` 아래의 SQLite |

Server는 로컬/클라우드 스토리지 선택기를 제공하지 않습니다. 인증된 읽기 데이터는 항상 Server에 저장됩니다.
상세한 비공개 읽기 세션 기록은 SSG에서 절대 생성되지 않습니다. SSG는 Server API에 접근하지 않으며
항상 현재 브라우저 오리진의 로컬 스토리지를 사용합니다.

### 자체 완결형 구성과 네트워크 동작

애플리케이션은 읽기에 필요한 구성을 자체적으로 갖추고 있습니다. 필요한 JavaScript, CSS, 글꼴, 아이콘, 매니페스트,
변환된 EPUB 리소스를 모두 로컬에서 제공합니다. 런타임 CDN 종속성이 없습니다. 외부 인터넷 액세스를 차단해도
설정, 로그인, 탐색, 읽기, 주석, 진도, 책장 사용, 관리, 소스 변환이 중단되지 않습니다.

푸터는 더 새로운 EPUB Browser 버전을 찾기 위해 GitHub Releases API에 선택적 요청을 보낼 수 있습니다.
실패, 차단, 오프라인 사용 시에는 해당 업데이트 힌트가 표시되지 않을 뿐입니다.

SSG는 정적 Service Worker를 게시합니다. Server는 한 계정이 다른 계정의 캐시된 보호 콘텐츠를 받지 않도록
오리진 전체 Service Worker를 의도적으로 비활성화하고 제거합니다.

### Server API 및 WebHooks

Server 계정은 Account settings에서 범위가 지정된 개인 액세스 토큰을 만들 수 있습니다. 외부 클라이언트는
버전이 지정된 `/api/v1/*` API에서 `Authorization: Bearer <PAT>`를 사용하며, 브라우저 쿠키로는 이 경로를 인증할 수 없습니다.
API는 사용자에게 표시되는 도서와 장 콘텐츠, 토큰 소유자의 책장, 진도, 주석, 리뷰를 다룹니다.
또한 `admin:data:read`가 있는 관리자 PAT는 다른 사용자의 데이터도 읽기 전용으로 조회할 수 있습니다.

OpenAPI 3.1 문서는 `/openapi.json`에서 제공되며, 로그인한 사용자는 `/api-docs`에서 로컬 참조를 볼 수 있습니다.
예: `curl -H 'Authorization: Bearer …' https://reader.example/api/v1/books`. 장 상세는 기본적으로 새니타이징된 HTML을 반환하며
`?format=text`를 지정하면 일반 텍스트를 반환합니다.

목록 엔드포인트는 `items`와 `next_cursor`를 반환합니다. `limit` 기본값은 24이고 최댓값은 100입니다.
동일한 필터를 유지하면서 `next_cursor`를 `cursor`로 전달하면 다음 페이지를 가져올 수 있습니다.
null 커서는 마지막 페이지를 나타냅니다. 예를 들어 `/api/v1/me/annotations?book_id=BOOK_ID&chapter_index=0&fields=id,text,note`를 사용하면
하나의 EPUB 장 또는 PDF 페이지에서 선택한 주석 필드를 가져올 수 있습니다.
쿼리 필터와 지원 필드는 OpenAPI 문서에 나열되어 있습니다.

어휘 목록도 기본적으로 동일한 목록 형식을 사용합니다. 이전 `words` 응답을 사용하는 클라이언트는
`page=1` 또는 `page_size`를 보내 레거시 페이지 매김 형식을 선택할 수 있습니다.

관리자는 Administration에서 WebHook 엔드포인트를 관리합니다. 시크릿은 생성 또는 교체할 때만 표시됩니다.
전달은 서명되고 영속화되며 2xx가 아닌 응답에서는 재시도됩니다. 도서 리뷰 이벤트에는 ID와 작업 타임스탬프가 포함되지만
평점이나 리뷰 본문은 절대 포함되지 않습니다.

### 데이터 안전 및 마이그레이션

영속적인 Server 설치를 업그레이드하기 전에 원본 EPUB/PDF 도서와 `<server-dir>/data`를 백업하세요.
컨테이너를 교체할 때도 동일한 영속 상태 볼륨을 유지하세요.

시작 마이그레이션은 자동이며 재시작해도 안전합니다. 레거시 데이터베이스를 검증하고 백업을 만든 다음 복사본을 업그레이드하며,
가져올 수 있는 레거시 책장/진도/주석 데이터를 생성 대기 중인 초기 관리자 계정으로 가져옵니다.
체크포인트가 성공한 후에만 교체 가능한 레거시 공개 아티팩트를 폐기합니다.
일반 요청은 레거시 동기화 디렉터리를 검색하지 않습니다. 손상된 데이터베이스, 유효하지 않은 비밀번호 해시, 모호한 레거시 데이터베이스, 충돌하는 ID가 발견되면
추측하거나 덮어쓰지 않고 시작을 중단합니다.

마이그레이션된 루트 `epub-browser.db` 또는 `annotations.db`는 민감한 복구용 사본으로 보관되며 기준 데이터는 아닙니다.
기준 데이터는 `data/epub-browser.db`이며 Server 요청은 보관된 루트 파일을 사용하지 않습니다.
복구 복사본은 비공개로 보관하세요. 기준 데이터베이스와 기록된 백업을 확인하고 v1 롤백이 더 이상 필요 없을 때,
Server가 중지된 상태에서만 수동으로 제거하세요. EPUB Browser가 자동으로 삭제하지는 않습니다.

레거시 루트에 `epub-browser.db`와 `annotations.db`가 모두 있으면 시작이 중단되고 두 파일 모두 변경되지 않습니다.
백업, 롤백, 캐시 재구축, 충돌 복구는 [v2로 마이그레이션](../migration-v2.md)을 참고하세요.

### 문제 해결

#### 명령은 시작됐지만 브라우저가 열리지 않음

그래픽 로컬 머신에서 실행할 때는 `--no-browser`를 제거하거나 출력/바인딩된 URL을 직접 여세요.
Docker, systemd, SSH, 비대화형 세션에서는 URL을 직접 여는 것이 정상입니다.

#### CLI 출력이 너무 적음

특히 비대화형 환경에서 `--log` 없이 출력이 적은 것은 의도된 동작입니다. 운영 및 액세스 상세 정보가 필요하면 `--log`를 추가하세요.
Server 스캔 진행률은 웹 인터페이스에 표시됩니다.

#### Docker가 안정적인 ID를 쓸 수 없음

이미지는 기본적으로 embedded ID 저장 방식을 사용합니다. `/app/Library`를 읽기/쓰기 가능으로 마운트하거나
일치하는 유효한 ID를 미리 embedded로 저장하세요. 쓰기 가능한 sidecar 저장 위치가 더 적합한 경우에만
사용자 지정 명령에서 `--book-id-storage sidecar`를 사용하세요.

#### 생성된 SSG 사이트의 하위 경로에서 링크가 깨짐

`/reader/`와 같이 정규화된 `--base-path`로 다시 생성하고, 동일한 접두사에서 출력을 제공하도록 정적 호스트를 구성하세요.

#### 업그레이드 후 Server가 시작을 거부함

처음 기록된 마이그레이션 또는 검증 오류를 확인하고 데이터와 소스 파일을 보존한 다음
[docs/migration-v2.md](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/migration-v2.md)를 참고하세요.
오류를 우회하려고 기준 데이터가 저장된 `data/` 디렉터리를 삭제하지 마세요.

## 개발 및 라이선스

### 기여

[dfface/epub-browser](https://github.com/dfface/epub-browser)에서 Issue와 Pull Request를 환영합니다.
유용한 보고서에는 실행한 명령, 브라우저/기기, 재현 단계, 관련 로그, 합법적으로 공유할 수 있는 경우 EPUB 또는 PDF를 포함하세요.

#### 유지 관리자를 위한 아키텍처 규약

콘텐츠 처리, 페이지 템플릿, 캐시, 권한, 자산 또는 배포 동작을 변경하기 전에 [AGENTS.md](../../AGENTS.md)를 읽으세요.
이 문서는 EPUB/PDF 형식 경계, SSG/Server 책임, 독립적인 캐시 리비전, 런타임 i18n 요구 사항,
보안 검사, 필수 검증을 정의합니다. *reader chapter*, *reading window*, *reading stage*, *content cache* 같은
공유 제품 용어는 [CONTEXT.md](../../CONTEXT.md)에 정의되어 있습니다.

핵심은 하나의 리더 UI를 유지하고, Server 전용 데이터를 SSG에서 제외하고, EPUB 및 PDF 파생 캐시를
SQLite 사용자 데이터와 분리하며, 런타임 CDN 종속성을 절대 추가하지 않는 것입니다.
공통 UI나 동작에 영향을 주는 변경은 해당하는 경우 두 형식과 두 배포 모드에서 모두 테스트해야 합니다.

#### 소스를 체크아웃하여 개발

타사 브라우저 파일은 프로젝트 소스가 아니라 생성되는 빌드 입력이므로 `epub_browser/assets/vendor/`는 의도적으로 Git에 포함되지 않습니다.
개발하거나 빌드하기 전에 잠금 파일에 지정된 정확한 버전을 명시적으로 가져온 다음 오프라인에서 검증하세요.

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
python3 -m unittest tests.test_vendor_assets -v
python3 -m build
```

위 명령 중 브라우저용 타사 자산을 다운로드하는 것은 `fetch`뿐입니다. 잠금 파일에는 불변 npm tarball,
파일 다이제스트, 허용 목록, 라이선스가 기록됩니다. `verify`, 테스트, 자산을 가져온 체크아웃에서의 빌드,
설치된 리더는 브라우저 자산을 다운로드하지 않습니다. 표준 격리 `python3 -m build` 명령도 빌드 요구 사항을 위해
Python 패키지 인덱스를 조회할 수 있습니다. 네트워크가 완전히 비활성화된 상태에서 빌드하려면 연결을 끊기 전에
타사 자산 트리를 가져오고 `build`, `setuptools`, `wheel`을 미리 설치한 다음
`PIP_NO_INDEX=1 python3 -m build --no-isolation`을 실행하세요. Wheel, 소스 배포판, Docker 이미지,
생성된 SSG 사이트에는 검증된 파일이 포함되며 런타임 CDN 종속성이 없습니다.
업데이트, 릴리스, 리포지토리 관리 워크플로는 [third_party/README.md](../../third_party/README.md)를 참고하세요.

### 라이선스

[MIT](../../License.txt)
