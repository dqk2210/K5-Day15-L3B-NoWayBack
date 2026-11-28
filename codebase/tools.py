"""Công cụ tra cứu và kiểm tra an toàn cho AI hỗ trợ dự thảo đơn thuốc.

Chỉ dùng thư viện chuẩn của Python 3.10+.
Mọi công cụ đều chỉ đọc/tính toán cục bộ (KHÔNG tác động ra ngoài, side_effect=False).
Mọi kiểm tra an toàn (validate_prescription) và tính chi phí (calculate_cost) là Python thuần.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tracing import TOOLS, tool  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

_CACHE: dict[str, Any] = {}

DIAGNOSIS_KEYWORDS: dict[str, list[str]] = {
    "I10": ["tăng huyết áp", "huyết áp cao"],
    "E78": ["rối loạn mỡ máu", "rối loạn lipid", "tăng lipid", "mỡ máu"],
    "E11": ["đái tháo đường", "tiểu đường", "tiền đái tháo đường"],
    "K21": ["trào ngược dạ dày", "trào ngược thực quản", "dạ dày trào ngược", "gerd"],
    "J01": ["viêm xoang"],
    "J02": ["viêm họng"],
    "J30": ["viêm mũi dị ứng"],
    "R05": ["ho có đờm", "ho cấp"],
    "A04": ["nhiễm trùng tiêu hóa", "viêm ruột cấp", "viêm dạ dày ruột"],
    "K59": ["tiêu chảy", "rối loạn tiêu hóa", "rối loạn chức năng ruột"],
    "M75": ["bao gân xoay", "viêm gân", "viêm quanh khớp vai"],
    "M54": ["đau cơ vùng thắt lưng", "đau thắt lưng", "đau cột sống thắt lưng", "đau lưng"],
    "M17": ["thoái hóa khớp gối"],
    "I83": ["suy giãn tĩnh mạch", "giãn tĩnh mạch"],
    "B35": ["nấm da", "hắc lào", "nấm kẽ"],
    "B02": ["zona"],
    "J09": ["cúm a", "cúm mùa", "nhiễm cúm"],
}

OUT_OF_SCOPE_KEYWORDS: list[tuple[str, str]] = [
    ("ruột thừa", "Viêm ruột thừa cấp — bệnh ngoại khoa cấp cứu (ngoài phạm vi)"),
    ("ung thư", "Bệnh lý ung thư (ngoài phạm vi kê đơn ngoại trú cơ bản)"),
    ("điều trị đích", "Phác đồ điều trị đích phân tử chuyên sâu (ngoài phạm vi)"),
    ("hóa trị", "Phác đồ hóa trị chuyên khoa ung bướu (ngoài phạm vi)"),
    ("dọa sảy", "Thai kỳ có dấu hiệu dọa sảy / ra huyết (cần bác sĩ chuyên khoa sản)"),
    ("ra huyết", "Thai kỳ ra huyết bất thường (cần bác sĩ chuyên khoa sản)"),
]

SINGLE_CLASS_LIMITS: set[str] = {
    "PPI",
    "Statin",
    "ARB",
    "ACEi",
    "Beta-blocker",
    "Sulfonylurea",
    "SGLT2i",
    "DPP-4i",
    "NSAID",
    "NSAID_COX2",
    "Venotonic",
    "Beta-lactam",
    "Cephalosporin",
}


def _load_json(filename: str) -> list[dict[str, Any]]:
    if filename not in _CACHE:
        path = PROCESSED_DIR / filename
        _CACHE[filename] = json.loads(path.read_text(encoding="utf-8"))
    return _CACHE[filename]


def _drugs_by_id() -> dict[str, dict[str, Any]]:
    if "drugs_by_id" not in _CACHE:
        _CACHE["drugs_by_id"] = {d["drug_id"]: d for d in _load_json("drug_catalog_clean.json")}
    return _CACHE["drugs_by_id"]


def _normalize_icd_prefix(code: str) -> str:
    cleaned = code.strip().upper()
    m = re.match(r"^([A-Z]\d{2})", cleaned)
    return m.group(1) if m else cleaned


def _drug_class_tokens(drug_class: str) -> set[str]:
    return {part.strip() for part in (drug_class or "").split("+") if part.strip()}


def _is_acei(drug: dict[str, Any]) -> bool:
    tokens = _drug_class_tokens(drug.get("drug_class", ""))
    comps = " ".join(drug.get("component_ingredients", [])).lower()
    return "ACEi" in tokens or any(x in comps for x in ("perindopril", "lisinopril", "enalapril"))


def _is_arb(drug: dict[str, Any]) -> bool:
    tokens = _drug_class_tokens(drug.get("drug_class", ""))
    comps = " ".join(drug.get("component_ingredients", [])).lower()
    return "ARB" in tokens or any(x in comps for x in ("losartan", "valsartan", "telmisartan", "candesartan"))


@tool
def search_guidelines(icd10_codes: list[str], diagnosis_text: str = "") -> dict[str, Any]:
    """Tên: search_guidelines · Input: danh sách mã ICD-10 và chuỗi chẩn đoán · Output: phác đồ khớp, mã trong/ngoài phạm vi, cờ dừng · Không tác động ra ngoài."""
    guidelines = _load_json("guidelines_clean.json")
    supported_prefixes = {g["icd10_prefix"] for g in guidelines}
    guide_by_prefix = {g["icd10_prefix"]: g for g in guidelines}

    in_scope: list[str] = []
    out_of_scope: list[str] = []
    seen_in: set[str] = set()
    seen_out: set[str] = set()

    for raw in icd10_codes or []:
        prefix = _normalize_icd_prefix(raw)
        if not prefix:
            continue
        if prefix in supported_prefixes:
            if prefix not in seen_in:
                seen_in.add(prefix)
                in_scope.append(prefix)
        else:
            if prefix not in seen_out:
                seen_out.add(prefix)
                out_of_scope.append(prefix)

    diag_low = (diagnosis_text or "").lower()
    for prefix, kws in DIAGNOSIS_KEYWORDS.items():
        if prefix in supported_prefixes and any(kw in diag_low for kw in kws):
            if prefix not in seen_in:
                seen_in.add(prefix)
                in_scope.append(prefix)

    high_risk_flags: list[str] = []
    for kw, msg in OUT_OF_SCOPE_KEYWORDS:
        if kw in diag_low:
            high_risk_flags.append(msg)

    # Oncology ICD-10 C00-C97 or obstetric hemorrhage O20 -> out of scope stop
    has_prohibited_icd = any(
        c.startswith("C") or c.startswith("O20") or c.startswith("K35") for c in out_of_scope
    )
    has_oncology_or_severe_oob = any(
        kw in diag_low for kw in ("ung thư", "điều trị đích", "hóa trị", "ruột thừa")
    )

    matched_guidelines = [guide_by_prefix[p] for p in in_scope if p in guide_by_prefix]
    is_in_scope = bool(in_scope) and not has_prohibited_icd and not has_oncology_or_severe_oob

    return {
        "in_scope_codes": in_scope,
        "out_of_scope_codes": out_of_scope,
        "high_risk_flags": high_risk_flags,
        "matched_guidelines": matched_guidelines,
        "is_in_scope": is_in_scope,
    }


@tool
def retrieve_similar_cases(icd10_codes: list[str], top_k: int = 3) -> list[dict[str, Any]]:
    """Tên: retrieve_similar_cases · Input: mã ICD-10 trong phạm vi và top_k · Output: danh sách ca giả lập tương tự rút gọn · Không tác động ra ngoài."""
    target_prefixes = {_normalize_icd_prefix(c) for c in (icd10_codes or []) if c}
    if not target_prefixes:
        return []

    cases = _load_json("case_base_clean.json")
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for case in cases:
        case_prefixes = set(case.get("in_scope_icd10_prefixes") or [])
        if not case_prefixes:
            case_prefixes = {_normalize_icd_prefix(c) for c in case.get("icd10_codes", [])}
        overlap = len(target_prefixes & case_prefixes)
        if overlap > 0:
            scored.append((overlap, int(case.get("verified_catalog_meds_count") or 0), case))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    results: list[dict[str, Any]] = []
    for _, _, case in scored[:top_k]:
        verified_meds = [
            {
                "drug_id": m.get("drug_id"),
                "canonical_name": m.get("canonical_name"),
                "strength_dosage": m.get("strength_dosage"),
                "frequency_per_day": m.get("frequency_per_day"),
                "meal_timing": m.get("meal_timing"),
            }
            for m in case.get("medications", [])
            if m.get("in_verified_catalog") and m.get("drug_id")
        ]
        results.append(
            {
                "case_id": case["case_id"],
                "in_scope_icd10_prefixes": case.get("in_scope_icd10_prefixes", []),
                "patient_profile": case.get("patient_profile", {}),
                "verified_medications": verified_meds,
            }
        )
    return results


@tool
def search_drug_catalog(
    icd10_codes: list[str] | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """Tên: search_drug_catalog · Input: danh sách mã ICD-10 hoặc từ khóa tìm kiếm · Output: các thuốc xác minh phù hợp · Không tác động ra ngoài."""
    drugs = _load_json("drug_catalog_clean.json")
    prefixes = {_normalize_icd_prefix(c) for c in (icd10_codes or []) if c}
    q = (query or "").strip().lower()

    matched: list[dict[str, Any]] = []
    for d in drugs:
        if prefixes:
            indications = set(d.get("verified_indications_icd10") or [])
            if not (prefixes & indications):
                continue
        if q:
            haystack = " | ".join(
                [
                    d.get("drug_id", ""),
                    d.get("canonical_name", ""),
                    d.get("active_ingredient", ""),
                    d.get("drug_class", ""),
                    " ".join(d.get("aliases") or []),
                    " ".join(d.get("sample_brand_names") or []),
                ]
            ).lower()
            if q not in haystack:
                continue
        matched.append(
            {
                "drug_id": d["drug_id"],
                "canonical_name": d["canonical_name"],
                "strength_dosage": d.get("strength_dosage"),
                "route_of_administration": d.get("route_of_administration"),
                "unit": d.get("unit"),
                "drug_class": d.get("drug_class"),
                "verified_indications_icd10": d.get("verified_indications_icd10", []),
                "typical_frequency": d.get("typical_frequency"),
                "typical_meal_timing": d.get("typical_meal_timing"),
                "max_daily_dose": d.get("max_daily_dose"),
                "contraindications": d.get("contraindications", []),
                "interactions": d.get("interactions", []),
                "source_reference": d.get("source_reference", ""),
            }
        )
    return matched


def _parse_single_dose_amount(strength_dosage: str | None, max_unit: str) -> float | None:
    """Parse numeric dose per tablet/packet in the same unit as max_daily_dose."""
    if max_unit in ("viên", "gói", "lần bôi"):
        return 1.0
    if not strength_dosage:
        return None
    text = strength_dosage.lower().replace(",", ".")
    # Look for first numeric value + unit (mg, g, mcg)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(mcg|mg|g)\b", text)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2)
    if unit == max_unit:
        return val
    if unit == "g" and max_unit == "mg":
        return val * 1000.0
    if unit == "mg" and max_unit == "g":
        return val / 1000.0
    if unit == "mcg" and max_unit == "mg":
        return val / 1000.0
    return None


@tool
def validate_prescription(
    draft_meds: list[dict[str, Any]],
    patient_profile: dict[str, Any],
    in_scope_codes: list[str],
) -> dict[str, Any]:
    """Tên: validate_prescription · Input: bản nháp thuốc, hồ sơ bệnh nhân, mã ICD-10 · Output: status (PASS/PASS_WITH_WARNINGS/BLOCKED), vi phạm, cảnh báo · Không tác động ra ngoài."""
    catalog = _drugs_by_id()
    blocking: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    missing_fields: list[str] = []

    def add_block(code: str, drug_id: str, msg: str) -> None:
        blocking.append({"code": code, "drug_id": drug_id, "message": msg})

    def add_warn(code: str, drug_id: str, msg: str) -> None:
        warnings.append({"code": code, "drug_id": drug_id, "message": msg})

    age = patient_profile.get("age")
    is_adult = bool(patient_profile.get("is_adult"))
    weight_kg = patient_profile.get("weight_kg")
    gender = (patient_profile.get("gender") or "unknown").strip()
    allergies_raw = (patient_profile.get("allergies") or "").strip()
    allergies_low = allergies_raw.lower()
    is_pregnant = patient_profile.get("is_pregnant")
    high_risk_pregnancy = bool(patient_profile.get("high_risk_pregnancy"))
    pregnancy_weeks = patient_profile.get("pregnancy_weeks")

    comorb_raw = patient_profile.get("comorbidities") or []
    comorb_text = (
        " | ".join(str(x) for x in comorb_raw)
        if isinstance(comorb_raw, list)
        else str(comorb_raw)
    ).lower()
    # Loại bỏ mệnh đề phủ định ("không suy thận", "không bệnh gan"...) tránh dương tính giả
    comorb_pos = re.sub(
        r"không\s+(?:có\s+|tiền sử\s+|bị\s+|mắc\s+)?(?:suy thận[^.;,]*|suy gan[^.;,]*|bệnh gan[^.;,]*|loét dạ dày[^.;,]*)",
        "",
        comorb_text,
    )
    current_meds_raw = patient_profile.get("current_medications") or []
    current_meds_text = (
        " | ".join(str(x) for x in current_meds_raw)
        if isinstance(current_meds_raw, list)
        else str(current_meds_raw)
    ).lower()

    renal_status = str(patient_profile.get("renal_impairment") or "").lower()
    liver_status = str(patient_profile.get("liver_disease") or "").lower()
    egfr = patient_profile.get("egfr")

    # ── Rule 1: Missing required safety info & high-risk groups ──
    if age is None and not is_adult:
        missing_fields.append("age")
        add_block("MISSING_INFO", "PATIENT", "Thiếu thông tin tuổi bệnh nhân — không đủ căn cứ kiểm tra liều an toàn.")

    if age is not None and isinstance(age, (int, float)) and age < 18:
        if weight_kg is None:
            missing_fields.append("weight_kg")
            add_block(
                "MISSING_INFO",
                "PATIENT",
                f"Bệnh nhi ({age} tuổi) thiếu cân nặng (kg) — dừng đề xuất liều nhi khoa, yêu cầu bổ sung cân nặng.",
            )
        else:
            add_warn("PEDIATRIC_REVIEW", "PATIENT", f"Bệnh nhi ({age} tuổi, {weight_kg} kg): bác sĩ cần đối chiếu liều theo cân nặng.")

    if not allergies_raw or allergies_low in {"unknown", "chưa rõ", "chưa ghi", "chưa có thông tin", "missing"}:
        missing_fields.append("allergies")
        add_block(
            "MISSING_INFO",
            "PATIENT",
            "Thiếu tiền sử dị ứng thuốc (allergies='unknown') — bắt buộc bác sĩ hỏi và xác nhận dị ứng trước khi hoàn tất.",
        )

    if high_risk_pregnancy:
        add_block(
            "HIGH_RISK_PREGNANCY",
            "PATIENT",
            "Thai kỳ giai đoạn sớm có dấu hiệu nguy cơ cao (dọa sảy / ra huyết) — dừng chốt đơn ngoại trú, chuyển bác sĩ chuyên khoa Sản duyệt trực tiếp.",
        )

    if is_pregnant is True and pregnancy_weeks and int(pregnancy_weeks) >= 28:
        add_warn(
            "PREGNANCY_TRIMESTER_3",
            "PATIENT",
            f"Thai kỳ tuần {pregnancy_weeks} (tam cá nguyệt 3): bác sĩ cần đánh giá kỹ lợi ích/nguy cơ từng thuốc trước khi duyệt.",
        )

    # Check CKD stage 3 & Elderly polypharmacy
    is_ckd_stage3_plus = (
        "suy thận" in comorb_pos
        or "n18" in comorb_pos
        or "ckd" in comorb_pos
        or renal_status == "true"
        or "suy thận" in renal_status
        or (isinstance(egfr, (int, float)) and egfr < 60)
    )
    is_severe_renal = (
        "suy thận nặng" in comorb_pos
        or "giai đoạn 4" in comorb_pos
        or "giai đoạn 5" in comorb_pos
        or "lọc máu" in comorb_pos
        or (isinstance(egfr, (int, float)) and egfr < 30)
    )
    if is_ckd_stage3_plus:
        add_warn(
            "RENAL_ADJUSTMENT_REQUIRED",
            "PATIENT",
            "Bệnh nhân có bệnh nền suy thận mạn: bác sĩ cần hiệu chỉnh liều theo eGFR và tránh thuốc độc thận (NSAID).",
        )

    is_polypharmacy_unknown = bool(patient_profile.get("polypharmacy_unknown")) or (
        ("nhiều thuốc" in current_meds_text or "đa thuốc" in current_meds_text or "cabg" in comorb_text or "mạch vành" in comorb_text)
        and (age is not None and age >= 65)
    )
    if is_polypharmacy_unknown:
        add_warn(
            "POLYPHARMACY_RECONCILIATION",
            "PATIENT",
            "Bệnh nhân cao tuổi đa bệnh lý tim mạch đang dùng nhiều thuốc: bắt buộc bác sĩ đối chiếu danh sách thuốc hiện dùng để rà tương tác trước khi duyệt.",
        )

    # ── Inspect each proposed medication ──
    in_scope_set = {_normalize_icd_prefix(c) for c in (in_scope_codes or [])}
    seen_components: dict[str, str] = {}
    seen_classes: dict[str, str] = {}
    resolved_drugs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    draft_classes: set[str] = set()

    for med in draft_meds or []:
        did = str(med.get("drug_id") or "").strip()
        if did not in catalog:
            add_block("UNVERIFIED_DRUG", did or "UNKNOWN", f"Thuốc '{did}' không tồn tại trong danh mục đã xác minh.")
            continue
        cat_drug = catalog[did]
        resolved_drugs.append((med, cat_drug))
        draft_classes.update(_drug_class_tokens(cat_drug.get("drug_class", "")))

    has_nsaid_or_steroid = bool(
        draft_classes & {"NSAID", "NSAID_COX2", "Systemic_Corticosteroid"}
    )

    for med, cat_drug in resolved_drugs:
        did = cat_drug["drug_id"]
        cname = cat_drug["canonical_name"]
        dclass = cat_drug.get("drug_class", "")
        class_tokens = _drug_class_tokens(dclass)
        tags = set(cat_drug.get("contraindication_tags") or [])

        # Rule 3: Indication match
        drug_icds = set(cat_drug.get("verified_indications_icd10") or [])
        gastroprotection_ok = ("PPI" in class_tokens and has_nsaid_or_steroid)
        if in_scope_set and not (drug_icds & in_scope_set) and not gastroprotection_ok:
            add_block(
                "INDICATION_MISMATCH",
                did,
                f"{cname} ({did}) chỉ định cho {sorted(drug_icds)}, không khớp chẩn đoán hiện tại {sorted(in_scope_set)}.",
            )

        # Rule 4: Duplicate therapy (component & single drug_class)
        for comp in cat_drug.get("component_ingredients") or []:
            clow = comp.lower().strip()
            if clow in seen_components:
                add_block(
                    "DUPLICATE_THERAPY",
                    did,
                    f"Trùng hoạt chất '{comp}' giữa {seen_components[clow]} và {did} ({cname}).",
                )
            else:
                seen_components[clow] = did

        if dclass in SINGLE_CLASS_LIMITS:
            if dclass in seen_classes:
                add_block(
                    "DUPLICATE_THERAPY",
                    did,
                    f"Trùng nhóm điều trị '{dclass}' giữa {seen_classes[dclass]} và {did} ({cname}).",
                )
            else:
                seen_classes[dclass] = did

        # Rule 5 & 6 will also cross-check current_medications
        # Rule 7: Contraindications (allergy + comorbidities + pregnancy + renal/liver)
        allergy_hit = False
        if allergies_low and allergies_low not in {"không", "khong", "none", "không ghi nhận", "unknown"}:
            names_to_check = [
                cname.lower(),
                cat_drug.get("active_ingredient", "").lower(),
                *(a.lower() for a in cat_drug.get("aliases") or []),
                *(c.lower() for c in cat_drug.get("component_ingredients") or []),
            ]
            if any(n and n in allergies_low for n in names_to_check):
                allergy_hit = True
            if ("nsaid" in allergies_low or "kháng viêm" in allergies_low) and (
                class_tokens & {"NSAID", "NSAID_COX2", "Topical_NSAID"} or "nsaid_allergy" in tags
            ):
                allergy_hit = True
            if "ppi" in allergies_low and ("PPI" in class_tokens or "ppi_allergy" in tags):
                allergy_hit = True
            if "statin" in allergies_low and ("Statin" in class_tokens):
                allergy_hit = True
            if any(k in allergies_low for k in ("penicillin", "amoxicillin", "beta-lactam")) and (
                "Beta-lactam" in class_tokens or "penicillin_allergy" in tags
            ):
                allergy_hit = True
            if "sulfonamid" in allergies_low and "sulfonamide_allergy" in tags:
                allergy_hit = True

        if allergy_hit:
            add_block("CONTRAINDICATION", did, f"Chống chỉ định do tiền sử dị ứng ('{allergies_raw}') với {cname} ({did}).")

        if is_pregnant is True and "pregnancy" in tags:
            add_block("CONTRAINDICATION", did, f"Chống chỉ định {cname} ({did}) cho phụ nữ đang mang thai.")
        elif (
            is_pregnant in ("unknown", None)
            and gender == "Nữ"
            and isinstance(age, (int, float))
            and 15 <= age <= 50
            and "pregnancy" in tags
        ):
            add_warn(
                "PREGNANCY_CHECK_REQUIRED",
                did,
                f"Bệnh nhân nữ trong độ tuổi sinh sản ({age} tuổi): cần xác nhận không mang thai trước khi dùng {cname}.",
            )

        if is_ckd_stage3_plus and (class_tokens & {"NSAID", "NSAID_COX2"} or "ckd_stage3_caution" in tags):
            add_block(
                "CONTRAINDICATION",
                did,
                f"Tránh/chống chỉ định thuốc độc thận {cname} ({did}) ở bệnh nhân suy thận mạn.",
            )
        if is_severe_renal and "severe_renal_impairment" in tags:
            add_block("CONTRAINDICATION", did, f"Chống chỉ định {cname} ({did}) khi suy thận nặng (eGFR < 30).")

        if (liver_status == "true" or "gan" in liver_status or "men gan" in comorb_pos or "viêm gan" in comorb_pos or "xơ gan" in comorb_pos) and (
            tags & {"active_liver_disease", "severe_liver_disease"}
        ):
            add_block("CONTRAINDICATION", did, f"Chống chỉ định/thận trọng cao {cname} ({did}) trên bệnh nhân có bệnh gan.")

        if ("hen" in comorb_pos or "asthma" in comorb_pos) and "severe_asthma" in tags:
            add_warn("COMORBIDITY_CAUTION", did, f"Bệnh nhân có tiền sử hen: thận trọng kiểm tra nguy cơ co thắt phế quản với {cname}.")

        # Rule 8: Max daily dose check
        max_dose_info = cat_drug.get("max_daily_dose") or {}
        max_val = max_dose_info.get("value")
        max_unit = max_dose_info.get("unit") or ""
        dose_per_intake = med.get("dose_per_intake")
        freq = med.get("frequency_per_day")
        if max_val is not None and dose_per_intake is not None and freq is not None:
            try:
                per_unit_amt = _parse_single_dose_amount(cat_drug.get("strength_dosage"), max_unit)
                if per_unit_amt is not None:
                    daily_total = float(dose_per_intake) * float(freq) * per_unit_amt
                    if daily_total > float(max_val) + 1e-6:
                        add_block(
                            "OVERDOSE",
                            did,
                            f"Vượt liều tối đa/ngày của {cname}: tính ra {daily_total:g} {max_unit}/ngày > giới hạn {max_dose_info.get('display')}.",
                        )
            except (TypeError, ValueError):
                pass

    # ── Rule 5: Dual RAAS Blockade (ACEi + ARB) across draft + current_medications ──
    has_acei = any(_is_acei(d) for _, d in resolved_drugs) or any(
        k in current_meds_text for k in ("perindopril", "lisinopril", "enalapril", "acei", "coversyl")
    )
    has_arb = any(_is_arb(d) for _, d in resolved_drugs) or any(
        k in current_meds_text for k in ("losartan", "valsartan", "telmisartan", "candesartan", "irbesartan", "arb")
    )
    if has_acei and has_arb:
        add_block(
            "DUAL_RAAS_BLOCKADE",
            "RAAS",
            "CẤM phối hợp kép ACEi + ARB (nguy cơ tụt huyết áp, tăng kali máu, suy thận cấp).",
        )

    # ── Rule 6: Drug-Drug Interactions (draft vs draft + draft vs current_medications) ──
    other_tokens_by_drug: list[tuple[str, str]] = []
    for _, d in resolved_drugs:
        tok_str = " | ".join(
            [
                d["canonical_name"],
                d.get("drug_class", ""),
                " ".join(d.get("aliases") or []),
                " ".join(d.get("component_ingredients") or []),
            ]
        ).lower()
        other_tokens_by_drug.append((d["drug_id"], tok_str))

    for _, d in resolved_drugs:
        did = d["drug_id"]
        cname = d["canonical_name"]
        for inter in d.get("interactions") or []:
            target_raw = inter.get("with_ingredient_or_class") or ""
            target_parts = [p.strip().lower() for p in re.split(r"[/,]+", target_raw) if p.strip()]
            # Match against current_medications
            hit_current = any(tp in current_meds_text for tp in target_parts)
            # Match against other draft drugs
            hit_draft_ids = [
                odid
                for odid, otok in other_tokens_by_drug
                if odid != did and any(tp in otok for tp in target_parts)
            ]
            if hit_current or hit_draft_ids:
                where = "thuốc đang dùng" if hit_current else f"thuốc trong đơn ({', '.join(hit_draft_ids)})"
                msg = f"Tương tác {cname} ({did}) với {target_raw} ({where}): {inter.get('mechanism_and_risk')}"
                if inter.get("action") == "BLOCK":
                    add_block("DRUG_INTERACTION", did, msg)
                else:
                    add_warn("DRUG_INTERACTION", did, msg)

    if blocking:
        status = "BLOCKED"
    elif warnings:
        status = "PASS_WITH_WARNINGS"
    else:
        status = "PASS"

    return {
        "status": status,
        "blocking_violations": blocking,
        "warnings": warnings,
        "missing_fields": missing_fields,
    }


@tool
def calculate_cost(approved_meds: list[dict[str, Any]]) -> dict[str, Any]:
    """Tên: calculate_cost · Input: danh sách thuốc kèm quantity · Output: chi phí từng thuốc và tổng chi phí giả lập · Không tác động ra ngoài."""
    catalog = _drugs_by_id()
    items: list[dict[str, Any]] = []
    total = 0

    for med in approved_meds or []:
        did = str(med.get("drug_id") or "").strip()
        if did not in catalog:
            raise ValueError(f"Không thể tính giá: drug_id '{did}' không tồn tại trong danh mục xác minh.")
        qty_raw = med.get("quantity")
        try:
            qty = int(qty_raw)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Số lượng không hợp lệ cho {did}: {qty_raw!r}") from e
        if qty <= 0:
            raise ValueError(f"Số lượng phải > 0 cho {did}: {qty}")

        drug = catalog[did]
        unit_price = int(drug["unit_price_vnd_synthetic"])
        subtotal = qty * unit_price
        total += subtotal
        items.append(
            {
                "drug_id": did,
                "canonical_name": drug["canonical_name"],
                "unit": drug.get("unit") or "Viên",
                "quantity": qty,
                "unit_price_vnd_synthetic": unit_price,
                "subtotal_vnd": subtotal,
            }
        )

    return {
        "items": items,
        "total_cost_vnd": total,
        "is_synthetic_price": True,
        "note": "Chi phí giả lập tham khảo (seed=42), không phải hóa đơn thật.",
    }
