# EPUB Browser

> **Transformez des livres en sites web. Constituez une bibliothèque qui vous appartient.**
>
> Publiez des livres EPUB et PDF sous forme de site statique, ou hébergez vous-même une bibliothèque privée
> avec des comptes, une progression synchronisée, des annotations et, en option, une lecture native avec l’IA.

[Découvrir la bibliothèque statique](https://epub-browser-test.yuhan.tech/) · [Essayer la bibliothèque privée](#démonstrations-en-ligne)

**README :** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/dfface/epub-browser/main/epub_browser/assets/logo-lockup-color.png" alt="Logo d’EPUB Browser" width="520">
</p>

[![Version PyPI](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Versions de Python](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![Licence](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![Un PDF affiché dans le lecteur commun d’EPUB Browser, avec la page originale, la navigation, les thèmes et les outils de lecture.](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser est plus qu’un convertisseur de livres. C’est une plateforme de lecture
complète que vous pouvez publier n’importe où ou héberger vous-même. EPUB et PDF
partagent la même bibliothèque, la même page de livre, la même table des matières,
les mêmes modes de lecture, les mêmes thèmes, le même suivi de progression et les
mêmes outils d’annotation. Chaque page PDF devient un chapitre du lecteur, affiché
localement par PDF.js dans la même interface de lecture, sans visionneuse distincte
ni CDN à l’exécution.

## Table des matières

- [Présentation du projet](#présentation-du-projet)
  - [Pourquoi EPUB Browser](#pourquoi-epub-browser)
  - [Pile technologique](#pile-technologique)
  - [Choisir SSG ou Server](#choisir-ssg-ou-server)
  - [Démonstrations en ligne](#démonstrations-en-ligne)
  - [Lecture native avec l’IA](#lecture-native-avec-lia-server-uniquement)
  - [Mode minimal pour Kindle](#mode-minimal-pour-kindle)
- [Premiers pas](#premiers-pas)
  - [Choisir une installation](#choisir-une-installation)
  - [Démarrage rapide](#démarrage-rapide)
- [Formats et lecture](#formats-et-lecture)
  - [Sources et identité stable des livres](#sources-et-identité-stable-des-livres)
  - [PDF : une page, un chapitre](#pdf--une-page-un-chapitre)
- [Déploiement](#déploiement)
  - [SSG](#ssg)
  - [Server](#server)
  - [Docker](#docker)
- [Référence et exploitation](#référence-et-exploitation)
  - [Référence des commandes](#référence-des-commandes)
  - [Données de lecture et répartition des fonctionnalités](#données-de-lecture-et-répartition-des-fonctionnalités)
  - [API Server et WebHooks](#api-server-et-webhooks)
  - [Sécurité des données et dépannage](#sécurité-des-données-et-migration)
- [Développement et licence](#développement-et-licence)
- [Centre de documentation](../README.md)

## Présentation du projet

### Pourquoi EPUB Browser

- **Publiez partout, gardez le contrôle.** Créez avec une seule commande un site
  statique complet pour Pages, un stockage objet ou Nginx, ou exécutez un Server
  persistant avec des comptes, des autorisations sur les livres et OIDC. Les
  ressources de l’application, les polices, PDF.js et les moteurs de rendu sont
  servis localement : la lecture ne dépend donc jamais d’un CDN.
- **EPUB et PDF dans le même lecteur.** Les deux formats partagent la bibliothèque,
  la page de livre, la table des matières, la mise en page adaptative, trois modes
  de lecture, les thèmes, le plein écran et la progression. Chaque page PDF reste
  dans l’espace de lecture, avec le zoom, la sélection dans la couche texte et les
  annotations, au lieu d’ouvrir une visionneuse distincte.
- **Trouvez le livre et le passage recherché.** La recherche dans la bibliothèque
  porte sur les métadonnées, les étiquettes et le pinyin, avec tri et pagination.
  Côté Server, la recherche dans l’intégralité d’un EPUB renvoie tous les résultats
  regroupés par chapitre et permet d’accéder directement au passage surligné. Les
  identifiants stables des livres conservent la reprise de lecture, les annotations
  et l’historique associés au bon livre.
- **Comprenez, ne vous contentez pas de faire défiler.** En mode Server, les guides
  de chapitre EPUB, les explications accompagnées de références au texte, les cartes
  mentales et les échanges privés avec Ask AI restent aux côtés du texte original.
  Les surlignages, les notes, le Dictionnaire et l’Encyclopédie fonctionnent dans
  les EPUB et les PDF dotés d’une couche texte ; les listes de vocabulaire du Server
  enregistrent l’origine et le niveau de maîtrise de chaque mot.
- **Construisez un historique de lecture qui mérite d’être conservé.** Des
  étagères imbriquées, des évaluations, des avis, l’export des annotations, les
  calendriers d’activité, les tendances, les statistiques par livre et les
  classements par temps de lecture forment un ensemble cohérent. Le Server conserve
  les données de lecture de chaque compte en toute confidentialité et les synchronise
  entre les appareils.
- **Exploitez un service de lecture, pas seulement une visionneuse.** En mode
  Server, ajoutez des livres via l’interface web d’administration ou des dossiers
  surveillés, limitez l’occupation du disque grâce à une purge LRU configurable du
  cache, gérez les autorisations des membres et de l’IA et intégrez OpenAPI, les PAT
  et les WebHooks. Le mode minimal pour Kindle prend en charge les appareils aux
  fonctionnalités limitées ; le Server fournit aussi un tableau de bord personnel
  pour l’écran de veille du Kindle, avec horloge, calendrier, agenda, mémo et
  minuteur Pomodoro.

![Un guide de chapitre intégré à côté du texte EPUB original, avec un panneau Ask AI privé.](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/readme/assets/ai-native-reading.png)

*L’accompagnement natif par l’IA et les questions privées restent directement liés au livre original.*

![Une vue privée des indicateurs de lecture avec un calendrier d’activité et la tendance du temps de lecture.](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/readme/assets/reading-insights.png)

*Les indicateurs de lecture transforment la lecture active en un historique privé facile à comprendre.*

### Pile technologique

EPUB Browser utilise délibérément une pile web légère avec rendu côté serveur.
L’application installée n’emploie aucun framework SPA et ne nécessite aucun
environnement d’exécution Node.js :

| Couche | Technologie | Rôle |
| --- | --- | --- |
| Interface | HTML sémantique, CSS, VanillaJS avec modules ES et API du navigateur | Une interface adaptative commune à SSG et Server |
| CLI et Server | Python 3.9+, Starlette, Uvicorn | Commandes de conversion, pages authentifiées, API et tâches en arrière-plan |
| Données | SQLite et caches de contenu JSON reconstructibles | L’état des utilisateurs reste distinct du contenu EPUB/PDF dérivé |
| Formats de livre | lxml, pypdf, pypdfium2, PDF.js | Analyse et assainissement unifiés des EPUB, avec priorité au mode strict et récupération en cas d’échec ; métadonnées et couvertures PDF ; rendu local dans le navigateur |
| Hors ligne et ressources | Service Worker, ressources immuables avec hachage, dépendances intégrées à versions verrouillées | Distribution autonome sans CDN à l’exécution |
| Distribution | PyPI, Docker, hébergement statique classique | Le même code est livré sous forme de SSG ou de Server persistant |
| IA facultative | API compatibles OpenAI avec rendu local de Markdown, KaTeX et Mermaid | Couches d’apprentissage EPUB en mode Server uniquement |

Node.js sert uniquement aux mainteneurs pour les tests côté navigateur ; il ne fait
pas partie de l’environnement d’exécution du lecteur en production.

### Choisir SSG ou Server

Le même traitement des sources et les mêmes modèles de page alimentent deux modes
de déploiement distincts. Choisissez selon l’emplacement souhaité des données de
lecture, et non selon le format du livre :

| Fonctionnalité | `ssg` | `server` |
| --- | --- | --- |
| EPUB et PDF | Oui | Oui |
| Distribution | Publication atomique du HTML statique et des ressources pour Pages, un stockage objet ou Nginx | Pages dynamiques authentifiées appuyées sur un cache de contenu remplaçable |
| Comptes et contrôle d’accès | Aucun | Comptes administrateur/membre, autorisations sur les livres restreints, sessions et protection CSRF |
| Authentification unique OIDC | Non incluse | Fournisseur générique, liaison de comptes existants et création facultative de comptes membres |
| Progression, annotations, étagère | Stockées dans le navigateur actuel | Synchronisées dans SQLite pour chaque compte authentifié |
| Évaluations, avis, sessions de lecture | Non générés | Données privées par compte et indicateurs de lecture |
| Mises à jour des sources | Relancer `ssg` | Redémarrer, relancer l’analyse ou utiliser `--watch` |
| Administration, étiquettes, OpenAPI, WebHooks | Non inclus | Inclus |
| Lecture par IA et Ask AI | Non incluses | Disponibles pour EPUB si elles sont configurées et explicitement autorisées ; masquées pour PDF |
| Base de données d’exécution | Aucune | Requise pour le mode persistant |
| Cas d’usage | Hébergement public/statique, lots hors ligne, publication personnelle simple | Bibliothèque privée, plusieurs appareils ou lecteurs, automatisation et accès administré |

Utilisez `ssg` lorsque le résultat doit être constitué de fichiers statiques ordinaires. Utilisez `server` lorsque les lecteurs ont besoin de comptes, de données partagées entre appareils, d’un contrôle d’accès ou d’une synchronisation automatique des sources.

### Démonstrations en ligne

- **Mode SSG** : [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Mode Server** : [epub.yuhan.tech](https://epub.yuhan.tech/) — connectez-vous avec l’identifiant `demo` et le mot de passe `demo`.

### Lecture native avec l’IA (Server uniquement)

Pour les livres EPUB, le mode Server peut ajouter des guides de chapitre, des
explications accompagnées de références au texte, des cartes mentales, des questions
de réflexion et un panneau Ask AI privé, sans éloigner le lecteur du texte original.
Les résultats restent régis par les autorisations sur les livres ; les membres
doivent être explicitement autorisés, et SSG ne contient ni contrôles d’IA,
ni tâches, ni données de compte, ni configuration de fournisseur. Pour les PDF,
la lecture par IA et Ask AI sont volontairement masqués.

Consultez le [guide de lecture native avec l’IA](../ai-native-reading.md) pour le
modèle d’interaction complet et les [notes sur les moteurs de rendu de texte enrichi locaux](../third-party-ai-renderers.md)
pour les limites de rendu et de sécurité réseau.

### Mode minimal pour Kindle

Les anciens Kindle à encre électronique et tout navigateur limité disposent d’une
interface de lecture minimale sans dépendance. Activez-la avec `--kindle` :

- SSG : `epub-browser ssg --kindle -o output/ SOURCE...`
- Server : `epub-browser server --kindle --server-dir data SOURCE...`

Chaque livre EPUB (les livres PDF sont exclus) reçoit trois pages supplémentaires :

- l’étagère minimale `/kindle-library.html`
- la page du livre `/book/<id>/kindle.html`
- la page de chapitre `/book/<id>/kindle_chapter_N.html`

Ces pages sont adaptées à l’encre électronique : balisage minimal, thèmes en CSS
uniquement, scripts compatibles ES5, sans Service Worker ni framework. La lecture
fonctionne sans aucun JavaScript. Le changement de thème (Clair / Sépia / Sombre),
la taille des caractères (A- / A+) et la localisation de l’interface utilisent de
légers scripts intégrés qui s’ajoutent au HTML simple.

Chaque page propose des commandes de thème et de police (dans l’en-tête, puis de
nouveau dans le pied des chapitres), la navigation dans la table des matières,
le chapitre précédent/suivant et un lien « Continuer la lecture » qui reprend à
partir de la progression enregistrée.

La progression de lecture varie selon le mode :

- **SSG :** la progression est stockée dans les cookies du navigateur actuel, localement et sans compte.
- **Server :** la progression et les signaux d’activité de lecture sont synchronisés
  dans SQLite pour chaque compte connecté. Les interfaces Kindle servent uniquement
  à lire et à transmettre ces données : elles enregistrent le chapitre actuel,
  envoient les signaux d’activité, affichent une étagère en lecture seule et ne
  donnent jamais accès aux indicateurs ni à la gestion du contenu.

Le contrôle d’accès est appliqué sur chaque interface Kindle. Pour un livre à
visibilité restreinte, un utilisateur non autorisé reçoit une réponse 403 sur la
page du livre, les chapitres et l’API de progression ; le livre est omis de
l’étagère minimale.

Les navigateurs pris en charge (dont l’agent utilisateur contient `Kindle/`,
`Arora/`, etc.) sont automatiquement redirigés du lecteur complet vers les pages
minimales ; les URL ci-dessus fonctionnent également directement. Ce mode minimal
constitue ainsi un repli adapté aux appareils peu puissants ou dont la prise en
charge de JavaScript est limitée.

## Premiers pas

### Choisir une installation

EPUB Browser prend en charge deux méthodes d’installation. Toutes deux acceptent
un ou plusieurs fichiers `.epub` ou `.pdf`, des répertoires imbriqués ou un
répertoire de bibliothèque de type Calibre.

| Installation | Utilisation | Prérequis sur l’hôte |
| --- | --- | --- |
| PyPI | Mode SSG ou Server | Python 3.9 ou version ultérieure |
| Docker | Mode Server persistant | Docker Engine ; Python est inclus dans l’image |

#### PyPI (SSG ou Server)

Installez l’application en ligne de commande :

```bash
pip install epub-browser
```

Affichez la référence des commandes propre à chaque mode :

```bash
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

#### Docker (Server)

L’image publiée [`dfface/epub-browser`](https://hub.docker.com/r/dfface/epub-browser)
exécute le mode Server et ne nécessite pas Python sur l’hôte :

```bash
docker pull dfface/epub-browser:latest
```

Utilisez `latest` pour évaluer la version actuelle ; épinglez une étiquette de
version numérotée pour un déploiement reproductible en production. Consultez
[Docker](#docker) pour les montages requis des livres et de l’état, un démarrage
rapide avec Compose, la première configuration et les recommandations réseau.

### Démarrage rapide

#### Générer un site statique

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

Servez `dist/` en HTTP. L’ouverture directe des pages générées via `file://` n’est pas prise en charge, car le stockage du navigateur, les modules, les manifestes et les Service Workers nécessitent une origine HTTP.

Pour un site hébergé sous un préfixe d’URL, définissez le chemin public séparément de la destination dans le système de fichiers :

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist \
  --base-path /my-repository/
```

`--base-path` modifie les URL générées, et non l’emplacement d’écriture des fichiers. Avec `/my-repository/`, les liens, icônes, manifestes, métadonnées des livres et entrées du Service Worker utilisent tous ce préfixe, tandis que les fichiers restent directement dans `dist/`.

#### Exécuter une bibliothèque Server persistante

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

Ouvrez `http://127.0.0.1:8000/`. Lors du premier accès, EPUB Browser vous invite à créer l’administrateur initial. La bibliothèque n’est ni analysée ni exposée tant que cette configuration unique n’est pas terminée.

Si vous avez choisi Docker, ignorez la commande Python ci-dessus et poursuivez avec
le [démarrage rapide Docker Compose](#docker-compose).

## Formats et lecture

### Sources et identité stable des livres

Chaque argument positionnel `SOURCE` peut être un fichier EPUB, un fichier PDF ou
un répertoire. Les répertoires sont parcourus récursivement. Une même commande
accepte plusieurs sources :

```bash
epub-browser server book.epub /srv/library /srv/periodicals \
  --server-dir /srv/epub-browser \
  --watch
```

Chaque livre reçoit un `book_id` stable, également exposé sous le nom `book_hash` dans les URL générées et les données du navigateur. La valeur par défaut générale de la CLI est :

```bash
--book-id-storage sidecar
```

Le mode sidecar écrit un fichier d’identité visible à côté de la source, par exemple `BOOK.epub.epub-browser.json` ou `BOOK.pdf.epub-browser.json`, sans modifier les octets de celle-ci. Le sidecar contient l’identifiant stable et une empreinte SHA-256 vérifiée de la source.

Pour placer l’identifiant dans les métadonnées OPF de l’EPUB ou dans le dictionnaire d’informations du document PDF, sélectionnez le stockage intégré pour toute l’invocation :

```bash
--book-id-storage embedded
```

Le mode intégré peut reconstruire le ZIP de l’EPUB ou ajouter une mise à jour incrémentielle des métadonnées au PDF avant la conversion. Si le PDF ne peut pas être mis à jour et que sa source est inchangée, EPUB Browser enregistre le même identifiant dans un sidecar adjacent. Cela vaut aussi pour les PDF signés, chiffrés et en lecture seule. EPUB Browser s’arrête si des identifiants divergent, si des sources actives partagent un identifiant, si un support est invalide ou si un support requis ne peut pas être écrit.

Lors d’une migration entre les modes de stockage, EPUB Browser copie l’identifiant existant sur le support choisi et conserve l’autre support valide. Un identifiant intégré existant depuis la v2.0.4 est copié vers le sidecar par défaut sans réécriture de l’EPUB. Après toute mise à jour des métadonnées, SSG et Server fournissent tous deux une copie octet par octet de la source PDF.

### PDF : une page, un chapitre

PDF est pris en charge par les deux modes de déploiement. Le lecteur traite chaque
page PDF comme un chapitre ordinaire d’EPUB Browser. La page de livre, la navigation
entre chapitres, la table des matières, la pagination, la lecture continue, la
progression, les sessions de lecture, les annotations, le Dictionnaire et
l’Encyclopédie conservent donc une interface et un modèle de données communs :

| Concept PDF | SSG | Server |
| --- | --- | --- |
| URL de la page 1 | `chapter_0.html` | `/book/<book-id>/chapter_0.html` |
| URL de la page N | `chapter_{N-1}.html` | `/book/<book-id>/chapter_{N-1}.html` |
| Étiquettes de page et table des matières | Générées localement ; chaque page est répertoriée | Générées à partir du cache de métadonnées PDF ; chaque page est répertoriée |
| Plan intégré | Un marqueur sur l’entrée de la table des matières correspondant à la page de destination | Le même marqueur, sans supprimer ni réorganiser les entrées de page |
| Défilement, pagination et changement de page | Structures de chapitre statiques et PDF.js local | Structures de chapitre communes dynamiques et PDF.js local |
| Surlignages, notes, Dictionnaire, Encyclopédie | Composants communs locaux au navigateur si une couche texte existe | Composants communs authentifiés si une couche texte existe |
| Octets PDF bruts | Un `document.pdf` dans la sortie statique du livre | Route réservée aux sessions, avec prise en charge des plages, pour le document mis en cache |

Les numéros de page visibles et ceux de PDF.js commencent à 1 ; les indices de
chapitre dans les URL, l’état, les API et SQLite commencent à 0. La page PDF 1
correspond donc toujours à `chapter_0.html`. La table des matières normalisée
conserve une entrée `Page N` pour chaque page ; les titres du plan PDF intégré
sont ajoutés comme marqueurs de plan à leur entrée de destination, y compris
plusieurs marqueurs sur une même page.

SSG écrit un seul `document.pdf` et une structure `chapter_<index>.html` par page.
La sortie SSG ne contient ni script de session, ni appel `/api/*`, ni donnée
d’annotation synchronisée, ni dépendance au Server. Le Server stocke la source
complète, identique octet par octet, sous `book/<book-id>/pdf/document.pdf` et ne
la divise ni ne la réécrit jamais. Il génère dynamiquement les mêmes structures
de chapitre à partir des métadonnées PDF. Une source modifiée invalide et actualise
entièrement le cache PDF (document, métadonnées et couverture dérivée) au lieu de
mélanger d’anciennes et de nouvelles pages.

Le point de terminaison du document brut du Server est réservé aux sessions :
`GET`/`HEAD /api/books/<book-id>/document`. Il vérifie l’authentification, la
visibilité du livre, le format PDF et les empreintes de la source et du cache,
puis prend en charge des réponses à plage unique, de taille limitée, avec `ETag`,
`Accept-Ranges`, une mise en cache privée, `nosniff` et une disposition `inline`
pour le PDF. Il n’expose aucun chemin absolu, n’accepte pas l’authentification
par PAT et ne figure pas dans la surface PAT/OpenAPI. SSG possède uniquement son
`document.pdf` local et aucune API de document brut.

Les PDF dotés d’une couche texte PDF.js exploitable réutilisent exactement la
fenêtre contextuelle de sélection et le composant d’annotation existants pour
les surlignages et les notes, ainsi que le Dictionnaire et l’Encyclopédie. Le
stockage, la propriété, l’export, la liste et les liens profonds des annotations
restent communs ; il n’existe ni table d’annotations ni interface de réglages
spécifique au PDF. Les PDF numérisés ou composés uniquement d’images restent
lisibles, mais les surlignages, les notes, le Dictionnaire, l’Encyclopédie et la
recherche dans le document, tous fondés sur une sélection, sont explicitement
indisponibles en l’absence d’une couche texte exploitable. Une sélection couvrant
plusieurs pages peut toujours être copiée, tandis que les actions d’annotation
et de consultation affichent le message localisé indiquant que la fonction n’est
pas prise en charge ; la sélection dans une page continue de fonctionner.

PDF.js ne constitue pas une seconde visionneuse. Avant de compiler ou de publier,
récupérez et vérifiez les ressources tierces verrouillées :

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
```

L’application sert ensuite à l’exécution les modules et workers PDF.js locaux avec
hachage ; elle ne les télécharge jamais depuis un CDN. Les fenêtres modales
d’affichage des images utilisent la dépendance verrouillée GLightbox ;
Fancyapps/Fancybox n’est ni une dépendance d’exécution ni une dépendance
redistribuée. Consultez
[third_party/README.md](../../third_party/README.md) pour le processus de gestion
des ressources verrouillées et des versions.

## Déploiement

### SSG

SSG construit un instantané complet dans un répertoire de préparation voisin, le valide, puis remplace la destination. Si une conversion échoue, la destination précédente reste inchangée. La sortie générée ne contient ni base de données Server, ni état de migration, ni page de compte, ni métadonnées de cache d’exécution.

Le comportement de SSG est volontairement local et sans compte :

- La progression de lecture et les annotations utilisent le stockage du navigateur sur l’origine actuelle.
- L’étagère prend en charge l’import et l’export JSON locaux ; elle n’offre aucune action de synchronisation cloud.
- La connexion, les paramètres de compte, les API Server et les contrôles dépendant de l’utilisateur sont absents.
- La destination de stockage est fixée au stockage local du navigateur et n’est pas présentée comme un réglage.
- La sortie statique inclut le Service Worker nécessaire aux ressources utilisables hors ligne.

Tous les JavaScript, CSS, polices et icônes requis par l’application sont inclus dans la sortie. Consultez [Fonctionnement autonome et comportement réseau](#fonctionnement-autonome-et-comportement-réseau) pour la seule requête réseau facultative.

### Server

#### Configuration initiale, comptes et autorisations

Sur un répertoire d’état persistant vierge, les pages normales redirigent vers `/setup`. Les API, flux d’événements, ressources générées et livres renvoient une réponse indiquant que la configuration est requise jusqu’à la création de l’administrateur initial. Effectuez cette configuration via loopback ou un autre chemin privé de confiance avant d’exposer le port : le premier envoi de configuration réussi attribue le compte administrateur.

Après la configuration :

- L’inscription publique est fermée. Les administrateurs créent et gèrent les utilisateurs.
- Les comptes ont le rôle `administrator` ou `member`.
- Les livres ordinaires sont visibles par tout compte authentifié.
- Les livres restreints ne sont visibles que par les administrateurs et les utilisateurs explicitement sélectionnés.
- Chaque utilisateur possède son étagère, sa progression, ses annotations et ses sessions actives.
- Les utilisateurs peuvent modifier leur mot de passe et révoquer leurs sessions.
- Les administrateurs peuvent gérer les utilisateurs, les rôles, les mots de passe, les sessions et les autorisations sur les livres.
- Les sessions utilisent un cookie HttpOnly, une protection CSRF et une durée de vie glissante de 30 jours.

#### Authentification unique OIDC et liaison de comptes

Le mode Server peut utiliser un fournisseur OpenID Connect (OIDC) générique,
notamment Authelia, Keycloak, Authentik et les services compatibles. Dans
**Administration → Connexion OIDC**, saisissez le nom du fournisseur présenté aux
lecteurs, l’URL de l’émetteur, l’ID client, le secret client, l’URI de redirection
exacte, les scopes et la revendication de nom d’utilisateur. EPUB Browser utilise
la découverte et le flux Authorization Code avec PKCE S256, valide le jeton
d’identité signé et identifie un compte externe uniquement par `(issuer, sub)` ;
les revendications d’e-mail et de nom d’utilisateur servent uniquement
d’indications pour l’affichage et la création de comptes, jamais de clés d’identité.

Enregistrez exactement cette URL de rappel auprès du fournisseur, y compris le schéma et l’hôte :

```text
https://reader.example.com/auth/oidc/callback
```

Les utilisateurs existants peuvent se connecter localement et associer le
fournisseur à leur compte dans les paramètres. Sinon, une identité externe inconnue
doit fournir une fois l’identifiant et le mot de passe d’un compte local existant.
Lorsque la création automatique de comptes est activée, elle crée un compte
membre sans mot de passe ; elle n’importe jamais de rôle administrateur. Laissez
les utilisateurs existants associer leur compte en premier : activer la création
automatique trop tôt peut créer des **comptes locaux en double**. La connexion par mot de passe de
l’**administrateur local** reste toujours disponible, même si la connexion locale
par mot de passe des membres est désactivée. Testez et protégez ces identifiants
de récupération. La déconnexion auprès du fournisseur n’est pas effectuée, et ses
jetons d’accès et d’actualisation ne sont pas stockés.

Pour Authelia, configurez un client confidentiel dans la section de son fournisseur
OIDC. L’extrait suivant utilise des valeurs volontairement fictives et suppose que
les clés et politiques du fournisseur requises par Authelia sont déjà configurées.
Stockez dans Authelia un hachage d’un secret client aléatoire robuste, puis
saisissez une fois le secret brut correspondant dans EPUB Browser :

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

Dans EPUB Browser, utilisez l’émetteur `https://auth.example.com`, l’ID client
`epub-browser`, les scopes `openid profile email` et la revendication de nom
d’utilisateur `preferred_username`. L’enregistrement vérifie immédiatement la
découverte et les capacités du fournisseur ; en cas d’échec, la configuration
précédente reste active.

#### Configurer et encadrer la lecture par IA

Les administrateurs configurent la lecture par IA dans **Administration**, juste
après la gestion des utilisateurs et avant la gestion des livres. La page enregistre
dans la base SQLite du Server une URL de base compatible OpenAI, une clé API, le
modèle, le délai d’attente, le budget de contexte, le plafond de concurrence et la
limite quotidienne par défaut d’appels au fournisseur. L’IA est initialement
désactivée pour les membres ; un administrateur doit en accorder l’accès à chacun
et peut définir une limite quotidienne individuelle (`0` signifie illimité).

Les couches d’apprentissage des chapitres et les avis au niveau du livre sont
partagés pour chaque langue admissible, tandis que les conversations de suivi
restent privées pour chaque compte. Les résultats, l’état des tâches, les
étiquettes personnalisées, la classification de lecture des livres et les échanges
privés de suivi sont stockés dans SQLite. Après un changement de configuration du
modèle, les anciens résultats restent disponibles jusqu’à ce qu’un administrateur
les régénère explicitement.

Lorsqu’un lecteur demande un guide généré par IA ou pose une question, le texte EPUB
sélectionné et le contexte compressé de la conversation sont envoyés au fournisseur
externe configuré. N’activez cette fonction que si les lecteurs sont autorisés à
envoyer ce contenu au fournisseur. La clé API n’est jamais renvoyée à un navigateur
ni exposée par une API ; protégez le répertoire d’état du Server en conséquence.

Pour un premier démarrage sans intervention, fournissez un nom d’utilisateur et un fichier de mot de passe :

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --admin-username admin \
  --admin-password-file /run/secrets/epub-browser-admin-password \
  --no-browser
```

Le fichier de mot de passe doit avoir le mode `0600`. EPUB Browser supprime un saut de ligne final, stocke un hachage Argon2id et n’affiche jamais le secret. Une configuration incomplète, un fichier vide ou illisible arrête le démarrage. Une fois la configuration terminée, les démarrages suivants ne lisent plus le secret d’amorçage.

Les équivalents d’environnement sont `EPUB_BROWSER_ADMIN_USERNAME` et `EPUB_BROWSER_ADMIN_PASSWORD_FILE`. `EPUB_BROWSER_ADMIN_PASSWORD` est uniquement une solution de repli en clair lorsqu’aucun fichier de mot de passe n’est configuré. Un chemin de fichier de mot de passe fourni par la CLI est prioritaire sur les sources de mot de passe de l’environnement.

#### Lancement du navigateur et journalisation

Par défaut, le Server tente d’ouvrir le navigateur par défaut du système d’exploitation après le démarrage du serveur HTTP. `--no-browser` empêche ce lancement local. Cette option **ne désactive ni l’interface web ni l’accès par navigateur** ; elle supprime uniquement l’appel local `webbrowser.open(...)`. Utilisez-la pour Docker, systemd, les sessions SSH, les machines sans interface graphique et les scripts.

Par défaut (`--log-level error`), la CLI n’émet que les erreurs afin que les affichages de progression du terminal ne soient pas interrompus par des messages ou avertissements ordinaires. Un terminal interactif affiche une fois l’URL d’écoute ; les exécutions Docker et de service non interactives restent autrement silencieuses. Utilisez `--log-level warning` pour inclure les avertissements, `--log-level info` pour la journalisation opérationnelle et des accès HTTP, ou `--log-level debug` pour le niveau de détail maximal. `--log` reste un alias de compatibilité de `--log-level info`.

Les analyses initiales et celles déclenchées par la surveillance des sources apparaissent dans l’interface web plutôt que sous forme de `tqdm` dans le terminal. Le résumé d’une analyse réussie se ferme automatiquement ; les échecs restent visibles jusqu’à leur fermeture. Avec `--watch`, corriger ou remplacer une source lance une nouvelle analyse sans intervention manuelle.

#### État persistant et éphémère

Le mode Server persistant requiert `--server-dir`. Pour une exécution jetable, utilisez plutôt `--ephemeral` :

```bash
epub-browser server book.epub --ephemeral
```

L’état éphémère est supprimé à l’arrêt. Comme sa base de données est nouvelle à chaque exécution, la configuration doit également être répétée, sauf si des identifiants d’amorçage sans intervention sont fournis.

Structure persistante :

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

Seul `data/` fait autorité. `cache/` peut être supprimé et sera reconstruit. Conservez `data/` lors des mises à niveau et du remplacement des conteneurs. Un verrou du système d’exploitation garantit l’exclusivité ; `.server.lock` peut subsister après un arrêt normal comme métadonnées de diagnostic.

Stockez le fichier persistant `data/epub-browser.db` sur un système de fichiers local. Les systèmes de fichiers partagés ou réseau ne sont pas pris en charge pour la concurrence WAL. Les sauvegardes vérifiées restent dans `data/backups/` et incluent toutes les données WAL validées.

#### Réseau local et proxy inverse

Le Server écoute par défaut sur `127.0.0.1:8000`. Pour un réseau local de confiance :

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --port 8080 \
  --no-browser
```

N’exposez pas le serveur HTTP intégré directement sur Internet. Assurez la terminaison TLS au niveau d’un proxy inverse, appliquez des contrôles réseau et activez les cookies sécurisés.

Pour enregistrer les adresses IP réelles des clients dans les sessions actives et les limites du nombre de tentatives de connexion derrière un proxy inverse, configurez le **réseau du proxy directement connecté** (et non les plages d’adresses des clients publics) :

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

Répétez `--trusted-proxy-cidr` une fois pour chaque adresse ou réseau de proxy directement connecté. `X-Forwarded-For` n’est pris en compte que si le proxy directement connecté appartient à l’un de ces CIDR ; sinon, seule l’adresse source de la connexion est enregistrée. Le traitement des adresses transférées par Uvicorn est désactivé : `Forwarded` et `FORWARDED_ALLOW_IPS` ne peuvent donc pas élargir cette frontière de confiance. Utilisez `--cookie-secure` uniquement lorsque le navigateur accède au service via HTTPS.

### Docker

L’image exécute le mode Server persistant avec les valeurs par défaut suivantes :

- `/app/Library` comme source
- `/app/EpubBrowserFiles` comme état persistant
- `--watch`
- `--no-browser`
- `--host 0.0.0.0 --port 80`
- `--book-id-storage embedded`
- `--kindle`

Comme l’identité intégrée peut modifier les fichiers EPUB ou PDF, montez la bibliothèque en lecture-écriture. Montez également l’état du Server en lecture-écriture et conservez-le lors du remplacement du conteneur :

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  dfface/epub-browser:latest
```

Consultez `http://127.0.0.1:8080/setup` avant de modifier la publication du port ou les règles du proxy.

#### Docker Compose

Le dépôt inclut un [docker-compose.yml](../../docker-compose.yml) pour les utilisateurs qui préfèrent Compose. Depuis une copie de travail, créez `Library/`, placez-y des livres EPUB ou PDF, puis exécutez :

```bash
docker compose up -d --build
```

Cette configuration publie uniquement `127.0.0.1:8080`, conserve les livres EPUB/PDF sources dans `./Library` et rend l’état du Server persistant dans `./EpubBrowserFiles`. La `command` complète du Server est volontairement visible dans le fichier afin que les options propres au déploiement puissent être ajoutées sans remplacer une valeur par défaut implicite de l’image. Effectuez la configuration unique sur `http://127.0.0.1:8080/setup`. Pour l’accès à distance, conservez cette publication limitée à l’interface loopback et placez devant elle un proxy inverse TLS authentifié.

Pour une configuration sans intervention :

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

Après le premier démarrage réussi, le montage du secret à usage unique peut être supprimé. Une bibliothèque en lecture seule fonctionne uniquement si chaque EPUB contient déjà un identifiant intégré valide correspondant. Les sidecars existants sont conservés lorsque leurs identifiants sont intégrés.

Montez `/app/SyncData:ro` uniquement pendant l’import de l’ancien JSON d’étagère :

```bash
-v /path/to/legacy-sync:/app/SyncData:ro
```

Dans les exemples, le port publié sur l’interface loopback rend le conteneur accessible uniquement depuis l’hôte. Pour l’accès à distance, utilisez un proxy inverse TLS, configurez le CIDR réel de son réseau de conteneurs et ajoutez `--cookie-secure`.

## Référence et exploitation

### Référence des commandes

#### `epub-browser ssg SOURCE [SOURCE ...]`

| Option | Signification |
| --- | --- |
| `--output-dir DIR`, `-o DIR` | Destination requise pour l’instantané statique atomique. |
| `--base-path PATH` | Préfixe d’URL public ; valeur par défaut `/`. Il doit commencer et se terminer par `/`. |
| `--book-id-storage sidecar\|embedded` | Support d’identité stable pour chaque source sélectionnée ; valeur par défaut `sidecar`. |
| `--kindle` | Génère des pages minimales sans dépendance pour les anciens Kindle à encre électronique et y redirige les navigateurs Kindle WebKit ; désactivé par défaut. |
| `--log` | Alias de compatibilité de `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Niveau de détail des journaux opérationnels ; valeur par défaut `error`, qui masque les sorties de conversion et avertissements ordinaires. |

#### `epub-browser server SOURCE [SOURCE ...]`

Exactement une des options `--server-dir` et `--ephemeral` est requise.

| Option | Signification |
| --- | --- |
| `--server-dir DIR` | Racine des données persistantes faisant autorité et du cache remplaçable. |
| `--ephemeral` | Utilise un état jetable ; incompatible avec `--server-dir`. |
| `--watch`, `-w` | Surveille les sources et synchronise les ajouts, les mises à jour, les déplacements et les suppressions. |
| `--host ADDRESS` | Adresse d’écoute ; valeur par défaut `127.0.0.1`. |
| `--port PORT`, `-p PORT` | Port d’écoute ; valeur par défaut `8000`. |
| `--no-browser` | Ne lance pas le navigateur local par défaut. L’interface web reste disponible. |
| `--log` | Alias de compatibilité de `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Niveau de détail des journaux opérationnels ; valeur par défaut `error`. Les journaux d’accès HTTP sont activés aux niveaux `info` et `debug`. |
| `--legacy-sync-dir DIR` | Lit l’ancien JSON d’étagère pendant la migration au démarrage. |
| `--book-id-storage sidecar\|embedded` | Support d’identité stable pour chaque source sélectionnée ; valeur par défaut `sidecar`. |
| `--admin-username NAME` | Administrateur initial sans intervention ; repli `EPUB_BROWSER_ADMIN_USERNAME`. |
| `--admin-password-file FILE` | Fichier secret initial privilégié ; repli `EPUB_BROWSER_ADMIN_PASSWORD_FILE`, puis `EPUB_BROWSER_ADMIN_PASSWORD` si aucun fichier n’est défini. |
| `--trusted-proxy-cidr CIDR` | Option répétable définissant les réseaux de proxys directement connectés approuvés pour lire en toute sécurité l’IP du client dans `X-Forwarded-For`. |
| `--cookie-secure` | Envoie le cookie de session uniquement via la connexion HTTPS exposée au navigateur. |
| `--kindle` | Sert des pages minimales sans dépendance pour les anciens Kindle à encre électronique et y redirige les navigateurs Kindle WebKit ; désactivé par défaut. |

#### Syntaxe v1 historique

L’ancienne syntaxe est prise en charge pendant toute la série majeure v2 :

| Commande v1 | Correspondance v2 |
| --- | --- |
| `epub-browser BOOKS` | `epub-browser server BOOKS --ephemeral` |
| `epub-browser BOOKS --output-dir STATE` | `epub-browser server BOOKS --server-dir STATE` |
| `epub-browser BOOKS --no-server --output-dir DIST` | `epub-browser ssg BOOKS --output-dir DIST` |
| `--sync-dir DIR` | `server --legacy-sync-dir DIR` |

L’option `--keep-files`, propre à l’ancienne version, conserve un répertoire Server temporaire. Les répertoires Server persistants sont déjà permanents. Avec `--log`, l’adaptateur de compatibilité affiche la commande v2 équivalente ; sinon, il reste silencieux.

### Données de lecture et répartition des fonctionnalités

- Découverte récursive des EPUB/PDF et bibliothèques Calibre, étiquettes de métadonnées, recherche et recherche en pinyin
- Interfaces adaptatives pour la bibliothèque, les détails du livre et la lecture des chapitres
- Défilement, pagination, lecture continue, largeur du contenu réglable, polices, CSS personnalisé, thèmes et mode de lecture sans distractions
- Surlignages, notes, consultation des annotations, groupes d’étagères imbriqués, étiquettes et import/export JSON
- Langues de l’interface : anglais, chinois simplifié, chinois traditionnel,
  coréen, japonais, espagnol, allemand, français, russe, italien, portugais du
  Brésil, arabe, indonésien, hindi, vietnamien, thaï et malais
- Comportement adapté aux liseuses pour les navigateurs Kindle/Silk ; les fonctions exigeantes du navigateur peuvent être réduites

| Données | SSG | Server |
| --- | --- | --- |
| Progression de lecture | Locale au navigateur | Enregistrement SQLite de l’utilisateur authentifié |
| Surlignages et notes | Locaux au navigateur | Enregistrements SQLite de l’utilisateur authentifié |
| Évaluations, avis et historique privés des sessions de lecture | Absents | Enregistrements SQLite de l’utilisateur authentifié |
| Étagère | Locale au navigateur ; import/export | Document cloud versionné de l’utilisateur authentifié ; enregistrement automatique |
| Comptes et sessions | Absents | SQLite sous `<server-dir>/data` |
| Autorisations sur les livres | Absentes | SQLite sous `<server-dir>/data` |

Le Server ne propose aucun sélecteur entre stockage local et cloud : les données de lecture des utilisateurs authentifiés sont toujours stockées sur le Server. SSG ne génère jamais d’historique privé détaillé des sessions de lecture. SSG n’interroge jamais les API Server et utilise toujours le stockage local de l’origine actuelle du navigateur.

### Fonctionnement autonome et comportement réseau

L’application est autonome pour la lecture : les JavaScript, CSS, polices, icônes, manifestes et ressources EPUB converties requis sont servis localement. Elle ne dépend d’aucun CDN à l’exécution. Bloquer l’accès sortant à Internet n’empêche aucune des opérations suivantes : configuration, connexion, navigation, lecture, annotations, progression, utilisation de l’étagère, administration ou conversion des sources.

Le pied de page peut effectuer une requête facultative auprès de l’API GitHub Releases pour découvrir une version plus récente d’EPUB Browser. En cas d’échec, de blocage ou d’utilisation hors ligne, seule cette indication de mise à jour disparaît.

SSG publie un Service Worker statique. Le Server désactive et retire délibérément le Service Worker à l’échelle de l’origine afin qu’un compte ne puisse pas recevoir le contenu protégé mis en cache d’un autre compte.

### API Server et WebHooks

Les comptes Server peuvent créer des jetons d’accès personnels à portée limitée dans les paramètres du compte. Les clients externes utilisent `Authorization: Bearer <PAT>` avec l’API versionnée `/api/v1/*` ; les cookies du navigateur n’authentifient pas ces routes. L’API couvre les livres visibles et le contenu des chapitres, l’étagère, la progression, les annotations et les avis du propriétaire du jeton, ainsi que des données inter-utilisateurs en lecture seule pour les PAT d’administrateur avec `admin:data:read`.

Le document OpenAPI 3.1 est disponible sur `/openapi.json` ; les utilisateurs connectés peuvent consulter la référence locale sur `/api-docs`. Exemple : `curl -H 'Authorization: Bearer …' https://reader.example/api/v1/books`. Le détail d’un chapitre renvoie par défaut du HTML assaini et du texte brut avec `?format=text`.

Les points de terminaison de liste renvoient `items` et `next_cursor`. La valeur par défaut de `limit` est 24 et le maximum est 100. Transmettez `next_cursor` comme `cursor` avec les mêmes filtres pour récupérer la page suivante. Un curseur null indique la dernière page. Utilisez par exemple `/api/v1/me/annotations?book_id=BOOK_ID&chapter_index=0&fields=id,text,note` pour récupérer des champs d’annotation sélectionnés dans un chapitre EPUB ou une page PDF. Les filtres de requête et les champs pris en charge sont répertoriés dans le document OpenAPI.

Le vocabulaire utilise par défaut le même format de liste. Les clients qui utilisent l’ancienne réponse `words` peuvent envoyer `page=1` ou `page_size` pour sélectionner l’ancien format de pagination.

Les administrateurs gèrent les points de terminaison WebHook dans Administration. Les secrets ne sont affichés qu’à leur création ou rotation. Les livraisons sont signées et enregistrées de façon durable ; elles font l’objet de nouvelles tentatives après toute réponse autre que 2xx. Les événements d’avis sur un livre contiennent les identifiants et les horodatages des actions, mais jamais l’évaluation ni le texte de l’avis.

### Sécurité des données et migration

Avant de mettre à niveau des installations Server persistantes, sauvegardez les livres EPUB/PDF sources et `<server-dir>/data`. Conservez le même volume d’état persistant lors du remplacement du conteneur.

La migration au démarrage est automatique et peut être reprise sans risque après un redémarrage. Elle vérifie les anciennes bases de données, crée une sauvegarde, met à niveau une copie, importe les anciennes données admissibles d’étagère, de progression et d’annotation dans l’administrateur initial en attente et ne retire les anciens artefacts publics remplaçables qu’après la réussite des points de contrôle. Les requêtes ordinaires n’analysent jamais les anciens répertoires de synchronisation. En cas de base corrompue, de hachage de mot de passe invalide, d’ancienne base ambiguë ou d’identifiants conflictuels, le démarrage s’arrête sans tenter de deviner les valeurs ni d’écraser les données.

Une base `epub-browser.db` ou `annotations.db` migrée à la racine est conservée comme copie de récupération sensible, mais ne fait plus autorité ; `data/epub-browser.db` fait autorité et les requêtes du Server n’utilisent pas le fichier conservé à la racine. Gardez cette copie de récupération privée. Ne la supprimez manuellement que lorsque le Server est arrêté, après avoir vérifié la base faisant autorité et la sauvegarde enregistrée, et uniquement si un retour à la v1 n’est plus nécessaire. EPUB Browser ne la supprime jamais automatiquement.

Si `epub-browser.db` et `annotations.db` existent tous deux à une ancienne racine, le démarrage s’arrête et les laisse intacts. Consultez [Migration vers v2](../migration-v2.md) pour la sauvegarde, le retour arrière, la reconstruction du cache et la résolution des conflits.

### Dépannage

#### La commande a démarré, mais aucun navigateur ne s’est ouvert

Supprimez `--no-browser` sur une machine locale dotée d’un environnement graphique ou ouvrez manuellement l’URL d’écoute affichée. Avec Docker, systemd, SSH et les sessions non interactives, vous devez normalement ouvrir l’URL vous-même.

#### La CLI semble silencieuse

L’absence de messages est volontaire sans `--log`, en particulier dans les environnements non interactifs. Ajoutez `--log` pour obtenir les détails opérationnels et d’accès. La progression des analyses du Server apparaît dans l’interface web.

#### Docker ne peut pas écrire d’identifiant stable

L’image utilise par défaut l’identité intégrée. Montez `/app/Library` en lecture-écriture ou intégrez au préalable des identifiants valides correspondants. Utilisez une commande personnalisée avec `--book-id-storage sidecar` uniquement si vous préférez un support sidecar accessible en écriture.

#### Un site SSG généré contient des liens brisés sous un sous-chemin

Régénérez-le avec un `--base-path` normalisé, par exemple `/reader/`, et configurez l’hôte statique pour servir la sortie sous ce même préfixe.

#### Le Server refuse de démarrer après une mise à niveau

Lisez la première erreur de migration ou de validation journalisée, conservez les données et les fichiers sources et consultez [docs/migration-v2.md](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/migration-v2.md). Ne supprimez pas le répertoire `data/` faisant autorité pour contourner une erreur.

## Développement et licence

### Contribution

Les Issues et Pull Requests sont les bienvenus sur [dfface/epub-browser](https://github.com/dfface/epub-browser). Un rapport utile comprend la commande exacte, le navigateur/appareil, les étapes de reproduction, les journaux pertinents et l’EPUB ou le PDF lorsqu’il peut être partagé légalement.

#### Contrat d’architecture pour les mainteneurs

Lisez [AGENTS.md](../../AGENTS.md) avant de modifier le traitement du contenu, les
modèles de page, les caches, les autorisations, les ressources ou le comportement
de déploiement. Ce document définit la frontière entre les formats EPUB/PDF, les
responsabilités de SSG et Server, les révisions de cache indépendantes, les
exigences d’i18n à l’exécution, les contrôles de sécurité et les vérifications
requises. Les termes communs du produit, tels que *chapitre du lecteur*, *fenêtre
de lecture*, *espace de lecture* et *cache de contenu*, sont définis dans
[CONTEXT.md](../../CONTEXT.md).

En résumé : conservez une seule interface de lecture, gardez les données réservées
au Server hors de SSG, séparez les caches dérivés EPUB et PDF des données
utilisateur SQLite et n’ajoutez jamais de dépendance à un CDN à l’exécution. Toute
modification d’une interface commune doit être testée avec les deux formats et les
deux modes de déploiement, lorsque cela s’applique.

#### Développement depuis une copie des sources

Les fichiers tiers du navigateur sont des fichiers de compilation générés, et non
des sources du projet ; `epub_browser/assets/vendor/` est donc volontairement absent
de Git. Récupérez explicitement les versions exactes verrouillées avant de
développer ou de compiler, puis vérifiez-les hors ligne :

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
python3 -m unittest tests.test_vendor_assets -v
python3 -m build
```

`fetch` est la seule commande ci-dessus qui télécharge des ressources tierces pour
le navigateur. Le fichier de verrouillage enregistre des archives npm immuables,
des empreintes de fichiers, des listes d’autorisation et des licences ; `verify`,
les tests, les compilations depuis une copie de travail où les dépendances ont été
récupérées et le lecteur installé ne téléchargent pas de ressources de navigateur.
La commande isolée standard `python3 -m build` peut néanmoins consulter un index
de paquets Python pour les prérequis de compilation. Pour une compilation entièrement sans réseau,
récupérez les fichiers de l’arborescence `vendor/` et préinstallez `build`,
`setuptools` et `wheel` avant de vous déconnecter, puis exécutez
`PIP_NO_INDEX=1 python3 -m build --no-isolation`. Les wheels, distributions
sources, images Docker et sites SSG générés contiennent les fichiers vérifiés et
ne dépendent d’aucun CDN à l’exécution. Consultez
[third_party/README.md](../../third_party/README.md) pour le processus de mise à
jour, de publication et de maintenance du dépôt.

### Licence

[MIT](../../License.txt)
