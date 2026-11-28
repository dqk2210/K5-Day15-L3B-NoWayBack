# Chi phí khi dùng thật

> Chấm ở rubric R6. Mọi số liệu đo trực tiếp từ `python run.py simulate --rate-from eval/run-2.csv --wait 1` (50 phiên, `seed=42`).

## 1. Đầu vào

- **Persona** ([personas.yaml](cost/personas.yaml)): 3 kiểu bác sĩ *(tự ước tính)* — `bac_si_phong_kham_nho` (50%, 60 ca/tháng, 1 lượt/phiên), `bac_si_noi_tong_quat` (35%, 150 ca/tháng, 1 lượt/phiên), `bac_si_chuyen_khoa_dong_benh` (15%, 300 ca/tháng, 2 lượt/phiên).
- **Số người dùng thật** 3 kịch bản *(tự ước tính)*: thấp **5 bác sĩ** (1 phòng khám nội khoa) · cơ sở **30 bác sĩ** (1 bệnh viện tuyến quận/huyện) · cao **150 bác sĩ** (chuỗi phòng khám/bệnh viện lớn).
- **Giá 2 mức model** (nguồn: `https://ai.google.dev/gemini-api/docs/pricing` · xem 25/11/2026, USD / 1M token):
  - `gemini-3.1-flash-lite`: Input `$0.25` · Output `$1.50` · Cache `$0.025`
  - `gemini-4-hydrogen`: Input `$1.50` · Output `$7.50` · Cache `$0.075`
- **Tỉ lệ đạt dùng để tính:** `19/20` (`95%`) — lượt `run-2@20261128-075436` ([run-2.csv](../eval/run-2.csv)).
- **Lưu ý đo lường:** **Đo token trên model `gemini-3.5-flash-lite`, tính giá theo 2 mức model `gemini-3.1-flash-lite` và `gemini-4-hydrogen`.** Tỷ giá tham khảo: `1 USD = 25.400 ₫` *(tự ước tính quy đổi · xem 28/11/2026)*.

## 2. Kết quả mô phỏng

Lượt mô phỏng: [simulate-1.csv](cost/simulate-1.csv) · Run ID: `simulate-1@20261128-075540` · **50 phiên** (`seed=42`, 2 phiên lỗi `S018`, `S034` không tính vào trung bình) · trace: `traces/simulate-1.jsonl`.

| Persona | Số phiên mô phỏng | Lượt hỏi / phiên | Token vào / phiên | Token ra / phiên | Gọi model / phiên | Gọi công cụ / phiên |
|---|---:|---:|---:|---:|---:|---:|
| `bac_si_phong_kham_nho` | 18 | 1 | 3128 | 451 | 0.8 | 5.3 |
| `bac_si_noi_tong_quat` | 24 | 1 | 3555 | 595 | 0.9 | 5.5 |
| `bac_si_chuyen_khoa_dong_benh` | 6 | 2 | 5664 | 923 | 1.5 | 9.5 |

| Model (giá) | Chi phí / phiên | Chi phí / task thành công | Chi phí / câu hỏi đạt | Chi phí / tháng — thấp (5 người) | Chi phí / tháng — cơ sở (30 người) | Chi phí / tháng — cao (150 người) | Chi phí / người / tháng (cơ sở) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gemini-3.1-flash-lite` (vào 0.25 · ra 1.5 $/1M) | $0.0018 (≈ 45 ₫) | $0.0019 (≈ 48 ₫) | $0.0017 (≈ 42 ₫) | $1.32 (≈ 33.443 ₫) | $7.90 (≈ 200.658 ₫) | $39.50 (≈ 1.003.289 ₫) | $0.2633 (≈ 6.689 ₫) |
| `gemini-4-hydrogen` (vào 1.5 · ra 7.5 $/1M) | $0.0099 (≈ 250 ₫) | $0.0104 (≈ 263 ₫) | $0.0092 (≈ 234 ₫) | $7.25 (≈ 184.212 ₫) | $43.51 (≈ 1.105.270 ₫) | $217.57 (≈ 5.526.348 ₫) | $1.45 (≈ 36.842 ₫) |

*(Công thức: Chi phí / task thành công = chi phí trung bình mỗi phiên `$0.0018` ÷ tỉ lệ đạt `0.95` = `$0.0019` — không coi như đạt 100%.)*

## 3. So với impact

- **Impact / người / tháng (`spec.md` §2):** Trung bình ~128 ca/tháng/bác sĩ *(theo tỷ trọng 3 persona)* — mỗi ca tiết kiệm ~1–2 phút tra cứu tương tác/liều (~2–4 giờ/tháng) và giảm rủi ro bỏ sót chống chỉ định/tương tác mức `BLOCK` (`[HUMAN_FILL: cập nhật phút đo thật từ phỏng vấn]`).
- **Chi phí / người / tháng (cơ sở, model `gemini-3.1-flash-lite`):** **$0.2633 / bác sĩ / tháng (≈ 6.689 ₫/tháng)** — tức chỉ khoảng **48 ₫ / task thành công**.
- **Kết luận một dòng — đáng làm không:** **GO** — chi phí chỉ ~6.689 ₫/bác sĩ/tháng (~48 ₫/task thành công) với độ chính xác đạt 19/20 (95% ở Lượt 2, 100% ca `kho` và `tu_choi`), cực kỳ xứng đáng so với thời gian tra cứu tiết kiệm được và rủi ro tương tác thuốc được chặn sớm.

## 4. Phân tích độ nhạy & chi phí ngoài model *(Tie-breaker)*

| Cần gạt tối ưu | Tác động ước tính lên chi phí (`gemini-3.1-flash-lite`) | Ghi chú triển khai |
|---|---|---|
| **Baseline hiện tại (`top_k=2`, không cache)** | $0.0018 / phiên ($0.0019 / task thành công, ~6.689 ₫/BS/tháng) | Token vào ~3.6k/phiên, 0.9 lần gọi model/phiên |
| **Bật Prompt Caching** (cố định System Prompt + danh mục 83 thuốc ở prefix, giá cache `$0.025/1M` = giảm 90% phần input cache) | Giảm ~45–55% chi phí input → còn **~$0.0013 / phiên** *(tự ước tính)* | Phù hợp khi số lượng thuốc mở rộng >200 thuốc |
| **Cắt ngữ cảnh (`top_k=1` ca tham khảo, chỉ gửi 15 thuốc khớp nhất)** | Giảm ~25–30% token vào → còn **~$0.0015 / phiên** *(tự ước tính)* | Giảm tải prompt mà vẫn giữ nguyên lớp chặn Python |
| **Chi phí ngoài model** | Hosting Python API nhẹ + lưu trữ JSON/log cục bộ (~$5–15/tháng cho cả phòng khám 30 BS) *(tự ước tính)* | Không cần GPU; mọi rule kiểm tra chạy CPU Python thuần |
