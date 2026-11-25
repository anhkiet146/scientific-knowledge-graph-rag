# Strict extraction v3.0 — hướng dẫn và giới hạn

## Thay đổi mặc định
scripts/extract_entities.py và src/extraction/extract_entities.py hiện chạy strict_runner.py. Mặc định chỉ chọn tối đa 2 bài và dành tối đa 2 API calls cho một thư mục run. Không tự retry phản hồi lỗi/cắt ngắn. Đường reextract_review.py cũ chỉ còn để tái lập: muốn gọi API phải bật --legacy-quote-transport rõ ràng; preflight cũ vẫn được phép. Không trộn output cũ với v3.

## Bằng chứng và Measurement
Model chỉ trả evidence_ids; code lấy exact text và character offsets từ catalog có fingerprint theo nguồn. ID có namespace riêng theo source; ID không có thật, offset âm/bool hoặc catalog bị đổi bị từ chối. Nội dung tài liệu không có quyền tự khai báo body là header tác giả. Dòng U+FFFD vẫn bị tách khỏi bằng chứng, nguồn gốc không bị sửa.

Metric bắt buộc có measurement gồm 7 chuỗi: endpoint, value, unit, object, condition, uncertainty, source_report (abstract/prose/table). value là số hoặc khoảng số thực sự đo, không phải phiên bản model. Các trường phải được chứng minh trong evidence chọn; không tự đổi đơn vị. Kiểm tra biên token tránh N1 khớp N10, g/mL khớp mg/mL hay 0.91 khớp 10.91. Unit có thể dính với số như 91.2% hoặc 3.21mg/mL. Table result cần caption/context bảng, row và headers; code chưa tự chứng minh ánh xạ đúng ô/cột.

## Trạng thái và review
Không có trạng thái tự động approved. Candidate đúng cấu trúc là pending_semantic_review; lỗi cấu trúc, unknown IDs hoặc Measurement sai làm quarantined. Nguồn mâu thuẫn được giữ riêng và gắn blocking_issues. Human review phải gắn đúng hash toàn bộ candidate; không sửa file candidate rồi dùng xác nhận cũ.

Source conflict hợp lệ có thể được reviewer giữ lại qua acknowledged_issues, với hash của issue, disposition retain_source_conflict và ghi chú. Alias nghi ngờ chỉ được xác nhận distinct bằng confirmed_distinct_entities; Dataset nghi ngờ specimen cần confirmed_digital_dataset và bằng chứng. Đây là attestation của workflow, không phải xác thực danh tính hay independent gold.

Graph loader kiểm tra toàn bộ paper trước khi mở transaction, không nuốt lỗi hoặc sanitize nhãn lạ thành nhãn có vẻ hợp lệ. Scientific labels/endpoints đúng schema; provenance dùng MENTIONS. Query result được consume trong transaction để bắt cả lỗi trả chậm. Mỗi paper atomic; toàn bộ folder không phải một transaction. Các paper đã commit trước lỗi của paper sau vẫn tồn tại. Không tự xóa hoặc sửa graph live.

Metric node dùng record_key gắn paper/id/measurement, tránh hai bài khác số liệu bị gộp vì cùng tên metric. Các non-Metric name/type vẫn dùng exact identity, còn nguy cơ homonym cần review. Chỉ build trên graph benchmark tách riêng, không trộn nhiều phiên bản chạy.

## Chạy offline
Từ thư mục repo/source:
python scripts/extract_entities.py --input <parsed_source_dir> --output <new_run_dir> --preflight --max-api-calls 0

Kiểm tra bằng model-output fixtures tự tạo, không có network:
python scripts/extract_entities.py --input <source_dir> --output <new_fixture_run> --offline-responses <response_dir>

Fixture filenames phải khớp input. Transport response chỉ có entities/relations, dùng evidence_ids đã xây từ nguồn. Fixture run được gắn offline_fixture; không dùng làm bằng chứng model accuracy. Exit 2 nghĩa có candidate bị quarantine; exit 3 nghĩa đã chạm budget hoặc API bị chặn. Exit 0 chỉ nói xử lý xong, không nói approved cho graph.

Live pilot mới khi đủ quota:
python scripts/extract_entities.py --input <two_dev_sources> --output <new_live_run> --keys-file <private_keys_file> --max-api-calls 2

Các thư mục lồng nhau giữa input/output bị cấm. Run lock ngăn hai writer trên cùng output; lock cũ sau crash phải kiểm tra trước khi phục hồi. Manifest gắn code/prompt/schema/source/budget. Request được ghi trước API, giữ budget reservation qua resume. Request dở mà không có response sẽ chặn tự gọi lại; raw response đã lưu có thể được xử lý lại mà không trả thêm API. Mọi sửa request/response/catalog/candidate sau receipt đều bị phát hiện khi resume.

Chạy --all hoặc --limit > 2 cần --pilot-acceptance trỏ tới attestation có decision=passed, reviewer, policy_sha256, pilot_directory, manifest_sha256 và reviews theo filename. Code kiểm tra live pilot đúng policy với hai bài, receipt/hashes và review của từng candidate. Preflight hoặc offline fixtures không đủ. Không tự tạo file passed từ unit tests.

## Upload / commit API
Batch và upload dùng chung strict schema, evidence resolver và validator. Web PDF parser nay giữ page-level text thay vì chỉ đoạn văn GROBID; GROBID vẫn cần để lấy metadata. Header, column order, rotated text và OCR vẫn cần audit.

Mongo lưu nguyên candidate/provenance, preview trả candidate_sha256. POST commit cần body reviewer, notes, payload_sha256 và acknowledged_issues nếu có. Frontend cũ chỉ bấm commit không gửi review sẽ nhận HTTP 409; cần cập nhật client để gửi hợp đồng này sau khi người dùng thực sự rà soát. Không có cơ chế tự phê duyệt từ model.

Upload SDK đặt attempts=1 để tắt retry trả phí ngầm. Mongo claim committing bằng compare-and-set chống hai request commit đồng thời. Neo4j transaction và Mongo status không có distributed transaction: lỗi không xác định để lại commit_in_doubt và trả HTTP 503; cần kiểm tra trước khi thử lại. Chưa triển khai authentication mới; tên reviewer là thông tin khai báo, không phải chữ ký xác thực.

## Scoring / annotation
V3 Metric được match theo chính xác 7 measurement fields trong paper, không theo opaque id như m1. Relation dùng typed semantic endpoint identity. Non-Metric vẫn exact typed name, NFKC/whitespace only. Không fuzzy matching hay unit conversion. Gold cũ thiếu Measurement không thể chấm lẫn như cùng protocol. Người gán nhãn làm độc lập từ PDF gốc, ghi measurement và evidence, không xem model predictions. Không bỏ gold finding chỉ vì parser/model không đọc được. Scoring vẫn chặn nhãn pending, duplicate gold và source hash không khớp.

## Những điều chưa được chứng minh
Tests và fixtures kiểm chứng logic kỹ thuật. Chưa gọi live API v3 hoặc chạy Mongo/Neo4j thật trong lượt hardening này. Không tuyên bố tăng F1, giảm hallucination hoặc giảm chi phí. Đúng quote/ID/token không chứng minh claim được entail; model vẫn có thể chọn nhầm row/column hoặc gán sai vai trò. Cần pilot thật, review chuyên môn và gold độc lập trước full benchmark. Schema số hiện cố ý bảo thủ: những biểu thức/locale số không hỗ trợ sẽ bị quarantine, không tự đoán.
