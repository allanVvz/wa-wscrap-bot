#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import os
from datetime import datetime
import nltk
from nltk.corpus import wordnet
import urllib.request
import bs4 as bs
import random
import string
import time
import warnings
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from nltk.corpus import stopwords

from product_search.indexer import (
    ProductSearchResult,
    PortfolioItem,
    search_products_hybrid,
    get_portfolio,
    get_featured_products,
)
from product_lookup import get_product_description
from utils.text_normalizer import normalize_basic

# Desativar avisos desnecessários
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)


def _periodo_do_dia() -> str:
    hora = datetime.now().hour
    if 5 <= hora < 12:
        return 'Bom dia'
    if 12 <= hora < 18:
        return 'Boa tarde'
    return 'Boa noite'


def _pausa_natural(texto: str = '') -> None:
    palavras = max(1, len((texto or '').split()))
    delay = min(3.0, max(0.8, palavras * 0.12 + random.uniform(0.4, 1.2)))
    time.sleep(delay)


_VARS_SAUDACAO = [
    '{periodo}! Aqui e a Vz Foreal. Como posso te ajudar?',
    '{periodo}! Tudo bem? Sou o assistente da Vz Foreal.',
    '{periodo}! Que bom te ver por aqui! Em que posso ajudar?',
    '{periodo}! Bem-vindo a Vz Foreal!',
]

_VARS_FOLLOW_UP = [
    'Posso te ajudar com algum produto, horario ou outra duvida?',
    'Procurando algum oculos especifico ou quer dar uma olhada no catalogo?',
    'Tem algum modelo em mente ou posso sugerir algo?',
    'Me conta o que voce esta procurando!',
]

_VARS_AGRADECIMENTO = [
    'De nada! Fico feliz em ajudar.',
    'Por nada! Se precisar de mais alguma coisa, e so chamar.',
    'Disponha! Qualquer duvida, estou por aqui.',
    'Que bom que pude ajudar! Ate mais.',
    'Imagina! Volte sempre.',
]

_VARS_DESPEDIDA = [
    'Ate mais! Foi um prazer te atender.',
    'Tchau! Volte sempre que precisar.',
    'Ate logo! Qualquer coisa e so chamar.',
    'Ate a proxima! Tenha um otimo dia.',
    'Fui! Qualquer duvida pode mandar mensagem.',
]

_VARS_DESCONHECIDO = [
    'Nao entendi muito bem. Pode reformular?',
    'Hmm, pode me dar mais detalhes? Assim consigo te ajudar melhor.',
    'Nao tenho certeza sobre isso. Voce esta procurando algum produto especifico?',
    'Pode explicar melhor? Quero entender o que voce precisa.',
]

# Função utilitária para garantir que um recurso do NLTK esteja disponí­vel
def ensure_nltk_resource(name, path):
    """Verifica se o recurso está disponí­vel; se não, faz o download."""
    try:
        nltk.data.find(path)
    except LookupError:
        nltk.download(name)


# Função para baixar as dependÃªncias do NLTK apenas quando necessário
def download_nltk_resources():
    resources = [
        ('wordnet', 'corpora/wordnet'),
        # Necessário para wordnet em pt-BR: OMW 1.4
        ('omw-1.4', 'corpora/omw-1.4'),
        ('punkt', 'tokenizers/punkt'),
        ('rslp', 'stemmers/rslp'),
        ('stopwords', 'corpora/stopwords'),
    ]
    for name, path in resources:
        ensure_nltk_resource(name, path)


# Função para gerar lista de sinônimos
def gerar_lista_sinonimos(palavras):
    lista_sinonimos = {}

    for palavra in palavras:
        sinonimos = []
        for syn in wordnet.synsets(palavra, lang="por"):
            for lem in syn.lemmas(lang="por"):
                sinonimos.append(lem.name())
        lista_sinonimos[palavra] = set(sinonimos)

    return lista_sinonimos


# Função para adicionar sinônimos manualmente
def adicionar_sinonimos(lista_sinonimos, sinonimos_adicionais):
    for palavra, sinonimos in sinonimos_adicionais.items():
        lista_sinonimos.setdefault(palavra, set()).update(sinonimos)
    return lista_sinonimos


# Função para gerar dicionário de palavras-chave (intents)
def gerar_keywords(lista_sinonimos):
    keywords = {
        'saudacao': [],
        'horario_atendimento': [],
        'produto': [],
        'olhar': [],
    }

    for sin in list(lista_sinonimos['ola']):
        keywords['saudacao'].append(f'.*\\b{sin}\\b.*')
    # incluir variações acentuadas e sem acento para saudação
    if 'olá' in lista_sinonimos:
        for sin in list(lista_sinonimos['olá']):
            keywords['saudacao'].append(f'.*\\b{sin}\\b.*')
    # termos base caso a lista venha vazia
    for termo in ['olá', 'ola', 'oi', 'oie', 'bom dia', 'boa tarde', 'boa noite', 'e aí', 'e ai']:
        keywords['saudacao'].append(f'.*\\b{termo}\\b.*')
    for sin in list(lista_sinonimos['horário']):
        keywords['horario_atendimento'].append(f'.*\\b{sin}\\b.*')
    # considerar chave sem acento tambem
    if 'horario' in lista_sinonimos:
        for sin in list(lista_sinonimos['horario']):
            keywords['horario_atendimento'].append(f'.*\\b{sin}\\b.*')
    # termos base para cobrir variações com/sem acento
    for termo in ['horário', 'horario', 'funcionamento', 'atendimento', 'abre', 'fecha']:
        keywords['horario_atendimento'].append(f'.*\\b{termo}\\b.*')
    # palavras-chave para intenção de compra/olhar (usa sinônimos definidos em main)
    for sin in list(lista_sinonimos.get('olhar', [])):
        keywords['olhar'].append(f'.*\\b{sin}\\b.*')

    # termos ligados a intenção de produto/compra
    termos_produto = [
        'comprar',
        'comprei',
        'compra',
        'tem',
        'têm',
        'vende',
        'vender',
        'preço',
        'preco',
        'valor',
        'link',
        'produto',
        'modelo',
        'onde comprar',
        'mostra',
        'mostrar',
        'quero',
        'oculos',
        'óculos',
        'lupa',
        'lupas',
        'catalogo',
        'catálogo',
    ]
    for termo in termos_produto:
        keywords['produto'].append(f'.*\\b{termo}\\b.*')

    keywords['destaque'] = []
    termos_destaque = [
        'promoção',
        'promocao',
        'promoções',
        'promocoes',
        'promo',
        'destaque',
        'destaques',
        'oferta',
        'ofertas',
        'desconto',
        'descontos',
        'compre 1 leve 2',
        'compre um leve dois',
        'compre 1 leve dois',
        'em promoção',
        'em promocao',
        'mais barato',
        'baratinho',
    ]
    for termo in termos_destaque:
        keywords['destaque'].append(f'.*{re.escape(termo)}.*')

    # Não manter uma intent separada 'ola'; tratar tudo como 'saudacao'

    keywords['agradecimento'] = []
    for termo in ['obrigado', 'obg', 'valeu', 'vlw', 'grato', 'agradeco', 'muito obrigado', 'thanks']:
        keywords['agradecimento'].append(f'.*\\b{termo}\\b.*')

    keywords['despedida'] = []
    for termo in ['tchau', 'xau', 'flw', 'ate mais', 'ate logo', 'bye', 'fui', 'falou']:
        keywords['despedida'].append(f'.*\\b{termo}\\b.*')

    keywords['confirmacao'] = []
    for termo in ['sim', 'claro', 'pode ser', 'ok', 'certo', 'isso mesmo', 'com certeza', 'afirmativo']:
        keywords['confirmacao'].append(f'.*\\b{termo}\\b.*')

    keywords['negacao'] = []
    for termo in ['nao quero', 'negativo', 'errado', 'nao mesmo']:
        keywords['negacao'].append(f'.*\\b{termo}\\b.*')

    return keywords


# Função para compilar as expressôes regulares para cada intenção
def compilar_keywords(keywords, debug=False):
    if not debug:
        try:
            debug = bool(int(os.environ.get('BOT_DEBUG', '0')))
        except Exception:
            debug = False
    keywords_dict = {}
    for intent, keys in keywords.items():
        # Remove vazios para evitar pattern que casa tudo
        keys = [k for k in keys if k]
        if not keys:
            continue
        pattern_str = '|'.join(keys)
        keywords_dict[intent] = re.compile(pattern_str, re.IGNORECASE)
        if debug:
            print(f"[DEBUG] Intent '{intent}' pattern: {pattern_str}")
    return keywords_dict


_PRODUCT_QUERY_STOPWORDS = {
    'quero',
    'queria',
    'gostaria',
    'olhar',
    'olha',
    'ver',
    'mostra',
    'mostrar',
    'tem',
    'têm',
    'temos',
    'vende',
    'vender',
    'venda',
    'comprar',
    'compra',
    'compraria',
    'pra',
    'para',
    'um',
    'uma',
    'de',
    'do',
    'da',
    'os',
    'as',
    'o',
    'a',
    'me',
    'vc',
    'vcs',
    'voce',
    'você',
    'link',
    'valor',
    'preço',
    'preco',
}


_INTENT_PRIORITY = (
    'destaque',
    'produto',
    'saudacao',
    'horario_atendimento',
    'olhar',
    'agradecimento',
    'despedida',
    'confirmacao',
    'negacao',
)

_GENERIC_PRODUCT_TERMS = {
    'ajuda',
    'help',
    'site',
    'link',
    'horario',
    'atendimento',
}

_RS_CIDADES = {
    'porto alegre', 'canoas', 'caxias do sul', 'pelotas', 'santa maria',
    'gravatai', 'viamao', 'novo hamburgo', 'sao leopoldo', 'rio grande',
    'alvorada', 'passo fundo', 'sapucaia do sul', 'uruguaiana',
    'santa cruz do sul', 'bage', 'bento goncalves', 'erechim',
    'cachoeirinha', 'guaiba', 'alegrete', 'lajeado', 'ijui',
    'sapiranga', 'cachoeira do sul', 'farroupilha', 'torres',
    'capao da canoa', 'camaqua', 'vacaria', 'sao gabriel',
}

_SIGLAS_OUTROS_ESTADOS = {
    'sp', 'rj', 'mg', 'ba', 'sc', 'pr', 'go', 'df', 'ce', 'pe',
    'am', 'pa', 'mt', 'ms', 'es', 'ma', 'pi', 'rn', 'pb', 'al',
    'se', 'ro', 'ac', 'ap', 'rr', 'to',
}


def _fmt_preco(valor: float) -> str:
    return f"R$ {valor:.2f}".replace('.', ',')


def _formatar_portfolio(items: list, titulo: str = "Temos varios modelos disponiveis! Confira:") -> str:
    linhas = [titulo]
    for i, item in enumerate(items, 1):
        preco = _fmt_preco(item.price) if item.price else "consultar"
        promo = " *[PROMO!]*" if item.is_promo else ""
        linhas.append(f"{i}. {item.label} — {preco}{promo}")
    linhas.append("\nQual desses te interessa? Me diga o numero ou o nome!")
    return "\n".join(linhas)


def _match_portfolio_item(texto: str, portfolio: list):
    """Matches user reply to a portfolio item by number or name. Returns PortfolioItem or None."""
    num_match = re.search(r'\b(\d+)\b', texto)
    if num_match:
        idx = int(num_match.group(1)) - 1
        if 0 <= idx < len(portfolio):
            return portfolio[idx]

    texto_norm = normalize_basic(texto)
    best = None
    best_score = 0
    for item in portfolio:
        item_norm = normalize_basic(item.label)
        words = set(texto_norm.split())
        item_words = set(item_norm.split())
        overlap = len(words & item_words)
        if overlap > best_score:
            best_score = overlap
            best = item
    return best if best_score > 0 else None


def _carrinho_total(carrinho: list) -> float:
    return sum(item.get('price', 0.0) for item in carrinho)


def _formatar_carrinho(carrinho: list, frete_val: float = None, frete_regiao: str = None) -> str:
    if not carrinho:
        return "Seu carrinho esta vazio."
    linhas = ["*Resumo do seu pedido:*"]
    for i, item in enumerate(carrinho, 1):
        linhas.append(f"{i}. {item['label']} — {_fmt_preco(item.get('price', 0.0))}")
    subtotal = _carrinho_total(carrinho)
    linhas.append("—————")
    if frete_val is not None:
        linhas.append(f"Subtotal: {_fmt_preco(subtotal)}")
        linhas.append(f"Frete para {frete_regiao}: {_fmt_preco(frete_val)}")
        linhas.append(f"*Total: {_fmt_preco(subtotal + frete_val)}*")
    else:
        linhas.append(f"*Subtotal: {_fmt_preco(subtotal)}*")
    return "\n".join(linhas)


def _calcular_frete(texto: str):
    """Retorna (valor_frete, descricao_regiao) ou (None, None) se não identificado."""
    texto_norm = normalize_basic(texto or '')

    cep_match = re.search(r'\b(\d{5})-?\d{0,3}\b', texto or '')
    if cep_match:
        cep_num = int(cep_match.group(1))
        if 90000 <= cep_num <= 99999:
            return 10.0, 'Rio Grande do Sul'
        return 20.0, 'fora do Rio Grande do Sul'

    if re.search(r'\brs\b', texto_norm):
        return 10.0, 'Rio Grande do Sul'
    for sigla in _SIGLAS_OUTROS_ESTADOS:
        if re.search(rf'\b{re.escape(sigla)}\b', texto_norm):
            return 20.0, 'fora do Rio Grande do Sul'

    for cidade in _RS_CIDADES:
        if cidade in texto_norm:
            return 10.0, 'Rio Grande do Sul'

    return None, None


def _extrair_query_produto(texto: str) -> str:
    normalizado = normalize_basic(texto)
    if not normalizado:
        return ''
    tokens = [token for token in normalizado.split() if token not in _PRODUCT_QUERY_STOPWORDS]
    if not tokens:
        tokens = normalizado.split()
    return ' '.join(tokens).strip()


def _formatar_resposta_produto(
    resultado: ProductSearchResult,
    query: str,
    respostas,
    debug: bool = False,
) -> str:
    if resultado.error:
        if debug:
            print(f"[DEBUG] Busca produto falhou: {resultado.error}")
        return 'Não consegui consultar o catálogo agora, tente novamente em instantes.'

    if not resultado.matches:
        return respostas.get('olhar') or 'Não encontrei esse produto ainda, dá uma olhada no nosso site.'

    top = resultado.matches[0]
    preco_txt = f" | *Preco: {_fmt_preco(top.price)}*" if top.price else ''

    if resultado.confidence == 'high' and top.purchase_url:
        return f"Encontrei *{top.label}*{preco_txt}\n{top.purchase_url}"

    if resultado.confidence == 'medium':
        sugestoes = []
        for match in resultado.matches[:3]:
            p = f" ({_fmt_preco(match.price)})" if match.price else ''
            if match.purchase_url:
                sugestoes.append(f"- {match.label}{p}: {match.purchase_url}")
            else:
                sugestoes.append(f"- {match.label}{p}")
        sugestoes_texto = '\n'.join(sugestoes)
        retorno = (
            "Encontrei algumas opcoes parecidas:\n"
            f"{sugestoes_texto}\n"
            "Qual dessas combina com o que voce procura?"
        )
        return retorno

    fallback = respostas.get('olhar') or 'Posso te encaminhar nosso site: www.vzforeal.com'
    if debug and top.purchase_url:
        print(
            f"[DEBUG] Confiança baixa para '{query}'. Top score={top.tfidf_score:.3f} "
            f"lexical={top.lexical_score}"
        )
    return fallback


def _responder_intencao_produto(entradas, respostas, debug=False):
    for entrada in entradas:
        query = _extrair_query_produto(entrada)
        if not query:
            continue
        tokens = query.split()
        if (len(tokens) == 1 and (tokens[0] in _GENERIC_PRODUCT_TERMS or len(tokens[0]) < 4)):
            if debug:
                print(f"[DEBUG] Query produto descartada (genérica): '{query}'")
            continue
        resultado = search_products_hybrid(query, top_k=3, debug=debug)
        resposta = _formatar_resposta_produto(resultado, query, respostas, debug=debug)
        if resposta:
            return resposta
    return respostas.get('olhar') or 'Não encontrei nada agora, veja nosso site.'


def _responder_produto_com_estado(entradas, respostas, debug=False):
    """Como _responder_intencao_produto, mas também retorna matches e flag de confiança média."""
    for entrada in entradas:
        query = _extrair_query_produto(entrada)
        if not query:
            continue
        tokens = query.split()
        if len(tokens) == 1 and (tokens[0] in _GENERIC_PRODUCT_TERMS or len(tokens[0]) < 4):
            if debug:
                print(f"[DEBUG] Query produto descartada (genérica): '{query}'")
            continue
        resultado = search_products_hybrid(query, top_k=3, debug=debug)
        resposta = _formatar_resposta_produto(resultado, query, respostas, debug=debug)
        is_medium = resultado.confidence == 'medium' and bool(resultado.matches)
        matches = resultado.matches or []
        if resposta:
            return resposta, matches, is_medium
    fallback = respostas.get('olhar') or 'Nao encontrei nada agora, veja nosso site.'
    return fallback, [], False


# Classe ConversaBot para gerar respostas dinâmicas
class ConversaBot:
    def __init__(self, url, timeout=15):
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                self.codigo_html = response.read()  # bytes
        except urllib.error.HTTPError as e:
            # Ex.: 403/404 â€” vocÃª pode logar e reerguer a exceção
            raise RuntimeError(f"HTTPError {e.code} ao acessar {url}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Erro de rede ao acessar {url}: {e.reason}") from e

        # Parser do BeautifulSoup (usa lxml se disponí­vel)
        self.html_processado = bs.BeautifulSoup(self.codigo_html, "lxml")
        self.texto = self._extrair_texto()

        # Tokenização e processamento
        self.sentencas = nltk.sent_tokenize(self.texto, language='portuguese')
        self.saudacoes_entrada = ("olá", "bom dia", "boa tarde", "boa noite", "oi", "como vai", "e aí­", "oii", "ola", "Oi", "eae", "qvc", "tudo bem?", "qual a boa?", "oiii", "oi td bem")
        self.saudacoes_respostas = ["E aí, Sou o vz-bot-tr1", "E aí­, espero que esteja tudo bem contigo", "oi! Sou o vz-bot-tr1", "Oie", "Seja bem vindo, Sou o vz-bot-tr1, em que posso te ajudar?", "E aí­! Sou o vz-bot-tr1, espero que esteja em paz"]
        self.n_messages = 0  # Inicializa o contador de mensagens

    def _extrair_texto(self):
        paragrafos = self.html_processado.find_all('p')
        texto = ''
        for p in paragrafos:
            texto += p.text

        # Normaliza o texto
        texto = texto.lower()
        texto = re.sub(r'\[[0-9]*\]', ' ', texto)
        texto = re.sub(r'\s+', ' ', texto)

        return texto

    # Função de Stemming
    def stemming(self, tokens):
        stemmer = nltk.stem.RSLPStemmer()
        novotexto = [stemmer.stem(token.lower()) for token in tokens]
        return novotexto

    # Remove pontuação de um documento
    def _remove_pontuacao(self, documento):
        removePontuacao = dict((ord(punctuation), None) for punctuation in string.punctuation)
        return documento.lower().translate(removePontuacao)

    # Preprocessa o texto removendo pontuações e aplicando stemming
    def preprocessa(self, documento):
        tokens = nltk.word_tokenize(self._remove_pontuacao(documento), language='portuguese')
        return self.stemming(tokens)

    # Gera respostas com base na similaridade
    def gerador_respostas(self, entrada_usuario):
        self.sentencas.append(entrada_usuario)

        # Vetorização usando TF-IDF
        word_vectorizer = TfidfVectorizer(tokenizer=self.preprocessa, stop_words=stopwords.words('portuguese'))
        all_word_vectors = word_vectorizer.fit_transform(self.sentencas)

        # Calcula a similaridade
        similar_vector_values = cosine_similarity(all_word_vectors[-1], all_word_vectors)
        similar_sentence_number = similar_vector_values.argsort()[0][-2]

        matched_vector = similar_vector_values.flatten()
        matched_vector.sort()
        vector_matched = matched_vector[-2]

        # Verifica se encontrou uma resposta adequada
        resposta = "Não entendi o que você quis dizer" if vector_matched == 0 else self.sentencas[similar_sentence_number]

        # Remove a entrada do usuário
        self.sentencas.pop()
        return resposta


# Função principal do chatbot

def chatbot(keywords_dict, respostas, bot, root, debug=False):
    mensagens_armazenadas = []

    while root.bot_ativo:
        if not debug:
            try:
                debug = bool(int(os.environ.get('BOT_DEBUG', '0')))
            except Exception:
                debug = False
        try:
            chat_id = getattr(root, 'expected_chat', None) or root.get_current_chat_identifier()
        except Exception:
            chat_id = ''

        collection = root.collect_messages_for_processing(chat_id)
        collection = collection or {'messages': []}
        mensagens_coletadas = collection.get('messages', [])
        if debug:
            print(f"[DEBUG] Início ciclo. bot_ativo={root.bot_ativo}")
            print(f"[DEBUG] Chat atual: {chat_id or 'desconhecido'}")
            print(f"[DEBUG] mensagens_coletadas: {mensagens_coletadas}")

        if not mensagens_coletadas:
            if chat_id:
                root.finalize_chat_processing(chat_id, [], responded=False, anchor_info=collection)
            return

        mensagens_a_processar = [
            {'texto': msg.get('texto', ''), 'hora': msg.get('hora'), 'key': msg.get('key')}
            for msg in mensagens_coletadas
        ]

        if debug:
            print(f"[DEBUG] mensagens_a_processar: {mensagens_a_processar}")

        try:
            ident_global = chat_id or getattr(root, 'expected_chat', None) or root.get_current_chat_identifier()
        except Exception:
            ident_global = chat_id or 'desconhecido'
        if not hasattr(root, 'processed_msgs_map'):
            root.processed_msgs_map = {}
        processed_set = root.processed_msgs_map.setdefault(ident_global, set())

        if not hasattr(root, '_conversa_contexto'):
            root._conversa_contexto = {}
        ctx = root._conversa_contexto.setdefault(ident_global, {})
        ctx.setdefault('last_intent', None)
        ctx.setdefault('produto_matches', [])
        ctx.setdefault('aguarda_produto', False)
        ctx.setdefault('aguarda_frete', False)
        ctx.setdefault('produto_preco', 0.0)
        ctx.setdefault('produto_label', '')
        ctx.setdefault('produto_url', '')
        ctx.setdefault('aguarda_selecao_portfolio', False)
        ctx.setdefault('portfolio_exibido', [])
        ctx.setdefault('aguarda_comprar_ou_outros', False)
        ctx.setdefault('carrinho', [])
        ctx.setdefault('aguarda_finalizar_ou_mais', False)

        novas_entradas = []
        processed_keys = []

        for mensagem in mensagens_a_processar:
            entrada = str(mensagem.get('texto', '')).strip()
            if not entrada:
                continue
            hora_val = mensagem.get('hora')
            if isinstance(hora_val, datetime):
                hora_key = hora_val.strftime("%Y-%m-%dT%H:%M:%S")
            else:
                hora_key = str(hora_val) if hora_val is not None else ''
            msg_key = mensagem.get('key') or f"fallback|{entrada.casefold()}|{hora_key}"
            chave = ('key', msg_key)
            if chave in processed_set:
                if debug:
                    print(f"[DEBUG] Ignorando repetida (já processada): '{entrada}'")
                continue
            try:
                ident = ident_global
                root.log_conversa('cliente', ident, entrada)
            except Exception:
                pass
            processed_set.add(chave)
            processed_keys.append(msg_key)
            novas_entradas.append({'texto': entrada, 'hora_key': hora_key, 'key': msg_key})

        if debug:
            print(f"[DEBUG] novas_entradas: {[item['texto'] for item in novas_entradas]}")

        if not novas_entradas:
            root.finalize_chat_processing(chat_id, [], responded=False, anchor_info=collection)
            return

        sentidos = {}
        for entrada_info in novas_entradas:
            texto = entrada_info['texto']
            matched_intent = None
            for intent in _INTENT_PRIORITY:
                pattern = keywords_dict.get(intent)
                if pattern and pattern.search(texto):
                    if debug:
                        print(f"[DEBUG] Intenção encontrada: {intent} para '{texto}'")
                    matched_intent = intent
                    break
            if not matched_intent:
                for intent, pattern in keywords_dict.items():
                    if intent in _INTENT_PRIORITY:
                        continue
                    if pattern.search(texto):
                        if debug:
                            print(f"[DEBUG] Intenção encontrada (fallback ordem): {intent} para '{texto}'")
                        matched_intent = intent
                        break
            if matched_intent == 'produto':
                categoria = 'produto'
            elif matched_intent and matched_intent in respostas:
                categoria = matched_intent
            else:
                categoria = 'wiki'
                if not matched_intent and debug:
                    print(f"[DEBUG] Intent fallback 'wiki' para '{texto}'")
            if debug:
                print(f"[DEBUG] Intent categorizada: {categoria} para '{texto}'")
            sentidos.setdefault(categoria, []).append(entrada_info)

        if debug:
            resumo_sentidos = {cat: [info['texto'] for info in entradas] for cat, entradas in sentidos.items()}
            print(f"[DEBUG] sentidos agrupados: {resumo_sentidos}")

        # --- Estado: aguardando confirmação de compra ---
        if ctx.get('aguarda_comprar_ou_outros') and novas_entradas and 'produto' not in sentidos and 'destaque' not in sentidos:
            texto_resp = ' '.join(info['texto'] for info in novas_entradas)
            norm_resp = normalize_basic(texto_resp)
            quer_comprar = bool(re.search(r'\b(comprar|compra|sim|quero|pode|ok|link|url|finalizar|compro|confirmar|confirmo)\b', norm_resp))
            quer_outros = bool(re.search(r'\b(outros|outro|mais|catalogo|lista|ver|nao|nao quero|negativo|outro modelo|cancelar)\b', norm_resp))
            if quer_comprar:
                carrinho = ctx.get('carrinho', [])
                urls = [item['url'] for item in carrinho if item.get('url')]
                if not urls:
                    url_fb = ctx.get('produto_url', '')
                    if url_fb:
                        urls = [url_fb]
                if urls:
                    links_txt = '\n'.join(f"• {u}" for u in urls)
                    resposta_compra = f'Perfeito! Aqui estao os links para finalizar:\n{links_txt}'
                else:
                    resposta_compra = 'Acesse nosso site para finalizar: www.vzforeal.com'
                ctx['aguarda_comprar_ou_outros'] = False
                ctx['carrinho'] = []
                ctx['last_intent'] = 'compra_confirmada'
                _pausa_natural(resposta_compra)
                root.enviar_mensagem(resposta_compra)
                try:
                    root.log_conversa('bot', ident_global, resposta_compra)
                except Exception:
                    pass
                processed_keys_unique = list({key for key in processed_keys if key})
                root.finalize_chat_processing(chat_id, processed_keys_unique, responded=True, anchor_info=collection)
                return
            elif quer_outros:
                ctx['aguarda_comprar_ou_outros'] = False
                portfolio = get_portfolio(max_items=6, debug=debug)
                if portfolio:
                    msg_portfolio = _formatar_portfolio(portfolio)
                    ctx['portfolio_exibido'] = portfolio
                    ctx['aguarda_selecao_portfolio'] = True
                    ctx['last_intent'] = 'produto'
                    _pausa_natural(msg_portfolio)
                    root.enviar_mensagem(msg_portfolio)
                    try:
                        root.log_conversa('bot', ident_global, msg_portfolio)
                    except Exception:
                        pass
                    processed_keys_unique = list({key for key in processed_keys if key})
                    root.finalize_chat_processing(chat_id, processed_keys_unique, responded=True, anchor_info=collection)
                    return
            else:
                reperguntar = 'Voce quer confirmar o pedido ou prefere ver outros modelos?'
                root.enviar_mensagem(reperguntar)
                try:
                    root.log_conversa('bot', ident_global, reperguntar)
                except Exception:
                    pass
                processed_keys_unique = list({key for key in processed_keys if key})
                root.finalize_chat_processing(chat_id, processed_keys_unique, responded=True, anchor_info=collection)
                return

        # --- Estado: aguardando seleção do portfólio ---
        if ctx.get('aguarda_selecao_portfolio') and novas_entradas and 'produto' not in sentidos and 'destaque' not in sentidos and 'saudacao' not in sentidos:
            texto_sel = ' '.join(info['texto'] for info in novas_entradas)
            portfolio = ctx.get('portfolio_exibido', [])
            selected = _match_portfolio_item(texto_sel, portfolio)
            if selected:
                ctx['aguarda_selecao_portfolio'] = False
                ctx['produto_label'] = selected.label
                ctx['produto_preco'] = selected.price
                ctx['produto_url'] = selected.url or ''
                ctx['aguarda_frete'] = True

                desc = None
                if selected.url:
                    try:
                        desc = get_product_description(selected.url, timeout=8)
                    except Exception:
                        pass

                msg_produto = f'Otima escolha! *{selected.label}*\nPreco: {_fmt_preco(selected.price)}'
                if desc:
                    msg_produto += f'\n\n_{desc}_'

                _pausa_natural(msg_produto)
                root.enviar_mensagem(msg_produto)
                try:
                    root.log_conversa('bot', ident_global, msg_produto)
                except Exception:
                    pass
                frete_msg = 'Qual sua cidade ou CEP para calcular o frete?'
                root.enviar_mensagem(frete_msg)
                try:
                    root.log_conversa('bot', ident_global, frete_msg)
                except Exception:
                    pass
                processed_keys_unique = list({key for key in processed_keys if key})
                root.finalize_chat_processing(chat_id, processed_keys_unique, responded=True, anchor_info=collection)
                return
            else:
                reperguntar = f'Nao entendi bem. Pode digitar o numero ou o nome do modelo?\n{_formatar_portfolio(portfolio)}'
                root.enviar_mensagem(reperguntar)
                try:
                    root.log_conversa('bot', ident_global, reperguntar)
                except Exception:
                    pass
                processed_keys_unique = list({key for key in processed_keys if key})
                root.finalize_chat_processing(chat_id, processed_keys_unique, responded=True, anchor_info=collection)
                return

        # Frete: se aguardando cidade/CEP e a mensagem não é sobre um novo produto
        if ctx.get('aguarda_frete') and novas_entradas and 'produto' not in sentidos:
            texto_frete = ' '.join(info['texto'] for info in novas_entradas)
            valor_frete, regiao = _calcular_frete(texto_frete)
            if valor_frete is not None:
                preco = ctx.get('produto_preco', 0.0)
                total = preco + valor_frete
                resposta_frete = (
                    f"Frete para {regiao}: {_fmt_preco(valor_frete)}\n"
                    f"Total (produto + frete): {_fmt_preco(total)}"
                )
                ctx['aguarda_frete'] = False
                ctx['last_intent'] = 'frete'
                if debug:
                    print(f"[DEBUG] Enviando frete: {resposta_frete}")
                root.enviar_mensagem(resposta_frete)
                try:
                    root.log_conversa('bot', ident_global, resposta_frete)
                except Exception:
                    pass
                comprar_msg = 'Voce gostaria de comprar agora ou prefere conhecer outros modelos?'
                root.enviar_mensagem(comprar_msg)
                try:
                    root.log_conversa('bot', ident_global, comprar_msg)
                except Exception:
                    pass
                ctx['aguarda_comprar_ou_outros'] = True
                processed_keys_unique = list({key for key in processed_keys if key})
                root.finalize_chat_processing(chat_id, processed_keys_unique, responded=True, anchor_info=collection)
                return

        respondeu_algo = False
        for categoria, entradas in sentidos.items():
            textos_categoria = [info['texto'] for info in entradas]
            if debug:
                print(f"[DEBUG] Respondendo categoria '{categoria}' com entradas: {textos_categoria}")

            resposta = ''

            if categoria == 'saudacao':
                periodo = _periodo_do_dia()
                resposta = random.choice(_VARS_SAUDACAO).format(periodo=periodo)
                _pausa_natural(resposta)
                if debug:
                    print(f"[DEBUG] Enviando resposta: {resposta}")
                root.enviar_mensagem(resposta)
                try:
                    root.log_conversa('bot', ident_global, resposta)
                except Exception:
                    pass
                respondeu_algo = True
                if len(sentidos) == 1:
                    follow_up = random.choice(_VARS_FOLLOW_UP)
                    _pausa_natural(follow_up)
                    root.enviar_mensagem(follow_up)
                    try:
                        root.log_conversa('bot', ident_global, follow_up)
                    except Exception:
                        pass
                ctx['last_intent'] = 'saudacao'
                continue

            elif categoria == 'destaque':
                featured = get_featured_products(debug=debug)
                if featured:
                    titulo = 'Nossas lupas e oculos em promocao:'
                    resposta = _formatar_portfolio(featured, titulo=titulo)
                    ctx['portfolio_exibido'] = featured
                    ctx['aguarda_selecao_portfolio'] = True
                    ctx['last_intent'] = 'destaque'
                else:
                    resposta = 'No momento nao temos promocoes ativas, mas confira nosso site: www.vzforeal.com'
                    ctx['last_intent'] = 'destaque'

            elif categoria == 'produto':
                # Mostrar portfólio primeiro; busca direta apenas se já está em seleção
                if not ctx.get('aguarda_selecao_portfolio'):
                    portfolio = get_portfolio(max_items=6, debug=debug)
                    if portfolio:
                        resposta = _formatar_portfolio(portfolio)
                        ctx['portfolio_exibido'] = portfolio
                        ctx['aguarda_selecao_portfolio'] = True
                        ctx['last_intent'] = 'produto'
                        _pausa_natural(resposta)
                        if debug:
                            print(f"[DEBUG] Exibindo portfolio: {resposta}")
                        root.enviar_mensagem(resposta)
                        try:
                            root.log_conversa('bot', ident_global, resposta)
                        except Exception:
                            pass
                        respondeu_algo = True
                        continue
                # Portfólio já exibido; usuário deu mais detalhes → busca direta
                resposta, matches, is_medium = _responder_produto_com_estado(textos_categoria, respostas, debug=debug)
                ctx['last_intent'] = 'produto'
                ctx['produto_matches'] = matches
                ctx['aguarda_produto'] = is_medium
                ctx['aguarda_selecao_portfolio'] = False
                if matches:
                    top = matches[0]
                    ctx['produto_preco'] = getattr(top, 'price', 0.0)
                    ctx['produto_label'] = top.label
                    ctx['produto_url'] = top.purchase_url or ''
                    ctx['aguarda_frete'] = True

            elif categoria == 'agradecimento':
                resposta = random.choice(_VARS_AGRADECIMENTO)
                ctx['last_intent'] = 'agradecimento'

            elif categoria == 'despedida':
                resposta = random.choice(_VARS_DESPEDIDA)
                ctx['last_intent'] = 'despedida'

            elif categoria == 'confirmacao':
                if ctx.get('aguarda_produto') and ctx.get('produto_matches'):
                    top = ctx['produto_matches'][0]
                    url = getattr(top, 'purchase_url', None) or ''
                    if url:
                        resposta = f'Perfeito! Aqui esta o link: {url}'
                    else:
                        resposta = respostas.get('olhar') or 'Confira nosso site: www.vzforeal.com'
                    ctx['aguarda_produto'] = False
                else:
                    resposta = 'Certo! Em que mais posso te ajudar?'
                ctx['last_intent'] = 'confirmacao'

            elif categoria == 'negacao':
                if ctx.get('aguarda_produto'):
                    resposta = 'Tudo bem! Me conta mais sobre o que voce procura.'
                    ctx['aguarda_produto'] = False
                else:
                    resposta = 'Entendido! Se precisar de algo, e so chamar.'
                ctx['last_intent'] = 'negacao'

            elif categoria in ('horario_atendimento', 'olhar'):
                resposta = respostas.get(categoria) or ''
                ctx['last_intent'] = categoria

            else:
                resposta = random.choice(_VARS_DESCONHECIDO)
                ctx['last_intent'] = 'wiki'

            if resposta:
                _pausa_natural(resposta)
                if debug:
                    print(f"[DEBUG] Enviando resposta: {resposta}")
                root.enviar_mensagem(resposta)
                try:
                    root.log_conversa('bot', ident_global, resposta)
                except Exception:
                    pass
                respondeu_algo = True
                if categoria == 'produto' and ctx.get('aguarda_frete'):
                    frete_msg = 'Qual sua cidade ou CEP para calcular o frete?'
                    root.enviar_mensagem(frete_msg)
                    try:
                        root.log_conversa('bot', ident_global, frete_msg)
                    except Exception:
                        pass

        processed_keys_unique = list({key for key in processed_keys if key})
        root.finalize_chat_processing(chat_id, processed_keys_unique, responded=respondeu_algo, anchor_info=collection)
        return