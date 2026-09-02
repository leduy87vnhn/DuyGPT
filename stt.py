import os
import tempfile
import threading

_model = None
_model_lock = threading.Lock()


def _setup_cuda_library_path():
    """Point the dynamic loader at the pip-installed cuBLAS/cuDNN .so files
    (nvidia-cublas-cu12 / nvidia-cudnn-cu12) so ctranslate2 can dlopen them,
    since a CUDA driver alone does not provide these runtime libraries."""
    try:
        import nvidia.cublas.lib
        import nvidia.cudnn.lib
    except ImportError:
        return
    extra = os.pathsep.join(
        dict.fromkeys([*nvidia.cublas.lib.__path__, *nvidia.cudnn.lib.__path__])
    )
    existing = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = f"{extra}{os.pathsep}{existing}" if existing else extra


def _build_model(device):
    from faster_whisper import WhisperModel

    return WhisperModel(
        os.getenv("STT_MODEL", "small"),
        device=device,
        compute_type=os.getenv("STT_COMPUTE_TYPE", "default"),
    )


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _setup_cuda_library_path()
                _model = _build_model(os.getenv("STT_DEVICE", "auto"))
    return _model


def transcribe(raw_bytes, filename="audio.wav"):
    global _model
    suffix = os.path.splitext(filename)[1] or ".wav"
    language = os.getenv("STT_LANGUAGE", "vi").strip() or None
    model = _get_model()
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(raw_bytes)
        tmp.flush()
        with _model_lock:
            try:
                segments, _info = model.transcribe(tmp.name, language=language, beam_size=5)
                return "".join(segment.text for segment in segments).strip()
            except Exception:
                if os.getenv("STT_DEVICE", "auto") == "cpu":
                    raise
                # GPU runtime libs unavailable at inference time; fall back to CPU once.
                _model = _build_model("cpu")
                segments, _info = _model.transcribe(tmp.name, language=language, beam_size=5)
                return "".join(segment.text for segment in segments).strip()
