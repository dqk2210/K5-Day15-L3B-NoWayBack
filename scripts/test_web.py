"""Kiểm thử HTTP của hai luồng Medora bằng dữ liệu giả lập."""

from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "codebase"))
from web import Handler, suggest


class MedoraHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.use_ai = False
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.worker = Thread(target=cls.server.serve_forever)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.worker.join()
        cls.server.server_close()

    def request(self, path, body=None, status=200):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            self.assertEqual(response.status, status)
            return response.read()

    def api(self, path, body=None, status=200):
        return json.loads(self.request("/api/" + path, body, status))

    def patient(self, **changes):
        fields = {
            "icd10": "I10", "age": 45, "gender": "Nữ", "weight_kg": 60,
            "allergies": "Không", "pregnancy": "no", "renal": "no", "liver": "no",
            "current_medications": "", "comorbidities": "",
        }
        return {**fields, **changes}

    def medication(self, **changes):
        fields = {
            "drug_id": "DRUG-001", "dose_per_intake": 1, "frequency_per_day": 1,
            "duration_days": 5, "quantity": 5,
        }
        return {**fields, **changes}

    def test_page_and_catalog_use_real_data(self):
        self.assertIn(b"prescriptions/draft", self.request("/"))
        self.assertEqual(self.api("health")["status"], "ok")
        self.assertTrue(self.api("health")["ai_enabled"])
        self.assertNotIn("api_key", self.api("health"))
        self.assertTrue(any(g["icd10_prefix"] == "J30" for g in self.api("guidelines")["guidelines"]))
        results = self.api("drugs?" + urlencode({"q": "Ámlodac 5", "unit": "Viên"}))
        self.assertEqual([drug["drug_id"] for drug in results["drugs"]], ["DRUG-001"])
        self.assertEqual(self.api("drugs?" + urlencode({"q": "Amlodipine", "unit": "Tuýp"}))["drugs"], [])
        self.request("/data/processed/case_base_clean.json", status=404)

    def test_offline_suggestions_have_catalog_and_guideline_ids(self):
        result = self.api("prescriptions/suggest", self.patient(icd10="J30.4"))
        self.assertEqual(result["mode"], "catalog")
        self.assertTrue(result["suggestions"])
        for drug in result["suggestions"]:
            self.assertIn("J30", drug["verified_indications_icd10"])
            self.assertTrue(drug["guideline_id"])
            self.assertNotIn("dose_per_intake", drug)

    def test_search_multiple_diagnoses_without_patient_details(self):
        body = {"diagnosis": "viem mui di ung, tăng huyết áp; chưa có dữ liệu"}
        result = self.api("prescriptions/suggest", body)
        self.assertEqual([g["icd10_prefix"] for g in result["guidelines"]], ["J30", "I10"])
        self.assertEqual(result["unmatched_diagnoses"], ["chưa có dữ liệu"])
        self.assertEqual(result["guardrail"]["status"], "PASS_WITH_WARNINGS")
        self.assertEqual({m["icd10"] for d in result["suggestions"] for m in d["matches"]}, {"J30", "I10"})
        self.assertEqual(len(result["suggestions"]), len({d["drug_id"] for d in result["suggestions"]}))
        self.assertEqual({code for c in result["reference_prescriptions"] for code in c["matched_icd10"]},
                         {"J30", "I10"})
        self.assertEqual(result, self.api("prescriptions/suggest",
                                          {**body, "age": 11, "allergies": "Amlodipine", "gender": "invalid"}))
        self.api("prescriptions/suggest", {"diagnosis": "  ;  "}, 400)

    def test_suggestions_stop_for_unsupported_or_high_risk_diagnosis(self):
        for changes in ({"diagnosis": "Chẩn đoán chưa xác định"}, {"diagnosis": "I10, C34"},
                        {"diagnosis": "tăng huyết áp, ung thu phoi"}):
            with self.subTest(changes=changes):
                result = self.api("prescriptions/suggest", self.patient(**changes))
                self.assertEqual(result["guardrail"]["status"], "BLOCKED")
                self.assertEqual(result["suggestions"], [])
                self.assertEqual(result["reference_prescriptions"], [])

    def test_reference_prescription_includes_original_rows(self):
        result = self.api("prescriptions/suggest", {"diagnosis": "viêm mũi dị ứng"})
        samples = result["reference_prescriptions"]
        self.assertTrue(samples)
        source = Path(__file__).resolve().parents[1] / "data" / "processed" / "case_base_clean.json"
        cases = {case["case_id"]: case for case in json.loads(source.read_text(encoding="utf-8"))}
        for sample in samples:
            case = cases[sample["case_id"]]
            expected = [m for m in case["medications"]
                        if m.get("in_verified_catalog") and m.get("drug_id") and m.get("canonical_name")]
            self.assertTrue(case["is_synthetic"])
            self.assertTrue(sample["diagnoses"])
            self.assertTrue(sample["medications"])
            self.assertEqual(len(sample["medications"]), len(expected))
            for row, original in zip(sample["medications"], expected):
                self.assertEqual(row["canonical_name"], original["canonical_name"])
                self.assertEqual(row["strength_dosage"], original["strength_dosage"])
                self.assertEqual(row["quantity"], original["quantity"])
                self.assertEqual(row["usage_instruction_full"], original["usage_instruction_full"])

    def test_initial_reference_prescription_needs_no_diagnosis(self):
        samples = self.api("reference-prescriptions")["reference_prescriptions"]
        self.assertEqual(len(samples), 1)
        self.assertTrue(samples[0]["diagnoses"])
        self.assertTrue(samples[0]["medications"])
        self.assertIn(samples[0]["case_id"], {
            case["case_id"] for case in self.api(
                "prescriptions/suggest", {"diagnosis": "viêm mũi dị ứng"}
            )["reference_prescriptions"]
        })

    def test_review_allows_optional_doses_but_checks_known_allergy(self):
        body = {"diagnosis": "tang huyet ap\nviem mui di ung", "medications": [{"drug_id": "DRUG-001"}]}
        result = self.api("prescriptions/review", body)
        self.assertEqual(result["guardrail"]["status"], "BLOCKED")
        self.assertIsNone(result["estimated_cost"])
        result = self.api("prescriptions/review", {**body, "allergies": "Amlodipine"})
        self.assertEqual(result["guardrail"]["status"], "BLOCKED")
        self.assertIn("CONTRAINDICATION", [v["code"] for v in result["guardrail"]["blocking_violations"]])
        result = self.api("prescriptions/review", {**body, "age": 11})
        self.assertEqual(result["guardrail"]["status"], "BLOCKED")

    def test_review_runs_safety_again_before_calculating_cost(self):
        med = self.medication()
        result = self.api("prescriptions/review", self.patient(medications=[med]))
        self.assertEqual(result["guardrail"]["status"], "PASS")
        self.assertTrue(result["estimated_cost"]["is_synthetic_price"])
        for medication, code in [
            (self.medication(dose_per_intake=20), "OVERDOSE"),
            (self.medication(drug_id="DRUG-999"), "UNVERIFIED_DRUG"),
        ]:
            with self.subTest(code=code):
                result = self.api("prescriptions/review", self.patient(medications=[medication]))
                self.assertEqual(result["guardrail"]["status"], "BLOCKED")
                self.assertIn(code, [x["code"] for x in result["guardrail"]["blocking_violations"]])
                self.assertIsNone(result["estimated_cost"])

    def test_review_rejects_invalid_dose_and_cross_origin_requests(self):
        self.api("prescriptions/review", self.patient(medications=[self.medication(quantity=True)]), 400)
        request = Request(self.base + "/api/health", headers={"Origin": "https://example.org"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=5)
        self.assertEqual(error.exception.code, 403)
        error.exception.close()

    def test_optional_model_can_only_reorder_existing_options(self):
        body = self.patient(icd10="J30", comorbidities="Dữ liệu riêng của hồ sơ thử")
        baseline = suggest(body, use_ai=False)["suggestions"]
        ids = [drug["drug_id"] for drug in baseline]
        with patch("ai.call_model", return_value={"text": json.dumps({"ids": ids[::-1]})}) as model:
            result = suggest(body, use_ai=True)
            self.assertEqual(result["mode"], "ollama")
            self.assertEqual({drug["drug_id"] for drug in result["suggestions"]}, set(ids))
            tier_order = [drug["tier"] for drug in result["suggestions"]]
            self.assertEqual(tier_order, sorted(tier_order))
            self.assertNotIn(body["comorbidities"], model.call_args.args[1])
        with patch("ai.call_model", return_value={"text": '{"ids": ["DRUG-999"]}'}):
            with self.assertLogs("medora", "WARNING"):
                result = suggest(body, use_ai=True)
            self.assertEqual(result["mode"], "catalog_fallback")
            self.assertEqual(result["suggestions"], baseline)

    def test_draft_uses_eval_agent_and_measured_usage(self):
        import tracing
        reply = {"text": json.dumps({"proposed_medications": [{"drug_id": "DRUG-001",
                 "dose_per_intake": 1, "frequency_per_day": 1, "duration_days": 5,
                 "quantity": 5, "rationale_source_id": "BYT-I10-01"}]}),
                 "model": "test-model", "tokens_in": 123, "tokens_out": 45}
        with patch("ai.MODEL_PROVIDER", "gemini"), patch("agent.call_model", tracing.model_call(lambda *a: reply)):
            result = self.api("prescriptions/draft", self.patient())
        self.assertEqual(result["mode"], "ai")
        self.assertEqual(result["ai"]["status"], "real")
        self.assertEqual(result["ai"]["tokens_in"], 123)
        self.assertEqual(result["ai"]["tokens_out"], 45)
        self.assertEqual(result["ai_draft"]["draft_medications"][0]["drug_id"], "DRUG-001")
        trace = Path(__file__).resolve().parents[1] / result["ai"]["trace_file"]
        self.addCleanup(trace.unlink, missing_ok=True)
        self.assertIn('"kind": "model"', trace.read_text(encoding="utf-8"))

    def test_draft_api_failure_never_returns_catalog_as_ai(self):
        def fail(*args):
            raise RuntimeError("provider failed")
        with patch("ai.MODEL_PROVIDER", "gemini"), patch("agent.call_model", side_effect=fail):
            result = self.api("prescriptions/draft", self.patient(), 502)
        self.assertEqual(result["ai"]["status"], "error")
        self.assertNotIn("suggestions", result)
        trace = Path(__file__).resolve().parents[1] / result["ai"]["trace_file"]
        self.addCleanup(trace.unlink, missing_ok=True)

    def test_draft_missing_age_stops_before_model(self):
        with patch("ai.MODEL_PROVIDER", "gemini"), patch("agent.call_model") as model:
            result = self.api("prescriptions/draft", self.patient(age=None))
        model.assert_not_called()
        self.assertEqual(result["ai"]["status"], "not_called")
        self.assertEqual(result["guardrail"]["status"], "BLOCKED")
        trace = Path(__file__).resolve().parents[1] / result["ai"]["trace_file"]
        self.addCleanup(trace.unlink, missing_ok=True)

    def test_draft_refuses_fake_provider(self):
        with patch("ai.MODEL_PROVIDER", "fake"), patch("agent.call_model") as model:
            result = self.api("prescriptions/draft", self.patient(), 400)
        model.assert_not_called()
        self.assertIn("error", result)
        self.assertNotIn("suggestions", result)


if __name__ == "__main__":
    unittest.main()
