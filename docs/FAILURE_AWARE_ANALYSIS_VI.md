# Phân tích có tính lỗi sinh câu trả lời

Đây là giao thức phân tích mới cho các lượt chạy mới, không chuyển đổi ngầm log lịch sử. `revision_statistics.py` cũ vẫn là conditional-success để tái lập; `failure_aware_statistics.py` xử lý lưới chạy đầy đủ theo thiết kế khai báo trước.

Mỗi dòng phải có `method`, `question_id`, `repeat`, `generation_status` (`success` hoặc `failed`) và `attempt_seconds` đo thực tế. Dòng thành công còn cần `assessment_source` (`independent_human` hoặc `llm_proxy`) và các metric [0,1] đã được quan sát. Không trộn nhãn chuyên gia với judge model trong cùng phân tích. Cột `error` cũ không đủ để suy ra thất bại xảy ra ở generation hay judging.

`failed` được tính utility chất lượng bằng 0 theo quy ước đã khai báo; không giả tạo điểm chấm chuyên gia cho dòng đó. Lượt thiếu hoàn toàn, duplicate, thiếu điểm ở dòng thành công hoặc thiếu thời gian thực tế làm phân tích thất bại. Latency không bị gán 0; thời gian attempt thành công/thất bại được báo riêng.

Lấy trung bình các repeats trong từng question trước khi tính chênh lệch paired, bootstrap và sign-flip; Wilcoxon bổ sung nếu SciPy có sẵn. Holm áp dụng cho họ so sánh method × metric đã khai báo. Không coi 45 × 5 là 225 câu hỏi độc lập. Chưa có dữ liệu thật đủ điều kiện nên hiện chưa tính p-value hay CI cho kết quả bài báo.

File design phải khai báo chính xác năm trường: `methods`, `question_ids`, `repeats`, `reference`, `metrics`. Lưới thực tế bắt buộc khớp tích Descartes của thiết kế; nên khóa hash design trước khi chạy dữ liệu đánh giá. Baseline released SOTA phải có tên/phiên bản thật trước khi khóa design; không đổi tên snapshot graph thành LightRAG.

```powershell
python src/evaluation/failure_aware_statistics.py --records run/results.jsonl --design run/locked_design.json --output analysis_new.json
```

Đây là code kiểm chứng bằng fixture, không phải bằng chứng thí nghiệm hoàn thành. Việc đánh giá độc lập, đủ năm lần lặp, fairness và so sánh SOTA vẫn là các điều kiện riêng.
