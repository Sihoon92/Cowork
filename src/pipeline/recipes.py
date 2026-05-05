"""Recipe engine — semantic slide layouts compiled to primitive instances.

A *recipe* is a named slide layout pattern (e.g. `matrix_2x2_compare`,
`headline_metric`, `as_is_to_be`). The LLM picks a recipe by name and fills
in its data; the recipe's compile function turns that data into a list of
`PrimitiveSpec`s, which the renderer draws inside the slide body.

Compile responsibilities:
- Build the Grid that splits the body Rect.
- Decide which primitive goes in which cell.
- Hand each primitive its own Rect + data.

What the recipe does NOT decide:
- Theme colors / fonts (deck_meta).
- Header / footer (apply_master).
- The actual draw (primitives.py functions).

This separation keeps recipes pure data → spec functions, easily unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict

from pydantic import BaseModel

from src.pptx.primitives import Rect


@dataclass(frozen=True)
class PrimitiveSpec:
    """One drawable primitive inside a slide body.

    `name` is a key into the renderer's primitive draw-function registry.
    `rect` is the absolute Rect (in inches, slide-relative).
    `data` is the primitive-specific data dict.
    """
    name: str
    rect: Rect
    data: dict


# Type aliases for clarity in registrations
RecipeCompileFn = Callable[[Any, Rect], list[PrimitiveSpec]]
"""Signature: (data_model_instance, body_rect) -> list[PrimitiveSpec]"""


@dataclass(frozen=True)
class RecipeEntry:
    """Registry entry: data model + compile function + summary string.

    `apply_master`: if True, render_slide_recipe paints the 3-tier header and
    passes the resulting body Rect to the compiler. If False, the compiler
    receives the full canvas Rect (cover/thesis-style slides).
    """
    name: str
    data_model: type[BaseModel]
    compile_fn: RecipeCompileFn
    summary: str  # one-line description; used by the LLM-facing catalog
    apply_master: bool = True


RECIPES: Dict[str, RecipeEntry] = {}


def register(entry: RecipeEntry) -> None:
    """Register a recipe. Raises if the name is already taken."""
    if entry.name in RECIPES:
        raise ValueError(f"recipe already registered: {entry.name!r}")
    RECIPES[entry.name] = entry


def get_recipe(name: str) -> RecipeEntry:
    if name not in RECIPES:
        raise KeyError(
            f"unknown recipe: {name!r}. Available: {sorted(RECIPES)}"
        )
    return RECIPES[name]


def compile_recipe(name: str, raw_data: dict, body: Rect) -> list[PrimitiveSpec]:
    """Validate raw_data against the recipe's data model and compile to specs.

    Raises pydantic ValidationError if raw_data doesn't match the model.
    Raises KeyError if the recipe is unknown.
    """
    entry = get_recipe(name)
    validated = entry.data_model.model_validate(raw_data)
    return entry.compile_fn(validated, body)


# ---------------------------------------------------------------------------
# Concrete recipes are registered in submodules. Importing them here ties
# them into the global RECIPES registry as a side effect.
# ---------------------------------------------------------------------------

# Importing a recipe module is what registers its recipes — the imports below
# are deliberate side-effect imports.
from src.pipeline import recipes_matrix     # noqa: F401, E402
from src.pipeline import recipes_basic      # noqa: F401, E402
from src.pipeline import recipes_metrics    # noqa: F401, E402
from src.pipeline import recipes_narrative  # noqa: F401, E402
