"""Đếm bằng chứng CP3 và in các đoạn nguồn đã ẩn danh."""

import json
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "data" / "processed" / "case_base_clean.json"
ORIGINAL_IDS = {f"SYN-CASE-{number:03d}" for number in range(1, 53)}
EXAMPLES = (1, 2, 3, 4, 9)


def report(label, count, total):
    print(f"{label}: {count}/{total} ({count / total:.1%})")


def main():
    records = json.loads(SOURCE.read_text(encoding="utf-8-sig"))
    cases = {case["case_id"]: case for case in records if case["case_id"] in ORIGINAL_IDS}
    if cases.keys() != ORIGINAL_IDS:
        raise ValueError("Thiếu ca có nguồn gốc từ tập đơn BTC đã xử lý.")
    rows = [row for case in cases.values() for row in case["medications"]]
    multiple = [c for c in cases.values() if len({code[:3].upper() for code in c["icd10_codes"]}) >= 2]
    report("Từ hai nhóm ICD-10", len(multiple), len(cases))
    report("Từ hai nhóm ICD-10 và năm dòng thuốc", sum(len(c["medications"]) >= 5 for c in multiple), len(cases))
    report("Thiếu duration_days", sum(row.get("duration_days") is None for row in rows), len(rows))
    report("Thiếu frequency_per_day", sum(row.get("frequency_per_day") is None for row in rows), len(rows))
    for number in EXAMPLES:
        case_id = f"SYN-CASE-{number:03d}"
        row = next(row for row in cases[case_id]["medications"] if row["med_index"] == 1)
        print(f"{case_id} / 1 · {row['usage_instruction_full']}")


if __name__ == "__main__":
    main()
