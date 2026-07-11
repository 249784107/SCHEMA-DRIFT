"""
Minimal stand-in for the `jsonschema` package, supporting only the subset
of Draft-7 features used by target_schema.json (type, required,
additionalProperties, enum, pattern, minItems, minimum/maximum, items,
properties). Used ONLY for local self-testing in this sandbox, which has
no network access to `pip install jsonschema`. The real task Docker image
installs the real `jsonschema` package -- see Dockerfile.
"""
import re


class ValidationError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


def _validate(instance, schema, path=""):
    t = schema.get("type")
    if t == "object":
        if not isinstance(instance, dict):
            raise ValidationError(f"{path}: expected object")
        for req in schema.get("required", []):
            if req not in instance:
                raise ValidationError(f"{path}: missing required field '{req}'")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(instance.keys()) - set(props.keys())
            if extra:
                raise ValidationError(f"{path}: additional properties not allowed: {extra}")
        for k, v in instance.items():
            if k in props:
                _validate(v, props[k], f"{path}.{k}")
    elif t == "array":
        if not isinstance(instance, list):
            raise ValidationError(f"{path}: expected array")
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise ValidationError(f"{path}: too few items")
        if "items" in schema:
            for i, item in enumerate(instance):
                _validate(item, schema["items"], f"{path}[{i}]")
    elif t == "integer":
        if not isinstance(instance, int) or isinstance(instance, bool):
            raise ValidationError(f"{path}: expected integer")
        if "minimum" in schema and instance < schema["minimum"]:
            raise ValidationError(f"{path}: below minimum")
        if "maximum" in schema and instance > schema["maximum"]:
            raise ValidationError(f"{path}: above maximum")
    elif t == "string":
        if not isinstance(instance, str):
            raise ValidationError(f"{path}: expected string")
        if "pattern" in schema and not re.match(schema["pattern"], instance):
            raise ValidationError(f"{path}: does not match pattern {schema['pattern']}")
        if "enum" in schema and instance not in schema["enum"]:
            raise ValidationError(f"{path}: '{instance}' not in enum {schema['enum']}")
    # format (date-time) intentionally not enforced by this shim


def validate(instance, schema):
    _validate(instance, schema)
