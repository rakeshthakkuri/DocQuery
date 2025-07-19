# 📄 DocQuery – Document Intelligence with Question Answering

DocQuery is a fully production-ready web application that allows users to upload documents (PDFs) and ask questions about their contents using natural language. It integrates authentication, semantic search, and a responsive web interface into a seamless experience.

---

## 🚀 Features

- 🔐 **Google Authentication**: Secure sign-in with OAuth2 via Google.
- 🔍 **Semantic Search & Question Answering**: Ask natural language questions about your documents.
- 🧠 **Transformer-based Embedding**: Uses `SentenceTransformers` to encode context semantically.
- 📚 **Vector Database Integration**: Qdrant for efficient and scalable similarity search.
- ⚡ **FastAPI Backend**: High-performance API service for document ingestion and query handling.
- 🧾 **PostgreSQL with Supabase**: For user authentication, session storage, and metadata tracking.
- 🌐 **Responsive Frontend**: Built with HTML, CSS, JavaScript for interaction and flow.
- ☁️ **Cloud Ready**: Deployed on Fly.io using Docker.

---

## 🧰 Tech Stack

| Component       | Technology                |
| --------------- | ------------------------- |
| Backend         | FastAPI                   |
| Authentication  | Google OAuth (Authlib)    |
| Embedding       | `sentence-transformers`   |
| Vector DB       | Qdrant                    |
| UI              | HTML, CSS, JavaScript     |
| Database        | Supabase (PostgreSQL)     |
| Deployment      | Docker + Fly.io           |

---

## 📁 Project Structure

```
docquery/
├── backend/                 # FastAPI backend
│   ├── main.py              # Entry point
│   ├── auth/                # Google OAuth handling, routes
│   ├── Dockerfile           # Docker config
│   ├── database.py          # Supabase/PostgreSQL connection & models
│   ├── models.py            # Pydantic models (request/response schemas, DB)
│   ├── requirements.txt     # Python dependencies     
│   ├── fly.toml             # Fly.io deployment config
├── frontend/                # HTML, JS, CSS
│   ├── app.html             # Main query interface after login
│   ├── index.html           # Landing page with "Get Started"
│   ├── app.js               # Handles document upload, query
│   ├── style.css            # Styling
├── .env                     # Secrets & environment config
└── README.md                # Project documentation

---

## 🔧 Setup Instructions

### 1. Clone the Repo

```bash
git clone https://github.com/rakeshthakkuri/DocQuery.git
cd DocQuery
```

### 2. Create and Activate Virtual Environment

```bash
python3.10 -m venv venv
source venv/bin/activate
```

### 3. Install Requirements

```bash
pip install -r backend/requirements.txt
```

### 4. Run Qdrant Locally (Optional)

```bash
docker run -p 6333:6333 qdrant/qdrant
```

Or connect to Qdrant Cloud.

### 5. Configure Environment

Create a `.env` file with:

```
# OAuth (Google Sign-In)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Supabase PostgreSQL Database
DATABASE_URL=https://your-project.supabase.co

# Frontend Redirect (after login)
FRONTEND_REDIRECT_URL=http://localhost:8000/app.html

# Gemini API (if you're using Google Gemini for any tasks)
GEMINI_API_KEY=your-gemini-api-key

# Qdrant Vector Search
QDRANT_URL=https://your-qdrant-instance-url
QDRANT_API_KEY=your-qdrant-api-key

# FastAPI session security
SECRET_KEY=your-random-secret-key

```

### 6. Start the FastAPI App

```bash
cd backend
uvicorn app.main:app --reload
```

Visit: `http://127.0.0.1:8000/docs` or navigate through the UI at `/`.

---

## 🌐 User Flow

1. 🏁 Landing Page: User opens the site and sees a **"Get Started"** button.
2. 🔐 Authentication: Clicking redirects to Google OAuth login.
3. 📄 Document Workspace (`app.html`): Post-login, users land in the dashboard to:
   - Upload documents (PDFs)
   - Query uploaded content using a search bar
   - View highlighted answers from the document

---

## ✅ TODOs

- [ ] Tag-based multi-document search
- [ ] Add document access controls (per-user auth)
- [ ] OCR enhancement for scanned PDFs
- [ ] Add document preview in UI

---

## 🤝 Contributing

Contributions are welcome! Fork, code, and send a PR.

---

## 📜 License

This project is licensed under the MIT License.
