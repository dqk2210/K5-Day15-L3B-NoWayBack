# Báo cáo đánh giá

## Lượt 1 · CP3

| Run ID | Model | Đạt / tổng | Thường | Khó | Từ chối | So với chuẩn §7 |
|---|---|---:|---:|---:|---:|---|
| `run-1@20261128-004906` | `gemini-3.5-flash-lite` | **16/20 (80%)** | 8/10 (80%) | 5/7 (71%) | 3/3 (100%) | Chưa đạt ngưỡng nhóm khó |

Điểm lấy từ `python run.py score eval/run-1.csv` trên cột `pass` đã lưu. Trace ghi 12 lần gọi model, tổng 52.610 token vào và 6.682 token ra. Các ca dừng ở cổng kiểm tra có thể kết thúc trước khi gọi model. [CSV](run-1.csv) · [Trace](../traces/run-1.jsonl) · [Spec](../spec.md)

## Các câu trượt trong Lượt 1

| Câu | Quan sát từ kết quả đã lưu |
|---|---|
| T04 | Thiếu tuổi khiến hệ thống dừng trước khi lập bản nháp, trong khi tiêu chí ca thường yêu cầu đầu ra hợp lệ. |
| T10 | Đầu vào ghi “không suy thận” nhưng kết quả cảnh báo suy thận mạn và chặn bản nháp. |
| K01 | Cảnh báo ngoài phạm vi bỏ sót hai trường thiếu là cân nặng và dị ứng. |
| K02 | Cảnh báo ngoài phạm vi bỏ sót cờ nguy cơ cao của thai kỳ ra huyết. |

## Lượt 2 · CP4

Chưa có kết quả Lượt 2. Khi thực hiện CP4, ghi cải tiến và đối chiếu hai lượt với cùng bộ câu thử và cùng tiêu chí chấm.
