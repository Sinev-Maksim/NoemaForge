# RAUC Bundle Notes

NoemaForge treats RAUC as a future signed-bundle transport, not as a runtime dependency for this prelaunch package.

The OTA contract requires a candidate bundle, a previous bundle, release evidence, signed model manifest references and a health gate before activation.
Any future RAUC bundle must map its slot status into the same `OTAUpdateLayerPolicy` report before promotion.
