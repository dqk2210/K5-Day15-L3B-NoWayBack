# AI SPEC — [Tên lát cắt] · Nhóm [tên nhóm] · Phòng [XXX] · Zone [X]

> Mốc nộp: §7 chốt chuẩn "đạt" tại **CP2 19:30 Thứ Sáu 27/11** · §0–§7 nộp **CP3 10:00 Thứ Bảy 28/11** · đủ §0–§10 **CP4 14:30 Thứ Bảy 28/11** · §10 changelog ghi tiếp đến **23:59 Thứ Bảy 28/11**.
> Đầu mỗi mục ghi bước guide (`02-guide.md` trong repo đề) chỉ cách điền. Mỗi mục ngắn, có số và nguồn; chi tiết để ở file được trỏ tới. Xoá dòng hướng dẫn trong ngoặc vuông khi điền xong.

Track: [ ] A · [ ] B · [ ] C · [ ] D · [ ] E — bài toán: [đề gợi ý trong file track, hoặc bài toán nhóm tự mở rộng] __
Data BTC cấp đã dùng (nếu có — không commit nguyên file): __

## §0. Hiện tại việc này diễn ra thế nào *(guide 1.1)*
- Luồng hiện tại của việc này, trong khoá hoặc trên app thật (3–5 bước; ảnh chụp từ tài khoản của mình, đã che thông tin):
- Công cụ / AI đang được dùng cho việc này (nếu có) + nguồn. Không kiểm được thì ghi "chưa kiểm":

## §1. Người dùng & bằng chứng *(guide 1.1, 1.2)*
- Người dùng chính (một vai cụ thể):
- Việc họ cố làm xong (`động từ + đối tượng + bối cảnh`, không có chữ AI):
- Hôm nay họ giải bằng gì, hỏng ở đâu, vì sao chưa bỏ:
- Pain (KHÔNG chữ AI): ai — đang làm gì — vướng đâu — hậu quả gì:
- Bằng chứng — số chính + kết luận (chi tiết: `evidence/summary.md`): __

## §2. Impact & quyết định chọn *(guide 1.3)*

| Hướng | Bao nhiêu người gặp | Bao nhiêu lần / tháng | Mỗi lần tốn gì | Impact / tháng | Làm kịp không | Chọn? |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |

- **Impact / tháng** của hướng chọn = __ người × __ lần × __ phút = __ — nguồn từng thừa số: __ (không có nguồn thì ghi rõ *(tự ước tính)*)
- Hướng ĐÃ LOẠI + vì sao (giữ lại, đừng xoá):
- Số lần / tháng của từng kiểu người dùng (dùng cho persona ở §8):

## §3. Giải pháp tương tự *(guide 2.1)*
- [sản phẩm / tính năng gần giống]: một điều đáng học · một điều đáng né · mình khác gì

## §4. Thiết kế *(guide 2.2, 3.2)*

- **Lát cắt MỘT CÂU:** Bác sĩ nhập chẩn đoán đã xác nhận và thông tin bệnh nhân, AI đề xuất phương án kê đơn dựa trên tài liệu chuyên môn và danh mục thuốc, hoặc báo thiếu căn cứ, để bác sĩ xem xét và quyết định.

- **Không làm:**
  - Không chẩn đoán bệnh từ triệu chứng.
  - Không tự động kê đơn hoặc phát hành đơn thuốc.
  - Không đề xuất thuốc ngoài danh mục đã xác minh.
  - Không tự suy diễn thông tin bệnh nhân còn thiếu.
  - Không thay thế quyết định chuyên môn của bác sĩ.

- **Sơ đồ kiến trúc AI:**

```text
┌───────────────────────────────────────────────┐
│                    INPUT                      │
│ Chẩn đoán, tuổi, cân nặng, chiều cao, bệnh nền,│
│ dị ứng và thuốc đang sử dụng                  │
└──────────────────────┬────────────────────────┘
                       ▼
┌───────────────────────────────────────────────┐
│       Kiểm tra và chuẩn hóa đầu vào           │
└──────────────────────┬────────────────────────┘
                       ▼
┌───────────────────────────────────────────────┐
│              DATA RETRIEVAL                   │
│                                               │
│  ├── Medical Knowledge Base: Phác đồ, slide   │
│  ├── Case Base: Đơn thuốc tham khảo           │
│  └── Drug Catalog: Danh mục thuốc             │
└──────────────────────┬────────────────────────┘
                       ▼
┌───────────────────────────────────────────────┐
│                   AI CORE                     │
│                                               │
│  LLM phân tích thông tin bệnh nhân, tài liệu  │
│  chuyên môn và danh mục thuốc để đề xuất      │
│  phương án kê đơn kèm căn cứ.                 │
└──────────────────────┬────────────────────────┘
                       ▼
┌───────────────────────────────────────────────┐
│              SAFETY GUARDRAILS                │
│                                               │
│  - Kiểm tra chống chỉ định, tương tác thuốc   │
│  - Kiểm tra liều lượng và hàm lượng           │
│  - Kiểm tra nguồn và thông tin còn thiếu      │
└───────────┬───────────────────────┬───────────┘
            │                       │
     Qua kiểm tra            Không đủ căn cứ
            ▼                       ▼
┌──────────────────────┐  ┌─────────────────────┐
│ Bản nháp đơn thuốc   │  │ Dừng đề xuất        │
│ Căn cứ và cảnh báo   │  │ Yêu cầu bổ sung     │
└───────────┬──────────┘  └─────────────────────┘
            ▼
┌───────────────────────────────────────────────┐
│          HUMAN-IN-THE-LOOP (HITL)             │
│              Bác sĩ kiểm duyệt                │
└───────────┬───────────────────────┬───────────┘
            │                       │
        Chấp nhận           Chỉnh sửa / Từ chối
            ▼                       ▼
┌──────────────────────┐  ┌─────────────────────┐
│ Tính giá bằng code   │  │ Kiểm tra lại hoặc   │
│ dựa trên bảng giá    │  │ kết thúc quy trình  │
└───────────┬──────────┘  └─────────────────────┘
            ▼
┌───────────────────────────────────────────────┐
│                    OUTPUT                     │
│                                               │
│  - Phương án kê đơn đã được bác sĩ duyệt      │
│  - Căn cứ chuyên môn và cảnh báo              │
│  - Tổng chi phí dự kiến                       │
│  - Bản mô phỏng, không phát hành đơn thật     │
└───────────────────────────────────────────────┘
```

- **Hình dạng:** [x] workflow cố định · [ ] một agent · [ ] nhiều agent.

  Quy trình truy xuất dữ liệu, đề xuất thuốc, kiểm tra rủi ro và kiểm duyệt có thứ tự xác định. Workflow cố định giúp kiểm soát đầu ra, dễ đánh giá và giảm chi phí; không cần agent tự lập kế hoạch hoặc nhiều agent phối hợp.

- **AI dựa vào đâu** — danh sách công cụ dự kiến triển khai trong `codebase/tools.py`:

| Công cụ | Input | Output | Tác động ra ngoài? |
|---|---|---|---|
| `search_guidelines` | Chẩn đoán, thông tin bệnh nhân | Đoạn tài liệu chuyên môn liên quan kèm nguồn | Không |
| `retrieve_similar_cases` | Chẩn đoán, đặc điểm bệnh nhân | Các đơn thuốc tham khảo giả lập tương tự | Không |
| `search_drug_catalog` | Dược chất, hàm lượng, dạng bào chế | Danh sách thuốc trong danh mục | Không |
| `validate_prescription` | Bản nháp đơn thuốc, thông tin bệnh nhân | Cảnh báo, vi phạm và điều kiện chưa kiểm chứng | Không |
| `calculate_cost` | Danh sách thuốc đã duyệt, số lượng | Chi phí từng thuốc và tổng chi phí dự kiến | Không |

- **Mức tự động:** [x] AI gợi ý, người quyết · [ ] AI tự làm khi chắc, chuyển người khi không · [ ] AI tự làm.

  Sai sót trong lựa chọn thuốc hoặc liều lượng có thể ảnh hưởng trực tiếp đến sức khỏe bệnh nhân. Vì vậy, AI chỉ hỗ trợ đề xuất có căn cứ; bác sĩ chịu trách nhiệm kiểm tra và quyết định.

- **Chỗ chặn rủi ro:** Safety Guardrails kiểm tra bản nháp dựa trên danh mục thuốc, nguồn chuyên môn và thông tin bệnh nhân. Nếu thiếu dữ liệu quan trọng, phát hiện chống chỉ định, tương tác hoặc không đủ căn cứ xác minh, hệ thống không cho hoàn tất đề xuất và yêu cầu bác sĩ kiểm tra lại. Không có dữ liệu kiểm chứng không đồng nghĩa với an toàn.

- **Chỗ người duyệt:** Bác sĩ kiểm tra từng thuốc, hàm lượng, liều dùng, tần suất, thời gian điều trị, căn cứ và cảnh báo trước khi xác nhận. AI không được tự phê duyệt hoặc phát hành đơn thuốc.

- **Nguyên tắc thiết kế:**

| Nguyên tắc | Chỗ cụ thể trên sơ đồ / trong bản chạy thử |
|---|---|
| G10 — thu hẹp phạm vi khi không chắc | Chỉ hỗ trợ các bệnh và thuốc có đủ nguồn chuyên môn đã xác minh; ngoài phạm vi hoặc thiếu căn cứ thì dừng đề xuất. |
| Grounding — dựa trên nguồn | AI Core truy xuất tài liệu y khoa và danh mục thuốc; mỗi đề xuất phải có căn cứ truy ngược được. |
| Human-in-the-loop | Bác sĩ kiểm duyệt bản nháp trước khi xuất kết quả. |
| Safety by design | Safety Guardrails kiểm tra các ràng buộc chuyên môn trước bước kiểm duyệt. |
| Deterministic computation | Tính chi phí bằng code và bảng giá, không để LLM tự sinh giá tiền. |

- **Phần nào còn giả:**
  - Hồ sơ bệnh nhân và đơn thuốc tham khảo sử dụng trong bản chạy thử là dữ liệu giả lập.
  - Giá thuốc và tồn kho được giả lập nếu chưa có nguồn thực tế.
  - Tài liệu chuyên môn và các quy tắc kiểm tra an toàn cần được xác minh trước khi đưa vào phạm vi hỗ trợ.
  - Bản chạy thử không kết nối với hệ thống bệnh viện hoặc nhà thuốc thật, không phát hành đơn thuốc thực tế.
  - AI Core được thiết kế để gọi LLM thật; trạng thái triển khai các công cụ cần được cập nhật theo code thực tế.

## §5. Chỗ khó — 4 lớp + ≥6 kịch bản + 2 tấn công *(guide 2.3)*

| Kịch bản | Lớp (1–4) | Hành vi mong muốn (nói gì, hiện gì, cho làm gì tiếp) | Câu thử |
|---|---|---|---|
|  |  |  |  |
| *(tấn công)* |  |  |  |
| *(tấn công)* |  |  |  |

(1) nguồn sự thật · (2) mơ hồ / thiếu thông tin · (3) ngoài phạm vi / thẩm quyền · (4) đặc thù lĩnh vực (sai thì người dùng mất gì đắt nhất)

## §6. Bốn đường đi của trải nghiệm
- Mọi thứ suôn sẻ: · Không chắc (lớp 2): · Không có căn cứ (lớp 1): · Người dùng sửa:
- Bị đòi ngoài phạm vi (lớp 3): · Trường hợp đặc thù lĩnh vực (lớp 4):

## §7. Đánh giá & chuẩn "đạt" *(guide 2.4, 4.1)*
- Data card: `data/DATA_CARD.md` · bộ câu thử: `eval/benchmark.csv` — 20 câu (thuong 10 · kho 7 · tu_choi 3) · metric: `eval/metric_spec.yaml` (4 metric)
- **Chuẩn "đạt"** (chốt **trước 19:30 Thứ Sáu 27/11**, giữ nguyên đến 23:59 Thứ Bảy 28/11): "Đạt khi >= 85% câu thuong qua cả metric căn cứ danh mục và cấu trúc bản nháp, >= 85% câu kho chặn rủi ro hoặc yêu cầu bổ sung đúng, và 100% câu tu_choi từ chối đúng phạm vi."
- Kết quả: lượt 1 __/__ (__%) · lượt 2 __/__ (__%) — run ID: __ / __ → chi tiết `eval/report.md`, hồ sơ `eval/README.md`

## §8. Chi phí khi dùng thật *(guide 4.2)*
- Persona + giá: `cost/personas.yaml` · lượt mô phỏng: `cost/simulate-__.csv` (__ phiên)
- Chi phí / task thành công: __ (model __) · __ (model __)
- Chi phí / tháng ở quy mô thật: thấp __ · cơ sở __ · cao __ → chi tiết `cost/cost-estimate.md`
- So với impact / người / tháng (§2): đáng làm không, vì sao:

## §9. Rủi ro & an toàn
- Dữ liệu: đã ẩn danh gì, không thu gì, không đưa gì vào model gói miễn phí:
- AI **không được** làm gì kể cả khi người dùng yêu cầu:
- Ai có thể bị hại nếu AI sai, và nhóm chặn thế nào:

## §10. Phân công & changelog
- Phân công có tên (theo chặng, chia cặp — guide "Cách chia việc"): __
- Dùng AI vào việc gì (2–3 dòng; chi tiết `docs/ai-usage.md`):
- Nhật ký thay đổi — **mọi thay đổi sau CP2 19:30 Thứ Sáu 27/11 phải có dòng ở đây**:

**CP2 → CP4** (vd thu hẹp lát cắt, hỏi thêm người dùng, lần cải tiến trước lượt 2)

| Thời điểm | Đổi gì | Vì sao (trỏ về câu thử / lỗi / bằng chứng nào) |
|---|---|---|
|  |  |  |

**Sau CP4 (đến 23:59 Thứ Bảy 28/11)** (sửa theo góp ý — không sửa chuẩn "đạt", câu thử, số bằng chứng, kết quả các lượt đã chạy)

| Thời điểm | Đổi gì | Vì sao |
|---|---|---|
|  |  |  |
