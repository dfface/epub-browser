# EPUB Browser

> **Trasforma i libri in siti web. Crea una libreria tutta tua.**
>
> Pubblica libri EPUB e PDF come sito web statico oppure gestisci una libreria privata
> self-hosted con account, avanzamento sincronizzato, annotazioni e, facoltativamente, lettura nativa con IA.

[Esplora la libreria statica](https://epub-browser-test.yuhan.tech/) · [Prova la libreria privata](#demo-live)

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/dfface/epub-browser/main/epub_browser/assets/logo-lockup-color.png" alt="Logo di EPUB Browser" width="520">
</p>

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![Un PDF nel lettore condiviso di EPUB Browser, con la pagina originale, la navigazione, i temi e gli strumenti di lettura.](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser è molto più di un convertitore di libri. È una piattaforma di lettura completa che
puoi pubblicare ovunque o gestire sul tuo server. EPUB e PDF condividono la stessa libreria, pagina
del libro, indice, modalità di lettura, temi, monitoraggio dell'avanzamento e gestione delle
annotazioni. Ogni pagina PDF diventa un capitolo del lettore, visualizzato localmente da PDF.js
nella stessa esperienza di lettura: niente visualizzatori separati né CDN a runtime.

## Indice dei contenuti

- [Panoramica del progetto](#panoramica-del-progetto)
  - [Perché EPUB Browser](#perché-epub-browser)
  - [Stack tecnologico](#stack-tecnologico)
  - [Scegliere SSG o Server](#scegliere-ssg-o-server)
  - [Demo live](#demo-live)
  - [Lettura nativa con IA](#lettura-nativa-con-ia-solo-server)
  - [Modalità essenziale per Kindle](#modalità-essenziale-per-kindle)
- [Per iniziare](#per-iniziare)
  - [Opzioni di installazione](#opzioni-di-installazione)
  - [Avvio rapido](#avvio-rapido)
- [Formati e lettura](#formati-e-lettura)
  - [Origini e identità stabile dei libri](#origini-e-identità-stabile-dei-libri)
  - [PDF: una pagina, un capitolo](#pdf-una-pagina-un-capitolo)
- [Distribuzione](#distribuzione)
  - [SSG](#ssg)
  - [Server](#server)
  - [Docker](#docker)
- [Riferimento e operazioni](#riferimento-e-operazioni)
  - [Riferimento dei comandi](#riferimento-dei-comandi)
  - [Dati di lettura e disponibilità delle funzioni](#dati-di-lettura-e-disponibilità-delle-funzioni)
  - [API Server e WebHooks](#api-server-e-webhooks)
  - [Sicurezza dei dati e risoluzione dei problemi](#sicurezza-dei-dati-e-migrazione)
- [Sviluppo e licenza](#sviluppo-e-licenza)
- [Centro documentazione](../README.md)

## Panoramica del progetto

### Perché EPUB Browser

- **Pubblica ovunque. Mantieni il controllo.** Con un solo comando crea un sito statico completo per
  Pages, object storage o Nginx, oppure esegui un Server persistente con account, permessi sui libri e
  OIDC. Asset dell'applicazione, font, PDF.js e renderer vengono serviti localmente, quindi la lettura
  non dipende mai da una CDN.
- **EPUB e PDF, un unico lettore.** Entrambi i formati condividono libreria, pagina del libro,
  indice, layout responsive, tre modalità di lettura, temi, schermo intero e avanzamento. Ogni pagina
  PDF resta nell'area di lettura, con zoom, selezione del livello testuale e annotazioni, invece di
  aprirsi in un visualizzatore separato.
- **Trova il libro e il passaggio che cerchi.** La ricerca nella libreria comprende metadati, tag e pinyin,
  con ordinamento e impaginazione. Sul Server, la ricerca in un intero libro EPUB restituisce tutti i
  risultati raggruppati per capitolo e porta al passaggio evidenziato. Gli ID stabili dei libri
  mantengono la ripresa della lettura, le annotazioni e la cronologia associate allo stesso libro.
- **Comprendi, non limitarti a scorrere.** In modalità Server, guide ai capitoli EPUB, spiegazioni
  con riferimenti al testo, mappe mentali e conversazioni private con Ask AI restano accanto al testo
  originale. Evidenziazioni, note, Dizionario ed Enciclopedia funzionano con EPUB e PDF dotati di livello
  testuale; gli elenchi di vocabolario del Server registrano l'origine e il livello di padronanza di
  ogni parola.
- **Trasforma la lettura in una cronologia da conservare.** Scaffali annidati, valutazioni, recensioni,
  esportazione delle annotazioni, calendari delle attività, tendenze, statistiche per libro e
  classifiche del tempo di lettura formano una cronologia coerente. Il Server mantiene i dati di lettura
  privati per ciascun account e li sincronizza tra i dispositivi.
- **Gestisci un servizio di lettura, non solo un visualizzatore.** In modalità Server, aggiungi libri
  tramite caricamenti web da amministratore o cartelle monitorate, limita l'uso del disco con
  l'eliminazione configurabile dei contenuti dalla cache LRU, gestisci i permessi di membri e IA e integra
  il servizio tramite OpenAPI, PAT e WebHooks. La lettura essenziale per Kindle supporta i dispositivi con
  risorse limitate; il Server offre anche un pannello personale per il salvaschermo Kindle con orologio,
  calendario, agenda, memo e timer Pomodoro.

![Una guida al capitolo integrata accanto al testo EPUB originale, con il pannello privato Ask AI.](assets/ai-native-reading.png)

*L'assistenza nativa con IA e le domande private restano legate al libro originale.*

![Una vista privata delle statistiche di lettura con calendario delle attività e andamento del tempo di lettura.](assets/reading-insights.png)

*Le statistiche di lettura trasformano la lettura attiva in una cronologia privata e comprensibile.*

### Stack tecnologico

EPUB Browser usa deliberatamente uno stack web essenziale con rendering sul server. L'applicazione
installata non include framework SPA e non richiede un ambiente di esecuzione Node.js:

| Livello | Tecnologia | Ruolo |
| --- | --- | --- |
| Frontend | HTML semantico, CSS, VanillaJS con moduli ES e API del browser | Un'unica interfaccia responsive condivisa da SSG e Server |
| CLI e Server | Python 3.9+, Starlette, Uvicorn | Comandi di conversione, pagine autenticate, API e attività in background |
| Dati | SQLite e cache di contenuti JSON ricostruibili | Lo stato degli utenti resta separato dai contenuti EPUB/PDF derivati |
| Formati dei libri | lxml, pypdf, pypdfium2, PDF.js | Parsing e sanitizzazione EPUB unificati, con approccio rigoroso in prima istanza e recupero in caso di errore, metadati e copertine PDF, rendering locale nel browser |
| Offline e asset | Service Worker, asset immutabili con hash, dipendenze integrate con versioni fissate | Distribuzione autonoma senza CDN a runtime |
| Distribuzione | PyPI, Docker, normale hosting statico | Lo stesso codice viene distribuito come SSG o come Server persistente |
| IA opzionale | API compatibili con OpenAI con rendering locale di Markdown, KaTeX e Mermaid | Livelli di apprendimento EPUB solo in modalità Server |

Node.js viene usato dai maintainer solo per i test lato browser; non fa parte dell'ambiente di
esecuzione in produzione del lettore.

### Scegliere SSG o Server

Lo stesso trattamento delle origini e gli stessi template di pagina alimentano due modalità di
distribuzione distinte. Scegli in base a dove devono risiedere i dati di lettura, non al formato del
libro:

| Funzionalità | `ssg` | `server` |
| --- | --- | --- |
| EPUB e PDF | Sì | Sì |
| Distribuzione | Pubblicazione atomica di HTML e asset statici per Pages, object storage o Nginx | Pagine dinamiche autenticate supportate da una cache di contenuti sostituibile |
| Account e controllo degli accessi | Nessuno | Account amministratore e membro, autorizzazioni per libri riservati, sessioni e protezione CSRF |
| Single sign-on OIDC | Non incluso | Provider generico, collegamento di account esistenti e creazione facoltativa di account membro |
| Avanzamento, annotazioni e scaffale | Memorizzati nel browser corrente | Sincronizzati per account autenticato in SQLite |
| Valutazioni, recensioni e sessioni di lettura | Non generati | Record privati per account e statistiche di lettura |
| Aggiornamenti delle origini | Esegui di nuovo `ssg` | Riavvia, ripeti la scansione o usa `--watch` |
| Amministrazione, tag, OpenAPI e WebHooks | Non inclusi | Inclusi |
| Lettura con IA e Ask AI | Non inclusi | Disponibili per EPUB se configurati ed esplicitamente autorizzati; nascosti per PDF |
| Database a runtime | Nessuno | Obbligatorio per la modalità persistente |
| Uso ideale | Hosting pubblico/statico, pacchetti offline, semplice pubblicazione personale | Una libreria privata, più dispositivi o lettori, automazione e accesso gestito |

Usa `ssg` quando il risultato deve essere composto da normali file statici. Usa `server` quando i lettori hanno bisogno di account, dati su più dispositivi, controllo degli accessi o sincronizzazione automatica delle origini.

### Demo live

- **Modalità SSG**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Modalità Server**: [epub.yuhan.tech](https://epub.yuhan.tech/) — accedi con nome utente `demo` e password `demo`.

### Lettura nativa con IA (solo Server)

Per i libri EPUB, la modalità Server può aggiungere guide ai capitoli, spiegazioni con riferimenti al
testo, mappe mentali, domande di riflessione e un pannello privato Ask AI senza allontanare il lettore
dal testo originale. I risultati restano soggetti ai permessi del libro; ogni membro deve essere
autorizzato esplicitamente e l'output SSG non contiene controlli, attività, dati degli account o
configurazioni del provider relativi all'IA. Nei PDF la lettura con IA e Ask AI sono volutamente
nascosti.

Consulta la [guida alla lettura nativa con IA](../ai-native-reading.md) per il modello di interazione
completo e le [note sui renderer locali di rich text](../third-party-ai-renderers.md) per i limiti di
rendering e sicurezza della rete.

### Modalità essenziale per Kindle

I Kindle e-Ink meno recenti (e qualsiasi browser con risorse limitate) dispongono di un'interfaccia di
lettura essenziale e priva di dipendenze. Attivala con `--kindle`:

- SSG: `epub-browser ssg --kindle -o output/ SOURCE...`
- Server: `epub-browser server --kindle --server-dir data SOURCE...`

Ogni libro EPUB (i libri PDF sono esclusi) ottiene tre pagine aggiuntive:

- lo scaffale essenziale `/kindle-library.html`
- la pagina del libro `/book/<id>/kindle.html`
- la pagina del capitolo `/book/<id>/kindle_chapter_N.html`

Queste pagine sono ottimizzate per e-Ink: markup minimo, temi basati solo su CSS, script compatibili
con ES5, nessun Service Worker e nessun framework. Puoi leggere senza JavaScript; il cambio di tema
(Chiaro / Seppia / Scuro), la dimensione dei caratteri (A- / A+) e la localizzazione dell'interfaccia
usano leggeri script inline aggiunti al semplice HTML.

Ogni pagina offre controlli per tema e caratteri (nell'intestazione e di nuovo nel piè di pagina del
capitolo), navigazione dell'indice, capitolo precedente e successivo e un collegamento «Continua a
leggere» che riprende dall'avanzamento salvato.

L'avanzamento di lettura varia in base alla modalità:

- **SSG:** l'avanzamento viene salvato nei cookie del browser corrente, in locale e senza account.
- **Server:** avanzamento e heartbeat di lettura vengono sincronizzati in SQLite per ciascun account
  autenticato. Le interfacce Kindle consentono solo la lettura e l'invio dei dati di avanzamento:
  registrano il capitolo corrente e inviano heartbeat, mostrano uno scaffale di sola lettura e non
  espongono mai statistiche o gestione dei contenuti.

Il controllo degli accessi viene applicato a ogni interfaccia Kindle. Per un libro con visibilità
limitata, lo scaffale essenziale omette il libro, mentre le pagine del libro e del capitolo e l'API
dell'avanzamento restituiscono 403 agli utenti non autorizzati.

I browser supportati (con UA contenente `Kindle/`, `Arora/` e così via) vengono reindirizzati
automaticamente dal lettore completo alle pagine essenziali; anche gli URL precedenti funzionano
direttamente. In questo modo la modalità essenziale offre un'alternativa funzionante per dispositivi
poco potenti o con supporto JavaScript limitato.

## Per iniziare

### Opzioni di installazione

EPUB Browser supporta due percorsi di installazione. Entrambi accettano uno o più file `.epub` o
`.pdf`, cartelle annidate o una directory di libreria in stile Calibre.

| Installazione | Utilizzo | Requisito dell'host |
| --- | --- | --- |
| PyPI | Modalità SSG o Server | Python 3.9 o successivo |
| Docker | Modalità Server persistente | Docker Engine; Python è incluso nell'immagine |

#### PyPI (SSG o Server)

Installa l'applicazione da riga di comando:

```bash
pip install epub-browser
```

Mostra il riferimento dei comandi specifico per ciascuna modalità:

```bash
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

#### Docker (Server)

L'immagine pubblicata [`dfface/epub-browser`](https://hub.docker.com/r/dfface/epub-browser)
esegue la modalità Server e non richiede Python sull'host:

```bash
docker pull dfface/epub-browser:latest
```

Usa `latest` per valutare la versione corrente; fissa un tag di versione numerato per una
distribuzione di produzione riproducibile. Consulta [Docker](#docker) per i mount obbligatori di
libri e stato, un avvio rapido con Compose, la configurazione iniziale e le indicazioni di rete.

### Avvio rapido

#### Generare un sito statico

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

Servi `dist/` tramite HTTP. L'apertura diretta delle pagine generate tramite `file://` non è supportata, perché storage del browser, moduli, manifest e Service Worker richiedono un origin HTTP.

Per un sito ospitato sotto un prefisso URL, imposta il percorso pubblico separatamente dalla destinazione nel filesystem:

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist \
  --base-path /my-repository/
```

`--base-path` modifica gli URL generati, non la posizione in cui vengono scritti i file. Con `/my-repository/`, collegamenti, icone, manifest, metadati dei libri e voci del Service Worker usano tutti quel prefisso, mentre i file restano direttamente in `dist/`.

#### Eseguire una libreria Server persistente

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

Apri `http://127.0.0.1:8000/`. Al primo accesso, EPUB Browser chiede di creare l'amministratore iniziale. La libreria non viene analizzata né esposta finché questa configurazione iniziale non è completata.

Se hai scelto Docker, salta il comando Python precedente e continua con
[l'avvio rapido di Docker Compose](#docker-compose).

## Formati e lettura

### Origini e identità stabile dei libri

Ogni `SOURCE` posizionale può essere un file EPUB, un file PDF o una directory.
Le directory vengono esaminate ricorsivamente. Puoi passare più origini a un solo comando:

```bash
epub-browser server book.epub /srv/library /srv/periodicals \
  --server-dir /srv/epub-browser \
  --watch
```

Ogni libro riceve un `book_id` stabile, esposto anche come `book_hash` negli URL generati e nei dati del browser. L'impostazione predefinita generale della CLI è:

```bash
--book-id-storage sidecar
```

La modalità sidecar scrive un file di identità visibile accanto all'origine, ad esempio `BOOK.epub.epub-browser.json` o `BOOK.pdf.epub-browser.json`, e lascia invariati i byte dell'origine. Il sidecar contiene l'ID stabile e un'impronta SHA-256 verificata dell'origine.

Per inserire l'ID nei metadati OPF dell'EPUB o nel dizionario delle informazioni del documento PDF, seleziona lo storage incorporato per l'intera invocazione:

```bash
--book-id-storage embedded
```

La modalità incorporata può ricostruire lo ZIP dell'EPUB o aggiungere un aggiornamento dei metadati al PDF prima della conversione. Se il PDF non può essere aggiornato e la sua origine è invariata, EPUB Browser salva lo stesso ID in un sidecar adiacente. Questo vale anche per PDF firmati, crittografati e di sola lettura. EPUB Browser si interrompe se gli ID non coincidono, se origini attive duplicano un ID, se un supporto non è valido o se un supporto obbligatorio non può essere scritto.

Durante la migrazione tra modalità di storage, EPUB Browser copia l'ID esistente nel supporto selezionato e conserva l'altro supporto valido. Un ID incorporato esistente dalla v2.0.4 viene copiato nel sidecar predefinito senza riscrivere l'EPUB. Sia SSG sia Server consegnano una copia byte per byte dell'origine PDF dopo qualsiasi aggiornamento dei metadati.

### PDF: una pagina, un capitolo

Il PDF è supportato da entrambe le modalità di distribuzione. Il lettore tratta ogni pagina PDF come
un normale capitolo di EPUB Browser; di conseguenza, la pagina del libro, la navigazione tra capitoli,
l'indice, l'impaginazione, la lettura continua, l'avanzamento, le sessioni di lettura, le annotazioni,
il Dizionario e l'Enciclopedia già esistenti condividono la stessa interfaccia e lo stesso modello di dati:

| Concetto PDF | SSG | Server |
| --- | --- | --- |
| URL della pagina 1 | `chapter_0.html` | `/book/<book-id>/chapter_0.html` |
| URL della pagina N | `chapter_{N-1}.html` | `/book/<book-id>/chapter_{N-1}.html` |
| Etichette di pagina e indice | Generati localmente; tutte le pagine sono elencate | Generati dalla cache dei metadati PDF; tutte le pagine sono elencate |
| Struttura incorporata | Un marcatore nella voce di indice della pagina di destinazione | Lo stesso marcatore, senza eliminare né riordinare le voci delle pagine |
| Scorrimento e impaginazione/cambio pagina | Strutture dei capitoli statiche e PDF.js locale | Strutture dei capitoli dinamiche condivise e PDF.js locale |
| Evidenziazioni, note, Dizionario ed Enciclopedia | Componenti condivisi locali nel browser quando esiste un livello testuale | Componenti condivisi autenticati quando esiste un livello testuale |
| Byte del PDF originale | Un `document.pdf` nell'output statico del libro | Endpoint con supporto delle richieste Range e accesso limitato alla sessione per il documento nella cache |

I numeri di pagina partono da uno nell'etichetta visibile e in PDF.js; gli indici dei capitoli partono
da zero negli URL, nello stato, nelle API e in SQLite. La pagina 1 di un PDF è quindi sempre
`chapter_0.html`. L'indice normalizzato mantiene una voce `Page N` per ogni pagina; i titoli della
struttura incorporata nel PDF vengono associati come marcatori alla relativa voce di destinazione,
inclusi più marcatori sulla stessa pagina.

SSG scrive un solo `document.pdf` e una struttura `chapter_<index>.html` per pagina. L'output SSG non
contiene script di sessione, chiamate `/api/*`, dati di annotazioni sincronizzati o dipendenze del
Server. Il Server conserva l'origine completa e identica byte per byte come
`book/<book-id>/pdf/document.pdf`, senza mai dividerla o riscriverla. Il Server genera dinamicamente
le stesse strutture dei capitoli dai metadati PDF; se l'origine cambia, invalida e aggiorna
completamente la cache PDF (documento, metadati e copertina derivata) invece di mescolare pagine
vecchie e nuove.

L'endpoint del documento originale del Server è accessibile solo tramite sessione:
`GET`/`HEAD /api/books/<book-id>/document`. Verifica autenticazione, visibilità del libro, formato PDF
e impronte dell'origine e della cache, quindi supporta risposte limitate a un singolo intervallo di
byte con `ETag`, `Accept-Ranges`, cache privata, `nosniff` e disposizione inline del PDF. Non espone
un percorso assoluto, non è disponibile con autenticazione PAT e non compare nella superficie delle API PAT/OpenAPI.
SSG ha solo il proprio `document.pdf` locale e nessuna API per il documento originale.

I PDF con un livello testuale utilizzabile da PDF.js riutilizzano esattamente il popup di selezione e
il componente di annotazione esistenti per Evidenziazione e Nota, oltre a Dizionario ed Enciclopedia.
Storage, proprietà, esportazione, elenco e deep link delle annotazioni restano condivisi; non esistono
una tabella di annotazioni né un'interfaccia di impostazioni specifiche per il PDF. I PDF scansionati
o composti solo da immagini restano leggibili, ma, quando manca un livello testuale utilizzabile,
le funzioni basate sulla selezione (Evidenziazione, Nota, Dizionario, Enciclopedia e ricerca nel
documento) sono esplicitamente non disponibili. Una selezione che attraversa più pagine può comunque essere copiata,
mentre le azioni di annotazione e consultazione mostrano il messaggio localizzato di funzione non
supportata; la selezione all'interno di una pagina continua a funzionare.

PDF.js non è una seconda interfaccia di visualizzazione. Prima di compilare o pubblicare, scarica e
verifica gli asset di terze parti bloccati:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
```

L'applicazione serve quindi a runtime gli asset locali con hash del modulo e del worker PDF.js, senza
mai recuperarli da una CDN. Le lightbox delle immagini usano la dipendenza bloccata GLightbox;
Fancyapps/Fancybox non è una dipendenza a runtime né viene ridistribuita. Consulta
[third_party/README.md](../../third_party/README.md) per il flusso di lavoro degli asset bloccati e
delle release.

## Distribuzione

### SSG

SSG crea uno snapshot completo in una directory di staging accanto alla destinazione, lo convalida e poi sostituisce la destinazione. Se una conversione non riesce, la destinazione precedente resta invariata. L'output generato non contiene database del Server, stato delle migrazioni, pagine degli account o metadati delle cache a runtime.

Il comportamento di SSG è volutamente locale e senza account:

- Avanzamento di lettura e annotazioni usano lo storage del browser sull'origin corrente.
- Lo scaffale supporta importazione ed esportazione JSON locali; non offre un'azione di sincronizzazione cloud.
- Accesso, impostazioni dell'account, API Server e controlli dipendenti dall'utente sono assenti.
- La destinazione di archiviazione è sempre lo spazio locale del browser e non viene presentata come impostazione.
- L'output statico include il Service Worker necessario per gli asset utilizzabili offline.

Tutti i JavaScript, CSS, font e icone richiesti dall'applicazione sono inclusi nell'output. Consulta [Funzionamento autonomo e comportamento di rete](#funzionamento-autonomo-e-comportamento-di-rete) per l'unica richiesta di rete facoltativa.

### Server

#### Configurazione iniziale, account e permessi

Con una nuova directory di stato persistente, le pagine normali reindirizzano a `/setup`. API, flussi di eventi, asset generati e libri restituiscono una risposta che richiede la configurazione finché non viene creato l'amministratore iniziale. Completa la configurazione tramite loopback o un altro percorso privato attendibile prima di esporre la porta: il primo invio della configurazione andato a buon fine assegna l'account amministratore.

Dopo la configurazione:

- La registrazione pubblica è chiusa. Gli amministratori creano e gestiscono gli utenti.
- Gli account hanno il ruolo `administrator` oppure `member`.
- I libri normali sono visibili a tutti gli account autenticati.
- I libri riservati sono visibili solo agli amministratori e agli utenti selezionati esplicitamente.
- Ogni utente possiede il proprio scaffale, avanzamento, annotazioni e sessioni attive.
- Gli utenti possono cambiare la password e revocare le proprie sessioni.
- Gli amministratori possono gestire utenti, ruoli, password, sessioni e autorizzazioni sui libri.
- Le sessioni usano un cookie HttpOnly, protezione CSRF e una validità di 30 giorni rinnovabile con l'attività.

#### Single sign-on OIDC e collegamento degli account

La modalità Server può usare un provider OpenID Connect (OIDC) generico, tra cui Authelia, Keycloak,
Authentik e servizi compatibili. In **Amministrazione → Accesso OIDC**, inserisci il nome del provider
mostrato ai lettori, l'URL dell'issuer, il client ID, il client secret, l'URI di reindirizzamento
esatto, gli scope e il claim del nome utente. EPUB Browser usa il discovery e il flusso Authorization
Code con PKCE S256, convalida l'ID token firmato e identifica un account esterno solo tramite
`(issuer, sub)`; i claim di email e nome utente sono indicazioni per la visualizzazione o la creazione
degli account, mai chiavi di identità.

Registra questo callback esatto presso il provider, inclusi schema e host:

```text
https://reader.example.com/auth/oidc/callback
```

Gli utenti esistenti possono accedere localmente e collegare il provider dalle impostazioni
dell'account. In caso contrario, a un'identità esterna sconosciuta vengono richiesti una sola volta
nome utente e password di un account locale esistente. Se abiliti la creazione automatica facoltativa,
viene creato un account membro senza password e non viene mai importato un ruolo di amministratore.
Consenti prima agli utenti esistenti di collegare i propri account: attivare troppo presto la creazione
automatica può generare **account locali duplicati**. L'accesso con password dell'**amministratore
locale** resta sempre disponibile, anche se l'accesso con password dei membri locali è disabilitato.
Verifica e proteggi questa credenziale di recupero. Non viene effettuato il logout dal provider e i
token di accesso o aggiornamento del provider non vengono memorizzati.

Per Authelia, configura un client confidenziale nella sezione del provider OIDC. L'estratto seguente
usa valori volutamente fittizi e presuppone che le chiavi e le policy del provider richieste da
Authelia siano già configurate. Memorizza in Authelia un hash di un client secret casuale e robusto,
quindi inserisci una sola volta in EPUB Browser il segreto in chiaro corrispondente:

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

In EPUB Browser usa l'issuer `https://auth.example.com`, il client ID `epub-browser`, gli scope
`openid profile email` e il claim del nome utente `preferred_username`. Il salvataggio esegue il
discovery e la convalida delle funzionalità in tempo reale; in caso di errore, la configurazione
precedente resta attiva.

#### Configurare e gestire la lettura con IA

Gli amministratori configurano la lettura con IA in **Amministrazione**, subito dopo la gestione degli
utenti e prima della gestione dei libri. La pagina memorizza nel database SQLite del Server un URL
base compatibile con OpenAI, la chiave API, il modello, il timeout, il budget di contesto, il limite di
concorrenza e il limite giornaliero predefinito di chiamate al provider. L'IA è inizialmente
disabilitata per i membri; un amministratore deve concedere l'accesso a ciascun membro e può
impostare un limite giornaliero individuale (`0` significa illimitato).

I livelli di apprendimento dei capitoli e le recensioni a livello di libro sono condivisi per ogni
lingua idonea, mentre le conversazioni di approfondimento restano private per ciascun account. Risultati,
stato delle attività, tag personalizzati, classificazione di lettura del libro e conversazioni private
di approfondimento vengono memorizzati in SQLite. I vecchi risultati restano disponibili dopo una modifica
alla configurazione del modello finché un amministratore non li rigenera esplicitamente.

Quando un lettore richiede una guida IA o pone una domanda, il testo EPUB selezionato e il contesto
compresso della conversazione vengono inviati al provider esterno configurato. Non attivare la
funzione se i lettori non sono autorizzati a inviare tali contenuti al provider. La chiave API non
viene mai restituita a un browser né esposta da un'API; proteggi di conseguenza la directory di stato
del Server.

Per un primo avvio non presidiato, fornisci un nome utente e un file contenente la password:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --admin-username admin \
  --admin-password-file /run/secrets/epub-browser-admin-password \
  --no-browser
```

Il file della password deve avere permessi `0600`. EPUB Browser rimuove un'eventuale nuova riga finale, memorizza un hash Argon2id e non stampa mai il segreto. Una configurazione incompleta, un file vuoto o illeggibile arrestano l'avvio. Una volta completata la configurazione, gli avvii successivi non leggono il segreto di bootstrap.

Gli equivalenti tramite ambiente sono `EPUB_BROWSER_ADMIN_USERNAME` ed `EPUB_BROWSER_ADMIN_PASSWORD_FILE`. `EPUB_BROWSER_ADMIN_PASSWORD` è un fallback in chiaro usato solo quando non è configurato alcun file della password. Un percorso del file della password indicato tramite CLI ha priorità sulle origini della password nell'ambiente.

#### Apertura del browser e logging

Per impostazione predefinita, il Server tenta di aprire il browser predefinito del sistema operativo dopo che il server HTTP ha iniziato ad ascoltare. `--no-browser` impedisce questa apertura locale. **Non disabilita l'interfaccia web né l'accesso tramite browser**; sopprime soltanto la chiamata locale `webbrowser.open(...)`. Usa questa opzione con Docker, systemd, sessioni SSH, macchine headless e script.

Per impostazione predefinita (`--log-level error`), la CLI emette solo errori, in modo che messaggi e avvisi ordinari non interrompano gli indicatori di avanzamento nel terminale. Un terminale interattivo mostra una volta l'URL su cui il server è in ascolto; le esecuzioni non interattive in Docker e nei servizi restano silenziose. Usa `--log-level warning` per includere gli avvisi, `--log-level info` per i log operativi e di accesso HTTP oppure `--log-level debug` per il massimo dettaglio. `--log` resta un alias di compatibilità per `--log-level info`.

Le scansioni iniziali e di monitoraggio compaiono nell'interfaccia web invece che in `tqdm` nel terminale. Il riepilogo di una scansione riuscita si chiude automaticamente; gli errori restano visibili finché l'utente non li chiude. Con `--watch`, correggere o sostituire un'origine avvia un'altra scansione senza richiedere un nuovo tentativo manuale.

#### Stato persistente ed effimero

La modalità Server persistente richiede `--server-dir`. Per un'esecuzione usa e getta, usa invece `--ephemeral`:

```bash
epub-browser server book.epub --ephemeral
```

Lo stato effimero viene eliminato alla chiusura. Poiché il database è nuovo a ogni esecuzione, anche la configurazione viene ripetuta, a meno che non vengano fornite credenziali di bootstrap non presidiato.

Struttura persistente:

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

Solo `data/` fa fede. `cache/` può essere eliminata e verrà ricostruita. Conserva `data/` durante gli aggiornamenti e la sostituzione dei container. Un lock del sistema operativo controlla l'esclusività; `.server.lock` può restare dopo una chiusura normale come metadato diagnostico.

Memorizza il file persistente `data/epub-browser.db` su un filesystem locale. I filesystem condivisi o di rete non supportano la concorrenza WAL. I backup verificati restano in `data/backups/` e includono tutti i dati WAL registrati in modo permanente.

#### LAN e reverse proxy

Il Server si associa per impostazione predefinita a `127.0.0.1:8000`. Per una LAN attendibile:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --port 8080 \
  --no-browser
```

Non esporre il server HTTP integrato direttamente su Internet. Termina TLS su un reverse proxy, applica controlli di rete e abilita i cookie sicuri.

Per registrare gli IP reali dei client nelle sessioni attive e nei limiti di frequenza degli accessi dietro un reverse proxy, configura la **rete del proxy direttamente connesso al Server** (non gli intervalli dei client pubblici):

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

Ripeti `--trusted-proxy-cidr` una volta per ogni indirizzo o rete dei proxy direttamente connessi. Solo le richieste il cui peer diretto appartiene a uno di questi CIDR possono fornire `X-Forwarded-For`; per tutte le altre viene registrato soltanto l'indirizzo del peer diretto. L'elaborazione degli indirizzi inoltrati di Uvicorn è disabilitata, quindi `Forwarded` e `FORWARDED_ALLOW_IPS` non possono ampliare questo perimetro di attendibilità. Usa `--cookie-secure` solo quando il browser raggiunge il servizio tramite HTTPS.

### Docker

L'immagine esegue la modalità Server persistente con queste impostazioni predefinite:

- `/app/Library` come origine
- `/app/EpubBrowserFiles` come stato persistente
- `--watch`
- `--no-browser`
- `--host 0.0.0.0 --port 80`
- `--book-id-storage embedded`

Poiché l'identità incorporata può aggiornare file EPUB o PDF, monta la libreria in lettura e scrittura. Monta lo stato del Server in lettura e scrittura e conservalo quando sostituisci il container:

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  dfface/epub-browser:latest
```

Visita `http://127.0.0.1:8080/setup` prima di modificare la pubblicazione della porta o le regole del proxy.

#### Docker Compose

Il repository include un [docker-compose.yml](../../docker-compose.yml) per chi preferisce Compose. Da un checkout, crea `Library/`, inserisci lì i libri EPUB o PDF ed esegui:

```bash
docker compose up -d --build
```

Pubblica solo `127.0.0.1:8080`, conserva i libri EPUB/PDF di origine in `./Library` e mantiene lo stato del Server in `./EpubBrowserFiles`. Il `command` completo del Server è volutamente visibile nel file, così puoi aggiungere opzioni specifiche della distribuzione senza sostituire un'impostazione predefinita implicita dell'immagine. Completa la configurazione iniziale su `http://127.0.0.1:8080/setup`. Per l'accesso remoto, mantieni la pubblicazione sulla sola interfaccia di loopback e anteponi un reverse proxy TLS con autenticazione.

Per una configurazione non presidiata:

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

Dopo il primo avvio riuscito, il mount del segreto monouso può essere rimosso. Una libreria di sola lettura funziona solo quando ogni EPUB contiene già un ID incorporato valido e corrispondente. I sidecar esistenti vengono conservati quando i relativi ID vengono incorporati.

Monta `/app/SyncData:ro` solo durante l'importazione del JSON di uno scaffale legacy:

```bash
-v /path/to/legacy-sync:/app/SyncData:ro
```

Negli esempi, la pubblicazione della porta sull'interfaccia di loopback rende il container accessibile solo dall'host. Per l'accesso remoto, usa un reverse proxy TLS, configura il CIDR effettivo della sua rete di container e aggiungi `--cookie-secure`.

## Riferimento e operazioni

### Riferimento dei comandi

#### `epub-browser ssg SOURCE [SOURCE ...]`

| Opzione | Significato |
| --- | --- |
| `--output-dir DIR`, `-o DIR` | Destinazione obbligatoria dello snapshot statico atomico. |
| `--base-path PATH` | Prefisso dell'URL pubblico; valore predefinito `/`. Deve iniziare e terminare con `/`. |
| `--book-id-storage sidecar\|embedded` | Supporto dell'identità stabile per ogni origine selezionata; valore predefinito `sidecar`. |
| `--kindle` | Genera pagine essenziali senza dipendenze per i Kindle e-Ink meno recenti e reindirizza a esse i browser Kindle WebKit; disabilitato per impostazione predefinita. |
| `--log` | Alias di compatibilità per `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Livello di dettaglio dei log operativi; valore predefinito `error`, che mantiene silenziosi output di conversione ordinari e avvisi. |

#### `epub-browser server SOURCE [SOURCE ...]`

È obbligatoria esattamente una tra `--server-dir` ed `--ephemeral`.

| Opzione | Significato |
| --- | --- |
| `--server-dir DIR` | Dati autorevoli persistenti e radice della cache sostituibile. |
| `--ephemeral` | Usa uno stato usa e getta; mutuamente esclusivo con `--server-dir`. |
| `--watch`, `-w` | Monitora le origini e rileva aggiunte, aggiornamenti, spostamenti ed eliminazioni, applicandoli alla libreria. |
| `--host ADDRESS` | Indirizzo di ascolto; valore predefinito `127.0.0.1`. |
| `--port PORT`, `-p PORT` | Porta di ascolto; valore predefinito `8000`. |
| `--no-browser` | Non apre il browser predefinito locale. L'interfaccia web resta disponibile. |
| `--log` | Alias di compatibilità per `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Livello di dettaglio dei log operativi; valore predefinito `error`. I log di accesso HTTP sono abilitati con `info` e `debug`. |
| `--legacy-sync-dir DIR` | Legge il JSON di uno scaffale legacy durante la migrazione all'avvio. |
| `--book-id-storage sidecar\|embedded` | Supporto dell'identità stabile per ogni origine selezionata; valore predefinito `sidecar`. |
| `--admin-username NAME` | Amministratore iniziale non presidiato; fallback `EPUB_BROWSER_ADMIN_USERNAME`. |
| `--admin-password-file FILE` | File del segreto iniziale preferito; fallback `EPUB_BROWSER_ADMIN_PASSWORD_FILE`, quindi `EPUB_BROWSER_ADMIN_PASSWORD` se non è impostato alcun file. |
| `--trusted-proxy-cidr CIDR` | Opzione ripetibile che definisce le reti dei proxy direttamente connessi considerate attendibili per analizzare in sicurezza l'IP client di `X-Forwarded-For`. |
| `--cookie-secure` | Invia il cookie di sessione solo tramite HTTPS esposto al browser. |
| `--kindle` | Serve pagine essenziali senza dipendenze per i Kindle e-Ink meno recenti e reindirizza a esse i browser Kindle WebKit; disabilitato per impostazione predefinita. |

#### Sintassi legacy v1

La sintassi legacy è supportata per tutta la serie v2:

| Comando v1 | Corrispondenza v2 |
| --- | --- |
| `epub-browser BOOKS` | `epub-browser server BOOKS --ephemeral` |
| `epub-browser BOOKS --output-dir STATE` | `epub-browser server BOOKS --server-dir STATE` |
| `epub-browser BOOKS --no-server --output-dir DIST` | `epub-browser ssg BOOKS --output-dir DIST` |
| `--sync-dir DIR` | `server --legacy-sync-dir DIR` |

L'opzione `--keep-files`, disponibile solo nella versione legacy, conserva una directory temporanea del Server. Le directory persistenti del Server sono già permanenti. Con `--log`, l'adattatore di compatibilità stampa il comando v2 equivalente; altrimenti resta silenzioso.

### Dati di lettura e disponibilità delle funzioni

- Individuazione ricorsiva di EPUB/PDF e librerie Calibre, tag dei metadati, ricerca e ricerca per pinyin
- Interfacce responsive per libreria, dettagli del libro e lettura dei capitoli
- Scorrimento, cambio pagina, lettura continua, larghezza del contenuto regolabile, font, CSS personalizzato, temi e modalità di lettura senza distrazioni
- Evidenziazioni, note, consultazione delle annotazioni, gruppi annidati dello scaffale, tag e importazione/esportazione JSON
- Localizzazione dell'interfaccia in inglese, cinese semplificato, cinese tradizionale, coreano,
  giapponese, spagnolo, tedesco, francese, russo, italiano, portoghese brasiliano, arabo, indonesiano,
  hindi, vietnamita, thailandese e malese
- Comportamento adatto agli e-reader con browser Kindle/Silk; le funzionalità più impegnative per il browser possono essere ridotte

| Dati | SSG | Server |
| --- | --- | --- |
| Avanzamento di lettura | Locale nel browser | Record SQLite dell'utente autenticato |
| Evidenziazioni e note | Locali nel browser | Record SQLite dell'utente autenticato |
| Valutazioni, recensioni e cronologia privata delle sessioni di lettura | Non presenti | Record SQLite dell'utente autenticato |
| Scaffale | Locale nel browser; importazione/esportazione | Documento cloud versionato dell'utente autenticato; salvataggio automatico |
| Account e sessioni | Non presenti | SQLite in `<server-dir>/data` |
| Autorizzazioni sui libri | Non presenti | SQLite in `<server-dir>/data` |

Il Server non offre un selettore tra storage locale e cloud: i dati di lettura degli utenti autenticati vengono sempre memorizzati sul Server. La cronologia privata dettagliata delle sessioni di lettura non viene mai generata da SSG. SSG non interroga mai le API Server e usa sempre lo storage locale dell'origin corrente del browser.

### Funzionamento autonomo e comportamento di rete

L'applicazione è autonoma per la lettura: JavaScript, CSS, font, icone, manifest e risorse EPUB convertite necessari vengono serviti localmente. Non esistono dipendenze da CDN a runtime. Bloccare l'accesso in uscita a Internet non impedisce configurazione, accesso, navigazione, lettura, annotazioni, avanzamento, uso dello scaffale, amministrazione o conversione delle origini.

Il piè di pagina può effettuare una richiesta facoltativa all'API GitHub Releases per individuare una versione più recente di EPUB Browser. Un errore, un blocco o l'uso offline comportano solo la soppressione di quel suggerimento di aggiornamento.

SSG pubblica un Service Worker statico. Il Server disabilita e ritira deliberatamente il Service Worker per l'intero origin, in modo che un account non possa ricevere contenuti protetti di un altro account conservati nella cache.

### API Server e WebHooks

Gli account del Server possono creare personal access token con scope nelle impostazioni dell'account. I client esterni usano `Authorization: Bearer <PAT>` con l'API versionata `/api/v1/*`; i cookie del browser non autenticano questi percorsi. L'API comprende libri visibili e contenuti dei capitoli, scaffale, avanzamento, annotazioni e recensioni del proprietario del token, oltre ai dati di sola lettura tra utenti per i PAT amministratore con `admin:data:read`.

Il documento OpenAPI 3.1 è disponibile su `/openapi.json`; gli utenti autenticati possono consultare il riferimento locale su `/api-docs`. Ad esempio: `curl -H 'Authorization: Bearer …' https://reader.example/api/v1/books`. I dettagli del capitolo restituiscono per impostazione predefinita HTML sanitizzato e testo semplice con `?format=text`.

Gli endpoint degli elenchi restituiscono `items` e `next_cursor`. Il `limit` predefinito è 24 e il massimo è 100. Passa `next_cursor` come `cursor` con gli stessi filtri per recuperare la pagina successiva. Un cursore nullo indica l'ultima pagina. Ad esempio, usa `/api/v1/me/annotations?book_id=BOOK_ID&chapter_index=0&fields=id,text,note` per recuperare campi selezionati delle annotazioni da un capitolo EPUB o da una pagina PDF. I filtri di query e i campi supportati sono elencati nel documento OpenAPI.

Il vocabolario usa per impostazione predefinita lo stesso formato di elenco. I client che utilizzano la precedente risposta `words` possono inviare `page=1` o `page_size` per selezionare il formato di impaginazione legacy.

Gli amministratori gestiscono gli endpoint WebHook in Amministrazione. I segreti vengono mostrati solo alla creazione o alla rotazione. Le consegne sono firmate, persistenti e vengono ritentate in caso di risposte non 2xx; gli eventi di recensione dei libri contengono ID e timestamp delle azioni, ma mai valutazioni o testo delle recensioni.

### Sicurezza dei dati e migrazione

Prima di aggiornare installazioni Server persistenti, esegui il backup dei libri EPUB/PDF di origine e di `<server-dir>/data`. Mantieni lo stesso volume di stato persistente durante la sostituzione del container.

La migrazione all'avvio è automatica e può essere ripresa in sicurezza dopo un riavvio. Verifica i database legacy, crea un backup, aggiorna una copia, importa i dati legacy idonei di scaffale, avanzamento e annotazioni nell'amministratore iniziale in attesa e ritira solo gli artefatti pubblici legacy sostituibili dopo checkpoint completati correttamente. Le normali richieste non analizzano mai le directory di sincronizzazione legacy. Database danneggiati, hash delle password non validi, database legacy ambigui e ID in conflitto bloccano l'avvio in modo sicuro, senza tentare interpretazioni arbitrarie né sovrascrivere i dati.

Un `epub-browser.db` o `annotations.db` migrato nella radice viene conservato come copia di recupero sensibile e non autorevole; `data/epub-browser.db` è autorevole e le richieste del Server non usano il file nella radice conservato. Mantieni privata la copia di recupero. Eliminala manualmente solo a Server spento, dopo aver verificato il database autorevole e il backup registrato e soltanto quando non è più necessario tornare alla v1. EPUB Browser non la elimina mai automaticamente.

Se sia `epub-browser.db` sia `annotations.db` esistono in una radice legacy, l'avvio si interrompe e li lascia invariati. Consulta [Migrazione alla v2](../migration-v2.md) per backup, rollback, ricostruzione della cache e ripristino dei conflitti.

### Risoluzione dei problemi

#### Il comando è stato avviato, ma non si è aperto alcun browser

Rimuovi `--no-browser` quando esegui il comando su una macchina locale con interfaccia grafica oppure apri manualmente l'URL visualizzato o su cui il server è in ascolto. Con Docker, systemd, SSH e sessioni non interattive è previsto che tu apra l'URL autonomamente.

#### La CLI sembra silenziosa

Il funzionamento silenzioso è intenzionale senza `--log`, soprattutto negli ambienti non interattivi. Aggiungi `--log` per i dettagli operativi e di accesso. L'avanzamento della scansione del Server viene mostrato nell'interfaccia web.

#### Docker non riesce a scrivere un ID stabile

L'immagine usa per impostazione predefinita l'identità incorporata. Monta `/app/Library` in lettura e scrittura oppure incorpora in anticipo ID validi e corrispondenti. Usa un comando personalizzato con `--book-id-storage sidecar` solo se preferisci un supporto sidecar scrivibile.

#### Un sito SSG generato ha collegamenti non funzionanti sotto un sottopercorso

Rigenera il sito con un `--base-path` normalizzato, ad esempio `/reader/`, e configura l'host statico per servire l'output con lo stesso prefisso.

#### Il Server non si avvia dopo un aggiornamento

Leggi il primo errore di migrazione o convalida registrato, conserva dati e file di origine e consulta [docs/migration-v2.md](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/migration-v2.md). Non eliminare la directory autorevole `data/` per tentare di aggirare un errore.

## Sviluppo e licenza

### Contribuire

Issue e pull request sono benvenuti su [dfface/epub-browser](https://github.com/dfface/epub-browser). Una segnalazione utile include il comando esatto, il browser o dispositivo, i passaggi per riprodurre il problema, i log pertinenti e il file EPUB o PDF quando può essere condiviso legalmente.

#### Contratto di architettura per i maintainer

Leggi [AGENTS.md](../../AGENTS.md) prima di modificare elaborazione dei contenuti, template di pagina,
cache, permessi, asset o comportamento della distribuzione. Definisce il confine tra i formati EPUB e
PDF, le responsabilità di SSG e Server, le revisioni indipendenti delle cache, i requisiti i18n a
runtime, i controlli di sicurezza e la verifica obbligatoria. Termini condivisi del prodotto come
*capitolo del lettore*, *finestra di lettura*, *area di lettura* e *cache dei contenuti* sono definiti
in [CONTEXT.md](../../CONTEXT.md).

In sintesi: mantieni un'unica interfaccia di lettura, tieni i dati esclusivi del Server fuori da SSG,
mantieni le cache derivate da EPUB e PDF separate dai dati utente in SQLite e non aggiungere mai una
dipendenza da CDN a runtime. Una modifica che interessa un componente condiviso deve essere testata
con entrambi i formati ed entrambe le modalità di distribuzione, ove applicabile.

#### Sviluppo da un checkout del codice sorgente

I file di terze parti per il browser sono input generati per la compilazione, non codice sorgente del
progetto, quindi `epub_browser/assets/vendor/` è volutamente assente da Git. Scarica esplicitamente le
versioni esatte fissate dal lockfile prima di sviluppare o compilare, quindi verificale offline:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
python3 -m unittest tests.test_vendor_assets -v
python3 -m build
```

`fetch` è l'unico comando precedente che scarica asset di terze parti per il browser. Il lockfile registra
tarball npm immutabili, digest dei file, allowlist e licenze; `verify`, i test, le build da un checkout
con gli asset già scaricati e il lettore installato non scaricano asset per il browser. Il normale comando isolato
`python3 -m build` può comunque consultare un indice di pacchetti Python per i requisiti di build. Per
una build completamente senza rete, scarica l'albero degli asset di terze parti e preinstalla `build`, `setuptools` e
`wheel` prima di disconnetterti, quindi esegui `PIP_NO_INDEX=1 python3 -m build --no-isolation`. Wheel,
distribuzioni sorgente, immagini Docker e siti SSG generati contengono i file verificati e non hanno
dipendenze da CDN a runtime. Consulta [third_party/README.md](../../third_party/README.md) per il
flusso di lavoro di aggiornamento, release e manutenzione del repository.

### Licenza

[MIT](../../License.txt)
