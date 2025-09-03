# wa-wscrap-bot

Automação simples do WhatsApp Web com Selenium para ler mensagens de conversas e responder automaticamente com base em intents (saudação, horário, link) e fallback de conhecimento extraído de uma página da Wikipédia.

## IMPORTANTE — DEMO (conversas filtradas)
- Este projeto é uma DEMO: o bot só responde automaticamente a conversas que estejam no filtro de alvo.
- O filtro está definido no código, em `main.py`, pela variável `nomes_das_conversas`.
- Para alterar a conversa alvo, edite a lista com o(s) nome(s) ou número(s) exatamente como aparecem na barra lateral do WhatsApp Web.

Como alterar o alvo:
- Arquivo: `main.py:513`
- Exemplo de edição:
  - De: `nomes_das_conversas = ['Tock']`
  - Para: `nomes_das_conversas = ['Maria', '5511998887777']`
- Se o nome/número não casar exatamente com o WhatsApp Web, o bot não vai abrir nem responder a essa conversa.

## Requisitos
- Python 3.9+ (recomendado)
- Google Chrome instalado
- Dependências Python: `pip install -r requirements.txt`

## Instalação
1) (Opcional) Crie e ative um ambiente virtual
   - Windows PowerShell: `python -m venv .venv && .venv\Scripts\Activate.ps1`
   - Linux/macOS: `python3 -m venv .venv && source .venv/bin/activate`
2) Instale as dependências
   - `pip install -r requirements.txt`

## Execução rápida
1) Inicie: `python main.py`
2) Aguarde o WhatsApp Web abrir e faça login com o QR Code (se necessário).
3) O bot tenta clicar no filtro “mensagens não lidas”, lista contatos com não lidas, entra na conversa e processa as últimas mensagens de entrada.
4) As respostas são enviadas automaticamente conforme as regras abaixo.

## Configuração
- Variáveis de ambiente:
  - `WIKI_URL`: URL da Wikipédia usada como base de conhecimento para o fallback (padrão: `https://pt.wikipedia.org/wiki/Oakley,_Inc.`).
  - `BOT_DEBUG=1`: habilita logs detalhados das intenções, agrupamentos e ciclos.
- Contatos alvo: hoje a lista está definida no código, em `main.py` na variável `nomes_das_conversas`. Edite para os nomes/números que deseja monitorar.
- Perfil do Chrome: é criado automaticamente em `User_Data/` para manter a sessão entre execuções.

## Como funciona
- Leitura de mensagens:
  - O bot abre a conversa com não lidas e coleta as últimas mensagens de entrada via seletores do WhatsApp Web.
  - Cada mensagem é tratada como `{'texto': ..., 'hora': ...}`; quando o contador de não lidas não está disponível, usa-se `hora=None` para manter a deduplicação estável entre ciclos.
- Deduplicação (anti-resposta repetida):
  - Para cada conversa, o bot mantém `root.processed_msgs_map[chat]` com chaves `(texto_normalizado, timestamp_normalizado)`.
  - Se a chave já foi processada, a mensagem é ignorada e não recebe nova resposta.
- Intents e respostas:
  - Intents básicas: `saudacao`, `horario_atendimento`, `olhar` (link/site).
  - Quando nenhuma casa, o bot usa fallback “wiki” com similaridade TF‑IDF sobre o texto da página definida em `WIKI_URL`.
  - Saudações são escolhidas aleatoriamente a partir de uma lista pré-definida.
- Logs e debug:
  - Com `BOT_DEBUG=1`, imprime padrões de intents, mensagens analisadas, agrupamentos por sentido e a categoria final escolhida.
  - O fallback “wiki” também é logado explicitamente.

## Estrutura do projeto
- `main.py`: inicializa Selenium/Chrome, gerencia a UI do WhatsApp Web, coleta mensagens e envia respostas.
- `mensages.py`: NLTK/Wikipedia, definição de intents, compilação de regex, deduplicação e roteamento de respostas.
- `requirements.txt`: dependências do projeto.
- `User_Data/`: perfil do Chrome (persistido).

## Dicas e solução de problemas
- Classes CSS do WhatsApp Web podem mudar e quebrar seletores. Se algo “sumir”, revise e ajuste os seletores em `main.py` conforme a estrutura atual do DOM.
- Se o `chromedriver` não iniciar, garanta que o Google Chrome esteja instalado e atualizado. O `webdriver-manager` baixa a versão adequada automaticamente.
- NLTK: os recursos necessários são baixados em tempo de execução; em ambientes sem internet, desabilite o componente de fallback ou pré‑baixe os corpora.
- Se não aparecerem logs, exporte `BOT_DEBUG=1` antes de rodar.

## Aviso
Use este projeto de forma responsável, respeitando os termos de uso do WhatsApp e a legislação local. Automatizações podem violar políticas da plataforma; utilize apenas para fins de estudo/demonstração.
