# Data card — dữ liệu bản chạy thử dùng

> Điền ở guide bước 2.4 (bản đầu ở CP2, đủ ở CP3). Chấm ở rubric R4.
> Một trang. Không đưa dữ liệu cá nhân thật chưa ẩn danh vào prompt, bộ câu thử hay bản chạy thử.

## Dataset 1 · `drug_catalog_clean.json` (Danh mục thuốc đã xác minh — 83 thuốc)

| | |
|---|---|
| Dùng để làm gì | Nguồn cho `search_drug_catalog`, `validate_prescription` và `calculate_cost` |
| Từ đâu | Chuẩn hóa từ tập 100 toa ngoại trú ẩn danh (52 thuốc mạn tính cốt lõi `DRUG-001`–`DRUG-052`) và mở rộng thêm 31 thuốc ngoại trú thường gặp (`DRUG-053`–`DRUG-083`) đối chiếu từ tài liệu chuyên môn nội bộ và Dược thư Quốc gia VN |
| Xử lý những bước gì | Chuẩn hóa tên hoạt chất (`canonical_name`, `aliases`, `component_ingredients`), phân nhóm `drug_class`, bổ sung `verified_indications_icd10`, `contraindications`, `contraindication_tags`, `interactions` (`BLOCK`/`WARN`), `max_daily_dose`; chuẩn hóa `source_reference` về nguồn y khoa chuẩn (không trỏ file cục bộ); sinh giá giả lập bội số 500đ (`seed=42`, `price_is_synthetic: true`) |
| Số dòng / quy mô | **83 thuốc** chuẩn hóa (`DRUG-001`–`DRUG-083`), phủ 4 bệnh mạn tính (`I10`, `E78`, `E11`, `K21`) và các bệnh ngoại trú phổ biến (`J01`, `J02`, `J30`, `R05`, `A04`, `K59`, `M75`, `M54`, `M17`, `I83`, `B35`, `B02`, `J09`) |
| Nguồn đối chiếu & nhãn | `synthetic` (giá) + đối chiếu **Dược thư Quốc gia Việt Nam (2022)**, **Hướng dẫn Bộ Y tế (`kcb.vn`)**, và **Tài liệu chuyên môn Dược lý học (Bài LL 5 - Kháng nấm, Virus)** |
| Giới hạn | Giá thuốc là giá giả lập phục vụ mô phỏng (`price_is_synthetic: true`), không phải bảng giá thanh toán BHYT/nhà thuốc thật |

## Dataset 2 · `guidelines_clean.json` (Phác đồ & quy tắc chuyên môn — 17 phác đồ)

| | |
|---|---|
| Dùng để làm gì | Nguồn cho `search_guidelines` trích xuất thuốc đầu tay, phối hợp cần tránh và cờ cảnh báo đỏ |
| Từ đâu | Hướng dẫn chẩn đoán và điều trị Bộ Y tế (`kcb.vn`), Dược thư Quốc gia VN (2022), và Tài liệu chuyên môn Dược lý học (Bài LL 5 - Kháng nấm, Virus) |
| Xử lý những bước gì | Chuẩn hóa **17 phác đồ** (`BYT-I10-01`..`BYT-I83-01` bao gồm `BYT-K59-01`, cùng `BLL5-B35-01`, `BLL5-B02-01`, `BLL5-J09-01`); đồng bộ tên hoạt chất chuẩn khớp 100% `canonical_name` trong `drug_catalog_clean.json` và đặt `official_source_url` chuẩn (`https://kcb.vn/`) |
| Số dòng / quy mô | **17 phác đồ** chuẩn hóa |
| Nhãn | `thật` (tóm lược quy tắc chuyên môn công khai, không thay thế quyết định bác sĩ) |
| Giới hạn | Phác đồ tóm lược cho tuyến ngoại trú người lớn; các bệnh lý cấp cứu ngoại khoa (`ruột thừa`), nhi khoa, thai kỳ dọa sảy và ung thư nằm ngoài phạm vi và bị dừng đề xuất |

## Dataset 3 · `case_base_clean.json` (Kho ca lâm sàng giả lập — 62 ca người lớn trong phạm vi, 0% PII)

| | |
|---|---|
| Dùng để làm gì | Nguồn cho `retrieve_similar_cases` và trích xuất ca lâm sàng ẩn danh vào `eval/benchmark.csv` (`data_that`) |
| Từ đâu | Làm sạch và tổng hợp hóa từ tập 100 đơn thuốc ngoại trú gốc (639 dòng thô) |
| Xử lý những bước gì | Xóa tuyệt đối 33 cột PII/hành chính/thiếu dữ liệu nặng; nhiễu tổng hợp `age` (±1–2 tuổi) và `weight_kg` (±1 kg, `seed=42`); giữ `allergies="unknown"` khi thiếu để kiểm tra guardrail; **lọc bỏ hoàn toàn** ca nhi khoa (`<18` tuổi), ca trống chẩn đoán, ca cấp cứu (`Viêm ruột thừa cấp`), thai dọa sảy và ca ngoài 17 phác đồ xác minh; khớp chặt `drug_id` theo đúng tên hoạt chất + đường dùng (loại bỏ mọi map sai chuỗi con) |
| Số dòng / quy mô | **62 ca** người lớn trong phạm vi (`SYN-CASE-001`–`SYN-CASE-052` + 10 ca ngoại trú người lớn bổ sung), **215 lượt thuốc** gắn khóa ngoại `drug_id` chính xác sang `drug_catalog_clean.json` |
| Nhãn | `synthetic` (`is_synthetic: true`, `seed: 42`) |
| Kiểm định bảo mật | **PII Audit Regex PASSED** (`vn_phone_10_digits=0`, `cccd_12_digits=0`, `raw_prescription_code=0`, `pii_column_leak=0`, `0` map sai đường dùng/hoạt chất) |
