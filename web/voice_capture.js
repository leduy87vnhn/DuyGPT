const state = {
  busy: false,
  recording: false,
  mediaRecorder: null,
  chunks: [],
  mimeType: "",
};

const parentOrigin = new URLSearchParams(window.location.search).get("parent") || "*";

const els = {
  record: document.querySelector("#record"),
  status: document.querySelector("#status"),
};

function notifyParent(message) {
  if (window.opener && !window.opener.closed) {
    window.opener.postMessage(message, parentOrigin);
  }
}

function setStatus(message, isError = false) {
  els.status.textContent = message;
  els.status.classList.toggle("error", isError);
  notifyParent({ type: "duygpt:user-info-status", status: message, error: isError });
}

function setBusy(value) {
  state.busy = value;
  els.record.disabled = value && !state.recording;
}

function setRecording(value) {
  state.recording = value;
  els.record.classList.toggle("recording", value);
  els.record.querySelector("span").textContent = value ? "Dừng ghi âm" : "Bắt đầu ghi âm";
  els.record.setAttribute("aria-label", value ? "Dừng ghi âm" : "Bắt đầu ghi âm");
}

function supportedAudioType() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

function audioExtension(mimeType) {
  if (mimeType.includes("ogg")) return "ogg";
  if (mimeType.includes("webm")) return "webm";
  return "wav";
}

function readBlobAsBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",", 2)[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

async function startRecording() {
  setStatus("");
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    setStatus("Trình duyệt này chưa hỗ trợ ghi âm trực tiếp.", true);
    return;
  }
  if (!window.isSecureContext) {
    setStatus("Popup ghi âm phải được mở bằng HTTPS.", true);
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.mimeType = supportedAudioType();
    state.chunks = [];
    state.mediaRecorder = new MediaRecorder(stream, state.mimeType ? { mimeType: state.mimeType } : undefined);
    state.mediaRecorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) state.chunks.push(event.data);
    });
    state.mediaRecorder.addEventListener("stop", () => {
      stream.getTracks().forEach((track) => track.stop());
      processRecording();
    });
    state.mediaRecorder.start();
    setRecording(true);
    setStatus("Đang ghi âm...");
  } catch (error) {
    setRecording(false);
    setStatus(error.message || "Không mở được micro.", true);
  }
}

function stopRecording() {
  if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
    state.mediaRecorder.stop();
  }
  setRecording(false);
  setStatus("Đang nhận dạng và tách thông tin...");
}

async function processRecording() {
  if (!state.chunks.length) {
    setStatus("Không có âm thanh để xử lý.", true);
    return;
  }

  setBusy(true);
  try {
    const blob = new Blob(state.chunks, { type: state.mimeType || state.chunks[0].type || "audio/webm" });
    const audioBase64 = await readBlobAsBase64(blob);
    const transcribeResponse = await fetch("/api/voice/transcribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        audio_base64: audioBase64,
        filename: `user-info.${audioExtension(blob.type)}`,
      }),
    });
    const transcribed = await transcribeResponse.json();
    if (!transcribeResponse.ok) throw new Error(transcribed.error || "Không nhận dạng được giọng nói.");
    const text = transcribed.text || "";
    if (!text) throw new Error("Không nhận ra nội dung nói.");

    const parseResponse = await fetch("/api/user-info/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const parsed = await parseResponse.json();
    if (!parseResponse.ok) throw new Error(parsed.error || "Không tách được thông tin.");
    notifyParent({ type: "duygpt:user-info-result", text, fields: parsed.fields || {} });
    setStatus("Đã gửi dữ liệu về trang nhập liệu.");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    state.chunks = [];
    state.mediaRecorder = null;
    setBusy(false);
  }
}

els.record.addEventListener("click", () => {
  if (state.busy && !state.recording) return;
  if (state.recording) {
    stopRecording();
  } else {
    startRecording();
  }
});
