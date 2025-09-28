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


class FallbackConversaBot:
    def __init__(self):
        self.sentencas = []
        self.saudacoes_respostas = [
            "Olá! No momento não consegui acessar todas as informações, mas posso te ajudar com o básico.",
            "Oi! Estou aqui para te ajudar mesmo sem a base completa.",
        ]
        self.n_messages = 0

    def gerador_respostas(self, entrada_usuario):
        if entrada_usuario:
            return (
                "Ainda estou carregando informações para te responder melhor. "
                "Pode me dizer qual produto procura ou deixar uma mensagem?"
            )
        return "Como posso te ajudar hoje?"


class WhatsAppBot:
    ACTIVE_CHAT_SELECTOR = "#pane-side > div:nth-child(1) > div > div > div:nth-child(2) > div > div > div > div._ak8l._ap1_ > div._ak8o > div._ak8q > div > div > span"
    ALL_FILTER_SELECTOR = "#all-filter"
    UNREAD_FILTER_SELECTOR = "#unread-filter > div > div"
    DEFAULT_INACTIVITY_TIMEOUT = 20.0

    @staticmethod
    def _sanitize_nome(valor):
        texto = (valor or '').strip()
        if not texto:
            return ''
        so_digitos = re.sub(r'\D', '', texto)
        if len(so_digitos) >= 6:
            return so_digitos
        texto_sem_pontuacao = re.sub(r'[^\w\s]', '', texto).replace('_', ' ').strip()
        return texto_sem_pontuacao.casefold()

    @staticmethod
    def _parse_unread_badge(elemento):
        if elemento is None:
            return 0
        texto = (elemento.get_attribute('aria-label') or elemento.text or '').strip()
        if not texto:
            return 0
        match = re.search(r"(\d+)", texto)
        if not match:
            return 0
        try:
            return int(match.group(1))
        except ValueError:
            return 0

    def ensure_chat_state(self, chat_id):
        state = self.chat_state.setdefault(chat_id or "", {
            "badge_at_click": 0,
            "badge_pending": 0,
            "last_out_key": None,
            "last_out_ts": None,
            "processed_in_keys": set(),
            "last_cycle_at": 0.0,
        })
        if not isinstance(state.get("processed_in_keys"), set):
            state["processed_in_keys"] = set(state.get("processed_in_keys", []))
        return state

    def get_current_chat_identifier(self):
        return self._current_chat_id or ""

    @staticmethod
    def _parse_pre_plain_timestamp(pre_plain_text):
        if not pre_plain_text:
            return datetime.now()
        try:
            raw = pre_plain_text.split("]")[0][1:]
            return datetime.strptime(raw, "%H:%M, %d/%m/%Y")
        except Exception:
            return datetime.now()

    def _get_timeline_entries(self, limit=120):
        seletor = "div.message-in, div.message-out"
        try:
            elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
        except Exception:
            return []
        total = len(elementos)
        if not total:
            return []
        elementos = elementos[-max(1, limit):]
        offset = total - len(elementos)
        entries = []
        for idx, elem in enumerate(elementos):
            try:
                classes = elem.get_attribute('class') or ''
            except Exception:
                continue
            tipo = 'in' if 'message-in' in classes else 'out' if 'message-out' in classes else None
            if not tipo:
                continue
            try:
                base = elem.find_element(By.CSS_SELECTOR, "div.copyable-text[data-pre-plain-text]")
            except NoSuchElementException:
                continue
            pre_plain = base.get_attribute('data-pre-plain-text') or ''
            try:
                texto = base.find_element(By.CSS_SELECTOR, "span[dir='ltr']").text
            except NoSuchElementException:
                texto = (base.text or '').strip()
            timestamp = self._parse_pre_plain_timestamp(pre_plain)
            global_idx = offset + idx
            key = f"{tipo}|{pre_plain}|{global_idx}"
            entries.append({'tipo': tipo, 'texto': (texto or '').strip(), 'hora': timestamp, 'key': key, 'pre_plain': pre_plain, 'index': global_idx})
        return entries

    def refresh_last_out_state(self, chat_id, state=None):
        state = self.ensure_chat_state(chat_id) if state is None else state
        entries = self._get_timeline_entries(limit=60)
        for entry in reversed(entries):
            if entry['tipo'] == 'out':
                state['last_out_key'] = entry['key']
                state['last_out_ts'] = entry['hora']
                return

    def collect_messages_for_processing(self, chat_id, fallback_limit=5):
        state = self.ensure_chat_state(chat_id)
        entries = self._get_timeline_entries()
        latest_out = None
        for entry in reversed(entries):
            if entry['tipo'] == 'out':
                latest_out = entry
                break
        if latest_out:
            state['last_out_key'] = latest_out['key']
            state['last_out_ts'] = latest_out['hora']
        anchor_index = -1
        anchor_key = None
        anchor_ts = None
        if state.get('last_out_key'):
            for entry in entries:
                if entry['tipo'] == 'out' and entry['key'] == state['last_out_key']:
                    anchor_index = entry['index']
                    anchor_key = entry['key']
                    anchor_ts = entry['hora']
                    break
        if anchor_index == -1 and latest_out is not None:
            anchor_index = latest_out['index']
            anchor_key = latest_out['key']
            anchor_ts = latest_out['hora']
        delta = []
        for entry in entries:
            if anchor_index > -1 and entry['index'] <= anchor_index:
                continue
            if entry['tipo'] != 'in' or not entry['texto']:
                continue
            if entry['key'] in state['processed_in_keys']:
                continue
            delta.append({'texto': entry['texto'], 'hora': entry['hora'], 'key': entry['key']})
        badge_limit = state.get('badge_pending')
        if badge_limit is None or badge_limit == 0:
            badge_limit = state.get('badge_at_click', 0)
        if badge_limit and badge_limit > 0:
            if len(delta) > badge_limit:
                delta = delta[-badge_limit:]
        else:
            limit = max(1, fallback_limit)
            if len(delta) > limit:
                delta = delta[-limit:]
        if not delta:
            if anchor_index == -1:
                recent_in = [entry for entry in entries if entry['tipo'] == 'in' and entry['texto']]
                if recent_in:
                    entry = recent_in[-1]
                    if entry['key'] not in state['processed_in_keys']:
                        delta = [{'texto': entry['texto'], 'hora': entry['hora'], 'key': entry['key']}]
        delta.sort(key=lambda item: (item['hora'], item['key']))
        self.conversa_bot.n_messages = len(delta)
        return {
            'messages': delta,
            'latest_out_key': state.get('last_out_key'),
            'latest_out_ts': state.get('last_out_ts'),
            'anchor_key': anchor_key,
            'anchor_ts': anchor_ts,
            'badge_limit': badge_limit or 0,
        }

    def finalize_chat_processing(self, chat_id, processed_keys, responded, anchor_info=None):
        state = self.ensure_chat_state(chat_id)
        if processed_keys:
            state['processed_in_keys'].update(processed_keys)
            pending = state.get('badge_pending')
            if pending is None or pending == 0:
                pending = state.get('badge_at_click', 0)
            pending = max(0, pending - len(processed_keys))
            state['badge_pending'] = pending
            state['badge_at_click'] = pending if pending > 0 else 0
        if anchor_info:
            if anchor_info.get('latest_out_key'):
                state['last_out_key'] = anchor_info['latest_out_key']
                state['last_out_ts'] = anchor_info.get('latest_out_ts')
        if not processed_keys and not responded and state.get('badge_pending', 0) > 0:
            state['badge_pending'] = 0
            state['badge_at_click'] = 0
        if responded:
            self.refresh_last_out_state(chat_id, state)
        state['last_cycle_at'] = time.time()

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
        self.chat_state = {}
        self._current_chat_id = None
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

    def _localizar_conversa_por_nome(self, nome_original):
        nome_limpo = self._sanitize_nome(nome_original)
        seletor = f"span[title='{nome_original}']"
        try:
            return self.driver.find_element(By.CSS_SELECTOR, seletor)
        except NoSuchElementException:
            pass
        try:
            pane = self.driver.find_element(By.ID, 'pane-side')
        except NoSuchElementException as exc:
            raise exc
        candidatos = pane.find_elements(By.CSS_SELECTOR, "span[title]")
        for candidato in candidatos:
            titulo = candidato.get_attribute('title') or candidato.text or ''
            if self._sanitize_nome(titulo) == nome_limpo:
                return candidato
        raise NoSuchElementException(f"Conversa com o nome {nome_original} não encontrada.")

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
        nao_lidas_cache = self.listar_contatos_nao_lidos()
        nao_lidas_map = {
            self._sanitize_nome(item.get('nome')): int(item.get('nao_lidas', 0))
            for item in nao_lidas_cache
        }

        for nome in nomes_conversas:
            nome_sanit = self._sanitize_nome(nome)
            state = self.ensure_chat_state(nome_sanit)
            if self.atualizar_conversa_corrente(nome):
                print(f"[DEBUG] Conversa '{nome}' esta ativa; fluxo alternativo sem badge.")
                self.conversa_bot.n_messages = state.get('badge_pending', 0)
                self._current_chat_id = nome_sanit or None
                return
            try:
                conversa_element = self._localizar_conversa_por_nome(nome)

                badge_internal = 0
                badges = conversa_element.find_elements(
                    By.CSS_SELECTOR,
                    "span[aria-label$='mensagem não lida'], span[aria-label$='mensagens não lidas']"
                )
                for badge in badges:
                    qtd = self._parse_unread_badge(badge)
                    if qtd > badge_internal:
                        badge_internal = qtd

                pane_badge = nao_lidas_map.get(nome_sanit, 0)
                badge_at_click = max(badge_internal, pane_badge)

                if badge_at_click > 0:
                    if badge_at_click != state.get('badge_at_click'):
                        state['badge_at_click'] = badge_at_click
                        state['badge_pending'] = badge_at_click
                        if os.environ.get('BOT_DEBUG') == '1':
                            print(f"[DEBUG] badge_at_click congelado para '{nome}': {badge_at_click}")
                elif state.get('badge_pending', 0) > 0:
                    badge_at_click = state['badge_pending']
                else:
                    badge_at_click = 0

                state['last_seen_pane_badge'] = pane_badge
                self.conversa_bot.n_messages = max(0, badge_at_click)
                if os.environ.get('BOT_DEBUG') == '1':
                    print(
                        f"[DEBUG] Contador de nao lidas para '{nome}': {self.conversa_bot.n_messages} (pane={pane_badge}, badge={badge_internal})"
                    )
                if self.conversa_bot.n_messages > 0:
                    print(f"Conversa encontrada com o nome: {nome}")

                conversa_element.click()
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.ID, 'main'))
                )
                try:
                    ultimo = self.driver.find_elements(By.CSS_SELECTOR, "div.message-in, div.message-out")[-1]
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'end'});", ultimo)
                except Exception:
                    pass
                self.conversa_corrente_ativa = True
                self.conversa_corrente_nome = nome
                self.conversa_corrente_last_seen = time.time()
                self.conversa_corrente_total_incoming = self._contar_mensagens_entrada()
                self._current_chat_id = nome_sanit or None
                state['last_cycle_start'] = time.time()
                if state.get('badge_pending', 0) == 0 and badge_at_click > 0:
                    state['badge_pending'] = badge_at_click
                if self.conversa_bot.n_messages <= 0:
                    time.sleep(0.6)
                return

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
        self._current_chat_id = None

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

    def get_mensagens_apos_resposta(self, limite=5):
        """
        Retorna mensagens do cliente posteriores à última resposta enviada pelo bot.
        Se não houver resposta anterior, retorna somente a mensagem mais recente do cliente.
        """
        try:
            elementos = self.driver.find_elements(By.CSS_SELECTOR, "div.message-in, div.message-out")
        except Exception as e:
            print(f"[AVISO] Falha ao coletar timeline de mensagens: {type(e).__name__}: {e}")
            return []

        if not elementos:
            return []

        registros = []
        for elem in elementos[-80:]:  # limita a inspeção aos itens mais recentes
            try:
                classes = elem.get_attribute('class') or ''
            except Exception:
                continue
            tipo = 'in' if 'message-in' in classes else 'out' if 'message-out' in classes else None
            if not tipo:
                continue
            try:
                base = elem.find_element(By.CSS_SELECTOR, "div.copyable-text[data-pre-plain-text]")
            except NoSuchElementException:
                continue
            texto = ''
            try:
                texto = base.find_element(By.CSS_SELECTOR, "span[dir='ltr']").text
            except NoSuchElementException:
                texto = (base.text or '').strip()
            pre_plain = base.get_attribute('data-pre-plain-text') or ''
            try:
                hora_raw = pre_plain.split(']')[0][1:]
                timestamp = datetime.strptime(hora_raw, "%H:%M, %d/%m/%Y")
            except Exception:
                timestamp = datetime.now()
            registros.append({'tipo': tipo, 'texto': texto.strip(), 'hora': timestamp})

        if not registros:
            return []

        ultima_resposta_idx = None
        for idx in range(len(registros) - 1, -1, -1):
            if registros[idx]['tipo'] == 'out':
                ultima_resposta_idx = idx
                break

        novas = []
        if ultima_resposta_idx is not None:
            for item in registros[ultima_resposta_idx + 1:]:
                if item['tipo'] == 'in' and item['texto']:
                    novas.append({'texto': item['texto'], 'hora': item['hora']})
        else:
            recentes_in = [r for r in registros if r['tipo'] == 'in' and r['texto']]
            if recentes_in:
                novas.append({'texto': recentes_in[-1]['texto'], 'hora': recentes_in[-1]['hora']})

        if not novas:
            return []

        return novas[-limite:]

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
                    nome_sanit = re.sub(r'[^\w\s]', '', nome_raw).replace('_', ' ').strip().casefold()

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
    try:
        bot = ConversaBot(url)
    except RuntimeError as exc:
        print(f"[AVISO] Falha ao inicializar ConversaBot: {exc}")
        bot = FallbackConversaBot()
    except Exception as exc:
        print(f"[AVISO] Erro inesperado ao preparar ConversaBot: {exc}")
        bot = FallbackConversaBot()

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
        # manter 'olhar' para expressões de navegação, sem conflitar com intenção de compra
        'olhar': {'ver', 'visualizar'}
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
    nomes_das_conversas = ['mana']

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



