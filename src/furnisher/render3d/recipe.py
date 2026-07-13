"""Room image generation recipe (docs/07).

Inputs per room: the room-crop grounding render (image 1), then product photos in legend
order. Outputs are cached by content hash — unchanged rooms never regenerate. Every render
dumps its prompt next to the image so recipe iteration stays inspectable.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from furnisher.agent.models import StyleProfile
from furnisher.render2d import render_room_crop

log = logging.getLogger(__name__)

RECIPE_VERSION = "v1"
MAX_PRODUCT_PHOTOS = 5

PROMPT_TEMPLATE = """\
Generate ONE photorealistic interior photograph of a real room.

Image 1 is a top-down schematic plan of the room. Numbered rectangles are furniture
footprints; the short line from each number shows which way that item faces. The camera
position and direction are marked in red.
{photo_note}

Room: {room_type}, {width:.1f} × {depth:.1f} m, ceiling {ceiling:.1f} m.

Furniture (numbers match the plan):
{legend}

Style: {style}.

Camera: {camera}.

Rules:
- Every piece of furniture must appear at the plan's position and orientation, with
  believable real-world scale for the given dimensions.
- Furniture with a reference photo must match that exact product: same shape, color,
  material. Do not substitute different designs.
- Walls, openings and windows exactly as in the plan; daylight comes through the windows.
- No people, no text, no watermarks. Natural photographic look, realistic materials.
{feedback}"""


def svg_to_png(svg: str) -> bytes:
    import resvg_py

    return bytes(resvg_py.svg_to_bytes(svg_string=svg))


def _style_text(style: StyleProfile | None) -> str:
    if style is None:
        return "bright, simple, real-estate-photo neutral"
    bits = []
    if style.style_tags:
        bits.append(", ".join(style.style_tags))
    if style.palette:
        bits.append("palette " + ", ".join(style.palette))
    if style.materials:
        bits.append("materials " + ", ".join(style.materials))
    if style.avoid:
        bits.append("avoid " + ", ".join(style.avoid))
    if style.notes:
        bits.append(style.notes)
    return "; ".join(bits) or "neutral"


APARTMENT_PROMPT = """\
Generate ONE 3D isometric cutaway "dollhouse" render of this apartment, viewed from above
at an angle, with the ceiling removed so every room is visible.

This is a SINGLE-STORY apartment: ONE floor only. All rooms are on the same level,
side by side in exactly the arrangement shown in the plan — do NOT stack them vertically.

Image 1 is the furnished floor plan: room names, dimensions, and every piece of furniture
drawn to scale at its exact position. Reproduce the same room adjacencies, wall positions,
door/window openings, and furniture arrangement faithfully, keeping the plan's proportions.

Style: {style}.
Warm, appealing architectural-visualization look, soft daylight, subtle shadows.
No people, no text overlays, no watermark.
{feedback}"""


def generate_apartment_image(llm, catalog, project, feedback: str = "", force: bool = False):
    """Whole-apartment isometric overview, grounded on the furnished plan render."""
    from furnisher.render2d import render_plan

    key = hashlib.sha256(
        json.dumps(
            {
                "recipe": RECIPE_VERSION,
                "placements": [p.model_dump(mode="json") for p in project.placements],
                "style": project.meta.get("style_profile"),
                "feedback": feedback,
                "kind": "apartment",
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:10]
    out_dir = project.path / "renders" / "rooms"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"apartment-{key}.png"
    if out_path.exists() and not force:
        return out_path

    style = project.meta.get("style_profile")
    style_profile = StyleProfile.model_validate(style) if style else None
    prompt = APARTMENT_PROMPT.format(
        style=_style_text(style_profile),
        feedback=f"- User feedback on the previous attempt: {feedback}" if feedback else "",
    )
    svg = render_plan(project.plan, placements=project.placements, catalog=catalog)
    image = llm.generate_image([prompt, (svg_to_png(svg), "image/png")])
    out_path.write_bytes(image)
    (out_dir / f"apartment-{key}.prompt.txt").write_text(prompt, encoding="utf-8")
    return out_path


def generate_room_image(
    llm,
    catalog,
    project,
    room_id: str,
    feedback: str = "",
    force: bool = False,
) -> Path:
    room = project.plan.room(room_id)
    placements = [p for p in project.placements if p.room == room_id]
    if not placements:
        raise ValueError(f"room {room_id!r} has no placements — furnish it first")

    svg, legend, camera = render_room_crop(project.plan, room_id, placements, catalog)
    style = project.meta.get("style_profile")
    style_profile = StyleProfile.model_validate(style) if style else None

    key = hashlib.sha256(
        json.dumps(
            {
                "recipe": RECIPE_VERSION,
                "placements": [p.model_dump(mode="json") for p in placements],
                "style": style,
                "feedback": feedback,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:10]
    out_dir = project.path / "renders" / "rooms"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{room_id}-{key}.png"
    if out_path.exists() and not force:
        log.info("room image cached: %s", out_path)
        return out_path

    # product photos in legend order (legend is sorted biggest-first, like the crop render)
    photos: list[Path] = []
    photo_lines: list[str] = []
    for line in legend:
        number = line.split(".", 1)[0]
        placement = sorted(
            placements,
            key=lambda p: catalog.get(p.item_ref).width_m * catalog.get(p.item_ref).depth_m,
            reverse=True,
        )[int(number) - 1]
        if len(photos) < MAX_PRODUCT_PHOTOS:
            paths = catalog.image_paths(placement.item_ref, max_images=1)
            if paths:
                photos.append(paths[0])
                photo_lines.append(f"  image {len(photos) + 1} = product photo of item {number}")

    xs = [p[0] for p in room.polygon]
    ys = [p[1] for p in room.polygon]
    photo_note = (
        "The following images are product photos of specific items:\n" + "\n".join(photo_lines)
        if photo_lines
        else "No product photos attached; render furniture matching the legend descriptions."
    )
    prompt = PROMPT_TEMPLATE.format(
        photo_note=photo_note,
        room_type=room.type.value.replace("_", " "),
        width=max(xs) - min(xs),
        depth=max(ys) - min(ys),
        ceiling=room.ceiling_height or project.plan.ceiling_height,
        legend="\n".join(legend),
        style=_style_text(style_profile),
        camera=camera,
        feedback=f"- User feedback on the previous attempt: {feedback}" if feedback else "",
    )

    content: list = [prompt, (svg_to_png(svg), "image/png")]
    content.extend(photos)
    image = llm.generate_image(content)

    out_path.write_bytes(image)
    (out_dir / f"{room_id}-{key}.prompt.txt").write_text(prompt, encoding="utf-8")
    (out_dir / f"{room_id}-{key}.plan.svg").write_text(svg, encoding="utf-8")
    return out_path
