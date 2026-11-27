# Data card — dữ liệu bản chạy thử dùng

> Điền ở guide bước 2.4 (bản đầu ở CP2, đủ ở CP3). Chấm ở rubric R4.
> Một trang. Không đưa dữ liệu cá nhân thật chưa ẩn danh vào prompt, bộ câu thử hay bản chạy thử.

## Dataset 1 · `drug_catalog_clean.json` (Danh mục thuốc đã xác minh — 83 thuốc)

| | |
|---|---|
| Dùng để làm gì | Nguồn cho `search_drug_catalog`, `validate_prescription` và `calculate_cost` |
| Từ đâu | Chuẩn hóa từ `100_Toa_NVM_2026_Dataset.csv` (52 thuốc mạn tính cốt lõi `DRUG-001`–`DRUG-052`) và mở rộng thêm 31 thuốc ngoại trú thường gặp (`DRUG-053`–`DRUG-083`) từ `Data thường gặp.xlsx` và `Bài LL 5. Thuốc kháng nấm virus lao sốt rét.pdf` |
| Xử lý những bước gì | Chuẩn hóa tên hoạt chất (`canonical_name`, `aliases`, `component_ingredients`), phân nhóm `drug_class`, bổ sung `verified_indications_icd10`, `contraindications`, `contraindication_tags`, `interactions` (`BLOCK`/`WARN`), `max_daily_dose`; sinh giá giả lập bội số 500đ (`seed=42`, `price_is_synthetic: true`) |
| Số dòng / quy mô | 83 thuốc chuẩn hóa (`DRUG-001`–`DRUG-083`), phủ 4 bệnh mạn tính (`I10`, `E78`, `E11`, `K21`) và các bệnh ngoại trú phổ biến (`J01`, `J02`, `J30`, `R05`, `A04`, `K59`, `M75`, `M54`, `M17`, `I83`, `B35`, `B02`, `J09`) |
| Nguồn đối chiếu & nhãn | `synthetic` (giá) + đối chiếu Dược thư Quốc gia VN (2022) & Hướng dẫn Bộ Y tế (`kcb.vn`) |
| Giới hạn | Giá thuốc là giá giả lập phục vụ mô phỏng (`price_is_synthetic: true`), không phải bảng giá thanh toán BHYT/nhà thuốc thật |

## Dataset 2 · `guidelines_clean.json` (Phác đồ & quy tắc chuyên môn — 16 phác đồ)

| | |
|---|---|
| Dùng để làm gì | Nguồn cho `search_guidelines` trích xuất thuốc đầu tay, phối hợp cần tránh và cờ cảnh báo đỏ |
| Từ đâu | Hướng dẫn chẩn đoán và điều trị Bộ Y tế (`kcb.vn`), Dược thư Quốc gia VN (2022), và tài liệu `Bài LL 5. Thuốc kháng nấm virus lao sốt rét.pdf` |
| Xử lý những bước gì | Chuẩn hóa 16 entry theo `guideline_id` (`BYT-I10-01`..`BYT-I83-01`, `BLL5-B35-01`, `BLL5-B02-01`, `BLL5-J09-01`) với các trường `first_line_ingredients`, `avoid_combinations`, `safety_red_flags`, `missing_info_checks` |
| Số dòng / quy mô | 16 phác đồ chuẩn hóa |
| Nhãn | `thật` (tóm lược quy tắc chuyên môn công khai, không thay thế quyết định bác sĩ) |
| Giới hạn | Phác đồ tóm lược cho tuyến ngoại trú; các bệnh lý chuyên khoa sâu (như ung thư `C34`, cấp cứu, dọa sảy thai) nằm ngoài phạm vi và bị dừng đề xuất |

## Dataset 3 · `case_base_clean.json` (Kho ca lâm sàng giả lập — 100 ca, 0% PII)

| | |
|---|---|
| Dùng để làm gì | Nguồn cho `retrieve_similar_cases` và trích xuất ca lâm sàng ẩn danh vào `eval/benchmark.csv` (`data_that`) |
| Từ đâu | Làm sạch và tổng hợp hóa từ 100 đơn thuốc ngoại trú (`100_Toa_NVM_2026_Dataset.csv`, 639 dòng gốc) |
| Xử lý những bước gì | Xóa tuyệt đối 33 cột PII/hành chính/thiếu dữ liệu nặng (tên, SĐT, CCCD, BHYT, địa chỉ, tên bác sĩ/phòng khám, mã đơn `DT...`); nhiễu tổng hợp `age` (±1–2 tuổi) và `weight_kg` (±1 kg, `seed=42`); giữ `allergies="unknown"` khi thiếu để kiểm tra guardrail; liên kết khóa ngoại `drug_id` sang `drug_catalog_clean.json` (339 lượt thuốc khớp danh mục xác minh) |
| Số dòng / quy mô | 100 ca giả lập (`SYN-CASE-001`–`SYN-CASE-100`), 638 dòng thuốc sạch |
| Nhãn | `synthetic` (`is_synthetic: true`, `seed: 42`) |
| Kiểm định bảo mật | **PII Audit Regex PASSED** (`vn_phone_10_digits=0`, `cccd_12_digits=0`, `raw_prescription_code=0`, `pii_column_leak=0`) |
