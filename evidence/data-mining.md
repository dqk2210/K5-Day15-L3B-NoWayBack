# Đào dữ liệu đơn ngoại trú

## Cách đếm

- Chọn `SYN-CASE-001` đến `SYN-CASE-052` trong `case_base_clean.json`, có nguồn gốc từ 100 đơn ngoại trú BTC cấp. Phép đếm bỏ qua nhân khẩu học tổng hợp và 10 ca bổ sung. [Data card](../data/DATA_CARD.md)
- Một nhóm chẩn đoán là ba ký tự đầu của mã ICD-10, đếm duy nhất trong từng ca. Mẫu số theo ca là 52.
- Một dòng thuốc là một phần tử trong `medications`, kể cả dòng chưa ghép được danh mục. Mẫu số theo dòng là 364. Với hai cột cấu trúc, đếm giá trị JSON `null` hoặc trường vắng mặt.
- Chạy `python evidence/count.py` để tính lại các tỷ lệ và kiểm tra năm đoạn đã trích.

## Kết quả

| Chỉ số | x/N | Tỷ lệ |
|---|---:|---:|
| Ca có từ hai nhóm ICD-10 | 46/52 | 88,5% |
| Ca có từ hai nhóm ICD-10 và từ năm dòng thuốc | 46/52 | 88,5% |
| Dòng thuốc có `duration_days` trống | 301/364 | 82,7% |
| Dòng thuốc có `frequency_per_day` trống | 118/364 | 32,4% |

Các đoạn sau làm sạch cho thấy cùng một loại thông tin có thể xuất hiện dưới dạng số lần, buổi trong ngày, phân số viên hoặc ghi chú trước hay sau ăn. [Năm trích đoạn](summary.md)

## Giới hạn

Mẫu được lọc theo phạm vi hỗ trợ của bản chạy thử. Tỷ lệ mô tả 52 ca trong tập này. Giá trị trống trong cột cấu trúc có thể xuất phát từ cách viết văn bản hoặc bước trích xuất. Dữ liệu chưa đo thời gian thao tác của bác sĩ hay kết quả đối với người bệnh.
