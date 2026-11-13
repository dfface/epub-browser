# EPUB Browser

> **Convierte libros en sitios web. Crea una biblioteca que sea tuya.**
>
> Publica libros EPUB y PDF como un sitio web estático o ejecuta una biblioteca privada
> autoalojada con cuentas, progreso sincronizado, anotaciones y lectura nativa con IA opcional.

[Explora la biblioteca estática](https://epub-browser-test.yuhan.tech/) · [Prueba la biblioteca privada](#demostraciones-en-vivo)

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/dfface/epub-browser/main/epub_browser/assets/logo-lockup-color.png" alt="Logotipo de EPUB Browser" width="520">
</p>

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![Un PDF en el lector compartido de EPUB Browser, con la página original, la navegación, los temas y las herramientas de lectura.](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser es mucho más que un conversor de libros. Es una plataforma de lectura completa que
puedes publicar en cualquier lugar o alojar por tu cuenta. EPUB y PDF comparten la misma biblioteca,
página del libro, índice, modos de lectura, temas, seguimiento del progreso y gestión de anotaciones.
Cada página de un PDF se convierte en un capítulo del lector que PDF.js renderiza localmente
dentro de la misma experiencia de lectura: sin un visor independiente ni CDN en tiempo de ejecución.

## Contenido

- [Descripción general del proyecto](#descripción-general-del-proyecto)
  - [Por qué EPUB Browser](#por-qué-epub-browser)
  - [Stack tecnológico](#stack-tecnológico)
  - [Elegir SSG o Server](#elegir-ssg-o-server)
  - [Demostraciones en vivo](#demostraciones-en-vivo)
  - [Lectura nativa con IA](#lectura-nativa-con-ia-solo-server)
  - [Modo mínimo para Kindle](#modo-mínimo-para-kindle)
- [Primeros pasos](#primeros-pasos)
  - [Elegir una instalación](#elegir-una-instalación)
  - [Inicio rápido](#inicio-rápido)
- [Formatos y lectura](#formatos-y-lectura)
  - [Fuentes e identidad estable de los libros](#fuentes-e-identidad-estable-de-los-libros)
  - [PDF: una página, un capítulo](#pdf-una-página-un-capítulo)
- [Despliegue](#despliegue)
  - [SSG](#ssg)
  - [Server](#server)
  - [Docker](#docker)
- [Referencia y operaciones](#referencia-y-operaciones)
  - [Referencia de comandos](#referencia-de-comandos)
  - [Datos de lectura y disponibilidad de funciones](#datos-de-lectura-y-disponibilidad-de-funciones)
  - [API del Server y WebHooks](#api-del-server-y-webhooks)
  - [Seguridad de los datos y solución de problemas](#seguridad-de-los-datos-y-migración)
- [Desarrollo y licencia](#desarrollo-y-licencia)
- [Centro de documentación](../README.md)

## Descripción general del proyecto

### Por qué EPUB Browser

- **Publica donde quieras. Mantén el control.** Crea con un solo comando un sitio estático completo
  para Pages, almacenamiento de objetos o Nginx, o ejecuta un Server persistente con cuentas,
  permisos de libros y OIDC. Los recursos de la aplicación, las fuentes, PDF.js y los renderizadores
  se sirven localmente, de modo que la lectura nunca depende de una CDN.
- **EPUB y PDF, un único lector.** Ambos formatos comparten la biblioteca, la página del
  libro, el índice, el diseño adaptable, los tres modos de lectura, los temas, la pantalla completa
  y el progreso. Cada página del PDF permanece dentro del área de lectura, con zoom, selección en la
  capa de texto y anotaciones, en lugar de recurrir a un visor de previsualización independiente.
- **Encuentra el libro y también el pasaje.** La búsqueda de la biblioteca cubre metadatos, etiquetas
  y pinyin, con ordenación y paginación. En el Server, la búsqueda en todo un libro EPUB
  devuelve resultados completos agrupados por capítulos y permite saltar al pasaje resaltado. Los ID estables
  de los libros mantienen los puntos de continuación, las anotaciones y el historial vinculados al
  mismo libro.
- **Comprende, no te limites a desplazarte.** En modo Server, las guías de capítulos EPUB, las
  explicaciones con referencias al texto, los mapas mentales y las consultas privadas a Ask AI permanecen
  junto al texto original. Los resaltados, las notas, el Diccionario y la Enciclopedia funcionan con
  EPUB y PDF con capa de texto; las listas de vocabulario del Server registran la fuente y el estado
  de dominio de cada palabra.
- **Convierte la lectura en un historial que merezca la pena conservar.** Las estanterías anidadas,
  valoraciones, reseñas, exportación de anotaciones, calendarios de actividad, tendencias,
  estadísticas por libro y clasificaciones de tiempo de lectura forman un registro conectado. El
  Server mantiene los datos de lectura privados para cada cuenta y sincronizados entre dispositivos.
- **Gestiona un servicio de lectura, no solo un visor.** En modo Server, añade libros mediante subidas
  web realizadas por administradores o carpetas supervisadas, limita el uso del disco con una purga
  configurable de la caché LRU, gestiona permisos de miembros y de IA, e integra el servicio mediante
  OpenAPI, PAT y WebHooks. La lectura mínima para Kindle admite dispositivos con recursos limitados;
  el Server también ofrece un panel personal de protector de pantalla para Kindle con reloj,
  calendario, agenda, notas y temporizador Pomodoro.

![Una guía de capítulo integrada junto al texto EPUB original, con un panel privado de Ask AI.](assets/ai-native-reading.png)

*La guía nativa con IA y las preguntas privadas siguen vinculadas al libro original.*

![Una vista privada de estadísticas de lectura con un calendario de actividad y la tendencia del tiempo de lectura.](assets/reading-insights.png)

*Las estadísticas de lectura convierten la lectura activa en un historial privado fácil de interpretar.*

### Stack tecnológico

EPUB Browser utiliza deliberadamente un stack web pequeño con renderizado en el servidor. La
aplicación instalada no incorpora ningún framework SPA ni requiere un entorno de ejecución de Node.js:

| Capa | Tecnología | Función |
| --- | --- | --- |
| Frontend | HTML semántico, CSS, VanillaJS con módulos ES y API del navegador | Una única interfaz adaptable compartida por SSG y Server |
| CLI y Server | Python 3.9+, Starlette, Uvicorn | Comandos de conversión, páginas autenticadas, API y trabajo en segundo plano |
| Datos | SQLite y cachés de contenido JSON reconstruibles | El estado de los usuarios permanece separado del contenido EPUB/PDF derivado |
| Formatos de libro | lxml, pypdf, pypdfium2, PDF.js | Análisis y saneamiento unificados de EPUB, con prioridad al modo estricto y recuperación en caso de error; metadatos y portadas de PDF; renderizado local en el navegador |
| Funcionamiento sin conexión y recursos | Service Worker, recursos inmutables con hash, dependencias integradas con versiones fijadas | Entrega autocontenida sin CDN en tiempo de ejecución |
| Distribución | PyPI, Docker, alojamiento estático convencional | El mismo código se distribuye como SSG o como Server persistente |
| IA opcional | API compatibles con OpenAI con Markdown, KaTeX y Mermaid renderizados localmente | Capas de aprendizaje EPUB solo en modo Server |

Los mantenedores solo utilizan Node.js para las pruebas en el navegador; no forma parte del
entorno de ejecución de producción del lector.

### Elegir SSG o Server

El mismo procesamiento de fuentes y las mismas plantillas de página sustentan dos modos de despliegue
explícitos. Elige según dónde deban residir los datos de lectura, no según el formato del libro:

| Función | `ssg` | `server` |
| --- | --- | --- |
| EPUB y PDF | Sí | Sí |
| Entrega | Publicación atómica de HTML y recursos estáticos para Pages, almacenamiento de objetos o Nginx | Páginas dinámicas autenticadas respaldadas por una caché de contenido reemplazable |
| Cuentas y control de acceso | Ninguno | Cuentas de administrador y miembro, permisos para libros restringidos, sesiones y protección CSRF |
| Inicio de sesión único OIDC | No incluido | Proveedor genérico, vinculación de cuentas existentes y creación opcional de cuentas de miembro |
| Progreso, anotaciones y estantería | Se guardan en el navegador actual | Se sincronizan por cuenta autenticada en SQLite |
| Valoraciones, reseñas y sesiones de lectura | No se generan | Registros privados por cuenta y estadísticas de lectura |
| Actualizaciones de las fuentes | Vuelve a ejecutar `ssg` | Reinicia, vuelve a analizar o usa `--watch` |
| Administración, etiquetas, OpenAPI y WebHooks | No incluidos | Incluidos |
| Lectura con IA y Ask AI | No incluidos | Disponibles para EPUB cuando se configuran y autorizan explícitamente; ocultos para PDF |
| Base de datos en tiempo de ejecución | Ninguna | Obligatoria para el modo persistente |
| Uso recomendado | Alojamiento público o estático, paquetes sin conexión, publicación personal sencilla | Una biblioteca privada, varios dispositivos o lectores, automatización y acceso gestionado |

Usa `ssg` cuando el resultado deba consistir en archivos estáticos normales. Usa `server` cuando los lectores necesiten cuentas, datos entre dispositivos, control de acceso o conciliación automática de las fuentes.

### Demostraciones en vivo

- **Modo SSG**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Modo Server**: [epub.yuhan.tech](https://epub.yuhan.tech/) — inicia sesión con el usuario `demo` y la contraseña `demo`.

### Lectura nativa con IA (solo Server)

Para los libros EPUB, el modo Server puede añadir guías de capítulos, explicaciones con referencias
al texto, mapas mentales, preguntas de reflexión y un panel privado de Ask AI sin alejar al lector del
texto original. Los resultados siguen sujetos a los permisos del libro; cada miembro debe recibir
autorización explícita y SSG no contiene ningún control, tarea, dato de cuenta ni configuración de
proveedor de IA. Los PDF ocultan deliberadamente la lectura con IA y Ask AI.

Consulta la [guía de lectura nativa con IA](../ai-native-reading.md) para conocer el modelo de
interacción completo y las [notas sobre los renderizadores locales de texto enriquecido](../third-party-ai-renderers.md)
para entender los límites de renderizado y seguridad de red.

### Modo mínimo para Kindle

Los Kindle antiguos con tinta electrónica (y cualquier navegador con recursos limitados) disponen de
una interfaz de lectura mínima y sin dependencias. Actívala con `--kindle`:

- SSG: `epub-browser ssg --kindle -o output/ SOURCE...`
- Server: `epub-browser server --kindle --server-dir data SOURCE...`

Cada libro EPUB (los PDF quedan excluidos) incorpora tres páginas adicionales:

- la estantería mínima `/kindle-library.html`
- la página del libro `/book/<id>/kindle.html`
- la página del capítulo `/book/<id>/kindle_chapter_N.html`

Estas páginas están optimizadas para tinta electrónica: marcado mínimo, temas aplicados solo con CSS,
scripts compatibles con ES5, sin Service Worker y sin framework. Puedes leer sin JavaScript; el cambio
de tema (Claro / Sepia / Oscuro), el tamaño de fuente (A- / A+) y la localización de la interfaz usan
ligeros scripts en línea añadidos sobre el HTML básico.

Todas las páginas ofrecen controles de tema y fuente (en el encabezado y de nuevo en el pie del
capítulo), navegación por el índice, capítulo anterior y siguiente, y un enlace «Seguir leyendo» que
reanuda desde el progreso guardado.

El progreso de lectura varía según el modo:

- **SSG:** el progreso se guarda en las cookies del navegador actual, de forma local y sin cuenta.
- **Server:** el progreso y las señales de actividad de lectura se sincronizan en SQLite para cada
  cuenta que ha iniciado sesión. Las interfaces para Kindle se limitan a la lectura y a comunicar el
  progreso: registran el capítulo actual y envían señales de actividad, muestran una estantería de
  solo lectura y nunca exponen estadísticas ni gestión de contenido.

El control de acceso se aplica en todas las interfaces para Kindle. En los libros de visibilidad
restringida, las páginas del libro y del capítulo y la API de progreso devuelven 403 a los usuarios
no autorizados; en la estantería mínima, estos libros se omiten.

Los navegadores compatibles (con UA que contiene `Kindle/`, `Arora/`, etc.) se redirigen
automáticamente del lector completo a las páginas mínimas; las URL anteriores también funcionan
directamente. Así, el modo mínimo sirve como alternativa para dispositivos de baja potencia o con
JavaScript limitado.

## Primeros pasos

### Elegir una instalación

EPUB Browser admite dos vías de instalación. Ambas aceptan uno o varios archivos `.epub` o `.pdf`,
directorios anidados o un directorio de biblioteca con estructura de Calibre.

| Instalación | Uso | Requisito del host |
| --- | --- | --- |
| PyPI | Modo SSG o Server | Python 3.9 o posterior |
| Docker | Modo Server persistente | Docker Engine; Python está incluido en la imagen |

#### PyPI (SSG o Server)

Instala la aplicación de línea de comandos:

```bash
pip install epub-browser
```

Muestra la referencia de comandos específica de cada modo:

```bash
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

#### Docker (Server)

La imagen publicada [`dfface/epub-browser`](https://hub.docker.com/r/dfface/epub-browser)
ejecuta el modo Server y no requiere Python en el host:

```bash
docker pull dfface/epub-browser:latest
```

Usa `latest` para evaluar la versión actual; fija una etiqueta de versión numerada para un despliegue
de producción reproducible. Consulta [Docker](#docker) para ver los montajes obligatorios de libros y
estado, un inicio rápido con Compose, la configuración inicial y recomendaciones de red.

### Inicio rápido

#### Generar un sitio estático

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

Sirve `dist/` mediante HTTP. No se admite abrir las páginas generadas directamente con `file://`, porque el almacenamiento del navegador, los módulos, los manifiestos y los Service Workers requieren un origen HTTP.

Para un sitio alojado bajo un prefijo de URL, define la ruta pública por separado del destino en el sistema de archivos:

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist \
  --base-path /my-repository/
```

`--base-path` cambia las URL generadas, no el lugar donde se escriben los archivos. Con `/my-repository/`, los enlaces, iconos, manifiestos, metadatos de libros y entradas del Service Worker usan ese prefijo, mientras que los archivos permanecen directamente dentro de `dist/`.

#### Ejecutar una biblioteca Server persistente

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

Abre `http://127.0.0.1:8000/`. En el primer acceso, EPUB Browser te pedirá que crees el administrador inicial. La biblioteca no se analiza ni se expone hasta que finaliza esta configuración única.

Si elegiste Docker, omite el comando de Python anterior y continúa con el
[inicio rápido de Docker Compose](#docker-compose).

## Formatos y lectura

### Fuentes e identidad estable de los libros

Cada `SOURCE` posicional puede ser un archivo EPUB, un archivo PDF o un directorio.
Los directorios se recorren recursivamente. Se pueden pasar varias fuentes a un mismo comando:

```bash
epub-browser server book.epub /srv/library /srv/periodicals \
  --server-dir /srv/epub-browser \
  --watch
```

Cada libro recibe un `book_id` estable, también expuesto como `book_hash` en las URL generadas y los datos del navegador. El valor predeterminado general de la CLI es:

```bash
--book-id-storage sidecar
```

El modo sidecar escribe un archivo de identidad visible junto a la fuente, como `BOOK.epub.epub-browser.json` o `BOOK.pdf.epub-browser.json`, y deja intactos los bytes de la fuente. El sidecar contiene el ID estable y una huella SHA-256 verificada de la fuente.

Para colocar el ID en los metadatos OPF del EPUB o en el diccionario de información del documento PDF, selecciona el almacenamiento integrado para toda la invocación:

```bash
--book-id-storage embedded
```

El modo integrado puede reconstruir el ZIP del EPUB o añadir una actualización de metadatos al PDF antes de la conversión. Si no es posible actualizar el PDF y su fuente no ha cambiado, EPUB Browser guarda el mismo ID en un sidecar adyacente. Esto incluye PDF firmados, cifrados y de solo lectura. EPUB Browser se detiene cuando los ID no coinciden, varias fuentes activas duplican un ID, un soporte no es válido o no se puede escribir en un soporte obligatorio.

Al migrar entre modos de almacenamiento, EPUB Browser copia el ID existente en el soporte seleccionado y conserva el otro soporte válido. Un ID integrado existente de la v2.0.4 se copia en el sidecar predeterminado sin reescribir el EPUB. Tanto SSG como Server entregan una copia byte por byte de la fuente PDF después de cualquier actualización de metadatos.

### PDF: una página, un capítulo

Ambos modos de despliegue admiten PDF. El lector trata cada página del PDF como un capítulo normal de
EPUB Browser, de modo que la página del libro, la navegación entre capítulos, el índice, la paginación,
la lectura continua, el progreso, las sesiones de lectura, las anotaciones, el Diccionario y la
Enciclopedia existentes siguen siendo la única interfaz y el único modelo de datos compartidos:

| Concepto de PDF | SSG | Server |
| --- | --- | --- |
| URL de la página 1 | `chapter_0.html` | `/book/<book-id>/chapter_0.html` |
| URL de la página N | `chapter_{N-1}.html` | `/book/<book-id>/chapter_{N-1}.html` |
| Etiquetas de página e índice | Generados localmente; aparecen todas las páginas | Generados a partir de la caché de metadatos del PDF; aparecen todas las páginas |
| Esquema integrado | Un marcador en la entrada del índice de su página de destino | El mismo marcador, sin eliminar ni reordenar las entradas de página |
| Desplazamiento y paginación/paso de página | Estructuras de capítulo estáticas y PDF.js local | Estructuras de capítulo dinámicas compartidas y PDF.js local |
| Resaltados, notas, Diccionario y Enciclopedia | Componentes compartidos locales del navegador cuando existe una capa de texto | Componentes compartidos autenticados cuando existe una capa de texto |
| Bytes del PDF original | Un `document.pdf` en la salida estática del libro | Ruta exclusiva para sesiones, con soporte de rangos, para el documento en caché |

Los números de página empiezan en uno en la etiqueta visible y en PDF.js; los índices de capítulo
empiezan en cero en las URL, el estado, las API y SQLite. Por tanto, la página 1 de un PDF siempre es
`chapter_0.html`. El índice normalizado conserva una entrada `Page N` para cada página; los títulos
del esquema integrado en el PDF se añaden como marcadores de esquema a su entrada de destino, incluidos
varios marcadores en una misma página.

SSG escribe un único `document.pdf` y una estructura `chapter_<index>.html` por página. La salida SSG
no contiene scripts de sesión, llamadas a `/api/*`, datos de anotaciones sincronizados ni
dependencias del Server. El Server guarda la fuente completa e idéntica byte por byte como
`book/<book-id>/pdf/document.pdf` y nunca la divide ni la reescribe. El Server renderiza dinámicamente
las mismas estructuras de capítulo a partir de los metadatos del PDF; si la fuente cambia, invalida y
actualiza por completo la caché del PDF (documento, metadatos y portada derivada) en lugar de mezclar
páginas antiguas y nuevas.

El endpoint del documento original del Server es exclusivo para sesiones:
`GET`/`HEAD /api/books/<book-id>/document`. Comprueba la autenticación, la visibilidad del libro, el
formato PDF y las huellas de la fuente y la caché; después admite respuestas limitadas a un único
rango de bytes con `ETag`, `Accept-Ranges`, caché privada, `nosniff` y disposición de PDF en línea.
No expone una ruta absoluta, no está disponible para la autenticación con PAT y no forma parte de la interfaz
PAT/OpenAPI. SSG solo tiene su `document.pdf` local y ninguna API de documento original.

Los PDF con una capa de texto utilizable por PDF.js reutilizan exactamente el mismo menú emergente de
selección y componente de anotaciones para Resaltado y Nota, además del Diccionario y la Enciclopedia.
El almacenamiento, la propiedad, la exportación, el listado y los enlaces profundos de las anotaciones
siguen siendo compartidos; no existe una tabla de anotaciones ni una interfaz de ajustes específica de
PDF. Los PDF escaneados o compuestos solo por imágenes siguen pudiendo leerse, pero, cuando no hay
una capa de texto utilizable, se indica explícitamente que las funciones basadas en la selección
(Resaltado, Nota, Diccionario, Enciclopedia y búsqueda en el documento) no están disponibles. Una
selección que abarque varias páginas aún puede copiarse, mientras que las acciones de anotación y
consulta muestran el mensaje localizado de función no admitida; la selección dentro de una página
sigue funcionando.

PDF.js no es una segunda interfaz de visor. Antes de compilar o publicar, descarga y verifica los
recursos de terceros bloqueados:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
```

Después, la aplicación sirve en tiempo de ejecución los recursos locales con hash del módulo y el
worker de PDF.js; nunca los descarga de una CDN. Los visores emergentes de imágenes usan la dependencia
bloqueada GLightbox; Fancyapps/Fancybox no es una dependencia en tiempo de ejecución ni se redistribuye.
Consulta [third_party/README.md](../../third_party/README.md) para conocer el flujo de trabajo de
recursos bloqueados y versiones.

## Despliegue

### SSG

SSG crea una instantánea completa en un directorio de preparación situado junto al destino, la valida y después sustituye el destino. Si falla alguna conversión, el destino anterior permanece intacto. La salida generada no contiene bases de datos del Server, estado de migración, páginas de cuenta ni metadatos de caché en tiempo de ejecución.

El comportamiento de SSG es deliberadamente local y sin cuentas:

- El progreso de lectura y las anotaciones usan el almacenamiento del navegador en el origen actual.
- La estantería admite importación y exportación local de JSON; no tiene acción de sincronización en la nube.
- El inicio de sesión, la configuración de cuenta, las API del Server y los controles que dependen del usuario no están incluidos.
- El destino siempre es el almacenamiento local del navegador y no se ofrece como un ajuste.
- La salida estática incluye el Service Worker necesario para que los recursos funcionen sin conexión.

Todos los JavaScript, CSS, fuentes e iconos necesarios de la aplicación se incluyen en la salida. Consulta [Aplicación autocontenida y comportamiento de red](#aplicación-autocontenida-y-comportamiento-de-red) para conocer la única solicitud de red opcional.

### Server

#### Configuración inicial, cuentas y permisos

En un directorio de estado persistente nuevo, las páginas normales redirigen a `/setup`. Las API, los flujos de eventos, los recursos generados y los libros devuelven una respuesta que indica que la configuración es obligatoria hasta que se crea el administrador inicial. Completa la configuración mediante loopback u otra ruta privada de confianza antes de exponer el puerto: el primer envío de configuración correcto asigna la cuenta de administrador a quien lo envía.

Después de la configuración:

- El registro público está cerrado. Los administradores crean y gestionan usuarios.
- Las cuentas tienen el rol `administrator` o `member`.
- Los libros normales son visibles para todas las cuentas autenticadas.
- Los libros restringidos solo son visibles para los administradores y los usuarios seleccionados explícitamente.
- Cada usuario es propietario de su estantería, progreso, anotaciones y sesiones activas.
- Los usuarios pueden cambiar su contraseña y revocar sus sesiones.
- Los administradores pueden gestionar usuarios, roles, contraseñas, sesiones y permisos de libros.
- Las sesiones usan una cookie HttpOnly, protección CSRF y una vigencia de 30 días que se renueva con la actividad.

#### Inicio de sesión único OIDC y vinculación de cuentas

El modo Server puede utilizar un proveedor genérico de OpenID Connect (OIDC), incluidos Authelia,
Keycloak, Authentik y servicios compatibles. En **Administración → Inicio de sesión con OIDC**,
introduce el nombre del proveedor que verán los lectores, la URL del emisor, el ID de cliente, el
secreto de cliente, la URI de redirección exacta, los ámbitos y la reclamación de nombre de usuario.
EPUB Browser utiliza descubrimiento y el flujo de código de autorización con PKCE S256, valida el token
de ID firmado e identifica una cuenta externa únicamente mediante `(issuer, sub)`; las reclamaciones
de correo electrónico y nombre de usuario solo sirven como sugerencias para mostrar datos o crear
cuentas, nunca como claves de identidad.

Registra exactamente esta URL de callback en el proveedor, incluidos el esquema y el host:

```text
https://reader.example.com/auth/oidc/callback
```

Los usuarios existentes pueden iniciar sesión localmente y vincular el proveedor desde la
configuración de la cuenta. A una identidad externa desconocida se le pedirá una sola vez un nombre de
usuario y una contraseña locales existentes. Si activas la creación automática opcional, se crea una
cuenta de miembro sin contraseña; nunca importa un rol de administrador. Deja que los usuarios
existentes vinculen primero sus cuentas: activar la creación automática demasiado pronto puede generar **cuentas locales
duplicadas**. El inicio de sesión con contraseña del **administrador local** siempre permanece
disponible, aunque se desactive el inicio de sesión con contraseña de los miembros locales. Prueba y
protege esa credencial de recuperación. No se cierra la sesión en el proveedor ni se guardan
sus tokens de acceso o actualización.

Para Authelia, configura un cliente confidencial en su sección de proveedor OIDC. El siguiente extracto
usa valores deliberadamente falsos y da por supuesto que las claves y políticas de proveedor que
requiere Authelia ya están configuradas. Guarda en Authelia un hash de un secreto de cliente aleatorio
y robusto; después introduce una sola vez el secreto sin cifrar correspondiente en EPUB Browser:

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

En EPUB Browser, usa el emisor `https://auth.example.com`, el ID de cliente `epub-browser`, los ámbitos
`openid profile email` y la reclamación de nombre de usuario `preferred_username`. Al guardar se
realizan el descubrimiento y la validación de capacidades en tiempo real; si fallan, la configuración anterior
permanece activa.

#### Configurar y gestionar la lectura con IA

Los administradores configuran la lectura con IA en **Administración**, inmediatamente después de la
gestión de usuarios y antes de la gestión de libros. La página guarda en la base de datos SQLite del
Server una URL base compatible con OpenAI, la clave de API, el modelo, el tiempo de espera, el
presupuesto de contexto, el límite de concurrencia y el límite diario predeterminado de llamadas al
proveedor. La IA empieza desactivada para los miembros; un administrador debe conceder acceso a cada
miembro y puede establecer un límite diario individual (`0` significa ilimitado).

Las capas de aprendizaje de los capítulos y las reseñas de cada libro se comparten para cada idioma
compatible, mientras que las conversaciones de seguimiento permanecen privadas para cada cuenta. Los
resultados, el estado de las tareas, las etiquetas personalizadas, la clasificación de lectura del libro
y las conversaciones privadas de seguimiento se guardan en SQLite. Los resultados antiguos siguen disponibles después
de cambiar la configuración del modelo hasta que un administrador los regenere explícitamente.

Cuando un lector solicita una guía de IA o formula una pregunta, el texto EPUB seleccionado y el
contexto comprimido de la conversación se envían al proveedor externo configurado. No actives la
función a menos que los lectores tengan permiso para enviar ese contenido al proveedor. La clave de API
nunca se devuelve a un navegador ni se expone mediante una API; protege el directorio de estado del
Server en consecuencia.

Para un primer inicio desatendido, proporciona un nombre de usuario y un archivo de contraseña:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --admin-username admin \
  --admin-password-file /run/secrets/epub-browser-admin-password \
  --no-browser
```

El archivo de contraseña debe tener permisos `0600`. EPUB Browser elimina un salto de línea final, guarda un hash Argon2id y nunca imprime el secreto. Una configuración incompleta, un archivo vacío o un archivo ilegible detienen el inicio. Una vez completada la configuración, los inicios posteriores no leen el secreto de arranque.

Los equivalentes de entorno son `EPUB_BROWSER_ADMIN_USERNAME` y `EPUB_BROWSER_ADMIN_PASSWORD_FILE`. `EPUB_BROWSER_ADMIN_PASSWORD` es una alternativa en texto sin cifrar que solo se usa cuando no hay configurado ningún archivo de contraseña. Una ruta de archivo de contraseña indicada por CLI tiene prioridad sobre las fuentes de contraseña del entorno.

#### Apertura del navegador y registro

De forma predeterminada, el Server intenta abrir el navegador predeterminado del sistema operativo después de que el servidor HTTP empiece a escuchar. `--no-browser` impide esa apertura local. **No desactiva la interfaz web ni el acceso mediante navegador**; solo suprime la llamada local `webbrowser.open(...)`. Utilízalo con Docker, systemd, sesiones SSH, máquinas sin interfaz gráfica y scripts.

De forma predeterminada (`--log-level error`), la CLI solo emite errores para que los mensajes o avisos rutinarios no interrumpan las visualizaciones de progreso del terminal. Un terminal interactivo muestra una vez la URL de escucha; las ejecuciones no interactivas en Docker y en servicios permanecen silenciosas. Usa `--log-level warning` para incluir avisos, `--log-level info` para el registro operativo y de acceso HTTP, o `--log-level debug` para obtener el máximo detalle. `--log` sigue siendo un alias de compatibilidad de `--log-level info`.

Los análisis iniciales y los que se activan con la supervisión de fuentes aparecen en la interfaz web en lugar de `tqdm` en el terminal. Si el análisis termina correctamente, el resumen se cierra automáticamente; los fallos permanecen visibles hasta que se descartan. Con `--watch`, corregir o reemplazar una fuente inicia otro análisis sin que tengas que reintentarlo manualmente.

#### Estado persistente y efímero

El modo Server persistente requiere `--server-dir`. Para una ejecución desechable, usa `--ephemeral` en su lugar:

```bash
epub-browser server book.epub --ephemeral
```

El estado efímero se elimina al cerrar. Como su base de datos es nueva en cada ejecución, la configuración también se repite, salvo que se proporcionen credenciales de arranque desatendido.

Estructura persistente:

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

Solo `data/` es autoritativo. `cache/` puede eliminarse y se reconstruirá. Conserva `data/` durante las actualizaciones y la sustitución de contenedores. Un bloqueo del sistema operativo controla la exclusividad; `.server.lock` puede permanecer tras un cierre normal como metadato de diagnóstico.

Guarda el archivo persistente `data/epub-browser.db` en un sistema de archivos local. Los sistemas de archivos compartidos o de red no son compatibles con la concurrencia de WAL. Las copias de seguridad verificadas permanecen en `data/backups/` e incluyen todos los datos WAL confirmados.

#### LAN y proxy inverso

De forma predeterminada, el Server escucha en `127.0.0.1:8000`. Para una LAN de confianza:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --port 8080 \
  --no-browser
```

No expongas el servidor HTTP integrado directamente a Internet. Termina TLS en un proxy inverso, aplica controles de red y activa las cookies seguras.

Para registrar las IP reales de los clientes en las sesiones activas y los límites de frecuencia de los inicios de sesión detrás de un proxy inverso, configura la **red del proxy directamente conectado** (no los rangos de clientes públicos):

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

Repite `--trusted-proxy-cidr` una vez por cada dirección o red de proxy directo. Solo se acepta `X-Forwarded-For` cuando el extremo directo de la conexión pertenece a uno de estos CIDR; en el resto de los casos, se registra únicamente la dirección de ese extremo. El procesamiento de direcciones reenviadas de Uvicorn está desactivado, por lo que `Forwarded` y `FORWARDED_ALLOW_IPS` no pueden ampliar este límite de confianza. Usa `--cookie-secure` solo cuando el navegador acceda al servicio mediante HTTPS.

### Docker

La imagen ejecuta el modo Server persistente con estos valores predeterminados:

- `/app/Library` como fuente
- `/app/EpubBrowserFiles` como estado persistente
- `--watch`
- `--no-browser`
- `--host 0.0.0.0 --port 80`
- `--book-id-storage embedded`

Como la identidad integrada puede actualizar archivos EPUB o PDF, monta la biblioteca con permisos de lectura y escritura. Monta el estado del Server con permisos de lectura y escritura y consérvalo al sustituir el contenedor:

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  dfface/epub-browser:latest
```

Visita `http://127.0.0.1:8080/setup` antes de cambiar la publicación del puerto o las reglas del proxy.

#### Docker Compose

El repositorio incluye un [docker-compose.yml](../../docker-compose.yml) para quienes prefieren Compose. Desde una copia del repositorio, crea `Library/`, coloca allí los libros EPUB o PDF y ejecuta:

```bash
docker compose up -d --build
```

Solo publica `127.0.0.1:8080`, conserva los libros EPUB/PDF de origen en `./Library` y mantiene el estado del Server en `./EpubBrowserFiles`. El `command` completo del Server se muestra deliberadamente en el archivo, de modo que se pueden añadir opciones específicas del despliegue sin sustituir un valor predeterminado implícito de la imagen. Completa la configuración única en `http://127.0.0.1:8080/setup`. Para el acceso remoto, mantén la publicación limitada a la interfaz de loopback y coloca delante un proxy inverso TLS con autenticación.

Para una configuración desatendida:

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

Después del primer inicio correcto, se puede retirar el montaje del secreto de un solo uso. Una biblioteca de solo lectura solo funciona cuando todos los EPUB ya contienen un ID integrado válido y coincidente. Los sidecars existentes se conservan cuando sus ID se integran.

Monta `/app/SyncData:ro` solo mientras importas el JSON de una estantería antigua:

```bash
-v /path/to/legacy-sync:/app/SyncData:ro
```

El puerto de loopback publicado en los ejemplos hace que el contenedor solo sea accesible desde el host. Para el acceso remoto, usa un proxy inverso TLS, configura el CIDR real de su red de contenedores y añade `--cookie-secure`.

## Referencia y operaciones

### Referencia de comandos

#### `epub-browser ssg SOURCE [SOURCE ...]`

| Opción | Significado |
| --- | --- |
| `--output-dir DIR`, `-o DIR` | Destino obligatorio de la instantánea estática atómica. |
| `--base-path PATH` | Prefijo de URL pública; valor predeterminado `/`. Debe empezar y terminar con `/`. |
| `--book-id-storage sidecar\|embedded` | Soporte de identidad estable para cada fuente seleccionada; valor predeterminado `sidecar`. |
| `--kindle` | Genera páginas mínimas sin dependencias para Kindle antiguos con tinta electrónica y redirige a ellas los navegadores Kindle WebKit; desactivado de forma predeterminada. |
| `--log` | Alias de compatibilidad de `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Nivel de detalle del registro operativo; valor predeterminado `error`, que silencia la salida de conversión rutinaria y los avisos. |

#### `epub-browser server SOURCE [SOURCE ...]`

Se requiere exactamente una de las opciones `--server-dir` y `--ephemeral`.

| Opción | Significado |
| --- | --- |
| `--server-dir DIR` | Datos autoritativos persistentes y raíz de caché reemplazable. |
| `--ephemeral` | Usa estado desechable; es mutuamente excluyente con `--server-dir`. |
| `--watch`, `-w` | Vigila las fuentes y concilia adiciones, actualizaciones, movimientos y eliminaciones. |
| `--host ADDRESS` | Dirección de escucha; valor predeterminado `127.0.0.1`. |
| `--port PORT`, `-p PORT` | Puerto de escucha; valor predeterminado `8000`. |
| `--no-browser` | No abre el navegador predeterminado local. La interfaz web sigue disponible. |
| `--log` | Alias de compatibilidad de `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Nivel de detalle del registro operativo; valor predeterminado `error`. Los registros de acceso HTTP se activan con `info` y `debug`. |
| `--legacy-sync-dir DIR` | Lee el JSON de una estantería antigua durante la migración de inicio. |
| `--book-id-storage sidecar\|embedded` | Soporte de identidad estable para cada fuente seleccionada; valor predeterminado `sidecar`. |
| `--admin-username NAME` | Administrador inicial desatendido; alternativa `EPUB_BROWSER_ADMIN_USERNAME`. |
| `--admin-password-file FILE` | Archivo de secreto inicial preferido; alternativa `EPUB_BROWSER_ADMIN_PASSWORD_FILE` y después `EPUB_BROWSER_ADMIN_PASSWORD` cuando no se define ningún archivo. |
| `--trusted-proxy-cidr CIDR` | Define una red de proxys directos de confianza; la opción puede repetirse para analizar de forma segura la IP del cliente de `X-Forwarded-For`. |
| `--cookie-secure` | Envía la cookie de sesión solo mediante HTTPS de cara al navegador. |
| `--kindle` | Sirve páginas mínimas sin dependencias para Kindle antiguos con tinta electrónica y redirige a ellas los navegadores Kindle WebKit; desactivado de forma predeterminada. |

#### Sintaxis de la v1 anterior

La sintaxis anterior se admite en toda la rama de versiones v2:

| Comando de v1 | Equivalencia en v2 |
| --- | --- |
| `epub-browser BOOKS` | `epub-browser server BOOKS --ephemeral` |
| `epub-browser BOOKS --output-dir STATE` | `epub-browser server BOOKS --server-dir STATE` |
| `epub-browser BOOKS --no-server --output-dir DIST` | `epub-browser ssg BOOKS --output-dir DIST` |
| `--sync-dir DIR` | `server --legacy-sync-dir DIR` |

La opción `--keep-files`, exclusiva de la versión anterior, conserva un directorio temporal del Server. Los directorios persistentes del Server ya son permanentes. Con `--log`, el adaptador de compatibilidad imprime el comando v2 equivalente; en caso contrario, permanece silencioso.

### Datos de lectura y disponibilidad de funciones

- Descubrimiento recursivo de EPUB/PDF y bibliotecas de Calibre, etiquetas de metadatos, búsqueda y búsqueda por pinyin
- Interfaces adaptables de biblioteca, detalles del libro y lectura de capítulos
- Desplazamiento, paso de página, lectura continua, ancho de contenido ajustable, fuentes, CSS personalizado, temas y modo de lectura sin distracciones
- Resaltados, notas, exploración de anotaciones, grupos de estanterías anidados, etiquetas e importación/exportación de JSON
- Localización de la interfaz en inglés, chino simplificado, chino tradicional, coreano, japonés,
  español, alemán, francés, ruso, italiano, portugués de Brasil, árabe, indonesio, hindi, vietnamita,
  tailandés y malayo
- Comportamiento adecuado para lectores electrónicos con navegadores Kindle/Silk; las funciones que exigen mucho al navegador pueden quedar reducidas

| Datos | SSG | Server |
| --- | --- | --- |
| Progreso de lectura | Local en el navegador | Registro SQLite del usuario autenticado |
| Resaltados y notas | Locales en el navegador | Registros SQLite del usuario autenticado |
| Valoraciones, reseñas e historial privado de sesiones de lectura | No presentes | Registros SQLite del usuario autenticado |
| Estantería | Local en el navegador; importación/exportación | Documento en la nube con versiones del usuario autenticado; guardado automático |
| Cuentas y sesiones | No presentes | SQLite en `<server-dir>/data` |
| Permisos de libros | No presentes | SQLite en `<server-dir>/data` |

El Server no ofrece un selector de almacenamiento local o en la nube: los datos de lectura de los usuarios autenticados siempre se guardan en el Server. SSG nunca genera el historial privado detallado de sesiones de lectura. SSG nunca consulta las API del Server y siempre utiliza el almacenamiento local del origen actual del navegador.

### Aplicación autocontenida y comportamiento de red

La aplicación incluye todo lo necesario para la lectura: los JavaScript, CSS, fuentes, iconos, manifiestos y recursos EPUB convertidos necesarios se sirven localmente. No hay dependencias de CDN en tiempo de ejecución. Bloquear el acceso saliente a Internet no impide la configuración, el inicio de sesión, la exploración, la lectura, las anotaciones, el progreso, el uso de la estantería, la administración ni la conversión de fuentes.

El pie de página puede hacer una solicitud opcional a la API de GitHub Releases para descubrir una versión más reciente de EPUB Browser. Un fallo, un bloqueo o el uso sin conexión solo suprimen ese aviso de actualización.

SSG publica un Service Worker estático. El Server desactiva y retira deliberadamente el Service Worker de todo el origen para que una cuenta no pueda recibir contenido protegido de otra cuenta almacenado en caché.

### API del Server y WebHooks

Las cuentas del Server pueden crear tokens de acceso personal con ámbitos en la configuración de la cuenta. Los clientes externos usan `Authorization: Bearer <PAT>` con la API versionada `/api/v1/*`; las cookies del navegador no autentican estas rutas. La API cubre los libros visibles y el contenido de sus capítulos, la estantería, el progreso, las anotaciones y las reseñas del propietario del token, además de datos de solo lectura entre usuarios para los PAT de administrador con `admin:data:read`.

El documento OpenAPI 3.1 está disponible en `/openapi.json`; los usuarios que han iniciado sesión pueden consultar la referencia local en `/api-docs`. Por ejemplo: `curl -H 'Authorization: Bearer …' https://reader.example/api/v1/books`. Los detalles de un capítulo devuelven HTML saneado de forma predeterminada y texto sin formato con `?format=text`.

Los endpoints de listas devuelven `items` y `next_cursor`. El `limit` predeterminado es 24 y el máximo es 100. Pasa `next_cursor` como `cursor` con los mismos filtros para obtener la página siguiente. Un cursor nulo marca la última página. Por ejemplo, usa `/api/v1/me/annotations?book_id=BOOK_ID&chapter_index=0&fields=id,text,note` para recuperar campos seleccionados de anotaciones de un capítulo EPUB o una página PDF. Los filtros de consulta y los campos admitidos figuran en el documento OpenAPI.

El vocabulario usa el mismo formato de lista de forma predeterminada. Los clientes que utilizan la respuesta `words` anterior pueden enviar `page=1` o `page_size` para seleccionar el formato de paginación anterior.

Los administradores gestionan los endpoints de WebHook en Administración. Los secretos solo se muestran al crearlos o rotarlos. Las entregas están firmadas, se almacenan de forma duradera y se reintentan ante respuestas que no sean 2xx; los eventos de reseña de libros contienen ID y marcas de tiempo de acciones, pero nunca valoraciones ni texto de reseñas.

### Seguridad de los datos y migración

Antes de actualizar instalaciones persistentes del Server, haz una copia de seguridad de los libros EPUB/PDF de origen y de `<server-dir>/data`. Conserva el mismo volumen de estado persistente al sustituir el contenedor.

La migración de inicio es automática y segura ante reinicios. Verifica las bases de datos antiguas, crea una copia de seguridad, actualiza una copia, importa los datos elegibles de estanterías, progreso y anotaciones antiguos en el administrador inicial pendiente, y retira únicamente los artefactos públicos antiguos reemplazables después de puntos de control correctos. Las solicitudes normales nunca analizan los directorios de sincronización antiguos. Las bases de datos dañadas, los hashes de contraseña no válidos, las bases de datos antiguas ambiguas y los ID en conflicto detienen el arranque por seguridad, sin hacer suposiciones ni sobrescribir datos.

Un `epub-browser.db` o `annotations.db` migrado en la raíz se conserva como copia de recuperación sensible y no autoritativa; `data/epub-browser.db` es autoritativo y las solicitudes del Server no utilizan el archivo raíz conservado. Mantén privada la copia de recuperación. Elimínala manualmente solo con el Server detenido, después de verificar la base de datos autoritativa y la copia de seguridad registrada, y únicamente cuando ya no necesites revertir a v1. EPUB Browser nunca la elimina automáticamente.

Si existen tanto `epub-browser.db` como `annotations.db` en una raíz antigua, el inicio se detiene y los deja intactos. Consulta [Migración a v2](../migration-v2.md) para conocer las copias de seguridad, la reversión, la reconstrucción de cachés y la recuperación de conflictos.

### Solución de problemas

#### El comando se inició, pero no se abrió ningún navegador

Elimina `--no-browser` cuando ejecutes el comando en una máquina local con interfaz gráfica, o abre manualmente la URL impresa o la dirección de escucha. En Docker, systemd, SSH y sesiones no interactivas, es normal que tengas que abrir la URL tú mismo.

#### La CLI parece silenciosa

El funcionamiento silencioso es intencionado sin `--log`, especialmente en entornos no interactivos. Añade `--log` para obtener detalles operativos y de acceso. El progreso del análisis del Server se muestra en la interfaz web.

#### Docker no puede escribir un ID estable

La imagen usa de forma predeterminada la identidad integrada. Monta `/app/Library` con permisos de lectura y escritura o integra previamente ID válidos y coincidentes. Usa un comando personalizado con `--book-id-storage sidecar` solo si prefieres un soporte sidecar en el que se pueda escribir.

#### Un sitio SSG generado tiene enlaces rotos bajo una subruta

Vuelve a generarlo con un `--base-path` normalizado, como `/reader/`, y configura el alojamiento estático para servir la salida con ese mismo prefijo.

#### El Server se niega a iniciarse después de una actualización

Lee el primer error de migración o validación registrado, conserva los datos y los archivos de origen, y consulta [docs/migration-v2.md](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/migration-v2.md). No elimines el directorio autoritativo `data/` para intentar sortear un error.

## Desarrollo y licencia

### Contribuir

Los Issues y Pull Requests son bienvenidos en [dfface/epub-browser](https://github.com/dfface/epub-browser). Un informe útil incluye el comando exacto, el navegador o dispositivo, los pasos de reproducción, los registros pertinentes y el EPUB o PDF cuando pueda compartirse legalmente.

#### Contrato de arquitectura para mantenedores

Lee [AGENTS.md](../../AGENTS.md) antes de modificar el procesamiento de contenido, las plantillas de
página, las cachés, los permisos, los recursos o el comportamiento de despliegue. Define los límites
entre los formatos EPUB y PDF, las responsabilidades de SSG y Server, las revisiones independientes de
caché, los requisitos de i18n en tiempo de ejecución, las comprobaciones de seguridad y la verificación
obligatoria. Los términos compartidos del producto como *capítulo del lector*, *ventana de lectura*, *área
de lectura* y *caché de contenido* se definen en [CONTEXT.md](../../CONTEXT.md).

En resumen: mantén una única interfaz de lector, mantén los datos exclusivos del Server fuera de SSG,
mantén las cachés derivadas de EPUB y PDF separadas de los datos de usuario de SQLite y nunca añadas
una dependencia de CDN en tiempo de ejecución. Un cambio que afecte a una superficie compartida debe
probarse con ambos formatos y ambos modos de despliegue cuando corresponda.

#### Desarrollo desde una copia del repositorio

Los archivos de terceros para el navegador son archivos generados necesarios para compilar, no código fuente del
proyecto, por lo que `epub_browser/assets/vendor/` está ausente deliberadamente de Git. Descarga
explícitamente las versiones bloqueadas exactas antes de desarrollar o compilar y después verifícalas
sin conexión:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
python3 -m unittest tests.test_vendor_assets -v
python3 -m build
```

`fetch` es el único comando anterior que descarga recursos de terceros para el navegador. El archivo de
bloqueo registra tarballs inmutables de npm, hashes de archivo, listas de permitidos y licencias;
`verify`, las pruebas, las compilaciones desde una copia con los recursos descargados y el lector
instalado no descargan recursos para el navegador. El comando aislado estándar `python3 -m build` aún
puede consultar un índice de paquetes de Python para los requisitos de compilación. Para compilar sin
ningún acceso a la red, descarga el árbol de recursos de terceros e instala previamente `build`,
`setuptools` y `wheel` antes de desconectarte; después ejecuta
`PIP_NO_INDEX=1 python3 -m build --no-isolation`. Los wheels, las distribuciones de código fuente, las
imágenes de Docker y los sitios SSG generados contienen los archivos verificados y no tienen ninguna
dependencia de CDN en tiempo de ejecución. Consulta [third_party/README.md](../../third_party/README.md)
para conocer el flujo de trabajo de actualización, publicación y mantenimiento del repositorio.

### Licencia

[MIT](../../License.txt)
