# Vietnamese residential rental heuristic review

Review target is knowledge snapshot `1.0.0` with the v2 retriever. All 18 entries and their examples are draft. The snapshot contains zero verified legal rules and zero linked legal references. The risk labels below are the repository taxonomy labels, supplied for mapping review. The seed entries do not declare categories directly. Group codes follow from their mapped risk codes.

The seed trigger groups are shown verbatim. Within a group, any phrase can match. Across groups, all groups must match on the lexical route. The notes on v2 describe additional matching behavior, including structural fallbacks where present. JSON exclusions and v2 distractor filters remove an entire eligible passage for the affected heuristic. A separate passage can still qualify. The required context and cross-clause checks describe reviewer work. A selection does not establish that the listed evidence exists or that a legal conclusion follows.

[Knowledge snapshot](../../../data/heuristics/vn_residential_rental.json) · [Taxonomy](../../../data/taxonomy/taxonomy.json) · [v2 matching rules](../../../backend/application/modules/heuristic_memory/rental_matching.py) · [v2 evaluation](../heuristic-memory-retriever-v2.md)

Use the [reviewer guide](reviewer-guide.md) and [CSV worksheet](review-sheet.csv) to record decisions. The [prioritized issues](prioritized-issues.md) identify which observed failures to review first.

## `deposit_identity` — Distinguish deposit from advance rent

- **Purpose.** Trace each transfer from reservation through lease signing and the first payment period.
- **Taxonomy mappings.** `B-DEP-08` (Tiền thuê/phương thức thanh toán không được xác định rõ). `B-DEP-04` (Không có cơ chế rõ ràng để hoàn trả tiền cọc).
- **Seed triggers.** `đặt cọc` / `tiền cọc` / `tiền giữ chỗ` **and** `trả trước` / `ứng trước` / `cấn trừ`
- **Seed exclusions.** `không có khoản đặt cọc`
- **v2 eligibility.** Adds reservation and security aliases and rent-credit wording. Adjacent eligible passages can combine when they contain a reservation cue. Remedy, settlement and damage compensation wording can block a candidate window.
- **Required context.** Reservation receipt, payment schedule and first rent invoice.
- **Cross-clause dependency.** Compare the receipt with the signing and rent-credit clauses.
- **Potential false positives and controls.** A rent credit for a different transfer can combine with reservation wording. VN-44 was a v1 false positive for a penalty offset and is a v2 regression control. Test distinct amounts and dates before linking transfers.
- **Review focus.** Confirm whether B-DEP-08 covers allocation of the payment and whether B-DEP-04 adds value when the dispute concerns classification alone. Refer any claim of refundability to legal review.

## `deposit_refund_clock` — Identify the deposit refund clock

- **Purpose.** A refund period may start only after keys are returned, an exit record is signed or final utilities are settled.
- **Taxonomy mappings.** `B-DEP-04` (Không có cơ chế rõ ràng để hoàn trả tiền cọc). `A-DEP-04` (Không hoàn trả cọc khi nghĩa vụ hoàn trả đã phát sinh).
- **Seed triggers.** `hoàn cọc` / `hoàn trả tiền cọc` / `trả lại tiền cọc`
- **Seed exclusions.** `cọc giữ chỗ mua nhà`
- **v2 eligibility.** Adds short refund aliases. A fallback accepts a return action, a named security amount and a timing cue in one passage.
- **Required context.** Refund interval, start event, signatories and final billing cycle.
- **Cross-clause dependency.** Compare the refund clause with handover and utility settlement clauses.
- **Potential false positives and controls.** Refunds of a different security amount or a timing phrase attached to another payment can still qualify. HO-13 misses a return of a sum described as bảo chứng.
- **Review focus.** Treat keys, signature and utility settlement as candidate contractual start events. Ask legal review before describing any withholding condition as enforceable.

## `deposit_deductions` — Reconcile deposit deductions and proof

- **Purpose.** A deposit settlement can combine unpaid rent, utility balances and repair charges.
- **Taxonomy mappings.** `B-DEP-02` (Nguy cơ mất/khấu trừ tiền cọc không có căn cứ). `A-DEP-02` (Giữ/Khấu trừ tiền cọc không có căn cứ).
- **Seed triggers.** `khấu trừ tiền cọc` / `trừ vào cọc` / `cấn trừ tiền cọc`
- **Seed exclusions.** None in the JSON.
- **v2 eligibility.** Adds explicit deductions from tiền cọc or khoản bảo đảm. Uses one passage.
- **Required context.** Deposit amount, itemized deductions, receipts and settlement statement.
- **Cross-clause dependency.** Match deduction items to the payment, maintenance and move-out clauses.
- **Potential false positives and controls.** A credit toward first rent or an offset against a different deposit can look like a settlement charge. Compare VN-44 with a genuine rent credit.
- **Review focus.** Validate both parties’ mappings against the documented item or unsupported deduction. Refer disputed entitlement or required proof for legal review.

## `deposit_forfeiture` — Distinguish breach from agreed early exit

- **Purpose.** A forfeiture provision may describe tenant breach while another clause permits early exit with notice.
- **Taxonomy mappings.** `B-DEP-03` (Điều kiện mất cọc không phù hợp với trường hợp vi phạm). `A-DEP-03` (Xử lý tiền cọc không phù hợp khi bên thuê vi phạm).
- **Seed triggers.** `mất cọc` / `tịch thu tiền cọc` / `không hoàn cọc`
- **Seed exclusions.** None in the JSON.
- **v2 eligibility.** Adds retaining all security and explicit nonreturn. Suppresses passages mentioning parking cards, parking spaces or a purchase deposit.
- **Required context.** Forfeiture events, notice clauses, cure rights and party initiating exit.
- **Cross-clause dependency.** Compare forfeiture language with tenant exit, mutual termination and landlord recovery clauses.
- **Potential false positives and controls.** An unconditional description of retention may match without an applicable breach. A shared passage covering both the parking and lease deposits can suppress a relevant finding. VN-22 tests negation and the parking object.
- **Review focus.** Distinguish a stated exit consequence from a conclusion about enforceability. Test tenant breach, mutual exit and landlord-initiated exit separately.

## `termination_notice_clock` — Reconstruct notice and cure deadlines

- **Purpose.** The effective date can turn on receipt of notice or expiration of a separate cure period.
- **Taxonomy mappings.** `B-TRM-01` (Bị chấm dứt hợp đồng/thu hồi nhà trước thời hạn không có căn cứ). `B-TRM-03` (Quyền đơn phương chấm dứt bị hạn chế). `A-PEN-06` (Thiếu quy trình ghi nhận và thông báo vi phạm).
- **Seed triggers.** `chấm dứt` / `thu hồi nhà` **and** `thông báo` / `báo trước` / `khắc phục`
- **Seed exclusions.** `chấm dứt hợp đồng môi giới`
- **v2 eligibility.** Adds early move-out and written notice aliases, including an explicit failure to give notice. Excludes cleaning, maintenance and service contracts within the matching passage.
- **Required context.** Notice channels, receipt date, day-count convention and cure period.
- **Cross-clause dependency.** Compare the notice, breach, termination and handover clauses.
- **Potential false positives and controls.** Separate notice events within one passage can be joined incorrectly. A single passage covering a service ending and lease ending can be suppressed. VN-23 and HO-28 exercise opposite sides of this boundary.
- **Review focus.** Check that A-PEN-06 applies to cure-related situations and that the relevant notice belongs to the triggering party and event. Refer any mandatory notice or service rule to legal review.

## `renewal_vs_exit` — Distinguish nonrenewal from early termination

- **Purpose.** A notice window before expiry may govern automatic renewal and differ from the notice for breaking a current term.
- **Taxonomy mappings.** `A-TRM-03` (Thời hạn thuê/điều kiện gia hạn không rõ ràng). `B-TRM-04` (Thời hạn thuê/điều kiện gia hạn không rõ ràng).
- **Seed triggers.** `gia hạn` / `tự động gia hạn` **and** `hết hạn` / `báo trước` / `không gia hạn`
- **Seed exclusions.** None in the JSON.
- **v2 eligibility.** Adds continuation, expiry and failure-to-notify aliases. Requires a lease cue or automatic renewal cue. Filters card and warranty phrases within the passage.
- **Required context.** End date, renewal mechanism, nonrenewal deadline and extension price.
- **Cross-clause dependency.** Compare the term clause and renewal annex with early exit provisions.
- **Potential false positives and controls.** A generic contract or automatic extension may describe a service. HO-18 misses continuation phrased without standard extension wording.
- **Review focus.** Check where A-TRM-03 and B-TRM-04 apply, including any difference in party perspective. Separate contractual deadline reconstruction from a legal conclusion about renewal.

## `lessor_identity` — Trace the lessor’s authority chain

- **Purpose.** The named lessor, signatory, title holder and deposit recipient may be different people.
- **Taxonomy mappings.** `B-AUT-01` (Thuê từ người không có quyền/thẩm quyền). `B-AUT-05` (Thông tin chủ thể/quyền cho thuê/ủy quyền ghi nhận không đầy đủ). `A-AUT-01` (Cho thuê nhà khi không có quyền/thẩm quyền).
- **Seed triggers.** `bên cho thuê` / `chủ nhà` **and** `giấy chứng nhận` / `ủy quyền` / `uỷ quyền` / `đứng tên`
- **Seed exclusions.** None in the JSON.
- **v2 eligibility.** Adds tenant-facing lessor labels and property-document aliases. Adjacent eligible passages can combine when title or mandate vocabulary appears.
- **Required context.** Property identifier, title holder, signer, mandate and payee.
- **Cross-clause dependency.** Compare party identification, signature block, authority documents and payment instructions.
- **Potential false positives and controls.** HO-11 links a furniture invoice bearing the owner's name with an authority-like phrase. Test that the document and named parties relate to the same unit and transaction.
- **Review focus.** Check overlap with sublease_scope for A-AUT-01 and B-AUT-01. Escalate conclusions about legal authority or the legal effect of a mandate.

## `co_owner_consent` — Check scope of co-owner consent

- **Purpose.** A co-owner may sign for a shared property while consent covers only management or collection.
- **Taxonomy mappings.** `B-AUT-02` (Thuê tài sản chung mà không đầy đủ ủy quyền). `A-AUT-02` (Cho thuê tải sản chung nhưng thiếu ủy quyền cần thiết).
- **Seed triggers.** `đồng sở hữu` / `tài sản chung` / `sở hữu chung`
- **Seed exclusions.** None in the JSON.
- **v2 eligibility.** Adds joint-title and household ownership phrases, requires a dwelling, signing, rental or title cue, and filters common-area distractors.
- **Required context.** Co-owner identity, shared property description and consent text.
- **Cross-clause dependency.** Compare the names on ownership documents with the signatures and authorization annex.
- **Potential false positives and controls.** A couple's signatures may describe co-occupancy rather than ownership. A common-area sentence could also mention the leased unit and suppress a relevant hit.
- **Review focus.** Test consent limited to collecting rent or one floor. An authorized legal reviewer should determine whether consent is required or sufficient.

## `sublease_scope` — Trace consent through the head lease

- **Purpose.** A sublease may exceed the head lease term, approved unit or permitted use.
- **Taxonomy mappings.** `B-AUT-01` (Thuê từ người không có quyền/thẩm quyền). `A-AUT-01` (Cho thuê nhà khi không có quyền/thẩm quyền).
- **Seed triggers.** `cho thuê lại` / `hợp đồng thuê gốc` / `thuê lại`
- **Seed exclusions.** `cho thuê lại chỗ đỗ xe`
- **v2 eligibility.** Adds head-lease and third-party letting language. Applies the seed parking exclusion to the passage carrying it.
- **Required context.** Head lease, owner consent, sublet unit and both expiry dates.
- **Cross-clause dependency.** Compare the head lease prohibition or consent clause to the sublease and attached approval.
- **Potential false positives and controls.** A prohibition may be useful in a real head-lease comparison, while a guest or roommate policy can be mistaken for a sublease. HO-30 tests separate parking and residential passages.
- **Review focus.** Check code overlap with lessor_identity and distinguish permission to occupy from a grant of sublease rights. Refer authority and enforceability claims separately.

## `wear_baseline` — Compare wear against the move-in baseline

- **Purpose.** A requirement to restore original condition can sweep in existing defects and use-related wear.
- **Taxonomy mappings.** `B-MNT-01` (Phải chịu trách nhiệm sửa chữa hư hỏng không do mình gây ra/hao mòn tự nhiên). `B-TRM-05` (Phải bồi thường cả hao mòn tự nhiên khi hoàn trả nhà). `B-PEN-02` (Bị yêu cầu bồi thường cả hao mòn tự nhiên).
- **Seed triggers.** `hao mòn tự nhiên` / `hao mòn thông thường` / `xuống cấp` / `nguyên trạng`
- **Seed exclusions.** None in the JSON.
- **v2 eligibility.** Adds wear and prior-damage wording, requires a move-out, baseline or condition cue, and filters vehicle and nameplate distractors. The fallback links condition evidence and baseline records to a return-cost passage.
- **Required context.** Dated inventory, photos, age, move-out record and cause of damage.
- **Cross-clause dependency.** Compare handover records with repair duties and deposit deductions.
- **Potential false positives and controls.** Generic wear on property unrelated to the unit can still qualify. Parallel defects may be mistaken for the same item. HO-25 misses the wording of a floor-replacement deduction.
- **Review focus.** Check that maintenance, return and damage-related codes apply to their respective fact patterns. Route responsibility for wear or repair costs for legal review if stated as an entitlement.

## `repair_reimbursement` — Trace repair approval and reimbursement

- **Purpose.** Emergency repairs may follow a different process from tenant-funded improvements.
- **Taxonomy mappings.** `A-MNT-03` (Không thanh toán chi phí bảo trì, sửa chữa hợp lý cho bên thuê). `B-MNT-04` (Bị hạn chế quyền yêu cầu sửa chữa hoặc hoàn trả chi phí hợp lý).
- **Seed triggers.** `sửa chữa` / `bảo trì` **and** `hoàn trả chi phí` / `chi phí hợp lý` / `khẩn cấp` / `thông báo`
- **Seed exclusions.** `chi phí sửa chữa xe`
- **v2 eligibility.** Adds work and repayment aliases. Requires a funding or urgency cue beyond mere notice. Uses one passage and the short negation filter.
- **Required context.** Defect notice, response window, urgency, consent and invoice.
- **Cross-clause dependency.** Compare repair duties with tenant alterations and reimbursement clauses.
- **Potential false positives and controls.** HO-21 treats a nested disclaimer of reimbursement as an operative term. Emergency-only wording may also qualify without a reimbursement provision. HO-14 misses an affirmative repair and repayment paraphrase.
- **Review focus.** Review whether missing reimbursement terms merit a checklist. Preserve conditional emergency authorization and distinguish costs of optional improvements. Refer claims of a right to reimbursement separately.

## `repair_disruption` — Check rent allocation during loss of use

- **Purpose.** A repair period may leave only part of the premises usable while rent continues on its regular schedule.
- **Taxonomy mappings.** `B-MNT-03` (Phải chịu tiền thuê trong thời gian nhà được bảo trì/cải tạo làm gián đoạn sử dụng). `A-MNT-05` (Không duy trì tài sản đúng tình trạng và mục đích thuê).
- **Seed triggers.** `bảo trì` / `cải tạo` **and** `gián đoạn` / `không sử dụng được` / `tạm ngừng sử dụng`
- **Seed exclusions.** None in the JSON.
- **v2 eligibility.** Adds repair and construction terms plus inability-to-occupy wording. Both groups must qualify in one passage.
- **Required context.** Affected area, dates, access plan, temporary accommodation and rent schedule.
- **Cross-clause dependency.** Compare repair access provisions with rent adjustment and early exit terms.
- **Potential false positives and controls.** HO-09 matches vehicle maintenance and a disrupted route. HO-26 misses related repair, occupancy and rent terms split across passages.
- **Review focus.** Check affected area and dates before inferring a change to rent. Refer any asserted rent relief or termination right for legal review.

## `rent_increase` — Reconcile scheduled and unilateral rent changes

- **Purpose.** Different provisions can set a fixed initial rent, an escalation schedule and a discretionary reset.
- **Taxonomy mappings.** `B-DEP-05` (Quyền tăng tiền thuê đơn phương). `A-DEP-05` (Quyền thay đổi tiền thuê không có căn cứ). `A-MNT-04` (Điều chỉnh giá thuê sau cải tạo không đúng điều kiện).
- **Seed triggers.** `tăng giá thuê` / `điều chỉnh giá thuê` / `thay đổi giá thuê`
- **Seed exclusions.** None in the JSON.
- **v2 eligibility.** Adds rent-reset and new-rate phrases. A single eligible phrase can qualify.
- **Required context.** Fixed period, formula, cap, notice and effective dates.
- **Cross-clause dependency.** Compare the rent table with renewal, improvement and amendment clauses.
- **Potential false positives and controls.** A new rate in an initial offer or another unit's rate can be mistaken for a midterm change. HO-15 misses a clause allowing the lessor to set the later monthly sum.
- **Review focus.** Check that A-MNT-04 is useful specifically for rent changes connected to improvements. Separate agreed pricing from a legal claim that the change is allowed.

## `utility_service_fees` — Reconcile service fees and utility billing

- **Purpose.** Building fees, metered charges and shared charges can have different payees and calculation bases.
- **Taxonomy mappings.** `B-DEP-07` (Nghĩa vụ thanh toán các khoản không có căn cứ). `A-DEP-07` (Yêu cầu khoản thanh toán không có căn cứ). `B-DEP-08` (Tiền thuê/phương thức thanh toán không được xác định rõ).
- **Seed triggers.** `phí quản lý` / `phí dịch vụ` / `tiền điện` / `tiền nước` / `phí gửi xe`
- **Seed exclusions.** `phí dịch vụ môi giới`
- **v2 eligibility.** Adds operating fees, combined utility costs and parking language. Brokerage exclusion applies per passage.
- **Required context.** Included services, rates, meter readings, billing period and payees.
- **Cross-clause dependency.** Compare inclusive rent wording with the fee annex and final utility settlement.
- **Potential false positives and controls.** An incidental fee name is enough to qualify. A passage containing brokerage and utilities together can still mask a valid hit. VN-41 checks separation across passages.
- **Review focus.** Check whether B-DEP-08 belongs beyond ambiguous payment amounts. Distinguish an express charge from a claim that a particular tariff or billing practice is lawful.

## `tax_incidence` — Distinguish inclusive rent from tax paid on behalf

- **Purpose.** The price schedule and invoice clause can disagree about who bears tax and who performs filing or payment.
- **Taxonomy mappings.** `A-TAX-04` (Phân bổ chi phí thuế, tiền phạt hoặc khoản tài chính không rõ ràng). `A-TAX-05` (Giá thuê và khoản thuế mâu thuẫn). `B-TAX-03` (Nộp thuế thay nhưng thiếu nghĩa vụ về hồ sơ/phối hợp của người cho thuê).
- **Seed triggers.** `thuế` / `hóa đơn` / `hoá đơn` **and** `nộp thay` / `đã bao gồm` / `chưa bao gồm` / `giá thuê`
- **Seed exclusions.** None in the JSON.
- **v2 eligibility.** Adds rental tax and filing/payment aliases and requires a tax or payment-on-behalf cue.
- **Required context.** Quoted price, included tax, payment on behalf and documentation obligations.
- **Cross-clause dependency.** Compare rent and tax clauses with the invoice and proof-of-payment provisions.
- **Potential false positives and controls.** A VAT reference on an unrelated invoice can still qualify if the passage includes rent language. VN-37 and HO-11 help test incidental invoices across neighboring heuristics.
- **Review focus.** Use the taxonomy to classify contractual cost or documentation. Refer statutory taxpayer, filing, invoice and penalty questions through legal review.

## `overlapping_remedies` — Reconcile remedies for the same breach

- **Purpose.** One missed payment or exit may trigger forfeiture, a fixed penalty and compensation calculated from the same loss.
- **Taxonomy mappings.** `B-PEN-03` (Bị áp dụng mức phạt vi phạm không rõ ràng). `B-PEN-04` (Bị yêu cầu sửa chữa và thay mới tài sản vượt quá thiệt hại thực tế). `B-DEP-03` (Điều kiện mất cọc không phù hợp với trường hợp vi phạm).
- **Seed triggers.** `phạt vi phạm` / `bồi thường` / `lãi chậm trả` **and** `mất cọc` / `khấu trừ` / `cộng dồn` / `đồng thời` / `cấn trừ`
- **Seed exclusions.** None in the JSON.
- **v2 eligibility.** Adds penalty and offset aliases. The local check looks for multiple remedy phrases or an offset. A fallback joins a referenced penalty and offset to a remedy elsewhere.
- **Required context.** Breach event, remedy formulas, loss evidence and any offsets.
- **Cross-clause dependency.** Compare default, penalty, compensation, forfeiture and settlement clauses.
- **Potential false positives and controls.** Two phrases can refer to the same remedy or different breaches. An offset can be a credit rather than another charge. HO-01 misses separate remedies joined by a different connector.
- **Review focus.** Adjudicate whether VN-44 warrants this guidance when one penalty is credited from security. Refer legality of stacking or recovery limits separately.

## `return_milestones` — Tie return obligations to a documented handover

- **Purpose.** Vacating, delivering access devices and signing a handover record may occur on different dates.
- **Taxonomy mappings.** `B-TRM-06` (Không xác định rõ hiện trạng và nghĩa vụ hoàn trả tài sản). `A-TRM-05` (Không xác định rõ hiện trạng và tiêu chí khi hoàn trả nhà). `B-PEN-05` (Bị phạt do chậm bàn giao nhà không rõ cách tính).
- **Seed triggers.** `bàn giao` / `trả nhà` **and** `chìa khóa` / `chìa khoá` / `công tơ` / `biên bản` / `chậm bàn giao`
- **Seed exclusions.** None in the JSON.
- **v2 eligibility.** Adds return and access phrases, requires a move-out cue, and can pair adjacent eligible passages with strong access or delayed-handover evidence.
- **Required context.** Initial inventory, keys and access cards, meter readings, tender and signature dates.
- **Cross-clause dependency.** Compare return criteria with late fees, rent cutoff and deposit refund triggers.
- **Potential false positives and controls.** Nearby move-in and move-out passages may be paired even if the keys refer to different events. HO-16 misses returning a room. HO-24 uses two relevant checklists at K=3.
- **Review focus.** Validate the relation to fees, rent cutoff and refund independently. Refer legal effect of receipt, tender or signature for review if asserted.

## `annex_conflict` — Resolve inconsistent annex and main-lease terms

- **Purpose.** A signed annex can revise only one term while another copy or payment schedule retains the old figure.
- **Taxonomy mappings.** `B-DEP-04` (Không có cơ chế rõ ràng để hoàn trả tiền cọc). `B-DEP-08` (Tiền thuê/phương thức thanh toán không được xác định rõ). `B-TRM-04` (Thời hạn thuê/điều kiện gia hạn không rõ ràng).
- **Seed triggers.** `phụ lục` / `thỏa thuận bổ sung` / `thoả thuận bổ sung` **and** `ưu tiên áp dụng` / `mâu thuẫn` / `thay thế` / `tiền cọc` / `giá thuê` / `thời hạn thuê`
- **Seed exclusions.** None in the JSON.
- **v2 eligibility.** Adds amendment language. The local route requires a change cue. The fallback links shared fields or a referenced fee across annex and contract passages.
- **Required context.** Signed versions, dates, scope of amendment, parties and priority wording.
- **Cross-clause dependency.** Compare the same payment, refund or term field across all versions and attachments.
- **Potential false positives and controls.** Shared field vocabulary does not prove conflict. An unexecuted attachment or an annex duplicating original terms can qualify. HO-23 misses the fee comparison when a numbered heading separates from the clause.
- **Review focus.** Test old and new amounts, scope, signatures and effective date. Review whether fee conflicts belong under the listed payment codes. Refer legal precedence or validity conclusions separately.
