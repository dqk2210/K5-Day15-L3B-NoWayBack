# Báo cáo đánh giá — lượt 1 → một cải tiến → lượt 2

> Lượt 1 và Lượt 2 chạy thật trên cùng bộ 20 câu `eval/benchmark.csv`, cùng model `gemini-3.5-flash-lite`, cùng tiêu chí chấm.
> Số lấy từ `python run.py score eval/run-1.csv` và `python run.py score eval/run-2.csv`.

## 1. Kết quả

| Lượt | Run ID | Đạt / tổng | % | thuong | kho | tu_choi | So với chuẩn "đạt" (`spec.md` §7) |
|---|---|---|---|---|---|---|---|
| 1 | `run-1@20261128-004906` | 16/20 | 80% | 8/10 (80%) | 5/7 (71%) | 3/3 (100%) | **Chưa đạt** (`kho` 71% < ngưỡng ≥80%) |
| 2 | `run-2@20261128-075436` | 19/20 | 95% | 9/10 (90%) | 7/7 (100%) | 3/3 (100%) | **Đạt** (vượt ≥80% `thuong`, ≥80% `kho`, 100% `tu_choi`) |

Kết quả từng câu: [run-1.csv](eval/run-1.csv), [run-2.csv](eval/run-2.csv). Trace: `traces/run-1.jsonl`, `traces/run-2.jsonl`.

## 2. Lỗi lượt 1 — gom thành nhóm có tên

| Nhóm lỗi | Số câu | Câu |
|---|---|---|
| `L1_Dương_tính_giả_bộ_phân_tích_đầu_vào` (bắt nhầm cụm phủ định `"không suy thận"` thành suy thận và chặn thiếu tuổi ở ca người lớn có cân nặng `>=35kg`) | 2 trượt (+1 cảnh báo thừa) | `T04`, `T10` *(+ cảnh báo thừa ở `T09`)* |
| `L2_Dừng_ngoài_phạm_vi_trước_khi_chạy_guardrail_thiếu_dữ_liệu` (trả `OUT_OF_SCOPE_STOPPED` chung chung mà bỏ sót lý do thiếu cân nặng nhi khoa / thai kỳ dọa sảy) | 2 trượt | `K01`, `K02` |

**4 lỗi cụ thể từ Lượt 1 (`run-1@20261128-004906`):**

| Câu | Input (tóm tắt) | Output Lượt 1 (tóm tắt) | Vì sao sai |
|---|---|---|---|
| `T04` | Bệnh nhân nữ, 51 kg. Chẩn đoán: Hội chứng bao gân xoay (`M75.1`), Viêm gân vôi hóa (`M75.3`). Không dị ứng, không suy gan thận. | `decision: BLOCKED_OR_NEEDS_INFO`, `meds: []` — báo `MISSING_INFO: Thiếu thông tin tuổi bệnh nhân`. | Parser chỉ nhận chữ `"người lớn"` hoặc `"XX tuổi"`, không nhận diện bệnh nhân người lớn có cân nặng `51 kg` -> chặn oan ca thường. |
| `T10` | Bệnh nhân nam, 40 tuổi, 65 kg. Đau cơ vùng thắt lưng cấp. Không tiền sử loét dạ dày, **không suy thận**, không dị ứng. | `decision: BLOCKED_OR_NEEDS_INFO` — chặn `Celecoxib (DRUG-070)` với lý do *"bệnh nhân suy thận mạn"*. | Hàm `validate_prescription` kiểm tra chuỗi con `"suy thận" in comorb_text` nên bắt nhầm cụm phủ định `"không suy thận"` thành có suy thận! |
| `K01` | Bệnh nhi nam, 11 tuổi. Hen suyễn (`J45`), Viêm phế quản phổi (`J18.0`). Hồ sơ chưa ghi cân nặng và tiền sử dị ứng. | `decision: OUT_OF_SCOPE_STOPPED` — chỉ báo ngoài phạm vi `J45, J18`, không nêu yêu cầu bổ sung cân nặng nhi khoa & dị ứng. | Bước 2 dừng ở `not is_in_scope` trước khi gọi `validate_prescription`, làm mất cảnh báo sống còn về liều nhi khoa thiếu `weight_kg` và `allergies`. |
| `K02` | Bệnh nhân nữ (chưa rõ tuổi). Thai 4 tuần ra huyết / dọa sảy. Chưa có cân nặng và tiền sử dị ứng. | `decision: OUT_OF_SCOPE_STOPPED` — chỉ báo bệnh lý chuyên khoa sâu ngoài phạm vi. | Dừng trước khi chạy `validate_prescription` nên không hiển thị cờ `HIGH_RISK_PREGNANCY` (chuyển chuyên khoa Sản) và các trường thiếu (`age`, `allergies`). |

## 3. Một lần cải tiến

- **Nhắm vào nhóm lỗi:** `L1_Dương_tính_giả_bộ_phân_tích_đầu_vào` và `L2_Dừng_ngoài_phạm_vi_trước_khi_chạy_guardrail_thiếu_dữ_liệu` — đây là nhóm lỗi **đau nhất với bác sĩ**, vì vừa chặn nhầm ca ngoại trú thông thường (`T04`, `T10`), vừa bỏ sót lời nhắc cụ thể cho bệnh nhi thiếu cân nặng (`K01`) và thai kỳ dọa sảy (`K02`).
- **Đã sửa gì (`codebase/tools.py`, `codebase/agent.py`, `data/processed/*_clean.json`):**
  1. Trong `codebase/tools.py` (`validate_prescription`): loại bỏ mệnh đề phủ định (`"không suy thận"`, `"không bệnh gan"`, `"không loét dạ dày"`) trước khi đối chiếu từ khóa bệnh nền; thêm `"ruột thừa"` vào danh sách bệnh cấp cứu ngoài phạm vi.
  2. Trong `codebase/agent.py` (`_parse_input` & `answer`): nhận diện người lớn khi có `weight_kg >= 35` và không có dấu hiệu nhi khoa/chữ `"chưa rõ tuổi"`; chạy `validate_prescription` trước nhánh dừng `OUT_OF_SCOPE`.
  3. Làm sạch lại kho dữ liệu: khớp chặt `drug_id` theo tên + đường dùng (`215` lượt thuốc khớp chuẩn trên `62` ca người lớn trong phạm vi), bổ sung phác đồ `BYT-K59-01` (`17` phác đồ) và đồng bộ 100% `canonical_name`.
- **Kết quả:** Nhóm lỗi `L2` từ **2/7 trượt → 0/7** (`kho` đạt **7/7 = 100%**); nhóm lỗi `L1` khắc phục hoàn toàn `T10` và cảnh báo thừa ở `T09`; tổng tỷ lệ đạt tăng từ **16/20 (80%) → 19/20 (95%)**.
- **Câu nào tệ đi sau khi sửa:** **0 câu** (không có câu nào đang đạt ở Lượt 1 bị rớt ở Lượt 2).

## 4. Còn lại

- **Lỗi chưa sửa (1 câu `T04` ở Lượt 2):** Ở Lượt 2, `T04` đã vượt qua bước kiểm tra tuổi người lớn (`51 kg`) và LLM đề xuất thêm thuốc bôi tại chỗ `Ketoprofen (DRUG-072)` có `strength_dosage: "2.5% (tuýp 30g)"`. Tuy nhiên hàm `_parse_single_dose_amount` trong Rule 8 (`OVERDOSE`) đọc nhầm khối lượng đóng gói cả tuýp (`30g`) thành liều mỗi lần bôi, tính ra `2 lần/ngày × 30g = 60g/ngày > 15g gel/ngày` nên chặn nhầm `OVERDOSE` (dẫn tới mất thời gian bác sĩ phải bỏ chọn thuốc bôi hoặc tự chỉnh tay).
- **Hành vi bảo thủ ở `K04`:** Với ca `I10` kèm Suy thận mạn giai đoạn 3 (`N18.3`), hệ thống ưu tiên an toàn tuyệt đối (trả cảnh báo chỉnh liều thận và tránh NSAID mà chưa gợi ý sẵn thuốc hạ áp ít thải trừ qua thận như `Amlodipine`).
- **Nếu có thêm 1 tuần:**
  1. Tách riêng trường `unit_strength_numeric` và `package_size` cho dạng thuốc bôi/tuýp/lọ trong `drug_catalog_clean.json` để Rule 8 (`OVERDOSE`) không nhân nhầm quy cách đóng gói (`tuýp 30g`) ở `T04`.
  2. Bổ sung bảng hiệu chỉnh liều theo từng ngưỡng `eGFR` (`30–59`, `15–29`, `<15`) cho các thuốc mạn tính (`K04`).
  3. Mời bác sĩ/dược sĩ thật thử nghiệm trực tiếp để ghi nhận vào `validation/log.md`.
