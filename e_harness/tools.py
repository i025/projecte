"""Native function schemas; dispatch lives in the small agent controller."""

def tool(name, description, properties, required=()):
    return {"type": "function", "function": {"name": name, "description": description,
        "parameters": {"type": "object", "properties": properties,
                       "required": list(required), "additionalProperties": False}}}


VECTOR = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}
TOOLS = [
    tool("execute_blender", "Save a scene version: replace starts empty; update edits the last successful scene without repeating prior code.",
         {"code": {"type": "string"},
          "mode": {"type": "string", "enum": ["replace", "update"], "default": "replace"}}, ["code"]),
    tool("render_scene", "Observe the saved scene. Custom camera does not change the saved scene. FOV is horizontal degrees.",
         {"view": {"type": "string", "enum": ["input", "custom"]},
          "camera_position": VECTOR, "look_at": VECTOR,
          "fov": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 180}}, ["view"]),
    tool("inspect_scene", "Inspect only your generated scene: world-space transforms, materials and active camera.", {}),
    tool("finish", "Finish using the last successful scene and its input-camera render.", {}),
]
