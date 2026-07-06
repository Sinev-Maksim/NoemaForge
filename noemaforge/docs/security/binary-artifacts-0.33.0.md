# Binary artifact policy for 0.33.0

NoemaForge intentionally ships `noemaforge/bin/noemaforge-llm-gateway` because
the target host service unit executes `/opt/noemaforge/bin/noemaforge-llm-gateway`.
The corresponding source is `noemaforge/src/noemaforge-llm-gateway.go`.

Release handling:

- Do not delete the binary during code-scanning remediation; that would break
  the packaged gateway service path.
- Do not treat a local source edit as binary provenance. If the Go source
  changes for a release, rebuild the binary in the approved release build lane,
  run `gofmt` and targeted gateway smoke/unit checks, and regenerate manifests
  and checksums after the binary is updated.
- Reviewers must compare the shipped binary timestamp/checksum with the source
  commit used for the release build. If that evidence is missing, keep
  BinaryArtifactsID open as a hardening follow-up rather than marking it fixed.
