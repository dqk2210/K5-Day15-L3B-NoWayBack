"""Máy chủ Medora chạy trên loopback, dùng thư viện chuẩn Python."""

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import re
import sys
import time
import uuid
from threading import RLock
from urllib.parse import parse_qs, urlsplit

from tools import (
    DIAGNOSIS_KEYWORDS,
    OUT_OF_SCOPE_KEYWORDS,
    _load_json,
    _search_key,
    calculate_cost,
    retrieve_similar_cases,
    search_drug_catalog,
    search_guidelines,
    validate_prescription,
)


# Windows consoles may default to a code page without Vietnamese characters.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


PAGE = Path(__file__).resolve().parents[1] / "web" / "medora.html"
ICD = re.compile(r"^([A-Z][0-9]{2}(?:\.[A-Z0-9]{1,4})?)(?=$|\s|[-–—:])", re.I)
DIAGNOSIS_SEPARATOR = re.compile(r"[,;\n]+")
EXTRA_DIAGNOSIS_ALIASES = {
    "E11": ["đái tháo đường type 2", "tiểu đường type 2", "đái tháo đường típ 2", "tiểu đường tuýp 2"],
}
MAX_BODY = 16_384
LOG = logging.getLogger("medora")
TRACE_LOCK = RLock()
TRACE_DIR = PAGE.parents[1] / "traces"


def text_field(data, key, limit=300):
    value = data.get(key, "")
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"Trường {key} phải là văn bản tối đa {limit} ký tự.")
    return value.strip()


def number_field(data, key, low, high, *, whole=False, optional=False):
    value = data.get(key)
    if value is None and optional:
        return None
    if (type(value) not in (int, float) or not low <= value <= high
            or (whole and int(value) != value)):
        raise ValueError(f"Trường {key} phải là số {'nguyên ' if whole else ''}từ {low} đến {high}.")
    return int(value) if whole else value


def patient_input(body):
    gender = text_field(body, "gender", 15) or "Chưa rõ"
    if gender not in {"Nam", "Nữ", "Chưa rõ"}:
        raise ValueError("Chọn giới tính hợp lệ.")

    def status(key):
        value = text_field(body, key, 15) or "unknown"
        if value not in {"yes", "no", "unknown"}:
            raise ValueError(f"Trường {key} cần giá trị Có, Không hoặc Chưa rõ.")
        return {"yes": True, "no": False, "unknown": "unknown"}[value]

    age = number_field(body, "age", 0, 150, whole=True, optional=True)
    allergies = text_field(body, "allergies")
    if allergies.casefold() in {"chưa ghi nhận", "chưa xác minh", "chưa biết", "không rõ", "n/a", "-"}:
        allergies = "unknown"
    medications = text_field(body, "current_medications", 600)
    comorbidities = text_field(body, "comorbidities", 600)
    pregnancy = status("pregnancy")
    if pregnancy is True and re.search(r"dọa sảy|doạ sảy|ra huyết", comorbidities, re.I):
        pregnancy_risk = True
    else:
        pregnancy_risk = False
    return {
        "age": age,
        "is_adult": age is not None and age >= 18,
        "weight_kg": number_field(body, "weight_kg", 0.01, 500, optional=True),
        "gender": gender,
        "allergies": allergies,
        "comorbidities": [comorbidities],
        "current_medications": [medications],
        "is_pregnant": pregnancy,
        "high_risk_pregnancy": pregnancy_risk,
        "pregnancy_weeks": number_field(body, "pregnancy_weeks", 1, 45, whole=True, optional=True)
        if pregnancy is True else None,
        "renal_impairment": status("renal"),
        "egfr": number_field(body, "egfr", 0, 250, optional=True),
        "liver_disease": status("liver"),
    }


def web_guidelines():
    # Keep broad or misleading legacy CLI keywords out of diagnosis resolution.
    ambiguous = {"tiền đái tháo đường", "tiêu chảy", "rối loạn tiêu hóa"}
    return [
        {**guide, "search_aliases": [
            name for name in DIAGNOSIS_KEYWORDS.get(guide["icd10_prefix"], [])
            if name not in ambiguous
        ] + EXTRA_DIAGNOSIS_ALIASES.get(guide["icd10_prefix"], [])}
        for guide in _load_json("guidelines_clean.json")
    ]


def resolve_diagnoses(body):
    field = "diagnosis" if "diagnosis" in body else "icd10"
    text = text_field(body, field, 500)
    terms = [part.strip() for part in DIAGNOSIS_SEPARATOR.split(text) if part.strip()]
    if not 1 <= len(terms) <= 10:
        raise ValueError("Nhập từ 1 đến 10 chẩn đoán, phân cách bằng dấu phẩy hoặc chấm phẩy.")
    names = {
        _search_key(name): guide["icd10_prefix"]
        for guide in web_guidelines()
        for name in [guide["disease_name_vi"], *guide["search_aliases"]]
    }
    codes = []
    unmatched = []
    for term in terms:
        match = ICD.match(term)
        code = match[1].upper() if match else names.get(_search_key(term))
        if code:
            codes.append(code)
        else:
            unmatched.append(term)
    return codes, unmatched


def diagnosis_checks(body):
    icds, unmatched = resolve_diagnoses(body)
    guide = search_guidelines(icds)
    unmatched.extend(icd for icd in icds if icd[:3] in guide["out_of_scope_codes"])
    unmatched = list(dict.fromkeys(unmatched))
    checks = {"status": "PASS", "blocking_violations": [], "warnings": [], "missing_fields": []}
    if unmatched:
        checks["warnings"].append({
            "code": "UNMATCHED_DIAGNOSES",
            "message": "Chưa có phác đồ khớp chính xác cho: " + ", ".join(unmatched) + ".",
        })
        checks["status"] = "PASS_WITH_WARNINGS"
    known_high_risk = any(_search_key(keyword) in _search_key(term)
                          for term in unmatched for keyword, _ in OUT_OF_SCOPE_KEYWORDS)
    if not guide["is_in_scope"] or known_high_risk:
        checks["status"] = "BLOCKED"
        checks["blocking_violations"].append({
            "code": "OUT_OF_SCOPE",
            "message": "Chẩn đoán ngoài phạm vi dữ liệu mô phỏng. Kiểm tra lại tên chẩn đoán đã nhập.",
        })
    return guide, checks, unmatched


def ollama_rank(candidates, codes):
    from ai import call_model

    ids = [drug["drug_id"] for drug in candidates]
    references = [
        [med["drug_id"] for med in case["verified_medications"] if med["drug_id"] in ids]
        for case in retrieve_similar_cases(codes, top_k=2)
    ]
    model_input = {
        "icd10": codes,
        "options": [
            {"id": drug["drug_id"], "name": drug["canonical_name"], "guideline_tier": drug["tier"]}
            for drug in candidates
        ],
        "synthetic_case_drug_ids": references,
    }
    reply = call_model(
        "Sắp xếp các ID tham khảo theo bậc phác đồ và độ phù hợp với ca giả lập. "
        'Chỉ trả JSON {"ids": ["..."]}. Giữ đúng các ID đã cho. Không đề xuất thuốc hoặc liều mới.',
        json.dumps(model_input, ensure_ascii=False),
    )
    ordered = json.loads(reply["text"])["ids"]
    if (not isinstance(ordered, list) or not all(isinstance(item, str) for item in ordered)
            or len(ordered) != len(ids) or set(ordered) != set(ids)):
        raise ValueError("Ollama trả về danh sách ID không hợp lệ.")
    priority = {drug_id: index for index, drug_id in enumerate(ordered)}
    return sorted(candidates, key=lambda drug: (drug["tier"], priority[drug["drug_id"]]))


def reference_prescriptions(codes):
    synthetic_cases = {
        case["case_id"]: case for case in _load_json("case_base_clean.json")
        if case.get("is_synthetic") is True
    }
    fields = ("canonical_name", "strength_dosage", "route", "quantity", "unit",
              "duration_days", "frequency_per_day", "usage_instruction_full")
    references = {}
    for code in codes:
        for match in retrieve_similar_cases([code], top_k=2):
            case_id = match["case_id"]
            if case_id not in synthetic_cases or case_id in references:
                continue
            case = synthetic_cases[case_id]
            profile = case.get("patient_profile", {})
            references[case_id] = {
                "case_id": case_id,
                "matched_icd10": [c for c in codes if c in match["in_scope_icd10_prefixes"]],
                "diagnoses": [
                    re.sub(r"\s*\([A-Z]\d{2}(?:\.[A-Z0-9]+)?\)\s*$", "", name)
                    for name in case.get("diagnoses", [])
                ],
                "patient_profile": {key: profile.get(key) for key in ("age", "gender", "weight_kg")},
                "medications": [
                    {key: med.get(key) for key in fields}
                    for med in case.get("medications", [])
                    if med.get("in_verified_catalog") and med.get("drug_id") and med.get("canonical_name")
                ],
            }
    return list(references.values())


def suggest(body, use_ai):
    guide, checks, unmatched = diagnosis_checks(body)
    codes = guide["in_scope_codes"]
    suggestions = []
    guidelines = guide["matched_guidelines"]
    if checks["status"] != "BLOCKED":
        tiers = {
            g["icd10_prefix"]: (
                set(g["first_line_ingredients"]), set(g["second_line_or_special_ingredients"])
            )
            for g in guidelines
        }
        for drug in search_drug_catalog(icd10_codes=codes):
            name = drug["canonical_name"]
            matches = []
            for guideline in guidelines:
                code = guideline["icd10_prefix"]
                first, alternatives = tiers[code]
                if code in drug["verified_indications_icd10"] and (name in first or name in alternatives):
                    matches.append({"icd10": code, "guideline_id": guideline["guideline_id"],
                                    "tier": 1 if name in first else 2})
            if not matches:
                continue
            primary = min(matches, key=lambda match: match["tier"])
            suggestions.append({**drug, "tier": primary["tier"], "matches": matches,
                                "guideline_id": primary["guideline_id"]})
        suggestions.sort(key=lambda drug: (drug["tier"], drug["canonical_name"]))
    references = reference_prescriptions(codes) if checks["status"] != "BLOCKED" else []
    mode = "catalog"
    if use_ai and suggestions:
        try:
            suggestions = ollama_rank(suggestions, codes)
            mode = "ollama"
        except Exception as exc:
            LOG.warning("Ollama fallback (%s)", type(exc).__name__)
            mode = "catalog_fallback"
    return {
        "guardrail": checks,
        "guidelines": guidelines,
        "unmatched_diagnoses": unmatched,
        "suggestions": suggestions,
        "reference_prescriptions": references,
        "mode": mode,
        "is_simulation": True,
    }


def ai_draft(body):
    """Run the same agent as eval and preserve measured model usage for this request."""
    from ai import MODEL_PROVIDER
    from agent import answer
    import tracing

    if MODEL_PROVIDER == "fake":
        raise ValueError("AI chua duoc cau hinh. Dien MODEL_PROVIDER, MODEL_NAME va API_KEY trong .env, roi khoi dong lai server.")
    baseline = suggest(body, use_ai=False)
    profile = patient_input(body)
    if profile["age"] is not None and profile["age"] < 18:
        raise ValueError("Ban web chi ho tro ho so gia lap nguoi lon.")
    if baseline["guardrail"]["status"] == "BLOCKED":
        return {**baseline, "mode": "ai_not_called", "ai": {"status": "not_called", "reason": "OUT_OF_SCOPE", "model_calls": 0}}
    codes, _ = resolve_diagnoses(body)
    text = json.dumps({"icd10_codes": codes, "diagnosis_text": text_field(body, "diagnosis", 500)
                       if "diagnosis" in body else text_field(body, "icd10", 500),
                       "patient_profile": profile}, ensure_ascii=False)
    trace_id = "web-" + uuid.uuid4().hex
    started = time.perf_counter()
    payload = None
    error_kind = None
    # tracing.py has shared state. Serialize all web routes with TRACE_LOCK below.
    tracing.begin(trace_id)
    try:
        output = answer(text)["output"]
        payload = json.loads(output.rsplit("```json\n", 1)[1].split("```", 1)[0])
    except Exception as exc:
        error_kind = type(exc).__name__
    finally:
        summary, events = tracing.end()
    real = bool(summary["model_calls"] and summary["tokens_in"] + summary["tokens_out"] > 0
                and summary["models"] and not any(m.lower() in {"fake", "mock"} for m in summary["models"]))
    if not error_kind and summary["model_calls"] and not real:
        error_kind = "UnverifiedModelUsage"
    info = {**summary, "errors": [], "status": "error" if error_kind else "real" if real else "not_called",
            "trace_id": trace_id, "trace_file": "traces/" + trace_id + ".jsonl",
            "latency_s": round(time.perf_counter() - started, 3)}
    TRACE_DIR.mkdir(exist_ok=True)
    with (TRACE_DIR / (trace_id + ".jsonl")).open("x", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps({"run_id": trace_id, **event}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"kind": "web_final", "ai": info, "payload": payload,
                            "error_kind": error_kind}, ensure_ascii=False) + "\n")
    if error_kind:
        return {"error": "Khong tao duoc ban nhap AI (" + error_kind + "). Kiem tra cau hinh/model/API quota va trace. Khong dung ket qua offline thay the.", "ai": info}
    return {**baseline, "mode": "ai", "guardrail": payload["guardrail_result"],
            "ai_draft": payload, "ai": info}


def review(body):
    guide, checks, _ = diagnosis_checks(body)
    profile = patient_input(body)
    if profile["age"] is not None and profile["age"] < 18:
        checks["status"] = "BLOCKED"
        checks["blocking_violations"].append({
            "code": "OUT_OF_SCOPE", "message": "Dữ liệu mô phỏng chỉ hỗ trợ đơn ngoại trú người lớn.",
        })
    if checks["status"] == "BLOCKED":
        return {"guardrail": checks, "estimated_cost": None, "is_simulation": True}
    raw = body.get("medications")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 20:
        raise ValueError("Đơn nháp cần từ 1 đến 20 dòng thuốc.")
    meds = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Dòng thuốc phải là một đối tượng JSON.")
        med = {
            "drug_id": text_field(item, "drug_id", 30),
            "dose_per_intake": number_field(item, "dose_per_intake", 0.001, 1000, optional=True),
            "frequency_per_day": number_field(item, "frequency_per_day", 1, 24, whole=True, optional=True),
            "duration_days": number_field(item, "duration_days", 1, 365, whole=True, optional=True),
            "quantity": number_field(item, "quantity", 1, 10000, whole=True, optional=True),
        }
        meds.append(med)
    ids = [med["drug_id"] for med in meds]
    if len(set(ids)) != len(ids):
        raise ValueError("Mỗi mã thuốc chỉ được xuất hiện một lần trong đơn.")
    result = validate_prescription(meds, profile, guide["in_scope_codes"], require_patient_details=True)
    result["warnings"].extend(checks["warnings"])
    if any(m["dose_per_intake"] is None or m["frequency_per_day"] is None for m in meds):
        result["warnings"].append({"code": "DOSE_NOT_CHECKED",
                                   "message": "Một số dòng còn trống liều hoặc tần suất. Bác sĩ cần tự kiểm tra các dòng này."})
    if result["status"] == "PASS" and result["warnings"]:
        result["status"] = "PASS_WITH_WARNINGS"
    cost = calculate_cost(meds) if result["status"] != "BLOCKED" and all(m["quantity"] for m in meds) else None
    return {"guardrail": result, "estimated_cost": cost, "is_simulation": True}


class Handler(BaseHTTPRequestHandler):
    def log_request(self, code="-", size="-"):
        pass

    def send_body(self, status, content, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, status, payload):
        content = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        self.send_body(status, content, "application/json; charset=utf-8")

    def check_origin(self):
        host = self.headers.get("Host")
        port = self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        return host in allowed and (origin is None or origin == f"http://{host}")

    def handle_api(self, route):
        if not self.check_origin():
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Chỉ chấp nhận truy cập Medora từ địa chỉ local."})
            return
        try:
            with TRACE_LOCK:
                route()
        except (BrokenPipeError, ConnectionResetError):
            return
        except ValueError as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            LOG.error("Backend error (%s)", type(exc).__name__)
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Backend không thể xử lý yêu cầu."})

    def do_GET(self):
        self.handle_api(self.get_route)

    def get_route(self):
        target = urlsplit(self.path)
        if target.path in {"/", "/medora.html"}:
            self.send_body(HTTPStatus.OK, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif target.path == "/api/guidelines":
            self.send_json(HTTPStatus.OK, {"guidelines": web_guidelines()})
        elif target.path == "/api/reference-prescriptions":
            samples = reference_prescriptions(["J30"])
            self.send_json(HTTPStatus.OK, {"reference_prescriptions": samples[:1]})
        elif target.path == "/api/drugs":
            params = parse_qs(target.query, max_num_fields=8)
            query = text_field({"q": params.get("q", [""])[0]}, "q", 150)
            unit = text_field({"unit": params.get("unit", [""])[0]}, "unit", 30)
            matches = search_drug_catalog(query=query)
            drugs = [drug for drug in matches if not unit or drug["unit"] == unit]
            units = sorted({drug["unit"] for drug in search_drug_catalog() if drug["unit"]})
            self.send_json(HTTPStatus.OK, {"drugs": drugs, "units": units})
        elif target.path == "/api/health":
            from ai import MODEL_PROVIDER, MODEL_NAME, API_KEY
            self.send_json(HTTPStatus.OK, {"status": "ok", "ai_enabled": getattr(self.server, "draft_ai", True),
                           "provider": MODEL_PROVIDER, "model": MODEL_NAME,
                           "configured": MODEL_PROVIDER != "fake" and (bool(API_KEY) or MODEL_PROVIDER == "ollama")})
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Không tìm thấy đường dẫn."})

    def do_POST(self):
        self.handle_api(self.post_route)

    def post_route(self):
        path = self.path
        if path not in {"/api/prescriptions/suggest", "/api/prescriptions/review", "/api/prescriptions/draft"}:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Không tìm thấy đường dẫn."})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Gửi nội dung application/json."})
            return
        length = int(self.headers.get("Content-Length", 0))
        if not 0 < length <= MAX_BODY:
            self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Kích thước yêu cầu không hợp lệ."})
            return
        body = json.loads(self.rfile.read(length))
        if not isinstance(body, dict):
            raise ValueError("Nội dung yêu cầu phải là một đối tượng JSON.")
        if path.endswith("/draft"):
            result = ai_draft(body) if getattr(self.server, "draft_ai", True) else suggest(body, use_ai=False)
        else:
            result = suggest(body, self.server.use_ai) if path.endswith("/suggest") else review(body)
        if result.get("error"):
            self.send_json(HTTPStatus.BAD_GATEWAY, result)
            return
        self.send_json(HTTPStatus.OK, result)


def main():
    parser = argparse.ArgumentParser(description="Chạy Medora trên máy local.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ai", action="store_true", help="Bật sắp xếp thuốc tham khảo với Ollama.")
    parser.add_argument("--offline", action="store_true", help="Catalog-only demo; no model calls.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port phải từ 1 đến 65535.")
    if args.ai:
        from ai import API_BASE_URL, MODEL_NAME, MODEL_PROVIDER

        endpoint = urlsplit(API_BASE_URL or "http://localhost:11434/api/chat")
        if (MODEL_PROVIDER != "ollama" or not MODEL_NAME or endpoint.scheme != "http"
                or endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}
                or endpoint.username is not None or endpoint.path != "/api/chat"):
            parser.error("--ai cần MODEL_PROVIDER=ollama, MODEL_NAME và endpoint Ollama loopback /api/chat.")

    _load_json("guidelines_clean.json")
    search_drug_catalog()
    _load_json("case_base_clean.json")
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.use_ai = args.ai
        server.draft_ai = not args.offline
        print(f"Medora đang chạy tại http://127.0.0.1:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
