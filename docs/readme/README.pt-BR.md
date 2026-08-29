# EPUB Browser

> EPUB e PDF em uma biblioteca de leitura privada ou como site estático autocontido.

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

**Idiomas da interface (17):** inglês, chinês simplificado, chinês tradicional, japonês, coreano, espanhol, alemão, francês, russo, italiano, português do Brasil, árabe, indonésio, hindi, vietnamita, tailandês e malaio.

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![Uma página PDF no leitor compartilhado do EPUB Browser.](../releases/assets/v2.8.0-pdf-reader.png)

O EPUB Browser processa `.epub` e `.pdf` em dois modos com responsabilidades claramente separadas:

| | `ssg` | `server` |
| --- | --- | --- |
| EPUB e PDF | Sim | Sim |
| Implantação | Hospedagem estática, Pages, armazenamento de objetos, Nginx | Serviço privado de leitura persistente |
| Contas | Nenhuma | Contas locais |
| Progresso, anotações e estante | Somente neste navegador | Dados da conta autenticada no SQLite |
| Atualização das fontes | Executar `ssg` novamente | Reiniciar o serviço ou usar `--watch` |
| Banco de dados em execução | Nenhum | Obrigatório |

PDF é um formato de livro de primeira classe: a página 1 se torna `chapter_0.html`, todas as páginas aparecem no sumário e o PDF.js as renderiza localmente na mesma biblioteca, página do livro, interface de leitura, busca e fluxo de anotações. Recursos de PDF não compatíveis, como leitura com IA, são ocultados explicitamente e nenhum CDN é necessário durante a leitura.

Use `ssg` para publicar arquivos estáticos comuns. Use `server` quando precisar de contas, dados entre dispositivos, controle de acesso aos livros ou monitoramento automático das fontes.

## Visão geral

### Por que escolher o EPUB Browser

- **Leitura nativa com IA, ancorada no texto:** no modo Server e somente para
  EPUB, guias de capítulo, explicações baseadas em evidências, mapas mentais,
  perguntas para reflexão e conversas privadas no Ask AI permanecem ao lado do
  texto original, em vez de reduzir o livro a um resumo genérico.
- **Estatísticas de leitura privadas:** no modo Server, acompanhe o tempo de leitura
  ativa, o calendário de atividades, tendências, sessões e os livros mais lidos;
  esses dados ficam visíveis apenas para a conta atual.

![Um guia de capítulo com IA ao lado do texto EPUB original e uma conversa privada no Ask AI.](assets/ai-native-reading.png)

*A orientação por IA e as perguntas privadas permanecem ancoradas no livro original.*

![Estatísticas de leitura privadas com calendário de atividades e tendência do tempo de leitura.](assets/reading-insights.png)

*As estatísticas transformam a leitura ativa em um histórico compreensível e visível apenas para a conta atual.*

### Tecnologias

A interface usa HTML semântico, CSS e Vanilla JavaScript sem framework SPA. A CLI e o Server usam Python 3.9+, Starlette, Uvicorn e SQLite; pypdf, pypdfium2 e PDF.js processam PDFs localmente, sem CDN em tempo de execução.

### Demonstrações

- **Modo SSG**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Modo Server**: [epub.yuhan.tech](https://epub.yuhan.tech/) — usuário e senha: `demo`.

### Leitura nativa com IA (somente Server)

A leitura com IA cria sobre o texto original uma camada de aprendizagem compartilhada e verificável, em vez de colocar um resumo genérico ao lado do livro. Ela inclui um roteiro antes da leitura, uma visão geral opcional do capítulo, explicações ligadas às citações, notas sobre a função dos parágrafos, esclarecimentos de vocabulário, uma explicação simples ao final e perguntas para aprofundamento.

Os resultados são gerados por tarefas em segundo plano, armazenados no SQLite e compartilhados entre leitores com acesso ao livro. As conversas posteriores permanecem privadas em cada conta. O administrador precisa configurar um provedor compatível com OpenAI e autorizar cada membro. O texto EPUB selecionado é enviado a esse provedor; portanto, ative o recurso somente com o consentimento dos leitores. A saída SSG nunca contém contas, controles de IA, tarefas ou configurações do provedor.

## Primeiros passos

### Requisitos e instalação

- Python 3.9 ou mais recente
- Um ou mais arquivos `.epub` ou `.pdf`, diretórios aninhados com livros ou uma biblioteca no estilo Calibre

A instalação pelo PyPI oferece os modos SSG e Server:

```bash
pip install epub-browser

# Ajuda completa de cada modo
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

Para um Server persistente com Docker, use a imagem publicada; o host não precisa de Python:

```bash
docker pull dfface/epub-browser:latest
```

### Início rápido

#### Gerar um site estático

```bash
epub-browser ssg /caminho/para/livros \
  --output-dir /caminho/para/dist
```

Sirva `dist/` por HTTP; não abra as páginas geradas diretamente com `file://`. Para implantar em um subcaminho, adicione `--base-path /meu-repositorio/`; a opção altera as URLs geradas, não o diretório de saída.

#### Executar uma biblioteca Server persistente

```bash
epub-browser server /caminho/para/livros \
  --server-dir /caminho/para/estado-do-epub-browser \
  --watch
```

Abra `http://127.0.0.1:8000/`. Na primeira visita, crie o administrador inicial; a biblioteca não é examinada nem publicada antes dessa configuração. `--no-browser` apenas impede que o serviço abra automaticamente o navegador local.

## Dados e operações

### Dados, contas e limites de acesso

Cada livro possui um `book_id` estável. Por padrão, `--book-id-storage sidecar` armazena a identidade ao lado do arquivo de origem sem alterar seus bytes. Para EPUB, `--book-id-storage embedded` grava a identidade nos metadados OPF e exige uma fonte modificável; para PDF, a configuração sempre usa o sidecar adjacente.

No modo Server, `--server-dir` é o local autoritativo do SQLite, dos caches e dos backups de migração. Contas, estantes, progresso, anotações, resultados de IA e tarefas também ficam ali. Administradores gerenciam usuários, funções, sessões e permissões de livros; membros usam apenas os livros autorizados e seus próprios dados privados. Proteja as permissões desse diretório e dos backups.

### Docker, proxy reverso e documentação completa

Em contêineres, monte os livros como somente leitura e `--server-dir` em um volume persistente. Aceite cabeçalhos de proxy apenas de proxies confiáveis e use HTTPS em implantações públicas.

Para Docker Compose, todas as opções de CLI, migrações, LAN, proxy reverso e solução de problemas, consulte o [README completo em inglês](../../README.md) ou o [README completo em chinês simplificado](README.zh-CN.md). O comportamento dos dois modos é igual em todos os idiomas.

## Desenvolvimento e licença

### Contribuição e licença

Issues e Pull Requests são bem-vindos. Consulte [License.txt](../../License.txt) para a licença.
