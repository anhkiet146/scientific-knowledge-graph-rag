import os
import requests
import json
import re
import time
from bs4 import BeautifulSoup
import fitz  # PyMuPDF


# --- CẤU HÌNH ---
INPUT_FOLDER = r'E:\LLM\pdf'
OUTPUT_FOLDER = r'E:\LLM\data\json'
GROBID_URL = "http://localhost:8070/api/processFulltextDocument"

SECTION_KEYWORDS = {
    "introduction": ["introduction", "background", "literature", "overview"],
    "methodology": ["method", "material", "approach", "proposed", "experimental"],
    "results": ["result", "discussion", "evaluation", "finding"],
    "conclusion": ["conclusion", "summary", "future work"]
}

def clean_text(text):
    if not text: return ""
    text = re.sub(r'\[\d+(?:[,-]\s*\d+)*\]', '', text)
    text = re.sub(r'\([A-Za-z\s\.,&]+,?\s*\d{4}.*?\)', '', text)
    text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def process_pdf_to_json(pdf_path):
    filename = os.path.basename(pdf_path)

    # 1. LẤY TEXT THÔ TRANG 1 BẰNG PyMuPDF (Để Gemini tự đọc Tác giả)
    raw_header = ""
    try:
        doc = fitz.open(pdf_path)
        raw_header = doc[0].get_text("text")[:2000] 
        doc.close()
    except Exception as e:
        print(f"Lỗi đọc PDF bằng fitz: {e}")

    # 2. LẤY CẤU TRÚC TỪ GROBID
    try:
        with open(pdf_path, 'rb') as f:
            response = requests.post(GROBID_URL, files={'input': f}, timeout=300)
        if response.status_code != 200: return None
        xml_content = response.text
    except Exception as e:
        print(f"Lỗi kết nối GROBID: {e}")
        return None

    soup = BeautifulSoup(xml_content, 'xml')

    paper_data = {
        "filename": filename,
        "title": "",
        "raw_header": clean_text(raw_header), # <--- TRUYỀN THẲNG TEXT THÔ VÀO ĐÂY
        "abstract": "",
        "sections": []
    }

    title_tag = soup.find('title', type='main')
    if title_tag: paper_data["title"] = clean_text(title_tag.get_text(strip=True))

    abstract_tag = soup.find('abstract')
    if abstract_tag: paper_data["abstract"] = clean_text(abstract_tag.get_text(strip=True))

    body = soup.find('body')
    if body:
        current_category = "uncategorized"
        for div in body.find_all('div'):
            head = div.find('head')
            if not head: continue
            
            title = head.get_text(strip=True)
            title_lower = title.lower()
            
            for cat, keywords in SECTION_KEYWORDS.items():
                if any(k in title_lower for k in keywords):
                    current_category = cat
                    break

            paragraphs = div.find_all('p')
            content = " ".join(p.get_text(strip=True) for p in paragraphs)
            content = clean_text(content)

            if len(content) > 30:
                paper_data["sections"].append({
                    "section_title": title,
                    "category": current_category,
                    "content": content
                })

    return paper_data

def main():
    if not os.path.exists(OUTPUT_FOLDER): os.makedirs(OUTPUT_FOLDER)
    files = [f for f in os.listdir(INPUT_FOLDER) if f.endswith(".pdf")]
    print(f"🚀 Bắt đầu xử lý {len(files)} bài báo (Chế độ tối giản, AI lo Tác giả)...")

    for i, file in enumerate(files):
        pdf_path = os.path.join(INPUT_FOLDER, file)
        result = process_pdf_to_json(pdf_path)
        if result:
            out_file = os.path.join(OUTPUT_FOLDER, file.replace(".pdf", ".json"))
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=4)
            print(f"✅ [{i+1}/{len(files)}] {file}")
        time.sleep(0.1)

if __name__ == "__main__":
    main()