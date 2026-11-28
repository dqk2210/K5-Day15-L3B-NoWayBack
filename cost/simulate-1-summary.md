# Tóm tắt mô phỏng simulate-1@20261128-075540

Do `python run.py simulate` sinh ra — không sửa tay. Chép bảng sang `cost/cost-estimate.md`.

| Persona | Số phiên mô phỏng | Lượt hỏi / phiên | Token vào / phiên | Token ra / phiên | Gọi model / phiên | Gọi công cụ / phiên |
|---|---:|---:|---:|---:|---:|---:|
| bac_si_phong_kham_nho | 18 | 1 | 3128 | 451 | 0.8 | 5.3 |
| bac_si_noi_tong_quat | 24 | 1 | 3555 | 595 | 0.9 | 5.5 |
| bac_si_chuyen_khoa_dong_benh | 6 | 2 | 5664 | 923 | 1.5 | 9.5 |

Tỉ lệ đạt dùng để tính: 19/20 (95%) — lượt run-2@20261128-075436

- Tỉ lệ đạt lấy từ lượt nhóm chọn: eval/run-2.csv (--rate-from).

| Model (giá) | Chi phí / phiên | Chi phí / task thành công | Chi phí / câu hỏi đạt | Chi phí / tháng — thấp (5 người) | Chi phí / tháng — cơ sở (30 người) | Chi phí / tháng — cao (150 người) | Chi phí / người / tháng (cơ sở) |
|---|---:|---:|---:|---:|---:|---:|---:|
| gemini-3.1-flash-lite (vào 0.25 · ra 1.5 $/1M) | $0.0018 (≈ 45 ₫) | $0.0019 (≈ 48 ₫) | $0.0017 (≈ 42 ₫) | $1.32 (≈ 33.443 ₫) | $7.90 (≈ 200.658 ₫) | $39.50 (≈ 1.003.289 ₫) | $0.2633 (≈ 6.689 ₫) |
| gemini-4-hydrogen (vào 1.5 · ra 7.5 $/1M) | $0.0099 (≈ 250 ₫) | $0.0104 (≈ 263 ₫) | $0.0092 (≈ 234 ₫) | $7.25 (≈ 184.212 ₫) | $43.51 (≈ 1.105.270 ₫) | $217.57 (≈ 5.526.348 ₫) | $1.45 (≈ 36.842 ₫) |

- Chi phí / task thành công = chi phí / phiên ÷ tỉ lệ đạt. Chi phí / câu hỏi đạt = chi phí / phiên ÷ số lượt hỏi trung bình mỗi phiên (1.1) ÷ tỉ lệ đạt — tỉ lệ đạt đo theo từng câu thử.
- Token đo trên model: gemini-3.5-flash-lite. Giá tính theo từng model trong bảng — model khác bộ tách token thì số token thật có thể lệch; ghi rõ "đo trên model X, tính giá model Y" trong cost/cost-estimate.md.
- Phiên lỗi (không tính vào trung bình): 2/50.
- Tỷ giá: 1 USD = 25.400 ₫ (Tỷ giá tham khảo Vietcombank (tự ước tính quy đổi) · xem 28/11/2026).
