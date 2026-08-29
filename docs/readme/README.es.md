# EPUB Browser

> EPUB y PDF en una biblioteca de lectura privada o como sitio estático autocontenido.

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

**Idiomas de la interfaz (17):** inglés, chino simplificado, chino tradicional, japonés, coreano, español, alemán, francés, ruso, italiano, portugués de Brasil, árabe, indonesio, hindi, vietnamita, tailandés y malayo.

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![Una página PDF en el lector compartido de EPUB Browser.](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser procesa `.epub` y `.pdf` en dos modos con responsabilidades claramente separadas:

| | `ssg` | `server` |
| --- | --- | --- |
| EPUB y PDF | Sí | Sí |
| Despliegue | Hosting estático, Pages, almacenamiento de objetos, Nginx | Servicio privado de lectura persistente |
| Cuentas | Ninguna | Cuentas locales |
| Progreso, anotaciones y estantería | Solo en este navegador | Datos de la cuenta autenticada en SQLite |
| Actualización de fuentes | Ejecutar `ssg` de nuevo | Reiniciar el servicio o usar `--watch` |
| Base de datos en tiempo de ejecución | No | Obligatoria |

PDF es un formato de libro de primera clase: la página 1 se convierte en `chapter_0.html`, todas las páginas aparecen en el índice y PDF.js las representa localmente en la misma biblioteca, ficha, interfaz de lectura, búsqueda y flujo de anotaciones. Las funciones no compatibles, como la lectura con IA para PDF, se ocultan de forma explícita y no se necesita ningún CDN durante la lectura.

Usa `ssg` para publicar archivos estáticos normales. Usa `server` cuando necesites cuentas, datos entre dispositivos, control de acceso a libros o sincronización automática de las fuentes.

## Descripción general

### Por qué elegir EPUB Browser

- **Lectura nativa con IA, anclada al texto:** En modo Server y solo para EPUB, las guías de capítulo, las explicaciones basadas en evidencias, los mapas mentales, las propuestas de reflexión y las conversaciones privadas con Ask AI permanecen junto al texto original, no en un resumen genérico separado.
- **Estadísticas de lectura privadas:** En modo Server, el tiempo de lectura activa, el calendario de actividad, las tendencias, las sesiones y los libros más leídos solo son visibles para la cuenta que ha iniciado sesión.

![Una guía de capítulo con IA junto al texto EPUB original y una conversación privada con Ask AI.](assets/ai-native-reading.png)

*La guía con IA y las preguntas privadas permanecen ancladas al libro original.*

![Estadísticas privadas de lectura con un calendario de actividad y la tendencia del tiempo de lectura.](assets/reading-insights.png)

*Las estadísticas convierten la lectura activa en un historial privado fácil de comprender.*

### Tecnologías

La interfaz usa HTML semántico, CSS y Vanilla JavaScript sin un framework SPA. La CLI y el Server se basan en Python 3.9+, Starlette, Uvicorn y SQLite; pypdf, pypdfium2 y PDF.js procesan los PDF localmente, sin CDN en tiempo de ejecución.

### Demostraciones

- **Modo SSG**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Modo Server**: [epub.yuhan.tech](https://epub.yuhan.tech/) — usuario y contraseña: `demo`.

### Lectura nativa con IA (solo Server)

La lectura con IA crea sobre el texto original una capa de aprendizaje compartida y revisable, no un resumen genérico separado del libro. Incluye una guía antes de leer, una vista general opcional del capítulo, explicaciones vinculadas a citas, notas sobre la función de los párrafos, aclaraciones de vocabulario, una explicación sencilla al final y preguntas para seguir pensando.

Los resultados se generan como tareas en segundo plano, se guardan en SQLite y se comparten entre lectores con acceso al libro. Las conversaciones de seguimiento son privadas para cada cuenta. El administrador debe configurar un proveedor compatible con OpenAI y autorizar a cada miembro. El texto EPUB seleccionado se envía a dicho proveedor, por lo que esta función solo debe habilitarse con el consentimiento del lector. La salida SSG nunca incluye cuentas, controles de IA, tareas ni configuración del proveedor.

## Primeros pasos

### Requisitos e instalación

- Python 3.9 o posterior
- Uno o varios archivos `.epub` o `.pdf`, directorios anidados con libros o una biblioteca con estructura de Calibre

La instalación desde PyPI permite usar los modos SSG y Server:

```bash
pip install epub-browser

# Ayuda completa para cada modo
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

Para un Server persistente con Docker, usa la imagen publicada; el host no necesita Python:

```bash
docker pull dfface/epub-browser:latest
```

### Inicio rápido

#### Generar un sitio estático

```bash
epub-browser ssg /ruta/a/libros \
  --output-dir /ruta/a/dist
```

Publica `dist/` mediante HTTP; no abras las páginas generadas directamente con `file://`. Para desplegar bajo una subruta, añade `--base-path /mi-repositorio/`; esta opción modifica las URL generadas, no el directorio de salida.

#### Ejecutar una biblioteca Server persistente

```bash
epub-browser server /ruta/a/libros \
  --server-dir /ruta/al/estado-de-epub-browser \
  --watch
```

Abre `http://127.0.0.1:8000/`. En la primera visita se crea el administrador inicial; la biblioteca no se analiza ni se publica hasta completar esa configuración. `--no-browser` solo impide que el servicio abra automáticamente el navegador local.

## Datos y operaciones

### Datos, cuentas y límites de acceso

Cada libro tiene un `book_id` estable. Por defecto, `--book-id-storage sidecar` guarda la identidad junto al archivo fuente sin modificar sus bytes. Para EPUB, `--book-id-storage embedded` la escribe en los metadatos OPF y requiere una fuente modificable; para PDF siempre recurre al sidecar adyacente.

En modo Server, `--server-dir` es la ubicación autoritativa para SQLite, cachés y copias de migración. Allí también se guardan cuentas, estanterías, progreso, anotaciones, resultados de IA y tareas. Los administradores gestionan usuarios, roles, sesiones y permisos de libros; los miembros solo pueden usar los libros autorizados y sus propios datos privados. Protege los permisos de este directorio y de sus copias de seguridad.

### Docker, proxy inverso y documentación completa

En contenedores, monta los libros como solo lectura y `--server-dir` en un volumen persistente. Acepta cabeceras de proxy únicamente desde proxies de confianza y usa HTTPS en despliegues públicos.

Para Docker Compose, todas las opciones de CLI, migraciones, LAN, proxy inverso y solución de problemas, consulta el [README completo en inglés](../../README.md) o el [README completo en chino simplificado](README.zh-CN.md). El comportamiento de ambos modos es el mismo en todos los idiomas.

## Desarrollo y licencia

### Contribuir y licencia

Se aceptan Issues y Pull Requests. Consulta [License.txt](../../License.txt) para conocer la licencia.
