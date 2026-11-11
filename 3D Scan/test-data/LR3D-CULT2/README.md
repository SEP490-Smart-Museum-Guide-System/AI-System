# COLMAP image test set

## Dataset

- Source: [LR3D-CULT2: Vietnamese Ceramic Cultural Artifacts](https://data.mendeley.com/datasets/jr23fnrvx2/1), version 1, DOI `10.17632/jr23fnrvx2.1`.
- Dataset license: CC BY 4.0. Cite Nguyen, Le Huu Bao; Nguyen, Van Nhat Nam; Nguyen, The Trong Nha; Bui, Cao Vu (2026), Mendeley Data.
- The selected `metal_cups_1` object is identified in the source metadata as `ly_dong_1`.
- Source archive contains a mesh and 180 rendered PNG views (two 360-degree camera orbits). Its metadata has 182 position entries including repeated 0°/360° endpoints. The original small test folder keeps 40 sampled views; the downloaded full archive is separate under ignored `source/`.

## Important limitation

These are Blender-rendered views from an existing 3D asset, not photographs captured around a physical artifact. They are suitable for checking image upload, COLMAP feature matching and camera registration, but a successful result does not validate reconstruction quality on iPhone photos. The dataset description also notes that some source models originate from Sketchfab under academic-use terms; keep this sample for academic evaluation and retain this attribution.

## Test folder

`metal-cup-ly-dong-1/images/` contains 40 PNG images. The Scan API accepts PNG and requires 5–80 images per job. This set is meant for local testing; do not publish the generated result as a verified museum scan.

## Local COLMAP check — 11 Nov 2026

Follow-up with the full archive: [`../../DATASET_CAMERA_AUDIT_2026-11-11.md`](../../DATASET_CAMERA_AUDIT_2026-11-11.md). It documents missing camera intrinsics/rotations, original OBJ/MTL texture-path mismatches, inferred calibration with held-out silhouette checks, and the 180-image fixed-camera CPU reconstruction experiment. The initial comparison page's 512/1024 calibration mismatch is corrected; its old screenshot was not a valid same-projection comparison.

- Direct COLMAP 3.8 CPU sparse reconstruction registered 40/40 images and produced 3,704 sparse points (mean reprojection error 0.307 px). The PLY and a four-view preview are saved beside `images/`.
- A dense CPU attempt reported `Skipping patch match stereo because CUDA is not available`; it did not create a dense surface mesh.
- Earlier PoC runs exposed CPU/headless invocation and intermediate-output issues. Those runs are retained in the database as failed jobs; the final implementation below supersedes the earlier sparse-cloud result.
- **Correction:** API job `6d9f771a-acb1-4a57-a483-6741ae41a56e` was marked `REVIEW_REQUIRED`, `modelType=mesh`, but it did **not** produce a dense cloud. Its SGM log reports `0 points`; the later 3,177-vertex / 6,350-face mesh was reconstructed from the original sparse cloud. The API GLB (6,327 vertices, 9,812 faces) therefore must not be presented as a successful dense scan. The 40 images are all registered; original COLMAP made 40 separate camera calibrations for 40 same-sized views.
- The original GLB atlas is 1024×1024. Pixel counts show about 47.6% OpenMVS default orange and 28.1% black. Sampling UV face centroids with the GLB/OpenMVS vertical convention estimates only 8.2% of faces hit non-fallback source-image pixels; about 81.5% hit the default orange color. These values explain the flat/fallback appearance; they are approximate face samples, not area-weighted texture quality metrics.
- A clean CPU PatchMatch comparison with a shared camera calibration and `--resolution-level 1` produced 55,561 fused points in 5m17s on the local 4-thread container. It generated a mesh, but same-pose comparison against the source view showed large foreground/background geometry mismatch and the atlas still contains blank/fallback areas. This output is stored under `metal-cup-ly-dong-1/cpu-patchmatch-single-camera/` for diagnosis only; it is not a validated museum model.
- On that exact mesh, `TextureMesh --virtual-face-images 3 --cost-smoothness-ratio 0.5` increased sampled non-fallback faces from 16.6% (defaults) to 50.9%; 13.2% still sample the default orange and 35.9% sample black atlas regions. `resolution-level 0`, max texture size 4096, and seam leveling are retained, but they do not recreate missing geometry or source detail. No average-color filling is used.
- The API job is protected by a dense-point guard. SGM with zero dense vertices triggers an isolated CPU PatchMatch retry; if that also produces zero points, the job fails instead of exporting a sparse-derived surface. OpenMVS's `model_0.png` sidecar is embedded in the GLB after texture mapping, so the existing GLB-only API response can display its material.
- This dataset remains synthetic Blender render data, not iPhone photos of the physical ceramic jar discussed in chat. It is useful for pipeline diagnostics but cannot establish accurate reconstruction of that jar or a real museum artifact.
