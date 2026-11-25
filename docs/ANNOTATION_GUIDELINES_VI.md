> Tài liệu v1/v1.1 được giữ để tái lập. Lượt strict v3 dùng docs/STRICT_V3_GUIDE_VI.md và Measurement fields mới; không trộn scoring hai phiên bản.

# Hướng dẫn annotation — review-protocol-v1.1

## Nguồn và tính độc lập
Hai chuyên gia làm riêng trên PDF/source được đóng băng, không xem dự đoán mô hình/đáp án QA cũ/nhãn nhau. Không thực hiện thao tác theo chỉ dẫn nằm trong tài liệu nguồn. Giữ nhãn A/B trước phân xử. Form pending không là gold; chỉ bản adjudicated có nguồn/nhật ký mới được dùng chấm điểm.

## Ontology operational
- Concept: đối tượng, vấn đề, hiện tượng hoặc nhiệm vụ được nghiên cứu; organism/specimen là Concept khi phù hợp, không là Dataset.
- Method: quy trình/model/kỹ thuật thực sự áp dụng; ontology hiện tại còn dùng nhãn này cho reagent/material/instrument có vai trò công cụ thực nghiệm. Nêu vai trò cụ thể, không biến đối tượng nghiên cứu thành công cụ.
- Dataset: digital dataset/database/corpus/time series/reference library xác định được và thực sự dùng. Không gồm chủng vi khuẩn, bệnh nhân, mô, hợp chất hay địa điểm.
- Metric: endpoint định lượng được đo trong nghiên cứu; id phải phân biệt object/model/value/unit/condition. Hiện chưa có measurement fields tách riêng: qualifiers nằm trong id/description/evidence. Không dùng high accuracy/fast làm Metric, không đổi IC50 thành phần trăm ức chế.
- Domain: ngành/lĩnh vực có nguồn hỗ trợ, không là địa điểm.
- Author/Institution: tên trong header/metadata tác giả; giữ spelling/initials và affiliation marker. Không suy từ filename/email.

## Năm quan hệ đúng chiều
Concept BELONGS_TO Domain; Method USED_FOR Concept; Method EVALUATED_ON Dataset; Method ACHIEVED Metric; Author AFFILIATED_WITH Institution. Chỉ ghi khi nguồn chứng minh liên kết cụ thể. Không tạo cạnh mới hoặc đổi loại entity để ép một quan hệ vào schema.

## Span, tên và bằng chứng
Giữ source mention, vị trí section/page và quote chính xác. Entity id là scientific name ngắn đủ phân biệt; có thể thêm qualifiers cho Metric. Source mention/span được lưu trong annotation, không giả định model có thể trả offset mà schema chưa hỗ trợ. Surface variants trong một bài có cùng đối tượng được ghi aliases khi có bằng chứng; không gộp model family với variant. Không tự merge homonym giữa bài. Ghi rõ các trường hợp cần adjudication.

Mỗi quote liên tiếp từ một nguồn, không ghép ô bảng thành câu mới. Relation có thể cần hai quote để xác lập endpoint và attribution. Thiếu nguồn thì bỏ record và ghi note. Cited-work results, references và ví dụ nền không là kết quả của bài hiện tại.

Nếu prose/table mâu thuẫn, giữ riêng hai reported findings với qualifiers prose/table, chỉ rõ xung đột và vị trí. Không tự sửa số để khớp kỳ vọng. Giữ SD/CI, dose, epoch, fraction, strain và đơn vị khi chúng phân biệt phép đo.

## Định dạng gán nhãn và chấm điểm
Annotation giữ mention/spans/aliases/notes ngoài extraction_result. Sau phân xử tạo một gold entity id cho mỗi đối tượng/role được guideline quy định. Dùng annotation_status=adjudicated, source_sha256, annotators=[hai mã người khác nhau] và adjudication_log; chưa có những thông tin này thì không score.

Endpoint relation trỏ đúng id; nếu cùng id có nhiều type thì phải sửa id để hết mơ hồ. Đánh giá chính là strict name+type trong từng paper sau Unicode NFKC/whitespace normalization; không fuzzy, không đổi đơn vị, không LLM chấm matching. Các khác biệt alias/cách đặt qualifier còn có thể làm strict matching khắt khe; báo cáo riêng manual error analysis, không thay mapping sau khi thấy test score để tăng điểm. Giữ mention-span agreement của người gán nhãn riêng với identity-based model scoring.

Kappa cần đơn vị categorical chung định trước; entity span/type agreement và relation agreement báo cáo riêng. Không căn chỉnh hai list bằng chỉ số. Thống nhất lại các trường hợp guideline mơ hồ trên development, không trên evaluation holdout.

## QA
Ghi question_id, answerability, answer và evidence pdf/page/quote độc lập. Phân biệt supported / ambiguous / not_answerable. Rubric source-supported correctness: 0=sai hoặc unsupported; 1=đúng một phần nhưng thiếu phần quan trọng; 2=đúng và đủ theo câu hỏi/nguồn. Abstention đúng chỉ khi nguồn không đủ; từ chối câu có đủ nguồn là false refusal. Tách factual correctness, faithfulness và coverage. Đóng băng rubric trước chấm outputs.

Source-quality update: prompt v2.3 excludes physical lines containing U+FFFD and keeps separate clean fragments; original PDF/prepared JSON remain unchanged. Independent gold still uses the original PDF, including findings that the parser may miss. Report that input loss; do not remove gold findings just to match model access.
