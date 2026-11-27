# Data card — dữ liệu bản chạy thử dùng

> Điền ở guide bước 2.4 (bản đầu ở CP2, đủ ở CP3). Ôn lại: ngày 6 · lab ngày 6. Chấm ở rubric R4.
> Một trang. Mỗi dataset một mục. Không đưa dữ liệu cá nhân thật chưa ẩn danh vào prompt, bộ câu thử hay bản chạy thử.

## Dataset 1 · `100_Toa_NVM_2026_Dataset.csv` (Case Base — 100 đơn thuốc tham khảo)

| | |
|---|---|
| Dùng để làm gì | Nguồn cho công cụ `retrieve_similar_cases` và trích xuất ca lâm sàng **đã ẩn danh** vào `eval/benchmark.csv` (`data_that`) |
| Từ đâu | Tập dữ liệu 100 đơn thuốc ngoại trú nhóm tổng hợp (`100_Toa_NVM_2026_Dataset.csv`, cập nhật trang 1–25 từ `V1.xlsx` và trang 51–75 từ `V2.xlsx`, giữ nguyên trang 26–50 và 76–100) |
| Xử lý những bước gì | Hợp nhất bản chỉnh sửa V1/V2 giữ nguyên định dạng ngày/giờ/số; **ẩn danh hoàn toàn** (loại bỏ họ tên, SĐT, CCCD, số thẻ BHYT, địa chỉ, tên bác sĩ, tên cơ sở y tế) trước khi đưa vào `eval/benchmark.csv` |
| Số dòng / số đoạn | 639 dòng thuốc thuộc 100 đơn (`page_number` 1–100), 56 cột |
| Phiên bản / ngày lấy | Cập nhật 27/11/2026 |
| Nhãn | `thật` (ẩn danh khi sử dụng trong benchmark và demo) |
| Giới hạn | Một số đơn còn thiếu trường `patient_age`, `weight_kg`, `allergies` (`null`) hoặc `icd10_codes`; chỉ phản ánh một tập đơn ngoại trú nhất định, không dùng thay phác đồ chuẩn |

## Dataset 2 · `Data thường gặp.xlsx` & `Data thi dược.xlsx` (Drug Catalog — Danh mục thuốc)

| | |
|---|---|
| Dùng để làm gì | Nguồn cho công cụ `search_drug_catalog` để tra dược chất, hàm lượng, dạng bào chế, biệt dược tương đương |
| Từ đâu | Hai bảng danh mục thuốc nhóm chuẩn bị trong `data/` (`Data thường gặp.xlsx`, `Data thi dược.xlsx`) |
| Xử lý những bước gì | Đọc và chuẩn hóa các cột `Nhóm dược lý`, `Dược chất`, `Hàm lượng`, `Dạng bào chế`, `Biệt dược` |
| Số dòng / số đoạn | `Data thường gặp.xlsx`: 128 dòng thuốc; `Data thi dược.xlsx`: 451 dòng thuốc |
| Phiên bản / ngày lấy | 27/11/2026 |
| Nhãn | `thật` (danh mục thuốc tham chiếu) |
| Giới hạn | Chưa có cột đơn giá và tồn kho thực tế theo cơ sở (cột giá dùng cho `calculate_cost` cần bảng giá giả lập hoặc bổ sung riêng) |

## Dataset 3 · `Bài LL 5. Thuốc kháng nấm virus lao sốt rét.pdf` & Bộ câu thử `eval/benchmark.csv`

| | |
|---|---|
| Dùng để làm gì | Nguồn tài liệu chuyên môn cho `search_guidelines` và bộ 20 câu thử đánh giá hệ thống (`eval/benchmark.csv`) |
| Từ đâu | Tài liệu chuyên môn PDF trong `data/` + 10 ca lâm sàng ẩn danh từ Dataset 1/Dataset 2 (`data_that`) + 10 ca biên/tấn công nhóm tự viết (`tu_viet`) |
| Xử lý những bước gì | Trích xuất ca bệnh ẩn danh theo lưới thông tin (bệnh lý đơn giản, thiếu dữ liệu, đa bệnh lý/thai kỳ/suy thận, tấn công vượt phạm vi); kiểm tra bằng `python run.py check` |
| Số dòng / số đoạn | 1 tài liệu PDF chuyên môn + 20 câu thử (10 `thuong`, 7 `kho`, 3 `tu_choi` gồm 2 câu tấn công) |
| Phiên bản / ngày lấy | 27/11/2026 |
| Nhãn | `thật` (tài liệu + ca ẩn danh) và `tu_viet` (ca biên/tấn công) |
| Giới hạn | Tài liệu PDF hiện có mới phủ nhóm thuốc kháng nấm, virus, lao, sốt rét; các nhóm bệnh khác cần bổ sung phác đồ chuẩn để AI không bị thiếu căn cứ |
