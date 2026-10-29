"""
Core DocuBot class responsible for:
- Loading documents from the docs/ folder
- Building a simple retrieval index (Phase 1)
- Retrieving relevant snippets (Phase 1)
- Supporting retrieval only answers
- Supporting RAG answers when paired with Gemini (Phase 2)
"""

import os
import glob
import string

# Common filler words that match almost any text, so they don't count as evidence
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "be", "do", "does", "did",
    "i", "my", "me", "you", "it", "in", "on", "of", "to", "for", "and",
    "or", "with", "by", "at", "from", "what", "which", "where", "when",
    "how", "who", "why", "there", "any", "these", "this", "that",
    "mention", "docs",
}

# A chunk must share at least this many non-stopword words with the query
MIN_KEYWORD_MATCHES = 1

class DocuBot:
    def __init__(self, docs_folder="docs", llm_client=None):
        """
        docs_folder: directory containing project documentation files
        llm_client: optional Gemini client for LLM based answers
        """
        self.docs_folder = docs_folder
        self.llm_client = llm_client

        # Load documents into memory
        self.documents = self.load_documents()  # List of (filename, text)

        # Split documents into smaller sections for retrieval
        self.chunks = self.chunk_documents(self.documents)  # List of (filename, chunk_text)

        # Build a retrieval index (implemented in Phase 1)
        self.index = self.build_index(self.documents)

    # -----------------------------------------------------------
    # Document Loading
    # -----------------------------------------------------------

    def load_documents(self):
        """
        Loads all .md and .txt files inside docs_folder.
        Returns a list of tuples: (filename, text)
        """
        docs = []
        pattern = os.path.join(self.docs_folder, "*.*")
        for path in glob.glob(pattern):
            if path.endswith(".md") or path.endswith(".txt"):
                with open(path, "r", encoding="utf8") as f:
                    text = f.read()
                filename = os.path.basename(path)
                docs.append((filename, text))
        return docs

    def chunk_documents(self, documents):
        """
        Splits each document into sections, starting a new chunk at every
        markdown heading (a line beginning with '#').
        Returns a list of tuples: (filename, chunk_text)
        """
        chunks = []
        for filename, text in documents:
            current = []
            for line in text.splitlines():
                if line.startswith("#") and current:
                    chunks.append((filename, "\n".join(current).strip()))
                    current = []
                current.append(line)
            if current:
                chunks.append((filename, "\n".join(current).strip()))
        return chunks

    # -----------------------------------------------------------
    # Index Construction (Phase 1)
    # -----------------------------------------------------------

    def build_index(self, documents):
        """
        TODO (Phase 1):
        Build a tiny inverted index mapping lowercase words to the documents
        they appear in.

        Example structure:
        {
            "token": ["AUTH.md", "API_REFERENCE.md"],
            "database": ["DATABASE.md"]
        }

        Keep this simple: split on whitespace, lowercase tokens,
        ignore punctuation if needed.
        """
        index = {}
        for filename, text in documents:
            for word in text.lower().split():
                word = word.strip(string.punctuation)
                if not word:
                    continue
                if word not in index:
                    index[word] = []
                if filename not in index[word]:
                    index[word].append(filename)
        return index

    # -----------------------------------------------------------
    # Scoring and Retrieval (Phase 1)
    # -----------------------------------------------------------

    def score_document(self, query, text):
        """
        TODO (Phase 1):
        Return a simple relevance score for how well the text matches the query.

        Suggested baseline:
        - Convert query into lowercase words
        - Count how many appear in the text
        - Return the count as the score
        """
        text_words = set(w.strip(string.punctuation) for w in text.lower().split())
        score = 0
        for word in query.lower().split():
            word = word.strip(string.punctuation)
            if word and word in text_words:
                score += 1
        return score

    def keyword_matches(self, query, text):
        """
        Guardrail helper: counts query words that appear in the text,
        ignoring STOPWORDS, so filler words can't count as evidence.
        """
        text_words = set(w.strip(string.punctuation) for w in text.lower().split())
        count = 0
        for word in query.lower().split():
            word = word.strip(string.punctuation)
            if word and word not in STOPWORDS and word in text_words:
                count += 1
        return count

    def retrieve(self, query, top_k=3):
        """
        TODO (Phase 1):
        Use the index and scoring function to select top_k relevant document snippets.

        Return a list of (filename, text) sorted by score descending.
        """
        # Use the index to find candidate documents containing any query word
        candidates = set()
        for word in query.lower().split():
            word = word.strip(string.punctuation)
            candidates.update(self.index.get(word, []))

        results = []
        for filename, text in self.chunks:
            if filename in candidates:
                # Guardrail: skip chunks with no meaningful evidence
                if self.keyword_matches(query, text) < MIN_KEYWORD_MATCHES:
                    continue
                score = self.score_document(query, text)
                if score > 0:
                    results.append((score, filename, text))

        results.sort(key=lambda r: r[0], reverse=True)
        results = [(filename, text) for _, filename, text in results]
        return results[:top_k]

    # -----------------------------------------------------------
    # Answering Modes
    # -----------------------------------------------------------

    def answer_retrieval_only(self, query, top_k=3):
        """
        Phase 1 retrieval only mode.
        Returns raw snippets and filenames with no LLM involved.
        """
        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I don't know based on these docs."

        formatted = []
        for filename, text in snippets:
            formatted.append(f"[{filename}]\n{text}\n")

        return "\n---\n".join(formatted)

    def answer_rag(self, query, top_k=3):
        """
        Phase 2 RAG mode.
        Uses student retrieval to select snippets, then asks Gemini
        to generate an answer using only those snippets.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I don't know based on these docs."

        return self.llm_client.answer_from_snippets(query, snippets)

    # -----------------------------------------------------------
    # Bonus Helper: concatenated docs for naive generation mode
    # -----------------------------------------------------------

    def full_corpus_text(self):
        """
        Returns all documents concatenated into a single string.
        This is used in Phase 0 for naive 'generation only' baselines.
        """
        return "\n\n".join(text for _, text in self.documents)
