# The managed edge is authorized only after live CAI/SCC evidence mapping is implemented and
# integration-tested. The application source and this code-owned local change together.
locals {
  managed_profile_implemented = false
}

check "managed_profile_is_implemented_before_serving" {
  assert {
    condition     = !var.production_edge_enabled || local.managed_profile_implemented
    error_message = "production_edge_enabled requires real, integration-tested CAI and SCC evidence mappings; see managed_readiness.py."
  }
}
