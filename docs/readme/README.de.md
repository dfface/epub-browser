# EPUB Browser

> **Mach aus Büchern Websites. Baue eine Bibliothek auf, die dir gehört.**
>
> Veröffentliche EPUB- und PDF-Bücher als statische Website oder betreibe eine private, selbst gehostete Bibliothek
> mit Konten, synchronisiertem Lesefortschritt, Anmerkungen und optionalem KI-nativem Lesen.

[Statische Bibliothek ansehen](https://epub-browser-test.yuhan.tech/) · [Private Bibliothek ausprobieren](#live-demos)

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/dfface/epub-browser/main/epub_browser/assets/logo-lockup-color.png" alt="EPUB-Browser-Logo" width="520">
</p>

[![PyPI-Version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python-Versionen](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![Lizenz](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![Ein PDF im gemeinsamen Reader von EPUB Browser mit Originalseite, Navigation, Designs und Lesewerkzeugen.](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser ist mehr als ein Buchkonverter. Es ist eine vollständige Leseplattform,
die du überall veröffentlichen oder selbst betreiben kannst. EPUB und PDF nutzen
dieselbe Bibliothek, Buchseite, Inhaltsverzeichnis, Lesemodi, Designs,
Fortschrittsverfolgung und Anmerkungsfunktionen. Jede PDF-Seite wird zu einem
Reader-Kapitel und lokal durch PDF.js in derselben Leseumgebung dargestellt –
ohne separaten Viewer und ohne CDN zur Laufzeit.

## Inhalt

- [Projektübersicht](#projektübersicht)
  - [Warum EPUB Browser](#warum-epub-browser)
  - [Technologie-Stack](#technologie-stack)
  - [Wahl zwischen SSG und Server](#wahl-zwischen-ssg-und-server)
  - [Live-Demos](#live-demos)
  - [KI-natives Lesen](#ki-natives-lesen-nur-server)
  - [Minimalmodus für Kindle](#minimalmodus-für-kindle)
- [Erste Schritte](#erste-schritte)
  - [Installation auswählen](#installation-auswählen)
  - [Schnellstart](#schnellstart)
- [Formate und Lesen](#formate-und-lesen)
  - [Quellen und stabile Buchidentität](#quellen-und-stabile-buchidentität)
  - [PDF: Eine Seite, ein Kapitel](#pdf-eine-seite-ein-kapitel)
- [Bereitstellung](#bereitstellung)
  - [SSG](#ssg)
  - [Server](#server)
  - [Docker](#docker)
- [Referenz und Betrieb](#referenz-und-betrieb)
  - [Befehlsreferenz](#befehlsreferenz)
  - [Lesedaten und Funktionen nach Modus](#lesedaten-und-funktionen-nach-modus)
  - [Server-API und WebHooks](#server-api-und-webhooks)
  - [Datensicherheit und Fehlerbehebung](#datensicherheit-und-migration)
- [Entwicklung und Lizenz](#entwicklung-und-lizenz)
- [Dokumentationsübersicht](../README.md)

## Projektübersicht

### Warum EPUB Browser

- **Überall veröffentlichen, die Kontrolle behalten.** Erzeuge mit einem Befehl
  eine vollständige statische Website für Pages, Objektspeicher oder Nginx oder
  betreibe einen dauerhaften Server mit Konten, Buchberechtigungen und OIDC.
  Anwendungsdateien, Schriftarten, PDF.js und Renderer werden lokal bereitgestellt,
  sodass das Lesen nie von einem CDN abhängt.
- **EPUB und PDF in einem echten Reader.** Beide Formate nutzen Bibliothek,
  Buchseite, Inhaltsverzeichnis, responsives Layout, drei Lesemodi, Designs,
  Vollbild und Fortschrittsverfolgung gemeinsam. Jede PDF-Seite bleibt in der
  Leseumgebung und bietet Zoom, Auswahl über die Textebene und Anmerkungen,
  statt in einer separaten Vorschau zu erscheinen.
- **Das Buch und die gesuchte Passage finden.** Die Bibliothekssuche umfasst
  Metadaten, Tags und Pinyin sowie Sortierung und Seitennavigation. Die
  serverseitige Volltextsuche in EPUB-Büchern liefert vollständige, nach Kapiteln
  gruppierte Ergebnisse und springt zur hervorgehobenen Passage. Stabile Buch-IDs
  halten Fortschritt, Anmerkungen und Verlauf mit dem jeweiligen Buch verbunden.
- **Verstehen statt nur scrollen.** Im Server-Modus bleiben EPUB-Kapitelführer,
  mit Belegen verknüpfte Erklärungen, Mindmaps und private Fragen an Ask AI direkt
  neben dem Ausgangstext. Markierungen, Notizen, Wörterbuch und Enzyklopädie
  funktionieren in EPUB und in PDFs mit Textebene; Server-Wortschatzlisten
  speichern Herkunft und Lernstand jedes Wortes.
- **Aus Lesen wird ein Verlauf, der es wert ist, aufbewahrt zu werden.**
  Verschachtelte Regale, Bewertungen, Rezensionen, Anmerkungsexport,
  Aktivitätskalender, Trends, Statistiken pro Buch und Lesezeit-Rankings bilden
  eine zusammenhängende Aufzeichnung. Der Server hält Lesedaten für jedes Konto
  privat und zwischen den Geräten synchronisiert.
- **Einen Lesedienst betreiben, nicht nur einen Viewer.** Im Server-Modus kannst
  du Bücher per Web-Upload durch Administratoren oder überwachte Ordner hinzufügen,
  die Speicherbelegung mit konfigurierbarer LRU-Cache-Bereinigung begrenzen,
  Mitglieder- und KI-Berechtigungen verwalten und OpenAPI, PATs und WebHooks
  integrieren. Der minimalistische Kindle-Reader unterstützt eingeschränkte
  Geräte; der Server bietet außerdem ein persönliches Kindle-Dashboard für den
  Ruhezustandsbildschirm mit Uhr, Kalender, Agenda, Notiz und Pomodoro-Timer.

![Ein Kapitelführer neben dem ursprünglichen EPUB-Text mit einer privaten Ask-AI-Seitenleiste.](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/readme/assets/ai-native-reading.png)

*KI-native Begleitung und private Fragen bleiben mit dem Originalbuch verknüpft.*

![Private Leseeinblicke mit Aktivitätskalender und Lesezeittrend.](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/readme/assets/reading-insights.png)

*Leseeinblicke machen aus aktivem Lesen einen nachvollziehbaren privaten Verlauf.*

### Technologie-Stack

EPUB Browser setzt bewusst auf einen kleinen, serverseitig gerenderten Web-Stack.
Die installierte Anwendung verwendet kein SPA-Framework und benötigt keine
Node.js-Laufzeit:

| Ebene | Technologie | Aufgabe |
| --- | --- | --- |
| Frontend | Semantisches HTML, CSS, VanillaJS mit ES-Modulen und Browser-APIs | Eine gemeinsame responsive Oberfläche für SSG und Server |
| CLI und Server | Python 3.9+, Starlette, Uvicorn | Konvertierungsbefehle, authentifizierte Seiten, APIs und Hintergrundaufgaben |
| Daten | SQLite und neu erzeugbare JSON-Inhaltscaches | Benutzerzustände bleiben von abgeleiteten EPUB-/PDF-Inhalten getrennt |
| Buchformate | lxml, pypdf, pypdfium2, PDF.js | Einheitliches, striktes EPUB-Parsing und Bereinigen mit Wiederherstellung bei Fehlern, PDF-Metadaten und -Cover, lokale Darstellung im Browser |
| Offline und Assets | Service Worker, unveränderliche Assets mit Hash, festgelegte gebündelte Abhängigkeiten | Eigenständige Bereitstellung ohne CDN zur Laufzeit |
| Distribution | PyPI, Docker, gewöhnliches statisches Hosting | Dieselbe Codebasis wird als SSG oder dauerhafter Server ausgeliefert |
| Optionale KI | OpenAI-kompatible APIs mit lokal gerendertem Markdown, KaTeX und Mermaid | EPUB-Lernebenen ausschließlich im Server-Modus |

Node.js wird nur von den Maintainern für browserseitige Tests verwendet; es gehört
nicht zur Produktionslaufzeit des Readers.

### Wahl zwischen SSG und Server

Dieselbe Quellenverarbeitung und dieselben Seitenvorlagen bilden die Grundlage
für zwei ausdrücklich getrennte Bereitstellungsmodi. Entscheide danach, wo die
Lesedaten liegen sollen, nicht nach dem Buchformat:

| Fähigkeit | `ssg` | `server` |
| --- | --- | --- |
| EPUB und PDF | Ja | Ja |
| Bereitstellung | Atomare statische HTML-Dateien und Assets für Pages, Objektspeicher oder Nginx | Dynamische authentifizierte Seiten auf Basis eines ersetzbaren Inhaltscaches |
| Konten und Zugriffskontrolle | Keine | Administrator- und Mitgliedskonten, Freigaben für eingeschränkte Bücher, Sitzungen und CSRF-Schutz |
| OIDC-Single-Sign-on | Nicht enthalten | Generischer Provider, Verknüpfung vorhandener Konten und optionale Bereitstellung von Mitgliedern |
| Fortschritt, Anmerkungen, Bücherregal | Im aktuellen Browser gespeichert | Pro authentifiziertem Konto in SQLite synchronisiert |
| Bewertungen, Rezensionen, Lesesitzungen | Nicht ausgegeben | Private Aufzeichnungen pro Konto und Leseeinblicke |
| Quellen aktualisieren | `ssg` erneut ausführen | Neu starten, erneut einlesen oder `--watch` verwenden |
| Verwaltung, Tags, OpenAPI, WebHooks | Nicht enthalten | Enthalten |
| KI-Lesen und Ask AI | Nicht enthalten | Für EPUB verfügbar, sofern konfiguriert und ausdrücklich freigegeben; für PDF ausgeblendet |
| Laufzeitdatenbank | Keine | Für den dauerhaften Modus erforderlich |
| Geeignet für | Öffentliches/statisches Hosting, Offline-Pakete, einfache persönliche Veröffentlichung | Eine private Bibliothek, mehrere Geräte oder Leser, Automatisierung und verwalteter Zugriff |

Verwende `ssg`, wenn das Ergebnis aus gewöhnlichen statischen Dateien bestehen soll. Verwende `server`, wenn Leser Konten, geräteübergreifende Daten, Zugriffskontrolle oder automatische Abgleichung der Quellen benötigen.

### Live-Demos

- **SSG-Modus**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Server-Modus**: [epub.yuhan.tech](https://epub.yuhan.tech/) — melde dich mit dem Benutzernamen `demo` und dem Passwort `demo` an.

### KI-natives Lesen (nur Server)

Für EPUB-Bücher kann der Server-Modus Kapitelführer, mit Belegen verknüpfte
Erklärungen, Mindmaps, Reflexionsfragen und eine private Ask-AI-Seitenleiste
hinzufügen, ohne den Leser aus dem Originaltext zu reißen. Die Ergebnisse
unterliegen weiterhin den Buchberechtigungen; Mitglieder müssen ausdrücklich
autorisiert werden, und SSG enthält weder KI-Steuerelemente oder Aufträge noch
Kontodaten oder Anbieterkonfigurationen. PDF blendet KI-Lesen und Ask AI
bewusst aus.

Das vollständige Interaktionsmodell beschreibt der [Leitfaden zum KI-nativen Lesen](../ai-native-reading.md).
Die [Hinweise zu lokalen Rich-Text-Renderern](../third-party-ai-renderers.md)
erläutern die Grenzen für Rendering und Netzwerksicherheit.

### Minimalmodus für Kindle

Ältere E-Ink-Kindles und andere eingeschränkte Browser erhalten eine
minimalistische Leseoberfläche ohne Abhängigkeiten. Aktiviere sie mit `--kindle`:

- SSG: `epub-browser ssg --kindle -o output/ SOURCE...`
- Server: `epub-browser server --kindle --server-dir data SOURCE...`

Jedes EPUB-Buch (PDF-Bücher sind ausgeschlossen) erhält drei zusätzliche Seiten:

- das minimalistische Bücherregal `/kindle-library.html`
- die Buchseite `/book/<id>/kindle.html`
- die Kapitelseite `/book/<id>/kindle_chapter_N.html`

Diese Seiten sind auf E-Ink abgestimmt: minimales Markup, Designs nur mit CSS,
ES5-kompatible Skripte, kein Service Worker und kein Framework. Das Lesen
funktioniert ganz ohne JavaScript. Der Wechsel des Designs (Hell / Sepia /
Dunkel), die Schriftgröße (A- / A+) und die Lokalisierung der Oberfläche werden
durch leichtgewichtige Inline-Skripte ergänzt, die auf dem einfachen HTML aufsetzen.

Jede Seite bietet Design- und Schriftsteuerung (in der Kopfzeile und auf
Kapitelseiten zusätzlich in der Fußzeile), Navigation im Inhaltsverzeichnis,
vorheriges/nächstes Kapitel und einen Link „Weiterlesen“, der beim gespeicherten
Fortschritt fortsetzt.

Der Lesefortschritt unterscheidet sich je nach Modus:

- **SSG:** Der Fortschritt wird in den Cookies des aktuellen Browsers gespeichert – lokal und ohne Konto.
- **Server:** Fortschritt und Lese-Heartbeats werden pro angemeldetem Konto in
  SQLite synchronisiert. Die Kindle-Oberflächen dienen nur zum Lesen und Melden:
  Sie speichern das aktuelle Kapitel, senden Heartbeats, zeigen ein schreibgeschütztes
  Bücherregal und bieten weder Leseeinblicke noch Inhaltsverwaltung.

Die Zugriffskontrolle gilt auf jeder Kindle-Oberfläche. Bei einem Buch mit
eingeschränkter Sichtbarkeit erhalten nicht berechtigte Benutzer 403 auf der
Buch- und Kapitelseite sowie über die Fortschritts-API; im minimalistischen
Bücherregal wird das Buch ausgelassen.

Unterstützte Browser (User-Agent mit `Kindle/`, `Arora/` usw.) werden automatisch
vom vollständigen Reader zu den minimalistischen Seiten weitergeleitet; die oben
genannten URLs funktionieren auch direkt. Damit ist der Minimalmodus ein
verlässlicher Fallback für Geräte mit geringer Leistung oder eingeschränkter
JavaScript-Unterstützung.

## Erste Schritte

### Installation auswählen

EPUB Browser unterstützt zwei Installationswege. Beide akzeptieren eine oder
mehrere `.epub`- oder `.pdf`-Dateien, verschachtelte Verzeichnisse oder ein
Bibliotheksverzeichnis im Calibre-Stil.

| Installation | Verwendung | Voraussetzung auf dem Host |
| --- | --- | --- |
| PyPI | SSG- oder Server-Modus | Python 3.9 oder neuer |
| Docker | Dauerhafter Server-Modus | Docker Engine; Python ist im Image enthalten |

#### PyPI (SSG oder Server)

Installiere die Befehlszeilenanwendung:

```bash
pip install epub-browser
```

Zeige die Befehlsreferenz für den jeweiligen Modus an:

```bash
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

#### Docker (Server)

Das veröffentlichte Image [`dfface/epub-browser`](https://hub.docker.com/r/dfface/epub-browser)
führt den Server-Modus aus und setzt kein Python auf dem Host voraus:

```bash
docker pull dfface/epub-browser:latest
```

Verwende `latest`, um die aktuelle Version zu testen; für eine reproduzierbare
Produktionsbereitstellung solltest du einen nummerierten Release-Tag festlegen.
Unter [Docker](#docker) findest du die erforderlichen Einhängepunkte für Bücher
und Zustände, einen Compose-Schnellstart, die Ersteinrichtung und Hinweise zum Netzwerk.

### Schnellstart

#### Statische Website erzeugen

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

Stelle `dist/` über HTTP bereit. Das direkte Öffnen erzeugter Seiten über `file://` wird nicht unterstützt, da Browserspeicher, Module, Manifeste und Service Workers einen HTTP-Ursprung benötigen.

Wenn die Website unter einem URL-Präfix gehostet wird, lege den öffentlichen Pfad getrennt vom Ziel im Dateisystem fest:

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist \
  --base-path /my-repository/
```

`--base-path` ändert die erzeugten URLs, nicht den Speicherort der Dateien. Mit `/my-repository/` verwenden Links, Symbole, Manifeste, Buchmetadaten und Service-Worker-Einträge dieses Präfix, während die Dateien weiterhin direkt in `dist/` liegen.

#### Dauerhafte Server-Bibliothek betreiben

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

Öffne `http://127.0.0.1:8000/`. Beim ersten Zugriff fordert EPUB Browser dich auf, den ersten Administrator zu erstellen. Die Bibliothek wird weder eingelesen noch veröffentlicht, bevor diese einmalige Einrichtung abgeschlossen ist.

Wenn du Docker gewählt hast, überspringe den obigen Python-Befehl und fahre mit dem
[Docker-Compose-Schnellstart](#docker-compose) fort.

## Formate und Lesen

### Quellen und stabile Buchidentität

Jede positionale Angabe `SOURCE` kann eine EPUB-Datei, eine PDF-Datei oder ein
Verzeichnis sein. Verzeichnisse werden rekursiv durchsucht. Ein Befehl kann
mehrere Quellen verarbeiten:

```bash
epub-browser server book.epub /srv/library /srv/periodicals \
  --server-dir /srv/epub-browser \
  --watch
```

Jedes Buch erhält eine stabile `book_id`, die in erzeugten URLs und Browserdaten auch als `book_hash` erscheint. Der allgemeine CLI-Standard lautet:

```bash
--book-id-storage sidecar
```

Im Sidecar-Modus wird eine sichtbare Identitätsdatei neben der Quelle abgelegt, etwa `BOOK.epub.epub-browser.json` oder `BOOK.pdf.epub-browser.json`; die Bytes der Quelle bleiben unverändert. Die Sidecar-Datei enthält die stabile ID und einen geprüften SHA-256-Fingerabdruck der Quelle.

Um die ID in den EPUB-OPF-Metadaten oder im Informations-Dictionary des PDF-Dokuments zu speichern, wähle für den gesamten Aufruf den eingebetteten Speicher:

```bash
--book-id-storage embedded
```

Der eingebettete Modus kann vor der Konvertierung das EPUB-ZIP neu aufbauen oder eine PDF-Metadatenaktualisierung anhängen. Wenn das PDF nicht aktualisiert werden kann und seine Quelle unverändert ist, speichert EPUB Browser dieselbe ID in einer benachbarten Sidecar-Datei. Dies gilt auch für signierte, verschlüsselte und schreibgeschützte PDFs. EPUB Browser bricht ab, wenn IDs voneinander abweichen, aktive Quellen eine ID mehrfach verwenden, ein Träger ungültig ist oder ein erforderlicher Träger nicht beschrieben werden kann.

Beim Wechsel des Speichermodus kopiert EPUB Browser die vorhandene ID auf den gewählten Träger und behält den anderen gültigen Träger. Eine vorhandene eingebettete ID aus v2.0.4 wird in die standardmäßige Sidecar-Datei kopiert, ohne das EPUB neu zu schreiben. Sowohl SSG als auch Server liefern nach einer Metadatenaktualisierung eine Byte-für-Byte-Kopie der PDF-Quelle aus.

### PDF: Eine Seite, ein Kapitel

PDF wird von beiden Bereitstellungsmodi unterstützt. Der Reader behandelt jede
PDF-Seite wie ein gewöhnliches EPUB-Browser-Kapitel. Daher bleiben Buchseite,
Kapitelnavigation, Inhaltsverzeichnis, Seitennavigation, kontinuierliches Lesen,
Fortschritt, Lesesitzungen, Anmerkungen, Wörterbuch und Enzyklopädie dieselbe
gemeinsame Oberfläche und dasselbe Datenmodell:

| PDF-Konzept | SSG | Server |
| --- | --- | --- |
| URL von Seite 1 | `chapter_0.html` | `/book/<book-id>/chapter_0.html` |
| URL von Seite N | `chapter_{N-1}.html` | `/book/<book-id>/chapter_{N-1}.html` |
| Seitenbezeichnungen und Inhaltsverzeichnis | Lokal erzeugt; jede Seite ist aufgeführt | Aus dem PDF-Metadatencache gerendert; jede Seite ist aufgeführt |
| Eingebettete Gliederung | Eine Markierung am Inhaltsverzeichniseintrag der Zielseite | Dieselbe Markierung, ohne Seiteneinträge zu entfernen oder umzuordnen |
| Scrollen, Seitennavigation und Umblättern | Statische Kapitelgerüste und lokales PDF.js | Dynamische gemeinsame Kapitelgerüste und lokales PDF.js |
| Markierungen, Notizen, Wörterbuch, Enzyklopädie | Gemeinsame browserlokale Komponenten bei vorhandener Textebene | Gemeinsame authentifizierte Komponenten bei vorhandener Textebene |
| Rohe PDF-Bytes | Eine `document.pdf` in der statischen Buchausgabe | Sitzungsgebundene Route mit Range-Unterstützung für das zwischengespeicherte Dokument |

Die sichtbaren Seitenzahlen und PDF.js zählen ab 1; Kapitelindizes in URLs,
Zuständen, APIs und SQLite zählen ab 0. PDF-Seite 1 ist daher immer
`chapter_0.html`. Das normalisierte Inhaltsverzeichnis enthält für jede Seite
einen Eintrag `Page N`; Titel aus der eingebetteten PDF-Gliederung werden als
Gliederungsmarkierungen an ihren Zieleintrag angehängt, auch mehrere Markierungen
auf derselben Seite.

SSG schreibt genau eine `document.pdf` und pro Seite ein Kapitelgerüst
`chapter_<index>.html`. Die SSG-Ausgabe enthält keine Sitzungsskripte,
`/api/*`-Aufrufe, synchronisierten Anmerkungsdaten oder Server-Abhängigkeiten.
Der Server speichert die vollständige, Byte-identische Quelle als
`book/<book-id>/pdf/document.pdf` und teilt oder verändert sie niemals. Der Server
rendert dieselben Kapitelgerüste dynamisch aus den PDF-Metadaten. Eine geänderte
Quelle macht den PDF-Cache ungültig und erneuert ihn vollständig (Dokument,
Metadaten und abgeleitetes Cover), statt alte und neue Seiten zu mischen.

Der Endpunkt für das Rohdokument auf dem Server ist sitzungsgebunden:
`GET`/`HEAD /api/books/<book-id>/document`. Er prüft Authentifizierung,
Sichtbarkeit des Buchs, PDF-Format und Fingerabdrücke von Quelle und Cache und
unterstützt anschließend begrenzte Antworten mit jeweils einem Byte-Bereich sowie
`ETag`, `Accept-Ranges`, privates Caching, `nosniff` und Inline-Darstellung des
PDF. Er gibt keinen absoluten Pfad preis, ist nicht für PAT-Authentifizierung
verfügbar und gehört nicht zur PAT-/OpenAPI-Schnittstelle. SSG besitzt nur die
lokale `document.pdf` und keine API für Rohdokumente.

PDFs mit einer nutzbaren PDF.js-Textebene verwenden genau das vorhandene
Auswahl-Popup und dieselbe Anmerkungskomponente für Markierungen und Notizen
sowie Wörterbuch und Enzyklopädie. Speicherung, Eigentümerschaft, Export,
Auflistung und Deep Links von Anmerkungen bleiben gemeinsam; es gibt weder eine
PDF-spezifische Anmerkungstabelle noch eine eigene Einstellungsoberfläche.
Gescannte oder reine Bild-PDFs bleiben lesbar, aber auswahlbasierte Markierungen,
Notizen, Wörterbuch, Enzyklopädie und Dokumentensuche sind ohne nutzbare
Textebene ausdrücklich nicht verfügbar. Eine Auswahl über mehrere Seiten kann
weiterhin kopiert werden; Anmerkungs- und Nachschlageaktionen zeigen dabei die
lokalisierte Meldung über die fehlende Unterstützung. Die Auswahl innerhalb
einer Seite funktioniert weiterhin.

PDF.js ist kein zweites Viewer-Gerüst. Lade vor dem Erstellen oder Veröffentlichen
die festgelegten Drittanbieter-Assets und überprüfe sie:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
```

Die Anwendung stellt zur Laufzeit lokale PDF.js-Modul- und Worker-Assets mit Hash
bereit und lädt sie niemals von einem CDN. Bild-Lightboxes verwenden die
festgelegte Abhängigkeit GLightbox; Fancyapps/Fancybox wird weder zur Laufzeit
benötigt noch weiterverteilt. Der Ablauf für festgelegte Assets und
Releases ist in [third_party/README.md](../../third_party/README.md) beschrieben.

## Bereitstellung

### SSG

SSG erstellt eine vollständige Momentaufnahme in einem benachbarten Staging-Verzeichnis, validiert sie und ersetzt anschließend das Ziel. Wenn eine Konvertierung fehlschlägt, bleibt das bisherige Ziel unverändert. Die erzeugte Ausgabe enthält keine Server-Datenbank, keinen Migrationszustand, keine Kontoseite und keine Metadaten des Laufzeitcaches.

SSG ist bewusst lokal und kontofrei:

- Lesefortschritt und Anmerkungen verwenden den Browserspeicher des aktuellen Ursprungs.
- Das Bücherregal unterstützt lokalen JSON-Import und -Export; es gibt keine Cloud-Synchronisation.
- Anmeldung, Kontoeinstellungen, Server-APIs und benutzerabhängige Steuerelemente fehlen.
- Das Speicherziel ist fest auf den lokalen Browserspeicher eingestellt und wird nicht als Option angeboten.
- Die statische Ausgabe enthält den Service Worker, der für offline verfügbare Assets erforderlich ist.

Alle erforderlichen JavaScript- und CSS-Dateien, Schriftarten und Symbole der Anwendung sind in der Ausgabe enthalten. Die einzige optionale Netzwerkanfrage beschreibt [Eigenständiger Betrieb und Netzwerkverhalten](#eigenständiger-betrieb-und-netzwerkverhalten).

### Server

#### Ersteinrichtung, Konten und Berechtigungen

In einem neuen dauerhaften Zustandsverzeichnis leiten normale Seiten zu `/setup` weiter. APIs, Ereignisströme, erzeugte Assets und Bücher liefern eine Antwort, die auf die erforderliche Einrichtung hinweist, bis der erste Administrator erstellt wurde. Schließe die Einrichtung über Loopback oder einen anderen vertrauenswürdigen privaten Pfad ab, bevor du den Port freigibst: Die erste erfolgreiche Einrichtung übernimmt das Administratorkonto.

Nach der Einrichtung gilt:

- Die öffentliche Registrierung ist geschlossen. Administratoren erstellen und verwalten Benutzer.
- Konten haben entweder die Rolle `administrator` oder `member`.
- Gewöhnliche Bücher sind für jedes authentifizierte Konto sichtbar.
- Eingeschränkte Bücher sind nur für Administratoren und ausdrücklich ausgewählte Benutzer sichtbar.
- Jedes Benutzerkonto besitzt sein Bücherregal, seinen Fortschritt, seine Anmerkungen und seine aktiven Sitzungen.
- Benutzer können ihr Passwort ändern und ihre Sitzungen widerrufen.
- Administratoren können Benutzer, Rollen, Passwörter, Sitzungen und Buchfreigaben verwalten.
- Sitzungen verwenden ein HttpOnly-Cookie, CSRF-Schutz und eine gleitende Laufzeit von 30 Tagen.

#### OIDC-Single-Sign-on und Kontoverknüpfung

Der Server-Modus kann einen generischen OpenID-Connect-Provider (OIDC) verwenden,
darunter Authelia, Keycloak, Authentik und kompatible Dienste. Gib unter
**Administration → OIDC-Anmeldung** den den Lesern angezeigten Providernamen,
die Issuer-URL, die Client-ID, das Client-Secret, die exakte Redirect-URI, die
Scopes und den Username-Claim ein. EPUB Browser verwendet Discovery und den
Authorization-Code-Flow mit S256-PKCE, validiert das signierte ID-Token und
identifiziert ein externes Konto ausschließlich anhand von `(issuer, sub)`;
E-Mail- und Benutzernamen-Claims sind Hinweise für Anzeige und Bereitstellung,
niemals Identitätsschlüssel.

Registriere beim Provider exakt diesen Callback einschließlich Schema und Host:

```text
https://reader.example.com/auth/oidc/callback
```

Vorhandene Benutzer können sich lokal anmelden und den Provider in den
Kontoeinstellungen verknüpfen. Bei einer unbekannten externen Identität werden
andernfalls einmalig der Benutzername und das Passwort eines vorhandenen lokalen
Kontos abgefragt. Die optionale automatische Bereitstellung erstellt ein Mitglied
ohne Passwort und importiert niemals eine Administratorrolle. Lasse vorhandene
Benutzer zuerst ihre Konten verknüpfen: Wird die automatische Bereitstellung zu
früh aktiviert, können **doppelte lokale Konten** entstehen. Die Passwortanmeldung
des **lokalen Administrators** bleibt immer verfügbar, selbst wenn die lokale
Passwortanmeldung für Mitglieder deaktiviert ist. Teste und schütze dieses
Wiederherstellungskennwort. Ein Provider-Logout wird nicht durchgeführt, und
Zugriffs- oder Refresh-Tokens des Providers werden nicht gespeichert.

Konfiguriere für Authelia einen vertraulichen Client im Abschnitt des OIDC-Providers.
Der folgende Auszug verwendet absichtlich falsche Werte und setzt voraus, dass die
von Authelia benötigten Provider-Schlüssel und Richtlinien bereits konfiguriert
sind. Speichere in Authelia einen Hash eines starken zufälligen Client-Secrets
und gib das zugehörige Secret im Klartext anschließend einmal in EPUB Browser ein:

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

Verwende in EPUB Browser den Issuer `https://auth.example.com`, die Client-ID
`epub-browser`, die Scopes `openid profile email` und den Username-Claim
`preferred_username`. Beim Speichern werden Discovery und Fähigkeiten live geprüft;
bei einem Fehler bleibt die bisherige Konfiguration aktiv.

#### KI-Lesen konfigurieren und verwalten

Administratoren konfigurieren KI-Lesen unter **Administration**, direkt nach der
Benutzerverwaltung und vor der Buchverwaltung. Die Seite speichert eine
OpenAI-kompatible Base-URL, einen API-Schlüssel, das Modell, das Timeout, das
Kontextbudget, die maximale Parallelität und das standardmäßige tägliche Limit
für Anbieteraufrufe in der SQLite-Datenbank des Servers. KI ist für Mitglieder
zunächst deaktiviert; ein Administrator muss den Zugriff pro Mitglied freigeben
und kann ein individuelles Tageslimit festlegen (`0` bedeutet unbegrenzt).

Lernebenen für Kapitel und buchweite Rezensionen werden pro geeigneter Sprache
gemeinsam genutzt, während Folgegespräche für jedes Konto privat bleiben.
Ergebnisse, Aufgabenzustände, eigene Tags, die Leseklassifizierung von Büchern
und private Folgegespräche werden in SQLite gespeichert. Nach einer Änderung der
Modellkonfiguration bleiben alte Ergebnisse verfügbar, bis ein Administrator sie
ausdrücklich neu erzeugt.

Wenn ein Leser einen KI-Führer anfordert oder eine Frage stellt, werden
ausgewählter EPUB-Text und der komprimierte Gesprächskontext an den konfigurierten
externen Anbieter gesendet. Aktiviere die Funktion nur, wenn Leser diese Inhalte
an den Anbieter übermitteln dürfen. Der API-Schlüssel wird niemals an einen
Browser zurückgegeben oder über eine API offengelegt; schütze das
Server-Zustandsverzeichnis entsprechend.

Für einen unbeaufsichtigten ersten Start gib eine Benutzernamen- und eine Passwortdatei an:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --admin-username admin \
  --admin-password-file /run/secrets/epub-browser-admin-password \
  --no-browser
```

Die Passwortdatei sollte den Modus `0600` haben. EPUB Browser entfernt einen abschließenden Zeilenumbruch, speichert einen Argon2id-Hash und gibt das Secret niemals aus. Eine unvollständige Konfiguration, eine leere Datei oder eine unlesbare Datei verhindert den Start. Nach abgeschlossener Einrichtung wird das Bootstrap-Secret bei späteren Starts nicht mehr gelesen.

Die Entsprechungen in der Umgebung sind `EPUB_BROWSER_ADMIN_USERNAME` und `EPUB_BROWSER_ADMIN_PASSWORD_FILE`. `EPUB_BROWSER_ADMIN_PASSWORD` dient nur als Klartext-Fallback, wenn keine Passwortdatei konfiguriert ist. Ein per CLI angegebener Pfad zur Passwortdatei hat Vorrang vor Passwortquellen aus der Umgebung.

#### Browserstart und Protokollierung

Standardmäßig versucht der Server nach dem Start des HTTP-Listeners den Standardbrowser des Betriebssystems zu öffnen. `--no-browser` verhindert diesen lokalen Start. Die Option **deaktiviert weder die Weboberfläche noch den Browserzugriff**; sie unterdrückt nur den lokalen Aufruf `webbrowser.open(...)`. Verwende sie für Docker, systemd, SSH-Sitzungen, Rechner ohne grafische Oberfläche und Skripte.

Standardmäßig (`--log-level error`) gibt die CLI nur Fehler aus, damit Fortschrittsanzeigen im Terminal nicht durch routinemäßige Meldungen oder Warnungen unterbrochen werden. Ein interaktives Terminal zeigt die gebundene URL einmal an; nicht interaktive Docker- und Dienstläufe bleiben ansonsten still. Verwende `--log-level warning`, um Warnungen einzuschließen, `--log-level info` für Betriebs- und HTTP-Zugriffsprotokolle oder `--log-level debug` für die ausführlichsten Angaben. `--log` bleibt ein Kompatibilitätsalias für `--log-level info`.

Erste Scans und Scans durch die Überwachung erscheinen in der Weboberfläche statt als `tqdm` im Terminal. Eine erfolgreiche Zusammenfassung wird automatisch geschlossen; Fehler bleiben sichtbar, bis sie verworfen werden. Mit `--watch` startet das Korrigieren oder Ersetzen einer Quelle einen weiteren Scan, ohne dass ein manueller erneuter Versuch erforderlich ist.

#### Dauerhafter und flüchtiger Zustand

Der dauerhafte Server-Modus erfordert `--server-dir`. Für einen einmaligen Lauf verwende stattdessen `--ephemeral`:

```bash
epub-browser server book.epub --ephemeral
```

Der flüchtige Zustand wird beim Beenden gelöscht. Da bei jedem Lauf eine neue Datenbank entsteht, muss die Einrichtung wiederholt werden, sofern keine Zugangsdaten für den unbeaufsichtigten Start angegeben werden.

Dauerhafte Verzeichnisstruktur:

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

Nur `data/` ist maßgeblich. `cache/` kann gelöscht und neu erstellt werden. Bewahre `data/` über Upgrades und den Austausch von Containern hinweg auf. Eine Betriebssystem-Sperre gewährleistet exklusiven Zugriff; `.server.lock` kann nach einem normalen Beenden als Diagnosemetadaten erhalten bleiben.

Speichere die dauerhafte Datei `data/epub-browser.db` auf einem lokalen Dateisystem. Gemeinsam genutzte oder Netzwerkdateisysteme werden für WAL-Parallelität nicht unterstützt. Geprüfte Sicherungen bleiben unter `data/backups/` und enthalten alle committeten WAL-Daten.

#### LAN und Reverse Proxy

Der Server bindet standardmäßig an `127.0.0.1:8000`. Für ein vertrauenswürdiges LAN:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --port 8080 \
  --no-browser
```

Setze den eingebauten HTTP-Server nicht direkt dem öffentlichen Internet aus. Beende TLS an einem Reverse Proxy, wende Netzwerkkontrollen an und aktiviere sichere Cookies.

Um hinter einem Reverse Proxy echte Client-IPs in aktiven Sitzungen und Anmeldelimits zu erfassen, konfiguriere das **Netzwerk der unmittelbar verbundenen Proxys** (nicht die öffentlichen Client-Netzwerke):

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

Wiederhole `--trusted-proxy-cidr` für jede direkte Proxy-Adresse oder jedes direkte Proxy-Netzwerk. Nur Anfragen, deren unmittelbarer Gegenpunkt zu einem dieser CIDRs gehört, dürfen `X-Forwarded-For` liefern; bei allen anderen Gegenpunkten wird nur deren direkte Adresse gespeichert. Die Verarbeitung weitergeleiteter Adressen durch Uvicorn ist deaktiviert, sodass `Forwarded` und `FORWARDED_ALLOW_IPS` diese Vertrauensgrenze nicht erweitern können. Verwende `--cookie-secure` nur, wenn der Browser den Dienst über HTTPS erreicht.

### Docker

Das Image führt den dauerhaften Server-Modus mit folgenden Standardeinstellungen aus:

- `/app/Library` als Quelle
- `/app/EpubBrowserFiles` als dauerhafter Zustand
- `--watch`
- `--no-browser`
- `--host 0.0.0.0 --port 80`
- `--book-id-storage embedded`

Da eingebettete Identitäten EPUB- oder PDF-Dateien ändern können, binde die Bibliothek mit Lese- und Schreibzugriff ein. Binde den Server-Zustand ebenfalls mit Lese- und Schreibzugriff ein und bewahre ihn beim Austausch des Containers:

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  dfface/epub-browser:latest
```

Rufe `http://127.0.0.1:8080/setup` auf, bevor du die Portbindung oder Proxy-Regeln änderst.

#### Docker Compose

Das Repository enthält eine [docker-compose.yml](../../docker-compose.yml) für Benutzer, die Compose bevorzugen. Erstelle in einem Checkout `Library/`, lege dort EPUB- oder PDF-Bücher ab und führe anschließend Folgendes aus:

```bash
docker compose up -d --build
```

Dadurch wird nur `127.0.0.1:8080` veröffentlicht, die EPUB-/PDF-Quellen bleiben in `./Library`, und der Server-Zustand wird in `./EpubBrowserFiles` gespeichert. Der vollständige Server-Befehl `command` ist absichtlich in der Datei sichtbar, damit bereitstellungsspezifische Flags hinzugefügt werden können, ohne einen impliziten Image-Standard zu ersetzen. Schließe die einmalige Einrichtung unter `http://127.0.0.1:8080/setup` ab. Behalte für Fernzugriff diese Loopback-Bindung bei und setze einen authentifizierten TLS-Reverse-Proxy davor.

Für eine unbeaufsichtigte Einrichtung:

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

Nach dem ersten erfolgreichen Start kann die einmalige Secret-Einhängung entfernt werden. Eine schreibgeschützte Bibliothek funktioniert nur, wenn jedes EPUB bereits eine passende gültige eingebettete ID enthält. Vorhandene Sidecar-Dateien bleiben erhalten, wenn ihre IDs eingebettet werden.

Binde `/app/SyncData:ro` nur während des Imports älterer Bücherregal-JSON-Daten ein:

```bash
-v /path/to/legacy-sync:/app/SyncData:ro
```

Der in den Beispielen an Loopback veröffentlichte Port hält den Container innerhalb der Host-Grenze. Verwende für Fernzugriff einen TLS-Reverse-Proxy, konfiguriere den tatsächlichen CIDR des Container-Netzwerks und füge `--cookie-secure` hinzu.

## Referenz und Betrieb

### Befehlsreferenz

#### `epub-browser ssg SOURCE [SOURCE ...]`

| Option | Bedeutung |
| --- | --- |
| `--output-dir DIR`, `-o DIR` | Erforderliches Ziel für die atomare statische Momentaufnahme. |
| `--base-path PATH` | Öffentliches URL-Präfix; Standard `/`. Es muss mit `/` beginnen und enden. |
| `--book-id-storage sidecar\|embedded` | Träger der stabilen Identität für jede ausgewählte Quelle; Standard `sidecar`. |
| `--kindle` | Erzeugt minimalistische Seiten ohne Abhängigkeiten für ältere E-Ink-Kindles und leitet Kindle-WebKit-Browser dorthin weiter; standardmäßig deaktiviert. |
| `--log` | Kompatibilitätsalias für `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Ausführlichkeit der Betriebsprotokolle; Standard `error`, wodurch routinemäßige Konvertierungsausgaben und Warnungen unterdrückt werden. |

#### `epub-browser server SOURCE [SOURCE ...]`

Genau eine der Optionen `--server-dir` und `--ephemeral` ist erforderlich.

| Option | Bedeutung |
| --- | --- |
| `--server-dir DIR` | Wurzelverzeichnis für dauerhafte maßgebliche Daten und ersetzbare Caches. |
| `--ephemeral` | Verwendet flüchtigen Zustand; schließt `--server-dir` gegenseitig aus. |
| `--watch`, `-w` | Überwacht Quellen und gleicht Hinzufügungen, Aktualisierungen, Verschiebungen und Löschungen ab. |
| `--host ADDRESS` | Bind-Adresse; Standard `127.0.0.1`. |
| `--port PORT`, `-p PORT` | Bind-Port; Standard `8000`. |
| `--no-browser` | Startet den lokalen Standardbrowser nicht. Die Weboberfläche bleibt verfügbar. |
| `--log` | Kompatibilitätsalias für `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Ausführlichkeit der Betriebsprotokolle; Standard `error`. HTTP-Zugriffsprotokolle werden bei `info` und `debug` aktiviert. |
| `--legacy-sync-dir DIR` | Liest ältere Bücherregal-JSON-Daten während der Migration beim Start. |
| `--book-id-storage sidecar\|embedded` | Träger der stabilen Identität für jede ausgewählte Quelle; Standard `sidecar`. |
| `--admin-username NAME` | Erster Administrator für den unbeaufsichtigten Start; Fallback `EPUB_BROWSER_ADMIN_USERNAME`. |
| `--admin-password-file FILE` | Bevorzugte Datei für das erste Secret; Fallback `EPUB_BROWSER_ADMIN_PASSWORD_FILE`, dann `EPUB_BROWSER_ADMIN_PASSWORD`, wenn keine Datei festgelegt ist. |
| `--trusted-proxy-cidr CIDR` | Wiederholbare Vertrauensgrenze für unmittelbar verbundene Proxy-Netzwerke zur sicheren Auswertung der Client-IP aus `X-Forwarded-For`. |
| `--cookie-secure` | Sendet das Sitzungscookie nur über die HTTPS-Verbindung zwischen Browser und Dienst. |
| `--kindle` | Stellt minimalistische Seiten ohne Abhängigkeiten für ältere E-Ink-Kindles bereit und leitet Kindle-WebKit-Browser dorthin weiter; standardmäßig deaktiviert. |

#### Legacy-v1-Syntax

Die alte Syntax wird über die gesamte Hauptversionslinie v2 unterstützt:

| v1-Befehl | Zuordnung in v2 |
| --- | --- |
| `epub-browser BOOKS` | `epub-browser server BOOKS --ephemeral` |
| `epub-browser BOOKS --output-dir STATE` | `epub-browser server BOOKS --server-dir STATE` |
| `epub-browser BOOKS --no-server --output-dir DIST` | `epub-browser ssg BOOKS --output-dir DIST` |
| `--sync-dir DIR` | `server --legacy-sync-dir DIR` |

Das nur in der alten Version vorhandene `--keep-files` bewahrt ein temporäres Server-Verzeichnis. Dauerhafte Server-Verzeichnisse sind ohnehin beständig. Mit `--log` gibt der Kompatibilitätsadapter den entsprechenden v2-Befehl aus; andernfalls bleibt er still.

### Lesedaten und Funktionen nach Modus

- Rekursive Erkennung von EPUB/PDF und Calibre-Bibliotheken, Metadaten-Tags, Suche und Pinyin-Suche
- Responsive Oberflächen für Bibliothek, Buchdetails und Kapitellektüre
- Scrollen, Umblättern, kontinuierliches Lesen, anpassbare Inhaltsbreite, Schriftarten, eigenes CSS, Designs und reiner Lesemodus
- Markierungen, Notizen, Anmerkungsübersicht, verschachtelte Bücherregalgruppen, Tags und JSON-Import/-Export
- Oberflächensprachen: Englisch, vereinfachtes Chinesisch, traditionelles Chinesisch,
  Koreanisch, Japanisch, Spanisch, Deutsch, Französisch, Russisch, Italienisch,
  brasilianisches Portugiesisch, Arabisch, Indonesisch, Hindi, Vietnamesisch,
  Thailändisch und Malaiisch
- E-Reader-freundliches Verhalten für Kindle-/Silk-Browser; aufwendige Browserfunktionen können eingeschränkt sein

| Daten | SSG | Server |
| --- | --- | --- |
| Lesefortschritt | Lokal im Browser | SQLite-Datensatz des authentifizierten Benutzers |
| Markierungen und Notizen | Lokal im Browser | SQLite-Datensätze des authentifizierten Benutzers |
| Private Bewertungen, Rezensionen und Verlauf der Lesesitzungen | Nicht vorhanden | SQLite-Datensätze des authentifizierten Benutzers |
| Bücherregal | Lokal im Browser; Import/Export | Versioniertes Cloud-Dokument des authentifizierten Benutzers; automatisches Speichern |
| Konten und Sitzungen | Nicht vorhanden | SQLite unter `<server-dir>/data` |
| Buchfreigaben | Nicht vorhanden | SQLite unter `<server-dir>/data` |

Der Server bietet keinen Umschalter zwischen lokalem und Cloud-Speicher: Authentifizierte Lesedaten werden immer auf dem Server gespeichert. Der detaillierte private Verlauf von Lesesitzungen wird von SSG niemals ausgegeben. SSG fragt niemals Server-APIs ab und verwendet stets den lokalen Speicher des aktuellen Browser-Ursprungs.

### Eigenständiger Betrieb und Netzwerkverhalten

Die Anwendung ist für das Lesen eigenständig: Erforderliches JavaScript, CSS, Schriftarten, Symbole, Manifeste und konvertierte EPUB-Ressourcen werden lokal bereitgestellt. Es gibt keine CDN-Abhängigkeiten zur Laufzeit. Das Blockieren ausgehender Internetzugriffe verhindert weder Einrichtung, Anmeldung, Stöbern, Lesen, Anmerkungen, Fortschritt, Bücherregalnutzung oder Verwaltung noch die Konvertierung der Quellen.

Die Fußzeile kann optional die GitHub-Releases-API abfragen, um eine neuere EPUB-Browser-Version zu erkennen. Ein Fehler, eine Blockierung oder Offline-Betrieb unterdrückt lediglich diesen Update-Hinweis.

SSG veröffentlicht einen statischen Service Worker. Der Server deaktiviert und entfernt den ursprungsweiten Service Worker bewusst, damit ein Konto keine zwischengespeicherten geschützten Inhalte eines anderen Kontos erhalten kann.

### Server-API und WebHooks

Server-Konten können in den Kontoeinstellungen persönliche Zugriffstoken mit festgelegtem Geltungsbereich erstellen. Externe Clients verwenden `Authorization: Bearer <PAT>` mit der versionierten `/api/v1/*`-API; Browser-Cookies authentifizieren diese Routen nicht. Die API umfasst sichtbare Bücher und Kapitelinhalte, Bücherregal, Fortschritt, Anmerkungen und Rezensionen des Token-Inhabers sowie schreibgeschützte benutzerübergreifende Daten für Administrator-PATs mit `admin:data:read`.

Das OpenAPI-3.1-Dokument ist unter `/openapi.json` verfügbar; angemeldete Benutzer können die lokale Referenz unter `/api-docs` durchsehen. Beispiel: `curl -H 'Authorization: Bearer …' https://reader.example/api/v1/books`. Kapiteldetails liefern standardmäßig bereinigtes HTML und mit `?format=text` reinen Text.

Listen-Endpunkte liefern `items` und `next_cursor`. Der Standardwert für `limit` ist 24, der Höchstwert 100. Übergib `next_cursor` als `cursor` mit denselben Filtern, um die nächste Seite abzurufen. Ein Cursor mit dem Wert null kennzeichnet die letzte Seite. Verwende beispielsweise `/api/v1/me/annotations?book_id=BOOK_ID&chapter_index=0&fields=id,text,note`, um ausgewählte Anmerkungsfelder aus einem EPUB-Kapitel oder einer PDF-Seite abzurufen. Abfragefilter und unterstützte Felder sind im OpenAPI-Dokument aufgeführt.

Der Wortschatz verwendet standardmäßig dasselbe Listenformat. Clients, die die ältere `words`-Antwort verwenden, können `page=1` oder `page_size` senden, um das alte Seitenformat auszuwählen.

Administratoren verwalten WebHook-Endpunkte unter Administration. Secrets werden nur beim Erstellen oder Rotieren angezeigt. Zustellungen werden signiert und dauerhaft gespeichert, bei Nicht-2xx-Antworten erneut versucht; Ereignisse zu Buchrezensionen enthalten IDs und Aktionszeitstempel, aber niemals Bewertungen oder Rezensionstext.

### Datensicherheit und Migration

Sichere vor dem Upgrade dauerhafter Server-Installationen die EPUB-/PDF-Quellen und `<server-dir>/data`. Behalte beim Austausch von Containern dasselbe dauerhafte Zustandsvolume bei.

Die Migration beim Start erfolgt automatisch und ist neustartsicher. Sie prüft alte Datenbanken, erstellt eine Sicherung, aktualisiert eine Kopie, importiert geeignete alte Bücherregal-, Fortschritts- und Anmerkungsdaten in den noch einzurichtenden ersten Administrator und entfernt erst nach erfolgreichen Prüfpunkten ersetzbare alte öffentliche Artefakte. Gewöhnliche Anfragen durchsuchen niemals alte Synchronisierungsverzeichnisse. Beschädigte Datenbanken, ungültige Passwort-Hashes, mehrdeutige alte Datenbanken und widersprüchliche IDs führen zu einem sicheren Abbruch, statt geschätzt oder überschrieben zu werden.

Eine migrierte `epub-browser.db` oder `annotations.db` im Wurzelverzeichnis bleibt als vertrauliche, nicht maßgebliche Wiederherstellungskopie erhalten; `data/epub-browser.db` ist maßgeblich, und Server-Anfragen verwenden die im Wurzelverzeichnis verbliebene Datei nicht. Halte die Wiederherstellungskopie privat. Entferne sie nur manuell bei gestopptem Server, nachdem du die maßgebliche Datenbank und die erfasste Sicherung geprüft hast, und nur wenn kein Rollback auf v1 mehr erforderlich ist. EPUB Browser löscht sie niemals automatisch.

Wenn im alten Wurzelverzeichnis sowohl `epub-browser.db` als auch `annotations.db` vorhanden sind, wird der Start abgebrochen und beide bleiben unverändert. Informationen zu Sicherung, Rollback, Cache-Neuaufbau und Konfliktlösung findest du unter [Migration auf v2](../migration-v2.md).

### Fehlerbehebung

#### Der Befehl wurde gestartet, aber kein Browser geöffnet

Entferne `--no-browser` auf einem lokalen Rechner mit grafischer Oberfläche oder öffne die ausgegebene/gebundene URL manuell. Bei Docker, systemd, SSH und nicht interaktiven Sitzungen wird erwartet, dass du die URL selbst öffnest.

#### Die CLI scheint keine Meldungen auszugeben

Der stille Betrieb ohne `--log` ist beabsichtigt, insbesondere in nicht interaktiven Umgebungen. Füge `--log` für Betriebs- und Zugriffsdetails hinzu. Der Fortschritt von Server-Scans wird in der Weboberfläche angezeigt.

#### Docker kann keine stabile ID schreiben

Das Image verwendet standardmäßig eingebettete Identitäten. Binde `/app/Library` mit Lese- und Schreibzugriff ein oder bette vorher gültige passende IDs ein. Verwende einen eigenen Befehl mit `--book-id-storage sidecar` nur, wenn ein beschreibbarer Sidecar-Träger vorzuziehen ist.

#### Eine erzeugte SSG-Website hat unterhalb eines Unterpfads defekte Links

Erzeuge sie mit einem normalisierten `--base-path` wie `/reader/` neu und konfiguriere den statischen Host so, dass er die Ausgabe unter demselben Präfix bereitstellt.

#### Der Server startet nach einem Upgrade nicht

Lies den ersten protokollierten Migrations- oder Validierungsfehler, bewahre Daten und Quelldateien auf und konsultiere [docs/migration-v2.md](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/migration-v2.md). Lösche nicht das maßgebliche Verzeichnis `data/`, um einen Fehler zu umgehen.

## Entwicklung und Lizenz

### Mitwirken

Issues und Pull Requests sind bei [dfface/epub-browser](https://github.com/dfface/epub-browser) willkommen. Ein hilfreicher Bericht enthält den genauen Befehl, Browser/Gerät, Schritte zur Reproduktion, relevante Protokolle und das EPUB oder PDF, sofern es rechtlich zulässig geteilt werden kann.

#### Architekturvorgaben für Maintainer

Lies [AGENTS.md](../../AGENTS.md), bevor du Inhaltsverarbeitung, Seitenvorlagen,
Caches, Berechtigungen, Assets oder Bereitstellungsverhalten änderst. Die Datei
definiert die Formatgrenze zwischen EPUB und PDF, die Zuständigkeiten von SSG und
Server, unabhängige Cache-Revisionen, Anforderungen an i18n zur Laufzeit,
Sicherheitsprüfungen und die erforderliche Verifikation. Gemeinsame Produktbegriffe
wie *Reader-Kapitel*, *Lesefenster*, *Lesebühne* und *Inhaltscache* werden in
[CONTEXT.md](../../CONTEXT.md) definiert.

Kurz gesagt: Verwende eine einzige Reader-Oberfläche, halte Server-spezifische
Daten aus SSG heraus, trenne abgeleitete EPUB- und PDF-Caches von SQLite-Benutzerdaten
und füge niemals eine CDN-Abhängigkeit zur Laufzeit hinzu. Eine Änderung an einer
gemeinsamen Oberfläche muss, soweit zutreffend, mit beiden Formaten und beiden
Bereitstellungsmodi getestet werden.

#### Entwicklung aus einem Quell-Checkout

Drittanbieterdateien für den Browser sind erzeugte Build-Eingaben und kein
Projektquellcode; deshalb ist `epub_browser/assets/vendor/` absichtlich nicht in
Git enthalten. Lade vor dem Entwickeln oder Erstellen ausdrücklich die exakt
festgelegten Versionen und überprüfe sie anschließend offline:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
python3 -m unittest tests.test_vendor_assets -v
python3 -m build
```

`fetch` ist der einzige der obigen Befehle, der Browser-Vendor-Assets herunterlädt.
Die Sperrdatei erfasst unveränderliche npm-Tarballs, Datei-Digests, Allowlists
und Lizenzen; `verify`, Tests, Builds aus einem aufgefüllten Checkout und der
installierte Reader laden keine Browser-Assets herunter. Der isolierte Standardbefehl
`python3 -m build` kann weiterhin einen Python-Paketindex für Build-Anforderungen
abfragen. Für einen Build ganz ohne Netzwerk fülle den Vendor-Baum auf und
installiere `build`, `setuptools` und `wheel`, bevor du die Verbindung trennst;
führe anschließend `PIP_NO_INDEX=1 python3 -m build --no-isolation` aus. Wheels,
Quell-Distributionen, Docker-Images und erzeugte SSG-Websites enthalten die geprüften
Dateien und benötigen zur Laufzeit kein CDN. Der Ablauf für Aktualisierungen,
Releases und Repository-Hygiene steht in [third_party/README.md](../../third_party/README.md).

### Lizenz

[MIT](../../License.txt)
