# Short-term Memory P0 · Chỉ mục điều khoản theo lượt phân tích

[`RunClauseIndex`](../../backend/application/modules/short_term_memory.py) tạo bảng tra trong bộ nhớ từ `Document.structure.clauses` của ingestion. Mỗi đối tượng thuộc một cặp `(run_id, document_sha256)`. Hash là SHA-256 của `Document.text` đã làm sạch, mã hóa UTF-8, cùng quy ước với [Context Packet Builder](heuristic-context-packet-pilot.md). ID `clause-<start>-<end>` dùng lại hàm `clause_id()` của Builder. Hai tài liệu có thể có cùng ID điều khoản, vì vậy mọi thao tác đọc đều kiểm tra cả cặp định danh.

## Vòng đời và cách tra cứu

- Tạo `RunScope` từ `Document` và ID do bên điều phối cấp, rồi mở `RunClauseIndex` bằng `with`. Hàm khởi tạo kiểm tra hash khớp với văn bản đưa vào.
- Dùng `by_id()`, `at_offset()` hoặc `overlapping()`. Offset là vị trí ký tự trong văn bản đã làm sạch. Khoảng `[start, end)` gồm đầu và loại cuối. Kết quả giao nhau theo thứ tự tài liệu. Tra vào khoảng trống hoặc tìm ID chưa biết trả `None`. Khoảng rỗng hoặc không có giao trả tuple rỗng.
- Điều khoản trả về có văn bản đúng bằng lát cắt nguồn, nhãn, tiêu đề, cấp, offset và provenance `clause_map`. Bản đồ thiếu hoặc rỗng cho chỉ mục rỗng. Bản đồ có offset sai hoặc các khoảng đè lên nhau cũng cho chỉ mục rỗng, theo cách Builder xử lý bản đồ không hợp lệ. Khoảng trống giữa các điều khoản hợp lệ vẫn được giữ.
- Gọi `to_references()` với các ID do bên gọi chọn để tạo `ClauseReferences` truyền qua `ContextRequest.references`. Adapter giữ thứ tự ưu tiên, bỏ ID trùng và từ chối cả yêu cầu nếu có ID lạ. Builder kiểm tra lại phạm vi rồi đọc đoạn từ `Document` đang hoạt động.
- Thoát `with` hoặc gọi `release()` để bỏ văn bản và metadata mà chỉ mục giữ. `release()` gọi lặp được. Sai phạm vi trả `ValueError`. Truy cập đúng phạm vi sau khi giải phóng trả `RuntimeError`.

## Ví dụ

Chạy từ thư mục `backend/`. Ví dụ dùng fixture nội bộ để có offset xác định.

```python
from application.modules.ingestion.ingest import Clause, Document, Structure
from application.modules.short_term_memory import RunClauseIndex, RunScope

text = "Cọc\nNhà"
document = Document(text, source={}, structure=Structure(clauses=[
    Clause("Điều 1", "Cọc", 0, 3),
    Clause("Điều 2", "Nhà", 4, 7),
]))
scope = RunScope.for_document("demo-run", document)

with RunClauseIndex(scope, document) as index:
    first = index.by_id(scope, "clause-0-3")
    second = index.at_offset(scope, 4)
    print(first.text, second.text)  # Cọc Nhà
    print([clause.clause_id for clause in index.overlapping(scope, 2, 5)])
    # ['clause-0-3', 'clause-4-7']
    references = index.to_references(scope, [second.clause_id])
    # Pass references to ContextRequest.references.
```

## Giới hạn của P0

Mỗi chỉ mục giữ một tham chiếu tới chuỗi văn bản bất biến và metadata tỷ lệ với số điều khoản. Văn bản của mỗi điều khoản được cắt khi tra cứu. Bên gọi sở hữu chỉ mục và các kết quả đã lấy ra. Giải phóng chỉ mục không thu hồi các kết quả bên gọi đang giữ. Chỉ mục hoạt động trong tiến trình, không tạo tệp hoặc cache toàn cục.

P0 cung cấp vị trí trên văn bản đã làm sạch. [P1 truy hồi dẫn chiếu liên điều khoản](short-term-memory-cross-clause.md) dùng chỉ mục này qua API độc lập. Ánh xạ sang tệp gốc và tích hợp vào pipeline thuộc các bước sau. Cặp ID và hash kiểm tra khớp dữ liệu trong tiến trình. Quyền truy cập lượt chạy thuộc về bên điều phối. Bên gọi dùng cùng bản đồ điều khoản từ ingestion khi tạo chỉ mục và khi build gói.

## Kiểm thử

Từ `backend/`, chạy `..\.venv\Scripts\python.exe -m pytest -q tests/test_short_term_memory.py tests/test_context_packet.py`. Test Builder dùng fixture nội bộ để xác nhận tham chiếu từ chỉ mục được đọc lại thành đúng văn bản và offset.
