import streamlit as st
import requests
import os
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ================== CONFIG ==================
API_BASE = os.environ.get("API_BASE", "http://localhost:8000")
REALTIME_HUB = os.environ.get("REALTIME_HUB", "http://127.0.0.1:9000")
TENANT_NUMBER = os.environ.get("TENANT_NUMBER", "+16148193454")

REFRESH_INTERVAL_MS = 2000  # 2 seconds
# ============================================

st.set_page_config(
    page_title="Patient Messaging Console",
    layout="wide",
)

# ================== WHATSAPP-STYLE CSS ==================
st.markdown("""
<style>
/* Chat container styling */
.chat-container {
    height: 65vh !important;
    overflow-y: auto !important;
    padding: 20px !important;
    background: linear-gradient(to bottom, #f0f2f5 0%, #e5e5e5 100%) !important;
    border-radius: 12px !important;
    margin-bottom: 20px !important;
}

/* Message bubbles - WhatsApp style */
.stChatMessage {
    margin-bottom: 12px !important;
    padding: 0 !important;
}

.stChatMessage > div {
    padding: 12px 16px !important;
    border-radius: 18px !important;
    max-width: 75% !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.1) !important;
    line-height: 1.4 !important;
    word-wrap: break-word !important;
}

/* Patient messages (right side, blue) */
.stChatMessage[data-testid="column"]:has(.patient) .stMarkdown {
    background: linear-gradient(135deg, #25d366, #128c7e) !important;
    color: white !important;
    margin-left: auto !important;
    border-bottom-right-radius: 4px !important;
}

/* Tenant messages (left side, light gray) */
.stChatMessage[data-testid="column"]:has(.tenant) .stMarkdown {
    background: #ffffff !important;
    color: #111827 !important;
    margin-right: auto !important;
    border-bottom-left-radius: 4px !important;
}

/* Timestamps */
.stCaption {
    font-size: 11px !important;
    opacity: 0.7 !important;
    margin-top: 4px !important;
    text-align: right !important;
}

/* Chat input styling */
.stChatInput input {
    border-radius: 25px !important;
    border: 1px solid #ddd !important;
}
</style>
""", unsafe_allow_html=True)

# ================== HELPERS ==================
@st.cache_data(show_spinner=False)
def load_past_messages(phone: str):
    """Load historical messages ONCE per phone"""
    resp = requests.get(
        f"{API_BASE}/chat/by-phone",
        params={"patientPhone": phone},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("chats", [])

def get_realtime_messages(phone: str):
    """Poll realtime hub (n8n → FastAPI)"""
    resp = requests.get(
        f"{REALTIME_HUB}/messages/by-phone",
        params={"patientPhone": phone},
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json().get("messages", [])

def send_message(from_phone: str, text: str):
    """Send patient → tenant"""
    resp = requests.post(
        f"{API_BASE}/message/send-test-patient",
        data={
            "From": from_phone,
            "To": TENANT_NUMBER,
            "Body": text,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()

# ================== SESSION STATE ==================
if "patient_phone" not in st.session_state:
    st.session_state.patient_phone = ""

if "loaded_phone" not in st.session_state:
    st.session_state.loaded_phone = None

if "messages" not in st.session_state:
    st.session_state.messages = []

# ================== HEADER ==================
st.title("💬 Patient Messaging Console")
st.caption("Realtime patient ↔ tenant messaging (WhatsApp-style)")

# ================== PHONE INPUT ==================
phone = st.text_input(
    "Patient phone number",
    placeholder="+16144683607",
    value=st.session_state.patient_phone,
)

# ================== LOAD PAST CONVERSATION ==================
if phone and phone != st.session_state.loaded_phone:
    with st.spinner("Loading conversation…"):
        st.session_state.messages = load_past_messages(phone)
        st.session_state.loaded_phone = phone
        st.session_state.patient_phone = phone

# ================== REALTIME POLLING ==================
if st.session_state.patient_phone:
    try:
        realtime = get_realtime_messages(st.session_state.patient_phone)

        # Deduplicate using message + direction
        existing = {
            (m.get("message"), m.get("chatType"))
            for m in st.session_state.messages
        }

        for msg in realtime:
            key = (msg.get("message"), "user")
            if key not in existing:
                st.session_state.messages.append({
                    "id": msg.get("chatId"),
                    "createdAt": msg.get("timestamp"),
                    "chatType": "user",  # tenant → patient
                    "message": msg.get("message"),
                    "source": "realtime",
                })
    except requests.exceptions.Timeout:
        pass  # silent fail keeps UI smooth

# ================== WHATSAPP CHAT VIEW ==================
if st.session_state.patient_phone and st.session_state.messages:
    # Sort messages by timestamp
    sorted_messages = sorted(st.session_state.messages, key=lambda x: x.get("createdAt", ""))
    
    # WhatsApp-style scrollable chat container
    chat_container = st.container(height=600)
    with chat_container:
        for msg in sorted_messages:
            is_patient = msg.get("chatType") in ("patient", "inbound", "sms", "user")
            role = "patient" if is_patient else "tenant"
            label = "Patient" if is_patient else "Tenant"
            
            with st.chat_message(role):
                # Add CSS class for styling
                st.markdown(
                    f'<div class="{role}">{msg.get("message", "")}</div>',
                    unsafe_allow_html=True
                )
                st.caption(f"{label} · {msg.get("createdAt", "just now")}")
    
    # WhatsApp-style input at bottom (ALWAYS VISIBLE)
    if prompt := st.chat_input("Type a message...", key="chat_input_main"):
        # Optimistic UI update FIRST
        st.session_state.messages.append({
            "id": f"ui-{int(time.time()*1000)}",
            "createdAt": datetime.now().strftime("%H:%M"),
            "chatType": "tenant",  # tenant → patient
            "message": prompt,
            "source": "ui",
        })
        
        # Send message
        send_message(st.session_state.patient_phone, prompt)
        st.rerun()

# ================== AUTO-SCROLL TO BOTTOM ==================
st.markdown("""
<script>
    // Auto-scroll chat to bottom on every rerun
    function autoScrollChat() {
        const containers = parent.document.querySelectorAll('.stContainer');
        containers.forEach(container => {
            const chatMessages = container.querySelectorAll('.stChatMessage');
            if (chatMessages.length > 0) {
                container.scrollTop = container.scrollHeight;
            }
        });
    }
    autoScrollChat();
    
    // Scroll on new messages
    const observer = new MutationObserver(autoScrollChat);
    observer.observe(document.body, { childList: true, subtree: true });
</script>
""", unsafe_allow_html=True)

# ================== AUTO REFRESH ==================
if st.session_state.patient_phone:
    st_autorefresh(interval=REFRESH_INTERVAL_MS, key="chat-refresh")
