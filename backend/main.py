from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
import fitz # PyMuPDF for PDF processing
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
    FieldCondition,
    CollectionStatus
)
from qdrant_client.http.exceptions import UnexpectedResponse
from google.generativeai import configure, GenerativeModel
import logging # For more structured logging

# --- Authentication Imports ---
# These imports are relative to the 'backend' directory.
# They assume you run your FastAPI app from the 'backend' directory (e.g., `uvicorn main:app --reload`)
from auth.routes import router as auth_router
from auth.oauth import get_current_active_user
from models import User # Assuming models.py defines a Pydantic User model (or SQLAlchemy model)

# === Setup ===
app = FastAPI(
    title="DocQuery",
    description="An AI assistant to answer questions based on uploaded pdf, with user authentication.",
    version="1.0.0"
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# CORS Middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # WARNING: In production, change "*" to your specific frontend URL(s)
    allow_credentials=True,
    allow_methods=["*"], # Or specify ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers=["*"]
)

# Load environment variables
load_dotenv()

# Session Middleware (if you're using sessions, otherwise can be removed if only JWT is for auth)
SESSION_SECRET_KEY = os.getenv("SECRET_KEY") 
if not SESSION_SECRET_KEY:
    logger.error("SECRET_KEY environment variable not set. SessionMiddleware requires it.")
    raise RuntimeError("SECRET_KEY environment variable not set. SessionMiddleware requires it.")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)

# Gemini API Key configuration
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    logger.error("GEMINI_API_KEY not set in environment.")
    raise RuntimeError("GEMINI_API_KEY not set in environment.")

configure(api_key=gemini_api_key)
model = GenerativeModel("gemini-1.5-flash")
logger.info("Google Generative AI model 'gemini-1.5-flash' configured.")

# Load models globally to avoid reloading on each request
# Using 'cpu' for broad compatibility. Consider 'cuda' if a GPU is available and configured.
try:
    embedder = SentenceTransformer("all-MiniLM-L12-v2", device='cpu') 
    reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    vector_dim = embedder.get_sentence_embedding_dimension() or 384
    logger.info(f"SentenceTransformer embedder and CrossEncoder reranker loaded. Vector dimension: {vector_dim}")
except Exception as e:
    logger.critical(f"Failed to load sentence-transformer models: {e}", exc_info=True)
    raise RuntimeError(f"Failed to load sentence-transformer models: {e}")

collection_name = "general_docs"

# --- Qdrant Client configuration ---
qdrant_url = os.getenv("QDRANT_URL")
if not qdrant_url:
    logger.critical("QDRANT_URL environment variable not set. Please set it to your Qdrant instance URL (e.g., your Qdrant Cloud URL).")
    raise RuntimeError("QDRANT_URL environment variable not set. Please set it to your Qdrant instance URL (e.g., your Qdrant Cloud URL).")

qdrant_api_key = os.getenv("QDRANT_API_KEY") # Optional, depending on your Qdrant setup

qdrant = QdrantClient(
    url=qdrant_url,
    api_key=qdrant_api_key,
    timeout=60.0 # Increased timeout for potentially long operations like initial indexing
)

# Print Qdrant client version for debugging
try:
    import qdrant_client
    logger.info(f"Qdrant client version: {qdrant_client.__version__}")
except AttributeError:
    logger.warning("Qdrant client version: Unable to determine version")
logger.info(f"Connecting to Qdrant at: {qdrant_url}")

# --- Qdrant Collection Initialization ---
try:
    # Attempt to get collection info to check existence and status
    collection_info = qdrant.get_collection(collection_name=collection_name)
    if collection_info.status == CollectionStatus.GREEN:
        logger.info(f"Qdrant collection '{collection_name}' already exists and is healthy.")
    else:
        logger.warning(f"Qdrant collection '{collection_name}' exists but its status is {collection_info.status}.")
except UnexpectedResponse as e:
    if e.status_code == 404:
        logger.info(f"Qdrant collection '{collection_name}' not found, attempting to recreate.")
        try:
            qdrant.recreate_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
                timeout=60.0 # Ensure recreation also has sufficient timeout
            )
            logger.info(f"Qdrant collection '{collection_name}' recreated successfully.")
        except Exception as recreate_e:
            logger.critical(f"Error recreating Qdrant collection: {recreate_e}", exc_info=True)
            raise RuntimeError(f"Error recreating Qdrant collection: {recreate_e}")
    else:
        logger.critical(f"Error checking Qdrant collection (UnexpectedResponse): {e}", exc_info=True)
        raise RuntimeError(f"Error checking Qdrant collection (UnexpectedResponse): {e}")
except Exception as e:
    logger.critical(f"Error checking/creating Qdrant collection: {e}", exc_info=True)
    raise RuntimeError(f"Error checking/creating Qdrant collection: {e}")

# --- Create payload index for 'source' and 'user_id' fields ---
# This ensures that filtering by these fields is efficient and doesn't throw errors
for field_name in ["source", "user_id"]:
    try:
        qdrant.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema="keyword" # For string values like "report" and user IDs
        )
        logger.info(f"Payload index for '{field_name}' field created or already exists in collection '{collection_name}'.")
    except UnexpectedResponse as e:
        # Check if the error is due to the index already existing (status code 409 Conflict)
        if e.status_code == 409 or "already exists" in str(e):
            logger.info(f"Payload index for '{field_name}' field already exists in collection '{collection_name}'.")
        else:
            logger.warning(f"Could not create payload index for '{field_name}' field (UnexpectedResponse): {e}", exc_info=True)
    except Exception as e:
        logger.warning(f"Could not create payload index for '{field_name}' field: {e}", exc_info=True)


def rerank_chunks(question: str, chunks: list[str], top_k=3) -> list[str]:
    """Reranks retrieved chunks based on relevance to the question."""
    if not chunks:
        return []

    # Using set to ensure uniqueness if the retrieval method can return duplicates
    unique_chunks = list(set(chunks))
    
    if not unique_chunks:
        return []

    pairs = [(question, chunk) for chunk in unique_chunks]
    
    try:
        scores = reranker.predict(pairs)
    except Exception as e:
        logger.error(f"Error during reranker prediction: {e}", exc_info=True)
        # Fallback: return original chunks if reranking fails
        return unique_chunks[:top_k] if len(unique_chunks) > top_k else unique_chunks

    # Sort chunks based on scores descending
    ranked = sorted(zip(unique_chunks, scores), key=lambda x: x[1], reverse=True)
    top_chunks = [chunk for chunk, _ in ranked[:top_k]]

    logger.info(f"Reranked {len(chunks)} chunks to top {len(top_chunks)}. Top scores: {[round(s, 3) for _, s in ranked[:top_k]]}")
    return top_chunks

# --- Include Authentication Router ---
# This line mounts your auth router under the /auth prefix
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])

# === Protected Routes ===

# Root path for testing authentication
@app.get("/", summary="Test authentication status", response_model=dict)
async def root(current_user: User = Depends(get_current_active_user)):
    """
    A simple endpoint to confirm that the user is authenticated.
    Returns a welcome message with the user's email.
    """
    logger.info(f"Authenticated user accessed root: {current_user.email}")
    return {"message": f"Welcome, {current_user.email}! Authentication successful."}


# === Upload Report Endpoint ===
@app.post("/upload", summary="Upload and index a PDF medical report", response_model=dict)
async def upload_report(file: UploadFile = File(..., description="The PDF medical report to upload."),
                        current_user: User = Depends(get_current_active_user)):
    """
    Uploads a PDF report, extracts its text, embeds chunks, and indexes them into Qdrant.
    Old reports for the same user will be cleared before indexing new ones.
    Requires authentication.
    """
    logger.info(f"User {current_user.email} attempting to upload report: {file.filename}")

    if not file.filename.lower().endswith(".pdf"):
        logger.warning(f"Upload failed for {current_user.email}: Invalid file type '{file.filename}'")
        raise HTTPException(status_code=400, detail="🚫 Only PDF files are allowed.")

    try:
        # Read file content
        file_content = await file.read()
        doc = fitz.open(stream=file_content, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        if not text.strip():
            logger.warning(f"Upload failed for {current_user.email} ({file.filename}): PDF contains no readable text.")
            raise HTTPException(status_code=400, detail="🚫 PDF contains no readable text.")
    except Exception as e:
        logger.error(f"Error reading PDF for user {current_user.email} ({file.filename}): {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"❌ Error reading PDF: {e}")

    # Simple chunking for demonstration (consider more advanced NLP-based chunking)
    chunks = [text[i:i+500] for i in range(0, len(text), 500)]
    if not chunks:
        logger.warning(f"Upload failed for {current_user.email} ({file.filename}): No text chunks extracted.")
        raise HTTPException(status_code=400, detail="🚫 No text chunks could be extracted from the PDF.")

    try:
        vectors = embedder.encode(chunks).tolist()
    except Exception as e:
        logger.error(f"Error encoding text chunks for user {current_user.email} ({file.filename}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"❌ Error encoding text chunks: {e}")

    # --- Clear old pdf data specific to 'report' source for this user ---
    # This is crucial for user-specific data management.
    try:
        delete_result = qdrant.delete(
            collection_name=collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(key="source", match=MatchValue(value="report")),
                        FieldCondition(key="user_id", match=MatchValue(value=str(current_user.id)))
                    ]
                )
            ),
            wait=True # Wait for the delete operation to complete
        )
        if delete_result.status == 'completed':
            logger.info(f"Old pdf data with source 'report' cleared for user {current_user.email} from Qdrant. Points deleted: {delete_result.result.points}")
        else:
            logger.warning(f"Qdrant delete status not completed for user {current_user.email}: {delete_result.status}. Points deleted: {delete_result.result.points}")

    except UnexpectedResponse as e:
        # 404 indicates no collection or points, which is fine for a delete
        if e.status_code == 404:
            logger.info(f"No old report data for user {current_user.email} to clear (404 response).")
        else:
            logger.warning(f"Unexpected response during Qdrant delete for user {current_user.email}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Error clearing old report data for user {current_user.email}: {e}", exc_info=True)
        # Continue with upload even if old data couldn't be cleared, but log the error.

    report_points = []
    for i, (v, c) in enumerate(zip(vectors, chunks)):
        # Ensure unique IDs across all users and uploads by including user.id and filename
        # Using uuid.uuid5 for consistent ID generation given the same inputs
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{current_user.id}-{file.filename}-{i}-{c[:100]}")) 
        report_points.append(
            PointStruct(id=point_id, vector=v, payload={"text": c, "source": "report", "filename": file.filename, "user_id": str(current_user.id)})
        )

    try:
        # Batch upsert points
        upsert_result = qdrant.upsert(collection_name=collection_name, points=report_points, wait=True)
        if upsert_result.status == 'completed':
            logger.info(f"Successfully indexed {len(report_points)} chunks for user {current_user.email} in Qdrant.")
            return JSONResponse(status_code=200, content={"detail": "✅ Report uploaded and indexed successfully!"})
        else:
            # If upsert is not completed, it indicates an issue on Qdrant side
            logger.error(f"Qdrant upsert status not completed for user {current_user.email}: {upsert_result.status}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"❌ Failed to index report: Qdrant upsert status: {upsert_result.status}")

    except Exception as e:
        logger.error(f"Failed to index report for user {current_user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, content={"detail": f"❌ Failed to index report: {e}"})


# === Ask Question Endpoint ===
class QuestionRequest(BaseModel):
    question: str

@app.post("/ask", summary="Ask a question about uploaded reports or general medical knowledge", response_model=dict)
async def ask_question(data: QuestionRequest, current_user: User = Depends(get_current_active_user)):
    """
    Asks a question and retrieves answers based on the authenticated user's indexed reports
    and general medical knowledge. Requires authentication.
    """
    logger.info(f"User {current_user.email} asked: '{data.question[:50]}...'")

    if not data.question.strip():
        logger.warning(f"Ask question failed for {current_user.email}: Empty question provided.")
        raise HTTPException(status_code=400, detail="🚫 Please provide a question.")

    try:
        q_vec = embedder.encode(data.question).tolist()
    except Exception as e:
        logger.error(f"Error encoding question for user {current_user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"❌ Error encoding question: {e}")

    report_context = ""
    try:
        # Query for relevant chunks from the 'report' source, filtered by user_id
        report_results = qdrant.query_points(
            collection_name=collection_name,
            query=q_vec,
            limit=10, # Retrieve more chunks for reranking to get diverse candidates
            with_payload=True,
            query_filter=Filter(
                must=[
                    FieldCondition(key="source", match=MatchValue(value="report")),
                    FieldCondition(key="user_id", match=MatchValue(value=str(current_user.id)))
                ]
            )
        )
        
        retrieved_chunks = [p.payload["text"] for p in report_results.points if p.payload and "text" in p.payload]
        
        if retrieved_chunks:
            top_relevant_chunks = rerank_chunks(data.question, retrieved_chunks, top_k=3)
            report_context = "\n".join(top_relevant_chunks)
            logger.info(f"Generated report context with {len(top_relevant_chunks)} chunks for user {current_user.email}.")
        else:
            report_context = "No highly relevant information found in your patient report."
            logger.info(f"No relevant chunks found in Qdrant for 'report' source for user {current_user.email}.")

    except Exception as e:
        logger.error(f"Error querying report context from Qdrant for user {current_user.email}: {e}", exc_info=True)
        report_context = "An error occurred while retrieving relevant information from your report. Providing general information."

    # --- Prompt for Gemini ---
    prompt = f"""
You are a helpful, knowledgeable, and empathetic AI health assistant designed to assist users in understanding their medical reports and answering general health-related questions.

--- User's Question ---
{data.question}
--- End of Question ---

--- Extracted Report Context ---
{report_context}
--- End of Report Context ---

Instructions:
1. Use the provided report context (if it contains relevant details) to answer the user's question as accurately and clearly as possible.
2. If the report context says "No highly relevant information found in your patient report.", rely on your general medical knowledge to answer the question instead.
3. Respond with clarity, empathy, and professionalism, making the explanation easy to understand for a non-medical user.
4. Include a polite disclaimer at the end of your response:

"**Disclaimer:** This information is for educational purposes only and is not a substitute for professional medical advice, diagnosis, or treatment. Please consult a licensed healthcare provider for personal medical concerns."

Return only the final response as if you are directly speaking to the user.
"""

    try:
        response = model.generate_content(prompt)
        if response and response.text:
            logger.info(f"Successfully generated response for user {current_user.email}.")
            return JSONResponse(status_code=200, content={"answer": response.text})
        else:
            logger.error(f"Gemini did not return a valid answer for user {current_user.email}.")
            raise HTTPException(status_code=500, detail="❌ Gemini did not return a valid answer. Please try again.")
    except Exception as e:
        logger.error(f"Gemini error for user {current_user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"❌ Gemini error: {e}")
