"""Time-step aggregation rules (ontology 0.8.0).

Time steps are four ordered classes: SubHourly < Hourly < Daily < MonthlyOrLonger.
The order comes from the ontology (minStepHours), never from the names.

The one idea behind every rule: values can be summed or averaged from a FINE step to
a COARSE step without loss, but cannot be split from coarse to fine without inventing
information.

Everything here is a pure function: 'hours' is {time-step id: minStepHours}.
"""

DISAGGREGATION_WARNING = (
    "This method needs data at a finer time step than yours. Splitting daily values "
    "into hours biases intensity-driven processes (infiltration-excess runoff, flood peaks)."
)


def finest(hours: dict[str, float], steps) -> float | None:
    """Smallest step (in hours) of a list of time-step classes, None if the list is empty."""
    known = [hours[s] for s in steps if s in hours]
    return min(known) if known else None


def coarsest(hours: dict[str, float], steps) -> float | None:
    known = [hours[s] for s in steps if s in hours]
    return max(known) if known else None


def usable_as_is(hours, supports, data_step: str) -> bool:
    """Rule A (data -> method): the data is as fine as, or finer than, a step the method runs at.

    Nothing recorded for the method means we cannot tell: it is not blocked.
    """
    top = coarsest(hours, supports)
    return top is None or data_step not in hours or top >= hours[data_step]


def can_deliver(hours, supports, output_step: str) -> bool:
    """Rule B (method -> results): the method runs as finely as, or finer than, the step wanted."""
    low = finest(hours, supports)
    return low is None or output_step not in hours or low <= hours[output_step]


def dataset_ok(hours, data_step: str | None, supports) -> bool:
    """Rule C (dataset -> method): the dataset is fine enough for the method.

    Static layers (DEM, soil map) have no time step and always pass.
    """
    top = coarsest(hours, supports)
    return data_step is None or data_step not in hours or top is None or hours[data_step] <= top


def step_ok(hours, supports_upstream, supports_downstream) -> bool:
    """Rule D (producer -> consumer in a chain): the upstream method can run at least as finely."""
    low = finest(hours, supports_upstream)
    top = coarsest(hours, supports_downstream)
    return low is None or top is None or low <= top


def order(hours, steps) -> list[str]:
    """Time-step ids from the finest to the coarsest."""
    return sorted((s for s in steps if s in hours), key=lambda s: hours[s])
