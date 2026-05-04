# Releasing MONK-system

MONK-system follows [Semantic Versioning](https://semver.org/). The version
lives in `monksystem/monksystem/__init__.py` (`__version__`) and is exposed
to templates as `MONK_VERSION` (rendered in the page footer).

While the project is pre-1.0, breaking schema or workflow changes bump the
**minor** number; bug fixes bump the **patch** number.

## Cutting a release

1. Decide the new version (e.g. `0.2.0`).
2. Update `monksystem/monksystem/__init__.py` — `__version__ = "X.Y.Z"`.
3. Move the `[Unreleased]` entries in `CHANGELOG.md` under a new
   `## [X.Y.Z] - YYYY-MM-DD` heading.
4. Commit:
   ```
   git commit -am "Release vX.Y.Z"
   ```
5. Tag and push:
   ```
   git tag -a vX.Y.Z -m "MONK-system X.Y.Z"
   git push origin main --tags
   ```

## Scope

This version covers the Django application in this repository only.
`python-monklib` is pinned independently via the MONK-library Guix
channel, and the kiosk OS image is versioned in its own repo. A given
deployment is therefore a tuple of (MONK-system tag, monklib commit,
kiosk image build) — record all three when capturing a known-good
configuration.
