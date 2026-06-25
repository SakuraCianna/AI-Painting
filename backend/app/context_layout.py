from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .schemas import ArtworkResponse, CommandPlan, DrawingObject, OperationRequest

CANVAS_WIDTH = 1024
CANVAS_HEIGHT = 768
LayoutKind = Literal["sky", "building", "plant", "ground", "generic"]

SKY_TAGS = {"sky", "scene.background"}
GROUND_TAGS = {"grass", "scene.grass", "ground", "scene.ground"}
SCAFFOLD_TAGS = {"scene.background", "scene.grass", "scene.ground"}
FOLLOW_UP_HINTS = ("再", "还有", "继续", "接着", "加", "添加", "再画")


@dataclass(frozen=True)
class Bounds:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2

    def moved(self, dx: float, dy: float) -> Bounds:
        return Bounds(self.left + dx, self.top + dy, self.right + dx, self.bottom + dy)


@dataclass(frozen=True)
class LayoutZones:
    sky: Bounds
    ground: Bounds
    full: Bounds


@dataclass(frozen=True)
class PlacementChoice:
    left: float
    top: float
    layer_id: str
    z_index: int
    score: float


def _tags(value: dict[str, Any] | DrawingObject) -> set[str]:
    if isinstance(value, DrawingObject):
        return set(value.semantic_tags)
    return {str(tag) for tag in value.get("semantic_tags", [])}


def _has_tag_prefix(tags: set[str], prefix: str) -> bool:
    return any(tag == prefix or tag.startswith(f"{prefix}.") for tag in tags)


def _object_type(value: dict[str, Any] | DrawingObject) -> str:
    return value.type if isinstance(value, DrawingObject) else str(value.get("type", ""))


def _geometry(value: dict[str, Any] | DrawingObject) -> dict[str, Any]:
    return value.geometry if isinstance(value, DrawingObject) else dict(value.get("geometry", {}))


def _layer_id(value: dict[str, Any] | DrawingObject) -> str:
    return value.layer_id if isinstance(value, DrawingObject) else str(value.get("layer_id", "base"))


def _bounds_for_item(item_type: str, geometry: dict[str, Any]) -> Bounds:
    if item_type == "circle" or "radius" in geometry and "cx" in geometry:
        radius = float(geometry.get("radius", 50))
        cx = float(geometry.get("cx", CANVAS_WIDTH / 2))
        cy = float(geometry.get("cy", CANVAS_HEIGHT / 2))
        return Bounds(cx - radius, cy - radius, cx + radius, cy + radius)
    if item_type == "ellipse" or {"rx", "ry", "cx", "cy"}.issubset(geometry):
        rx = float(geometry.get("rx", 60))
        ry = float(geometry.get("ry", 40))
        cx = float(geometry.get("cx", CANVAS_WIDTH / 2))
        cy = float(geometry.get("cy", CANVAS_HEIGHT / 2))
        return Bounds(cx - rx, cy - ry, cx + rx, cy + ry)
    if item_type == "triangle" and "size" in geometry:
        size = float(geometry.get("size", 100))
        cx = float(geometry.get("x", CANVAS_WIDTH / 2))
        cy = float(geometry.get("y", CANVAS_HEIGHT / 2))
        height = size * 0.86
        return Bounds(cx - size / 2, cy - height / 2, cx + size / 2, cy + height / 2)
    if {"x1", "y1", "x2", "y2"}.issubset(geometry):
        x1 = float(geometry.get("x1", 0))
        y1 = float(geometry.get("y1", 0))
        x2 = float(geometry.get("x2", 0))
        y2 = float(geometry.get("y2", 0))
        return Bounds(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    if "width" in geometry or "height" in geometry or "x" in geometry or "y" in geometry:
        x = float(geometry.get("x", CANVAS_WIDTH / 2 - 50))
        y = float(geometry.get("y", CANVAS_HEIGHT / 2 - 50))
        width = float(geometry.get("width", 100))
        height = float(geometry.get("height", 100))
        return Bounds(x, y, x + width, y + height)

    points: list[dict[str, Any]] = []
    for key in ("points", "commands"):
        raw_items = geometry.get(key)
        if isinstance(raw_items, list):
            points.extend(item for item in raw_items if isinstance(item, dict))
    xs: list[float] = []
    ys: list[float] = []
    for point in points:
        for key in ("x", "x1", "x2"):
            if isinstance(point.get(key), (int, float)):
                xs.append(float(point[key]))
        for key in ("y", "y1", "y2"):
            if isinstance(point.get(key), (int, float)):
                ys.append(float(point[key]))
    if xs and ys:
        return Bounds(min(xs), min(ys), max(xs), max(ys))
    return Bounds(462, 334, 562, 434)


def _bounds_for_object(obj: dict[str, Any] | DrawingObject) -> Bounds:
    return _bounds_for_item(_object_type(obj), _geometry(obj))


def _virtual_drawing_object(obj: dict[str, Any], fallback_id: str) -> DrawingObject:
    return DrawingObject(
        id=str(obj.get("id") or fallback_id),
        type=str(obj.get("type", "")),
        name=obj.get("name"),
        geometry=dict(obj.get("geometry", {})),
        style=dict(obj.get("style", {})),
        z_index=int(obj.get("z_index", 0) or 0),
        layer_id=str(obj.get("layer_id", "base")),
        group_id=None if obj.get("group_id") is None else str(obj.get("group_id")),
        semantic_tags=[str(tag) for tag in obj.get("semantic_tags", [])],
        transform=dict(obj.get("transform", {})),
    )


def _move_coordinate(item: Any, dx: float, dy: float) -> Any:
    if not isinstance(item, dict):
        return item
    moved = dict(item)
    for key in ("x", "x1", "x2"):
        if isinstance(moved.get(key), (int, float)):
            moved[key] = round(float(moved[key]) + dx, 2)
    for key in ("y", "y1", "y2"):
        if isinstance(moved.get(key), (int, float)):
            moved[key] = round(float(moved[key]) + dy, 2)
    return moved


def _move_geometry(geometry: dict[str, Any], dx: float, dy: float) -> dict[str, Any]:
    moved = dict(geometry)
    for key in ("x", "cx", "x1", "x2"):
        if isinstance(moved.get(key), (int, float)):
            moved[key] = round(float(moved[key]) + dx, 2)
    for key in ("y", "cy", "y1", "y2"):
        if isinstance(moved.get(key), (int, float)):
            moved[key] = round(float(moved[key]) + dy, 2)
    if isinstance(moved.get("points"), list):
        moved["points"] = [_move_coordinate(point, dx, dy) for point in moved["points"]]
    if isinstance(moved.get("commands"), list):
        moved["commands"] = [_move_coordinate(command, dx, dy) for command in moved["commands"]]
    return moved


def _move_object(obj: dict[str, Any], dx: float, dy: float) -> dict[str, Any]:
    moved = dict(obj)
    moved["geometry"] = _move_geometry(dict(obj.get("geometry", {})), dx, dy)
    return moved


def _overlap_area(a: Bounds, b: Bounds) -> float:
    left = max(a.left, b.left)
    top = max(a.top, b.top)
    right = min(a.right, b.right)
    bottom = min(a.bottom, b.bottom)
    return max(0.0, right - left) * max(0.0, bottom - top)


def _overlap_ratio(a: Bounds, b: Bounds) -> float:
    return _overlap_area(a, b) / max(1.0, a.area)


def _is_background_scaffold(obj: DrawingObject) -> bool:
    tags = _tags(obj)
    if tags.intersection(SCAFFOLD_TAGS):
        return True
    return _layer_id(obj) == "background" and _bounds_for_object(obj).area > CANVAS_WIDTH * CANVAS_HEIGHT * 0.25


def _is_planned_scaffold(obj: dict[str, Any]) -> bool:
    tags = _tags(obj)
    if tags.intersection(SCAFFOLD_TAGS):
        return True
    return str(obj.get("layer_id", "base")) == "background" and _bounds_for_object(obj).area > CANVAS_WIDTH * CANVAS_HEIGHT * 0.25


def _colliders(artwork: ArtworkResponse) -> list[DrawingObject]:
    return [obj for obj in artwork.objects if not _is_background_scaffold(obj)]


def _union_bounds(bounds: list[Bounds]) -> Bounds:
    return Bounds(min(item.left for item in bounds), min(item.top for item in bounds), max(item.right for item in bounds), max(item.bottom for item in bounds))


def _group_bounds(objects: list[dict[str, Any]]) -> Bounds:
    return _union_bounds([_bounds_for_object(obj) for obj in objects])


def _infer_layout_zones(artwork: ArtworkResponse) -> LayoutZones:
    sky_bounds = [_bounds_for_object(obj) for obj in artwork.objects if _tags(obj).intersection(SKY_TAGS)]
    ground_bounds = [_bounds_for_object(obj) for obj in artwork.objects if _tags(obj).intersection(GROUND_TAGS)]
    sky = _union_bounds(sky_bounds) if sky_bounds else Bounds(0, 0, artwork.width, artwork.height * 0.55)
    ground = _union_bounds(ground_bounds) if ground_bounds else Bounds(0, artwork.height * 0.58, artwork.width, artwork.height)
    return LayoutZones(sky=sky, ground=ground, full=Bounds(0, 0, artwork.width, artwork.height))


def _classify_tags(tags: set[str]) -> LayoutKind:
    if "cloud" in tags or "sun" in tags or _has_tag_prefix(tags, "shape.boolean.moon"):
        return "sky"
    if _has_tag_prefix(tags, "house"):
        return "building"
    if "tree" in tags or _has_tag_prefix(tags, "tree"):
        return "plant"
    if _has_tag_prefix(tags, "shape.boolean.flower") or "flower" in tags or "bench" in tags or "person" in tags or _has_tag_prefix(tags, "person"):
        return "ground"
    return "generic"


def _classify_object(obj: dict[str, Any]) -> LayoutKind:
    return _classify_tags(_tags(obj))


def _classify_group(objects: list[dict[str, Any]]) -> LayoutKind:
    tags: set[str] = set()
    for obj in objects:
        tags.update(_tags(obj))
    return _classify_tags(tags)


def _z_index_for(kind: LayoutKind, artwork: ArtworkResponse) -> int:
    if kind == "sky":
        sky_count = sum(1 for obj in artwork.objects if _classify_tags(_tags(obj)) == "sky")
        return 5 + sky_count
    if kind == "building":
        return 30
    if kind in {"plant", "ground"}:
        return 45
    return max((item.z_index for item in artwork.objects), default=-1) + 1


def _layer_for(kind: LayoutKind, original_layer: str) -> str:
    if kind == "sky":
        return "background"
    if kind == "building":
        return "middle"
    if kind in {"plant", "ground"}:
        return "foreground"
    return original_layer


def _clamp(value: float, lower: float, upper: float) -> float:
    if upper < lower:
        return lower
    return max(lower, min(value, upper))


def _slot_positions(kind: LayoutKind, bounds: Bounds, artwork: ArtworkResponse, zones: LayoutZones) -> list[tuple[float, float]]:
    if kind == "sky":
        bottom_limit = min(zones.sky.bottom, zones.ground.top - 110, artwork.height * 0.42)
        top_min = max(24.0, zones.sky.top + 24)
        top_max = max(top_min, bottom_limit - bounds.height)
        raw_slots = [
            (artwork.width * 0.14 - bounds.width / 2, top_min + 20),
            (artwork.width * 0.74 - bounds.width / 2, top_min + 30),
            (artwork.width * 0.5 - bounds.width / 2, top_min + 5),
            (artwork.width * 0.32 - bounds.width / 2, top_min + 70),
            (artwork.width * 0.86 - bounds.width / 2, top_min + 80),
        ]
        return [(_clamp(left, 24, artwork.width - bounds.width - 24), _clamp(top, top_min, top_max)) for left, top in raw_slots]

    if kind == "building":
        body_top = max(360.0, zones.ground.top - min(70.0, bounds.height * 0.22))
        raw_slots = [
            (artwork.width * 0.16 - bounds.width / 2, body_top),
            (artwork.width * 0.74 - bounds.width / 2, body_top),
            (artwork.width * 0.45 - bounds.width / 2, body_top),
            (artwork.width * 0.28 - bounds.width / 2, max(330.0, body_top - 50)),
            (artwork.width * 0.68 - bounds.width / 2, max(330.0, body_top - 50)),
        ]
        return [(_clamp(left, 24, artwork.width - bounds.width - 24), _clamp(top, 260, artwork.height - bounds.height - 24)) for left, top in raw_slots]

    if kind == "plant":
        top = max(zones.ground.top - min(bounds.height - 10, 110), zones.sky.bottom - 110)
        raw_slots = [
            (artwork.width * 0.18 - bounds.width / 2, top),
            (artwork.width * 0.82 - bounds.width / 2, top),
            (artwork.width * 0.32 - bounds.width / 2, top + 35),
            (artwork.width * 0.68 - bounds.width / 2, top + 35),
            (artwork.width * 0.5 - bounds.width / 2, top),
        ]
        return [
            (_clamp(left, 18, artwork.width - bounds.width - 18), _clamp(slot_top, 300, artwork.height - bounds.height - 18)) for left, slot_top in raw_slots
        ]

    if kind == "ground":
        top = max(zones.ground.top, artwork.height * 0.55)
        raw_slots = [
            (artwork.width * 0.24 - bounds.width / 2, top + 12),
            (artwork.width * 0.76 - bounds.width / 2, top + 12),
            (artwork.width * 0.5 - bounds.width / 2, top + 35),
            (artwork.width * 0.36 - bounds.width / 2, top + 70),
            (artwork.width * 0.64 - bounds.width / 2, top + 70),
        ]
        return [
            (_clamp(left, 18, artwork.width - bounds.width - 18), _clamp(slot_top, zones.ground.top, artwork.height - bounds.height - 18))
            for left, slot_top in raw_slots
        ]

    raw_slots = [
        (artwork.width * 0.25 - bounds.width / 2, artwork.height * 0.5 - bounds.height / 2),
        (artwork.width * 0.75 - bounds.width / 2, artwork.height * 0.5 - bounds.height / 2),
        (artwork.width * 0.5 - bounds.width / 2, artwork.height * 0.25 - bounds.height / 2),
        (artwork.width * 0.5 - bounds.width / 2, artwork.height * 0.75 - bounds.height / 2),
        (artwork.width * 0.25 - bounds.width / 2, artwork.height * 0.75 - bounds.height / 2),
        (artwork.width * 0.75 - bounds.width / 2, artwork.height * 0.75 - bounds.height / 2),
    ]
    return [(_clamp(left, 18, artwork.width - bounds.width - 18), _clamp(top, 18, artwork.height - bounds.height - 18)) for left, top in raw_slots]


def _current_position_fits_kind(kind: LayoutKind, bounds: Bounds, artwork: ArtworkResponse, zones: LayoutZones) -> bool:
    if bounds.left < 0 or bounds.top < 0 or bounds.right > artwork.width or bounds.bottom > artwork.height:
        return False
    if kind == "sky":
        return bounds.bottom <= min(zones.ground.top - 30, artwork.height * 0.52)
    if kind in {"building", "plant", "ground"}:
        return bounds.bottom >= zones.ground.top - 70 and bounds.top >= zones.sky.top + 40
    return True


def _score_slot(kind: LayoutKind, candidate_bounds: Bounds, colliders: list[DrawingObject], artwork: ArtworkResponse, slot_index: int) -> float:
    if candidate_bounds.left < 0 or candidate_bounds.top < 0 or candidate_bounds.right > artwork.width or candidate_bounds.bottom > artwork.height:
        return 1_000_000.0
    overlap_penalty = sum(_overlap_ratio(candidate_bounds, _bounds_for_object(existing)) for existing in colliders) * 1000
    center_bias = abs(candidate_bounds.center_x - artwork.width / 2) / max(1.0, artwork.width) * 5
    if kind in {"sky", "plant", "ground", "building"}:
        center_bias = 0
    return overlap_penalty + center_bias + slot_index * 0.1


def _choose_placement(kind: LayoutKind, bounds: Bounds, artwork: ArtworkResponse, zones: LayoutZones) -> PlacementChoice:
    colliders = _colliders(artwork)
    slots: list[tuple[float, float]] = []
    if _current_position_fits_kind(kind, bounds, artwork, zones):
        slots.append((bounds.left, bounds.top))
    slots.extend(_slot_positions(kind, bounds, artwork, zones))
    choices = [
        PlacementChoice(
            left=left,
            top=top,
            layer_id=_layer_for(kind, "base"),
            z_index=_z_index_for(kind, artwork),
            score=_score_slot(kind, bounds.moved(left - bounds.left, top - bounds.top), colliders, artwork, index),
        )
        for index, (left, top) in enumerate(slots)
    ]
    return min(choices, key=lambda choice: choice.score)


def _place_single_object(obj: dict[str, Any], artwork: ArtworkResponse, zones: LayoutZones, *, avoid_generic_overlap: bool) -> dict[str, Any]:
    kind = _classify_object(obj)
    if kind == "generic" and not avoid_generic_overlap:
        return obj

    bounds = _bounds_for_object(obj)
    choice = _choose_placement(kind, bounds, artwork, zones)
    moved = _move_object(obj, choice.left - bounds.left, choice.top - bounds.top)
    moved["layer_id"] = _layer_for(kind, str(obj.get("layer_id", "base")))
    moved["z_index"] = choice.z_index
    tags = _tags(moved)
    if kind == "sky":
        tags.add("sky")
    elif kind in {"plant", "ground"}:
        tags.add("grounded")
    if tags:
        moved["semantic_tags"] = sorted(tags)
    return moved


def _unique_group_id(base_group_id: str | None, artwork: ArtworkResponse) -> str | None:
    if not base_group_id:
        return None
    existing = {obj.group_id for obj in artwork.objects if obj.group_id}
    if base_group_id not in existing:
        return base_group_id
    suffix = 2
    while f"{base_group_id}-{suffix}" in existing:
        suffix += 1
    return f"{base_group_id}-{suffix}"


def _place_group(objects: list[dict[str, Any]], artwork: ArtworkResponse, zones: LayoutZones) -> list[dict[str, Any]]:
    kind = _classify_group(objects)
    bounds = _group_bounds(objects)
    choice = _choose_placement(kind, bounds, artwork, zones)
    dx = choice.left - bounds.left
    dy = choice.top - bounds.top
    placed: list[dict[str, Any]] = []
    for relative_index, obj in enumerate(objects):
        moved = _move_object(obj, dx, dy)
        moved["layer_id"] = _layer_for(kind, str(obj.get("layer_id", "base")))
        moved["z_index"] = choice.z_index + relative_index
        tags = _tags(moved)
        if kind in {"plant", "ground"}:
            tags.add("grounded")
        if kind == "sky":
            tags.add("sky")
        if tags:
            moved["semantic_tags"] = sorted(tags)
        placed.append(moved)
    return placed


def _contextualized_add_operations(operations: list[OperationRequest], artwork: ArtworkResponse, *, avoid_generic_overlap: bool) -> list[OperationRequest]:
    virtual_artwork = artwork.model_copy(deep=True)
    next_operations: list[OperationRequest] = []
    index = 0
    while index < len(operations):
        operation = operations[index]
        if operation.operation_type != "add_object" or not isinstance(operation.payload.get("object"), dict):
            next_operations.append(operation)
            index += 1
            continue

        obj = dict(operation.payload["object"])
        if _is_planned_scaffold(obj):
            next_operations.append(operation)
            virtual_artwork.objects.append(_virtual_drawing_object(obj, f"planned-{index}"))
            index += 1
            continue

        zones = _infer_layout_zones(virtual_artwork)
        group_id = obj.get("group_id")
        if group_id and _classify_object(obj) != "generic":
            group_ops: list[OperationRequest] = []
            group_objects: list[dict[str, Any]] = []
            while index < len(operations):
                candidate = operations[index]
                candidate_obj = candidate.payload.get("object")
                if candidate.operation_type != "add_object" or not isinstance(candidate_obj, dict) or candidate_obj.get("group_id") != group_id:
                    break
                group_ops.append(candidate)
                group_objects.append(dict(candidate_obj))
                index += 1
            placed = _place_group(group_objects, virtual_artwork, zones)
            unique_group_id = _unique_group_id(str(group_id), virtual_artwork)
            for source_operation, placed_object in zip(group_ops, placed, strict=True):
                placed_object["group_id"] = unique_group_id
                next_operations.append(source_operation.model_copy(update={"payload": {"object": placed_object}}))
                virtual_artwork.objects.append(_virtual_drawing_object(placed_object, f"planned-{len(virtual_artwork.objects)}"))
            continue

        placed_obj = _place_single_object(obj, virtual_artwork, zones, avoid_generic_overlap=avoid_generic_overlap)
        next_operations.append(operation.model_copy(update={"payload": {"object": placed_obj}}))
        virtual_artwork.objects.append(_virtual_drawing_object(placed_obj, f"planned-{len(virtual_artwork.objects)}"))
        index += 1
    return next_operations


def _is_open_vector_scene_plan(plan: CommandPlan) -> bool:
    if plan.scene_plan is None:
        return False
    if plan.scene_plan.intent == "compose_open_scene":
        return True
    return any(step.target.get("domain") == "open_vector_scene" for step in plan.scene_plan.steps)


def adjust_plan_for_existing_artwork(plan: CommandPlan, artwork: ArtworkResponse) -> CommandPlan:
    if not any(operation.operation_type == "add_object" for operation in plan.operations):
        return plan
    if not artwork.objects and not _is_open_vector_scene_plan(plan):
        return plan
    adjusted = plan.model_copy(deep=True)
    avoid_generic_overlap = any(keyword in plan.normalized_text for keyword in FOLLOW_UP_HINTS)
    adjusted.operations = _contextualized_add_operations(list(adjusted.operations), artwork, avoid_generic_overlap=avoid_generic_overlap)
    return adjusted
