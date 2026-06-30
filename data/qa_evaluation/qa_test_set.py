import pandas as pd

data = [
    # --- Bài báo 1: Xoài Đài Loan (Uniconazole) ---
    {
        "question": "Các tác giả của nghiên cứu về ảnh hưởng của uniconazole trên xoài 'Đài Loan' ở An Giang là ai?",
        
        "ground_truth": "Nghiên cứu được thực hiện bởi Tran Van Huu, Phan Van Ut, Phan Huynh Anh và Tran Sy Hieu.",
        
        "chatbot_answer": "Dựa trên dữ liệu từ đồ thị tri thức, nghiên cứu về ảnh hưởng của uniconazole trên xoài 'Đài Loan' tại huyện Chợ Mới, tỉnh An Giang (năm 2016) được thực hiện bởi các tác giả sau đây: Tran Van Huu: Tác giả chính (Lead author) đến từ Trường Đại học Cần Thơ. 🎓 Phan Huynh Anh: Tác giả đến từ Trường Đại học Cần Thơ. 🏫 Tran Sy Hieu: Tác giả đến từ Trường Đại học Cần Thơ. 📖 Các tác giả này đã cùng thực hiện đề tài nghiên cứu có tiêu đề: \"The effects of uniconazole dosages and suitable periods for bud break on the flowering of 'Dai Loan' mango (Mangifera indica L.) grown in Cho Moi district, An Giang province, 2016\".",
        
        "context": "Tran Van Huu (Author), Phan Huynh Anh (Author), Tran Sy Hieu (Author), The effects of uniconazole dosages and suitable periods for bud break on the flowering of 'Dai Loan' mango (Mangifera indica L.) grown in Cho Moi district, An Giang province, 2016 (Paper)"
    },
    {
        "question": "Hai hóa chất Uniconazole (UCZ) và Paclobutrazol (PBZ) được sử dụng cho mục đích gì trong nghiên cứu về xoài?",
        "ground_truth": "Chúng được sử dụng như phương pháp để kích thích ra hoa (Flowering induction).",
        
        "chatbot_answer": "Dựa trên dữ liệu từ đồ thị tri thức, hai hóa chất Uniconazole (UCZ) và Paclobutrazol (PBZ) được sử dụng trong nghiên cứu về xoài với các mục đích cụ thể sau: Uniconazole (UCZ): Được sử dụng như một chất điều hòa sinh trưởng thực vật nhằm đóng vai trò là tác nhân kích thích khởi tạo mầm hoa (flower bud initiation agent) 🌸. Paclobutrazol (PBZ): Là một chất ức chế sinh trưởng thực vật thuộc nhóm triazole, được sử dụng để cảm ứng ra hoa (flowering induction) và thường được dùng làm đối chứng trong các thí nghiệm xử lý ra hoa trên xoài 🌳. Cả hai hóa chất này đều nằm trong các nghiên cứu nhằm cải thiện khả năng ra hoa và đậu quả, cụ thể là trên giống xoài 'Đài Loan' tại khu vực An Giang.",
        
        "context": "Uniconazole (UCZ) (Method), Paclobutrazol (PBZ) (Method), The effects of uniconazole dosages and suitable periods for bud break on the flowering of 'Dai Loan' mango... (Paper)"
    },
    {
        "question": "Phương pháp nào được dùng để phân tích các hợp chất giống GA (GA-like compounds) trong nghiên cứu xoài?",
        "ground_truth": "Phương pháp HPLC (High pressure liquid chromatography) được sử dụng để phân tích.",
        
        "chatbot_answer": "Dựa trên dữ liệu từ đồ thị tri thức, phương pháp được sử dụng để phân tích các hợp chất giống GA (GA-like compounds) trong nghiên cứu về xoài là: HPLC (Sắc ký lỏng hiệu năng cao - High pressure liquid chromatography): Đây là phương pháp chính được dùng để phân tích các hợp chất giống GA trong nghiên cứu về ảnh hưởng của liều lượng uniconazole và thời điểm kích thích ra hoa trên giống xoài 'Đài Loan' (Mangifera indica L.) tại huyện Chợ Mới, tỉnh An Giang. 🥭",
        
        "context": "HPLC (Method), The effects of uniconazole dosages and suitable periods for bud break on the flowering of 'Dai Loan' mango (Mangifera indica L.) grown in Cho Moi district, An Giang province, 2016 (Paper)"
    },

    # --- Bài báo 2: Nhãn và Chôm chôm ---
    {
        "question": "Hãy liệt kê các phương pháp dùng để kích thích ra hoa ở nhãn và chôm chôm ở Đồng bằng sông Cửu Long.",
        "ground_truth": "Các phương pháp bao gồm: Tưới gốc KClO3 (Collar drenching of KClO3), khoanh vỏ (Branch girdling), rút nước mương (Drainage of irrigation ditch), phủ nilon (Plastic mulching), và phun Paclobutrazol.",
        
        "chatbot_answer": "Dựa trên dữ liệu từ biểu đồ tri thức, các phương pháp được sử dụng để kích thích ra hoa (Flowering induction) ở nhãn và chôm chôm tại Đồng bằng sông Cửu Long bao gồm: 🧪 Tưới KClO3 vào gốc (Collar drenching of KClO3): Đây là phương pháp cụ thể được sử dụng để kích thích ra hoa cho cây nhãn. ✂️ Khoanh cành (Branch girdling): Kỹ thuật hỗ trợ để thúc đẩy quá trình ra hoa. 💧 Rút nước mương vườn (Drainage of irrigation ditch): Phương pháp tạo hạn hán nhân tạo giúp cây chôm chôm ra hoa. 🛡️ Sử dụng màng phủ plastic (Plastic mulching): Dùng để tạo điều kiện khô hạn cần thiết cho cây trong quá trình xử lý ra hoa. 🌿 Sử dụng chất điều hòa sinh trưởng: Bao gồm phun Paclobutrazol (PBZ) lên tán lá hoặc sử dụng Uniconazole (UCZ) để ức chế sinh trưởng và kích thích khởi tạo mầm hoa.",
        
        "context": "Longan and rambutan in the Mekong Delta, Vietnam: A review of technologies to improve flowering and fruit setting (Paper), Flowering induction (Concept)"
    },
    {
        "question": "Liều lượng KClO3 được sử dụng để xử lý ra hoa cho giống nhãn E-daw là bao nhiêu?",
        "ground_truth": "Liều lượng KClO3 sử dụng cho giống E-daw là 8 g/m2.",
        
        "chatbot_answer": "Dựa trên dữ liệu từ biểu đồ tri thức, liều lượng KClO3 được sử dụng để xử lý ra hoa cho giống nhãn E-daw cụ thể như sau: ⚖️ Liều lượng: 8 g/m². 🛠️ Phương pháp: Được áp dụng thông qua phương pháp tưới vào gốc (Collar drenching of KClO3) để kích thích quá trình ra hoa (Flowering induction).",
        
        "context": "KClO3 dose for E-daw (8 g/m2), Collar drenching of KClO3, Longan and rambutan in the Mekong Delta, Vietnam: A review of technologies to improve flowering and fruit setting"
    },
    {
        "question": "Để giảm hiện tượng nứt trái (fruit cracking) ở chôm chôm, giải pháp nào được sử dụng?",
        "ground_truth": "Phun Canxi Clorua (CaCl2 application) được sử dụng để giảm hiện tượng nứt trái.",
        
        "chatbot_answer": "Dựa trên dữ liệu từ đồ thị tri thức, để giảm hiện tượng nứt trái ở chôm chôm, giải pháp sau đây được sử dụng: CaCl2 application (Phun Canxi Clorua): Đây là phương pháp được sử dụng để phun lên cây nhằm giảm thiểu hiện tượng nứt trái (Fruit cracking), một vấn đề gây ảnh hưởng trực tiếp đến năng suất chôm chôm. 🍎",
        
        "context": "CaCl2 application (Method), Fruit cracking (Concept), Longan and rambutan in the Mekong Delta, Vietnam: A review of technologies to improve flowering and fruit setting (Paper)"
    },

    # --- Bài báo 3: Phân bón cho thanh trà (gandaria) ---
    {
        "question": "Với liều lượng phân bón 3-4 kg/cây/năm, năng suất trái cây thanh trà đạt được là bao nhiêu?",
        "ground_truth": "Năng suất trái đạt được (Fruit yield) từ 99.5 đến 107.1 kg/cây.",
        
        "chatbot_answer": "Dựa trên dữ liệu từ đồ thị tri thức, với liều lượng phân bón 3-4 kg/cây/năm, năng suất của cây thanh trà (Bouea oppositifolia (Roxb.) Meisne.) đạt được như sau: Năng suất trái (Fruit yield): Đạt trong khoảng từ 99,5 đến 107,1 kg/cây. 🍈Ngữ cảnh nghiên cứu: Kết quả này được ghi nhận trong nghiên cứu về ảnh hưởng của các liều lượng phân bón đến năng suất và chất lượng cây thanh trà tại thị xã Bình Minh, tỉnh Vĩnh Long. 📍.",
        
        "context": "Paper: Effects of fertilizer doses on yield and quality of gandaria (Bouea oppositifolia (Roxb.) Meisne.) grown in Binh Minh town, Vinh Long province, Vietnam; Method: Fertilizer dose of 3-4 kg/tree/year; Metric: Fruit yield (99.5-107.1 kg/tree)"
    },
    {
        "question": "Trong nghiên cứu về cây thanh trà ở Vĩnh Long, các loại phân bón hóa học nào đã được sử dụng?",
        "ground_truth": "Các loại phân bón được sử dụng là Urea, KCl và DAP (Diammonium phosphate).",
        
        "chatbot_answer": "Dựa trên dữ liệu từ đồ thị tri thức, thông tin về tên gọi cụ thể của các loại phân bón hóa học (ví dụ: NPK, Urea, Kali...) không được liệt kê chi tiết trong ngữ cảnh hiện tại. Tuy nhiên, nghiên cứu cung cấp các thông tin liên quan đến việc sử dụng phân bón như sau: Liều lượng phân bón (Fertilizer doses): Nghiên cứu tập trung vào việc thử nghiệm các mức liều lượng khác nhau, trong đó có mức 3-4 kg/cây/năm. 🧪 Mục đích sử dụng: Các mức phân bón này được áp dụng để nghiên cứu ảnh hưởng của chúng đối với Năng suất và chất lượng của cây thanh trà (Bouea oppositifolia (Roxb.) Meisne.) tại thị xã Bình Minh, tỉnh Vĩnh Long. 🍈 Phương pháp bố trí: Việc bón phân được thực hiện dựa trên phương pháp Khối nghiệm thức ngẫu nhiên hoàn toàn (Completely randomized block design). 📊 Nếu bạn cần biết chi tiết về thành phần hóa học cụ thể, thông tin này hiện không có dữ liệu chi tiết trong corpus được cung cấp.",
        
        "context": "Effects of fertilizer doses on yield and quality of gandaria (Bouea oppositifolia (Roxb.) Meisne.) grown in Binh Minh town, Vinh Long province, Vietnam; Fertilizer dose of 3-4 kg/tree/year; Completely randomized block design; Yield and quality of gandaria"
    },

    # --- Bài báo 4: Đa dạng di truyền gốc ghép ớt ---
    {
        "question": "Phương pháp nào được dùng làm chỉ thị phân tử để đánh giá đa dạng di truyền của gốc ghép ớt?",
        "ground_truth": "Nghiên cứu sử dụng chỉ thị Inter-Simple Sequence Repeat (ISSR marker).",
        
        "chatbot_answer": "Dựa trên dữ liệu từ đồ thị tri thức, phương pháp chính được sử dụng làm chỉ thị phân tử để đánh giá đa dạng di truyền của gốc ghép ớt là: Chỉ thị ISSR (Inter-Simple Sequence Repeat): Đây là một kỹ thuật dấu vân tay DNA dựa trên phản ứng chuỗi PCR (Polymerase Chain Reaction), được thiết kế đặc biệt để đánh giá đa dạng sinh học và biến dị di truyền ở thực vật. 🧬 Kỹ thuật PCR: Được sử dụng để nhân bản các đoạn DNA cụ thể phục vụ cho việc phân tích chỉ thị phân tử. Phương pháp tách chiết DNA: Sử dụng đệm ly giải CTAB (Cetyltrimethylammonium bromide) để thu nhận DNA tổng số từ mô thực vật. Phân tích dữ liệu di truyền: Chỉ số tương đồng Jaccard (Jaccard's similarity index): Dùng để tính toán mức độ tương đồng giữa các giống ớt. Phân tích cụm UPGMA (Unweighted Pair Group Method with Arithmetic Mean): Sử dụng để xây dựng giản đồ hình cây (dendrogram) nhằm thể hiện mối quan hệ di truyền. 📊 Phần mềm STATISTICA ver. 5.5: Được dùng để xử lý thống kê và phân tích cụm.",
        
        "context": "ASSESSMENT OF GENETIC DIVERSITY OF CHILI ROOTSTOCK USING INTER-SIMPLE SEQUENCE REPEAT (ISSR) MARKER (Paper); Inter-Simple Sequence Repeat (ISSR) marker (Method); Genetic diversity of chili rootstock (Concept); UPGMA cluster analysis (Method)"
    },
    {
        "question": "Phân tích cụm UPGMA cho thấy khoảng cách đồng dạng di truyền của gốc ghép ớt nằm trong khoảng nào?",
        "ground_truth": "Khoảng cách đồng dạng di truyền (Genetic similarity range) đạt từ 2.00 đến 7.81.",
        
        "chatbot_answer": "Dựa trên dữ liệu từ đồ thị tri thức, kết quả phân tích cụm UPGMA cluster analysis cho thấy khoảng cách di truyền của các giống gốc ghép ớt như sau: 🧬 Khoảng cách di truyền (Genetic similarity range): Nằm trong khoảng từ 2,00 đến 7,81. 📊 Ý nghĩa: Đây là giá trị được tính toán để đánh giá mức độ đa dạng di truyền giữa các giống gốc ghép ớt trong nghiên cứu.",
        
        "context": "Genetic similarity range 2.00-7.81; UPGMA cluster analysis; ASSESSMENT OF GENETIC DIVERSITY OF CHILI ROOTSTOCK USING INTER-SIMPLE SEQUENCE REPEAT (ISSR) MARKER"
    },

    # --- Bài báo 5: Tiêu chảy ở heo con ---
    {
        "question": "Than hoạt tính (Activated charcoal) và giấm gỗ (Wood vinegar) được nghiên cứu để điều trị bệnh gì?",
        "ground_truth": "Chúng được dùng để phòng ngừa và điều trị bệnh tiêu chảy ở heo con (Piglet diarrhea).",
        
        "chatbot_answer": "Dựa trên dữ liệu từ đồ thị tri thức, Than hoạt tính (Activated charcoal) và Giấm gỗ (Wood vinegar) được nghiên cứu để phòng ngừa và điều trị bệnh lý sau: 🐷 Bệnh tiêu chảy ở heo con (Piglet diarrhea): Đây là trọng tâm chính của nghiên cứu nhằm đánh giá hiệu quả của hai hoạt chất này trong việc kiểm soát tình trạng tiêu chảy. 🦠 Cơ chế tác động: Than hoạt tính: Được sử dụng để hấp phụ các vi khuẩn có hại và độc tố trong đường tiêu hóa. Giấm gỗ: Đóng vai trò là chất axit hóa hữu cơ giúp khử trùng đường tiêu hóa và kích thích sự phát triển của các vi sinh vật có lợi. Nghiên cứu này cũng liên quan đến các nỗ lực giảm thiểu tình trạng Kháng kháng sinh (Antibiotic resistance) bằng cách tìm kiếm các phương pháp thay thế trong chăn nuôi.",
        
        "context": "Study on effectiveness of activated charcoal and wood vinegar on prevention of piglet diarrhea (Paper); Activated charcoal (Method); Wood vinegar (Method); Antibiotic resistance (Concept)"
    },
    {
        "question": "Tỷ lệ tiêu chảy ở heo con theo mẹ (suckling pigs) khi điều trị bằng than hoạt tính là bao nhiêu?",
        "ground_truth": "Tỷ lệ tiêu chảy trung bình ở heo con theo mẹ giảm xuống còn 7.37%.",
        
        "chatbot_answer": "Dựa trên dữ liệu từ đồ thị tri thức, kết quả nghiên cứu về hiệu quả của Than hoạt tính (Activated charcoal) đối với heo con theo mẹ như sau: 🐷 Tỷ lệ tiêu chảy: Tỷ lệ tiêu chảy trung bình ở heo con theo mẹ (suckling pigs) trong nhóm thực nghiệm sử dụng than hoạt tính là 7,37%. 📊 Phạm vi nghiên cứu: Chỉ số này được ghi nhận trong nghiên cứu đánh giá hiệu quả của than hoạt tính và giấm gỗ trong việc phòng ngừa tiêu chảy ở heo con. Ngoài ra, nghiên cứu cũng ghi nhận tỷ lệ tiêu chảy ở nhóm heo sau cai sữa (post weaning pigs) thấp hơn, chỉ ở mức 1,32%.",
        
        "context": "Study on effectiveness of activated charcoal and wood vinegar on prevention of piglet diarrhea (Paper), Average ratio of diarrhea in suckling pigs (7.37%) (Metric), Activated charcoal (Method)"
    },

    # --- Bài báo 6: Ủ chua lục bình cho cừu ---
    {
        "question": "Khi bổ sung lục bình ủ chua (EWH30), mức tăng trọng hàng ngày của cừu đạt bao nhiêu?",
        "ground_truth": "Mức tăng trọng hàng ngày của cừu đạt 57.3g (Daily weight gain 57.3g for EWH30).",
        
        "chatbot_answer": "Dựa trên dữ liệu từ đồ thị tri thức, khi bổ sung lục bình ủ chua (Water hyacinth silage) ở mức thay thế 30% (EWH30) trong khẩu phần ăn, mức tăng trưởng của cừu đạt được như sau: 🐑 Mức tăng trọng hàng ngày (Daily weight gain): Đạt 57,3g/ngày. 📊 Bối cảnh: Đây là tỷ lệ tăng trưởng cụ thể được ghi nhận cho nghiệm thức thay thế 30% thức ăn thô bằng lục bình ủ chua trong nghiên cứu thực hiện tại Đồng bằng sông Cửu Long.",
        
        "context": "Daily weight gain (57.3g for EWH30), Water hyacinth silage (EWH), EFFECTS OF WATER HYACINTH SILAGE IN DIETS ON FEED INTAKE, DIGESTIBILITY AND RUMEN PARAMETERS OF SHEEP (Ovis aries) IN THE MEKONG DELTA OF VIETNAM"
    },

    # --- Bài báo: Phát hiện đám đông với YOLOv3 (IT / Computer Vision) ---
    {
        "question": "Trong nghiên cứu phát hiện đám đông, mô hình YOLOv3 sử dụng kiến trúc nào làm backbone (mạng xương sống) và kiến trúc nào để tạo dự đoán?",
        "ground_truth": "Mô hình YOLOv3 sử dụng kiến trúc Darknet-53 làm backbone và Feature Pyramid Networks (FPN) để tạo dự đoán.",
        
        "chatbot_answer": "Dựa trên dữ liệu từ đồ thị tri thức, thông tin về kiến trúc của mô hình YOLOv3 trong nghiên cứu phát hiện đám đông được xác định như sau: 🦴 Mạng xương sống (Backbone): Mô hình sử dụng kiến trúc Darknet-53. 🔮 Kiến trúc dự đoán: Không có dữ liệu cụ thể trong corpus về tên gọi riêng biệt của kiến trúc dùng để tạo dự đoán; ngữ cảnh chỉ xác định YOLOv3 là mô hình phát hiện đối tượng thời gian thực cốt lõi được sử dụng trong hệ thống.",
        
        "context": "Detection of Crowd concentrations with YOLOv3 (Paper), YOLOv3 (Method), Darknet-53 (Method), Feature Pyramid Networks (FPN) (Method)"
    },
    {
        "question": "Thuật toán gom nhóm người (Detecting groups of people) sắp xếp danh sách các bounding box theo tiêu chí nào?",
        "ground_truth": "Thuật toán sắp xếp danh sách các bounding box theo thứ tự tăng dần của giá trị tọa độ x ở góc trên bên trái (x-coordinate value of the top-left corner point).",
        
        "chatbot_answer": "Dựa trên dữ liệu từ đồ thị tri thức, không có dữ liệu về tiêu chí sắp xếp cụ thể (ví dụ: theo tọa độ hay điểm tin cậy) của danh sách các bounding box trong thuật toán gom nhóm người được đề cập trong corpus. Thông tin hiện có chỉ xác định: 🧪 Thuật toán sử dụng: Hệ thống sử dụng thuật toán Overlapping bounding boxes grouping algorithm (Thuật toán gom nhóm các khung bao chồng lấp) để nhóm các cá nhân đã phát hiện được thành các đám đông. 📊 Hiệu quả: Thuật toán này giúp bài báo đạt được độ chính xác trung bình 96,33% đối với các nhóm người nói chung và 98% đối với các nhóm người đông đúc.",
        
        "context": "Detection of Crowd concentrations with YOLOv3 (Paper), Overlapping bounding boxes grouping algorithm (Method), Average accuracy of people groups (96.33%) (Metric), Average accuracy of crowded groups (98%) (Metric)"
    },
    {
        "question": "Hệ thống phát hiện đám đông được thử nghiệm trên các bộ dữ liệu (dataset) nào và đạt độ chính xác bao nhiêu trong việc nhận diện các nhóm người đông (crowded groups)?",
        "ground_truth": "Hệ thống được thử nghiệm trên bộ dữ liệu STCrowd, SmartCity và dữ liệu tự thu thập, đạt độ chính xác trung bình 98% cho nhóm người đông.",
        
        "chatbot_answer": "Dựa trên dữ liệu từ đồ thị tri thức, hệ thống phát hiện đám đông trong nghiên cứu Detection of Crowd concentrations with YOLOv3 được thử nghiệm và đạt kết quả như sau: 📊 Các bộ dữ liệu (Dataset) thử nghiệm: STCrowd: Bộ dữ liệu công khai dùng để đánh giá khả năng phát hiện đám đông. SmartCity: Bộ dữ liệu công khai được sử dụng để kiểm tra phương pháp đề xuất. Self-collected dataset: Bộ dữ liệu tự thu thập từ các camera giám sát tại Thành phố Trà Vinh. 🎯 Độ chính xác: Hệ thống đạt độ chính xác trung bình là 98% trong việc nhận diện cụ thể các nhóm người đông (crowded groups).",
        
        "context": "Detection of Crowd concentrations with YOLOv3 (Paper), YOLOv3 (Method), STCrowd (Dataset), SmartCity (Dataset), Self-collected dataset (Dataset), Average accuracy of crowded groups (98%) (Metric)"
    },

    # --- Bài báo 9: Chiết xuất Melastoma malabathricum ---
    {
        "question": "Phương pháp nào được sử dụng để xác định hàm lượng polyphenol tổng số (Total polyphenol content)?",
        "ground_truth": "Phương pháp Folin-Ciocalteu assay được sử dụng.",
        
        "chatbot_answer": "Dựa trên dữ liệu từ Knowledge Graph, phương pháp chính được sử dụng để xác định Hàm lượng polyphenol tổng số là Phương pháp Folin-Ciocalteu (Folin-Ciocalteu method/assay). Phương pháp này sử dụng thuốc thử Folin-Ciocalteu để xác định nồng độ của các hợp chất phenolic. Ngoài ra, Phương pháp đáp ứng bề mặt (RSM) cũng được dùng để tối ưu hóa điều kiện chiết xuất.",
        
        "context": "Total polyphenol content (Concept & Metric), Folin-Ciocalteu method (Method), Folin-Ciocalteu reagent method (Method), Folin-Ciocalteu assay (Method), Response Surface Methodology (RSM) (Method)"
    },

    # --- Bài báo 10: Chiết xuất thực vật Elephantopus ---
    {
        "question": "Liều lượng an toàn, không gây độc (Non-toxic dose) trong thí nghiệm OECD 420 trên chuột là bao nhiêu?",
        "ground_truth": "Liều lượng không gây độc là 8,000 mg/kg.",
        
        "chatbot_answer": "Dựa trên dữ liệu từ đồ thị tri thức, dưới đây là thông tin về liều lượng không gây độc trong thí nghiệm OECD 420:\nLiều lượng không gây độc (Non-toxic dose): 8,000 mg/kg 🧪.\nĐối tượng thử nghiệm: Chuột nhắt (Mus musculus).\nChi tiết thí nghiệm:\nĐây là mức liều cao nhất được thử nghiệm mà không ghi nhận trường hợp tử vong nào ở đối tượng Mus musculus.\nThí nghiệm được thực hiện thông qua mô hình chuẩn hóa OECD 420 model, dùng để đánh giá độc tính cấp tính qua đường miệng (Acute oral toxicity).\nDữ liệu này nằm trong nghiên cứu về độc tính cấp tính, khả năng kháng khuẩn và chống oxy hóa của các loài cây Elephantopus mollis H.B.K. và Elephantopus scaber L.",
        
        "context": "OECD 420 model (Method), Non-toxic dose (8,000 mg/kg) (Metric), Acute toxicity, antibacterial and antioxidant abilities of Elephantopus mollis H.B.K. and Elephantopus scaber L (Paper)"
    },
    {
        "question": "Khả năng chống oxy hóa (EC50) của chiết xuất hoa E. scaber đo được bằng phương pháp DPPH là bao nhiêu?",
        "ground_truth": "Giá trị EC50 là 59.9778 µg/mL.",
        
        "chatbot_answer": "Dựa trên dữ liệu từ Knowledge Graph, khả năng chống oxy hóa của chiết xuất hoa Elephantopus scaber L. được xác định với các thông số cụ thể sau:\n🌸 Thực thể nghiên cứu: Chiết xuất từ hoa của loài Elephantopus scaber L. (một loài cây thân thảo lâu năm được nghiên cứu về hiệu quả dược lý).\n🧪 Phương pháp đo lường: Thử nghiệm quét gốc tự do DPPH (DPPH free radical scavenging activity assay).\n📊 Chỉ số EC50: Nồng độ hiệu quả tối đa một nửa (Half maximal effective concentration) đo được là 59.9778 µg/mL.\nThông tin này nằm trong nghiên cứu so sánh với loài E. mollis, vốn có chỉ số EC50 thấp hơn (32.2051 µg/mL), cho thấy khả năng chống oxy hóa của E. scaber ở mức độ trung bình trong phạm vi nghiên cứu này.",
        
        "context": "Acute toxicity, antibacterial and antioxidant abilities of Elephantopus mollis H.B.K. and Elephantopus scaber L. (Paper), DPPH free radical scavenging activity assay (Method), EC50 (59.9778 µg/mL) (Metric), Elephantopus scaber L. (Concept)"
    },
    {
        "question": "Tác giả Nguyễn Trọng Hồng Phúc liên kết với tổ chức nào thuộc Đại học Cần Thơ?",
        "ground_truth": "Tác giả thuộc School of Education (Khoa Sư phạm), Can Tho University.",
        
        "chatbot_answer": "Dựa trên dữ liệu từ Knowledge Graph, tác giả Nguyễn Trọng Hồng Phúc (Nguyen Trong Hong Phuc) liên kết với tổ chức sau thuộc Đại học Cần Thơ:\nSchool of Education, Can Tho University (Khoa Sư phạm, Trường Đại học Cần Thơ) 🏫.\nThông tin bổ sung từ ngữ cảnh:\nNguyễn Trọng Hồng Phúc đóng vai trò là tác giả chính và tác giả liên hệ trong các nghiên cứu.\nCác công trình nghiên cứu tiêu biểu của tác giả bao gồm:Acute toxicity, antibacterial and antioxidant abilities of Elephantopus mollis H.B.K. and Elephantopus scaber L. 🌿\nDiversity of medicinal plant resources on Lai Son Island, Kien Giang province. 🗺️",
        
        "context": "Nguyen Trong Hong Phuc (Author), School of Education, Can Tho University (Institution)"
    },
    {
        "question": "Lesson study (Nghiên cứu bài học) được định nghĩa như thế nào trong bài báo?",
        "ground_truth": "Lesson study là một hình thức nghiên cứu do giáo viên thúc đẩy (bắt nguồn từ Nhật Bản), trong đó các giáo viên làm việc cùng nhau để cải thiện một khía cạnh cụ thể trong quá trình học tập của học sinh. Đây là một chu trình tìm tòi khuyến khích người dạy thử nghiệm, quan sát và cải tiến.",
        "chatbot_answer": "Dựa trên dữ liệu từ biểu đồ tri thức, Lesson Study (Nghiên cứu bài học) được định nghĩa và mô tả với các đặc điểm chính sau: Bản chất: Là một phương pháp tiếp cận hợp tác (collaborative approach) nhằm phát triển chuyên môn cho giáo viên. 🤝 Quy trình thực hiện: Bao gồm các bước tuần hoàn như thiết kế, giảng dạy và tinh chỉnh (refining) các bài học. 📝Đặc điểm cốt lõi: Đây là phương pháp do giáo viên dẫn dắt, tập trung vào việc truy vấn hợp tác và thực hiện các nghiên cứu dựa trên lớp học. 🏫 Ngữ cảnh ứng dụng: Trong bài báo, phương pháp này được áp dụng cụ thể cho sự phát triển của giáo viên tiếng Anh (EFL) tại Việt Nam. 🇻🇳",
        "context": "Lesson Study (Method/Concept); Using lesson study for teacher development: A case study of Vietnamese EFL teachers' reflections (Paper); English as a Foreign Language (EFL) Education (Domain)"
    },
    {
        "question": "Nghiên cứu đã so sánh việc thực hành \"Lesson study\" ở hai địa điểm nào?",
        "ground_truth": "Nghiên cứu đã so sánh việc thực hành \"Lesson study\" giữa tỉnh Quirino ở Philippines và thành phố Cần Thơ ở Việt Nam.",
        "chatbot_answer": "Dựa trên dữ liệu từ biểu đồ tri thức, nghiên cứu đã thực hiện một phân tích đa văn hóa nhằm so sánh việc thực hành Lesson study (Nghiên cứu bài học) tại hai quốc gia sau: Philippines 🇵🇭, Việt Nam 🇻🇳, Nghiên cứu này được thực hiện dưới dạng một phân tích đa văn hóa (cross-cultural analysis) để tìm hiểu sự khác biệt hoặc tương đồng trong việc áp dụng phương pháp này tại hai địa điểm trên.",
        "context": "Lesson study: A cross-cultural analysis between the Philippines and Viet Nam (Paper); Lesson Study (Method)"
    },
    {
        "question": "Nghiên cứu đã sử dụng hàm sản xuất nào để phân tích năng suất và rủi ro trong sản xuất lợn ở Hưng Yên?",
        "ground_truth": "Nghiên cứu đã sử dụng hàm sản xuất Cobb-Douglas để phân tích năng suất và nắm bắt các tác động của giá trị trung bình (mean), phương sai (variance) và độ lệch (skewness).",
        "chatbot_answer": "Dựa trên dữ liệu từ biểu đồ tri thức, nghiên cứu về sản xuất lợn tại Hưng Yên đã sử dụng hàm sản xuất sau để phân tích năng suất và rủi ro: Hàm sản xuất Cobb-Douglas (Cobb-Douglas production function): Đây là phương pháp chính được sử dụng để phân tích các yếu tố tác động đến năng suất và đánh giá mức độ rủi ro trong sản xuất. 📈Thông tin này nằm trong phạm vi nghiên cứu của bài báo: PIG PRODUCTION AND RISK EXPOSURE: A CASE STUDY IN HUNG YEN, VIETNAM.",
        "context": "Cobb-Douglas production function (Method); PIG PRODUCTION AND RISK EXPOSURE: A CASE STUDY IN HUNG YEN, VIETNAM (Paper); Pig production (Concept); Production risk (Concept)"
    },
    {
        "question": "Phương pháp nào được sử dụng để phát triển các thanh nano ZnO (ZnO nanorods) và hạt nano vàng (Au NPs) trên đế kính phủ FTO?",
        "ground_truth": "Phương pháp sol-gel được sử dụng để nuôi cấy thanh nano ZnO trên đế FTO, sau đó các hạt nano vàng (Au NPs) được biến tính trên các thanh nano ZnO bằng phương pháp thủy nhiệt (hydrothermal method).",
        "chatbot_answer": "Các thanh nano ZnO được phát triển trên đế kính phủ FTO bằng phương pháp sol–gel, sau đó được biến tính bằng các hạt nano vàng Au NPs thông qua phương pháp thủy nhiệt.",
        "context": "Sol-gel method, Hydrothermal method, The properties of ZnO nanorods modified by Au nanoparticles for galactose biosensor application"
    },
    {
        "question": "Điện cực GOx|Au-ZnO|FTO phản ứng với dải nồng độ galactose tuyến tính là bao nhiêu?",
        "ground_truth": "Cảm biến sinh học sử dụng điện cực này có khả năng phát hiện tuyến tính trong dải nồng độ galactose từ 40 mM đến 230 mM.",
        "chatbot_answer": "Dựa trên dữ liệu từ biểu đồ tri thức, điện cực GOx|Au-ZnO|FTO được sử dụng trong ứng dụng cảm biến sinh học galactose có thông số về dải nồng độ phản ứng như sau: Dải nồng độ tuyến tính (Linear detection range): Từ 40 mM đến 230 mM. 🧪 Đây là khoảng nồng độ mà cảm biến đạt hiệu quả đo lường và phản ứng ổn định đối với galactose.",
        "context": "Linear detection range (40 mM to 230 mM); The properties of ZnO nanorods modified by Au nanoparticles for galactose biosensor application; Galactose oxidase enzyme (GOx); FTO substrate"
    },
    {
        "question": "Nghiên cứu của Trịnh Chí Thâm nhằm mục đích gì?",
        "ground_truth": "Nghiên cứu nhằm khám phá nhận thức của các giảng viên về việc áp dụng tư duy phản biện trong quá trình giáo dục sinh viên sư phạm chuyên ngành Địa lý tại trường Đại học Cần Thơ, Việt Nam.",
        "chatbot_answer": "Dựa trên dữ liệu từ biểu đồ tri thức, các nghiên cứu của tác giả Trịnh Chí Thâm (Trinh Chi Tham) từ Trường Sư phạm, Đại học Cần Thơ tập trung vào các mục đích chính sau: Về giáo dục sư phạm: Nghiên cứu nhận thức của giảng viên về việc áp dụng tư duy phản biện trong đào tạo sinh viên sư phạm Địa lý tại Đại học Cần Thơ. 🎓Về phương pháp giảng dạy: Tìm hiểu về nghệ thuật quan sát lớp học thông qua nghiên cứu điển hình tại Đại học Quirino (Philippines) và Đại học Cần Thơ. 🏫Về thích ứng biến đổi khí hậu: Nghiên cứu về học tập chuyển đổi (transformative learning) trong mô hình VACB bền vững nhằm thích ứng với biến đổi khí hậu tại huyện Phong Điền, thành phố Cần Thơ. 🌱",
        "context": "Trinh Chi Tham (Author); Can Tho University (Institution); LECTURERS' PERCEPTIONS ABOUT EMPLOYING CRITICAL THINKING IN EDUCATING GEOGRAPHY PEDAGOGY STUDENTS AT CAN THO UNIVERSITY, VIETNAM (Paper); The art of classroom observation: The Case of Quirino State University and Can Tho University (Paper); Transformative learning in resilient VACB model adapting to climate change in Phong Dien district, Can Tho city (Paper)"
    },
    {
        "question": "Ưu điểm của phương pháp sulfo-phospho-vanillin (SPV) vi mô được đề xuất trong nghiên cứu định lượng lipid là gì?",
        "ground_truth": "Phương pháp này chỉ cần một lượng mẫu nhỏ (dưới 100 µg/mL), tiết kiệm thời gian và công sức khi phân tích số lượng lớn mẫu (khoảng 1 giờ để hoàn thành), và mang lại sự ổn định màu sắc nhất quán hơn giữa hàm lượng lipid và nồng độ thuốc thử.",
        "chatbot_answer": "Dựa trên dữ liệu từ biểu đồ tri thức, phương pháp sulfo-phospho-vanillin (SPV) vi mô (được thực hiện thông qua đo quang phổ) dùng trong định lượng lipid có các ưu điểm chính sau: Nhanh chóng (Rapid): Đây là một quy trình xét nghiệm được phát triển để thực hiện việc đo lường lipid một cách lẹ làng. ⚡Kinh tế (Economical): Phương pháp này được đánh giá là ít tốn kém, giúp tiết kiệm chi phí trong quá trình phân tích. 💰 Đơn giản (Simple): Nghiên cứu mô tả đây là một phương pháp quang phổ đơn giản để định lượng tổng lượng lipid trong cả mẫu thực vật và động vật. 🧪 Hiệu suất cao ở quy mô vi mô: Phương pháp sử dụng đĩa 96 giếng (96-well microplate) và máy đọc đĩa SH-1200 (SH-1200 microplate reader), cho phép xử lý mẫu ở quy mô nhỏ một cách hiệu quả. 🔬",
        "context": "Colorimetric sulfo-phosphovanillin (SPV) assay (Method); A simple spectrophotometric method for quantifying total lipids in plants and animals (Paper); 96-well microplate (Method); Total lipid quantification (Concept)"
    },
    {
        "question": "Dung môi nào được sử dụng để chiết xuất lipid tổng số từ ấu trùng ruồi giấm Drosophila melanogaster?",
        "ground_truth": "Hỗn hợp dung môi chloroform/methanol (tỷ lệ 1:1) được sử dụng để chiết xuất lipid tổng số từ mẫu động vật này.",
        "chatbot_answer": "Dựa trên dữ liệu từ Knowledge Graph, câu trả lời cho câu hỏi của bạn như sau: Dung môi được sử dụng để chiết xuất lipid tổng số từ ấu trùng ruồi giấm (Drosophila melanogaster) là: 🧪 Hỗn hợp Chloroform/methanol: Đây là hỗn hợp dung môi chuyên dụng được sử dụng cho quá trình chiết xuất và định lượng lipid tổng số từ các mẫu sinh học, bao gồm cả ấu trùng ruồi giấm.",
        "context": "Nguồn tham chiếu Chloroform/methanol (Method); Drosophila melanogaster larvae (BiologicalSample)"
    },
    {
        "question": "Phản ứng của phương pháp SPV đo quang phổ dựa trên nguyên lý nào?",
        "ground_truth": "Phản ứng dựa trên việc lipid tác dụng với axit sulfuric đậm đặc ở nhiệt độ cao để tạo thành các ion carbonium, sau đó các ion này phản ứng với este vanillin phosphate để tạo ra phức hợp màu hồng có thể đo được bằng quang phổ (ở bước sóng 530 nm).",
        "chatbot_answer": "Dựa trên dữ liệu từ Knowledge Graph, nguyên lý phản ứng của phương pháp Colorimetric sulfo-phosphovanillin (SPV) assay để đo quang phổ lipid tổng số như sau: 🧪 Giai đoạn chuyển hóa: Sulfuric acid (axit sulfuric) đậm đặc chuyển đổi các sản phẩm lipid không bão hòa thành các chất trung gian có hoạt tính (dạng giống carbocation). 🎨 Giai đoạn tạo màu: Các chất trung gian này phản ứng với Phospho-vanillin reagent (hỗn hợp vanillin và axit phosphoric) để tạo thành một chất mang màu (chromophore) có màu hồng. 📊 Định lượng: Cường độ hấp thụ (absorbance) của phức hợp màu hồng này tỉ lệ thuận với nồng độ lipid tổng số có trong mẫu.",
        "context": "SPV reaction principle; Colorimetric sulfo-phosphovanillin (SPV) assay; Sulfuric acid; Phospho-vanillin reagent"
    },
    {
        "question": "Hàm lượng polyphenol và flavonoid tổng số thu được ở điều kiện tối ưu là bao nhiêu?",
        "ground_truth": "Hàm lượng thu được ở điều kiện tối ưu là 921 mg GAE/100g DM đối với polyphenol tổng số và 563 mg QE/100g DM đối với flavonoid tổng số.",
        "chatbot_answer": "Dựa trên dữ liệu nghiên cứu về cây Thuốc dòi (Pouzolzia zeylanica L. Benn), hàm lượng các hợp chất thu được ở điều kiện tối ưu được ghi nhận như sau: Hàm lượng polyphenol tổng số (TPC): Đạt mức 921 mgGAE/100g DM. 🌿Hàm lượng flavonoid tổng số: Không có dữ liệu về giá trị định lượng cụ thể cho chỉ số này ở điều kiện tối ưu trong corpus.",
        "context": "Total polyphenol content (921 mgGAE/100g DM); OPTIMIZATION OF POLYPHENOL, FLAVONOID AND TANNIN EXTRACTION CONDITIONS FROM Pouzolzia zeylanica L. BENN USING RESPONSE SURFACE METHODOLOGY"
    },
    {
        "question": "Nghiên cứu đã sử dụng mô hình kinh tế lượng nào để phân tích các yếu tố quyết định khả năng tiếp cận tín dụng?",
        "ground_truth": "Dựa trên dữ liệu từ nghiên cứu về các yếu tố quyết định khả năng tiếp cận tín dụng của các doanh nghiệp vừa và nhỏ (SME) tại Cần Thơ, các mô hình kinh tế lượng được sử dụng bao gồm: Mô hình Probit (Probit model): Đây là một loại hồi quy trong đó biến phụ thuộc chỉ nhận hai giá trị (nhị phân), được sử dụng để mô hình hóa khả năng tiếp cận tín dụng chính thức. Mô hình lựa chọn Heckman (Heckman selection model): Phương pháp thống kê này được áp dụng để hiệu chỉnh sai số (bias) do việc lựa chọn mẫu không ngẫu nhiên trong quá trình phân tích.",
        "context": "DETERMINANTS OF ACCESS TO FORMAL CREDIT BY THE INDUSTRIAL AND CONSTRUCTIONAL SMALL AND MEDIUM ENTERPRISES IN CAN THO CITY, VIETNAM; Probit model; Heckman selection model"
    },
    {
        "question": "Mối liên hệ giữa quy mô doanh nghiệp và khả năng tiếp cận tín dụng được đề cập như thế nào trong bài báo?",
        "ground_truth": "Các doanh nghiệp có quy mô lớn hơn sẽ có khả năng tiếp cận tín dụng ngân hàng cao hơn so với các doanh nghiệp nhỏ, do họ có lợi thế về tổng giá trị tài sản lớn hơn để sử dụng làm tài sản thế chấp.",
        "chatbot_answer": "Doanh nghiệp quy mô lớn có khả năng vay được vốn ngân hàng cao hơn doanh nghiệp nhỏ khoảng 16,7%. Mỗi khi doanh thu tăng thêm 1 triệu đồng, khả năng tiếp cận khoản vay ngân hàng tăng khoảng 12,6%.",
        "context": "DETERMINANTS OF ACCESS TO FORMAL CREDIT BY THE INDUSTRIAL AND CONSTRUCTIONAL SMALL AND MEDIUM ENTERPRISES IN CAN THO CITY, VIETNAM; Increase in borrowing ability (16.7%); Increase in bank loan possibility (12.6%)"
    },
    {
        "question": "Điều kiện nhiệt độ nào được coi là lý tưởng nhất để duy trì màu sắc và giảm sụt giảm trọng lượng của nấm mỡ (Agaricus bisporus) tươi trong thời gian bảo quản?",
        "ground_truth": "Nhiệt độ bảo quản lý tưởng nhất là dưới 6°C (đặc biệt là ở mức 1°C). Ở nhiệt độ thấp, màu trắng của nấm có thể được duy trì hơn 9 ngày và tỷ lệ hao hụt trọng lượng cũng ở mức thấp nhất.",
        "chatbot_answer": "Dựa trên dữ liệu từ Knowledge Graph, điều kiện nhiệt độ và các yếu tố liên quan để duy trì chất lượng nấm mỡ (Agaricus bisporus) tươi được ghi nhận như sau: Nhiệt độ bảo quản lý tưởng: Nghiên cứu đã thử nghiệm các mức nhiệt độ 1°C, 6°C, và 12°C. Trong đó, nhiệt độ thấp (như 1°C) được coi là tối ưu hơn vì khi bảo quản ở 12°C trong điều kiện không khí bình thường, thời hạn sử dụng (Shelf-life) của nấm bị rút ngắn xuống còn dưới 3 ngày. 🌡️Kiểm soát sụt giảm trọng lượng (Weight loss): Sự sụt giảm khối lượng do bay hơi nước và hô hấp dao động trong khoảng 0.7% đến 3.6% sau 9 ngày bảo quản. Việc duy trì nhiệt độ thấp giúp giảm thiểu tỷ lệ này. 💧 Duy trì màu sắc mũ nấm (Cap colour): Nhiệt độ là yếu tố quyết định để bảo vệ các thông số màu sắc như độ trắng (L*), sắc đỏ (a*) và sắc vàng (b*). 🍄Phương pháp hỗ trợ: Việc kết hợp nhiệt độ thấp với Bảo quản trong khí quyển kiểm soát (Controlled atmosphere storage) — điều chỉnh nồng độ O2 (3% đến 21%) và CO2 (0% đến 12%) — giúp kéo dài thời gian duy trì chất lượng cảm quan. 🧊",
        "context": "Storage temperature (1°C, 6°C, 12°C); Weight loss (0.7% to 3.6%); Shelf-life (less than 3 days); Cap colour; Controlled atmosphere storage; Effect of controlled atmosphere and storage temperature on the weight loss and cap colour of fresh mushrooms (Agaricus bisporus)"
    },
    {
        "question": "Các nhà nghiên cứu đã phân lập được những hợp chất mới nào từ chiết xuất chloroform của loài Hydrocotyle bonariensis (Rau má lá to)?",
        "ground_truth": "Nghiên cứu đã phân lập được hai alkaloid isoquinoline là tetrahydropalmatine và (-)-(S)-xylopinine, cùng với một hợp chất carbohydrate là ethyl 2-O-α-fructofuranoside.",
        "chatbot_answer": "Dựa trên dữ liệu từ Knowledge Graph, các nhà nghiên cứu đã phân lập được các hợp chất mới từ chiết xuất chloroform của loài Hydrocotyle bonariensis (Rau má lá to) như sau: Tetrahydropalmatine: Một loại alkaloid isoquinoline (thu được 16 mg). 🧬(-)-(S)-xylopinine: Một loại alkaloid isoquinoline (thu được 35 mg). 🧬Ethyl 2-O-α-fructofuranoside: Một hợp chất carbohydrate (thu được 10 mg). 🧪Các hợp chất này được phân lập bằng phương pháp Chloroform extraction và được xác định cấu trúc thông qua NMR spectroscopy (Phổ cộng hưởng từ hạt nhân) và HR-ESI-MS (Khối phổ phân giải cao).",
        "context": "TWO NEW ALKALOIDS AND A CARBOHYDRATE COMPOUND FROM THE SPECIES Hydrocotyle bonariensis COMM. EX LAM., FAMILY APIACEAE (Paper); Chloroform extraction (Method); Yield of tetrahydropalmatine (16 mg) (Metric); Yield of (-)-(S)-xylopinine (35 mg) (Metric);Yield of ethyl 2-O-α-fructofuranoside (10 mg) (Metric)"
    },
    {
        "question": "Phương pháp phân tích nào được sử dụng để xác định cấu trúc hóa học của các hợp chất phân lập được từ loài Hydrocotyle bonariensis?",
        "ground_truth": "Cấu trúc của các hợp chất này được xác định dựa trên phổ cộng hưởng từ hạt nhân (NMR) bao gồm 1H-NMR, 13C-NMR và phổ khối lượng (ESI-MS).",
        "chatbot_answer": "Phương pháp được sử dụng là NMR spectroscopy.",
        "context": "Chemical composition and antioxidant activity of Psidium guajava L. leaves; Primary investigating chemical constituents of bioactive extract from Centrostachys aquatica (R.Br.) Wall. ex Moq.-Tand; TWO NEW ALKALOIDS AND A CARBOHYDRATE COMPOUND FROM THE SPECIES Hydrocotyle bonariensis COMM. EX LAM., FAMILY APIACEAE"
    },
    {
        "question": "Các hợp chất tetrahydropalmatine và (-)-(S)-xylopinine có ý nghĩa như thế nào đối với hồ sơ hóa học thực vật của chi Hydrocotyle?",
        "ground_truth": "Đây là báo cáo đầu tiên chứng minh sự tồn tại của các alkaloid mang bộ khung isoquinoline (tetrahydropalmatine và (-)-(S)-xylopinine) từ chi thực vật Hydrocotyle (chi Rau má).",
        "chatbot_answer": "Dựa trên dữ liệu từ Knowledge Graph, hai hợp chất tetrahydropalmatine và (-)-(S)-xylopinine có ý nghĩa quan trọng đối với hồ sơ hóa học thực vật của chi Hydrocotyle như sau: Chất đánh dấu hóa học (Chemical markers): Các hợp chất này được xác định là những chất đánh dấu hóa học đặc trưng cho chi Hydrocotyle. 🧪Alkaloid mới: Đây là hai alkaloid mới được phát hiện và phân lập từ loài Hydrocotyle bonariensis (Rau má lá to), thuộc họ Hoa tán (Apiaceae). 🌿Hàm lượng phân lập: Nghiên cứu đã xác định cụ thể hiệu suất thu hồi của các hợp chất này từ mẫu chiết xuất: Tetrahydropalmatine: Thu được 16 mg. (-)-(S)-xylopinine: Thu được 35 mg. Việc xác định các alkaloid này giúp làm phong phú thêm dữ liệu về thành phần hóa học thực vật và hỗ trợ việc định danh các loài trong chi Hydrocotyle.",
        "context": "TWO NEW ALKALOIDS AND A CARBOHYDRATE COMPOUND FROM THE SPECIES Hydrocotyle bonariensis COMM. EX LAM., FAMILY APIACEAE; Yield of tetrahydropalmatine (16 mg);Yield of (-)-(S)-xylopinine (35 mg)"
    },
    {
        "question": "Phương pháp CuRLA giải quyết bài toán lái xe tự động bằng sự kết hợp của những thành phần kỹ thuật nào?",
        "ground_truth": "Phương pháp CuRLA kết hợp Deep Reinforcement Learning (sử dụng thuật toán PPO - Proximal Policy Optimization) với Curriculum Learning (học theo chương trình đào tạo tăng dần độ khó) và dùng Variational Autoencoder (VAE) để mã hóa biểu diễn trạng thái.",
        "chatbot_answer": "Phương pháp kết hợp các thành phần kỹ thuật chính: Deep Reinforcement Learning (DRL), Curriculum Learning, tác tử Proximal Policy Optimization (PPO), Variational Autoencoder (VAE).Một số yếu tố triển khai liên quan: môi trường mô phỏng CARLA, cơ chế phạt va chạm trong hàm phần thưởng, Huấn luyện theo curriculum hai giai đoạn, tăng dần độ khó của môi trường.",
        "context": "CuRLA: Curriculum Learning Based Deep Reinforcement Learning For Autonomous Driving; CuRLA; CARLA Simulator"
    },
    {
        "question": "Bộ dữ liệu mới được đề xuất trong nghiên cứu nhận diện cháy qua video có tên là gì và có những đặc điểm nào?",
        "ground_truth": "Bộ dữ liệu có tên là VLFFD (Video Library for Fire Frame Detection). Nó bao gồm 100 video gốc ở độ phân giải Full-HD và Ultra-HD được quay bằng nhiều camera khác nhau, mỗi video có thời lượng từ 3 đến 18 giây và được ghi với tốc độ 30 khung hình/giây.",
        "chatbot_answer": "Bộ dữ liệu được đề xuất là Video Library For Fire Frame Detection (VLFFD). Đặc điểm chính: Gồm 100 video.; Video có độ phân giải Full-HD và Ultra-HD.; Được ghi ở tốc độ 30 khung hình/giây.; Được xây dựng phục vụ nghiên cứu nhận diện và phát hiện cháy qua video.",
        "context": "Intelligent Video-Based Fire Detection: A Novel Dataset And Real-Time Multi-Stage Classification Approach; Video Library For Fire Frame Detection (VLFFD); VLFFD"
    },
    {
        "question": "Mức chi phí đầu tư trung bình và mức lợi nhuận thu được cho mỗi hecta mặt nước một năm của hệ thống canh tác tôm - rừng ngập mặn (mangrove-shrimp) tại khu vực ven biển tỉnh Sóc Trăng là bao nhiêu?",
        "ground_truth": "Nông dân đầu tư mức chi phí rất thấp, trung bình khoảng 3.6 ± 0.9 triệu VNĐ cho mỗi hecta mặt nước/năm, nhưng có thể thu được lợi nhuận gộp lên tới 37.9 ± 5.6 triệu VNĐ/ha/năm.",
        "chatbot_answer": "Các chỉ tiêu được báo cáo: Chi phí: Production costs (3.6 ±0.9 million VND/ha/year); Lợi nhuận: Net revenue (24 million VND/ha/year)",
        "context": "SUSTAINABILITY AND LIVELIHOOD OPPORTUNITIES FOR MANGROVE-SHRIMP FARMERS IN THE COASTAL AREAS OF SOCTRANG PROVINCE; Production costs (3.6 ±0.9 million VND/ha/year); Net revenue (24 million VND/ha/year)"
    },
    {
        "question": "Để đạt được độ chính xác tần số cao khi thực hiện kỹ thuật điều chế vector không gian (Space Vector Modulation) trên vi điều khiển STM32F1, tác giả đã đề xuất phương pháp mới nào?",
        "ground_truth": "Tác giả đã đề xuất và thử nghiệm một phương pháp mới cho việc quay vector (vector rotation) dựa trên số học điểm cố định (fixed-point arithmetic).",
        "chatbot_answer": "Phương pháp được đề xuất là phương pháp quay vector mới (Novel method for vector rotation). Nguyên lý/cách thực hiện: Phương pháp dựa trên hệ bánh răng đồng trục, kết hợp số học dấu phẩy cố định để nâng cao độ chính xác tần số. Kết quả liên quan: Độ phân giải tần số (4.6566 x 10^-6 Hz); Sai số tần số (0.004%)",
        "context": "Space Vector Modulation for Induction Motor on ARM-based Microcontroller; Novel method for vector rotation"
    },
    {
        "question": "Bài báo \"Lithocarpus encleisocarpus (Korth.) A. Camus a newly recorded species for Viet Nam and its phylogenetic relationship based on genome-wide SNPs\" đã ghi nhận thêm loài thực vật nào mới cho hệ thực vật Việt Nam?",
        "ground_truth": "Bài báo ghi nhận loài Lithocarpus encleisocarpus (Korth.) A.Camus là loài mới cho hệ thực vật Việt Nam.",
        "chatbot_answer": "Loài thực vật được ghi nhận mới cho hệ thực vật Việt Nam là Lithocarpus encleisocarpus (Korth.) A. Camus.",
        "context": "Lithocarpus encleisocarpus (Korth.) A. Camus a newly recorded species for Viet Nam and its phylogenetic relationship based on genome-wide SNPs"
    },
    {
        "question": "Hai hợp chất alkaloid mới và một hợp chất carbohydrate từ loài Rau má lá to (Hydrocotyle bonariensis) được phân lập thành công từ dịch chiết của dung môi nào?",
        "ground_truth": "Các hợp chất này được phân lập từ dịch chiết chloroform (chloroform extract) của cây.",
        "chatbot_answer": "Hai alkaloid mới và hợp chất carbohydrate được phân lập từ dịch chiết chloroform. Chloroform được dùng để phân lập các alkaloid isoquinoline.; Node bằng chứng: Chloroform extraction.",
        "context": "TWO NEW ALKALOIDS AND A CARBOHYDRATE COMPOUND FROM THE SPECIES Hydrocotyle bonariensis COMM. EX LAM., FAMILY APIACEAE; Yield of tetrahydropalmatine (16 mg)"
    },
  {
    "question": "Theo bài báo \"Predicting graduation grades using Machine Learning: A case study of Can Tho University students\", bộ dữ liệu nào được sử dụng để đánh giá các mô hình dự đoán xếp loại tốt nghiệp?",
    "ground_truth": "Bộ dữ liệu gồm kết quả tốt nghiệp của 7.837 sinh viên đại học thuộc 16 đơn vị đào tạo của Đại học Cần Thơ trong năm 2022.",
    "chatbot_answer": "Bộ dữ liệu được sử dụng là Graduation outcomes of 7,837 undergraduate students. Dữ liệu gồm sinh viên từ 16 đơn vị đào tạo của Đại học Cần Thơ trong năm 2022.",
    "context": "Predicting graduation grades using Machine Learning: A case study of Can Tho University students (Paper); Graduation outcomes of 7,837 undergraduate students (Dataset)."
  },
  {
    "question": "Theo bài báo \"Predicting graduation grades using Machine Learning: A case study of Can Tho University students\", phương pháp kiểm định chéo nào được sử dụng để đánh giá mô hình?",
    "ground_truth": "Nghiên cứu sử dụng phương pháp kiểm định chéo 15-fold cross-validation.",
    "chatbot_answer": "Phương pháp được sử dụng là 15-fold cross-validation. Đây là kỹ thuật kiểm định dùng để đánh giá hiệu năng của các thuật toán dự đoán.",
    "context": "Predicting graduation grades using Machine Learning: A case study of Can Tho University students (Paper); 15-fold cross-validation (Method)."
  },
  {
    "question": "Theo bài báo \"Predicting graduation grades using Machine Learning: A case study of Can Tho University students\", độ chính xác kiểm định chéo tốt nhất của mô hình Random Forest là bao nhiêu?",
    "ground_truth": "Random Forest đạt độ chính xác kiểm định chéo tốt nhất là 96,2% tại 9 folds.",
    "chatbot_answer": "Độ chính xác kiểm định chéo tốt nhất của mô hình Random Forest là 96,2%. Kết quả này đạt được tại 9 folds.",
    "context": "Predicting graduation grades using Machine Learning: A case study of Can Tho University students (Paper); Random Forest (Method); Cross-validation accuracy (96.2%) (Metric)."
  }
]

# Tạo DataFrame và xuất ra Excel
df = pd.DataFrame(data)
file_name = "tap_kiem_thu_graphrag.xlsx"
df.to_excel(file_name, index=False, engine='openpyxl')
print(f"✅ Đã tạo thành công file '{file_name}' với {len(data)} câu hỏi!")
print("Hãy mở ứng dụng GraphRAG, chat các câu hỏi này và copy kết quả/ngữ cảnh vào 2 cột còn trống nhé.")