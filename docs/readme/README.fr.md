# EPUB Browser

> EPUB et PDF dans une bibliothèque de lecture privée ou sous forme de site statique autonome.

**README :** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

**Langues de l’interface (17) :** anglais, chinois simplifié, chinois traditionnel, japonais, coréen, espagnol, allemand, français, russe, italien, portugais du Brésil, arabe, indonésien, hindi, vietnamien, thaï et malais.

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![Une page PDF dans le lecteur commun d’EPUB Browser.](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser traite les fichiers `.epub` et `.pdf` dans deux modes aux responsabilités clairement séparées :

| | `ssg` | `server` |
| --- | --- | --- |
| EPUB et PDF | Oui | Oui |
| Déploiement | Hébergement statique, Pages, stockage objet, Nginx | Service privé de lecture persistant |
| Comptes | Aucun | Comptes locaux |
| Authentification unique OIDC | Non incluse | Provider générique, liaison de comptes existants et création facultative de membres |
| Progression, annotations, bibliothèque | Ce navigateur uniquement | Données du compte authentifié dans SQLite |
| Mise à jour des sources | Relancer `ssg` | Redémarrer le service ou utiliser `--watch` |
| Base de données d’exécution | Aucune | Obligatoire |

PDF est un format de livre de premier rang : la page 1 devient `chapter_0.html`, chaque page figure dans la table des matières et PDF.js l’affiche localement dans la même bibliothèque, fiche de livre, interface de lecture, recherche et chaîne d’annotation. Les fonctions PDF non prises en charge, comme la lecture par IA, sont explicitement masquées et aucun CDN n’est requis pendant la lecture.

Utilisez `ssg` pour publier des fichiers statiques ordinaires. Utilisez `server` si vous avez besoin de comptes, de données partagées entre appareils, de contrôle d’accès aux livres ou d’une surveillance automatique des sources.

## Vue d’ensemble

### Pourquoi choisir EPUB Browser ?

- **Lecture native avec l’IA, ancrée dans le texte :** en mode Server et pour les EPUB uniquement, les guides de chapitre, les explications étayées par des preuves, les cartes mentales, les pistes de réflexion et les conversations privées avec Ask AI restent à côté du texte original, plutôt que dans un résumé générique détaché.
- **Indicateurs de lecture privés :** en mode Server, le temps de lecture active, le calendrier d’activité, les tendances, les sessions et les livres les plus lus ne sont visibles que par le compte actuellement connecté.

![Un guide de chapitre généré par l’IA à côté du texte EPUB original, avec une conversation Ask AI privée.](assets/ai-native-reading.png)

*L’accompagnement par l’IA et les questions privées restent ancrés dans le livre original.*

![Des indicateurs de lecture privés avec un calendrier d’activité et la tendance du temps de lecture.](assets/reading-insights.png)

*Les indicateurs transforment la lecture active en un historique privé facile à comprendre.*

### Pile technique

L’interface utilise du HTML sémantique, du CSS et du Vanilla JavaScript, sans framework SPA. La CLI et le Server reposent sur Python 3.9+, Starlette, Uvicorn et SQLite ; pypdf, pypdfium2 et PDF.js traitent les PDF localement, sans CDN à l’exécution.

### Démonstrations

- **Mode SSG** : [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Mode Server** : [epub.yuhan.tech](https://epub.yuhan.tech/) — identifiant et mot de passe : `demo`.

### Lecture native avec l’IA (Server uniquement)

La lecture avec l’IA construit sur le texte original une couche d’apprentissage partagée et vérifiable, plutôt qu’un résumé générique détaché du livre. Elle comprend un parcours avant la lecture, une vue d’ensemble du chapitre à la demande, des explications reliées aux citations, des indications sur le rôle des paragraphes, des éclaircissements de vocabulaire, une explication simple en fin de chapitre et des questions pour approfondir.

Les résultats sont produits par des tâches en arrière-plan, conservés dans SQLite et partagés entre les lecteurs autorisés à consulter le livre. Les conversations de suivi restent privées pour chaque compte. L’administrateur doit configurer un fournisseur compatible avec OpenAI et autoriser chaque membre. Le texte EPUB sélectionné est envoyé à ce fournisseur ; n’activez donc cette fonction qu’avec l’accord des lecteurs. Une sortie SSG ne contient jamais de comptes, de contrôles IA, de tâches ni de configuration de fournisseur.

## Bien démarrer

### Prérequis et installation

- Python 3.9 ou version ultérieure
- Un ou plusieurs fichiers `.epub` ou `.pdf`, des dossiers de livres imbriqués ou une bibliothèque de type Calibre

L’installation depuis PyPI permet d’utiliser les modes SSG et Server :

```bash
pip install epub-browser

# Aide complète pour chaque mode
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

Pour un Server persistant avec Docker, utilisez l’image publiée ; Python n’est pas requis sur l’hôte :

```bash
docker pull dfface/epub-browser:latest
```

### Démarrage rapide

#### Générer un site statique

```bash
epub-browser ssg /chemin/vers/livres \
  --output-dir /chemin/vers/dist
```

Servez `dist/` en HTTP ; n’ouvrez pas directement les pages générées avec `file://`. Pour un déploiement sous un sous-chemin, ajoutez `--base-path /mon-depot/` ; cette option modifie les URL générées, pas le dossier de sortie.

#### Lancer une bibliothèque Server persistante

```bash
epub-browser server /chemin/vers/livres \
  --server-dir /chemin/vers/etat-epub-browser \
  --watch
```

Ouvrez `http://127.0.0.1:8000/`. La première visite permet de créer l’administrateur initial ; la bibliothèque n’est ni analysée ni publiée avant la fin de cette configuration. `--no-browser` empêche seulement l’ouverture automatique du navigateur local.

## Données et exploitation

### Données, comptes et limites d’accès

Chaque livre possède un `book_id` stable. Par défaut, `--book-id-storage sidecar` enregistre cette identité à côté du fichier source sans modifier ses octets. Pour EPUB, `--book-id-storage embedded` l’inscrit dans les métadonnées OPF et nécessite une source modifiable ; pour PDF, ce réglage utilise toujours le sidecar adjacent.

En mode Server, `--server-dir` est l’emplacement de référence pour SQLite, les caches et les sauvegardes de migration. Les comptes, bibliothèques, progressions, annotations, résultats IA et tâches y sont également enregistrés. Les administrateurs gèrent les utilisateurs, rôles, sessions et autorisations d’accès aux livres ; les membres n’utilisent que les livres autorisés et leurs propres données privées. Protégez les permissions de ce dossier et de ses sauvegardes.

### Docker, proxy inverse et documentation complète

Dans un conteneur, montez les livres en lecture seule et `--server-dir` sur un volume persistant. N’acceptez les en-têtes de proxy que depuis des proxys de confiance et utilisez HTTPS pour les déploiements publics.

Pour Docker Compose, l’ensemble des options CLI, les migrations, le réseau local, le proxy inverse et le dépannage, consultez le [README anglais complet](../../README.md) ou le [README complet en chinois simplifié](README.zh-CN.md). Le comportement des deux modes est identique dans toutes les langues.

## Développement et licence

### Contribution et licence

Les Issues et Pull Requests sont les bienvenus. Consultez [License.txt](../../License.txt) pour la licence.
