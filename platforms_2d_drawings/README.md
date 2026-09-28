# Platforms – 2D drawings (DXF)

Generated from the SpaceClaim model `platofrms.scdocx`. It contains surface bodies and line bodies with cross-sections.

## Files (`dxf/`, units mm, Z up)
| File | Content |
|---|---|
| `PLATFORMS_ALL_VIEWS_A0.dxf` | All views on one A0 sheet at 1:50 (third-angle layout, frame, title block, notes) |
| `PLAN_UPPER.dxf` | Plan view (looking -Z), upper platform only |
| `PLAN_LOWER.dxf` | Plan view (looking -Z), lower platform only |
| `ELEVATION.dxf` | Elevation from +X (looking -X), both platforms |
| `SIDE_VIEW.dxf` | Side view from +Y (looking -Y), both platforms |

The two platforms overlap in plan, so each one gets its own plan view. They don't overlap in elevation or side view, so both appear together there.

## Layers
- `PLATE_VISIBLE` / `PLATE_HIDDEN`: surface bodies. Hidden lines are dashed.
- `PROFILE_VISIBLE` / `PROFILE_HIDDEN`: line bodies drawn with their true cross-section (flat bars, face plates, pipe braces).
- `DIMENSIONS`, `LEVELS`, `TEXT`, `AXES`, `FRAME`.

Freeze the `*_HIDDEN` layers if you want a drawing with visible lines only.

## Notes
- Plates are drawn at their mid/reference surface. Plate thickness is not drawn.
- Coordinates:
  - Elevation and side view use true Z levels (screen Y = Z in mm).
  - Plan views: screen X = model Y, screen Y = -model X.
  - Each individual file keeps these true coordinates. On the A0 sheet the views are offset.
- `scripts/` holds the converter: it reads the .scdocx tessellation and beam definitions, then does the hidden-line projection and writes the DXF with ezdxf.
