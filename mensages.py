import re
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
from main import *

# Desativar avisos desnecessários
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)


# Função para baixar as dependências do NLTK
def download_nltk_resources():
    nltk.download('wordnet')
    nltk.download('omw')
    nltk.download('punkt')
    nltk.download('rslp')
    nltk.download('stopwords')


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
        lista_sinonimos[palavra].update(sinonimos)
    return lista_sinonimos


# Função para gerar dicionário de palavras-chave (intents)
def gerar_keywords(lista_sinonimos):
    keywords = {
        'saudacao': [],
        'horario_atendimento': [],
        'olhar': []
    }

    for sin in list(lista_sinonimos['olá']):
        keywords['saudacao'].append(f'.*\\b{sin}\\b.*')
    for sin in list(lista_sinonimos['horário']):
        keywords['horario_atendimento'].append(f'.*\\b{sin}\\b.*')
    for sin in list(lista_sinonimos['olhar']):
        keywords['olhar'].append(f'.*\\b{sin}\\b.*')

    return keywords


# Função para compilar as expressões regulares para cada intenção
def compilar_keywords(keywords):
    keywords_dict = {}
    for intent, keys in keywords.items():
        keywords_dict[intent] = re.compile('|'.join(keys))
    return keywords_dict


# Classe ConversaBot para gerar respostas dinâmicas
class ConversaBot:
    def __init__(self, url):
        self.codigo_html = urllib.request.urlopen(url).read()
        self.html_processado = bs.BeautifulSoup(self.codigo_html, 'lxml')
        self.texto = self._extrair_texto()

        # Tokenização e processamento
        self.sentencas = nltk.sent_tokenize(self.texto, language='portuguese')
        self.saudacoes_entrada = ("olá", "bom dia", "boa tarde", "boa noite", "oi", "como vai", "e aí", "oii", "ola", "Oi", "eae", "qvc", "tudo bem?", "qual a boa?", "oiii", "oi td bem")
        self.saudacoes_respostas = ["E aí, Sou o vz-bot-tr1", "E aí, espero que esteja tudo bem contigo", "oi! Sou o vz-bot-tr1", "Oie", "Seja bem-vindo, Sou o vz-bot-tr1, em que posso te ajudar?", "E aí! Sou o vz-bot-tr1, espero que esteja em paz"]
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
        resposta = "PROMOÇÃO ATÉ DIA 14" if vector_matched == 0 else self.sentencas[similar_sentence_number]

        # Remove a entrada do usuário
        self.sentencas.pop()
        return resposta


# Função principal do chatbot
def chatbot(keywords_dict, respostas, bot, root):
    mensagens_armazenadas = []

    while root.bot_ativo:
        # Chama o método last_two_messages, que também atualiza conversa_bot.n_messages
        mensagens = root.last_n_messages()

        # Verifica o número de mensagens armazenado no conversa_bot e limita o for loop
        max_mensagens = root.conversa_bot.n_messages

        # Limitar o número de mensagens a serem processadas de acordo com n_messages
        mensagens_a_processar = mensagens[:max_mensagens]  # Limita ao número de mensagens em n_messages
        contador_mensagens = 0

        # Verificar se a mensagem já foi lida e processar apenas as novas
        for mensagem in mensagens_a_processar:
            if mensagem not in mensagens_armazenadas:
                # Criar um identificador único da mensagem (por exemplo, texto + hora)
                identificador_unico = (mensagem['texto'], mensagem['hora'])

                # Processar apenas mensagens não armazenadas
                if identificador_unico not in mensagens_armazenadas:
                    mensagens_armazenadas.append(identificador_unico)  # Armazenar o identificador da nova mensagem
                    entrada = str(mensagem['texto'].lower())
                    print(f"Identificador: {identificador_unico}")
                else:
                    continue  # Ignorar mensagens repetidas

                print(f"Nova mensagem: {entrada}, Hora: {mensagem['hora']}")

                # Checar se o usuário quer sair
                if entrada == 'sair':
                    print("Obrigado pela visita.")
                    root.enviar_mensagem("Obrigado pela visita. Até logo!")
                    root.back_main()  # Fechar o WhatsApp
                    return  # Encerra o loop principal

                # Tentar encontrar a intenção correspondente
                matched_intent = None
                for intent, pattern in keywords_dict.items():
                    if re.search(pattern, entrada):
                        matched_intent = intent
                        break

                # Decidir qual chave de resposta usar
                if matched_intent in respostas:
                    key = matched_intent
                else:
                    key = 'padrao'

                # Enviar a resposta correspondente
                if key == 'padrao':
                    resposta = bot.gerador_respostas(entrada)
                else:
                    resposta = respostas[key]

                root.enviar_mensagem(resposta)

                # Incrementar o contador de mensagens processadas
                contador_mensagens += 1

            # Verificar se já processou o número máximo de mensagens (n_messages)
            if contador_mensagens >= max_mensagens:
                print(f"Limite de {max_mensagens} mensagens alcançado. Fechando o WhatsApp.")
                root.back_main()  # volta para a conversa padrão
                #return  # Encerra o loop principal