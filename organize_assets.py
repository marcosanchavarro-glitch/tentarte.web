"""Move supplied assets into public/images without overwriting different images."""
import hashlib
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
ASSETS = {
    "oreo.jpg": "products/oreo/oreo.jpg",
    "banoffee.jpg": "products/banoffee/banoffee.jpg",
    "toffee.jpg": "products/toffee/toffee.jpg",
    "tentarte-logo.png": "branding/tentarte-logo.png",
    "banner-tentarte.jpg": "banners/banner-tentarte.jpg",
}

def organize(root=ROOT):
    for filename, relative in ASSETS.items():
        target = root / "public/images" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        matches = [p for p in root.rglob('*') if p.is_file() and p.name.lower() == filename
                   and not any(part in {'.git', '.venv', 'node_modules', 'instance', '__pycache__'} for part in p.relative_to(root).parts)
                   and p.resolve() != target.resolve() and not p.is_symlink()]
        for source in matches:
            if target.exists():
                if hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256(target.read_bytes()).digest():
                    source.unlink()
                else:
                    print(f'Conflicto: se conserva {source}; el destino ya tiene otra imagen.')
            else:
                shutil.move(str(source), str(target))
                print(f'Organizado: {target.relative_to(root)}')
        if not target.exists():
            print(f'Pendiente: {filename}')

if __name__ == '__main__':
    organize()
