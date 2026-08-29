# EPUB Browser

> EPUB e PDF in una libreria di lettura privata o come sito statico autonomo.

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

**Lingue dell’interfaccia (17):** inglese, cinese semplificato, cinese tradizionale, giapponese, coreano, spagnolo, tedesco, francese, russo, italiano, portoghese brasiliano, arabo, indonesiano, hindi, vietnamita, thailandese e malese.

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![Una pagina PDF nel lettore condiviso di EPUB Browser.](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser gestisce `.epub` e `.pdf` in due modalità con responsabilità chiaramente separate:

| | `ssg` | `server` |
| --- | --- | --- |
| EPUB e PDF | Sì | Sì |
| Distribuzione | Hosting statico, Pages, object storage, Nginx | Servizio privato di lettura persistente |
| Account | Nessuno | Account locali |
| Avanzamento, annotazioni, libreria | Solo in questo browser | Dati dell’account autenticato in SQLite |
| Aggiornamento delle fonti | Eseguire di nuovo `ssg` | Riavviare il servizio o usare `--watch` |
| Database a runtime | Nessuno | Obbligatorio |

PDF è un formato librario di prima classe: la pagina 1 diventa `chapter_0.html`, ogni pagina appare nell’indice e PDF.js la visualizza localmente nella stessa libreria, scheda del libro, interfaccia di lettura, ricerca e flusso di annotazione. Le funzioni PDF non supportate, come la lettura IA, vengono nascoste esplicitamente e durante la lettura non serve alcuna CDN.

Usa `ssg` per pubblicare normali file statici. Usa `server` quando servono account, dati tra dispositivi, controllo dell’accesso ai libri o monitoraggio automatico delle fonti.

## Panoramica

### Perché scegliere EPUB Browser

- **Lettura nativa con IA, ancorata al testo (solo Server ed EPUB):** In modalità Server, guide ai capitoli, spiegazioni collegate ai passaggi che le sostengono, mappe mentali, spunti di riflessione e conversazioni private con Ask AI restano accanto al testo EPUB originale, invece di diventare un riassunto generico separato.
- **Statistiche di lettura private (solo Server):** Consulta il tempo di lettura attivo, il calendario delle attività, le tendenze, le sessioni e i libri più letti. Ogni dato è visibile solo all’account attualmente autenticato.

![Una guida al capitolo accanto al testo EPUB originale, con il pannello privato Ask AI.](assets/ai-native-reading.png)

*Le guide IA e le domande private restano ancorate al testo originale.*

![La vista privata delle statistiche di lettura, con calendario delle attività e andamento del tempo di lettura.](assets/reading-insights.png)

*Le statistiche trasformano il tempo di lettura attivo in una cronologia privata e comprensibile.*

### Stack tecnologico

L’interfaccia usa HTML semantico, CSS e Vanilla JavaScript senza framework SPA. CLI e Server si basano su Python 3.9+, Starlette, Uvicorn e SQLite; pypdf, pypdfium2 e PDF.js elaborano i PDF localmente, senza CDN a runtime.

### Demo

- **Modalità SSG**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Modalità Server**: [epub.yuhan.tech](https://epub.yuhan.tech/) — nome utente e password: `demo`.

### Lettura nativa con IA (solo Server)

La lettura con IA crea sul testo originale un livello di apprendimento condiviso e verificabile, invece di affiancare al libro un riassunto generico. Comprende un percorso prima della lettura, una panoramica del capitolo su richiesta, spiegazioni collegate alle citazioni, note sul ruolo dei paragrafi, chiarimenti del lessico, una spiegazione semplice conclusiva e domande per approfondire.

I risultati vengono prodotti da attività in background, salvati in SQLite e condivisi tra i lettori che possono accedere al libro. Le conversazioni successive restano private per ciascun account. L’amministratore deve configurare un provider compatibile con OpenAI e autorizzare ogni membro. Il testo EPUB selezionato viene inviato al provider, quindi la funzione va attivata solo con il consenso dei lettori. L’output SSG non include mai account, controlli IA, attività o configurazioni del provider.

## Per iniziare

### Requisiti e installazione

- Python 3.9 o successivo
- Uno o più file `.epub` o `.pdf`, cartelle annidate con libri o una libreria in stile Calibre

L’installazione da PyPI supporta sia la modalità SSG sia la modalità Server:

```bash
pip install epub-browser

# Guida completa per ogni modalità
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

Per un Server persistente con Docker, usa l’immagine pubblicata; Python non è necessario sull’host:

```bash
docker pull dfface/epub-browser:latest
```

### Avvio rapido

#### Generare un sito statico

```bash
epub-browser ssg /percorso/dei/libri \
  --output-dir /percorso/di/dist
```

Pubblica `dist/` tramite HTTP; non aprire direttamente le pagine generate con `file://`. Per distribuire sotto un percorso secondario, aggiungi `--base-path /mio-repository/`; l’opzione modifica gli URL generati, non la cartella di output.

#### Avviare una libreria Server persistente

```bash
epub-browser server /percorso/dei/libri \
  --server-dir /percorso/dello-stato-epub-browser \
  --watch
```

Apri `http://127.0.0.1:8000/`. Alla prima visita viene creato l’amministratore iniziale; prima di completare la configurazione, la libreria non viene analizzata né pubblicata. `--no-browser` impedisce soltanto l’apertura automatica del browser locale.

## Dati e operazioni

### Dati, account e limiti di accesso

Ogni libro possiede un `book_id` stabile. Per impostazione predefinita, `--book-id-storage sidecar` salva l’identità accanto al file sorgente senza modificarne i byte. Per EPUB, `--book-id-storage embedded` la scrive nei metadati OPF e richiede una fonte modificabile; per PDF usa sempre il sidecar adiacente.

In modalità Server, `--server-dir` è la posizione autorevole per SQLite, cache e backup delle migrazioni. Qui vengono conservati anche account, librerie, avanzamento, annotazioni, risultati IA e attività. Gli amministratori gestiscono utenti, ruoli, sessioni e permessi sui libri; i membri usano solo i libri autorizzati e i propri dati privati. Proteggi i permessi di questa cartella e dei relativi backup.

### Docker, reverse proxy e documentazione completa

Nei container monta i libri in sola lettura e `--server-dir` come volume persistente. Accetta le intestazioni proxy solo da proxy attendibili e usa HTTPS nelle distribuzioni pubbliche.

Per Docker Compose, tutte le opzioni CLI, le migrazioni, la LAN, il reverse proxy e la risoluzione dei problemi, consulta il [README inglese completo](../../README.md) o il [README completo in cinese semplificato](README.zh-CN.md). Il comportamento delle due modalità è uguale in tutte le lingue.

## Sviluppo e licenza

### Contributi e licenza

Issues e Pull Requests sono benvenuti. Consulta [License.txt](../../License.txt) per la licenza.
