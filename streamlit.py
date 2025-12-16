# app.py
import streamlit as st
import requests
import os
from typing import Any, Dict, List
import time
API_BASE = os.environ.get("API_BASE", "http://localhost:8000")
DEFAULT_TENANT_NUMBER = os.environ.get("TENANT_NUMBER", "+16148193454")
REALTIME_HUB = os.environ.get("REALTIME_HUB", "http://127.0.0.1:9000")
REFRESH_INTERVAL = 2
st.set_page_config(page_title="Patient Dashboard Chat", layout="wide")

st.title("Patient Dashboard Chat")
st.caption("Load conversations by patient phone. (UI posts to your backend HTTP endpoints)")

# Optional: allow user to provide an auth token if backend requires it
token = st.sidebar
headers: Dict[str, str] = {}
if token:
    headers["Authorization"] = f"Bearer {token}"

# Sidebar: patient phone and tenant number
with st.sidebar:
    st.markdown("## Controls")
    patient_phone = st.text_input("Patient phone (e.g. +16144683607)", value=st.session_state.get("patient_phone", ""))
    tenant_number = st.text_input("Tenant phone (tenant recipient)", value=os.environ.get("TENANT_NUMBER", DEFAULT_TENANT_NUMBER))
    if st.button("Save / Set phones"):
        st.session_state["patient_phone"] = patient_phone
        st.session_state["tenant_number"] = tenant_number
        st.success("Saved phones in session")

# Helper HTTP functions (talk to your backend)
def get_chats_by_phone(patientPhone: str, headers: Dict[str, str]) -> Dict[str, Any]:
    resp = requests.get(
        f"{API_BASE}/chat/by-phone",
        params={"patientPhone": patientPhone},
        timeout=10,
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json()

def api_send_test_message(form: dict, headers: dict, files=None):
    url = f"{API_BASE}/message/send-test-patient"
    if files:
        resp = requests.post(url, data=form, headers=headers, files=files, timeout=30)
    else:
        resp = requests.post(url, data=form, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()
def get_realtime_messages(patient_phone: str):
    resp = requests.get(
        f"{REALTIME_HUB}/messages/by-phone",
        params={"patientPhone": patient_phone},
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json()["messages"]

# Session-state defaults
if "chats" not in st.session_state:
    st.session_state.chats = []
if "draft" not in st.session_state:
    st.session_state.draft = ""
if "patient_phone" not in st.session_state:
    st.session_state.patient_phone = patient_phone or ""
if "tenant_number" not in st.session_state:
    st.session_state.tenant_number = tenant_number or DEFAULT_TENANT_NUMBER

if st.session_state.patient_phone:
    try:
        realtime_msgs = get_realtime_messages(st.session_state.patient_phone)

        # Build a deduplication set from existing messages
        existing_keys = {
            (m.get("createdAt"), m.get("message"))
            for m in st.session_state.chats
        }

        for msg in realtime_msgs:
            key = (msg.get("timestamp"), msg.get("message"))
            if key not in existing_keys:
                st.session_state.chats.append({
                    "createdAt": msg.get("timestamp"),
                    "chatType": "user",   # tenant → patient
                    "message": msg.get("message"),
                    "chatStatus": "delivered",
                })
    except Exception:
        # Fail silently so UI never breaks
        pass
# Main UI
col1, col2 = st.columns([3, 1])
with col1:
    input_phone = st.text_input("Patient phone to load (or use saved)", value=st.session_state.patient_phone)
with col2:
    if st.button("Load conversation"):
        if not input_phone.strip():
            st.warning("Please enter a patient phone to load.")
        else:
            st.session_state.patient_phone = input_phone.strip()
            try:
                with st.spinner("Loading chats from backend..."):
                    data = get_chats_by_phone(st.session_state.patient_phone, headers)
                chats = data.get("chats") if isinstance(data, dict) else data
                st.session_state.chats = chats or []
                st.success(f"Loaded {len(st.session_state.chats)} messages")
            except requests.HTTPError as e:
                st.error(f"HTTP error when loading chats: {e}")
                try:
                    st.json(e.response.json())
                except Exception:
                    pass
            except Exception as e:
                st.error(f"Error loading chats: {e}")

st.markdown("---")

# Show conversation or message
if not st.session_state.chats:
    st.info("No messages loaded. Use the Patient phone field and click 'Load conversation'.")
else:
    st.markdown("### Conversation")
    # sort by createdAt if present
    chats_to_show = st.session_state.chats
    if isinstance(chats_to_show, list):
        try:
            chats_to_show = sorted(chats_to_show, key=lambda x: x.get("createdAt", ""))
        except Exception:
            pass
        for c in chats_to_show:
            chat_type = c.get("chatType") or c.get("type") or c.get("direction") or ""
            # interpret user/chatType mapping sensibly
            if chat_type == "user":
                direction = "Tenant → Patient"
            elif chat_type in ("patient", "inbound", "sms"):
                direction = "Patient → Tenant"
            else:
                direction = "Unknown"
            created = c.get("createdAt", "")
            message = c.get("message") or c.get("messageText") or c.get("text") or ""
            status = c.get("chatStatus") or c.get("status") or ""
            st.markdown(f"**{created}** — {direction}")
            st.markdown(message)
            if status:
                st.caption(f"status: `{status}`")
            st.markdown("---")

# Composer area
st.markdown("### Send message (simulate patient → tenant)")
st.session_state.draft = st.text_area("Message text", value=st.session_state.draft, height=140)

col_send_left, col_send_right = st.columns([1, 3])
with col_send_right:
    if st.button("Send message"):
        if not st.session_state.draft.strip():
            st.warning("Please enter a message to send.")
        elif not st.session_state.patient_phone:
            st.warning("Set the patient phone first (use Save / Set phones or Load conversation).")
        else:
            try:
                with st.spinner("Sending message to backend..."):
                    form = {
                        "From": st.session_state.patient_phone,
                        "To": st.session_state.tenant_number or DEFAULT_TENANT_NUMBER,
                        "Body": st.session_state.draft,
                    }
                    resp = api_send_test_message(form, headers=headers)
                    # optimistic UI append
                    st.session_state.chats.append({
                        "createdAt": "just now",
                        "chatType": "patient",
                        "message": st.session_state.draft,
                        "chatStatus": "sent"
                    })
                    st.session_state.draft = ""
                st.success("Message sent (patient → tenant)")
                st.write("Server response:")
                st.json(resp)
            except requests.HTTPError as e:
                st.error(f"HTTP error when sending message: {e}")
                try:
                    st.json(e.response.json())
                except Exception:
                    pass
            except Exception as e:
                st.error(f"Failed to send message: {e}")

with col_send_left:
    if st.button("Refresh conversation"):
        if not st.session_state.patient_phone:
            st.warning("No patient phone set to refresh.")
        else:
            try:
                with st.spinner("Refreshing..."):
                    data = get_chats_by_phone(st.session_state.patient_phone, headers)
                st.session_state.chats = data.get("chats") if isinstance(data, dict) else data or []
                st.success("Refreshed conversation")
            except Exception as e:
                st.error(f"Refresh failed: {e}")

# Helpful tips
st.caption("Tips: Set API_BASE env var to point to your backend. If your backend requires auth, paste a bearer token in the left sidebar.")
if st.session_state.patient_phone:
    time.sleep(REFRESH_INTERVAL)
    st.rerun()
