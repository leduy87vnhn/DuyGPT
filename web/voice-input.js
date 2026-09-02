(() => {
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

  window.attachVoiceInput = function attachVoiceInput({ button, textarea, status, onBusyChange }) {
    const state = { recording: false, mediaRecorder: null, audioChunks: [], audioMimeType: "" };

    function setVoiceStatus(message, isError = false) {
      if (!status) return;
      status.textContent = message;
      status.classList.toggle("error", isError);
    }

    function appendPromptText(text) {
      const cleaned = text.trim();
      if (!cleaned) return;
      const current = textarea.value.trim();
      textarea.value = current ? `${current}\n${cleaned}` : cleaned;
      textarea.dispatchEvent(new Event("input"));
      textarea.focus();
    }

    function setRecording(value) {
      state.recording = value;
      button.classList.toggle("recording", value);
      button.setAttribute("aria-label", value ? "Stop recording" : "Start recording");
      button.title = value ? "Stop recording" : "Start recording";
    }

    async function startRecording() {
      setVoiceStatus("");
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
        setVoiceStatus("Trình duyệt này chưa hỗ trợ ghi âm trực tiếp.", true);
        return;
      }
      if (!window.isSecureContext) {
        setVoiceStatus("Trình duyệt đang chặn micro trên HTTP. Dùng localhost hoặc mở trang bằng HTTPS.", true);
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        state.audioMimeType = supportedAudioType();
        state.audioChunks = [];
        state.mediaRecorder = new MediaRecorder(
          stream,
          state.audioMimeType ? { mimeType: state.audioMimeType } : undefined
        );

        state.mediaRecorder.addEventListener("dataavailable", (event) => {
          if (event.data.size > 0) state.audioChunks.push(event.data);
        });

        state.mediaRecorder.addEventListener("stop", () => {
          stream.getTracks().forEach((track) => track.stop());
          transcribeRecording();
        });

        state.mediaRecorder.start();
        setRecording(true);
        setVoiceStatus("Đang ghi âm...");
      } catch (error) {
        setRecording(false);
        setVoiceStatus(error.message || "Không mở được micro.", true);
      }
    }

    function stopRecording() {
      if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
        state.mediaRecorder.stop();
      }
      setRecording(false);
      setVoiceStatus("Đang nhận dạng giọng nói...");
    }

    async function transcribeRecording() {
      if (!state.audioChunks.length) {
        setVoiceStatus("Không có âm thanh để nhận dạng.", true);
        return;
      }

      const blob = new Blob(state.audioChunks, {
        type: state.audioMimeType || state.audioChunks[0].type || "audio/webm",
      });
      const filename = `recording.${audioExtension(blob.type)}`;

      onBusyChange?.(true);
      try {
        const audioBase64 = await readBlobAsBase64(blob);
        const response = await fetch("/api/voice/transcribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ audio_base64: audioBase64, filename }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Speech recognition failed");
        appendPromptText(data.text || "");
        setVoiceStatus(data.text ? "" : "Không nhận ra nội dung nói.", !data.text);
      } catch (error) {
        setVoiceStatus(error.message, true);
      } finally {
        state.audioChunks = [];
        state.mediaRecorder = null;
        onBusyChange?.(false);
      }
    }

    button.addEventListener("click", () => {
      if (state.recording) {
        stopRecording();
      } else {
        startRecording();
      }
    });
  };
})();
