# EPUB Browser

> Um serviço privado de leitura EPUB e um gerador de sites estáticos autocontido.

**README:** [English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

**Idiomas da interface (17):** inglês, chinês simplificado, chinês tradicional, japonês, coreano, espanhol, alemão, francês, russo, italiano, português do Brasil, árabe, indonésio, hindi, vietnamita, tailandês e malaio.

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](License.txt)

O EPUB Browser oferece dois modos com responsabilidades claramente separadas:

| | `ssg` | `server` |
| --- | --- | --- |
| Implantação | Hospedagem estática, Pages, armazenamento de objetos, Nginx | Serviço privado de leitura persistente |
| Contas | Nenhuma | Contas locais |
| Progresso, anotações e estante | Somente neste navegador | Dados da conta autenticada no SQLite |
| Atualização das fontes | Executar `ssg` novamente | Reiniciar o serviço ou usar `--watch` |
| Banco de dados em execução | Nenhum | Obrigatório |

Use `ssg` para publicar arquivos estáticos comuns. Use `server` quando precisar de contas, dados entre dispositivos, controle de acesso aos livros ou monitoramento automático das fontes.

## Demonstrações

- **Modo SSG**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Modo Server**: [epub.yuhan.tech](https://epub.yuhan.tech/) — usuário e senha: `demo`.

## Leitura nativa com IA (somente Server)

A leitura com IA cria sobre o texto original uma camada de aprendizagem compartilhada e verificável, em vez de colocar um resumo genérico ao lado do livro. Ela inclui um roteiro antes da leitura, uma visão geral opcional do capítulo, explicações ligadas às citações, notas sobre a função dos parágrafos, esclarecimentos de vocabulário, uma explicação simples ao final e perguntas para aprofundamento.

Os resultados são gerados por tarefas em segundo plano, armazenados no SQLite e compartilhados entre leitores com acesso ao livro. As conversas posteriores permanecem privadas em cada conta. O administrador precisa configurar um provedor compatível com OpenAI e autorizar cada membro. O texto EPUB selecionado é enviado a esse provedor; portanto, ative o recurso somente com o consentimento dos leitores. A saída SSG nunca contém contas, controles de IA, tarefas ou configurações do provedor.

## Requisitos e instalação

- Python 3.9 ou mais recente
- Um ou mais arquivos `.epub`, diretórios aninhados com EPUB ou uma biblioteca no estilo Calibre

```bash
pip install epub-browser

# Ajuda completa de cada modo
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

## Início rápido

### Gerar um site estático

```bash
epub-browser ssg /caminho/para/livros \
  --output-dir /caminho/para/dist
```

Sirva `dist/` por HTTP; não abra as páginas geradas diretamente com `file://`. Para implantar em um subcaminho, adicione `--base-path /meu-repositorio/`; a opção altera as URLs geradas, não o diretório de saída.

### Executar uma biblioteca Server persistente

```bash
epub-browser server /caminho/para/livros \
  --server-dir /caminho/para/estado-do-epub-browser \
  --watch
```

Abra `http://127.0.0.1:8000/`. Na primeira visita, crie o administrador inicial; a biblioteca não é examinada nem publicada antes dessa configuração. `--no-browser` apenas impede que o serviço abra automaticamente o navegador local.

## Dados, contas e limites de acesso

Cada livro possui um `book_id` estável. Por padrão, `--book-id-storage sidecar` armazena a identidade ao lado do EPUB sem alterar seus bytes. `--book-id-storage embedded` grava a identidade nos metadados OPF e exige uma fonte que possa ser modificada.

No modo Server, `--server-dir` é o local autoritativo do SQLite, dos caches e dos backups de migração. Contas, estantes, progresso, anotações, resultados de IA e tarefas também ficam ali. Administradores gerenciam usuários, funções, sessões e permissões de livros; membros usam apenas os livros autorizados e seus próprios dados privados. Proteja as permissões desse diretório e dos backups.

## Docker, proxy reverso e documentação completa

Em contêineres, monte os livros como somente leitura e `--server-dir` em um volume persistente. Aceite cabeçalhos de proxy apenas de proxies confiáveis e use HTTPS em implantações públicas.

Para Docker Compose, todas as opções de CLI, migrações, LAN, proxy reverso e solução de problemas, consulte o [README completo em inglês](README.md) ou o [README completo em chinês simplificado](README.zh-CN.md). O comportamento dos dois modos é igual em todos os idiomas.

## Contribuição e licença

Issues e Pull Requests são bem-vindos. Consulte [License.txt](License.txt) para a licença.
