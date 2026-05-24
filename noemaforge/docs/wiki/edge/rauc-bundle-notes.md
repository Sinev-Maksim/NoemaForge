# RAUC Bundle Notes

NoemaForge treats RAUC as a future signed-bundle transport, not as a runtime dependency for this prelaunch package.

The OTA contract requires a candidate bundle, a previous bundle, release evidence, signed model manifest references and a health gate before activation.
Any future RAUC bundle must map its slot status into the same `OTAUpdateLayerPolicy` report before promotion.

The practical alpha direction is to keep RAUC behind the Edge/TinyML/OTA contract. A bundle can be considered only after model manifests are signed, fallback rules are declared, target health is measured before and after activation, and rollback evidence is attached to the release record. This prevents the update transport from becoming a shortcut around NoemaForge governance.

RAUC-specific slot names, bootloader state and bundle signatures should be translated into neutral NoemaForge evidence fields. The release gate should be able to compare RAUC, Mender or a simpler local update path through the same policy vocabulary: candidate identity, prior state, activation decision, health result and rollback plan.
