"""Run the real CLIP + production ASGI recognition route with an isolated reference store.

No production DB, catalog records, user-photo uploads, or trained/fake embeddings.
"""
import argparse
import csv
import hashlib
from html import escape
import json
import logging
import os
from pathlib import Path
import platform
import secrets
import sys
import time

REPO = Path(__file__).resolve().parents[1]
REVISION = 'f71041903f3a04f7a883b90f0126eeb4ab44fa7c'
logging.basicConfig(level=logging.WARNING)


class IsolatedReferences:
    """Only persistence is replaced; the actual encoder and API ranking are used."""
    def __init__(self):
        self.rows = []

    def count(self, model_id):
        return len(self.list_embeddings(model_id))

    def count_for_artifact(self, artifact_id, model_id):
        return sum(row['artifact_id'] == artifact_id for row in self.list_embeddings(model_id))

    def add(self, artifact_id, image_name, embedding, dimensions, model_id, limit=None):
        if limit is not None and self.count_for_artifact(artifact_id, model_id) >= limit:
            raise ValueError('Test quota exceeded')
        self.rows.append({'id': len(self.rows) + 1, 'artifact_id': artifact_id,
                          'image_name': image_name, 'embedding': embedding,
                          'dimensions': dimensions, 'model_id': model_id})
        return len(self.rows)

    def list_embeddings(self, model_id):
        return [row for row in self.rows if row['model_id'] == model_id]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(dataset_path, downloads_path, output, cache):
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
    sys.path.insert(0, str(REPO / 'AI Vision'))
    from app import settings
    settings.MODEL_CACHE_DIR = cache
    settings.MODEL_REVISION = REVISION
    # Freeze existing thresholds before any evaluation; never tune them on this set.
    settings.MIN_SIMILARITY, settings.MIN_MARGIN = 0.72, 0.04
    settings.SERVICE_API_KEY = secrets.token_urlsafe(32)
    from app import main
    from app.vision import get_encoder
    from fastapi.testclient import TestClient
    import numpy as np
    import onnxruntime as ort

    data = json.loads(dataset_path.read_text(encoding='utf-8'))
    profiles = {p['id']: p for p in data['profiles']}
    images = {p['id']: p for p in data['images']}
    dataset_root = dataset_path.parent
    actual_ids = {identity: 900000 + index for index, identity in enumerate(profiles, 1)}
    labels = {value: key for key, value in actual_ids.items()}
    overrides = {'PHOTO-003': 'A05', 'PHOTO-009': 'A16'}
    references = []
    reference_hashes = set()
    for identity, profile in profiles.items():
        image_id = overrides.get(identity, profile['reference_candidate_ids'][0])
        photo = images[image_id]
        path = dataset_root / photo['path']
        checksum = digest(path)
        if checksum != photo['sha256']:
            raise ValueError('A reference no longer matches its reviewed photo manifest')
        if checksum in reference_hashes:
            raise ValueError('Duplicate reference file across catalog groups')
        reference_hashes.add(checksum)
        references.append({'profile_id': identity, 'image_id': image_id,
                           'path': path.relative_to(REPO).as_posix(), 'sha256': checksum})

    queries = []
    for image_id, identity, exploratory in [('A04', 'PHOTO-003', False), ('A09', 'PHOTO-006', False),
                                            ('A11', 'PHOTO-007', False), ('A15', 'PHOTO-009', False),
                                            ('B05', 'PHOTO-012', True)]:
        photo = images[image_id]
        queries.append({'id': image_id, 'title': profiles[identity]['title'],
                        'path': (dataset_root / photo['path']).relative_to(REPO).as_posix(),
                        'sha256': photo['sha256'],
                        'kind': 'exploratory_grouping' if exploratory else 'same_group_holdout',
                        'expected_profile_id': identity, 'expected_family_ids': [identity],
                        'expected_matched': True, 'source': 'Ảnh người dùng; nhóm trực quan tạm, chưa có mã DB chính thức.'})
    downloads = json.loads(downloads_path.read_text(encoding='utf-8'))
    for item in downloads:
        if item.get('download_error'):
            continue
        queries.append({**item, 'kind': 'external_similar_object', 'expected_profile_id': None})
    for query in queries:
        checksum = digest(REPO / query['path'])
        if query.get('sha256') != checksum:
            raise ValueError('A query no longer matches its reviewed source manifest')
        query['sha256'] = checksum
        if query['sha256'] in reference_hashes:
            raise ValueError('Holdout/external image duplicates an indexed reference')

    started = time.perf_counter()
    encoder = get_encoder()
    load_ms = (time.perf_counter() - started) * 1000
    main.store = IsolatedReferences()
    main.app.state.model_ready = True
    # Deliberately do not enter app lifespan: it initializes production PostgreSQL.
    client = TestClient(main.app)
    headers = {'X-Service-Key': settings.SERVICE_API_KEY}
    for item in references:
        path = REPO / item['path']
        response = client.post('/api/v1/references', params={'artifact_id': actual_ids[item['profile_id']]},
                               headers=headers, files={'image': (path.name, path.read_bytes(), 'image/png')})
        if response.status_code != 200:
            raise RuntimeError(f'Reference {item["image_id"]}: {response.status_code} {response.text}')
    if client.get('/health').json().get('reference_images') != len(references):
        raise RuntimeError('Wrong reference count')

    results = []
    for query in queries:
        path = REPO / query['path']
        mime = 'image/png' if path.suffix.lower() == '.png' else 'image/jpeg'
        start = time.perf_counter()
        response = client.post('/api/v1/recognitions?top_k=3', headers=headers,
                               files={'image': (path.name, path.read_bytes(), mime)})
        elapsed = (time.perf_counter() - start) * 1000
        item = {**query, 'http_status': response.status_code, 'latency_ms': round(elapsed, 2)}
        if response.status_code != 200:
            item.update({'api_error': response.json(), 'passed': False})
            results.append(item)
            continue
        body = response.json()
        # Verify the top_k ambiguity fix with real embeddings, not handcrafted scores.
        one = client.post('/api/v1/recognitions?top_k=1', headers=headers,
                          files={'image': (path.name, path.read_bytes(), mime)})
        if one.status_code != 200 or any(one.json()[field] != body[field] for field in ['matched', 'artifactId', 'margin', 'similarity']):
            raise RuntimeError('top_k changed a real-image matching decision')
        candidates = [{'profile_id': labels[row['artifactId']], 'similarity': row['similarity']}
                      for row in body['candidates']]
        top = candidates[0]['profile_id']
        selected = labels[body['artifactId']] if body['artifactId'] is not None else None
        if query['kind'] == 'external_similar_object':
            passed = body['matched'] is False
        else:
            passed = body['matched'] is True and selected == query['expected_profile_id']
        item.update({'matched': body['matched'], 'selected_profile_id': selected,
                     'top_profile_id': top, 'similarity': body['similarity'], 'margin': body['margin'],
                     'requires_confirmation': body['requiresConfirmation'], 'candidates': candidates,
                     'family_top1_hit': top in query['expected_family_ids'],
                     'passed': passed, 'top_k_decision_consistent': True})
        results.append(item)
        print(query['id'], 'top', top, 'similarity', body['similarity'], 'margin', body['margin'],
              'matched', body['matched'], 'expected', query['expected_profile_id'] or 'OUTSIDE CATALOG', flush=True)
    client.close()
    held = [row for row in results if row['kind'] == 'same_group_holdout']
    negatives = [row for row in results if row['kind'] == 'external_similar_object']
    summary = {
        'reference_profiles': len(references), 'reference_images': len(references),
        'same_group_holdouts': len(held), 'holdout_top1_hits': sum(r.get('family_top1_hit', False) for r in held),
        'holdout_auto_accept_correct': sum(r['passed'] for r in held),
        'external_similar_objects': len(negatives),
        'external_rejected': sum(r['passed'] for r in negatives),
        'external_false_accepts': sum(r.get('matched') is True for r in negatives),
        'exploratory_unconfirmed_groups': sum(r['kind'] == 'exploratory_grouping' for r in results),
        'http_errors': sum(r['http_status'] != 200 for r in results),
    }
    report = {'schema_version': 1, 'evaluation_date': '2026-11-08', 'mode': 'real_onnx_encoder_and_production_asgi_routes_isolated_memory_store',
              'model_id': encoder.model_id, 'providers': encoder._session.get_providers(),
              'python': platform.python_version(), 'onnxruntime': ort.__version__, 'numpy': np.__version__,
              'model_load_ms': round(load_ms, 2), 'thresholds': {'min_similarity': 0.72, 'min_margin': 0.04},
              'production_db_written': False, 'production_r2_written': False, 'user_photos_uploaded': False,
              'source_sha256': {name: digest(REPO / 'AI Vision' / 'app' / name) for name in ['main.py', 'vision.py', 'settings.py']},
              'references': references, 'summary': summary, 'results': results,
              'limitations': ['Chỉ 4 holdout cùng nhóm quan sát; chưa có ground truth định danh bảo tàng chính thức.',
                              'B05/PHOTO-012 là nhóm ghép tạm, loại khỏi metric holdout chính.',
                              'Ảnh ngoài được coi là ngoài catalog, không dùng làm reference hay đếm thành positive.',
                              'Không dùng A12 trùng A05; không augment ảnh để tạo holdout giả.',
                              'Model và inference thật; persistence tạm trong RAM, không kiểm thử PostgreSQL/gateway/deploy.']}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with (output / 'results.csv').open('w', encoding='utf-8-sig', newline='') as file:
        fields = ['id', 'kind', 'expected_profile_id', 'top_profile_id', 'matched', 'selected_profile_id', 'similarity', 'margin', 'requires_confirmation', 'passed', 'latency_ms']
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(results)
    write_report(output, report, profiles)
    print('SUMMARY', json.dumps(summary, ensure_ascii=False), flush=True)


def write_report(output, report, profiles):
    s = report['summary']
    lines = ['# Kiểm thử CLIP thật với bộ ảnh người dùng — 08/11/2026', '',
             f"Model: `{report['model_id']}`; CPU ONNX Runtime `{report['onnxruntime']}`.", '',
             '**Encoder/model và API nhận diện là code thật. Chỉ thay persistence bằng kho RAM cô lập; không ghi DB/R2, không upload ảnh người dùng ra internet.**', '',
             f"Dùng {s['reference_images']} ảnh reference cho {s['reference_profiles']} hồ sơ nháp. Ngưỡng cố định similarity=0.72, margin=0.04; không chỉnh theo kết quả.", '',
             f"- Holdout cùng nhóm: top-1 đúng {s['holdout_top1_hits']}/{s['same_group_holdouts']}; tự chấp nhận đúng {s['holdout_auto_accept_correct']}/{s['same_group_holdouts']}.",
             f"- Ảnh tương tự ngoài catalog: từ chối {s['external_rejected']}/{s['external_similar_objects']}; tự nhận nhầm {s['external_false_accepts']} trường hợp.",
             '- Một nhóm ghép tạm được thử riêng, không tính vào metric chính.', '',
             '| Ảnh | Nhóm test | Kỳ vọng | Gần nhất | Similarity | Margin | Tự nhận | Kết quả |',
             '| --- | --- | --- | --- | ---: | ---: | --- | --- |']
    for r in report['results']:
        kind = {'same_group_holdout': 'Cùng nhóm, giữ riêng', 'external_similar_object': 'Tương tự nhưng ngoài catalog', 'exploratory_grouping': 'Ghép tạm, thăm dò'}[r['kind']]
        lines.append(f"| {r['id']} | {kind} | {r.get('expected_profile_id') or 'Không tự gán ID'} | {r.get('top_profile_id', 'Lỗi')} | {r.get('similarity', '')} | {r.get('margin', '')} | {'Có' if r.get('matched') else 'Không'} | {'Đạt' if r['passed'] else 'Chưa đạt'} |")
    lines += ['', '## Cách hiểu kết quả', '',
              '- Top-1 đúng nhóm và tự nhận đúng là hai chỉ số khác nhau: khi margin thấp, API có thể yêu cầu xác nhận dù gợi ý đứng đầu đúng.',
              '- Ảnh web cùng kiểu đèn/cân/van không chứng minh là chính hiện vật trong bảo tàng. Tự gán ID trong các ca này được tính là false accept.',
              '- Similarity không phải xác suất nhận đúng; tập này quá nhỏ và nhiều góc gần nhau để kết luận độ chính xác production.',
              '- Những ảnh chỉ có một view chưa có holdout độc lập; không lấy ảnh reference làm query rồi tính thành accuracy.', '',
              '- Ảnh van tay quay WEB-04 bị tự nhận nhầm thành PHOTO-007 (đồng hồ). Giữ nguyên ngưỡng đã đặt trước; không điều chỉnh ngưỡng để làm đẹp kết quả trên chính bộ test này.',
              '- Kết quả này hỗ trợ làm UI gợi ý Top 3 và khách xác nhận, chưa đủ để tự khẳng định danh tính hiện vật ở production.', '',
              '## Nguồn ảnh web', '']
    for r in report['results']:
        if r['kind'] == 'external_similar_object':
            lines += [f"- [{r['id']} — {r['title']}]({r['page_url']}): {r['creator']}; {r['license']}"]
    lines += ['', '## Tái hiện', '', '```powershell', 'cd D:\\SEP409\\AI-System',
              '.\\.venv\\Scripts\\python.exe tools/evaluate_user_photo_recognition.py', '```', '',
              'Cần model cache và ảnh web đã tải; nguồn/checksum trong external_downloads.json. Không tự index các ảnh này vào hệ thống thật.', '',
              'Giới hạn: ' + ' '.join(report['limitations']), '']
    (output / 'README.md').write_text('\n'.join(lines), encoding='utf-8')
    render_html(output, report, profiles)


def render_html(output, report, profiles):
    refs = {row['profile_id']: row for row in report['references']}
    def src(relative):
        return Path(os.path.relpath(REPO / relative, output)).as_posix()
    cards = []
    kinds = {'same_group_holdout': 'Ảnh cùng nhóm, giữ riêng để test', 'external_similar_object': 'Ảnh tương tự ngoài catalog', 'exploratory_grouping': 'Nhóm ghép tạm — không tính vào metric chính'}
    for row in report['results']:
        if row['http_status'] != 200:
            cards.append(f'<article><h2>{escape(row["id"])}</h2><p>Lỗi API: {row["http_status"]}</p></article>')
            continue
        top = row['top_profile_id']; predicted = profiles[top]
        if row['kind'] == 'external_similar_object':
            outcome = 'Nhận nhầm hiện vật ngoài kho' if row['matched'] else 'Từ chối tự gán hiện vật'
            theme = 'bad' if row['matched'] else 'good'
        elif row['kind'] == 'exploratory_grouping':
            outcome, theme = 'Nhóm ảnh chưa xác nhận — kết quả thăm dò', 'review'
        elif row['family_top1_hit']:
            outcome = 'Đúng hồ sơ và tự nhận' if row['matched'] else 'Gợi ý đúng; cần khách xác nhận'
            theme = 'good' if row['matched'] else 'review'
        else:
            outcome, theme = 'Gợi ý sai hồ sơ', 'bad'
        candidates = ''.join(f'<tr><td>{escape(candidate["profile_id"])}</td><td>{escape(profiles[candidate["profile_id"]]["title"])}</td><td>{candidate["similarity"]:.4f}</td></tr>' for candidate in row['candidates'])
        external = f'<p class="source">Nguồn ảnh: <a href="{escape(row["page_url"])}">{escape(row["creator"])}</a><br>{escape(row["license"])}</p>' if row.get('page_url') else ''
        expected = profiles[row['expected_profile_id']]['title'] if row.get('expected_profile_id') else 'Ngoài kho: không tự gán ID hiện vật'
        cards.append(f'<article id="{escape(row["id"])}"><div class="card-head"><small>{escape(row["id"])} · {kinds[row["kind"]]}</small><h2>{escape(row["title"])}</h2><span class="badge {theme}">{outcome}</span><p>Kỳ vọng: {escape(expected)}</p></div><div class="pair"><figure><img src="{escape(src(row["path"]))}" alt="Ảnh test {escape(row["id"])}"><figcaption>Ảnh đưa vào nhận diện</figcaption></figure><figure><img src="{escape(src(refs[top]["path"]))}" alt="Ảnh tham chiếu {escape(top)}"><figcaption>Đứng đầu: {escape(top)} — {escape(predicted["title"])}</figcaption></figure></div><div class="card-body"><p>Similarity: <b>{row["similarity"]:.4f}</b> · Margin: <b>{row["margin"]:.4f}</b> · Tự nhận: <b>{"Có" if row["matched"] else "Không"}</b></p><div class="table"><table><thead><tr><th>Hồ sơ</th><th>Gợi ý Top 3</th><th>Độ tương đồng</th></tr></thead><tbody>{candidates}</tbody></table></div>{external}</div></article>')
    s = report['summary']
    html = '''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SMGS · Kết quả thử CLIP thật</title><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"><style>*{box-sizing:border-box}body{margin:0;background:#f4ebdd;color:#3b302a;font:16px/1.65 system-ui,sans-serif}header,main,footer{max-width:1180px;padding:28px;margin:auto}h1{font:40px/1.2 Georgia,serif;color:#6b2e2e}h2{font-size:22px;line-height:1.4}a{color:#6b2e2e}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.metric,article{border:1px solid #d9c5a8;background:#fffaf3;border-radius:14px}.metric{padding:16px}.metric b{display:block;font-size:28px}.notice{background:#eadbc6;border-left:4px solid #6b2e2e;padding:16px 20px}.badge{display:inline-block;border-radius:8px;padding:6px 12px;font-weight:600}.good{background:#e1eee2;color:#24572c}.review{background:#f4e7c7;color:#725214}.bad{background:#f7dddd;color:#8b2424}article{overflow:hidden;margin-bottom:26px}.card-head,.card-body{padding:22px}.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;padding:0 22px}figure{margin:0;min-width:0}figure img{width:100%;height:350px;object-fit:contain;background:#e6ded2;border-radius:8px}figcaption,.source,small{font-size:14px}.source{overflow-wrap:anywhere}.table{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:10px;border-bottom:1px solid #e1d3c1;text-align:left}td:last-child{font-variant-numeric:tabular-nums}footer{font-size:14px}@media(max-width:680px){header,main,footer{padding:16px}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.pair{grid-template-columns:1fr;padding:0 16px}figure img{height:280px}.card-head,.card-body{padding:16px}h1{font-size:32px}}</style></head><body>'''
    html += f'<header><p>SMGS · KIỂM THỬ MODEL THẬT · 08/11/2026</p><h1>CLIP nhận được những ảnh nào?</h1><div class="metrics"><div class="metric"><b>{s["holdout_top1_hits"]}/{s["same_group_holdouts"]}</b>Holdout đúng Top 1</div><div class="metric"><b>{s["holdout_auto_accept_correct"]}/{s["same_group_holdouts"]}</b>Holdout tự nhận đúng</div><div class="metric"><b>{s["external_rejected"]}/{s["external_similar_objects"]}</b>Ảnh ngoài được từ chối</div><div class="metric"><b>{s["external_false_accepts"]}</b>Ca nhận nhầm ảnh ngoài</div></div><p class="notice">Model ONNX thật, 14 ảnh tham chiếu cho 14 hồ sơ nháp. Ngưỡng giữ nguyên: similarity ≥ 0.72 và margin ≥ 0.04. Không tính ảnh reference hoặc ảnh trùng thành holdout. Các mẫu quá ít để kết luận độ chính xác production.</p><p><a href="README.md">Báo cáo</a> · <a href="results.csv">Bảng CSV</a> · <a href="results.json">JSON đầy đủ</a> · <a href="#WEB-04">Xem ca nhận nhầm</a></p></header><main>'
    html += ''.join(cards) + '</main><footer>Encoder và route API thật; lưu reference trong RAM cô lập, không test DB/gateway/deploy. Ảnh người dùng không được gửi ra internet. Ảnh web chỉ dùng làm query; không thêm vào kho tham chiếu. Nội dung/tác giả/giấy phép theo từng nguồn bên trên. Similarity không phải xác suất nhận đúng.</footer></body></html>'
    (output / 'index.html').write_text(html, encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=REPO / 'test-data/user-museum-2026-11-08/dataset.json')
    parser.add_argument('--downloads', type=Path, default=REPO / 'evaluations/vision-2026-11-08/external_downloads.json')
    parser.add_argument('--output', type=Path, default=REPO / 'evaluations/vision-2026-11-08')
    parser.add_argument('--cache', type=Path, default=REPO / 'state/models/vision-evaluation')
    args = parser.parse_args()
    run(args.dataset.resolve(), args.downloads.resolve(), args.output.resolve(), args.cache.resolve())
