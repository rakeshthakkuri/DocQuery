// --- Configuration ---
const backendUrl = "https://docquerytest.fly.dev"; 
const loginPage = "index.html"; 
const mainAppPage = "app.html";

// --- Utility Functions ---

function getJwtToken() {
    return localStorage.getItem('jwt_token');
}

function setJwtToken(token) {
    localStorage.setItem('jwt_token', token);
}

function removeJwtToken() {
    localStorage.removeItem('jwt_token');
    localStorage.removeItem('user_info'); // Clear any stored user info
}

function decodeJwtToken(token) {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join(''));
        return JSON.parse(jsonPayload);
    } catch (e) {
        console.error("Error decoding JWT:", e);
        return null;
    }
}

function displayUserInfo() {
    const userNameElement = document.getElementById('userName');
    const logoutBtn = document.getElementById('logoutButton');

    const userInfo = JSON.parse(localStorage.getItem('user_info'));

    if (userInfo && userInfo.name) {
        userNameElement.textContent = `Welcome, ${userInfo.name}!`;
        if (logoutBtn) logoutBtn.style.display = 'block'; // Ensure logout button is visible
    } else {
        userNameElement.textContent = "Guest";
        if (logoutBtn) logoutBtn.style.display = 'none'; // Hide logout button if no user info
    }
}


// --- Authentication Logic ---

function handleAuthCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');
    const error = urlParams.get('error');

    console.log("Auth callback - Token found:", !!token);
    console.log("Auth callback - Error found:", error);
    console.log("Current URL:", window.location.href);

    // Handle OAuth errors
    if (error) {
        console.error("OAuth error:", error);
        if (error === 'csrf_state_mismatch') {
            alert('Authentication session expired. Please try logging in again.');
            // Clear any existing tokens and redirect to login
            removeJwtToken();
            window.location.href = 'https://docquerytest.fly.dev/auth/google/login';
            return;
        }
    }

    if (token) {
        setJwtToken(token);
        const decodedToken = decodeJwtToken(token);
        if (decodedToken) {
            localStorage.setItem('user_info', JSON.stringify({
                id: decodedToken.sub,
                name: decodedToken.name,
                email: decodedToken.email,
                // picture: decodedToken.picture // Uncomment if you store/display user picture
            }));
            console.log("User info stored:", decodedToken.name, decodedToken.email);
        }

        // Clear the token from the URL for security and cleanliness
        const cleanUrl = window.location.pathname;
        window.history.replaceState({}, document.title, cleanUrl);
        console.log("JWT Token received and stored. Cleaned URL to:", cleanUrl);
        displayUserInfo(); // Update UI immediately after token is processed
    } else {
        // If no token in URL and not already logged in, redirect to login page
        if (!getJwtToken()) {
            console.log("No JWT Token found, redirecting to login.");
            
            // **UPDATED REDIRECTION LOGIC**
            // Get the current path (e.g., "/app.html", or "/" if it's the root)
            const currentPath = window.location.pathname;
            
            // Check if the current page is indeed the main application page (where this script runs)
            // It could be '/app.html' or if 'app.html' is served as the root, it could be '/'
            const isCurrentlyOnMainAppPage = currentPath.endsWith(`/${mainAppPage}`) || currentPath === "/";

            // Only redirect to the login page if we are on the main app page AND not already on the login page
            // (The login page is now 'index.html' at the root, so its path would be '/' or '/index.html')
            const isCurrentlyOnLoginPage = currentPath.endsWith(`/${loginPage}`) || currentPath === "/"; // This line might be redundant if mainAppPage is not '/'

            // The main condition is: If we are on the page that runs this script (mainAppPage)
            // AND we don't have a token, then redirect to the login page.
            if (isCurrentlyOnMainAppPage && !getJwtToken()) { // Re-check getJwtToken here to be sure
                 window.location.href = loginPage; // Redirect to the NEW login page (which is now index.html)
            }
            // If the user navigates directly to the root ('/') and your static host serves 'app.html' as default,
            // the 'currentPath === "/"' condition ensures they are redirected.
            // If the user navigates directly to 'index.html' (the login page), this handleAuthCallback
            // should not be running, as app.js is not included there.
        } else {
            // Token exists in local storage, display user info
            displayUserInfo();
        }
    }
}

function logout() {
    removeJwtToken();
    window.location.href = loginPage; // **UPDATED: Redirect to the NEW login page**
}

// --- Event Listeners ---
document.addEventListener('DOMContentLoaded', () => {
    handleAuthCallback(); // Ensure this runs early

    const uploadButton = document.getElementById('uploadButton');
    const askButton = document.getElementById('askButton');
    const fileInput = document.getElementById('fileInput');
    const questionInput = document.getElementById('questionInput');
    const uploadStatus = document.getElementById('uploadStatus');
    const questionStatus = document.getElementById('questionStatus');
    const answerText = document.getElementById('answerText');
    const logoutBtn = document.getElementById('logoutButton');
    const uploadZone = document.getElementById('uploadZone');
    const browseBtn = document.getElementById('browseBtn');

    // Multiple file upload elements
    const initialUploadState = uploadZone ? uploadZone.querySelector('.initial-state') : null;
    const selectedFilesDisplay = document.getElementById('selectedFilesDisplay');
    const filesCount = document.getElementById('filesCount');
    const filesList = document.getElementById('filesList');
    const clearAllButton = document.getElementById('clearAllButton');

    // Document management elements
    const refreshDocumentsButton = document.getElementById('refreshDocumentsButton');
    const deleteAllDocumentsButton = document.getElementById('deleteAllDocumentsButton');
    const documentsList = document.getElementById('documentsList');
    const documentsStatus = document.getElementById('documentsStatus');


    if (uploadButton) {
        uploadButton.addEventListener('click', (event) => {
            event.preventDefault();
            uploadDocuments();
        });
    }

    if (askButton) {
        askButton.addEventListener('click', askQuestion);
    }

    // Document management event listeners
    if (refreshDocumentsButton) {
        refreshDocumentsButton.addEventListener('click', loadDocuments);
    }

    if (deleteAllDocumentsButton) {
        deleteAllDocumentsButton.addEventListener('click', deleteAllDocuments);
    }

    if (fileInput && uploadZone) {
        if (browseBtn) {
            browseBtn.addEventListener('click', (e) => {
                e.preventDefault();
                fileInput.click();
            });
        }
        
        const updateFilesDisplay = (files) => {
            if (files && files.length > 0) {
                // Show selected files display
                if (initialUploadState && selectedFilesDisplay) {
                    initialUploadState.style.display = 'none';
                    selectedFilesDisplay.style.display = 'block';
                }
                
                // Update files count
                if (filesCount) {
                    filesCount.textContent = `${files.length} file${files.length > 1 ? 's' : ''} selected`;
                }
                
                // Clear and populate files list
                if (filesList) {
                    filesList.innerHTML = '';
                    Array.from(files).forEach((file, index) => {
                        const fileItem = createFileItem(file, index);
                        filesList.appendChild(fileItem);
                    });
                }
                
                uploadStatus.textContent = `Selected ${files.length} file${files.length > 1 ? 's' : ''}`;
                uploadStatus.style.color = '#6EE7B7';
            } else {
                // Show initial state
                if (initialUploadState && selectedFilesDisplay) {
                    initialUploadState.style.display = 'flex';
                    selectedFilesDisplay.style.display = 'none';
                }
                uploadStatus.textContent = "No files selected.";
                uploadStatus.style.color = 'inherit';
            }
        };

        const createFileItem = (file, index) => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';
            fileItem.innerHTML = `
                <span class="file-icon">📄</span>
                <div class="file-info">
                    <div class="file-name">${file.name}</div>
                    <div class="file-size">${formatFileSize(file.size)}</div>
                </div>
                <button class="remove-file-button" data-index="${index}">
                    <i class="fas fa-times"></i>
                </button>
            `;
            
            // Add remove file functionality
            const removeBtn = fileItem.querySelector('.remove-file-button');
            removeBtn.addEventListener('click', (e) => {
                e.preventDefault();
                removeFile(index);
            });
            
            return fileItem;
        };

        const removeFile = (index) => {
            const dt = new DataTransfer();
            const files = Array.from(fileInput.files);
            files.splice(index, 1);
            
            files.forEach(file => dt.items.add(file));
            fileInput.files = dt.files;
            
            updateFilesDisplay(fileInput.files);
        };

        const formatFileSize = (bytes) => {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        };

        fileInput.addEventListener('change', (event) => {
            const files = event.target.files;
            updateFilesDisplay(files);
        });

        uploadZone.addEventListener('dragover', (event) => {
            event.preventDefault();
            uploadZone.classList.add('drag-over');
        });
        
        uploadZone.addEventListener('dragleave', () => {
            uploadZone.classList.remove('drag-over');
        });
        
        uploadZone.addEventListener('drop', (event) => {
            event.preventDefault();
            uploadZone.classList.remove('drag-over');
            const files = event.dataTransfer.files;
            if (files.length > 0) {
                // Filter only PDF files
                const pdfFiles = Array.from(files).filter(file => 
                    file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
                );
                
                if (pdfFiles.length !== files.length) {
                    uploadStatus.textContent = `Only PDF files are allowed. ${pdfFiles.length} of ${files.length} files are valid.`;
                    uploadStatus.style.color = '#F59E0B';
                }
                
                if (pdfFiles.length > 0) {
                    const dt = new DataTransfer();
                    pdfFiles.forEach(file => dt.items.add(file));
                    fileInput.files = dt.files;
                    updateFilesDisplay(fileInput.files);
                }
            }
        });

        if (clearAllButton) {
            clearAllButton.addEventListener('click', (e) => {
                e.preventDefault();
                fileInput.value = '';
                updateFilesDisplay(null);
                uploadStatus.textContent = "All files cleared.";
                uploadStatus.style.color = '#F59E0B';
            });
        }
    }

    if (logoutBtn) {
        logoutBtn.addEventListener('click', logout);
    }
});


// --- API Calls ---

async function uploadDocuments() {
    const fileInput = document.getElementById('fileInput');
    const uploadStatus = document.getElementById('uploadStatus');
    const files = fileInput.files;

    if (!files || files.length === 0) {
        uploadStatus.textContent = "🚫 Please select PDF files first.";
        uploadStatus.style.color = '#EF4444';
        return;
    }

    if (files.length > 10) {
        uploadStatus.textContent = "🚫 Maximum 10 files allowed per upload.";
        uploadStatus.style.color = '#EF4444';
        return;
    }

    // Check file sizes
    for (let file of files) {
        if (file.size > 50 * 1024 * 1024) { // 50MB limit
            uploadStatus.textContent = `🚫 File "${file.name}" exceeds 50MB limit.`;
            uploadStatus.style.color = '#EF4444';
            return;
        }
    }

    const token = getJwtToken();
    console.log("Upload - Token available:", !!token);
    if (!token) {
        uploadStatus.textContent = "🚫 Not authenticated. Please log in.";
        uploadStatus.style.color = '#EF4444';
        setTimeout(() => window.location.href = loginPage, 2000);
        return;
    }

    uploadStatus.textContent = `Uploading and processing ${files.length} file${files.length > 1 ? 's' : ''}... ⏳`;
    uploadStatus.style.color = '#F59E0B';

    const formData = new FormData();
    Array.from(files).forEach(file => {
        formData.append("files", file);
    });

    try {
        const response = await fetch(`${backendUrl}/upload`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData,
        });

        const data = await response.json();

        if (response.ok) {
            uploadStatus.textContent = data.detail;
            uploadStatus.style.color = '#6EE7B7';
            
            // Clear the file input and reset UI
            document.getElementById('fileInput').value = '';
            const uploadZone = document.getElementById('uploadZone');
            const initialUploadState = uploadZone ? uploadZone.querySelector('.initial-state') : null;
            const selectedFilesDisplay = document.getElementById('selectedFilesDisplay');
            if (initialUploadState && selectedFilesDisplay) {
                initialUploadState.style.display = 'flex';
                selectedFilesDisplay.style.display = 'none';
            }
            
            // Refresh documents list
            setTimeout(() => loadDocuments(), 1000);
        } else {
            uploadStatus.textContent = `❌ Upload failed: ${data.detail || 'Unknown error'}`;
            uploadStatus.style.color = '#EF4444';
        }
    } catch (error) {
        console.error('Error during upload:', error);
        uploadStatus.textContent = `❌ Network error: ${error.message}`;
        uploadStatus.style.color = '#EF4444';
    }
}

async function askQuestion() {
    const questionInput = document.getElementById('questionInput');
    const questionStatus = document.getElementById('questionStatus');
    const answerText = document.getElementById('answerText');
    const question = questionInput.value.trim();

    if (!question) {
        questionStatus.textContent = "🚫 Please type a question.";
        questionStatus.style.color = '#EF4444';
        return;
    }

    const token = getJwtToken();
    console.log("Ask question - Token available:", !!token);
    if (!token) {
        questionStatus.textContent = "🚫 Not authenticated. Please log in.";
        questionStatus.style.color = '#EF4444';
        setTimeout(() => window.location.href = loginPage, 2000); // **UPDATED: Redirect to loginPage**
        return;
    }

    questionStatus.textContent = "Getting an answer... 🧠";
    questionStatus.style.color = '#F59E0B';
    answerText.textContent = "";

    try {
        const response = await fetch(`${backendUrl}/ask`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ question: question }),
        });

        const data = await response.json();

        if (response.ok) {
            answerText.textContent = data.answer;
            questionStatus.textContent = "Answer ready! 🎉";
            questionStatus.style.color = '#6EE7B7';

            answerText.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });

        } else {
            answerText.textContent = `Error: ${data.detail || 'Unknown error'}`;
            questionStatus.textContent = `❌ Failed to get answer: ${data.detail || 'Unknown error'}`;
            questionStatus.style.color = '#EF4444';
        }
    } catch (error) {
        console.error('Error during question:', error);
        questionStatus.textContent = `❌ Network error: ${error.message}`;
        questionStatus.style.color = '#EF4444';
    }
}

// --- Document Management Functions ---

async function loadDocuments() {
    const documentsList = document.getElementById('documentsList');
    const documentsStatus = document.getElementById('documentsStatus');
    
    const token = getJwtToken();
    if (!token) {
        documentsStatus.textContent = "🚫 Not authenticated. Please log in.";
        documentsStatus.style.color = '#EF4444';
        return;
    }

    documentsStatus.textContent = "Loading documents... ⏳";
    documentsStatus.style.color = '#F59E0B';

    try {
        const response = await fetch(`${backendUrl}/documents`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const data = await response.json();

        if (response.ok) {
            displayDocuments(data.documents);
            documentsStatus.textContent = `✅ Loaded ${data.total_documents} document${data.total_documents !== 1 ? 's' : ''} (${data.total_chunks} chunks)`;
            documentsStatus.style.color = '#6EE7B7';
        } else {
            documentsStatus.textContent = `❌ Failed to load documents: ${data.detail || 'Unknown error'}`;
            documentsStatus.style.color = '#EF4444';
        }
    } catch (error) {
        console.error('Error loading documents:', error);
        documentsStatus.textContent = `❌ Network error: ${error.message}`;
        documentsStatus.style.color = '#EF4444';
    }
}

function displayDocuments(documents) {
    const documentsList = document.getElementById('documentsList');
    
    if (!documents || documents.length === 0) {
        documentsList.innerHTML = '<div class="loading-message">No documents uploaded yet. Upload some PDFs to get started!</div>';
        return;
    }

    documentsList.innerHTML = '';
    documents.forEach(doc => {
        const documentItem = document.createElement('div');
        documentItem.className = 'document-item';
        documentItem.innerHTML = `
            <div class="document-info">
                <div class="document-name">${doc.filename}</div>
                <div class="document-meta">${doc.total_chunks} chunks • Uploaded ${new Date(parseInt(doc.upload_timestamp)).toLocaleDateString()}</div>
            </div>
            <div class="document-actions">
                <button class="btn btn-small btn-outline-danger" onclick="deleteDocument('${doc.filename}')">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="3,6 5,6 21,6"/>
                        <path d="M19,6v14a2,2 0 0,1 -2,2H7a2,2 0 0,1 -2,-2V6m3,0V4a2,2 0 0,1 2,-2h4a2,2 0 0,1 2,2v2"/>
                    </svg>
                    Delete
                </button>
            </div>
        `;
        documentsList.appendChild(documentItem);
    });
}

async function deleteDocument(filename) {
    if (!confirm(`Are you sure you want to delete "${filename}"? This action cannot be undone.`)) {
        return;
    }

    const documentsStatus = document.getElementById('documentsStatus');
    const token = getJwtToken();
    
    if (!token) {
        documentsStatus.textContent = "🚫 Not authenticated. Please log in.";
        documentsStatus.style.color = '#EF4444';
        return;
    }

    documentsStatus.textContent = `Deleting "${filename}"... ⏳`;
    documentsStatus.style.color = '#F59E0B';

    try {
        const response = await fetch(`${backendUrl}/documents/${encodeURIComponent(filename)}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const data = await response.json();

        if (response.ok) {
            documentsStatus.textContent = data.detail;
            documentsStatus.style.color = '#6EE7B7';
            // Refresh the documents list
            setTimeout(() => loadDocuments(), 1000);
        } else {
            documentsStatus.textContent = `❌ Failed to delete document: ${data.detail || 'Unknown error'}`;
            documentsStatus.style.color = '#EF4444';
        }
    } catch (error) {
        console.error('Error deleting document:', error);
        documentsStatus.textContent = `❌ Network error: ${error.message}`;
        documentsStatus.style.color = '#EF4444';
    }
}

async function deleteAllDocuments() {
    if (!confirm('Are you sure you want to delete ALL documents? This action cannot be undone.')) {
        return;
    }

    const documentsStatus = document.getElementById('documentsStatus');
    const token = getJwtToken();
    
    if (!token) {
        documentsStatus.textContent = "🚫 Not authenticated. Please log in.";
        documentsStatus.style.color = '#EF4444';
        return;
    }

    documentsStatus.textContent = "Deleting all documents... ⏳";
    documentsStatus.style.color = '#F59E0B';

    try {
        const response = await fetch(`${backendUrl}/documents`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const data = await response.json();

        if (response.ok) {
            documentsStatus.textContent = data.detail;
            documentsStatus.style.color = '#6EE7B7';
            // Refresh the documents list
            setTimeout(() => loadDocuments(), 1000);
        } else {
            documentsStatus.textContent = `❌ Failed to delete documents: ${data.detail || 'Unknown error'}`;
            documentsStatus.style.color = '#EF4444';
        }
    } catch (error) {
        console.error('Error deleting all documents:', error);
        documentsStatus.textContent = `❌ Network error: ${error.message}`;
        documentsStatus.style.color = '#EF4444';
    }
}