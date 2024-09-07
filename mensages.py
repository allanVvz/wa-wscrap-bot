import nltk
nltk.download('punkt')
nltk.download('rslp')  # Stemming em pt-br
nltk.download('stopwords')  # Lista de stopwords
from nltk.corpus import stopwords
import numpy as np
import random
import string
import bs4 as bs
import urllib.request
import re
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class ConversaBot:
    def __init__(self, url):
        # Carrega e processa o conteúdo HTML da página fornecida
        self.codigo_html = urllib.request.urlopen(url).read()
        self.html_processado = bs.BeautifulSoup(self.codigo_html, 'lxml')
        self.texto = self._extrair_texto()

        # Tokenização e processamento
        self.sentencas = nltk.sent_tokenize(self.texto, language='portuguese')
        self.palavras = nltk.word_tokenize(self.texto, language='portuguese')
        self.saudacoes_entrada = ("olá", "bom dia", "boa tarde", "boa noite", "oi", "como vai", "e aí", "oii", "ola", "Oi")
        self.saudacoes_respostas = ["E aí, Sou o vz-bot-tr1", "E aí, espero que esteja tudo bem contigo", "oi! Sou o vz-bot-tr1", "Oie", "Seja bem-vindo,Sou o vz-bot-tr1, em que posso te ajudar?", "E aí! Sou o vz-bot-tr1, espero que esteja em paz"]

    def _extrair_texto(self):
        # Extrai e processa o texto do HTML
        paragrafos = self.html_processado.find_all('p')
        texto = ''
        for p in paragrafos:
            texto += p.text

        # Normaliza o texto
        texto = texto.lower()
        texto = re.sub(r'\[[0-9]*\]', ' ', texto)
        texto = re.sub(r'\s+', ' ', texto)

        return texto

    # Função de Stemming para processamento de tokens
    def stemming(self, tokens):
        stemmer = nltk.stem.RSLPStemmer()
        novotexto = []
        for token in tokens:
            novotexto.append(stemmer.stem(token.lower()))
        return novotexto

    # Remove pontuação de um texto
    def _remove_pontuacao(self, documento):
        removePontuacao = dict((ord(punctuation), None) for punctuation in string.punctuation)
        return documento.lower().translate(removePontuacao)

    # Preprocessa um documento (remove pontuação, faz stemming)
    def preprocessa(self, documento):
        tokens = nltk.word_tokenize(self._remove_pontuacao(documento), language='portuguese')
        return self.stemming(tokens)

    # Método para gerar respostas com base em saudações
    def gerar_saudacao(self, saudacao):
        for token in saudacao.split():
            if token.lower() in self.saudacoes_entrada:
                return random.choice(self.saudacoes_respostas)
        return "Desculpe, não entendi sua saudação."

    # Método para gerar respostas com base em similaridade
    def gerador_respostas(self, entrada_usuario):
        resposta = ''
        self.sentencas.append(entrada_usuario)  # Adiciona a entrada do usuário às sentenças

        # Vetorização das palavras usando TF-IDF
        word_vectorizer = TfidfVectorizer(tokenizer=self.preprocessa, stop_words=stopwords.words('portuguese'))
        all_word_vectors = word_vectorizer.fit_transform(self.sentencas)

        # Calcula a similaridade entre a entrada e as sentenças
        similar_vector_values = cosine_similarity(all_word_vectors[-1], all_word_vectors)
        similar_sentence_number = similar_vector_values.argsort()[0][-2]

        # Acha o vetor mais próximo
        matched_vector = similar_vector_values.flatten()
        matched_vector.sort()
        vector_matched = matched_vector[-2]

        # Verifica se encontrou uma resposta
        if vector_matched == 0:
            resposta = "PROMOÇÃO ATÉ DIA 14"
        else:
            resposta = self.sentencas[similar_sentence_number]

        # Remove a última sentença para não duplicar na próxima rodada
        self.sentencas.pop()
        return resposta
