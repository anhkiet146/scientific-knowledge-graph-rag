# Phiếu độc lập v3.1 — không dùng prediction làm gold

Hai chuyên gia làm riêng trên PDF gốc, không xem output mô hình, đáp án cũ hoặc nhãn nhau. Bộ phiếu này chưa có nhãn. Không gọi model để điền thay chuyên gia. Những đoạn chữ bị parser loại không làm mất trách nhiệm gán nhãn theo PDF; ghi nhận lỗi parser riêng.

`id` là khóa kỹ thuật trong bài, còn `name` là tên giữ spelling nguồn. Quan hệ trỏ `id`. Author/Institution dùng bằng chứng header. Domain là ngành khoa học, không phải địa danh; Dataset là dữ liệu số, không phải mẫu sinh học. Không đổi loại entity để ép cạnh.

Metric cần bảy chuỗi `measurement`: endpoint, value, unit, object, condition, uncertainty, source_report. Giữ giá trị/đơn vị/điều kiện và báo cáo prose/table khác nhau, không tự đổi đơn vị hoặc hòa giải bất nhất nguồn. Tách chữ superscript khỏi số và giữ ghi chú. Mô tả high/fast không phải phép đo số.

Năm quan hệ được giữ nguyên: Concept BELONGS_TO Domain; Method USED_FOR Concept; Method EVALUATED_ON Dataset; Method ACHIEVED Metric; Author AFFILIATED_WITH Institution. Chỉ ghi liên kết cụ thể được nguồn hỗ trợ. Không tạo Method chỉ để nối một Metric không có quan hệ phù hợp.

Mỗi quote phải liên tiếp, có file/trang/section. Không biến các ô rời thành một câu trích nguyên văn. Có thể đính kèm ghi chú tọa độ bảng; trước khi chuyển annotation sang scorer phải có adapter bằng chứng được kiểm chứng. `source_sha256` trỏ JSON chuẩn bị; `source_pdf_sha256` trỏ PDF đầy đủ. Hai hash có vai trò khác nhau.

Mỗi chuyên gia hoàn thành độc lập và ký thông tin completed_by/completed_at/independence_attestation. Không tự đánh dấu adjudicated. Giữ nguyên A/B, phân xử thành file gold riêng với hai mã annotator khác nhau và log; tính agreement trên đơn vị định trước, không khớp list theo thứ tự.

QA: ghi câu trả lời, supported/ambiguous/not_answerable và evidence PDF/trang/quote. Correctness rubric 0=sai/không có nguồn, 1=đúng một phần, 2=đúng và đủ. Nếu dùng bộ phân tích [0,1], khai báo trước `correctness = raw_rubric_score / 2`; giữ cả điểm thô và provenance độc lập. Phân biệt unsupported claim với từ chối sai một câu có đủ nguồn.

Không mở xem hoặc chỉnh kết quả test để điều chỉnh mapping/weights. Bộ 57 candidate bảng là development và không điền vào 40 bài holdout này.
