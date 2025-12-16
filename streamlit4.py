import streamlit as st
import requests
import os
from typing import Dict, Any
from streamlit_autorefresh import st_autorefresh
# ---------------- CONFIG ----------------
API_BASE = os.environ.get("API_BASE", "http://localhost:8000")
REALTIME_HUB = os.environ.get("REALTIME_HUB", "http://127.0.0.1:9000")
TENANT_NUMBER = os.environ.get("TENANT_NUMBER", "+16148193454")

REFRESH_INTERVAL_MS = 2000  # 2 seconds
# ---------------------------------------

st.set_page_config(
    page_title="Patient Messaging Console",
    layout="wide",
)

# ---------------- STYLES ----------------
st.markdown("""
<style>
.chat-container {
    max-width: 900px;
    margin: auto;
}
.msg {
    padding: 10px 14px;
    border-radius: 12px;
    margin-bottom: 8px;
    max-width: 70%;
    line-height: 1.4;
}
.patient {
    background-color: #1f2937;
    color: #f9fafb;
    margin-left: auto;
}
.tenant {
    background-color: #e5e7eb;
    color: #111827;
    margin-right: auto;
}
.timestamp {
    font-size: 11px;
    opacity: 0.6;
}
</style>
""", unsafe_allow_html=True)


# ---------------- HELPERS ----------------
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

# ---------------- SESSION STATE ----------------
if "patient_phone" not in st.session_state:
    st.session_state.patient_phone = ""

if "loaded_phone" not in st.session_state:
    st.session_state.loaded_phone = None

if "messages" not in st.session_state:
    st.session_state.messages = []

# ---------------- HEADER ----------------
st.title("💬 Patient Messaging Console")
st.caption("Realtime patient ↔ tenant messaging")

# ---------------- PHONE INPUT ----------------
phone = st.text_input(
    "Patient phone number",
    placeholder="+16144683607",
    value=st.session_state.patient_phone,
)

# ---------------- LOAD PAST CHATS ----------------
if phone and phone != st.session_state.loaded_phone:
    with st.spinner("Loading conversation…"):
        st.session_state.messages = load_past_messages(phone)
        st.session_state.loaded_phone = phone
        st.session_state.patient_phone = phone

# ---------------- REALTIME POLLING ----------------
if st.session_state.patient_phone:
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
                    "chatType": "user",
                    "message": msg.get("message"),
                })

    except requests.exceptions.Timeout:
        pass  # silent fail keeps UI smooth

# ---------------- CHAT VIEW ----------------
st.markdown("<div class='chat-container'>", unsafe_allow_html=True)

for msg in sorted(st.session_state.messages, key=lambda x: x.get("createdAt", "")):
    is_patient = msg.get("chatType") in ("patient", "inbound", "sms")

    role_class = "patient" if is_patient else "tenant"
    direction = "Patient" if is_patient else "Tenant"

    st.markdown(
        f"""
        <div class="msg {role_class}">
            <div>{msg.get("message", "")}</div>
            <div class="timestamp">{direction} · {msg.get("createdAt","")}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown("</div>", unsafe_allow_html=True)

# ---------------- SEND MESSAGE ----------------
st.markdown("---")

with st.form("send-message", clear_on_submit=True):
    text = st.text_area("Send message", height=80)
    sent = st.form_submit_button("Send")

    if sent and text.strip() and st.session_state.patient_phone:
        send_message(st.session_state.patient_phone, text)
        st.session_state.messages.append({
            "createdAt": "just now",
            "chatType": "patient",
            "message": text,
        })

# ---------------- AUTO REFRESH ----------------
if st.session_state.patient_phone:
    st_autorefresh(interval=REFRESH_INTERVAL_MS, key="chat-refresh")
