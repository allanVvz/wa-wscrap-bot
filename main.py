from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
from mensages import *
from selenium.common.exceptions import NoSuchElementException
from datetime import datetime

CHROMEDRIVER_PATH = '/usr/bin/chromedriver'  # Atualize com o caminho do seu chromedriver


class WhatsAppBot:
    def __init__(self):
        # Configurações do Chrome
        options = Options()
        options.add_argument(
            'user-data-dir=./User_Data')  # Salva os dados do usuário para evitar escanear o QR Code novamente

        # Inicializa o WebDriver
        self.driver = webdriver.Chrome(executable_path=CHROMEDRIVER_PATH, options=options)
        self.driver.get('https://web.whatsapp.com/')
        input('Pressione Enter após escanear o QR Code ou após a página carregar completamente\n')

    def buscar_contato(self, nome_contato):
        try:
            # Busca o campo de pesquisa e insere o nome do contato
            self.caixa_de_pesquisa = self.driver.find_element(By.CSS_SELECTOR, "div[contenteditable='true'][aria-label='Pesquisar']")
            self.caixa_de_pesquisa.send_keys(nome_contato)
            time.sleep(2)
            # Seleciona o contato baseado nas classes fornecidas
            contato_seletor =f"span[title='{nome_contato}']"
            self.contato = self.driver.find_element(By.CSS_SELECTOR, contato_seletor)
            self.contato.click()
            time.sleep(2)

        except Exception as e:
            print(f"Erro ao buscar contato: {e}")

    def buscar_novas_mensagens(self):
        qMsg = 0
        #self.icone = self.driver.find_element(By.CSS_SELECTOR, 'span[aria-label]')
        #self.icone = self.driver.find_element(By.CSS_SELECTOR,  'span[aria-label="1 mensagem não lida"], span[aria-label="2 mensagens não lidas"]')
        for i in range(1, 10):  # Ajuste o range de acordo com o número máximo de mensagens que você deseja buscar
            try:
                # Tenta encontrar o elemento com "i mensagem(s) não lida(s)"
                self.icone = self.driver.find_element(By.CSS_SELECTOR,
                                                      f'span[aria-label="1 mensagem não lida"], span[aria-label="{i} mensagens não lidas"]')
                print(f"Elemento encontrado com {i} mensagem(s) não lida(s)")
                break  # Se o elemento for encontrado, interrompe o loop
            except NoSuchElementException:
                # Se não encontrar o elemento, continua o loop para o próximo valor de i
                continue
        else:
            print("Nenhuma mensagem não lida encontrada.")
        self.icone.click()
        return

    # def last_message(self):
    #     # Procura o elemento que contém a última mensagem
    #     #elemento_ultima_mensagem = self.driver.find_element(By.CSS_SELECTOR, 'span[dir="ltr"]')
    #     elemento_ultima_mensagem = self.driver.find_element(By.CSS_SELECTOR, 'span[dir="ltr"][class="_ao3e selectable-text copyable-text"]')
    #     # Lê o texto da última mensagem e atribui à variável 'self.ultima_mensagem'
    #     self.ultima_mensagem = elemento_ultima_mensagem.text
    #     return self.ultima_mensagem

    def last_two_messages(self):
        try:
            # Encontra todos os elementos que representam mensagens, ordenando pelas mais recentes
            elementos_mensagens = self.driver.find_elements(By.CSS_SELECTOR, 'div.copyable-text[data-pre-plain-text]')

            # Verifica se há pelo menos 2 mensagens
            if len(elementos_mensagens) >= 2:
                # Extrai as duas últimas mensagens
                ultimas_mensagens = elementos_mensagens[-2:]  # Pega as duas últimas mensagens

                # Lista para armazenar as mensagens e suas horas
                mensagens = []

                # Itera pelas duas últimas mensagens
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

                # Retorna as duas mensagens mais recentes
                return mensagens

            else:
                print("Menos de duas mensagens encontradas.")
                return []

        except NoSuchElementException:
            print("Nenhuma nova mensagem encontrada.")
            return []


    def enviar_mensagem(self, mensagem):
        try:
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
    root = WhatsAppBot()
    time.sleep(2)
    root.buscar_novas_mensagens()
    time.sleep(2)

    url = 'https://pt.wikipedia.org/wiki/Oakley,_Inc.'
    bot = ConversaBot(url)

    mensagens = root.last_two_messages()
    for mensagem in mensagens:
        print(f"Mensagem: {mensagem['texto']}, Hora: {mensagem['hora']}")
        human_text = mensagem['texto']

        if human_text in ['obrigado', 'muito obrigado', 'agradecido']:
            print("valeu! falou!")
            root.enviar_mensagem("valeu! falou!")

        elif human_text in ["tchau", "não vou comprar agora"]:
            print("valeu! falou!")
            root.enviar_mensagem("valeu! falou!")
            break

        elif any(saudacao in human_text for saudacao in bot.saudacoes_entrada):
            print(random.choice(bot.saudacoes_respostas))
            root.enviar_mensagem(random.choice(bot.saudacoes_respostas))

        else:
            # Gera uma resposta baseada em similaridade
            root.enviar_mensagem(bot.gerador_respostas(human_text))



if __name__ == "__main__":
    main()


