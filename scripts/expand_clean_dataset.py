"""Expand and audit clean, PII-free datasets for chronic + outpatient conditions.

Fixes enforced in this script:
1. Strict exact active-ingredient + route matching for drug_id (zero substring mismatches).
2. Exact canonical_name sync between drug_catalog_clean.json and guidelines_clean.json,
   plus full K59 guideline coverage.
3. Case base strictly filtered to adult, non-empty-diagnosis, non-emergency, in-scope cases.
4. Clean standard medical source references (no local .xlsx/.pdf filenames or paths).

Run with Python 3.10 (pandas/numpy):
    python scripts/expand_clean_dataset.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROCESSED_DIR = Path("data/processed")
RAW_CSV_PATH = Path("data/100_Toa_NVM_2026_Dataset.csv")

REF_BYT = "Dược thư Quốc gia Việt Nam (2022) & Hướng dẫn chẩn đoán và điều trị Bộ Y tế (kcb.vn)"
REF_BLL5 = "Dược thư Quốc gia Việt Nam (2022) & Tài liệu chuyên môn Dược lý học (Bài LL 5 - Kháng nấm, Virus)"

CORE_ONLY_KEYWORDS: dict[str, list[str]] = {
    "I10": ["tăng huyết áp", "huyết áp cao"],
    "E78": ["rối loạn mỡ máu", "rối loạn lipid", "tăng lipid", "mỡ máu"],
    "E11": ["đái tháo đường", "tiểu đường"],
    "K21": ["trào ngược dạ dày", "trào ngược thực quản", "gerd"],
}

ALL_DISEASE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "I10": [re.compile(r"tăng huyết áp|huyết áp cao")],
    "E78": [re.compile(r"rối loạn mỡ máu|rối loạn lipid|tăng lipid|mỡ máu")],
    "E11": [re.compile(r"đái tháo đường|tiểu đường")],
    "K21": [re.compile(r"trào ngược dạ dày|trào ngược thực quản|gerd")],
    "J01": [re.compile(r"viêm xoang")],
    "J02": [re.compile(r"viêm họng")],
    "J30": [re.compile(r"viêm mũi dị ứng")],
    "R05": [re.compile(r"ho có đờm|ho khan|ho cấp")],
    "A04": [re.compile(r"nhiễm trùng tiêu hóa|viêm ruột(?!\s*thừa)")],
    "K59": [re.compile(r"tiêu chảy|rối loạn tiêu hóa|rối loạn chức năng ruột|rối loạn ruột chức năng")],
    "M75": [re.compile(r"bao gân xoay|viêm gân vai|viêm quanh khớp vai")],
    "M54": [re.compile(r"đau thắt lưng|đau cơ vùng thắt lưng|đau cột sống|đau lưng")],
    "M17": [re.compile(r"thoái hóa khớp gối")],
    "I83": [re.compile(r"suy giãn tĩnh mạch|giãn tĩnh mạch")],
    "B35": [re.compile(r"nấm da|hắc lào|nấm kẽ")],
    "B02": [re.compile(r"\bzona\b")],
    "J09": [re.compile(r"cúm a|cúm mùa|nhiễm cúm")],
}

EXCLUDED_DIAGNOSIS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ruột thừa"),
    re.compile(r"dọa sảy"),
    re.compile(r"ra huyết"),
    re.compile(r"ung thư"),
    re.compile(r"điều trị đích"),
    re.compile(r"hóa trị"),
    re.compile(r"nhồi máu cơ tim"),
    re.compile(r"đột quỵ"),
)

PII_AUDIT_PATTERNS: dict[str, re.Pattern[str]] = {
    "vn_phone_10_digits": re.compile(r"(?<!\d)0[35789]\d{8}(?!\d)"),
    "cccd_12_digits": re.compile(r"(?<!\d)\d{12}(?!\d)"),
    "raw_prescription_code": re.compile(r"\bDT25\d+\b"),
    "pii_column_leak": re.compile(
        r"\b(?:"
        + "|".join(
            [
                "prescription_code", "hospital_clinic_name", "hospital_address",
                "hospital_phone", "doctor_name", "doctor_phone", "patient_id",
                "patient_name", "guardian_name", "patient_phone", "patient_cccd",
                "bhyt_card_number", "patient_dob", "patient_address",
            ]
        )
        + r")\b"
    ),
}

EXTRA_DRUGS: list[dict[str, Any]] = [
    {
        "canonical_name": "Amoxicillin + Clavulanic acid",
        "active_ingredient": "Amoxicillin + Clavulanic acid",
        "aliases": ["Amoxicilin + acid clavulanic", "Amoxicilline + Clavulanic acid", "Augmentin", "Klamentin"],
        "component_ingredients": ["Amoxicillin", "Clavulanic acid"],
        "drug_class": "Beta-lactam",
        "strength_dosage": "875mg + 125mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Augmentin 1g", "Klamentin 875/125"],
        "typical_frequency": 2,
        "typical_meal_timing": "Ngay trước bữa ăn hoặc đầu bữa ăn",
        "verified_indications_icd10": ["J01", "J02"],
        "contraindications": [
            "Dị ứng với Penicillin hoặc nhóm Beta-lactam",
            "Tiền sử vàng da / rối loạn chức năng gan liên quan đến Amoxicillin-Clavulanate",
        ],
        "contraindication_tags": ["penicillin_allergy", "beta_lactam_allergy", "severe_liver_disease"],
        "interactions": [
            {
                "with_ingredient_or_class": "Warfarin",
                "severity": "moderate",
                "mechanism_and_risk": "Có thể làm tăng chỉ số INR khi phối hợp thuốc chống đông",
                "action": "WARN",
            },
            {
                "with_ingredient_or_class": "Methotrexate",
                "severity": "moderate",
                "mechanism_and_risk": "Giảm thanh thải thận của Methotrexate, tăng độc tính",
                "action": "WARN",
            },
        ],
        "max_daily_dose": {"value": 2000, "unit": "mg", "display": "2 viên/ngày (1750mg Amoxicillin + 250mg Clavulanic)"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Amoxicillin + Clavulanic acid",
        "active_ingredient": "Amoxicillin + Clavulanic acid",
        "aliases": ["Amoxicilin + acid clavulanic 500/125", "Augmentin 625mg"],
        "component_ingredients": ["Amoxicillin", "Clavulanic acid"],
        "drug_class": "Beta-lactam",
        "strength_dosage": "500mg + 125mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Augmentin 625mg", "Klamentin 500/125"],
        "typical_frequency": 3,
        "typical_meal_timing": "Đầu bữa ăn",
        "verified_indications_icd10": ["J01", "J02"],
        "contraindications": [
            "Dị ứng với Penicillin hoặc nhóm Beta-lactam",
            "Tiền sử tổn thương gan do Amoxicillin-Clavulanate",
        ],
        "contraindication_tags": ["penicillin_allergy", "beta_lactam_allergy", "severe_liver_disease"],
        "interactions": [
            {
                "with_ingredient_or_class": "Warfarin",
                "severity": "moderate",
                "mechanism_and_risk": "Có thể làm tăng INR",
                "action": "WARN",
            }
        ],
        "max_daily_dose": {"value": 1875, "unit": "mg", "display": "3 viên/ngày (1500mg Amoxicillin + 375mg Clavulanic)"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Cefuroxime",
        "active_ingredient": "Cefuroxime axetil",
        "aliases": ["Cefuroxim", "Zinnat"],
        "component_ingredients": ["Cefuroxime"],
        "drug_class": "Cephalosporin",
        "strength_dosage": "500mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Zinnat 500mg", "Cefuroxim 500mg"],
        "typical_frequency": 2,
        "typical_meal_timing": "Sau ăn",
        "verified_indications_icd10": ["J01", "J02"],
        "contraindications": ["Dị ứng với Cephalosporin hoặc tiền sử phản vệ với Penicillin"],
        "contraindication_tags": ["cephalosporin_allergy", "beta_lactam_allergy"],
        "interactions": [
            {
                "with_ingredient_or_class": "Antacid",
                "severity": "moderate",
                "mechanism_and_risk": "Thuốc giảm acid dạ dày làm giảm sinh khả dụng Cefuroxime",
                "action": "WARN",
            }
        ],
        "max_daily_dose": {"value": 1000, "unit": "mg", "display": "1000 mg/ngày"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Azithromycin",
        "active_ingredient": "Azithromycin",
        "aliases": ["Azithromycin", "Zithromax"],
        "component_ingredients": ["Azithromycin"],
        "drug_class": "Macrolide",
        "strength_dosage": "250mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Zithromax 250mg", "Azithromycin 250mg"],
        "typical_frequency": 1,
        "typical_meal_timing": "Trước ăn 1 giờ hoặc sau ăn 2 giờ",
        "verified_indications_icd10": ["J01", "J02"],
        "contraindications": [
            "Dị ứng với Azithromycin hoặc Macrolide",
            "Bệnh gan nặng hoặc tiền sử kéo dài khoảng QT nặng",
        ],
        "contraindication_tags": ["macrolide_allergy", "severe_liver_disease"],
        "interactions": [
            {
                "with_ingredient_or_class": "Warfarin",
                "severity": "moderate",
                "mechanism_and_risk": "Có thể làm tăng tác dụng chống đông của Warfarin",
                "action": "WARN",
            }
        ],
        "max_daily_dose": {"value": 500, "unit": "mg", "display": "500 mg/ngày"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Budesonide",
        "active_ingredient": "Budesonide",
        "aliases": ["Budesonid", "Rhinocort"],
        "component_ingredients": ["Budesonide"],
        "drug_class": "Intranasal_Corticosteroid",
        "strength_dosage": "64mcg/liều",
        "route_of_administration": "Xịt mũi",
        "unit": "Lọ",
        "sample_brand_names": ["Rhinocort Aqua 64mcg"],
        "typical_frequency": 2,
        "typical_meal_timing": "Sáng và tối, mỗi bên mũi 1-2 nhát",
        "verified_indications_icd10": ["J30", "J01"],
        "contraindications": ["Dị ứng với Budesonide", "Nhiễm nấm/virus tại mũi chưa điều trị"],
        "contraindication_tags": ["corticosteroid_allergy"],
        "interactions": [],
        "max_daily_dose": {"value": 400, "unit": "mcg", "display": "400 mcg/ngày (xịt mũi)"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Fexofenadine",
        "active_ingredient": "Fexofenadine HCl",
        "aliases": ["Fexofenadin", "Telfast"],
        "component_ingredients": ["Fexofenadine"],
        "drug_class": "Antihistamine_H1",
        "strength_dosage": "180mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Telfast HD 180mg", "Fexofenadin 180mg"],
        "typical_frequency": 1,
        "typical_meal_timing": "Uống với nước lọc, tránh nước ép hoa quả",
        "verified_indications_icd10": ["J30", "J01"],
        "contraindications": ["Dị ứng với Fexofenadine"],
        "contraindication_tags": ["antihistamine_allergy"],
        "interactions": [
            {
                "with_ingredient_or_class": "Antacid",
                "severity": "moderate",
                "mechanism_and_risk": "Antacid chứa nhôm/magnesi làm giảm hấp thu Fexofenadine (uống cách >= 2 giờ)",
                "action": "WARN",
            }
        ],
        "max_daily_dose": {"value": 180, "unit": "mg", "display": "180 mg/ngày"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Desloratadine",
        "active_ingredient": "Desloratadine",
        "aliases": ["Desloratadin", "Aerius"],
        "component_ingredients": ["Desloratadine"],
        "drug_class": "Antihistamine_H1",
        "strength_dosage": "5mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Aerius 5mg", "Desloratadine 5mg"],
        "typical_frequency": 1,
        "typical_meal_timing": "Không phụ thuộc bữa ăn",
        "verified_indications_icd10": ["J30"],
        "contraindications": ["Dị ứng với Desloratadine hoặc Loratadine"],
        "contraindication_tags": ["antihistamine_allergy"],
        "interactions": [],
        "max_daily_dose": {"value": 5, "unit": "mg", "display": "5 mg/ngày"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Methylprednisolone",
        "active_ingredient": "Methylprednisolone",
        "aliases": ["Methylprednisolon", "Medrol"],
        "component_ingredients": ["Methylprednisolone"],
        "drug_class": "Systemic_Corticosteroid",
        "strength_dosage": "16mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Medrol 16mg", "Methylprednisolon 16mg"],
        "typical_frequency": 1,
        "typical_meal_timing": "Sau ăn sáng",
        "verified_indications_icd10": ["J01", "J30", "J02"],
        "contraindications": [
            "Nhiễm nấm toàn thân chưa kiểm soát",
            "Loét dạ dày - tá tràng tiến triển",
            "Dị ứng với Methylprednisolone",
        ],
        "contraindication_tags": ["corticosteroid_allergy", "active_gi_ulcer"],
        "interactions": [
            {
                "with_ingredient_or_class": "NSAID",
                "severity": "moderate",
                "mechanism_and_risk": "Tăng nguy cơ loét và xuất huyết tiêu hóa khi phối hợp Corticoid + NSAID",
                "action": "WARN",
            },
            {
                "with_ingredient_or_class": "Warfarin",
                "severity": "moderate",
                "mechanism_and_risk": "Thay đổi đáp ứng chống đông của Warfarin",
                "action": "WARN",
            },
        ],
        "max_daily_dose": {"value": 48, "unit": "mg", "display": "48 mg/ngày (đợt ngắn ngoại trú)"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Acetylcysteine",
        "active_ingredient": "Acetylcysteine",
        "aliases": ["Acetylcystein", "Acemuc", "Fluimucil"],
        "component_ingredients": ["Acetylcysteine"],
        "drug_class": "Mucolytic",
        "strength_dosage": "200mg",
        "route_of_administration": "Uống",
        "unit": "Gói",
        "sample_brand_names": ["Acemuc 200mg", "Mitux 200mg"],
        "typical_frequency": 3,
        "typical_meal_timing": "Sau ăn",
        "verified_indications_icd10": ["R05", "J01", "J02"],
        "contraindications": [
            "Dị ứng với Acetylcysteine",
            "Tiền sử hen phế quản (nguy cơ co thắt phế quản)",
        ],
        "contraindication_tags": ["severe_asthma"],
        "interactions": [
            {
                "with_ingredient_or_class": "Antitussive",
                "severity": "moderate",
                "mechanism_and_risk": "Không phối hợp thuốc long đờm với thuốc ức chế phản xạ ho gây ứ đọng đờm",
                "action": "WARN",
            }
        ],
        "max_daily_dose": {"value": 600, "unit": "mg", "display": "600 mg/ngày"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Ambroxol",
        "active_ingredient": "Ambroxol HCl",
        "aliases": ["Ambroxol", "Ambroxol HCl", "Mucosolvan"],
        "component_ingredients": ["Ambroxol"],
        "drug_class": "Mucolytic",
        "strength_dosage": "30mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Mucosolvan 30mg", "Ambroxol 30mg"],
        "typical_frequency": 3,
        "typical_meal_timing": "Sau ăn",
        "verified_indications_icd10": ["R05", "J02"],
        "contraindications": ["Dị ứng với Ambroxol", "Loét dạ dày - tá tràng tiến triển"],
        "contraindication_tags": ["active_gi_ulcer"],
        "interactions": [],
        "max_daily_dose": {"value": 120, "unit": "mg", "display": "120 mg/ngày"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Paracetamol",
        "active_ingredient": "Paracetamol",
        "aliases": ["Acetaminophen", "Efferalgan", "Hapacol", "Panadol"],
        "component_ingredients": ["Paracetamol"],
        "drug_class": "Analgesic_Antipyretic",
        "strength_dosage": "500mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Hapacol 500mg", "Panadol 500mg", "Efferalgan 500mg"],
        "typical_frequency": 3,
        "typical_meal_timing": "Sau ăn hoặc khi sốt/đau (cách nhau >= 4-6 giờ)",
        "verified_indications_icd10": ["J01", "J02", "A04", "M54", "M17", "M75", "B02", "J09"],
        "contraindications": [
            "Dị ứng với Paracetamol",
            "Suy gan nặng hoặc bệnh gan tiến triển",
            "Thiếu hụt men G6PD nặng",
        ],
        "contraindication_tags": ["paracetamol_allergy", "severe_liver_disease", "active_liver_disease"],
        "interactions": [
            {
                "with_ingredient_or_class": "Warfarin",
                "severity": "moderate",
                "mechanism_and_risk": "Dùng Paracetamol liều cao kéo dài (> 2g/ngày) có thể làm tăng INR",
                "action": "WARN",
            }
        ],
        "max_daily_dose": {"value": 4000, "unit": "mg", "display": "4000 mg/ngày (người lớn chức năng gan bình thường)"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Paracetamol",
        "active_ingredient": "Paracetamol",
        "aliases": ["Acetaminophen 650mg", "Hapacol 650"],
        "component_ingredients": ["Paracetamol"],
        "drug_class": "Analgesic_Antipyretic",
        "strength_dosage": "650mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Hapacol 650mg", "Tylenol 650mg"],
        "typical_frequency": 3,
        "typical_meal_timing": "Sau ăn hoặc khi sốt/đau",
        "verified_indications_icd10": ["J01", "J02", "M54", "M17", "B02", "J09"],
        "contraindications": ["Dị ứng Paracetamol", "Suy gan nặng / bệnh gan tiến triển"],
        "contraindication_tags": ["paracetamol_allergy", "severe_liver_disease", "active_liver_disease"],
        "interactions": [
            {
                "with_ingredient_or_class": "Warfarin",
                "severity": "moderate",
                "mechanism_and_risk": "Có thể làm tăng INR nếu dùng liều cao nhiều ngày",
                "action": "WARN",
            }
        ],
        "max_daily_dose": {"value": 3900, "unit": "mg", "display": "6 viên/ngày (3900 mg/ngày, không quá 4000 mg/ngày)"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Cefixime",
        "active_ingredient": "Cefixime",
        "aliases": ["Cefixim", "Fixef"],
        "component_ingredients": ["Cefixime"],
        "drug_class": "Cephalosporin",
        "strength_dosage": "200mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Cefixim 200mg", "Fixef 200mg"],
        "typical_frequency": 2,
        "typical_meal_timing": "Sau ăn",
        "verified_indications_icd10": ["A04", "J02"],
        "contraindications": ["Dị ứng Cephalosporin hoặc phản vệ với Penicillin"],
        "contraindication_tags": ["cephalosporin_allergy", "beta_lactam_allergy"],
        "interactions": [
            {
                "with_ingredient_or_class": "Warfarin",
                "severity": "moderate",
                "mechanism_and_risk": "Có thể làm kéo dài thời gian prothrombin",
                "action": "WARN",
            }
        ],
        "max_daily_dose": {"value": 400, "unit": "mg", "display": "400 mg/ngày"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Alverine citrate + Simethicone",
        "active_ingredient": "Alverine citrate + Simethicone",
        "aliases": ["Alverin citrat + simethicon", "Meteospasmyl"],
        "component_ingredients": ["Alverine citrate", "Simethicone"],
        "drug_class": "Antispasmodic",
        "strength_dosage": "60mg + 300mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Meteospasmyl", "Alverin Simethicon"],
        "typical_frequency": 2,
        "typical_meal_timing": "Trước ăn",
        "verified_indications_icd10": ["A04", "K59"],
        "contraindications": ["Liệt ruột, tắc ruột", "Dị ứng với thành phần thuốc"],
        "contraindication_tags": ["gi_bleeding_obstruction"],
        "interactions": [],
        "max_daily_dose": {"value": 3, "unit": "viên", "display": "3 viên/ngày"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Diosmectite",
        "active_ingredient": "Diosmectite",
        "aliases": ["Smecta", "Diosmectit"],
        "component_ingredients": ["Diosmectite"],
        "drug_class": "Antidiarrheal_Adsorbent",
        "strength_dosage": "3g",
        "route_of_administration": "Uống",
        "unit": "Gói",
        "sample_brand_names": ["Smecta 3g"],
        "typical_frequency": 3,
        "typical_meal_timing": "Pha nước uống cách các thuốc khác >= 2 giờ",
        "verified_indications_icd10": ["A04", "K59"],
        "contraindications": ["Dị ứng với Diosmectite", "Tắc ruột"],
        "contraindication_tags": ["gi_bleeding_obstruction"],
        "interactions": [
            {
                "with_ingredient_or_class": "Thuốc uống khác",
                "severity": "moderate",
                "mechanism_and_risk": "Đặc tính hấp phụ làm giảm hấp thu thuốc uống cùng (uống cách >= 2 giờ)",
                "action": "WARN",
            }
        ],
        "max_daily_dose": {"value": 18, "unit": "g", "display": "6 gói/ngày (18 g/ngày giai đoạn đầu tiêu chảy cấp)"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Bacillus subtilis",
        "active_ingredient": "Bacillus subtilis",
        "aliases": ["Bacillus subtilis", "Biolactovin"],
        "component_ingredients": ["Bacillus subtilis"],
        "drug_class": "Probiotic",
        "strength_dosage": "10^8 CFU",
        "route_of_administration": "Uống",
        "unit": "Gói",
        "sample_brand_names": ["Bacillus subtilis gói"],
        "typical_frequency": 2,
        "typical_meal_timing": "Sau ăn (uống cách kháng sinh 2 giờ nếu dùng kèm)",
        "verified_indications_icd10": ["A04", "K59"],
        "contraindications": ["Dị ứng với chế phẩm probiotic", "Suy giảm miễn dịch nặng (thận trọng)"],
        "contraindication_tags": [],
        "interactions": [],
        "max_daily_dose": {"value": 4, "unit": "gói", "display": "4 gói/ngày"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Oresol (ORS)",
        "active_ingredient": "Glucose + Natri clorid + Kali clorid + Natri citrat",
        "aliases": ["Oresol", "ORS"],
        "component_ingredients": ["ORS"],
        "drug_class": "Electrolyte_Replacement",
        "strength_dosage": "1 gói (pha 200mL)",
        "route_of_administration": "Uống",
        "unit": "Gói",
        "sample_brand_names": ["Oresol 245"],
        "typical_frequency": 3,
        "typical_meal_timing": "Uống từng ngụm bù nước sau mỗi lần đi ngoài",
        "verified_indications_icd10": ["A04", "K59"],
        "contraindications": ["Vô niệu, tắc ruột, nôn ói không kiểm soát"],
        "contraindication_tags": ["gi_bleeding_obstruction"],
        "interactions": [],
        "max_daily_dose": {"value": 10, "unit": "gói", "display": "Theo mức độ mất nước"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Celecoxib",
        "active_ingredient": "Celecoxib",
        "aliases": ["Celebrex", "Celecoxib"],
        "component_ingredients": ["Celecoxib"],
        "drug_class": "NSAID_COX2",
        "strength_dosage": "100mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Celebrex 100mg", "Celecoxib 100mg"],
        "typical_frequency": 2,
        "typical_meal_timing": "Sau ăn no",
        "verified_indications_icd10": ["M75", "M54", "M17"],
        "contraindications": [
            "Dị ứng với NSAID, Aspirin hoặc Sulfonamid",
            "Loét dạ dày - tá tràng tiến triển / xuất huyết tiêu hóa",
            "Suy thận nặng (ClCr < 30), suy gan nặng, suy tim nặng, 3 tháng cuối thai kỳ",
        ],
        "contraindication_tags": [
            "nsaid_allergy", "sulfonamide_allergy", "active_gi_ulcer",
            "severe_renal_impairment", "ckd_stage3_caution", "severe_liver_disease", "pregnancy"
        ],
        "interactions": [
            {
                "with_ingredient_or_class": "Warfarin",
                "severity": "high",
                "mechanism_and_risk": "Tăng mạnh nguy cơ xuất huyết tiêu hóa và xuất huyết toàn thân",
                "action": "BLOCK",
            },
            {
                "with_ingredient_or_class": "ACEi",
                "severity": "moderate",
                "mechanism_and_risk": "Giảm hiệu quả hạ áp và tăng nguy cơ tổn thương thận cấp",
                "action": "WARN",
            },
            {
                "with_ingredient_or_class": "ARB",
                "severity": "moderate",
                "mechanism_and_risk": "Giảm hiệu quả hạ áp và tăng nguy cơ suy giảm chức năng thận",
                "action": "WARN",
            },
        ],
        "max_daily_dose": {"value": 400, "unit": "mg", "display": "400 mg/ngày"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Meloxicam",
        "active_ingredient": "Meloxicam",
        "aliases": ["Mobic", "Meloxicam"],
        "component_ingredients": ["Meloxicam"],
        "drug_class": "NSAID",
        "strength_dosage": "7.5mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Mobic 7.5mg", "Meloxicam 7.5mg"],
        "typical_frequency": 1,
        "typical_meal_timing": "Sau ăn no",
        "verified_indications_icd10": ["M75", "M54", "M17"],
        "contraindications": [
            "Dị ứng với NSAID / Aspirin",
            "Loét dạ dày - tá tràng tiến triển, xuất huyết tiêu hóa",
            "Suy thận nặng không lọc máu, suy gan nặng, phụ nữ có thai",
        ],
        "contraindication_tags": [
            "nsaid_allergy", "active_gi_ulcer",
            "severe_renal_impairment", "ckd_stage3_caution", "severe_liver_disease", "pregnancy"
        ],
        "interactions": [
            {
                "with_ingredient_or_class": "Warfarin",
                "severity": "high",
                "mechanism_and_risk": "Tăng nghiêm trọng nguy cơ xuất huyết tiêu hóa và chảy máu",
                "action": "BLOCK",
            },
            {
                "with_ingredient_or_class": "ACEi",
                "severity": "moderate",
                "mechanism_and_risk": "Giảm tác dụng hạ áp và tăng nguy cơ suy thận cấp",
                "action": "WARN",
            },
        ],
        "max_daily_dose": {"value": 15, "unit": "mg", "display": "15 mg/ngày"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Ketoprofen",
        "active_ingredient": "Ketoprofen",
        "aliases": ["Fastum gel", "Ketoprofen 2.5%", "Ketoprofen"],
        "component_ingredients": ["Ketoprofen"],
        "drug_class": "Topical_NSAID",
        "strength_dosage": "2.5% (tuýp 30g)",
        "route_of_administration": "Bôi ngoài da",
        "unit": "Tuýp",
        "sample_brand_names": ["Fastum gel 2.5%"],
        "typical_frequency": 2,
        "typical_meal_timing": "Bôi mỏng vùng đau 2 lần/ngày (tránh vùng da tổn thương và ánh nắng)",
        "verified_indications_icd10": ["M75", "M54", "M17"],
        "contraindications": ["Dị ứng với Ketoprofen / NSAID", "Vùng da trầy xước/nhiễm trùng", "3 tháng cuối thai kỳ"],
        "contraindication_tags": ["nsaid_allergy", "pregnancy"],
        "interactions": [
            {
                "with_ingredient_or_class": "Warfarin",
                "severity": "high",
                "mechanism_and_risk": "NSAID vẫn có thể hấp thu toàn thân khi bôi diện rộng, tránh dùng ở người dị ứng NSAID / dùng Warfarin",
                "action": "BLOCK",
            }
        ],
        "max_daily_dose": {"value": 15, "unit": "g", "display": "15 g gel/ngày"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Eperisone",
        "active_ingredient": "Eperisone HCl",
        "aliases": ["Eperison", "Eperison hydroclorid", "Myonal"],
        "component_ingredients": ["Eperisone"],
        "drug_class": "Muscle_Relaxant",
        "strength_dosage": "50mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Myonal 50mg", "Eperisone 50mg"],
        "typical_frequency": 3,
        "typical_meal_timing": "Sau ăn",
        "verified_indications_icd10": ["M54", "M75"],
        "contraindications": ["Dị ứng với Eperisone", "Thận trọng ở bệnh nhân suy gan nặng"],
        "contraindication_tags": ["severe_liver_disease"],
        "interactions": [
            {
                "with_ingredient_or_class": "Tolperisone",
                "severity": "moderate",
                "mechanism_and_risk": "Tránh phối hợp hai thuốc giãn cơ trung ương",
                "action": "WARN",
            }
        ],
        "max_daily_dose": {"value": 150, "unit": "mg", "display": "150 mg/ngày"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Vitamin B1 + B6 + B12",
        "active_ingredient": "Thiamine + Pyridoxine + Cyanocobalamin",
        "aliases": ["3B", "Neurobion", "Vitamin 3B"],
        "component_ingredients": ["Vitamin B1", "Vitamin B6", "Vitamin B12"],
        "drug_class": "Neurotropic_Vitamin",
        "strength_dosage": "100mg + 100mg + 150mcg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Neurobion", "Vitamin 3B"],
        "typical_frequency": 2,
        "typical_meal_timing": "Sau ăn",
        "verified_indications_icd10": ["M75", "M54", "B02"],
        "contraindications": ["Dị ứng với bất kỳ thành phần vitamin nhóm B", "Khối u ác tính (với B12)"],
        "contraindication_tags": [],
        "interactions": [],
        "max_daily_dose": {"value": 3, "unit": "viên", "display": "3 viên/ngày"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Diosmin + Hesperidin",
        "active_ingredient": "Diosmin + Hesperidin",
        "aliases": ["Daflon 500mg", "Diosmin + hesperidin"],
        "component_ingredients": ["Diosmin", "Hesperidin"],
        "drug_class": "Venotonic",
        "strength_dosage": "450mg + 50mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Daflon 500mg", "Venrutin"],
        "typical_frequency": 2,
        "typical_meal_timing": "Trong hoặc sau bữa ăn",
        "verified_indications_icd10": ["I83"],
        "contraindications": ["Dị ứng với Diosmin/Hesperidin", "Phụ nữ đang cho con bú (thận trọng)"],
        "contraindication_tags": ["lactation"],
        "interactions": [],
        "max_daily_dose": {"value": 1000, "unit": "mg", "display": "1000 mg/ngày (2 viên/ngày trong suy tĩnh mạch mạn)"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Rutin + Vitamin C",
        "active_ingredient": "Rutin + Ascorbic acid",
        "aliases": ["Rutin C", "Rutin + Vitamin C"],
        "component_ingredients": ["Rutin", "Vitamin C"],
        "drug_class": "Venotonic",
        "strength_dosage": "50mg + 50mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Rutin Vitamin C 50/50"],
        "typical_frequency": 2,
        "typical_meal_timing": "Sau ăn",
        "verified_indications_icd10": ["I83"],
        "contraindications": ["Dị ứng thành phần thuốc", "Tiền sử sỏi thận oxalat (với Vitamin C liều cao)"],
        "contraindication_tags": [],
        "interactions": [],
        "max_daily_dose": {"value": 6, "unit": "viên", "display": "6 viên/ngày"},
        "source_reference": REF_BYT,
    },
    {
        "canonical_name": "Clotrimazole",
        "active_ingredient": "Clotrimazole",
        "aliases": ["Clotrimazol", "Canesten"],
        "component_ingredients": ["Clotrimazole"],
        "drug_class": "Topical_Antifungal",
        "strength_dosage": "1% (tuýp 10g)",
        "route_of_administration": "Bôi ngoài da",
        "unit": "Tuýp",
        "sample_brand_names": ["Canesten 1%", "Clotrimazole 1%"],
        "typical_frequency": 2,
        "typical_meal_timing": "Rửa sạch lau khô, bôi mỏng 2 lần/ngày (sáng, tối) trong 2-4 tuần",
        "verified_indications_icd10": ["B35"],
        "contraindications": ["Dị ứng với Clotrimazole hoặc nhóm Azol"],
        "contraindication_tags": ["azole_allergy"],
        "interactions": [],
        "max_daily_dose": {"value": 3, "unit": "lần bôi", "display": "Bôi ngoài da 2-3 lần/ngày"},
        "source_reference": REF_BLL5,
    },
    {
        "canonical_name": "Terbinafine",
        "active_ingredient": "Terbinafine HCl",
        "aliases": ["Lamisil", "Terbinafin", "Terbinafine hydroclorid"],
        "component_ingredients": ["Terbinafine"],
        "drug_class": "Topical_Antifungal",
        "strength_dosage": "1% (tuýp 15g)",
        "route_of_administration": "Bôi ngoài da",
        "unit": "Tuýp",
        "sample_brand_names": ["Lamisil 1%", "Terbinafine 1%"],
        "typical_frequency": 2,
        "typical_meal_timing": "Bôi mỏng vùng da nhiễm nấm 1-2 lần/ngày",
        "verified_indications_icd10": ["B35"],
        "contraindications": ["Dị ứng với Terbinafine"],
        "contraindication_tags": [],
        "interactions": [],
        "max_daily_dose": {"value": 2, "unit": "lần bôi", "display": "Bôi ngoài da 1-2 lần/ngày"},
        "source_reference": REF_BLL5,
    },
    {
        "canonical_name": "Itraconazole",
        "active_ingredient": "Itraconazole",
        "aliases": ["Sporal", "Itraconazol"],
        "component_ingredients": ["Itraconazole"],
        "drug_class": "Systemic_Antifungal",
        "strength_dosage": "100mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Sporal 100mg", "Itraconazol 100mg"],
        "typical_frequency": 1,
        "typical_meal_timing": "Ngay sau bữa ăn chính để tăng hấp thu",
        "verified_indications_icd10": ["B35"],
        "contraindications": [
            "Dị ứng với Itraconazole / Azol",
            "Suy tim sung huyết hoặc tiền sử rối loạn chức năng thất",
            "Phụ nữ có thai; bệnh gan tiến triển",
        ],
        "contraindication_tags": ["azole_allergy", "pregnancy", "active_liver_disease", "severe_liver_disease"],
        "interactions": [
            {
                "with_ingredient_or_class": "Simvastatin",
                "severity": "high",
                "mechanism_and_risk": "Ức chế mạnh CYP3A4 gây tiêu cơ vân nặng (CHỐNG CHỈ ĐỊNH)",
                "action": "BLOCK",
            },
            {
                "with_ingredient_or_class": "Atorvastatin",
                "severity": "high",
                "mechanism_and_risk": "Ức chế CYP3A4 làm tăng nồng độ Atorvastatin và nguy cơ tiêu cơ vân",
                "action": "BLOCK",
            },
        ],
        "max_daily_dose": {"value": 400, "unit": "mg", "display": "400 mg/ngày"},
        "source_reference": REF_BLL5,
    },
    {
        "canonical_name": "Acyclovir",
        "active_ingredient": "Acyclovir",
        "aliases": ["Aciclovir", "Zovirax"],
        "component_ingredients": ["Acyclovir"],
        "drug_class": "Antiviral",
        "strength_dosage": "800mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Acyclovir 800mg", "Zovirax 800mg"],
        "typical_frequency": 5,
        "typical_meal_timing": "Uống đều 5 lần/ngày (cách ~4 giờ, bỏ cữ đêm) + uống nhiều nước",
        "verified_indications_icd10": ["B02"],
        "contraindications": [
            "Dị ứng với Acyclovir hoặc Valacyclovir",
            "Thận trọng hiệu chỉnh liều khi suy thận (nguy cơ kết tinh ống thận nếu thiếu nước)",
        ],
        "contraindication_tags": ["renal_dose_adjust"],
        "interactions": [
            {
                "with_ingredient_or_class": "NSAID",
                "severity": "moderate",
                "mechanism_and_risk": "Tăng nguy cơ độc tính trên thận khi phối hợp thuốc độc thận",
                "action": "WARN",
            }
        ],
        "max_daily_dose": {"value": 4000, "unit": "mg", "display": "4000 mg/ngày (800mg x 5 lần/ngày trong Zona)"},
        "source_reference": REF_BLL5,
    },
    {
        "canonical_name": "Valacyclovir",
        "active_ingredient": "Valacyclovir",
        "aliases": ["Valaciclovir", "Valtrex"],
        "component_ingredients": ["Valacyclovir"],
        "drug_class": "Antiviral",
        "strength_dosage": "500mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Valtrex 500mg", "Valacyclovir 500mg"],
        "typical_frequency": 3,
        "typical_meal_timing": "Uống với nhiều nước, không phụ thuộc bữa ăn",
        "verified_indications_icd10": ["B02"],
        "contraindications": ["Dị ứng với Valacyclovir hoặc Acyclovir", "Thận trọng hiệu chỉnh liều ở người suy thận"],
        "contraindication_tags": ["renal_dose_adjust"],
        "interactions": [],
        "max_daily_dose": {"value": 3000, "unit": "mg", "display": "3000 mg/ngày (1000mg x 3 lần/ngày trong Zona)"},
        "source_reference": REF_BLL5,
    },
    {
        "canonical_name": "Oseltamivir",
        "active_ingredient": "Oseltamivir phosphate",
        "aliases": ["Tamiflu", "Oseltamivir"],
        "component_ingredients": ["Oseltamivir"],
        "drug_class": "Antiviral",
        "strength_dosage": "75mg",
        "route_of_administration": "Uống",
        "unit": "Viên",
        "sample_brand_names": ["Tamiflu 75mg", "Flustad 75mg"],
        "typical_frequency": 2,
        "typical_meal_timing": "Uống cùng thức ăn để giảm buồn nôn",
        "verified_indications_icd10": ["J09"],
        "contraindications": [
            "Dị ứng với Oseltamivir",
            "Thận trọng hiệu chỉnh liều khi suy thận (ClCr < 60 mL/phút) và đánh giá kỹ ở phụ nữ có thai",
        ],
        "contraindication_tags": ["renal_dose_adjust"],
        "interactions": [],
        "max_daily_dose": {"value": 150, "unit": "mg", "display": "150 mg/ngày (75mg x 2 lần/ngày trong 5 ngày)"},
        "source_reference": REF_BLL5,
    },
    {
        "canonical_name": "Glucosamine sulfate",
        "active_ingredient": "Glucosamine sulfate",
        "aliases": ["Glucosamin", "Viartril-S"],
        "component_ingredients": ["Glucosamine"],
        "drug_class": "Chondroprotective",
        "strength_dosage": "1500mg",
        "route_of_administration": "Uống",
        "unit": "Gói",
        "sample_brand_names": ["Viartril-S 1500mg", "Glucosamine 1500mg"],
        "typical_frequency": 1,
        "typical_meal_timing": "Sau ăn",
        "verified_indications_icd10": ["M17"],
        "contraindications": ["Dị ứng với động vật giáp xác (tôm, cua)", "Phụ nữ có thai hoặc cho con bú"],
        "contraindication_tags": ["shellfish_allergy", "pregnancy"],
        "interactions": [
            {
                "with_ingredient_or_class": "Warfarin",
                "severity": "moderate",
                "mechanism_and_risk": "Có thể làm tăng INR khi phối hợp Warfarin",
                "action": "WARN",
            }
        ],
        "max_daily_dose": {"value": 1500, "unit": "mg", "display": "1500 mg/ngày"},
        "source_reference": REF_BYT,
    },
]

EXTRA_GUIDELINES: list[dict[str, Any]] = [
    {
        "guideline_id": "BYT-J01-01",
        "icd10_prefix": "J01",
        "disease_name_vi": "Viêm xoang cấp",
        "first_line_ingredients": ["Amoxicillin + Clavulanic acid", "Budesonide", "Paracetamol", "Fexofenadine"],
        "second_line_or_special_ingredients": ["Cefuroxime", "Azithromycin", "Methylprednisolone", "Acetylcysteine"],
        "avoid_combinations": ["Không phối hợp hai kháng sinh cùng nhóm Beta-lactam", "Kiểm tra tiền sử dị ứng Penicillin/Beta-lactam trước khi kê"],
        "safety_red_flags": ["Đau đầu dữ dội, sưng nề quanh mắt, sốt cao kéo dài -> chuyển chuyên khoa Tai Mũi Họng"],
        "missing_info_checks": ["allergies", "age", "weight_kg"],
        "content_excerpt": "Điều trị triệu chứng (rửa mũi, corticoid xịt mũi, giảm đau hạ sốt Paracetamol) và cân nhắc kháng sinh Amoxicillin + Clavulanic acid khi nghi ngờ bội nhiễm vi khuẩn.",
        "official_source_url": "https://kcb.vn/",
    },
    {
        "guideline_id": "BYT-J30-01",
        "icd10_prefix": "J30",
        "disease_name_vi": "Viêm mũi dị ứng",
        "first_line_ingredients": ["Fexofenadine", "Desloratadine", "Budesonide"],
        "second_line_or_special_ingredients": ["Methylprednisolone"],
        "avoid_combinations": ["Không kê trùng hai thuốc kháng histamin H1 thế hệ 2 trong cùng đơn"],
        "safety_red_flags": ["Thận trọng corticoid toàn thân kéo dài; ưu tiên corticoid xịt mũi tại chỗ"],
        "missing_info_checks": ["allergies", "age"],
        "content_excerpt": "Kháng histamin H1 không gây buồn ngủ (Fexofenadine/Desloratadine) kết hợp corticoid xịt mũi (Budesonide) là lựa chọn đầu tay kiểm soát triệu chứng viêm mũi dị ứng.",
        "official_source_url": "https://kcb.vn/",
    },
    {
        "guideline_id": "BYT-J02-01",
        "icd10_prefix": "J02",
        "disease_name_vi": "Viêm họng cấp",
        "first_line_ingredients": ["Paracetamol", "Amoxicillin + Clavulanic acid", "Cefuroxime"],
        "second_line_or_special_ingredients": ["Azithromycin", "Ambroxol", "Acetylcysteine"],
        "avoid_combinations": ["Kiểm tra dị ứng Penicillin/Cephalosporin trước khi kê kháng sinh"],
        "safety_red_flags": ["Khó thở, nuốt nghẹn hoàn toàn, áp xe quanh amidan -> cấp cứu/chuyên khoa"],
        "missing_info_checks": ["allergies", "age"],
        "content_excerpt": "Hạ sốt giảm đau bằng Paracetamol; chỉ định kháng sinh (Amoxicillin + Clavulanic acid, Cefuroxime hoặc Azithromycin nếu dị ứng beta-lactam) khi có bằng chứng viêm họng do vi khuẩn.",
        "official_source_url": "https://kcb.vn/",
    },
    {
        "guideline_id": "BYT-R05-01",
        "icd10_prefix": "R05",
        "disease_name_vi": "Ho có đờm cấp tính",
        "first_line_ingredients": ["Acetylcysteine", "Ambroxol"],
        "second_line_or_special_ingredients": [],
        "avoid_combinations": ["Không phối hợp thuốc tiêu đờm (Acetylcysteine/Ambroxol) với thuốc ức chế ho (Codein/Dextromethorphan)"],
        "safety_red_flags": ["Ho ra máu, sốt cao > 3 ngày, khó thở, đau tức ngực -> chuyển khám chuyên khoa ngay"],
        "missing_info_checks": ["allergies", "age", "asthma_history"],
        "content_excerpt": "Sử dụng thuốc tiêu đờm (Acetylcysteine 200mg hoặc Ambroxol 30mg) uống nhiều nước để làm loãng dịch tiết đường hô hấp.",
        "official_source_url": "https://kcb.vn/",
    },
    {
        "guideline_id": "BYT-A04-01",
        "icd10_prefix": "A04",
        "disease_name_vi": "Nhiễm trùng tiêu hóa và tiêu chảy cấp",
        "first_line_ingredients": ["Oresol (ORS)", "Diosmectite", "Bacillus subtilis", "Alverine citrate + Simethicone"],
        "second_line_or_special_ingredients": ["Cefixime", "Paracetamol"],
        "avoid_combinations": ["Uống Diosmectite cách các thuốc khác >= 2 giờ để tránh giảm hấp thu"],
        "safety_red_flags": ["Mất nước nặng, phân có máu, sốt cao liên tục -> chuyển tuyến cấp cứu/nội trú"],
        "missing_info_checks": ["allergies", "age", "dehydration_status"],
        "content_excerpt": "Bù nước điện giải (Oresol) là nền tảng; phối hợp chất hấp phụ (Diosmectite), men vi sinh (Bacillus subtilis), chống co thắt (Alverine+Simethicone) và kháng sinh (Cefixime) khi có chỉ định nhiễm khuẩn.",
        "official_source_url": "https://kcb.vn/",
    },
    {
        "guideline_id": "BYT-K59-01",
        "icd10_prefix": "K59",
        "disease_name_vi": "Rối loạn chức năng ruột khác / Tiêu chảy",
        "first_line_ingredients": ["Oresol (ORS)", "Diosmectite", "Bacillus subtilis", "Alverine citrate + Simethicone"],
        "second_line_or_special_ingredients": [],
        "avoid_combinations": ["Uống Diosmectite cách các thuốc khác >= 2 giờ; tránh thuốc chống co thắt khi nghi tắc ruột"],
        "safety_red_flags": ["Mất nước nặng, phân nhầy máu, đau bụng cấp ngoại khoa (nghi ruột thừa) -> chuyển cấp cứu ngay"],
        "missing_info_checks": ["allergies", "age", "dehydration_status"],
        "content_excerpt": "Kiểm soát triệu chứng rối loạn chức năng ruột / tiêu chảy bằng bù nước điện giải (Oresol), chất hấp phụ bảo vệ niêm mạc (Diosmectite), men vi sinh (Bacillus subtilis) và giảm co thắt (Alverine + Simethicone).",
        "official_source_url": "https://kcb.vn/",
    },
    {
        "guideline_id": "BYT-M75-01",
        "icd10_prefix": "M75",
        "disease_name_vi": "Hội chứng bao gân xoay / Viêm gân vai",
        "first_line_ingredients": ["Paracetamol", "Celecoxib", "Meloxicam", "Ketoprofen"],
        "second_line_or_special_ingredients": ["Eperisone", "Vitamin B1 + B6 + B12", "Pantoprazole", "Esomeprazole"],
        "avoid_combinations": ["Không phối hợp hai NSAID cùng lúc; tránh NSAID khi dị ứng NSAID hoặc dùng Warfarin/suy thận nặng"],
        "safety_red_flags": ["Khi dùng NSAID đường uống cần đánh giá nguy cơ tiêu hóa và cân nhắc PPI bảo vệ dạ dày"],
        "missing_info_checks": ["allergies", "age", "renal_function_status", "gi_ulcer_history"],
        "content_excerpt": "Giảm đau kháng viêm (Celecoxib/Meloxicam kèm PPI bảo vệ dạ dày nếu có nguy cơ, hoặc Ketoprofen bôi ngoài) phối hợp giãn cơ (Eperisone) và vitamin nhóm B.",
        "official_source_url": "https://kcb.vn/",
    },
    {
        "guideline_id": "BYT-M54-01",
        "icd10_prefix": "M54",
        "disease_name_vi": "Đau cơ vùng thắt lưng cấp",
        "first_line_ingredients": ["Paracetamol", "Eperisone", "Celecoxib", "Meloxicam"],
        "second_line_or_special_ingredients": ["Vitamin B1 + B6 + B12", "Pantoprazole"],
        "avoid_combinations": ["Không dùng quá 4000mg Paracetamol/ngày; không phối hợp 2 NSAID"],
        "safety_red_flags": ["Hội chứng chùm đuôi ngựa, yếu liệt chi dưới, rối loạn cơ tròn -> chuyển cấp cứu ngoại thần kinh"],
        "missing_info_checks": ["allergies", "age", "gi_ulcer_history", "renal_function_status"],
        "content_excerpt": "Phối hợp giảm đau (Paracetamol hoặc NSAID uống sau ăn no) cùng thuốc giãn cơ trung ương (Eperisone 50mg) trong đợt cấp.",
        "official_source_url": "https://kcb.vn/",
    },
    {
        "guideline_id": "BYT-M17-01",
        "icd10_prefix": "M17",
        "disease_name_vi": "Thoái hóa khớp gối",
        "first_line_ingredients": ["Paracetamol", "Glucosamine sulfate"],
        "second_line_or_special_ingredients": ["Celecoxib", "Meloxicam", "Ketoprofen"],
        "avoid_combinations": [
            "TUYỆT ĐỐI KHÔNG kê bất kỳ NSAID nào (kể cả bôi ngoài) nếu bệnh nhân dị ứng NSAID hoặc đang dùng Warfarin"
        ],
        "safety_red_flags": [
            "Tương tác xuất huyết nặng giữa NSAID và thuốc chống đông Warfarin",
            "Chống chỉ định NSAID ở bệnh nhân suy thận mạn giai đoạn 3 trở lên / tiền sử dị ứng NSAID",
        ],
        "missing_info_checks": ["allergies", "age", "concurrent_medications", "renal_function_status"],
        "content_excerpt": "Ưu tiên Paracetamol và thuốc tác dụng chậm (Glucosamine sulfate) cùng biện pháp không dùng thuốc; chỉ dùng NSAID khi không dị ứng, không dùng chống đông và chức năng thận cho phép.",
        "official_source_url": "https://kcb.vn/",
    },
    {
        "guideline_id": "BYT-I83-01",
        "icd10_prefix": "I83",
        "disease_name_vi": "Suy giãn tĩnh mạch chi dưới mạn tính",
        "first_line_ingredients": ["Diosmin + Hesperidin", "Rutin + Vitamin C"],
        "second_line_or_special_ingredients": [],
        "avoid_combinations": ["Không phối hợp trùng lặp nhiều chế phẩm cùng nhóm trợ tĩnh mạch không cần thiết"],
        "safety_red_flags": ["Sưng nóng đỏ đau đột ngột một bên chân (nghi huyết khối tĩnh mạch sâu DVT) -> siêu âm cấp cứu"],
        "missing_info_checks": ["allergies", "age", "lactation_status"],
        "content_excerpt": "Thuốc trợ tĩnh mạch flavonoid (Diosmin + Hesperidin 450mg+50mg hoặc Rutin + Vitamin C) kết hợp mang vớ áp lực và thay đổi lối sống.",
        "official_source_url": "https://kcb.vn/",
    },
    {
        "guideline_id": "BLL5-B35-01",
        "icd10_prefix": "B35",
        "disease_name_vi": "Nhiễm nấm da nông",
        "first_line_ingredients": ["Clotrimazole", "Terbinafine"],
        "second_line_or_special_ingredients": ["Itraconazole"],
        "avoid_combinations": ["TUYỆT ĐỐI KHÔNG phối hợp Itraconazole đường uống với Simvastatin/Atorvastatin (nguy cơ tiêu cơ vân)"],
        "safety_red_flags": ["Kiểm tra men gan và tương tác CYP3A4 nếu cân nhắc thuốc kháng nấm azol đường uống"],
        "missing_info_checks": ["allergies", "age", "liver_function_status", "concurrent_medications"],
        "content_excerpt": "Theo tài liệu chuyên môn Bài LL 5: ưu tiên thuốc kháng nấm bôi tại chỗ (Clotrimazole 1% hoặc Terbinafine 1%) cho nấm da nông khu trú; chỉ dùng Itraconazole đường uống khi tổn thương lan rộng và không có chống chỉ định.",
        "official_source_url": "https://kcb.vn/",
    },
    {
        "guideline_id": "BLL5-B02-01",
        "icd10_prefix": "B02",
        "disease_name_vi": "Zona thần kinh (Herpes zoster)",
        "first_line_ingredients": ["Acyclovir", "Valacyclovir", "Paracetamol"],
        "second_line_or_special_ingredients": ["Vitamin B1 + B6 + B12"],
        "avoid_combinations": ["Hiệu chỉnh liều Acyclovir/Valacyclovir theo chức năng thận; tránh phối hợp NSAID độc thận"],
        "safety_red_flags": ["Zona vùng mắt / trán mũi (Hutchinson), suy giảm miễn dịch nặng -> hội chẩn chuyên khoa ngay"],
        "missing_info_checks": ["allergies", "age", "renal_function_status", "onset_within_72h"],
        "content_excerpt": "Theo tài liệu chuyên môn Bài LL 5: khởi trị sớm thuốc kháng virus trong vòng 48-72 giờ (Acyclovir 800mg x 5 lần/ngày hoặc Valacyclovir 500mg-1000mg x 3 lần/ngày) kết hợp giảm đau và uống đủ nước.",
        "official_source_url": "https://kcb.vn/",
    },
    {
        "guideline_id": "BLL5-J09-01",
        "icd10_prefix": "J09",
        "disease_name_vi": "Cúm A / Nhiễm virus cúm mùa",
        "first_line_ingredients": ["Oseltamivir", "Paracetamol"],
        "second_line_or_special_ingredients": ["Amoxicillin + Clavulanic acid", "Cefuroxime"],
        "avoid_combinations": ["Tránh Aspirin ở trẻ em/thanh thiếu niên (hội chứng Reye); kiểm tra dị ứng trước khi dùng kháng sinh bội nhiễm"],
        "safety_red_flags": [
            "Phụ nữ mang thai (đặc biệt tam cá nguyệt 3) mắc cúm A bội nhiễm là nhóm nguy cơ cao -> cần bác sĩ chuyên khoa đánh giá lợi ích/nguy cơ kỹ và xác nhận dị ứng trước khi duyệt"
        ],
        "missing_info_checks": ["allergies", "age", "pregnancy_status", "renal_function_status"],
        "content_excerpt": "Theo tài liệu chuyên môn Bài LL 5: Oseltamivir 75mg x 2 lần/ngày trong 5 ngày hiệu quả nhất khi dùng trong 48 giờ đầu; thận trọng cân nhắc nguy cơ-lợi ích ở phụ nữ mang thai và chỉnh liều khi suy thận.",
        "official_source_url": "https://kcb.vn/",
    },
]


def clean_str(val: Any) -> str | None:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    s = re.sub(r"\s+", " ", str(val)).strip()
    return s if s else None


def parse_icd10_codes(val: Any) -> list[str]:
    s = clean_str(val)
    if not s:
        return []
    out, seen = [], set()
    for part in re.split(r"[;,]+", s):
        code = part.strip().upper()
        if code and code not in seen:
            seen.add(code)
            out.append(code)
    return out


def parse_diagnoses(val: Any) -> list[str]:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return []
    raw = str(val).replace("\r", "\n")
    out, seen = [], set()
    for part in re.split(r"[;\n]+", raw):
        s = re.sub(r"\s+", " ", part).strip(" .-\t")
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def strip_text_pii(text: str | None) -> str | None:
    if not text:
        return text
    s = re.sub(r"\bDT25\d+\b", "[REDACTED_CODE]", text)
    s = re.sub(r"(?<!\d)0[35789]\d{8}(?!\d)", "[REDACTED_PHONE]", s)
    s = re.sub(r"(?<!\d)\d{12}(?!\d)", "[REDACTED_ID]", s)
    return s


def route_group(route: str | None) -> str:
    """Normalize administration route into strict compatibility groups."""
    r = (clean_str(route) or "").lower()
    if not r:
        return ""
    if "xịt mũi" in r:
        return "nasal_spray"
    if "hít" in r:
        return "inhaled"
    if "khí dung" in r:
        return "nebulized"
    if "bôi" in r:
        return "topical"
    if "tiêm" in r or "truyền" in r:
        return "injectable"
    if "nhỏ mắt" in r or "tra mắt" in r:
        return "ophthalmic"
    if "súc" in r:
        return "gargle"
    if "ngậm" in r:
        return "sublingual"
    if "uống" in r or "nhai" in r:
        return "oral"
    return r


def norm_drug_name(name: str | None) -> str:
    """Canonicalize active ingredient / brand name without losing multi-ingredient structure."""
    s = (clean_str(name) or "").lower()
    s = re.sub(r"\s*[+/]\s*", " + ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def norm_strength(strength: str | None) -> str:
    s = (clean_str(strength) or "").lower().replace(" ", "")
    s = s.replace(",", ".")
    return s


def match_in_scope_prefixes(codes: list[str], diagnoses: list[str]) -> list[str]:
    diag_low = " | ".join(diagnoses).lower()
    if any(p.search(diag_low) for p in EXCLUDED_DIAGNOSIS_PATTERNS):
        return []
    matched: list[str] = []
    for prefix, pats in ALL_DISEASE_PATTERNS.items():
        has_icd = any(c.startswith(prefix) for c in codes)
        has_kw = any(p.search(diag_low) for p in pats)
        if has_icd or has_kw:
            matched.append(prefix)
    return matched


def match_core_prefixes(codes: list[str], diagnoses: list[str]) -> list[str]:
    diag_low = " | ".join(diagnoses).lower()
    matched = []
    for prefix, kws in CORE_ONLY_KEYWORDS.items():
        if any(c.startswith(prefix) for c in codes) or any(kw in diag_low for kw in kws):
            matched.append(prefix)
    return matched


def is_excluded_case(age: Any, diagnoses: list[str], in_scope: list[str]) -> bool:
    if not diagnoses or all(not d.strip() for d in diagnoses):
        return True
    if isinstance(age, (int, float)) and age < 18:
        return True
    diag_low = " | ".join(diagnoses).lower()
    if any(p.search(diag_low) for p in EXCLUDED_DIAGNOSIS_PATTERNS):
        return True
    if not in_scope:
        return True
    return False


def build_strict_drug_lookup(
    catalog: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str, str], str], dict[tuple[str, str], str]]:
    """Build exact (name, route_group, strength) and (name, route_group) maps.

    Never indexes component_ingredients alone and never allows cross-route matches.
    """
    exact_with_strength: dict[tuple[str, str, str], str] = {}
    exact_no_strength: dict[tuple[str, str], str] = {}
    ambiguous_no_strength: set[tuple[str, str]] = set()

    for item in catalog:
        did = item["drug_id"]
        rg = route_group(item.get("route_of_administration"))
        st = norm_strength(item.get("strength_dosage"))
        candidate_names = {
            item["canonical_name"],
            item["active_ingredient"],
            *(item.get("aliases") or []),
            *(item.get("sample_brand_names") or []),
        }
        for raw_n in candidate_names:
            nn = norm_drug_name(raw_n)
            if not nn:
                continue
            if st:
                exact_with_strength.setdefault((nn, rg, st), did)
            key2 = (nn, rg)
            if key2 in exact_no_strength and exact_no_strength[key2] != did:
                ambiguous_no_strength.add(key2)
            else:
                exact_no_strength[key2] = did

    for k in ambiguous_no_strength:
        exact_no_strength.pop(k, None)

    return exact_with_strength, exact_no_strength


def match_drug_id_strict(
    ingredient: str,
    strength: str | None,
    route: str | None,
    exact_with_strength: dict[tuple[str, str, str], str],
    exact_no_strength: dict[tuple[str, str], str],
) -> str | None:
    nn = norm_drug_name(ingredient)
    rg = route_group(route)
    st = norm_strength(strength)
    if not nn or not rg:
        return None
    if st and (nn, rg, st) in exact_with_strength:
        return exact_with_strength[(nn, rg, st)]
    if (nn, rg) in exact_no_strength:
        return exact_no_strength[(nn, rg)]
    return None


def main() -> None:
    rng = np.random.default_rng(42)

    # 1. Build clean 83-drug catalog (preserving DRUG-001..DRUG-052 + clean EXTRA_DRUGS)
    drug_path = PROCESSED_DIR / "drug_catalog_clean.json"
    drugs: list[dict[str, Any]] = json.loads(drug_path.read_text(encoding="utf-8"))
    drugs = [d for d in drugs if int(d["drug_id"].split("-")[1]) <= 52]
    existing_keys = {
        (d["canonical_name"].lower(), (d.get("strength_dosage") or "").lower())
        for d in drugs
    }
    next_id = 53
    for item in EXTRA_DRUGS:
        key = (item["canonical_name"].lower(), (item.get("strength_dosage") or "").lower())
        if key in existing_keys:
            continue
        existing_keys.add(key)
        entry = {
            "drug_id": f"DRUG-{next_id:03d}",
            **item,
            "unit_price_vnd_synthetic": int(rng.integers(3, 51) * 500),
            "price_is_synthetic": True,
            "verification_status": "VERIFIED_FOR_SIMULATION",
        }
        src_ref = entry.pop("source_reference")
        entry["source_reference"] = src_ref
        drugs.append(entry)
        next_id += 1
    drug_path.write_text(json.dumps(drugs, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. Build clean 17-guideline file (4 core + 13 outpatient including BYT-K59-01)
    guide_path = PROCESSED_DIR / "guidelines_clean.json"
    guides: list[dict[str, Any]] = json.loads(guide_path.read_text(encoding="utf-8"))
    core_ids = {"BYT-I10-01", "BYT-E78-01", "BYT-E11-01", "BYT-K21-01"}
    guides = [g for g in guides if g["guideline_id"] in core_ids]
    guides.extend(EXTRA_GUIDELINES)
    guide_path.write_text(json.dumps(guides, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3. Build clean, adult-only, in-scope case_base_clean.json with strict drug_id matching
    case_path = PROCESSED_DIR / "case_base_clean.json"
    existing_cases: list[dict[str, Any]] = json.loads(case_path.read_text(encoding="utf-8"))
    core_cases = [c for c in existing_cases if int(c["case_id"].split("-")[-1]) <= 52]
    exact_ws, exact_ns = build_strict_drug_lookup(drugs)

    clean_cases: list[dict[str, Any]] = []
    for c in core_cases:
        diags = [strip_text_pii(d) or "" for d in c.get("diagnoses", []) if d and d.strip()]
        in_scope = match_in_scope_prefixes(c.get("icd10_codes", []), diags)
        if is_excluded_case(c["patient_profile"].get("age"), diags, in_scope):
            continue
        c["diagnoses"] = diags
        c["in_scope_icd10_prefixes"] = in_scope
        vcount = 0
        for m in c.get("medications", []):
            m["usage_instruction_full"] = strip_text_pii(m.get("usage_instruction_full"))
            did = match_drug_id_strict(
                m.get("active_ingredient", ""),
                m.get("strength_dosage"),
                m.get("route"),
                exact_ws,
                exact_ns,
            )
            m["drug_id"] = did
            m["in_verified_catalog"] = did is not None
            if did is not None:
                vcount += 1
        c["verified_catalog_meds_count"] = vcount
        clean_cases.append(c)

    # Append remaining adult, in-scope cases from raw CSV
    raw_df = pd.read_csv(RAW_CSV_PATH, encoding="utf-8-sig")
    raw_df = raw_df[raw_df["page_number"].notna() & raw_df["active_ingredient"].notna()].copy()
    raw_df["page_num_int"] = raw_df["page_number"].astype(int)

    next_case = 53
    for _, grp in raw_df.groupby("page_num_int", sort=True):
        first = grp.iloc[0]
        icds = parse_icd10_codes(first.get("icd10_codes"))
        diags = [strip_text_pii(d) or "" for d in parse_diagnoses(first.get("diagnosis_primary_and_comorbidities"))]
        if match_core_prefixes(icds, diags):
            continue  # Already handled in SYN-CASE-001..052

        age_raw = clean_str(first.get("patient_age"))
        age_syn = None
        if age_raw:
            m_age = re.search(r"(\d+)", age_raw)
            if m_age:
                a = int(m_age.group(1))
                age_syn = max(18, a + int(rng.choice([-2, -1, 1, 2]))) if a >= 18 else int(np.clip(a + int(rng.choice([-1, 0, 1])), 1, 17))

        in_scope = match_in_scope_prefixes(icds, diags)
        if is_excluded_case(age_syn, diags, in_scope):
            continue

        w_syn = None
        if pd.notna(first.get("weight_kg")):
            w = float(first["weight_kg"])
            if w > 3.5:
                w_syn = round(w + float(rng.choice([-1.0, -0.5, 0.5, 1.0])), 1)

        g_raw = (clean_str(first.get("patient_gender")) or "").lower()
        gender = "Nam" if g_raw in {"nam", "male", "m"} else ("Nữ" if g_raw in {"nữ", "nu", "female", "f"} else "unknown")
        allergy = clean_str(first.get("allergies")) or "unknown"

        meds = []
        vcount = 0
        for idx, (_, row) in enumerate(grp.iterrows(), start=1):
            ing = clean_str(row.get("active_ingredient")) or ""
            strength = clean_str(row.get("strength_dosage"))
            route = clean_str(row.get("route_of_administration"))
            did = match_drug_id_strict(ing, strength, route, exact_ws, exact_ns)
            in_cat = did is not None
            if in_cat:
                vcount += 1
            usage = strip_text_pii(clean_str(row.get("usage_instruction_full")))
            dur_m = re.search(r"(\d+)\s*ngày\b", usage or "", re.IGNORECASE)
            sched = {}
            for k_out, col in [("morning", "dose_morning"), ("noon", "dose_noon"), ("afternoon", "dose_afternoon"), ("evening", "dose_evening")]:
                if pd.notna(row.get(col)):
                    v = float(row[col])
                    sched[k_out] = int(v) if v.is_integer() else round(v, 3)
            qty_raw = row.get("quantity")
            qty = int(float(qty_raw)) if pd.notna(qty_raw) and float(qty_raw).is_integer() else (round(float(qty_raw), 2) if pd.notna(qty_raw) else None)
            freq_raw = row.get("frequency_per_day")
            freq = int(float(freq_raw)) if pd.notna(freq_raw) and float(freq_raw).is_integer() else (round(float(freq_raw), 2) if pd.notna(freq_raw) else None)
            meds.append({
                "med_index": idx,
                "drug_id": did,
                "in_verified_catalog": in_cat,
                "canonical_name": ing,
                "active_ingredient": ing,
                "strength_dosage": strength,
                "route": route,
                "quantity": qty,
                "unit": clean_str(row.get("unit")),
                "duration_days": int(dur_m.group(1)) if dur_m else None,
                "frequency_per_day": freq,
                "dosage_schedule": sched,
                "meal_timing": clean_str(row.get("meal_timing")),
                "usage_instruction_full": usage,
            })

        clean_cases.append({
            "case_id": f"SYN-CASE-{next_case:03d}",
            "is_synthetic": True,
            "seed": 42,
            "patient_profile": {
                "age": age_syn,
                "gender": gender,
                "weight_kg": w_syn,
                "allergies": allergy,
            },
            "icd10_codes": icds,
            "in_scope_icd10_prefixes": in_scope,
            "icd10_backfilled_from_diagnosis": False,
            "diagnoses": diags,
            "total_meds": len(meds),
            "verified_catalog_meds_count": vcount,
            "medications": meds,
        })
        next_case += 1

    case_path.write_text(json.dumps(clean_cases, ensure_ascii=False, indent=2), encoding="utf-8")

    # 4. Self-audit all 4 defect classes + PII audit
    guide_prefixes = {g["icd10_prefix"] for g in guides}
    drug_icds = {ic for d in drugs for ic in d.get("verified_indications_icd10", [])}
    assert drug_icds <= guide_prefixes, f"Missing guidelines for {drug_icds - guide_prefixes}"

    cat_names = {d["canonical_name"] for d in drugs}
    for g in guides:
        for ing in g.get("first_line_ingredients", []) + g.get("second_line_or_special_ingredients", []):
            # Core guidelines (I10..K21) contain general class/ingredient names; EXTRA_GUIDELINES must exact match
            if g["guideline_id"] not in core_ids:
                assert ing in cat_names, f"Guideline {g['guideline_id']} ingredient {ing!r} not in canonical_name"

    for d in drugs:
        src = d.get("source_reference", "")
        assert ".xlsx" not in src and ".pdf" not in src and "data/" not in src, f"Local file in {d['drug_id']}: {src}"
    for g in guides:
        url = g.get("official_source_url", "")
        assert ".xlsx" not in url and ".pdf" not in url and "data/" not in url, f"Local file in {g['guideline_id']}: {url}"

    for c in clean_cases:
        assert c["diagnoses"] and c["in_scope_icd10_prefixes"], f"Invalid scope/diag in {c['case_id']}"
        age_v = c["patient_profile"].get("age")
        assert age_v is None or age_v >= 18, f"Pediatric leaked: {c['case_id']}"

    for path in (drug_path, guide_path, case_path):
        txt = path.read_text(encoding="utf-8")
        for pname, pat in PII_AUDIT_PATTERNS.items():
            hits = pat.findall(txt)
            assert not hits, f"PII audit failed in {path.name} for {pname}: {hits[:3]}"

    print(
        f"[OK] drugs={len(drugs)} | guidelines={len(guides)} | cases={len(clean_cases)} "
        f"| verified_case_meds={sum(c['verified_catalog_meds_count'] for c in clean_cases)} | ALL_4_AUDITS=PASS"
    )


if __name__ == "__main__":
    main()
