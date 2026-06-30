# Results synchronized with manuscript

These files follow the values reported in `Scientific_KG_RAG_IJITCS (1).pdf`.

Corpus:
- 482 papers from the CTU Journal of Innovation and Sustainable Development, 2015-2025.
- Extraction evaluation: 40 randomly selected papers.
- QA evaluation: 45 questions.

Baseline comparison:
- Lexical BM25 RAG: Faithfulness 0.800, Answer Relevancy 0.811, Context Precision 0.789, Context Recall 0.620, Latency 27.963 s.
- Vector RAG: Faithfulness 0.803, Answer Relevancy 0.830, Context Precision 0.853, Context Recall 0.664, Latency 48.524 s.
- Proposed KG-RAG: Faithfulness 0.837, Answer Relevancy 0.866, Context Precision 0.868, Context Recall 0.865, Latency 24.516 s.
