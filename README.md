# NoWayBack — AI Hỗ trợ Bác sĩ Dự thảo Đơn thuốc Ngoại trú (Track B)

**Thành viên, lớp, track:** xem [TEAMS.md](TEAMS.md).

*Lát cắt: Bác sĩ nhập chẩn đoán đã xác nhận và thông tin bệnh nhân, AI đề xuất phương án kê đơn dựa trên tài liệu chuyên môn và danh mục thuốc (83 thuốc xác minh), hoặc báo thiếu căn cứ / chặn vi phạm an toàn bằng Python thuần, để bác sĩ kiểm duyệt và quyết định (HITL).*

---

## Chạy trong 3 phút

Yêu cầu **Python 3.10 trở lên** (chỉ dùng thư viện chuẩn cho `run.py` và `codebase/`, **không cần `pip install`**).

1. Tạo file `.env` từ `.env.example` và điền key thật:
   ```ini
   MODEL_PROVIDER=gemini
   MODEL_NAME=gemini-2.5-flash-lite
   API_KEY=<key của nhóm>
   ```
2. Chạy thử luồng tương tác (HITL):
   ```powershell
   python run.py
   ```
3. Kiểm tra toàn bộ benchmark & metric spec:
   ```powershell
   python run.py check
   ```

---

## Lệnh

| Lệnh | Làm gì |
|---|---|
| `python run.py` | Chạy bản chạy thử tương tác CLI kèm bước bác sĩ kiểm duyệt `[A]/[E]/[R]` |
| `python run.py check` | Kiểm `eval/benchmark.csv`, `eval/metric_spec.yaml` và `TEAMS.md` |
| `python run.py eval --try` | Chạy thử 3 câu đầu để kiểm tra kết nối model và số token |
| `python run.py eval` | Chạy đủ 20 câu thử qua `codebase/agent.py` -> `eval/run-N.csv` + `traces/run-N.jsonl` |
| `python scripts/grade_run.py eval/run-1.csv` | Hỗ trợ chấm tự động cột `pass` và `ghi_chu` theo schema & guardrails |
| `python run.py score eval/run-1.csv` | Tính % đạt tổng và theo từng loại (`thuong`, `kho`, `tu_choi`) |
| `python run.py simulate --try` | Thử mô phỏng chi phí 10 phiên |
| `python run.py simulate --rate-from eval/run-2.csv` | Mô phỏng chi phí 50 phiên dùng thật -> `cost/simulate-N.csv` + tóm tắt |
| `python scripts/test_guardrails.py` | Chạy unit test kiểm tra 8 quy tắc an toàn Python thuần và Pre-Gate |

---

## Phần nào thật, phần nào giả

| Thành phần | Thật / Giả | Ghi chú |
|---|---|---|
| Lời gọi AI Core (`codebase/ai.py`) | **Thật** | Model đo thật: `gemini-3.5-flash-lite` (lấy token thật từ `usageMetadata` của API) |
| Safety Guardrails & Tính giá (`codebase/tools.py`) | **Thật (Python thuần)** | 8 quy tắc kiểm tra an toàn + tính giá deterministic |
| Dữ liệu bệnh nhân & đơn giá (`data/processed/`) | **Giả lập (`synthetic`, `seed=42`)** | 100 ca tổng hợp hóa (0% PII); 83 thuốc đối chiếu Dược thư QG VN & `Bài LL 5`, giá giả lập bội số 500đ |

## Dùng AI vào việc gì

Nhóm dùng AI hỗ trợ viết script làm sạch/tổng hợp hóa dữ liệu (`seed=42`), triển khai khung code Python (`codebase/tools.py`, `codebase/agent.py`, `codebase/ai.py`) và rà soát tài liệu. Toàn bộ quy tắc an toàn, đối chiếu nguồn y khoa, phỏng vấn người dùng và chấm kiểm định đều do thành viên nhóm kiểm soát; chi tiết xem [docs/ai-usage.md](docs/ai-usage.md).
