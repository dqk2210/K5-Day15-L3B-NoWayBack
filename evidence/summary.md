# Bằng chứng CP3 về rà soát đơn ngoại trú

**Nguồn:** Đào dữ liệu BTC từ 52 ca có nguồn gốc từ đơn ngoại trú, đã được làm sạch và ẩn danh. Phép đếm dùng các trường chẩn đoán và dòng thuốc. Các trường nhân khẩu học tổng hợp và 10 ca mở rộng nằm ngoài mẫu. [Cách đếm và nguồn](data-mining.md)

- **46/52 ca (88,5%)** có từ hai nhóm ICD-10 và từ năm dòng thuốc trở lên. Người rà soát cần đối chiếu nhiều dòng thuốc và chẩn đoán trong cùng một đơn.
- **301/364 dòng (82,7%)** có trường thời gian điều trị dạng số trống. **118/364 (32,4%)** có trường số lần dùng mỗi ngày dạng số trống. Hướng dẫn bằng văn bản có nhiều cách ghi nên đây là số đo khả năng chuẩn hóa của bộ dữ liệu.
- Kết quả phù hợp với việc tổ chức bản nháp để bác sĩ rà từng dòng. Thời gian tra cứu, nguyên nhân sai sót, lợi ích về tốc độ và giả thuyết riêng về dược sĩ bán OTC vẫn cần đo trực tiếp. [Giả thuyết ban đầu](hypothesis.md)

## Năm trích đoạn nguyên văn đã ẩn danh

Trích từ trường `usage_instruction_full` **sau khi làm sạch**. Mã ca và số dòng dùng để đối chiếu với dữ liệu ẩn danh.

| Ca, dòng thuốc | Trích nguyên văn |
|---|---|
| `SYN-CASE-001`, dòng 1 | “7 ngày - Ngày 2 lần : Sáng: 1 Viên; Chiều: 1 Viên” |
| `SYN-CASE-002`, dòng 1 | “Ngày uống 1/2 viên buổi chiều (sau ăn)” |
| `SYN-CASE-003`, dòng 1 | “14 ngày - Ngày 3 lần : Sáng: 1 Viên; Chiều: 1 Viên; Tối: 1 Viên” |
| `SYN-CASE-004`, dòng 1 | “Uống Sáng: 1 viên khi thức dậy” |
| `SYN-CASE-009`, dòng 1 | “Uống, Sáng: 01 Viên Chiều: 01 Viên Trước ăn 30 phút” |

[Dữ liệu đã xử lý](../data/processed/case_base_clean.json) · [Data card](../data/DATA_CARD.md)
