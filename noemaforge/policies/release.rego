# release.rego — Release gate policy
#
# This file is a POLICY-AS-DATA artifact for documentation and review in 0.32.2.
# Active enforcement by "noema release verify" and the release-gate CI workflow
# are planned for 0.33.0.
#
# Intent: a release is publishable only when ALL of the following hold:
#   1. The manifest conforms to the release-manifest schema.
#   2. Every artifact hash in the manifest matches the actual content.
#   3. The manifest's contract_epoch is a known, non-revoked epoch.
#   4. The manifest carries a valid signature (when signing is enforced).
#   5. The release version matches the version source of truth.
#   6. All required smoke-test evidence artifacts are present.

package noemaforge.release

import rego.v1

default publishable := false

publishable if {
    manifest_valid
    all_hashes_match
    epoch_valid
    version_consistent
    smoke_evidence_present
}

manifest_valid if {
    input.manifest.apiVersion == "noemaforge.release-manifest/v1"
    count(input.manifest.artifacts) > 0
}

all_hashes_match if {
    count([a | a := input.manifest.artifacts[_]; a.sha256 != input.content_hashes[a.path]]) == 0
}

epoch_valid if {
    data.epochs[input.manifest.contract_epoch]
    not data.revoked_epochs[input.manifest.contract_epoch]
}

version_consistent if {
    input.manifest.version == data.version_source_of_truth
}

smoke_evidence_present if {
    # At minimum the premerge quality gate evidence must be recorded as passing.
    input.evidence.premerge_quality_gate == "pass"
}

violations contains msg if {
    not manifest_valid
    msg := "release manifest is missing required fields or has wrong apiVersion"
}

violations contains msg if {
    not epoch_valid
    msg := sprintf("epoch %q is unknown or revoked", [input.manifest.contract_epoch])
}

violations contains msg if {
    not version_consistent
    msg := sprintf("manifest version %q does not match version source of truth %q",
                   [input.manifest.version, data.version_source_of_truth])
}

violations contains msg if {
    not smoke_evidence_present
    msg := "premerge quality gate evidence is missing or did not pass"
}
