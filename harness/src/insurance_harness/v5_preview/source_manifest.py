"""Frozen source identities used by the local V5 provider trial."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class ApprovedPdf:
    """Immutable identity and page count for one approved source PDF."""

    file_name: str
    sha256: str
    page_count: int


@dataclass(frozen=True, slots=True)
class ApprovedProduct:
    """Immutable source manifest used to select an approved product fixture."""

    directory_name: str
    metadata_sha256: str
    product_id: str
    product_version_id: str
    product_display_name: str
    insurance_class: str
    pdfs: tuple[ApprovedPdf, ...]


M146_SUPPLEMENTAL_PDFS: Final[tuple[ApprovedPdf, ...]] = (
    ApprovedPdf(
        "安有医健康服务手册（尊享版）.pdf",
        "9c9c6343fd0333084345376bec52bf30d2692a7e23ea98fb04a5722a8fa8f8be",
        60,
    ),
    ApprovedPdf(
        "平安添瑞·安有医（安医保尊享版）一页纸.pdf",
        "fa52b05bcf8561fa82d4c24db34585870a4b014f2315e742a9c43db41f91fead",
        2,
    ),
)


APPROVED_PRODUCTS: Final[tuple[ApprovedProduct, ...]] = (
    ApprovedProduct(
        directory_name="平安e生保（尊享版）医疗保险",
        metadata_sha256="0550999d9541722a38173ad25396878f0c9b3592dd590dd9999ad3f7d1b82979",
        product_id="596",
        product_version_id="596-1",
        product_display_name="平安e生保（尊享版）医疗保险",
        insurance_class="医疗险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "5e2aef32d319b5aca6d37268e99ee5252ea0c7a56885b1e4dfa1ebb0308e4279",
                27,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "88b784c61f52a2e21a2a12f96ba5d73412de95e68a4453af03a27e8ab1245edc",
                39,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "7b35fa3b0e1820860dafc2fec9858949d387f2aab19006d3d3e02b92e0bb75fb",
                2,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安创享盛世金越（尊享版26）终身寿险（分红型）",
        metadata_sha256="02f2ff44cb5481852b3ea495f4822030cccd7ac42762433d2bc1df8460b071d0",
        product_id="5003",
        product_version_id="5003-1",
        product_display_name="平安创享盛世金越（尊享版26）终身寿险（分红型）",
        insurance_class="终身寿险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "38720048d356a9c0ece11c8cf35f175d3bd98115ad76c39533e7610db1823c80",
                10,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "b2260a6162930fc01341ac988aa830116c6092efca079926556b3ce58d3718de",
                15,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "ac99d646fe63e8256c65dc0c38513cd03fe7001f446ee7f1fdfd2beb6fb8ebbf",
                2,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安守护百分百（2026）两全保险",
        metadata_sha256="e6f62472a211d408d02361e29117af0807a3d2c26c7277393b5b0d4827fd30cb",
        product_id="1826",
        product_version_id="1826-1",
        product_display_name="平安守护百分百（2026）两全保险",
        insurance_class="两全保险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "d4c9611b7a0b0f59e9b37aef6ff0e5d12d42b00ba20daff670630f2d04e5c08a",
                7,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "829346499a67156e77e2778a4c5542e88456f8918beda055162f85ab3a30d007",
                9,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "9ea421ad68d443e5e6572b7c2c91fcd2302ab18103a7b85f733c0ea29439ea19",
                6,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安e生保（惠享版）长期医疗保险（费率可调）",
        metadata_sha256="9bdde7c27c56b9034c88cce1ff288b1681cf6e3986a338c5ed3a3db0793c3c1d",
        product_id="594",
        product_version_id="594-1",
        product_display_name="平安e生保（惠享版）长期医疗保险（费率可调）",
        insurance_class="医疗险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "3c7b24cd12e1c6bb04c714be511077f85fa6e5c820ed18dde3f025e9e71b320f",
                17,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "7bfac182fe11866e9d4c6f2b970a3a56db79833476f51e83ddcafe127b4c9ce5",
                44,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "fbc9adca68254427541afa594508f7b2e9c75d7c9b23b4804f9436a3a35a0f44",
                7,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安爱满分（2026）两全保险",
        metadata_sha256="4cd29c76d84104720ba4a8be72372d3e0442b4c548de648e1e083cd8fc50ad17",
        product_id="1818",
        product_version_id="1818-1",
        product_display_name="平安爱满分（2026）两全保险",
        insurance_class="两全保险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "d2119896e15b0fed076db80a2f780fd08ffd2498b260eb95fc7f1957c5169208",
                8,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "2e31eaf4dd259c4a04c04d5870bc6f6fdc2f4e3019d2d93b273db3f4a16bb932",
                9,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "48f4e5ba20c270947e9473a95bf12f4861d0ec6d3d9625565c94ac4f08e79ac4",
                2,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安盛世金越（尊享版26）终身寿险",
        metadata_sha256="ec2cff56d3f67946272ffa45f10cac5bb29ca217c81460bbed808a4b610fc8d5",
        product_id="1824",
        product_version_id="1824-1",
        product_display_name="平安盛世金越（尊享版26）终身寿险",
        insurance_class="终身寿险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "a484e0757d1989ef2fd3f3700273a081b30f026547b4f965a77854c028a713f6",
                7,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "42c9536acddd41d77e3d56e238bb47060cb36ac96a798317d875ec51cd967911",
                9,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "9811367acd0d3875260e926fe64901e3423c07569ae06bf1438926769860c66f",
                2,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安盛世金越（至尊版26）年金保险（分红型）",
        metadata_sha256="3b48b3d24151b7e972b21940321fd8a18e572e7964c891510bab022218a0f96b",
        product_id="1830",
        product_version_id="1830-2",
        product_display_name="平安盛世金越（至尊版26）年金保险（分红型）",
        insurance_class="年金险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "7025fd26e5c6e37c3f861a46036935bbc516b747a3f9074199599deed4afd5be",
                10,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "ad56b02e0c25599e26cd409f9d5e216af9582ea95967ec81a14a236043b59c8c",
                11,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "bf8951ca84880229cef503191ce78db14b16fdfa4313dfb4deccfd4ff96683e9",
                68,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安附加（2026）意外伤害保险",
        metadata_sha256="75e2c64f92760dd73f195f40254919f8f6e7908f8e26d619ca2f30b3db3ffca5",
        product_id="1814",
        product_version_id="1814-1",
        product_display_name="平安附加（2026）意外伤害保险",
        insurance_class="意外险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "68105656802ea7ad267d9d1def1f78c1fb706a807bc75fc93ba8ef1aeae83abf",
                12,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "0ef33683ec95d5b0976cf6b567956333aedf32eaf5f49aeae7012b00d50b795c",
                12,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "72224c36ed2455365fcbcd361444d3f26b50ee88d62aba7673d41525c27b99c7",
                10,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安附加（2026）失能收入损失保险",
        metadata_sha256="23c1a56861c1141a4c0388afdeab307e12ca28a2cffa50f613a478810530034c",
        product_id="1816",
        product_version_id="1816-1",
        product_display_name="平安附加（2026）失能收入损失保险",
        insurance_class="失能收入损失保险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "c156596bb234188ec324a5a9e56efb905e91804ee5bc29fd4ece1bc62dbc7db7",
                8,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "5da2822c7367682d64d7f2f2b4b5564891018a0ee714a464fb45833f6c4b492f",
                44,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "b081ec26d0f318921c0374bdf86da3a13e057c1b4fa41cb46fa8e6c53d95043a",
                2,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安安佑福（全能版）重大疾病保险",
        metadata_sha256="6842f82ada88bc4780a227633a96bbff793411875068898a99e65b7f7486aac6",
        product_id="1828",
        product_version_id="1828-1",
        product_display_name="平安安佑福（全能版）重大疾病保险",
        insurance_class="重疾险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "1c3e868b8d2acbf018087af5e345f70f0a934f94e75c2dc5a09fd9c41190b933",
                11,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "d68c2d3f88af277b392d4c8f3f8665620b9873a31d8411ce5e1763b8e129d474",
                43,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "600e95faf04a8268c90a2a0d08448c140b8a323f6e24bccfce186d96e0c9aa52",
                2,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安个人重大疾病保险",
        metadata_sha256="c26c39d72186e6c13ebc351e9cf87b7f9598adcb58d7846936abcad9f880e228",
        product_id="L2332",
        product_version_id="L2332-1",
        product_display_name="平安个人重大疾病保险",
        insurance_class="重疾险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "ce551adb217da6f3b54600d7523888c848145f54c9fa5012a73c30b8996db6a3",
                8,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "3964e686450e7b5bf332965f120397cda58ac55780b1b9ba68c37fc3dfe77d45",
                33,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "ac288709d7dc4be2984f550df68f063a0aebfdf533acd975fdce56693817d297",
                1,
            ),
        ),
    ),
)

M140_PRODUCT_IDS: Final[tuple[str, ...]] = ("596", "5003", "1826")
_EXPECTED_SCHEMA_FIELDS_BY_CLASS: Final[Mapping[str, int]] = {
    "医疗险": 67,
    "终身寿险": 75,
    "两全保险": 79,
    "年金险": 82,
    "意外险": 62,
    "失能收入损失保险": 76,
    "重疾险": 67,
}

__all__ = [
    "APPROVED_PRODUCTS",
    "M140_PRODUCT_IDS",
    "M146_SUPPLEMENTAL_PDFS",
    "ApprovedPdf",
    "ApprovedProduct",
]
