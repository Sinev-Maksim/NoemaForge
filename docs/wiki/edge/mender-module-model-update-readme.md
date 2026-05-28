# Mender Update Module placeholder

This directory is an offline contract placeholder for a future Mender Update Module.
It intentionally performs no host/device update work in the prelaunch package.

The executable implementation must preserve the OTA contract:

- install only signed manifest-backed model/container/gateway bundles;
- stage rollout through shadow/canary/stable;
- hold activation until `/health`, `/ready`, and `/metrics` gates pass;
- rollback to the previous bundle on health or activation failure.
