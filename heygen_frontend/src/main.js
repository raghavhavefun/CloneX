import './style.css'
import { LiveAvatarSession } from "@heygen/liveavatar-web-sdk";

const AVATAR_ID = "6991a8bd878f406c91cd452d1d745158";
const API_KEY = "sk_V2_hgu_ksnqWDIEUPd_xL9awSaJidIjxtLdBq13qBn8p9U4bi6z";

let session = null;

document.querySelector('#app').innerHTML = `
  <h1>Project Aria Live Avatar</h1>
  <p>Status: <span id="statusText">Disconnected</span></p>
  
  <div class="avatar-container">
    <video id="avatarVideo" autoplay playsinline></video>
  </div>

  <div class="controls">
    <button id="startBtn">Start Avatar</button>
    <button id="stopBtn" disabled>Stop Avatar</button>
  </div>

  <div class="input-container">
    <input type="text" id="textInput" placeholder="Type something for the avatar to say..." disabled />
    <button id="speakBtn" disabled>Speak</button>
  </div>
`;

const videoElement = document.getElementById('avatarVideo');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const textInput = document.getElementById('textInput');
const speakBtn = document.getElementById('speakBtn');
const statusText = document.getElementById('statusText');

async function getAccessToken() {
    const res = await fetch("https://api.liveavatar.com/v1/sessions/create-session-token", {
        method: "POST",
        headers: { 
            "X-Api-Key": API_KEY,
            "Content-Type": "application/json"
        }
    });
    const data = await res.json();
    if (!res.ok || data.error || !data.data) {
        throw new Error(JSON.stringify(data));
    }
    // Depending on the new API, it might just return data.data.session_token
    return data.data.token || data.data.session_token || data.data; 
}

async function startAvatar() {
    try {
        statusText.innerText = "Initializing...";
        startBtn.disabled = true;

        const token = await getAccessToken();
        let sessionToken = typeof token === 'string' ? token : token.token;
        
        session = new LiveAvatarSession(sessionToken, {
            avatarId: AVATAR_ID,
            videoElement: videoElement, // Many modern SDKs take the video element directly
        });

        // The SDK might bind the video stream automatically if we pass the videoElement in config or attach it later.
        // We'll also just try to start it.
        await session.start();

        statusText.innerText = "Connected";
        
        stopBtn.disabled = false;
        textInput.disabled = false;
        speakBtn.disabled = false;

        // If video needs manual attachment:
        if (session.mediaStream) {
            videoElement.srcObject = session.mediaStream;
        }

    } catch (error) {
        console.error("Error starting avatar:", error);
        statusText.innerText = `Error: ${error.message || error}`;
        startBtn.disabled = false;
    }
}

async function stopAvatar() {
    if (!session) return;
    
    try {
        await session.stop();
        videoElement.srcObject = null;
        statusText.innerText = "Disconnected";
        resetUI();
    } catch (error) {
        console.error("Error stopping avatar:", error);
    }
}

async function speak() {
    if (!session) return;
    
    const text = textInput.value.trim();
    if (!text) return;

    try {
        speakBtn.disabled = true;
        // The new SDK usually has a speak or send message method.
        if (session.speak) {
            await session.speak(text);
        } else if (session.sendText) {
            await session.sendText(text);
        } else if (session.speakText) {
            await session.speakText(text);
        } else {
           console.warn("Speak method not found on session object", session);
        }
        textInput.value = '';
    } catch (error) {
        console.error("Error making avatar speak:", error);
    } finally {
        speakBtn.disabled = false;
    }
}

function resetUI() {
    startBtn.disabled = false;
    stopBtn.disabled = true;
    textInput.disabled = true;
    speakBtn.disabled = true;
    session = null;
}

startBtn.addEventListener('click', startAvatar);
stopBtn.addEventListener('click', stopAvatar);
speakBtn.addEventListener('click', speak);
textInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') speak();
});
