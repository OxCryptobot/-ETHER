# Clear Quartz

**Role**: Sandbox & Validation Engine

## Profiles

- `fast` — Docker with network disabled, read-only rootfs, 512MB memory limit
- `strict` — (Future) Firecracker microVM + deeper analysis

## Security Model

1. AST + name blacklist (defense-in-depth)
2. Docker isolation (real security boundary)
3. No network, no Docker socket, limited resources

## Status

- Basic Docker execution: implemented
- Static analysis: basic AST walk
- Test counting: placeholder (pytest integration next)
- Strict profile: not yet implemented
