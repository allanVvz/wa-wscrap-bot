from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
from mensages import *
from selenium.common.exceptions import NoSuchElementException
from datetime import datetime

CHROMEDRIVER_PATH = '/usr/bin/chromedriver'  # Atualize com o caminho do seu chromedriver


class WhatsAppBot:
    def __init__(self, conversa_bot):
        # Configurações do Chrome
        options = Options()
        options.add_argument(
            'user-data-dir=./User_Data')  # Salva os dados do usuário para evitar escanear o QR Code novamente

        # Inicializa o WebDriver
        self.driver = webdriver.Chrome(executable_path=CHROMEDRIVER_PATH, options=options)
        self.driver.get('https://web.whatsapp.com/')
        input('Pressione Enter após escanear o QR Code ou após a página carregar completamente\n')
        self.conversa_bot = conversa_bot

        # Define o status do bot
        self.bot_ativo = True

    def buscar_contato(self, nome_contato):
        try:
            # Busca o campo de pesquisa e insere o nome do contato
            self.caixa_de_pesquisa = self.driver.find_element(By.CSS_SELECTOR, "div[contenteditable='true'][aria-label='Pesquisar']")
            self.caixa_de_pesquisa.send_keys(nome_contato)
            time.sleep(2)
            # Seleciona o contato baseado nas classes fornecidas
            contato_seletor =f"span[title='{nome_contato}']"
            self.contato = self.driver.find_element(By.CSS_SELECTOR, contato_seletor)
            self.bot_ativo = True
            self.contato.click()
            time.sleep(2)

        except Exception as e:
            print(f"Erro ao buscar contato: {e}")

    def buscar_novas_mensagens(self, nomes_conversas):
        """
        Busca e clica em conversas com nomes específicos e verifica se há mensagens não lidas.
        :param nomes_conversas: Lista de nomes das conversas que deseja selecionar
        """
        self.conversa_bot.n_messages = 0

        for nome in nomes_conversas:
            try:
                # Localiza o elemento de uma conversa com o nome desejado
                contato_seletor = f"span[title='{nome}']"
                self.icone = self.driver.find_element(By.CSS_SELECTOR, contato_seletor)
                print(f"Conversa encontrada com o nome: {nome}")

                # Verifica se há mensagens não lidas para essa conversa
                for i in range(1, 10):  # Ajuste o range de acordo com o número máximo de mensagens que deseja buscar
                    try:
                        # Tenta encontrar o elemento que indica "i mensagem(s) não lida(s)"
                        self.icone = self.driver.find_element(By.CSS_SELECTOR,
                                                              f'span[aria-label="1 mensagem não lida"], span[aria-label="{i} mensagens não lidas"]')
                        print(f"Elemento encontrado com {i} mensagem(s) não lida(s)")
                        self.conversa_bot.n_messages = i
                        break  # Se o elemento for encontrado, interrompe o loop
                    except NoSuchElementException:
                        # Se não encontrar o elemento, continua o loop para o próximo valor de i
                        continue
                else:
                    print("Nenhuma mensagem não lida encontrada.")

                # Clica na conversa
                self.icone.click()
                return  # Sai do método após encontrar e clicar na conversa

            except NoSuchElementException:
                # Se o nome da conversa não for encontrado, continua para o próximo nome
                print(f"Conversa com o nome {nome} não encontrada.")
                continue

    def last_n_messages(self):
        try:
            # Encontra todos os elementos que representam mensagens, ordenando pelas mais recentes
            elementos_mensagens = self.driver.find_elements(By.CSS_SELECTOR, 'div.copyable-text[data-pre-plain-text]')

            # Verifica se há pelo menos n_messages mensagens
            if len(elementos_mensagens) >= self.conversa_bot.n_messages:
                # Extrai as últimas n_messages mensagens
                ultimas_mensagens = elementos_mensagens[-self.conversa_bot.n_messages:]  # Pega as últimas n mensagens

                # Lista para armazenar as mensagens e suas horas
                mensagens = []

                # Itera pelas últimas n_messages
                for elemento in ultimas_mensagens:
                    # Extrai o texto da mensagem
                    mensagem_texto = elemento.find_element(By.CSS_SELECTOR, 'span[dir="ltr"]').text

                    # Extrai a hora e a data da mensagem do atributo 'data-pre-plain-text'
                    pre_plain_text = elemento.get_attribute('data-pre-plain-text')
                    mensagem_hora = pre_plain_text.split(']')[0][1:]  # Pega o horário e a data [HH:MM, DD/MM/YYYY]

                    # Converte a hora e a data da mensagem para datetime
                    mensagem_datetime = datetime.strptime(mensagem_hora, "%H:%M, %d/%m/%Y")

                    # Adiciona a mensagem e sua hora à lista
                    mensagens.append({
                        'texto': mensagem_texto,
                        'hora': mensagem_datetime
                    })

                # Retorna as últimas n mensagens
                print(f"mensagens: {mensagens}")
                return mensagens

            else:
                print(f"Menos de {self.conversa_bot.n_messages} mensagens encontradas.")
                return []

        except NoSuchElementException:
            print("Nenhuma nova mensagem encontrada.")
            return []

    def back_main(self):
        """
        Volta para a tela principal do WhatsApp e clica na primeira conversa da lista.
        """
        self.bot_ativo = False
        try:
            # Localiza o primeiro contato/conversa na lista de conversas do WhatsApp
            primeira_conversa = self.driver.find_element(By.CSS_SELECTOR,
                                                         "span[title='main']")  # Usando a estrutura da lista de conversas

            # Clica na primeira conversa
            primeira_conversa.click()
            print("Primeira conversa selecionada com sucesso.")
        except NoSuchElementException:
            print("Erro: Não foi possível encontrar a primeira conversa.")
        except Exception as e:
            print(f"Erro ao tentar voltar para a tela principal: {e}")


    def enviar_mensagem(self, mensagem):
        try:
            if not self.bot_ativo:
                print("Bot de mensagens está desativado.")
                return

            # Espera um tempo para garantir que o campo de mensagem esteja disponível
            time.sleep(2)

            # Encontra o campo de entrada de mensagem
            campo_mensagem = self.driver.find_element(By.CSS_SELECTOR, "div[aria-placeholder='Digite uma mensagem']")
            campo_mensagem.click()
            time.sleep(1)

            # Digita a mensagem no campo de texto
            campo_mensagem.send_keys(mensagem)
            time.sleep(1)

            # Envia a mensagem pressionando "Enter"
            campo_mensagem.send_keys("\n")
            time.sleep(1)

        except Exception as e:
            print(f"Erro ao enviar mensagem: {e}")


def main():
    # URL para carregar conteúdo para o ConversaBot
    url = "https://pt.wikipedia.org/wiki/Oakley,_Inc."  # URL de exemplo

    # Criar uma instância do bot de conversação
    bot = ConversaBot(url)

    root = WhatsAppBot(bot)
    time.sleep(2)

    download_nltk_resources()

    # Lista de palavras
    palavras = ['olá', 'horário', 'olhar']
    lista_sinonimos = gerar_lista_sinonimos(palavras)

    # Adicionar sinônimos manualmente
    sinonimos_adicionais = {
        'olá': {'oi'},
        'horário': {'hora'},
        'olhar' : {'comprar'}
    }
    lista_sinonimos = adicionar_sinonimos(lista_sinonimos, sinonimos_adicionais)

    # Gerar palavras-chave e compilar regex
    keywords = gerar_keywords(lista_sinonimos)
    keywords_dict = compilar_keywords(keywords)

    # Dicionário de respostas
    respostas = {
        'saudacao': random.choice(bot.saudacoes_respostas),
        'horario_atendimento': 'Nosso horário de funcionamento é a partir das 16h00 até às 23h00.',
        'olhar': 'Claro, você pode dar uma olhada em nosso site: www.vzforeal.com',
        'padrao': 'Desculpe, não entendi sua pergunta. Vou tentar responder com base no que sei:'
    }

    # Lista de nomes das conversas que você deseja buscar no WhatsApp
    nomes_das_conversas = ['Deia']

    while(True):
        # Chamar o método para buscar e selecionar as conversas com os nomes fornecidos
        root.buscar_novas_mensagens(nomes_das_conversas)

        time.sleep(2)
        # Iniciar o chatbot
        chatbot(keywords_dict, respostas, bot, root)



if __name__ == "__main__":
    main()


