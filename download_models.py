"""
oemer ONNX Checkpoints Downloader
Downloads only the necessary ONNX model checkpoints for inference (CPU / ONNX Runtime).
Avoids 404 errors by fetching valid release assets directly.
"""
import os
import sys
import urllib.request

# Safe encoding reconfiguration
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def ensure_checkpoints():
    try:
        from oemer import MODULE_PATH
    except ImportError:
        print("[Error] oemer package is not installed yet.", file=sys.stderr)
        sys.exit(1)

    checkpoints_dir = os.path.join(MODULE_PATH, "checkpoints")

    models = {
        "unet_big/model.onnx": "https://github.com/BreezeWhite/oemer/releases/download/checkpoints/1st_model.onnx",
        "seg_net/model.onnx": "https://github.com/BreezeWhite/oemer/releases/download/checkpoints/2nd_model.onnx"
    }

    print(f"[INFO] Verifying oemer ONNX checkpoints in: {checkpoints_dir}")

    for rel_path, url in models.items():
        dest = os.path.join(checkpoints_dir, rel_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        if not os.path.exists(dest) or os.path.getsize(dest) < 1000000:
            print(f"[DOWNLOAD] Downloading {url} -> {dest} ...")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp, open(dest, "wb") as f:
                while chunk := resp.read(65536):
                    f.write(chunk)
            print(f"[OK] Downloaded {rel_path} ({os.path.getsize(dest):,} bytes)")
        else:
            print(f"[OK] Checkpoint already present: {rel_path} ({os.path.getsize(dest):,} bytes)")

    unet_path = os.path.join(checkpoints_dir, "unet_big", "model.onnx")
    seg_path = os.path.join(checkpoints_dir, "seg_net", "model.onnx")

    assert os.path.exists(unet_path) and os.path.getsize(unet_path) > 1000000, f"Missing {unet_path}"
    assert os.path.exists(seg_path) and os.path.getsize(seg_path) > 1000000, f"Missing {seg_path}"
    print("[SUCCESS] All required ONNX checkpoints verified successfully!")

if __name__ == "__main__":
    ensure_checkpoints()
