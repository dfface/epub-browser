# EPUB Browser

> EPUB und PDF in einer privaten Lesebibliothek oder als eigenständige statische Website.

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

**Oberflächensprachen (17):** Englisch, vereinfachtes Chinesisch, traditionelles Chinesisch, Japanisch, Koreanisch, Spanisch, Deutsch, Französisch, Russisch, Italienisch, brasilianisches Portugiesisch, Arabisch, Indonesisch, Hindi, Vietnamesisch, Thailändisch und Malaiisch.

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![Eine PDF-Seite im gemeinsamen EPUB-Browser-Reader.](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser verarbeitet `.epub` und `.pdf` in zwei klar getrennten Betriebsarten:

| | `ssg` | `server` |
| --- | --- | --- |
| EPUB und PDF | Ja | Ja |
| Bereitstellung | Statisches Hosting, Pages, Objektspeicher, Nginx | Dauerhafter privater Lesedienst |
| Konten | Keine | Lokale Konten |
| Fortschritt, Anmerkungen, Bücherregal | Nur in diesem Browser | Daten des angemeldeten Kontos in SQLite |
| Quellen aktualisieren | `ssg` erneut ausführen | Dienst neu starten oder `--watch` verwenden |
| Laufzeitdatenbank | Keine | Erforderlich |

PDF ist ein gleichwertiges Buchformat: PDF-Seite 1 wird zu `chapter_0.html`, jede Seite erscheint im Inhaltsverzeichnis und wird lokal mit PDF.js in derselben Bibliothek, Buchseite, Leseoberfläche, Suche und Anmerkungsfunktion dargestellt. Nicht unterstützte PDF-Funktionen wie KI-Lesen werden ausdrücklich ausgeblendet; zur Laufzeit wird kein CDN benötigt.

Verwende `ssg`, wenn gewöhnliche statische Dateien veröffentlicht werden sollen. Verwende `server` für Konten, geräteübergreifende Daten, Zugriffskontrolle oder die automatische Überwachung der Quellen.

## Demos

- **SSG-Modus**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Server-Modus**: [epub.yuhan.tech](https://epub.yuhan.tech/) — Benutzername und Passwort: `demo`.

## KI-gestütztes Lesen (nur Server)

Die KI-Lesefunktion legt eine gemeinsame, überprüfbare Lernschicht direkt über den Originaltext, statt eine allgemeine Zusammenfassung daneben zu stellen. Dazu gehören eine Leseeinführung, eine bei Bedarf geöffnete Kapitelübersicht, mit Zitaten verknüpfte Erklärungen, Hinweise zur Funktion einzelner Absätze, Worterklärungen, eine leicht verständliche Abschlussdarstellung und weiterführende Fragen.

Ergebnisse werden als Hintergrundaufträge erzeugt, in SQLite gespeichert und von Lesern mit Zugriff auf das Buch gemeinsam genutzt. Folgegespräche bleiben für jedes Konto privat. Administratoren müssen einen OpenAI-kompatiblen Anbieter einrichten und Mitglieder einzeln freischalten. Ausgewählter EPUB-Text wird an diesen Anbieter gesendet; aktiviere die Funktion daher nur mit Zustimmung der Leser. SSG-Ausgaben enthalten niemals Konten, KI-Steuerung, Aufträge oder Anbieterkonfiguration.

## Voraussetzungen und Installation

- Python 3.9 oder neuer
- Eine oder mehrere `.epub`- oder `.pdf`-Dateien, verschachtelte Buchverzeichnisse oder eine Bibliothek im Calibre-Stil

Die Installation von PyPI unterstützt den SSG- und den Server-Modus:

```bash
pip install epub-browser

# Vollständige Hilfe für jeden Modus
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

Für einen dauerhaften Server mit Docker verwende das veröffentlichte Image; auf dem Host ist kein Python erforderlich:

```bash
docker pull dfface/epub-browser:latest
```

## Schnellstart

### Statische Website erzeugen

```bash
epub-browser ssg /pfad/zu/buechern \
  --output-dir /pfad/zu/dist
```

Stelle `dist/` über HTTP bereit; öffne die erzeugten Seiten nicht direkt per `file://`. Für eine Bereitstellung unter einem Unterpfad verwende `--base-path /mein-repository/`; dies ändert die erzeugten URLs, nicht das Ausgabeverzeichnis.

### Dauerhafte Server-Bibliothek starten

```bash
epub-browser server /pfad/zu/buechern \
  --server-dir /pfad/zum/epub-browser-status \
  --watch
```

Öffne `http://127.0.0.1:8000/`. Beim ersten Besuch wird der erste Administrator angelegt; vorher wird die Bibliothek weder eingelesen noch veröffentlicht. `--no-browser` verhindert nur das automatische Öffnen des lokalen Browsers.

## Daten, Konten und Zugriffsgrenzen

Jedes Buch besitzt eine stabile `book_id`. Standardmäßig speichert `--book-id-storage sidecar` die Identität neben der Quelldatei, ohne deren Bytes zu verändern. Für EPUB schreibt `--book-id-storage embedded` sie in die OPF-Metadaten und erfordert eine beschreibbare Quelle; bei PDF fällt diese Einstellung immer auf die benachbarte Sidecar-Datei zurück.

Im Server-Modus ist `--server-dir` der maßgebliche Speicherort für SQLite, Caches und Migrationssicherungen. Dort liegen auch Konten, Bücherregale, Lesefortschritt, Anmerkungen, KI-Ergebnisse und Aufträge. Administratoren verwalten Benutzer, Rollen, Sitzungen und Buchberechtigungen; Mitglieder verwenden nur freigegebene Bücher und ihre eigenen privaten Daten. Schütze die Dateirechte dieses Verzeichnisses und seiner Sicherungen.

## Docker, Reverse Proxy und vollständige Dokumentation

Hänge Bücher in Containern schreibgeschützt und `--server-dir` als dauerhaftes Volume ein. Akzeptiere Proxy-Header nur von vertrauenswürdigen Proxys und verwende bei öffentlichen Bereitstellungen HTTPS.

Docker Compose, alle CLI-Optionen, Migrationen, LAN, Reverse Proxy und Fehlerbehebung findest du im [vollständigen englischen README](../../README.md) oder im [vollständigen README auf vereinfachtem Chinesisch](README.zh-CN.md). Das Verhalten beider Modi ist in allen Sprachen identisch.

## Mitwirken und Lizenz

Issues und Pull Requests sind willkommen. Die Lizenz steht in [License.txt](../../License.txt).
