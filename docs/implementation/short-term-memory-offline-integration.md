# Short-term Memory P3 · Tích hợp và đánh giá ngoại tuyến

[`build_offline_context()`](../../backend/application/modules/offline_context.py) nhận `Document`, `run_id` và tuple `GroundedRisk` của một mục giải thích. Mỗi `GroundedRisk` bọc một `Finding` đã xác minh và có thể mang căn cứ luật đã gắn từ trước. Đường chạy này phù hợp với các mục có bằng chứng `present`. Mục thiếu điều khoản chưa có bằng chứng nguồn sẽ trả `invalid_primary`.

1. P0 lập chỉ mục cho cặp `(run_id, SHA-256(Document.text))`.
2. P2 kiểm tra lại trích dẫn và offset của phát hiện. P2 gọi P1 để tìm đích dẫn chiếu từ các điều khoản chứa bằng chứng, rồi chọn đoạn hợp đồng theo ngân sách byte.
3. Nếu P2 trả `ready`, P3 đưa `ClauseReferences` vào `ContextRequest`. Builder kiểm tra lại lượt chạy và hash, đọc lại các đích bằng offset chuẩn và quyết định nội dung gói.
4. Kết quả trả cả `selection` và `packet`. `selection` ghi đoạn được chọn, đoạn bị bỏ, lỗi tham chiếu và lý do. Nếu bằng chứng chính không hợp lệ hoặc vượt ngân sách, `packet` là `None`. Nếu Builder vượt ngân sách lõi, `packet.status` là `core_over_budget` và phần dữ liệu gói rỗng.

## Ba ngân sách

| Giai đoạn | Đại lượng giới hạn |
|---|---|
| P2 | Tổng byte UTF-8 của các đoạn hợp đồng được chọn. Mỗi đoạn giữ nguyên văn và khoảng ký tự `[start, end)`. |
| Context Packet Builder | Ngân sách cho JSON gói theo `PromptBudget.allowance`. Runner dùng bộ đếm UTF-8 mặc định của Builder, bao gồm metadata và checklist được đóng gói. |
| Prompt LLM | Giới hạn cho thông điệp đầy đủ, gồm instructions và định dạng yêu cầu. Luồng P3 không tạo hoặc gửi prompt LLM. |

### Chính sách chọn trong P3.1

`selection_policy="legacy"` là mặc định của Builder và bộ điều phối. Builder có thể mở rộng sang Điều chứa bằng chứng và Điều liền kề. Trong báo cáo P3 gốc, `budget-01` chỉ có đủ byte P2 cho câu bằng chứng nhưng Builder đã thêm cả Điều nguồn và một Điều liền kề.

Truyền `selection_policy="strict"` vào `build_offline_context()` để Builder chỉ xét câu bằng chứng đã xác minh, `ClauseReferences` từ P2 và các Điều liền kề thực sự được P2 chọn. Hai danh sách được kiểm tra riêng theo lượt chạy và hash, rồi đọc lại từ bản đồ điều khoản. Giới hạn kích thước cửa sổ, số tham chiếu, đóng gói heuristic và kiểm tra căn cứ luật vẫn áp dụng. `multiple-03` cho thấy P2 có thể chọn sáu đích dù giới hạn tham chiếu mặc định của Builder là ba.

`selection.omitted` ghi việc P2 loại đoạn và lý do. `packing_diagnostics` đối chiếu hai tầng, dùng `selected_context_not_packed` cho ID đã chọn nhưng không được đóng gói và `packet_context_outside_selection` cho ID Builder bổ sung. `packet.diagnostics` giữ lý do cụ thể do Builder cung cấp khi có. STRICT xét câu bằng chứng nguyên văn nên heuristic cần thông tin ngoài câu có thể không khớp. Đoạn đã qua P2 vẫn có thể bị loại ở bước đóng gói.

## Dữ liệu và cách đo

[Bộ P3](../../data/context_eval/offline_context_synthetic_v1.json) có 29 hợp đồng dựng sẵn, ID theo offset, nhãn đích và giải thích có thể rà soát. Các tình huống bao gồm đích xa trước và sau nguồn, nhiều dẫn chiếu, Điều trùng số, đích thiếu, Phụ lục, ngân sách chặt và hợp đồng không có đích. Runner dựng bản đồ điều khoản từ fixture và dùng hàm grounding hiện có. Builder thật chạy cùng một heuristic `return_milestones` trong chế độ fixture tổng hợp có sẵn. Chế độ đánh giá này chỉ dùng văn bản hợp đồng và checklist thử nghiệm, không truy vấn kho luật. [Bộ P2 năm ca](../../data/context_eval/context_selection_synthetic_v1.json) và [kết quả P2 gốc](../../data/context_eval/context_selection_synthetic_v1_results.json) vẫn dùng đường chạy riêng.

- **Recall@K** lấy số ID kỳ vọng trong K tham chiếu P2 đầu tiên chia cho số ID kỳ vọng. Báo cáo lấy trung bình trên các ca có đích kỳ vọng.
- **Precision@K** lấy số ID đúng trong K vị trí đầu chia cho K trên tất cả ca. Vị trí trống có giá trị 0, nên chỉ số giảm ở K lớn khi hợp đồng thường chỉ có một đích.
- **Context coverage** đo tỷ lệ giữ câu bằng chứng bắt buộc và các ID đích kỳ vọng trong toàn bộ phần P2 chọn. Đích thực sự vào gói được báo cáo riêng.
- **Giữ bằng chứng bắt buộc** kiểm tra ID và provenance `grounded_span` ở P2 và trong gói. Mẫu số bao gồm hai ca dừng có chủ đích do ngân sách.
- **Tuân thủ ngân sách** đối chiếu số byte thực tế ở mỗi tầng. Ca dừng có chủ đích được tính tuân thủ nếu không phát ra dữ liệu vượt hạn mức.
- **Bác bỏ tham chiếu không hợp lệ** yêu cầu chẩn đoán khớp nhãn và không phát ra đích bị cấm qua `ClauseReferences`. Điều khoản liền kề có thể vẫn xuất hiện dưới vai trò khác khi Builder xét cửa sổ.

[Báo cáo P3 gốc](../../data/context_eval/offline_context_synthetic_v1_results.md) và [JSON v1](../../data/context_eval/offline_context_synthetic_v1_results.json) là đường cơ sở cố định. [So sánh P3.1 Markdown](../../data/context_eval/offline_context_synthetic_v2_results.md) và [JSON v2](../../data/context_eval/offline_context_synthetic_v2_results.json) ghi thay đổi theo ca. Ngoài Precision@K, v2 tính precision trên số đích thực sự trả về trong top K và trên toàn bộ đích trả về. Những ca không trả đích được loại khỏi mẫu số của hai chỉ số này.

`appendix-03` và `format-01` có thêm đích đúng ở P2. `appendix-03` giữ nguyên ID kỳ vọng, còn kỳ vọng `missing_target` cũ được bỏ trong phép đo v2. `budget-01` mất một đoạn liên quan trong gói vì phần byte dành cho câu bằng chứng đã hết. Báo cáo ghi đây là hồi quy độ bao phủ gói theo tiêu chí so sánh. Chế độ nghiêm ngặt giữ bằng chứng bắt buộc trong cả 27 gói tạo thành công và phần văn bản thực tế của gói tuân thủ hạn mức P2 trong cả 29 ca, gồm hai ca không phát gói. Kết quả trên Golden Set được thẩm định độc lập, hợp đồng thực và tác động tới chất lượng câu trả lời vẫn chưa được đo.

## Chạy lại

Từ `backend/`, chọn hai đường dẫn đầu ra mới. Runner hiện tạo báo cáo P3.1 theo chế độ nghiêm ngặt và đọc báo cáo v1 để đối chiếu. Runner báo lỗi nếu một đường dẫn đã có tệp. Mã thoát khác 0 báo lỗi về trạng thái kỳ vọng, bằng chứng bắt buộc, offset, ngân sách hoặc bác bỏ dẫn chiếu. Sai lệch truy hồi vẫn được giữ trong báo cáo để đánh giá chất lượng.

```powershell
..\.venv\Scripts\python.exe evaluate_offline_context.py --json p31-reproduction.json --markdown p31-reproduction.md
..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_offline_context.py tests/test_context_selection.py tests/test_cross_clause.py tests/test_short_term_memory.py tests/test_context_packet.py
```
