// app.js - Enhanced with modern UI interactions

const backendUrl = "http://127.0.0.1:8000";

// Helper function to update status messages
function updateStatus(elementId, message, type = '') {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = message;
        element.className = 'status-message'; // Reset classes
        if (type === 'upload') {
            element.classList.add('upload-status');
        } else if (type === 'question') {
            element.classList.add('question-status');
        }
        element.classList.add('visible'); // Make sure it's visible
        element.classList.add('animate-fade-in'); // Add animation
    }
}

// Helper function to disable/enable buttons and show/hide spinner
function setButtonLoading(buttonId, isLoading, defaultText, iconSvg) {
    const button = document.getElementById(buttonId);
    if (button) {
        button.disabled = isLoading;
        if (isLoading) {
            button.innerHTML = '<span class="spinner"></span>' + (buttonId === 'uploadButton' ? 'Uploading...' : 'Processing...');
        } else {
            button.innerHTML = iconSvg + ' <span>' + defaultText + '</span>';
        }
    }
}

// Enhanced file upload with drag and drop
function setupFileUpload() {
    const fileInput = document.getElementById("fileInput");
    const uploadArea = document.querySelector(".upload-area");
    
    // Drag and drop functionality
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('drag-over');
    });
    
    uploadArea.addEventListener('dragleave', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');
    });
    
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            fileInput.files = files;
            updateFileDisplay(files[0]);
        }
    });
    
    // File input change
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            updateFileDisplay(e.target.files[0]);
        }
    });
}

function updateFileDisplay(file) {
    const uploadArea = document.querySelector(".upload-area");
    const uploadText = uploadArea.querySelector(".upload-text");
    
    if (file) {
        uploadText.innerHTML = `
            <p class="upload-primary">📄 ${file.name}</p>
            <p class="upload-secondary">Ready to upload (${(file.size / 1024 / 1024).toFixed(2)} MB)</p>
        `;
    }
}

async function uploadReport() {
    const fileInput = document.getElementById("fileInput");
    const answerCard = document.getElementById("answerCard");
    const answerText = document.getElementById("answerText");
    const questionStatus = document.getElementById("questionStatus");
    const uploadStatus = document.getElementById("uploadStatus");

    // Define the SVG for the upload button
    const uploadIconSvg = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="17 8 12 3 7 8"/>
        <line x1="12" x2="12" y1="3" y2="15"/>
    </svg>`;

    // Hide answer card and clear previous status messages on new upload attempt
    answerCard.style.display = 'none';
    answerCard.classList.remove('visible', 'animate-fade-in');
    answerText.textContent = '';
    questionStatus.textContent = '';
    questionStatus.classList.remove('visible', 'animate-fade-in', 'question-status');
    uploadStatus.classList.remove('visible', 'animate-fade-in', 'upload-status');

    setButtonLoading('uploadButton', true, 'Upload Document', uploadIconSvg);
    updateStatus('uploadStatus', 'Uploading and processing your document...', 'upload');

    if (!fileInput.files.length) {
        updateStatus('uploadStatus', '❌ Please select a PDF file first.', 'upload');
        setButtonLoading('uploadButton', false, 'Upload Document', uploadIconSvg);
        return;
    }

    const file = fileInput.files[0];
    if (file.type !== 'application/pdf') {
        updateStatus('uploadStatus', '❌ Please upload a PDF file only.', 'upload');
        setButtonLoading('uploadButton', false, 'Upload Document', uploadIconSvg);
        return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
        const response = await fetch(`${backendUrl}/upload`, {
            method: "POST",
            body: formData,
        });

        const result = await response.json();
        if (response.ok) {
            updateStatus('uploadStatus', result.detail || "✅ Document uploaded successfully! You can now ask questions.", 'upload');
        } else {
            updateStatus('uploadStatus', result.detail || "❌ Upload failed. Please check the backend server.", 'upload');
            console.error("Upload error response:", result);
        }
    } catch (err) {
        updateStatus('uploadStatus', "❌ Upload failed. Could not connect to the backend server.", 'upload');
        console.error("Upload fetch error:", err);
    } finally {
        setButtonLoading('uploadButton', false, 'Upload Document', uploadIconSvg);
    }
}

async function askQuestion() {
    const questionInput = document.getElementById("questionInput");
    const answerCard = document.getElementById("answerCard");
    const answerText = document.getElementById("answerText");
    const questionStatus = document.getElementById("questionStatus");

    // Define the SVG for the ask button
    const askIconSvg = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
    </svg>`;

    const question = questionInput.value.trim();

    // Clear previous answer and status
    answerText.textContent = '';
    answerCard.classList.remove('visible', 'animate-fade-in');
    answerCard.style.display = 'none';
    questionStatus.classList.remove('visible', 'animate-fade-in', 'question-status');

    setButtonLoading('askButton', true, 'Get Answer', askIconSvg);
    updateStatus('questionStatus', 'Processing your question...', 'question');

    if (!question) {
        updateStatus('questionStatus', '❌ Please enter a question.', 'question');
        setButtonLoading('askButton', false, 'Get Answer', askIconSvg);
        return;
    }

    try {
        const response = await fetch(`${backendUrl}/ask`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question }),
        });

        const result = await response.json();
        if (response.ok) {
            answerText.textContent = result.answer || "No answer found for your question.";
            answerCard.style.display = 'block';
            // Small delay for smooth animation
            setTimeout(() => {
                answerCard.classList.add('visible', 'animate-fade-in');
            }, 100);
            updateStatus('questionStatus', '✅ Analysis completed successfully!', 'question');
            
            // Scroll to results
            answerCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
            updateStatus('questionStatus', result.detail || "❌ Failed to get answer. Please check the backend server.", 'question');
            console.error("Ask question error response:", result);
        }

    } catch (err) {
        updateStatus('questionStatus', "❌ Failed to get answer. Could not connect to the backend server.", 'question');
        console.error("Ask question fetch error:", err);
    } finally {
        setButtonLoading('askButton', false, 'Get Answer', askIconSvg);
    }
}

// Enhanced keyboard shortcuts
function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Enter key in question input
        if (e.target.id === 'questionInput' && e.key === 'Enter') {
            askQuestion();
        }
        
        // Ctrl/Cmd + U for upload
        if ((e.ctrlKey || e.metaKey) && e.key === 'u') {
            e.preventDefault();
            document.getElementById('fileInput').click();
        }
    });
}

// Attach event listeners after DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    setupFileUpload();
    setupKeyboardShortcuts();
    
    document.getElementById('uploadButton').addEventListener('click', uploadReport);
    document.getElementById('askButton').addEventListener('click', askQuestion);
    
    // Add click handler for upload area
    document.querySelector('.upload-area').addEventListener('click', () => {
        document.getElementById('fileInput').click();
    });
});
