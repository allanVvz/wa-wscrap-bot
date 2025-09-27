from product_search import indexer
from product_lookup import Product, Sku

# =============================
# Catálogo fake baseado nos LINKS enviados
# =============================

def fake_products():
    radar = Product(
        id=1,
        name="Oakley Radar EV Path",
        slug="oakley-radar-ev-path",
        sku=None,
        url="https://vzforeal.com/products/radar-white-liquid-metal",
        preview_url=None,
        skus=[
            # Radar EV – White Liquid Metal
            Sku(
                id=101,
                product_id=1,
                sku="RADAR-EV-WHITE-LIQUID-METAL",
                token=None,
                title="Radar EV Path White Liquid Metal",
                availability=5,
                price_sale=0.0,
                price_discount=0.0,
                purchase_url="https://vzforeal.com/products/radar-white-liquid-metal",
                created_at=None,
                updated_at=None,
            ),
            # Radar EV – Preta
            Sku(
                id=102,
                product_id=1,
                sku="RADAR-EV-PRETA",
                token=None,
                title="Radar EV Path Preta",
                availability=3,
                price_sale=0.0,
                price_discount=0.0,
                purchase_url="https://vzforeal.com/products/radar-preta?pr_prod_strat=e5_desc&pr_rec_id=59862658b&pr_rec_pid=8860573663527&pr_ref_pid=8860576645415&pr_seq=uniform",
                created_at=None,
                updated_at=None,
            ),
        ],
    )

    plate_silver_liquid = Product(
        id=2,
        name="Plate Silver Liquid Metal",
        slug="platesilverliquid-metal",
        sku=None,
        url="https://vzforeal.com/products/platesilverliquid-metal?pr_prod_strat=e5_desc&pr_rec_id=59862658b&pr_rec_pid=9636851417383&pr_ref_pid=8860576645415&pr_seq=uniform",
        preview_url=None,
        skus=[
            Sku(
                id=201,
                product_id=2,
                sku="PLATE-SILVER-LIQUID-METAL",
                token=None,
                title="Plate Silver Liquid Metal",
                availability=7,
                price_sale=0.0,
                price_discount=0.0,
                purchase_url="https://vzforeal.com/products/platesilverliquid-metal?pr_prod_strat=e5_desc&pr_rec_id=59862658b&pr_rec_pid=9636851417383&pr_ref_pid=8860576645415&pr_seq=uniform",
                created_at=None,
                updated_at=None,
            )
        ],
    )

    plate_silver_icon_black = Product(
        id=3,
        name="Plate Silver Icon Black Iridium",
        slug="plate-silver-icon-black-iridium",
        sku=None,
        url="https://vzforeal.com/products/plate-silver-icon-black-iridium?pr_prod_strat=e5_desc&pr_rec_id=77293a089&pr_rec_pid=9666907668775&pr_ref_pid=9636851417383&pr_seq=uniform",
        preview_url=None,
        skus=[
            Sku(
                id=301,
                product_id=3,
                sku="PLATE-SILVER-ICON-BLACK-IRIDIUM",
                token=None,
                title="Plate Silver Icon Black Iridium",
                availability=2,
                price_sale=0.0,
                price_discount=0.0,
                purchase_url="https://vzforeal.com/products/plate-silver-icon-black-iridium?pr_prod_strat=e5_desc&pr_rec_id=77293a089&pr_rec_pid=9666907668775&pr_ref_pid=9636851417383&pr_seq=uniform",
                created_at=None,
                updated_at=None,
            )
        ],
    )

    return [radar, plate_silver_liquid, plate_silver_icon_black]


def main():
    # Reset e monkeypatch da fonte usada pelo indexer
    indexer._INDEX_CACHE = None
    indexer.fetch_products = fake_products

    query = "tem radar ev liquid?"
    result = indexer.search_products_hybrid(query, top_k=3, debug=True)
    print(f"\nQUERY: {query}")
    print(f"confidence={result.confidence} error={result.error}")
    for m in result.matches:
        print(
            f" - {m.label} | url={m.purchase_url} | tfidf={m.tfidf_score:.3f} | lex={m.lexical_score}"
        )

if __name__ == "__main__":
    main()
