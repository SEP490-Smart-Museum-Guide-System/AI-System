"""Read native stage counters; never turn elapsed time into progress."""
from datetime import datetime, timezone
from pathlib import Path
import re


def activity(root: Path, status: str, progress: int = 0) -> dict:
    result = dict(stage='sfm', title='Phân tích ảnh và tính camera', phase=1,
                  percent=None, completed=None, total=None, lastActivityAt=None,
                  detail='Máy chủ đang xử lý giai đoạn này. Tiến độ toàn tác vụ được cập nhật theo mốc.')
    if status in {'REVIEW_REQUIRED', 'COMPLETED'}:
        result.update(stage='complete', title='Đã dựng xong mô hình', phase=5, percent=100, detail='')
    if status in {'FAILED', 'CANCELLED', 'DISCARDED'}:
        return {**result, 'stage': 'stopped', 'title': 'Tác vụ đã dừng', 'phase': 0, 'detail': ''}
    if status == 'QUEUED':
        return {**result, 'stage': 'queued', 'title': 'Đang xếp hàng', 'phase': 0, 'detail': 'Đang chờ worker nhận bộ ảnh.'}
    if status == 'FINALIZING':
        result.update(stage='export', title='Kiểm định và đóng gói GLB', phase=4)
    logs = []
    for directory in (root/'logs', root/'openmvs', root/'openmvs/logs', root/'openmvs/patchmatch', root/'openmvs/patchmatch/logs'):
        if directory.is_dir():
            logs.extend(p for p in directory.glob('*.log') if p.is_file())
    if not logs:
        return result
    # Keep photo work visible after the engine advances to mesh/texture.
    native_depth_logs = [p for p in logs if 'densifypointcloud' in p.name.lower()]
    if native_depth_logs:
        try:
            depth_log = max(native_depth_logs, key=lambda p: p.stat().st_mtime)
            if depth_log.stat().st_size <= 196608:
                values = re.findall(r'Depth-map for image\s+(\d+)\s+estimated', depth_log.read_text(encoding='utf8', errors='replace'))
                if values:
                    result.update(depthImages=len(set(values)), depthOperations=len(values))
        except OSError:
            pass
    if status in {'REVIEW_REQUIRED', 'COMPLETED', 'FINALIZING'}:
        return result
    try:
        latest = max(logs, key=lambda p: p.stat().st_mtime)
        info = latest.stat()
        with latest.open('rb') as source:
            source.seek(max(0, info.st_size - 196608))
            text = source.read(196608).decode('utf8', errors='replace')
        result['lastActivityAt'] = datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat()
    except OSError:
        return result
    name = latest.name.lower()
    if any(token in name for token in ('texture', 'export')):
        return {**result, 'stage': 'texture', 'title': 'Tạo texture và xuất GLB', 'phase': 4}
    if any(token in name for token in ('densify', 'densification')):
        result.update(stage='dense', title='Ước lượng độ sâu ảnh', phase=3)
        counters = list(re.finditer(r'(Estimated depth-maps|Dense fused depth-maps)\s+(\d+)\s+\(([\d.]+)%', text, re.I))
        if counters:
            match = counters[-1]
            percent = float(match[3])
            if 0 <= percent <= 100:
                result.update(percent=percent, completed=int(match[2]),
                              detail=f'Đã xử lý {match[2]} bản đồ độ sâu.')
                if match[1].lower().startswith('dense fused'):
                    result['title'] = 'Hợp nhất bản đồ độ sâu'
        elif info.st_size <= 196608:
            # Native per-image completion lines often flush sooner than the
            # aggregated stdout counter. Count unique completed images only
            # when the complete log fits; no denominator is invented.
            operations = re.findall(r'Depth-map for image\s+(\d+)\s+estimated', text)
            completed = set(operations)
            if completed:
                result.update(completed=len(completed), operations=len(operations),
                              detail=(f'Đã xử lý {len(completed)} ảnh qua {len(operations)} lượt tính độ sâu; đang tiếp tục tinh chỉnh.'
                                      if len(operations) > len(completed) else f'Đã tính độ sâu cho {len(completed)} ảnh.'))
        return result
    if any(token in name for token in ('reconstruct', 'mesh_reconstruction', 'refine', 'mesh_refinement')):
        return {**result, 'stage': 'mesh', 'title': 'Dựng và tinh chỉnh lưới bề mặt', 'phase': 3}
    if 'undistort' in name:
        result.update(stage='undistortion', title='Hiệu chỉnh ảnh theo camera', phase=2)
        counts = re.findall(r'Undistorting image \[(\d+)/(\d+)\]', text)
        if counts:
            current, total = map(int, counts[-1])
            if 0 < current <= total:
                result.update(completed=current-1, total=total, percent=round(100*(current-1)/total, 1),
                              detail=f'Đang hiệu chỉnh ảnh {current}/{total}.')
        return result
    if any(token in name for token in ('triangulation', 'calibration', 'interfacecolmap', 'colmap_import')) or re.search(
            r'Initializing with image pair|Registering image #|Bundle adjustment report|Retriangulation|Incremental mapping', text):
        return {**result, 'stage': 'cameras', 'title': 'Ước lượng và tối ưu camera', 'phase': 2,
                'detail': 'Đang đăng ký góc chụp và tối ưu điểm 3D; bước này không có tổng số vòng cố định.'}
    blocks = list(re.finditer(r'Matching block \[(\d+)/(\d+),\s*(\d+)/(\d+)\]', text))
    if blocks:
        match = blocks[-1]
        row, rows, col, cols = map(int, match.groups())
        if 0 < row <= rows and 0 < col <= cols:
            current, total = (row-1)*cols+col, rows*cols
            completed = current if re.search(r' in [\d.]+s', text[match.end():]) else current-1
            return {**result, 'stage': 'matching', 'title': 'Khớp đặc trưng giữa các ảnh', 'phase': 2,
                    'completed': completed, 'total': total, 'percent': round(100*completed/total, 1),
                    'detail': f'Đã khớp {completed}/{total} nhóm ảnh.'}
    counts = re.findall(r'Processed file \[(\d+)/(\d+)\]', text)
    if counts:
        current, total = map(int, counts[-1])
        if 0 < current <= total:
            result.update(stage='features', title='Trích xuất đặc trưng ảnh',
                          completed=current-1, total=total, percent=round(100*(current-1)/total, 1),
                          detail=f'Đang xử lý ảnh {current}/{total}.')
    return result
