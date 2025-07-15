// --- Configuration ---
const backendUrl = "http://127.0.0.1:8000"; 
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
        }

        // Clear the token from the URL for security and cleanliness
        window.history.replaceState({}, document.title, window.location.pathname);
        console.log("JWT Token received and stored.");
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

    const initialUploadState = uploadZone ? uploadZone.querySelector('.initial-state') : null;
    const selectedFileDisplay = document.getElementById('fileDisplayNameInsideBox');
    const fileNameText = selectedFileDisplay ? selectedFileDisplay.querySelector('.file-name-text') : null;
    const clearFileButton = document.getElementById('clearFileButton');


    if (uploadButton) {
        uploadButton.addEventListener('click', (event) => {
            event.preventDefault();
            uploadReport();
        });
    }

    if (askButton) {
        askButton.addEventListener('click', askQuestion);
    }

    if (fileInput && uploadZone) {
        if (browseBtn) {
            browseBtn.addEventListener('click', (e) => {
                e.preventDefault();
                fileInput.click();
            });
        }
        
        const updateFileDisplay = (file) => {
            if (file && fileNameText && initialUploadState && selectedFileDisplay) {
                fileNameText.textContent = file.name;
                initialUploadState.style.display = 'none';
                selectedFileDisplay.style.display = 'flex';
                uploadStatus.textContent = `Selected: ${file.name}`;
                uploadStatus.style.color = '#6EE7B7';
            } else if (fileNameText && initialUploadState && selectedFileDisplay) {
                fileNameText.textContent = "";
                initialUploadState.style.display = 'flex';
                selectedFileDisplay.style.display = 'none';
                uploadStatus.textContent = "No file selected.";
                uploadStatus.style.color = 'inherit';
            }
        };

        fileInput.addEventListener('change', (event) => {
            const file = event.target.files[0];
            updateFileDisplay(file);
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
                fileInput.files = files;
                updateFileDisplay(files[0]);
            }
        });

        if (clearFileButton) {
            clearFileButton.addEventListener('click', (e) => {
                e.preventDefault();
                fileInput.value = '';
                updateFileDisplay(null);
                uploadStatus.textContent = "File cleared. Please select another.";
                uploadStatus.style.color = '#F59E0B';
            });
        }
    }

    if (logoutBtn) {
        logoutBtn.addEventListener('click', logout);
    }
});


// --- API Calls ---

async function uploadReport() {
    const fileInput = document.getElementById('fileInput');
    const uploadStatus = document.getElementById('uploadStatus');
    const file = fileInput.files[0];

    if (!file) {
        uploadStatus.textContent = "🚫 Please select a PDF file first.";
        uploadStatus.style.color = '#EF4444';
        return;
    }

    if (file.size > 10 * 1024 * 1024) {
        uploadStatus.textContent = "🚫 File size exceeds 10MB limit.";
        uploadStatus.style.color = '#EF4444';
        return;
    }

    const token = getJwtToken();
    if (!token) {
        uploadStatus.textContent = "🚫 Not authenticated. Please log in.";
        uploadStatus.style.color = '#EF4444';
        setTimeout(() => window.location.href = loginPage, 2000); // **UPDATED: Redirect to loginPage**
        return;
    }

    uploadStatus.textContent = "Uploading and processing... ⏳";
    uploadStatus.style.color = '#F59E0B';

    const formData = new FormData();
    formData.append("file", file);

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
            document.getElementById('fileInput').value = '';
            const uploadZone = document.getElementById('uploadZone');
            const initialUploadState = uploadZone ? uploadZone.querySelector('.initial-state') : null;
            const selectedFileDisplay = document.getElementById('fileDisplayNameInsideBox');
            if (initialUploadState && selectedFileDisplay) {
                initialUploadState.style.display = 'flex';
                selectedFileDisplay.style.display = 'none';
            }
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