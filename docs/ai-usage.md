# Khai báo dùng AI

README của nhóm có mục "Dùng AI vào việc gì" (2–3 dòng, bắt buộc). Chi tiết phân công và kiểm soát của con người:

> Luật của đề: dùng AI để làm bài thoải mái, nhưng **ai không giải thích được phần có tên mình thì phần đó nhận 0 điểm**. Khai thiếu không bị trừ; giấu mới bị.

| Việc | Công cụ AI | AI làm gì | Người kiểm/sửa gì | Ai phụ trách |
|---|---|---|---|---|
| Code bản chạy thử | AI coding assistant | Hỗ trợ viết khung `codebase/tools.py`, `codebase/agent.py`, `codebase/ai.py` và unit test | Kiểm tra toàn bộ 8 luật guardrails Python thuần, logic tính giá, không phụ thuộc thư viện ngoài | Nguyễn Tiến Đạt |
| Prompt / thiết kế lời gọi mô hình | AI coding assistant | Gợi ý cấu trúc system prompt ép JSON schema và trích dẫn `guideline_id` / `drug_id` | Rà soát điều khoản cấm bịa thuốc, kiểm tra kết quả thực tế trên từng ca `thuong`/`kho`/`tu_choi` | Đỗ Quốc Khánh, Nguyễn Tiến Đạt |
| Đào data & làm sạch dữ liệu | AI coding assistant | Viết script `scripts/build_clean_dataset.py` và `scripts/expand_clean_dataset.py` | Kiểm tra tay danh mục 83 thuốc, đối chiếu Dược thư QG VN (2022) & `Bài LL 5`, chạy PII Audit Regex PASS | Nguyễn Tiến Đạt |
| Rà câu hỏi phỏng vấn / khảo sát | AI assistant | Chỉ rà câu dẫn dắt phỏng vấn | Nhóm tự thực hiện phỏng vấn, ghi chép không dùng AI bịa trích dẫn | Võ Thị Phương Nhung |
| Viết câu thử (benchmark) | AI coding assistant | Hỗ trợ chuẩn hóa định dạng 20 câu thử từ 100 toa ẩn danh & `Data thường gặp.xlsx` | Đối chiếu từng câu với `source` (`data_that` 11/20, `tu_viet` 9/20) và `metric_spec.yaml` | Mai Lê Bá Vương |
| Sinh data `synthetic` | Python script (`seed=42`) | Nhiễu tổng hợp tuổi/cân nặng và sinh đơn giá giả lập bội số 500đ | Xác nhận `price_is_synthetic=true`, `is_synthetic=true`, kiểm tay PII Audit = 0 rò rỉ | Nguyễn Tiến Đạt |
| Chấm cột `pass` (script hỗ trợ) | Python script (`scripts/grade_run.py`) | Hỗ trợ kiểm tra tự động schema JSON, `drug_id`, `calculate_cost` | Người chấm rà soát thủ công từng output và đối chiếu chéo 2 người trên 5 output | Mai Lê Bá Vương |
| Slide, văn bản | AI assistant | Hỗ trợ tóm tắt bố cục `slides/outline.md`, `spec.md`, `README.md` | Nhóm kiểm tra lại mọi con số trỏ đúng file kết quả đo thật | Đỗ Quốc Khánh, Võ Thị Phương Nhung |

**Không dùng AI để:** tạo người được phỏng vấn, trích dẫn, câu trả lời khảo sát; sửa kết quả các lượt đã chạy (`eval/run-*.csv`, `cost/simulate-*.csv`, `traces/`).
