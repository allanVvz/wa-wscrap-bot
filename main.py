from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

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
    # Inicializa o bot do WhatsApp
    bot = WhatsAppBot()

    # Pergunta ao usuário o nome do contato
    nome_contato = input("Digite o nome do contato ou grupo: ")

    # Busca o contato no WhatsApp
    bot.buscar_contato(nome_contato)

    # Envia uma mensagem de saudação
    mensagem = "E aí! Sou o vz-bot-tr1, espero que esteja em paz :)"
    bot.enviar_mensagem(mensagem)


if __name__ == "__main__":
    main()
