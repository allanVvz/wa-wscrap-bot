# -*- coding: utf-8 -*-
#!/usr/bin/env python3
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from mensages import *
from selenium.common.exceptions import (
    NoSuchElementException,
    SessionNotCreatedException,
    StaleElementReferenceException,
    TimeoutException,
)
from datetime import datetime
import random
import os
import tempfile
import re
import unicodedata


class WhatsAppBot:
    ACTIVE_CHAT_SELECTOR = "#pane-side > div:nth-child(1) > div > div > div:nth-child(2) > div > div > div > div._ak8l._ap1_ > div._ak8o > div._ak8q > div > div > span"
    ALL_FILTER_SELECTOR = "#all-filter"
    UNREAD_FILTER_SELECTOR = "#unread-filter > div > div"
    DEFAULT_INACTIVITY_TIMEOUT = 5.0

    def __init__(self, conversa_bot):
        # Configuraçoes do Chrome
        def build_options(user_data_dir=None):
            opts = Options()
            # Flags de estabilidade e reduço de logs
            opts.add_argument('--remote-allow-origins=*')
            opts.add_argument('--disable-dev-shm-usage')
            opts.add_argument('--disable-gpu')
            # opts.add_argument('--no-sandbox')  # opcional
            opts.add_argument('--start-maximized')
            opts.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
            opts.add_experimental_option('useAutomationExtension', False)
            if user_data_dir:
                opts.add_argument(f"--user-data-dir={user_data_dir}")
                # opcional: usar perfil Default dentro do diretório
                opts.add_argument("--profile-directory=Default")
            return opts

        # Define diretório de perfil persistente com caminho absoluto
        persist_dir = os.path.abspath(os.path.join('.', 'User_Data'))
        os.makedirs(persist_dir, exist_ok=True)

        # Inicializa o WebDriver com tentativas e perfis distintos
        service = Service(ChromeDriverManager().install())
        last_error = None
        for attempt in range(1, 4):
            try:
                if attempt == 1:
                    options = build_options(persist_dir)
                elif attempt == 2:
                    # Tenta sem perfil persistente (perfil temporário limpo)
                    temp_dir = tempfile.mkdtemp(prefix='wa_web_profile_')
                    options = build_options(temp_dir)
                else:
                    # Tenta com depuraço remota e sem perfil
                    options = build_options(None)
                    options.add_argument('--remote-debugging-port=0')

                self.driver = webdriver.Chrome(service=service, options=options)
                break
            except SessionNotCreatedException as e:
                last_error = e
                time.sleep(1)
                continue
            except Exception as e:
                last_error = e
                time.sleep(1)
                continue
        else:
            raise RuntimeError(
                'Falha ao iniciar o Chrome WebDriver após múltiplas tentativas. '
                'Possi­veis causas: versão do Chrome incompati­vel com o chromedriver, perfil corrompido, ou polí­ticas locais. '
                f'Erro original: {last_error}'
            )

        self.driver.get('https://web.whatsapp.com/')
        try:
            WebDriverWait(self.driver, 12).until(
                EC.presence_of_element_located((By.ID, 'pane-side'))
            )
            print('Login detectado; seguindo o fluxo automaticamente.')
        except TimeoutException:
            try:
                WebDriverWait(self.driver, 60).until(
                    EC.presence_of_element_located((By.ID, 'pane-side'))
                )
                print('Login realizado; seguindo o fluxo.')
            except TimeoutException:
                input('Escaneie o QR Code e pressione Enter para continuar...\\n')
        self.conversa_bot = conversa_bot

        self.bot_ativo = True
        self.conversa_corrente_ativa = False
        self.conversa_corrente_nome = None
        self.conversa_corrente_last_seen = 0.0
        self.conversa_corrente_total_incoming = 0
        try:
            timeout_cfg = float(os.environ.get('CHAT_TIMEOUT_SECONDS', self.DEFAULT_INACTIVITY_TIMEOUT))
        except (TypeError, ValueError):
            timeout_cfg = self.DEFAULT_INACTIVITY_TIMEOUT
        self.timeout_conversa_corrente = max(timeout_cfg, 0.0)


    def _contar_mensagens_entrada(self):
        """Conta mensagens de entrada visiveis na conversa atual."""
        try:
            elementos = self.driver.find_elements(By.CSS_SELECTOR, "div.message-in")
            return len(elementos)
        except Exception:
            return self.conversa_corrente_total_incoming

    def buscar_contato(self, nome_contato):
        try:
            self.caixa_de_pesquisa = self.driver.find_element(By.CSS_SELECTOR, "div[contenteditable='true'][aria-label='Pesquisar']")
            self.caixa_de_pesquisa.send_keys(nome_contato)
            time.sleep(2)
            contato_seletor =f"span[title='{nome_contato}']"
            self.contato = self.driver.find_element(By.CSS_SELECTOR, contato_seletor)
            self.bot_ativo = True
            self.contato.click()
            time.sleep(2)

        except Exception as e:
            print(f"Erro ao buscar contato: {e}")

    def atualizar_conversa_corrente(self, alvo_nome):
        """Atualiza o indicador de conversa corrente com base no seletor informado."""
        alvo_normalizado = (alvo_nome or '').strip().lower()
        ativo_nome = ''
        try:
            ativo_elem = self.driver.find_element(By.CSS_SELECTOR, self.ACTIVE_CHAT_SELECTOR)
            ativo_nome = (ativo_elem.text or '').strip()
        except NoSuchElementException:
            pass
        ativo_normalizado = (ativo_nome or '').strip().lower()
        is_active = bool(alvo_normalizado and ativo_normalizado == alvo_normalizado)
        if is_active:
            if not self.conversa_corrente_ativa or self.conversa_corrente_nome != alvo_nome:
                self.conversa_corrente_total_incoming = self._contar_mensagens_entrada()
                self.conversa_corrente_last_seen = time.time()
            else:
                total_atual = self._contar_mensagens_entrada()
                if total_atual > self.conversa_corrente_total_incoming:
                    self.conversa_corrente_total_incoming = total_atual
                    self.conversa_corrente_last_seen = time.time()
            self.conversa_corrente_ativa = True
            self.conversa_corrente_nome = alvo_nome
        else:
            if self.conversa_corrente_nome == alvo_nome:
                self.conversa_corrente_ativa = False
                self.conversa_corrente_nome = None
                self.conversa_corrente_total_incoming = 0
                self.conversa_corrente_last_seen = 0.0
        return is_active

    def buscar_novas_mensagens(self, nomes_conversas):
        """
        Busca e clica em conversas com nomes específicos e verifica se há mensagens não lidas.
        :param nomes_conversas: Lista de nomes das conversas que deseja selecionar
        """
        self.conversa_bot.n_messages = 0

        for nome in nomes_conversas:
            if self.atualizar_conversa_corrente(nome):
                print(f"[DEBUG] Conversa '{nome}' esta ativa; fluxo alternativo sem badge.")
                self.conversa_bot.n_messages = 0
                return
            try:
                # Localiza o elemento da conversa pelo nome
                contato_seletor = f"span[title='{nome}']"
                conversa_element = self.driver.find_element(By.CSS_SELECTOR, contato_seletor)

                # Inicializa o contador de mensagens não lidas
                n_mensagens = 0

                # Procura pelo badge de mensagens não lidas dentro do elemento da conversa
                for i in range(1, 10):
                    try:
                        badge = conversa_element.find_element(
                            By.CSS_SELECTOR,
                            f'span[aria-label="1 mensagem não lida"], span[aria-label="{i} mensagens não lidas"]'
                        )
                        n_mensagens = i
                        print(f"Elemento encontrado com {i} mensagem(s) nao lida(s)")
                        break
                    except NoSuchElementException:
                        continue
                else:
                    pass  # não imprimir quando não houver não lidas

                # Atualiza o objeto de conversa com a quantidade de mensagens
                self.conversa_bot.n_messages = n_mensagens
                print(f"[DEBUG] Contador de nao lidas para '{nome}': {self.conversa_bot.n_messages}")
                if n_mensagens > 0:
                    print(f"Conversa encontrada com o nome: {nome}")

                # Clica na conversa correta (elemento principal, não o badge)
                conversa_element.click()
                self.conversa_corrente_ativa = True
                self.conversa_corrente_nome = nome
                self.conversa_corrente_last_seen = time.time()
                self.conversa_corrente_total_incoming = self._contar_mensagens_entrada()
                return  # Sai do método após clicar na conversa correta

            except NoSuchElementException:
                print(f"Conversa com o nome {nome} não encontrada.")
                continue

    def clicar_filtro_generico(self, seletor, descricao):
        """Clica em um filtro superior identificado pelo seletor informado."""
        try:
            alvo = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, seletor))
            )
            alvo.click()
            print(f"[DEBUG] Filtro '{descricao}' selecionado.")
            return True
        except Exception as e:
            print(f"[AVISO] Nao foi possivel selecionar o filtro '{descricao}': {type(e).__name__}: {e}")
            return False

    def clicar_filtro_nao_lidas(self):
        """
        Clica no filtro superior "mensagens não lidas".
        Seletor: #unread-filter > div > div
        """
        try:
            filtro = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, self.UNREAD_FILTER_SELECTOR))
            )
            filtro.click()
            print("Filtro 'mensagens não lidas' clicado.")
        except Exception as e:
            print(f"Não foi possã­vel clicar no filtro de não lidas: {e}")

    def checar_timeout_conversa_corrente(self):
        """Verifica se a conversa ativa excedeu o tempo de inatividade."""
        if not self.conversa_corrente_ativa:
            return
        limite = getattr(self, "timeout_conversa_corrente", self.DEFAULT_INACTIVITY_TIMEOUT)
        if limite <= 0:
            return
        ultimo = self.conversa_corrente_last_seen or 0.0
        if (time.time() - ultimo) >= limite:
            nome = self.conversa_corrente_nome or "desconhecida"
            print(f"[DEBUG] Timeout de inatividade atingido para '{nome}'. Alternando para conversa 'main'.")
            self.ir_para_conversa_main()

    def ir_para_conversa_main(self):
        """Alterna temporariamente para o filtro "tudo" e seleciona a conversa "main"."""
        if self.clicar_filtro_generico(self.ALL_FILTER_SELECTOR, "tudo"):
            try:
                main_chat = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "span[title='main']"))
                )
                main_chat.click()
                print("[DEBUG] Conversa 'main' clicada.")
            except Exception as e:
                print(f"[AVISO] Falha ao clicar na conversa 'main': {type(e).__name__}: {e}")
        time.sleep(1)
        self.clicar_filtro_nao_lidas()
        self.conversa_corrente_ativa = False
        self.conversa_corrente_nome = None
        self.conversa_corrente_total_incoming = 0
        self.conversa_corrente_last_seen = 0.0
        self.conversa_bot.n_messages = 0

    def last_n_messages(self):
        try:
            # Somente mensagens ENTRANTES do cliente
            seletor = "div.message-in div.copyable-text[data-pre-plain-text]"
            elementos_mensagens = self.driver.find_elements(By.CSS_SELECTOR, seletor)

            n = max(0, int(self.conversa_bot.n_messages or 0))
            if n <= 0:
                return []

            # Pega as últimas n mensagens de entrada; se houver menos, pega as existentes
            ultimas_mensagens = elementos_mensagens[-n:]

            mensagens = []
            for elemento in ultimas_mensagens:
                # Extrai o texto; se não houver span ltr, usa o texto bruto
                try:
                    mensagem_texto = elemento.find_element(By.CSS_SELECTOR, "span[dir='ltr']").text
                except NoSuchElementException:
                    mensagem_texto = (elemento.text or '').strip()

                # Extrai timestamp do atributo; se falhar, usa agora
                pre_plain_text = elemento.get_attribute('data-pre-plain-text') or ''
                try:
                    mensagem_hora = pre_plain_text.split(']')[0][1:]  # [HH:MM, DD/MM/YYYY]
                    mensagem_datetime = datetime.strptime(mensagem_hora, "%H:%M, %d/%m/%Y")
                except Exception:
                    mensagem_datetime = datetime.now()

                mensagens.append({'texto': mensagem_texto, 'hora': mensagem_datetime})
            print(f"[DEBUG] Lendo {len(mensagens)} mensagem(ns) com contador n_messages={n}")

            print(f"mensagens: {mensagens}")
            return mensagens

        except NoSuchElementException:
            print("Nenhuma nova mensagem encontrada (entrada).")
            return []

    def back_main(self):
        """
        Volta para a tela principal do WhatsApp e clica na primeira conversa da lista.
        """
        self.bot_ativo = False
        try:
            # Localiza o primeiro contato/conversa na lista de conversas do WhatsApp
            primeira_conversa = self.driver.find_element(By.CSS_SELECTOR, "span[title='main']")

            # Clica na primeira conversa
            primeira_conversa.click()
            print("Primeira conversa selecionada com sucesso.")
        except NoSuchElementException:
            print("Erro: Não foi possã­vel encontrar a primeira conversa.")
        except Exception as e:
            print(f"Erro ao tentar voltar para a tela principal: {e}")


    def enviar_mensagem(self, mensagem):
        try:
            if not self.bot_ativo:
                print("Bot de mensagens está desativado.")
                return

            # Espera um tempo para garantir que o campo de mensagem esteja disponí­vel
            time.sleep(2)

            campo_mensagem = self.driver.find_element(By.CSS_SELECTOR, "div[aria-placeholder='Digite uma mensagem']")
            campo_mensagem.click()
            time.sleep(1)

            try:
                nfkd = unicodedata.normalize('NFKD', mensagem or '')
                msg_ascii = nfkd.encode('ascii', 'ignore').decode('ascii')
            except Exception:
                msg_ascii = mensagem or ''
            campo_mensagem.send_keys(msg_ascii)
            time.sleep(1)

            campo_mensagem.send_keys("\n")
            time.sleep(1)

        except Exception as e:
            print(f"Erro ao enviar mensagem: {e}")

    def listar_contatos_nao_lidos(self):
        """
        Percorre a lista lateral de conversas e coleta apenas as que têm
        cí­rculo de mensagens não lidas. Retorna lista de dicts:
        { 'nome': str, 'nao_lidas': int, 'row': WebElement, 'badge': WebElement }.

        Baseado nos seletores fornecidos, usando buscas relativas por linha.
        """
        resultados = []
        try:
            pane = self.driver.find_element(By.ID, 'pane-side')
        except NoSuchElementException:
            print('[ERRO] pane-side não encontrado; verifique se a página carregou.')
            return resultados

        # Linhas de conversa (estrutura pode variar; tentamos duas formas)
        rows = pane.find_elements(By.CSS_SELECTOR, 'div > div > div > div')
        if not rows:
            rows = self.driver.find_elements(By.CSS_SELECTOR, '#pane-side > div:nth-child(1) > div > div > div')

        print(f"[DEBUG] Total de containers de conversa encontrados: {len(rows)}")

        # Para evitar duplicidade, acumulamos por nome sanitizado, mantendo maior 'nao_lidas'
        agregados = {}

        for row in rows:
            try:
                # Badge de não lidas (cí­rculo à direita)
                badge = row.find_element(By.CSS_SELECTOR, 'div._ak8l._ap1_ div._ak8j div._ak8i span:nth-child(1) > div > span > span')
                qtd_text = (badge.text or '').strip()
                if not qtd_text:
                    continue
                try:
                    qtd = int(qtd_text)
                except ValueError:
                    continue

                # Nome do contato
                nome_elem = None
                try:
                    nome_elem = row.find_element(By.CSS_SELECTOR, 'div._ak8l._ap1_ div._ak8o div._ak8q > div > div > span')
                except NoSuchElementException:
                    try:
                        nome_elem = row.find_element(By.CSS_SELECTOR, 'div._ak8l._ap1_ div._ak8o div._ak8q')
                    except NoSuchElementException:
                        nome_elem = None

                nome_raw = (nome_elem.text or '').strip() if nome_elem else ''

                # Sanitizaço: números de celular -> apenas dí­gitos; nomes -> sem pontuaço
                so_digitos = re.sub(r'\D', '', nome_raw)
                if len(so_digitos) >= 6:
                    nome_sanit = so_digitos
                else:
                    nome_sanit = re.sub(r'[^\w\s]', '', nome_raw).replace('_', ' ').strip()

                # Deduplicaço: agrupar pelo nome sanitizado, manter maior contagem
                existente = agregados.get(nome_sanit)
                if (existente is None) or (qtd > existente['nao_lidas']):
                    agregados[nome_sanit] = {'nome': nome_sanit, 'nao_lidas': qtd}
            except NoSuchElementException:
                continue
            except StaleElementReferenceException:
                continue
            except Exception as e:
                print(f"[AVISO] Falha ao varrer linha: {type(e).__name__}: {e}")
                continue

        resultados = list(agregados.values())
        print(f"[DEBUG] Contatos com não lidas (deduplicados): {len(resultados)}")
        return resultados

    def clicar_badge_por_nome(self, nome_sanit, tentativas=3):
        """
        Reencontra a linha do contato pelo texto e clica no badge (cí­rculo de não lidas)
        com retentativas para contornar StaleElementReference.
        """
        row_selector = "#pane-side > div:nth-child(1) > div > div > div"
        badge_rel = "div._ak8l._ap1_ div._ak8j div._ak8i span:nth-child(1) > div > span > span"
        for i in range(tentativas):
            try:
                pane = self.driver.find_element(By.ID, 'pane-side')
                rows = pane.find_elements(By.CSS_SELECTOR, row_selector)
                alvo = None
                for r in rows:
                    try:
                        if nome_sanit and (nome_sanit in (r.text or '')):
                            alvo = r
                            break
                    except StaleElementReferenceException:
                        continue
                if not alvo:
                    raise NoSuchElementException(f"Linha do contato não encontrada: {nome_sanit}")

                badge = alvo.find_element(By.CSS_SELECTOR, badge_rel)
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", badge)
                try:
                    badge.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", badge)
                return True
            except StaleElementReferenceException:
                if i == tentativas - 1:
                    print("[ERRO] Elemento ficou obsoleto repetidamente ao tentar clicar no badge.")
                    return False
                time.sleep(0.2)
            except Exception as e:
                if i == tentativas - 1:
                    print(f"[ERRO] Falha ao localizar/clicar badge de '{nome_sanit}': {type(e).__name__}: {e}")
                    return False
                time.sleep(0.2)

    def focar_caixa_texto(self):
        """
        Foca a caixa de texto da conversa aberta usando o seletor fornecido.
        Retorna True/False conforme sucesso.
        """
        selector = (
            "#main > footer > div.x1n2onr6.xhtitgo.x9f619.x78zum5.x1q0g3np.xuk3077.xjbqb8w.x1wiwyrm.xvc5jky.x11t971q.xquzyny.xnpuxes.copyable-area > "
            "div > span > div > div._ak1r > div > div.x1n2onr6.xh8yej3.xjdcl3y.lexical-rich-text-input > "
            "div.x1hx0egp.x6ikm8r.x1odjw0f.x1k6rcq7.x6prxxf > p"
        )
        try:
            box = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            box.click()
            self.caixa_texto = box
            print("[OK] Caixa de texto focada.")
            return True
        except TimeoutException:
            print("[ERRO] Caixa de texto não encontrada a tempo.")
            return False
        except Exception as e:
            print(f"[ERRO] Falha ao focar caixa de texto: {type(e).__name__}: {e}")
            return False

    def focar_caixa_texto_novo(self):
        """
        Foca a caixa de texto usando o seletor solicitado pelo usuário
        e fallbacks para contenteditable.
        """
        selectors = [
            "#main > footer > div.x1n2onr6.xhtitgo.x9f619.x78zum5.x1q0g3np.xuk3077.xjbqb8w.x1wiwyrm.xvc5jky.x11t971q.xquzyny.xnpuxes.copyable-area > div > span > div > div._ak1r > div [contenteditable='true']",
            "#main > footer > div.x1n2onr6.xhtitgo.x9f619.x78zum5.x1q0g3np.xuk3077.xjbqb8w.x1wiwyrm.xvc5jky.x11t971q.xquzyny.xnpuxes.copyable-area > div > span > div > div._ak1r > div",
            "div[aria-placeholder='Digite uma mensagem']",
            "#main footer [contenteditable='true']",
        ]
        last_err = None
        for sel in selectors:
            try:
                elem = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                target = elem
                try:
                    if elem.get_attribute('contenteditable') != 'true':
                        target = elem.find_element(By.CSS_SELECTOR, "[contenteditable='true']")
                except Exception:
                    pass
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
                try:
                    target.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", target)
                self.caixa_texto = target
                print("[OK] Caixa de texto focada (novo seletor).")
                return True
            except Exception as e:
                last_err = e
                continue
        print(f"[ERRO] Caixa de texto não encontrada com novo seletor: {type(last_err).__name__}: {last_err}")
        return False

    def get_ultimas_mensagens_cliente(self, n):
        """
        Lê as últimas N mensagens do cliente (entrantes) na conversa aberta.
        Tenta primeiro por '.message-in'; se não achar, faz fallback mais permissivo.
        """
        try:
            elems = self.driver.find_elements(By.CSS_SELECTOR, "div.message-in div.copyable-text[data-pre-plain-text] span[dir='ltr']")
            if not elems:
                elems = self.driver.find_elements(By.CSS_SELECTOR, "div.message-in span[dir='ltr']")
            total_incoming = self._contar_mensagens_entrada()
            if self.conversa_corrente_ativa and total_incoming > self.conversa_corrente_total_incoming:
                self.conversa_corrente_total_incoming = total_incoming
                self.conversa_corrente_last_seen = time.time()
            textos = [e.text.strip() for e in elems if e.text and e.text.strip()]
            return textos[-n:] if n and n > 0 else []
        except Exception as e:
            print(f"[ERRO] Falha ao coletar mensagens do cliente: {type(e).__name__}: {e}")
            return []

    def digitar_e_aguardar_envio(self, mensagem):
        """
        Escreve a mensagem no campo e aguarda Enter no terminal para enviar.
        """
        try:
            if not (self.focar_caixa_texto_novo() or self.focar_caixa_texto()):
                return False
            self.caixa_texto.send_keys(mensagem)
            input("Pressione Enter no terminal para enviar a mensagem...")
            self.caixa_texto.send_keys("\n")
            return True
        except Exception as e:
            print(f"[ERRO] Falha ao digitar/enviar: {type(e).__name__}: {e}")
            return False


def main():
    # garantir recursos NLTK
    try:
        download_nltk_resources()
    except Exception:
        pass

    # Criar ConversaBot (Wikipedia)
    url = os.environ.get('WIKI_URL', 'https://pt.wikipedia.org/wiki/Oakley,_Inc.')
    bot = ConversaBot(url)

    root = WhatsAppBot(bot)
    time.sleep(2)

    # Clicar no filtro superior "mensagens não lidas" e encerrar
    root.clicar_filtro_nao_lidas()
    time.sleep(1)

    # Listar contatos com não lidas e exibir debug
    contatos = root.listar_contatos_nao_lidos()
    if not contatos:
        print('Nenhum contato com mensagens não lidas encontrado.')
    else:
        print('Contatos com não lidas:')
        for idx, c in enumerate(contatos, start=1):
            print(f"[{idx}] nome/numero='{c['nome']}' | nao_lidas={c['nao_lidas']}")
    time.sleep(1)

    # Lista de palavras
    palavras = ['ola', 'horário', 'olhar']
    lista_sinonimos = gerar_lista_sinonimos(palavras)

    # Adicionar sinonimos manualmente (ASCII)
    sinonimos_adicionais = {
        'ola': {'oi'},
        'horario': {'hora'},
        'olhar': {'comprar'}
    }
    lista_sinonimos = adicionar_sinonimos(lista_sinonimos, sinonimos_adicionais)

    # Gerar palavras-chave e compilar regex
    keywords = gerar_keywords(lista_sinonimos)
    keywords_dict = compilar_keywords(keywords)

        # Dicionario de respostas (ASCII; saudacao decidida no chatbot)
    respostas = {
        'saudacao': None,
        'horario_atendimento': 'Nosso horario de funcionamento e de 16:00 as 23:00.',
        'olhar': 'Claro, voce pode ver nosso site: www.vzforeal.com',
        'padrao': 'Nao entendi bem. Vou tentar responder com base no que sei:'
    }

    # Lista de nomes das conversas que você deseja buscar no WhatsApp
    nomes_das_conversas = ['Iza']

    while(True):
        root.checar_timeout_conversa_corrente()
        # Chamar o método para buscar e selecionar as conversas com os nomes fornecidos
        root.buscar_novas_mensagens(nomes_das_conversas)

        time.sleep(2)
        # Iniciar o chatbot
        chatbot(keywords_dict, respostas, bot, root)
        root.checar_timeout_conversa_corrente()



if __name__ == "__main__":
    main()













