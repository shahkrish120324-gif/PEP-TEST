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

REFRESH_INTERVAL_MS = 2000  # 2 seconds
SEND_TIMEOUT = 15  # seconds for POST / send
# LOAD_TIMEOUT = 20

st.set_page_config(page_title="Patient Messaging Console", layout="wide")

# ---------------- COMPACT STYLES ----------------
BASE_CSS = """
<style>
:root { --bg: #ffffff; --muted: #6b7280; --tenant-bg:#f3f4f6; --patient-bg:#0f172a; }
body { font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial; }
.container { max-width: 980px; margin: 10px auto; }
.header { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:8px; }
.title { font-size:18px; font-weight:700; color:#111827; }
.note { color:var(--muted); font-size:12px; }
.chat-window {
  background: var(--bg);
  border-radius: 10px;
  padding: 10px;
  height: 520px;
  overflow-y: auto;
  border: 1px solid #e6e6e6;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
.row { display:flex; gap:8px; margin-bottom:6px; align-items:flex-end; }
.row.patient { justify-content:flex-end; }
.avatar { width:30px; height:30px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; font-weight:700; color:#fff; font-size:12px; flex: 0 0 30px; }
.avatar.tenant { background:#9CA3AF; color:#111827; }
.avatar.patient { background:#111827; }
.bubble {
  padding:8px 10px;
  border-radius:8px;
  max-width:72%;
  font-size:13px;
  line-height:1.25;
  word-break:break-word;
  white-space:pre-wrap;
}
.bubble.tenant { background:var(--tenant-bg); color:#111827; border-bottom-left-radius:4px; }
.bubble.patient { background:var(--patient-bg); color:#fff; border-bottom-right-radius:4px; }
.meta { font-size:11px; color:var(--muted); margin-top:4px; display:flex; gap:8px; align-items:center; }
.status-dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
.status-sending { background:#f59e0b; }
.status-sent { background:#10b981; }
.status-failed { background:#ef4444; }
.empty { text-align:center; color:#9ca3af; padding:28px 0; }
.footer { margin-top:8px; display:flex; gap:8px; align-items:center; }
.input { flex:1; }
.send-btn { background:#0f172a; color:white; border:none; padding:8px 12px; border-radius:8px; cursor:pointer; }
.small { font-size:12px; color:var(--muted); }
.placeholder-card {
  max-width: 980px;
  margin: 24px auto;
  padding: 28px;
  border-radius: 12px;
  border: 1px dashed #e5e7eb;
  color: #6b7280;
  text-align: center;
}
</style>
"""

# ---------------- HELPERS & STATE ----------------
if "patient_phone" not in st.session_state:
    st.session_state.patient_phone = ""

if "loaded_phone" not in st.session_state:
    st.session_state.loaded_phone = None

if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_start_ts" not in st.session_state:
    st.session_state.session_start_ts = datetime.now(timezone.utc)
# ensure outgoing_text exists before any widget uses that key
if "outgoing_text" not in st.session_state:
    st.session_state.outgoing_text = ""

@st.cache_data(show_spinner=False)
def load_past_messages(phone: str) -> List[Dict[str, Any]]:
    try:
        resp = requests.get(f"{API_BASE}/chat/by-phone", params={"patientPhone": phone}, timeout=LOAD_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("chats", [])
    except Exception:
        # On failure return empty list (calling code may show UI feedback)
        return []

def get_realtime_messages(phone: str) -> List[Dict[str, Any]]:
    try:
        resp = requests.get(f"{REALTIME_HUB}/messages/by-phone", params={"patientPhone": phone}, timeout=5)
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
        try:
            body = resp.json()
        except Exception:
            body = {"status_code": resp.status_code}
        return {"ok": True, "resp": body, "error": None}
    except requests.exceptions.ReadTimeout:
        return {"ok": False, "resp": None, "error": "Request timed out"}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "resp": None, "error": str(e)}

def is_patient_msg(m: Dict[str, Any]) -> bool:
    ct = (m.get("chatType") or "").lower()
    return ct in ("patient", "inbound", "sms", "user", "from_patient", "user_from_patient")

def normalize_realtime_msg(msg: Dict[str, Any]) -> Dict[str, Any]:
    ts = msg.get("timestamp") or msg.get("createdAt") or datetime.now(timezone.utc).isoformat()
    text = msg.get("message") or msg.get("body") or ""
    from_field = (msg.get("from") or msg.get("source") or "").lower()
    chat_type = "patient" if ("+" in from_field or "patient" in from_field or msg.get("direction", "").lower().startswith("inbound")) else "tenant"
    return {"createdAt": ts, "chatType": chat_type, "message": text}

def format_time(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%b %d • %H:%M")
    except Exception:
        return ts

def render_chat_iframe(messages: List[Dict[str, Any]], iframe_height: int = 520):
    rows = []
    for msg in sorted(messages, key=lambda x: x.get("createdAt", "")):
        print("All Messages",msg)
        patient = is_patient_msg(msg)
        role = "patient" if patient else "tenant"
        msg_text = html_lib.escape(msg.get("message", "") or "")
        timestamp = format_time(str(msg.get("createdAt", "") or ""))
        status = msg.get("status", "")
        status_dot = ""
        if status:
            cls = "status-sending" if status == "sending" else "status-sent" if status == "sent" else "status-failed"
            status_dot = f'<span class="status-dot {cls}" title="{status}"></span>'
        left_avatar = f"<div class='avatar tenant'>T</div>" if not patient else ""
        right_avatar = f"<div class='avatar patient'>P</div>" if patient else ""
        bubble = f"""
        <div class="row {role}">
          {left_avatar}
          <div>
            <div class="bubble {role}">{msg_text}</div>
            <div class="meta"><span class="small">{timestamp}</span> {status_dot}</div>
          </div>
          {right_avatar}
        </div>
        """
        rows.append(bubble)

    inner = "\n".join(rows) if rows else '<div class="empty">No messages yet — start the conversation</div>'

    # Add a script that reliably scrolls the chat-window to bottom on load and whenever content changes.
    # The MutationObserver ensures auto-scroll for new messages appended after the iframe has loaded.
    full = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      {BASE_CSS}
    </head>
    <body>
      <div class="container">
        <div class="header">
          <div class="title">Patient Messaging</div>
        </div>
        <div id="chat-window" class="chat-window">
          {inner}
        </div>
      </div>

      <script>
        (function() {{
          var chat = document.getElementById('chat-window');

          function scrollToBottom() {{
            try {{
              if (chat) {{
                chat.scrollTop = chat.scrollHeight;
              }}
            }} catch (e) {{ /* ignore */ }}
          }}

          // Scroll after a short delay on load to let layout settle
          window.addEventListener('load', function() {{
            setTimeout(scrollToBottom, 30);
            setTimeout(scrollToBottom, 150); // a second attempt in case images/fonts change layout
          }});

          // Also run on DOMContentLoaded (some environments fire this instead of load)
          document.addEventListener('DOMContentLoaded', function() {{
            setTimeout(scrollToBottom, 20);
          }});

          // MutationObserver: whenever children/characterData change, scroll to bottom.
          if (window.MutationObserver && chat) {{
            var mo = new MutationObserver(function(muts) {{
              // small timeout to allow rendering
              setTimeout(scrollToBottom, 20);
            }});
            mo.observe(chat, {{ childList: true, subtree: true, characterData: true }});
          }}

          // Expose a simple message-based trigger: parent can postMessage('scroll-to-bottom')
          window.addEventListener('message', function(ev) {{
            if (ev && ev.data === 'scroll-to-bottom') {{
              setTimeout(scrollToBottom, 10);
            }}
          }});
        }})();
      </script>
    </body>
    </html>
    """
    # Allow the iframe itself to scroll (scrolling=True). The iframe's internal script scrolls the chat-window automatically.
    components_html(full, height=iframe_height, scrolling=True)

# ---------------- UI ----------------
st.title("💬 Patient Messaging Console")
st.caption("Realtime patient ↔ tenant messaging")

# Phone input — chat will load only after a non-empty phone is entered
phone = st.text_input("Patient phone number", placeholder="+16144683607", value=st.session_state.patient_phone)

# Load past messages only when a phone number is provided and it's different from what's loaded
if phone and phone != st.session_state.loaded_phone:
    with st.spinner("Loading conversation…"):
        # st.session_state.messages = []
        st.session_state.loaded_phone = phone
        st.session_state.patient_phone = phone
        st.session_state.messages = []
        st.session_state.session_start_ts = datetime.now(timezone.utc)

# If no phone has been loaded yet, show a simple placeholder and skip rendering chat + send form
if not st.session_state.loaded_phone:
    st.markdown(f"<div class='placeholder-card'>Enter a patient phone number above to load the conversation.</div>", unsafe_allow_html=True)
else:
    # ---------------- REALTIME POLLING ----------------
    realtime = get_realtime_messages(st.session_state.patient_phone)
    existing = {(m.get("createdAt"), (m.get("message") or "").strip()) for m in st.session_state.messages}
    for msg in realtime:
        normalized = normalize_realtime_msg(msg)
        key = (normalized.get("createdAt"), (normalized.get("message") or "").strip())
        if key not in existing:
            st.session_state.messages.append(normalized)

    # ---------------- CHAT VIEW ----------------
    num_messages = len(st.session_state.messages)
    iframe_height = min(700, max(360, 240 + num_messages * 26))
    render_chat_iframe(st.session_state.messages, iframe_height=iframe_height)

    # ---------------- SEND MESSAGE ----------------
    st.markdown("---")
    with st.form("send-message", clear_on_submit=True):
        # outgoing_text widget key matches session_state key; no manual modification of session_state after widget is created
        outgoing = st.text_area("Type your message", height=80, max_chars=1600, key="outgoing_text")
        submit = st.form_submit_button("Send")
        if submit:
            text = (outgoing or "").strip()
            if not text:
                st.warning("Please type a message before sending.")
            elif not st.session_state.patient_phone:
                st.warning("Please enter a patient phone number first.")
            else:
                # Add local 'sending' message to show immediately
                tmp_id = f"tmp-{len(st.session_state.messages)+1}-{datetime.now(timezone.utc).timestamp()}"
                tmp_msg = {
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "chatType": "patient",
                    "message": text,
                    "status": "sending",
                    "id": tmp_id,
                }
                st.session_state.messages.append(tmp_msg)

                # Call API and update status
                result = send_message_api(st.session_state.patient_phone, text)
                if result["ok"]:
                    for m in reversed(st.session_state.messages):
                        if m.get("id") == tmp_id:
                            m["status"] = "sent"
                            server_ts = None
                            if isinstance(result["resp"], dict):
                                server_ts = result["resp"].get("timestamp") or result["resp"].get("createdAt") or result["resp"].get("sentAt")
                            if server_ts:
                                m["createdAt"] = server_ts
                            break
                else:
                    for m in reversed(st.session_state.messages):
                        if m.get("id") == tmp_id:
                            m["status"] = "failed"
                            break
                    st.error(f"Failed to send message: {result['error']}")

                # Nudge iframe to re-scroll (posting a message that iframe listens to)
                st.markdown(
                    """
                    <script>
                    (function() {
                      try {
                        var iframes = window.document.querySelectorAll('iframe');
                        iframes.forEach(function(f) {
                          try { f.contentWindow.postMessage('scroll-to-bottom', '*'); } catch(e) {}
                        });
                      } catch(e) {}
                    })();
                    </script>
                    """,
                    unsafe_allow_html=True,
                )

# ---------------- AUTO REFRESH ----------------
if st.session_state.loaded_phone:
    st_autorefresh(interval=REFRESH_INTERVAL_MS, key="chat-refresh")