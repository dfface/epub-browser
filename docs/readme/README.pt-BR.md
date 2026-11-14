# EPUB Browser

> **Transforme livros em sites. Crie uma biblioteca que é só sua.**
>
> Publique livros EPUB e PDF como um site estático ou mantenha uma biblioteca privada
> em seu próprio servidor, com contas, progresso sincronizado, anotações e, opcionalmente,
> leitura com IA integrada.

[Conheça a biblioteca estática](https://epub-browser-test.yuhan.tech/) · [Experimente a biblioteca privada](#demonstrações-ao-vivo)

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/dfface/epub-browser/main/epub_browser/assets/logo-lockup-color.png" alt="Logotipo do EPUB Browser" width="520">
</p>

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![Um PDF no leitor compartilhado do EPUB Browser, com a página original, navegação, temas e ferramentas de leitura.](../releases/assets/v2.8.0-pdf-reader.png)

O EPUB Browser é mais que um conversor de livros. É uma plataforma de leitura completa,
que você pode publicar em qualquer lugar ou hospedar por conta própria. EPUB e PDF usam
a mesma biblioteca, página do livro, sumário, modos de leitura, temas, acompanhamento de
progresso e fluxo de anotações. Cada página do PDF se torna um capítulo do leitor,
renderizada localmente pelo PDF.js dentro da mesma experiência de leitura, sem um
visualizador separado nem CDN em tempo de execução.

## Conteúdo

- [Visão geral do projeto](#visão-geral-do-projeto)
  - [Por que o EPUB Browser](#por-que-o-epub-browser)
  - [Tecnologias](#tecnologias)
  - [Como escolher entre SSG e Server](#como-escolher-entre-ssg-e-server)
  - [Demonstrações ao vivo](#demonstrações-ao-vivo)
  - [Leitura com IA integrada](#leitura-com-ia-integrada-somente-server)
  - [Modo mínimo para Kindle](#modo-mínimo-para-kindle)
- [Primeiros passos](#primeiros-passos)
  - [Escolha uma forma de instalação](#escolha-uma-forma-de-instalação)
  - [Início rápido](#início-rápido)
- [Formatos e leitura](#formatos-e-leitura)
  - [Fontes e identidade estável dos livros](#fontes-e-identidade-estável-dos-livros)
  - [PDF: uma página, um capítulo](#pdf-uma-página-um-capítulo)
- [Implantação](#implantação)
  - [SSG](#ssg)
  - [Server](#server)
  - [Docker](#docker)
- [Referência e operações](#referência-e-operações)
  - [Referência de comandos](#referência-de-comandos)
  - [Dados de leitura e disponibilidade de recursos](#dados-de-leitura-e-disponibilidade-de-recursos)
  - [API do Server e WebHooks](#api-do-server-e-webhooks)
  - [Segurança dos dados e solução de problemas](#segurança-dos-dados-e-migração)
- [Desenvolvimento e licença](#desenvolvimento-e-licença)
- [Central de documentação](../README.md)

## Visão geral do projeto

### Por que o EPUB Browser

- **Publique onde quiser e mantenha o controle.** Com um único comando, gere um site
  estático completo para Pages, armazenamento de objetos ou Nginx; ou execute um Server
  persistente com contas, permissões por livro e OIDC. Os recursos do aplicativo, as
  fontes, o PDF.js e os renderizadores são servidos localmente, de modo que a leitura
  nunca dependa de um CDN.
- **EPUB e PDF em um único leitor de verdade.** Os dois formatos compartilham biblioteca,
  página do livro, sumário, layout responsivo, três modos de leitura, temas, tela cheia
  e progresso. Cada página do PDF permanece na área de leitura, com zoom, seleção de
  texto na camada de texto e anotações, em vez de abrir em um visualizador separado.
- **Encontre o livro e também o trecho.** A busca da biblioteca cobre metadados, tags e
  pinyin, com ordenação e paginação. A busca no livro inteiro para EPUB, feita no Server,
  retorna resultados completos agrupados por capítulo e leva ao trecho destacado. IDs
  estáveis mantêm pontos de continuação, anotações e histórico vinculados ao mesmo livro.
- **Entenda o texto, não apenas role a página.** No modo Server, guias de capítulos EPUB,
  explicações ligadas a evidências, mapas mentais e o Ask AI privado ficam ao lado do
  texto original. Destaques, notas, dicionário e enciclopédia funcionam em EPUB e em PDFs
  com camada de texto; as listas de vocabulário do Server registram a origem e o grau
  de domínio de cada palavra.
- **Transforme a leitura em um histórico que vale a pena guardar.** Estantes aninhadas,
  avaliações, resenhas, exportação de anotações, calendários de atividades, tendências,
  estatísticas por livro e rankings de tempo de leitura formam um registro conectado.
  O Server mantém os dados de leitura de cada conta privados e sincronizados entre
  dispositivos.
- **Ofereça um serviço de leitura, não apenas um visualizador.** No modo Server, adicione
  livros por upload na interface do administrador ou por pastas monitoradas, limite o uso
  de disco com remoção configurável de itens do cache por LRU, gerencie permissões de membros e de IA
  e integre outros sistemas por OpenAPI, PATs e WebHooks. A leitura mínima para Kindle
  atende dispositivos com recursos limitados; o Server também oferece um painel pessoal
  de descanso de tela para Kindle com relógio, calendário, agenda, memorando e temporizador
  Pomodoro.

![Guia de capítulo ao lado do texto EPUB original, com uma gaveta privada do Ask AI.](assets/ai-native-reading.png)

*As orientações da IA e as perguntas privadas continuam ancoradas no livro original.*

![Visão privada das estatísticas de leitura, com calendário de atividades e tendência do tempo de leitura.](assets/reading-insights.png)

*As estatísticas transformam a leitura ativa em um histórico privado e fácil de entender.*

### Tecnologias

O EPUB Browser usa propositalmente uma stack web enxuta, com renderização no servidor.
O aplicativo instalado não tem framework SPA nem exige Node.js em tempo de execução:

| Camada | Tecnologia | Função |
| --- | --- | --- |
| Frontend | HTML semântico, CSS, VanillaJS com módulos ES e APIs do navegador | Uma interface responsiva compartilhada entre SSG e Server |
| CLI e Server | Python 3.9+, Starlette, Uvicorn | Comandos de conversão, páginas autenticadas, APIs e trabalhos em segundo plano |
| Dados | SQLite e caches de conteúdo JSON reconstruíveis | O estado do usuário fica separado do conteúdo derivado de EPUB/PDF |
| Formatos de livro | lxml, pypdf, pypdfium2, PDF.js | Análise e sanitização unificadas de EPUB com prioridade ao modo estrito, metadados e capas de PDF e renderização local no navegador |
| Operação offline e recursos | Service Worker, recursos imutáveis com hash e dependências vendorizadas com versões fixadas | Entrega autossuficiente, sem CDN em tempo de execução |
| Distribuição | PyPI, Docker e hospedagem estática comum | O mesmo código é distribuído como SSG ou como Server persistente |
| IA opcional | APIs compatíveis com OpenAI, com Markdown, KaTeX e Mermaid renderizados localmente | Camadas de aprendizagem para EPUB somente no modo Server |

O Node.js é usado apenas pelos mantenedores em testes no navegador; ele não faz parte
do ambiente de produção do leitor.

### Como escolher entre SSG e Server

O mesmo processamento das fontes e os mesmos modelos de página sustentam dois modos de
implantação bem definidos. Escolha conforme o local onde os dados de leitura devem ficar,
não conforme o formato do livro:

| Recurso | `ssg` | `server` |
| --- | --- | --- |
| EPUB e PDF | Sim | Sim |
| Entrega | HTML e recursos estáticos publicados atomicamente para Pages, armazenamento de objetos ou Nginx | Páginas dinâmicas autenticadas, apoiadas por um cache de conteúdo substituível |
| Contas e controle de acesso | Nenhum | Contas de administrador e membro, concessões para livros restritos, sessões e proteção contra CSRF |
| Login único com OIDC | Não incluído | Provider genérico, vinculação de contas existentes e provisionamento opcional de membros |
| Progresso, anotações e estante | Armazenados no navegador atual | Sincronizados por conta autenticada no SQLite |
| Avaliações, resenhas e sessões de leitura | Não gerados | Registros privados por conta e estatísticas de leitura |
| Atualizações das fontes | Execute `ssg` novamente | Reinicie, faça uma nova varredura ou use `--watch` |
| Administração, tags, OpenAPI e WebHooks | Não incluídos | Incluídos |
| Leitura com IA e Ask AI | Não incluídos | Disponíveis para EPUB quando configurados e explicitamente permitidos; ocultos para PDF |
| Banco de dados em tempo de execução | Nenhum | Obrigatório no modo persistente |
| Melhor uso | Hospedagem pública ou estática, pacotes offline e publicação pessoal simples | Biblioteca privada, vários dispositivos ou leitores, automação e acesso gerenciado |

Use `ssg` quando o resultado precisar ser composto por arquivos estáticos comuns. Use `server` quando os leitores precisarem de contas, dados entre dispositivos, controle de acesso ou reconciliação automática das fontes.

### Demonstrações ao vivo

- **Modo SSG**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Modo Server**: [epub.yuhan.tech](https://epub.yuhan.tech/) — entre com o usuário `demo` e a senha `demo`.

### Leitura com IA integrada (somente Server)

Para livros EPUB, o modo Server pode acrescentar guias de capítulo, explicações ligadas
a evidências, mapas mentais, perguntas para reflexão e uma gaveta privada do Ask AI sem
afastar o leitor do texto original. Os resultados continuam sujeitos às permissões do
livro; os membros precisam de autorização explícita, e o SSG não contém controles de IA,
tarefas, dados de conta nem configuração do provedor. Para PDF, a leitura com IA e o
Ask AI ficam intencionalmente ocultos.

Consulte o [guia de leitura com IA integrada](../ai-native-reading.md) para ver o modelo
completo de interação e as [notas sobre os renderizadores locais de rich text](../third-party-ai-renderers.md)
para conhecer os limites de renderização e segurança de rede.

### Modo mínimo para Kindle

Kindles antigos com e-Ink e qualquer navegador com recursos limitados recebem uma
interface de leitura mínima, sem dependências. Ative-a com `--kindle`:

- SSG: `epub-browser ssg --kindle -o output/ SOURCE...`
- Server: `epub-browser server --kindle --server-dir data SOURCE...`

Cada livro EPUB (livros PDF são excluídos) ganha três páginas adicionais:

- a estante mínima `/kindle-library.html`
- a página do livro `/book/<id>/kindle.html`
- a página do capítulo `/book/<id>/kindle_chapter_N.html`

Essas páginas são ajustadas para e-Ink: marcação mínima, temas feitos só com CSS, scripts
compatíveis com ES5, sem Service Worker e sem framework. A leitura funciona sem nenhum
JavaScript; a troca de tema (Light / Sepia / Dark), o tamanho da fonte (A- / A+) e a
localização da interface usam pequenos scripts inline sobre o HTML simples.

Todas as páginas oferecem controles de tema e fonte (no cabeçalho e novamente no rodapé
dos capítulos), navegação pelo sumário, capítulo anterior e seguinte e um link “Continuar
lendo”, que retoma o progresso salvo.

O progresso de leitura varia conforme o modo:

- **SSG:** o progresso fica nos cookies do navegador atual, localmente e sem conta.
- **Server:** o progresso e os heartbeats de leitura são sincronizados no SQLite por
  conta conectada. As interfaces do Kindle apenas leem e informam dados: registram o
  capítulo atual, enviam heartbeats e mostram uma estante somente leitura, sem expor
  estatísticas nem gerenciamento de conteúdo.

O controle de acesso é aplicado em todas as interfaces do Kindle. Para um livro de
visibilidade restrita, usuários sem autorização recebem 403: o livro é omitido da estante
mínima, e as páginas do livro e dos capítulos e a API de progresso negam o acesso.

Navegadores compatíveis (com `Kindle/`, `Arora/` etc. no UA) são redirecionados
automaticamente do leitor completo para as páginas mínimas; as URLs acima também podem
ser acessadas diretamente. Assim, o modo mínimo funciona como alternativa viável para
dispositivos de baixa potência ou com suporte limitado a JavaScript.

## Primeiros passos

### Escolha uma forma de instalação

O EPUB Browser oferece duas formas de instalação. Ambas aceitam um ou mais arquivos
`.epub` ou `.pdf`, diretórios aninhados ou um diretório de biblioteca no estilo Calibre.

| Instalação | Uso indicado | Requisito do host |
| --- | --- | --- |
| PyPI | Modo SSG ou Server | Python 3.9 ou mais recente |
| Docker | Modo Server persistente | Docker Engine; o Python já vem na imagem |

#### PyPI (SSG ou Server)

Instale o aplicativo de linha de comando:

```bash
pip install epub-browser
```

Mostre a referência de comandos específica de cada modo:

```bash
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

#### Docker (Server)

A imagem publicada [`dfface/epub-browser`](https://hub.docker.com/r/dfface/epub-browser)
executa o modo Server e não exige Python no host:

```bash
docker pull dfface/epub-browser:latest
```

Use `latest` para avaliar a versão atual; fixe uma tag de versão numerada para ter uma
implantação de produção reproduzível. Consulte [Docker](#docker) para ver as montagens
obrigatórias de livros e estado, o início rápido com Compose, a configuração inicial e
as orientações de rede.

### Início rápido

#### Gerar um site estático

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

Sirva `dist/` por HTTP. Não há suporte para abrir as páginas geradas diretamente por `file://`, pois o armazenamento do navegador, os módulos, os manifestos e os Service Workers exigem uma origem HTTP.

Para um site hospedado sob um prefixo de URL, defina o caminho público separadamente do destino no sistema de arquivos:

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist \
  --base-path /my-repository/
```

`--base-path` altera as URLs geradas, não o local de gravação dos arquivos. Com `/my-repository/`, links, ícones, manifestos, metadados dos livros e entradas do Service Worker usam esse prefixo, enquanto os arquivos continuam diretamente em `dist/`.

#### Executar uma biblioteca Server persistente

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

Abra `http://127.0.0.1:8000/`. No primeiro acesso, o EPUB Browser pede a criação do administrador inicial. A biblioteca não é varrida nem exposta até que essa configuração única seja concluída.

Se você escolheu Docker, pule o comando Python acima e siga para o
[início rápido com Docker Compose](#docker-compose).

## Formatos e leitura

### Fontes e identidade estável dos livros

Cada `SOURCE` posicional pode ser um arquivo EPUB, um arquivo PDF ou um diretório.
Os diretórios são pesquisados recursivamente. É possível passar várias fontes em um
mesmo comando:

```bash
epub-browser server book.epub /srv/library /srv/periodicals \
  --server-dir /srv/epub-browser \
  --watch
```

Cada livro recebe um `book_id` estável, também exposto como `book_hash` nas URLs geradas e nos dados do navegador. O padrão geral da CLI é:

```bash
--book-id-storage sidecar
```

O modo sidecar grava um arquivo de identidade visível ao lado da fonte, como `BOOK.epub.epub-browser.json` ou `BOOK.pdf.epub-browser.json`, sem alterar os bytes da fonte. O sidecar contém o ID estável e uma fingerprint SHA-256 verificada da fonte.

Para colocar o ID nos metadados OPF do EPUB ou no dicionário de informações do documento PDF, selecione o armazenamento incorporado para toda a invocação:

```bash
--book-id-storage embedded
```

O modo incorporado pode reconstruir o ZIP do EPUB ou acrescentar uma atualização de metadados ao PDF antes da conversão. Se o PDF não puder ser atualizado e sua fonte não tiver mudado, o EPUB Browser salva o mesmo ID em um sidecar adjacente. Isso inclui PDFs assinados, criptografados e somente leitura. O EPUB Browser interrompe a operação quando os IDs divergem, fontes ativas duplicam um ID, um local de armazenamento é inválido ou não é possível gravar no local necessário.

Ao migrar entre modos de armazenamento, o EPUB Browser copia o ID existente para o novo local e mantém o outro local válido. Um ID incorporado existente desde a v2.0.4 é copiado para o sidecar padrão sem regravar o EPUB. Depois de qualquer atualização de metadados, tanto o SSG quanto o Server entregam uma cópia exata, byte a byte, do PDF de origem.

### PDF: uma página, um capítulo

O PDF é compatível com os dois modos de implantação. O leitor trata cada página do PDF
como um capítulo comum do EPUB Browser. Assim, a página do livro, a navegação entre
capítulos, o sumário, a paginação, a leitura contínua, o progresso, as sessões de leitura,
as anotações, o dicionário e a enciclopédia continuam sendo uma única interface e um
único modelo de dados compartilhados:

| Conceito do PDF | SSG | Server |
| --- | --- | --- |
| URL da página 1 | `chapter_0.html` | `/book/<book-id>/chapter_0.html` |
| URL da página N | `chapter_{N-1}.html` | `/book/<book-id>/chapter_{N-1}.html` |
| Rótulos de página e sumário | Gerados localmente; todas as páginas são listadas | Renderizados a partir do cache de metadados do PDF; todas as páginas são listadas |
| Outline incorporado | Um marcador na entrada do sumário da página de destino | O mesmo marcador, sem remover nem reordenar as entradas das páginas |
| Rolagem e paginação/virada de página | Shells de capítulo estáticos e PDF.js local | Shells de capítulo compartilhados e dinâmicos e PDF.js local |
| Destaques, notas, dicionário e enciclopédia | Componentes compartilhados locais ao navegador quando há camada de texto | Componentes compartilhados autenticados quando há camada de texto |
| Bytes brutos do PDF | Um `document.pdf` na saída estática do livro | Rota com suporte a Range, exclusiva para Session, para o documento em cache |

Os números de página visíveis e o PDF.js começam em um; os índices de capítulo nas URLs,
no estado, nas APIs e no SQLite começam em zero. Portanto, a página 1 do PDF é sempre
`chapter_0.html`. O sumário normalizado mantém uma entrada `Page N` para cada página;
os títulos do outline incorporado ao PDF são associados como marcadores de outline à
entrada de destino, inclusive vários marcadores em uma mesma página.

O SSG grava um único `document.pdf` e um shell `chapter_<index>.html` por página. A saída
SSG não contém scripts de Session, chamadas a `/api/*`, dados de anotações sincronizados
nem dependências do Server. O Server armazena a fonte completa e idêntica byte a byte
em `book/<book-id>/pdf/document.pdf`, sem nunca dividi-la ou regravá-la. O Server renderiza
os mesmos shells de capítulo dinamicamente a partir dos metadados do PDF; uma fonte
alterada invalida e atualiza totalmente o cache do PDF (documento, metadados e capa
derivada), em vez de misturar páginas antigas e novas.

O endpoint do documento bruto no Server é exclusivo para Session:
`GET`/`HEAD /api/books/<book-id>/document`. Ele verifica autenticação, visibilidade do
livro, formato PDF e fingerprints da fonte e do cache. Em seguida, responde a solicitações de
um único intervalo limitado, com `ETag`, `Accept-Ranges`, cache privado, `nosniff` e
exibição inline do PDF. Não expõe caminho absoluto, não está disponível para
autenticação por PAT e não aparece na interface PAT/OpenAPI. O SSG tem apenas seu
`document.pdf` local e nenhuma API de documento bruto.

PDFs com uma camada de texto utilizável pelo PDF.js reutilizam exatamente o mesmo popup
de seleção e o mesmo componente de anotações para destaques e notas, além do dicionário
e da enciclopédia. Armazenamento, propriedade, exportação, listagem e links profundos de
anotações continuam compartilhados; não há tabela de anotações nem interface de
configurações específica para PDF. PDFs digitalizados ou compostos só por imagens
continuam legíveis, mas destaques e notas baseados em seleção, dicionário, enciclopédia
e busca no documento ficam explicitamente indisponíveis quando não existe uma camada de
texto utilizável. Uma seleção que atravessa páginas ainda pode ser copiada, enquanto as
ações de anotação e consulta mostram a mensagem localizada de recurso não compatível;
a seleção dentro de uma página continua funcionando.

O PDF.js não é um segundo shell de visualização. Antes de compilar ou publicar, baixe e
verifique os recursos de terceiros com versões fixadas:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
```

Depois disso, o aplicativo serve localmente, em tempo de execução, os módulos e workers
do PDF.js com hash e nunca os busca em um CDN. Os lightboxes de imagens usam a dependência
fixada GLightbox; Fancyapps/Fancybox não é uma dependência de execução nem redistribuída.
Consulte [third_party/README.md](../../third_party/README.md) para conhecer o fluxo dos
recursos fixados e das versões.

## Implantação

### SSG

O SSG cria um snapshot completo em um diretório de preparação irmão, valida esse snapshot e só então substitui o destino. Se alguma conversão falhar, o destino anterior permanece inalterado. A saída gerada não contém banco de dados do Server, estado de migração, página de conta nem metadados de cache de execução.

O comportamento do SSG é intencionalmente local e sem contas:

- O progresso de leitura e as anotações usam o armazenamento do navegador na origem atual.
- A estante aceita importação e exportação local em JSON; não há ação de sincronização na nuvem.
- Login, configurações de conta, APIs do Server e controles dependentes do usuário não estão presentes.
- O destino de armazenamento é fixado no armazenamento local do navegador e não aparece como configuração.
- A saída estática inclui o Service Worker necessário para os recursos funcionarem offline.

Todos os JavaScript, CSS, fontes e ícones necessários ao aplicativo estão incluídos na saída. Consulte [Autossuficiência e comportamento de rede](#autossuficiência-e-comportamento-de-rede) para conhecer a única requisição de rede opcional.

### Server

#### Configuração inicial, contas e permissões

Em um diretório novo de estado persistente, as páginas normais redirecionam para `/setup`. APIs, fluxos de eventos, recursos gerados e livros retornam uma resposta de configuração necessária até que o administrador inicial seja criado. Conclua a configuração por loopback ou outro caminho privado confiável antes de expor a porta: o primeiro envio de configuração bem-sucedido reivindica a conta de administrador.

Depois da configuração:

- O registro público fica fechado. Os administradores criam e gerenciam usuários.
- As contas têm o papel `administrator` ou `member`.
- Livros comuns ficam visíveis para todas as contas autenticadas.
- Livros restritos ficam visíveis apenas para administradores e usuários selecionados explicitamente.
- Cada usuário é dono da própria estante, progresso, anotações e sessões ativas.
- Os usuários podem alterar a senha e revogar as próprias sessões.
- Os administradores podem gerenciar usuários, papéis, senhas, sessões e concessões de livros.
- As sessões usam cookie HttpOnly, proteção contra CSRF e validade deslizante de 30 dias.

#### Login único com OIDC e vinculação de contas

O modo Server pode usar um único Provider genérico de OpenID Connect (OIDC), incluindo
Authelia, Keycloak, Authentik e serviços compatíveis. Em **Administration →
OIDC login**, informe o nome do Provider mostrado aos leitores, a URL do emissor, o
client ID, o client secret, a redirect URI exata, os escopos e o claim de nome de usuário.
O EPUB Browser usa discovery e o fluxo Authorization Code com S256 PKCE, valida o ID token
assinado e identifica uma conta externa somente por `(issuer, sub)`; os claims de e-mail
e nome de usuário são dicas para exibição e provisionamento, nunca chaves de identidade.

Registre exatamente este callback no Provider, incluindo esquema e host:

```text
https://reader.example.com/auth/oidc/callback
```

Usuários existentes podem entrar localmente e conectar o Provider nas configurações da
conta. Caso contrário, uma identidade externa desconhecida precisa informar uma única vez
o nome de usuário e a senha de uma conta local existente. O provisionamento automático
opcional cria um membro sem senha e nunca importa o papel de administrador. Deixe os
usuários existentes fazerem a vinculação primeiro: ativar o provisionamento automático
cedo demais pode criar **contas locais duplicadas**. O login por senha do **administrador
local** sempre continua disponível, mesmo quando o login por senha dos membros locais está
desativado. Mantenha essa credencial de recuperação testada e protegida. O logout no
Provider não é executado, e seus tokens de acesso e atualização não são armazenados.

No Authelia, configure um cliente confidencial na seção do OIDC Provider. O trecho abaixo
usa valores propositalmente fictícios e pressupõe que as chaves e políticas exigidas pelo
provider do Authelia já estejam configuradas. Armazene no Authelia o hash de um client
secret aleatório e forte; depois informe uma única vez, no EPUB Browser, o segredo
correspondente sem hash:

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

No EPUB Browser, use o issuer `https://auth.example.com`, o client ID
`epub-browser`, os scopes `openid profile email` e o username claim
`preferred_username`. Salvar executa discovery real e validação de capacidades; em caso
de falha, a configuração anterior permanece ativa.

#### Configurar e controlar a leitura com IA

Os administradores configuram a leitura com IA em **Administration**, logo depois do
gerenciamento de usuários e antes do gerenciamento de livros. A página armazena no banco
SQLite do Server a Base URL compatível com OpenAI, a API key, o modelo, o tempo limite,
o orçamento de contexto, o limite de concorrência e o limite diário padrão de chamadas
ao provedor. A IA começa desativada para membros; o administrador precisa conceder acesso
a cada membro e pode definir um limite diário individual (`0` significa ilimitado).

As camadas de aprendizagem dos capítulos e as resenhas no nível do livro são
compartilhadas por idioma elegível, enquanto as conversas posteriores permanecem
privadas em cada conta. Resultados, estado das tarefas, tags personalizadas,
classificação de leitura do livro e conversas privadas posteriores ficam no SQLite.
Os resultados antigos continuam disponíveis depois de uma mudança na configuração do
modelo até que um administrador os gere novamente de forma explícita.

Quando o leitor pede um guia de IA ou faz uma pergunta, o texto EPUB selecionado e o
contexto compactado da conversa são enviados ao provedor externo configurado. Não ative
o recurso a menos que os leitores tenham permissão para enviar esse conteúdo ao provedor.
A API key nunca é devolvida ao navegador nem exposta por uma API; proteja o diretório de
estado do Server de acordo.

Para um primeiro início sem intervenção, forneça um nome de usuário e um arquivo de senha:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --admin-username admin \
  --admin-password-file /run/secrets/epub-browser-admin-password \
  --no-browser
```

O arquivo de senha deve ter permissões `0600`. O EPUB Browser remove uma quebra de linha final, armazena um hash Argon2id e nunca imprime o segredo. A inicialização é interrompida se a configuração estiver incompleta ou se o arquivo estiver vazio ou não puder ser lido. Depois que a configuração é concluída, as inicializações seguintes não leem o segredo de bootstrap.

Os equivalentes em variáveis de ambiente são `EPUB_BROWSER_ADMIN_USERNAME` e `EPUB_BROWSER_ADMIN_PASSWORD_FILE`. `EPUB_BROWSER_ADMIN_PASSWORD` é uma alternativa em texto simples usada apenas quando nenhum arquivo de senha está configurado. O caminho do arquivo de senha na CLI tem prioridade sobre as fontes de senha do ambiente.

#### Abertura do navegador e logs

Por padrão, depois que o listener HTTP é iniciado, o Server tenta abrir o navegador padrão do sistema operacional. `--no-browser` impede essa abertura local. A opção **não desativa a interface web nem o acesso pelo navegador**; ela apenas suprime a chamada local `webbrowser.open(...)`. Use-a no Docker, no systemd, em sessões SSH, máquinas sem interface gráfica e scripts.

Por padrão (`--log-level error`), a CLI emite apenas erros para que mensagens e avisos de rotina não interrompam os indicadores de progresso no terminal. Um terminal interativo mostra a URL vinculada uma vez; execuções não interativas no Docker e em serviços permanecem silenciosas. Use `--log-level warning` para incluir avisos, `--log-level info` para logs operacionais e de acesso HTTP ou `--log-level debug` para o máximo de detalhes. `--log` continua sendo um alias de compatibilidade para `--log-level info`.

As varreduras iniciais e do modo watch aparecem na interface web, não no `tqdm` do terminal. Um resumo de sucesso fecha automaticamente; as falhas continuam visíveis até serem dispensadas. Com `--watch`, corrigir ou substituir uma fonte inicia outra varredura sem exigir uma ação manual de repetição.

#### Estado persistente e efêmero

O modo Server persistente exige `--server-dir`. Para uma execução descartável, use `--ephemeral`:

```bash
epub-browser server book.epub --ephemeral
```

O estado efêmero é excluído no encerramento. Como o banco de dados é novo a cada execução, a configuração também se repete, a menos que sejam fornecidas credenciais de bootstrap para operação sem intervenção.

Estrutura persistente:

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

Somente `data/` é autoritativo. `cache/` pode ser excluído e será reconstruído. Preserve `data/` durante upgrades e substituições de contêiner. Um lock do sistema operacional controla a exclusividade; `.server.lock` pode permanecer após um encerramento normal como metadado de diagnóstico.

Armazene o `data/epub-browser.db` persistente em um sistema de arquivos local. Sistemas de arquivos compartilhados ou de rede não são compatíveis com a concorrência do WAL. Os backups verificados permanecem em `data/backups/` e incluem todos os dados confirmados no WAL.

#### LAN e proxy reverso

Por padrão, o Server se vincula a `127.0.0.1:8000`. Para uma LAN confiável:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --port 8080 \
  --no-browser
```

Não exponha o servidor HTTP integrado diretamente à internet pública. Termine o TLS em um proxy reverso, aplique controles de rede e ative cookies seguros.

Para registrar os IPs reais dos clientes nas sessões ativas e nos limites de tentativas de login atrás de um proxy reverso, configure a **rede do socket direto** dele, não os intervalos dos clientes públicos:

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

Repita `--trusted-proxy-cidr` uma vez para cada endereço ou rede de proxy direto. Somente requisições cujo par direto pertença a um desses CIDRs podem fornecer `X-Forwarded-For`; todos os outros pares registram apenas seu endereço direto. O processamento de endereços encaminhados do Uvicorn fica desativado, de modo que `Forwarded` e `FORWARDED_ALLOW_IPS` não podem ampliar esse limite de confiança. Use `--cookie-secure` somente quando o navegador acessar o serviço por HTTPS.

### Docker

A imagem executa o modo Server persistente com estes padrões:

- `/app/Library` como fonte
- `/app/EpubBrowserFiles` como estado persistente
- `--watch`
- `--no-browser`
- `--host 0.0.0.0 --port 80`
- `--book-id-storage embedded`
- `--kindle`

Como a identidade incorporada pode atualizar arquivos EPUB ou PDF, monte a biblioteca com leitura e gravação. Monte o estado do Server com leitura e gravação e mantenha esse estado ao substituir o contêiner:

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  dfface/epub-browser:latest
```

Acesse `http://127.0.0.1:8080/setup` antes de alterar o mapeamento da porta ou as regras de proxy.

#### Docker Compose

O repositório inclui um [docker-compose.yml](../../docker-compose.yml) para quem prefere Compose. Em um checkout, crie `Library/`, coloque ali os livros EPUB ou PDF e execute:

```bash
docker compose up -d --build
```

Ele publica apenas `127.0.0.1:8080`, mantém os livros EPUB/PDF de origem em `./Library` e persiste o estado do Server em `./EpubBrowserFiles`. O `command` completo do Server fica intencionalmente visível no arquivo, permitindo acrescentar flags específicos da implantação sem substituir um padrão implícito da imagem. Conclua a configuração única em `http://127.0.0.1:8080/setup`. Para acesso remoto, mantenha esse mapeamento em loopback e coloque à frente um proxy reverso TLS com autenticação.

Para configuração sem intervenção:

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

Depois do primeiro início bem-sucedido, a montagem do segredo único pode ser removida. Uma biblioteca somente leitura funciona apenas quando todos os EPUBs já contêm um ID incorporado válido e correspondente. Sidecars existentes são mantidos quando seus IDs são incorporados.

Monte `/app/SyncData:ro` somente durante a importação do JSON da estante legada:

```bash
-v /path/to/legacy-sync:/app/SyncData:ro
```

A porta publicada em loopback nos exemplos mantém o contêiner atrás do limite do host. Para acesso remoto, use um proxy reverso TLS, configure o CIDR real da rede do contêiner e acrescente `--cookie-secure`.

## Referência e operações

### Referência de comandos

#### `epub-browser ssg SOURCE [SOURCE ...]`

| Opção | Significado |
| --- | --- |
| `--output-dir DIR`, `-o DIR` | Destino obrigatório do snapshot estático atômico. |
| `--base-path PATH` | Prefixo da URL pública; padrão `/`. Precisa começar e terminar com `/`. |
| `--book-id-storage sidecar\|embedded` | Local de armazenamento da identidade estável de cada fonte selecionada; padrão `sidecar`. |
| `--kindle` | Gera páginas mínimas sem dependências para Kindles antigos com e-Ink e redireciona os navegadores Kindle WebKit para elas; desativado por padrão. |
| `--log` | Alias de compatibilidade para `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Verbosidade do log operacional; padrão `error`, que mantém a saída de conversão de rotina e os avisos silenciosos. |

#### `epub-browser server SOURCE [SOURCE ...]`

É obrigatório usar exatamente um entre `--server-dir` e `--ephemeral`.

| Opção | Significado |
| --- | --- |
| `--server-dir DIR` | Raiz dos dados persistentes autoritativos e do cache substituível. |
| `--ephemeral` | Usa estado descartável; mutuamente exclusivo com `--server-dir`. |
| `--watch`, `-w` | Monitora as fontes e reconcilia inclusões, atualizações, movimentações e exclusões. |
| `--host ADDRESS` | Endereço de vinculação; padrão `127.0.0.1`. |
| `--port PORT`, `-p PORT` | Porta de vinculação; padrão `8000`. |
| `--no-browser` | Não abre o navegador padrão local. A interface web continua disponível. |
| `--log` | Alias de compatibilidade para `--log-level info`. |
| `--log-level debug\|info\|warning\|error` | Verbosidade do log operacional; padrão `error`. Os logs de acesso HTTP são ativados em `info` e `debug`. |
| `--legacy-sync-dir DIR` | Lê o JSON da estante legada durante a migração na inicialização. |
| `--book-id-storage sidecar\|embedded` | Local de armazenamento da identidade estável de cada fonte selecionada; padrão `sidecar`. |
| `--admin-username NAME` | Administrador inicial para configuração sem intervenção; alternativa `EPUB_BROWSER_ADMIN_USERNAME`. |
| `--admin-password-file FILE` | Arquivo preferencial do segredo inicial; alternativa `EPUB_BROWSER_ADMIN_PASSWORD_FILE` e, se nenhum arquivo for definido, `EPUB_BROWSER_ADMIN_PASSWORD`. |
| `--trusted-proxy-cidr CIDR` | Pode ser repetido; define a rede do proxy direto como fronteira de confiança para analisar com segurança o IP do cliente em `X-Forwarded-For`. |
| `--cookie-secure` | Envia o cookie de sessão somente por HTTPS entre o navegador e o serviço. |
| `--kindle` | Serve páginas mínimas sem dependências para Kindles antigos com e-Ink e redireciona os navegadores Kindle WebKit para elas; desativado por padrão. |

#### Sintaxe legada da v1

A sintaxe legada é aceita em toda a linha principal v2:

| Comando v1 | Equivalente na v2 |
| --- | --- |
| `epub-browser BOOKS` | `epub-browser server BOOKS --ephemeral` |
| `epub-browser BOOKS --output-dir STATE` | `epub-browser server BOOKS --server-dir STATE` |
| `epub-browser BOOKS --no-server --output-dir DIST` | `epub-browser ssg BOOKS --output-dir DIST` |
| `--sync-dir DIR` | `server --legacy-sync-dir DIR` |

O `--keep-files`, exclusivo da sintaxe legada, mantém um diretório temporário do Server. Os diretórios persistentes do Server já são permanentes. Com `--log`, o adaptador de compatibilidade imprime o comando v2 equivalente; sem essa opção, ele permanece silencioso.

### Dados de leitura e disponibilidade de recursos

- Descoberta recursiva de EPUB/PDF e bibliotecas Calibre, tags de metadados, busca e busca por pinyin
- Interfaces responsivas de biblioteca, detalhes do livro e leitura de capítulos
- Rolagem, virada de página, leitura contínua, largura ajustável do conteúdo, fontes, CSS personalizado, temas e modo de leitura sem distrações
- Destaques, notas, navegação por anotações, grupos aninhados na estante, tags e importação/exportação em JSON
- Localização da interface para inglês, chinês simplificado, chinês tradicional,
  coreano, japonês, espanhol, alemão, francês, russo, italiano, português do Brasil,
  árabe, indonésio, hindi, vietnamita, tailandês e malaio
- Comportamento adequado a e-readers com navegadores Kindle/Silk; recursos pesados do navegador podem ser reduzidos

| Dados | SSG | Server |
| --- | --- | --- |
| Progresso de leitura | Local no navegador | Registro do usuário autenticado no SQLite |
| Destaques e notas | Locais no navegador | Registros do usuário autenticado no SQLite |
| Avaliações, resenhas e histórico privado de sessões de leitura | Não presentes | Registros do usuário autenticado no SQLite |
| Estante | Local no navegador; importação/exportação | Documento versionado na nuvem do usuário autenticado; salvamento automático |
| Contas e sessões | Não presentes | SQLite em `<server-dir>/data` |
| Concessões de livros | Não presentes | SQLite em `<server-dir>/data` |

O Server não oferece seletor entre armazenamento local e na nuvem: os dados de leitura do usuário autenticado são sempre armazenados no Server. O histórico privado detalhado das sessões de leitura nunca é emitido pelo SSG. O SSG nunca sonda APIs do Server e sempre usa o armazenamento local da origem atual do navegador.

### Autossuficiência e comportamento de rede

O aplicativo é autossuficiente para leitura: JavaScript, CSS, fontes, ícones, manifestos e recursos EPUB convertidos necessários são servidos localmente. Não há dependências de CDN em tempo de execução. Bloquear o acesso de saída à internet não impede configuração, login, navegação, leitura, anotações, progresso, uso da estante, administração nem conversão das fontes.

O rodapé pode fazer uma requisição opcional à API de Releases do GitHub para descobrir uma versão mais recente do EPUB Browser. Falha, bloqueio ou uso offline apenas suprime esse aviso de atualização.

O SSG publica um Service Worker estático. O Server desativa e descontinua propositalmente o Service Worker de toda a origem para que uma conta não receba conteúdo protegido de outra conta armazenado em cache.

### API do Server e WebHooks

As contas do Server podem criar personal access tokens com escopos nas configurações da conta. Clientes externos usam `Authorization: Bearer <PAT>` com a API versionada `/api/v1/*`; cookies do navegador não autenticam essas rotas. A API cobre livros visíveis e conteúdo dos capítulos, estante do dono do token, progresso, anotações e resenhas, além de dados somente leitura entre usuários para PATs de administrador com `admin:data:read`.

O documento OpenAPI 3.1 está disponível em `/openapi.json`; usuários conectados podem consultar a referência local em `/api-docs`. Por exemplo: `curl -H 'Authorization: Bearer …' https://reader.example/api/v1/books`. Os detalhes do capítulo retornam HTML sanitizado por padrão e texto simples com `?format=text`.

Os endpoints de lista retornam `items` e `next_cursor`. O `limit` padrão é 24, e o máximo é 100. Passe `next_cursor` como `cursor` com os mesmos filtros para buscar a próxima página. Um cursor nulo marca a última página. Por exemplo, use `/api/v1/me/annotations?book_id=BOOK_ID&chapter_index=0&fields=id,text,note` para recuperar campos selecionados de anotações de um capítulo EPUB ou de uma página PDF. Os filtros de consulta e os campos aceitos estão listados no documento OpenAPI.

O vocabulário usa o mesmo formato de lista por padrão. Clientes que ainda usam a resposta antiga `words` podem enviar `page=1` ou `page_size` para selecionar o formato de paginação legado.

Os administradores gerenciam endpoints de WebHook em Administration. Os segredos aparecem apenas na criação ou na rotação. As entregas são assinadas, duráveis e repetidas diante de respostas fora de 2xx; os eventos de resenha de livros contêm IDs e timestamps das ações, mas nunca a avaliação nem o texto da resenha.

### Segurança dos dados e migração

Antes de atualizar instalações persistentes do Server, faça backup dos livros EPUB/PDF de origem e de `<server-dir>/data`. Mantenha o mesmo volume de estado persistente ao substituir o contêiner.

A migração na inicialização é automática e segura contra reinícios. Ela verifica bancos de dados legados, cria um backup, atualiza uma cópia, importa os dados elegíveis de estante, progresso e anotações legados para a conta do administrador inicial ainda não criado e descontinua apenas artefatos públicos legados substituíveis depois de checkpoints bem-sucedidos. Requisições comuns nunca varrem diretórios de sincronização legados. Bancos de dados corrompidos, hashes de senha inválidos, bancos legados ambíguos e IDs conflitantes fazem a inicialização falhar de forma segura, sem suposições nem sobrescrita.

Um `epub-browser.db` ou `annotations.db` migrado na raiz é mantido como cópia de recuperação sensível e não autoritativa; `data/epub-browser.db` é a fonte autoritativa, e as requisições do Server não usam o arquivo mantido na raiz. Mantenha a cópia de recuperação privada. Remova-a manualmente somente com o Server parado, depois de verificar o banco autoritativo e o backup registrado e apenas quando o rollback para v1 não for mais necessário. O EPUB Browser nunca a exclui automaticamente.

Se `epub-browser.db` e `annotations.db` existirem juntos em uma raiz legada, a inicialização para e deixa os dois intactos. Consulte [Migrando para a v2](../migration-v2.md) para backup, rollback, reconstrução de cache e recuperação de conflitos.

### Solução de problemas

#### O comando iniciou, mas nenhum navegador abriu

Remova `--no-browser` ao executar em uma máquina local com interface gráfica ou abra manualmente a URL exibida/vinculada. No Docker, no systemd, em SSH e em sessões não interativas, espera-se que você abra a URL por conta própria.

#### A CLI parece silenciosa

O funcionamento silencioso é intencional sem `--log`, principalmente em ambientes não interativos. Acrescente `--log` para ver detalhes operacionais e de acesso. O progresso da varredura do Server aparece na interface web.

#### O Docker não consegue gravar um ID estável

A imagem usa identidade incorporada por padrão. Monte `/app/Library` com leitura e gravação ou incorpore previamente IDs válidos correspondentes. Use um comando personalizado com `--book-id-storage sidecar` apenas se for preferível gravar a identidade em um sidecar.

#### Um site SSG gerado tem links quebrados sob um subcaminho

Gere o site novamente com um `--base-path` normalizado, como `/reader/`, e configure o host estático para servir a saída nesse mesmo prefixo.

#### O Server se recusa a iniciar após um upgrade

Leia o primeiro erro de migração ou validação registrado, preserve os dados e os arquivos de origem e consulte [docs/migration-v2.md](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/migration-v2.md). Não exclua o diretório autoritativo `data/` para contornar um erro.

## Desenvolvimento e licença

### Contribuindo

Issues e pull requests são bem-vindos em [dfface/epub-browser](https://github.com/dfface/epub-browser). Um bom relatório inclui o comando exato, navegador e dispositivo, passos para reproduzir, logs relevantes e o EPUB ou PDF quando ele puder ser compartilhado legalmente.

#### Contrato de arquitetura para mantenedores

Antes de alterar processamento de conteúdo, modelos de página, caches, permissões,
recursos ou comportamento de implantação, leia [AGENTS.md](../../AGENTS.md). O documento
define os limites entre EPUB e PDF, as responsabilidades de SSG e Server, as revisões
independentes de cache, os requisitos de i18n em tempo de execução, as verificações de
segurança e a validação obrigatória. Termos compartilhados do produto, como *capítulo do
leitor*, *janela de leitura*, *área de leitura* e *cache de conteúdo*, estão definidos
em [CONTEXT.md](../../CONTEXT.md).

Em resumo: mantenha uma única interface de leitura, não coloque dados exclusivos do
Server no SSG, mantenha os caches derivados de EPUB e PDF separados dos dados de usuário
no SQLite e nunca acrescente uma dependência de CDN em tempo de execução. Mudanças em
um componente compartilhado devem ser testadas nos dois formatos e nos dois modos de
implantação, quando aplicável.

#### Desenvolvimento a partir de um checkout do código

Os arquivos de terceiros para o navegador são entradas geradas para a build, não código
do projeto; por isso, `epub_browser/assets/vendor/` fica intencionalmente fora do Git.
Antes de desenvolver ou compilar, baixe explicitamente as versões exatas fixadas e depois
verifique-as offline:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
python3 -m unittest tests.test_vendor_assets -v
python3 -m build
```

`fetch` é o único comando acima que baixa recursos vendorizados para o navegador. O lock
registra tarballs imutáveis do npm, resumos dos arquivos, listas de itens permitidos e licenças;
`verify`, testes, builds a partir de um checkout preparado e o leitor instalado não baixam
recursos para o navegador. O comando isolado padrão `python3 -m build` ainda pode consultar
um índice de pacotes Python para obter requisitos de build. Para uma build totalmente sem
rede, prepare a árvore vendorizada e instale previamente `build`, `setuptools` e `wheel`
antes de desconectar; depois execute `PIP_NO_INDEX=1 python3 -m build --no-isolation`.
Wheels, distribuições de código-fonte, imagens Docker e sites SSG gerados contêm os
arquivos verificados e não dependem de CDN em tempo de execução. Consulte
[third_party/README.md](../../third_party/README.md) para conhecer o fluxo de atualização,
versão e higiene do repositório.

### Licença

[MIT](../../License.txt)
