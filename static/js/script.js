// Global variables
let currentUser = null;
const API_BASE = window.location.origin;

// Utility functions
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        border-radius: 5px;
        color: white;
        font-weight: 500;
        z-index: 1000;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        background: ${type === 'success' ? '#2ecc71' : type === 'error' ? '#e74c3c' : '#3498db'};
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

async function apiCall(endpoint, options = {}) {
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        return await response.json();
    } catch (error) {
        showNotification('Network error. Please try again.', 'error');
        throw error;
    }
}

// Chat functionality
function initializeChat() {
    const chatInput = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendMessage');
    const chatWindow = document.getElementById('chatWindow');
    
    if (!chatInput || !sendBtn) return;
    
    function sendMessage() {
        const message = chatInput.value.trim();
        if (!message) return;
        
        addMessage(message, 'user');
        chatInput.value = '';
        chatInput.disabled = true;
        
        apiCall('/chatbot', {
            method: 'POST',
            body: JSON.stringify({ message })
        })
        .then(data => {
            if (data.response) {
                addMessage(data.response, 'ai');
                updateMessageCount();
            }
            if (data.limit_reached) {
                showNotification('Daily message limit reached!', 'error');
            }
        })
        .catch(error => {
            addMessage("I'm having trouble responding. Please try again.", 'ai');
        })
        .finally(() => {
            chatInput.disabled = false;
            chatInput.focus();
        });
    }
    
    function addMessage(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}`;
        messageDiv.innerHTML = `<strong>${sender === 'user' ? 'You' : 'AI'}:</strong> ${text}`;
        chatWindow.appendChild(messageDiv);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }
    
    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
}

// Message limit functionality
async function updateMessageCount() {
    try {
        const result = await apiCall('/api/message_limit');
        const messageCountEl = document.getElementById('messageCount');
        const limitTextEl = document.getElementById('limitText');
        
        if (messageCountEl) {
            messageCountEl.textContent = 50 - result.message_count;
        }
        
        if (limitTextEl) {
            if (result.limit_reached) {
                limitTextEl.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Daily limit reached!';
                limitTextEl.parentElement.style.background = 'var(--danger)';
                limitTextEl.parentElement.style.color = 'white';
            } else {
                limitTextEl.textContent = `You have ${50 - result.message_count} messages remaining today`;
            }
        }
    } catch (error) {
        console.error('Failed to get message count');
    }
}

// Navigation
function initializeNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const contentSections = document.querySelectorAll('.content-section');
    
    navItems.forEach(item => {
        item.addEventListener('click', function() {
            const targetSection = this.dataset.section;
            
            // Update active nav item
            navItems.forEach(nav => nav.classList.remove('active'));
            this.classList.add('active');
            
            // Show target section
            contentSections.forEach(section => section.classList.remove('active'));
            document.getElementById(targetSection).classList.add('active');
            
            // Load section-specific data
            if (targetSection === 'chatbot') {
                updateMessageCount();
            }
        });
    });
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeNavigation();
    initializeChat();
    updateMessageCount();
    
    // Check if user is logged in
    if (window.location.pathname === '/dashboard') {
        showNotification('Welcome back!', 'success');
    }
});

// Export for use in other scripts
window.MindSpace = {
    showNotification,
    apiCall,
    updateMessageCount
};