const backendUrl = "http://127.0.0.1:8000";

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
    const userInfoElement = document.getElementById('userInfo'); // Assuming this is your container
    const userNameElement = document.getElementById('userName');
    const userPictureElement = document.getElementById('userPicture'); // If you have one
    const logoutBtn = document.getElementById('logoutButton');

    const userInfo = JSON.parse(localStorage.getItem('user_info'));

    if (userInfo && userInfo.name) {
        userNameElement.textContent = `Welcome, ${userInfo.name}!`;
        if (logoutBtn) logoutBtn.style.display = 'block'; // Ensure logout button is visible
        // You can add logic here to display userPictureElement if userInfo.picture exists
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
                // picture: decodedToken.picture
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
            // Only redirect if we are NOT already on introduction.html to prevent loops
            if (window.location.pathname.endsWith("/index.html") || window.location.pathname === "/") {
                window.location.href = "introduction.html";
            }
        } else {
            // Token exists in local storage, display user info
            displayUserInfo();
        }
    }
}

function logout() {
    removeJwtToken();
    window.location.href = "introduction.html"; // Redirect to login page
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
    const uploadZone = document.getElementById('uploadZone'); // Use ID for consistency
    const browseBtn = document.getElementById('browseBtn'); // New: for the browse button inside the zone

    // New elements for file display inside the box
    const initialUploadState = uploadZone ? uploadZone.querySelector('.initial-state') : null;
    const selectedFileDisplay = document.getElementById('fileDisplayNameInsideBox');
    const fileNameText = selectedFileDisplay ? selectedFileDisplay.querySelector('.file-name-text') : null;
    const clearFileButton = document.getElementById('clearFileButton'); // New: for clearing selected file


    // --- 1. Fix for "double asking" and general upload flow ---
    // Ensure upload button prevents default form submission
    if (uploadButton) {
        uploadButton.addEventListener('click', (event) => {
            event.preventDefault(); // Prevent default form submission if button is type="submit"
            uploadReport();
        });
    }

    if (askButton) {
        askButton.addEventListener('click', askQuestion);
    }

    if (fileInput && uploadZone) {
        // Handle click on browse button inside the zone
        if (browseBtn) {
            browseBtn.addEventListener('click', (e) => {
                e.preventDefault(); // Prevent accidental form submission
                fileInput.click();
            });
        }
        
        // --- 2. Visual feedback for drag-and-drop box ---
        const updateFileDisplay = (file) => {
            if (file && fileNameText && initialUploadState && selectedFileDisplay) {
                fileNameText.textContent = file.name;
                initialUploadState.style.display = 'none'; // Hide initial instructions
                selectedFileDisplay.style.display = 'flex'; // Show selected file display (using flex for layout)
                uploadStatus.textContent = `Selected: ${file.name}`; // Also update status below for clarity
                uploadStatus.style.color = '#6EE7B7';
            } else if (fileNameText && initialUploadState && selectedFileDisplay) {
                // No file selected, revert to initial state
                fileNameText.textContent = "";
                initialUploadState.style.display = 'flex'; // Show initial instructions
                selectedFileDisplay.style.display = 'none'; // Hide selected file display
                uploadStatus.textContent = "No file selected."; // Clear status below
                uploadStatus.style.color = 'inherit';
            }
        };

        // Handle file selection from input
        fileInput.addEventListener('change', (event) => {
            const file = event.target.files[0];
            updateFileDisplay(file);
        });

        // Handle drag and drop
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
                fileInput.files = files; // Assign dropped files to file input
                updateFileDisplay(files[0]);
            }
        });

        // Handle clearing the selected file
        if (clearFileButton) {
            clearFileButton.addEventListener('click', (e) => {
                e.preventDefault();
                fileInput.value = ''; // Clear the file input
                updateFileDisplay(null); // Reset display
                uploadStatus.textContent = "File cleared. Please select another.";
                uploadStatus.style.color = '#F59E0B'; // Orange
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
        uploadStatus.style.color = '#EF4444'; // Red color
        return;
    }

    if (file.size > 10 * 1024 * 1024) { // 10 MB limit
        uploadStatus.textContent = "🚫 File size exceeds 10MB limit.";
        uploadStatus.style.color = '#EF4444';
        return;
    }

    const token = getJwtToken();
    if (!token) {
        uploadStatus.textContent = "🚫 Not authenticated. Please log in.";
        uploadStatus.style.color = '#EF4444';
        setTimeout(() => window.location.href = "introduction.html", 2000);
        return;
    }

    uploadStatus.textContent = "Uploading and processing... ⏳";
    uploadStatus.style.color = '#F59E0B'; // Orange color

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
            uploadStatus.style.color = '#6EE7B7'; // Green color
            // Optional: Clear file input and reset display after successful upload
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
        setTimeout(() => window.location.href = "introduction.html", 2000);
        return;
    }

    questionStatus.textContent = "Getting an answer... 🧠";
    questionStatus.style.color = '#F59E0B';
    answerText.textContent = ""; // Clear previous answer

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

            // --- 3. Fix for answer not sliding down ---
            // Assuming answerText is within a scrollable area, or you want to scroll the window
            answerText.scrollIntoView({
                behavior: 'smooth', // Smooth scrolling
                block: 'center'    // Scroll to the middle of the viewport
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