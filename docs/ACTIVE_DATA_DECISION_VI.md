# Dữ liệu được chọn — 16/11/2026

Theo quyết định của người dùng: dùng lại các file extraction lịch sử, không extract lại corpus.

- Input extraction: `C:\Users\Admin\Documents\Codex\2026-11-11\t\outputs\rerun_2026-11-12\frozen_dataset_repaired\extracted`.
- Ngữ cảnh controlled đã chuẩn bị: `C:\Users\Admin\Documents\Codex\2026-11-11\t\outputs\review_offline_v3_2026-11-15\source_scoped\all_eight_methods.jsonl`.
- Không dùng candidates hoặc phản hồi bị cắt trong `outputs/extraction_pilot_2026-11-16/live`.
- Giữ nguyên snapshot gốc. Mọi sửa dữ liệu sau này phải tạo phiên bản riêng, có nhật ký và dựng lại artifacts phụ thuộc; không sửa ngữ cảnh đã khóa rồi dùng kết quả cũ.
- Chất lượng: historical extraction, chưa được xác nhận độc lập; không gọi là strict-v3.1 reextraction hoặc approved gold. Việc chọn dùng không phải phê duyệt mọi record.
- Các vấn đề đã biết vẫn mở: endpoint/chiều quan hệ, ký tự đơn vị và mâu thuẫn nguồn trong mẫu kiểm tra; 235 quan hệ chưa ánh xạ và 26 ngữ cảnh KG rỗng trong audit trước.
- Không tự suy đoán/sửa đơn vị mâu thuẫn hoặc tạo endpoint thiếu. Không ghi các dữ liệu này vào Neo4j sản xuất chỉ dựa trên quyết định lựa chọn input.
- Ngân sách extraction lại được loại khỏi kế hoạch hiện tại. Chạy sinh QA/verification và LightRAG vẫn cần ngân sách riêng; quyết định này không tự cấp thêm lượt gọi API.

Đối chiếu mẫu: `outputs/extract_source_spotcheck_2026-11-16/REPORT_VI.md`. Các bước kế tiếp sử dụng track historical này và công bố giới hạn tương ứng trong bài.

## Chuẩn bị generation mới ngày 16/11/2026

Đầu vào matched đã chuẩn bị mới: `C:\Users\Admin\Documents\Codex\2026-11-11\t\outputs\review_execution_2026-11-16\matched_study\contexts.jsonl` (360 records, 8 methods). Đây là phiên bản riêng có metadata/source scope/planner đã sửa; context `review_offline_v3_2026-11-15` được giữ để tái lập lịch sử, không trộn vào lượt generation mới.

Pilot mới chỉ hoàn thành một record rồi gặp request in doubt; không có phê duyệt chạy lớn hoặc kết quả QA chính thức. Xem `outputs/review_execution_2026-11-16/REPORT_VI.md` trước khi chạy tiếp; không tự retry/migrate request lỗi.
