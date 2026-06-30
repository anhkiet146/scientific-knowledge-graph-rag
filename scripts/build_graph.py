import os
import json
from tqdm import tqdm
from neo4j import GraphDatabase


# --- CẤU HÌNH ---
INPUT_FOLDER = r'E:\LLM\data\final_graph'  # Thư mục chứa JSON đã chuẩn hóa
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

if not NEO4J_PASSWORD:
    raise ValueError("Please set NEO4J_PASSWORD before building the graph.")

class KnowledgeGraphBuilder:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def load_paper_data(self, data):
        # --- BẮT ĐẦU: LỚP PHÒNG THỦ CHỐNG LỖI ---
        if not isinstance(data, dict):
            return  # Bỏ qua nếu dữ liệu không phải từ điển
        
        with self.driver.session() as session:
            # 1. Tạo Nút Paper
            session.run("""
                MERGE (p:Paper {filename: $filename})
                SET p.title = $title, 
                    p.abstract = $abstract
            """, filename=data['filename'], title=data.get('paper_title', ''), abstract=data.get('abstract', ''))

            # Lấy danh sách thực thể và quan hệ an toàn
            result = data.get('extraction_result', {})
            if not isinstance(result, dict):
                result = {}

            entities = result.get('entities', [])
            if not isinstance(entities, list):
                entities = []

            relations = result.get('relations', [])
            if not isinstance(relations, list):
                relations = []
            # --- KẾT THÚC LỚP PHÒNG THỦ ---

            # 2. Tạo Nút Thực thể (Entities) & Link với Paper
            for ent in entities:
                if not isinstance(ent, dict): continue
                
                e_type = ent.get('type')
                e_id = ent.get('id')
                if not e_type or not e_id: continue
                
                e_desc = ent.get('description', '')

                # Cypher query động theo Label (Type)
                query_node = f"""
                    MERGE (e:`{e_type}` {{name: $name}})
                    ON CREATE SET e.description = $desc
                """
                try:
                    session.run(query_node, name=e_id, desc=e_desc)
                except Exception:
                    continue

                # Tạo quan hệ: (Paper)-[:MENTIONS]->(Entity)
                rel_type = {
                    "Author":      "AFFILIATED_WITH",
                    "Institution": "AFFILIATED_WITH",
                    "Method":      "USED_FOR",
                    "Dataset":     "EVALUATED_ON",
                    "Metric":      "ACHIEVED",
                    "Concept":     "BELONGS_TO",
                    "Domain":      "BELONGS_TO",
                }.get(e_type, "BELONGS_TO")
                
                query_link = f"""
                    MATCH (p:Paper {{filename: $filename}})
                    MATCH (e:`{e_type}` {{name: $name}})
                    MERGE (p)-[:{rel_type}]->(e)
                """
                try:
                    session.run(query_link, filename=data['filename'], name=e_id)
                except Exception:
                    continue

            # 3. Tạo Quan hệ giữa các Thực thể (Semantic Relations)
            for rel in relations:
                if not isinstance(rel, dict): continue
                
                src_id = rel.get('source')
                tgt_id = rel.get('target')
                rel_t = rel.get('type')
                
                if not src_id or not tgt_id or not rel_t: continue
                
                rel_type_clean = str(rel_t).upper().replace(" ", "_").replace("-", "_")
                
                query_rel = f"""
                    MATCH (a {{name: $src}})
                    MATCH (b {{name: $tgt}})
                    MERGE (a)-[:{rel_type_clean}]->(b)
                """
                try:
                    session.run(query_rel, src=src_id, tgt=tgt_id)
                except Exception as e:
                    pass

def main():
    builder = KnowledgeGraphBuilder(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    
    files = [f for f in os.listdir(INPUT_FOLDER) if f.endswith('.json')]
    print(f"🚀 Đang nạp {len(files)} bài báo vào Neo4j...")

    for filename in tqdm(files):
        file_path = os.path.join(INPUT_FOLDER, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if isinstance(data, dict):
                if 'filename' not in data: 
                    data['filename'] = filename
                builder.load_paper_data(data)
        except Exception as e:
            # File bị lỗi đọc JSON (mã hóa hoặc định dạng hỏng)
            pass

    builder.close()
    print("🎉 Hoàn tất! Hãy mở Neo4j Browser hoặc quay lại trang Web để kiểm tra.")

if __name__ == "__main__":
    main()
