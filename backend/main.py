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
from auth.routes import router as auth_router
from auth.oauth import get_current_active_user
from models import User 
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
    allow_origins=["https://docquery-rocs.onrender.com","https://docquerytest2.onrender.com"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Load environment variables
load_dotenv()

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
model = GenerativeModel("gemini-2.5-flash")
logger.info("Google Generative AI model 'gemini-2.5-flash' configured.")

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

qdrant_api_key = os.getenv("QDRANT_API_KEY")
qdrant = QdrantClient(
    url=qdrant_url,
    api_key=qdrant_api_key,
    timeout=60.0 
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
                timeout=60.0 
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

for field_name in ["source", "user_id"]:
    try:
        qdrant.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema="keyword" 
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


app.include_router(auth_router, prefix="/auth", tags=["Authentication"])

# Root path for testing authentication
@app.get("/", summary="Test authentication status", response_model=dict)
async def root(current_user: User = Depends(get_current_active_user)):
    """
    A simple endpoint to confirm that the user is authenticated.
    Returns a welcome message with the user's email.
    """
    logger.info(f"Authenticated user accessed root: {current_user.email}")
    return {"message": f"Welcome, {current_user.email}! Authentication successful."}


# === Upload Multiple PDFs Endpoint ===
@app.post("/upload", summary="Upload and index multiple PDF documents", response_model=dict)
async def upload_documents(files: list[UploadFile] = File(..., description="PDF documents to upload."),
                          current_user: User = Depends(get_current_active_user)):
    """
    Uploads multiple PDF documents, extracts their text, embeds chunks, and indexes them into Qdrant.
    Documents are added incrementally to the user's existing collection.
    Requires authentication.
    """
    if not files:
        raise HTTPException(status_code=400, detail="🚫 No files provided.")
    
    if len(files) > 10:  # Limit to prevent abuse
        raise HTTPException(status_code=400, detail="🚫 Maximum 10 files allowed per upload.")
    
    logger.info(f"User {current_user.email} attempting to upload {len(files)} documents")

    # Validate all files are PDFs
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            logger.warning(f"Upload failed for {current_user.email}: Invalid file type '{file.filename}'")
            raise HTTPException(status_code=400, detail=f"🚫 Only PDF files are allowed. Found: {file.filename}")

    all_points = []
    successful_uploads = []
    failed_uploads = []

    for file in files:
        try:
            # Read file content
            file_content = await file.read()
            if len(file_content) > 50 * 1024 * 1024:  # 50MB limit per file
                failed_uploads.append(f"{file.filename}: File too large (>50MB)")
                continue
                
            doc = fitz.open(stream=file_content, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            
            if not text.strip():
                failed_uploads.append(f"{file.filename}: No readable text found")
                continue

            # Improved chunking with overlap for better context preservation
            chunk_size = 800  # Increased chunk size for better context
            overlap = 100     # Overlap between chunks
            chunks = []
            
            for i in range(0, len(text), chunk_size - overlap):
                chunk = text[i:i + chunk_size]
                if len(chunk.strip()) > 50:  # Only include substantial chunks
                    chunks.append(chunk.strip())
            
            if not chunks:
                failed_uploads.append(f"{file.filename}: No valid chunks extracted")
                continue

            # Process chunks in batches to handle large documents
            batch_size = 50  # Process 50 chunks at a time
            for batch_start in range(0, len(chunks), batch_size):
                batch_chunks = chunks[batch_start:batch_start + batch_size]
                
                try:
                    vectors = embedder.encode(batch_chunks).tolist()
                except Exception as e:
                    logger.error(f"Error encoding chunks for {file.filename}: {e}", exc_info=True)
                    failed_uploads.append(f"{file.filename}: Error processing chunks")
                    break

                # Create points for this batch
                for i, (vector, chunk) in enumerate(zip(vectors, batch_chunks)):
                    chunk_index = batch_start + i
                    # Create unique ID using file content hash for deduplication
                    content_hash = str(hash(chunk[:200]))  # Use first 200 chars for hash
                    point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{current_user.id}-{file.filename}-{chunk_index}-{content_hash}"))
                    
                    all_points.append(
                        PointStruct(
                            id=point_id, 
                            vector=vector, 
                            payload={
                                "text": chunk, 
                                "source": "document", 
                                "filename": file.filename, 
                                "user_id": str(current_user.id),
                                "chunk_index": chunk_index,
                                "total_chunks": len(chunks),
                                "upload_timestamp": str(uuid.uuid4().time_low)  # Simple timestamp
                            }
                        )
                    )
            
            successful_uploads.append(f"{file.filename}: {len(chunks)} chunks")
            logger.info(f"Successfully processed {file.filename} with {len(chunks)} chunks for user {current_user.email}")

        except Exception as e:
            logger.error(f"Error processing {file.filename} for user {current_user.email}: {e}", exc_info=True)
            failed_uploads.append(f"{file.filename}: Processing error - {str(e)[:100]}")

    # Batch insert all points to Qdrant
    if all_points:
        try:
            # Process in batches of 100 points to avoid memory issues
            batch_size = 100
            total_inserted = 0
            
            for i in range(0, len(all_points), batch_size):
                batch_points = all_points[i:i + batch_size]
                upsert_result = qdrant.upsert(collection_name=collection_name, points=batch_points, wait=True)
                
                if upsert_result.status == 'completed':
                    total_inserted += len(batch_points)
                    logger.info(f"Successfully indexed batch {i//batch_size + 1} with {len(batch_points)} points for user {current_user.email}")
                else:
                    logger.error(f"Qdrant upsert status not completed for batch {i//batch_size + 1}: {upsert_result.status}")
            
            response_message = f"✅ Successfully uploaded {len(successful_uploads)} documents with {total_inserted} total chunks!"
            if failed_uploads:
                response_message += f"\n⚠️ Failed uploads: {', '.join(failed_uploads)}"
            
            return JSONResponse(status_code=200, content={"detail": response_message})

        except Exception as e:
            logger.error(f"Failed to index documents for user {current_user.email}: {e}", exc_info=True)
            raise HTTPException(status_code=500, content={"detail": f"❌ Failed to index documents: {e}"})
    else:
        error_message = "❌ No documents could be processed successfully."
        if failed_uploads:
            error_message += f" Errors: {', '.join(failed_uploads)}"
        raise HTTPException(status_code=400, detail=error_message)


# === Ask Question Endpoint ===
class QuestionRequest(BaseModel):
    question: str

@app.post("/ask", summary="Ask a question about uploaded documents", response_model=dict)
async def ask_question(data: QuestionRequest, current_user: User = Depends(get_current_active_user)):
    """
    Asks a question and retrieves answers based on the authenticated user's indexed documents.
    Searches across all uploaded PDFs for the user. Requires authentication.
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

    document_context = ""
    source_files = set()
    
    try:
        # Query for relevant chunks from all user documents
        document_results = qdrant.query_points(
            collection_name=collection_name,
            query=q_vec,
            limit=20, # Retrieve more chunks for better reranking across multiple documents
            with_payload=True,
            query_filter=Filter(
                must=[
                    FieldCondition(key="source", match=MatchValue(value="document")),
                    FieldCondition(key="user_id", match=MatchValue(value=str(current_user.id)))
                ]
            )
        )
        
        retrieved_chunks = []
        for point in document_results.points:
            if point.payload and "text" in point.payload:
                retrieved_chunks.append(point.payload["text"])
                if "filename" in point.payload:
                    source_files.add(point.payload["filename"])
        
        if retrieved_chunks:
            # Rerank to get the most relevant chunks across all documents
            top_relevant_chunks = rerank_chunks(data.question, retrieved_chunks, top_k=5)
            document_context = "\n\n".join([f"[Chunk {i+1}]: {chunk}" for i, chunk in enumerate(top_relevant_chunks)])
            
            source_info = f"Sources: {', '.join(list(source_files)[:3])}"  # Show up to 3 source files
            if len(source_files) > 3:
                source_info += f" and {len(source_files) - 3} more"
            
            logger.info(f"Generated document context with {len(top_relevant_chunks)} chunks from {len(source_files)} files for user {current_user.email}.")
        else:
            document_context = "No relevant information found in your uploaded documents."
            logger.info(f"No relevant chunks found in Qdrant for user {current_user.email}.")

    except Exception as e:
        logger.error(f"Error querying document context from Qdrant for user {current_user.email}: {e}", exc_info=True)
        document_context = "An error occurred while retrieving relevant information from your documents."

    # --- Enhanced Prompt for Gemini ---
    prompt = f"""
You are a helpful, knowledgeable, and empathetic AI assistant designed to assist users in understanding their uploaded documents and answering questions about their content.

--- User's Question ---
{data.question}
--- End of Question ---

--- Extracted Document Context ---
{document_context}
--- End of Document Context ---

Instructions:
1. Use the provided document context to answer the user's question as accurately and clearly as possible.
2. If the information is found across multiple documents, synthesize the information coherently.
3. If specific information is mentioned in the context, cite which document or section it comes from when relevant.
4. Respond with clarity, empathy, and professionalism, making the explanation easy to understand.
5. If the question cannot be answered from the provided context, clearly state this limitation.
6. Include a polite disclaimer at the end of your response:

"**Disclaimer:** This information is based on the content of your uploaded documents and is for educational purposes only. Please verify important information and consult appropriate professionals when needed."

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


# === Document Management Endpoints ===

@app.get("/documents", summary="List user's uploaded documents", response_model=dict)
async def list_documents(current_user: User = Depends(get_current_active_user)):
    """
    Lists all documents uploaded by the authenticated user with metadata.
    """
    try:
        # Query all points for the user to get document metadata
        all_results = qdrant.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="source", match=MatchValue(value="document")),
                    FieldCondition(key="user_id", match=MatchValue(value=str(current_user.id)))
                ]
            ),
            limit=1000,  # Adjust based on expected document count
            with_payload=True
        )
        
        documents = {}
        for point in all_results[0]:  # all_results is a tuple (points, next_page_offset)
            if point.payload and "filename" in point.payload:
                filename = point.payload["filename"]
                if filename not in documents:
                    documents[filename] = {
                        "filename": filename,
                        "total_chunks": 0,
                        "upload_timestamp": point.payload.get("upload_timestamp", "unknown")
                    }
                documents[filename]["total_chunks"] += 1
        
        document_list = list(documents.values())
        logger.info(f"Retrieved {len(document_list)} documents for user {current_user.email}")
        
        return JSONResponse(status_code=200, content={
            "documents": document_list,
            "total_documents": len(document_list),
            "total_chunks": sum(doc["total_chunks"] for doc in document_list)
        })
        
    except Exception as e:
        logger.error(f"Error listing documents for user {current_user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"❌ Error retrieving documents: {e}")


@app.delete("/documents/{filename}", summary="Delete a specific document", response_model=dict)
async def delete_document(filename: str, current_user: User = Depends(get_current_active_user)):
    """
    Deletes a specific document and all its chunks from the user's collection.
    """
    try:
        # Delete all points for the specific document
        delete_result = qdrant.delete(
            collection_name=collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(key="source", match=MatchValue(value="document")),
                        FieldCondition(key="user_id", match=MatchValue(value=str(current_user.id))),
                        FieldCondition(key="filename", match=MatchValue(value=filename))
                    ]
                )
            ),
            wait=True
        )
        
        if delete_result.status == 'completed':
            deleted_count = delete_result.result.points if hasattr(delete_result.result, 'points') else 0
            logger.info(f"Successfully deleted document '{filename}' with {deleted_count} chunks for user {current_user.email}")
            return JSONResponse(status_code=200, content={
                "detail": f"✅ Document '{filename}' deleted successfully!",
                "deleted_chunks": deleted_count
            })
        else:
            logger.warning(f"Delete status not completed for document '{filename}': {delete_result.status}")
            raise HTTPException(status_code=500, detail=f"❌ Failed to delete document: {delete_result.status}")
            
    except UnexpectedResponse as e:
        if e.status_code == 404:
            logger.info(f"Document '{filename}' not found for user {current_user.email}")
            raise HTTPException(status_code=404, detail=f"🚫 Document '{filename}' not found.")
        else:
            logger.error(f"Unexpected response during document deletion: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"❌ Error deleting document: {e}")
    except Exception as e:
        logger.error(f"Error deleting document '{filename}' for user {current_user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"❌ Error deleting document: {e}")


@app.delete("/documents", summary="Delete all user documents", response_model=dict)
async def delete_all_documents(current_user: User = Depends(get_current_active_user)):
    """
    Deletes all documents and chunks for the authenticated user.
    """
    try:
        delete_result = qdrant.delete(
            collection_name=collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(key="source", match=MatchValue(value="document")),
                        FieldCondition(key="user_id", match=MatchValue(value=str(current_user.id)))
                    ]
                )
            ),
            wait=True
        )
        
        if delete_result.status == 'completed':
            deleted_count = delete_result.result.points if hasattr(delete_result.result, 'points') else 0
            logger.info(f"Successfully deleted all documents with {deleted_count} chunks for user {current_user.email}")
            return JSONResponse(status_code=200, content={
                "detail": "✅ All documents deleted successfully!",
                "deleted_chunks": deleted_count
            })
        else:
            logger.warning(f"Delete all status not completed for user {current_user.email}: {delete_result.status}")
            raise HTTPException(status_code=500, detail=f"❌ Failed to delete documents: {delete_result.status}")
            
    except Exception as e:
        logger.error(f"Error deleting all documents for user {current_user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"❌ Error deleting documents: {e}")
