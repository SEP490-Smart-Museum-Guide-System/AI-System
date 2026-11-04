from pathlib import Path
from PIL import Image, UnidentifiedImageError
from .settings import MAX_IMAGE_PIXELS


def validate_image(path: Path) -> None:
    try:
        with Image.open(path) as image:
            expected = 'PNG' if path.suffix.lower() == '.png' else 'JPEG'
            if image.format != expected or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('Định dạng nội dung ảnh phải khớp đuôi JPG/PNG và là ảnh tĩnh.')
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError('Ảnh vượt giới hạn số pixel cho phép.')
            image.verify()
        with Image.open(path) as image:
            image.load()  # verify() alone can accept truncated image data.
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Tệp ảnh bị hỏng hoặc không được hỗ trợ.') from exc
