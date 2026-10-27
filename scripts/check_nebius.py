"""Step-by-step check of the Nebius connection. Prints PASS/FAIL per step and the exact error.
   export NEBIUS_API_KEY=...; python scripts/check_nebius.py [optional_image.jpg]
"""
import base64, os, sys, pathlib, traceback
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("DAWA_PROVIDER", "nebius")
from dawa_buddy import llm


def step(name, fn):
    try:
        out = fn()
        print(f"PASS  {name}: {str(out)[:160]}")
        return True
    except Exception as e:
        print(f"FAIL  {name}: {type(e).__name__}: {str(e)[:500]}")
        if os.environ.get("DEBUG"):
            traceback.print_exc()
        return False


print("provider:", llm.provider(), "| base url:", llm.BASE_URL)
print("key set:", bool(os.environ.get("NEBIUS_API_KEY")), "| text model:", llm.TEXT_MODEL, "| vision model:", llm.vision_model())
if not step("openai package", lambda: __import__("openai").__version__):
    sys.exit("Run: pip install -r requirements.txt")
if not os.environ.get("NEBIUS_API_KEY"):
    sys.exit("NEBIUS_API_KEY is not set in THIS terminal. Run: export NEBIUS_API_KEY=your_key")
step("list models (key + network)", lambda: [m.id for m in llm._client().models.list().data if "emotron" in m.id])
step("text model JSON", lambda: llm.chat_json('Reply with ONLY JSON {"ok": true}', "ping"))
img = sys.argv[1] if len(sys.argv) > 1 else None
if img:
    p = pathlib.Path(img)
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    step("vision on your image", lambda: llm.chat_vision_json(base64.b64encode(p.read_bytes()).decode(), mime,
                                                              'List any words you can read as JSON {"words":[...]}'))
else:
    print("skip  vision: pass an image path to test it")
