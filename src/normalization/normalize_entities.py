import os
import json
import numpy as np
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from rapidfuzz import fuzz
from sklearn.metrics.pairwise import cosine_similarity

# --- CẤU HÌNH ---
INPUT_FOLDER = r'E:\LLM\data\extracted'     # Thư mục chứa JSON đã trích xuất
OUTPUT_FOLDER = r'E:\LLM\data\final_graph'  # Thư mục chứa JSON sạch để nạp Neo4j
MAPPING_LOG_FILE = 'entity_mapping.json'    # File ghi lại nhật ký gộp từ (để kiểm tra)

# Ngưỡng (Threshold)
SEMANTIC_THRESHOLD_HIGH = 0.92  # Nếu > 92% giống nghĩa -> Gộp luôn
SEMANTIC_THRESHOLD_MID = 0.80   # Nếu > 80% giống nghĩa...
FUZZY_THRESHOLD = 90            # ... và > 90% giống mặt chữ -> Gộp

# --- LOAD MODEL ---
print("⏳ Đang tải model Embedding (all-MiniLM-L6-v2)...")
model = SentenceTransformer('all-MiniLM-L6-v2')

def load_entities(folder):
    all_entities = {} 
    
    files = [f for f in os.listdir(folder) if f.endswith('.json')]
    print(f"📂 Đang đọc {len(files)} files để tìm thực thể...")

    for filename in tqdm(files):
        with open(os.path.join(folder, filename), 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except Exception:
                continue

            # --- KIỂM TRA TYPE AN TOÀN ---
            if not isinstance(data, dict):
                continue
                
            result = data.get('extraction_result', data)
            if not isinstance(result, dict):
                continue
                
            entities = result.get('entities', [])
            if not isinstance(entities, list):
                continue

            for ent in entities:
                if not isinstance(ent, dict):
                    continue
                e_type = ent.get('type')
                e_id = ent.get('id')
                if not e_type or not e_id:
                    continue
                e_type = str(e_type).strip()
                e_id = str(e_id).strip()

                if e_type not in all_entities:
                    all_entities[e_type] = set()
                all_entities[e_type].add(e_id)

    return {k: list(v) for k, v in all_entities.items()}

def resolve_entities(entity_list):
    """
    Thuật toán Hybrid: Kết hợp Embedding + Fuzzy để tìm các nhóm từ đồng nghĩa
    """
    if not entity_list: return {}
    
    # 1. Mã hóa tất cả tên thành Vector
    embeddings = model.encode(entity_list)
    
    # 2. Tính ma trận tương đồng (Cosine Similarity)
    sim_matrix = cosine_similarity(embeddings)
    
    mapping = {} # { "Tên_Cũ": "Tên_Chuẩn" }
    processed_indices = set()
    
    # 3. Duyệt từng thực thể để gom nhóm
    for i in range(len(entity_list)):
        if i in processed_indices: continue
        
        current_name = entity_list[i]
        group_indices = [i]
        processed_indices.add(i)
        
        for j in range(i + 1, len(entity_list)):
            if j in processed_indices: continue
            
            sim_score = sim_matrix[i][j]
            is_match = False
            
            # CASE A: Semantic cực cao (Gần như là một)
            if sim_score >= SEMANTIC_THRESHOLD_HIGH:
                is_match = True
                
            # CASE B: Semantic khá cao + Fuzzy cao (Viết tắt hoặc sai chính tả nhẹ)
            elif sim_score >= SEMANTIC_THRESHOLD_MID:
                fuzzy_score = fuzz.ratio(current_name.lower(), entity_list[j].lower())
                if fuzzy_score >= FUZZY_THRESHOLD:
                    is_match = True
            
            if is_match:
                group_indices.append(j)
                processed_indices.add(j)
        
        # Chọn tên chuẩn (Canonical Name) cho nhóm
        # Chiến thuật: Chọn tên DÀI NHẤT trong nhóm (thường đầy đủ nghĩa nhất)
        candidates = [entity_list[idx] for idx in group_indices]
        canonical_name = max(candidates, key=len) 
        
        # Lưu mapping
        for name in candidates:
            mapping[name] = canonical_name
            
    return mapping

def apply_mapping_and_save(input_folder, output_folder, full_mapping):
    """Áp dụng mapping vào file JSON và lưu ra thư mục mới"""
    if not os.path.exists(output_folder): os.makedirs(output_folder)

    files = [f for f in os.listdir(input_folder) if f.endswith('.json')]
    print("💾 Đang chuẩn hóa và lưu file sạch...")

    for filename in tqdm(files):
        try:
            with open(os.path.join(input_folder, filename), 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            continue
            
        if not isinstance(data, dict):
            continue

        result = data.get('extraction_result', {})
        if not isinstance(result, dict):
            result = {}
            
        entities = result.get('entities', [])
        if not isinstance(entities, list):
            entities = []
            
        relations = result.get('relations', [])
        if not isinstance(relations, list):
            relations = []

        # 1. Chuẩn hóa Entities
        new_entities = []
        seen_ids = set() # Tránh trùng lặp sau khi gộp
        id_map_local = {} # Map ID cũ -> ID mới trong phạm vi file này

        for ent in entities:
            if not isinstance(ent, dict): continue
            old_id = str(ent.get('id', '')).strip()
            e_type = str(ent.get('type', '')).strip()
            if not old_id or not e_type: continue

            # Lấy tên mới từ Global Mapping
            if e_type in full_mapping and old_id in full_mapping[e_type]:
                new_id = full_mapping[e_type][old_id]
            else:
                new_id = old_id # Giữ nguyên nếu không có trong map

            id_map_local[old_id] = new_id

            # Chỉ thêm nếu chưa tồn tại trong file này
            unique_key = (new_id, e_type)
            if unique_key not in seen_ids:
                ent['id'] = new_id
                new_entities.append(ent)
                seen_ids.add(unique_key)

        # 2. Chuẩn hóa Relations (Cập nhật source/target theo ID mới)
        new_relations = []
        for rel in relations:
            if not isinstance(rel, dict): continue
            src = str(rel.get('source', '')).strip()
            tgt = str(rel.get('target', '')).strip()
            if not src or not tgt: continue

            # Đổi tên source/target nếu có trong Mapping mù
            new_src = src
            new_tgt = tgt
            for e_type in full_mapping:
                if src in full_mapping[e_type]: new_src = full_mapping[e_type][src]
                if tgt in full_mapping[e_type]: new_tgt = full_mapping[e_type][tgt]

            rel['source'] = new_src
            rel['target'] = new_tgt
            new_relations.append(rel)

        # Cập nhật data
        if 'extraction_result' in data and isinstance(data['extraction_result'], dict):
            data['extraction_result']['entities'] = new_entities
            data['extraction_result']['relations'] = new_relations
        else:
             data['entities'] = new_entities
             data['relations'] = new_relations

        # Lưu file
        with open(os.path.join(output_folder, filename), 'w', encoding='utf-8') as f_out:
            json.dump(data, f_out, ensure_ascii=False, indent=2)

def main():
    # Bước 1: Load dữ liệu
    all_entities_by_type = load_entities(INPUT_FOLDER)
    
    full_mapping = {}
    
    # Bước 2: Tạo Mapping cho từng loại thực thể
    print("🔄 Đang tính toán hợp nhất thực thể (Fuzzy + Embedding)...")
    for e_type, names in all_entities_by_type.items():
        print(f"   -> Đang xử lý loại: {e_type} ({len(names)} thực thể)")
        full_mapping[e_type] = resolve_entities(names)
    
    # Ghi log mapping ra file để bạn kiểm tra
    with open(MAPPING_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(full_mapping, f, ensure_ascii=False, indent=2)
    print(f"✅ Đã tạo file nhật ký: {MAPPING_LOG_FILE} (Hãy mở xem thử các từ được gộp!)")

    # Bước 3: Áp dụng vào file JSON
    apply_mapping_and_save(INPUT_FOLDER, OUTPUT_FOLDER, full_mapping)
    print(f"🎉 Hoàn tất! Dữ liệu đã chuẩn hóa nằm tại: {OUTPUT_FOLDER}")

if __name__ == "__main__":
    main()