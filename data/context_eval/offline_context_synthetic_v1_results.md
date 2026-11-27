# Đánh giá ngoại tuyến Short-term Memory P3

Bộ dữ liệu tổng hợp gồm 29 tình huống. Kết quả Golden Set được thẩm định độc lập chưa có.
Recall chỉ tính ca có đích kỳ vọng. Precision@K chia số đích đúng cho K và tính cả ca không trả đích.

| Chỉ số | Kết quả | Mẫu |
|---|---:|---:|
| recall@1 | 68.94% | 22 |
| precision@1 | 62.07% | 29 |
| recall@3 | 77.27% | 22 |
| precision@3 | 26.44% | 29 |
| recall@5 | 78.79% | 22 |
| precision@5 | 17.24% | 29 |
| Context coverage | 93.10% | 29 |
| Giữ bằng chứng bắt buộc tại P2 | 28/29 | 29 |
| Giữ bằng chứng bắt buộc trong gói | 27/29 | 29 |
| Tuân thủ hạn mức văn bản | 29/29 | 29 |
| Tuân thủ hạn mức gói | 29/29 | 29 |
| Bác bỏ dẫn chiếu không hợp lệ | 9/9 | 9 |

| Ca | Byte P2 | Đích P2 | Đích đúng trong gói | Trạng thái gói | Sai lệch |
|---|---:|---|---|---|---|
| direct-01 | 120/4000 | clause-83-137 | clause-83-137 | ready | packet_added_context_outside_selection (clause-0-82) |
| direct-02 | 122/4000 | clause-94-144 | — | ready | relevant_context_not_in_packet (clause-94-144) |
| direct-03 | 122/4000 | clause-73-127 | clause-73-127 | ready | packet_added_context_outside_selection (clause-0-72) |
| direct-04 | 120/4000 | clause-84-138 | clause-84-138 | ready | packet_added_context_outside_selection (clause-0-83) |
| distant-01 | 132/4000 | clause-152-201 | clause-152-201 | ready | packet_added_context_outside_selection (clause-0-104) |
| distant-02 | 169/4000 | clause-0-48 | clause-0-48 | ready | packet_added_context_outside_selection (clause-71-153) |
| distant-03 | 135/4000 | clause-126-175 | clause-126-175 | ready | packet_added_context_outside_selection (clause-0-81) |
| multiple-01 | 172/4000 | clause-108-157, clause-158-186 | clause-108-157 | ready | relevant_context_not_in_packet (clause-158-186) · packet_added_context_outside_selection (clause-0-91) |
| multiple-02 | 137/4000 | clause-106-155, clause-156-172 | clause-106-155 | ready | relevant_context_not_in_packet (clause-156-172) · packet_added_context_outside_selection (clause-0-105) |
| multiple-03 | 269/4000 | clause-132-158, clause-159-183, clause-184-200, clause-201-223, clause-224-273, clause-274-299 | — | ready | relevant_context_not_in_packet (clause-132-158, clause-159-183, clause-184-200, clause-201-223, clause-224-273, clause-274-299) |
| paragraph-01 | 133/4000 | clause-87-151 | clause-87-151 | ready | packet_added_context_outside_selection (clause-0-86) |
| paragraph-02 | 140/4000 | clause-116-169, clause-99-115 | clause-116-169 | ready | relevant_context_not_in_packet (clause-99-115) · packet_added_context_outside_selection (clause-0-98) |
| paragraph-03 | 116/4000 | — | — | ready | packet_added_context_outside_selection (clause-0-86) |
| ambiguous-01 | 74/4000 | — | — | ready | — |
| ambiguous-02 | 116/4000 | — | — | ready | packet_added_context_outside_selection (clause-0-86) |
| ambiguous-03 | 137/4000 | clause-120-169 | clause-120-169 | ready | packet_added_context_outside_selection (clause-0-84) |
| missing-01 | 73/4000 | — | — | ready | — |
| missing-02 | 115/4000 | clause-88-137 | clause-88-137 | ready | packet_added_context_outside_selection (clause-0-87) |
| appendix-01 | 143/4000 | clause-110-162 | clause-110-162 | ready | packet_added_context_outside_selection (clause-0-74) |
| appendix-02 | 109/4000 | clause-96-124 | — | ready | relevant_context_not_in_packet (clause-96-124) |
| appendix-03 | 110/4000 | — | — | ready | missing_relevant_references (clause-75-119) · relevant_context_not_in_packet (clause-75-119) |
| budget-01 | 52/52 | — | clause-88-136 | ready | missing_relevant_references (clause-137-156, clause-88-136) · relevant_context_not_in_packet (clause-137-156) · packet_added_context_outside_selection (clause-0-87, clause-88-136) |
| budget-02 | 74/90 | clause-271-287 | — | ready | missing_relevant_references (clause-85-270) · relevant_context_not_in_packet (clause-271-287, clause-85-270) |
| budget-03 | 0/8 | — | — | not_built | missing_relevant_references (clause-73-121) · relevant_context_not_in_packet (clause-73-121) |
| budget-04 | 113/4000 | clause-73-121 | — | core_over_budget | relevant_context_not_in_packet (clause-73-121) |
| none-01 | 75/4000 | — | — | ready | — |
| none-02 | 72/4000 | — | — | ready | — |
| none-03 | 74/4000 | — | — | ready | — |
| format-01 | 113/4000 | — | clause-83-131 | ready | missing_relevant_references (clause-83-131) · packet_added_context_outside_selection (clause-0-82) |
