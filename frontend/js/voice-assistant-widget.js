/**
 * Voice Assistant Widget - Floating Icon Integration
 * Add this to any page to enable voice assistant functionality
 * Automatically fetches real sensor data from the backend
 */

(function() {
    'use strict';

    // Configuration
    const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
        ? 'http://localhost:8000'
        : window.location.origin;
    
    const VOICE_API = `${API_BASE}/api/voice/chat`;
    const READINGS_API = `${API_BASE}/api/fields`;

    // State
    let isListening = false;
    let isProcessing = false;
    let currentFieldId = null;
    let latestSensorData = null;
    let recognition = null;

    // Initialize Speech Recognition
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'hi-IN'; // Default to Hindi
    }

    // Create Widget HTML
    function createWidget() {
        const widgetHTML = `
            <div id="voice-assistant-widget" style="display: none;">
                <!-- Floating Button -->
                <button id="voice-assistant-btn" class="voice-assistant-floating-btn" title="Voice Assistant">
                    <i class="fas fa-microphone"></i>
                </button>

                <!-- Mini Dialog -->
                <div id="voice-assistant-dialog" class="voice-assistant-dialog">
                    <div class="voice-assistant-header">
                        <div class="voice-assistant-title">
                            <i class="fas fa-robot"></i>
                            <span>SoilEdge Assistant</span>
                        </div>
                        <button class="voice-assistant-close" id="voice-assistant-close">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    
                    <div class="voice-assistant-body">
                        <div class="voice-assistant-status" id="voice-status">
                            Click microphone to speak
                        </div>
                        
                        <div class="voice-assistant-transcript" id="voice-transcript" style="display: none;">
                            <strong>You:</strong> <span id="transcript-text"></span>
                        </div>
                        
                        <div class="voice-assistant-answer" id="voice-answer" style="display: none;">
                            <strong>Assistant:</strong> <span id="answer-text"></span>
                        </div>
                        
                        <div class="voice-assistant-data" id="voice-data" style="display: none;">
                            <small>📊 <span id="data-text"></span></small>
                        </div>
                    </div>
                    
                    <div class="voice-assistant-footer">
                        <select id="voice-language" class="voice-language-select">
                            <option value="hi-IN">🇮🇳 हिंदी</option>
                            <option value="mr-IN">🇮🇳 मराठी</option>
                            <option value="en-IN">🇬🇧 English</option>
                        </select>
                    </div>
                </div>
            </div>
        `;

        // Inject HTML
        document.body.insertAdjacentHTML('beforeend', widgetHTML);
        
        // Inject CSS
        injectStyles();
        
        // Show widget after injection
        setTimeout(() => {
            document.getElementById('voice-assistant-widget').style.display = 'block';
        }, 100);
    }

    // Inject Styles
    function injectStyles() {
        const styles = `
            <style id="voice-assistant-styles">
                .voice-assistant-floating-btn {
                    position: fixed;
                    bottom: 30px;
                    right: 30px;
                    width: 60px;
                    height: 60px;
                    border-radius: 50%;
                    background: linear-gradient(135deg, #2E7D32, #43A047);
                    border: none;
                    color: white;
                    font-size: 24px;
                    cursor: pointer;
                    box-shadow: 0 4px 20px rgba(46, 125, 50, 0.4);
                    z-index: 9998;
                    transition: all 0.3s ease;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }

                .voice-assistant-floating-btn:hover {
                    transform: scale(1.1);
                    box-shadow: 0 6px 30px rgba(46, 125, 50, 0.5);
                }

                .voice-assistant-floating-btn.listening {
                    background: linear-gradient(135deg, #E53935, #F44336);
                    animation: pulse-voice 1.5s infinite;
                }

                .voice-assistant-floating-btn.processing {
                    background: linear-gradient(135deg, #1565C0, #1E88E5);
                }

                .voice-assistant-floating-btn.processing i {
                    animation: spin-voice 1s linear infinite;
                }

                @keyframes pulse-voice {
                    0%, 100% { transform: scale(1); }
                    50% { transform: scale(1.1); }
                }

                @keyframes spin-voice {
                    from { transform: rotate(0deg); }
                    to { transform: rotate(360deg); }
                }

                .voice-assistant-dialog {
                    position: fixed;
                    bottom: 100px;
                    right: 30px;
                    width: 340px;
                    max-width: calc(100vw - 60px);
                    background: white;
                    border-radius: 16px;
                    box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15);
                    z-index: 9999;
                    display: none;
                    flex-direction: column;
                    animation: slideUp 0.3s ease;
                }

                .voice-assistant-dialog.show {
                    display: flex;
                }

                @keyframes slideUp {
                    from { transform: translateY(20px); opacity: 0; }
                    to { transform: translateY(0); opacity: 1; }
                }

                .voice-assistant-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 16px;
                    background: linear-gradient(135deg, #2E7D32, #43A047);
                    color: white;
                    border-radius: 16px 16px 0 0;
                }

                .voice-assistant-title {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    font-weight: 600;
                    font-size: 14px;
                }

                .voice-assistant-close {
                    background: rgba(255, 255, 255, 0.2);
                    border: none;
                    color: white;
                    width: 28px;
                    height: 28px;
                    border-radius: 50%;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    transition: all 0.2s ease;
                }

                .voice-assistant-close:hover {
                    background: rgba(255, 255, 255, 0.3);
                }

                .voice-assistant-body {
                    padding: 16px;
                    max-height: 300px;
                    overflow-y: auto;
                }

                .voice-assistant-status {
                    font-size: 13px;
                    color: #666;
                    text-align: center;
                    padding: 8px;
                    background: #f8fafc;
                    border-radius: 8px;
                    margin-bottom: 12px;
                }

                .voice-assistant-status.listening {
                    background: #FFEBEE;
                    color: #E53935;
                    font-weight: 600;
                }

                .voice-assistant-status.processing {
                    background: #E3F2FD;
                    color: #1565C0;
                    font-weight: 600;
                }

                .voice-assistant-transcript,
                .voice-assistant-answer {
                    font-size: 13px;
                    padding: 10px;
                    border-radius: 8px;
                    margin-bottom: 10px;
                    line-height: 1.5;
                }

                .voice-assistant-transcript {
                    background: #f8fafc;
                    border-left: 3px solid #2E7D32;
                }

                .voice-assistant-answer {
                    background: #E8F5E9;
                    border-left: 3px solid #43A047;
                }

                .voice-assistant-data {
                    font-size: 11px;
                    color: #666;
                    padding: 8px;
                    background: #FFF8E1;
                    border-radius: 6px;
                    margin-top: 8px;
                }

                .voice-assistant-footer {
                    padding: 12px 16px;
                    border-top: 1px solid #e8ecf0;
                    background: #f8fafc;
                    border-radius: 0 0 16px 16px;
                }

                .voice-language-select {
                    width: 100%;
                    padding: 8px 12px;
                    border: 2px solid #e8ecf0;
                    border-radius: 8px;
                    font-size: 13px;
                    background: white;
                    cursor: pointer;
                    transition: all 0.2s ease;
                }

                .voice-language-select:focus {
                    outline: none;
                    border-color: #2E7D32;
                }

                @media (max-width: 640px) {
                    .voice-assistant-floating-btn {
                        bottom: 20px;
                        right: 20px;
                        width: 50px;
                        height: 50px;
                        font-size: 20px;
                    }

                    .voice-assistant-dialog {
                        bottom: 80px;
                        right: 20px;
                        width: calc(100vw - 40px);
                    }
                }
            </style>
        `;
        
        document.head.insertAdjacentHTML('beforeend', styles);
    }

    // Fetch Latest Sensor Data
    async function fetchLatestSensorData() {
        try {
            const token = localStorage.getItem('krishi_token');
            
            // Try to get current field ID from localStorage or URL
            currentFieldId = localStorage.getItem('current_field_id') || 
                            new URLSearchParams(window.location.search).get('field_id') ||
                            1; // Default to field 1

            const headers = { 'Content-Type': 'application/json' };
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }

            const response = await fetch(`${READINGS_API}/${currentFieldId}/readings/latest`, {
                headers: headers
            });

            if (response.ok) {
                latestSensorData = await response.json();
                console.log('📊 Fetched sensor data:', latestSensorData);
                return latestSensorData;
            } else {
                console.warn('Could not fetch sensor data, using demo values');
                return null;
            }
        } catch (error) {
            console.warn('Error fetching sensor data:', error);
            return null;
        }
    }

    // Process Voice Query
    async function processVoiceQuery(text) {
        isProcessing = true;
        updateButtonState();
        updateStatus('🤔 Thinking...', 'processing');
        
        try {
            const token = localStorage.getItem('krishi_token');
            
            // Fetch latest sensor data
            const sensorData = await fetchLatestSensorData();
            
            // Build request body
            const requestBody = {
                text: text,
                field_id: currentFieldId ? parseInt(currentFieldId) : null
            };

            // Add sensor data if not available from DB
            if (!sensorData) {
                requestBody.moisture = 28.5;
                requestBody.ph = 6.7;
                requestBody.ec = 5.4;
                requestBody.temperature = 28.0;
                requestBody.last_action = "Monitoring";
            }

            const headers = { 'Content-Type': 'application/json' };
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }

            const response = await fetch(VOICE_API, {
                method: 'POST',
                headers: headers,
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) {
                if (response.status === 429) {
                    throw new Error('Rate limit exceeded. Please wait a moment.');
                }
                throw new Error(`API error: ${response.status}`);
            }

            const data = await response.json();
            
            // Display answer
            showAnswer(data.answer);
            
            // Display sensor data context
            if (data.context_used) {
                showSensorData(data.context_used);
            }
            
            // Speak answer
            speakText(data.answer);
            
            updateStatus('Click microphone to ask another question');
            
        } catch (error) {
            console.error('Voice query error:', error);
            showAnswer(`Sorry, ${error.message}`);
            updateStatus('Error occurred. Click to try again.');
        } finally {
            isProcessing = false;
            updateButtonState();
        }
    }

    // Speak Text using TTS
    function speakText(text) {
        speechSynthesis.cancel();
        
        const utterance = new SpeechSynthesisUtterance(text);
        const lang = document.getElementById('voice-language').value;
        utterance.lang = lang;
        utterance.rate = 0.9;
        utterance.pitch = 1.0;
        
        utterance.onstart = () => {
            updateStatus('🔊 Speaking...', 'processing');
        };
        
        utterance.onend = () => {
            updateStatus('Click microphone to ask another question');
        };
        
        speechSynthesis.speak(utterance);
    }

    // Update Status
    function updateStatus(text, className = '') {
        const statusEl = document.getElementById('voice-status');
        statusEl.textContent = text;
        statusEl.className = 'voice-assistant-status ' + className;
    }

    // Show Transcript
    function showTranscript(text) {
        const transcriptEl = document.getElementById('voice-transcript');
        document.getElementById('transcript-text').textContent = text;
        transcriptEl.style.display = 'block';
    }

    // Show Answer
    function showAnswer(text) {
        const answerEl = document.getElementById('voice-answer');
        document.getElementById('answer-text').textContent = text;
        answerEl.style.display = 'block';
    }

    // Show Sensor Data
    function showSensorData(context) {
        const dataEl = document.getElementById('voice-data');
        const parts = [];
        
        if (context.moisture !== undefined) parts.push(`Moisture: ${context.moisture}%`);
        if (context.ph !== undefined) parts.push(`pH: ${context.ph}`);
        if (context.ec !== undefined) parts.push(`EC: ${context.ec} dS/m`);
        if (context.temperature !== undefined) parts.push(`Temp: ${context.temperature}°C`);
        
        if (parts.length > 0) {
            document.getElementById('data-text').textContent = parts.join(' | ');
            dataEl.style.display = 'block';
        }
    }

    // Update Button State
    function updateButtonState() {
        const btn = document.getElementById('voice-assistant-btn');
        btn.className = 'voice-assistant-floating-btn';
        
        if (isListening) {
            btn.classList.add('listening');
            btn.querySelector('i').className = 'fas fa-microphone';
        } else if (isProcessing) {
            btn.classList.add('processing');
            btn.querySelector('i').className = 'fas fa-spinner';
        } else {
            btn.querySelector('i').className = 'fas fa-microphone';
        }
    }

    // Start Listening
    function startListening() {
        if (!recognition) {
            alert('Speech recognition not supported in this browser. Please use Chrome.');
            return;
        }

        isListening = true;
        updateButtonState();
        updateStatus('🎤 Listening... Speak now!', 'listening');
        
        // Clear previous results
        document.getElementById('voice-transcript').style.display = 'none';
        document.getElementById('voice-answer').style.display = 'none';
        document.getElementById('voice-data').style.display = 'none';
        
        try {
            recognition.start();
        } catch (e) {
            console.error('Recognition start error:', e);
            isListening = false;
            updateButtonState();
            updateStatus('Error starting microphone');
        }
    }

    // Stop Listening
    function stopListening() {
        isListening = false;
        updateButtonState();
        if (recognition) {
            try {
                recognition.stop();
            } catch (e) {
                console.error('Recognition stop error:', e);
            }
        }
    }

    // Initialize Widget
    function init() {
        // Check if widget already exists
        if (document.getElementById('voice-assistant-widget')) {
            return;
        }

        // Create widget
        createWidget();

        // Get elements
        const btn = document.getElementById('voice-assistant-btn');
        const dialog = document.getElementById('voice-assistant-dialog');
        const closeBtn = document.getElementById('voice-assistant-close');
        const langSelect = document.getElementById('voice-language');

        // Button click handler
        btn.addEventListener('click', () => {
            if (isProcessing) return;
            
            // Toggle dialog
            if (!dialog.classList.contains('show')) {
                dialog.classList.add('show');
                // Fetch latest data when opening
                fetchLatestSensorData();
            }
            
            if (isListening) {
                stopListening();
            } else {
                startListening();
            }
        });

        // Close button
        closeBtn.addEventListener('click', () => {
            dialog.classList.remove('show');
            if (isListening) stopListening();
        });

        // Language change
        langSelect.addEventListener('change', (e) => {
            if (recognition) {
                recognition.lang = e.target.value;
            }
        });

        // Setup speech recognition handlers
        if (recognition) {
            recognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                console.log('Transcript:', transcript);
                
                showTranscript(transcript);
                processVoiceQuery(transcript);
            };

            recognition.onerror = (event) => {
                console.error('Recognition error:', event.error);
                isListening = false;
                updateButtonState();
                
                let errorMsg = 'Microphone error';
                switch (event.error) {
                    case 'no-speech':
                        errorMsg = 'No speech detected. Please try again.';
                        break;
                    case 'not-allowed':
                        errorMsg = 'Microphone permission denied';
                        break;
                    case 'network':
                        errorMsg = 'Network error';
                        break;
                }
                
                updateStatus(errorMsg);
            };

            recognition.onend = () => {
                if (isListening && !isProcessing) {
                    isListening = false;
                    updateButtonState();
                    updateStatus('Processing...');
                }
            };
        }

        console.log('✅ Voice Assistant Widget initialized');
    }

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Export for manual initialization if needed
    window.VoiceAssistant = {
        init: init,
        fetchSensorData: fetchLatestSensorData
    };

})();
