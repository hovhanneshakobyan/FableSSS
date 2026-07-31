---
name: changelog-maintenance
description: Add and format entries in CHANGELOG.md following Keep a Changelog conventions. Use when the user asks to update the changelog, log a change for release notes, or after completing a user-facing feature or fix.
---

# Changelog Maintenance

Follows [Keep a Changelog](https://keepachangelog.com/) format.

## File structure

```markdown
# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added
- New feature description.

### Changed
- Behavior change description.

### Fixed
- Bug fix description.

### Removed
- Removed feature description.

## [0.1.0] - YYYY-MM-DD

### Added
- Initial release.
```

If `CHANGELOG.md` doesn't exist yet, create it with this structure the first
time an entry is needed.

## Workflow

1. Determine the category: `Added`, `Changed`, `Fixed`, `Removed`,
   `Deprecated`, or `Security`.
2. Add a single-line, user-facing entry under `[Unreleased]` in the right
   category (create the category heading if missing).
3. Write from the user's perspective, not the implementation's:
   - ✅ "Fixed crash when loading an empty config file."
   - ❌ "Added null check in `load_config`."
4. On release, rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD` and add a fresh
   empty `[Unreleased]` section above it.

## Checklist

- [ ] Entry is under the correct category
- [ ] Entry is user-facing, not implementation detail
- [ ] Entry is one concise line
- [ ] `[Unreleased]` section exists for future entries
