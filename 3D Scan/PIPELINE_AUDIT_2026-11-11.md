# 3D Reconstruction pipeline audit — 2026-11-11

## Result

The original API job `6d9f771a-acb1-4a57-a483-6741ae41a56e` did **not** produce a dense reconstruction even though it reached `REVIEW_REQUIRED`. COLMAP registered all 40 images and produced 4,037 sparse points. OpenMVS SGM logged `40 depth-maps, 0 depths, 0 points` and did not write `scene_dense.ply`. The worker did not check this and `ReconstructMesh` used the sparse points still present in `scene_dense.mvs`. The previous claim that this job completed a dense CPU scan is corrected.

The input set is 40 Blender-rendered views of a different metal cup/chalice, not the physical ceramic jar in the user's three photos. The output is not a validated museum model.

## COLMAP cameras and image mapping

- COLMAP: 40/40 registered; 4,037 sparse points; 18,270 observations; mean reprojection error 0.600 px.
- All input views are 512×512. COLMAP generated 40 camera models, with 39 distinct focal lengths. OpenMVS imported all 40 images as calibrated. Image names remained `image_001.png` through `image_040.png`; the uploaded `image_001.png` hash matches source `view_001_cam1.png`.
- A separate `--single_camera 1` COLMAP run also registered 40/40, with 4,251 sparse points and 1.086 px mean reprojection error. SGM still produced 0 points. Thus shared intrinsics alone did not solve dense reconstruction.

## Mesh diagnosis

Original sparse-derived rough mesh: 3,177 vertices / 6,350 faces. Refined PLY: 4,908 vertices / 9,812 faces. Both were watertight and winding-consistent with 0 boundary edges, 0 non-manifold edges, 0 degenerate faces, and finite face normals. The reported GLB has 6,327 vertices because UV seams duplicate vertices. Its 2,664 topological boundary edges are from those UV splits; the checks do not establish 2,664 real holes in the pre-texture geometry. The visible mismatch is primarily caused by missing dense geometry plus poor texture coverage.

## Texture and material diagnosis

- OpenMVS wrote a 1024×1024 atlas as external `model_0.png`; the GLB referenced that PNG instead of embedding it. The Scan model endpoint returns only GLB, so that material could be lost outside a folder containing the sidecar.
- Pixel counts in the original atlas: about 47.6% OpenMVS default orange `(255,127,39)` and 28.1% black. Correct-convention UV face-centroid sampling: about 81.5% of faces sampled orange fallback, 10.3% black, and 8.2% another source-image pixel. This explains the flat orange/brown appearance; it is not a viewer light issue. Percentages are approximate face-center samples, not area-weighted.
- Seam leveling was already enabled by TextureMesh defaults. On a separately generated CPU PatchMatch mesh, setting `--virtual-face-images 3 --cost-smoothness-ratio 0.5` improved sampled non-fallback face centers from 16.6% to 50.9%; orange fallback fell from 70.8% to 13.2%, while black samples remained 35.9%. Atlas stayed 1024×1024 with 512×512 source views. No average-color fill was used.

## CPU reconstruction experiment

On the same-camera scene, OpenMVS CPU PatchMatch (`--fusion-mode 0 --resolution-level 1 --max-threads 4`) completed in 5m17s and saved 55,561 fused points after ROI trimming. It created a rough mesh of 37,455 vertices / 74,810 faces and a refined mesh of 6,740 vertices / 13,243 faces. A browser comparison page uses COLMAP poses to show each source image beside the corresponding model camera view:

`test-data/LR3D-CULT2/metal-cup-ly-dong-1/cpu-patchmatch-single-camera/comparison.html`

The pose-aligned view exposes large screen-space/background geometry and texture mismatch. The result is a diagnostic candidate, not an acceptable final scan. The test data cannot establish how well real iPhone photos of the jar reconstruct.

## Code changes

- COLMAP now uses one camera model for a same-sequence capture.
- After SGM, the worker checks the dense PLY vertex count. If empty, it re-imports COLMAP into a clean workspace and retries CPU PatchMatch at half resolution with four threads.
- If SGM and PatchMatch both produce no dense points, the job fails with a clear message and cannot mesh sparse points as a surface artifact.
- TextureMesh uses the tested virtual-face/smoothness settings, preserves full source resolution, and caps atlas texture size at 4096. Follow-up isolation below supersedes the earlier decision to retain seam leveling: both seam options are now disabled.
- After texturing, the worker re-exports GLB with the PNG atlas embedded, preserving the current one-file API response.
- Removed the median-color and gap-fill trial outputs and redirected the prior preview page to the source/model comparison.

## Latest API verification

Fresh API job `b21737db-6a72-42a3-89f7-d3fe9fa24dea` used 40 rendered sample views. `automatic_reconstructor` produced six separate sparse models; the best contains 25/40 images (the others contain 24, 24, 13, 10, and 10 registered images). The service chose the best model and imported only its 25 images. OpenMVS SGM again produced no dense points. CPU PatchMatch did produce 106,006 fused points in 2m41s; its raw mesh had 52,454 vertices / 104,806 faces, and the refined mesh had 9,862 vertices / 19,585 faces. The refined mesh had 127 boundary edges, no non-manifold or degenerate faces, and finite normals. These counts show PatchMatch ran, but do not establish that its geometry corresponds to the artifact.

TextureMesh completed with a 2048×2048 atlas. The GLB contained an embedded PNG bufferView and a PBR material; the GLB itself was about 1.48 MB. However, UV face-center samples from this job did not establish trustworthy source-image coverage (the raw TextureMesh output showed the same issue before embedding). Combined with only 25/40 registered views, six disconnected candidate models, the boundary edges, and the pose-aligned geometry mismatch seen in the separate comparison, this is not an acceptable reconstruction. The API record was corrected from `REVIEW_REQUIRED` to `FAILED`, and `model_path`/`model_type` were cleared so the model endpoint no longer advertises the candidate. The raw job data and logs remain available in the container for diagnosis.

The current worker now rejects this input at the 80% registration-coverage gate before dense reconstruction. The already completed job predates that gate; the manual database correction prevents its former false-positive review state. The service image rebuilt successfully. `compileall` could not write bytecode under the container's unprivileged user due to a read-only source directory, while importing `app.reconstruction` successfully loaded the module and its registered-image counter returned the expected counts (25, 24, 24, 13, 10, 10).

## Follow-up: invalid camera fit and seam-leveling corruption

The initial comparison page was incorrect: its JSON used 512×512 source-image dimensions with the calibration used by OpenMVS after undistortion (1024×1024). The page now uses the actual undistorted image, its full calibration including principal point, and offers an explicit toggle to the original distorted image. The earlier screenshot alone was therefore not a valid same-projection comparison. GLB vertex bounds match the PLY bounds and the GLB has no node transform; a hidden GLB axis transform does not explain the discrepancy.

The shared-camera COLMAP fit has SIMPLE_RADIAL parameters `f=1307.771`, `cx=cy=256`, `k=-7.595533` for the 512×512 inputs. Its radial map has nonpositive derivative within the image extent. The exported 1024×1024 undistorted image visibly contains a large stretched ring/duplicated artifact around the central object; this corrupted image is already the input used by OpenMVS. A low reprojection error and 40/40 registrations did not guarantee physically valid calibration. The worker now checks the SIMPLE_RADIAL fit before undistortion and rejects a folded mapping. Other camera models are not covered by this additional radial-fold check.

On the exact same dense mesh, three additional TextureMesh runs isolated the seam options. Atlas pixels with all RGB channels below 5: existing tuned output (both seams on) 34.65%, both off 0.00%, global only 35.19%, local only 26.34%. The no-seam atlas preserves actual input colors and still contains large gray background patches; no pixel recoloring, average-color fill, or geometry filling was used. These measurements establish that seam processing creates the black output on this candidate, while disabling it does not repair the bad geometry/calibration. Both seam options are disabled in the worker based on this observed failure. The corrected browser page displays `seam-off.glb` as a failed diagnostic model, not a museum-ready output.
