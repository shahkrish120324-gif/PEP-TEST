# app.py
import streamlit as st
import requests
import os
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ================= CONFIG =================
API_BASE = os.environ.get("API_BASE", "http://localhost:8000")
REALTIME_HUB = os.environ.get("REALTIME_HUB", "http://127.0.0.1:9000")
TENANT_NUMBER = os.environ.get("TENANT_NUMBER", "+16148193454")
REFRESH_INTERVAL = 2

st.set_page_config(
    page_title="Patient Communication Portal",
    layout="centered",
)

# ================= STYLES =================
st.markdown("""
<style>
body {
    background-color: #F8F9FA;
}
.chat-wrapper {
    max-width: 800px;
    margin: auto;
}
.chat-bubble {
    padding: 12px 16px;
    border-radius: 14px;
    margin-bottom: 10px;
    max-width: 75%;
    font-size: 15px;
    color: #000;
}
.patient {
    background-color: #DCF8C6;
    margin-left: auto;
}
.tenant {
    background-color: #FFFFFF;
    border: 1px solid #DDD;
    margin-right: auto;
}
.timestamp {
    font-size: 11px;
    color: #666;
    margin-top: 4px;
}
input {
    font-size: 16px !important;
}
</style>
""", unsafe_allow_html=True)

# ================= HELPERS =================
def fetch_realtime_messages(patient_phone: str):
    r = requests.get(
        f"{REALTIME_HUB}/messages/by-phone",
        params={"patientPhone": patient_phone},
        timeout=5,
    )
    r.raise_for_status()
    return r.json()["messages"]

def send_message_to_tenant(patient_phone: str, message: str):
    payload = {
        "From": patient_phone,
        "To": TENANT_NUMBER,
        "Body": message,
    }
    r = requests.post(
        f"{API_BASE}/message/send-test-patient",
        data=payload,
        timeout=10,
    )
    r.raise_for_status()

# ================= SESSION =================
if "patient_phone" not in st.session_state:
    st.session_state.patient_phone = ""
if "messages" not in st.session_state:
    st.session_state.messages = []
if "draft" not in st.session_state:
    st.session_state.draft = ""

# ================= HEADER =================
st.markdown("<h2 style='text-align:center;'>Patient Messaging</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center;color:#666;'>Secure real-time communication</p>", unsafe_allow_html=True)

# ================= TABS =================
tab_chat, tab_info = st.tabs(["💬 Chat", "ℹ️ About"])

# ================= CHAT TAB =================
with tab_chat:
    st.markdown("### Patient Phone")

    phone_input = st.text_input(
        "Enter patient phone number",
        placeholder="+16144683607",
        value=st.session_state.patient_phone,
    )

    # Auto-load when phone changes
    if phone_input and phone_input != st.session_state.patient_phone:
        st.session_state.patient_phone = phone_input
        st.session_state.messages = []

    if not st.session_state.patient_phone:
        st.info("Enter a patient phone number to start chatting.")
        st.stop()

    # -------- REALTIME FETCH --------
    try:
        incoming = fetch_realtime_messages(st.session_state.patient_phone)

        existing_keys = {
            (m["createdAt"], m["message"])
            for m in st.session_state.messages
        }

        for msg in incoming:
            key = (msg.get("timestamp"), msg.get("message"))
            if key not in existing_keys:
                st.session_state.messages.append({
                    "createdAt": msg.get("timestamp"),
                    "sender": "tenant",
                    "message": msg.get("message"),
                })
    except Exception:
        pass

    # -------- CHAT VIEW --------
    st.markdown("<div class='chat-wrapper'>", unsafe_allow_html=True)

    for m in sorted(st.session_state.messages, key=lambda x: x["createdAt"] or ""):
        css_class = "patient" if m["sender"] == "patient" else "tenant"
        ts = m["createdAt"]
        ts_fmt = ""
        if ts:
            ts_fmt = datetime.fromisoformat(ts.replace("Z", "")).strftime("%I:%M %p")

        st.markdown(f"""
        <div class="chat-bubble {css_class}">
            {m["message"]}
            <div class="timestamp">{ts_fmt}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # -------- MESSAGE COMPOSER --------
    st.markdown("---")
    col1, col2 = st.columns([6, 1])

    with col1:
        st.session_state.draft = st.text_input(
            "Message",
            value=st.session_state.draft,
            label_visibility="collapsed",
            placeholder="Type a message…",
        )

    with col2:
        if st.button("Send"):
            if st.session_state.draft.strip():
                send_message_to_tenant(
                    st.session_state.patient_phone,
                    st.session_state.draft,
                )
                st.session_state.messages.append({
                    "createdAt": datetime.utcnow().isoformat(),
                    "sender": "patient",
                    "message": st.session_state.draft,
                })
                st.session_state.draft = ""

# ================= ABOUT TAB =================
with tab_info:
    st.markdown("""
    ### Patient Communication Portal

    - Real-time patient ↔ tenant messaging  
    - Powered by FastAPI, n8n, and Twilio  
    - Designed for healthcare engagement  

    This interface demonstrates live two-way communication.
    """)

# ================= AUTO REFRESH =================
st_autorefresh(
    interval=2000,  # milliseconds
    key="chat_refresh"
)