# -*- coding: utf-8 -*-
"""
阿里云百炼 智能体应用(Agent 1.0) - Streamlit 调用网页
支持: 多轮对话 / 流式输出 / 图片(截图)上传 / 知识库检索
---------------------------------------------------
官方接口(华北2·北京地域):
    POST https://dashscope.aliyuncs.com/api/v1/apps/{APP_ID}/completion
多轮对话: 使用 input.messages, 此时不传 prompt 与 session_id
图片/文件: input.image_list(图片 URL 或 Base64 Data URL) / input.file_list(文件 URL)

运行:
    streamlit run bailian_agent_app.py
"""
from __future__ import annotations

import base64
import io
import json
import mimetypes
import os
import time

import requests
import streamlit as st

try:  # 图片压缩用，非必需
    from PIL import Image
except Exception:
    Image = None

ALLOWED_IMG = ["jpg", "jpeg", "png", "webp", "bmp", "gif"]
MAX_UPLOAD_MB = 9          # 单图上限(Base64 编码前)
MAX_DATAURL_MB = 9         # Data URL 字符串上限
MAX_LONG_EDGE = 1568       # 超过则等比压缩长边

DEFAULT_APP_ID = os.getenv("BAILIAN_APP_ID", "")
API_TEMPLATE = "https://dashscope.aliyuncs.com/api/v1/apps/{}/completion"

try:  # 支持 .streamlit/secrets.toml
    SECRET_APP_ID = st.secrets.get("BAILIAN_APP_ID", DEFAULT_APP_ID)
    SECRET_KEY = st.secrets.get("DASHSCOPE_API_KEY", "")
except Exception:
    SECRET_APP_ID, SECRET_KEY = DEFAULT_APP_ID, ""

st.set_page_config(page_title="百炼智能体 · 本地调用", page_icon="🤖", layout="centered")
st.title("🤖 阿里云百炼智能体（Agent 1.0）")
st.caption("本地 Streamlit 网页 · 支持多轮对话、流式输出与截图上传")

# =============== 侧栏 ===============
with st.sidebar:
    st.header("⚙️ 连接配置")
    app_id = st.text_input("应用 APP_ID", value=SECRET_APP_ID, placeholder="应用卡片上获取")
    api_key = st.text_input("API Key", value=SECRET_KEY or os.getenv("DASHSCOPE_API_KEY", ""),
                            type="password", placeholder="sk-xxxxxx")
    use_rag = st.checkbox("挂载知识库 rag_options", value=False)
    rag_pipeline_ids = ""
    if use_rag:
        rag_pipeline_ids = st.text_input("pipeline_ids（逗号分隔）", placeholder="知识库 ID")
    stream_out = st.checkbox("流式输出 stream", value=True)
    use_file_list = st.checkbox("把图片也放进 file_list（文件解析）", value=False,
                                help="部分应用开启了文件解析能力时可勾选")

    st.divider()
    if st.button("🗑️ 清空对话", use_container_width=True):
        st.session_state.pop("messages", None)
        st.session_state.pop("pending_images", None)
        st.rerun()

    st.markdown(
        "**图片要能看懂的前提**\n"
        "应用需在配置页选用**支持视觉理解的模型**（如 qwen-vl-max、qwen3.x-plus 多模态版），\n"
        "纯 qwen-plus 不支持读图。"
    )

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_images" not in st.session_state:
    st.session_state.pending_images = []

# =============== 图片处理 ===============
def to_data_url(raw: bytes, name: str) -> tuple[str, dict]:
    """把上传的字节转成可传给百炼的 Data URL，必要时自动压缩"""
    mime = mimetypes.guess_type(name)[0] or "image/png"
    data_url = "data:{};base64,{}".format(mime, base64.b64encode(raw).decode())
    info = {"name": name, "kb": len(raw) // 1024, "compressed": False}

    need = (len(raw) > MAX_UPLOAD_MB * 1024 * 1024
            or len(data_url) > MAX_DATAURL_MB * 1024 * 1024)
    if need and Image is not None:
        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGB") if mime == "image/jpeg" else img
        w, h = img.size
        scale = min(1.0, MAX_LONG_EDGE / max(w, h))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)))
        buf = io.BytesIO()
        img.save(buf, format="JPEG" if mime == "image/jpeg" else "PNG", optimize=True)
        raw = buf.getvalue()
        data_url = "data:{};base64,{}".format(mime, base64.b64encode(raw).decode())
        info.update(kb=len(raw) // 1024, compressed=True)
    return data_url, info


# =============== 附件区 ===============
with st.expander("📎 上传图片 / 截图（可选）", expanded=False):
    uploads = st.file_uploader(
        "支持 JPG/PNG/WEBP/BMP/GIF，可多选；大图会自动压缩后再上传",
        type=ALLOWED_IMG, accept_multiple_files=True, key="uploader",
    )
    if uploads:
        st.session_state.pending_images = []
        for f in uploads:
            url, meta = to_data_url(f.getvalue(), f.name)
            st.session_state.pending_images.append({"url": url, "name": f.name, "info": meta})
    if st.session_state.pending_images:
        cols = st.columns(min(4, len(st.session_state.pending_images)))
        for c, it in zip(cols, st.session_state.pending_images):
            with c:
                st.image(it["url"], caption="{} · {}KB{}".format(
                    it["name"], it["info"]["kb"], " ·已压缩" if it["info"]["compressed"] else ""),
                    use_container_width=True)
        if st.button("❌ 移除附件"):
            st.session_state.pending_images = []
            st.rerun()

# =============== 必填校验 ===============
if not app_id or not api_key:
    st.info("👈 请在左侧填入 **APP_ID** 和 **API Key** 后开始对话。", icon="ℹ️")
    st.stop()

API_URL = API_TEMPLATE.format(app_id)


def build_headers() -> dict:
    h = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if stream_out:
        h["X-DashScope-SSE"] = "enable"   # HTTP 流式必需请求头
    return h


def build_payload(question: str, history: list[dict], images: list[dict]) -> dict:
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": question})

    inp = {"messages": messages}
    parameters: dict = {}
    if stream_out:
        parameters["incremental_output"] = True

    if images:                                   # 图片走 image_list
        inp["image_list"] = [it["url"] for it in images]
        if use_file_list:
            inp["file_list"] = [it["url"] for it in images]

    if use_rag and rag_pipeline_ids.strip():
        parameters["rag_options"] = {
            "pipeline_ids": [p.strip() for p in rag_pipeline_ids.split(",") if p.strip()],
            "metadata_filter": None,
        }
    return {"input": inp, "parameters": parameters, "stream": stream_out}


def call_non_stream(payload: dict) -> str:
    r = requests.post(API_URL, headers=build_headers(), data=json.dumps(payload), timeout=180)
    if r.status_code != 200:
        _raise_api_error(r)
    return r.json().get("output", {}).get("text", "（返回内容为空）")


def call_stream(payload: dict, holder) -> str:
    full = ""
    with requests.post(API_URL, headers=build_headers(), data=json.dumps(payload),
                       stream=True, timeout=(10, 180)) as r:
        if r.status_code != 200:
            _raise_api_error(r)
        for raw in r.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            chunk = raw[5:].strip()
            if not chunk or chunk == "[DONE]":
                continue
            try:
                js = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if js.get("code") and js.get("code") != "Success":
                raise RuntimeError(f"{js.get('code')}: {js.get('message')}")
            text = js.get("output", {}).get("text", "")
            if text:
                full = text if text.startswith(full) else full + text   # 累积 / 增量自适应
                holder.markdown(full + "▌")
    holder.markdown(full or "（返回内容为空）")
    return full


def _raise_api_error(r: requests.Response):
    body = {}
    try:
        body = r.json()
    except Exception:
        pass
    req_id = r.headers.get("request_id") or body.get("request_id", "-")
    raise RuntimeError(
        f"HTTP {r.status_code} | request_id={req_id} | "
        f"code={body.get('code', '-')} | message={body.get('message', r.text[:200])}"
    )


# =============== 渲染历史 ===============
for m in st.session_state.messages:
    with st.chat_message("user" if m["role"] == "user" else "assistant"):
        if m.get("images"):
            cols = st.columns(min(4, len(m["images"])))
            for c, u in zip(cols, m["images"]):
                c.image(u, use_container_width=True)
        st.markdown(m["content"])

# =============== 对话 ===============
if q := st.chat_input("输入问题，回车发送…（可先在上方上传截图）"):
    imgs = st.session_state.pending_images
    img_urls = [it["url"] for it in imgs]

    st.session_state.messages.append({"role": "user", "content": q, "images": img_urls})
    with st.chat_message("user"):
        if img_urls:
            cols = st.columns(min(4, len(img_urls)))
            for c, u in zip(cols, img_urls):
                c.image(u, use_container_width=True)
        st.markdown(q)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        t0 = time.time()
        try:
            payload = build_payload(q, st.session_state.messages[:-1], imgs)
            if stream_out:
                answer = call_stream(payload, placeholder)
            else:
                with st.spinner("智能体思考中…"):
                    answer = call_non_stream(payload)
                placeholder.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
            st.session_state.pending_images = []       # 发送后清空附件
            st.caption(f"耗时 {time.time() - t0:.1f}s")
        except requests.exceptions.RequestException as e:
            st.error(f"网络请求失败：{e}")
        except Exception as e:
            st.error(f"调用失败：{e}")
