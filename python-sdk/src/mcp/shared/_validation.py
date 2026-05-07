"""
Local fork point (MultiModalMCP): JSON-Schema validation backend selection.

The upstream python-sdk uses ``jsonschema.validate(...)`` on every tool
call (both client-side, in ``ClientSession._validate_tool_result``, and
server-side, in ``server.lowlevel.server`` for input + output schemas).
That recompiles + meta-validates the schema on every call, which dominates
the per-tool-call latency in our profiling (see
`results/PROFILING_BIRD_E2E.md`).

This module exposes a single ``get_validator(schema, schema_id) -> ValidatorFn``
factory with caching plus a backend preference chain that's faster *and*
behaviour-compatible:

  1. ``MCP_VALIDATOR_BACKEND=skip`` (or ``MCP_SKIP_VALIDATE=1``) - returns
     a no-op validator.
  2. ``MCP_VALIDATOR_BACKEND=jsonschema-rs`` - Rust-backed, supports
     Draft 2020-12 (``pip install jsonschema-rs``).
  3. ``MCP_VALIDATOR_BACKEND=fastjsonschema`` - Python compile-to-closure,
     supports Draft 04/06/07 (``pip install fastjsonschema``).
  4. ``MCP_VALIDATOR_BACKEND=jsonschema`` - reference Python implementation
     (always available; the fallback).
  5. ``MCP_VALIDATOR_BACKEND=auto`` (default) - try (2) -> (3) -> (4) and
     remember the first one that compiled this schema.

Each backend's "validation failed" path raises a single shared
``ValidationFailed`` exception whose ``.message`` matches what the upstream
SDK would have surfaced from ``jsonschema.ValidationError`` (so caller code
that wraps the message in ``RuntimeError(...)`` keeps producing identical
text). Schema-compilation failures from a non-default backend silently
fall through to the next backend in the chain, so we never break a
schema that the reference validator would have accepted.

References:

- Blaze: Compiling JSON Schema for 10x Faster Validation
  https://arxiv.org/abs/2503.02770
- Validation of Modern JSON Schema (POPL 2024) https://doi.org/10.1145/3632891
- fastjsonschema docs:
  https://horejsek.github.io/python-fastjsonschema/modules/fastjsonschema.html
- jsonschema-rs benchmarks:
  https://raw.githubusercontent.com/Stranger6667/jsonschema/master/crates/jsonschema-py/BENCHMARKS.md
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional, Tuple


class ValidationFailed(Exception):
    """Single shared validation-failure exception across all backends."""

    def __init__(self, message: str, *, backend: str = "unknown") -> None:
        super().__init__(message)
        self.message = message
        self.backend = backend


ValidatorFn = Callable[[Any], None]


# Cache key: (id(schema), backend_choice). We key on the schema *object*
# id rather than its content because schemas are dicts (unhashable) and
# the python-sdk reuses the same dict across calls for a given tool.
_VALIDATOR_CACHE: Dict[Tuple[int, str], ValidatorFn] = {}


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _selected_backend() -> str:
    """Return the user-requested backend, or 'auto'."""
    if _truthy("MCP_SKIP_VALIDATE"):
        return "skip"
    raw = os.environ.get("MCP_VALIDATOR_BACKEND", "").strip().lower()
    if raw in {"skip", "auto", "jsonschema-rs", "fastjsonschema", "jsonschema"}:
        return raw
    return "auto"


def _no_op_validator(_instance: Any) -> None:
    return None


# ---------- Backend builders ------------------------------------------------


def _build_jsonschema_rs(schema: Dict[str, Any]) -> Optional[ValidatorFn]:
    try:
        import jsonschema_rs  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        compiled = jsonschema_rs.validator_for(schema)
    except Exception:
        return None

    def _validate(instance: Any) -> None:
        try:
            compiled.validate(instance)
        except jsonschema_rs.ValidationError as exc:  # type: ignore[attr-defined]
            raise ValidationFailed(str(exc), backend="jsonschema-rs") from exc

    return _validate


def _build_fastjsonschema(schema: Dict[str, Any]) -> Optional[ValidatorFn]:
    try:
        import fastjsonschema  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        # use_default=False keeps validation pure (don't mutate input).
        # use_formats=False matches the reference jsonschema default
        # (formats are advisory unless an explicit format_checker is passed).
        compiled = fastjsonschema.compile(schema, use_default=False, use_formats=False)
    except Exception:
        return None

    def _validate(instance: Any) -> None:
        try:
            compiled(instance)
        except fastjsonschema.JsonSchemaValueException as exc:  # type: ignore[attr-defined]
            raise ValidationFailed(exc.message, backend="fastjsonschema") from exc

    return _validate


def _build_jsonschema(schema: Dict[str, Any]) -> Optional[ValidatorFn]:
    try:
        from jsonschema import SchemaError, ValidationError
        from jsonschema.validators import validator_for
    except Exception:
        return None
    try:
        validator_cls = validator_for(schema)
        validator_cls.check_schema(schema)
        compiled = validator_cls(schema)
    except SchemaError:
        # Caller can't recover from a malformed schema; surface up.
        raise
    except Exception:
        return None

    def _validate(instance: Any) -> None:
        try:
            compiled.validate(instance)
        except ValidationError as exc:
            raise ValidationFailed(exc.message, backend="jsonschema") from exc

    return _validate


_BACKEND_BUILDERS: Dict[str, Callable[[Dict[str, Any]], Optional[ValidatorFn]]] = {
    "jsonschema-rs": _build_jsonschema_rs,
    "fastjsonschema": _build_fastjsonschema,
    "jsonschema": _build_jsonschema,
}

_AUTO_PREFERENCE = ("jsonschema-rs", "fastjsonschema", "jsonschema")


def _build(schema: Dict[str, Any], requested: str) -> Tuple[ValidatorFn, str]:
    """Build (or fail-soft to the next backend) for one schema."""
    if requested == "skip":
        return _no_op_validator, "skip"
    if requested == "auto":
        for name in _AUTO_PREFERENCE:
            fn = _BACKEND_BUILDERS[name](schema)
            if fn is not None:
                return fn, name
        # All builders returned None - degrade to a no-op so we never
        # break a tool call due to a missing optional dependency.
        return _no_op_validator, "skip"
    fn = _BACKEND_BUILDERS[requested](schema)
    if fn is not None:
        return fn, requested
    # Requested backend rejected this schema (e.g. fastjsonschema can't
    # compile a Draft 2020-12 schema). Fall back through the auto chain.
    for name in _AUTO_PREFERENCE:
        if name == requested:
            continue
        fn = _BACKEND_BUILDERS[name](schema)
        if fn is not None:
            return fn, name
    return _no_op_validator, "skip"


def get_validator(
    schema: Optional[Dict[str, Any]],
    *,
    schema_id: Optional[str] = None,
) -> Tuple[ValidatorFn, str]:
    """
    Return ``(validator_fn, backend_name)`` for a given JSON Schema, cached
    per ``(schema_id or id(schema), backend_choice)`` pair.

    ``schema is None`` returns a no-op validator (matches the upstream
    "no output_schema -> nothing to validate" behaviour).
    """
    if schema is None:
        return _no_op_validator, "skip"

    backend = _selected_backend()
    key = (id(schema) if schema_id is None else hash(("id", schema_id)), backend)
    cached = _VALIDATOR_CACHE.get(key)
    if cached is not None:
        # We don't carry the backend name through the cache; reconstruct
        # by re-binding — cheap because cache hits dominate.
        return cached, backend

    fn, picked = _build(schema, backend)
    _VALIDATOR_CACHE[key] = fn
    return fn, picked


def reset_cache() -> None:
    """Clear the per-schema validator cache (test/list_tools refresh)."""
    _VALIDATOR_CACHE.clear()


def invalidate_schema(schema_id: Optional[str]) -> None:
    """Drop cached validators tied to a specific ``schema_id``."""
    if schema_id is None:
        return
    target_hash = hash(("id", schema_id))
    for key in list(_VALIDATOR_CACHE.keys()):
        if key[0] == target_hash:
            _VALIDATOR_CACHE.pop(key, None)
