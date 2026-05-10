"""
Property-based tests for the AgentCore Policy Engine feature.

Feature: agentcore-policy-engine

This module validates the Cedar `when` clause logic and resource name
constraints for the three CloudFormation resources provisioned by the
policy engine feature:
  - PolicyEngine  (AWS::BedrockAgentCore::PolicyEngine)
  - PermitPolicy  (AWS::BedrockAgentCore::Policy)
  - ForbidPolicy  (AWS::BedrockAgentCore::Policy)

Properties tested
-----------------
Property 1: ForbidPolicy blocks orders with qty >= 100
    For any createOrder / updateOrder request where context.input.qty >= 100,
    the Cedar forbid `when` clause evaluates to True (deny the request).
    Validates: Requirements 3.5, 3.6

Property 2: ForbidPolicy permits orders with qty < 100
    For any request where context.input.qty < 100, the `when` clause
    evaluates to False (request is not denied by the forbid policy).
    Validates: Requirement 3.5

Property 3: ForbidPolicy permits requests without qty field
    For any request where context has no `input` field, or `input` has no
    `qty` field, the `when` clause evaluates to False (safe navigation
    prevents errors; request is not denied).
    Validates: Requirement 3.5

Property 4: Resource names fit within 48-character limit
    For any combination of allowed Environment values (dev, staging, prod)
    and a 12-character DeploymentSuffix (yyyymmddHHMM), all three generated
    resource names have length <= 48 characters.
    Validates: Requirements 6.1, 6.2, 6.3, 6.4

Property 5: Resource names match the AWS name pattern
    For any combination of allowed Environment values and a valid
    DeploymentSuffix, all three generated resource names match the regex
    ^[A-Za-z][A-Za-z0-9_]*$
    Validates: Requirements 1.2, 2.2, 3.2
"""

import re
import unittest

# ---------------------------------------------------------------------------
# Hypothesis import guard — mirrors the project's existing pattern so the
# test suite degrades gracefully when hypothesis is not installed.
# ---------------------------------------------------------------------------
try:
    from hypothesis import given, settings, strategies as st
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False
    print("Warning: hypothesis not available, property tests will be skipped")

    # Dummy decorators so the class definitions below remain valid Python
    # even without hypothesis installed.
    def given(*args, **kwargs):
        def decorator(func):
            return lambda self: self.skipTest("Hypothesis not installed")
        return decorator

    def settings(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    class st:  # noqa: N801  (intentional lowercase to match hypothesis API)
        """Minimal stub that satisfies the strategy references in @given."""

        @staticmethod
        def integers(**kwargs):
            class _S:
                pass
            return _S()

        @staticmethod
        def one_of(*args):
            class _S:
                pass
            return _S()

        @staticmethod
        def just(value):
            class _S:
                pass
            return _S()

        @staticmethod
        def fixed_dictionaries(mapping):
            class _S:
                pass
            return _S()

        @staticmethod
        def text(**kwargs):
            class _S:
                pass
            return _S()

        @staticmethod
        def sampled_from(items):
            class _S:
                pass
            return _S()

        @staticmethod
        def from_regex(pattern, **kwargs):
            class _S:
                pass
            return _S()


# ---------------------------------------------------------------------------
# Helper: Cedar `when` clause mirror
# ---------------------------------------------------------------------------

def evaluate_forbid_when_clause(context: dict) -> bool:
    """Mirror the Cedar ForbidPolicy ``when`` clause in Python.

    Cedar source::

        when {
            ((context has input) && ((context.input) has qty)) &&
            (!(((context.input).qty) < 100))
        };

    Returns ``True`` when the forbid should trigger (i.e. the request should
    be denied), ``False`` otherwise.

    The function uses the same safe-navigation semantics as Cedar:
    - If ``context`` has no ``input`` key  → return False (no deny)
    - If ``context["input"]`` has no ``qty`` key → return False (no deny)
    - Otherwise deny when ``qty >= 100``

    Args:
        context: A dict representing the Cedar request context, e.g.
                 ``{"input": {"qty": 150}}``.

    Returns:
        bool: True if the forbid clause matches (deny), False otherwise.
    """
    # Cedar: (context has input)
    if "input" not in context:
        return False

    # Cedar: ((context.input) has qty)
    if "qty" not in context["input"]:
        return False

    # Cedar: !(((context.input).qty) < 100)  →  qty >= 100
    return not (context["input"]["qty"] < 100)


# ---------------------------------------------------------------------------
# Helper: resource name generator
# ---------------------------------------------------------------------------

def generate_resource_names(env: str, suffix: str) -> list[str]:
    """Return the three CloudFormation resource names for a given deployment.

    The naming convention follows the pattern used in ``agentcore-app-stack.yaml``
    (underscores, no hyphens) and matches the regex ``^[A-Za-z][A-Za-z0-9_]*$``.

    Args:
        env:    Deployment environment, e.g. ``"dev"``, ``"staging"``, ``"prod"``.
        suffix: DeploymentSuffix parameter value, e.g. ``"202605071814"``
                (12-character timestamp in yyyymmddHHMM format).

    Returns:
        list[str]: Three names in order:
            1. PolicyEngine  name: ``{env}_orders_gateway_policy_{suffix}``
            2. PermitPolicy  name: ``{env}_permit_orders_policy_{suffix}``
            3. ForbidPolicy  name: ``{env}_forbid_orders_policy_{suffix}``
    """
    return [
        f"{env}_orders_gateway_policy_{suffix}",
        f"{env}_permit_orders_policy_{suffix}",
        f"{env}_forbid_orders_policy_{suffix}",
    ]


# ---------------------------------------------------------------------------
# Compiled regex used by Property 5
# ---------------------------------------------------------------------------
_AWS_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestAgentCorePolicyEngineProperties(unittest.TestCase):
    """Property-based tests for the AgentCore Policy Engine feature."""

    # ------------------------------------------------------------------
    # Property 1 — ForbidPolicy blocks orders with qty >= 100
    # ------------------------------------------------------------------

    @given(qty=st.integers(min_value=100))
    @settings(max_examples=100)
    def test_property_1_forbid_when_clause_matches_qty_gte_100(self, qty: int) -> None:
        """Property 1: ForbidPolicy blocks orders with qty >= 100.

        For any integer qty >= 100, the Cedar forbid ``when`` clause must
        evaluate to True, meaning the request is denied.

        Validates: Requirements 3.5, 3.6
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")

        context = {"input": {"qty": qty}}
        result = evaluate_forbid_when_clause(context)

        self.assertIs(
            result,
            True,
            f"Expected forbid clause to match (deny) for qty={qty}, got False",
        )

    # ------------------------------------------------------------------
    # Property 2 — ForbidPolicy permits orders with qty < 100
    # ------------------------------------------------------------------

    @given(qty=st.integers(max_value=99))
    @settings(max_examples=100)
    def test_property_2_forbid_when_clause_does_not_match_qty_lt_100(self, qty: int) -> None:
        """Property 2: ForbidPolicy permits orders with qty < 100.

        For any integer qty < 100, the Cedar forbid ``when`` clause must
        evaluate to False, meaning the request is NOT denied by the forbid
        policy (the permit policy wins).

        Validates: Requirement 3.5
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")

        context = {"input": {"qty": qty}}
        result = evaluate_forbid_when_clause(context)

        self.assertIs(
            result,
            False,
            f"Expected forbid clause NOT to match (permit) for qty={qty}, got True",
        )

    # ------------------------------------------------------------------
    # Property 3 — ForbidPolicy permits requests without qty field
    # ------------------------------------------------------------------

    @given(
        context=st.one_of(
            # Case A: no input field at all
            st.just({}),
            # Case B: input field present but empty
            st.just({"input": {}}),
            # Case C: input field present with other fields but no qty
            st.fixed_dictionaries(
                {"input": st.fixed_dictionaries({"other_field": st.text()})}
            ),
        )
    )
    @settings(max_examples=100)
    def test_property_3_forbid_when_clause_safe_navigation(self, context: dict) -> None:
        """Property 3: ForbidPolicy permits requests without qty field.

        When the context has no ``input`` key, or ``input`` has no ``qty``
        key, the Cedar safe-navigation semantics must prevent an error and
        the ``when`` clause must evaluate to False (no deny).

        Validates: Requirement 3.5
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")

        result = evaluate_forbid_when_clause(context)

        self.assertIs(
            result,
            False,
            f"Expected forbid clause NOT to match for context without qty: {context!r}",
        )

    # ------------------------------------------------------------------
    # Property 4 — Resource names fit within 48-character limit
    # ------------------------------------------------------------------

    @given(
        env=st.sampled_from(["dev", "staging", "prod"]),
        suffix=st.from_regex(r"[0-9]{12}", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_property_4_resource_names_within_48_chars(self, env: str, suffix: str) -> None:
        """Property 4: Resource names fit within 48-character limit.

        For any allowed Environment value and a 12-character DeploymentSuffix,
        all three generated resource names must have length <= 48 characters.

        The tightest case is ``staging_orders_gateway_policy_<12-char-suffix>``
        at 42 characters, leaving 6 characters of headroom.

        Validates: Requirements 6.1, 6.2, 6.3, 6.4
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")

        names = generate_resource_names(env, suffix)

        for name in names:
            self.assertLessEqual(
                len(name),
                48,
                f"Resource name exceeds 48-character AWS limit: {name!r} ({len(name)} chars)",
            )

    # ------------------------------------------------------------------
    # Property 5 — Resource names match the AWS name pattern
    # ------------------------------------------------------------------

    @given(
        env=st.sampled_from(["dev", "staging", "prod"]),
        suffix=st.from_regex(r"[0-9]{12}", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_property_5_resource_names_match_aws_pattern(self, env: str, suffix: str) -> None:
        """Property 5: Resource names match the AWS name pattern.

        For any allowed Environment value and a valid DeploymentSuffix, all
        three generated resource names must match ``^[A-Za-z][A-Za-z0-9_]*$``.

        This ensures names start with a letter and contain only alphanumeric
        characters and underscores — the pattern required by
        AWS::BedrockAgentCore resources.

        Validates: Requirements 1.2, 2.2, 3.2
        """
        if not HYPOTHESIS_AVAILABLE:
            self.skipTest("Hypothesis not installed")

        names = generate_resource_names(env, suffix)

        for name in names:
            self.assertRegex(
                name,
                _AWS_NAME_PATTERN,
                f"Resource name does not match AWS name pattern: {name!r}",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
