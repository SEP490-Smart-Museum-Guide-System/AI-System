# LR3D-CULT2 source-camera audit — 11 November 2026

Source: https://data.mendeley.com/datasets/jr23fnrvx2/1 (DOI 10.17632/jr23fnrvx2.1).
Archive file ID `ad5334d5-bfa5-4542-bc4c-a048d57d5b64`, 72,042,717 bytes.
Verified SHA-256: `f16622e0620e1fe241eb46a7e51f69fd286a8a55974a2c47057b6abad16ddc28`.
Downloaded archive and extracted source files are intentionally ignored by Git.

## Actual contents

- Object: `metal_cups_1`, metadata name `ly_dong_1`.
- 180 PNG images: 90 from CAM1 and 90 from CAM2, image frame numbers 0001–0090.
- `metadata.json` has 182 entries: frames 0–90 for each camera; endpoints repeat 0°/360°.
- No `transforms.json`. Metadata has object center, Y-up axis convention, camera world positions, spherical angles/radius. It has **no camera rotation matrices/quaternions, focal length/FOV, principal point or lens model**. These are not full original camera poses/calibration.
- OBJ, MTL and a 2880×3840 PNG texture are present. OBJ refers to `ly_dong_1.mtl`, while the archive file is `metal_cups_1.mtl`; that MTL refers to `ly_dong_1.png`, while the archive file is `metal_cups_1.png`. The texture/material paths must be corrected in a reference-only conversion; this asset must never be presented as a reconstructed scan output.
- Source geometry has 460,164 imported vertices (UV splits) / 153,388 faces. Bounds approximately ±2.898 X, ±3.348 Y, ±2.732 Z.

## Benchmark camera inference and coordinate conversion

`tools/audit_dataset_cameras.py` tests a perspective, zero-roll camera looking at `object_center_world`, with world +Y up. These orientations are **inferred**, not supplied by the metadata. Camera position C is kept from metadata. OpenCV/COLMAP camera axes are right/down/forward: `forward=normalize(target-C)`, `right=normalize(cross(forward,world_up))`, `down=cross(forward,right)`, R contains these axes as rows, t = −R C. The resulting world-to-camera quaternion/translation is written as COLMAP TXT for InterfaceCOLMAP/OpenMVS.

Since intrinsics are missing, this benchmark estimates fx/fy/cx/cy from source-OBJ silhouette bounds in ten views (five from each orbit). **Reference geometry is used to calibrate/validate this synthetic benchmark**, not to supply reconstructed triangles. This calibration method is not available for a real unknown museum scan and must not be claimed as an end-to-end photogrammetry result without that qualification.

- Image number maps to the **same metadata frame number**, not frame minus one. Bbox RMSE was 0.222 px versus 0.341 px for the other offset.
- Estimated camera at 512×512: fx=743.500, fy=745.855, cx=255.421, cy=255.449.
- Source silhouette IoU in the ten calibration views: 98.79–99.06%.
- Eight additional held-out views, not used to fit the intrinsics: silhouette IoU 98.70–99.03%.
- This verifies silhouette alignment; it does not prove exact camera roll/focal or all visible texture/occlusion alignment. JSON reports and binary-mask overlays are retained for inspection.

## Reconstruction experiment

The experiment uses all 180 source images with these fixed camera priors. COLMAP feature extraction/matching/point triangulation is used to create sparse point tracks; incremental camera estimation is not rerun. `point_triangulator --refine_intrinsics 0 --Mapper.fix_existing_images 1` keeps the supplied calibration. The CPU matcher uses 1,890 nearby-camera pairs selected from all 180 cameras; an earlier exhaustive attempt was interrupted and its already-computed matches remain in the diagnostic database. Pair selection reduces cost without dropping images. It is a standalone benchmark; the existing Scan API is unchanged.

Triangulation produced 16,411 points, 157,421 observations and 0.887 px mean reprojection error across 180 registered images. A TXT export comparison verified the maximum change in quaternion/translation parameters was 3.33e−16 (floating-point noise), with intrinsics unchanged. Thus this experiment really keeps the camera priors rather than rerunning camera estimation.

The 40-image PINHOLE SfM comparison separately produced 162,592 dense points and a refined mesh with 8,929 vertices / 17,862 faces (watertight). Those figures alone do not certify shape/color.

## Final 180-image result: insufficient interior coverage

- CPU PatchMatch at source resolution (`--resolution-level 0`, four threads) fused 665,122 points in 7m28s. Log VmPeak was 2,736,048 kB (virtual-memory peak, not a measured RAM/RSS peak).
- ReconstructMesh with hole filling disabled produced 70,534 vertices / 141,036 faces. RefineMesh with `--decimate 1 --close-holes 0` completed in 3m56s, retaining 70,537 vertices / 141,041 faces. No reference triangles were inserted.
- Refined mesh: winding consistent, finite normals, 0 non-manifold edges, 0 degenerate faces, but 41 boundary edges and not watertight. Ten same-camera silhouette checks: **95.14–96.83%** IoU.
- Vertical ray profiles across the X and Z center sections are missing 45 of 158 positions where the source reference has a surface. Mean absolute height error is 0.0433 dataset units **only on valid matched hits**; that number excludes missing hits and must not be used to claim complete accuracy. The central floor has no reconstructed intersection.
- Direct reading of the original OpenMVS PLY with view tracks found **zero dense points** in a central interior-floor region (radius 0.8, Y from 1 to 2). Thus the hole already exists in the dense data; texture cannot fix it.
- A separate `ReconstructMesh --free-space-support 1 --close-holes 0` attempt worsened silhouette to 92.13–94.14%, increased boundary edges to 162, and still missed the floor. It was rejected.
- `tools/verify_reference_visibility.py` casts rays from each original camera position toward the reference central floor `(0, 1.344624, 0)`. **All 180 rays hit a wall before reaching the floor.** The point is unobserved in both orbits. This is direct visibility evidence for that central point, not a claim that every interior surface is invisible.

No TextureMesh run was performed on this incomplete 180-image mesh: geometry failed the pre-texture check. A neutral-color geometry GLB was exported strictly for diagnosis, with status `INSUFFICIENT_COVERAGE`; it is not an approved textured scan and was not written to a Backend artifact record.

The viewer at `test-data/LR3D-CULT2/metal-cup-ly-dong-1/cpu-known-poses-180/comparison.html` compares the reconstructed geometry with the source camera views. Its separate **OBJ original / imported asset** option uses the actual original OBJ/PNG converted to `REFERENCE_IMPORTED_ASSET.glb`; the material filename mismatches were bypassed by explicitly assigning the original PNG. The UI and `provenance.json` state that this is **not** SMGS reconstruction output. It can demonstrate an existing-asset import workflow without misrepresenting the scan experiment.

To reconstruct a true interior, acquire an additional higher orbit/top-down views that actually reveal the floor, with overlapping rim/inner-wall detail for registration. The required viewing angle depends on rim height and cavity depth; verify floor visibility while capturing. Switching reconstruction engines or using a generative fill cannot recover measured detail from the currently occluded center. The source OBJ can be used as a legitimate imported museum asset if that is the chosen workflow, with provenance retained.

## Service changes and verification

### User-authorized partial textured preview

After the initial geometry failure report, the user explicitly accepted an incomplete artifact and requested its GLB preview. TextureMesh was therefore run on the same refined mesh without filling its missing floor: 141,041 faces, 24.74 seconds, one 2048×2048 atlas. The actual texture bytes were embedded into `reconstructed-partial.glb` (11,223,768 bytes), preserving UV/material definitions. The viewer now defaults to this **partial reconstruction with texture**, with separate geometry-only and original-reference options. This supersedes the earlier decision to stop before texturing for the preview; it does not change the missing-coverage evidence or claim museum approval. No average-color fill or reference-mesh substitution was performed.

The existing API contract is retained. The worker now has a configurable COLMAP camera model, rejects folded SIMPLE_RADIAL calibration and low registration coverage, verifies dense output, tries CPU PatchMatch in a clean scene after empty SGM, disables automatic hole filling/tower-mode synthetic scaffolding, and keeps refine geometry instead of automatic decimation. Texture seam options are disabled based on the isolated black-atlas tests. Native commands retain their stdout/stderr and arguments. GLB atlas embedding appends the actual PNG bytes and modifies image bufferViews only, preserving original UVs, geometry, material definitions and unlit extensions.

Verified: the actual folded camera is rejected; the PINHOLE model passes; embedded PNG bytes and original geometry/UV/material/unlit metadata are unchanged; all service modules parse; image rebuild/restart succeeds; readiness reports COLMAP, OpenMVS CPU, worker and database ready. Browser inspection verified both the neutral incomplete reconstruction and the separately labeled original imported asset. No complete textured reconstruction is claimed for the 180-image experiment.
