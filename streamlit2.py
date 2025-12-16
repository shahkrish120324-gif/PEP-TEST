# app.py
import streamlit as st
import requests
import os
import time
from datetime import datetime

# ---------------- CONFIG ----------------
API_BASE = os.environ.get("API_BASE", "http://localhost:8000")
REALTIME_HUB = os.environ.get("REALTIME_HUB", "http://127.0.0.1:9000")
DEFAULT_TENANT_NUMBER = os.environ.get("TENANT_NUMBER", "+16148193454")
REFRESH_INTERVAL = 2

st.set_page_config(
    page_title="Patient Chat",
    layout="centered",
)

# ---------------- STYLES ----------------
st.markdown("""
<style>
.chat-container {
    max-width: 720px;
    margin: auto;
}
.chat-bubble {
    padding: 10px 14px;
    border-radius: 12px;
    margin: 6px 0;
    max-width: 75%;
    line-height: 1.4;
}
.patient {
    background-color: #DCF8C6;
    margin-left: auto;
    text-align: right;
}
.tenant {
    background-color: #F1F0F0;
    margin-right: auto;
}
.timestamp {
    font-size: 11px;
    color: #666;
}
input, textarea {
    font-size: 16px !important;
}
</style>
""", unsafe_allow_html=True)

# ---------------- HELPERS ----------------
def get_realtime_messages(patient_phone: str):
    r = requests.get(
        f"{REALTIME_HUB}/messages/by-phone",
        params={"patientPhone": patient_phone},
        timeout=5,
    )
    r.raise_for_status()
    return r.json()["messages"]

def send_patient_message(patient_phone: str, message: str):
    payload = {
        "From": patient_phone,
        "To": DEFAULT_TENANT_NUMBER,
        "Body": message,
    }
    r = requests.post(
        f"{API_BASE}/message/send-test-patient",
        data=payload,
        timeout=10,
    )
    r.raise_for_status()
    return r.json()

# ---------------- SESSION ----------------
if "patient_phone" not in st.session_state:
    st.session_state.patient_phone = ""
if "messages" not in st.session_state:
    st.session_state.messages = []
if "draft" not in st.session_state:
    st.session_state.draft = ""

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("## Patient Login")
    phone = st.text_input("Patient Phone Number", placeholder="+16144683607")
    if st.button("Open Chat"):
        st.session_state.patient_phone = phone
        st.session_state.messages = []
        st.success("Chat loaded")

# ---------------- HEADER ----------------
st.markdown(
    f"<h2 style='text-align:center;'>Patient Messaging</h2>",
    unsafe_allow_html=True,
)

if not st.session_state.patient_phone:
    st.info("Please enter patient phone number to view chat.")
    st.stop()

# ---------------- REALTIME FETCH ----------------
try:
    realtime = get_realtime_messages(st.session_state.patient_phone)

    existing = {
        (m.get("createdAt"), m.get("message"))
        for m in st.session_state.messages
    }

    for msg in realtime:
        key = (msg.get("timestamp"), msg.get("message"))
        if key not in existing:
            st.session_state.messages.append({
                "createdAt": msg.get("timestamp"),
                "sender": "tenant",
                "message": msg.get("message"),
            })
except Exception:
    pass

# ---------------- CHAT VIEW ----------------
st.markdown("<div class='chat-container'>", unsafe_allow_html=True)

for m in sorted(st.session_state.messages, key=lambda x: x["createdAt"] or ""):
    sender_class = "patient" if m["sender"] == "patient" else "tenant"
    ts = m["createdAt"]
    if ts:
        ts = datetime.fromisoformat(ts.replace("Z", "")).strftime("%I:%M %p")

    st.markdown(f"""
    <div class="chat-bubble {sender_class}">
        {m["message"]}
        <div class="timestamp">{ts or ""}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# ---------------- COMPOSER ----------------
st.markdown("---")
col1, col2 = st.columns([5, 1])

with col1:
    st.session_state.draft = st.text_input(
        "Type your message",
        value=st.session_state.draft,
        label_visibility="collapsed",
        placeholder="Type a message…",
    )

with col2:
    if st.button("Send"):
        if st.session_state.draft.strip():
            send_patient_message(
                st.session_state.patient_phone,
                st.session_state.draft,
            )
            st.session_state.messages.append({
                "createdAt": datetime.utcnow().isoformat(),
                "sender": "patient",
                "message": st.session_state.draft,
            })
            st.session_state.draft = ""

# ---------------- AUTO REFRESH ----------------
time.sleep(REFRESH_INTERVAL)
st.rerun()
