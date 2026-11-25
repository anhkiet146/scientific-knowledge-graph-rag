# Ontology dùng cho thí nghiệm sửa bài theo review

Trạng thái: thiết kế và kiểm thử bằng code; chưa chứng minh độ chính xác extraction, chưa thay thế nhãn chuyên gia độc lập.

## Phiên bản và phạm vi

`legacy-v3.1` giữ bảy loại thực thể và năm loại quan hệ của pipeline strict cũ. Các dữ liệu lịch sử được giữ nguyên.

`composition-experimental-v1` thêm đúng một quan hệ cấu thành giữa phương pháp. Protocol được ghi là `chunked-extraction-v3.2-experimental`. Cần chọn rõ cấu hình này; mặc định vẫn là legacy. Bộ nạp production hiện từ chối cấu hình thử nghiệm.

Review không trực tiếp yêu cầu bổ sung quan hệ này. Đây là lựa chọn thiết kế để công bố rõ giới hạn biểu diễn của ontology cũ, không phải một kết quả đáp ứng review hoặc cải thiện đã được đo.

## Định nghĩa thực thể

| Loại | Định nghĩa | Không dùng cho |
|---|---|---|
| Concept | Đối tượng, nhiệm vụ hoặc hiện tượng được nghiên cứu | Đổi một thuật toán thành Concept chỉ để quan hệ hợp lệ |
| Method | Phương pháp, mô hình, quy trình hoặc công cụ thực sự được dùng | Kỹ thuật chỉ xuất hiện trong danh mục tham khảo |
| Dataset | Tập dữ liệu số được xác định trong nghiên cứu | Mẫu sinh học hoặc bản thân phần mềm mô phỏng |
| Metric | Kết quả đo có giá trị số, đối tượng, điều kiện và nguồn hỗ trợ | Nhận xét “improved”, “fast”, “high”; số phiên bản hoặc tham số cài đặt đơn thuần |
| Domain | Ngành hoặc lĩnh vực khoa học | Quốc gia, địa phương hoặc tên tổ chức |
| Author | Tác giả của bài hiện tại, có bằng chứng ở phần đầu bài | Tác giả của bài được trích dẫn |
| Institution | Cơ quan của tác giả, có bằng chứng ở phần đầu bài | Tự suy diễn liên kết mọi tác giả với mọi cơ quan |

Ví dụ: phần mềm mô phỏng có thể là Method nếu là công cụ nghiên cứu thực sự. Không gọi phần mềm đó là Dataset; tập dữ liệu được phần mềm sinh ra chỉ là Dataset khi bài xác định rõ tập đó. Kiểm tra kiểu bằng code chưa chứng minh phân loại ngữ nghĩa đúng.

## Định nghĩa quan hệ

| Quan hệ | Chiều và kiểu | Điều kiện |
|---|---|---|
| BELONGS_TO | Concept → Domain | Bằng chứng xác định lĩnh vực của đối tượng |
| USED_FOR | Method → Concept | Phương pháp được dùng cho nhiệm vụ/đối tượng đó |
| EVALUATED_ON | Method → Dataset | Phương pháp được đánh giá trên tập dữ liệu số đó |
| ACHIEVED | Method → Metric | Kết quả đo số gắn đúng phương pháp, điều kiện và nguồn |
| AFFILIATED_WITH | Author → Institution | Có bằng chứng liên kết cụ thể ở phần đầu bài |
| HAS_COMPONENT | Method → Method; chỉ cấu hình thử nghiệm | Bài nói rõ phương pháp nguồn tích hợp phương pháp đích như một thành phần vận hành |

HAS_COMPONENT không dùng cho hai kỹ thuật cùng được nhắc tới, so sánh, trích dẫn hoặc cùng áp dụng cho một bài toán. Không tạo cạnh tự trỏ. Không tự chuyển USED_FOR sai kiểu thành HAS_COMPONENT. Không thêm cạnh từ đáp án tham chiếu.

Ví dụ minh họa tự tạo: “Method A incorporates Method B as an operational component” hỗ trợ kiểm tra cấu trúc A HAS_COMPONENT B. “Method A is compared with Method B” không đủ hỗ trợ. Validator hiện kiểm tra kiểu, nguồn trích dẫn và phạm vi; việc xác nhận quan hệ được câu văn diễn đạt đúng vẫn cần kiểm tra ngữ nghĩa.

## Hợp đồng bằng chứng và thực thi

- Chỉ chọn ID từ scope/context của tác vụ; tối đa 16 ID cho một bản ghi.
- Quan hệ nội dung cần ít nhất một ID thuộc scope, không chỉ phần context dùng để hiểu bài.
- Không cắt bớt bằng chứng quá dài hoặc sửa kiểu thực thể tự động để làm bản ghi đạt kiểm tra.
- Prompt, schema, validator và bước gộp dùng cùng cấu hình ontology; lưu cấu hình và hash trong manifest.
- Kết quả thiếu, sai hoặc chưa rõ nguồn được ghi trạng thái riêng; không mặc định cho điểm chất lượng bằng 0 hoặc coi là dữ liệu đúng.

## Áp dụng vào đánh giá theo review

1. Chốt cấu hình và corpus trước lượt chạy so sánh. Bộ nguồn 488 hiện chưa có extraction hoàn chỉnh cho sáu bài bổ sung.
2. Nếu thử ontology mở rộng, giữ một nhánh kết quả riêng. Không gộp kết quả dùng hai ontology thành một bảng duy nhất mà không phân biệt.
3. Đánh giá đóng góp graph expansion, normalization và ranking bằng các nhánh ablation cùng dữ liệu, model, câu hỏi và giới hạn ngữ cảnh.
4. Nhãn extraction và reference QA hiện có vẫn chờ kiểm chứng độc lập. Các câu hỏi đã được dùng phát triển; không gọi là tập kiểm tra chưa từng thấy.
5. Ghi lại lỗi extraction, mất chi tiết nguồn, vượt giới hạn, lỗi API và giới hạn biểu diễn. Không coi tỷ lệ qua validator hoặc số câu có context là độ chính xác QA.

## Kiểm tra đã làm

Hai phản hồi CuRLA được kiểm tra lại bằng cả hai cấu hình, không gọi API và không sửa phản hồi. Cả hai vẫn bị cách ly; việc thêm HAS_COMPONENT không làm các quan hệ USED_FOR sai kiểu trở thành đúng. Đây là kiểm tra khả năng tái lập và cơ chế chặn lỗi, không phải chứng minh cải thiện chất lượng.
