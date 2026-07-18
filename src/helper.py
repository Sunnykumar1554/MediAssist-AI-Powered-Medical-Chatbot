from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List
from langchain.schema import Document
import csv
import os
import requests


# Lightweight embedding wrapper using HuggingFace Inference API
# Falls back to local model if API is unreachable
class _HuggingFaceAPIEmbeddings:
    API_URL = "https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self):
        self._token = os.environ.get("HF_API_TOKEN", "")
        self._headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def embed_documents(self, texts: List[str]) -> List[list[float]]:
        response = requests.post(self.API_URL, headers=self._headers, json={"inputs": texts, "options": {"wait_for_model": True}})
        response.raise_for_status()
        return response.json()

    def embed_query(self, text: str) -> list[float]:
        response = requests.post(self.API_URL, headers=self._headers, json={"inputs": text, "options": {"wait_for_model": True}})
        response.raise_for_status()
        return response.json()



#Extract Data From the PDF File
def load_pdf_file(data):
    loader= DirectoryLoader(data,
                            glob="*.pdf",
                            loader_cls=PyPDFLoader)

    documents=loader.load()

    return documents



def filter_to_minimal_docs(docs: List[Document]) -> List[Document]:
    """
    Given a list of Document objects, return a new list of Document objects
    containing only 'source' in metadata and the original page_content.
    """
    minimal_docs: List[Document] = []
    for doc in docs:
        src = doc.metadata.get("source")
        minimal_docs.append(
            Document(
                page_content=doc.page_content,
                metadata={"source": src}
            )
        )
    return minimal_docs



#Split the Data into Text Chunks
def text_split(extracted_data):
    text_splitter=RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=20)
    text_chunks=text_splitter.split_documents(extracted_data)
    return text_chunks



def download_hugging_face_embeddings():
    """Return an embedding object compatible with LangChain.

    Strategy: Use local model if sentence-transformers is installed (local dev).
    Otherwise, fall back to HuggingFace Inference API (Render deployment).
    """
    try:
        # Check if sentence-transformers is installed
        import sentence_transformers
        from langchain_community.embeddings import HuggingFaceEmbeddings
        print("[Embeddings] sentence-transformers package detected. Using local model.")
        return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    except ImportError:
        print("[Embeddings] sentence-transformers package not found. Using HuggingFace Inference API.")
        return _HuggingFaceAPIEmbeddings()


def load_csv_file(csv_path: str, deduplicate: bool = True) -> List[Document]:
    """Load medical Q&A data from the CSV file.

    Each row becomes a LangChain Document with structured content combining
    the question description, patient query, and doctor response.

    Parameters
    ----------
    csv_path : str
        Path to the CSV file.
    deduplicate : bool
        If True, drop duplicate rows based on the 'Description' column.

    Returns
    -------
    List[Document]
        List of LangChain Document objects ready for embedding.
    """
    documents: List[Document] = []
    seen_descriptions: set = set()

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            description = (row.get("Description") or "").strip()
            patient = (row.get("Patient") or "").strip()
            doctor = (row.get("Doctor") or "").strip()

            # Skip empty rows
            if not description and not patient and not doctor:
                continue

            # Deduplicate based on Description
            if deduplicate:
                if description in seen_descriptions:
                    continue
                seen_descriptions.add(description)

            # Build structured content for better retrieval
            page_content = (
                f"Question: {description}\n"
                f"Patient: {patient}\n"
                f"Doctor: {doctor}"
            )

            documents.append(
                Document(
                    page_content=page_content,
                    metadata={
                        "source": os.path.basename(csv_path),
                        "type": "qa",
                    },
                )
            )

    return documents
