"""Build a clean, PII-free, synthetic-labeled dataset for the prescription drafting AI.

Workflow supported:
    search_guidelines -> retrieve_similar_cases -> search_drug_catalog
    -> validate_prescription -> calculate_cost

Usage:
    python scripts/build_clean_dataset.py --input 100_Toa_NVM_2026_Dataset.csv
    python scripts/build_clean_dataset.py --input data/100_Toa_NVM_2026_Dataset.csv --scope all
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Group A: 22 columns containing PII, administrative, or facility identifiers.
PII_ADMIN_COLUMNS: list[str] = [
    "prescription_code",
    "prescription_type",
    "patient_payment_type",
    "hospital_clinic_name",
    "hospital_address",
    "hospital_phone",
    "department_room",
    "doctor_name",
    "doctor_phone",
    "prescription_date",
    "prescription_time",
    "patient_id",
    "patient_name",
    "guardian_name",
    "patient_phone",
    "patient_cccd",
    "bhyt_card_number",
    "bhyt_valid_from",
    "bhyt_valid_to",
    "patient_dob",
    "patient_address",
    "med_coverage_category",
]

# Group B: 11 columns with >75% missingness or outside confirmed-diagnosis scope.
SPARSE_OOS_COLUMNS: list[str] = [
    "height_cm",
    "bmi",
    "pulse_bpm",
    "blood_pressure_mmhg",
    "temperature_c",
    "respiratory_rate",
    "symptoms_clinical_notes",
    "re_examination_date",
    "re_examination_department",
    "doctor_advice_lifestyle",
    "duration_days",
]

CORE_DISEASE_GROUPS: dict[str, dict[str, Any]] = {
    "I10": {
        "name_vi": "Tăng huyết áp",
        "keywords": ["tăng huyết áp", "huyết áp cao"],
    },
    "E78": {
        "name_vi": "Rối loạn mỡ máu",
        "keywords": ["rối loạn mỡ máu", "rối loạn lipid", "tăng lipid", "mỡ máu"],
    },
    "E11": {
        "name_vi": "Đái tháo đường typ 2",
        "keywords": ["đái tháo đường", "tiểu đường"],
    },
    "K21": {
        "name_vi": "Trào ngược dạ dày - thực quản",
        "keywords": ["trào ngược dạ dày", "trào ngược thực quản", "gerd"],
    },
}

PII_AUDIT_PATTERNS: dict[str, re.Pattern[str]] = {
    "vn_phone_10_digits": re.compile(r"(?<!\d)0[35789]\d{8}(?!\d)"),
    "cccd_12_digits": re.compile(r"(?<!\d)\d{12}(?!\d)"),
    "pii_column_leak": re.compile(
        r"\b(?:"
        + "|".join(
            re.escape(col)
            for col in [
                "prescription_code",
                "hospital_clinic_name",
                "hospital_address",
                "hospital_phone",
                "doctor_name",
                "doctor_phone",
                "patient_id",
                "patient_name",
                "guardian_name",
                "patient_phone",
                "patient_cccd",
                "bhyt_card_number",
                "patient_dob",
                "patient_address",
            ]
        )
        + r")\b"
    ),
}


def resolve_input_path(raw_input: str) -> Path:
    """Resolve input CSV path, checking CWD first and falling back to data/."""
    candidate = Path(raw_input)
    if candidate.exists():
        return candidate
    data_candidate = Path("data") / raw_input
    if data_candidate.exists():
        return data_candidate
    raise FileNotFoundError(
        f"Could not find input CSV at '{candidate}' or '{data_candidate}'."
    )


def clean_whitespace(value: Any) -> str | None:
    """Strip and collapse internal whitespace; return None if empty or NaN."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text if text else None


def parse_duration_days(usage_text: Any) -> int | None:
    """Extract duration in days (e.g. '7 ngày') from usage_instruction_full."""
    cleaned = clean_whitespace(usage_text)
    if not cleaned:
        return None
    match = re.search(r"(\d+)\s*ngày\b", cleaned, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def normalize_gender(value: Any) -> str:
    """Normalize gender values to 'Nam', 'Nữ', or 'unknown'."""
    cleaned = clean_whitespace(value)
    if not cleaned:
        return "unknown"
    lowered = cleaned.lower()
    if lowered in {"nam", "male", "m"}:
        return "Nam"
    if lowered in {"nữ", "nu", "female", "f"}:
        return "Nữ"
    return "unknown"


def synthesize_age(value: Any, rng: np.random.Generator) -> int | None:
    """Parse age and apply ±1..2 year perturbation while keeping age group bounds."""
    cleaned = clean_whitespace(value)
    if not cleaned:
        return None
    match = re.search(r"(\d+)", cleaned)
    if not match:
        return None
    age = int(match.group(1))
    if age >= 18:
        delta = int(rng.choice([-2, -1, 1, 2]))
        return max(18, age + delta)
    delta = int(rng.choice([-1, 0, 1]))
    return int(np.clip(age + delta, 1, 17))


def synthesize_weight(value: Any, rng: np.random.Generator) -> float | None:
    """Apply ±1.0 kg synthetic noise to weight_kg and round to 1 decimal place."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        weight = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(weight):
        return None
    noise = float(rng.choice([-1.0, -0.5, 0.5, 1.0]))
    return round(max(3.0, weight + noise), 1)


def normalize_allergies(value: Any) -> str:
    """Preserve allergies field; normalize missing values to 'unknown'."""
    cleaned = clean_whitespace(value)
    return cleaned if cleaned else "unknown"


def parse_icd10_codes(value: Any) -> list[str]:
    """Split ICD-10 string by ';' or ',' and return deduplicated uppercase codes."""
    cleaned = clean_whitespace(value)
    if not cleaned:
        return []
    parts = re.split(r"[;,]+", cleaned)
    seen: set[str] = set()
    codes: list[str] = []
    for part in parts:
        code = part.strip().upper()
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def parse_diagnoses(value: Any) -> list[str]:
    """Clean diagnosis_primary_and_comorbidities into a list of diagnosis strings."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    raw = str(value).replace("\r", "\n")
    parts = re.split(r"[;\n]+", raw)
    diagnoses: list[str] = []
    seen: set[str] = set()
    for part in parts:
        item = re.sub(r"\s+", " ", part).strip(" .-\t")
        if item and item not in seen:
            seen.add(item)
            diagnoses.append(item)
    return diagnoses


def build_dosage_schedule(row: pd.Series) -> dict[str, float]:
    """Merge dose_morning/noon/afternoon/evening into a compact dict."""
    mapping = {
        "morning": "dose_morning",
        "noon": "dose_noon",
        "afternoon": "dose_afternoon",
        "evening": "dose_evening",
    }
    schedule: dict[str, float] = {}
    for key, col in mapping.items():
        val = row.get(col)
        if pd.notna(val):
            try:
                num = float(val)
                schedule[key] = int(num) if num.is_integer() else round(num, 3)
            except (TypeError, ValueError):
                continue
    return schedule


def to_clean_number(value: Any) -> int | float | None:
    """Convert numeric cell to int (if whole) or float, else None."""
    if pd.isna(value):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(num):
        return None
    return int(num) if num.is_integer() else round(num, 3)


def match_core_groups(icd10_codes: list[str], diagnoses: list[str]) -> list[str]:
    """Return matching core chronic disease group prefixes (I10, E78, E11, K21)."""
    matched: list[str] = []
    diag_blob = " | ".join(diagnoses).lower()
    for prefix, meta in CORE_DISEASE_GROUPS.items():
        has_icd = any(code.startswith(prefix) for code in icd10_codes)
        has_kw = any(kw in diag_blob for kw in meta["keywords"])
        if has_icd or has_kw:
            matched.append(prefix)
    return matched


def normalize_drug_key(
    active_ingredient: str,
    strength_dosage: str | None,
    route: str | None,
) -> tuple[str, str, str]:
    """Create canonical lowercase tuple key for drug deduplication."""
    return (
        active_ingredient.lower(),
        (strength_dosage or "").lower(),
        (route or "").lower(),
    )


def most_common_non_null(values: list[Any]) -> Any:
    """Return the most frequent non-null value in a list, or None."""
    filtered = [v for v in values if v is not None]
    if not filtered:
        return None
    counts = Counter(filtered)
    return counts.most_common(1)[0][0]


def build_guidelines_template() -> list[dict[str, Any]]:
    """Build the 4 starter guideline entries for I10, E78, E11, K21."""
    return [
        {
            "guideline_id": "BYT-I10-01",
            "icd10_prefix": "I10",
            "disease_name_vi": "Tăng huyết áp vô căn (nguyên phát)",
            "first_line_ingredients": [
                "Amlodipine",
                "Losartan",
                "Valsartan",
                "Perindopril",
                "Enalapril",
                "Hydrochlorothiazide",
                "Indapamide",
            ],
            "safety_red_flags": [
                "Chống chỉ định ACEi/ARB ở phụ nữ có thai hoặc nghi ngờ mang thai",
                "Thận trọng tăng kali máu và suy thận cấp khi phối hợp ACEi + ARB",
                "Kiểm tra tiền sử phù mạch trước khi kê nhóm ACEi",
            ],
            "missing_info_checks": [
                "allergies",
                "patient_age",
                "weight_kg",
                "renal_function_status",
            ],
            "content_excerpt": (
                "Khởi trị đơn trị liệu hoặc phối hợp liều thấp (CCB, ACEi/ARB, "
                "lợi tiểu thiazide/like-thiazide) tùy phân tầng nguy cơ tim mạch."
            ),
            "official_source_url": "https://kcb.vn/",
        },
        {
            "guideline_id": "BYT-E78-01",
            "icd10_prefix": "E78",
            "disease_name_vi": "Rối loạn chuyển hóa lipoprotein và tình trạng tăng lipid máu",
            "first_line_ingredients": [
                "Atorvastatin",
                "Rosuvastatin",
                "Simvastatin",
                "Fenofibrate",
                "Ezetimibe",
            ],
            "safety_red_flags": [
                "Theo dõi men gan (AST/ALT) và nguy cơ tiêu cơ vân (đau cơ, CK tăng)",
                "Chống chỉ định statin ở bệnh gan tiến triển hoặc phụ nữ có thai",
                "Thận trọng tương tác thuốc làm tăng nồng độ statin",
            ],
            "missing_info_checks": [
                "allergies",
                "patient_age",
                "liver_function_status",
            ],
            "content_excerpt": (
                "Statin là lựa chọn hàng đầu để giảm LDL-C; cân nhắc fibrate khi "
                "triglyceride tăng rất cao có nguy cơ viêm tụy cấp."
            ),
            "official_source_url": "https://kcb.vn/",
        },
        {
            "guideline_id": "BYT-E11-01",
            "icd10_prefix": "E11",
            "disease_name_vi": "Đái tháo đường không phụ thuộc insulin (typ 2)",
            "first_line_ingredients": [
                "Metformin",
                "Gliclazide",
                "Glimepiride",
                "Sitagliptin",
                "Empagliflozin",
                "Dapagliflozin",
            ],
            "safety_red_flags": [
                "Chống chỉ định Metformin khi eGFR < 30 mL/phút/1.73m2 (nguy cơ nhiễm toan lactic)",
                "Cảnh báo nguy cơ hạ đường huyết với nhóm Sulfonylurea (nhất là người cao tuổi)",
                "Hướng dẫn thời điểm uống theo bữa ăn để giảm tác dụng phụ tiêu hóa",
            ],
            "missing_info_checks": [
                "allergies",
                "patient_age",
                "weight_kg",
                "renal_function_status",
            ],
            "content_excerpt": (
                "Metformin là thuốc đầu tay nếu không có chống chỉ định; phối hợp "
                "SGLT2i hoặc DPP-4i/SU dựa trên bệnh đồng mắc tim mạch - thận."
            ),
            "official_source_url": "https://kcb.vn/",
        },
        {
            "guideline_id": "BYT-K21-01",
            "icd10_prefix": "K21",
            "disease_name_vi": "Bệnh trào ngược dạ dày - thực quản (GERD)",
            "first_line_ingredients": [
                "Omeprazole",
                "Esomeprazole",
                "Pantoprazole",
                "Rabeprazole",
                "Lansoprazole",
                "Alginate / Antacid",
            ],
            "safety_red_flags": [
                "Lưu ý tương tác Clopidogrel với Omeprazole/Esomeprazole (giảm hoạt tính chống kết tập tiểu cầu)",
                "Đánh giá triệu chứng báo động (nuốt khó, sụt cân, thiếu máu) trước điều trị kéo dài",
                "Uống PPI trước bữa ăn sáng 30 phút để đạt hiệu quả ức chế acid tối ưu",
            ],
            "missing_info_checks": [
                "allergies",
                "patient_age",
                "concurrent_antiplatelet_use",
            ],
            "content_excerpt": (
                "Ưu tiên PPI liều chuẩn uống trước ăn 30 phút trong 4-8 tuần; "
                "có thể phối hợp antacid/alginate hỗ trợ kiểm soát triệu chứng."
            ),
            "official_source_url": "https://kcb.vn/",
        },
    ]


def run_pii_audit(output_files: list[Path]) -> dict[str, int]:
    """Scan generated JSON files for leaked PII patterns and raise AssertionError if found."""
    findings: list[str] = []
    counts: dict[str, int] = {name: 0 for name in PII_AUDIT_PATTERNS}
    for path in output_files:
        text = path.read_text(encoding="utf-8")
        for name, pattern in PII_AUDIT_PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                counts[name] += len(matches)
                findings.append(f"{path.name}: {name} ({len(matches)} match(es))")
    if findings:
        raise AssertionError("PII audit failed! Detected potential leaks: " + "; ".join(findings))
    return counts


def build_clean_dataset(
    input_path: Path,
    output_dir: Path,
    scope: str = "core",
    seed: int = 42,
) -> None:
    """Execute full cleaning, anonymization, catalog generation, and PII audit."""
    raw_df = pd.read_csv(input_path, encoding="utf-8-sig")
    raw_rows = len(raw_df)
    raw_prescriptions = int(raw_df["page_number"].dropna().nunique())

    # 1. Drop Group A + Group B columns (33 columns).
    cols_to_drop = [c for c in PII_ADMIN_COLUMNS + SPARSE_OOS_COLUMNS if c in raw_df.columns]
    df = raw_df.drop(columns=cols_to_drop).copy()

    # 2. Drop garbage rows where page_number or active_ingredient is NaN/empty.
    df["active_ingredient_clean"] = df["active_ingredient"].apply(clean_whitespace)
    df = df[df["page_number"].notna() & df["active_ingredient_clean"].notna()].copy()
    df["page_num_int"] = df["page_number"].astype(int)

    # Extract duration_days from usage_instruction_full before dropping med_raw_text.
    df["parsed_duration_days"] = df["usage_instruction_full"].apply(parse_duration_days)
    if "med_raw_text" in df.columns:
        df = df.drop(columns=["med_raw_text"])

    rng = np.random.default_rng(seed)

    # 3. Group by prescription (page_num_int) to synthesize patient profiles consistently.
    all_cases: list[dict[str, Any]] = []
    for page_num, group in df.groupby("page_num_int", sort=True):
        first_row = group.iloc[0]
        case_id = f"SYN-CASE-{page_num:03d}"

        icd10_codes = parse_icd10_codes(first_row.get("icd10_codes"))
        diagnoses = parse_diagnoses(first_row.get("diagnosis_primary_and_comorbidities"))
        core_matches = match_core_groups(icd10_codes, diagnoses)

        patient_profile = {
            "age": synthesize_age(first_row.get("patient_age"), rng),
            "gender": normalize_gender(first_row.get("patient_gender")),
            "weight_kg": synthesize_weight(first_row.get("weight_kg"), rng),
            "allergies": normalize_allergies(first_row.get("allergies")),
        }

        all_cases.append(
            {
                "case_id": case_id,
                "is_synthetic": True,
                "seed": seed,
                "patient_profile": patient_profile,
                "icd10_codes": icd10_codes,
                "diagnoses": diagnoses,
                "core_groups": core_matches,
                "rows": group,
            }
        )

    total_cases_before_scope = len(all_cases)
    total_rows_before_scope = sum(len(c["rows"]) for c in all_cases)

    if scope == "core":
        selected_cases = [c for c in all_cases if c["core_groups"]]
    else:
        selected_cases = all_cases

    # 4. Build deduplicated drug_catalog from selected cases.
    drug_buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for case in selected_cases:
        case_icds = case["icd10_codes"]
        for _, row in case["rows"].iterrows():
            ingredient = row["active_ingredient_clean"]
            strength = clean_whitespace(row.get("strength_dosage"))
            route = clean_whitespace(row.get("route_of_administration"))
            key = normalize_drug_key(ingredient, strength, route)

            if key not in drug_buckets:
                drug_buckets[key] = {
                    "active_ingredient": ingredient,
                    "strength_dosage": strength,
                    "route_of_administration": route,
                    "units": [],
                    "brand_names": set(),
                    "frequencies": [],
                    "meal_timings": [],
                    "icd10s": set(),
                }
            bucket = drug_buckets[key]
            unit = clean_whitespace(row.get("unit"))
            if unit:
                bucket["units"].append(unit)
            brand = clean_whitespace(row.get("brand_name"))
            if brand:
                bucket["brand_names"].add(brand)
            freq = to_clean_number(row.get("frequency_per_day"))
            if freq is not None:
                bucket["frequencies"].append(freq)
            meal = clean_whitespace(row.get("meal_timing"))
            if meal:
                bucket["meal_timings"].append(meal)
            bucket["icd10s"].update(case_icds)

    sorted_drug_keys = sorted(drug_buckets.keys())
    drug_catalog: list[dict[str, Any]] = []
    key_to_drug_id: dict[tuple[str, str, str], str] = {}

    for idx, key in enumerate(sorted_drug_keys, start=1):
        drug_id = f"DRUG-{idx:03d}"
        key_to_drug_id[key] = drug_id
        bucket = drug_buckets[key]
        # Synthetic unit price: multiple of 500 VND between 1,500 and 25,000.
        synthetic_price = int(rng.integers(3, 51) * 500)

        drug_catalog.append(
            {
                "drug_id": drug_id,
                "active_ingredient": bucket["active_ingredient"],
                "strength_dosage": bucket["strength_dosage"],
                "route_of_administration": bucket["route_of_administration"],
                "unit": most_common_non_null(bucket["units"]),
                "sample_brand_names": sorted(bucket["brand_names"]),
                "typical_frequency": most_common_non_null(bucket["frequencies"]),
                "typical_meal_timing": most_common_non_null(bucket["meal_timings"]),
                "observed_icd10_cooccurrence": sorted(bucket["icd10s"]),
                "observed_icd10_note": (
                    "CHỈ ĐỂ THAM KHẢO NỘI BỘ — KHÔNG PHẢI CHỈ ĐỊNH CHÍNH THỨC"
                ),
                "verified_indications_icd10": [],
                "contraindications": [],
                "interactions": [],
                "max_daily_dose": None,
                "unit_price_vnd_synthetic": synthetic_price,
                "price_is_synthetic": True,
                "verification_status": "NEEDS_MEDICAL_REVIEW",
                "source_reference": "",
            }
        )

    # 5. Build case_base_synthetic.json.
    case_base: list[dict[str, Any]] = []
    total_med_rows_after_scope = 0
    for case in selected_cases:
        medications: list[dict[str, Any]] = []
        for idx, (_, row) in enumerate(case["rows"].iterrows(), start=1):
            ingredient = row["active_ingredient_clean"]
            strength = clean_whitespace(row.get("strength_dosage"))
            route = clean_whitespace(row.get("route_of_administration"))
            drug_id = key_to_drug_id[normalize_drug_key(ingredient, strength, route)]

            med_index = to_clean_number(row.get("med_index"))
            medications.append(
                {
                    "med_index": int(med_index) if med_index is not None else idx,
                    "drug_id": drug_id,
                    "active_ingredient": ingredient,
                    "strength_dosage": strength,
                    "route": route,
                    "quantity": to_clean_number(row.get("quantity")),
                    "unit": clean_whitespace(row.get("unit")),
                    "duration_days": (
                        int(row["parsed_duration_days"])
                        if pd.notna(row["parsed_duration_days"])
                        else None
                    ),
                    "frequency_per_day": to_clean_number(row.get("frequency_per_day")),
                    "dosage_schedule": build_dosage_schedule(row),
                    "meal_timing": clean_whitespace(row.get("meal_timing")),
                    "usage_instruction_full": clean_whitespace(
                        row.get("usage_instruction_full")
                    ),
                }
            )

        total_med_rows_after_scope += len(medications)
        case_base.append(
            {
                "case_id": case["case_id"],
                "is_synthetic": True,
                "seed": seed,
                "patient_profile": case["patient_profile"],
                "icd10_codes": case["icd10_codes"],
                "diagnoses": case["diagnoses"],
                "total_meds": len(medications),
                "medications": medications,
            }
        )

    # 6. Write outputs to data/processed/.
    output_dir.mkdir(parents=True, exist_ok=True)
    drug_catalog_path = output_dir / "drug_catalog.json"
    case_base_path = output_dir / "case_base_synthetic.json"
    guidelines_path = output_dir / "guidelines_template.json"
    report_path = output_dir / "DATA_CLEANING_REPORT.md"

    drug_catalog_path.write_text(
        json.dumps(drug_catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    case_base_path.write_text(
        json.dumps(case_base, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    guidelines_path.write_text(
        json.dumps(build_guidelines_template(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 7. Run PII audit on all JSON outputs before finalizing report.
    audit_counts = run_pii_audit([drug_catalog_path, case_base_path, guidelines_path])

    # 8. Compute report statistics and write DATA_CLEANING_REPORT.md.
    total_selected = len(case_base)
    age_missing = sum(1 for c in case_base if c["patient_profile"]["age"] is None)
    weight_missing = sum(
        1 for c in case_base if c["patient_profile"]["weight_kg"] is None
    )
    allergy_unknown = sum(
        1 for c in case_base if c["patient_profile"]["allergies"] == "unknown"
    )

    def pct(part: int, whole: int) -> str:
        return f"{(part / whole * 100):.1f}%" if whole else "0.0%"

    group_counts = Counter()
    for c in selected_cases:
        for g in c["core_groups"]:
            group_counts[g] += 1

    report_lines = [
        "# DATA CLEANING & ANONYMIZATION REPORT",
        "",
        f"- **Nguồn dữ liệu thô:** `{input_path.name}`",
        f"- **Phạm vi lọc (`--scope`):** `{scope}`",
        f"- **Seed tổng hợp hóa:** `{seed}`",
        "",
        "## 1. Thống kê trước và sau xử lý",
        "",
        "| Chỉ số | Trước lọc (Thô) | Sau làm sạch rác | Sau lọc phạm vi |",
        "|---|---:|---:|---:|",
        f"| Số dòng thuốc | {raw_rows} | {total_rows_before_scope} | {total_med_rows_after_scope} |",
        f"| Số đơn thuốc (`case_id`) | {raw_prescriptions} | {total_cases_before_scope} | {total_selected} |",
        f"| Số thuốc chuẩn hóa (`drug_catalog`) | — | — | {len(drug_catalog)} |",
        "",
        "## 2. Phân bố 4 nhóm bệnh mạn tính trọng tâm",
        "",
        "| Nhóm ICD-10 | Tên bệnh | Số đơn xuất hiện | Tỷ lệ trên tập xuất |",
        "|---|---|---:|---:|",
    ]
    for prefix, meta in CORE_DISEASE_GROUPS.items():
        cnt = group_counts.get(prefix, 0)
        report_lines.append(
            f"| `{prefix}` | {meta['name_vi']} | {cnt} | {pct(cnt, total_selected)} |"
        )

    report_lines.extend(
        [
            "",
            "## 3. Tỷ lệ thiếu thông tin lâm sàng trọng yếu (trên tập sau lọc)",
            "",
            "| Trường thông tin | Số ca thiếu / `unknown` | Tỷ lệ |",
            "|---|---:|---:|",
            f"| `patient_profile.age` (`null`) | {age_missing}/{total_selected} | {pct(age_missing, total_selected)} |",
            f"| `patient_profile.weight_kg` (`null`) | {weight_missing}/{total_selected} | {pct(weight_missing, total_selected)} |",
            f"| `patient_profile.allergies` (`\"unknown\"`) | {allergy_unknown}/{total_selected} | {pct(allergy_unknown, total_selected)} |",
            "",
            "## 4. Danh sách 33 cột đã xóa bỏ",
            "",
            f"- **Nhóm A — PII / Hành chính / Cơ sở y tế ({len(PII_ADMIN_COLUMNS)} cột):** "
            + ", ".join(f"`{c}`" for c in PII_ADMIN_COLUMNS),
            f"- **Nhóm B — Thiếu >75% hoặc ngoài phạm vi ({len(SPARSE_OOS_COLUMNS)} cột):** "
            + ", ".join(f"`{c}`" for c in SPARSE_OOS_COLUMNS),
            "- *Ghi chú:* Đã xóa thêm `med_raw_text` sau khi xử lý; `duration_days` được trích xuất tự động từ `usage_instruction_full` khi có mẫu `X ngày`.",
            "",
            "## 5. Kết quả kiểm tra bảo mật (PII Audit Assert)",
            "",
            f"- Trạng thái: **PASS** (0 rò rỉ trên `{drug_catalog_path.name}`, `{case_base_path.name}`, `{guidelines_path.name}`)",
            f"- Chi tiết kiểm tra: "
            + ", ".join(f"`{k}={v}`" for k, v in audit_counts.items()),
            "",
        ]
    )
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    print(
        f"[OK] scope={scope} | cases={total_selected}/{total_cases_before_scope} "
        f"| meds={total_med_rows_after_scope} | drugs={len(drug_catalog)} "
        f"| PII_audit=PASS -> {output_dir}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean and anonymize 100_Toa_NVM_2026_Dataset.csv into synthetic outputs."
    )
    parser.add_argument(
        "--input",
        default="data/100_Toa_NVM_2026_Dataset.csv",
        help="Path to raw CSV dataset (falls back to data/<input> if needed).",
    )
    parser.add_argument(
        "--output-dir",
        default="data/processed",
        help="Directory to write processed JSON and report files.",
    )
    parser.add_argument(
        "--scope",
        choices=["core", "all"],
        default="core",
        help="Filter prescriptions to core chronic diseases (I10, E78, E11, K21) or keep all.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for synthetic perturbation and pricing (default: 42).",
    )
    args = parser.parse_args()

    input_path = resolve_input_path(args.input)
    build_clean_dataset(
        input_path=input_path,
        output_dir=Path(args.output_dir),
        scope=args.scope,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
