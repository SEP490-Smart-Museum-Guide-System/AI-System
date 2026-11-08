"""Prepare local photo dossiers from a reviewed intake JSON; never contact an API/DB."""
import argparse
from collections import Counter
import csv
import hashlib
from html import escape
import json
from pathlib import Path
import re
import shutil
import struct
import zipfile

ROLES = {
    'reference_candidate': 'Ảnh hiện vật để duyệt làm tham chiếu',
    'label_evidence': 'Ảnh bảng tên, bổ sung thông tin',
    'duplicate': 'Ảnh trùng, không tính thêm mẫu',
    'context_review': 'Ảnh nhiều đối tượng/bối cảnh, chờ phân loại',
}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_csv(path, fields, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def prepare(intake_path: Path, source_dir: Path, output: Path):
    intake = json.loads(intake_path.read_text(encoding='utf-8-sig'))
    images, profiles = intake['images'], intake['profiles']
    profile_ids, photo_ids = {p['id'] for p in profiles}, {p['id'] for p in images}
    if len(profile_ids) != len(profiles) or len(photo_ids) != len(images):
        raise ValueError('Mã ảnh/hồ sơ bị trùng.')
    if any(not re.fullmatch(r'PHOTO-\d{3}', value) for value in profile_ids):
        raise ValueError('Mã hồ sơ không hợp lệ.')
    prepared, known_hashes = [], {}
    # Validate all attachments and grouping before copying any image.
    for image in images:
        if not re.fullmatch(r'[A-Z]\d{2}', image['id']) or image['role'] not in ROLES:
            raise ValueError('Mã hoặc vai trò ảnh không hợp lệ.')
        if image['profile'] is not None and image['profile'] not in profile_ids:
            raise ValueError('Ảnh trỏ tới hồ sơ không tồn tại.')
        if Path(image['source']).name != image['source'] or not image['source'].endswith('.png'):
            raise ValueError('Nguồn ảnh phải là tên file PNG trong thư mục đầu vào.')
        source = source_dir / image['source']
        content = source.read_bytes()
        if content[:8] != b'\x89PNG\r\n\x1a\n' or content[12:16] != b'IHDR':
            raise ValueError(f"{image['id']}: không phải PNG hợp lệ.")
        width, height = struct.unpack('>II', content[16:24])
        digest = hashlib.sha256(content).hexdigest()
        previous = known_hashes.get(digest)
        if image.get('duplicate_of') != previous:
            raise ValueError(f"{image['id']}: khai báo ảnh trùng chưa khớp SHA-256; cần xem lại intake.")
        known_hashes.setdefault(digest, image['id'])
        row = {**image, 'path': f"images/{image['id']}.png", 'sha256': digest,
               'bytes': len(content), 'width': width, 'height': height,
               'indexing_enabled': False, 'split': 'unassigned'}
        prepared.append(row)
    by_image = {image['id']: image for image in prepared}
    for profile in profiles:
        for evidence in profile.get('label_evidence', []):
            if evidence['image_id'] not in by_image or by_image[evidence['image_id']]['profile'] != profile['id']:
                raise ValueError('Bảng tên không thuộc nhóm ảnh của hồ sơ.')

    output.mkdir(parents=True, exist_ok=True)
    (output / 'images').mkdir(exist_ok=True)
    for image in prepared:
        target = output / image['path']
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != image['sha256']:
                raise ValueError(f'Không ghi đè ảnh đã thay đổi: {target}')
        else:
            shutil.copy2(source_dir / image['source'], target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != image['sha256']:
            raise RuntimeError(f"Sai checksum sau khi sao chép {image['id']}")

    dossiers = []
    for profile in profiles:
        group = [image for image in prepared if image['profile'] == profile['id']]
        references = [image for image in group if image['role'] == 'reference_candidate']
        if not references:
            raise ValueError(f"Hồ sơ {profile['id']} chưa có ảnh hiện vật.")
        evidence = list(profile.get('label_evidence', []))
        for image in group:
            if image.get('transcription') and not any(e['image_id'] == image['id'] for e in evidence):
                evidence.append({'image_id': image['id'], 'text': image['transcription'],
                                 'status': 'transcribed_from_photo_unverified'})
        dossier = {**profile,
            'catalog_binding': {'museum_id': None, 'artifact_id': None, 'gallery_id': None,
                                'official_name': None, 'catalog_number': None},
            'historical_facts': {'date': None, 'provenance': None, 'verified_description': None},
            'label_evidence': evidence, 'source_image_ids': [i['id'] for i in group],
            'reference_candidate_ids': [i['id'] for i in references],
            'cover_image_id': profile.get('cover_image_id', references[0]['id']),
            'review_status': 'awaiting_human_review_and_catalog_mapping',
            'indexing_enabled': False, 'embeddings_created': False,
            'holdout_image_ids': [], 'model_id': None}
        dossiers.append(dossier)
        folder = output / 'profiles' / profile['id']
        write_json(folder / 'profile.json', dossier)
        lines = [f"# {profile['title']}", '', f"Mã nội bộ: `{profile['id']}`. **Hồ sơ nháp — chưa index vào Vision.**", '',
                 f"Cơ sở đặt tên: {profile['name_basis']}.", '',
                 '## Đặc điểm nhìn thấy', '', *[f'- {feature}' for feature in profile['features']], '',
                 '## Ảnh gốc và vai trò', '']
        for image in group:
            lines += [f"### {image['id']} — {ROLES[image['role']]}", '', image['view'], '',
                      f"![{image['id']}](../../{image['path']})", '']
        if evidence:
            lines += ['## Nội dung đọc từ bảng tên', '', 'Phần chép lại dưới đây chưa được đối chiếu hồ sơ bảo tàng.', '']
            for item in evidence:
                lines += [f"Nguồn: {item['image_id']}", '', *['> ' + line for line in item['text'].splitlines()], '']
        lines += ['## Ghi chú cần xác nhận', '', *[f'- {note}' for note in profile.get('notes', [])], '',
                  '- Tên chính thức, bảo tàng, mã hiện vật và vị trí trong DB còn trống.',
                  '- Chọn ảnh phù hợp trước khi index; chưa có ảnh holdout độc lập để đánh giá độ chính xác.',
                  '- Chỉnh nguồn mô tả trong intake.json rồi chạy lại công cụ; các file hồ sơ là bản sinh ra từ nguồn đó.', '']
        (folder / 'README.md').write_text('\n'.join(lines), encoding='utf-8')

    counts = Counter(i['role'] for i in prepared)
    summary = {'images_received': len(prepared), 'unique_image_files': len(known_hashes),
               'draft_profiles': len(dossiers), **dict(counts), 'indexed_images': 0, 'embeddings_created': 0}
    dataset = {key: value for key, value in intake.items() if key not in {'profiles', 'images'}}
    dataset.update({'summary': summary, 'indexing_enabled': False, 'profiles': dossiers, 'images': prepared})
    write_json(output / 'dataset.json', dataset)
    write_json(output / 'reference_queue.json', {
        'enabled': False, 'reason': 'Chưa có museum_id/artifact_id thật và chưa duyệt ảnh.',
        'items': [{'local_profile_id': p['id'], 'museum_id': None, 'artifact_id': None,
                   'enabled': False, 'images': [by_image[key]['path'] for key in p['reference_candidate_ids']]}
                  for p in dossiers]})
    write_csv(output / 'image_manifest.csv', ['image_id', 'local_profile_id', 'role', 'path', 'source_filename', 'sha256', 'width', 'height', 'duplicate_of', 'indexing_enabled', 'note'], [
        {'image_id': i['id'], 'local_profile_id': i['profile'] or '', 'role': i['role'], 'path': i['path'],
         'source_filename': i['source'], 'sha256': i['sha256'], 'width': i['width'], 'height': i['height'],
         'duplicate_of': i.get('duplicate_of', ''), 'indexing_enabled': False, 'note': i.get('note', '')}
        for i in prepared])
    write_csv(output / 'catalog_mapping.csv', ['local_profile_id', 'descriptive_name', 'museum_id', 'artifact_id', 'official_name', 'gallery_id', 'catalog_number', 'review_status'], [
        {'local_profile_id': p['id'], 'descriptive_name': p['title'], 'museum_id': '', 'artifact_id': '',
         'official_name': '', 'gallery_id': '', 'catalog_number': '', 'review_status': 'Chờ xác nhận'} for p in dossiers])
    readme = ['# Hồ sơ ảnh nhận diện bảo tàng', '', f"Tiếp nhận: {intake['received_on']}. Ngày chụp và bảo tàng: chưa xác nhận.", '',
              f"**{len(prepared)} ảnh · {len(known_hashes)} file ảnh khác nhau · {len(dossiers)} hồ sơ nháp.**", '',
              f"Ảnh ứng viên tham chiếu: {counts['reference_candidate']}; ảnh bảng tên: {counts['label_evidence']}; ảnh trùng: {counts['duplicate']}; ảnh nhiều đối tượng/bối cảnh chờ phân loại: {counts['context_review']}.", '',
              'A01–A16 là lượt gửi thứ nhất; B01–B11 là lượt bổ sung. Ảnh được giữ nguyên byte; SHA-256 nằm trong manifest. A12 trùng A05.', '',
              '## Mở và đối chiếu', '',
              '- Mở [index.html](index.html) bằng trình duyệt để xem toàn bộ hồ sơ và ảnh. Không cần BE, DB hay internet.',
              '- [dataset.json](dataset.json): hồ sơ, đặc điểm nhận biết, nhóm ảnh, checksum và trạng thái.',
              '- [catalog_mapping.csv](catalog_mapping.csv): điền mã bảo tàng/hiện vật thật và tên đã xác nhận. Không dùng số vị trí trên nhãn làm artifact_id.',
              '- [image_manifest.csv](image_manifest.csv): đối chiếu toàn bộ 27 ảnh với nguồn, vai trò và ảnh trùng.',
              '- [reference_queue.json](reference_queue.json): danh sách ứng viên; mặc định disabled, chưa gửi vào service.', '',
              '## Danh sách hồ sơ', '', '| Mã nháp | Tên mô tả | Ảnh hiện vật | Hồ sơ |', '| --- | --- | --- | --- |']
    readme += [f"| {p['id']} | {p['title']} | {', '.join(p['reference_candidate_ids'])} | [Xem](profiles/{p['id']}/README.md) |" for p in dossiers]
    readme += ['', '## Các ảnh chờ xác định đối tượng', '']
    readme += [f"- {i['id']}: {i['view']}. {i.get('note', '')}" for i in prepared if i['role'] == 'context_review']
    readme += ['', '## Phạm vi dữ liệu', '',
               '- Tên mô tả tạm, chữ nhìn thấy và nội dung bảng tên được tách riêng khỏi thông tin chính thức.',
               '- Không tự thêm niên đại, xuất xứ, nhân vật, danh tính tượng hay thông số kỹ thuật. Lời chép trên bảng chưa được xác minh độc lập.',
               '- Nhóm B04/B05 và bảng tên B01 cần xác nhận cách ghép với hiện vật tương ứng.',
               '- Chưa train, chạy inference, tạo embedding, index, tạo bản ghi hiện vật hoặc ghi DB/R2.',
               '- Chưa chia tập đánh giá; ảnh trùng/góc gần giống không được coi là bằng chứng chất lượng nhận diện.',
               '- Giấy phép công khai chưa xác nhận; bộ này phục vụ chuẩn bị dự án theo yêu cầu người gửi.', '',
               'Nguồn phân loại thủ công: [intake.json](intake.json). Công cụ dựng hồ sơ: tools/prepare_recognition_dossiers.py.', '']
    (output / 'README.md').write_text('\n'.join(readme), encoding='utf-8')
    render_gallery(output / 'index.html', dataset, by_image)
    return summary


def render_gallery(path, dataset, by_image):
    def image_tag(image):
        return f'<a href="{escape(image["path"])}"><img src="{escape(image["path"])}" alt="{escape(image["id"] + ": " + image["view"])}"></a><span>{escape(image["id"])} · {escape(ROLES[image["role"]])}</span>'
    cards = []
    for profile in dataset['profiles']:
        group = [by_image[key] for key in profile['source_image_ids']]
        features = ''.join(f'<li>{escape(value)}</li>' for value in profile['features'])
        notes = ''.join(f'<li>{escape(value)}</li>' for value in profile.get('notes', []))
        evidence = ''.join(f'<blockquote><small>{escape(item["image_id"])} · Chép từ ảnh, chưa đối chiếu</small><p>{escape(item["text"])}</p></blockquote>' for item in profile['label_evidence'])
        cards.append(f'<article id="{profile["id"]}"><div class="heading"><span class="badge">{profile["id"]} · Hồ sơ nháp</span><h2>{escape(profile["title"])}</h2><p>{escape(profile["name_basis"])}</p></div><div class="photos">' + ''.join(f'<figure>{image_tag(i)}</figure>' for i in group) + f'</div><div class="body"><h3>Đặc điểm nhìn thấy</h3><ul>{features}</ul>{evidence}<details><summary>Ghi chú cần xác nhận</summary><ul>{notes}</ul><p>Mã bảo tàng, mã hiện vật, tên chính thức, niên đại và xuất xứ trong DB chưa được điền. Chưa index vào AI.</p></details><p><a href="profiles/{profile["id"]}/README.md">Hồ sơ Markdown</a> · <a href="profiles/{profile["id"]}/profile.json">Dữ liệu JSON</a></p></div></article>')
    pending = ''.join(f'<figure>{image_tag(i)}<p>{escape(i.get("note", ""))}</p></figure>' for i in dataset['images'] if i['role'] == 'context_review')
    summary = dataset['summary']
    html = '''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>SMGS · Hồ sơ ảnh nhận diện</title>
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'">
<style>*{box-sizing:border-box}body{margin:0;background:#f4ebdd;color:#3b302a;font:16px/1.65 system-ui,sans-serif}header,main,footer{max-width:1280px;margin:auto;padding:28px}header{padding-top:50px}h1{font:42px/1.2 Georgia,serif;color:#6b2e2e;margin:10px 0 20px}h2{font-size:22px;line-height:1.4}h3{font-size:17px}a{color:#6b2e2e}small,.badge{font-size:13px}.notice{padding:16px 20px;background:#eadbc6;border-left:4px solid #6b2e2e;border-radius:4px}.summary{display:flex;flex-wrap:wrap;gap:12px}.summary span,.badge{background:#fffaf3;padding:7px 12px;border:1px solid #d9c5a8;border-radius:8px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}article{min-width:0;background:#fffaf3;border:1px solid #d9c5a8;border-radius:16px;overflow:hidden}.heading,.body{padding:22px}.photos{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;padding:0 16px}figure{margin:0;min-width:0}figure img{display:block;width:100%;height:280px;object-fit:contain;background:#e8dfd3;border-radius:8px}figure span{font-size:13px;display:block;padding:8px 0}figure p{font-size:14px}blockquote{margin:16px 0;padding:12px 16px;background:#f4ebdd;border-left:3px solid #94734c;white-space:pre-line}summary{cursor:pointer;font-weight:600}.pending{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:20px}footer{font-size:14px}@media(max-width:720px){header,main,footer{padding:18px}.grid{grid-template-columns:1fr}h1{font-size:32px}.photos{grid-template-columns:1fr}figure img{height:320px}.heading,.body{padding:16px}}</style></head><body>'''
    html += f'<header><p>SMGS · BỘ ẢNH TIẾP NHẬN {escape(dataset["received_on"])}</p><h1>Hồ sơ ảnh nhận diện bảo tàng</h1><div class="summary"><span>{summary["images_received"]} ảnh gốc</span><span>{summary["draft_profiles"]} hồ sơ nháp</span><span>{summary["reference_candidate"]} ảnh ứng viên tham chiếu</span><span>Chưa index vào AI</span></div><p class="notice">Bảo tàng và mã hiện vật DB chưa xác nhận. Tên mô tả không thay cho tên chính thức. A là lượt gửi đầu, B là lượt bổ sung. Nhấn ảnh để mở bản gốc.</p><p><a href="README.md">Hướng dẫn</a> · <a href="catalog_mapping.csv">Bảng điền mã hiện vật</a> · <a href="image_manifest.csv">Danh sách ảnh</a> · <a href="dataset.json">Dữ liệu đầy đủ</a></p></header>'
    html += '<main><section class="grid">' + ''.join(cards) + '</section><h2>Ảnh bối cảnh hoặc nhiều đối tượng — chờ xác định</h2><div class="pending">' + pending + '</div></main>'
    html += '<footer>Ngày chụp, giấy phép công khai và thông tin lịch sử chưa xác nhận. Không train model, tạo embedding hoặc ghi dữ liệu vào hệ thống trong bước chuẩn bị này.</footer></body></html>'
    path.write_text(html, encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--intake', required=True, type=Path)
    parser.add_argument('--source-dir', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--zip', action='store_true', help='Create a local review ZIP beside the output folder.')
    args = parser.parse_args()
    output = (args.output or args.intake.parent).resolve()
    if args.intake.resolve().parent != output:
        output.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.intake, output / 'intake.json')
    result = prepare(args.intake, args.source_dir.resolve(), output)
    if args.zip:
        archive_path = output.with_suffix('.zip')
        with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(output.rglob('*')):
                if file.is_file():
                    archive.write(file, arcname=Path(output.name) / file.relative_to(output))
        with zipfile.ZipFile(archive_path) as archive:
            if archive.testzip() is not None:
                raise RuntimeError('ZIP verification failed')
        result['zip'] = str(archive_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
