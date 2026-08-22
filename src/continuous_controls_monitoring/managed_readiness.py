"""Fail-closed declaration for the incomplete managed evidence scanner."""

from __future__ import annotations

from collections.abc import Mapping

INCOMPLETE_MANAGED_OPERATIONS: tuple[str, ...] = (
    "evidence_scanner.CloudEvidenceScanner._from_asset_inventory",
    "evidence_scanner.CloudEvidenceScanner._from_scc",
)


def _incomplete_operations_for_bindings(
    profile: str, adapters: Mapping[str, Mapping[str, str]] | None
) -> tuple[str, ...]:
    """Return only placeholders that the selected binding map would actually execute."""
    if adapters is None:
        return INCOMPLETE_MANAGED_OPERATIONS
    active_targets = {str(table.get(profile, "")) for table in adapters.values()}
    active: list[str] = []
    for operation in INCOMPLETE_MANAGED_OPERATIONS:
        module_name, class_name, *_ = operation.split(".")
        binding_suffix = f".{module_name}:{class_name}"
        if any(target.endswith(binding_suffix) for target in active_targets):
            active.append(operation)
    return tuple(active)


def assert_managed_profile_ready(
    profile: str, adapters: Mapping[str, Mapping[str, str]] | None = None
) -> None:
    """Refuse a managed process only when its active bindings contain placeholders."""
    incomplete = _incomplete_operations_for_bindings(profile, adapters)
    if profile in {"gcp", "platform"} and incomplete:
        operations = ", ".join(incomplete)
        raise RuntimeError(
            "managed profile is not production ready; implement and integration-test these "
            f"operations before serving {profile}: {operations}"
        )


def main() -> None:
    """Run the same fail-closed preflight used by every production container."""
    from .config import Settings, resolve_profile

    choice = resolve_profile()
    assert_managed_profile_ready(choice.profile, Settings.load().adapters)


if __name__ == "__main__":  # pragma: no cover - exercised by the container command
    main()
