# legal_corpus: provenance

Plain-text statute copies for the retrieval index. Fetched 2026-10-16 from `ketoananpha.vn`
(a commercial accounting-services site, NOT an official gazette). Page chrome, ads and the
table of contents were stripped; article text is as published on that site. **Not yet checked
against the official publication** (congbao.chinhphu.vn / vbpl.vn); quotes cited to users must be.

| File | Document | Điều | Notes |
|---|---|---|---|
| luat_cu_tru_68_2020.txt | Luật Cư trú 68/2020/QH14 | 38 | Original 2020 text. One later amendment (effective 2026-01-01) is NOT applied. |
| luat_quan_ly_thue_108_2025.txt | Luật Quản lý thuế 108/2025/QH15 | 53 | Most of it in force from 2026-07-01; Điều 26 (e-invoice) from 2026-01-01. |
| nd68_2026.txt | NĐ 68/2026/NĐ-CP (household / individual business tax) | 19 | Signed 2026-03-05. Amended by NĐ 141/2026, which changes "500 triệu đồng" to "01 tỷ đồng" in Điều 3, 4, 8, 9, 10, 11, 12, 17, 18 (confirmed from its text). This file still shows 500 triệu; apply the amendment before quoting figures. |
| nd141_2026.txt | NĐ 141/2026/NĐ-CP, amends NĐ 68/2026 | 5 | Amending text only, not a consolidated version. |
| tt18_2026_btc.txt | TT 18/2026/TT-BTC (tax procedures for household / individual business) | 9 | Guides NĐ 68/2026. Form templates (Mẫu) at the end were dropped. |
| nd254_2026.txt | NĐ 254/2026/NĐ-CP (e-invoices under Luật QLT 108/2025) | 45 | Its guiding circular is TT 91/2026/TT-BTC (not fetched). |

Taxonomy citations these cover: Luật Cư trú Điều 27/28/30, Luật QLT Điều 26, NĐ 68/2026,
NĐ 254/2026, TT 18/2026. Luật Nhà ở 2013 (cited by B-AUT-03) is deliberately not fetched; it is
superseded by Luật Nhà ở 2023 and the citation looks like a typo.

## Official scans (vanban.chinhphu.vn), OCR'd 2026-10-18

Signed PDFs downloaded from `vanban.chinhphu.vn` (the official source). They are scans with no text layer, so the
text was read by a vision model (Qwen3.5-9B Q8_0 + mmproj-F32, local, through `ingest()`; ~10 s/page, no `[?]`
marks). **OCR errors remain** (seen in signature blocks: "THỦ TRƯỞNG" for THỨ TRƯỞNG, "Công TTĐT" for Cổng);
check a quote against the PDF before showing it to a user. The PDFs are not committed (`.gitignore`); match a
local copy by sha256.

Edits after OCR: the digital-signature stamp line ("Ký bởi" / "Người ký") removed from the top of each file;
appendices dropped (forms and annex tables, no articles); three headings restored from the page images, where the
model turned bold mixed case into capitals or dropped the period (NĐ 181 Điều 7, NĐ 125 Điều 13 and 29); NĐ 125
page 1, returned as one line, split back into lines; TT 20 Điều 1 heading split from its body.

| File | Document | Điều | PDF (sha256) | Notes |
|---|---|---|---|---|
| nd125_2020.txt | NĐ 125/2020/NĐ-CP (administrative penalties: tax, invoices) | 47 | `125.signed.pdf` `965d027aade955b2f187c4651d9669204ceb612801793edc11be5597674c3356` | Original 2020 text. Amended by NĐ 310/2025 from 2026-01-16; **no official consolidated text (VBHN) exists**, apply nd310 before quoting. Appendix of forms (Mẫu BB/QĐ) dropped. |
| nd310_2025.txt | NĐ 310/2025/NĐ-CP, amends NĐ 125/2020 | 4 | `310-cp.signed.pdf` `9c8a7f4ae823f42b396830912f82c65524b78081dbc6a8a604ba803f2b0d962d` | Amending text only. In force 2026-01-16. |
| nd181_2025.txt | NĐ 181/2025/NĐ-CP (VAT, guides Luật Thuế GTGT 48/2024) | 40 | `181nd.signed.pdf` `63777bd1640c91598f95ee40e3d793cf9422afc123ae79bb75f83dd183d74157` | In force 2025-07-01. Điều 26: non-cash payment as a condition for input VAT deduction. Appendices I–V (resource tables, refund forms) dropped. |
| tt20_2026_btc.txt | TT 20/2026/TT-BTC (corporate income tax) | 10 | `20-btc.pdf` `babcb501e6850d8068b8d608f94d8bccbb47ef4da99f5177616e659bf7912ec1` | In force 2026-03-12, replaces TT 78/2014 and TT 96/2015. Guides Luật Thuế TNDN 2025 and NĐ 320/2025 (neither in the KB). Forms 01–02/TNDN dropped. |

Replaced statutes still cited by the taxonomy (fix in the workbook, do not fetch): NĐ 123/2020 and NĐ 70/2025
(invoices) → NĐ 254/2026 from 2026-07-01; TT 96/2015 → TT 20/2026 from 2026-03-12. Article numbers do not carry
over between a statute and its replacement.
