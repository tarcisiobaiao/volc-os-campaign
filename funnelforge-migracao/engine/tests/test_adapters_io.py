import io
from pathlib import Path
from PIL import Image
from funnelforge.adapters.briefing_docx import DocxBriefingLoader
from funnelforge.adapters.images_pillow import PillowImageProcessor


def test_loader_reads_txt(tmp_path: Path):
    f = tmp_path / "b.txt"
    f.write_text("Briefing do funil FGTS")
    assert "FGTS" in DocxBriefingLoader().load(f)


def test_pillow_converts_to_webp(tmp_path: Path):
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 20, 30)).save(buf, format="PNG")
    out = PillowImageProcessor().to_webp(buf.getvalue(), tmp_path / "x.webp")
    assert out.exists()
    assert Image.open(out).format == "WEBP"
