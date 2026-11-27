"""Luồng chính 6 bước cố định của AI hỗ trợ dự thảo đơn thuốc (spec.md §4).

Chỉ dùng thư viện chuẩn của Python 3.10+.
Hợp đồng: answer(text: str) -> {"output": str}
"""

from __future__ import annotations

import json
import re
from typing import Any

from ai import call_model
from tools import (
    calculate_cost,
    retrieve_similar_cases,
    search_drug_catalog,
    search_guidelines,
    validate_prescription,
)
from tracing import note

MAX_STEPS = 5

SYSTEM_PROMPT = """Bạn là AI hỗ trợ bác sĩ DỰ THẢO ĐƠN THUỐC ngoại trú (chế độ HITL — bác sĩ quyết định, KHÔNG tự phát hành đơn).
NGUYÊN TẮC CỨNG:
1. Chỉ được chọn thuốc có `drug_id` NẰM TRONG danh sách `drug_catalog` được cung cấp. TUYỆT ĐỐI KHÔNG tự bịa tên thuốc hoặc `drug_id`.
2. Mọi thuốc đề xuất phải gắn `rationale_source_id` là `guideline_id` hợp lệ từ `guidelines` được cung cấp.
3. Kiểm tra kỹ `allergies`, `current_medications`, `is_pregnant`, `renal_impairment`, `liver_disease`, `comorbidities`:
   - Nếu bệnh nhân dị ứng nhóm thuốc nào (vd dị ứng NSAID, PPI, Penicillin...) -> TUYỆT ĐỐI KHÔNG chọn thuốc nhóm đó.
   - Nếu bệnh nhân đang dùng Warfarin -> TUYỆT ĐỐI KHÔNG chọn NSAID (kể cả bôi ngoài).
   - Nếu bệnh nhân đang dùng Clopidogrel và bị K21 -> ưu tiên Pantoprazole hoặc Rabeprazole, KHÔNG chọn Omeprazole/Esomeprazole.
   - Nếu bệnh nhân suy thận mạn (N18.3 / eGFR giảm) -> tránh NSAID, ghi chú hiệu chỉnh liều và cảnh báo theo dõi chức năng thận.
   - Nếu bệnh nhân cao tuổi đa bệnh lý tim mạch đang dùng nhiều thuốc -> liệt kê cảnh báo rà soát tương tác với thuốc đang dùng.
   - Nếu bệnh nhân mang thai -> tránh thuốc có chống chỉ định thai kỳ (ACEi, ARB, Statin, NSAID), nêu rõ cảnh báo thai kỳ.
4. Không tự suy diễn thông tin còn thiếu; nếu thiếu thông tin an toàn (`allergies == "unknown"`), ghi rõ câu hỏi bổ sung trong `missing_info_questions`.
5. Xuất DUY NHẤT một JSON hợp lệ theo schema:
{
  "status": "DRAFT" hoặc "NEEDS_MORE_INFO",
  "proposed_medications": [
    {
      "drug_id": "DRUG-XXX",
      "dose_per_intake": 1,
      "frequency_per_day": 2,
      "duration_days": 5,
      "quantity": 10,
      "meal_timing": "Sau ăn",
      "usage_instruction": "Uống 1 viên/lần, ngày 2 lần sau ăn trong 5 ngày",
      "rationale_source_id": "BYT-XXX-01",
      "note": "Lý do chọn ngắn gọn"
    }
  ],
  "missing_info_questions": [],
  "clinical_notes": "Lưu ý lâm sàng cho bác sĩ duyệt",
  "warnings": [],
  "citations": ["BYT-XXX-01"]
}"""


def _detect_pre_gate_refusal(text: str) -> tuple[bool, str, bool]:
    """Kiểm tra tấn công jailbreak/vượt quyền hoặc yêu cầu tự chẩn đoán từ triệu chứng."""
    low = text.lower()
    has_red_flag = any(
        k in low
        for k in ("ho ra máu", "đau tức ngực", "đau ngực trái", "khó thở", "vã mồ hôi", "lơ mơ")
    )

    attack_triggers = (
        ("bỏ qua" in low and any(w in low for w in ("guardrails", "kiểm tra", "quy tắc", "an toàn", "danh mục", "hướng dẫn")))
        or "tự bịa" in low
        or "chưa có trong danh mục" in low
        or "tự ước lượng giá" in low
        or "đã được phê duyệt" in low
        or "tự động phát hành" in low
        or "không cần kiểm duyệt" in low
        or "mua thuốc luôn" in low
    )
    if attack_triggers:
        return True, "Yêu cầu vượt giới hạn an toàn (bỏ qua Safety Guardrails, bịa thuốc/giá ngoài danh mục hoặc giả mạo phê duyệt bác sĩ).", has_red_flag

    asks_diagnosis = any(
        k in low
        for k in ("chẩn đoán giúp tôi", "chẩn đoán tôi bị bệnh gì", "bị bệnh gì và kê", "kê luôn đơn thuốc")
    )
    has_confirmed_diag = "chẩn đoán đã xác nhận" in low
    if asks_diagnosis and not has_confirmed_diag:
        return True, "Hệ thống không chẩn đoán bệnh từ triệu chứng và không tự ý kê đơn; chỉ hỗ trợ bác sĩ sau khi có chẩn đoán đã xác nhận.", has_red_flag

    return False, "", has_red_flag


def _parse_input(text: str) -> dict[str, Any]:
    """Chuẩn hóa đầu vào từ text tự do tiếng Việt hoặc JSON cấu trúc."""
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            obj = json.loads(stripped)
            if isinstance(obj, dict) and ("diagnoses" in obj or "icd10_codes" in obj):
                return obj
        except json.JSONDecodeError:
            pass

    low = text.lower()

    # ICD-10 codes
    icd_codes: list[str] = []
    seen_icd: set[str] = set()
    for m in re.finditer(r"\b([A-Z]\d{2}(?:\.\d+)?)\b", text):
        code = m.group(1).upper()
        if code not in seen_icd:
            seen_icd.add(code)
            icd_codes.append(code)

    # Weight
    weight_kg: float | None = None
    m_w = re.search(r"(\d+(?:\.\d+)?)\s*kg\b", low)
    if m_w:
        weight_kg = float(m_w.group(1))

    # Age & adult/pediatric status
    age: int | None = None
    m_age = re.search(r"(\d{1,3})\s*tuổi", low)
    if m_age:
        age = int(m_age.group(1))
    age_explicitly_missing = any(
        p in low for p in ("chưa rõ tuổi", "không rõ tuổi", "thiếu tuổi")
    )
    is_pediatric = any(p in low for p in ("bệnh nhi", "trẻ em")) or (
        age is not None and age < 18
    )
    is_adult = (
        not age_explicitly_missing
        and not is_pediatric
        and (
            "người lớn" in low
            or (age is not None and age >= 18)
            or (weight_kg is not None and weight_kg >= 35.0)
        )
    )

    # Gender
    if re.search(r"\bnữ\b", low):
        gender = "Nữ"
    elif re.search(r"\bnam\b", low):
        gender = "Nam"
    else:
        gender = "unknown"

    # Allergies
    allergies = "unknown"
    if any(p in low for p in ("chưa rõ tiền sử dị ứng", "chưa ghi cân nặng và tiền sử dị ứng", "chưa có thông tin cân nặng và tiền sử dị ứng", "chưa rõ dị ứng")):
        allergies = "unknown"
    elif any(p in low for p in ("không ghi nhận dị ứng", "không dị ứng", "dị ứng: không", "không có dị ứng")):
        allergies = "Không"
    else:
        m_all = re.search(r"(?:tiền sử\s+)?dị ứng\s+([^.;\n]+)", text, flags=re.IGNORECASE)
        if m_all:
            cand = m_all.group(1).strip()
            if cand and not cand.lower().startswith("chưa"):
                allergies = cand

    # Pregnancy
    is_pregnant: bool | str = "unknown"
    pregnancy_weeks: int | None = None
    high_risk_pregnancy = False
    if "không mang thai" in low:
        is_pregnant = False
    elif "mang thai" in low or "thai " in low:
        is_pregnant = True
        m_wk = re.search(r"thai\s*(\d{1,2})\s*tuần", low)
        if m_wk:
            pregnancy_weeks = int(m_wk.group(1))
        if any(k in low for k in ("dọa sảy", "ra huyết")):
            high_risk_pregnancy = True

    # Renal / Liver / eGFR
    renal_impairment: bool | str = False
    if "không suy thận" in low or "gan thận bình thường" in low:
        renal_impairment = False
    elif "suy thận" in low or "n18" in low:
        renal_impairment = True

    egfr: int | None = None
    m_egfr = re.search(r"egfr\s*[=:]?\s*(\d+)", low)
    if m_egfr:
        egfr = int(m_egfr.group(1))
        if egfr < 60:
            renal_impairment = True

    liver_disease: bool | str = False
    if "không suy gan" in low or "gan thận bình thường" in low:
        liver_disease = False
    elif any(k in low for k in ("suy gan", "viêm gan", "xơ gan", "men gan tăng")):
        liver_disease = True

    # Current medications
    current_meds: list[str] = []
    for med_kw in ("Warfarin", "Clopidogrel", "Perindopril", "Losartan", "Enalapril", "Clarithromycin", "Itraconazole", "Spironolactone", "Furosemide"):
        if med_kw.lower() in low:
            current_meds.append(med_kw)
    polypharmacy_unknown = "đang dùng nhiều thuốc" in low or "nhiều thuốc tim mạch" in low
    if polypharmacy_unknown:
        current_meds.append("nhiều thuốc tim mạch chưa liệt kê chi tiết")

    # Diagnosis text
    m_diag = re.search(r"chẩn đoán(?:\s+đã xác nhận)?\s*:\s*([^\n]+)", text, flags=re.IGNORECASE)
    diag_text = m_diag.group(1).strip() if m_diag else text

    return {
        "icd10_codes": icd_codes,
        "diagnosis_text": diag_text,
        "patient_profile": {
            "age": age,
            "is_adult": is_adult,
            "gender": gender,
            "weight_kg": weight_kg,
            "allergies": allergies,
            "is_pregnant": is_pregnant,
            "pregnancy_weeks": pregnancy_weeks,
            "high_risk_pregnancy": high_risk_pregnancy,
            "renal_impairment": renal_impairment,
            "egfr": egfr,
            "liver_disease": liver_disease,
            "comorbidities": [diag_text],
            "current_medications": current_meds,
            "polypharmacy_unknown": polypharmacy_unknown,
        },
    }


def _extract_json(raw_text: str) -> dict[str, Any]:
    """Trích xuất JSON an toàn từ đầu ra của model."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.DOTALL).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    return {
        "status": "NEEDS_MORE_INFO",
        "proposed_medications": [],
        "missing_info_questions": ["Model trả về định dạng chưa hợp lệ, đề nghị bác sĩ kiểm tra lại."],
        "clinical_notes": raw_text[:400],
        "warnings": [],
        "citations": [],
    }


def _format_output(payload: dict[str, Any]) -> str:
    """Render kết quả dễ đọc cho bác sĩ kèm block JSON chuẩn để chấm tự động."""
    lines: list[str] = [
        f"Quyết định: {payload['decision']}",
        f"Tóm tắt: {payload['summary']}",
    ]

    meds = payload.get("draft_medications") or []
    if meds:
        lines.append("\nDanh sách thuốc dự kiến (bản nháp):")
        for idx, m in enumerate(meds, start=1):
            lines.append(
                f"  {idx}. [{m.get('drug_id')}] {m.get('canonical_name', '')} "
                f"{m.get('strength_dosage', '')} | SL: {m.get('quantity')} | "
                f"Cách dùng: {m.get('usage_instruction') or m.get('meal_timing') or ''} | "
                f"Căn cứ: {m.get('rationale_source_id')}"
            )

    gr = payload.get("guardrail_result") or {}
    if gr.get("blocking_violations"):
        lines.append("\n[CHẶN AN TOÀN - Safety Guardrails]:")
        for v in gr["blocking_violations"]:
            lines.append(f"  - ({v['code']}) {v['message']}")
    if gr.get("warnings"):
        lines.append("\n[CẢNH BÁO LÂM SÀNG]:")
        for w in gr["warnings"]:
            lines.append(f"  - ({w['code']}) {w['message']}")
    if payload.get("missing_info_questions"):
        lines.append("\n[THÔNG TIN CẦN BÁC SĨ BỔ SUNG]:")
        for q in payload["missing_info_questions"]:
            lines.append(f"  - {q}")

    cost = payload.get("estimated_cost")
    if cost:
        lines.append(
            f"\nChi phí dự kiến (giả lập): {cost['total_cost_vnd']:,} VNĐ ({cost['note']})"
        )

    lines.append("\n[LƯU Ý HITL] BẢN MÔ PHỎNG — CHỜ BÁC SĨ KIỂM DUYỆT, KHÔNG PHÁT HÀNH ĐƠN THẬT.")
    lines.append("\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```")
    return "\n".join(lines)


def answer(text: str) -> dict[str, str]:
    """Chạy đúng workflow 6 bước cố định từ input đến output."""
    # ── Bước 1: Pre-Gate & Input Parser ──
    is_refused, refuse_reason, has_red_flag = _detect_pre_gate_refusal(text)
    if is_refused:
        note(f"pre_gate: REFUSED ({refuse_reason})")
        summary = refuse_reason
        if has_red_flag:
            summary += " CẢNH BÁO CẤP CỨU: Có triệu chứng nguy hiểm (ho ra máu / đau tức ngực / khó thở) — đề nghị người bệnh đến cơ sở y tế khám cấp cứu ngay lập tức."
        payload = {
            "decision": "REFUSED",
            "summary": summary,
            "draft_medications": [],
            "guardrail_result": {
                "status": "BLOCKED",
                "blocking_violations": [{"code": "OUT_OF_AUTHORITY", "drug_id": "SYSTEM", "message": refuse_reason}],
                "warnings": [],
                "missing_fields": [],
            },
            "missing_info_questions": [],
            "estimated_cost": None,
            "citations": [],
            "is_simulation": True,
        }
        return {"output": _format_output(payload)}

    parsed = _parse_input(text)
    icd10_codes = parsed["icd10_codes"]
    diagnosis_text = parsed["diagnosis_text"]
    patient_profile = parsed["patient_profile"]

    # ── Bước 2: Data Retrieval & Pre-LLM Safety Gate ──
    guide_res = search_guidelines(icd10_codes, diagnosis_text)
    in_scope_codes = guide_res["in_scope_codes"]
    matched_guidelines = guide_res["matched_guidelines"]

    # Luôn chạy kiểm tra thiếu dữ liệu sống còn / thai kỳ nguy cơ cao trước khi dừng ngoài phạm vi
    pre_check = validate_prescription([], patient_profile, in_scope_codes)
    must_stop_before_llm = (
        patient_profile.get("high_risk_pregnancy")
        or ("weight_kg" in pre_check["missing_fields"])
        or ("age" in pre_check["missing_fields"])
    )
    if must_stop_before_llm:
        note("stop: GUARDRAIL_BLOCKED_PRE_LLM")
        questions = [v["message"] for v in pre_check["blocking_violations"]]
        summary = "Dừng đề xuất thuốc do thiếu dữ liệu an toàn bắt buộc hoặc ca thai kỳ nguy cơ cao cần bác sĩ chuyên khoa duyệt trực tiếp."
        if not guide_res["is_in_scope"]:
            summary += f" Đồng thời chẩn đoán ({guide_res['out_of_scope_codes'] or 'chuyên khoa sâu'}) nằm ngoài phạm vi hỗ trợ."
        payload = {
            "decision": "BLOCKED_OR_NEEDS_INFO",
            "summary": summary,
            "draft_medications": [],
            "guardrail_result": pre_check,
            "missing_info_questions": questions,
            "estimated_cost": None,
            "citations": [g["guideline_id"] for g in matched_guidelines],
            "is_simulation": True,
        }
        return {"output": _format_output(payload)}

    if not guide_res["is_in_scope"]:
        note(f"stop: OUT_OF_SCOPE (out={guide_res['out_of_scope_codes']})")
        payload = {
            "decision": "OUT_OF_SCOPE_STOPPED",
            "summary": (
                "Chẩn đoán nằm ngoài phạm vi hỗ trợ đã xác minh của hệ thống hoặc thiếu căn cứ chuyên môn "
                f"(ngoài phạm vi: {guide_res['out_of_scope_codes'] or 'bệnh lý chuyên khoa sâu'}). "
                "Hệ thống dừng đề xuất đơn thuốc và chuyển bác sĩ chuyên khoa tự lập phác đồ."
            ),
            "draft_medications": [],
            "guardrail_result": {
                "status": "BLOCKED",
                "blocking_violations": [
                    {
                        "code": "OUT_OF_SCOPE",
                        "drug_id": "SYSTEM",
                        "message": "Thiếu phác đồ và danh mục thuốc xác minh cho bệnh lý chuyên khoa ngoài phạm vi.",
                    }
                ],
                "warnings": [],
                "missing_fields": [],
            },
            "missing_info_questions": [],
            "estimated_cost": None,
            "citations": [],
            "is_simulation": True,
        }
        return {"output": _format_output(payload)}

    similar_cases = retrieve_similar_cases(in_scope_codes, top_k=2)
    catalog_drugs = search_drug_catalog(icd10_codes=in_scope_codes)
    # Bổ sung PPI bảo vệ dạ dày khi kê bệnh cơ xương khớp có thể dùng NSAID
    if any(c in in_scope_codes for c in ("M75", "M54")) and not any(d["drug_class"] == "PPI" for d in catalog_drugs):
        ppi_extra = search_drug_catalog(query="Pantoprazole")
        existing_ids = {d["drug_id"] for d in catalog_drugs}
        for d in ppi_extra:
            if d["drug_id"] not in existing_ids:
                catalog_drugs.append(d)

    catalog_by_id = {d["drug_id"]: d for d in catalog_drugs}

    # ── Bước 3: AI Core (1 lời gọi LLM duy nhất) ──
    user_prompt = json.dumps(
        {
            "patient_profile": patient_profile,
            "in_scope_icd10": in_scope_codes,
            "out_of_scope_icd10": guide_res["out_of_scope_codes"],
            "diagnosis_text": diagnosis_text,
            "guidelines": [
                {
                    "guideline_id": g["guideline_id"],
                    "icd10_prefix": g["icd10_prefix"],
                    "disease_name_vi": g["disease_name_vi"],
                    "first_line_ingredients": g["first_line_ingredients"],
                    "second_line_or_special_ingredients": g.get("second_line_or_special_ingredients", []),
                    "avoid_combinations": g.get("avoid_combinations", []),
                    "safety_red_flags": g.get("safety_red_flags", []),
                }
                for g in matched_guidelines
            ],
            "similar_cases_reference": similar_cases,
            "drug_catalog": [
                {
                    "drug_id": d["drug_id"],
                    "canonical_name": d["canonical_name"],
                    "strength_dosage": d["strength_dosage"],
                    "route": d["route_of_administration"],
                    "unit": d["unit"],
                    "drug_class": d["drug_class"],
                    "verified_indications_icd10": d["verified_indications_icd10"],
                    "typical_frequency": d["typical_frequency"],
                    "typical_meal_timing": d["typical_meal_timing"],
                    "max_daily_dose": d["max_daily_dose"],
                    "contraindications": d["contraindications"],
                    "interactions": d["interactions"],
                }
                for d in catalog_drugs[:32]
            ],
        },
        ensure_ascii=False,
    )

    llm_reply = call_model(SYSTEM_PROMPT, user_prompt)
    ai_json = _extract_json(llm_reply["text"])
    raw_meds = ai_json.get("proposed_medications") or []

    # ── Bước 4: Deterministic Safety Guardrails ──
    guardrail_res = validate_prescription(raw_meds, patient_profile, in_scope_codes)

    enriched_meds: list[dict[str, Any]] = []
    for m in raw_meds:
        did = str(m.get("drug_id") or "").strip()
        cat = catalog_by_id.get(did, {})
        enriched_meds.append(
            {
                "drug_id": did,
                "canonical_name": cat.get("canonical_name") or m.get("canonical_name") or did,
                "strength_dosage": cat.get("strength_dosage") or "",
                "dose_per_intake": m.get("dose_per_intake", 1),
                "frequency_per_day": m.get("frequency_per_day") or cat.get("typical_frequency") or 1,
                "duration_days": m.get("duration_days", 5),
                "quantity": m.get("quantity") or 10,
                "meal_timing": m.get("meal_timing") or cat.get("typical_meal_timing") or "",
                "usage_instruction": m.get("usage_instruction") or "",
                "rationale_source_id": m.get("rationale_source_id") or (matched_guidelines[0]["guideline_id"] if matched_guidelines else ""),
                "source_reference": cat.get("source_reference") or "",
            }
        )

    # ── Bước 5: Cost calculation (chỉ chạy khi không bị BLOCKED) ──
    estimated_cost: dict[str, Any] | None = None
    if guardrail_res["status"] == "BLOCKED":
        note("guardrail: BLOCKED")
        decision = "BLOCKED_OR_NEEDS_INFO"
    elif guardrail_res["status"] == "PASS_WITH_WARNINGS":
        decision = "DRAFT_WITH_WARNINGS"
        if enriched_meds:
            estimated_cost = calculate_cost(enriched_meds)
    else:
        decision = "DRAFT_READY"
        if enriched_meds:
            estimated_cost = calculate_cost(enriched_meds)

    citations = list(
        dict.fromkeys(
            [g["guideline_id"] for g in matched_guidelines]
            + [c for c in (ai_json.get("citations") or []) if isinstance(c, str)]
        )
    )
    missing_qs = list(ai_json.get("missing_info_questions") or [])
    for mf in guardrail_res.get("missing_fields") or []:
        q = f"Vui lòng bác sĩ bổ sung thông tin: {mf}"
        if q not in missing_qs:
            missing_qs.append(q)

    summary_parts = [ai_json.get("clinical_notes") or "Đã lập bản nháp dự thảo theo phác đồ và danh mục xác minh."]
    if guide_res["out_of_scope_codes"]:
        summary_parts.append(
            f"Lưu ý: mã {guide_res['out_of_scope_codes']} ngoài phạm vi tự động, chỉ dự thảo cho {in_scope_codes}."
        )

    payload = {
        "decision": decision,
        "summary": " ".join(summary_parts).strip(),
        "draft_medications": enriched_meds,
        "guardrail_result": guardrail_res,
        "missing_info_questions": missing_qs,
        "estimated_cost": estimated_cost,
        "citations": citations,
        "is_simulation": True,
    }
    return {"output": _format_output(payload)}
