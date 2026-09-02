const els = {
  fullName: document.querySelector("#fullName"),
  address: document.querySelector("#address"),
  phone: document.querySelector("#phone"),
  record: document.querySelector("#record"),
  clear: document.querySelector("#clear"),
  status: document.querySelector("#status"),
  transcript: document.querySelector("#transcript"),
};

let captureWindow = null;

function setStatus(message, isError = false) {
  els.status.textContent = message;
  els.status.classList.toggle("error", isError);
}

function fillFields(fields) {
  if (fields.full_name) els.fullName.value = fields.full_name;
  if (fields.address) els.address.value = fields.address;
  if (fields.phone) els.phone.value = fields.phone;
}

function captureUrl() {
  const httpsPort = "8443";
  const parentOrigin = window.location.origin;
  const url = new URL(`https://${window.location.hostname}:${httpsPort}/voice_capture`);
  url.searchParams.set("parent", parentOrigin);
  return url.toString();
}

function openCapturePopup() {
  const width = 260;
  const height = 180;
  const left = Math.max(0, window.screenX + window.outerWidth - width - 40);
  const top = Math.max(0, window.screenY + window.outerHeight - height - 80);
  captureWindow = window.open(
    captureUrl(),
    "duygpt_voice_capture",
    `popup=yes,width=${width},height=${height},left=${left},top=${top},resizable=yes`
  );
  if (!captureWindow) {
    setStatus("Trình duyệt đã chặn popup. Hãy cho phép popup cho trang này.", true);
    return;
  }
  setStatus("Cửa sổ ghi âm HTTPS đã mở.");
}

window.addEventListener("message", (event) => {
  const expectedOrigin = `https://${window.location.hostname}:8443`;
  if (event.origin !== expectedOrigin) return;
  const message = event.data || {};
  if (message.type === "duygpt:user-info-status") {
    setStatus(message.status || "", Boolean(message.error));
    return;
  }
  if (message.type !== "duygpt:user-info-result") return;
  fillFields(message.fields || {});
  els.transcript.textContent = message.text ? `Nội dung: ${message.text}` : "";
  setStatus("Đã điền thông tin từ ghi âm.");
  if (captureWindow && !captureWindow.closed) {
    captureWindow.close();
  }
});

els.record.addEventListener("click", openCapturePopup);

els.clear.addEventListener("click", () => {
  els.fullName.value = "";
  els.address.value = "";
  els.phone.value = "";
  els.transcript.textContent = "";
  setStatus("");
});
