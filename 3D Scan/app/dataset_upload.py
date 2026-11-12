"""Validated directory upload for the same CPU pipeline as the local command."""
import json
from pathlib import Path
import re

from fastapi import HTTPException
from .settings import MAX_IMAGE_BYTES, MAX_TOTAL_BYTES
from .validation import validate_image


def save_dataset(root, images, metadata, reference_obj, mode):
    if mode not in {'auto', 'photos', 'benchmark'}:
        raise HTTPException(422, 'Chế độ scan không hợp lệ.')
    if not 5 <= len(images) <= 200:
        raise HTTPException(422, 'Chọn 5–200 ảnh của cùng một hiện vật.')
    has_reference = metadata is not None and reference_obj is not None
    if mode != 'photos' and bool(metadata) != bool(reference_obj):
        raise HTTPException(422, 'Benchmark cần cả metadata.json và OBJ tham chiếu; hoặc chọn chế độ chỉ ảnh.')
    selected = ('benchmark' if has_reference else 'photos') if mode == 'auto' else mode
    if selected == 'benchmark' and not has_reference:
        raise HTTPException(422, 'Thiếu metadata.json hoặc OBJ tham chiếu.')
    source = root / 'dataset'
    folder = source / 'images'
    folder.mkdir(parents=True)
    total = 0
    def save(upload, target, maximum):
        nonlocal total
        size = 0
        with target.open('wb') as output:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                total += len(chunk)
                if size > maximum or total > MAX_TOTAL_BYTES:
                    raise HTTPException(413, 'Bộ ảnh vượt dung lượng cho phép (tổng tối đa 500 MiB).')
                output.write(chunk)
        if size == 0:
            raise HTTPException(422, 'Tệp không được rỗng.')
    names = []
    for index, image in enumerate(images, 1):
        original = (image.filename or '').replace('\\', '/').rsplit('/', 1)[-1]
        suffix = Path(original).suffix.lower()
        if suffix not in {'.jpg', '.jpeg', '.png'}:
            raise HTTPException(415, 'Chỉ nhận JPG/PNG.')
        name = original if selected == 'benchmark' else f'image_{index:05d}{suffix}'
        if selected == 'benchmark' and not re.fullmatch(r'[A-Za-z0-9_.-]*CAM\d+[A-Za-z0-9_.-]*\.\d+\.png', name):
            raise HTTPException(422, 'Tên ảnh benchmark phải giữ camera/frame của dataset LR3D.')
        if name.lower() in {n.lower() for n in names}:
            raise HTTPException(422, 'Tên ảnh trùng nhau.')
        save(image, folder / name, MAX_IMAGE_BYTES)
        try:
            validate_image(folder / name)
        except ValueError as error:
            raise HTTPException(415, str(error)) from error
        names.append(name)
    if selected == 'benchmark':
        save(metadata, source / 'metadata.json', 2 * 1024 * 1024)
        save(reference_obj, source / 'reference.obj', 64 * 1024 * 1024)
        try:
            info = json.loads((source / 'metadata.json').read_text(encoding='utf-8'))
            if not isinstance(info, dict) or not isinstance(info.get('frames'), list) or not isinstance(info.get('object_center_world'), dict):
                raise ValueError('Missing camera metadata')
        except (ValueError, UnicodeError) as error:
            raise HTTPException(422, 'metadata.json không đúng định dạng LR3D.') from error
    config = dict(mode=selected, images=['images/' + name for name in names], image_count=len(names))
    (root / 'config.json').write_text(json.dumps(config), encoding='utf-8')
    return config
