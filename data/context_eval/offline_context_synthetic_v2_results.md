# So sánh ngoại tuyến Short-term Memory P3.1

Bộ dữ liệu tổng hợp gồm 29 tình huống. Kết quả Golden Set được thẩm định độc lập chưa có.
Recall chỉ tính ca có đích kỳ vọng. Precision@K chia số đích đúng cho K và tính cả ca không trả đích.
Precision returned chia cho số đích thực sự trả về và bỏ qua ca không trả đích.
appendix-03 giữ nguyên ID đích và bỏ kỳ vọng chẩn đoán missing_target của P3.

| Chỉ số | P3 | P3.1 | Mẫu P3.1 |
|---|---:|---:|---:|
| recall@1 | 68.94% | 78.03% | 22 |
| precision@1 | 62.07% | 68.97% | 29 |
| precision_returned@1 | 100.00% | 100.00% | 20 |
| recall@3 | 77.27% | 86.36% | 22 |
| precision@3 | 26.44% | 28.74% | 29 |
| precision_returned@3 | 100.00% | 100.00% | 20 |
| recall@5 | 78.79% | 87.88% | 22 |
| precision@5 | 17.24% | 18.62% | 29 |
| precision_returned@5 | 100.00% | 100.00% | 20 |
| precision_returned_all | 100.00% | 100.00% | 20 |
| Context coverage | 93.10% | 93.10% | 29 |
| Giữ bằng chứng bắt buộc tại P2 | 28/29 | 28/29 | 29 |
| Giữ bằng chứng bắt buộc trong gói | 27/29 | 27/29 | 29 |
| Tuân thủ hạn mức văn bản | 29/29 | 29/29 | 29 |
| Tuân thủ hạn mức gói | 29/29 | 29/29 | 29 |
| Văn bản thực tế trong gói tuân thủ hạn mức P2 | — | 29/29 | 29 |
| Bác bỏ dẫn chiếu không hợp lệ | 9/9 | 8/8 | 8 |

Số ca có hồi quy theo tiêu chí đối chiếu là 1.

| Ca | Đích P2 trước → sau | Đích đúng trong gói thêm / mất | Hồi quy | Sai lệch còn lại |
|---|---|---|---|---|
| direct-01 | clause-83-137 → clause-83-137 | — / — | — | — |
| direct-02 | clause-94-144 → clause-94-144 | — / — | — | relevant_context_not_in_packet (clause-94-144) |
| direct-03 | clause-73-127 → clause-73-127 | — / — | — | — |
| direct-04 | clause-84-138 → clause-84-138 | — / — | — | — |
| distant-01 | clause-152-201 → clause-152-201 | — / — | — | — |
| distant-02 | clause-0-48 → clause-0-48 | — / — | — | — |
| distant-03 | clause-126-175 → clause-126-175 | — / — | — | — |
| multiple-01 | clause-108-157, clause-158-186 → clause-108-157, clause-158-186 | — / — | — | relevant_context_not_in_packet (clause-158-186) |
| multiple-02 | clause-106-155, clause-156-172 → clause-106-155, clause-156-172 | — / — | — | relevant_context_not_in_packet (clause-156-172) |
| multiple-03 | clause-132-158, clause-159-183, clause-184-200, clause-201-223, clause-224-273, clause-274-299 → clause-132-158, clause-159-183, clause-184-200, clause-201-223, clause-224-273, clause-274-299 | — / — | — | relevant_context_not_in_packet (clause-132-158, clause-159-183, clause-184-200, clause-201-223, clause-224-273, clause-274-299) |
| paragraph-01 | clause-87-151 → clause-87-151 | — / — | — | — |
| paragraph-02 | clause-116-169, clause-99-115 → clause-116-169, clause-99-115 | — / — | — | relevant_context_not_in_packet (clause-99-115) |
| paragraph-03 | — → — | — / — | — | — |
| ambiguous-01 | — → — | — / — | — | — |
| ambiguous-02 | — → — | — / — | — | — |
| ambiguous-03 | clause-120-169 → clause-120-169 | — / — | — | — |
| missing-01 | — → — | — / — | — | — |
| missing-02 | clause-88-137 → clause-88-137 | — / — | — | — |
| appendix-01 | clause-110-162 → clause-110-162 | — / — | — | — |
| appendix-02 | clause-96-124 → clause-96-124 | — / — | — | relevant_context_not_in_packet (clause-96-124) |
| appendix-03 | — → clause-75-119 | — / — | — | relevant_context_not_in_packet (clause-75-119) |
| budget-01 | — → — | — / clause-88-136 | relevant_packet_context_lost | missing_relevant_references (clause-137-156, clause-88-136) · relevant_context_not_in_packet (clause-137-156, clause-88-136) |
| budget-02 | clause-271-287 → clause-271-287 | — / — | — | missing_relevant_references (clause-85-270) · relevant_context_not_in_packet (clause-271-287, clause-85-270) |
| budget-03 | — → — | — / — | — | missing_relevant_references (clause-73-121) · relevant_context_not_in_packet (clause-73-121) |
| budget-04 | clause-73-121 → clause-73-121 | — / — | — | relevant_context_not_in_packet (clause-73-121) |
| none-01 | — → — | — / — | — | — |
| none-02 | — → — | — / — | — | — |
| none-03 | — → — | — / — | — | — |
| format-01 | — → clause-83-131 | — / — | — | — |
