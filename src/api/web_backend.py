import os
import re
import json
import logging
import requests
import fitz
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

try:
    from config import GEMINI_API_KEY, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
except ImportError:
    GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
    NEO4J_URI       = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER      = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD  = os.getenv("NEO4J_PASSWORD", "")

GROBID_URL = os.getenv("GROBID_URL", "http://localhost:8070/api/processFulltextDocument")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

JSON_GENERATION_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json"
)
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

══════════════════════════════════════════════════════════════════
KẾT THÚC PHẦN VÍ DỤ — Bắt đầu trích xuất bài báo thực tế bên dưới
══════════════════════════════════════════════════════════════════
"""

# ---------------------------------------------------------------------------
# 3. PROMPT CẢI TIẾN
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

• (Paper title)  BELONGS_TO    (Domain)
• (Method)       ACHIEVED      (Metric)        — phương pháp đạt được kết quả nào
• (Method)       USED_FOR      (Concept)       — phương pháp dùng để giải quyết khái niệm/vấn đề nào
• (Method)       EVALUATED_ON  (Dataset)       — phương pháp được kiểm tra trên dataset nào
• (Author)       AFFILIATED_WITH (Institution) — gắn ĐÚNG tác giả với ĐÚNG tổ chức

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

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\[\d+(?:[,-]\s*\d+)*\]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def normalize_entity_name(name):
    if not name:
        return ""
    name = str(name).strip()
    name = re.sub(r'\s+', ' ', name)
    return name

def parse_pdf(pdf_path):
    filename = os.path.basename(pdf_path)
    raw_header = ""

    try:
        doc = fitz.open(pdf_path)
        raw_header = doc[0].get_text("text")[:2000]
        doc.close()
    except:
        pass

    try:
        with open(pdf_path, 'rb') as f:
            response = requests.post(GROBID_URL, files={'input': f}, timeout=300)
        if response.status_code != 200:
            return None
        xml_content = response.text
    except:
        return None

    soup = BeautifulSoup(xml_content, 'xml')

    paper_data = {
        "filename": filename,
        "title": "",
        "raw_header": clean_text(raw_header),
        "abstract": "",
        "sections": []
    }

    title_tag = soup.find('title', type='main')
    if title_tag:
        paper_data["title"] = clean_text(title_tag.get_text())

    abstract_tag = soup.find('abstract')
    if abstract_tag:
        paper_data["abstract"] = clean_text(abstract_tag.get_text())

    body = soup.find('body')
    if body:
        for div in body.find_all('div'):
            head = div.find('head')
            if not head:
                continue

            title = head.get_text(strip=True)
            paragraphs = div.find_all('p')
            content = " ".join(p.get_text(strip=True) for p in paragraphs)
            content = clean_text(content)

            if len(content) > 30:
                paper_data["sections"].append({
                    "section_title": title,
                    "content": content
                })

    return paper_data

def prepare_content(paper_data):
    parts = []

    if paper_data.get("title"):
        parts.append(f"PAPER TITLE: {paper_data['title']}")

    if paper_data.get("raw_header"):
        parts.append(
            "--- Header Information ---\n"
            + paper_data["raw_header"]
        )

    if paper_data.get("abstract"):
        parts.append(f"ABSTRACT:\n{paper_data['abstract']}")

    for sec in paper_data.get("sections", []):
        content = sec.get("content", "")
        if len(content) > 50:
            parts.append(f"SECTION: {sec['section_title']}\n{content}")

    return "\n\n".join(parts)


def extract_knowledge(paper_data):
    content = prepare_content(paper_data)

    prompt = (
        f"{IMPROVED_INSTRUCTION}\n\n"
        f"{FEW_SHOT_EXAMPLES}\n\n"
        f"══════════════════════════════════════════════════════════\n"
        f"BÀI BÁO CẦN TRÍCH XUẤT:\n"
        f"══════════════════════════════════════════════════════════\n"
        f"{content}\n\n"
        f"Trả về JSON theo schema."
    )

    try:
        response = gemini_client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config=JSON_GENERATION_CONFIG,
        )
        result = json.loads(response.text)

        # Normalize + Deduplicate
        unique = {}

        for ent in result.get("entities", []):
            ent_id = normalize_entity_name(ent.get("id"))
            ent_type = ent.get("type")

            if not ent_id or not ent_type:
                continue

            key = (ent_id, ent_type)

            if key not in unique:
                ent["id"] = ent_id
                unique[key] = ent

        result["entities"] = list(unique.values())

        for rel in result.get("relations", []):
            rel["source"] = normalize_entity_name(rel.get("source"))
            rel["target"] = normalize_entity_name(rel.get("target"))

        return {
            "filename": paper_data["filename"],
            "title": paper_data["title"],
            "abstract": paper_data["abstract"],
            "extraction_result": result
        }

    except Exception as e:
        logger.error(f"LLM ERROR: {e}")
        return None


def save_to_neo4j(data):
    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD)
    )

    entities_saved = 0
    relations_saved = 0

    with driver.session() as session:

        # p.name = title (fallback filename) — bắt buộc để Graph Explorer đọc được tên node
        # get_dynamic_graph() và get_entities_table() trong main.py đều tra cứu n.name trước
        paper_name = (data.get("title") or "").strip() or data["filename"]
        session.run(
            """
            MERGE (p:Paper {filename: $filename})
            SET p.title    = $title,
                p.name     = $name,
                p.abstract = $abstract
            """,
            filename = data["filename"],
            title    = data.get("title", ""),
            name     = paper_name,
            abstract = data.get("abstract", ""),
        )

        result = data.get("extraction_result", {})
        if not result:
             result = {}

        # Entities
        for ent in result.get("entities", []):
            name  = ent.get("id")
            etype = ent.get("type")
            edesc = ent.get("description", "")

            if not name or not etype:
                continue

            # Sanitize label: Neo4j label không được có ký tự đặc biệt
            safe_label = re.sub(r"[^A-Za-z0-9_]", "_", etype)

            try:
                session.run(
                    f"MERGE (e:`{safe_label}` {{name: $name}}) SET e.description = $desc",
                    name=name, desc=edesc,
                )

                rel_type = "AUTHORED_BY" if etype == "Author" else "MENTIONS"
                session.run(
                    f"""
                    MATCH (p:Paper {{filename: $filename}})
                    MATCH (e:`{safe_label}` {{name: $name}})
                    MERGE (p)-[:{rel_type}]->(e)
                    """,
                    filename=data["filename"], name=name,
                )
                entities_saved += 1
            except Exception as e:
                logger.warning(f"Entity save error [{name}]: {e}")

        # Relations
        for rel in result.get("relations", []):
            src   = rel.get("source")
            tgt   = rel.get("target")
            rtype = rel.get("type")

            if not src or not tgt or not rtype:
                continue

            # Sanitize: chỉ giữ A-Z, 0-9, _
            clean_rel = re.sub(r"[^A-Z0-9_]", "_", rtype.upper().replace(" ", "_"))

            try:
                session.run(
                    f"""
                    MATCH (a {{name: $src}})
                    MATCH (b {{name: $tgt}})
                    MERGE (a)-[:{clean_rel}]->(b)
                    """,
                    src=src, tgt=tgt,
                )
                relations_saved += 1
            except Exception as e:
                logger.warning(f"Relation save error [{src}]-[{clean_rel}]->[{tgt}]: {e}")

    driver.close()
    
    # ADD THIS RETURN STATEMENT
    logger.info(f"Saved {entities_saved} entities, {relations_saved} relations to Neo4j")
    return {"entities_saved": entities_saved, "relations_saved": relations_saved}

def clear_graph():
    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD)
    )
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    driver.close()