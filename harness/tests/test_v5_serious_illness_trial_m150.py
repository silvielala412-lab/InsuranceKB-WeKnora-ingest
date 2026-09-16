from insurance_harness.v5_preview.provider_trial import APPROVED_PRODUCTS


def test_m150_serious_illness_products_are_registered():
    selected = {
        product.product_id: product
        for product in APPROVED_PRODUCTS
        if product.product_id in {"1828", "L2332"}
    }

    assert set(selected) == {"1828", "L2332"}
    assert all(product.insurance_class == "重疾险" for product in selected.values())
    assert selected["1828"].product_version_id == "1828-1"
    assert selected["L2332"].product_version_id == "L2332-1"
    assert all(len(product.pdfs) == 3 for product in selected.values())
    assert [pdf.page_count for pdf in selected["1828"].pdfs] == [11, 43, 2]
    assert [pdf.page_count for pdf in selected["L2332"].pdfs] == [8, 33, 1]
