import os
import json
import time
import warnings
import google.generativeai as genai
from tqdm import tqdm
import re

# --- 1. CẤU HÌNH ---
warnings.filterwarnings("ignore")
os.environ["GRPC_VERBOSITY"] = "ERROR"

INPUT_FOLDER  = r'E:\LLM\data\json'
OUTPUT_FOLDER = r'E:\LLM\data\new_extract'
API_KEY = os.environ.get("GEMINI_API_KEY", "")

if not API_KEY:
    raise ValueError("Please set GEMINI_API_KEY before running extraction.")

genai.configure(api_key=API_KEY)

# --- 2. CẤU HÌNH MODEL ---
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

model = genai.GenerativeModel(
    'gemini-2.5-flash',  
    generation_config={"response_mime_type": "application/json"},
    safety_settings=safety_settings,
)

# ---------------------------------------------------------------------------
# 3. PROMPT HƯỚNG DẪN
# ---------------------------------------------------------------------------
IMPROVED_INSTRUCTION = """
Bạn là chuyên gia trích xuất tri thức từ bài báo khoa học. Hãy đọc kỹ toàn bộ
nội dung bài báo rồi trả về JSON với đúng schema bên dưới.

══════════════════════════════════════════════════════════════════
PHẦN A — ĐỊNH NGHĨA 7 LOẠI THỰC THỂ (ĐỌC KỸ TRƯỚC KHI TRÍCH XUẤT)
══════════════════════════════════════════════════════════════════

1. CONCEPT — Khái niệm / vấn đề nghiên cứu / đối tượng nghiên cứu trung tâm
   ✅ Bao gồm: khái niệm khoa học (bacterial wilt, deep learning, adsorption),
      đối tượng sinh học/hóa học được nghiên cứu (Ralstonia pseudosolanacearum,
      tetracycline, citrus nematode), vấn đề/thách thức mà bài báo giải quyết.
   ❌ KHÔNG bao gồm: tên tác giả, tên phương pháp, tiêu đề bài báo nguyên văn.
   ⚠️  CẢNH BÁO: Tuyệt đối không dùng tiêu đề bài báo làm Concept. Nếu muốn nắm
      bắt chủ đề chính, hãy đặt tên khái niệm ngắn gọn (≤ 6 từ).

2. METHOD — Phương pháp, kỹ thuật, công cụ, vật liệu, thiết bị, hóa chất
   ✅ Bao gồm MỌI thứ sau:
      • Phương pháp / kỹ thuật / thuật toán / mô hình được ÁP DỤNG:
        Colony PCR, MobileNetV3, HPLC, Hummer's method, Duncan test.
      • Vật liệu / hóa chất / chất xúc tác được sử dụng:
        Fe₃O₄/GO/PVP composite, H₂O₂, TZC medium, Chlorella sp. biomass,
        Coal-combustion bottom ash, Cement PCB40.
      • Thiết bị / phần mềm được sử dụng:
        Olympus CX23 microscope, MEGA 7, ISOMET 2114, Jupyter Notebook.
      • Quy trình / thiết kế thí nghiệm:
        Completely randomized design, subcritical methanol method.
   ❌ KHÔNG bao gồm: tên tập dữ liệu (→ Dataset), số đo kết quả (→ Metric).

3. DATASET — Cơ sở dữ liệu / tập dữ liệu số / nguồn dữ liệu tra cứu
   ✅ Bao gồm: GenBank, ImageNet, COCO, Kaggle rice disease dataset,
      JCPDS No.65-3107, NIST 2008 library, exchange rate time series.
   ❌ KHÔNG bao gồm: mẫu vật sinh học, cây trồng, bệnh nhân.

4. METRIC — Chỉ số đo lường KẾT QUẢ (đầu ra), KÈM GIÁ TRỊ CỤ THỂ
   ✅ Bao gồm: kết quả thực nghiệm có số (Accuracy 98%, F1-score 0.91,
      Compressive strength 52.7 MPa, FAME conversion 95%, Bootstrap 90-100%).
   ❌ KHÔNG bao gồm:
      • Điều kiện / thông số đầu VÀO: nhiệt độ phản ứng, tỉ lệ methanol/biomass,
        liều lượng chất xúc tác, pH môi trường, độ ẩm tương đối, thời gian ủ mẫu
        — đây là experimental conditions, KHÔNG phải Metric.
      • Thống kê từ tài liệu tham khảo (VD: "crop yield losses up to 85% theo
        Jones 2014") — chỉ lấy kết quả đo trong nghiên cứu này.
   🔑 Quy tắc phân biệt Metric vs Condition:
      → Nếu tác giả ĐO/QUAN SÁT/THU ĐƯỢC giá trị đó ⇒ Metric
      → Nếu tác giả ĐẶT/CHỌN/ĐIỀU CHỈNH giá trị đó ⇒ bỏ qua hoặc ghi vào
         description của Method liên quan.

5. DOMAIN — Lĩnh vực nghiên cứu chính (chỉ lấy 1–2 Domain rõ nhất).
   VD: Molecular Plant Pathology, Agricultural Science, Deep Learning, Civil
   Engineering, Environmental Chemistry.

6. AUTHOR — Từng tác giả riêng biệt (tách từ Header Information).
   Ghi đúng tên đầy đủ, không viết tắt, không ghép nhiều người vào một entity.

7. INSTITUTION — Từng tổ chức / trường / phòng thí nghiệm riêng biệt.
   Ghi đúng tên như trong Header. Nếu hai tác giả cùng trường thì chỉ tạo
   một Institution entity duy nhất.

══════════════════════════════════════════════════════════════════
PHẦN B — 5 LOẠI QUAN HỆ
══════════════════════════════════════════════════════════════════

• (Concept)  BELONGS_TO    (Domain)
• (Method)   ACHIEVED      (Metric)        — phương pháp đạt được kết quả nào
• (Method)   USED_FOR      (Concept)       — phương pháp dùng để giải quyết vấn đề nào
• (Method)   EVALUATED_ON  (Dataset)       — phương pháp được kiểm tra trên dataset nào
• (Author)   AFFILIATED_WITH (Institution) — gắn ĐÚNG tác giả với ĐÚNG tổ chức

══════════════════════════════════════════════════════════════════
PHẦN C — KIỂM TRA CHẤT LƯỢNG (tự kiểm trước khi trả về)
══════════════════════════════════════════════════════════════════

Trước khi xuất JSON, hãy tự hỏi:
□ Có entity nào dùng tiêu đề bài báo nguyên văn làm Concept không? → Xóa đi.
□ Có entity Concept nào thực ra là Method (tên phương pháp, tên mô hình)? → Đổi type.
□ Có entity Method nào thực ra là Material/Instrument nhưng tôi muốn giữ?
  → Vẫn giữ là Method (vì định nghĩa Method bao gồm vật liệu & thiết bị).
□ Có entity Metric nào là thông số đầu vào (temperature, ratio, dose, pH)?
  → Đổi thành ghi chú trong description của Method hoặc xóa đi.
□ Mỗi Author có relation AFFILIATED_WITH đúng Institution chưa?
□ Có Concept quan trọng nào bị bỏ sót không (đọc lại Abstract & Introduction)?

══════════════════════════════════════════════════════════════════
PHẦN D — JSON SCHEMA BẮT BUỘC
══════════════════════════════════════════════════════════════════

{
  "entities": [
    {
      "id": "Tên ngắn gọn của thực thể (≤ 8 từ, không dùng tiêu đề bài nguyên văn)",
      "type": "Concept | Method | Dataset | Metric | Domain | Author | Institution",
      "description": "Mô tả 1 câu, nêu rõ vai trò trong bài báo này"
    }
  ],
  "relations": [
    {
      "source": "id thực thể nguồn",
      "target": "id thực thể đích",
      "type": "BELONGS_TO | ACHIEVED | USED_FOR | EVALUATED_ON | AFFILIATED_WITH"
    }
  ]
}

Lưu ý: id trong relations phải khớp chính xác với id trong entities.
"""

# ---------------------------------------------------------------------------
# 4. FEW-SHOT EXAMPLES
#    3 ví dụ, mỗi ví dụ minh họa một nhóm lỗi hay gặp nhất:
#      Ex-1 (Biodiesel / Chemistry) → phân biệt Metric vs Condition
#      Ex-2 (Deep learning / IT)   → phân biệt Concept vs Method + tránh dùng title làm Concept
#      Ex-3 (Plant pathology / Biology) → vật liệu & thiết bị đều là Method; bỏ sót Concept
# ---------------------------------------------------------------------------
FEW_SHOT_EXAMPLES = """
══════════════════════════════════════════════════════════════════
PHẦN E — VÍ DỤ MẪU (FEW-SHOT): HỌC CÁCH PHÂN LOẠI ĐÚNG
══════════════════════════════════════════════════════════════════

Mỗi ví dụ gồm: đoạn văn bản bài báo → JSON đầu ra đúng.
Hãy học phong cách phân loại này và áp dụng cho bài báo thực tế ở cuối.

────────────────────────────────────────────────────────────────
VÍ DỤ 1 — Lĩnh vực: Hóa học / Nhiên liệu sinh học
          Trọng tâm học: Metric vs Condition + Method bao gồm vật liệu
────────────────────────────────────────────────────────────────

INPUT (trích đoạn bài báo):
  Title: Biodiesel synthesis from Chlorella sp. under subcritical methanol conditions
  Header: Ho Quoc Phong¹, Tran Dong Au², Huynh Lien Huong¹
          ¹College of Engineering Technology, Can Tho University
          ²Ho Chi Minh University of Technology
  Abstract: Transesterification under subcritical methanol was used to directly produce
  biodiesel from Chlorella sp. biomass. Effects of temperature (165–185°C),
  methanol-to-biomass ratio (10–25 g/g), water content (5–80%) and reaction time
  (1–12 h) were studied. Highest FAME conversion of 95% was obtained at 175°C,
  20 g/g ratio, 50% water content, after 12 h. Linoleic acid methyl ester (47.4%)
  was the dominant product.
  Results section: FAME conversion increased with reaction time. At 12 h a conversion
  of 95.1% was achieved. High temperature gas chromatography (HTGC) confirmed the
  FAME composition: linoleic acid methyl ester 47.4 wt%, palmitic acid 38.3 wt%.

OUTPUT JSON ĐÚNG:
{
  "entities": [
    {"id": "Biodiesel synthesis",         "type": "Concept",     "description": "Quá trình tổng hợp biodiesel từ vi tảo, vấn đề trung tâm của bài báo."},
    {"id": "Transesterification",         "type": "Concept",     "description": "Phản ứng hóa học chuyển lipid thành FAME (fatty acid methyl ester)."},
    {"id": "Subcritical methanol method", "type": "Method",      "description": "Phương pháp phản ứng dưới điều kiện methanol cận tới hạn, không dùng xúc tác axit/bazơ."},
    {"id": "Chlorella sp. biomass",       "type": "Method",      "description": "Vi tảo dùng làm nguyên liệu đầu vào cho quá trình tổng hợp biodiesel."},
    {"id": "HTGC",                        "type": "Method",      "description": "High temperature gas chromatography — thiết bị phân tích thành phần FAME."},
    {"id": "Biofuel Production",          "type": "Domain",      "description": "Lĩnh vực nghiên cứu chính của bài báo."},
    {"id": "Ho Quoc Phong",               "type": "Author",      "description": "Tác giả chính."},
    {"id": "Tran Dong Au",                "type": "Author",      "description": "Đồng tác giả."},
    {"id": "Huynh Lien Huong",            "type": "Author",      "description": "Đồng tác giả."},
    {"id": "College of Engineering Technology, Can Tho University", "type": "Institution", "description": "Đơn vị của tác giả 1 và 3."},
    {"id": "Ho Chi Minh University of Technology",                  "type": "Institution", "description": "Đơn vị của tác giả 2."},
    {"id": "FAME conversion (95%)",       "type": "Metric",      "description": "Tỷ lệ chuyển hóa FAME cao nhất ĐO ĐƯỢC sau 12 giờ phản ứng."},
    {"id": "Linoleic acid methyl ester (47.4 wt%)", "type": "Metric", "description": "Thành phần FAME chiếm tỷ lệ cao nhất QUAN SÁT ĐƯỢC qua HTGC."},
    {"id": "Palmitic acid methyl ester (38.3 wt%)", "type": "Metric", "description": "Thành phần FAME lớn thứ hai QUAN SÁT ĐƯỢC qua HTGC."}
  ],
  "relations": [
    {"source": "Biodiesel synthesis",         "target": "Biofuel Production",        "type": "BELONGS_TO"},
    {"source": "Subcritical methanol method", "target": "Biodiesel synthesis",       "type": "USED_FOR"},
    {"source": "Subcritical methanol method", "target": "FAME conversion (95%)",     "type": "ACHIEVED"},
    {"source": "HTGC",  "target": "Linoleic acid methyl ester (47.4 wt%)",          "type": "ACHIEVED"},
    {"source": "HTGC",  "target": "Palmitic acid methyl ester (38.3 wt%)",          "type": "ACHIEVED"},
    {"source": "Ho Quoc Phong",    "target": "College of Engineering Technology, Can Tho University", "type": "AFFILIATED_WITH"},
    {"source": "Huynh Lien Huong", "target": "College of Engineering Technology, Can Tho University", "type": "AFFILIATED_WITH"},
    {"source": "Tran Dong Au",     "target": "Ho Chi Minh University of Technology",                  "type": "AFFILIATED_WITH"}
  ]
}

⚠️ LƯU Ý từ Ví dụ 1:
  • Nhiệt độ 175°C, tỉ lệ 20 g/g, water content 50%, thời gian 12 h là ĐIỀU KIỆN
    được tác giả ĐẶT/CHỌN → KHÔNG tạo Metric cho các giá trị này.
  • FAME conversion 95%, linoleic 47.4%, palmitic 38.3% là kết quả ĐO/QUAN SÁT ĐƯỢC
    → tạo Metric cho các giá trị này.
  • Chlorella sp. biomass là vật liệu đầu vào → vẫn là Method (không phải Dataset).
  • Tiêu đề bài báo ("Biodiesel synthesis from Chlorella sp...") KHÔNG được dùng
    làm Concept. Thay vào đó dùng khái niệm cốt lõi: "Biodiesel synthesis".

────────────────────────────────────────────────────────────────
VÍ DỤ 2 — Lĩnh vực: AI / Nông nghiệp
          Trọng tâm học: Concept vs Method (mô hình AI) + tránh title làm Concept
────────────────────────────────────────────────────────────────

INPUT (trích đoạn bài báo):
  Title: Application of deep learning for rice leaf disease detection in the Mekong Delta
  Header: Ngo Duc Luu*, Le Thi Thuy Diem, Ha Thi Phuong Anh
          Faculty of Engineering and Technology, Bac Lieu University, Viet Nam
  Abstract: This paper applies MobileNetV3-Small and ResNet50 to classify three rice
  leaf diseases — leaf smut, brown spot, and bacterial leaf blight — using a Kaggle
  image dataset. MobileNetV3-Small achieved 100% accuracy on the test set with only
  ~20 seconds training time per epoch. A diagnostic program was developed for
  real-world deployment.
  Results: MobileNetV3-Small dominates: test accuracy 100%, training time 20 s/epoch.
  ResNet50 test accuracy also 100% but training time is longer (~180 s/epoch).

OUTPUT JSON ĐÚNG:
{
  "entities": [
    {"id": "Rice leaf disease detection",  "type": "Concept",  "description": "Bài toán nhận dạng bệnh lá lúa từ hình ảnh, vấn đề nghiên cứu chính."},
    {"id": "Leaf smut",                   "type": "Concept",  "description": "Bệnh lá lúa thứ nhất được phân loại trong nghiên cứu."},
    {"id": "Brown spot",                  "type": "Concept",  "description": "Bệnh lá lúa thứ hai được phân loại trong nghiên cứu."},
    {"id": "Bacterial leaf blight",       "type": "Concept",  "description": "Bệnh lá lúa thứ ba được phân loại trong nghiên cứu."},
    {"id": "MobileNetV3-Small",           "type": "Method",   "description": "Mô hình CNN nhẹ của Google, được chọn làm mô hình tối ưu."},
    {"id": "ResNet50",                    "type": "Method",   "description": "Mô hình CNN 50 lớp dùng để so sánh với MobileNetV3."},
    {"id": "Kaggle rice disease dataset", "type": "Dataset",  "description": "Tập ảnh bệnh lá lúa chuẩn hóa từ Kaggle, dùng để train/test."},
    {"id": "Agriculture / AI",            "type": "Domain",   "description": "Lĩnh vực nghiên cứu chính: ứng dụng AI trong nông nghiệp."},
    {"id": "Ngo Duc Luu",                 "type": "Author",   "description": "Tác giả chính."},
    {"id": "Le Thi Thuy Diem",            "type": "Author",   "description": "Đồng tác giả."},
    {"id": "Ha Thi Phuong Anh",           "type": "Author",   "description": "Đồng tác giả."},
    {"id": "Bac Lieu University",         "type": "Institution", "description": "Đơn vị của cả 3 tác giả."},
    {"id": "Test accuracy (100%)",        "type": "Metric",   "description": "Độ chính xác trên tập test — kết quả ĐO ĐƯỢC của cả MobileNetV3 và ResNet50."},
    {"id": "Training time MobileNetV3-Small (20 s/epoch)", "type": "Metric", "description": "Thời gian huấn luyện mỗi epoch ĐO ĐƯỢC — ưu thế chính của mô hình được chọn."}
  ],
  "relations": [
    {"source": "Rice leaf disease detection", "target": "Agriculture / AI",              "type": "BELONGS_TO"},
    {"source": "MobileNetV3-Small", "target": "Rice leaf disease detection",            "type": "USED_FOR"},
    {"source": "ResNet50",          "target": "Rice leaf disease detection",            "type": "USED_FOR"},
    {"source": "MobileNetV3-Small", "target": "Kaggle rice disease dataset",           "type": "EVALUATED_ON"},
    {"source": "ResNet50",          "target": "Kaggle rice disease dataset",           "type": "EVALUATED_ON"},
    {"source": "MobileNetV3-Small", "target": "Test accuracy (100%)",                  "type": "ACHIEVED"},
    {"source": "MobileNetV3-Small", "target": "Training time MobileNetV3-Small (20 s/epoch)", "type": "ACHIEVED"},
    {"source": "Ngo Duc Luu",       "target": "Bac Lieu University",                   "type": "AFFILIATED_WITH"},
    {"source": "Le Thi Thuy Diem",  "target": "Bac Lieu University",                   "type": "AFFILIATED_WITH"},
    {"source": "Ha Thi Phuong Anh", "target": "Bac Lieu University",                   "type": "AFFILIATED_WITH"}
  ]
}

⚠️ LƯU Ý từ Ví dụ 2:
  • "Deep learning" là công nghệ tổng quát → KHÔNG tạo Concept riêng cho nó; đây
    đã bao hàm trong mô hình cụ thể MobileNetV3 / ResNet50 (type: Method).
  • Tiêu đề "Application of deep learning for rice leaf disease detection…"
    KHÔNG được dùng làm Concept. Dùng "Rice leaf disease detection" thay thế.
  • 3 loại bệnh (leaf smut, brown spot, bacterial leaf blight) là đối tượng nghiên
    cứu → Concept, không phải Method hay Dataset.
  • Training time là kết quả ĐO ĐƯỢC → Metric. Số epoch (10, 20, 30) do tác giả
    ĐẶT → không tạo Metric.

────────────────────────────────────────────────────────────────
VÍ DỤ 3 — Lĩnh vực: Sinh học phân tử / Bệnh lý thực vật
          Trọng tâm học: Vật liệu & thiết bị = Method + không bỏ sót Concept
────────────────────────────────────────────────────────────────

INPUT (trích đoạn bài báo):
  Title: Molecular identification of Ralstonia pseudosolanacearum causing bacterial
         wilt in tomatoes from Da Nang by using Colony PCR
  Header: Nguyen Minh Ly*, Kieu Duc Toan
          Faculty of Biology, University of Science and Education, The University
          of Danang, Viet Nam
  Abstract: Colony PCR with specific primers 759/760 and multiplex PCR were applied
  to screen RSSC strains from diseased tomatoes. Strains were identified as
  Ralstonia pseudosolanacearum phylotype I. Phylogenetic analysis of 16S-23S rDNA
  confirmed the results (bootstrap 90–100%). Colony PCR efficiency on 10 subcolonies
  was 100%.
  Methodology: Colonies cultured on TZC medium (pH 7–7.2). DNA sequenced by First
  BASE Laboratories. 71 reference sequences from GenBank aligned using ClustalW in
  MEGA 7. Trees built by Neighbor-Joining method, visualised in iTOL.
  Results: Colony 1 (T04) confirmed as R. pseudosolanacearum phylotype I. PCR band
  ~280 bp with primer 759/760. Multiplex bands: 140 bp and 300 bp.

OUTPUT JSON ĐÚNG:
{
  "entities": [
    {"id": "Bacterial wilt",                         "type": "Concept",   "description": "Bệnh héo vi khuẩn trên cây cà chua, vấn đề nông nghiệp trung tâm của bài báo."},
    {"id": "Ralstonia solanacearum species complex",  "type": "Concept",   "description": "Nhóm vi khuẩn gây bệnh héo, bao gồm R. pseudosolanacearum."},
    {"id": "Ralstonia pseudosolanacearum",            "type": "Concept",   "description": "Loài vi khuẩn cụ thể được xác định là tác nhân gây bệnh tại Đà Nẵng."},
    {"id": "Phylotype I",                             "type": "Concept",   "description": "Phân loại di truyền của RSSC, chủ yếu có nguồn gốc châu Á."},
    {"id": "Colony PCR",                              "type": "Method",    "description": "Kỹ thuật PCR trực tiếp từ khuẩn lạc, không cần tách chiết DNA trước."},
    {"id": "Multiplex PCR",                           "type": "Method",    "description": "PCR đa mồi để xác định phylotype của RSSC."},
    {"id": "16S-23S rDNA sequencing",                 "type": "Method",    "description": "Giải trình tự vùng rDNA để xác định và phân tích phát sinh loài."},
    {"id": "TZC medium",                              "type": "Method",    "description": "Môi trường chọn lọc nuôi cấy RSSC (vật liệu thí nghiệm)."},
    {"id": "ClustalW",                                "type": "Method",    "description": "Phần mềm căn chỉnh đa trình tự dùng trong phân tích phát sinh loài."},
    {"id": "MEGA 7",                                  "type": "Method",    "description": "Phần mềm xây dựng cây phát sinh loài theo Neighbor-Joining."},
    {"id": "iTOL",                                    "type": "Method",    "description": "Công cụ trực tuyến biểu diễn cây phát sinh loài."},
    {"id": "GenBank",                                 "type": "Dataset",   "description": "Cơ sở dữ liệu trình tự nucleotide — nguồn 71 trình tự tham chiếu."},
    {"id": "Molecular Plant Pathology",               "type": "Domain",    "description": "Lĩnh vực nghiên cứu chính của bài báo."},
    {"id": "Nguyen Minh Ly",                          "type": "Author",    "description": "Tác giả chính."},
    {"id": "Kieu Duc Toan",                           "type": "Author",    "description": "Đồng tác giả."},
    {"id": "University of Science and Education, The University of Danang", "type": "Institution", "description": "Đơn vị của cả 2 tác giả."},
    {"id": "Colony PCR efficiency (100%)",            "type": "Metric",    "description": "Tỷ lệ thành công của Colony PCR trên 10 subcolony — kết quả ĐO ĐƯỢC."},
    {"id": "Bootstrap coefficient (90–100%)",         "type": "Metric",    "description": "Độ tin cậy clade phylotype I trong cây phát sinh loài — kết quả ĐO ĐƯỢC."},
    {"id": "PCR band size (280 bp)",                  "type": "Metric",    "description": "Kích thước băng PCR với mồi 759/760 — kết quả ĐO ĐƯỢC trên gel điện di."}
  ],
  "relations": [
    {"source": "Bacterial wilt",          "target": "Molecular Plant Pathology",   "type": "BELONGS_TO"},
    {"source": "Colony PCR",             "target": "Bacterial wilt",              "type": "USED_FOR"},
    {"source": "Multiplex PCR",          "target": "Phylotype I",                 "type": "USED_FOR"},
    {"source": "16S-23S rDNA sequencing","target": "Ralstonia pseudosolanacearum","type": "USED_FOR"},
    {"source": "Colony PCR",            "target": "GenBank",                     "type": "EVALUATED_ON"},
    {"source": "Colony PCR",            "target": "Colony PCR efficiency (100%)", "type": "ACHIEVED"},
    {"source": "MEGA 7",               "target": "Bootstrap coefficient (90–100%)", "type": "ACHIEVED"},
    {"source": "Colony PCR",            "target": "PCR band size (280 bp)",      "type": "ACHIEVED"},
    {"source": "Nguyen Minh Ly",        "target": "University of Science and Education, The University of Danang", "type": "AFFILIATED_WITH"},
    {"source": "Kieu Duc Toan",         "target": "University of Science and Education, The University of Danang", "type": "AFFILIATED_WITH"}
  ]
}

⚠️ LƯU Ý từ Ví dụ 3:
  • TZC medium là môi trường nuôi cấy (vật liệu thí nghiệm) → Method, không phải
    Dataset. pH 7–7.2 là thông số ĐẶT sẵn của môi trường → KHÔNG tạo Metric.
  • ClustalW, MEGA 7, iTOL là phần mềm được dùng → Method (hay bị bỏ sót).
  • PCR band 280 bp là kết quả QUAN SÁT ĐƯỢC → Metric.
  • Cần trích xuất đủ các Concept: không chỉ có R. pseudosolanacearum mà còn cả
    RSSC (nhóm vi khuẩn bao quát) và Phylotype I (hệ thống phân loại).
  • Số khuẩn lạc (8 colonies, 10 subcolonies) do tác giả ĐẶT/CHỌN → không tạo Metric.

────────────────────────────────────────────────────────────────
VÍ DỤ 4 — Lĩnh vực: Luật học / So sánh pháp luật
          Trọng tâm học: Legal framework & treaty → Concept (KHÔNG phải Method)
                         Case law → Dataset; legal doctrine → Concept
                         KHÔNG có Metric trong bài so sánh luật thuần túy
────────────────────────────────────────────────────────────────

INPUT (trích đoạn bài báo):
  Title: The right to avoid the international sale of goods contract:
         Comparison of Viet Nam to CISG and PICC
  Header: Nguyen Thi Hoa Cuc*, Doan Nguyen Phu Cuong, Nguyen Minh Phu
          School of Law, Can Tho University, Viet Nam
  Abstract: This article compared Vietnamese Commercial Law 2005 with CISG
  and PICC regarding avoidance of sale contracts, covering three aspects:
  fundamental breach, failure in performance obligations at the end of adding
  time, and anticipatory breach. Findings show differences and similarities
  between Vietnamese law and international rules, and put forward three
  implications for rebuilding the definition of "fundamental breach" in
  Vietnamese commercial law.
  Introduction: While CISG and PICC have codified a clear foundation for
  identifying "fundamental breach", current Vietnamese laws are quite general.
  Also, anticipatory breach has not been stipulated in Vietnamese law. The
  case Delchi Carrier SpA v. Rotorex Corp (2nd Circuit) held that a
  fundamental breach occurred when the air compressor did not comply with
  sample specifications.
  Conclusion: Vietnamese law should: (1) rebuild the definition of
  "fundamental breach"; (2) draw a specific framework for Nachfrist-based
  termination; (3) accept anticipatory breach as a ground for avoidance.

OUTPUT JSON ĐÚNG:
{
  "entities": [
    {"id": "Avoidance of contract",         "type": "Concept",     "description": "Quyền hủy bỏ hợp đồng mua bán hàng hóa quốc tế, vấn đề pháp lý trung tâm của bài báo."},
    {"id": "Fundamental breach",            "type": "Concept",     "description": "Vi phạm cơ bản — căn cứ chính để hủy bỏ hợp đồng, được so sánh giữa 3 hệ thống pháp luật."},
    {"id": "Anticipatory breach",           "type": "Concept",     "description": "Vi phạm trước thời hạn thực hiện — chưa được quy định trong luật Việt Nam."},
    {"id": "Nachfrist principle",           "type": "Concept",     "description": "Nguyên tắc gia hạn thêm thời gian hợp lý trước khi tuyên bố hủy hợp đồng."},
    {"id": "CISG",                          "type": "Concept",     "description": "Công ước LHQ về Hợp đồng Mua bán Hàng hóa Quốc tế — khung pháp lý quốc tế thứ nhất được so sánh."},
    {"id": "PICC",                          "type": "Concept",     "description": "Bộ nguyên tắc Hợp đồng Thương mại Quốc tế của UNIDROIT — khung pháp lý quốc tế thứ hai được so sánh."},
    {"id": "Vietnamese Commercial Law 2005","type": "Concept",     "description": "Luật Thương mại Việt Nam 2005 — hệ thống pháp luật quốc gia được đối chiếu với chuẩn quốc tế."},
    {"id": "Comparative legal analysis",   "type": "Method",      "description": "Phương pháp so sánh luật học được áp dụng để đối chiếu quy định trong nước và quốc tế."},
    {"id": "Delchi Carrier SpA v. Rotorex Corp", "type": "Dataset", "description": "Án lệ (2nd Circuit) được trích dẫn để minh họa định nghĩa fundamental breach trong thực tiễn."},
    {"id": "International Trade Law",      "type": "Domain",      "description": "Lĩnh vực pháp luật thương mại quốc tế, trọng tâm nghiên cứu của bài báo."},
    {"id": "Nguyen Thi Hoa Cuc",           "type": "Author",      "description": "Tác giả chính và người liên hệ."},
    {"id": "Doan Nguyen Phu Cuong",        "type": "Author",      "description": "Đồng tác giả."},
    {"id": "Nguyen Minh Phu",              "type": "Author",      "description": "Đồng tác giả."},
    {"id": "School of Law, Can Tho University", "type": "Institution", "description": "Đơn vị công tác của cả 3 tác giả."}
  ],
  "relations": [
    {"source": "Avoidance of contract",    "target": "International Trade Law",        "type": "BELONGS_TO"},
    {"source": "Fundamental breach",       "target": "International Trade Law",        "type": "BELONGS_TO"},
    {"source": "Comparative legal analysis","target": "Avoidance of contract",         "type": "USED_FOR"},
    {"source": "Comparative legal analysis","target": "Fundamental breach",            "type": "USED_FOR"},
    {"source": "Comparative legal analysis","target": "Delchi Carrier SpA v. Rotorex Corp", "type": "EVALUATED_ON"},
    {"source": "Nguyen Thi Hoa Cuc",       "target": "School of Law, Can Tho University", "type": "AFFILIATED_WITH"},
    {"source": "Doan Nguyen Phu Cuong",    "target": "School of Law, Can Tho University", "type": "AFFILIATED_WITH"},
    {"source": "Nguyen Minh Phu",          "target": "School of Law, Can Tho University", "type": "AFFILIATED_WITH"}
  ]
}

⚠️ LƯU Ý từ Ví dụ 4 — QUAN TRỌNG cho mọi bài báo Luật / Social Science:
  • CISG, PICC, Vietnamese Commercial Law 2005 là CÁC KHUNG PHÁP LÝ (legal frameworks /
    treaties / statutes) → type: "Concept". KHÔNG phải Method dù chúng được "dùng để
    so sánh" — chúng là ĐỐI TƯỢNG nghiên cứu, không phải công cụ thực hiện nghiên cứu.
  • Comparative legal analysis là PHƯƠNG PHÁP tác giả áp dụng → type: "Method". Đây
    là công cụ thực hiện, khác với các framework pháp lý là đối tượng được phân tích.
  • Án lệ (case law) như "Delchi Carrier SpA v. Rotorex Corp" là nguồn dữ liệu tra cứu
    → type: "Dataset". Tương tự: JCPDS card, GenBank sequence — đây là dữ liệu tham chiếu.
  • Bài so sánh luật thuần túy KHÔNG có Metric số học. Đừng cố tạo Metric từ
    "3 kiến nghị" hay "3 khía cạnh so sánh" — đây là kết quả định tính, không phải
    chỉ số đo lường có giá trị cụ thể.
  • Các học thuyết / nguyên tắc pháp lý (Nachfrist principle, anticipatory breach,
    fundamental breach) là Concept — đối tượng phân tích của bài báo.
  • Quy tắc nhớ nhanh: nếu thực thể là "thứ tác giả NGHIÊN CỨU / SO SÁNH / PHÂN TÍCH"
    → Concept. Nếu là "thứ tác giả DÙNG ĐỂ nghiên cứu" → Method.

══════════════════════════════════════════════════════════════════
KẾT THÚC PHẦN VÍ DỤ — Bắt đầu trích xuất bài báo thực tế bên dưới
══════════════════════════════════════════════════════════════════
"""

# ---------------------------------------------------------------------------
# 5. CÁC HÀM TIỆN ÍCH
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def prepare_content(json_data: dict) -> str:
    """Tổng hợp nội dung bài báo thành chuỗi văn bản gửi cho LLM."""
    parts = []

    title = json_data.get('title', '').strip()
    if title:
        parts.append(f"PAPER TITLE: {title}")

    raw_header = json_data.get('raw_header', '').strip()
    if raw_header:
        parts.append(
            "--- Header Information (Authors & Affiliations) ---\n"
            + raw_header
            + "\n--- End of Header ---"
        )

    abstract = clean_text(json_data.get('abstract', ''))
    if abstract:
        parts.append(f"ABSTRACT:\n{abstract}")

    PRIORITY_CATS = {"introduction", "methodology", "results", "conclusion"}
    for section in json_data.get('sections', []):
        cat     = section.get('category', '').lower()
        content = clean_text(section.get('content', ''))
        title_s = section.get('section_title', '')
        if (cat in PRIORITY_CATS or len(content) > 800) and len(content) > 30:
            parts.append(f"SECTION [{title_s} / {cat}]:\n{content}")

    return "\n\n".join(parts)


def parse_response(text: str) -> dict:
    """
    Parse JSON từ response của LLM.
    Xử lý trường hợp model bọc kết quả trong markdown code fence (```json ... ```).
    """
    text = text.strip()
    # Bóc code fence nếu có
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text.strip())


# ---------------------------------------------------------------------------
# 6. GỌI API VÀ XỬ LÝ LỖI
# ---------------------------------------------------------------------------

MAX_RETRIES = 3  # giới hạn số lần thử lại khi gặp lỗi 429/503

def extract(content: str, _retry: int = 0) -> dict:
    prompt = (
        f"{IMPROVED_INSTRUCTION}\n\n"
        f"{FEW_SHOT_EXAMPLES}\n\n"
        f"══════════════════════════════════════════════════════════\n"
        f"BÀI BÁO CẦN TRÍCH XUẤT:\n"
        f"══════════════════════════════════════════════════════════\n"
        f"{content}\n\n"
        f"Áp dụng đúng quy tắc ở Phần A–D và phong cách ở Phần E.\n"
        f"Trả về JSON theo đúng schema ở Phần D:"
    )

    try:
        response = model.generate_content(prompt)
        return parse_response(response.text)

    except json.JSONDecodeError as e:
        print(f"❌ LLM không trả về JSON hợp lệ: {e}")
        return {"entities": [], "relations": []}

    except Exception as e:
        err = str(e)
        if ("429" in err or "503" in err) and _retry < MAX_RETRIES:
            wait = 15 * (_retry + 1)  # back-off: 15s, 30s, 45s
            print(f"\n⏳ API quá tải — chờ {wait}s rồi thử lại (lần {_retry + 1}/{MAX_RETRIES})…")
            time.sleep(wait)
            return extract(content, _retry + 1)
        print(f"\n❌ Lỗi API: {err}")
        return {"entities": [], "relations": []}


# ---------------------------------------------------------------------------
# 7. HÀM MAIN
# ---------------------------------------------------------------------------

def main():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    files = [f for f in os.listdir(INPUT_FOLDER) if f.endswith('.json')]
    print(f"🚀 Bắt đầu trích xuất {len(files)} file…")

    for filename in tqdm(files):
        output_path = os.path.join(OUTPUT_FOLDER, filename)
        if os.path.exists(output_path):
            continue

        try:
            with open(os.path.join(INPUT_FOLDER, filename), 'r', encoding='utf-8') as f:
                data = json.load(f)

            content = prepare_content(data)
            if len(content) < 50:
                continue

            result = extract(content)

            final = {
                "filename":          filename,
                "paper_title":       data.get('title'),
                "extraction_result": result,
            }
            with open(output_path, 'w', encoding='utf-8') as f_out:
                json.dump(final, f_out, ensure_ascii=False, indent=4)

        except Exception as e:
            print(f"❌ Lỗi file {filename}: {e}")

        time.sleep(2)


if __name__ == "__main__":
    main()
