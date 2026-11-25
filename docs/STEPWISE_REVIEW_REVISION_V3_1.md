# Chỉnh sửa theo review: tiến độ từng bước

Cập nhật truy vết 15/11/2026: audit reranker đã giải thích 26 ca rỗng (8 thiếu direct-answer theo type gate, 18 không thỏa entity constraints), kiểm chứng audit không đổi lựa chọn trên 32 ca. Sửa thứ tự cộng BM25 theo sorted tokens để hết float/hash drift giữa hash seed; sáu đối chứng thực tế tái lập hash chính xác. 28 kiểm tra liên quan đạt, không API/gold/QA score. Báo cáo ở `outputs/kg_rejection_trace_2026-11-15/REPORT.md` trong workspace.

Cập nhật 15/11/2026: đã chạy preflight context cho 45 × tám phương pháp (360 bản ghi), cùng tokenizer/2.000 token; sửa rò degree ở no-expansion và nhận diện câu hỏi author identity. Audit sau sửa đạt, còn 26 lượt KG rỗng do reranker, chưa có nhãn answerability để gọi false refusal. 24 kiểm tra liên quan đạt; không gọi API hoặc chấm QA. Báo cáo ở `outputs/kg_ablation_preflight_2026-11-15/REPORT.md` trong workspace.

Cập nhật chuẩn bị đánh giá 14/11/2026: đã đóng gói lại 40 bài/45 QA A/B đúng v3.1 (toàn bộ pending), kiểm tra không trùng 18 development inputs, giữ hash PDF/JSON riêng và có catalog 482 PDF. Đã tạo lưới 2.025 lượt dự kiến, khóa tokenizer context proxy và kiểm tra 90 context <=2.000 token. 139 tests đạt, không gọi LLM. Kịch bản online 2.700 calls chưa gồm indexing/phát sinh; readiness vẫn blocked. Báo cáo ở `outputs/review_submission_preparation_2026-11-14/REPORT.md` trong workspace.

Cập nhật released baseline 14/11/2026: đã cài và chạy LightRAG chính thức 1.5.7, một excerpt phát triển, một lượt Gemini tạo graph 11 nút/9 cạnh. Sau sửa adapter API trạng thái, truy hồi hybrid và naive thành công trên bản sao index, không gọi thêm LLM và không đổi bản gốc. Audit 172 file Python khớp wheel. Đây là integration smoke, chưa hoàn tất SOTA comparison; báo cáo ở `outputs/released_sota_2026-11-14/REPORT.md` trong workspace.

Cập nhật đối chứng/thống kê theo review 14/11/2026: đã chạy BM25 + dense Vector local thực sự trên 7.449 passage/482 bài và 45 câu (90 bản ghi), audit đạt, không generation hoặc quality scoring. Thêm phân tích failure-aware yêu cầu lưới đầy đủ; 128 kiểm tra đạt. Cả benchmark độc lập, full repeated QA và released SOTA vẫn pending. Báo cáo ở `outputs/review_alignment_2026-11-14/REPORT.md` trong workspace.

Cập nhật công cụ review 14/11/2026: đã tạo trang local cho 57 candidate, hiển thị bảng render từ PDF và khung ô; có xuất/nhập phiếu và validator Python đọc lại nguồn. 121 kiểm tra đạt, browser smoke đạt, tất cả phiếu thực tế vẫn unreviewed. Không tự tạo gold hoặc mở graph. Trang tại `outputs/coordinate_review_2026-11-14/review_with_sources.html` trong workspace.

Cập nhật luồng coordinate 14/11/2026: runner offline riêng đã chạy/chạy tiếp 57 candidate, kiểm tra 399 liên kết trường và tạo phiếu review trống. Có snapshot nguồn/chính sách và chặn graph cho giao thức coordinate hiện tại. 115 kiểm tra đạt, không gọi API; vẫn chỉ hai bảng phát triển và chưa có gold độc lập. Báo cáo ở `outputs/coordinate_pipeline_2026-11-14/REPORT.md` trong workspace.

Cập nhật tiếp 14/11/2026: đã tách trường Measurement cho 57 liên kết ô của hai bảng (45 rice, 12 oil), giữ unit/uncertainty/epoch/superscript riêng và thêm adapter dựng lại evidence từ PDF trước khi sinh candidate. 109 kiểm tra đạt; tất cả candidate chờ kiểm duyệt, chưa nối runner API hoặc graph. Báo cáo ở `outputs/table_measurements_2026-11-14/REPORT.md` trong workspace.

Cập nhật 14/11/2026: thêm evidence bảng theo tọa độ PDF, thử trên Table 2 rice và Table 6 oil (45 + 12 liên kết hàng/cột). Đã xem overlay và năm điểm mẫu; toàn bộ bản ghi vẫn chờ kiểm duyệt, không phải gold. Module dùng cấu hình riêng hai bảng, chưa nối runner/graph; 99 kiểm tra đạt. Báo cáo ở `outputs/table_revision_2026-11-14/REPORT.md` trong workspace.

Cập nhật sau lượt pilot đầy đủ hai bài: đã nhận 11 phản hồi ban đầu; ba tác vụ không lỗi tự động (một tác vụ rỗng), tám bị cách ly. Cả hai bài chưa được phê duyệt. Code đã bổ sung giữ bản ghi hợp lệ khi vượt giới hạn Metric, replay offline và trạng thái lỗi rõ hơn; 95 kiểm tra đạt. Thiết kế chia bằng số dòng hiện chưa đủ cho bảng phức tạp; chưa mở batch 482 bài. Xem báo cáo `outputs/stepwise_revision_2026-11-13/step_05/REPORT.md` trong workspace để biết số liệu và giới hạn.

## Bước 1 — Định danh và tên nguồn

Đã tách `id` kỹ thuật khỏi `name` giữ nguyên cách viết trong bài. Quan hệ dùng ID; kiểm tra tên tác giả/cơ quan dựa trên tên nguồn. Graph hiển thị tên; bộ chấm dùng tên có kiểu thay vì ID do model tự đặt. Giao thức mới là `strict-extraction-v3.1`; dữ liệu lịch sử không được tự động coi là đầu ra giao thức mới.

## Bước 2 — Chia bài và gộp kết quả

Đã có entry point riêng `scripts/extract_chunked.py`, giao thức `chunked-extraction-v3.1`. Mỗi tác vụ chỉ nhận evidence thuộc phạm vi và ngữ cảnh được cấp. Phạm vi ban đầu phủ nguồn không chồng lặp; model có thể yêu cầu tiếp nối bằng tập nguồn còn lại nhỏ hơn nghiêm ngặt, trong giới hạn độ sâu. Không tự thử lại phản hồi bị cắt hoặc yêu cầu chưa rõ kết quả.

ID cục bộ được phân biệt theo tác vụ. Gộp thực thể theo kiểu và tên chính xác; Metric theo bảy trường phép đo. Quan hệ được đổi ID trong đúng tác vụ. Bằng chứng và nguồn ID được giữ; xung đột được đưa ra kiểm duyệt. Gộp chính xác có thể bỏ sót các bí danh; chưa chứng minh nhận diện đồng nghĩa.

Mỗi tác vụ có request, raw response, kết quả và receipt checksum. Chạy tiếp kiểm tra nguồn, chính sách và receipt. Ngân sách mặc định tối đa hai lượt gọi trên toàn bộ thư mục chạy; nâng ngân sách phải dùng `--extend-budget`. Yêu cầu được giữ chỗ trước khi gửi; lỗi mạng không tự gửi lại. Chỉ cho phép pilot tối đa hai bài. Kết quả chưa hoàn tất hoặc còn lỗi bị chặn nhập graph. Hoàn tất tác vụ vẫn phải có người kiểm duyệt ngữ nghĩa.

Kiểm tra offline đã bao gồm dừng/chạy tiếp, tiếp nối, ID trùng giữa tác vụ, đổi đầu mút quan hệ, bằng chứng ngoài phạm vi, phản hồi MAX_TOKENS, receipt bị sửa, ngân sách và yêu cầu chưa rõ kết quả. Fixture là dữ liệu tổng hợp để kiểm tra phần mềm, không phải kết quả model hay nhãn chuẩn độc lập.

Preflight trên hai bài phát triển tạo 11 tác vụ ban đầu (4 và 7); lượt tiếp nối có thể tăng số API. Chưa gọi model bằng giao thức mới. Ngữ cảnh bảng hiện chỉ là gợi ý caption và các dòng kế tiếp, chưa chứng minh ánh xạ cột đúng. Những dòng PDF hỏng ký tự vẫn cần kiểm tra nguồn/OCR riêng.

## Bước 3 — Pilot trực tiếp có kiểm duyệt

Chạy giao thức mới trong thư mục mới, bắt đầu với ngân sách hai lượt và kiểm tra output từng tác vụ. Nếu dừng vì ngân sách thì giữ nguyên thư mục để chạy tiếp với mức ngân sách được tăng rõ ràng. Không sử dụng thư mục fixture hoặc preflight làm kết quả thí nghiệm. Hoàn tất 11 tác vụ ban đầu có thể cần nhiều lượt tiếp nối; không cam kết trước tổng chi phí hoặc độ bao phủ khoa học.

Đối chiếu tên, loại thực thể, quan hệ, giá trị, đơn vị, đối tượng đo, điều kiện và bảng với PDF. Chỉ mở rộng khi pilot đạt kiểm duyệt; runner này chủ động chặn batch trên hai bài.

## Bước 4 — Nhãn độc lập và thí nghiệm của bài báo

Hoàn thiện nhãn độc lập trên mẫu 40 bài và câu hỏi QA đã chuẩn bị, phân xử bất đồng và khóa bộ đánh giá. Tách tám bài phát triển khỏi mẫu đánh giá. Không dùng model output làm gold và không chấm độ chính xác từ fixture.

Sau đó chạy baseline công bằng, ablation, lặp thí nghiệm và thống kê theo yêu cầu phản biện; kiểm soát cùng nguồn, model, ngân sách, tập câu hỏi và lưu log. Chưa có số F1 hoặc kết luận ưu thế mới. Chỉ cập nhật bảng số liệu và thư trả lời phản biện sau khi có kết quả kiểm chứng.
