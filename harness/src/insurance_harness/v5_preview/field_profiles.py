from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FieldExtractionProfile:
    scan_all_materials: bool
    preserve_document_diversity: bool
    neighbor_pages: int
    exhaustive_items: bool
    semantic_terms: tuple[str, ...]
    instruction: str
    preferred_document_terms: tuple[str, ...] = ()
    required_evidence_document_terms: tuple[str, ...] = ()


_PROFILES: dict[str, FieldExtractionProfile] = {
    "special_coverage_and_exclusion_tags": FieldExtractionProfile(
        scan_all_materials=True,
        preserve_document_diversity=True,
        neighbor_pages=1,
        exhaustive_items=True,
        semantic_terms=(
            "既往症",
            "既往疾病",
            "特别约定",
            "条件承保",
            "加费承保",
            "除外承保",
            "不承担保险责任",
        ),
        instruction=(
            "特殊承保与除外标签：遍历条款、说明书和特别约定，按‘具体对象+承保方向’逐项输出，"
            "例如‘既往症不可赔’或‘某疾病条件承保’，不能只写‘条件承保/除外不保’。可保、"
            "不可赔、条件承保的方向必须与直接证据一致；Schema value_guidance 中的标签只是示例，"
            "不得据此推断产品事实。每个标签提供独立 Evidence。"
        ),
        preferred_document_terms=("条款",),
        required_evidence_document_terms=("条款",),
    ),
    "exclusions": FieldExtractionProfile(
        scan_all_materials=True,
        preserve_document_diversity=True,
        neighbor_pages=2,
        exhaustive_items=True,
        semantic_terms=(
            "责任免除",
            "除外责任",
            "不承担保险责任",
            "不予给付",
            "不负责赔偿",
            "下列情形之一",
        ),
        instruction=(
            "责任免除：遍历全部材料和条款续页，只整理明确适用于当前合同的正式免责。按原子免责"
            "情形逐项编号，保留前置条件、例外、适用责任和条款中的完整限定；不得用‘等’、"
            "‘包括但不限于’、目录标题或‘详见条款’代替已列出的项目。每个项目必须有保险条款中"
            "直接支持该项目的独立 Evidence；单条 quote 只支持一个原子免责且不超过600字符，"
            "不得把整页免责作为一条 Evidence。"
        ),
        preferred_document_terms=("条款",),
        required_evidence_document_terms=("条款",),
    ),
    "out_of_hospital_special_drug_coverage": FieldExtractionProfile(
        scan_all_materials=True,
        preserve_document_diversity=True,
        neighbor_pages=2,
        exhaustive_items=True,
        semantic_terms=(
            "院外购药",
            "院外药品费用",
            "特定药品",
            "药品清单",
            "药品处方",
            "指定药店",
            "购药申请",
            "用药审核",
        ),
        instruction=(
            "外购药/特药责任：必须跨产品说明书与保险条款合并，说明书摘要不能视为完整答案。"
            "按责任逐项保留药品/疾病范围、医院诊断、处方要求、购药渠道或指定药店、事前申请/"
            "审核、购药时限、额度、免赔额、赔付比例、材料要求和除外限制；材料出现哪一项就必须"
            "写入哪一项。每个原子规则提供直接 Evidence，并写清适用责任或计划。保险条款中的"
            "正式责任必须至少提供一条条款 Evidence，不能只引用产品说明书或服务手册。"
        ),
        preferred_document_terms=("条款",),
        required_evidence_document_terms=("条款",),
    ),
    "reimbursable_expense_scope": FieldExtractionProfile(
        scan_all_materials=True,
        preserve_document_diversity=True,
        neighbor_pages=2,
        exhaustive_items=True,
        semantic_terms=(
            "医疗费用范围",
            "合理且必要",
            "实际支出",
            "床位费",
            "药品费",
            "材料费",
            "检查费",
            "治疗费",
            "手术费",
            "社会医疗保险目录",
        ),
        instruction=(
            "报销范围：不得只返回‘合理且必要的医疗费用’等摘要。跨页、跨责任列出材料明确的"
            "费用项目，并保留实际发生/合理且必要、社保目录内外、医院或科室、责任/计划、扣除项、"
            "不纳入费用和其他计算限制。费用项目有清单时逐项写全，每项或同一完整清单提供直接 "
            "Evidence。"
        ),
        preferred_document_terms=("条款",),
        required_evidence_document_terms=("条款",),
    ),
    "reimbursement_rate_rules": FieldExtractionProfile(
        scan_all_materials=True,
        preserve_document_diversity=True,
        neighbor_pages=2,
        exhaustive_items=True,
        semantic_terms=(
            "给付比例",
            "赔付比例",
            "报销比例",
            "社会医疗保险身份",
            "社会医疗保险结算",
            "未使用社会医疗保险",
            "预审核",
        ),
        instruction=(
            "报销比例：按保险责任和结算场景逐项抽取比例，分别保留有无社会医疗保险身份、是否"
            "使用社会医疗保险结算、是否完成预审核、医保目录内外等改变比例的条件。不得把不同"
            "责任的比例合并为一个通用比例；每项比例及其条件必须提供保险条款 Evidence。"
        ),
        preferred_document_terms=("条款",),
        required_evidence_document_terms=("条款",),
    ),
    "claim_application_deadline_and_documents": FieldExtractionProfile(
        scan_all_materials=True,
        preserve_document_diversity=True,
        neighbor_pages=2,
        exhaustive_items=True,
        semantic_terms=(
            "保险事故通知",
            "保险金申请人",
            "申请保险金",
            "证明和资料",
            "申请材料",
            "诉讼时效",
            "理赔时效",
            "作出核定",
            "履行给付保险金义务",
        ),
        instruction=(
            "理赔申请时效与申请材料：分别抽取保险事故通知时限、客户申请/诉讼时效、保险公司"
            "核定时效、保险金给付时效和申请材料，不能把这些概念合并成一句概括。不得把保险公司"
            "的核定或给付时效写成客户申请时效；原文没有客户申请/诉讼时效时应明确材料未载明，"
            "不得用5日核定、30日核定等处理期限代替。材料清单按身故、医疗、疾病、伤残、失能等"
            "责任或理赔类型分组，"
            "逐项保留申请书、身份/关系证明、诊断或鉴定、病历、费用票据/清单及条款要求的其他文件；"
            "每个分组和时效提供直接 Evidence。"
        ),
        preferred_document_terms=("条款",),
        required_evidence_document_terms=("条款",),
    ),
    "policyholder_rights": FieldExtractionProfile(
        scan_all_materials=True,
        preserve_document_diversity=True,
        neighbor_pages=1,
        exhaustive_items=True,
        semantic_terms=(
            "保单贷款",
            "自动垫交",
            "减额交清",
            "减少基本保险金额",
            "现金价值",
            "解除合同",
            "保单红利",
        ),
        instruction=(
            "保单权益：遍历全部条款，逐项抽取当前合同明确享有的红利、现金价值、保单贷款、"
            "自动垫交、减额交清、减保、退保等权益及其条件和限制；Schema 列表只是示例，不是"
            "固定全集。健康服务不能冒充保单权益，附加险不得继承仅适用于主险的权益。每项权益"
            "必须有直接支持该项的独立 Evidence；未约定时不得补充。对材料明确写出的权益，还要"
            "保留办理条件、办理材料、处理期限、返还或给付内容和限制，不能只输出权益名称标签。"
        ),
        preferred_document_terms=("条款",),
        required_evidence_document_terms=("条款",),
    ),
    "medical_service_benefits": FieldExtractionProfile(
        scan_all_materials=True,
        preserve_document_diversity=True,
        neighbor_pages=1,
        exhaustive_items=True,
        semantic_terms=(
            "就医绿通",
            "在线问诊",
            "专家会诊",
            "门诊预约",
            "住院安排",
            "陪诊",
            "费用垫付",
            "预赔",
            "闪赔",
            "线上理赔",
            "康复护理",
        ),
        instruction=(
            "增值服务：跨产品材料、服务手册和准入清单合并全部明确适用的服务，Schema 列表只是"
            "示例，不得直接把 Schema 示例标签当成答案；除非材料逐字出现并有 Evidence，否则禁止"
            "只返回‘就医绿通、费用垫付、预赔、闪赔、线上理赔’。value 必须使用材料中的准确服务"
            "名称逐项输出，每项写成‘服务名称：次数/额度；关键申请条件或限制’。保留服务内容、"
            "准入对象、使用次数/额度、申请条件、"
            "办理流程、服务期限、地区/机构限制和不适用情形；不要把多个服务压成‘就医服务等’。"
            "每项服务提供直接 Evidence，不能把保险责任当成增值服务。"
        ),
        preferred_document_terms=("服务手册",),
    ),
    "waiting_period": FieldExtractionProfile(
        scan_all_materials=True,
        preserve_document_diversity=True,
        neighbor_pages=1,
        exhaustive_items=True,
        semantic_terms=(
            "等待期",
            "观察期",
            "合同生效之日起",
            "不受等待期限制",
            "等待期内",
        ),
        instruction=(
            "等待期：完整抽取等待期时长、起算点、适用责任、意外原因是否例外、等待期内发生"
            "保险事故的处理后果，以及续保/重新投保等特殊例外；不得只返回天数。每个组成部分"
            "都要有直接 Evidence。"
        ),
        preferred_document_terms=("条款",),
        required_evidence_document_terms=("条款",),
    ),
}


BUSINESS_PRIORITY_FIELD_IDS = tuple(_PROFILES)
FULL_MATERIAL_PROFILE_FIELD_IDS = frozenset(
    field_id for field_id, profile in _PROFILES.items() if profile.scan_all_materials
)


def field_extraction_profile(field_id: str) -> FieldExtractionProfile | None:
    return _PROFILES.get(field_id)


__all__ = [
    "BUSINESS_PRIORITY_FIELD_IDS",
    "FULL_MATERIAL_PROFILE_FIELD_IDS",
    "FieldExtractionProfile",
    "field_extraction_profile",
]
