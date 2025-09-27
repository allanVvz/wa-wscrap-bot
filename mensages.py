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
import warnings
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from nltk.corpus import stopwords

from product_search.indexer import ProductSearchResult, search_products_hybrid
from utils.text_normalizer import normalize_basic

# Desativar avisos desnecessários
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

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
    ]
    for termo in termos_produto:
        keywords['produto'].append(f'.*\\b{termo}\\b.*')

    # Não manter uma intent separada 'ola'; tratar tudo como 'saudacao'

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
    'produto',
    'saudacao',
    'horario_atendimento',
    'olhar',
)

_GENERIC_PRODUCT_TERMS = {
    'ajuda',
    'help',
    'site',
    'link',
    'horario',
    'atendimento',
}


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
    if resultado.confidence == 'high' and top.purchase_url:
        return f"Encontrei {top.label}. Você pode comprar aqui: {top.purchase_url}"

    if resultado.confidence == 'medium':
        sugestoes = []
        for match in resultado.matches[:3]:
            if match.purchase_url:
                sugestoes.append(f"- {match.label}: {match.purchase_url}")
            else:
                sugestoes.append(f"- {match.label}")
        sugestoes_texto = '\n'.join(sugestoes)
        retorno = (
            "Encontrei algumas opções parecidas:\n"
            f"{sugestoes_texto}\n"
            "Me avise qual dessas combina melhor com o que você procura."
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
    mensagens_armazenadas = []  # legado local (não usado para dedupe entre ciclos)

    while root.bot_ativo:
        if not debug:
            try:
                debug = bool(int(os.environ.get('BOT_DEBUG', '0')))
            except Exception:
                debug = False
        mensagens = root.last_n_messages()
        max_mensagens = root.conversa_bot.n_messages
        if debug:
            print(f"[DEBUG] Início ciclo. bot_ativo={root.bot_ativo}")
            try:
                ident_dbg = getattr(root, 'expected_chat', None) or root.get_current_chat_identifier()
            except Exception:
                ident_dbg = 'desconhecido'
            print(f"[DEBUG] Chat atual: {ident_dbg}")
            print(f"[DEBUG] last_n_messages(): {mensagens}")
            print(f"[DEBUG] contador n_messages alvo: {max_mensagens}")

        if not max_mensagens or max_mensagens <= 0:
            mensagens_recent = root.get_mensagens_apos_resposta()
            if mensagens_recent:
                mensagens_a_processar = mensagens_recent
                if debug:
                    print(f"[DEBUG] Fallback ancorado em message-out: {mensagens_recent}")
            else:
                textos_cli = root.get_ultimas_mensagens_cliente(1)
                if not textos_cli:
                    return
                mensagens_a_processar = [
                    {'texto': t, 'hora': None} for t in textos_cli if t
                ]
                if debug:
                    print(f"[DEBUG] Fallback ultimas mensagens cliente (sem anchor): {textos_cli}")
        else:
            mensagens_a_processar = mensagens[:max_mensagens]
        if debug:
            print(f"[DEBUG] mensagens_a_processar: {mensagens_a_processar}")
        novas_entradas = []

        # Mapa persistente de mensagens já processadas por conversa
        try:
            ident_global = getattr(root, 'expected_chat', None) or root.get_current_chat_identifier()
        except Exception:
            ident_global = 'desconhecido'
        if not hasattr(root, 'processed_msgs_map'):
            root.processed_msgs_map = {}
        processed_set = root.processed_msgs_map.setdefault(ident_global, set())

        for mensagem in mensagens_a_processar:
            # chave de dedupe: texto normalizado (não usar hora, que varia a cada fallback)
            entrada = str(mensagem.get('texto', '')).strip().lower()
            hora_val = mensagem.get('hora')
            if isinstance(hora_val, datetime):
                hora_key = hora_val.strftime("%Y-%m-%dT%H:%M")
            else:
                hora_key = str(hora_val) if hora_val is not None else ''
            chave = (entrada, hora_key)
            if not entrada:
                continue
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
            novas_entradas.append(entrada)
        if debug:
            print(f"[DEBUG] novas_entradas: {novas_entradas}")

        if not novas_entradas:
            return

        sentidos = {}
        for entrada in novas_entradas:
            matched_intent = None
            for intent in _INTENT_PRIORITY:
                pattern = keywords_dict.get(intent)
                if pattern and pattern.search(entrada):
                    if debug:
                        print(f"[DEBUG] Intenção encontrada: {intent} para '{entrada}'")
                    matched_intent = intent
                    break
            if not matched_intent:
                for intent, pattern in keywords_dict.items():
                    if intent in _INTENT_PRIORITY:
                        continue
                    if pattern.search(entrada):
                        if debug:
                            print(f"[DEBUG] Intenção encontrada (fallback ordem): {intent} para '{entrada}'")
                        matched_intent = intent
                        break
            if matched_intent == 'produto':
                categoria = 'produto'
            elif matched_intent and matched_intent in respostas:
                categoria = matched_intent
            else:
                categoria = 'wiki'
                if not matched_intent and debug:
                    print(f"[DEBUG] Intent fallback 'wiki' para '{entrada}'")
            if debug:
                print(f"[DEBUG] Intent categorizada: {categoria} para '{entrada}'")
            sentidos.setdefault(categoria, []).append(entrada)
        if debug:
            print(f"[DEBUG] sentidos agrupados: {sentidos}")

        try:
            ident = getattr(root, 'expected_chat', None) or root.get_current_chat_identifier()
            root.senses_map[ident] = sentidos
            root.senses_count[ident] = len(sentidos)
        except Exception:
            pass

        for categoria, entradas in sentidos.items():
            if debug:
                print(f"[DEBUG] Respondendo categoria '{categoria}' com entradas: {entradas}")
            if categoria == 'saudacao':
                resposta = random.choice(bot.saudacoes_respostas)
            elif categoria == 'produto':
                resposta = _responder_intencao_produto(entradas, respostas, debug=debug)
            elif categoria in ('horario_atendimento', 'olhar'):
                resposta = respostas.get(categoria) or ''
            else:
                combinado = ' '.join(entradas)
                resposta = bot.gerador_respostas(combinado)
            if resposta:
                if debug:
                    print(f"[DEBUG] Enviando resposta: {resposta}")
                root.enviar_mensagem(resposta)

        # Conclui o ciclo mantendo o bot ativo para próximas interações
        if debug:
            print("[DEBUG] Ciclo do chatbot concluído; bot permanece ativo.")
        return
