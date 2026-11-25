# Phương pháp xếp hạng và phân tích theo review

Tài liệu cho runner snapshot phát triển ngày 16/11/2026. Không giả định đây là toàn bộ hành vi Neo4j production hoặc cơ sở để phục dựng các phép đo latency lịch sử. Implementation tham chiếu: `src/retrieval/hybrid_retrieval.py`, hàm `rerank_candidates` và các helper liên quan.

## Chín tín hiệu

Các đại lượng được tính trên cùng tập candidate C cho mỗi câu. Chuỗi được chuẩn hóa/tokenize bằng helper trong code; Q và X là tập token, không phải embedding. Giá trị 0.5 khi thiếu một số ràng buộc là giá trị mặc định kỹ thuật, không phải xác suất đúng.

| Tín hiệu | Công thức hoặc bước tính hiện hành |
|---|---|
| semantic | min(1, 0.55 × token-overlap + 0.30 × phrase-hit + 0.15 × name-similarity). overlap = số token giao / sqrt(số token Q × số token X). phrase-hit = 1 khi ít nhất một search term nằm trong entity text, ngược lại 0. name-similarity dùng SequenceMatcher giữa query và tên. X gồm tên, loại, mô tả, connections và tiêu đề nguồn. Đây là lexical proxy, không gọi embedding model. |
| entity | Tỷ lệ các plan.entities có mặt trong tên/mô tả/tiêu đề/neighbor names. Không có entity constraint thì 0.5. Đây là phép match truy xuất, không phải quyết định identity normalization. |
| answer_type | Với nhánh thông thường: 1 khi label phù hợp expected_labels, 0.35 cho Paper/Concept hỗ trợ không trực tiếp, 0 nếu không phù hợp; expected rỗng thì 0.5. Các nhánh method/solvent/principle/process/taxonomy/relationship có heuristic riêng theo role, relation hoặc keyword; phải giữ cùng code hash khi so sánh. Không gọi nhánh heuristic là xác suất đã được hiệu chỉnh. |
| relation | Nếu không có quan hệ mong đợi thì 0.5; nếu có, min(1, số label incident giao với expected / max(1,min(2,số expected))). Graph search đi hai chiều; đây là overlap nhãn incident, không phải chứng minh cạnh đúng chiều hoặc entailment. |
| path | 1/(1 + hop_distance), với khoảng cách không âm. |
| source | log(1+source_count) / log(1+max_source_count trong C); mẫu số không có nguồn thì 0. |
| evidence | min(1, 0.7 × search-term coverage + 0.3 × relation). Một search term được coi có coverage nếu là substring một supporting segment hoặc có ít nhất min(2,số token term) token giao. Supporting segments gồm tên/mô tả/title/neighbor text. Đây là lexical support proxy, không phải quote verification hoặc Faithfulness. |
| retrieval | Điểm truy xuất ban đầu chia điểm tối đa trong C, hoặc 0 khi không có điểm dương. Snapshot BM25 seed score bị giảm theo hop trước bước này. |
| degree | log(1+degree) / log(1+max_degree trong C), hoặc 0 khi max_degree=0. Snapshot mới tính degree theo unique neighbors, không phải số entity occurrences. |

Base score = tổng(w_i × multiplier_i × signal_i) / tổng(w_i × multiplier_i).

Trọng số theo thứ tự semantic/entity/answer_type/relation/path/source/evidence/retrieval/degree là 0.32/0.14/0.16/0.11/0.09/0.05/0.08/0.04/0.01. Trọng số hữu hiệu phải hữu hạn, không âm và tổng dương. Tên degree_aux trong ranking audit tương ứng base weight degree.

Không được gọi đây là công thức toàn bộ cuối cùng: câu metric có metric-target bonus (0.82 base + 0.18 target); nếu có requested-item thì tiếp tục bước (0.82 score + 0.12 requested-item + 0.06 subject). Câu comparison có thể thêm bước (0.85 score + 0.15 comparison). Code còn có minimum-evidence, required-entity/type filters, đa dạng/giới hạn direct answers và supporting nodes. Bỏ một hệ số không loại hết thông tin tương quan hoặc các nhánh bonus này.

## Chính sách normalization và query

Giữ paper-local identity, không tự gộp người/tổ chức/cùng tên giữa các bài. Bảng alias phải có scope, nguồn và nhật ký; Metric khác record không bị gộp chỉ vì cùng tên. Model alias chỉ là đề xuất, evidence ID đúng không chứng minh đồng nghĩa. Bản dùng global exact-name merging lịch sử là track khác và phải công bố nguy cơ homonym.

`review_query_plan.py` là planner thử nghiệm có phiên bản: multiword parenthetical gloss là soft term, không tự thành hard identity; vẫn giữ ràng buộc model/acronym rõ. Các intent định nghĩa/sorting/compound-list là để tìm bằng chứng, không tạo đáp án. Query shared_query được tái sử dụng cho mọi track và không chứa reference answer.

Ví dụ có thể tái tạo, không phải output model: chạy build_plan trên câu “which analytical methods identify compounds from Salvia officinalis?” sẽ tạo kế hoạch tìm Method; lưu JSON thực tế cùng code hash thay vì chép ví dụ rồi coi là LLM query-analysis output. Planner trong thí nghiệm mới là deterministic/offline, không được mô tả như có thêm một lượt LLM analysis cho mỗi câu.

## Chi phí tính toán

- Xây chỉ mục BM25: tuyến tính theo tổng số token được index, cộng chi phí tokenize. Search truy cập posting lists rồi sắp xếp candidate có điểm: O(P + M log M) với P là tổng posting entries xét, M là số node có điểm; không giả định full scan mọi văn bản là tối ưu Neo4j.
- BFS: O(V_r+E_r) cho vùng đã chạm; implementation còn sắp thứ tự neighbors nên cộng chi phí sum(d_v log d_v). Giới hạn 24 seed, 240 candidate và hai hops là giới hạn vận hành, không chứng minh toàn graph search có thời gian hằng số.
- Reranking: O(CF + C log C), F là chi phí feature extraction. SequenceMatcher có thể có chi phí bậc hai theo độ dài chuỗi; không bỏ qua chiều dài query/name khi phân tích worst case.
- Packing: mỗi lần thử serialize và tokenize toàn context ứng viên. Tổng chi phí theo tổng độ dài các lần thử; không coi là một tokenization duy nhất. Giữ nguyên record, tối đa 2.000 proxy tokens, không cắt câu khoa học để vừa ngân sách.

## Độ nhạy

Nhân riêng từng hệ số với 0, 0.5, 2; còn lại giữ nguyên; baseline + 27 biến thể = 28 cấu hình. Cùng 45 query/plan/candidate snapshot, top8, tokenizer và budget; tổng 1.260 phép đo. Kiểm tra baseline context hash phải bằng retrieval snapshot. Dùng changed order, changed evidence set và Jaccard làm diagnostics, không coi là điểm chất lượng.

Không chọn trọng số tốt nhất dựa trên tập câu đã xem hoặc số context thay đổi. Cần nhãn độc lập để đánh giá đúng–đủ/faithfulness và QA ghép cặp; phải giữ nguyên chính sách trước giai đoạn đánh giá xác nhận. Các câu hiện tại đã dùng để phát triển, cần công bố giới hạn này.
