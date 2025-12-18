from datetime import datetime, timezone
import requests
import os
import html as html_lib
from typing import List, Dict, Any
from streamlit_autorefresh import st_autorefresh
import streamlit as st
from streamlit.components.v1 import html as components_html

# ---------------- CONFIG ----------------
API_BASE = os.environ.get("API_BASE", "http://localhost:8000")
REALTIME_HUB = os.environ.get("REALTIME_HUB", "http://127.0.0.1:9000")
TENANT_NUMBER = os.environ.get("TENANT_NUMBER", "+16148193454")

REFRESH_INTERVAL_MS = 2000
SEND_TIMEOUT = 15

st.set_page_config(page_title="Patient Messaging Console", layout="wide")

# ---------------- SESSION INIT ----------------
if "patient_phone" not in st.session_state:
    st.session_state.patient_phone = ""

if "loaded_phone" not in st.session_state:
    st.session_state.loaded_phone = None

if "messages" not in st.session_state:
    st.session_state.messages = []

# 🔑 Used to ignore old realtime messages
if "session_start_ts" not in st.session_state:
    st.session_state.session_start_ts = datetime.now(timezone.utc)

if "outgoing_text" not in st.session_state:
    st.session_state.outgoing_text = ""

# ---------------- STYLES ----------------
BASE_CSS = """
<style>
:root { --tenant-bg:#f3f4f6; --patient-bg:#0f172a; }
.chat-window { height:520px; overflow-y:auto; border:1px solid #e6e6e6; padding:10px; border-radius:10px; }
.row { display:flex; gap:8px; margin-bottom:6px; }
.row.patient { justify-content:flex-end; }
.avatar { width:30px; height:30px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:700; }
.avatar.tenant { background:#9CA3AF; }
.avatar.patient { background:#0f172a; color:white; }
.bubble { padding:8px 10px; border-radius:8px; max-width:72%; }
.bubble.tenant { background:var(--tenant-bg); }
.bubble.patient { background:var(--patient-bg); color:white; }
.empty { text-align:center; color:#9ca3af; padding:28px; }
</style>
"""

# ---------------- HELPERS ----------------
def get_realtime_messages(phone: str) -> List[Dict[str, Any]]:
    try:
        resp = requests.get(
            f"{REALTIME_HUB}/messages/by-phone",
            params={"patientPhone": phone},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json().get("messages", [])
    except Exception:
        return []

def send_message_api(from_phone: str, text: str) -> Dict[str, Any]:
    try:
        resp = requests.post(
            f"{API_BASE}/message/send-test-patient-2",
            data={"From": from_phone, "To": TENANT_NUMBER, "Body": text},
            timeout=SEND_TIMEOUT,
        )
        resp.raise_for_status()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def normalize_realtime_msg(msg: Dict[str, Any]) -> Dict[str, Any]:
    ts = msg.get("timestamp") or msg.get("createdAt")
    if not ts:
        return {}

    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))

    # 🔑 IGNORE OLD REALTIME MESSAGES
    if dt < st.session_state.session_start_ts:
        return {}

    return {
        "createdAt": ts,
        "chatType": "tenant",
        "message": msg.get("message") or msg.get("body") or "",
    }

def render_chat(messages: List[Dict[str, Any]]):
    rows = []
    for m in messages:
        role = m["chatType"]
        bubble = html_lib.escape(m["message"])
        rows.append(
            f"""
            <div class="row {role}">
                {'' if role == 'patient' else '<div class="avatar tenant">T</div>'}
                <div class="bubble {role}">{bubble}</div>
                {'' if role == 'tenant' else '<div class="avatar patient">P</div>'}
            </div>
            """
        )

    inner = "\n".join(rows) if rows else '<div class="empty">No messages</div>'

    components_html(
        f"""
        <html>
        <head>{BASE_CSS}</head>
        <body>
            <div class="chat-window">{inner}</div>
        </body>
        </html>
        """,
        height=560,
        scrolling=True,
    )

# ---------------- UI ----------------
st.title("💬 Patient Messaging Console")
st.caption("Temporary testing UI (no history)")

phone = st.text_input("Patient phone number", placeholder="+16144683607")

# 🔑 RESET EVERYTHING when phone changes or reload
if phone and phone != st.session_state.loaded_phone:
    st.session_state.loaded_phone = phone
    st.session_state.patient_phone = phone
    st.session_state.messages = []
    st.session_state.session_start_ts = datetime.now(timezone.utc)

if not st.session_state.loaded_phone:
    st.info("Enter a patient phone number to start testing.")
    st.stop()

# ---------------- REALTIME ----------------
realtime = get_realtime_messages(st.session_state.patient_phone)

existing = {(m["createdAt"], m["message"]) for m in st.session_state.messages}

for msg in realtime:
    normalized = normalize_realtime_msg(msg)
    if not normalized:
        continue

    key = (normalized["createdAt"], normalized["message"])
    if key not in existing:
        st.session_state.messages.append(normalized)

render_chat(st.session_state.messages)

# ---------------- SEND ----------------
with st.form("send"):
    text = st.text_area("Send as patient", height=80)
    if st.form_submit_button("Send"):
        if text.strip():
            st.session_state.messages.append(
                {
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "chatType": "patient",
                    "message": text.strip(),
                }
            )
            send_message_api(st.session_state.patient_phone, text.strip())

# ---------------- AUTO REFRESH ----------------
st_autorefresh(interval=REFRESH_INTERVAL_MS, key="refresh")
