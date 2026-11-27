# Short-term Memory P2 · Chọn ngữ cảnh theo ngân sách

[`select_context()`](../../backend/application/modules/context_selection.py) chọn đoạn hợp đồng cho một mục phân tích. Nó dùng [chỉ mục P0](short-term-memory-clause-index.md) để đọc đúng bản văn của lượt chạy và [bộ truy hồi P1](short-term-memory-cross-clause.md) để lấy các Điều hoặc Phụ lục được dẫn chiếu.

## Thứ tự chọn

1. **Bằng chứng chính là bắt buộc.** ID điều khoản chọn toàn bộ điều khoản. Với một `Finding` loại `present`, bộ chọn đối chiếu trích dẫn và offset trên văn bản hiện tại rồi giữ chính xác khoảng đã xác minh. Các điều khoản giao với khoảng đó là nguồn tìm dẫn chiếu và điều khoản lân cận. Nếu bản đồ điều khoản rỗng, khoảng đã xác minh vẫn dùng được.
2. **Dẫn chiếu trực tiếp đứng trước đoạn liền kề.** Mức ưu tiên từ P1 cao hơn được xét trước. Cùng mức thì dùng vị trí dẫn chiếu rồi vị trí đích. Các đoạn liền kề được xét theo thứ tự tài liệu. Một ID xuất hiện một lần và giữ vai trò ưu tiên cao nhất.
3. **Đo ngân sách trên nguyên văn UTF-8.** `budget_bytes` giới hạn tổng số byte văn bản của các đoạn được chọn. Mỗi đoạn tùy chọn được giữ nguyên hoặc bỏ toàn bộ. Nếu đoạn xếp hạng cao quá lớn, bộ chọn vẫn xét đoạn nhỏ hơn ở sau. Khi tổng bằng chứng bắt buộc vượt hạn mức, kết quả có trạng thái `mandatory_over_budget`, số byte cần cho bằng chứng bắt buộc và danh sách đoạn bị bỏ. Khi bằng chứng chính thiếu hoặc sai, kết quả có trạng thái `invalid_primary`.

## Giao diện

| Thành phần | Dữ liệu |
|---|---|
| Phạm vi | `RunClauseIndex` và `RunScope(run_id, document_sha256)` của văn bản đã làm sạch. Sai phạm vi chỉ mục gây `ValueError`. |
| Bằng chứng chính | `primary_clause_ids`, `findings` hoặc cả hai. Khoảng bằng chứng và toàn điều khoản có ID khác nhau được tính riêng nếu bên gọi yêu cầu cả hai. |
| Dẫn chiếu | `cross_clause_results=None` tự chạy P1. Truyền tuple kết quả P1 để dùng lại. Tuple rỗng chỉ chọn bằng chứng chính và các đoạn liền kề nếu vừa ngân sách. Kết quả ngoại phạm vi bị bỏ với chẩn đoán `foreign_reference_scope`. |
| Kết quả | `selected` chứa đoạn nguyên văn, offset, provenance và lý do. Dẫn chiếu được chọn còn mang `ClauseRelation` của P1. `omitted` ghi đích hợp lệ bị giới hạn bởi truy hồi hoặc ngân sách. `invalid` ghi lỗi dữ liệu, gồm đích thiếu hoặc mơ hồ do P1 phát hiện. |
| Adapter | `references` chỉ chứa ID các đích dẫn chiếu được chọn. Đoạn lân cận vẫn có thể xuất hiện trong `selected` với vai trò `neighbor`. |

## Sử dụng với Context Packet Builder

```python
from dataclasses import replace

from application.modules.context_selection import select_context
from application.modules.short_term_memory import RunClauseIndex, RunScope

# request là ContextRequest cho mục giải thích đã có bằng chứng.
scope = RunScope.for_document(request.run_id, request.document)
with RunClauseIndex(scope, request.document) as index:
    selection = select_context(
        index,
        scope,
        findings=tuple(risk.finding for risk in request.risks),
        budget_bytes=2000,
    )
if selection.status == "ready":
    packet = builder.build(replace(request, references=selection.references), prompt_budget)
```

Builder vẫn tự đọc lại bằng chứng và giữ quyền quyết định đoạn nào vào gói cuối. Ngân sách P2 chỉ tính byte của văn bản hợp đồng, còn Builder và Explanation áp dụng giới hạn riêng cho gói, căn cứ pháp lý, checklist, instructions và messages. Giới hạn byte của P2 không đo token hoặc bảo đảm kích thước prompt cuối. Các kết quả P1 được tái sử dụng trong cùng phạm vi từ bên gọi nội bộ. P2 kiểm tra sự khớp chỉ mục và offset. P2 vẫn là API độc lập với pipeline production.

## Đánh giá tổng hợp

[Bộ dữ liệu](../../data/context_eval/context_selection_synthetic_v1.json) gồm 5 tình huống với ID điều khoản kỳ vọng cố định. [Báo cáo JSON](../../data/context_eval/context_selection_synthetic_v1_results.json) ghi từng đích được chọn, bị bỏ và các chẩn đoán.

- **Recall@3 đạt 50,00%**. Tính tỷ lệ ID đúng trong tối đa ba đích dẫn chiếu đầu tiên, lấy trung bình trên ba tình huống có đích kỳ vọng. Tình huống tràn bằng chứng bắt buộc có recall bằng 0.
- **Context coverage đạt 73,33%**. Tính tỷ lệ ID được chọn trong tập gồm bằng chứng chính và các đích kỳ vọng, lấy trung bình trên cả năm tình huống.
- **Hai dẫn chiếu bị bỏ**. Một Phụ lục vượt phần ngân sách còn lại. Một đích bị chặn khi bằng chứng bắt buộc vượt ngân sách.
- **5/5 tình huống tuân thủ ngân sách byte**, gồm tình huống thất bại rõ ràng với 0 byte được chọn.

Các tình huống được dựng để kiểm tra lựa chọn, chẩn đoán và giới hạn byte. Chất lượng ngữ nghĩa, độ chính xác trên hợp đồng thực và tác động đến Explanation cần được đo riêng.

Chạy từ `backend/`:

```powershell
..\.venv\Scripts\python.exe evaluate_context_selection.py
..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_context_selection.py tests/test_cross_clause.py tests/test_short_term_memory.py tests/test_context_packet.py
```
