# Short-term Memory P1 · Truy hồi dẫn chiếu liên điều khoản

[`retrieve_cross_clause()`](../../backend/application/modules/cross_clause.py) tìm các dẫn chiếu trực tiếp trong một điều khoản của hợp đồng thuê nhà. Nó đọc văn bản từ [chỉ mục P0](short-term-memory-clause-index.md) và tra các tiêu đề đã được ingestion lập chỉ mục. Vì tra trên toàn bộ bản đồ, Điều 1 có thể tìm thấy Điều 12 dù giữa chúng có nhiều điều khoản. Các quy tắc chạy trong tiến trình với dữ liệu của lượt phân tích.

## Quy tắc truy hồi

| Văn bản trong điều khoản nguồn | Cách xác định đích |
|---|---|
| `theo Điều 5`, `quy định tại Điều 12` | Tìm một Điều có số tương ứng tại đầu một điều khoản đã được lập chỉ mục. |
| `tham chiếu Khoản 2 Điều 7` | Tìm Điều 7 duy nhất, rồi xác minh một dấu Khoản 2 duy nhất ở đầu dòng trong Điều đó, ví dụ `Khoản 2.`, `2)` hoặc `7.2.`. Đích mang ID của Điều 7. |
| `xem Phụ lục 1`, `xem Phụ lục số 1` | Tìm một điều khoản có tiêu đề Phụ lục 1 ở ngay đầu. |

Số Ả Rập và số La Mã viết hoa hợp lệ được quy về cùng giá trị. Hai tiêu đề cùng loại và cùng số tạo ra đích mơ hồ, kể cả khi chỉ một bản có dấu Khoản được nhắc. Đích mơ hồ, đích thiếu, tự dẫn chiếu, dạng sai và các hậu tố được nhận diện là dẫn chiếu ghép hoặc văn bản bên ngoài đều cho kết quả rỗng đối với lần nhắc đó. Bộ truy hồi tiếp tục xét các lần nhắc khác trong cùng điều khoản.

Kết quả được xếp theo mức ưu tiên giảm dần. Dẫn chiếu Khoản đã xác minh có mức 2, dẫn chiếu Điều hoặc Phụ lục có mức 1. Cùng mức thì xếp theo vị trí lần nhắc trong nguồn rồi theo vị trí đích. Mỗi ID đích xuất hiện một lần. `top_k` mặc định là 3 và giới hạn số đích phân biệt.

## Giao diện

- Đầu vào gồm `RunClauseIndex` đang mở, `RunScope`, ID điều khoản nguồn và tùy chọn `top_k`. Phạm vi khác lượt chạy hoặc khác hash bị từ chối ngay khi tra nguồn. ID nguồn chưa biết trả kết quả rỗng.
- `CrossClauseResult.relations` chứa `ClauseRelation` với ID nguồn/đích, loại `article`, `paragraph` hoặc `appendix`, cụm từ khớp nguyên văn, lý do và mức ưu tiên. `source_start/source_end` chỉ đúng cụm từ dẫn chiếu, còn `target_start/target_end` chỉ toàn bộ điều khoản đích. Cả hai là khoảng ký tự `[start, end)` trong `Document.text`.
- `CrossClauseResult.references` là `ClauseReferences` của P0, chứa `run_id`, hash tài liệu và danh sách ID đích theo thứ tự xếp hạng.

```python
from dataclasses import replace

from application.modules.cross_clause import retrieve_cross_clause
from application.modules.short_term_memory import RunClauseIndex, RunScope

# request is an existing ContextRequest for the current explanation item.
# finding is a grounded finding with a source offset.
scope = RunScope.for_document(request.run_id, request.document)
with RunClauseIndex(scope, request.document) as index:
    source = index.at_offset(scope, finding.char_start)
    if source is not None:
        result = retrieve_cross_clause(index, scope, source.clause_id, top_k=3)
        request = replace(request, references=result.references)

packet = builder.build(request, budget)
```

Builder đối chiếu lại phạm vi và đọc các đoạn đích từ tài liệu đang hoạt động. Mỗi đoạn là ứng viên cho cửa sổ truy hồi heuristic. Việc đưa đoạn vào gói cuối phụ thuộc vào heuristic được chọn và ngân sách của Builder. Explanation production hiện chưa gọi bộ truy hồi này.

## Giới hạn và kiểm thử

[P2 chọn ngữ cảnh theo ngân sách](short-term-memory-context-selection.md) dùng thêm chẩn đoán `unresolved` và các đích vượt `top_k` trong `limited` để giải thích vì sao một đích không xuất hiện trong gói đề xuất.

P3.1 cho phép dấu xuống dòng và khoảng trắng ngang giữa các thành phần của dẫn chiếu. Một dòng trống vẫn là ranh giới. Cụm khớp và offset giữ nguyên theo văn bản nguồn.

Phụ lục có thể là mục riêng hoặc là một tiêu đề rõ ở đầu dòng bên trong một mục đã lập chỉ mục. Dạng lồng cần có tiêu đề đứng riêng hoặc dấu phân cách như trong `Phụ lục 1: Danh mục`. Khi chỉ có một tiêu đề khớp, kết quả dùng ID của điều khoản chứa tiêu đề và ghi thêm `embedded_heading_span`. Tiêu đề lặp, kể cả lặp trong cùng mục, trả `ambiguous_target`. Phụ lục không có dấu hiệu tiêu đề đủ rõ vẫn có thể bị bỏ sót. Dấu Khoản được kiểm tra trong nội dung Điều và dùng ID của Điều. Các quan hệ ngầm, chuỗi dẫn chiếu, danh sách hoặc khoảng số và xác định phạm vi tham chiếu bằng ngữ nghĩa nằm ngoài phạm vi này.

Từ `backend/`, chạy:

```powershell
..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_cross_clause.py tests/test_short_term_memory.py tests/test_context_packet.py
```

Bài kiểm thử dùng dữ liệu cố định và bao gồm một hợp đồng chạy qua bộ phân đoạn theo quy tắc. Test tích hợp xác nhận Builder đọc được đích ở xa và loại tham chiếu khi đổi lượt chạy hoặc hash.
