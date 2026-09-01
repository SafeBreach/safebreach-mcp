"""
Plan statistics scoring.

Wraps the orchestrator ``POST /plan/statistics`` endpoint, which answers
"given this configuration, what would actually run" for a plan that need not
have been saved. The endpoint natively resolves a saved plan when the body
carries ``id``, and the scenario behind a past run when it carries ``testId``,
so both are scored by passthrough rather than by a client-side fetch. ``planId``
is in the request schema but is destructured by nothing and silently ignored.

Counts arrive nullable: ``None`` means *not computed* (Core stopped early on a
limit-reached response), while ``0`` means *in scope, runs nowhere*. Nothing
here defaults one to the other, and no count is compared or summed without
first establishing it is an integer.

Results are never cached — a re-check after a changed decision must not be
answered from a stale local copy.

Usage::

    from safebreach_mcp_core.plan_statistics import fetch_plan_statistics

    # Score an ad-hoc plan that was never saved
    result = fetch_plan_statistics(
        console="pentest01",
        plan={"name": "", "steps": [{...}, {...}]},
    )
    result["steps"][0]["simulationCount"]   # int, or None when not computed
    result["truncated"]                     # Core stopped early

    # Score a saved scenario by id
    result = fetch_plan_statistics(console="pentest01", scenario_id="3b8eade5-...")

    # Score whatever a past run actually executed
    result = fetch_plan_statistics(console="pentest01", test_id="1764165600525.2")
"""

import logging
from urllib.parse import urlencode

import requests
from safebreach_mcp_core.secret_utils import get_auth_headers_for_console, check_rbac_response
from safebreach_mcp_core.environments_metadata import get_api_base_url, get_api_account_id

logger = logging.getLogger(__name__)

STATISTICS_TIMEOUT_SECONDS = 120

DEFAULT_LIMIT = 500000
DEFAULT_INCLUDE_DISABLED = False
DEFAULT_GET_CONSTRAINTS = True
DEFAULT_GET_ALL_CONSTRAINTS = True
DEFAULT_USE_CACHE = True

_STEP_MAP_FIELDS = (
    'moves',
    'simulators',
    'attackerSimulators',
    'targetSimulators',
    'simulatorConstraints',
)


class PlanHasNoStepsError(ValueError):
    """A plan body carried no steps, so there is nothing to score."""


class PlanStatisticsAPIError(ValueError):
    """The statistics endpoint rejected the request; the message carries its body."""


class PastRunHasNoScenarioError(ValueError):
    """A past run's summary no longer carries the scenario it ran, so it cannot be scored.

    Not named for the API's ``originalPlan`` field: a ``Test``-prefixed class is
    swept up by pytest's collector in any module that imports it.
    """


def _is_computed_count(value) -> bool:
    """Whether a count is a real number rather than 'not computed'.

    The single arbiter of the null-safety rule — bools are excluded so a stray
    ``False`` cannot read as ``0``.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def _build_request_body(plan, scenario_id, test_id=None) -> dict:
    """Build the ValidatePlan body for an ad-hoc plan, a saved scenario or a past run.

    ``planId`` is never written: it exists in the request schema, but the
    controller destructures only ``{id, testId}``, so a body carrying it looks
    correct, falls through to the inline branch and is scored as an empty plan.

    ``name`` is always present. The schema requires it and the request is
    validated at the edge, so an id-only body still carries one; it is
    unconstrained, and "" is what the console's own UI posts.
    """
    supplied = [value is not None for value in (plan, scenario_id, test_id)]
    if sum(supplied) != 1:
        raise ValueError(
            "Provide exactly one of 'plan' (an ad-hoc plan body), 'scenario_id' "
            "(a saved scenario) or 'test_id' (the planRunId of a past run) — "
            "not several, and not none."
        )

    if scenario_id is not None:
        return {"name": "", "id": scenario_id}

    if test_id is not None:
        return {"name": "", "testId": test_id}

    if not isinstance(plan, dict):
        raise ValueError(
            f"'plan' must be a plan body dict, got {type(plan).__name__}. "
            "Pass the parsed object, not a JSON string."
        )

    body = dict(plan)
    body.setdefault("name", "")
    if not body.get("steps"):
        raise PlanHasNoStepsError(
            "Cannot score a plan with no steps: the statistics endpoint answers a "
            "step-less plan with 400 NOT_ALLOWED. This is expected while a plan is "
            "still being built — add at least one step, then score it."
        )
    return body


def _build_url(console: str, params: dict) -> str:
    """Build the statistics URL with every parameter escaped.

    urlencode rather than string joining: these values reach us from an MCP tool
    call, so an unescaped one could inject its own query parameters and silently
    rewrite the others.
    """
    base_url = get_api_base_url(console, 'orchestrator')
    account_id = get_api_account_id(console)
    query = urlencode({
        key: str(value).lower() if isinstance(value, bool) else value
        for key, value in params.items()
    })
    return (
        f"{base_url}/api/orch/v1/accounts/{account_id}/plan/statistics?{query}"
    )


def _normalize_step(raw: dict, index: int) -> dict:
    """Project one response step, preserving every count exactly as it arrived.

    Counts keep their exact value, including None. The map fields themselves are
    normalized to {} when absent — an absent map means "no entries", which is not
    the null-versus-zero distinction; that distinction lives in the map's values,
    which are passed through untouched.
    """
    simulation_count = raw.get('simulationCount')
    is_limit_reached = bool(raw.get('isLimitReached'))

    step = {
        # Indexes the RETURNED list, which is shorter than the plan's when Core
        # truncates — never treat it as a plan-step position.
        'response_step_index': index,
        # No default: an absent count is 'not computed', never 0.
        'simulationCount': simulation_count,
        # False when this step's own count is missing, or when this step is the
        # one Core stopped on — a step computed before that keeps True.
        'counts_computed': _is_computed_count(simulation_count) and not is_limit_reached,
        'isLimitReached': is_limit_reached,
    }
    for field in _STEP_MAP_FIELDS:
        value = raw.get(field)
        step[field] = value if isinstance(value, dict) else {}
    return step


def fetch_plan_statistics(
    console: str,
    plan: dict | None = None,
    scenario_id: str | int | None = None,
    test_id: str | None = None,
    *,
    include_disabled: bool = DEFAULT_INCLUDE_DISABLED,
    get_constraints: bool = DEFAULT_GET_CONSTRAINTS,
    get_all_constraints: bool = DEFAULT_GET_ALL_CONSTRAINTS,
    limit: int = DEFAULT_LIMIT,
    use_cache: bool = DEFAULT_USE_CACHE,
) -> dict:
    """
    Score a plan against a console and return the response unreduced.

    Args:
        console: SafeBreach console identifier
        plan: An ad-hoc plan body; ``name`` defaults to ``""`` when absent.
            Mutually exclusive with ``scenario_id`` and ``test_id``.
        scenario_id: A saved scenario, passed as ``id`` for native resolution.
            Mutually exclusive with ``plan`` and ``test_id``.
        test_id: The planRunId of a past run, passed as ``testId``; the endpoint
            resolves it to the scenario that run actually executed. Mutually
            exclusive with ``plan`` and ``scenario_id``.
        include_disabled: ``True`` scores every simulator (expected counts);
            ``False`` scores only those that could run now (runnable counts).
        get_constraints: Populate ``simulatorConstraints`` and the response's
            own ``constraintCatalog``.
        get_all_constraints: Report every reason per pairing, not just the first.
        limit: Upper bound on simulations Core will evaluate before stopping.
        use_cache: Whether Core may answer from its own cache.

    Returns:
        A dict with ``steps`` (each carrying the six response fields unmodified,
        plus ``isLimitReached``, ``counts_computed`` and ``response_step_index``
        — an index into the *returned* list, which is shorter than the plan's
        when ``truncated`` is set, so it is not a plan-step position),
        ``constraint_catalog`` (the response root's, verbatim; ``None`` when the
        console supplied none, ``{}`` when it supplied an empty one),
        ``plan_step_count`` (``None`` on the ``scenario_id`` and ``test_id``
        paths, where it is not knowable client-side), ``returned_step_count``,
        ``truncated``, and ``params_used``.

    Raises:
        PlanHasNoStepsError: the plan body carried no steps (before any request).
        ValueError: other than exactly one of ``plan``, ``scenario_id`` and
            ``test_id`` was given.
        PastRunHasNoScenarioError: the past run's summary no longer carries the
            scenario it ran, so the endpoint cannot reconstruct it.
        PlanStatisticsAPIError: the endpoint returned a non-2xx; the message
            carries the full response body.
        PermissionError: the caller's role may not score plans (403).
    """
    body = _build_request_body(plan, scenario_id, test_id)

    params = {
        "limit": int(limit),
        "includeDisabled": include_disabled,
        "getConstraints": get_constraints,
        "getAllConstraints": get_all_constraints,
        "useCache": use_cache,
    }
    api_url = _build_url(console, params)
    headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}

    response = requests.post(
        api_url, headers=headers, json=body, timeout=STATISTICS_TIMEOUT_SECONDS
    )
    try:
        # Only HTTPError is caught: a 403 raises PermissionError, which carries
        # its own RBAC hint and must reach the caller unchanged.
        check_rbac_response(response)
    except requests.exceptions.HTTPError as exc:
        error_body = getattr(response, 'text', '')
        logger.error(f"Statistics API error {response.status_code}: {error_body}")
        if test_id is not None and 'originalPlan' in error_body:
            raise PastRunHasNoScenarioError(
                f"Test '{test_id}' cannot be scored: its summary no longer carries the "
                f"scenario that ran, which SafeBreach needs to reconstruct the plan. "
                f"Score the saved scenario with 'scenario_id', or pass an ad-hoc 'plan'."
            ) from exc
        raise PlanStatisticsAPIError(
            f"Statistics API error ({response.status_code}): {error_body}"
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        # A 2xx carrying a non-JSON body — a proxy or gateway page, typically.
        raise PlanStatisticsAPIError(
            f"Statistics API returned a non-JSON body ({response.status_code}): "
            f"{getattr(response, 'text', '')[:500]}"
        ) from exc
    # The envelope is inconsistent: swagger documents a `data` wrapper while the
    # endpoint's own component tests show `steps` at the top level (SAF-32019).
    # Accept either — reading an unwrapped body as absent would report a scored
    # plan as having no steps at all, which is exactly the silent-empty result
    # the null-versus-zero rule exists to prevent.
    data = payload if isinstance(payload, dict) else {}
    wrapped = data.get('data')
    if isinstance(wrapped, dict):
        data = wrapped

    raw_steps = data.get('steps')
    if not isinstance(raw_steps, list):
        raw_steps = []
    # Enumerate the filtered list so response_step_index has no gaps.
    steps = [
        _normalize_step(raw, i)
        for i, raw in enumerate(raw for raw in raw_steps if isinstance(raw, dict))
    ]

    catalog = data.get('constraintCatalog')
    constraint_catalog = catalog if isinstance(catalog, dict) else None

    # Knowable only on the ad-hoc path: an id-resolved plan is expanded
    # server-side, so how many steps it holds is not visible from here.
    plan_step_count = len(body["steps"]) if plan is not None else None
    returned_step_count = len(steps)
    truncated = any(step['isLimitReached'] for step in steps) or (
        plan_step_count is not None and returned_step_count < plan_step_count
    )

    logger.info(
        f"Plan statistics for console '{console}': {returned_step_count} step(s) returned"
        f"{' (truncated)' if truncated else ''}, params={params}"
    )

    return {
        "steps": steps,
        "constraint_catalog": constraint_catalog,
        "plan_step_count": plan_step_count,
        "returned_step_count": returned_step_count,
        "truncated": truncated,
        "params_used": dict(params),
    }
