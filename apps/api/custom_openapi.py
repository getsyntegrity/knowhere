from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def custom_openapi(app: FastAPI):
    if app.openapi_schema:
        return app.openapi_schema

    # 1. Get default OpenAPI dictionary
    openapi_schema = get_openapi(
        title="Custom API",
        version="1.0.0",
        routes=app.routes,
    )

    # 2. Safely Dereference while keeping schema flattened
    # We use a 'seen' set to track recursive references, similar to how JSON.stringify handles circular structures.

    def dereference(schema: dict, definitions: dict, seen: set = None) -> dict:
        """
        Recursively resolve $ref pointers.
        If a circular reference is detected (same model visited twice in the path),
        it stops recursion and leaves the $ref as is.
        """
        if seen is None:
            seen = set()

        if isinstance(schema, list):
            return [dereference(item, definitions, seen.copy()) for item in schema]

        if isinstance(schema, dict):
            if "$ref" in schema:
                ref_path = schema["$ref"]
                if ref_path.startswith("#/components/schemas/"):
                    model_name = ref_path.split("/")[-1]

                    # Cycle detection: if we have already seen this model in the current traversal path, stop!
                    if model_name in seen:
                        return schema  # Return original { $ref: ... } to avoid infinite loop

                    if model_name in definitions:
                        # Add current model to seen path
                        new_seen = seen.copy()
                        new_seen.add(model_name)

                        # Dereference the target definition
                        return dereference(
                            definitions[model_name], definitions, new_seen
                        )

                return schema

            # Helper for processing dict items
            return {
                k: dereference(v, definitions, seen.copy()) for k, v in schema.items()
            }

        return schema

    try:
        # Extract existing definitions to use for lookup
        definitions = openapi_schema.get("components", {}).get("schemas", {})

        # Dereference the paths section (main entry point)
        resolved_paths = dereference(openapi_schema.get("paths", {}), definitions)
        openapi_schema["paths"] = resolved_paths

    except Exception as e:
        print(f"Warning: OpenAPI dereferencing failed: {e}")
        # Fallback to original schema
        pass

    app.openapi_schema = openapi_schema
    return app.openapi_schema
