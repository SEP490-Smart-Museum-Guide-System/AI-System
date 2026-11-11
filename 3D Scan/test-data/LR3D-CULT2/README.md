# COLMAP image test set

## Dataset

- Source: [LR3D-CULT2: Vietnamese Ceramic Cultural Artifacts](https://data.mendeley.com/datasets/jr23fnrvx2/1), version 1, DOI `10.17632/jr23fnrvx2.1`.
- Dataset license: CC BY 4.0. Cite Nguyen, Le Huu Bao; Nguyen, Van Nhat Nam; Nguyen, The Trong Nha; Bui, Cao Vu (2026), Mendeley Data.
- The selected `metal_cups_1` object is identified in the source metadata as `ly_dong_1`.
- Source archive contains a mesh and 182 rendered PNG views (two 360-degree camera orbits). The repository test set keeps only 40 evenly spaced PNG views, 20 from each orbit; the source mesh is not part of the extracted test folder.

## Important limitation

These are Blender-rendered views from an existing 3D asset, not photographs captured around a physical artifact. They are suitable for checking image upload, COLMAP feature matching and camera registration, but a successful result does not validate reconstruction quality on iPhone photos. The dataset description also notes that some source models originate from Sketchfab under academic-use terms; keep this sample for academic evaluation and retain this attribution.

## Test folder

`metal-cup-ly-dong-1/images/` contains 40 PNG images. The Scan API accepts PNG and requires 5–80 images per job. This set is meant for local testing; do not publish the generated result as a verified museum scan.

## Local COLMAP check — 11 Nov 2026

- Direct COLMAP 3.8 CPU sparse reconstruction registered 40/40 images and produced 3,704 sparse points (mean reprojection error 0.307 px). The PLY and a four-view preview are saved beside `images/`.
- A dense CPU attempt reported `Skipping patch match stereo because CUDA is not available`; it did not create a dense mesh or GLB.
- The actual Scan API job was accepted, then failed with COLMAP exit `-6`: the worker's `automatic_reconstructor` default tried to create an OpenGL context in the headless container because the API command does not pass `--use_gpu 0`.
- Therefore this sample verifies CPU feature matching and camera registration only. It does not demonstrate end-to-end GLB generation.
