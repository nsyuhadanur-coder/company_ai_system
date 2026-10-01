import os
import re
import math
from typing import List, Dict, Any, Optional

class PolicyChunk:
    def __init__(
        self,
        chunk_id: str,
        doc_id: str,
        doc_title: str,
        category: str,
        section_title: str,
        content: str,
        source_filename: str
    ):
        self.chunk_id = chunk_id
        self.doc_id = doc_id
        self.doc_title = doc_title
        self.category = category
        self.section_title = section_title
        self.content = content.strip()
        self.source_filename = source_filename
        self.tokens = self._tokenize(f"{doc_title} {section_title} {content}")

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        # Lowercase, clean punctuation, tokenize
        cleaned = re.sub(r"[^\w\s-]", " ", text.lower())
        words = re.findall(r"\b[a-z0-9_-]{2,}\b", cleaned)
        stopwords = {
            "the", "and", "is", "in", "to", "of", "for", "with", "a", "an", "as",
            "at", "by", "from", "on", "or", "that", "this", "it", "be", "are",
            "was", "were", "will", "would", "can", "could", "should", "all",
            "any", "each", "our", "your", "their", "such", "has", "have", "had"
        }
        return [w for w in words if w not in stopwords]


class RAGEngine:
    def __init__(self, policies_dir: str, uploads_dir: str):
        self.policies_dir = policies_dir
        self.uploads_dir = uploads_dir
        os.makedirs(self.policies_dir, exist_ok=True)
        os.makedirs(self.uploads_dir, exist_ok=True)

        self.chunks: List[PolicyChunk] = []
        self.documents: Dict[str, Dict[str, Any]] = {}
        self.vocab_idf: Dict[str, float] = {}
        self.avg_doc_len: float = 0.0

        # Build initial index
        self.rebuild_index()

    def rebuild_index(self):
        """Scans policies and uploads directories and indexes all documents."""
        self.chunks = []
        self.documents = {}

        # 1. Load policies
        if os.path.exists(self.policies_dir):
            for fname in sorted(os.listdir(self.policies_dir)):
                fpath = os.path.join(self.policies_dir, fname)
                if os.path.isfile(fpath) and fname.endswith((".md", ".txt")):
                    self._parse_and_add_text_doc(fpath, fname, is_upload=False)

        # 2. Load uploaded documents
        if os.path.exists(self.uploads_dir):
            for fname in sorted(os.listdir(self.uploads_dir)):
                fpath = os.path.join(self.uploads_dir, fname)
                if os.path.isfile(fpath):
                    self._parse_and_add_file(fpath, fname, is_upload=True)

        # 3. Compute BM25 parameters
        self._compute_bm25_params()

    def _compute_bm25_params(self):
        """Calculates IDF and average length for BM25 search scoring."""
        n_chunks = len(self.chunks)
        if n_chunks == 0:
            self.avg_doc_len = 0.0
            self.vocab_idf = {}
            return

        total_len = sum(len(c.tokens) for c in self.chunks)
        self.avg_doc_len = total_len / n_chunks

        # Calculate document frequency for each word
        df: Dict[str, int] = {}
        for chunk in self.chunks:
            unique_words = set(chunk.tokens)
            for w in unique_words:
                df[w] = df.get(w, 0) + 1

        self.vocab_idf = {}
        for w, count in df.items():
            # Standard BM25 IDF formulation with smoothing
            self.vocab_idf[w] = math.log((n_chunks - count + 0.5) / (count + 0.5) + 1.0)

    def _parse_and_add_file(self, fpath: str, fname: str, is_upload: bool = True):
        ext = os.path.splitext(fname)[1].lower()
        if ext in [".md", ".txt"]:
            self._parse_and_add_text_doc(fpath, fname, is_upload=is_upload)
        elif ext == ".docx":
            self._parse_and_add_docx(fpath, fname, is_upload=is_upload)
        elif ext == ".pdf":
            self._parse_and_add_pdf(fpath, fname, is_upload=is_upload)

    def _parse_and_add_text_doc(self, fpath: str, fname: str, is_upload: bool = False):
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {fpath}: {e}")
            return

        doc_id = os.path.splitext(fname)[0]
        # Extract title and category from metadata headers if present
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        doc_title = title_match.group(1).strip() if title_match else fname.replace("_", " ").replace("-", " ")
        
        cat_match = re.search(r"\*\*Category:\*\*\s*(.+)$", content, re.MULTILINE)
        category = cat_match.group(1).strip() if cat_match else ("Uploaded Policies" if is_upload else "General Operations")

        self.documents[doc_id] = {
            "id": doc_id,
            "title": doc_title,
            "category": category,
            "filename": fname,
            "is_upload": is_upload,
            "raw_content": content,
            "file_size": os.path.getsize(fpath),
            "updated_at": os.path.getmtime(fpath)
        }

        # Chunk content by markdown headers (## or ###)
        sections = re.split(r"(?m)^(?=##\s+)", content)
        for idx, sec in enumerate(sections):
            if not sec.strip():
                continue
            lines = sec.strip().split("\n")
            first_line = lines[0].strip()
            if first_line.startswith("##"):
                sec_title = first_line.lstrip("#").strip()
            else:
                sec_title = "Overview & Introduction"

            chunk_id = f"{doc_id}_chunk_{idx}"
            chunk = PolicyChunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                doc_title=doc_title,
                category=category,
                section_title=sec_title,
                content=sec.strip(),
                source_filename=fname
            )
            self.chunks.append(chunk)

    def _parse_and_add_docx(self, fpath: str, fname: str, is_upload: bool = True):
        try:
            import docx
            doc = docx.Document(fpath)
            full_text = []
            for p in doc.paragraphs:
                if p.text.strip():
                    full_text.append(p.text.strip())
            content = "\n\n".join(full_text)
        except Exception as e:
            print(f"Error parsing DOCX {fpath}: {e}")
            return

        doc_id = os.path.splitext(fname)[0]
        doc_title = fname.replace(".docx", "").replace("_", " ")
        category = "Uploaded Operations Document"

        self.documents[doc_id] = {
            "id": doc_id,
            "title": doc_title,
            "category": category,
            "filename": fname,
            "is_upload": is_upload,
            "raw_content": content,
            "file_size": os.path.getsize(fpath),
            "updated_at": os.path.getmtime(fpath)
        }

        # Split into paragraph chunks of ~300 words
        words = content.split()
        chunk_size = 250
        for i in range(0, len(words), chunk_size):
            sec_words = words[i:i + chunk_size]
            sec_content = " ".join(sec_words)
            chunk_id = f"{doc_id}_chunk_{i // chunk_size}"
            chunk = PolicyChunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                doc_title=doc_title,
                category=category,
                section_title=f"Section {i // chunk_size + 1}",
                content=sec_content,
                source_filename=fname
            )
            self.chunks.append(chunk)

    def _parse_and_add_pdf(self, fpath: str, fname: str, is_upload: bool = True):
        try:
            from pypdf import PdfReader
            reader = PdfReader(fpath)
            pages_text = []
            for page_idx, page in enumerate(reader.pages):
                text = page.extract_text()
                if text and text.strip():
                    pages_text.append(f"--- Page {page_idx + 1} ---\n" + text.strip())
            content = "\n\n".join(pages_text)
        except Exception as e:
            print(f"Error parsing PDF {fpath}: {e}")
            return

        doc_id = os.path.splitext(fname)[0]
        doc_title = fname.replace(".pdf", "").replace("_", " ")
        category = "Uploaded PDF Handbook"

        self.documents[doc_id] = {
            "id": doc_id,
            "title": doc_title,
            "category": category,
            "filename": fname,
            "is_upload": is_upload,
            "raw_content": content,
            "file_size": os.path.getsize(fpath),
            "updated_at": os.path.getmtime(fpath)
        }

        # Chunk per page or 300 words
        for idx, page_str in enumerate(pages_text):
            chunk_id = f"{doc_id}_chunk_{idx}"
            chunk = PolicyChunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                doc_title=doc_title,
                category=category,
                section_title=f"Page {idx + 1}",
                content=page_str,
                source_filename=fname
            )
            self.chunks.append(chunk)

    def retrieve(self, query: str, top_k: int = 4) -> List[Dict[str, Any]]:
        """Retrieves top-k relevant policy chunks using BM25 ranking + title boosting."""
        query_tokens = PolicyChunk._tokenize(query)
        if not query_tokens or not self.chunks:
            return []

        k1 = 1.5
        b = 0.75
        scores = []

        query_text_lower = query.lower()

        for chunk in self.chunks:
            score = 0.0
            doc_len = len(chunk.tokens)
            chunk_word_counts = {}
            for t in chunk.tokens:
                chunk_word_counts[t] = chunk_word_counts.get(t, 0) + 1

            for qt in query_tokens:
                if qt in chunk_word_counts:
                    freq = chunk_word_counts[qt]
                    idf = self.vocab_idf.get(qt, 0.5)
                    # BM25 term weight
                    numerator = freq * (k1 + 1)
                    denominator = freq + k1 * (1 - b + b * (doc_len / (self.avg_doc_len or 1.0)))
                    score += idf * (numerator / denominator)

            # Boost matches in section title or doc title
            if any(qt in chunk.section_title.lower() for qt in query_tokens):
                score += 2.5
            if any(qt in chunk.doc_title.lower() for qt in query_tokens):
                score += 1.8

            # Extra boost for exact phrase overlap
            if len(query_tokens) >= 2:
                # check if consecutive words appear in chunk content
                for i in range(len(query_tokens) - 1):
                    bigram = f"{query_tokens[i]} {query_tokens[i+1]}"
                    if bigram in chunk.content.lower():
                        score += 3.0

            if score > 0:
                scores.append((score, chunk))

        scores.sort(key=lambda x: x[0], reverse=True)
        top_results = scores[:top_k]

        results = []
        for score, chunk in top_results:
            # Highlight snippet
            content_snippet = chunk.content[:400] + ("..." if len(chunk.content) > 400 else "")
            results.append({
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "doc_title": chunk.doc_title,
                "category": chunk.category,
                "section_title": chunk.section_title,
                "content": chunk.content,
                "snippet": content_snippet,
                "source_filename": chunk.source_filename,
                "relevance_score": round(score, 3)
            })

        return results

    def add_uploaded_file(self, fpath: str, original_filename: str) -> Dict[str, Any]:
        """Processes an uploaded file, chunks it, and updates index."""
        self._parse_and_add_file(fpath, original_filename, is_upload=True)
        self._compute_bm25_params()
        doc_id = os.path.splitext(original_filename)[0]
        return self.documents.get(doc_id, {})

    def delete_document(self, doc_id: str) -> bool:
        """Deletes an uploaded document and removes it from the index."""
        if doc_id in self.documents:
            doc = self.documents[doc_id]
            if doc.get("is_upload"):
                fpath = os.path.join(self.uploads_dir, doc["filename"])
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
                self.rebuild_index()
                return True
        return False

    def list_documents(self) -> List[Dict[str, Any]]:
        """Returns metadata list of all indexed documents."""
        docs = []
        for doc_id, doc in self.documents.items():
            # Count chunks for this doc
            c_count = sum(1 for c in self.chunks if c.doc_id == doc_id)
            docs.append({
                "id": doc["id"],
                "title": doc["title"],
                "category": doc["category"],
                "filename": doc["filename"],
                "is_upload": doc["is_upload"],
                "chunk_count": c_count,
                "file_size": doc["file_size"],
                "updated_at": doc["updated_at"]
            })
        return docs

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        return self.documents.get(doc_id)
