import streamlit as st
import requests
import os
import html as html_lib
from typing import List, Dict, Any
from streamlit_autorefresh import st_autorefresh
from streamlit.components.v1 import html as components_html
from datetime import datetime

# ---------------- CONFIG ----------------
API_BASE = os.environ.get("API_BASE", "http://localhost:8000")
REALTIME_HUB = os.environ.get("REALTIME_HUB", "http://127.0.0.1:9000")
TENANT_NUMBER = os.environ.get("TENANT_NUMBER", "+16148193454")

REFRESH_INTERVAL_MS = 2000  # 2 seconds
# ---------------------------------------

st.set_page_config(page_title="Patient Messaging Console", layout="wide")

# ---------------- COMPACT STYLES ----------------
# Compact bubble layout with small fonts, avatars, inline timestamp + status,
# and a scrollable fixed-height chat window that auto-scrolls to bottom.
BASE_CSS = """
<style>
.chat-wrapper {
  max-width: 940px;
  margin: 8px auto;
  font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
}
.header {
  display:flex;
  align-items:center;
  justify-content:space-between;
  margin-bottom:8px;
}
.meta {
  color: #374151;
  font-weight:600;
}
.chat-window {
  background: #ffffff;
  border-radius: 12px;
  padding: 10px;
  height: 520px;
  overflow-y: auto;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  border: 1px solid #e6e6e6;
}
.message-row {
  display:flex;
  align-items:flex-end;
  gap:8px;
  margin-bottom:6px;
}
.message-row.patient {
  justify-content:flex-end;
}
.bubble {
  display:inline-block;
  padding:8px 10px;
  border-radius:10px;
  max-width: 72%;
  font-size: 13px;
  line-height: 1.25;
  word-wrap: break-word;
  white-space: pre-wrap;
}
.bubble.patient {
  background: #0f172a;
  color: #f8fafc;
  border-bottom-right-radius: 4px;
}
.bubble.tenant {
  background: #f3f4f6;
  color: #111827;
  border-bottom-left-radius: 4px;
}
.meta-line {
  font-size: 11px;
  color: #6b7280;
  margin-top:4px;
  display:flex;
  gap:8px;
  align-items:center;
}
.avatar {
  width:30px;
  height:30px;
  border-radius:50%;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  font-weight:700;
  color: white;
  font-size:12px;
}
.avatar.patient { background:#111827; }
.avatar.tenant { background:#9CA3AF; color:#111827; }
.status-dot {
  width:8px;
  height:8px;
  border-radius:50%;
}
.status-sending { background:#f59e0b; }
.status-sent { background:#10b981; }
.status-failed { background:#ef4444; }
.empty-state {
  color:#9ca3af;
  text-align:center;
  padding:40px 0;
}
.small-note { font-size:12px; color:#6b7280; }
</style>
"""

# ---------------- HELPERS ----------------
@st.cache_data(show_spinner=False)
def load_past_messages(phone: str) -> List[Dict[str, Any]]:
    resp = requests.get(f"{API_BASE}/chat/by-phone", params={"patientPhone": phone}, timeout=20)
    resp.raise_for_status()
    return resp.json().get("chats", [])

def get_realtime_messages(phone: str) -> List[Dict[str, Any]]:
    resp = requests.get(f"{REALTIME_HUB}/messages/by-phone", params={"patientPhone": phone}, timeout=5)
    resp.raise_for_status()
    return resp.json().get("messages", [])

def post_send_message(from_phone: str, text: str) -> Dict[str, Any]:
    resp = requests.post(
        f"{API_BASE}/message/send-test-patient",
        data={"From": from_phone, "To": TENANT_NUMBER, "Body": text},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()

def is_patient_msg(m: Dict[str, Any]) -> bool:
    # Accept a broader set of chatType values that represent patient/inbound messages,
    # including 'user' which in some parts of your code was used for realtime.
    ct = (m.get("chatType") or "").lower()
    return ct in ("patient", "inbound", "sms", "user", "user_from_patient", "from_patient")

def normalize_realtime_msg(msg: Dict[str, Any]) -> Dict[str, Any]:
    # Map realtime payload into the chat message dict shape used by the UI
    # Expected realtime fields: timestamp, message, maybe direction/source
    ts = msg.get("timestamp") or msg.get("createdAt") or datetime.utcnow().isoformat()
    text = msg.get("message") or msg.get("body") or ""
    # Determine chatType heuristically
    direction = msg.get("direction") or msg.get("source") or msg.get("fromType") or ""
    chat_type = "patient" if "inbound" in direction.lower() or "patient" in direction.lower() or msg.get("from") else "tenant"
    return {"createdAt": ts, "chatType": chat_type, "message": text}

def format_time(ts: str) -> str:
    # keep simple: if isoformat, show HH:MM, else return raw
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%b %d • %H:%M")
    except Exception:
        return ts

def render_chat_iframe(messages: List[Dict[str, Any]], iframe_height: int = 520):
    # Build compact HTML for the chat window. Auto-scrolls to bottom on each render.
    msgs_html = []
    for msg in sorted(messages, key=lambda x: x.get("createdAt", "")):
        patient = is_patient_msg(msg)
        role = "patient" if patient else "tenant"
        msg_text = html_lib.escape(msg.get("message", "") or "")
        timestamp = format_time(str(msg.get("createdAt", "") or ""))
        status = msg.get("status", "")  # sending, sent, failed or empty
        status_dot = ""
        if status:
            cls = "status-sending" if status == "sending" else "status-sent" if status == "sent" else "status-failed"
            status_dot = f'<span class="status-dot {cls}" title="{status}"></span>'
        avatar_label = "P" if patient else "T"
        bubble = f"""
        <div class="message-row {role}">
          {"<div class='avatar " + role + "'>" + avatar_label + "</div>" if not patient else ""}
          <div>
            <div class="bubble {role}">{msg_text}</div>
            <div class="meta-line"><span class="small-note">{timestamp}</span> {status_dot}</div>
          </div>
          {"<div class='avatar patient'>P</div>" if patient else ""}
        </div>
        """
        msgs_html.append(bubble)

    inner = "\n".join(msgs_html) if msgs_html else '<div class="empty-state">No messages yet — start the conversation</div>'

    full = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      {BASE_CSS}
    </head>
    <body>
      <div class="chat-wrapper">
        <div class="header">
          <div class="meta">Patient Messaging</div>
          <div class="small-note">Auto-updates every {REFRESH_INTERVAL_MS // 1000}s</div>
        </div>
        <div id="chat-window" class="chat-window">
          {inner}
        </div>
      </div>

      <script>
        // scroll to bottom on load
        (function() {{
          var c = document.getElementById('chat-window');
          if (c) {{
            c.scrollTop = c.scrollHeight;
          }}
        }})();
      </script>
    </body>
    </html>
    """
    components_html(full, height=iframe_height, scrolling=True)

# ---------------- SESSION STATE ----------------
if "patient_phone" not in st.session_state:
    st.session_state.patient_phone = ""

if "loaded_phone" not in st.session_state:
    st.session_state.loaded_phone = None

# messages is a list of dicts with keys: createdAt, chatType, message, (optional) status, id
if "messages" not in st.session_state:
    st.session_state.messages = []

# ---------------- HEADER ----------------
st.markdown("<div style='display:flex;gap:12px;align-items:center'>", unsafe_allow_html=True)
st.title("💬 Patient Messaging Console")
st.markdown("</div>", unsafe_allow_html=True)
st.caption("Compact, fast, and clear — newest messages are in view automatically.")

# ---------------- PHONE INPUT ----------------
col1, col2 = st.columns([3, 1])
with col1:
    phone = st.text_input("Patient phone number", placeholder="+16144683607", value=st.session_state.patient_phone)
    

# ---------------- LOAD PAST CHATS ----------------
if phone and phone != st.session_state.loaded_phone:
    with st.spinner("Loading conversation…"):
        try:
            st.session_state.messages = load_past_messages(phone)
        except Exception as e:
            st.error(f"Failed to load messages: {e}")
            st.session_state.messages = []
        st.session_state.loaded_phone = phone
        st.session_state.patient_phone = phone

# ---------------- REALTIME POLLING ----------------
if st.session_state.patient_phone:
    try:
        realtime = get_realtime_messages(st.session_state.patient_phone)
        existing = {(m.get("createdAt"), (m.get("message") or "").strip()) for m in st.session_state.messages}
        for msg in realtime:
            normalized = normalize_realtime_msg(msg)
            key = (normalized.get("createdAt"), (normalized.get("message") or "").strip())
            if key not in existing:
                # classify as patient if appropriate (normalize_realtime_msg already sets chatType)
                st.session_state.messages.append(normalized)
    except requests.exceptions.Timeout:
        # keep smooth UI
        pass
    except Exception as e:
        # don't spam user but log minimal
        st.session_state._last_realtime_error = str(e)

# ---------------- CHAT VIEW (compact, auto-scroll) ----------------
# Calculate a reasonable height based on messages but keep compact
num_messages = len(st.session_state.messages)
iframe_height = min(700, max(360, 260 + num_messages * 28))
render_chat_iframe(st.session_state.messages, iframe_height=iframe_height)

# ---------------- SEND MESSAGE ----------------
st.markdown("---")
with st.form("send-message", clear_on_submit=True):
    outgoing = st.text_area("Type your message", height=80, max_chars=1600, key="outgoing_text")
    cols = st.columns([1, 4, 1])
    with cols[0]:
        send_btn = st.form_submit_button("Send")
    with cols[1]:
        st.write("")  # spacing
    with cols[2]:
        if st.form_submit_button("Clear"):
            st.session_state["outgoing_text"] = ""
            st.experimental_rerun()

    if send_btn:
        text = (outgoing or "").strip()
        if not text:
            st.warning("Please type a message before sending.")
        elif not st.session_state.patient_phone:
            st.warning("Please enter and load a patient phone number first.")
        else:
            # Add a local 'sending' message so UI reflects it immediately
            tmp = {
                "createdAt": datetime.utcnow().isoformat(),
                "chatType": "patient",
                "message": text,
                "status": "sending",
                "id": f"tmp-{len(st.session_state.messages)+1}"
            }
            st.session_state.messages.append(tmp)

            # Try to send and update status accordingly
            try:
                resp = post_send_message(st.session_state.patient_phone, text)
                # mark last appended message as sent and replace timestamp if API returned one
                for m in reversed(st.session_state.messages):
                    if m.get("id", "").startswith("tmp-") and m.get("status") == "sending":
                        m["status"] = "sent"
                        if isinstance(resp, dict):
                            # try to update timestamp/message from response
                            maybe_ts = resp.get("timestamp") or resp.get("createdAt") or resp.get("sentAt")
                            if maybe_ts:
                                m["createdAt"] = maybe_ts
                        break
                # optionally append any server-echo message fields
            except Exception as e:
                # mark sending message as failed
                for m in reversed(st.session_state.messages):
                    if m.get("id", "").startswith("tmp-") and m.get("status") == "sending":
                        m["status"] = "failed"
                        break
                st.error(f"Failed to send message: {e}")

            # Rerun so iframe will re-render and scroll to bottom
            st.experimental_rerun()

# ---------------- AUTO REFRESH ----------------
if st.session_state.patient_phone:
    # Put autorefresh near the end so everything re-renders cleanly
    st_autorefresh(interval=REFRESH_INTERVAL_MS, key="chat-refresh")