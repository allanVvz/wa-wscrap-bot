"""Testes offline para validar fluxos principais do chatbot."""
import argparse
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

try:
    from mensages import (
        chatbot,
        compilar_keywords,
        gerar_keywords,
    )
    MENSAGES_IMPORT_ERROR = None
except ModuleNotFoundError as import_error:
    chatbot = None
    compilar_keywords = None
    gerar_keywords = None
    MENSAGES_IMPORT_ERROR = import_error
try:
    from product_lookup import Product
    from product_search.indexer import ProductMatch, ProductSearchResult
    PRODUCT_IMPORT_ERROR = None
except ModuleNotFoundError as import_error:
    Product = None
    ProductMatch = None
    ProductSearchResult = None
    PRODUCT_IMPORT_ERROR = import_error


def make_message(text, hora=None):
    """Cria um dicionario de mensagem alinhado ao esperado pelo chatbot."""
    return {
        "texto": text,
        "hora": hora or datetime(2024, 1, 1, 12, 0),
    }


def make_keywords_dict():
    """Monta o dicionario de keywords usando sinonimos simples em ASCII."""
    sinonimos = {
        "ola": {"ola", "oi", "oie"},
        "horario": {"horario", "funcionamento", "atendimento"},
        "horário": {"horário", "funcionamento"},
        "olhar": {"olhar", "ver", "visualizar", "site", "link"},
    }
    keywords = gerar_keywords(sinonimos)
    return compilar_keywords(keywords)


def make_respostas_dict():
    return {
        "saudacao": None,
        "horario_atendimento": "Nosso horario de funcionamento e de 16:00 as 23:00.",
        "olhar": "Claro, voce pode ver nosso site: www.vzforeal.com",
        "padrao": "Nao entendi bem. Vou tentar responder com base no que sei:",
    }


def make_match(label, url, *, tfidf=0.5, lexical=90.0):
    product = Product(
        id=1,
        name=label,
        slug=label.lower().replace(" ", "-"),
        sku=None,
        url=url,
        preview_url=None,
        skus=[],
    )
    return ProductMatch(
        label=label,
        purchase_url=url,
        product=product,
        sku=None,
        tfidf_score=tfidf,
        lexical_score=lexical,
        forced=False,
    )


class FakeBot:
    def __init__(self):
        self.saudacoes_respostas = ["Ola! Eu sou o vz-bot-tr1."]
        self.n_messages = 0
        self.fallback_inputs = []

    def gerador_respostas(self, entrada_usuario):
        self.fallback_inputs.append(entrada_usuario)
        return f"Wiki stub: {entrada_usuario}"


class FakeRoot:
    def __init__(self, bot, chat_id="cliente-test", incoming=None, messages_after=None, ultimas=None):
        self.bot_ativo = True
        self.conversa_bot = bot
        self.expected_chat = chat_id
        self.processed_msgs_map = {}
        self.senses_map = {}
        self.senses_count = {}
        self.enviadas = []
        self.logs = []
        self._incoming = []
        self._messages_after = []
        self._ultimas = list(ultimas) if ultimas is not None else []
        if incoming is not None:
            self.update_incoming(incoming)
        else:
            self.conversa_bot.n_messages = 0
        if messages_after is not None:
            self.set_messages_after(messages_after)

    def update_incoming(self, incoming, n_messages=None):
        self._incoming = [dict(item) for item in incoming]
        if n_messages is None:
            self.conversa_bot.n_messages = len(self._incoming)
        else:
            self.conversa_bot.n_messages = n_messages
        if incoming:
            self._ultimas = [item["texto"] for item in incoming]

    def set_messages_after(self, messages):
        self._messages_after = [dict(item) for item in messages]

    def last_n_messages(self):
        n = int(self.conversa_bot.n_messages or 0)
        if n <= 0:
            return []
        return self._incoming[-n:]

    def get_mensagens_apos_resposta(self, limite=5):
        if not self._messages_after:
            return []
        return self._messages_after[-limite:]

    def get_ultimas_mensagens_cliente(self, n):
        if not n:
            return []
        return self._ultimas[-n:]

    def enviar_mensagem(self, mensagem):
        self.enviadas.append(mensagem)

    def log_conversa(self, tipo, chat, texto):
        self.logs.append((tipo, chat, texto))

    def get_current_chat_identifier(self):
        return self.expected_chat


def _print_incoming_block(title, items):
    if not items:
        return
    print(title)
    for item in items:
        if isinstance(item, dict):
            texto = item.get("texto", "")
        else:
            texto = str(item)
        print(f"  cliente: {texto}")


def run_simulation_case(label, incoming=None, search_result=None, messages_after=None, ultimas=None):
    keywords = make_keywords_dict()
    respostas = make_respostas_dict()
    bot = FakeBot()
    root = FakeRoot(bot, incoming=incoming, messages_after=messages_after, ultimas=ultimas)

    print(f"=== {label} ===")
    _print_incoming_block("Mensagens recebidas:", incoming or [])
    _print_incoming_block("Mensagens apos resposta anterior:", messages_after or [])
    _print_incoming_block("Ultimas mensagens conhecidas:", ultimas or [])

    if ProductSearchResult is None:
        raise RuntimeError("ProductSearchResult indisponivel; instalacao incompleta")

    vazio = ProductSearchResult(matches=[], confidence="none", error=None)
    resultado = search_result if search_result is not None else vazio

    with patch("mensages.search_products_hybrid", return_value=resultado):
        chatbot(keywords, respostas, bot, root)

    if root.enviadas:
        print("Respostas do bot:")
        for texto in root.enviadas:
            print(f"  bot: {texto}")
    else:
        print("Respostas do bot: (nenhuma)")

    ident = root.get_current_chat_identifier()
    sentidos = root.senses_map.get(ident, {})
    if sentidos:
        print("Intencoes detectadas:")
        for intent, entradas in sentidos.items():
            print(f"  {intent}: {entradas}")

    if root.logs:
        print("Logs registrados:")
        for tipo, chat, texto in root.logs:
            print(f"  {tipo}@{chat}: {texto}")

    if bot.fallback_inputs:
        print("Fallback recebeu:")
        for entrada in bot.fallback_inputs:
            print(f"  {entrada}")

    print()


def simulate_deduplicacao():
    if ProductSearchResult is None:
        raise RuntimeError("ProductSearchResult indisponivel; instalacao incompleta")

    keywords = make_keywords_dict()
    respostas = make_respostas_dict()
    bot = FakeBot()
    hora = datetime(2024, 1, 1, 12, 0)
    mensagem = make_message("Tem radar ev?", hora=hora)
    root = FakeRoot(bot, incoming=[mensagem])
    match = make_match("Radar EV Path", "https://example.com/radar")
    resultado = ProductSearchResult(matches=[match], confidence="high", error=None)

    print("=== Deduplicacao de mensagens repetidas ===")
    _print_incoming_block("Mensagens recebidas:", [mensagem])

    with patch("mensages.search_products_hybrid", return_value=resultado) as patched:
        chatbot(keywords, respostas, bot, root)

    if root.enviadas:
        print("Primeira resposta do bot:")
        for texto in root.enviadas:
            print(f"  bot: {texto}")

    ident = root.get_current_chat_identifier()
    sentidos = root.senses_map.get(ident, {})
    if sentidos:
        print("Intencoes detectadas:")
        for intent, entradas in sentidos.items():
            print(f"  {intent}: {entradas}")

    with patch("mensages.search_products_hybrid", return_value=resultado) as patched2:
        root.update_incoming([mensagem])
        chatbot(keywords, respostas, bot, root)
        chamou_novamente = patched2.called

    print("Reexecutando com a mesma mensagem...")
    if chamou_novamente:
        print("  (aviso) buscou dados do catalogo novamente.")
    else:
        print("  Nenhuma nova consulta ao catalogo foi necessaria.")

    total_respostas = len(root.enviadas)
    print(f"Total de respostas armazenadas: {total_respostas}")
    if total_respostas > 1:
        extras = root.enviadas[1:]
        for texto in extras:
            print(f"  bot extra: {texto}")
    else:
        print("  Nenhuma nova resposta enviada.")

    print()


def simulate_all_flows():
    if MENSAGES_IMPORT_ERROR is not None:
        print(f"mensages nao pode ser importado: {MENSAGES_IMPORT_ERROR}")
        print("Instale as dependencias listadas em requirements.txt e tente novamente.")
        return
    if PRODUCT_IMPORT_ERROR is not None:
        print(f"product_search.indexer nao pode ser importado: {PRODUCT_IMPORT_ERROR}")
        print("Instale as dependencias listadas em requirements.txt e tente novamente.")
        return

    print("Simulando fluxos principais do chatbot...\n")

    run_simulation_case(
        "Saudacao basica",
        incoming=[make_message("Oi, tudo bem?")],
    )

    run_simulation_case(
        "Horario de atendimento",
        incoming=[make_message("Qual o horario de atendimento?")],
    )

    run_simulation_case(
        "Pedido de link",
        incoming=[make_message("Pode me mandar o link do site?")],
    )

    match_alta = make_match("Radar EV Path", "https://example.com/radar")
    run_simulation_case(
        "Busca de produto (alta confianca)",
        incoming=[make_message("Quero comprar radar ev path")],
        search_result=ProductSearchResult(matches=[match_alta], confidence="high", error=None),
    )

    matches_medias = [
        make_match("Radar EV Path", "https://example.com/radar-ev", tfidf=0.2),
        make_match("Radar EV XS", "https://example.com/radar-xs", tfidf=0.18),
        make_match("Radar EV Pitch", "https://example.com/radar-pitch", tfidf=0.17),
    ]
    run_simulation_case(
        "Busca de produto (media confianca)",
        incoming=[make_message("Tem radar ev?")],
        search_result=ProductSearchResult(matches=matches_medias, confidence="medium", error=None),
    )

    match_baixa = make_match("Radar Desconhecido", "https://example.com/radar-x", tfidf=0.05, lexical=10.0)
    run_simulation_case(
        "Busca de produto (conf baixa)",
        incoming=[make_message("Tem algum radar diferente?")],
        search_result=ProductSearchResult(matches=[match_baixa], confidence="low", error=None),
    )

    run_simulation_case(
        "Fallback wiki",
        incoming=[make_message("Pode contar a historia da marca?")],
    )

    simulate_deduplicacao()

    run_simulation_case(
        "Sem mensagens novas (fallback anchor)",
        incoming=[],
        messages_after=[make_message("Oi bot")],
        ultimas=["Oi bot"],
    )

class ChatbotFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if MENSAGES_IMPORT_ERROR is not None:
            raise unittest.SkipTest(
                f"mensages nao pode ser importado: {MENSAGES_IMPORT_ERROR}"
            )
        if PRODUCT_IMPORT_ERROR is not None:
            raise unittest.SkipTest(
                f"produto/indice nao pode ser importado: {PRODUCT_IMPORT_ERROR}"
            )

    def setUp(self):
        self.bot = FakeBot()
        self.keywords = make_keywords_dict()
        self.respostas = make_respostas_dict()
        self.empty_search = ProductSearchResult(matches=[], confidence="none", error=None)

    def run_chatbot(self, root, search_result=None):
        result = search_result if search_result is not None else self.empty_search
        with patch("mensages.search_products_hybrid", return_value=result):
            chatbot(self.keywords, self.respostas, self.bot, root)

    def test_saudacao_flow(self):
        root = FakeRoot(self.bot, incoming=[make_message("Oi, tudo bem?")])
        self.run_chatbot(root)
        self.assertEqual(root.enviadas, ["Ola! Eu sou o vz-bot-tr1."])
        ident = root.get_current_chat_identifier()
        self.assertIn("saudacao", root.senses_map.get(ident, {}))

    def test_horario_flow(self):
        root = FakeRoot(self.bot, incoming=[make_message("Qual o horario de atendimento?")])
        self.run_chatbot(root)
        self.assertEqual(root.enviadas, [self.respostas["horario_atendimento"]])

    def test_olhar_flow_sem_resultado_produto(self):
        root = FakeRoot(self.bot, incoming=[make_message("Pode me mandar o link do site?")])
        self.run_chatbot(root)
        self.assertEqual(root.enviadas, [self.respostas["olhar"]])

    def test_produto_high_confidence(self):
        mensagem = make_message("Quero comprar radar ev path")
        root = FakeRoot(self.bot, incoming=[mensagem])
        match = make_match("Radar EV Path", "https://example.com/radar")
        result = ProductSearchResult(matches=[match], confidence="high", error=None)
        self.run_chatbot(root, search_result=result)
        esperado = "Encontrei Radar EV Path. Você pode comprar aqui: https://example.com/radar"
        self.assertEqual(root.enviadas, [esperado])

    def test_produto_medium_confidence_lista_sugestoes(self):
        mensagem = make_message("Tem radar ev?")
        root = FakeRoot(self.bot, incoming=[mensagem])
        matches = [
            make_match("Radar EV Path", "https://example.com/radar-ev", tfidf=0.2),
            make_match("Radar EV XS", "https://example.com/radar-xs", tfidf=0.18),
            make_match("Radar EV Pitch", "https://example.com/radar-pitch", tfidf=0.17),
        ]
        result = ProductSearchResult(matches=matches, confidence="medium", error=None)
        self.run_chatbot(root, search_result=result)
        resposta = root.enviadas[0]
        self.assertTrue(resposta.startswith("Encontrei algumas opções parecidas:"))
        self.assertIn("- Radar EV Path: https://example.com/radar-ev", resposta)

    def test_produto_conf_low_fallback_site(self):
        mensagem = make_message("Tem algum radar diferente?")
        root = FakeRoot(self.bot, incoming=[mensagem])
        match = make_match("Radar Desconhecido", "https://example.com/radar-x", tfidf=0.05, lexical=10.0)
        result = ProductSearchResult(matches=[match], confidence="low", error=None)
        self.run_chatbot(root, search_result=result)
        self.assertEqual(root.enviadas, [self.respostas["olhar"]])

    def test_fallback_wiki(self):
        mensagem = make_message("Pode contar a historia da marca?")
        root = FakeRoot(self.bot, incoming=[mensagem])
        self.run_chatbot(root)
        self.assertTrue(root.enviadas[0].startswith("Wiki stub:"))
        self.assertEqual(self.bot.fallback_inputs, ["pode contar a historia da marca?"])

    def test_deduplicacao_mesma_mensagem(self):
        hora = datetime(2024, 1, 1, 12, 0)
        mensagem = make_message("Tem radar ev?", hora=hora)
        root = FakeRoot(self.bot, incoming=[mensagem])
        match = make_match("Radar EV Path", "https://example.com/radar")
        result = ProductSearchResult(matches=[match], confidence="high", error=None)
        self.run_chatbot(root, search_result=result)
        self.assertEqual(len(root.enviadas), 1)

        # Mesma mensagem novamente: o chatbot deve ignorar
        root.update_incoming([mensagem])
        with patch("mensages.search_products_hybrid", side_effect=AssertionError("nao deveria chamar")):
            chatbot(self.keywords, self.respostas, self.bot, root)
        self.assertEqual(len(root.enviadas), 1)

    def test_fluxo_sem_novas_mensagens_usando_fallback_anchor(self):
        root = FakeRoot(self.bot, incoming=[], messages_after=[make_message("Oi bot")], ultimas=["Oi bot"])
        root.conversa_bot.n_messages = 0
        self.run_chatbot(root)
        self.assertEqual(root.enviadas, ["Ola! Eu sou o vz-bot-tr1."])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Testes e simulacoes offline do chatbot."
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Imprime os fluxos e respostas sem executar o WhatsApp Web.",
    )
    parsed_args, remaining_args = parser.parse_known_args()

    if parsed_args.simulate:
        simulate_all_flows()
    else:
        unittest.main(argv=[sys.argv[0]] + remaining_args)
