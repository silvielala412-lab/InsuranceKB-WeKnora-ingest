from insurance_harness.v5_preview.provider_trial import (
    APPROVED_PRODUCTS,
    MAX_PROVIDER_CALLS,
)


def test_m139_freezes_nine_products_across_six_schema_classes() -> None:
    m139_products = tuple(
        product for product in APPROVED_PRODUCTS if product.product_id not in {"1828", "L2332"}
    )
    assert len(m139_products) == 9
    assert len({product.product_version_id for product in m139_products}) == 9
    assert {product.insurance_class for product in m139_products} == {
        "医疗险",
        "意外险",
        "终身寿险",
        "两全保险",
        "年金险",
        "失能收入损失保险",
    }
    assert all(len(product.pdfs) == 3 for product in m139_products)


def test_m139_standard_provider_budget_is_two_attempts_per_product() -> None:
    assert MAX_PROVIDER_CALLS == 18
