from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import fitz
import uuid
import os
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer, CrossEncoder
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    Filter,
    MatchValue,
    FilterSelector,
    PointStruct,
    FieldCondition
)
from qdrant_client.http.exceptions import UnexpectedResponse
from google.generativeai import configure, GenerativeModel
import time

# === Setup ===
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
load_dotenv()
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise RuntimeError("GEMINI_API_KEY not set in environment.")

configure(api_key=gemini_api_key)
model = GenerativeModel("gemini-1.5-flash")

# Load models globally to avoid reloading on each request
# This line loads the SentenceTransformer model on startup, which is memory-intensive
try:
    embedder = SentenceTransformer("all-MiniLM-L12-v2", device='cpu')
    reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    vector_dim = embedder.get_sentence_embedding_dimension() or 384
    print(f"SentenceTransformer embedder and CrossEncoder reranker loaded. Vector dimension: {vector_dim}")
except Exception as e:
    raise RuntimeError(f"Failed to load sentence-transformer models: {e}")

collection_name = "medical_docs"

# --- Qdrant Client updated to use environment variables and increased timeout ---
qdrant_url = os.getenv("QDRANT_URL")
if not qdrant_url:
    raise RuntimeError("QDRANT_URL environment variable not set. Please set it to your Qdrant instance URL (e.g., your Qdrant Cloud URL).")

qdrant_api_key = os.getenv("QDRANT_API_KEY") # Optional, depending on your Qdrant setup

qdrant = QdrantClient(
    url=qdrant_url,
    api_key=qdrant_api_key,
    timeout=60.0 # Increased timeout for potentially long operations like initial indexing
)

# Print client version for debugging
try:
    import qdrant_client
    print(f"Qdrant client version: {qdrant_client.__version__}")
except AttributeError:
    print("Qdrant client version: Unable to determine version")
print(f"Connecting to Qdrant at: {qdrant_url}")

try:
    # Attempt to get the collection to see if it exists
    qdrant.get_collection(collection_name=collection_name)
    print(f"Qdrant collection '{collection_name}' already exists.")
except UnexpectedResponse as e:
    # If it doesn't exist (e.g., 404 Not Found), recreate it
    if e.status_code == 404:
        print(f"Qdrant collection '{collection_name}' not found, attempting to recreate.")
        try:
            qdrant.recreate_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE)
            )
            print(f"Qdrant collection '{collection_name}' recreated successfully.")
        except Exception as recreate_e:
            raise RuntimeError(f"Error recreating Qdrant collection: {recreate_e}")
    else:
        raise RuntimeError(f"Error checking Qdrant collection (UnexpectedResponse): {e}")
except Exception as e:
    # Catch any other unexpected errors during collection check/recreation
    raise RuntimeError(f"Error checking/creating Qdrant collection: {e}")

# --- Create payload index for 'source' field ---
# This ensures that filtering by 'source' is efficient and doesn't throw errors
try:
    # Ensure index creation is idempotent
    # Qdrant's create_payload_index raises 409 Conflict if index already exists, which is fine.
    # We can handle this by checking for the error message.
    qdrant.create_payload_index(
        collection_name=collection_name,
        field_name="source",
        field_schema="keyword"
    )
    print(f"Payload index for 'source' field created or already exists in collection '{collection_name}'.")
except UnexpectedResponse as e:
    # Check if the error is due to the index already existing (status code 409 Conflict)
    if e.status_code == 409 or "already exists" in str(e):
        print(f"Payload index for 'source' field already exists in collection '{collection_name}'.")
    else:
        print(f"Warning: Could not create payload index for 'source' field (UnexpectedResponse): {e}")
except Exception as e:
    print(f"Warning: Could not create payload index for 'source' field: {e}")


def rerank_chunks(question: str, chunks: list[str], top_k=3) -> list[str]:
    """Reranks retrieved chunks based on relevance to the question."""
    if not chunks:
        return []

    # Ensure chunks are unique before reranking if needed, though not strictly necessary for this model
    unique_chunks = list(set(chunks))

    pairs = [(question, chunk) for chunk in unique_chunks]
    
    if not pairs: # Handle case where unique_chunks might be empty after set conversion
        return []

    scores = reranker.predict(pairs)

    # Sort chunks based on scores descending
    ranked = sorted(zip(unique_chunks, scores), key=lambda x: x[1], reverse=True)
    top_chunks = [chunk for chunk, _ in ranked[:top_k]]

    print(f"Reranked {len(chunks)} chunks to top {len(top_chunks)}. Top scores: {[round(s, 3) for _, s in ranked[:top_k]]}")
    return top_chunks

# === Upload Report Endpoint ===
@app.post("/upload")
async def upload_report(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse(status_code=400, content={"detail": "🚫 Only PDF files are allowed."})

    try:
        # Read file content
        file_content = await file.read()
        doc = fitz.open(stream=file_content, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        if not text.strip():
            return JSONResponse(status_code=400, content={"detail": "🚫 PDF contains no readable text."})
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": f"❌ Error reading PDF: {e}"})

    # Simple chunking for demonstration (you might use a more advanced strategy)
    chunks = [text[i:i+500] for i in range(0, len(text), 500)]
    if not chunks:
        return JSONResponse(status_code=400, content={"detail": "🚫 No text chunks could be extracted from the PDF."})

    try:
        vectors = embedder.encode(chunks).tolist()
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"❌ Error encoding text chunks: {e}"})

    # Clear old pdf data specific to 'report' source
    try:
        delete_result = qdrant.delete(
            collection_name=collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="source", match=MatchValue(value="report"))]
                )
            ),
            wait=True # Wait for the delete operation to complete
        )
        if delete_result.status == 'completed':
            print("Old pdf data with source 'report' cleared from Qdrant.")
        else:
            print(f"Qdrant delete status not completed: {delete_result.status}. Points deleted: {delete_result.result.points}")

    except UnexpectedResponse as e:
        print(f"Warning: No old report data to clear or unexpected response during delete: {e}")
    except Exception as e:
        print(f"Error clearing old report data: {e}")
        # Pass silently, we don't want upload to fail just because old data couldn't be cleared

    report_points = []
    for i, (v, c) in enumerate(zip(vectors, chunks)):
        # Ensure unique IDs even if chunks are identical
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, file.filename + str(i) + c[:50])) # Unique ID based on filename, chunk index, and partial content
        report_points.append(
            PointStruct(id=point_id, vector=v, payload={"text": c, "source": "report", "filename": file.filename})
        )

    try:
        # Batch upsert points
        upsert_result = qdrant.upsert(collection_name=collection_name, points=report_points, wait=True)
        if upsert_result.status == 'completed':
            print(f"Successfully indexed {len(report_points)} chunks.")
            return JSONResponse(status_code=200, content={"detail": "✅ Report uploaded and indexed successfully!"})
        else:
            raise Exception(f"Qdrant upsert status not completed: {upsert_result.status}")

    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"❌ Failed to index report: {e}"})


# === Ask Question Endpoint ===
class QuestionRequest(BaseModel):
    question: str

@app.post("/ask")
async def ask_question(data: QuestionRequest):
    if not data.question.strip():
        return JSONResponse(status_code=400, content={"detail": "🚫 Please provide a question."})

    try:
        q_vec = embedder.encode(data.question).tolist()
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"❌ Error encoding question: {e}"})

    report_context = ""
    try:
        # Query for relevant chunks from the 'report' source
        report_results = qdrant.query_points(
            collection_name=collection_name,
            query=q_vec,
            limit=10, # Retrieve more chunks for reranking
            with_payload=True,
            query_filter=Filter(
                must=[FieldCondition(key="source", match=MatchValue(value="report"))]
            )
        )
        
        retrieved_chunks = [p.payload["text"] for p in report_results.points if p.payload and "text" in p.payload]
        
        if retrieved_chunks:
            # Rerank and select the top 3 most relevant chunks
            top_relevant_chunks = rerank_chunks(data.question, retrieved_chunks, top_k=3)
            report_context = "\n".join(top_relevant_chunks)
            print(f"Generated report context with {len(top_relevant_chunks)} chunks.")
        else:
            report_context = "No highly relevant information found in patient report."
            print("No relevant chunks found in Qdrant for 'report' source.")

    except Exception as e:
        print(f"Error querying report context from Qdrant: {e}")
        report_context = "An error occurred while retrieving relevant information from the report. Providing general information."

    # --- Prompt for Gemini ---
    prompt = f"""You are a helpful and empathetic AI assistant specialized in providing health information based on medical reports and general medical knowledge.

User's Question: "{data.question}"

--- Medical Report Context ---
{report_context}
--- End of Medical Report Context ---

Based on the provided medical report context (if available and relevant) and your general medical knowledge, please answer the user's question clearly, concisely, and empathetically.

If the report context is 'No highly relevant information found in patient report.', indicate that the answer is based on general medical knowledge.
Always remind the user that this information is for educational purposes only and should not replace professional medical advice. Encourage them to consult a qualified healthcare provider for diagnosis and treatment.
"""
    try:
        response = model.generate_content(prompt)
        # Check if response has text content
        if response and response.text:
            return JSONResponse(status_code=200, content={"answer": response.text})
        else:
            return JSONResponse(status_code=500, content={"detail": "❌ Gemini did not return a valid answer. Please try again."})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"❌ Gemini error: {e}"})