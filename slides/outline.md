# Dàn slide → lấy số từ file nào

> Luật: **không có bằng chứng thì không có slide** — mỗi trang ≥1 con số / trích dẫn có nguồn / kết quả đo.

| # | Trang | Có gì | Số lấy từ | Xong |
|---|---|---|---|---|
| 1 | Người dùng & pain | Bác sĩ khám ngoại trú — vướng tra thủ công tương tác/chống chỉ định — `[HUMAN_FILL: số liệu & trích dẫn nguyên văn]` | `evidence/summary.md` | ☐ |
| 2 | Vì sao chọn bài này | Bảng impact rút gọn (`[HUMAN_FILL]`) + hướng bị loại (tự chẩn đoán, chuyên khoa ung thư) | `spec.md` §2 | ☐ |
| 3 | Giải pháp | Lát cắt 1 câu · sơ đồ workflow 6 bước · 8 quy tắc Safety Guardrails Python thuần · HITL | `spec.md` §4 | ☑ |
| 4 | Demo live | 1 ca thường (`T01` hoặc `T10`) + 1 ca khó (`K06` dị ứng NSAID + Warfarin) + 1 tấn công (`R02`) | `eval/benchmark.csv` | ☑ |
| 5 | **Đánh giá thế nào** | 83 thuốc · 17 phác đồ · 62 ca người lớn sạch · 20 câu thử · **Lượt 1: 16/20 (80%) → Lượt 2: 19/20 (95%)** (`run-1@20261128-004906` → `run-2@20261128-075436`), lỗi còn lại `T04` | `eval/README.md`, `eval/report.md` | ☑ |
| 6 | **Chi phí khi dùng thật** | **$0.0019 (≈48đ)/task thành công** · 3 kịch bản (`$1.32` / `$7.90` / `$39.50`/tháng với `gemini-3.1-flash-lite`) · **$0.2633 (≈6.689đ)/BS/tháng** | `cost/cost-estimate.md` | ☑ |
| 7 | Kết luận | **GO** — 95% đạt chuẩn Lượt 2 (100% `kho` & `tu_choi`) + ~48đ/task (~6.689đ/BS/tháng) + `[HUMAN_FILL: số pain trang 1]` | `spec.md`, `eval/`, `cost/` | ☑ |
| 8 | Nếu có thêm 1 tuần | Tách `package_size` khỏi `strength_dosage` cho thuốc bôi (`T04`), bảng chỉnh liều theo `eGFR` (`K04`), bật Prompt Caching | `eval/report.md`, `cost/cost-estimate.md` | ☑ |

Ai nói trang nào (mỗi người ≥1 phần):

| Trang | Người nói |
|---|---|
| 1–2 | Võ Thị Phương Nhung |
| 3–4 | Đỗ Quốc Khánh & Nguyễn Tiến Đạt |
| 5–6 | Mai Lê Bá Vương & Võ Thị Phương Nhung |
| 7–8 | Đỗ Quốc Khánh |
