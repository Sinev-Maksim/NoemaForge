# toolproxy.rego — ToolProxy deny-by-default capability policy
#
# This file is a POLICY-AS-DATA artifact for documentation and review purposes in 0.32.2.
# Active enforcement by a policy engine (e.g. OPA) and the "noema policy test" CI gate
# are planned for 0.33.0.
#
# Intent: a tool call through ToolProxy is denied unless ALL of the following hold:
#   1. The capability token is valid (not revoked, signature checks out).
#   2. The token's tool matches the requested tool exactly.
#   3. The token's scope matches the requested scope exactly.
#   4. The token's contract_epoch matches the active runtime epoch.
#   5. The token's expiry is in the future.
#   6. The active epoch's policy enables this tool.
#
# Any single failing condition results in denial; the reason is recorded in the audit trail.

package noemaforge.toolproxy

import rego.v1

default allow := false

allow if {
    input.cap.token_valid
    input.cap.tool == input.request.tool
    input.cap.scope == input.request.scope
    input.cap.contract_epoch == input.runtime.contract_epoch
    input.cap.exp_ns > time.now_ns()
    data.epochs[input.runtime.contract_epoch].tools[input.request.tool].enabled
}

deny_reason contains msg if {
    not allow
    msg := "tool access denied by ToolProxy policy"
}

# Specific denial reasons for better audit messages.

deny_reason contains msg if {
    not input.cap.token_valid
    msg := "capability token is invalid or revoked"
}

deny_reason contains msg if {
    input.cap.exp_ns <= time.now_ns()
    msg := "capability token has expired"
}

deny_reason contains msg if {
    input.cap.contract_epoch != input.runtime.contract_epoch
    msg := sprintf("token epoch %q does not match runtime epoch %q",
                   [input.cap.contract_epoch, input.runtime.contract_epoch])
}

deny_reason contains msg if {
    not data.epochs[input.runtime.contract_epoch].tools[input.request.tool].enabled
    msg := sprintf("tool %q is not enabled in epoch %q",
                   [input.request.tool, input.runtime.contract_epoch])
}
